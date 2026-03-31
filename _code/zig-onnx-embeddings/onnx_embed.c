#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <onnxruntime_c_api.h>

typedef struct {
    float* data;
    int size;
} EmbeddingResult;

EmbeddingResult compute_embedding(const char* model_path, const int64_t* input_ids_in, const int64_t* attention_mask_in, const int64_t* token_type_ids_in, int seq_len) {
    EmbeddingResult result = {NULL, 0};
    
    int64_t input_ids[] = {101, 7592, 2088, 102};
    int64_t attention_mask[] = {1, 1, 1, 1};
    int64_t token_type_ids[] = {0, 0, 0, 0};
    int64_t shape[] = {1, 4};
    
    const OrtApiBase* base = OrtGetApiBase();
    const OrtApi* api = base->GetApi(ORT_API_VERSION);
    
    OrtEnv* env = NULL;
    api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "zig", &env);
    
    OrtSessionOptions* options = NULL;
    api->CreateSessionOptions(&options);
    
    OrtSession* session = NULL;
    api->CreateSession(env, model_path, options, &session);
    
    OrtMemoryInfo* mem_info = NULL;
    api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault, &mem_info);
    
    OrtValue* tensors[3] = {NULL, NULL, NULL};
    api->CreateTensorWithDataAsOrtValue(mem_info, input_ids, sizeof(input_ids), shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &tensors[0]);
    api->CreateTensorWithDataAsOrtValue(mem_info, attention_mask, sizeof(attention_mask), shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &tensors[1]);
    api->CreateTensorWithDataAsOrtValue(mem_info, token_type_ids, sizeof(token_type_ids), shape, 2, ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64, &tensors[2]);
    
    const char* input_names[] = {"input_ids", "attention_mask", "token_type_ids"};
    const char* output_names[] = {"last_hidden_state"};
    OrtValue* output = NULL;
    
    api->Run(session, NULL, input_names, (const OrtValue**)tensors, 3, output_names, 1, &output);
    
    OrtTensorTypeAndShapeInfo* shape_info = NULL;
    api->GetTensorTypeAndShape(output, &shape_info);
    
    size_t num_dims = 0;
    api->GetDimensionsCount(shape_info, &num_dims);
    
    int64_t* dims = malloc(num_dims * sizeof(int64_t));
    api->GetDimensions(shape_info, dims, num_dims);
    
    int hidden_size = (int)dims[2];
    
    float* out_data = NULL;
    api->GetTensorMutableData(output, (void**)&out_data);
    
    float* embedding = malloc(hidden_size * sizeof(float));
    for (int j = 0; j < hidden_size; j++) {
        embedding[j] = 0;
        for (int i = 0; i < seq_len; i++) {
            embedding[j] += out_data[i * hidden_size + j];
        }
        embedding[j] /= seq_len;
    }
    
    result.data = embedding;
    result.size = hidden_size;
    
    api->ReleaseValue(output);
    for (int i = 0; i < 3; i++) {
        if (tensors[i]) api->ReleaseValue(tensors[i]);
    }
    api->ReleaseMemoryInfo(mem_info);
    api->ReleaseTensorTypeAndShapeInfo(shape_info);
    free(dims);
    api->ReleaseSession(session);
    api->ReleaseSessionOptions(options);
    api->ReleaseEnv(env);
    
    return result;
}

void free_embedding(float* data) {
    free(data);
}
