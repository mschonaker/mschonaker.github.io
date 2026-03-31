# Getting Started with SIMD in Zig

SIMD (Single Instruction, Multiple Data) lets you perform the same operation on multiple data points simultaneously. Instead of adding two numbers one at a time, you can add eight at once. This is perfect for image processing, numerical computing, and string operations.

Zig has excellent built-in support for SIMD through vector types. Let me show you how to use them.

## Your First SIMD Operation

Here's a simple example that adds two vectors element-wise:

```zig
const std = @import("std");

pub fn main() void {
    const a = @Vector(4, f32){ 1.0, 2.0, 3.0, 4.0 };
    const b = @Vector(4, f32){ 5.0, 6.0, 7.0, 8.0 };
    const c = a + b;

    std.debug.print("Result: {d}\n", .{c});
}
```

Run it:

```bash
zig run add.zig
```

Output:
```
Result: { 6, 8, 10, 12 }
```

The `@Vector(N, T)` type represents a vector of N elements of type T. The `+` operator works element-wise automatically.

## Why This Matters

Let's compare scalar vs SIMD performance with a real workload: summing a large array of f64 values.

```zig
const std = @import("std");

fn scalarSum(data: []const f64) f64 {
    var sum: f64 = 0;
    for (data) |x| {
        sum += x;
    }
    return sum;
}

fn simdSum(data: []const f64) f64 {
    var acc: @Vector(4, f64) = @splat(0);
    var i: usize = 0;
    
    while (i + 4 <= data.len) : (i += 4) {
        const src: *const [4]f64 = @ptrCast(&data[i]);
        const vector = src.*;
        acc = acc + vector;
    }
    
    const partial_sum = @reduce(.Add, acc);
    
    var tail_sum: f64 = 0;
    while (i < data.len) : (i += 1) {
        tail_sum += data[i];
    }
    return partial_sum + tail_sum;
}

pub fn main() void {
    const size = 1_000_000;
    var data: [size]f64 = undefined;
    for (&data, 0..) |*x, i| {
        x.* = @floatFromInt(i);
    }

    const start = std.time.nanoTimestamp();
    const r1 = scalarSum(&data);
    const scalar_time = std.time.nanoTimestamp() - start;

    const start2 = std.time.nanoTimestamp();
    const r2 = simdSum(&data);
    const simd_time = std.time.nanoTimestamp() - start2;

    std.debug.print("Scalar: {d:.2}ms, SIMD: {d:.2}ms, Speedup: {d:.2}x\n", .{
        @as(f64, @floatFromInt(scalar_time)) / 1e6,
        @as(f64, @floatFromInt(simd_time)) / 1e6,
        @as(f64, @floatFromInt(scalar_time)) / @as(f64, @floatFromInt(simd_time)),
    });
    std.debug.print("Results match: {}\n", .{r1 == r2});
}
```

Typical output:
```
Scalar: 3.00ms, SIMD: 1.39ms, Speedup: 2.15x
Results match: true
```

The speedup comes from processing 4 f64 values at once. On modern CPUs with AVX, you can process 8 floats (256-bit) or even 16 (512-bit with AVX-512).

## Practical Example: Image Brightness

Here's a more practical example—adjusting image brightness. This simulates processing a grayscale image where each pixel is a u8 value.

