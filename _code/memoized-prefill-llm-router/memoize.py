#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["torch", "transformers"]
# ///
"""Memoize step. Prefills the instruction block ONCE and writes the KV state
to a directory of plain files. The serving script needs nothing from this
file except that directory layout:

    memo/
      instructions.txt        exact prompt text, diffable, human editable
      version.txt             sha256(model_id + dtype + instructions)[:12]
      meta.json               model id, dtype, base_len, layer count,
                              library versions, questions + thresholds
      state/layer_00_key.pt   one tensor per cache layer (keys + values)
      state/layer_00_value.pt ...
"""
import hashlib
import importlib.metadata
import json
import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache

MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "mps" else torch.float32
OUTDIR = "memo"

BRANDS = """Nike, Adidas, Puma, Asics, New Balance, Salomon, Decathlon, Reebok,
Under Armour, Fila, Mizuno, Brooks, Saucony, Hoka, On, Merrell, The North Face,
Columbia, Patagonia, Arc'teryx, Vans, Converse, Skechers, Crocs, Birkenstock,
Clarks, Geox, ECCO, Timberland, Dr. Martens, Apple, Samsung, Sony, LG, Bosch,
Siemens, Philips, Xiaomi, OnePlus, Google, Huawei, Dell, HP, Lenovo, Asus,
Acer, Logitech, Razer, JBL, Bose, Sennheiser, Anker, Belkin, TP-Link, Netgear,
Zara, H&M, Uniqlo, Gap, Old Navy, Levi's, Wrangler, Carhartt, Dickies, IKEA,
JYSK, Leroy Merlin, C&A, Only, Vero Moda, Jack & Jones, Selected, Tommy
Hilfiger, Calvin Klein, Ralph Lauren, Lacoste, L'Oreal, Nivea, Dove, Gillette,
Oral-B, Braun, Tefal, WMF, Zwilling, Le Creuset, Pyrex, Tupperware"""

INSTRUCTIONS = """You are the query router of an ecommerce search engine.
Decide each question about the user query. User queries arrive lowercased and
whitespace-normalized; judge the words as given.

Known brands:
""" + BRANDS + """

Known categories: shoes, sandals, boots, sneakers, slippers, jackets, coats,
hoodies, t-shirts, jeans, shorts, dresses, skirts, backpacks, handbags,
wallets, watches, headphones, earbuds, speakers, phones, tablets, laptops,
monitors, keyboards, mice, televisions, fridges, washers, vacuums, cookware,
knives, towels, bedding, furniture, lamps, tools, drills, bikes, tents.

Rules:
- PRICE is yes when the query bounds a price: "under 10", "cheap", "50 to 100".
- BRAND is yes when the query mentions or hints one of the known brands,
  including a misspelled brand of something that brand makes.
- FUZZY is no when every word is a correctly spelled common word or known brand.
- FUZZY is yes when a word looks misspelled or is an unknown brand spelling.
- LOCATION is yes when a city, country, or region name appears in the query.
- CATEGORY is yes when the whole user query looks like a product category
  name or a plain category phrase: "sneakers", "running shoes", "trail boots".
- CATEGORY is no when the query adds anything beyond a category phrase: a
  price, a brand, a place, or a described need, recipient, or occasion.
- HYBRID is yes when the query describes a need, recipient, occasion, or use
  beyond naming products: "for my wife", "birthday", "long walks".
- HYBRID is no when the query only names product types, brands, model numbers,
  colors, sizes, or prices, with no described need, recipient, occasion, or use.
"""

SEMANTIC = {}   # set {"NOPLACE": "LOCATION", ...} to flip a probe's decision side

QUESTIONS = {
    "PRICE":    ["PRICE? Answer:", 0.5, False],
    "BRAND":    ["BRAND? Answer:", 0.5, False],
    "FUZZY":    ["FUZZY? Answer:", 0.5, False],
    "LOCATION": ["LOCATION? Answer:",   0.5, False],
    "HYBRID":   ["HYBRID? Answer:",     0.5, False],
    "CATEGORY": ["CATEGORY? Answer:",   0.5, False],
}

