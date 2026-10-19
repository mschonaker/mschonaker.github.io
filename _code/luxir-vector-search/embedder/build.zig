const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    // Zig 0.17 replaced @cImport with an explicit translate-c build step that
    // produces an ordinary module.
    const tc = b.addTranslateC(.{
        .root_source_file = b.path("onnx_embed.h"),
        .target = target,
        .optimize = optimize,
    });

    const mod = b.createModule(.{
        .root_source_file = b.path("main.zig"),
        .target = target,
        .optimize = optimize,
    });
    mod.addImport("onnx", tc.createModule());
    mod.addIncludePath(b.path("."));

    // ONNX Runtime itself is a C library. `brew install onnxruntime` ships the
    // libonnxruntime.pc file that resolves both the headers and the dylib.
    mod.linkSystemLibrary("libonnxruntime", .{ .use_pkg_config = .yes });
    mod.addCSourceFile(.{
        .file = b.path("onnx_embed.c"),
        .flags = &.{ "-I/opt/homebrew/include/onnxruntime" },
    });
    mod.link_libc = true;

    b.installArtifact(b.addExecutable(.{ .name = "embed", .root_module = mod }));

    // The tokenizer tests read tokenizer.json from the working directory.
    const tests = b.addTest(.{ .root_module = mod });
    const run = b.addRunArtifact(tests);
    run.setCwd(b.path("."));
    b.step("test", "Run the tokenizer tests").dependOn(&run.step);
}