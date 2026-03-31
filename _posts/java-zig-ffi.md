# Calling Zig from Java using JNR-FFI

![Java and Zig FFI header](/images/java-zig-ffi.png)

This article shows how to call a Zig compiled library from Java without writing any JNI code. We'll use [JNR-FFI](https://github.com/jnr/jnr-ffi), a pure Java library that can load native libraries dynamically.

## Why Zig + Java?

Zig is a modern systems programming language that produces highly optimized native code. It's an excellent choice for performance-critical parts of Java applications. Unlike other approaches like JNI or JNA, JNR-FFI lets you call native functions from Java without generating any C boilerplate.

## The Zig Side

First, let's create a simple Zig library with a function that greets the user. Save this as `hello.zig`:

```zig
const std = @import("std");

export fn greet(name: [*:0]const u8) void {
    std.debug.print("Hello, {s}!\n", .{name});
}
```

The `export` keyword makes this function visible to the dynamic linker. The `[*:0]const u8` type is a null-terminated C string, which is how strings are typically passed across FFI boundaries.

Build it as a macOS dylib:

```bash
zig build-lib -dynamic hello.zig -O ReleaseFast -ofmt=macho
```

This produces `libhello.dylib`. The `-dynamic` flag creates a shared library, `-O ReleaseFast` enables optimizations, and `-ofmt=macho` produces macOS Mach-O binaries.

## The Java Side

We'll use Maven with JNR-FFI. Create a `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>hello-zig-ffi</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.github.jnr</groupId>
            <artifactId>jnr-ffi</artifactId>
            <version>2.2.18</version>
        </dependency>
        <dependency>
            <groupId>com.github.jnr</groupId>
            <artifactId>jffi</artifactId>
            <version>1.3.14</version>
            <classifier>complete</classifier>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.1.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The JNR-FFI library handles the low-level FFI details. The `complete` classifier for jffi includes all native libraries bundled together, which avoids architecture issues on Apple Silicon.

Create the Java source in `src/main/java/Hello.java`:

```java
import jnr.ffi.LibraryLoader;
import jnr.ffi.annotations.Pinned;
import java.util.Scanner;

public class Hello {
    public interface LibHello {
        void greet(@Pinned String name);
    }

    public static void main(String[] args) {
        LibHello lib = LibraryLoader.create(LibHello.class)
            .load("hello");
        
        System.out.print("Enter your name: ");
        Scanner scanner = new Scanner(System.in);
        String name = scanner.nextLine();
        
        lib.greet(name);
    }
}
```

The key parts:

- **`LibHello` interface**: Defines the native function signature. JNR-FFI maps Java methods to native functions by name.
- **`@Pinned String`**: Tells JNR-FFI to keep the Java string in memory (pinned) for the duration of the native call. This is important because Java's garbage collector can move objects around, but native code expects fixed memory addresses.
- **`LibraryLoader.create(LibHello.class).load("hello")`**: Loads the `libhello.dylib` (or `libhello.so` on Linux) dynamically.

## Running It

Build and run:

```bash
mvn compile exec:java -Dexec.mainClass=Hello -Djava.library.path=.
```

The `-Djava.library.path=.` tells Java to look for native libraries in the current directory.

Example output:

```
Enter your name: World
Hello, World!
```

## How It Works

When you call `lib.greet(name)`:

1. JNR-FFI creates a pinned byte buffer from the Java String
2. It passes the buffer's memory address to the native `greet` function
3. Zig's `[*:0]const u8` receives a pointer to the string data
4. The `std.debug.print` outputs the greeting
5. After the call returns, JNR-FFI unpins the buffer so it can be garbage collected

This approach works with any native library - not just Zig. You can call C, C++, Rust, or other languages that produce compatible shared libraries.

## Caveats

- **String encoding**: Java strings are UTF-16 internally. JNR-FFI converts to UTF-8 by default, which works for ASCII but may cause issues with Unicode.
- **Memory management**: The `@Pinned` annotation keeps Java strings alive during the call, but for complex scenarios you'll need to manage native memory explicitly.
- **Architecture**: On Apple Silicon (M1/M2/M3), ensure your JNR-FFI native JAR includes ARM64 binaries. The `complete` classifier bundles all architectures.

## References

- [JNR-FFI GitHub](https://github.com/jnr/jnr-ffi)
- [Zig Documentation - C Export](https://ziglang.org/doc/master/#toc-Exporting-to-C)
- [JNR-FFI Maven Central](https://central.sonatype.com/artifact/com.github.jnr/jnr-ffi)