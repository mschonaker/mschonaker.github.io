---
id: pca-knn
title: Shrinking Embeddings: PCA Versus Elasticsearch's Built-In Quantization
summary: Project MiniLM vectors from 384 to 128, 64, and 32 dimensions with a hand-run PCA and compare recall, latency, and storage against Better Binary Quantization on the same kNN index.
date: 2026-09-20
image: /images/pca-knn.jpg
---

# Shrinking Embeddings: PCA Versus Elasticsearch's Built-In Quantization

[Semantic Product Search with Elasticsearch kNN and Quarkus](/#article/es-knn-quarkus) closed with a promise: the 384-dimension vectors are honest but heavy, and the series should test whether they can be smaller. This post runs that experiment. It fits a real PCA — covariance plus Jacobi eigendecomposition, about 150 lines of plain Java — projects the catalog to 128, 64, and 32 dimensions, and measures recall@10, latency, and storage for every option. The control group is `bbq_hnsw`, the quantization Elasticsearch 9 already applies to these vectors by default.

The headline finding is uncomfortable for PCA and useful to know: **the built-in beats the hand-rolled one, by a wide margin, at every dimension worth caring about.**

## Setup

Same building blocks as the previous two posts:

| Component | Version |
|-----------|---------|
| JDK | 25.0.2 |
| Elasticsearch | 9.5.4 (Docker) |
| com.microsoft.onnxruntime:onnxruntime | 1.30.0 |
| ai.djl.huggingface:tokenizers | 0.38.0 |
| Catalog | Algolia ecommerce, 10,000 products |

One embedding pass over the 10,000 product texts produces the 384-dimension vectors. Everything downstream — PCA fit, all six experiment indexes — is built from that one pass, so the only variable is how vectors are stored.

## How PCA Works Here

PCA finds the directions that capture the most variance in the data and keeps only the top ones. Three steps:

1. **Center** the data: subtract the mean vector from every embedding.
2. **Covariance**: form the 384 × 384 matrix C = XᵀX / (n − 1).
3. **Eigendecompose** C; the top-k eigenvectors are the new axes. A vector x becomes `(x − mean) · Vᵀ` — k numbers instead of 384.

Step 3 uses a cyclic Jacobi eigendecomposition: repeatedly rotate the matrix to zero out its off-diagonal entries; the accumulated rotations are the eigenvectors. It is old, simple, and completely adequate for a 384 × 384 matrix:

```java
double theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
double t = Math.signum(theta) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
double c = 1 / Math.sqrt(t * t + 1);
double s = t * c;
// apply rotation (c, s) to rows/columns p and q of the matrix and the accumulator
```

Fitting all 10,000 vectors takes **1.1 seconds**. The `Pca` class is 180 lines: `Pca.java` in `_code/pca-knn/`.

The first useful number falls out of the fit itself — the share of total variance kept by the top dimensions:

| Kept dims | Variance explained |
|-----------|--------------------|
| 128 | 87.9% |
| 64 | 71.9% |
| 32 | 55.3% |

88% of the variance at one-third the dimensions sounds like a free lunch. Hold that thought.

## The Experiment

`Build.java` creates nine indexes, all with `dense_vector`, `similarity: cosine`, 10,000 documents each. They differ only in vector content:

| Index | Dims | Vector content | index_options |
|-------|------|----------------|---------------|
| products_hnsw | 384 | original floats | `hnsw` (plain, uncompressed) |
| products_bbq | 384 | original floats | `bbq_hnsw` (Elasticsearch default ≥9.1) |
| products_pca128 | 128 | PCA-projected | `hnsw` |
| products_pca64 | 64 | PCA-projected | `hnsw` |
| products_pca32 | 32 | PCA-projected | `hnsw` |
| products_pca128bbq | 128 | PCA-projected | `bbq_hnsw` |
| products_flat384 | 384 | original floats | `flat` (brute force, no graph) |
| products_flat128 | 128 | PCA-projected | `flat` |
| products_flat32 | 32 | PCA-projected | `flat` |

The `bbq` rows answer whether the two techniques stack; the `flat` rows isolate scoring cost — with no graph to traverse, `took` is the raw price of scoring 10,000 vectors at that dimensionality.

`Eval.java` runs 20 shopping queries ("quiet keyboard for office work", "air fryer for healthy cooking", ...). For each query:

1. Embed to 384 dimensions, project as the index requires.
2. kNN search: `k: 10, num_candidates: 100` — identical budget for every index.
3. **Ground truth** comes from a `script_score` brute-force cosine scan over the plain float index — exact top-10 against exact vectors.
4. Recall@10 = fraction of the exact top-10 that each index returned.

The plain 384-dimension HNSW scores a recall of 1.000 against that truth, which validates both the harness and how far from exact HNSW is at this tiny scale.

## Results

```
index,               dims, recall@10, mean_took_ms, mean_wall_ms, store_mb
products_hnsw,        384,   1.000,       1.0,         4.2,          15
products_bbq,         384,   0.935,       0.9,         3.8,          15
products_pca128,      128,   0.765,       0.9,         3.7,           5
products_pca64,        64,   0.520,       0.3,         3.3,           2
products_pca32,        32,   0.375,       0.3,         3.3,           1
products_pca128bbq,   128,   0.675,       0.7,         3.4,           5
products_flat384,     384,   1.000,       1.7,         4.8,          14
products_flat128,     128,   0.765,       0.6,         3.4,           1
products_flat32,       32,   0.375,       0.2,         3.0,           1
```

A few honest caveats before reading it: `took` is the Elasticsearch-side time and is a coarse clock at this scale; end-to-end wall time (embedding plus search plus HTTP) sat between 3.0 and 4.8 ms for every variant. Exact sizes from `_cat/indices` tell the storage story more precisely: 15.8 MB plain, 15.6 MB BBQ, 5.3 / 2.8 / 1.6 MB for PCA-128/64/32. Recall numbers drift ±0.01 between runs because HNSW construction is randomized. And 20 queries is a sample, not a benchmark suite. None of that changes the shape of the result.

### Reading the table

**BBQ keeps 93.5% of the exact ranking with zero configuration.** It is the default for 384-dimension float vectors since Elasticsearch 9.1, it needs no training data, no projection matrix to version alongside your model, and no retraining if the corpus drifts.

**PCA at 128 dimensions loses almost a quarter of the top-10**, even though it keeps 87.9% of the variance. Variance and ranking quality are different things. Variance counts total squared distance; ranking cares about which neighbor is *closest*. Discarding the low-variance tail still shuffles the close calls, and close calls are the entire content of a top-10 list.

**The storage column is the one place PCA clearly wins.** HNSW-on-PCA scales linearly with dimension: 15.0 → 5.3 → 2.8 → 1.6 MB. BBQ is flat or worse on disk — it quantizes the *memory* representation but keeps raw floats on disk for rescoring and reindexing (the official docs call this out explicitly). PCA is a disk-and-compute reducer; BBQ is a memory reducer. If your pain is the RAM bill from the HNSW graphs, the table says buy BBQ's memory discount for free and stop there.

**Stacking works but inherits PCA's loss.** PCA-128 + BBQ costs about 8 recall points over BBQ alone and keeps the disk win. It is the right shape only if you must reduce all three axes at once.

**Latency separates where scoring dominates — and that is measured, not projected.** The `flat` rows are brute-force indexes: no graph, every score touches every dimension, so the `took` column is pure scoring cost. Dropping dimensions cut it from 1.7 ms (384) to 0.6 ms (128) and 0.2 ms (32) — almost exactly proportional to the dimension count. That is the performance lever people mean when they say "fewer dimensions": less work per score, forever, on every query. Inside HNSW at 10k vectors, graph traversal hides most of that win; it re-emerges at million-vector scale, on high-recall settings that visit many candidates, and on any brute-force or rescoring path.

## Two Levers: Memory Versus Compute

The comparison is really about two different resources, and the techniques pull different ones:

- **BBQ shrinks the bytes per dimension.** The graph keeps 384 dimensions but stores 1 bit each, so the memory footprint of the vector index drops ~32x. Scoring still touches all 384 dimensions — through fast bit operations instead of float multiply-adds, so the per-score *constant* improves, but the work still scales with dimension count.
- **PCA shrinks the dimension count.** Every similarity score, graph entry, and stored value drops from 384 numbers to k. That is the lever when scoring cost dominates: brute-force search, high-recall settings with many visited candidates, rescoring paths, or million-vector workloads.

The `flat` rows in the results show the compute lever in its purest form: scoring time fell from 1.7 ms to 0.6 to 0.2 as dimensions fell from 384 to 128 to 32 — nearly proportional. The two levers stack: PCA-128 plus BBQ compresses the memory of a 128-dimension index (5.5 MB on disk, same as PCA-128 alone, because BBQ keeps raw floats on disk either way).

If your bill is RAM for the vector graphs, BBQ is free money. If your bill is CPU for scoring, only fewer dimensions pay it down — and no quantization setting will do that for you.

## Isn't This Just a Smaller Model?

Half right. Operationally both give you a k-dimension vector to index, and costs scale with k identically. Mechanically, embed-then-project is even equivalent to prepending a frozen linear layer to the model — PCA just derives that layer's weights from the data's variance instead of learning them.

The difference is what the dimensions are for. A model trained natively at k dimensions optimizes every surviving dimension for the similarity task — contrastive training pushes what separates neighbors into whatever width it gets. PCA keeps the directions where the data cloud *spreads*, not where neighbors *separate*. Variance and ranking quality are different objectives, and the gap is measurable: 87.9% of variance kept at 128 dimensions bought only 0.765 recall.

The industry's trained answer to "a smaller model" is Matryoshka representation learning: models like bge, nomic, or jina are trained so the first N dimensions work alone, and truncation replaces projection. With such a model, "smaller index" needs no PCA at all — you slice the vector. MiniLM-L6-v2 is not one of those models, which is why this experiment needed the projection in the first place.

And PCA has one more cost a smaller model never has: the projection is fitted on *your corpus*. Ship the catalog to a different domain and the variance structure shifts; the matrix is now a versioned artifact next to your model.

## What I Would Actually Ship

For this stack — MiniLM-L6-v2, Elasticsearch 9.5, kNN product search — the winning configuration is the one the previous post already had: plain float vectors, default `bbq_hnsw`, tune `num_candidates` if recall matters. **PCA earns its complexity only when the reduced dimensionality itself is the goal**: exporting small vectors to a browser or edge device, feeding a downstream model with a width budget, or shrinking a brute-force flat index. If the goal is simply "cheaper kNN in Elasticsearch", use the built-in quantization.

A useful intuition for why the ranking collapses: MiniLM's 384 dimensions look statistically near-isotropic — no dimension dominates — so there is no fat to trim. PCA thrives on redundant, correlated dimensions; a trained transformer embeds away most of that redundancy already.

## Files and Reproduce

```
_code/pca-knn/
├── pom.xml
├── src/main/java/
│   ├── Embedder.java   # tokenizer + ONNX + masked mean pooling (from the Java post)
│   ├── Pca.java        # covariance + Jacobi eigendecomposition + project/save/load
│   ├── Es.java         # plain REST client: create index, bulk, stats
│   ├── Build.java      # one embedding pass -> fit -> nine indexes
│   └── Eval.java       # 20 queries, recall@10 vs exact, latency, size
└── queries.txt
```

With Elasticsearch 9.5.4 running and the model files downloaded:

```bash
mvn -q compile exec:java -Dexec.mainClass=Build
mvn -q exec:java -Dexec.mainClass=Eval
```

## Next Up: Weighting the Variance by Query Frequency

One limitation of everything above is silent: the PCA fit treats all 10,000 products as equally important, so the kept subspace serves the *corpus* — not the *traffic*. Real catalogs are skewed; a small head of queries carries most of the value, and plain PCA has no way to know which products those queries touch.

The fix is a small change to the fit, not a new method. **Traffic-weighted PCA**:

1. Build a weight per product from traffic — how often it appears (or gets clicked) in results for the frequent queries. This dataset ships a `popularity` field, a zero-log proxy that keeps the experiment reproducible; production systems would use aggregated query logs.
2. Fit the covariance on weighted vectors: scale each product by the square root of its weight, center with the weighted mean, and run the same Jacobi pass. The top eigenvectors then rotate toward the regions of the space where popular products — and the queries that find them — actually live.
3. A stronger variant also fits on the embedded frequent queries themselves, so the projection preserves the query-side geometry, which product-only PCA never sees.

The evaluation design writes itself: split the query set into head terms and long-tail terms, measure recall@10 for each group separately, and compare plain PCA against popularity-weighted PCA at 32 and 128 dimensions. The expected finding — several recall points gained on the head, paid for on the tail — turns a hidden trade-off into a visible dial. The risks are equally concrete: weights are a hyperparameter that needs a sensitivity sweep (linear versus log popularity), and the tail pays for the head, which is a business decision more than a technical one.

This post stops at the proposal; the experiment is the next article's to run.


Four posts, one throughline: sentence embeddings are a dependency you can own. [Zig computes them through the ONNX C API](/#article/zig-onnx-embeddings), [two Maven artifacts do the same job inside the JVM with the reference tokenizer](/#article/java-onnx-embeddings), [Elasticsearch turns them into a search service](/#article/es-knn-quarkus), and this post shows the storage layer already does the compression job that PCA tried to hand-roll. Measure before you shrink.

## References

- [Elasticsearch dense_vector field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/dense-vector) — quantization types, default `bbq_hnsw` for ≥384-dim float vectors since 9.1, and the note that quantized indexes keep raw vectors on disk
- [Better Binary Quantization (BBQ)](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/bbq) — official BBQ design: 1 bit per dimension plus corrective factors, oversampling, 32× memory reduction
- [Approximate kNN search tuning](https://www.elastic.co/docs/deploy-manage/production-guidance/optimize-performance/approximate-knn-search) — official `num_candidates` and recall guidance
- [Jacobi eigenvalue algorithm](https://en.wikipedia.org/wiki/Jacobi_eigenvalue_algorithm) — standard reference for the cyclic rotation method used here
- [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) — the model and its 384-dimension output
- The earlier series posts: [Zig embeddings](/#article/zig-onnx-embeddings), [pure Java embeddings](/#article/java-onnx-embeddings), [kNN search with Quarkus](/#article/es-knn-quarkus) (official docs used above; the series posts are my own ecosystem sources)
