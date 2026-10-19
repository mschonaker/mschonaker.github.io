#!/usr/bin/env python3
"""Compare approximate and exact kNN over the same queries, and report how
much of the approximate result is the true top set."""

import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request

PORT = sys.argv[1] if len(sys.argv) > 1 else "9410"
EMBED = sys.argv[2] if len(sys.argv) > 2 else "embedder/zig-out/bin/embed"
MODEL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(EMBED))) or "."
ARGS = [EMBED, "--model", os.path.join(MODEL_DIR, "model.onnx"),
        "--tokenizer", os.path.join(MODEL_DIR, "tokenizer.json"),
        "--server", "--threads", "6", "--max-tokens", "64"]

QUERIES = [
    "headphones",
    "wireless earbuds with long battery life",
    "cheap television for a small bedroom",
    "something to keep my ears warm in winter",
    "gift for a ten year old",
    "kitchen stand mixer",
]
K = 100


def embed_many(texts):
    payload = "".join(json.dumps({"title_t": t}) + "\n" for t in texts).encode()
    out = subprocess.run(ARGS, input=payload, capture_output=True, check=True)
    return [json.loads(line)["embedding_v"] for line in out.stdout.splitlines()]


def post(body):
    req = urllib.request.Request(
        f"http://localhost:{PORT}/collections/products/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    raw = urllib.request.urlopen(req, timeout=60).read()
    return (time.perf_counter() - t0) * 1000, json.loads(raw)["docs"]


def knn(vec, k, exact=False):
    body = {"query": {"knn": {"field": "embedding_v", "query": vec, "k": k}},
            "limit": k, "fields": ["id"]}
    if exact:
        body["query"]["knn"]["exact"] = True
    return post(body)


def median_ms(call, runs=9):
    """call() returns (ms, docs); take the median of the timings."""
    return statistics.median(call()[0] for _ in range(runs))


def main():
    vecs = embed_many(QUERIES)
    print(f"{'query':<42}{'exact':>8}{'ann':>8}{'speedup':>9}   recall@10 / @100")
    print("-" * 84)
    for q, v in zip(QUERIES, vecs):
        ex_ms = median_ms(lambda: knn(v, K, True))
        ex = knn(v, K, True)[1]
        an_ms = median_ms(lambda: knn(v, K))
        an = knn(v, K)[1]
        ex_ids = [d["id"] for d in ex]
        an_ids = [d["id"] for d in an]
        r10 = len(set(ex_ids[:10]) & set(an_ids[:10])) / 10
        r100 = len(set(ex_ids) & set(an_ids)) / len(ex_ids)
        print(f"{q:<42}{ex_ms:>8.1f}{an_ms:>8.1f}{ex_ms/an_ms:>8.1f}x   "
              f"{r10:>8.0%} / {r100:>6.0%}")

    print("\n--- ivf.nprobe, query 'headphones' ---")
    v = vecs[0]
    ex = knn(v, K, True)[1]
    for nprobe in (0, 1, 4, 16, 64):
        body = {"query": {"knn": {"field": "embedding_v", "query": v, "k": K,
                                  "ivf": {"nprobe": nprobe}}},
                "limit": K, "fields": ["id"]}
        ms, an = median_ms(lambda: post(body)), post(body)[1]
        ids = {d["id"] for d in an}
        recall = len(ids & {d["id"] for d in ex}) / len(ex)
        print(f"  nprobe {nprobe:>3}{'(adaptive)' if nprobe == 0 else '':<12}"
              f"{ms:>7.1f} ms   recall {recall:.0%}")


if __name__ == "__main__":
    main()