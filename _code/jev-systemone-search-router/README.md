# Jev System One search router

Repeats the memoized-prefill search-router example (`../memoized-prefill-llm-router/`)
with OpenCode Zen's hosted decision model instead of local Qwen logits.

## Run

```bash
uv run router_jev.py
```

- Endpoint: `https://opencode.ai/zen/v1/systemone`, model `jev-1.13-free`
  (free for a limited time; fall back to paid `jev-1.13` when the window closes).
- No API key needed for the free id. No dependencies beyond the standard library.
- `state` is the query; six `noul` questions return P(yes) in one request;
  flags use threshold 0.5; `GOLD` is the same 22-query bank as the blog post.
