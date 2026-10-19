#!/usr/bin/env python3
"""Compare the WordPiece rule from the first post with the one used here.

The first post's greedy scan never prefixed continuation pieces with "##", so
every word that is not a whole vocabulary entry was split into whatever
standalone words happened to match, and the rest was thrown away."""

import json
import re
import sys

CLS, SEP, UNK = 101, 102, 100
WORD = re.compile(r"[A-Za-z0-9']+")


def old_pieces(word, vocab):
    """First post: longest match from the start, no '##', then give up."""
    for end in range(len(word), 0, -1):
        if word[:end] in vocab:
            return [vocab[word[:end]]]
    return [UNK]


def new_pieces(word, vocab, max_word_chars=24):
    """WordPiece: longest entry at the start, then longest '##' continuation."""
    start = 0
    while start < len(word):
        limit = min(len(word), start + max_word_chars)
        for end in range(limit, start, -1):
            piece = word[start:end] if start == 0 else "##" + word[start:end]
            if piece in vocab:
                return [vocab[piece]]
        if start == 0:
            return [UNK]
        start += 1
    return []


def main():
    vocab = json.load(open(sys.argv[1]))["model"]["vocab"]
    inv = {i: t for t, i in vocab.items()}

    words = diff = unk_old = unk_new = 0
    shorter = []
    for line in open(sys.argv[2]):
        d = json.loads(line)
        for word in WORD.findall(d.get("title_t", "") + " " + d.get("description_t", "")):
            words += 1
            a, b = old_pieces(word.lower(), vocab), new_pieces(word.lower(), vocab)
            unk_old += UNK in a
            unk_new += UNK in b
            if a != b:
                diff += 1
                if len(b) < len(a) or len(shorter) < 8:
                    shorter.append((word, a, b))

    print(f"words tokenized           {words:,}")
    print(f"old rule != new rule      {diff:,}  ({diff / words:.1%})")
    print(f"words with [UNK], old     {unk_old:,}  ({unk_old / words:.2%})")
    print(f"words with [UNK], new     {unk_new:,}  ({unk_new / words:.2%})")
    print()
    for word, a, b in shorter[:8]:
        print(f"  {word:<20} old={[inv[i] for i in a]}")
        print(f"  {'':<20} new={[inv[i] for i in b]}")


if __name__ == "__main__":
    main()