#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Router task through Laya: same queries and gold labels as the causal
engine. Usage: laya_router_task.py [english|typed-decisions]
"""
import sys, time
from laya import Router
QUESTIONS = {
    "PRICE":    {"type": "noul", "instructions": "Does the query bound a price, for example 'under 10', 'cheap', '50 to 100'?"},
    "BRAND":    {"type": "noul", "instructions": "Does the query mention or hint one of these brands, including a misspelled brand? Brands: Nike, Adidas, Puma, Asics, New Balance, Salomon, Decathlon, Reebok, Apple, Samsung, Sony, Xiaomi, Lenovo"},
    "FUZZY":    {"type": "noul", "instructions": "Does a word in the query look misspelled or an unknown brand spelling? No when every word is a correctly spelled common word or known brand."},
    "LOCATION": {"type": "noul", "instructions": "Does a city, country, or region name appear in the query?"},
    "CATEGORY": {"type": "noul", "instructions": "Is the whole query a product category name or plain category phrase, like 'sneakers' or 'running shoes', with nothing else added? No when the query adds a price, brand, place, or a described need or occasion."},
    "HYBRID":   {"type": "noul", "instructions": "Does the query describe a need, recipient, occasion, or use beyond naming products, for example 'for my wife', 'birthday', 'long walks'? No when the query only names product types, brands, model numbers, colors, sizes, or prices."},
}
GOLD = {
    "shoes under 10":     {"PRICE": 1, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "nike air force 1":   {"PRICE": 0, "BRAND": 1, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "addidass ultraboost": {"PRICE": 0, "BRAND": 1, "FUZZY": 1, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 0},
    "running shoes from berlin": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 1, "HYBRID": 1, "CATEGORY": 0},
    "sneakers":           {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 0, "CATEGORY": 1},
    "gift for wife birthday": {"PRICE": 0, "BRAND": 0, "FUZZY": 0, "LOCATION": 0, "HYBRID": 1, "CATEGORY": 0},
}
r = Router()
model = sys.argv[1] if len(sys.argv) > 1 else None
lat = []
hit = tot = 0
for q, gold in GOLD.items():
    t0 = time.perf_counter()
    res = r.predict(q, QUESTIONS, model=(model if model != "auto" else None))
    lat.append((time.perf_counter() - t0) * 1000)
    p = {k: v["noul"] for k, v in res["answers"].items()}
    cells = []
    for n, g in gold.items():
        ok = int(p[n] >= 0.5) == g
        hit, tot = hit + ok, tot + 1
        cells.append(f"{n[:3]}={p[n]:.2f}" + ("" if ok else "*"))
    print(f"  {q:28s} " + " ".join(cells))
print(f"laya accuracy @0.5 (fixed CATEGORY rule): {hit}/{tot} | p50 {sorted(lat)[len(lat)//2]:.0f} ms")
