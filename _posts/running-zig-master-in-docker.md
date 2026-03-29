# Running Zig Master in Docker

Want to try the latest Zig development version without installing anything? Docker makes it easy.

## The Image

There's no official Zig image with the full toolchain - `ziglang/static-base` is just a base for building static binaries. The best option is `ziglings/ziglang`, which provides daily builds of Zig's current development version. It's minimal and updated regularly.

## Quick Start

Run a simple hello world:

```bash
docker run --rm ziglings/ziglang sh -c 'echo "Hello from Zig $(zig version)!"'
```

Output:
```
Hello from Zig 0.16.0-dev.3013+abd131e33!
```

## Interactive REPL

Want to explore Zig interactively:

```bash
docker run --rm -it ziglings/ziglang
```

Once inside, try the REPL:

```
>>> @import("std").debug.print("Hello from Zig!\n");
Hello from Zig!
```

## Compiling Code

Create a file `hello.zig`:

```zig
const std = @import("std");

pub fn main() void {
    std.debug.print("Hello from Zig {s}!\n", .{@import("builtin").zig_version_string});
}
```

Run it:

```bash
docker run --rm -v $(pwd):/app -w /app ziglings/ziglang zig run hello.zig
```

## Why Use Docker?

- No need to build Zig from source
- Try different versions easily
- Isolated environment
- Works on any platform with Docker
