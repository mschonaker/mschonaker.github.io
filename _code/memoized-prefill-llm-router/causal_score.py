#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["torch", "transformers"]
# ///
"""Score the memoized engine at threshold 0.5 across four scripts.
One artifact, one english prefill, english markers, no changes to the LLM.

Usage: python causal_score.py [memo-dir]"""
import json
import sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache

torch.set_grad_enabled(False)
DIRPATH = sys.argv[1] if len(sys.argv) > 1 else "memo"
meta = json.load(open(f"{DIRPATH}/meta.json"))
device = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = getattr(torch, meta["dtype"].split(".")[-1])
state = [(torch.load(f"{DIRPATH}/state/layer_{i:02d}_key.pt", map_location=device, weights_only=True),
          torch.load(f"{DIRPATH}/state/layer_{i:02d}_value.pt", map_location=device, weights_only=True))
         for i in range(meta["layers"])]
tok = AutoTokenizer.from_pretrained(meta["model_id"])
model = (AutoModelForCausalLM.from_pretrained(meta["model_id"], dtype=dtype)
         .to(device).eval())
enc = lambda s: tok(s, add_special_tokens=False).input_ids
YES = torch.tensor([enc(" yes")[0], enc(" no")[0]], device=device)
base_len, pad = meta["base_len"], tok.eos_token_id

GOLD = {
    "shoes under 10":          {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "nike air force 1":        {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "addidass ultraboost":     {"PRICE": 0, "BRAND": 1, "FUZZY": 1, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "running shoes from berlin": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "CATEGORY": 0, "HYBRID": 1},
    "sneakers":                {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "gift for wife birthday":  {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 1},
    "zapatos por menos de 10": {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "sandalias baratas":       {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "botas de madrid":         {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "CATEGORY": 0, "HYBRID": 1},
    "regalo para el cumpleanos de mi esposa": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 1},
    "tenis para correr":       {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "zapatillas nike air force": {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "鞋子 10 元以下":            {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "耐克 Air Force 1":          {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "靴子 北京":                 {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "CATEGORY": 0, "HYBRID": 1},
    "妻子的生日礼物":             {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 1},
    "跑鞋":                     {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "10 से कम की जूते":         {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "नाइक एयर फोर्स 1":          {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 0},
    "जोधपुर के जूते":            {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "CATEGORY": 0, "HYBRID": 1},
    "लंबी पैदल यात्रा के लिए जूते": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 1},
    "स्नीकर्स":                  {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
}

SEMANTIC = {}   # flip knob, same as memoize.py

def decide(query):
    query = " ".join(query.strip().lower().split())
    rows = [(name, enc(f"\nUser query: {query}\n{marker}"))
            for name, (marker, *_) in meta["questions"].items()]
    n, L = len(rows), max(len(t) for _, t in rows)
    ids = torch.full((n, L), pad, device=device, dtype=torch.long)
    m = torch.zeros((n, L), device=device, dtype=torch.long)
    last = []
    for i, (_, t) in enumerate(rows):
        ids[i, :len(t)] = torch.tensor(t, device=device)
        m[i, :len(t)] = 1
        last.append(len(t) - 1)
    cache = DynamicCache()
    for i, (k, v) in enumerate(state):
        cache.update(k.expand(n, -1, -1, -1), v.expand(n, -1, -1, -1), i)
    attn = torch.cat([torch.ones(n, base_len, device=device, dtype=torch.long), m], 1)
    pos = (base_len + torch.arange(L, device=device)).unsqueeze(0).expand(n, -1)
    logits = model(input_ids=ids, past_key_values=cache, position_ids=pos,
                   attention_mask=attn, use_cache=False).logits
    return {rows[i][0]: float(torch.softmax(logits[i, last[i], YES].float(), -1)[0])
            for i in range(n)}

# per-question precision/recall on the pipeline-semantic positive, with
# flipped probes decided from the no-side
stats = {}
for i, (q, gold) in enumerate(GOLD.items()):
    raw = decide(q)
    for name, (marker, *_) in meta["questions"].items():
        sem = SEMANTIC.get(name, name)
        if sem not in gold:
            continue
        peff = raw[name] if name not in SEMANTIC else 1.0 - raw[name]
        s = stats.setdefault(sem, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
        pred, g = peff >= 0.5, gold[sem]
        if pred and g: s["tp"] += 1
        elif pred: s["fp"] += 1
        elif g: s["fn"] += 1
        else: s["tn"] += 1
    cells = []
    for n, g in gold.items():
        rawname = n if n in raw else next(k for k, v in SEMANTIC.items() if v == n)
        peff = raw[rawname] if rawname not in SEMANTIC else 1.0 - raw[rawname]
        cells.append(f"{n[:3]}={peff:.2f}" + ("" if int(peff >= 0.5) == g else "*"))
    print(f"  {q:38s} " + " ".join(cells))

print("\nper question: found = of the queries needing this path, how many said yes;"
      " right when yes = of its yeses, how many were true")
for sem in ["PRICE", "BRAND", "FUZZY", "LOCATION", "CATEGORY", "HYBRID"]:
    s = stats[sem]
    print(f"  {sem:9s} found {s['tp']}/{s['tp'] + s['fn']}  |  right when yes {s['tp']}/{s['tp'] + s['fp']}")
