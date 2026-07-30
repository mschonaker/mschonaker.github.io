---
id: camel-k-pipeline
title: Building an ETL Data Pipeline with Apache Camel K
summary: A practical end-to-end demonstration of Apache Camel K on Kubernetes, using separate vintage-styled Kamelets for two H2 databases and a Groovy-powered join processor to index joined movie-actor documents into Elasticsearch.
date: 2026-07-28
image: /images/camel-k-data-pipeline-header.png
---

# Building an ETL Data Pipeline with Apache Camel K

[Camel K](https://camel.apache.org/camel-k/2.10.x/index.html) is a lightweight integration framework built for Kubernetes. It runs [Apache Camel](https://camel.apache.org/) integrations natively on Kubernetes with minimal configuration — define a `Kamelet` or `Pipe`, apply it, and Camel K handles the rest.

This post walks through an end-to-end ETL pipeline built with Camel K:

- **Extract** movies from one H2 database and actors from another
- **Transform** by joining movies with their actors in-flight using **Groovy** scripts
- **Load** the joined JSON documents into Elasticsearch

The twist: each Kamelet is styled to look like it was created at a different time by a different engineer. The pipeline processor uses **Groovy** — not Simple expressions — for all join logic.

## Architecture

The pipeline uses three Kamelets wired together by a Pipe, with Elasticsearch as pre-existing infrastructure:

```
┌─────────────────────┐     ┌──────────────────────┐     ┌──────────────────────────┐
│   movies-source     │────►│     groovy-join      │────►│ elasticsearch-index-sink │
│  (source kamelet)   │     │  (processor kamelet)  │     │  (sink kamelet, pre-ex)  │
│                     │     │                      │     │                          │
│  polls movies from  │     │  receives movie row  │     │  indexes joined JSON     │
│  H2 via SQL +       │     │  builds actors query │     │  into ES cluster         │
│  Groovy properties  │     │  via Groovy          │     │                          │
│                     │     │  queries actors DB   │     │                          │
│  vintage 2024       │     │  joins with Groovy   │     │  infra, not part of      │
│  (Alice)            │     │  JsonOutput          │     │  pipeline deployment     │
└─────────────────────┘     └──────────────────────┘     └──────────────────────────┘
                                     │
                                     │ queries via Groovy (setBody → sql:.)
                                     ▼
                            ┌──────────────────┐
                            │   H2 actors DB   │
                            │  (pre-existing)   │
                            └──────────────────┘
```

The `actors-source.kamelet.yaml` exists as a standalone artifact with a distinct style (newer, HikariCP-based) — it is not directly wired into this Pipe, but serves as a reusable definition of the actors database pattern from a different engineering vintage.

## Data Model

The movies database has a single `movies` table:

```sql
CREATE TABLE movies (
  id VARCHAR(10) PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  release_year INTEGER NOT NULL,
  genre VARCHAR(100)
);

INSERT INTO movies (id, title, release_year, genre) VALUES
  ('tt0111161', 'The Shawshank Redemption', 1994, 'Drama'),
  ('tt0068646', 'The Godfather', 1972, 'Crime'),
  ...
  (50 rows total)
```

The actors database has a single `actors` table with a composite primary key:

```sql
CREATE TABLE actors (
  id INTEGER NOT NULL,
  name VARCHAR(200) NOT NULL,
  character_name VARCHAR(200),
  movie_id VARCHAR(10) NOT NULL,
  PRIMARY KEY (id, movie_id)
);

INSERT INTO actors (id, name, character_name, movie_id) VALUES
  (1, 'Tim Robbins', 'Andy Dufresne', 'tt0111161'),
  (2, 'Morgan Freeman', 'Ellis Boyd "Red" Redding', 'tt0111161'),
  ...
  (125 rows total, ~2-4 actors per movie)
```

## The Kamelets

The pipeline comprises three Kamelets plus a standalone reference Kamelet. Each was (fictionally) written by a different engineer at a different time, and the differences in style are intentional.

### 1. movies-source — Alice, 2024

The oldest Kamelet in the set. It uses a bare `JdbcDataSource` from H2 itself — no connection pool, no frills. Groovy is used to extract column values into exchange properties.

```yaml
# Alice's Kamelet — 2024
# Simple movies database poller
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: movies-source
  labels:
    camel.apache.org/kamelet.type: "source"
spec:
  definition:
    title: "Movies Source"
    description: Polls movies from an H2 database
    required:
      - url
    properties:
      period:
        type: integer
        default: 60000
      url:
        type: string
        example: jdbc:h2:tcp://h2-movies:9092/movies
      user:
        type: string
        default: sa
      pw:
        type: string
        default: ""
        format: password
  dependencies:
    - "camel:core"
    - "camel:sql"
    - "camel:groovy"
    - "mvn:com.h2database:h2:2.2.224"
  template:
    beans:
      - name: ds
        type: "#class:org.h2.jdbcx.JdbcDataSource"
        properties:
          url: "{{url}}"
          user: "{{user}}"
          password: "{{pw}}"
    from:
      uri: "sql:SELECT id, title, release_year, genre FROM movies ORDER BY title"
      parameters:
        dataSource: "#bean:ds"
        delay: "{{period}}"
      steps:
        - setProperty:
            name: movieId
            groovy: "body['ID']"
        - setProperty:
            name: movieTitle
            groovy: "body['TITLE']"
        - setProperty:
            name: movieYear
            groovy: "body['RELEASE_YEAR']"
        - setProperty:
            name: movieGenre
            groovy: "body['GENRE']"
        - to: kamelet:sink
```

Notice the short property names (`url`, `pw`, `ds`), minimal annotations, and the absence of an icon. This is a Kamelet that gets the job done without ceremony — vintage 2024.

### 2. actors-source — Bob, 2026

A newer, production-oriented Kamelet written a year and a half later. It uses **HikariCP** for connection pooling, has full metadata annotations with an icon, and uses descriptive camelCase property names.

```yaml
# Bob's Kamelet — 2026
# Production-grade actors database poller
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: actors-source
  labels:
    camel.apache.org/kamelet.type: "source"
  annotations:
    camel.apache.org/provider: "Apache Software Foundation"
    camel.apache.org/kamelet.group: "Database"
    camel.apache.org/kamelet.namespace: "Database"
    camel.apache.org/kamelet.icon: >-
      data:image/svg+xml;base64,...
spec:
  definition:
    title: "Actors Source"
    description: |-
      Polls the actors database and emits one exchange per actor row.
      Designed to work alongside movies-source for join-based pipelines.
    required:
      - actorsDatabaseUrl
    type: object
    properties:
      pollPeriod:
        title: "Poll Period"
        description: "Delay between polls in milliseconds"
        type: integer
        default: 60000
      actorsDatabaseUrl:
        title: "Actors Database JDBC URL"
        description: "Full JDBC URL for the actors H2 database"
        type: string
        example: "jdbc:h2:tcp://h2-actors:9092/actors"
      actorsDatabaseUser:
        title: "Actors Database User"
        description: "Login user for the actors database"
        type: string
        default: sa
      actorsDatabasePassword:
        title: "Actors Database Password"
        description: "Password for the actors database user"
        type: string
        default: ""
        format: password
  dependencies:
    - "camel:core"
    - "camel:sql"
    - "camel:groovy"
    - "camel:jackson"
    - "mvn:com.h2database:h2:2.2.224"
    - "mvn:com.zaxxer:HikariCP:6.2.1"
  template:
    beans:
      - name: actorsPool
        type: "#class:com.zaxxer.hikari.HikariDataSource"
        properties:
          jdbcUrl: "{{actorsDatabaseUrl}}"
          username: "{{actorsDatabaseUser}}"
          password: "{{actorsDatabasePassword}}"
          driverClassName: "org.h2.Driver"
          maximumPoolSize: 5
          idleTimeout: 30000
          connectionTimeout: 5000
    from:
      uri: "sql:SELECT id, name, character_name, movie_id FROM actors ORDER BY movie_id, id"
      parameters:
        dataSource: "#bean:actorsPool"
        delay: "{{pollPeriod}}"
      steps:
        - setProperty:
            name: actorId
            groovy: "body['ID']"
        - setProperty:
            name: actorName
            groovy: "body['NAME']"
        - setProperty:
            name: actorCharacter
            groovy: "body['CHARACTER_NAME']"
        - setProperty:
            name: actorMovieId
            groovy: "body['MOVIE_ID']"
        - marshal:
            json:
              library: Jackson
        - to: kamelet:sink
```

The contrast with Alice's Kamelet is deliberate: where Alice used `ds`, Bob uses `actorsPool`; where Alice used `url`/`pw`, Bob spells out `actorsDatabaseUrl`/`actorsDatabasePassword`; where Alice had no connection pool, Bob tunes `maximumPoolSize`, `idleTimeout`, and `connectionTimeout`.

This Kamelet is not directly wired into the pipeline Pipe — it exists as a standalone reusable component, showing the actors database pattern from a different era.

### 3. groovy-join — Charlie, 2026

The heart of the pipeline. This is a **processor Kamelet** (type `sink`) that receives movie data from `movies-source`, queries the actors database, and joins them — all powered by **Groovy**.

```yaml
# Charlie's Groovy join processor — 2026
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: groovy-join
  labels:
    camel.apache.org/kamelet.type: "sink"
  annotations:
    camel.apache.org/provider: "Apache Software Foundation"
    camel.apache.org/kamelet.group: "Processing"
    camel.apache.org/kamelet.namespace: "Transform"
spec:
  definition:
    title: "Groovy Movie-Actor Joiner"
    description: |-
      Takes movie data from exchange properties, queries the actors
      database for matching cast members, and produces a joined JSON
      document — all powered by Groovy.
    required:
      - actorsUrl
    properties:
      actorsUrl:
        title: Actors Database URL
        description: JDBC URL for the actors H2 database
        type: string
        example: jdbc:h2:tcp://h2-actors:9092/actors
      actorsUser:
        title: Actors DB User
        type: string
        default: sa
      actorsPassword:
        title: Actors DB Password
        type: string
        default: ""
        format: password
  dependencies:
    - "camel:core"
    - "camel:sql"
    - "camel:groovy"
    - "mvn:com.h2database:h2:2.2.224"
    - "mvn:org.apache.commons:commons-dbcp2:2.14.0"
  template:
    beans:
      - name: actorsDb
        type: "#class:org.apache.commons.dbcp2.BasicDataSource"
        properties:
          url: "{{actorsUrl}}"
          username: "{{actorsUser}}"
          password: "{{actorsPassword}}"
          driverClassName: "org.h2.Driver"
          initialSize: 2
          maxTotal: 10
    from:
      uri: kamelet:source
      steps:
        - setBody:
            groovy: |
              "SELECT id, name, character_name FROM actors WHERE movie_id = '" +
                exchange.getProperty('movieId') + "'"
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
            name: indexId
            groovy: "exchange.getProperty('movieId')"
        - to: kamelet:sink
```

This Kamelet does three things with Groovy:

1. **Builds the actors SQL query** — `setBody` with a Groovy expression that interpolates `movieId` from the exchange property
2. **Forwards the query to the actors database** — `sql:.` with `useMessageBodyForSql: true`
3. **Constructs the joined JSON** — `setBody` with `groovy.json.JsonOutput.toJson()` that builds a proper JSON document with the actors array embedded

No Simple expressions. No string-concatenated JSON. Just Groovy code building Groovy data structures and serialising them with the standard library.

Before forwarding the joined document, the Kamelet sets the `indexId` header to the movie's ID. This tells the Elasticsearch sink to upsert — update the document if it already exists, create it if it does not. Without this header, every poll cycle would create duplicate documents. With it, the pipeline is **idempotent**: running it once or a hundred times produces the same set of 50 ES documents.

### 4. elasticsearch-index-sink — pre-existing infrastructure

The Elasticsearch sink Kamelet is part of the cluster's pre-existing infrastructure. It is deployed before the pipeline and shared across integrations. The cleaned version (with the empty-step bug removed from the Camel K 2.10.1 bundled Kamelet) is stored locally for reproducibility, but conceptually it belongs to the infrastructure layer — not to this pipeline.

## The Pipe

A `Pipe` binds the three Kamelets together and provides configuration values. It has multiple steps: `movies-source` feeds into `groovy-join`, which feeds into `elasticsearch-index-sink`.

```yaml
apiVersion: camel.apache.org/v1
kind: Pipe
metadata:
  name: movies-actors-to-es
  annotations:
    camel.apache.org/description: >-
      Binds movies-source (polls H2 movies DB) through groovy-join
      (queries actors per movie, joins via Groovy) into the
      elasticsearch-index-sink.  Elasticsearch is pre-existing
      infrastructure — not created by this Pipe.
spec:
  source:
    ref:
      kind: Kamelet
      apiVersion: camel.apache.org/v1
      name: movies-source
    properties:
      period: "30000"
      url: "jdbc:h2:tcp://h2-movies:9092/movies"
      user: "sa"
      pw: ""
  steps:
    - ref:
        kind: Kamelet
        apiVersion: camel.apache.org/v1
        name: groovy-join
      properties:
        actorsUrl: "jdbc:h2:tcp://h2-actors:9092/actors"
        actorsUser: "sa"
        actorsPassword: ""
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

Note how the Pipe uses the `steps` array to insert the `groovy-join` processor between the source and the sink. Each Kamelet receives only the properties it needs — `movies-source` gets the movies database URL, `groovy-join` gets the actors database URL, and the sink gets the Elasticsearch connection details.

Elasticsearch is not configured here — it is referenced as an existing service at `elasticsearch:9200`. The infrastructure team manages the ES cluster; this pipeline merely indexes into it.

## Running the Pipeline

### Deploy to Kubernetes

The `setup.sh` script automates the full deployment on a minikube cluster:

```bash
# From the project root
cd _code/camel-k-movies-actors
./setup.sh
```

This script:

1. Starts minikube with the registry addon
2. Installs the Camel K operator (if not already present)
3. Configures the IntegrationPlatform registry address
4. Deploys pre-existing infrastructure (Elasticsearch cluster + ES sink Kamelet)
5. Deploys the H2 movies and actors databases with seed data
6. Applies the pipeline Kamelets (`movies-source`, `groovy-join`)
7. Applies the Pipe (`movies-actors-to-es`)

### Check the pipeline status

```bash
# List all Kamelets in the namespace
kubectl get kamelet -n default

# Check the Pipe status
kubectl get pipe -n default

# Check the Integration status
kubectl get integration -n default -o wide

# View pod logs for the running integration
kubectl logs -l camel.apache.org/integration=movies-actors-to-es -n default --tail=50
```

When the Pipe is ready, its status phase changes to `Ready` and a new integration pod starts running.

### Verify Elasticsearch data

```bash
# List ES indices
kubectl exec deploy/elasticsearch -n default -- curl -s http://localhost:9200/_cat/indices?v

# Count documents in the joined index
kubectl exec deploy/elasticsearch -n default -- curl -s 'http://localhost:9200/movies-actors-joined/_count' | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', 'N/A'))"

# View sample documents
kubectl exec deploy/elasticsearch -n default -- curl -s 'http://localhost:9200/movies-actors-joined/_search?pretty&size=2'
```

Expect 50 documents — one per movie — each with an embedded `actors` array.

### Re-run the pipeline

Because the pipeline sets the `indexId` header to the movie ID, Elasticsearch upserts documents instead of creating duplicates. You can safely re-run by deleting the index and waiting for the next poll cycle:

```bash
# Delete the index (clears all joined documents)
kubectl exec deploy/elasticsearch -n default -- curl -s -X DELETE 'http://localhost:9200/movies-actors-joined'

# The integration will re-create all 50 documents on the next poll (within 30 seconds)
```

To restart the integration itself:

```bash
kubectl delete integration movies-actors-to-es -n default
```

The Pipe will recreate the integration automatically.

### Debug common issues

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| No documents in ES | Poll period not yet elapsed | Wait 30 seconds, check integration logs |
| Integration pod stuck in `Building` | Registry address misconfigured | Check `IntegrationPlatform` registry address |
| `NoSuchBeanException` | Bean suffixing in dynamic `toD` URIs | Use `sql:.` with `useMessageBodyForSql: true` |
| Pipe stays in `Phase: None` | Kamelet type mismatch | Verify `groovy-join` uses `type: sink` |

### Run locally without Kubernetes

For local development, use the Docker Compose setup and Camel JBang:

```bash
cd _code/camel-k-movies-actors

# Start H2 databases and Elasticsearch
docker compose up -d

# Run the pipeline locally via Camel JBang
jbang camel@apache/camel run \
  kamelets/movies-source.kamelet.yaml \
  kamelets/groovy-join.kamelet.yaml \
  kamelets/elasticsearch-index-sink.kamelet.yaml \
  pipes/movies-actors-pipe.yaml
```

This runs the same Kamelets and Pipe configuration outside Kubernetes, which is useful for fast iteration. The `local/movies-actors-route.yaml` file provides an equivalent standalone route that predates the multi-Kamelet architecture.

## Operational Behavior

### How the pipeline reacts to database changes

The pipeline polls the movies database every 30 seconds. It does **not** redeploy when data changes — the Integration pod runs continuously and picks up new data on the next poll cycle.

| Database change | Automatic? | When | How |
|----------------|-----------|------|-----|
| **Insert** new movie | Yes | Next poll (≤30s) | SQL query returns the new row, pipeline indexes it with its actors |
| **Update** movie title/genre | Yes | Next poll (≤30s) | New value in SQL result, ES upsert via `indexId` replaces the document |
| **Insert/update** actors | Yes | Next poll (≤30s) | Actors are re-queried per movie, the joined document is re-built and upserted |
| **Delete** movie or actors | **No** | Never | The SQL query skips deleted rows, but old ES documents are **never removed** |

The `indexId` header makes inserts and updates safe — Elasticsearch upserts by document ID, so the same 50 documents are updated in-place every cycle. This also means you never accumulate duplicates, even if the integration restarts or you re-deploy the Pipe.

### The stale-delete problem

The one gap is deletions. If a movie is removed from the `movies` table, the pipeline simply stops seeing it in the `SELECT` results. The corresponding ES document stays in the index forever — nothing tells the pipeline to delete it.

This is a fundamental limitation of timer-based SQL polling. The pipeline only knows what the database returns on each query. It has no way to detect that something is *missing*.

Solutions:

1. **Soft-delete column** — Add a `deleted` boolean to the movies table and filter `WHERE deleted = false`. The document still stays in ES, but at least the pipeline stops refreshing it. A separate cleanup job can purge stale ES documents after a grace period.

2. **Full re-index on schedule** — Delete the ES index nightly and let the next poll rebuild everything from scratch. The `indexId` header ensures the same 50 IDs are recreated.

3. **CDC (Change Data Capture)** — Instead of polling, listen to the database's change stream for insert/update/delete events. Debezium reads PostgreSQL's logical replication slot (`pgoutput` plugin) and emits an event for every row change, including deletions. No polling, no stale documents, sub-second latency.

   H2 does **not** support this — H2 has no WAL, no logical replication, no binlog. Real CDC requires PostgreSQL or MySQL. The follow-up post will replace H2 with PostgreSQL and use the Camel K `debezium-postgresql-source` Kamelet to stream changes through a Groovy processor that handles `create`/`update`/`delete` operations natively.

### Why not redeploy?

You never need to redeploy a Kamelet or Pipe because data changed. Kamelets are route templates, not snapshots. The Integration pod runs continuously and reacts to data at runtime. You only redeploy if you change the *logic* — a different SQL query, a new join strategy, a different target index.

### When polling is enough

Timer-based SQL polling works well when:

- Latency of 30–60 seconds is acceptable
- Deletions are rare or handled by a separate process
- The dataset is small enough to re-read on every cycle (50 movies is trivially small)
- You want a simple architecture with no message broker dependency

### When you need CDC

Change Data Capture becomes necessary when:

- You need sub-second latency (deletions reflected immediately)
- The dataset is too large to re-read on every poll (millions of rows)
- You need an audit trail of all changes
- The database is shared and you cannot add soft-delete columns

**That is the topic of the next post.** PostgreSQL, Debezium, and a Groovy-powered CDC processor that handles deletes cleanly. No polling, no stale documents.

## The Debugging Journey

This demo took several iterations to get right. Here are the bugs we encountered and how we fixed them.

### 1. Empty Step in the Bundled Kamelet

The `elasticsearch-index-sink` Kamelet that ships with Camel K 2.10.1 has an empty step `- {}` in its template that causes a parse error in the operator's YAML inspector (`pkg/util/source/inspector_yaml.go`). The fix is to create a clean copy in a `kamelets/` directory and apply it to the integration namespace.

**The error:**
```
unable to parse step: map[]
```

**The fix:** Copy the Kamelet YAML from the `camel-k` namespace, remove the empty step line, and apply the clean copy to the `default` namespace.

### 2. Registry Port Mismatch

The minikube registry addon exposes a service on port 80 that forwards to the container port 5000. The `IntegrationPlatform` had the registry address configured as `host:5000` instead of `host:80`.

**The error:** Builds timed out trying to push images.

**The fix:** Patch the IntegrationPlatform to use port 80:
```yaml
status:
  integrationKit:
    configuration:
      - type: "runtime"
        value: "quarkus.container-image.registry=10.103.150.14:80"
```

### 3. Pipeline Steps Require Processor Kamelets

When a Pipe has multiple steps, each intermediate Kamelet must be of type `sink` — because it receives data from the previous step via `kamelet:source`. A `source`-type Kamelet expects to be the initiator of the route, not a receiver.

**The error:** The `groovy-join` Kamelet was initially typed as `source`, causing the Pipe to fail wiring the steps together.

**The fix:** Set `camel.apache.org/kamelet.type: "sink"` on the `groovy-join` Kamelet. This tells Camel K that the Kamelet expects to receive data and forward it, making it suitable as an intermediate Pipe step.

### 4. Bean Registration and Groovy in Kamelet Templates

When beans are defined in a Kamelet template's `beans` section, the Camel K runtime registers them in the bean registry. However, using `toD` (dynamic `to`) with bean references in the URI string causes the Kamelet component to suffix the bean name (e.g., `actorsDb` becomes `actorsDb-2`), which then fails to resolve.

**The error:**
```
NoSuchBeanException: No bean could be found in the registry for: actorsDb-2
```

**The fix:** Use the standard `sql:` scheme with a static URI (`sql:.`) and set `useMessageBodyForSql: true`. Pass the SQL query (built with Groovy) as the message body.

### 5. Groovy Expressions vs Simple Expressions

The original version used Simple expressions (`${exchangeProperty.movieId}`) to build the SQL query. These were evaluated at endpoint creation time — not per exchange — resulting in zero rows returned.

With Groovy, the expression is evaluated **per exchange** because it is a `setBody` step that runs at exchange processing time:

```yaml
- setBody:
    groovy: |
      "SELECT id, name, character_name FROM actors WHERE movie_id = '" +
        exchange.getProperty('movieId') + "'"
```

This is a key advantage of using a general-purpose scripting language over Camel's Simple language for dynamic query construction.

## Verification

After the integration is running and a poll cycle completes, Elasticsearch contains 50 documents — one per movie — each with its actors embedded:

```json
{
  "movieId": "tt0111161",
  "title": "The Shawshank Redemption",
  "year": 1994,
  "genre": "Drama",
  "actors": [
    {
      "ID": 1,
      "NAME": "Tim Robbins",
      "CHARACTER_NAME": "Andy Dufresne"
    },
    {
      "ID": 2,
      "NAME": "Morgan Freeman",
      "CHARACTER_NAME": "Ellis Boyd \"Red\" Redding"
    }
  ]
}
```

Note that the actors array is built natively by Groovy's `JsonOutput.toJson()` — no string interpolation, no manual JSON construction.

Re-run the verification as many times as you like. The `indexId` header ensures Elasticsearch upserts, so you always see exactly 50 documents — never duplicates.

## Key Takeaways

1. **Pipe steps require `sink`-type Kamelets.** Intermediate Kamelets in a multi-step Pipe must be labelled as type `sink` because they receive data from the previous step via `kamelet:source`.

2. **Use Groovy for dynamic SQL queries.** The Camel SQL component evaluates Simple expressions in endpoint URIs at creation time. Groovy expressions in `setBody` steps are evaluated per exchange — exactly what you need for dynamic query construction.

3. **Use `groovy.json.JsonOutput` to build JSON documents.** Instead of string concatenation or multiple `marshal` steps, use Groovy's built-in `JsonOutput.toJson()` with native data structures (maps, lists). The result is cleaner, type-safe, and composable.

4. **Style Kamelets for the era they represent.** Kamelets are code — they should look like they belong to their time. Older Kamelets can use simpler patterns (JdbcDataSource, short property names), while newer ones can adopt modern practices (HikariCP, full annotations, descriptive naming). This makes the evolution of the codebase visible.

5. **Treat infrastructure Kamelets as pre-existing.** The Elasticsearch sink Kamelet is not part of the pipeline — it is deployed once and shared. The Pipe references it but does not own it. This separation of concerns reflects real-world team boundaries.

6. **Polls propagate inserts and updates, but not deletes.** The timer-based SQL query automatically picks up new and changed rows within 30 seconds. Deleted rows leave stale ES documents behind. If your use case requires immediate delete propagation, CDC is the right tool — see the follow-up post.

7. **Never redeploy for data changes.** The Integration pod runs continuously. Data changes flow through on the next poll cycle. Redeploy only when the *pipeline logic* changes — a different query, a new join, a different sink.
