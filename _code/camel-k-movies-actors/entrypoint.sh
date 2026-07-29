#!/bin/sh
set -e

DB="${DB_NAME:-data}"
BASE_DIR="/opt/h2-data"

mkdir -p "$BASE_DIR"

# Start H2 TCP server in background with explicit baseDir
java -cp /opt/h2.jar org.h2.tools.Server \
  -tcp -tcpAllowOthers -tcpPort 9092 \
  -web -webAllowOthers -webPort 8082 \
  -ifNotExists \
  -baseDir "$BASE_DIR" &

H2_PID=$!

# Give H2 time to start
sleep 3

# Run init SQL if provided
if [ -n "$INIT_SQL" ] && [ -f "$INIT_SQL" ]; then
  echo "Running init SQL: $INIT_SQL"
  java -cp /opt/h2.jar org.h2.tools.RunScript \
    -url "jdbc:h2:tcp://localhost:9092/$DB" \
    -user sa \
    -password "" \
    -script "$INIT_SQL"
  RC=$?
  if [ $RC -eq 0 ]; then
    echo "Init SQL completed for database: $DB"
  else
    echo "Init SQL failed with exit code $RC"
  fi
fi

# Wait for H2 process
wait $H2_PID