---
id: laya-hello-world
title: "Laya Hello World: A Non-Autoregressive System 1 Decision in 35 ms"
summary: Run Laya, the open-source non-autoregressive System 1 decision model, with uv on Apple Silicon — an editable request.json, a 100-call benchmark, and honest limits.
date: 2026-09-26
tags: ai, ml, python
image: /images/laya-hello-world.jpg
---

# Laya Hello World: A Non-Autoregressive System 1 Decision in 35 ms

Hello world means print. With [Laya](https://github.com/NandhaKishorM/laya) it does not. Laya is an open-source, non-autoregressive "System 1" decision model: you give it a state (a ticket, an email, a document) and typed questions, and it answers every question in one forward pass. No text is generated, so there is nothing to parse and nothing to hallucinate. The hello world is a decision.

## What Laya is

LLMs are System 2 machines: they generate token by token, then you parse the answer. Laya is a System 1 machine: a bidirectional encoder (ModernBERT-large, 421M parameters) with a decision head. Each answer option is scored at its own `[MASK]` token, then softmaxed.

Three question types:

| Primitive | Output | Typical use |
|-----------|--------|-------------|
| `choice`  | top label + probability per option | department routing, intent |
| `score`   | expected level on an ordinal rubric | urgency, frustration |
| `noul`    | P(true), 0.0 to 1.0 | churn risk, guardrails |

A `Router` picks between an english and a multilingual (100+ languages) checkpoint per request. Training uses RLCD — reinforcement learning against strictly proper scoring rules. Apache 2.0, weights on Hugging Face.

## Installing: a wheel and a download

Laya is a plain Python package. `uv pip install laya` gets the module, its deps (torch, transformers, huggingface_hub), and console scripts (`laya`, `laya-serve`). That is a few MB.

The weights are separate. The first `predict` call downloads a checkpoint (~800 MB english) from Hugging Face into `~/.cache/huggingface` — no account or token. Routing alone never downloads anything: it is pure Python.

The scripts below carry PEP 723 headers and a `.python-version` file pins Python 3.11 (the version Laya's own Dockerfile uses). uv provisions the interpreter and the environment on first run; no venv management and no flags. On macOS the default ARM64 torch wheel already includes the MPS backend.

## The editable prompt: request.json

State and questions live in one JSON file. Try new inputs by editing it — never code:

```json
{
  "state": "Hi, we were billed twice for March. Please refund the duplicate today or we will cancel our plan.",
  "questions": {
    "department": {
      "type": "choice",
      "instructions": "Which department should handle this?",
      "criteria": {
        "billing": "invoices, payments, refunds",
        "technical": "bugs, outages, system errors",
        "other": "everything else"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this?",
      "criteria": ["not urgent", "soon", "blocking"]
    },
    "churn_risk": {
      "type": "noul",
      "instructions": "Does the user threaten to cancel or leave?"
    }
  }
}
```

The runner (`hello_laya.py`) is deliberately small. It loads the JSON file, builds a `Router`, and makes one call. The whole PEP 723 header plus the core of `main()`:

```python
#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Laya hello world: run one editable request.json through the Router."""
from laya import Router

req = json.loads(Path(args.request).read_text())
router = Router(**({"device": args.device} if args.device else {}))

t0 = time.perf_counter()
result = router.predict(req["state"], req["questions"], **({"model": args.model} if args.model else {}))
cold = (time.perf_counter() - t0) * 1000
```

One `predict(state, questions)` call answers every question. The script also re-runs the same call to time the warm path. Run it:

```bash
cd _code/laya-hello-world
uv run hello_laya.py
```

## First decision: real output

The cold call (download plus load) took 95 s once. Every run after that is warm. Output from my Mac:

```text
routed : english  (English Latin text)
answers:
  department     choice -> 'billing'  conf=0.9267
                          [billing: 0.987, technical: 0.008, other: 0.005]
  urgency        score  -> 1.7722 / 2.0  conf=0.4714
  churn_risk     noul   -> p(true)=0.879
usage  : {'input_tokens': 164, 'output_tokens': 0}
```

`output_tokens: 0` — a non-autoregressive model produces no tokens. One forward pass answered all three questions.

Edit the state to a crash report and re-run (`--request request-crash.json`):

```text
  department     choice -> 'technical'  conf=0.7148
  churn_risk     noul   -> p(true)=0.069
```

The department flips to `technical`, churn drops from 0.879 to 0.069. The answer space was defined at request time, not training time. The literal hello world works too: `"Hello, world"` against a noul question "Is this a polite greeting?" answers `p(true)=0.720`.

## Multilingual routing without a second download

`route_only.py` inspects the routing decision alone, before any weights load:

```python
#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Show the Router's language routing decisions without loading any checkpoint."""
from laya import Router

questions = {"department": {"type": "choice", "instructions": "Which department?",
               "criteria": {"billing": "invoices, payments, refunds",
                            "technical": "bugs, outages, system errors",
                            "other": "everything else"}}}

router = Router()  # lazy: route() never downloads weights
for text in ["Please refund the duplicate charge on my invoice.",
             "मुझसे मार्च में दो बार शुल्क लिया गया, कृपया डुप्लिकेट राशि वापस करें।",
             "La aplicación se cierra cada vez que abro la configuración.",
             "Hello, world"]:
    r = router.route(text, questions)
    print(f"{text[:40]:42s} -> model={r.model:12s} reason: {r.reason}")
```

Output from my Mac:

```text
Please refund the duplicate charge on m   -> model=english      reason: English Latin text
मुझसे मार्च में दो बार शुल्क लिया गया, कृपया   -> model=multilingual reason: non-Latin script (devanagari, 100% of letters)
La aplicación se cierra cada vez que abr   -> model=multilingual reason: Latin script, 3% non-English letters
```

The reason strings explain each pick in full; the english checkpoint "cannot read" the devanagari text, and the Spanish ticket is not safe for the english checkpoint either. Detection costs under a millisecond. Their benchmark shows why it matters: the english checkpoint on Khmer scored 0.000 accuracy at 0.952 confidence — confidently wrong, so a confidence gate cannot catch it.

## How the call flows

```mermaid
flowchart LR
    app[hello_laya.py] -- "predict(state, questions) ▻ / typed answers ◅" --> router[Laya Router]
    router -- "script and language check <1 ms" --> router
    router -- "one forward pass ▻ / logits at each option's [MASK] ◅" --> ckpt[english checkpoint ModernBERT-large 421M]
    ckpt -- "answers + routing metadata ▻ / result dict ◅" --> app
```

## Apple Silicon: MPS works, the fast path does not

`bench_laya.py` measures warm latency properly: one preloaded router, 100 `predict` calls over varied ticket texts, three questions each, warmup call excluded. The core of `main()`:

```python
rng = random.Random(42)
states = make_states(100, rng)

router = Router(device="mps")
router.preload(["english"])
router.predict(states[0], QUESTIONS)  # compile/warmup pass, not counted

samples = []
for state in states:
    t0 = time.perf_counter()
    result = router.predict(state, QUESTIONS)
    samples.append((time.perf_counter() - t0) * 1000)

samples.sort()
n = len(samples)
mean = sum(samples) / n
p50 = samples[n // 2]
p95 = samples[int(n * 0.95)]
```

`make_states` fills five ticket templates with random months, amounts, and products, so the 100 calls run on distinct inputs. Measured on an Apple Silicon Mac, english checkpoint:

| Device | Cold (load + first call) | Warm |
|--------|--------------------------|------|
| MPS    | ~2.3 s                   | **mean 36.3 ms, p50 34.5 ms, p95 38 ms** |
| CPU    | ~2.2 s                   | 119 ms (single reference call) |

The distribution is tight: min 32 ms, one 210 ms outlier. MPS is about 3x faster than CPU on this machine. What Mac users do not get: the TileLang fast path (`laya[fast]`) is NVIDIA-CUDA-only and falls back to the stock forward on CPU/MPS.

## Honest limits

The project documents its own weaknesses, and I hit one immediately. On load the runtime warns that the shipped checkpoint temperatures are invalid — treat the confidence numbers above as uncalibrated, and fit temperatures on your own data before gating on them. Other documented limits:

- **Base checkpoints are weak zero-shot.** On the typed-decisions benchmark the base english checkpoint scores 0.362 against a 0.461 majority-class baseline; the fine-tuned `laya-typed-decisions` checkpoint reaches 0.766. Fine-tuning is where the accuracy comes from.
- **Many-option choices degrade.** Options share a token budget, so a 77-option question gives each label ~3-4 tokens and accuracy falls to 0.425.
- **English context is short.** The english checkpoint truncates at 512 tokens; long documents need `predict_long` or the multilingual checkpoint.

## Try it yourself

```bash
cd _code/laya-hello-world
uv run hello_laya.py                    # refund ticket
uv run hello_laya.py --request request-crash.json
uv run hello_laya.py --device cpu       # compare with MPS
uv run route_only.py                    # routing, no downloads
uv run bench_laya.py                    # 100 calls: mean / p50 / p95
```

Edit `request.json` and re-run. The package also ships a CLI: `laya "My payment failed twice" --predict --preset triage`.

## References

- [NandhaKishorM/laya](https://github.com/NandhaKishorM/laya) — official GitHub README (install, quickstart, benchmarks, honest limits).
- [convaiinnovations/laya](https://huggingface.co/convaiinnovations/laya) — official model card with architecture and RLCD training details.
- [Laya documentation site](https://nandhakishorm.github.io/laya/) — official guides and API reference.
- [PyPI: laya](https://pypi.org/project/laya/) — the Python package.
- [PyTorch MPS backend docs](https://pytorch.org/docs/stable/notes/mps.html) — official source for Metal acceleration on Apple Silicon.
- Secondary: the author's [dev.to write-up](https://dev.to/nandakishor_m_6cc0adfde9f/i-built-non-autoregressive-decision-models-a-year-ago-then-a-frontier-lab-called-it-a-18me) on the model's history. Jev comparison numbers are third-party published and flagged as such in the README.
