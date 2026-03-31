#ifndef ONNX_EMBED_H
#define ONNX_EMBED_H

#include <stdint.h>

typedef struct {
    float* data;
    int size;
} EmbeddingResult;

EmbeddingResult compute_embedding(const char* model_path, const int64_t* input_ids, const int64_t* attention_mask, const int64_t* token_type_ids, int seq_len);

void free_embedding(float* data);

#endif
