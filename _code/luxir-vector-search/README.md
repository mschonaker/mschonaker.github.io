# Hybrid Search — Luxir + RRF + a Zig embedder

The [hello-world demo](../luxir-hello-world) ranked 10,000 Algolia products
with BM25 alone. This adds a 384-dimension MiniLM vector per product, searches
it with a `knn` query, and merges the two rankings with reciprocal rank fusion.
The query vector comes from the Zig embedder in `embedder/`.

- Engine: [Luxir](https://luxir.org) 0.1.0 over gRPC, JSON over HTTP
- Data: the [Algolia ecommerce dataset](https://github.com/algolia/datasets/tree/master/ecommerce)
  (10,000 Best Buy products)
- Model: [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
  384 dimensions, cosine

## 1. Build the embedder

```bash
brew install onnxruntime zig
cd embedder
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
zig build -Doptimize=ReleaseFast
zig build test      # seven tokenizer tests against reference ids
```

## 2. Start Luxir

The release binary is Linux x86-64 only, so run it in a container
(natively on Linux, emulated on Apple Silicon). Port 9401 is gRPC:

```bash
curl -fL -o luxir https://github.com/luxir-search/luxir/releases/download/v0.1.0/luxir-0.1.0-linux-x86_64-v2
chmod +x luxir
docker run -d --name luxir --platform linux/amd64 -p 9400:9400 -p 9401:9401 -v "$PWD":/data ubuntu:22.04 /data/luxir
curl http://localhost:9400/health
```

## 3. Declare the metric first

A `_v` field is not searchable until the schema names a similarity metric, and
this call also creates the collection:

```bash
curl -X POST http://localhost:9400/collections/products/_schema \
  -H 'Content-Type: application/json' \
  -d '{"fields":{"embedding_v":{"type":"vector","dims":384,"metric":"cosine"}}}'
```

## 4. Index with vectors

```bash
curl -fL -o bestbuy_seo.json https://raw.githubusercontent.com/algolia/datasets/master/ecommerce/bestbuy_seo.json
go run ./cmd/convert bestbuy_seo.json > products.ndjson

# One process, ten thousand documents, about 65 s on six threads.
./embedder/zig-out/bin/embed \
  --model embedder/model.onnx --tokenizer embedder/tokenizer.json \
  --threads 6 --max-tokens 256 --fields title_t,description_t \
  < products.ndjson > products_v.ndjson

curl -X POST 'http://localhost:9400/collections/products/_update?commit=true' \
  -H 'Content-Type: application/x-ndjson' --data-binary @products_v.ndjson
```

Optional: build the IVF+PQ overlay for approximate search.

```bash
curl -X POST 'http://localhost:9400/collections/products/_update' \
  -H 'Content-Type: application/json' \
  -d '{"commit":{"build_aux_indexes":["vec.embedding_v"]}}'
```

## 5. Run the app

```bash
go run .              # --luxir-grpc localhost:9401 by default
```

Open <http://localhost:8080>. The `Rank by` control switches between the
lexical ranking, the vector ranking, and the fused one; the pool row resizes
each source's candidate window.

## Benchmarks

```bash
./bench.sh                                   # index time, with and without vectors
python3 bench_queries.py                     # per-query latency, all three modes
python3 bench_recall.py                      # approximate vs exact, and ivf.nprobe
python3 bench_app.py http://localhost:8080   # engine round trip, facets included
python3 check_tokenizer.py                   # tokenizer vs huggingface/tokenizers
node test_typeahead.cjs http://localhost:8080 # search box, in a real browser
```

`--bulk-in` on the Go binary runs the embedder over a file and exits, which is
how `products_v.ndjson` can also be produced without the shell pipeline.

## Files

```
embedder/
  main.zig            NDJSON in, NDJSON out; --server keeps it alive
  tokenizer.zig       WordPiece with ## pieces, accent folding, 7 tests
  onnx_embed.c        persistent ONNX Runtime session, mean pooling
embedder/zig-out/bin/embed
templates/            htmx views, srp fragment swaps
main.go               three request shapes: words, vectors, fusion with rrf
luxirpb/              generated gRPC client
```

## Regenerating the gRPC client (optional)

`luxirpb/` is checked in. To regenerate it from the vendored protos,
you need `protoc-gen-go` and `protoc-gen-go-grpc` on your PATH:

```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
go run github.com/bufbuild/buf/cmd/buf@v1.50.0 generate --template buf.gen.yaml protos
```