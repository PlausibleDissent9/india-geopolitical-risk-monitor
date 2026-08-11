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

# Pin the commit BEFORE the gate and push the pin, not HEAD. The gate
# takes ~37 minutes, and `git push origin HEAD:main` resolves HEAD at
# push time -- so a commit made while the gate ran would ship ungated
# through a green light earned by its parent. That is a verify-to-use
# gap (the admission design's A9, in our own tooling), and it nearly
# fired on 2026-08-10: a commit landed on top of a running gate and
# only a manual kill kept the pair honest. The remaining window is the
# milliseconds between this rev-parse and gate.sh's own `git archive
# HEAD`, which is not a workflow anyone has.
COMMIT="$(git rev-parse HEAD)"

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
# --publish, for the same reason publish_push.sh uses it: the `live` tests
# fetch igrm.in and assert about the payloads the site is ALREADY SERVING,
# which cannot say anything about the commit being pushed. Leaving them in
# meant a stale site refused every push, including the pushes that would
# refresh it -- and including, absurdly, the push of the fix for that
# deadlock. Everything that describes the candidate still runs: registry
# refusals, conformance diffs, ruff, mypy, the non-live suite with coverage.
# ci.yml still runs the live assertions on main, where a stale site is an
# alert rather than a lock. See scripts/gate.sh for the full reasoning.
if ! bash scripts/gate.sh --publish > "$OUT" 2>&1; then
  echo "ship: COMMITTED GATE RED -- not pushing. Failures:"
  grep -E "FAILED|error:" "$OUT" | head -10
  exit 1
fi
if [ "$(git rev-parse HEAD)" != "$COMMIT" ]; then
  echo "ship: HEAD advanced past $COMMIT while the gate ran;"
  echo "ship: pushing only the gated commit. Re-run ship.sh for the rest."
fi
git push origin "$COMMIT":main
echo "ship: pushed $(git rev-parse --short "$COMMIT") through a green gate"
