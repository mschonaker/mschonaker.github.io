---
id: camel-k-cdc-pipeline
title: Change Data Capture with Apache Camel K, PostgreSQL, and Debezium
summary: A CDC-powered evolution of the Camel K ETL pipeline — replacing H2 polling with PostgreSQL logical replication and Debezium, with a Groovy processor that handles creates, updates, and deletes natively. Stale documents are a thing of the past.
date: 2026-07-31
image: /images/camel-k-data-pipeline-header.png
---

# Change Data Capture with Apache Camel K, PostgreSQL, and Debezium

The [previous post](/2026/07/28/camel-k-pipeline) built an ETL pipeline with Apache Camel K using timer-based SQL polling. It worked, but had a fundamental gap: **deletions were never propagated**. Remove a row from the database, and the corresponding Elasticsearch document stayed forever.

This post fixes that problem with **Change Data Capture (CDC)** — streaming database changes in real time using PostgreSQL logical replication and Debezium, with a Groovy-powered processor that handles create, update, *and delete* events correctly.

This pipeline follows the same architecture as the polling version: source Kamelet → Groovy processor → ES sink, with each Kamelet styled by a different fictional engineer at a different time.

## Architecture

```
PostgreSQL ──► movies-cdc-source ──► groovy-cdc-processor ──► elasticsearch-index-sink
   │                │                        │                       │
   │          debezium-postgres         change-event                infra
   │          component watches         parsing:
   │          movies table via          c/r  → query actors,
   │          logical replication       u    → query actors, join
   │          (pgoutput plugin)         d    → delete from ES
   │
   └── Both movies and actors tables live in the same PostgreSQL database
```

| Aspect | Polling pipeline (previous post) | CDC pipeline (this post) |
|--------|--------------------------|--------------------------|
| Trigger | Timer every 30 seconds | Database change event |
| Deletions | Stale documents stay | Deleted from ES immediately |
| Latency | ≤30 seconds | Sub-second |
| Data set | Full re-read every cycle | Only changed rows |
| Database | H2 | PostgreSQL (logical replication) |
| Source component | `sql:` consumer | `debezium-postgres` component |
| Processor logic | Always query actors + join | Branch by operation type |

## Data Model

The same schema as the polling version, but running on PostgreSQL with CDC-specific configuration:

```sql
CREATE TABLE movies (
  id VARCHAR(10) PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  release_year INTEGER NOT NULL,
  genre VARCHAR(100)
);

ALTER TABLE movies REPLICA IDENTITY FULL;

CREATE TABLE actors (
  id INTEGER NOT NULL,
  name VARCHAR(200) NOT NULL,
  character_name VARCHAR(200),
  movie_id VARCHAR(10) NOT NULL,
  PRIMARY KEY (id, movie_id)
);

ALTER TABLE actors REPLICA IDENTITY FULL;

CREATE PUBLICATION debezium_publication FOR TABLE movies, actors;
```

Two things are different from the H2 version:

1. **`REPLICA IDENTITY FULL`** — Tells PostgreSQL to include the full row (all columns) in the WAL change event, not just the primary key. Debezium needs this to emit the complete `before` and `after` images.

2. **`CREATE PUBLICATION`** — Exposes the tables to Debezium's logical replication slot.

PostgreSQL's `wal_level` is set to `logical` (configured via container args `-c wal_level=logical`), which enables the write-ahead log to carry enough information for Debezium to reconstruct change events.

## The Kamelets

### 1. movies-cdc-source — Alice, 2024

Alice's first CDC Kamelet uses the `debezium-postgres` Camel component directly. No timer, no SQL polling — it opens a replication slot and streams events as they happen.

