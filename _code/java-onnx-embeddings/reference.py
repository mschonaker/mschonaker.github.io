"""Reference values for the Java pipeline: official HF tokenizers + ONNX Runtime.

Run from this directory (needs model.onnx and tokenizer.json downloaded):

    uvx --with tokenizers --with onnxruntime --with numpy python3 reference.py
"""

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

tok = Tokenizer.from_file("tokenizer.json")
sess = ort.InferenceSession("model.onnx", providers=["CPUExecutionProvider"])

texts = [
    "hello world",
    "The woman is walking.",
    "A lady is walking.",
    "The stock market went up.",
    "café crème",
]


def embed(text):
    enc = tok.encode(text)
    ids = np.array([enc.ids], dtype=np.int64)
    mask = np.array([enc.attention_mask], dtype=np.int64)
    out = sess.run(None, {
        "input_ids": ids,
        "attention_mask": mask,
        "token_type_ids": np.zeros_like(ids),
    })[0][0]
    return (out * mask[0][:, None]).sum(0) / mask[0].sum()


def cos(a, b):
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


for t in texts:
    v = embed(t)
    print(f"embed({t!r}): " + ", ".join(f"{x:.4f}" for x in v[:10]) + f" | norm {np.linalg.norm(v):.4f}")

print(f"cos(walking, lady)  = {cos(embed(texts[1]), embed(texts[2])):.4f}")
print(f"cos(walking, stock) = {cos(embed(texts[1]), embed(texts[3])):.4f}")
