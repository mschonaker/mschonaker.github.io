# memoized-prefill-llm-router

Two independent PyTorch files implementing a decision engine for ecommerce
search routing, plus a Laya comparison script. No shared code between the two
halves — only the artifact directory format.

- `memoize.py` — prefills the instruction block once, fits per-question
  thresholds on labeled queries, writes `memo/` (instructions.txt, version.txt,
  meta.json, one tensor file per layer). Run once per instruction version.
- `server.py` — loads `memo/`, verifies the version hash, answers all question
  probes per query in one batched forward pass. Never prefills.
- `laya_router_task.py` — the same task run through Laya (encoder), for the
  latency/accuracy comparison in the post.

Run:

```
uv run memoize.py
uv run server.py memo "shoes under 10" "gift for wife birthday"
uv run laya_router_task.py
```

Blog post: `_posts/memoized-prefill-llm-router.md`.
