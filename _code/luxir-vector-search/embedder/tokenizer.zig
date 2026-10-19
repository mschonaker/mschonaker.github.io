const std = @import("std");

/// Longest forward window the greedy WordPiece scan will consider for a
/// continuation piece. BERT's own max_chars_per_word is 100; MiniLM's longest
/// vocabulary entry is far shorter, so a bounded window finds the same pieces
/// while turning an unbounded scan over long words into a linear one.
const max_word_chars = 24;

pub const Tokenizer = struct {
    vocab: std.StringHashMapUnmanaged(u32) = .empty,
    unk_token_id: u32 = 100,
    cls_token_id: u32 = 101,
    sep_token_id: u32 = 102,
};

pub fn load(io: std.Io, allocator: std.mem.Allocator, path: []const u8) !Tokenizer {
    const content = try std.Io.Dir.cwd().readFileAlloc(io, path, allocator, .limited(50 << 20));
    defer allocator.free(content);

    const parsed = try std.json.parseFromSlice(std.json.Value, allocator, content, .{});
    defer parsed.deinit();

    const vocab_obj = switch (parsed.value) {
        .object => |o| o.get("model").?.object.get("vocab").?.object,
        else => return error.BadTokenizer,
    };

    var t: Tokenizer = .{};
    try t.vocab.ensureTotalCapacity(allocator, @intCast(vocab_obj.count()));
    var it = vocab_obj.iterator();
    while (it.next()) |entry| {
        const id: u32 = switch (entry.value_ptr.*) {
            .integer => |v| @intCast(v),
            .float => |v| @intFromFloat(v),
            else => continue,
        };
        try t.vocab.put(allocator, try allocator.dupe(u8, entry.key_ptr.*), id);
    }
    t.unk_token_id = t.vocab.get("[UNK]") orelse t.unk_token_id;
    t.cls_token_id = t.vocab.get("[CLS]") orelse t.cls_token_id;
    t.sep_token_id = t.vocab.get("[SEP]") orelse t.sep_token_id;
    return t;
}

pub fn free(allocator: std.mem.Allocator, t: *Tokenizer) void {
    var it = t.vocab.iterator();
    while (it.next()) |entry| allocator.free(entry.key_ptr.*);
    t.vocab.deinit(allocator);
}

