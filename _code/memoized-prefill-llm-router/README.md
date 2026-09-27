# memoized-prefill-llm-router

Two independent PyTorch files implementing a decision engine for ecommerce
search routing, plus the two scoring scripts used for the comparison tables.
No shared code between the halves — only the artifact directory format.

- `memoize.py` — prefills the instruction block once, fits per-question
  thresholds on labeled queries, writes `memo/` (instructions.txt, version.txt,
  meta.json, one tensor file per layer). Run once per instruction version.
- `server.py` — loads `memo/`, verifies the version hash, answers all question
  probes per query in one batched forward pass. Never prefills.
- `causal_score.py` — scores the memoized engine at threshold 0.5 across the
  22-query, four-script bank (english, Spanish, Chinese, Hindi), per class.

Run:

```
uv run memoize.py
uv run server.py memo "shoes under 10" "gift for wife birthday"
uv run causal_score.py memo
```

Blog post: `_posts/memoized-prefill-llm-router.md`.
