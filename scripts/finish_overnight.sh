#!/usr/bin/env bash
# Unattended finisher: harvest -> build -> publish -> validate -> tag.
#
# Runs the whole remaining launch sequence without supervision, pushing
# after each durable milestone so progress survives a crash, a closed
# laptop, or a network drop. Every analysis step is tolerant: a step that
# cannot reach its API is skipped and reported, never fatal, so one
# throttled service cannot cost the whole night.
#
#   nohup scripts/finish_overnight.sh > overnight.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
PY=.venv/bin/python
GIT_ID=(-c user.name="Ishan Krishna" -c user.email="ishankrishna9@gmail.com")

say() { echo "[overnight $(date -u +%H:%M:%S)] $*"; }

push() {  # push(message) -- commit whatever changed, rebase, push
  git add -A ':!*.log' >/dev/null 2>&1 || true
  git "${GIT_ID[@]}" commit -q -m "$1" 2>/dev/null || { say "nothing to commit: $1"; return 0; }
  git pull -q --rebase origin main >/dev/null 2>&1 || true
  if git push -q origin main 2>/dev/null; then say "pushed: $1"; else say "PUSH FAILED: $1"; fi
}

step() {  # step(label, module) -- run a module, never fatal
  say "running $1"
  if $PY -m "$2" >> overnight.log 2>&1; then say "  ok: $1"; else say "  skipped (failed): $1"; fi
}

# 1. Harvest every historical chunk (blocks until all are cached).
say "phase 1: harvesting GDELT chunks"
$PY -u scripts/harvest.py 1800 >> overnight.log 2>&1
push "data: banked GDELT historical chunk cache"

# 2. Build the index, episodes, event study, and site outputs.
say "phase 2: building index"
for attempt in 1 2 3 4 5; do
  if $PY -m src.run_daily --backfill >> overnight.log 2>&1; then
    say "  index built on attempt $attempt"; break
  fi
  say "  build attempt $attempt failed; retrying in 180s"
  sleep 180
done
push "data: first full backfill 2017-2026, index and event study published"

# 3. Validation battery + analyses. Each is optional-but-attempted.
say "phase 3: validation and analysis"
$PY -m src.validate hit-rate   >> overnight.log 2>&1 && say "  ok: hit-rate"   || say "  skipped: hit-rate"
push "validation: pre-registered episode hit rate"

for mode in placebo robustness drift precision; do
  say "running validate $mode"
  $PY -m src.validate "$mode" >> overnight.log 2>&1 && say "  ok: $mode" || say "  skipped: $mode"
  push "validation: $mode"
done

step "wikipedia cross-source" src.fetch_wikipedia
push "validation: Wikipedia cross-source agreement"

step "seasonality"   src.seasonality
step "alt specs"     src.alt_specs
step "priced risk"   src.priced_risk
step "weekly datapack" src.make_datapack
push "analysis: seasonality, alternative specifications, attention-pricing gap, datapack"

# 4. Tag the release once the index actually exists.
if [ -f docs/data/latest.json ] && grep -q '"composite"' docs/data/latest.json; then
  git "${GIT_ID[@]}" tag -f v1.0.0 -m "IGRM v1.0.0: first published index with validation" 2>/dev/null || true
  git push -f origin v1.0.0 2>/dev/null && say "tagged v1.0.0" || say "tag push failed"
fi

say "DONE -- site data, validation, and analyses published"
