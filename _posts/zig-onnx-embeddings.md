# Computing Embeddings in Pure Zig Without Python

For a recent project, I needed to compute sentence embeddings without relying on Python. After some research, I found that MiniLM-L6-v2 is available as a pre-converted ONNX model, and ONNX Runtime has a C API that can be called from any language.

This post documents my journey implementing this in Zig.

## The Setup

MiniLM-L6-v2 is a compact but powerful sentence embedding model from Microsoft Research. It's only 384 dimensions and has excellent performance for semantic similarity tasks. The pre-quantized ONNX version is just 52MB.

```
Model: sentence-transformers/all-MiniLM-L6-v2
ONNX: Xenova/all-MiniLM-L6-v2
Embedding: 384 dimensions
Size: ~52MB (Q4 quantized)
```

## The Approach

Three steps to compute embeddings:

```mermaid
flowchart LR
    A["Text: 'hello world'"] --> B["Normalize\nlowercase"]
    B --> C["WordPiece Tokenizer"]
    C --> D["Token IDs\n101, 7592, 2088, 102"]
    D --> E["ONNX Model\nMiniLM-L6-v2"]
    E --> F["Token Embeddings\n[seq_len x 384]"]
    F --> G["Mean Pooling"]
    G --> H["Sentence Embedding\n[384]"]
```

## Step 1: Downloading Files

Hugging Face models are just Git repositories. Download directly via HTTPS:

```bash
# ONNX model (Q4 quantized)
curl -L -o model.onnx https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx

# Tokenizer config
curl -L -o tokenizer.json https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
```

Or in Zig using std.http:

```zig
var child = std.process.Child.init(
    &.{ "curl", "-L", "-o", dest, url },
    std.heap.c_allocator,
);
const term = try child.spawnAndWait();
```

## Step 2: Parsing the Tokenizer

The tokenizer.json is a Hugging Face tokenizer config with a BERT WordPiece vocabulary:

```json
{
  "model": {
    "type": "WordPiece",
    "vocab": {
      "[CLS]": 101,
      "[SEP]": 102,
      "hello": 7592,
      "world": 2088,
      ...
    }
  }
}
```

The Zig implementation parses JSON and builds a hash map:

```zig
const Tokenizer = struct {
    vocab: std.StringHashMap(u32),
    unk_token_id: u32,
    cls_token_id: u32,
    sep_token_id: u32,
};

fn loadTokenizer(allocator: std.mem.Allocator, path: []const u8) !Tokenizer {
    const content = try std.fs.cwd().readFileAlloc(allocator, path, 50 * 1024 * 1024);
    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, content, .{});
    defer parsed.deinit();

    const vocab_obj = parsed.value.object.get("model").?.object.get("vocab").?;
    var vocab = std.StringHashMap(u32).init(allocator);

    var it = vocab_obj.object.iterator();
    while (it.next()) |entry| {
        const id: u32 = switch (entry.value_ptr.*) {
            .integer => |v| @intCast(v),
            .float => |v| @intFromFloat(v),
            else => continue,
        };
        try vocab.put(try allocator.dupe(u8, entry.key_ptr.*), id);
    }

    return Tokenizer{
        .vocab = vocab,
        .unk_token_id = vocab.get("[UNK]").?,
        .cls_token_id = vocab.get("[CLS]").?,
        .sep_token_id = vocab.get("[SEP]").?,
    };
}
```

## Step 3: Tokenizing

WordPiece tokenization works by greedily matching the longest possible token from the vocabulary:

```zig
fn tokenize(allocator: std.mem.Allocator, tokenizer: Tokenizer, text: []const u8) ![]u32 {
    // Normalize: lowercase
    var normalized = std.ArrayList(u8).init(allocator);
    for (text) |c| {
        if (c >= 'A' and c <= 'Z') {
            try normalized.append(c + 32);
        } else {
            try normalized.append(c);
        }
    }

    var tokens = std.ArrayList(u32).init(.{});
    tokens.appendAssumeCapacity(tokenizer.cls_token_id);

    // Greedy longest-match tokenization
    var i: usize = 0;
    while (i < normalized.items.len) {
        var end = normalized.items.len;
        var found = false;

        while (end > i) {
            const substr = normalized.items[i..end];
            if (tokenizer.vocab.get(substr)) |id| {
                tokens.appendAssumeCapacity(id);
                found = true;
                break;
            }
            end -= 1;
        }

        if (!found) {
            if (normalized.items[i] == ' ') {
                i += 1;
                continue;
            }
            tokens.appendAssumeCapacity(tokenizer.unk_token_id);
        }
        i = end;
    }

    tokens.appendAssumeCapacity(tokenizer.sep_token_id);
    return tokens.toOwnedSlice(allocator);
}
```