# toy labeled set; production uses hundreds of log-mined decisions
LABELS = {
    "shoes under 10":               {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "running shoes cheaper than 50": {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "nike air force 1":             {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "addidass ultraboost":          {"PRICE": 0, "BRAND": 1, "FUZZY": 1, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "running shoes from berlin":    {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "HYBRID": 1, "CATEGORY": 0},
    "sneakers":                     {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 1},
    "gift for wife birthday":       {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 1, "CATEGORY": 0},
    "comfortable shoes for long walks": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 1, "CATEGORY": 0},
    "iphone 15 pro max":            {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "womanss handbagg":             {"PRICE": 0, "BRAND": 0, "FUZZY": 1, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 1},
    "boots from madrid":            {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "HYBRID": 1, "CATEGORY": 0},
    "cheap sandals":                {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "hoka clotree for muddy trails": {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "HYBRID": 1, "CATEGORY": 0},
    "laptop under 3000 for student": {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 1, "CATEGORY": 0},
}

def main():
    tok = AutoTokenizer.from_pretrained(MODEL_ID)
    model = (AutoModelForCausalLM.from_pretrained(MODEL_ID, dtype=DTYPE)
             .to(DEVICE).eval())
    torch.set_grad_enabled(False)
    enc = lambda s: tok(s, add_special_tokens=False).input_ids
    yes, no = enc(" yes")[0], enc(" no")[0]

    # prefill once: this forward pass IS the memoization
    ids = torch.tensor([enc(INSTRUCTIONS)], device=DEVICE)
    cache = model(ids, use_cache=True).past_key_values
    state = [(l.keys.clone(), l.values.clone()) for l in cache.layers]
    base_len = ids.shape[1]
    print(f"memoized {base_len} tokens, {len(state)} layers")

    def probe(query, marker):
        fresh = DynamicCache()
        for i, (k, v) in enumerate(state):
            fresh.update(k, v, i)
        s = enc(f"\nUser query: {query}\n{marker}")
        pos = torch.arange(base_len, base_len + len(s), device=DEVICE).unsqueeze(0)
        logits = model(input_ids=torch.tensor([s], device=DEVICE),
                       past_key_values=fresh, position_ids=pos,
                       use_cache=False).logits[0, len(s) - 1]
        return float(torch.softmax(logits[[yes, no]].float(), -1)[0])

    # one threshold per question: balanced-accuracy sweep over the labels
    probs = {q: {n: probe(q, m) for n, (m, _, _) in QUESTIONS.items()} for q in LABELS}
    for name in QUESTIONS:
        sem = SEMANTIC.get(name, name)
        pts = [(probs[q][name], g[sem]) for q, g in LABELS.items() if sem in g]
        n1 = sum(1 for _, g in pts if g) or 1
        n0 = sum(1 for _, g in pts if not g) or 1
        flipped = QUESTIONS[name][2]
        best = max([i / 100 for i in range(10, 96)],
                   key=lambda t: 0.5 * (sum(int((p >= t) != flipped) == g for p, g in pts if g) / n1
                                        + sum(int((p >= t) != flipped) == g for p, g in pts if not g) / n0))
        QUESTIONS[name][1] = best
        print(f"  {name:9s} threshold={best:.2f}")

    os.makedirs(f"{OUTDIR}/state", exist_ok=True)
    with open(f"{OUTDIR}/instructions.txt", "w") as f:
        f.write(INSTRUCTIONS)
    version = hashlib.sha256(
        (MODEL_ID + str(DTYPE) + INSTRUCTIONS).encode()).hexdigest()[:12]
    with open(f"{OUTDIR}/version.txt", "w") as f:
        f.write(version)
    with open(f"{OUTDIR}/meta.json", "w") as f:
        json.dump({"model_id": MODEL_ID, "dtype": str(DTYPE), "device": DEVICE,
                   "base_len": base_len, "layers": len(state), "version": version,
                   "torch": str(torch.__version__),
                   "transformers": importlib.metadata.version("transformers"),
                   "normalize": "strip; lower; collapse whitespace",
                   "questions": QUESTIONS}, f, indent=2)
    for i, (k, v) in enumerate(state):
        torch.save(k.cpu(), f"{OUTDIR}/state/layer_{i:02d}_key.pt")
        torch.save(v.cpu(), f"{OUTDIR}/state/layer_{i:02d}_value.pt")
    total = sum(os.path.getsize(f"{OUTDIR}/state/{n}") for n in os.listdir(f"{OUTDIR}/state"))
    print(f"wrote {OUTDIR}/: version={version}, {len(state) * 2} state files, {total / 1e6:.1f} MB")

if __name__ == "__main__":
    main()
