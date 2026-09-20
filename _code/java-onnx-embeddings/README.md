# java-onnx-embeddings

Sentence embeddings (all-MiniLM-L6-v2) in pure Java. No Zig, no native build
step: the official ONNX Runtime Java binding runs the model, and the DJL
binding to Hugging Face `tokenizers` handles WordPiece tokenization.

Blog post: https://mschonaker.github.io/#article/java-onnx-embeddings

## Requirements

| Component | Version |
|-----------|---------|
| JDK | 17+ (tested on 25) |
| Maven | 3.9.x |
| com.microsoft.onnxruntime:onnxruntime | 1.30.0 |
| ai.djl.huggingface:tokenizers | 0.38.0 |

## Files

Download the model and tokenizer once:

```bash
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
```

## Run

```bash
mvn -q compile exec:java -Dexec.mainClass=EmbedJava
```

Expected validation output:

```
Token IDs: 101 7592 2088 102
Embedding (first 10 dims): -0.1761, 0.2930, 0.1513, -0.0303, -0.1342, -0.7992, 0.2508, 0.0200, -0.3306, 0.0226
Embedding norm: 5.9607
```

Extra knobs:

```bash
# embed an arbitrary text
mvn -q exec:java -Dexec.mainClass=EmbedJava -Dtext="café crème"
# benchmark one-at-a-time vs a single batched call
mvn -q exec:java -Dexec.mainClass=EmbedJava -Dbench=500
```

## References

- [ONNX Runtime Java API](https://onnxruntime.ai/docs/api/java/)
- [DJL Hugging Face tokenizers](https://docs.djl.ai/master/extensions/tokenizers/index.html)
- [Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2)