/// ASCII punctuation, exactly the ranges BERT's BasicTokenizer treats as
/// punctuation. Everything above ASCII stays inside a word, which is what keeps
/// "Bose®" one word and "café" one word.
fn isSeparator(c: u8) bool {
    return switch (c) {
        ' ', '\t', '\n', '\r', '\x0b', '\x0c' => true,
        '!', '"', '#', '$', '%', '&', '\'', '(', ')', '*', '+', ',', '-', '.', '/' => true,
        ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`' => true,
        '{', '|', '}', '~' => true,
        else => c < 0x20 or c == 0x7f,
    };
}

/// Accent folding over Latin-1 Supplement and Latin Extended-A, the two blocks
/// a product catalog actually hits. Ranges keep the table short.
const fold = [_]struct { lo: u21, hi: u21, to: u8 }{
    .{ .lo = 0x00C0, .hi = 0x00C6, .to = 'a' },
    .{ .lo = 0x00E0, .hi = 0x00E6, .to = 'a' },
    .{ .lo = 0x00C7, .hi = 0x00C7, .to = 'c' },
    .{ .lo = 0x00E7, .hi = 0x00E7, .to = 'c' },
    .{ .lo = 0x00C8, .hi = 0x00CB, .to = 'e' },
    .{ .lo = 0x00E8, .hi = 0x00EB, .to = 'e' },
    .{ .lo = 0x00D0, .hi = 0x00D0, .to = 'd' },
    .{ .lo = 0x00F0, .hi = 0x00F0, .to = 'd' },
    .{ .lo = 0x00D1, .hi = 0x00D1, .to = 'n' },
    .{ .lo = 0x00F1, .hi = 0x00F1, .to = 'n' },
    .{ .lo = 0x00D2, .hi = 0x00D6, .to = 'o' },
    .{ .lo = 0x00F2, .hi = 0x00F6, .to = 'o' },
    .{ .lo = 0x00D8, .hi = 0x00D8, .to = 'o' },
    .{ .lo = 0x00F8, .hi = 0x00F8, .to = 'o' },
    .{ .lo = 0x00D9, .hi = 0x00DC, .to = 'u' },
    .{ .lo = 0x00F9, .hi = 0x00FC, .to = 'u' },
    .{ .lo = 0x00DD, .hi = 0x00DD, .to = 'y' },
    .{ .lo = 0x00FD, .hi = 0x00FF, .to = 'y' },
    .{ .lo = 0x0104, .hi = 0x0105, .to = 'a' },
    .{ .lo = 0x0106, .hi = 0x0107, .to = 'c' },
    .{ .lo = 0x010C, .hi = 0x010D, .to = 'c' },
    .{ .lo = 0x010E, .hi = 0x010F, .to = 'd' },
    .{ .lo = 0x0112, .hi = 0x0113, .to = 'e' },
    .{ .lo = 0x0118, .hi = 0x011B, .to = 'e' },
    .{ .lo = 0x011E, .hi = 0x011F, .to = 'g' },
    .{ .lo = 0x0126, .hi = 0x0127, .to = 'h' },
    .{ .lo = 0x0130, .hi = 0x0131, .to = 'i' },
    .{ .lo = 0x0134, .hi = 0x0135, .to = 'j' },
    .{ .lo = 0x0138, .hi = 0x0138, .to = 'k' },
    .{ .lo = 0x0139, .hi = 0x0142, .to = 'l' },
    .{ .lo = 0x0143, .hi = 0x0148, .to = 'n' },
    .{ .lo = 0x014C, .hi = 0x0151, .to = 'o' },
    .{ .lo = 0x0154, .hi = 0x0155, .to = 'r' },
    .{ .lo = 0x0156, .hi = 0x0161, .to = 's' },
    .{ .lo = 0x0162, .hi = 0x0167, .to = 't' },
    .{ .lo = 0x0168, .hi = 0x0173, .to = 'u' },
    .{ .lo = 0x0174, .hi = 0x0175, .to = 'w' },
    .{ .lo = 0x0176, .hi = 0x0178, .to = 'y' },
    .{ .lo = 0x0179, .hi = 0x017E, .to = 'z' },
};

fn foldChar(cp: u21) ?u8 {
    for (fold) |f| {
        if (cp >= f.lo and cp <= f.hi) return f.to;
    }
    return null;
}

/// Strip accents and fold to lower case, which is what the model's normalizer
/// does. `café` has to reach the same piece as `cafe`.
fn normalize(allocator: std.mem.Allocator, text: []const u8, out: *std.ArrayList(u8)) !void {
    try out.ensureTotalCapacity(allocator, text.len);
    var i: usize = 0;
    while (i < text.len) {
        const c = text[i];
        if (c < 0x80) {
            try out.append(allocator, std.ascii.toLower(c));
            i += 1;
            continue;
        }
        const len = std.unicode.utf8ByteSequenceLength(c) catch {
            try out.append(allocator, c);
            i += 1;
            continue;
        };
        if (i + len > text.len) {
            try out.append(allocator, c);
            i += 1;
            continue;
        }
        const seq = text[i .. i + len];
        const cp = std.unicode.utf8Decode(seq) catch {
            try out.appendSlice(allocator, seq);
            i += len;
            continue;
        };
        if (foldChar(cp)) |ascii| {
            try out.append(allocator, ascii);
        } else {
            try out.appendSlice(allocator, seq);
        }
        i += len;
    }
}

pub fn tokenize(
    allocator: std.mem.Allocator,
    t: *Tokenizer,
    text: []const u8,
    max_tokens: usize,
    out: *std.ArrayList(i64),
    scratch: *std.ArrayList(u8),
) !void {
    out.clearRetainingCapacity();
    try out.append(allocator, t.cls_token_id);

    scratch.clearRetainingCapacity();
    try normalize(allocator, text, scratch);

    var i: usize = 0;
    while (i < scratch.items.len and out.items.len < max_tokens) {
        if (isSeparator(scratch.items[i])) {
            // BERT's pre-tokenizer makes every punctuation character its own
            // word, and this vocabulary holds '-' '"' '\'' '(' ')' and
            // friends, so keep the ones it knows and drop the rest.
            if (out.items.len < max_tokens) {
                if (t.vocab.get(scratch.items[i .. i + 1])) |id| {
                    try out.append(allocator, id);
                }
            }
            i += 1;
            continue;
        }
        var word_end = i;
        while (word_end < scratch.items.len and !isSeparator(scratch.items[word_end])) word_end += 1;

        try wordPieces(allocator, t, scratch.items[i..word_end], max_tokens, out);
        i = word_end;
    }
    try out.append(allocator, t.sep_token_id);
}

/// WordPiece: at each position take the longest vocabulary entry that starts
/// there, then carry on from where it ended. The first piece of a word is
/// looked up plain, every later piece with the "##" prefix — `headphone` is
/// `head` + `##phone`, not `head` + `phone`.
fn wordPieces(
    allocator: std.mem.Allocator,
    t: *Tokenizer,
    word: []const u8,
    max_tokens: usize,
    out: *std.ArrayList(i64),
) !void {
    var buf: [max_word_chars + 2]u8 = undefined;
    var start: usize = 0;
    var first = true;

    while (start < word.len and out.items.len < max_tokens) {
        // The leading piece may be as long as the word; a continuation piece
        // never is, so bound that scan.
        const limit = if (first) word.len else @min(word.len, start + max_word_chars);
        const prefix_len: usize = if (first) 0 else 2;
        if (prefix_len == 2) {
            buf[0] = '#';
            buf[1] = '#';
        }

        var end = limit;
        while (end > start) : (end -= 1) {
            @memcpy(buf[prefix_len..][0 .. end - start], word[start..end]);
            const piece = buf[0 .. prefix_len + end - start];
            if (t.vocab.get(piece)) |id| {
                try out.append(allocator, id);
                start = end;
                first = false;
                break;
            }
        } else {
            if (first) try out.append(allocator, t.unk_token_id);
            start += 1;
        }
    }
}

// Reference ids from HuggingFace tokenizers on Xenova/all-MiniLM-L6-v2.
const test_allocator = std.testing.allocator;

fn expectIds(t: *Tokenizer, text: []const u8, want: []const u32) !void {
    var got: std.ArrayList(i64) = .empty;
    defer got.deinit(test_allocator);
    var scratch: std.ArrayList(u8) = .empty;
    defer scratch.deinit(test_allocator);
    try tokenize(test_allocator, t, text, 512, &got, &scratch);
    try std.testing.expectEqual(want.len, got.items.len);
    for (want, got.items) |w, g| try std.testing.expectEqual(@as(i64, w), g);
}

fn fixture() !Tokenizer {
    const io = std.testing.io;
    return load(io, test_allocator, "tokenizer.json");
}

test "whole words" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "hello world", &.{ 101, 7592, 2088, 102 });
}

test "continuation pieces carry ##" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "headphone", &.{ 101, 2132, 9864, 102 });
    try expectIds(&t, "headphones", &.{ 101, 2132, 19093, 102 });
    try expectIds(&t, "webroot", &.{ 101, 4773, 3217, 4140, 102 });
}

test "one word already in the vocabulary" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "unbelievable", &.{ 101, 23653, 102 });
}

test "accents are stripped" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "caf\u{00E9}", &.{ 101, 7668, 102 });
}

test "punctuation splits words but keeps its own token" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "anti-establishment", &.{ 101, 3424, 1011, 5069, 102 });
    try expectIds(&t, "don't", &.{ 101, 2123, 1005, 1056, 102 });
}

test "symbols stay inside the word" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "Bose\u{00AE} QuietComfort\u{00AE} 15", &.{
        101, 21299, 29656, 4251, 9006, 13028, 29656, 2321, 102,
    });
}

test "model numbers split into sub-words" {
    var t = try fixture();
    defer free(test_allocator, &t);
    try expectIds(&t, "UN65JU7500", &.{ 101, 4895, 26187, 9103, 23352, 8889, 102 });
}