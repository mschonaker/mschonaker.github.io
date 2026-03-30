# Getting Started with ES|QL in Docker

ES|QL (Elasticsearch Query Language) is a pipe-based language that lets you query and transform data in Elasticsearch. Here's a minimalistic example with students and courses.

## Start Elasticsearch

```bash
docker run -d \
  -p 9200:9200 \
  -e discovery.type=single-node \
  -e xpack.security.enabled=false \
  -e ES_JAVA_OPTS=-Xms512m -Xmx512m \
  docker.elastic.co/elasticsearch/elasticsearch:9.3.2
```

## Create Index and Ingest Data

```bash
curl -X POST "localhost:9200/_bulk?pretty" \
  -H "Content-Type: application/x-ndjson" \
  -d '{"index": {"_index": "courses"}}
{"course_id": "CS101", "title": "Intro to Programming", "credits": 3}
{"index": {"_index": "courses"}}
{"course_id": "CS201", "title": "Data Structures", "credits": 4}
{"index": {"_index": "students"}}
{"student_id": "S001", "name": "Alice", "course_id": "CS101", "grade": "A"}
{"index": {"_index": "students"}}
{"student_id": "S002", "name": "Bob", "course_id": "CS101", "grade": "B"}
{"index": {"_index": "students"}}
{"student_id": "S003", "name": "Charlie", "course_id": "CS201", "grade": "A"}
'
```

## Query with ES|QL

Join students with courses:

```bash
curl -X POST "localhost:9200/_query?pretty" \
  -H "Content-Type: application/json" \
  -d '{
    "query": """
      FROM students
      | JOIN courses ON course_id == course_id
      | KEEP student_id, name, title, grade
    """
  }'
```

Result:

```json
{
  "columns": [
    {"name": "student_id", "type": "keyword"},
    {"name": "name", "type": "text"},
    {"name": "title", "type": "text"},
    {"name": "grade", "type": "keyword"}
  ],
  "values": [
    ["S001", "Alice", "Intro to Programming", "A"],
    ["S002", "Bob", "Intro to Programming", "B"],
    ["S003", "Charlie", "Data Structures", "A"]
  ]
}
```

## Further Reading

- [ES|QL Reference](https://www.elastic.co/docs/reference/query-languages/esql)
- [ES|QL Commands](https://www.elastic.co/docs/reference/query-languages/esql/esql-commands)
- [ES|QL Functions and Operators](https://www.elastic.co/docs/reference/query-languages/esql/esql-functions-operators)