```yaml
# Alice's CDC Kamelet — 2024
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: movies-cdc-source
  labels:
    camel.apache.org/kamelet.type: "source"
spec:
  definition:
    title: "Movies CDC Source"
    description: Streams change events from the PostgreSQL movies table via Debezium
    required:
      - dbHost
      - dbPassword
    properties:
      dbHost:
        type: string
        example: postgres.default.svc
      dbPort:
        type: string
        default: "5432"
      dbUser:
        type: string
        default: postgres
      dbPassword:
        type: string
        format: password
      dbName:
        type: string
        default: movies_db
      serverName:
        type: string
        default: movies_pg
      tableInclude:
        type: string
        default: public.movies
  dependencies:
    - "camel:core"
    - "camel:groovy"
    - "camel:debezium-postgres"
  template:
    from:
      uri: "debezium-postgres:{{serverName}}"
      parameters:
        databaseHostname: "{{dbHost}}"
        databasePort: "{{dbPort}}"
        databaseUser: "{{dbUser}}"
        databasePassword: "{{dbPassword}}"
        databaseDbname: "{{dbName}}"
        databaseServerName: "{{serverName}}"
        tableIncludeList: "{{tableInclude}}"
        pluginName: pgoutput
        slotName: "movies_cdc_slot"
        offsetStorage: "org.apache.kafka.connect.storage.MemoryOffsetBackingStore"
        debezium.max.queue.size: 8192
      steps:
        - to: kamelet:sink
```

Notice the short property names (`dbHost`, `dbPort`, `dbUser`), the minimal annotations, and the simple slot configuration. The `offsetStorage` is set to in-memory — for a demo this is fine; in production you would switch to a persistent Kafka offsets topic or a database-backed store.

Debezium connects to PostgreSQL using the `pgoutput` plugin (the native logical decoding output plugin for PostgreSQL 10+). It creates a replication slot named `movies_cdc_slot` and streams every insert, update, and delete on the `public.movies` table as a structured JSON event.

### 2. actors-cdc-source — Bob, 2026

Bob's standalone actors CDC Kamelet is a production-oriented reference — it is not wired into the pipeline Pipe, but documents the actors CDC pattern with a different style.

```yaml
# Bob's Kamelet — 2026
# Production-grade actors CDC source
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: actors-cdc-source
  labels:
    camel.apache.org/kamelet.type: "source"
  annotations:
    camel.apache.org/provider: "Apache Software Foundation"
    camel.apache.org/kamelet.group: "Database"
    camel.apache.org/kamelet.namespace: "CDC"
    camel.apache.org/kamelet.icon: >-
      data:image/svg+xml;base64,...
spec:
  definition:
    title: "Actors CDC Source"
    description: |-
      Streams change events from the PostgreSQL actors table via Debezium.
      Designed to work alongside movies-cdc-source for join-based pipelines.
    required:
      - actorsDatabaseHost
      - actorsDatabasePassword
    type: object
    properties:
      actorsDatabaseHost:
        title: "Database Host"
        type: string
        example: "postgres.default.svc"
      actorsDatabasePort:
        title: "Database Port"
        type: string
        default: "5432"
      actorsDatabaseUser:
        title: "Database User"
        type: string
        default: postgres
      actorsDatabasePassword:
        title: "Database Password"
        type: string
        default: ""
        format: password
      actorsDatabaseName:
        title: "Database Name"
        type: string
        default: movies_db
      actorsServerName:
        title: "Debezium Server Name"
        type: string
        default: actors_pg
      actorsSlotName:
        title: "Replication Slot Name"
        type: string
        default: actors_cdc_slot
  dependencies:
    - "camel:core"
    - "camel:groovy"
    - "camel:debezium-postgres"
  template:
    beans:
      - name: pgOffsetStore
        type: "#class:org.apache.kafka.connect.storage.MemoryOffsetBackingStore"
    from:
      uri: "debezium-postgres:{{actorsServerName}}"
      parameters:
        databaseHostname: "{{actorsDatabaseHost}}"
        databasePort: "{{actorsDatabasePort}}"
        databaseUser: "{{actorsDatabaseUser}}"
        databasePassword: "{{actorsDatabasePassword}}"
        databaseDbname: "{{actorsDatabaseName}}"
        databaseServerName: "{{actorsServerName}}"
        tableIncludeList: "public.actors"
        pluginName: pgoutput
        slotName: "{{actorsSlotName}}"
        offsetStorage: "#bean:pgOffsetStore"
        debezium.max.queue.size: 16384
        provideTransactionMetadata: true
      steps:
        - to: kamelet:sink
```

The differences from Alice's version are deliberate:

- Alice used `offsetStorage` as a string class name; Bob uses an explicit bean reference (`#bean:pgOffsetStore`)
- Alice used short names (`dbHost`); Bob spells them out (`actorsDatabaseHost`)
- Bob adds `provideTransactionMetadata: true` for transaction boundary tracking
- Bob includes a larger queue buffer (16384 vs 8192)

