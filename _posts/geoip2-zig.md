---
id: geoip2-zig
title: Building a GeoIP2 Service from Scratch in Zig
summary: A deep dive into implementing binary protocol parsing, Patricia trie traversal, and async I/O in Zig—no external dependencies.
date: 2026-04-04
image: /images/geoip2-zig-header.png
---

# Building a GeoIP2 Service from Scratch in Zig

I just released [GeoIP2-zig](https://github.com/mschonaker/GeoIP2-zig), a hand-rolled implementation of MaxMind's GeoIP2 binary format in Zig. No C bindings, no wrappers—just Zig's standard library and a 40MB embedded database.

**Performance: ~5K requests/second.**

This project was an exercise in low-level systems programming: binary protocol parsing at the bit level, zero-allocation IP lookups, and Zig's async I/O model.

## The Problem

MaxMind's GeoIP2 format (MMDB) is a binary database that maps IP addresses to geographic data. It's optimized for fast lookups—hence the "MMDB" name (MaxMind Database). The format uses a Patricia trie for IP routing with custom binary encoding and pointer compression.

Most implementations wrap C libraries. But MMDB is surprisingly elegant once you understand its structure. The format is well-documented, so I decided to implement it from scratch.

## Architecture Overview

```mermaid
flowchart LR
    Client[HTTP client] --> Server[HTTP server<br/>main.zig]
    Server --> Parser[URL parser<br/>IpVersion union]
    Parser --> Lookup[MMDB trie lookup<br/>mmdb.zig]
    Lookup --> Reader[Binary data reader<br/>data_reader.zig]
    Reader --> Writer[JSON writer<br/>data_writer.zig]
    Writer --> Response[Streaming JSON<br/>HTTP response]
```

The server runs on Zig's `Io.Threaded` with per-connection async handlers. Each request walks the trie, reads from the embedded database, and streams JSON directly to the socket.

## Binary Protocol Parsing

The MMDB format uses a custom encoding scheme that packs data tightly. The interesting part is `data_reader.zig`—it handles pointers, variable-length integers, maps, arrays, and strings.

The pointer compression is particularly clever. Instead of storing full offsets, smaller pointers use fewer bytes by leveraging the fact that most references point to nearby data.

## Patricia Trie Traversal

The IP lookup uses a Patricia trie—a binary tree where each bit of an IP address determines the path. Walking 128 bits (for IPv6) through a precomputed binary trie is elegantly simple. No heap allocations after startup—the entire lookup is zero-allocation.

## Streaming JSON Serialization

Rather than building an intermediate representation, the JSON writer writes directly to the socket buffer. This avoids allocating JSON AST nodes for every request.

## The API

Simple and RESTful:

```
GET /ipv4/8.8.8.8
GET /ipv6/2001:4860:4860::8888
```

Response:
```json
{
  "country": { "iso_code": "US", "names": { "en": "United States" } },
  "city": { "names": { "en": "Mountain View" } },
  "location": { "latitude": 37.4223, "longitude": -122.0848, "time_zone": "America/Los_Angeles" }
}
```

## Running It

```bash
zig build
./zig-out/bin/geoip-zig
curl http://127.0.0.1:8080/ipv4/8.8.8.8
```

## Project Structure

```
src/
├── main.zig              # entry point, http server, async
├── signals.zig           # POSIX signal handlers
├── mmdb/
│   ├── mmdb.zig         # trie traversal, lookup API
│   ├── data_reader.zig  # binary format parser
│   ├── data_writer.zig  # binary-to-JSON
│   └── metadata.zig     # database metadata
```

## Why This Matters

The code demonstrates how to decode a real binary protocol byte-by-byte. The MMDB format isn't a toy—it's a production format used by Cloudflare, Fastly, and others for geo-blocking, content localization, and security analytics.

For anyone learning low-level systems programming, this is a concrete example of:
- Bit-level binary protocol parsing
- Patricia trie data structures
- Explicit memory management with fixed buffers
- Zig's async I/O model
- Streaming JSON without intermediate representations

The interesting files to read are `data_reader.zig` and `mmdb.zig`—they show the core algorithms.

## References

### Official Sources
- [MaxMind GeoIP2 Database Format](https://maxmind.github.io/MaxMind-DB/) — Official specification
- [MaxMind DB File Format Spec](https://github.com/maxmind/maxmind-db-reader-xs/blob/main/lib/MaxMind/DB/Reader.pm) — Perl implementation reference
- [GeoIP2 ZIP Download](https://dev.maxmind.com/geoip/geoip2/downloadable/) — Free database downloads