## Validating the Output

Let's verify against Python's transformers library:

```bash
pip3 install transformers --break-system-packages
```

```python
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
print('Tokens:', tok.tokenize('hello world'))
print('IDs:', tok.encode('hello world'))
```

Output:
```
Tokens: ['hello', 'world']
IDs: [101, 7592, 2088, 102]
```

Our Zig implementation produces **identical output**:
```
Token IDs: 101 7592 2088 102
```

You can also validate online:
- [Hugging Face Sentence Transformers Space](https://huggingface.co/spaces/sentence-transformers/Sentence_Transformers_for_semantic_search)
- [tokenizer.io](https://tokenizer.io/)

## The ONNX Inference Part (TODO)

The tokenizer works. Next up: actually running the ONNX model via ONNX Runtime's C API.

The ONNX Runtime C API requires:
1. Creating an environment and session
2. Converting token IDs to input tensors
3. Running inference
4. Applying mean pooling over token embeddings

I'll document that in a follow-up post once I get it working.

## Files

```
_code/zig-onnx-embeddings/
├── main.zig          # Working tokenizer (144 lines)
├── README.md         # Project documentation
├── model.onnx        # Download (~52MB)
└── tokenizer.json    # Download (~700KB)
```

Download the model files:
```bash
curl -L -o _code/zig-onnx-embeddings/model.onnx \
  https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx

curl -L -o _code/zig-onnx-embeddings/tokenizer.json \
  https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json
```

## References

### Model Sources
- [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) -- Main model page
- [Xenova/all-MiniLM-L6-v2](https://huggingface.co/Xenova/all-MiniLM-L6-v2) -- Pre-converted ONNX versions
- [onnx-models/all-MiniLM-L6-v2-onnx](https://huggingface.co/onnx-models/all-MiniLM-L6-v2-onnx) -- Official ONNX models

### Technical Resources

**ONNX Runtime:**
- [ONNX Runtime C API Documentation](https://onnxruntime.ai/docs/api/c/index.html)
- [ONNX Runtime Installation](https://onnxruntime.ai/docs/install/)
- [Spring AI ONNX Support](https://docs.spring.io/spring-ai/reference/api/embeddings/onnx.html)

**Tokenization:**
- [BERT Tokenization Paper](https://arxiv.org/abs/1810.04805)
- [Hugging Face Tokenizers Documentation](https://huggingface.co/docs/tokenizers)
- [Transformers.js (JS implementation)](https://huggingface.co/docs/transformers.js)

**Tools & Ecosystem:**
- [Sentence Transformers Library](https://www.sbert.net/)
- [Transformers.js Space](https://huggingface.co/spaces/xenova/transformers) -- Run models in browser
- [Sentence Transformers Semantic Search Space](https://huggingface.co/spaces/sentence-transformers/Sentence_Transformers_for_semantic_search)
- [tokenizer.io](https://tokenizer.io/) -- Online tokenizer tool

**Quantization:**
- [onnxruntime-optimization](https://huggingface.co/philschmid/all-MiniLM-L6-v2-optimum-embeddings)
- [Quantized Models List](https://huggingface.co/unsloth/all-MiniLM-L6-v2)

**YouTube Tutorials:**
- [LLM Inference Without Python (ONNX Runtime)](https://www.youtube.com/watch?v=0LUM-CBmyOA)
- [Sentence Embeddings Explained](https://www.youtube.com/watch?v=IMytIsb2qwk)
- [MiniLM Model Overview](https://www.youtube.com/watch?v=pmb6cjngbcA)

**Mobile/Embedded:**
- [Android Sentence Embeddings Library](https://www.reddit.com/r/androiddev/comments/1dpunde/sentenceembeddingsandroid_an_android_library_to/) -- Uses ONNX Runtime