### 3. groovy-cdc-processor — Charlie, 2026

The heart of the pipeline. This processor Kamelet receives Debezium change events and branches on the operation type:

```
Debezium change event
  │
  ├─ op = "d" (delete)  →  CamelEsOperation=DELETE, indexId=movieId
  │
  └─ op = "c"/"r"/"u"   →  extract movie fields from after-image
       (create/read/       →  query actors table via Groovy SQL
        update)             →  build joined JSON with JsonOutput
                            →  CamelEsOperation=INDEX, indexId=movieId
```

```yaml
# Charlie's Groovy CDC processor — 2026
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: groovy-cdc-processor
  labels:
    camel.apache.org/kamelet.type: "sink"
  annotations:
    camel.apache.org/provider: "Apache Software Foundation"
    camel.apache.org/kamelet.group: "Processing"
    camel.apache.org/kamelet.namespace: "CDC"
spec:
  definition:
    title: "Groovy CDC Processor"
    description: |-
      Processes Debezium change events for the movies table.
      For create/update events, queries the actors table and produces
      a joined JSON document.  For delete events, instructs the ES
      sink to remove the document.
    required:
      - actorsJdbcUrl
    properties:
      actorsJdbcUrl:
        title: Actors JDBC URL
        type: string
        example: jdbc:postgresql://postgres.default.svc:5432/movies_db
      actorsDbUser:
        title: Actors DB User
        type: string
        default: postgres
      actorsDbPassword:
        title: Actors DB Password
        type: string
        default: ""
        format: password
  dependencies:
    - "camel:core"
    - "camel:sql"
    - "camel:groovy"
    - "mvn:org.postgresql:postgresql:42.7.4"
    - "mvn:org.apache.commons:commons-dbcp2:2.14.0"
  template:
    beans:
      - name: actorsDb
        type: "#class:org.apache.commons.dbcp2.BasicDataSource"
        properties:
          url: "{{actorsJdbcUrl}}"
          username: "{{actorsDbUser}}"
          password: "{{actorsDbPassword}}"
          driverClassName: "org.postgresql.Driver"
          initialSize: 2
          maxTotal: 10
    from:
      uri: kamelet:source
      steps:
        - setProperty:
            name: cdcOp
            groovy: "body['op']"
        - setProperty:
            name: cdcAfter
            groovy: "body['after']"
        - setProperty:
            name: cdcBefore
            groovy: "body['before']"

        - choice:
            when:
              - groovy: "exchange.getProperty('cdcOp') == 'd'"
                steps:
                  - setHeader:
                      name: CamelEsOperation
                      constant: "DELETE"
                  - setHeader:
                      name: indexId
                      groovy: "exchange.getProperty('cdcBefore')['id']"
                  - setBody:
                      constant: ""

              - groovy: "exchange.getProperty('cdcOp') == 'c' || exchange.getProperty('cdcOp') == 'r' || exchange.getProperty('cdcOp') == 'u'"
                steps:
                  - setProperty:
                      name: movieId
                      groovy: "exchange.getProperty('cdcAfter')['id']"
                  - setProperty:
                      name: movieTitle
                      groovy: "exchange.getProperty('cdcAfter')['title']"
                  - setProperty:
                      name: movieYear
                      groovy: "exchange.getProperty('cdcAfter')['release_year']"
                  - setProperty:
                      name: movieGenre
                      groovy: "exchange.getProperty('cdcAfter')['genre']"

                  - setBody:
                      groovy: |
                        "SELECT id, name, character_name FROM actors WHERE movie_id = '" + exchange.getProperty('movieId') + "'"
                  - to:
                      uri: "sql:."
                      parameters:
                        dataSource: "#bean:actorsDb"
                        outputType: SelectList
                        useMessageBodyForSql: true

                  - setProperty:
                      name: actorsList
                      groovy: "body"

                  - setBody:
                      groovy: |
                        groovy.json.JsonOutput.toJson([
                          movieId: exchange.getProperty('movieId'),
                          title: exchange.getProperty('movieTitle'),
                          year: exchange.getProperty('movieYear') as Integer,
                          genre: exchange.getProperty('movieGenre'),
                          actors: exchange.getProperty('actorsList')
                        ])

                  - setHeader:
                      name: CamelEsOperation
                      constant: "INDEX"
                  - setHeader:
                      name: indexId
                      groovy: "exchange.getProperty('movieId')"

        - to: kamelet:sink
```

