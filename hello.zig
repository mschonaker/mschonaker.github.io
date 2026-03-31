const std = @import("std");

export fn greet(name: [*:0]const u8) void {
    std.debug.print("Hello, {s}!\n", .{name});
}
