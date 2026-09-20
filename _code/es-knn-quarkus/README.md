# es-knn-quarkus

End-to-end semantic product search: MiniLM embeddings computed in Java
(official ONNX Runtime + Hugging Face tokenizers), bulk-indexed into an
Elasticsearch `dense_vector` field, served as kNN search from Quarkus.

Blog post: https://mschonaker.github.io/#article/es-knn-quarkus

## Requirements

| Component | Version |
|-----------|---------|
| JDK | 17+ (tested on 25) |
| Quarkus | 3.39.4 |
| Elasticsearch | 9.5.4 (Docker) |
| com.microsoft.onnxruntime:onnxruntime | 1.30.0 |
| ai.djl.huggingface:tokenizers | 0.38.0 |

## Setup

```bash
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
mkdir -p data && curl -L -o data/records.json \
  https://raw.githubusercontent.com/algolia/datasets/master/ecommerce/records.json

docker run -d --name es9 -p 9200:9200 \
  -e discovery.type=single-node -e xpack.security.enabled=false \
  -e ES_JAVA_OPTS="-Xms1g -Xmx1g" \
  docker.elastic.co/elasticsearch/elasticsearch:9.5.4
```

## Index the catalog

Creates the `products` index (dense_vector, cosine), embeds every product in
batches of 64, and pushes them through the `_bulk` API:

```bash
mvn -q compile exec:java -Dexec.mainClass=Indexer
# done: 10000 docs in 46.5 s (215 docs/s) | embed 44.5 s | bulk 2.0 s
```

## Serve search

```bash
mvn -q package -DskipTests
java -jar target/quarkus-app/quarkus-run.jar
```

Open http://localhost:8080 and try queries like `quiet keyboard for office
work` or `gift for a coffee lover`. The API is also directly usable:

```bash
curl "localhost:8080/api/search?q=protect+my+phone+screen&n=5"
```

## Files

- `Embedder.java` — tokenizer + ONNX session + masked mean pooling (same math as `java-onnx-embeddings`)
- `Indexer.java` — recreate index, batch embed, `_bulk` NDJSON
- `EmbeddingService.java` / `SearchResource.java` — Quarkus CDI bean + `/api/search`
- `src/main/resources/META-INF/resources/index.html` — minimal search page
- `data/records.json` — Algolia ecommerce dataset (downloaded, not committed)

## References

- [Elasticsearch dense_vector](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector)
- [Elasticsearch kNN search](https://www.elastic.co/docs/solutions/search/vector/knn)
- [Quarkus REST guide](https://quarkus.io/guides/rest)
- [algolia/datasets](https://github.com/algolia/datasets)