The `choice` step branches on the operation code:

- **`d` (delete)**: Extracts the movie ID from `cdcBefore` (the row state before deletion), sets `CamelEsOperation` to `DELETE`, and clears the body. The ES sink receives the deletion request and removes the document.

- **`c` (create), `r` (snapshot read), `u` (update)**: Extracts movie fields from `cdcAfter`, queries the actors table via Groovy-built SQL, joins with `JsonOutput.toJson()`, and sets `CamelEsOperation` to `INDEX` for upsert.

The `CamelEsOperation` header overrides the Elasticsearch component's default `INDEX` operation on a per-exchange basis.

### 4. elasticsearch-index-sink — pre-existing infrastructure

Same as the polling pipeline. The cleaned ES sink Kamelet is pre-deployed infrastructure, shared across pipelines.

## The Pipe

The Pipe uses the same multi-step structure as the polling version, but with CDC-specific Kamelets:

```yaml
apiVersion: camel.apache.org/v1
kind: Pipe
metadata:
  name: movies-actors-cdc
  annotations:
    camel.apache.org/description: >-
      CDC pipeline: streams movies changes from PostgreSQL via Debezium,
      joins with actors via Groovy, and indexes/deletes documents in
      Elasticsearch.  Deletes are propagated — not left as stale.
spec:
  source:
    ref:
      kind: Kamelet
      apiVersion: camel.apache.org/v1
      name: movies-cdc-source
    properties:
      dbHost: "postgres.default.svc"
      dbPort: "5432"
      dbUser: "postgres"
      dbPassword: "postgres"
      dbName: "movies_db"
      tableInclude: "public.movies"
  steps:
    - ref:
        kind: Kamelet
        apiVersion: camel.apache.org/v1
        name: groovy-cdc-processor
      properties:
        actorsJdbcUrl: "jdbc:postgresql://postgres.default.svc:5432/movies_db"
        actorsDbUser: "postgres"
        actorsDbPassword: "postgres"
  sink:
    ref:
      kind: Kamelet
      apiVersion: camel.apache.org/v1
      name: elasticsearch-index-sink
    properties:
      clusterName: "elasticsearch"
      hostAddresses: "elasticsearch:9200"
      indexName: "movies-actors-joined"
      enableSSL: "false"
```

The source now points at `movies-cdc-source` (the Debezium-powered Kamelet) instead of the polling `movies-source`. The `groovy-cdc-processor` replaces the `groovy-join` — it handles all three operation types instead of only the upsert case.

## Running the Pipeline

### Deploy to Kubernetes

```bash
cd _code/camel-k-movies-actors-cdc
./setup.sh
```

The script:
1. Starts minikube, installs Camel K, configures the registry
2. Deploys Elasticsearch and the ES sink Kamelet (pre-existing infrastructure)
3. Deploys PostgreSQL 16 with `wal_level=logical`, tables, seed data, and the Debezium publication
4. Applies the pipeline Kamelets and Pipe

### Verify

```bash
# Check the Pipe and Integration
kubectl get pipe -n default
kubectl get integration -n default

# After a few seconds, the Debezium snapshot should have indexed all 50 movies
kubectl exec deploy/elasticsearch -n default -- curl -s 'http://localhost:9200/movies-actors-joined/_count'
# → {"count":50}

# View integration logs
kubectl logs -l camel.apache.org/integration=movies-actors-cdc -n default --tail=30
```

### Test deletion propagation

This is the headline feature of CDC — deletions are propagated immediately:

```bash
# Delete a movie from PostgreSQL
kubectl exec deploy/postgres -n default -- psql -U postgres -d movies_db \
  -c "DELETE FROM movies WHERE id = 'tt0111161';"

# Check ES — the document should be gone within seconds
kubectl exec deploy/elasticsearch -n default -- curl -s 'http://localhost:9200/movies-actors-joined/_count'
# → {"count":49}
```

The Debezium source emits a change event with `op: "d"`, the Groovy processor sets `CamelEsOperation: DELETE`, and the ES sink removes the document. No stale documents, no cleanup job, no full re-index.

### Idempotency

