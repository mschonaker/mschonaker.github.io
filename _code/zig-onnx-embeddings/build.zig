const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.graph.host;

    const exe = b.addExecutable(.{
        .name = "zig-embeddings",
        .root_module = b.createModule(.{
            .target = target,
            .root_source_file = b.path("main.zig"),
        }),
    });

    exe.linkLibC();
    exe.addLibraryPath(.{ .cwd_relative = "/opt/homebrew/lib" });
    exe.linkSystemLibrary("onnxruntime");
    exe.addIncludePath(.{ .cwd_relative = "." });
    exe.addObjectFile(.{ .cwd_relative = "onnx_embed.o" });

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);

    const run_step = b.step("run", "Run the app");
    run_step.dependOn(&run_cmd.step);
}
