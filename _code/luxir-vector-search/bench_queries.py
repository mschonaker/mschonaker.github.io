#!/usr/bin/env python3
"""Run the same queries three ways against a running Luxir and report the
engine round trip. Query vectors come from the Zig embedder, reused across
all queries so the reported cost is the search and not the model load."""

import json
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "9410"
EMBED = sys.argv[2] if len(sys.argv) > 2 else "embedder/zig-out/bin/embed"
# The binary lives at <dir>/zig-out/bin/embed; the model files sit in <dir>.
MODEL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(EMBED))) or "."
EMBED_ARGS = [
    EMBED,
    "--model", os.path.join(MODEL_DIR, "model.onnx"),
    "--tokenizer", os.path.join(MODEL_DIR, "tokenizer.json"),
]
FIELDS = ["title_t", "description_t", "brand_name"]

QUERIES = [
    "headphones",
    "wireless earbuds with long battery life",
    "cheap television for a small bedroom",
    "headfones",  # a typo: BM25 has nothing to stem to
    "something to keep my ears warm in winter",
    "gift for a ten year old",
]


def embed_many(texts):
    """One child process, one line in, one line out."""
    payload = "".join(
        json.dumps({"title_t": t}) + "\n" for t in texts
    ).encode()
    out = subprocess.run(
        EMBED_ARGS + ["--server", "--threads", "6", "--max-tokens", "64"],
        input=payload,
        capture_output=True,
        check=True,
    )
    return [json.loads(line).get("embedding_v") for line in out.stdout.splitlines()]


def post(body):
    req = urllib.request.Request(
        f"http://localhost:{PORT}/collections/products/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def lexical(q, limit):
    return {
        "query": {"simple_query": {"q": q, "fields": FIELDS}},
        "limit": limit,
        "get_number": True,
        "get_scores": True,
        "fields": ["id", "title_t", "brand_name", "price_f"],
    }


def vectors(vec, limit, pool):
    return {
        "query": {"knn": {"field": "embedding_v", "query": vec, "k": pool}},
        "limit": limit,
        "get_number": True,
        "get_scores": True,
        "fields": ["id", "title_t", "brand_name", "price_f"],
    }


def hybrid(q, vec, pool, limit=12):
    return {
        "ops": {
            "q": {
                "fusion": {
                    "sources": {
                        "words": {"query": {"simple_query": {"q": q, "fields": FIELDS}}, "limit": pool},
                        "vectors": {"query": {"knn": {"field": "embedding_v", "query": vec, "k": pool}}, "limit": pool},
                    },
                    "rrf": {"k": 60},
                    "limit": limit,
                    "get_number": True,
                    "get_scores": True,
                    "fields": ["id", "title_t", "brand_name", "price_f"],
                }
            }
        }
    }


def titles(resp):
    q = resp.get("q", resp)
    ops = resp.get("ops", {})
    if "q" in ops:
        q = ops["q"]
    return [d["title_t"] for d in q.get("docs", [])]


def median_ms(fn, runs=7):
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.median(samples)


def main():
    vecs = embed_many(QUERIES)
    pool = 200
    print(f"{'query':<44}{'words':>9}{'vectors':>9}{'hybrid':>9}   found (w/v/h)")
    print("-" * 92)
    for q, vec in zip(QUERIES, vecs):
        rw = post(lexical(q, 12))
        rv = post(vectors(vec, 12, pool))
        rh = post(hybrid(q, vec, pool))
        tw = median_ms(lambda: post(lexical(q, 12)))
        tv = median_ms(lambda: post(vectors(vec, 12, pool)))
        th = median_ms(lambda: post(hybrid(q, vec, pool)))
        fq = lambda r: (r.get("ops", {}).get("q") or r).get("found", 0)
        print(f"{q:<44}{tw:>9.1f}{tv:>9.1f}{th:>9.1f}   {fq(rw)}/{fq(rv)}/{fq(rh)}")

    print("\n--- top 3 for the typo 'headfones' ---")
    for name, body in (
        ("words  ", lexical("headfones", 3)),
        ("vectors", vectors(vecs[3], 3, pool)),
        ("hybrid ", hybrid("headfones", vecs[3], pool, 3)),
    ):
        for t in titles(post(body)):
            print(f"  {name} {t[:88]}")

    print("\n--- candidate pool size, query 'cheap television for a small bedroom' ---")
    for p in (20, 50, 200, 500):
        r = post(hybrid("cheap television for a small bedroom", vecs[2], p))
        q = r["ops"]["q"]
        print(f"  pool {p:>4}  found {q.get('found')}")
        for d in q.get("docs", [])[:3]:
            print(f"      {d['_score_']:.6f}  {d['title_t'][:70]}")


if __name__ == "__main__":
    main()