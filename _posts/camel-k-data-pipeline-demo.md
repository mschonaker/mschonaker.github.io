---
id: camel-k-pipeline
title: Building an ETL Data Pipeline with Apache Camel K
summary: A practical end-to-end demonstration of Apache Camel K on Kubernetes reading from two H2 databases, joining the data in-flight, and indexing the result into Elasticsearch — including the debugging journey and lessons learned.
date: 2026-07-28
image: /images/camel-k-data-pipeline-header.png
---

# Building an ETL Data Pipeline with Apache Camel K

[Camel K](https://camel.apache.org/camel-k/2.10.x/index.html) is a lightweight integration framework built for Kubernetes. It runs [Apache Camel](https://camel.apache.org/) integrations natively on Kubernetes with minimal configuration — define a `Kamelet` or `Pipe`, apply it, and Camel K handles the rest.

This post walks through an end-to-end ETL pipeline built with Camel K:

- **Extract** movies from one H2 database and actors from another
- **Transform** by joining movies with their actors in-flight
- **Load** the joined JSON documents into Elasticsearch

The result: every movie document in Elasticsearch includes its cast of actors as an embedded array.

## Architecture

Two separate H2 TCP server instances (packaged in custom Docker images) run alongside Elasticsearch in the `default` namespace. A custom `movies-actors-source` Kamelet polls movies every 30 seconds, looks up the matching actors by movie ID, constructs a joined JSON document, and sends it to the `elasticsearch-index-sink` Kamelet.

```
h2-movies:9092 ──► movies-actors-source ──► elasticsearch-index-sink ──► elasticsearch:9200
h2-actors:9092 ──►                                        ▲
                     polls movies, queries actors          │
                     per movie row, joins as JSON          │
                                                           │
                     Pipe binds source → sink,             │
                     configures connection URLs            │
```

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

## The Custom Kamelet

The heart of the pipeline is the custom `movies-actors-source` Kamelet. It defines two `BasicDataSource` beans (one per database), polls the movies table via the Camel SQL component, and for each movie row, dynamically queries the actors table.

```yaml
apiVersion: camel.apache.org/v1
kind: Kamelet
metadata:
  name: movies-actors-source
  labels:
    camel.apache.org/kamelet.type: "source"
spec:
  definition:
    required:
      - moviesUrl
      - actorsUrl
    properties:
      period:
        type: integer
        default: 60000
      moviesUrl:
        type: string
      moviesUser:
        type: string
        default: sa
      moviesPassword:
        type: string
        default: ""
      actorsUrl:
        type: string
      actorsUser:
        type: string
        default: sa
      actorsPassword:
        type: string
        default: ""
  dependencies:
    - "camel:core"
    - "camel:sql"
    - "camel:jackson"
    - "camel:kamelet"
    - "mvn:com.h2database:h2:2.2.224"
    - "mvn:org.apache.commons:commons-dbcp2:2.14.0"
  template:
    beans:
      - name: moviesDb
        type: "#class:org.apache.commons.dbcp2.BasicDataSource"
        properties:
          username: "{{moviesUser}}"
          password: "{{moviesPassword}}"
          url: "{{moviesUrl}}"
          driverClassName: "org.h2.Driver"
      - name: actorsDb
        type: "#class:org.apache.commons.dbcp2.BasicDataSource"
        properties:
          username: "{{actorsUser}}"
          password: "{{actorsPassword}}"
          url: "{{actorsUrl}}"
          driverClassName: "org.h2.Driver"
    from:
      uri: "sql:SELECT id, title, release_year, genre FROM movies ORDER BY title"
      parameters:
        dataSource: "#bean:{{moviesDb}}"
        delay: "{{period}}"
      steps:
        - setProperty:
            name: movieId
            simple: "${body[ID]}"
        - setProperty:
            name: movieTitle
            simple: "${body[TITLE]}"
        - setProperty:
            name: movieYear
            simple: "${body[RELEASE_YEAR]}"
        - setProperty:
            name: movieGenre
            simple: "${body[GENRE]}"
        - setBody:
            simple: "SELECT id, name, character_name FROM actors WHERE movie_id = '${exchangeProperty.movieId}'"
        - to:
            uri: "sql:."
            parameters:
              dataSource: "#bean:{{actorsDb}}"
              outputType: SelectList
              useMessageBodyForSql: true
        - marshal:
            json:
              library: Jackson
        - setProperty:
            name: actorsJson
            simple: "${body}"
        - setBody:
            simple: |-
              {"movieId":"${exchangeProperty.movieId}","title":"${exchangeProperty.movieTitle}","year":${exchangeProperty.movieYear},"genre":"${exchangeProperty.movieGenre}","actors":${exchangeProperty.actorsJson}}
        - to: "kamelet:sink"
```

## The Pipe

A `Pipe` binds the source Kamelet to the `elasticsearch-index-sink` Kamelet and provides configuration values:

```yaml
apiVersion: camel.apache.org/v1
kind: Pipe
metadata:
  name: movies-actors-to-es
spec:
  source:
    ref:
      kind: Kamelet
      apiVersion: camel.apache.org/v1
      name: movies-actors-source
    properties:
      period: "30000"
      moviesUrl: "jdbc:h2:tcp://h2-movies:9092/movies"
      moviesUser: "sa"
      moviesPassword: ""
      actorsUrl: "jdbc:h2:tcp://h2-actors:9092/actors"
      actorsUser: "sa"
      actorsPassword: ""
      indexName: "movies-actors-joined"
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

### 3. Bean Registration in Kamelet Templates

When beans are defined in a Kamelet template's `beans` section, the Camel K runtime registers them in the bean registry. However, using `toD` (dynamic `to`) with bean references in the URI string causes the Kamelet component to suffix the bean name (e.g., `actorsDb` becomes `actorsDb-2`), which then fails to resolve.

**The error:**
```
NoSuchBeanException: No bean could be found in the registry for: actorsDb-2
```

**Why it works in `from:` but not `toD:`:** The `from:` endpoint's `parameters` section resolves bean references differently than URI string placeholders. In `parameters`, `#bean:{{moviesDb}}` is resolved correctly. In a `toD` URI like `sql:...?dataSource=%23bean:{{actorsDb}}`, the placeholder is textually replaced with the suffixed name.

**The fix:** Use the standard `sql:` scheme with a static URI and set `useMessageBodyForSql: true`. Pass the SQL query (with per-exchange expressions already evaluated) as the message body.

### 4. Dynamic SQL Queries in `to:` Endpoints

The initial approach placed the dynamic movie ID directly in the `to:` endpoint URI:

```yaml
- to:
    uri: "sql:SELECT ... WHERE movie_id = '${exchangeProperty.movieId}'"
```

This appeared to work (the integration started, data flowed to ES), but the `${exchangeProperty.movieId}` expression was evaluated at endpoint creation time (before any exchange was available), resolving to a literal string that matched zero rows.

**The fix:** Construct the SQL query as a `setBody` step (which evaluates per exchange) and use `useMessageBodyForSql: true` on the SQL endpoint:

```yaml
- setBody:
    simple: "SELECT ... WHERE movie_id = '${exchangeProperty.movieId}'"
- to:
    uri: "sql:."
    parameters:
      dataSource: "#bean:{{actorsDb}}"
      outputType: SelectList
      useMessageBodyForSql: true
```

This ensures the Simple expression is evaluated per movie row against the correct exchange context.

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

## Key Takeaways

1. **Kamelet beans must be referenced in `parameters`, not URI strings.** The Kamelet component handles bean reference resolution differently in the `parameters` section versus inline URI placeholders. Always use `#bean:{{name}}` in the `parameters` section.

2. **Dynamic queries require `useMessageBodyForSql=true`.** The Camel SQL component evaluates Simple expressions in endpoint URIs at creation time — not per exchange. To execute dynamic queries, construct the SQL in a `setBody` step and use `useMessageBodyForSql: true`.

3. **The `to:` endpoint with Simple expressions in its URI is NOT dynamic in this context.** Despite Camel documentation suggesting otherwise, `${...}` expressions in `to:` endpoint URIs are evaluated when the endpoint is first resolved, before any exchange data is available.

4. **Check bundled Kamelets for template issues.** The `elasticsearch-index-sink` Kamelet that ships with Camel K 2.10.1 has a YAML quality issue (empty step element). Copying it to the project namespace and fixing it is the safest approach.

5. **Pod logs are your best debug tool.** Adding `log:` steps to the route helped pinpoint that the actors query was returning zero rows due to the expression evaluation issue, not a database connectivity problem.
