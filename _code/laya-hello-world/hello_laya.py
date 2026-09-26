#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Laya hello world: run one editable request.json through the Router."""
import argparse
import json
import time
from pathlib import Path

from laya import Router


def show(answers):
    for name, ans in answers.items():
        kind = ans.get("type") or ("choice" if "choice" in ans else "noul" if "noul" in ans else "score")
        if "choice" in ans:
            probs = ans.get("probabilities", ans.get("options", {}))
            print(f"  {name:14s} choice -> {ans['choice']!r}  conf={ans.get('confidence', ans.get('answer_confidence'))}")
        elif "score" in ans:
            probs = ans.get("distribution", ans.get("levels", {}))
            print(f"  {name:14s} score  -> {ans['score']}  conf={ans.get('confidence', ans.get('answer_confidence'))}")
        else:
            probs = None
            print(f"  {name:14s} noul   -> p(true)={ans['noul']:.3f}")
        if isinstance(probs, dict) and probs:
            inner = ", ".join(f"{k}: {v:.3f}" for k, v in probs.items())
            print(f"  {'':14s}          [{inner}]")
        extras = {k: v for k, v in ans.items() if k not in ("type", "choice", "score", "noul", "confidence", "probabilities", "options", "distribution", "levels")}
        if extras:
            print(f"  {'':14s}          keys={list(extras)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", default=str(Path(__file__).parent / "request.json"))
    ap.add_argument("--device", default=None, help="cpu | mps (default: laya auto-select)")
    ap.add_argument("--model", default=None, help="force english | multilingual | typed-decisions")
    args = ap.parse_args()

    req = json.loads(Path(args.request).read_text())
    router = Router(**({"device": args.device} if args.device else {}))

    t0 = time.perf_counter()
    result = router.predict(req["state"], req["questions"], **({"model": args.model} if args.model else {}))
    cold = (time.perf_counter() - t0) * 1000

    routing = result.get("routing", {})
    print(f"routed : {routing.get('model')}  ({routing.get('reason')})")
    print(f"state  : {json.dumps(req['state'])[:100]}")
    print("answers:")
    show(result["answers"])
    print(f"usage  : {result.get('usage')}")

    t0 = time.perf_counter()
    router.predict(req["state"], req["questions"], **({"model": args.model} if args.model else {}))
    warm = (time.perf_counter() - t0) * 1000
    print(f"timing : first={cold:.0f} ms (incl. checkpoint load)  warm={warm:.0f} ms")


if __name__ == "__main__":
    main()
