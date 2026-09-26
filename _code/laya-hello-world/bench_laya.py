#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Benchmark warm latency over many distinct inputs against one preloaded router."""
import random
import time

from laya import Router

MONTHS = ["January", "March", "April", "July", "October", "December"]
AMOUNTS = [19, 49, 99, 249, 510, 1200]
PRODUCTS = ["the mobile app", "the web dashboard", "the API", "the billing portal", "the sync service"]
OPENERS = [
    "Hi, we were billed twice for {month}. Please refund the duplicate of ${amount} today or we will cancel our plan.",
    "{product} keeps crashing since the update. It blocks our whole team every day.",
    "Quick question about our invoice for {month}: is the ${amount} charge correct?",
    "Cannot log in after the password reset. Support has not answered for two days.",
    "Love the product. Could you add SSO for {product}?",
]

QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which department should handle this?",
        "criteria": {
            "billing": "invoices, payments, refunds",
            "technical": "bugs, outages, system errors",
            "other": "everything else",
        },
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this?",
        "criteria": ["not urgent", "soon", "blocking"],
    },
    "churn_risk": {
        "type": "noul",
        "instructions": "Does the user threaten to cancel or leave?",
    },
}


def make_states(n, rng):
    states = []
    for _ in range(n):
        opener = rng.choice(OPENERS)
        states.append(
            opener.format(
                month=rng.choice(MONTHS),
                amount=rng.choice(AMOUNTS),
                product=rng.choice(PRODUCTS),
            )
        )
    return states


def main():
    rng = random.Random(42)
    states = make_states(100, rng)

    router = Router(device="mps")
    router.preload(["english"])
    router.predict(states[0], QUESTIONS)  # compile/warmup pass, not counted

    samples = []
    answers = {"billing": 0, "technical": 0, "other": 0}
    for state in states:
        t0 = time.perf_counter()
        result = router.predict(state, QUESTIONS)
        samples.append((time.perf_counter() - t0) * 1000)
        answers[result["answers"]["department"]["choice"]] += 1

    samples.sort()
    n = len(samples)
    mean = sum(samples) / n
    p50 = samples[n // 2]
    p95 = samples[int(n * 0.95)]
    print(f"device=mps  n={n}  distinct inputs={len(set(states))}")
    print(f"mean={mean:.1f} ms  min={samples[0]:.1f}  p50={p50:.1f}  p95={p95:.1f}  max={samples[-1]:.1f}")
    print(f"department distribution: {answers}")


if __name__ == "__main__":
    main()
