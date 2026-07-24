#!/usr/bin/env bash
# Rides out GDELT's multi-minute 429 storms: run the backfill, and when a
# pass dies mid-storm, cool down and relaunch. The chunk cache in
# data/raw/gdelt_chunks makes every pass resume where the last one died,
# so persistence costs nothing but time.
set -u
cd "$(dirname "$0")/.."

MAX_PASSES=40
COOLDOWN_S=300

for i in $(seq 1 "$MAX_PASSES"); do
  echo "[supervisor] pass $i starting $(date -u +%H:%M:%S)" >> backfill.log
  if .venv/bin/python -u -m src.run_daily --backfill >> backfill.log 2>&1; then
    echo "[supervisor] backfill complete on pass $i" >> backfill.log
    exit 0
  fi
  echo "[supervisor] pass $i died; cooling down ${COOLDOWN_S}s" >> backfill.log
  sleep "$COOLDOWN_S"
done
echo "[supervisor] gave up after $MAX_PASSES passes" >> backfill.log
exit 1
