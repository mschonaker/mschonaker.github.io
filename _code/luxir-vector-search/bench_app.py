#!/usr/bin/env python3
"""Median engine round trip per mode, taken from the meta line the app
renders. That number is measured around the gRPC call only, so it excludes
HTTP and template cost. Includes the four facet operations and the exact
count (get_number)."""

import re
import statistics
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8099"
QUERIES = [
    "headphones",
    "noise cancelling earbuds",
    "wireless earbuds with long battery life",
    "cheap television for a small bedroom",
    "headfones",
    "gift for a ten year old",
]
RUNS = 9


def hit(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        page = r.read().decode()
    meta = re.search(r'<p class="meta">(.*?)</p>', page, re.S)
    text = re.sub(r"<[^>]+>", "", meta.group(1))
    engine = float(re.search(r"([\d.]+) ms round trip", text).group(1))
    embed = re.search(r"([\d.]+) ms to embed", text)
    found = int(re.search(r"([\d]+) products", text).group(1))
    return engine, (float(embed.group(1)) if embed else 0.0), found


def main():
    head = f"{'query':<40}{'words':>9}{'vectors':>9}{'embed':>9}{'hybrid':>9}{'embed':>9}   found w/v/h"
    print(head)
    print("-" * len(head))
    agg = {m: [] for m in ("words", "vectors", "hybrid")}
    emb = {"vectors": [], "hybrid": []}
    for q in QUERIES:
        url = urllib.parse.quote(q)
        cells, found = [], []
        for mode in ("words", "vectors", "hybrid"):
            runs = [hit(f"{BASE}/?q={url}&mode={mode}") for _ in range(RUNS)]
            engine = statistics.median(r[0] for r in runs)
            embed = statistics.median(r[1] for r in runs)
            cells.append((engine, embed))
            agg[mode].append(engine)
            if embed:
                emb[mode].append(embed)
            found.append(runs[0][2])
        print(f"{q:<40}{cells[0][0]:>9.1f}{cells[1][0]:>9.1f}{cells[1][1]:>9.1f}"
              f"{cells[2][0]:>9.1f}{cells[2][1]:>9.1f}   {'/'.join(map(str, found))}")
    print("-" * len(head))
    print(f"{'median':<40}"
          f"{statistics.median(agg['words']):>9.1f}"
          f"{statistics.median(agg['vectors']):>9.1f}{statistics.median(emb['vectors']):>9.1f}"
          f"{statistics.median(agg['hybrid']):>9.1f}{statistics.median(emb['hybrid']):>9.1f}")


if __name__ == "__main__":
    main()