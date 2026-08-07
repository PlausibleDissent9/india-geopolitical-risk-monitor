#!/usr/bin/env bash
# Push only through the committed-tree gate, with nothing to launder.
#
#   scripts/ship.sh        gate HEAD, push iff green
#
# Exists because on 2026-08-07 I pushed through a red gate TWICE in ten
# minutes by chaining `gate | tail` before `git push`: the pipe's exit
# status is the last command's, so the gate's refusal vanished. The
# repo's own daily.yml documents exactly this laundering ("pipefail is
# load-bearing") and I reproduced it by hand, twice, while quoting it.
# A habit that survives two written post-mortems in one day does not get
# fixed by a third; it gets removed from the keyboard.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
if ! bash scripts/gate.sh --committed > "$OUT" 2>&1; then
  echo "ship: COMMITTED GATE RED -- not pushing. Failures:"
  grep -E "FAILED|error:" "$OUT" | head -10
  exit 1
fi
git push origin main
echo "ship: pushed $(git rev-parse --short HEAD) through a green gate"
