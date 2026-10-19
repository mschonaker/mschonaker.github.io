#ifndef LUXIR_EMBED_H
#define LUXIR_EMBED_H

#include <stdint.h>

/* A loaded ONNX Runtime session that is reused for every text. The
   hello-world version created and released the session per call; over
   ten thousand products that cost more than the inference did. */
typedef struct Embedder Embedder;

Embedder *embedder_new(const char *model_path, int intra_threads);
int embedder_dim(Embedder *e);

/* Mean-pools last_hidden_state over the unmasked positions and returns
   a malloc'd float[embedder_dim(e)]. NULL on failure. */
float *embedder_embed(Embedder *e, const int64_t *input_ids,
                      const int64_t *attention_mask,
                      const int64_t *token_type_ids, int seq_len);
void embedder_free(Embedder *e);

#endif