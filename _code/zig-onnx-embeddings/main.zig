const std = @import("std");

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();
    const allocator = gpa.allocator();

    std.debug.print("Downloading model and tokenizer...\n", .{});

    try downloadFile(
        "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/onnx/model_q4.onnx",
        "model.onnx",
    );

    try downloadFile(
        "https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main/tokenizer.json",
        "tokenizer.json",
    );

    std.debug.print("Loading tokenizer...\n", .{});
    var tokenizer = try loadTokenizer(allocator, "tokenizer.json");
    defer freeTokenizer(&tokenizer);

    std.debug.print("Tokenizing 'hello world'...\n", .{});
    const tokens = try tokenize(allocator, tokenizer, "hello world");
    defer allocator.free(tokens);

    std.debug.print("Token IDs: ", .{});
    for (tokens) |id| {
        std.debug.print("{d} ", .{id});
    }
    std.debug.print("\n", .{});

    std.debug.print("\nNote: ONNX Runtime integration requires installing the library:\n", .{});
    std.debug.print("  macOS: brew install onnxruntime\n", .{});
    std.debug.print("  Linux: download from https://onnxruntime.ai/\n", .{});
}

const Tokenizer = struct {
    vocab: std.StringHashMap(u32),
    unk_token_id: u32,
    cls_token_id: u32,
    sep_token_id: u32,
};

fn loadTokenizer(allocator: std.mem.Allocator, path: []const u8) !Tokenizer {
    const content = try std.fs.cwd().readFileAlloc(allocator, path, 50 * 1024 * 1024);
    defer allocator.free(content);

    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, content, .{});
    defer parsed.deinit();

    const root = parsed.value;
    const vocab_obj = root.object.get("model").?.object.get("vocab").?;

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

fn freeTokenizer(tokenizer: *Tokenizer) void {
    tokenizer.vocab.deinit();
}

fn tokenize(allocator: std.mem.Allocator, tokenizer: Tokenizer, text: []const u8) ![]u32 {
    var normalized: std.ArrayList(u8) = .{ .items = &.{}, .capacity = 0 };
    defer normalized.deinit(allocator);
    try normalized.ensureTotalCapacityPrecise(allocator, text.len * 4);

    for (text) |c| {
        if (c >= 'A' and c <= 'Z') {
            normalized.appendAssumeCapacity(c + 32);
        } else {
            normalized.appendAssumeCapacity(c);
        }
    }

    var tokens: std.ArrayList(u32) = .{ .items = &.{}, .capacity = 0 };
    errdefer tokens.deinit(allocator);
    try tokens.ensureTotalCapacityPrecise(allocator, normalized.items.len * 2 + 3);

    tokens.appendAssumeCapacity(tokenizer.cls_token_id);

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

fn downloadFile(url: []const u8, dest: []const u8) !void {
    if (std.fs.cwd().openFile(dest, .{})) |file| {
        defer file.close();
        std.debug.print("  {s} already exists, skipping\n", .{dest});
        return;
    } else |_| {}

    std.debug.print("  Downloading {s}...\n", .{dest});

    var child = std.process.Child.init(&.{ "curl", "-L", "-o", dest, url }, std.heap.c_allocator);
    const term = try child.spawnAndWait();

    if (term != .Exited or term.Exited != 0) {
        return error.DownloadFailed;
    }
}
