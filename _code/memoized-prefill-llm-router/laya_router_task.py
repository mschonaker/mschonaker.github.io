#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Router task through Laya, fixed prompt. Same six queries as the causal
batched script. Usage: laya_router_task.py [english|typed-decisions]"""
import sys
import time
from laya import Router

BRANDS = ("Nike, Adidas, Puma, Asics, New Balance, Salomon, Decathlon, Reebok, "
          "Under Armour, Fila, Mizuno, Brooks, Saucony, Hoka, On, Merrell, "
          "The North Face, Columbia, Patagonia, Apple, Samsung, Sony, LG, "
          "Bosch, Philips, Xiaomi, Dell, HP, Lenovo, Logitech, JBL, Bose, "
          "Zara, H&M, Uniqlo, Gap, Levi's, IKEA, Tommy Hilfiger, Lacoste")
CATEGORIES = ("shoes, sandals, boots, sneakers, slippers, jackets, coats, "
              "hoodies, t-shirts, jeans, dresses, backpacks, handbags, watches, "
              "headphones, earbuds, speakers, phones, tablets, laptops, "
              "televisions, vacuums, cookware, bikes")

QUESTIONS = {
    "PRICE":    {"type": "noul", "instructions":
        "Does the query bound a price, for example 'under 10', 'cheap', '50 to 100'?"},
    "BRAND":    {"type": "noul", "instructions":
        f"Does the query mention or hint one of these brands, including a misspelled brand? Brands: {BRANDS}"},
    "FUZZY":    {"type": "noul", "instructions":
        "Does a word in the query look misspelled or an unknown brand spelling? "
        "No when every word is a correctly spelled common word or known brand."},
    "LOCATION": {"type": "noul", "instructions":
        "Does a city, country, or region name appear in the query?"},
    "CATEGORY": {"type": "noul", "instructions":
        f"Does the query name a product type, directly or as a common synonym "
        f"like 'runners' or 'trainers'? Categories include: {CATEGORIES}"},
    "HYBRID":   {"type": "noul", "instructions":
        "Does the query describe a need, recipient, occasion, or use beyond "
        "naming products, for example 'for my wife', 'birthday', 'long walks'? "
        "No when the query only names product types, brands, model numbers, "
        "colors, sizes, or prices."},
}

QUERIES = ["shoes under 10", "nike air force 1", "addidass ultraboost",
           "running shoes from berlin", "sneakers", "gift for wife birthday"]
GOLD = {
    "shoes under 10":          {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "nike air force 1":        {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "addidass ultraboost":     {"PRICE": 0, "BRAND": 1, "FUZZY": 1, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "running shoes from berlin": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "CATEGORY": 1, "HYBRID": 1},
    "sneakers":                {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 1, "HYBRID": 0},
    "gift for wife birthday":  {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "CATEGORY": 0, "HYBRID": 1},
}
NAMES = list(QUESTIONS)

model = sys.argv[1] if len(sys.argv) > 1 else "english"
r = Router()
lat = []
probs = {}
for q in QUERIES:
    t0 = time.perf_counter()
    res = r.predict(q, QUESTIONS, model=("typed-decisions" if model == "typed-decisions" else None))
    lat.append((time.perf_counter() - t0) * 1000)
    probs[q] = {k: v["noul"] for k, v in res["answers"].items()}

print(f"checkpoint={model} p50={sorted(lat)[len(lat)//2]:.0f} ms")
print(f"{'query':30s} " + " ".join(f"{n[:4]:>6s}" for n in NAMES) + "  (correct in parens)")
for q in QUERIES:
    cells = []
    for n in NAMES:
        p = probs[q][n]
        ok = int(p >= 0.5) == GOLD[q][n]
        cells.append(f"{p:6.2f}" + ("  " if ok else "*"))
    print(f"{q:30s} " + " ".join(cells))
acc = sum(int(probs[q][n] >= 0.5) == GOLD[q][n] for q in QUERIES for n in NAMES)
print(f"accuracy @0.5: {acc}/{len(QUERIES)*len(NAMES)}")
