#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# ///
"""Search router on OpenCode's hosted decision model, jev-1.13-free.

Repeats the memoized-prefill example: six yes/no routing questions per query,
P(yes) per answer, threshold 0.5, the same 22-query gold bank.

Local: python memoize.py + server.py, probe logits at "BRAND? Answer:" markers.
Here:   POST state + six noul questions to https://opencode.ai/zen/v1/systemone,
        read the probabilities back. No model weights, no prefill, no artifacts.

Usage: uv run router_jev.py
"""
import json
import time
import urllib.request

ENDPOINT = "https://opencode.ai/zen/v1/systemone"
MODEL = "jev-1.13-free"

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

CATEGORIES = """shoes, sandals, boots, sneakers, slippers, jackets, coats,
hoodies, t-shirts, jeans, shorts, dresses, skirts, backpacks, handbags,
wallets, watches, headphones, earbuds, speakers, phones, tablets, laptops,
monitors, keyboards, mice, televisions, fridges, washers, vacuums, cookware,
knives, towels, bedding, furniture, lamps, tools, drills, bikes, tents"""

QUESTIONS = {
    "PRICE": {"type": "noul", "instructions": "Does the query bound a price?",
              "criteria": {
                  "true": 'A price bound appears: "under 10", "cheap", "50 to 100", or an equivalent in any language',
                  "false": "No price bound appears in the query"}},
    "BRAND": {"type": "noul", "instructions": {
                  "known_brands": BRANDS,
                  "question": "Does the query mention or hint at one of the known brands?"}},
    "FUZZY": {"type": "noul", "instructions": "Does any word in the query look misspelled?",
              "criteria": {
                  "true": "A word looks misspelled or is an unknown brand spelling",
                  "false": "Every word is a correctly spelled common word or a known brand"}},
    "LOCATION": {"type": "noul", "instructions": "Does a city, country, or region name appear in the query?"},
    "CATEGORY": {"type": "noul", "instructions": {
                  "known_categories": CATEGORIES,
                  "question": 'Is the whole query a product category name or a plain category phrase, e.g. "sneakers", "running shoes", "trail boots"?'},
                 "criteria": {
                  "true": "The whole query is just a category phrase",
                  "false": "The query adds a price, a brand, a place, or a described need, recipient, or occasion"}},
    "HYBRID": {"type": "noul", "instructions": "Does the query describe a need, recipient, occasion, or use beyond naming products?",
               "criteria": {
                  "true": 'A need, recipient, occasion, or use appears: "for my wife", "birthday", "long walks", "for student"',
                  "false": "The query only names product types, brands, model numbers, colors, sizes, or prices"}},
}

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


def decide(query):
    body = json.dumps({"model": MODEL, "state": query, "questions": QUESTIONS}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={
        "Content-Type": "application/json", "User-Agent": "curl/8.9.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        answers = json.load(resp)["answers"]
    return {name: answers[name]["noul"] for name in QUESTIONS}


def main():
    total = ok = 0
    for query, gold in GOLD.items():
        t0 = time.perf_counter()
        probs = decide(query)
        ms = (time.perf_counter() - t0) * 1000
        flags = {n: int(p >= 0.5) for n, p in probs.items()}
        wrong = [n for n in flags if flags[n] != gold[n]]
        total += len(flags)
        ok += len(flags) - len(wrong)
        line = " ".join(f"{n}={'Y' if flags[n] else 'n'}({probs[n]:.2f})" for n in QUESTIONS)
        mark = "  " if not wrong else "!!"
        print(f"{mark} {query!r:45s} {line}  [{ms:.0f} ms]"
              + (f"  MISS: {','.join(wrong)}" if wrong else ""))
    a, b = decide("shoes under 10"), decide("shoes under 10")
    print(f"\naccuracy: {ok}/{total} = {ok/total:.1%}")
    print(f"determinism (rerun identical): {a == b}")


if __name__ == "__main__":
    main()
