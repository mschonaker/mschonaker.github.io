#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting Bento + Conduit CDC Pipeline ==="
echo ""

# --------------------------------------------------
# Step 1: Clean previous run state
# --------------------------------------------------
echo "=== Step 1: Clean previous run state ==="
rm -f bridge/cdc-events.jsonl
rm -rf conduit.db
curl -s -X DELETE "http://localhost:9200/movies-actors-joined" >/dev/null 2>&1 || true
echo "Bridge file, conduit state, and ES index reset."
echo ""

# --------------------------------------------------
# Step 2: Start Conduit (CDC capture)
# --------------------------------------------------
echo "=== Step 2: Start Conduit ==="
nohup conduit run --config.path ./conduit.yaml > /tmp/conduit.log 2>&1 &
CONDUIT_PID=$!
echo "Conduit started (pid $CONDUIT_PID). Waiting for snapshot..."
sleep 8
if [ ! -s bridge/cdc-events.jsonl ]; then
  echo "ERROR: bridge file is empty. Check /tmp/conduit.log"
  tail -20 /tmp/conduit.log
  exit 1
fi
EVENTS=$(wc -l < bridge/cdc-events.jsonl)
echo "Snapshot wrote $EVENTS events to bridge/cdc-events.jsonl."
echo ""

# --------------------------------------------------
# Step 3: Start Bento (processing)
# --------------------------------------------------
echo "=== Step 3: Start Bento ==="
nohup bento -c configs/bento.yaml > /tmp/bento.log 2>&1 &
BENTO_PID=$!
echo "Bento started (pid $BENTO_PID). Waiting for indexing..."
sleep 8
COUNT=$(curl -s "http://localhost:9200/movies-actors-joined/_count" | python3 -c "import sys,json; print(json.load(sys.stdin).get('count','0'))" 2>/dev/null || echo 0)
echo "Indexed documents: $COUNT"
echo ""

echo "=== Pipeline running! ==="
echo "  Conduit log: /tmp/conduit.log"
echo "  Bento log:   /tmp/bento.log"
echo "  Bridge file: bridge/cdc-events.jsonl"
echo ""
echo "To verify the pipeline:"
echo "  ./test.sh"
echo ""
echo "To stop the pipeline:"
echo "  kill $CONDUIT_PID $BENTO_PID"
echo ""