```zig
const std = @import("std");

fn clamp(val: i16, min_val: i16, max_val: i16) i16 {
    if (val < min_val) return min_val;
    if (val > max_val) return max_val;
    return val;
}

fn adjustBrightnessScalar(pixels: []u8, amount: i16) void {
    for (pixels) |*pixel| {
        const new_val = @as(i16, @intCast(pixel.*)) + amount;
        pixel.* = @intCast(clamp(new_val, 0, 255));
    }
}

fn adjustBrightnessSimd(pixels: []u8, amount: i16) void {
    const vector_size = 4;
    var i: usize = 0;
    
    const amount_vec: @Vector(4, i32) = @splat(@as(i32, amount));
    const zero: @Vector(4, i32) = @splat(0);
    const max_val: @Vector(4, i32) = @splat(255);

    while (i + vector_size <= pixels.len) : (i += vector_size) {
        const src: *const [4]u8 = @ptrCast(&pixels[i]);
        const vector: @Vector(4, u8) = src.*;
        
        const extended: @Vector(4, i32) = @intCast(vector);
        
        var adjusted = extended + amount_vec;
        adjusted = @min(@max(adjusted, zero), max_val);
        
        const result: @Vector(4, u8) = @intCast(adjusted);
        
        const dst: *[4]u8 = @ptrCast(&pixels[i]);
        dst.* = result;
    }

    while (i < pixels.len) : (i += 1) {
        const new_val = @as(i16, @intCast(pixels[i])) + amount;
        pixels[i] = @intCast(clamp(new_val, 0, 255));
    }
}

pub fn main() void {
    const size = 1_000_000;
    var pixels1: [size]u8 = undefined;
    var pixels2: [size]u8 = undefined;
    for (&pixels1, 0..) |*x, i| {
        x.* = @intCast(i % 256);
    }
    @memcpy(&pixels2, &pixels1);

    const amount: i16 = 30;

    const start = std.time.nanoTimestamp();
    adjustBrightnessScalar(&pixels1, amount);
    const scalar_time = std.time.nanoTimestamp() - start;

    const start2 = std.time.nanoTimestamp();
    adjustBrightnessSimd(&pixels2, amount);
    const simd_time = std.time.nanoTimestamp() - start2;

    std.debug.print("Scalar: {d:.2}ms, SIMD: {d:.2}ms, Speedup: {d:.2}x\n", .{
        @as(f64, @floatFromInt(scalar_time)) / 1e6,
        @as(f64, @floatFromInt(simd_time)) / 1e6,
        @as(f64, @floatFromInt(scalar_time)) / @as(f64, @floatFromInt(simd_time)),
    });
    
    var match = true;
    for (&pixels1, &pixels2) |a, b| {
        if (a != b) {
            match = false;
            break;
        }
    }
    std.debug.print("Results match: {}\n", .{match});
}
```

Output:
```
Scalar: 6.34ms, SIMD: 2.57ms, Speedup: 2.47x
Results match: true
```

The SIMD version processes 4 pixels at once. The `@splat` operator broadcasts a single value across all vector elements—this is useful for constants like our brightness adjustment amount.

## Useful Vector Operations

Zig's vectors support many operations out of the box:

| Operation | Description |
|-----------|-------------|
| `a + b`, `a - b`, `a * b`, `a / b` | Element-wise arithmetic |
| `a == b`, `a < b`, `a >= b` | Element-wise comparison (returns vector of bool) |
| `a & b`, `a \| b`, `a ^ b`, `~a` | Bitwise operations |
| `@splat(x)` | Create vector with all elements = x |
| `@reduce(.Add, v)` | Sum all elements of v into scalar |
| `@intCast(v)` | Convert between vector types |
| `@min(v1, v2)`, `@max(v1, v2)` | Element-wise min/max |
| `@select(T, cond, a, b)` | Like `cond ? a : b` for vectors |

## Platform-Specific Vectors

Zig abstracts over SIMD width. You can query what's available:

```zig
const std = @import("std");

pub fn main() void {
    const vec_size = @sizeOf(@Vector(16, u8)) * 8;
    std.debug.print("Native SIMD width: {} bytes\n", .{vec_size});
}
```

This reports 128 bytes (1024 bits) on most modern CPUs—the compiler will use the appropriate SIMD instructions for your target.

## When to Use SIMD

SIMD shines for:
- **Image/video processing**: brightness, contrast, filters
- **Numerical computing**: matrix operations, FFT
- **String operations**: searching, matching
- **Cryptography**: hashing, encryption

The key pattern is: *same operation on lots of independent data*.

## Further Reading

- [Zig Guide: Vectors](https://zig.guide/language-basics/vectors) - Official documentation
- [Wikipedia: SIMD](https://en.wikipedia.org/wiki/Single_instruction,_multiple_data) - Theory background
- [Intrinsics Guide](https://www.intel.com/content/www/us/en/docs/intrinsics-guide/) - CPU-specific SIMD instructions