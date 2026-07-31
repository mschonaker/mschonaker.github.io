# Change Data Capture with Bento and Conduit

This demo streams change events from a PostgreSQL `movies` table into
Elasticsearch. It uses two open-source tools:

- **Conduit** (`ConduitIO/conduit` v0.19.0) captures CDC from PostgreSQL via
  logical replication and writes each change as an OpenCDC JSON record to a
  plain text bridge file.
- **Bento** (`warpstreamlabs/bento` v1.20.0) tails the bridge file, joins each
  movie with its actors, and indexes the enriched document into
  Elasticsearch.

There is no message broker. The bridge file is the only connection between the
two tools, which keeps the demo small and easy to inspect.

## Pipeline

```
PostgreSQL (movies) ──logical replication──▶ Conduit ──▶ bridge/cdc-events.jsonl
                                                           │ (OpenCDC JSONL)
                                                           ▼
                                               Bento: file_tail input
                                                      sql_raw join actors
                                                      mapping + switch
                                                           ▼
                                                   Elasticsearch (movies-actors-joined)
```

1. Conduit's `builtin:postgres` source connects to PostgreSQL, takes an
   initial snapshot, and then listens for logical replication changes.
2. Each change becomes one JSON line in `bridge/cdc-events.jsonl` with the
   OpenCDC record format (`operation`, `key`, `payload.before`, `payload.after`).
3. Bento's `file_tail` input reads every new line.
4. Bento enriches each movie event with its actors using an `sql_raw`
   processor, maps the result, and writes to Elasticsearch with the
   `elasticsearch_v2` output.
5. Create, update, and delete operations are propagated to Elasticsearch as
   index and delete actions.

## Data Model

- `movies`: 50 rows. Primary key `id` is an auto-incrementing integer.
  `imdb_id` keeps the original IMDb-style identifier (`tt0111161`) as a unique
  business key.
- `actors`: 125 rows, one to many with `movies` via `movie_id`.
- Both tables use `REPLICA IDENTITY FULL` so logical replication carries the
  full row image (needed for delete events).

### Why is the primary key an integer?

The Conduit PostgreSQL source connector only accepts integer primary keys
(`smallint`, `integer`, `bigint`) for its snapshot iterator. A `varchar`
primary key fails with:

```
failed to validate key: key "id" of type "character varying" is unsupported
```

The connector has no option to override the key column, so the demo adds a
`SERIAL` surrogate key and keeps the IMDb id as a separate unique column.

## Prerequisites

- Docker (PostgreSQL and Elasticsearch run as containers)
- `conduit` (brew install conduit)
- `bento` (brew install bento)
- `curl` and `python3` (used by the helper scripts)

## Run

```bash
./setup.sh       # start PostgreSQL + Elasticsearch containers, seed data
./run.sh         # start Conduit + Bento, verify 50 docs indexed
./test.sh        # show pipeline status and indexed documents
./test-cdc.sh    # insert/update/delete a movie and watch it propagate
```

## Inspect

```bash
# Change events written by Conduit
head -1 bridge/cdc-events.jsonl

# An enriched movie document in Elasticsearch
curl -s localhost:9200/movies-actors-joined/_doc/1 | python3 -m json.tool

# Document count
curl -s localhost:9200/movies-actors-joined/_count
```

## Stop

```bash
pkill -f "conduit run"
pkill -f "bento -c"
docker stop pg-movies es-movies && docker rm pg-movies es-movies
```

## Layout

```
data/init-db.sql       schema + seed data (50 movies, 125 actors)
pipelines/movies-cdc.yaml   Conduit pipeline (postgres -> file bridge)
conduit.yaml           Conduit service config (portable relative paths)
configs/bento.yaml     Bento config (file_tail -> sql_raw -> elasticsearch_v2)
bridge/                runtime bridge file (created by run.sh)
```

## References

- Bento docs: https://warpstreamlabs.github.io/bento/docs/about
- Conduit docs: https://conduitio.github.io/docs/
- Conduit PostgreSQL connector: https://github.com/ConduitIO/conduit-connector-postgres
