---
id: bento-conduit-cdc-pipeline
title: Change Data Capture with Conduit, PostgreSQL, and Bento
summary: A CDC-powered pipeline with no message broker — Conduit streams PostgreSQL logical replication changes to a plain JSONL bridge file, and Bento tails the file, joins actors, and indexes enriched documents into Elasticsearch. Deletes propagate, stale documents are gone.
date: 2026-08-01
image: /images/bento-conduit-cdc-header.png
---

# Change Data Capture with Conduit, PostgreSQL, and Bento

The [Camel K CDC post](/2026/07/31/camel-k-cdc-pipeline) built a change-data-capture pipeline with Debezium and Groovy. It fixed the polling version's biggest gap: **deletions were never propagated**. But it ran on Kubernetes with a message broker and a JVM — a heavy setup for a small demo.

This post rebuilds the same pipeline with two smaller open-source tools and **no message broker**:

- **[Conduit](https://conduitio.github.io/docs/)** captures CDC from PostgreSQL via logical replication and writes each change as an OpenCDC JSON record to a plain text file.
- **[Bento](https://warpstreamlabs.github.io/bento/docs/about)** tails that file, joins each movie with its actors, and indexes the enriched document into Elasticsearch.

The two tools never talk over a network. The bridge file is the only connection, which makes the pipeline easy to run, inspect, and debug on a laptop.

## Architecture

```
PostgreSQL ──logical replication──► Conduit ──► bridge/cdc-events.jsonl
   movies                              │              │
   (publication movies_pub)            │     (OpenCDC JSONL, one
                                       │      record per change)
                                       ▼              ▼
                                             Bento: file_tail input
                                                    sql_raw join actors
                                                    switch by operation
                                                           │
                                                           ▼
                                                   Elasticsearch
                                              (movies-actors-joined)
```

| Aspect | Polling pipeline (Camel K) | CDC pipeline (Camel K + Debezium) | CDC pipeline (this post) |
|--------|--------------------------|--------------------------|--------------------------|
| Trigger | Timer every 30 seconds | Database change event | Database change event |
| Deletions | Stale documents stay | Deleted from ES immediately | Deleted from ES immediately |
| Latency | ≤30 seconds | Sub-second | Sub-second |
| Data set | Full re-read every cycle | Only changed rows | Only changed rows |
| Database | H2 | PostgreSQL (logical replication) | PostgreSQL (logical replication) |
| Capture | `sql:` consumer | `debezium-postgres` component | Conduit `builtin:postgres` |
| Join | Groovy + SQL | Groovy + SQL | Bento `sql_raw` |
| Broker | none | Kafka (Debezium offset storage) | none |

## Data Model

The same seed data as the Camel K version — 50 movies, 125 actors — with one structural change required by Conduit:

```sql
CREATE TABLE movies (
  id SERIAL PRIMARY KEY,
  imdb_id VARCHAR(10) NOT NULL UNIQUE,
  title VARCHAR(200) NOT NULL,
  release_year INTEGER NOT NULL,
  genre VARCHAR(100)
);

ALTER TABLE movies REPLICA IDENTITY FULL;

CREATE TABLE actors (
  id INTEGER NOT NULL,
  name VARCHAR(200) NOT NULL,
  character_name VARCHAR(200),
  movie_id INTEGER NOT NULL REFERENCES movies(id),
  PRIMARY KEY (id, movie_id)
);

ALTER TABLE actors REPLICA IDENTITY FULL;

CREATE PUBLICATION movies_pub FOR TABLE movies;
```

Three things are different from the Camel K version:

1. **`movies.id` is now an integer auto-increment (`SERIAL`).** The Conduit PostgreSQL source only accepts integer primary keys for its snapshot iterator — a `varchar` key fails validation (more on this in the debugging section). The original IMDb identifier (`tt0111161`) survives as the unique `imdb_id` business key.

2. **`REPLICA IDENTITY FULL`** — Tells PostgreSQL to include the full row in the WAL change event, not just the primary key. Conduit needs this to emit complete `before` and `after` images, especially for deletes.

3. **`CREATE PUBLICATION movies_pub FOR TABLE movies`** — Publishes only the `movies` table. The actors table is *not* published: actors are joined at processing time by Bento, not streamed through the bridge. Publishing both tables would leak actor events into the bridge file and corrupt the join (another debugging-story entry below).

PostgreSQL's `wal_level` is set to `logical` (container arg `-c wal_level=logical`), which enables the write-ahead log to carry enough information for Conduit to reconstruct change events.

## The Conduit Pipeline

Conduit is configured with two files. The service config `conduit.yaml` uses relative paths so the whole demo is portable:

```yaml
config:
  path: ./conduit.yaml
db:
  type: badger
  badger:
    path: ./conduit.db
api:
  enabled: true
  http:
    address: :8080
  grpc:
    address: :8084
connectors:
  path: ./connectors
processors:
  path: ./processors
pipelines:
  path: ./pipelines
```

The pipeline `pipelines/movies-cdc.yaml` wires a `builtin:postgres` source to a `builtin:file` destination:

```yaml
version: 2.2
pipelines:
  - id: movies-cdc
    status: running
    description: >-
      Streams change events from the PostgreSQL movies table via logical
      replication and writes them to the bridge file consumed by Bento.
    connectors:
      - id: movies-source
        type: source
        plugin: builtin:postgres
        settings:
          url: "postgres://postgres:postgres@localhost:5432/movies_db?sslmode=disable"
          tables: "movies"
          cdcMode: "logrepl"
          logrepl.publicationName: "movies_pub"
          logrepl.slotName: "movies_slot"
          snapshotMode: "initial"
      - id: cdc-bridge
        type: destination
        plugin: builtin:file
        settings:
          path: "./bridge/cdc-events.jsonl"
          sdk.record.format: "opencdc/json"
```

Notes on the settings:

- **`cdcMode: "logrepl"`** — Uses PostgreSQL's native logical replication (the same `pgoutput` plugin Debezium uses). Conduit creates the replication slot and publication if they do not exist.
- **`snapshotMode: "initial"`** — On first run, Conduit takes a consistent snapshot of the table, then switches to streaming. Each snapshot row becomes a record with `operation: "snapshot"`.
- **`sdk.record.format: "opencdc/json"`** — Writes each record as one line of JSON in the [OpenCDC record format](https://conduitio.github.io/docs/using/connectors/configuration-parameters/output-format): `position`, `operation`, `metadata`, `key`, and `payload`.

## The Bridge File

This is the heart of the "no broker" design. Conduit writes one JSON record per line:

```json
{"position":"eyJ0eXBlIjoxLCJzbmFwc2hvdHMiOnsibW92aWVzIjp7Imxhc3RfcmVhZCI6MSwic25hcHNob3RfZW5kIjo1MH19fQ==","operation":"snapshot","metadata":{"conduit.source.connector.id":"movies-cdc:movies-source","opencdc.collection":"movies","opencdc.readAt":"1785466039958291000"},"key":{"id":1},"payload":{"before":null,"after":{"genre":"Drama","id":1,"imdb_id":"tt0111161","release_year":1994,"title":"The Shawshank Redemption"}}}
```

Three fields drive Bento's logic:

- **`operation`** — `snapshot`, `create`, `update`, or `delete`.
- **`metadata.opencdc.collection`** — The source table name (`movies`). This is how Bento distinguishes movie events from any other table that might share the bridge.
- **`payload.before` / `payload.after`** — The row state before and after the change. For a delete, `after` is `null` and `before` holds the last state.

## The Bento Config

Bento's config `configs/bento.yaml` is a single file: input, processors, output.

```yaml
input:
  file_tail:
    path: ./bridge/cdc-events.jsonl

pipeline:
  processors:
    - switch:
        - check: this.operation == "delete" && this.metadata."opencdc.collection" == "movies"
          processors:
            - mapping: |
                meta es_action = "delete"
                root.movieId = this.payload.before.id

        - check: (this.operation == "create" || this.operation == "update" || this.operation == "snapshot") && this.metadata."opencdc.collection" == "movies"
          processors:
            - mapping: |
                meta es_action = "index"
                meta movie_id = this.payload.after.id
                meta movie_title = this.payload.after.title
                meta movie_year = this.payload.after.release_year
                meta movie_genre = this.payload.after.genre
                root = this

            - sql_raw:
                driver: postgres
                dsn: "postgres://postgres:postgres@localhost:5432/movies_db?sslmode=disable"
                query: "SELECT id, name, character_name FROM actors WHERE movie_id = $1"
                args_mapping: |
                  root = [ meta("movie_id") ]

            - mapping: |
                root.movieId = meta("movie_id")
                root.title = meta("movie_title")
                root.year = meta("movie_year")
                root.genre = meta("movie_genre")
                root.actors = this

output:
  elasticsearch_v2:
    urls: ["http://localhost:9200"]
    index: movies-actors-joined
    id: ${! json("movieId") }
    action: ${! meta("es_action") }
```

The `switch` processor branches on the operation type, mirroring the Groovy `choice` block from the Camel K version:

- **`delete`** → Sets `es_action` to `delete` and extracts the movie ID from the `before` image. Bento issues an Elasticsearch `delete` — no stale documents.
- **`create` / `update` / `snapshot`** → Sets `es_action` to `index`, extracts movie fields into metadata, queries the actors table with `sql_raw`, and builds the joined document with `actors` as an array.

Two details are easy to miss:

1. **`this.metadata."opencdc.collection"` is quoted.** The Conduit metadata keys literally contain dots (`opencdc.collection`). Unquoted, Bloblang treats the dot as a path separator and the check silently evaluates to `false` — and the `switch` drops the message. Quoting the key makes the whole record, and the whole pipeline, work.

2. **The `switch` drops unhandled operations.** Any record that matches neither branch (for example, an event from a table that is not `movies`) is silently dropped. This is the second line of defense against the actor-event leak described below.

## Running the Pipeline

All the containers and configs live in `_code/bento-conduit-movies-actors/`:

```bash
cd _code/bento-conduit-movies-actors
./setup.sh   # start PostgreSQL + Elasticsearch containers, seed data
./run.sh     # start Conduit + Bento, verify 50 docs indexed
```

`setup.sh` starts the two Docker containers and waits for them to be healthy. `run.sh` resets the bridge file and the ES index, starts Conduit, waits for the snapshot, starts Bento, and reports the indexed document count.

### Verify

```bash
./test.sh
```

```text
Elasticsearch index:
health status index                uuid                   pri rep docs.count
yellow open   movies-actors-joined ...                      1   1         50

Document count in movies-actors-joined:
Count: 50

Sample documents (first movie):
  title: The Shawshank Redemption | actors: 4
```

### Test deletion propagation

The headline feature of CDC — deletions are propagated immediately:

```bash
./test-cdc.sh
```

```text
1) Insert a new movie (id=51)...
   ES doc found: True -> Test Movie
2) Update the movie title...
   ES title: Test Movie Updated
3) Delete the movie...
   ES doc found after delete: False
4) Final document count (should be 50):
   Count: 50
```

The insert flows through Conduit as `operation: create`, Bento indexes it with its (empty) actor list. The update flows as `operation: update` and overwrites the document. The delete flows as `operation: delete` and removes it. No cleanup job, no full re-index.

### Inspect

The bridge file makes the pipeline transparent at every step:

```bash
# Change events written by Conduit
head -1 bridge/cdc-events.jsonl

# An enriched movie document in Elasticsearch
curl -s localhost:9200/movies-actors-joined/_doc/1 | python3 -m json.tool
```

## The Debugging Journey

### 1. Integer Primary Keys Are Mandatory

**The error:** Conduit's source connector started, then the pipeline stopped with:

```
failed to create snapshot iterator: failed to validate table fetcher "movies"
config: failed to validate key: key "id" of type "character varying" is unsupported
```

**The cause:** The Conduit PostgreSQL connector auto-detects the primary key and only supports `smallint`, `integer`, and `bigint` for its snapshot iterator. The original `movies.id VARCHAR(10)` (IMDb-style `tt0111161`) is rejected, and there is no configuration option to override the key column.

**The fix:** Add a `SERIAL` surrogate key and keep the IMDb id as a separate unique `imdb_id` column. This is a real limitation worth knowing if you plan to stream an existing table with string keys.

### 2. The Publication Must Cover Only the Source Table

**The error:** An `UPDATE` on the `actors` table overwrote a movie document in Elasticsearch with garbage fields (`title: null`, `year: null`).

**The cause:** The original seed SQL created `CREATE PUBLICATION movies_pub FOR TABLE movies, actors`. Conduit's logical replication streamed actor changes through the bridge too. Bento treated an actor event as a movie event: the actor's `id` became the ES document id, the `sql_raw` join used the wrong value, and the document at that id was corrupted.

**The fix:** Publish only `movies` in the SQL, and guard Bento's `switch` on `this.metadata."opencdc.collection" == "movies"` as a second line of defense. The actors table is joined at processing time, not streamed.

### 3. Quoted Keys in Bloblang

**The error:** After adding the collection guard, no documents were indexed at all. Bento's log showed `elasticsearch action 'null' is not allowed`.

**The cause:** `this.metadata.opencdc.collection` evaluates to `null` because the Conduit metadata key is literally named `opencdc.collection` — the dots are part of the key, not path separators. Every message failed the switch checks and was dropped.

**The fix:** Quote the key: `this.metadata."opencdc.collection"`. Verified with `bento blobl` before restarting.

### 4. Relative Paths Are Relative to the Working Directory

**The error:** A test pipeline wrote its bridge file to the repository root instead of the demo directory.

**The cause:** Conduit resolves a relative `path` setting against the process working directory, not against the pipeline file location.

**The fix:** Always run Conduit from the demo directory (`./run.sh` does this with `cd`), and keep the configs in the same directory tree so the paths stay portable.

## Verification

After the initial snapshot completes, Elasticsearch contains 50 documents:

```json
{
  "movieId": 1,
  "title": "The Shawshank Redemption",
  "year": 1994,
  "genre": "Drama",
  "actors": [
    { "id": 1, "name": "Tim Robbins", "character_name": "Andy Dufresne" },
    { "id": 2, "name": "Morgan Freeman", "character_name": "Ellis Boyd \"Red\" Redding" }
  ]
}
```

The difference from the polling version is the same as the Debezium post, but the machinery is lighter:

- **Polling version**: 50 SQL queries (one for movies, 50 for actors), every 30 seconds
- **Debezium version**: Debezium + Kafka offset storage + Groovy processor on Kubernetes
- **Conduit + Bento version**: two single-binary tools, one JSONL file, no broker

And when you delete a movie from the database, the document is removed within seconds in both CDC versions. The polling version would keep it forever.

## Key Takeaways

1. **CDC propagates deletes automatically.** This is the single biggest advantage over timer-based polling. Conduit emits `operation: delete`, and Bento's `switch` maps it to an Elasticsearch `delete` action.

2. **A file is a legitimate event bus for a demo.** Conduit writes OpenCDC JSONL; Bento tails it with `file_tail`. No broker to install, no topics to create, and every event is human-readable in the bridge file.

3. **The Conduit PostgreSQL source requires integer primary keys.** Plan for a `SERIAL` surrogate key when you adopt Conduit for an existing table with string keys.

4. **Publish only the tables you stream.** `CREATE PUBLICATION ... FOR TABLE movies` — including `actors` in the publication leaked actor events into the bridge and corrupted the join.

5. **Quote metadata keys that contain dots.** `metadata."opencdc.collection"` — unquoted, the check silently fails and the `switch` drops every message.

6. **CDC does not remove the need for a join.** Conduit streams changes from a single table. The actors join is still a query — Bento's `sql_raw` processor plays the role of the Groovy `choice` + `sql:` steps from the Camel K version.

7. **Two binaries replace a cluster.** For a laptop-scale demo, Conduit and Bento give the same CDC behavior as Debezium + Kafka on Kubernetes, with a much smaller footprint.
