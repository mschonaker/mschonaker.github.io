# Zig Embeddings - ONNX Model Inference in Pure Zig

A pure Zig implementation for computing sentence embeddings using the MiniLM-L6-v2 model without Python.

## Model Details

- **Model**: [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- **ONNX Version**: [Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2/tree/main/onnx)
- **Embedding Dimension**: 384
- **Quantized Size**: ~52MB (Q4 quantization)

## What This Does

1. Downloads the ONNX model and tokenizer from Hugging Face
2. Parses the BERT WordPiece tokenizer from `tokenizer.json`
3. Tokenizes input text into token IDs
4. (TODO) Runs ONNX model inference via ONNX Runtime C API
5. (TODO) Applies mean pooling to produce sentence embeddings

## Setup

Download the model files:

```bash
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
```

Or let the program download them automatically on first run.

## Running

```bash
zig run main.zig
```

Expected output:
```
Downloading model and tokenizer...
  Downloading model.onnx...
  Downloading tokenizer.json...
Loading tokenizer...
Tokenizing 'hello world'...
Token IDs: 101 7592 2088 102
```

## Tokenization Output

| Token | ID | Description |
|-------|-----|-------------|
| [CLS] | 101 | Classifier token (start) |
| hello | 7592 | First word |
| world | 2088 | Second word |
| [SEP] | 102 | Separator token (end) |

## Validating Against Python

```bash
pip3 install transformers --break-system-packages
python3 -c "
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
print(tok.encode('hello world'))
"
# Output: [101, 7592, 2088, 102]
```

## Validating Online

- [Hugging Face Sentence Transformers Space](https://huggingface.co/spaces/sentence-transformers/Sentence_Transformers_for_semantic_search)
- [tokenizer.io](https://tokenizer.io/)

## Files

- `main.zig` - Main implementation
- `model.onnx` - Quantized ONNX model (~52MB) - download from Hugging Face
- `tokenizer.json` - BERT tokenizer configuration (~700KB) - download from Hugging Face

## Dependencies

- Zig 0.15+
- curl (for downloading files)
- ONNX Runtime (for inference - TODO)

## Installing ONNX Runtime

**macOS:**
```bash
brew install onnxruntime
```

**Linux:** Download from https://onnxruntime.ai/

## References

- [ONNX Runtime C API Documentation](https://onnxruntime.ai/docs/api/c/index.html)
- [Hugging Face Transformers.js](https://huggingface.co/docs/transformers.js)
- [BERT Tokenization Paper](https://arxiv.org/abs/1810.04805)
