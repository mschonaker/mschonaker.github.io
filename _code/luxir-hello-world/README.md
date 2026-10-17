# Hello World Search — Luxir + Go + htmx

A minimal ecommerce search app: typeahead, a search results page with
multi-select facets, and a product page with breadcrumbs. The engine is
[Luxir](https://luxir.org) 0.1.0; the Go server talks to it over gRPC.
The data is the
[Algolia ecommerce dataset](https://github.com/algolia/datasets/tree/master/ecommerce)
(10,000 Best Buy products).

## 1. Start Luxir

The release binary is Linux x86-64 only, so run it in a container
(natively on Linux, emulated on Apple Silicon). Port 9401 is gRPC:

```bash
curl -fL -o luxir https://github.com/luxir-search/luxir/releases/download/v0.1.0/luxir-0.1.0-linux-x86_64-v2
chmod +x luxir
docker run -d --name luxir --platform linux/amd64 -p 9400:9400 -p 9401:9401 -v "$PWD":/data ubuntu:22.04 /data/luxir
curl http://localhost:9400/health
```

## 2. Index the dataset

```bash
curl -fL -o bestbuy_seo.json https://raw.githubusercontent.com/algolia/datasets/master/ecommerce/bestbuy_seo.json
go run ./cmd/convert bestbuy_seo.json > products.ndjson
curl -X POST 'http://localhost:9400/collections/products/_update?commit=true' \
  -H 'Content-Type: application/x-ndjson' --data-binary @products.ndjson
```

The response is `{"update_version":1,"status":"ok"}`. The collection and
its schema were created automatically from the field-name suffixes.

## 3. Run the app

```bash
go run .              # --luxir-grpc localhost:9401 by default
```

Open <http://localhost:8080>.

## Regenerating the gRPC client (optional)

`luxirpb/` is checked in. To regenerate it from the vendored protos,
you need `protoc-gen-go` and `protoc-gen-go-grpc` on your PATH:

```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
go run github.com/bufbuild/buf/cmd/buf@v1.50.0 generate --template buf.gen.yaml protos
```
