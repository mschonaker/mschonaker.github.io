# pca-knn

Experiment: how far can MiniLM's 384-dimension embeddings shrink before kNN
search quality collapses? Hand-run PCA (cyclic Jacobi eigendecomposition) at
128/64/32 dimensions, compared against Elasticsearch's default Better Binary
Quantization (`bbq_hnsw`) on the same 10,000-product catalog.

Blog post: https://mschonaker.github.io/#article/pca-knn

## Requirements

| Component | Version |
|-----------|---------|
| JDK | 17+ (tested on 25) |
| Elasticsearch | 9.5.4 (Docker) — must be running on localhost:9200 |
| com.microsoft.onnxruntime:onnxruntime | 1.30.0 |
| ai.djl.huggingface:tokenizers | 0.38.0 |

## Setup

Model files (symlinks to the `java-onnx-embeddings` copies work locally):

```bash
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
```

## Run

```bash
# one embedding pass -> PCA fit -> nine indexes (products_hnsw, products_bbq,
# products_pca128/64/32, products_pca128bbq, products_flat384/128/32)
mvn -q compile exec:java -Dexec.mainClass=Build

# 20 queries x 9 indexes: recall@10 vs exact ground truth, latency, store size
mvn -q exec:java -Dexec.mainClass=Eval
```

Feel the differences in a browser (index selector, same query across variants):

```bash
mvn -q exec:java -Dexec.mainClass=SearchServer
# open http://localhost:8090
```

Expected eval table:

```
index, dims, recall@10, mean_took_ms, mean_wall_ms, store_mb
products_hnsw, 384, 1.000, 1.0, 4.4, 15
products_bbq,  384, 0.935, 1.3, 6.4, 15
products_pca128, 128, 0.765, 1.0, 4.0, 5
products_pca64, 64, 0.520, 0.8, 3.8, 2
products_pca32, 32, 0.375, 0.8, 3.6, 1
products_pca128bbq, 128, 0.685, 0.9, 3.8, 5
```

## Files

- `Pca.java` — mean, covariance, cyclic Jacobi eigendecomposition, projection, save/load
- `Build.java` — one embedding pass, PCA fit, builds all experiment indexes
- `Eval.java` — recall@10 against exact `script_score` ground truth, latency, store size
- `SearchServer.java` — minimal JDK HTTP server with a variant selector, to feel the differences
- `Es.java` — plain REST helpers over `java.net.http`
- `Embedder.java` — same embedding math as the series' Java post
- `queries.txt` — the 20 evaluation queries

## References

- [Elasticsearch dense_vector](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)
- [Better Binary Quantization (BBQ)](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/bbq)
- [Jacobi eigenvalue algorithm](https://en.wikipedia.org/wiki/Jacobi_eigenvalue_algorithm)
