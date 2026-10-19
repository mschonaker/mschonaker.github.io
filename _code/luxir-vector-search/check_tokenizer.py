#!/usr/bin/env python3
"""Compare this embedder's tokenizer with HuggingFace tokenizers over the
whole product corpus. The first post checked one sentence against Python; this
checks ten thousand documents, token for token."""

import json
import subprocess
import sys

from tokenizers import Tokenizer

EMBED = sys.argv[1] if len(sys.argv) > 1 else "embedder/zig-out/bin/embed"
MODEL = sys.argv[2] if len(sys.argv) > 2 else "embedder/model.onnx"
TOKENIZER = sys.argv[3] if len(sys.argv) > 3 else "embedder/tokenizer.json"
CORPUS = sys.argv[4] if len(sys.argv) > 4 else "products.ndjson"
CLS, SEP = 101, 102


def main():
    ref = Tokenizer.from_file(TOKENIZER)
    docs = [json.loads(line) for line in open(CORPUS)]
    texts = [
        ((d.get("title_t") or "") + ". " + (d.get("description_t") or "")).strip(". ")
        for d in docs
    ]

    payload = b"".join((json.dumps({"title_t": t}) + "\n").encode() for t in texts)
    run = subprocess.run(
        [EMBED, "--model", MODEL, "--tokenizer", TOKENIZER,
         "--max-tokens", "256", "--fields", "title_t", "--dump-tokens"],
        input=payload, capture_output=True, check=True,
    )

    total = identical = 0
    ref_tokens = 0
    shown = 0
    for text, line in zip(texts, run.stdout.splitlines()):
        # The reference pads to a fixed length; cut at [SEP] so the two are
        # comparing token sequences, not padding policy.
        want = ref.encode(text, add_special_tokens=True).ids
        want = want[:want.index(SEP) + 1] if SEP in want else want
        got = [int(x) for x in line.split()]
        total += 1
        ref_tokens += len(want)
        if want == got:
            identical += 1
        else:
            at = next((n for n, (a, b) in enumerate(zip(want, got)) if a != b),
                      min(len(want), len(got)))
            if shown < 5:
                shown += 1
                inv = {i: t for t, i in ref.get_vocab().items()}
                lo = max(0, at - 6)
                a = " ".join(inv.get(i, "?") for i in want[lo:at + 6])
                b = " ".join(inv.get(i, "?") for i in got[lo:at + 6])
                print(f"  text   {text[:70]}")
                print(f"  at {at} of {len(want)}/{len(got)}")
                print(f"  ref    ...{a}")
                print(f"  zig    ...{b}")

    print()
    print(f"documents compared       {total:,}")
    print(f"token sequences equal    {identical:,}  ({identical / total:.2%})")
    print(f"mean tokens per document {ref_tokens / total:.1f}")


if __name__ == "__main__":
    main()