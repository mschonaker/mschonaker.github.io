#!/usr/bin/env bash
set -euo pipefail

echo "=== CDC Propagation Test (create / update / delete) ==="
echo ""

echo "1) Insert a new movie (id=51)..."
docker exec pg-movies psql -U postgres -d movies_db \
  -c "INSERT INTO movies (id, imdb_id, title, release_year, genre) VALUES (51, 'tt9999999', 'Test Movie', 2026, 'Sci-Fi');"
sleep 3
curl -s "http://localhost:9200/movies-actors-joined/_doc/51" | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('_source',{}); print('   ES doc found:', d.get('found'), '->', s.get('title'))"
echo ""

echo "2) Update the movie title..."
docker exec pg-movies psql -U postgres -d movies_db \
  -c "UPDATE movies SET title='Test Movie Updated' WHERE id=51;"
sleep 3
curl -s "http://localhost:9200/movies-actors-joined/_doc/51" | python3 -c "import sys,json; d=json.load(sys.stdin); print('   ES title:', d.get('_source',{}).get('title'))"
echo ""

echo "3) Delete the movie..."
docker exec pg-movies psql -U postgres -d movies_db \
  -c "DELETE FROM movies WHERE id=51;"
sleep 3
curl -s "http://localhost:9200/movies-actors-joined/_doc/51" | python3 -c "import sys,json; print('   ES doc found after delete:', json.load(sys.stdin).get('found'))"
echo ""

echo "4) Final document count (should be 50):"
curl -s "http://localhost:9200/movies-actors-joined/_count" | python3 -c "import sys,json; print('   Count:', json.load(sys.stdin).get('count'))"
echo ""

echo "=== Test complete ==="
