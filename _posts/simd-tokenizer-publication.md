---
id: simd-tokenizer-poc
title: SIMD Tokenizer - A Whitespace Tokenizer in Zig with Bounded Memory
summary: A proof-of-concept streaming tokenizer that processes arbitrarily large inputs using just 9KB of memory, achieving 5x speedup over bash baseline.
date: 2026-04-12
---

# SIMD Tokenizer - A Whitespace Tokenizer in Zig with Bounded Memory

I've published a small proof-of-concept project: a streaming whitespace tokenizer built in Zig that processes arbitrarily large inputs while using bounded memory. The key insight here is that tokenization doesn't require loading the entire input into memory - you can process it in fixed-size chunks.

## The Problem

Traditional tokenizers often assume you can read entire files into memory. This works fine for small files but breaks down when processing multi-gigabyte datasets. I wanted to build something that could handle any input size without modification.

## The Solution

The tokenizer uses two fixed-size buffers:

- **Input buffer**: 4KB (CHUNK_SIZE)
- **Output buffer**: 5KB (OUTPUT_BUFFER_SIZE)

Total memory usage: ~9KB regardless of input file size.

The implementation uses Zig's SIMD vector types (`@Vector(64, u8)`) to process chunks of 64 bytes at once. The state machine tracks whether we're inside a token or a delimiter, flushing tokens immediately to the output buffer as they're complete.

## Performance Results

Benchmarks comparing against a bash baseline (`tr -s ' \t\n\r' '\n' | grep -v '^$'`):

| Input Size | Bash    | Zig     | Speedup |
|-----------|---------|---------|---------|
| 5MB       | ~0.19s  | ~0.03s  | ~5x     |
| 10MB      | ~0.38s  | ~0.07s  | ~5x     |
| 50MB      | ~1.85s  | ~0.34s  | ~5.4x   |

Throughput reaches ~32M tokens/second on large inputs.

## Implementation Highlights

```zig
const CHUNK_SIZE = 4096;
const OUTPUT_BUFFER_SIZE = 5120;

pub fn processChunk(buf: []const u8, state: *TokenizerState) void {
    const input_vec = @as(@Vector(64, u8), buf[0..64].*);
    const is_whitespace = input_vec == ' ' | input_vec == '\t' | 
                         input_vec == '\n' | input_vec == '\r';
    // ... SIMD processing
}
```

The key decisions:

1. **Streaming architecture**: Read chunk, process, flush, repeat
2. **SIMD for character classification**: 64 bytes processed per instruction
3. **Immediate token flush**: No waiting for full token before outputting
4. **Single delim collapsed**: Multiple whitespace characters treated as one delimiter

## Code

The project is available at [github.com/mschonaker/simd-tokenizer](https://github.com/mschonaker/simd-tokenizer). It includes the tokenizer implementation, benchmarks, and a performance report.

Build and run:

```bash
zig build
echo "hello world foo bar" | ./zig-out/bin/simd-tokenizer
```

## Trade-offs

This approach works well for whitespace tokenization but has limitations:

- **Delimiter boundary alignment**: Tokens spanning chunk boundaries require carry-over state
- **Fixed delimiters only**: Adding new delimiters requires code changes
- **No unicode normalization**: ASCII-focused design

For general-purpose tokenization, you'd want more sophisticated handling of UTF-8, grapheme clusters, and locale-specific rules. But for the common case of whitespace splitting, this achieves the goal: bounded memory with excellent performance.