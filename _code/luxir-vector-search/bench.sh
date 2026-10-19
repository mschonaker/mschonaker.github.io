#!/usr/bin/env bash
# Index the same ten thousand products three times each way, into a fresh
# collection every time, and report the wall clock of the commit.
set -euo pipefail

BENCH_DIR=${BENCH_DIR:-/private/var/folders/r5/rm4_bkf10sdgjs1pgxzm4nhm0000gn/T/opencode/luxir-bench}
PORT=${PORT:-9410}
RUNS=${RUNS:-3}
HERE=$(cd "$(dirname "$0")" && pwd)

for run in $(seq 1 "$RUNS"); do
  for mode in lexical vector; do
    docker exec luxirbench rm -rf /data/data
    docker restart luxirbench >/dev/null
    sleep 2

    file=products.ndjson
    [ "$mode" = vector ] && file=products_v.ndjson

    start=$(python3 -c 'import time;print(time.time())')
    curl -s --max-time 600 -X POST "http://localhost:$PORT/collections/products/_update?commit=true" \
      -H 'Content-Type: application/x-ndjson' --data-binary "@$HERE/$file" >/dev/null
    end=$(python3 -c 'import time;print(time.time())')

    size=$(wc -c <"$HERE/$file" | tr -d ' ')
    python3 -c "print(f'run $run  $mode: {$end-$start:6.2f} s   ($size bytes)')"
  done
done