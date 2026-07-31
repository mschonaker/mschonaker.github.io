#!/usr/bin/env bash
set -euo pipefail

echo "=== Bento + Conduit CDC Pipeline Verification ==="
echo ""

echo "Pipeline processes:"
pgrep -fl "conduit run" || echo "  conduit not running"
pgrep -fl "bento -c" || echo "  bento not running"
echo ""

echo "Elasticsearch index:"
curl -s "http://localhost:9200/_cat/indices?v" 2>/dev/null || echo "Could not reach ES"
echo ""

echo "Document count in movies-actors-joined:"
COUNT=$(curl -s "http://localhost:9200/movies-actors-joined/_count" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('count','N/A'))" 2>/dev/null || echo "N/A")
echo "Count: $COUNT"
echo ""

echo "Sample documents (first movie):"
curl -s "http://localhost:9200/movies-actors-joined/_doc/1" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); s=d.get('_source',{}); print('  title:', s.get('title'), '| actors:', len(s.get('actors',[])))" 2>/dev/null || echo "Could not query ES"
echo ""

echo "=== Verification complete ==="
echo "To test CDC propagation:"
echo "  ./test-cdc.sh"
echo ""
