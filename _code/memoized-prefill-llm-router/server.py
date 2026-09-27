#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["torch", "transformers"]
# ///
"""Serve step. Loads the memoized directory written by memoize.py — plain
files, no shared code, no prefill. Answers every question of every query in
ONE batched forward pass over the memo.

Usage: python server.py "memo" "shoes under 10" "gift for wife birthday"
"""
import hashlib
import json
import sys
import time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, DynamicCache

torch.set_grad_enabled(False)

def load(dirpath):
    with open(f"{dirpath}/meta.json") as f:
        meta = json.load(f)
    with open(f"{dirpath}/instructions.txt") as f:
        instructions = f.read()
    with open(f"{dirpath}/version.txt") as f:
        version = f.read().strip()
    recomputed = hashlib.sha256(
        (meta["model_id"] + meta["dtype"] + instructions).encode()).hexdigest()[:12]
    if recomputed != version or recomputed != meta["version"]:
        raise RuntimeError(f"artifact inconsistent: files say {version}, "
                           f"content hashes to {recomputed}")
    if str(meta["torch"]) != str(torch.__version__):
        raise RuntimeError(f"artifact built with torch {meta['torch']}, "
                           f"running {torch.__version__}")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    dtype = getattr(torch, meta["dtype"].split(".")[-1])
    state = [(torch.load(f"{dirpath}/state/layer_{i:02d}_key.pt",
                         map_location=device, weights_only=True),
              torch.load(f"{dirpath}/state/layer_{i:02d}_value.pt",
                         map_location=device, weights_only=True))
             for i in range(meta["layers"])]
    return meta, state, device, dtype

def main():
    args = sys.argv[1:]
    dirpath = args[0] if args and not args[0].startswith("-") else "memo"
    queries = args[1:] or ["shoes under 10"]

    t0 = time.perf_counter()
    meta, state, device, dtype = load(dirpath)
    tok = AutoTokenizer.from_pretrained(meta["model_id"])
    model = (AutoModelForCausalLM.from_pretrained(meta["model_id"], dtype=dtype)
             .to(device).eval())
    enc = lambda s: tok(s, add_special_tokens=False).input_ids
    YES = torch.tensor([enc(" yes")[0], enc(" no")[0]], device=device)
    base_len, pad = meta["base_len"], tok.eos_token_id
    print(f"loaded {dirpath}: version={meta['version']} prefix={base_len} tokens, "
          f"setup {(time.perf_counter() - t0) * 1000:.0f} ms — no prefill ran")

    def decide(query):
        query = " ".join(query.strip().lower().split())
        rows = [(name, enc(f"\nUser query: {query}\n{marker}"), thr, flip)
                for name, (marker, thr, flip) in meta["questions"].items()]
        n = len(rows)
        L = max(len(toks) for _, toks, _ in rows)
        input_ids = torch.full((n, L), pad, device=device, dtype=torch.long)
        new_mask = torch.zeros((n, L), device=device, dtype=torch.long)
        for i, (_, toks, _, _) in enumerate(rows):
            input_ids[i, :len(toks)] = torch.tensor(toks, device=device)
            new_mask[i, :len(toks)] = 1
        cache = DynamicCache()
        for i, (k, v) in enumerate(state):
            cache.update(k.expand(n, -1, -1, -1), v.expand(n, -1, -1, -1), i)
        attn = torch.cat([torch.ones(n, base_len, device=device, dtype=torch.long),
                          new_mask], dim=1)
        pos = (base_len + torch.arange(L, device=device)).unsqueeze(0).expand(n, -1)
        logits = model(input_ids=input_ids, past_key_values=cache,
                       position_ids=pos, attention_mask=attn,
                       use_cache=False).logits
        out = {}
        for i, (name, toks, thr, flip) in enumerate(rows):
            z = logits[i, len(toks) - 1, YES].float()
            p = float(torch.softmax(z, -1)[0])
            out[name] = ((p >= thr) != flip, p)
        return out

    for query in queries:
        t0 = time.perf_counter()
        answers = decide(query)
        line = " ".join(f"{n}={'Y' if flag else 'n'}({p:.2f})"
                        for n, (flag, p) in answers.items())
        print(f"  {query!r:35s} {line}  [{(time.perf_counter() - t0) * 1000:.0f} ms]")

    def bench(query, n=20, warm=3):
        for _ in range(warm):
            decide(query)
        t0 = time.perf_counter()
        for _ in range(n):
            decide(query)
        return (time.perf_counter() - t0) * 1000 / n

    a, b = decide(queries[0]), decide(queries[0])
    print(f"bench: {bench(queries[0]):.1f} ms per decide | "
          f"determinism (rerun identical): {a == b}")

if __name__ == "__main__":
    main()
