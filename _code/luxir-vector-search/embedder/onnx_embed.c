#include "onnx_embed.h"
#include <onnxruntime_c_api.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct Embedder {
    const OrtApi *api;
    OrtEnv *env;
    OrtSessionOptions *options;
    OrtSession *session;
    OrtMemoryInfo *mem_info;
    OrtValue *inputs[3];
    OrtValue *output;
    OrtTensorTypeAndShapeInfo *shape_info;
    int64_t *shape;
    /* The runtime keeps a pointer to the input buffers for as long as the
       tensors live, so the embedder owns them and copies into them. A caller
       whose own buffer grows or moves would otherwise feed stale memory. */
    int64_t *ids;
    int64_t *mask;
    int64_t *types;
    int seq_cap;
    int dim;
};

static const char *INPUT_NAMES[] = {"input_ids", "attention_mask", "token_type_ids"};
static const char *OUTPUT_NAMES[] = {"last_hidden_state"};

Embedder *embedder_new(const char *model_path, int intra_threads) {
    const OrtApi *api = OrtGetApiBase()->GetApi(ORT_API_VERSION);
    if (api == NULL) {
        fprintf(stderr, "onnxruntime: unsupported API version\n");
        return NULL;
    }

    Embedder *e = calloc(1, sizeof(Embedder));
    if (e == NULL) {
        return NULL;
    }
    e->api = api;

    if (api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "luxir-embed", &e->env) != 0) {
        goto fail;
    }
    if (api->CreateSessionOptions(&e->options) != 0) {
        goto fail;
    }
    api->SetIntraOpNumThreads(e->options, intra_threads > 0 ? intra_threads : 1);
    api->SetInterOpNumThreads(e->options, 1);
    api->SetSessionExecutionMode(e->options, ORT_SEQUENTIAL);
    api->SetSessionGraphOptimizationLevel(e->options, ORT_ENABLE_ALL);

    if (api->CreateSession(e->env, model_path, e->options, &e->session) != 0) {
        goto fail;
    }
    if (api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &e->mem_info) != 0) {
        goto fail;
    }

    return e;

fail:
    fprintf(stderr, "onnxruntime: failed to load %s\n", model_path);
    if (e->session != NULL) {
        api->ReleaseSession(e->session);
    }
    if (e->options != NULL) {
        api->ReleaseSessionOptions(e->options);
    }
    if (e->env != NULL) {
        api->ReleaseEnv(e->env);
    }
    free(e);
    return NULL;
}

int embedder_dim(Embedder *e) {
    if (e->dim > 0) {
        return e->dim;
    }
    /* The embedding width is not in the input signature — [batch, seq] is —
     * so read it off one probe run of the output tensor. */
    const int64_t ids[] = {101, 7592, 2088, 102};
    const int64_t ones[] = {1, 1, 1, 1};
    const int64_t zeros[] = {0, 0, 0, 0};
    float *probe = embedder_embed(e, ids, ones, zeros, 4);
    if (probe == NULL) {
        return 0;
    }
    free(probe);
    return e->dim;
}

float *embedder_embed(Embedder *e, const int64_t *input_ids,
                      const int64_t *attention_mask,
                      const int64_t *token_type_ids, int seq_len) {
    const OrtApi *api = e->api;

    if (seq_len > e->seq_cap) {
        const size_t bytes = (size_t)seq_len * sizeof(int64_t);
        int64_t *ids = realloc(e->ids, bytes);
        int64_t *mask = realloc(e->mask, bytes);
        int64_t *types = realloc(e->types, bytes);
        int64_t *shape = realloc(e->shape, sizeof(int64_t) * 2);
        if (ids == NULL || mask == NULL || types == NULL || shape == NULL) {
            return NULL;
        }
        e->ids = ids;
        e->mask = mask;
        e->types = types;
        e->shape = shape;
        shape[0] = 1;
        shape[1] = seq_len;
        e->seq_cap = seq_len;

        for (int i = 0; i < 3; i++) {
            int64_t *data = (i == 0) ? e->ids : (i == 1) ? e->mask : e->types;
            OrtValue *v = NULL;
            if (api->CreateTensorWithDataAsOrtValue(e->mem_info, data, bytes, shape, 2,
                                                    ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64,
                                                    &v) != 0) {
                return NULL;
            }
            if (e->inputs[i] != NULL) {
                api->ReleaseValue(e->inputs[i]);
            }
            e->inputs[i] = v;
        }
    }

    memcpy(e->ids, input_ids, (size_t)seq_len * sizeof(int64_t));
    memcpy(e->mask, attention_mask, (size_t)seq_len * sizeof(int64_t));
    memcpy(e->types, token_type_ids, (size_t)seq_len * sizeof(int64_t));
    e->shape[1] = seq_len;

    /* The model has a dynamic output shape, so the runtime must allocate the
   output tensor. Pre-allocating it once would pin it to the first sequence
   length and every longer document would fail. */
    OrtValue *output = NULL;
    if (api->Run(e->session, NULL, INPUT_NAMES, (const OrtValue *const *)e->inputs, 3,
                 OUTPUT_NAMES, 1, &output) != 0) {
        return NULL;
    }
    if (e->output != NULL) {
        api->ReleaseValue(e->output);
    }
    e->output = output;

    if (e->shape_info != NULL) {
        api->ReleaseTensorTypeAndShapeInfo(e->shape_info);
        e->shape_info = NULL;
    }
    if (api->GetTensorTypeAndShape(e->output, &e->shape_info) != 0) {
        return NULL;
    }

    int64_t dims[3] = {0, 0, 0};
    if (api->GetDimensions(e->shape_info, dims, 3) != 0) {
        return NULL;
    }
    e->dim = (int)dims[2];

    const float *out = NULL;
    if (api->GetTensorMutableData(e->output, (void **)&out) != 0) {
        return NULL;
    }

    const int dim = e->dim;
    float *pooled = malloc(sizeof(float) * (size_t)dim);
    if (pooled == NULL) {
        return NULL;
    }
    memset(pooled, 0, sizeof(float) * (size_t)dim);

    int live = 0;
    for (int i = 0; i < seq_len; i++) {
        if (attention_mask[i] == 0) {
            continue;
        }
        live++;
        const float *row = out + (size_t)i * (size_t)dim;
        for (int j = 0; j < dim; j++) {
            pooled[j] += row[j];
        }
    }
    if (live > 0) {
        for (int j = 0; j < dim; j++) {
            pooled[j] /= (float)live;
        }
    }
    return pooled;
}

void embedder_free(Embedder *e) {
    if (e == NULL) {
        return;
    }
    const OrtApi *api = e->api;
    for (int i = 0; i < 3; i++) {
        if (e->inputs[i] != NULL) {
            api->ReleaseValue(e->inputs[i]);
        }
    }
    if (e->output != NULL) {
        api->ReleaseValue(e->output);
    }
    if (e->shape_info != NULL) {
        api->ReleaseTensorTypeAndShapeInfo(e->shape_info);
    }
    if (e->mem_info != NULL) {
        api->ReleaseMemoryInfo(e->mem_info);
    }
    if (e->session != NULL) {
        api->ReleaseSession(e->session);
    }
    if (e->options != NULL) {
        api->ReleaseSessionOptions(e->options);
    }
    if (e->env != NULL) {
        api->ReleaseEnv(e->env);
    }
    free(e->shape);
    free(e->ids);
    free(e->mask);
    free(e->types);
    free(e);
}