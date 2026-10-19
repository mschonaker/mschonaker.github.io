const std = @import("std");
const onnx = @import("onnx");
const tok = @import("tokenizer.zig");

/// Longest forward window the greedy WordPiece scan will consider. BERT's own
/// max_chars_per_word is 100; MiniLM's longest vocabulary entry is far shorter,
/// so a bounded window finds the same tokens while turning a quadratic scan
/// over long descriptions into a linear one.
const max_word_chars = 24;

pub fn main(init: std.process.Init) !void {
    const io = init.io;
    const allocator = init.arena.allocator();
    var args = init.minimal.args.iterate();

    const Opts = struct {
        model: []const u8 = "model.onnx",
        tokenizer: []const u8 = "tokenizer.json",
        fields: []const u8 = "title_t,description_t",
        out: []const u8 = "embedding_v",
        max_tokens: usize = 256,
        threads: i32 = 1,
        server: bool = false,
        dump_tokens: bool = false,
    };
    var o: Opts = .{};

    _ = args.skip();
    while (args.next()) |flag0| {
        const flag: []const u8 = flag0;
        if (std.mem.eql(u8, flag, "--help")) {
            std.debug.print(
                \\usage: embed [--fields a,b] [--out name] [--max-tokens n]
                \\             [--threads n] [--model path] [--tokenizer path]
                \\             [--server] [--dump-tokens]
                \\
                \\Reads NDJSON documents on stdin, one per line, and writes each
                \\back with the embedding field appended, or with token ids under
                \\--dump-tokens. Lines are answered as
                \\they arrive, so stdin may stay open: --server turns off the
                \\progress log for a caller that keeps one process alive.
                \\
            , .{});
            return;
        }
        if (std.mem.eql(u8, flag, "--server")) {
            o.server = true;
            continue;
        }
        if (std.mem.eql(u8, flag, "--dump-tokens")) {
            o.dump_tokens = true;
            continue;
        }
        const value = args.next() orelse {
            std.log.err("{s} needs a value", .{flag});
            return error.MissingValue;
        };
        if (std.mem.eql(u8, flag, "--model")) {
            o.model = value;
        } else if (std.mem.eql(u8, flag, "--tokenizer")) {
            o.tokenizer = value;
        } else if (std.mem.eql(u8, flag, "--fields")) {
            o.fields = value;
        } else if (std.mem.eql(u8, flag, "--out")) {
            o.out = value;
        } else if (std.mem.eql(u8, flag, "--max-tokens")) {
            o.max_tokens = try std.fmt.parseInt(usize, value, 10);
        } else if (std.mem.eql(u8, flag, "--threads")) {
            o.threads = try std.fmt.parseInt(i32, value, 10);
        } else {
            std.log.err("unknown flag: {s}", .{flag});
            return error.UnknownFlag;
        }
    }

    var field_list: std.ArrayList([]const u8) = .empty;
    defer field_list.deinit(allocator);
    var split = std.mem.splitScalar(u8, o.fields, ',');
    while (split.next()) |f| {
        if (f.len > 0) try field_list.append(allocator, f);
    }

    const model_start = std.Io.Clock.now(.real, io);
    var emb: ?*onnx.Embedder = null;
    var dim: usize = 0;
    var model_secs: f64 = 0;
    if (!o.dump_tokens) {
        const model_z = try allocator.dupeSentinel(u8, o.model, 0);
        emb = onnx.embedder_new(model_z.ptr, o.threads);
        if (emb == null) return error.EmbedderFailed;
        dim = @intCast(onnx.embedder_dim(emb.?));
        model_secs = elapsed(io, model_start);
    }

    const tok_start = std.Io.Clock.now(.real, io);
    var tokenizer = try tok.load(io, allocator, o.tokenizer);
    defer tok.free(allocator, &tokenizer);
    const tok_secs = elapsed(io, tok_start);

    var in_buf: [1 << 20]u8 = undefined;
    var stdin = std.Io.File.stdin().readerStreaming(io, &in_buf);
    const in = &stdin.interface;

    var out_buf: [1 << 16]u8 = undefined;
    var stdout = std.Io.File.stdout().writerStreaming(io, &out_buf);
    const out = &stdout.interface;
    defer out.flush() catch {};

    const start = std.Io.Clock.now(.real, io);

    var joined: std.ArrayList(u8) = .empty;
    defer joined.deinit(allocator);
    var ids: std.ArrayList(i64) = .empty;
    defer ids.deinit(allocator);
    var zeros: std.ArrayList(i64) = .empty;
    defer zeros.deinit(allocator);
    var pad: std.ArrayList(i64) = .empty;
    defer pad.deinit(allocator);
    var scratch: std.ArrayList(u8) = .empty;
    defer scratch.deinit(allocator);

    var count: u64 = 0;
    var token_total: u64 = 0;

    // One line in, one line out, answered before the next line is read. A caller
    // that writes one line and reads one line gets a service; a caller that
    // pipes a file gets a batch job. Same loop either way.
    while (try in.takeDelimiter('\n')) |line| {
        if (line.len == 0) continue;

        joined.clearRetainingCapacity();
        for (field_list.items) |f| {
            const piece = try fieldText(allocator, line, f, &joined);
            if (piece.len == 0) continue;
            if (joined.items.len > 0) try joined.appendSlice(allocator, ". ");
            try joined.appendSlice(allocator, piece);
        }

        try tok.tokenize(allocator, &tokenizer, joined.items, o.max_tokens, &ids, &scratch);

        if (o.dump_tokens) {
            // Tokenizer-only mode, for checking against a reference
            // implementation without running inference.
            for (ids.items, 0..) |id, n| {
                if (n > 0) try out.writeByte(' ');
                try out.print("{d}", .{id});
            }
            try out.writeByte('\n');
            try out.flush();
            token_total += ids.items.len;
            count += 1;
            continue;
        }

        if (ids.items.len <= 2) {
            // Nothing to embed. Echo the line so the caller still gets one
            // response per request and the streams stay aligned.
            try out.writeAll(line);
            try out.writeByte('\n');
            try out.flush();
            continue;
        }

        // Every position is live in a single unpadded sequence, and the model is a
// single-segment BERT, so token_type_ids are all zero.
        pad.clearRetainingCapacity();
        try pad.appendNTimes(allocator, 1, ids.items.len);
        zeros.clearRetainingCapacity();
        try zeros.appendNTimes(allocator, 0, ids.items.len);

        const vec = onnx.embedder_embed(
            emb.?,
            @as([*]const i64, @ptrCast(ids.items.ptr)),
            @as([*]const i64, @ptrCast(pad.items.ptr)),
            @as([*]const i64, @ptrCast(zeros.items.ptr)),
            @intCast(ids.items.len),
        );
        if (vec == null) return error.InferenceFailed;
        const embedding = vec[0..dim];
        defer allocator.free(embedding);

        // Splice the vector onto the original line instead of re-encoding it.
        try out.writeAll(line[0 .. line.len - 1]);
        try out.print(",\"{s}\":[", .{o.out});
        for (embedding, 0..) |v, d| {
            if (d > 0) try out.writeByte(',');
            try out.print("{d:.5}", .{v});
        }
        try out.writeAll("]}\n");
        try out.flush();

        token_total += ids.items.len;
        count += 1;
        if (!o.server and count % 2000 == 0) {
            const secs = elapsed(io, start);
            std.log.info("{d} docs, {d:.0} docs/s", .{ count, @as(f64, @floatFromInt(count)) / secs });
        }
    }

    const secs = elapsed(io, start);
    if (o.server) {
        std.log.info("embedded {d} docs over {d:.2} s", .{ count, secs });
        return;
    }
    std.log.info("{d} docs, {d} tokens, {d:.2} s, {d:.0} docs/s, {d:.2} ms/doc", .{
        count,
        token_total,
        secs,
        @as(f64, @floatFromInt(count)) / secs,
        secs * 1000.0 / @as(f64, @floatFromInt(count)),
    });
    std.log.info("startup: model {d:.0} ms, tokenizer {d:.0} ms, {d} dims", .{
        model_secs * 1000.0,
        tok_secs * 1000.0,
        dim,
    });
}


/// Reads one string field out of an NDJSON line. A field holding an array of
/// strings is joined with spaces, which covers the category documents.
fn fieldText(
    allocator: std.mem.Allocator,
    line: []const u8,
    field: []const u8,
    out: *std.ArrayList(u8),
) ![]const u8 {
    const parsed = std.json.parseFromSlice(std.json.Value, allocator, line, .{}) catch return "";
    defer parsed.deinit();
    const obj = switch (parsed.value) {
        .object => |o| o,
        else => return "",
    };
    switch (obj.get(field) orelse return "") {
        .string => |s| return s,
        .array => |a| {
            out.clearRetainingCapacity();
            for (a.items) |item| {
                if (item != .string) continue;
                if (out.items.len > 0) try out.append(allocator, ' ');
                try out.appendSlice(allocator, item.string);
            }
            return out.items;
        },
        else => return "",
    }
}

fn elapsed(io: std.Io, start: std.Io.Timestamp) f64 {
    return @as(f64, @floatFromInt(start.durationTo(std.Io.Clock.now(.real, io)).toNanoseconds())) / 1e9;
}
