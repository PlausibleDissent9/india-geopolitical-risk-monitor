#!/usr/bin/env bash
# Stage a daily run without publishing a half-updated derived-data tree.
#
# The acquisition store and byte-exact response evidence are worth banking
# even when a downstream gate fails. Derived docs are publishable only when
# the complete required job is successful. On failure, stash those derived
# worktree changes so publish_push.sh can safely rebase and push the raw-only
# evidence commit; the stash is recoverable in a persistent runner.
set -euo pipefail

JOB_STATUS="${1:?usage: stage_daily_outputs.sh <success|failure|cancelled>}"

git add data/raw || true

if [ "$JOB_STATUS" = "success" ]; then
  git add docs notes-inbox .trigger || true
  echo "[daily-stage] complete job: raw inputs and derived outputs staged"
  exit 0
fi

echo "[daily-stage] $JOB_STATUS job: refusing every derived docs change"
git reset -q -- docs notes-inbox .trigger 2>/dev/null || true
git stash push --include-untracked \
  -m "failed daily derived outputs (${GITHUB_RUN_ID:-local})" \
  -- docs notes-inbox .trigger >/dev/null

# Prove the boundary instead of trusting the pathspec. A failed job may stage
# data/raw only; any other staged path is an atomic-publication violation.
unexpected="$(git diff --cached --name-only | grep -Ev '^data/raw/' || true)"
if [ -n "$unexpected" ]; then
  echo "[daily-stage] refusing non-raw staged paths after failed job:" >&2
  printf '%s\n' "$unexpected" >&2
  exit 1
fi
echo "[daily-stage] failed job: raw evidence only staged"