Like the polling version, the `indexId` header makes upserts safe — re-inserting the same movie updates the existing document rather than creating a duplicate. The CDC source is also idempotent: Debezium tracks offsets via the replication slot, so a restart picks up where it left off.

## The Debugging Journey

### 1. REPLICA IDENTITY Matters

**The error:** Debezium emitted events with `before: null` even for deletes.

**The cause:** The `actors` table had only a default `REPLICA IDENTITY` (which uses the primary key). Before PostgreSQL 15, a DELETE event would include only the PK columns in `before`. After PostgreSQL 15, it includes nothing.

**The fix:** Set `ALTER TABLE <table> REPLICA IDENTITY FULL` — this tells PostgreSQL to include all columns in the WAL before-image.

### 2. Memory Offset Storage Is Not Persistent

**The error:** After a Pod restart, Debezium re-processed all 50 movies (duplicate snapshot events).

**The cause:** `MemoryOffsetBackingStore` loses offsets on restart. Debezium thinks it's starting fresh.

**The fix:** In production, switch to `org.apache.kafka.connect.storage.FileOffsetBackingStore` (with a persistent volume) or use Kafka to store offsets. For this demo, the `indexId` header makes re-processing safe — it just upserts existing documents.

### 3. Debezium Component vs Kamelet

**The error:** At first, we tried to use `kamelet:debezium-postgresql-source` inside a custom Kamelet's `from:` URI. The operator did not resolve the bundled Kamelet correctly in this context.

**The cause:** Camel K Kamelets resolve `kamelet:` endpoints at the Pipe level, not inside other Kamelets' templates.

**The fix:** Use the `debezium-postgres` Camel component directly in the custom Kamelet's `from:` URI. This bypasses the Kamelet resolution layer and works reliably.

### 4. PostgreSQL WAL Retention

**The error:** The replication slot grew unbounded during debugging, filling the pod's disk.

**The cause:** Debezium creates a replication slot (`movies_cdc_slot`). If the consumer disconnects without advancing the offset, PostgreSQL retains WAL segments indefinitely.

**The fix:** In the development cluster, drop and recreate the slot when restarting:
```sql
SELECT pg_drop_replication_slot('movies_cdc_slot');
```
In production, configure `slot.retention.time` and monitor WAL disk usage.

## Verification

After the initial Debezium snapshot completes, Elasticsearch contains 50 documents — same as the polling pipeline:

```json
{
  "movieId": "tt0111161",
  "title": "The Shawshank Redemption",
  "year": 1994,
  "genre": "Drama",
  "actors": [
    { "ID": 1, "NAME": "Tim Robbins", "CHARACTER_NAME": "Andy Dufresne" },
    { "ID": 2, "NAME": "Morgan Freeman", "CHARACTER_NAME": "Ellis Boyd \"Red\" Redding" }
  ]
}
```

The difference is how we got there:

- **Polling version**: 50 SQL queries (one for movies, 50 for actors), every 30 seconds
- **CDC version**: One initial snapshot event per movie, then zero queries until data changes

And when you delete a movie from the database:
- **Polling version**: Document stays in ES forever
- **CDC version**: Document is removed within seconds

## Key Takeaways

1. **CDC propagates deletes automatically.** This is the single biggest advantage over timer-based polling. The Groovy processor's `choice` block branches on the Debezium `op` field to issue `DELETE` operations to Elasticsearch.

2. **Use `CamelEsOperation` header to override the sink's operation.** The ES endpoint is configured with `operation: INDEX`, but setting the header `CamelEsOperation: DELETE` on a per-exchange basis overrides it for delete events.

3. **`REPLICA IDENTITY FULL` is required for complete before-images.** Without it, the `before` field in Debezium events contains only the primary key (or nothing on PostgreSQL 15+).

4. **Debezium offset storage must match your durability requirements.** Memory is fine for demos. Production needs persistent storage — either a file on a PV or a Kafka topic.

5. **Same vintage styling, same Groovy patterns, different trigger mechanism.** The architecture (source → processor → sink) carries over cleanly from polling to CDC. The Kamelets still look like different engineers wrote them at different times. Only the `from:` endpoint changes — from `sql:` to `debezium-postgres:`.

6. **CDC does not replace the need for a Groovy-powered join processor.** Debezium streams changes from a single table. The join with the `actors` table is still a SQL query driven by Groovy — the same pattern as the polling version.
