#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Bento + Conduit CDC Demo Setup (PostgreSQL + Elasticsearch) ==="
echo ""

# --------------------------------------------------
# Step 1: Start Elasticsearch
# --------------------------------------------------
echo "=== Step 1: Start Elasticsearch ==="
if docker ps --format '{{.Names}}' | grep -q '^es-movies$'; then
  echo "es-movies container already running."
else
  docker run -d --name es-movies \
    -p 9200:9200 \
    -e "discovery.type=single-node" \
    -e "xpack.security.enabled=false" \
    -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
    docker.elastic.co/elasticsearch/elasticsearch:8.18.0 2>/dev/null || true
  echo "es-movies container started."
fi
echo "Waiting for Elasticsearch to be healthy..."
for i in $(seq 1 30); do
  if curl -s "http://localhost:9200" >/dev/null 2>&1; then
    echo "Elasticsearch is up."
    break
  fi
  sleep 2
done
curl -s "http://localhost:9200/_cat/health?v" || echo "ES not ready yet, check later."
echo ""

# --------------------------------------------------
# Step 2: Start PostgreSQL with CDC
# --------------------------------------------------
echo "=== Step 2: Start PostgreSQL ==="
if docker ps --format '{{.Names}}' | grep -q '^pg-movies$'; then
  echo "pg-movies container already running."
else
  docker run -d --name pg-movies \
    -e POSTGRES_USER=postgres \
    -e POSTGRES_PASSWORD=postgres \
    -e POSTGRES_DB=movies_db \
    -p 5432:5432 \
    -v "$SCRIPT_DIR/data/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro" \
    postgres:16 -c wal_level=logical
  echo "pg-movies container started."
fi
echo "Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
  if docker exec pg-movies pg_isready -U postgres -d movies_db >/dev/null 2>&1; then
    echo "PostgreSQL is up."
    break
  fi
  sleep 2
done
echo ""

# --------------------------------------------------
# Step 3: Check tools
# --------------------------------------------------
echo "=== Step 3: Check tools ==="
command -v conduit >/dev/null 2>&1 && echo "conduit: $(conduit -v 2>&1 | head -1)" || echo "ERROR: conduit not found. Install with: brew install conduit"
command -v bento >/dev/null 2>&1 && echo "bento: $(bento --version 2>&1 | head -1)" || echo "ERROR: bento not found. Install with: brew install bento"
echo ""

echo "=== Setup complete! ==="
echo "To start the pipeline:"
echo "  ./run.sh"
echo ""
