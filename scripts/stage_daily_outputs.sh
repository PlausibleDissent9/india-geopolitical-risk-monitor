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
PYTHON_BIN="${PYTHON:-python}"

if [ "$JOB_STATUS" = "success" ]; then
  git add data/raw || true
  git add docs notes-inbox .trigger || true
  echo "[daily-stage] complete job: raw inputs and derived outputs staged"
  exit 0
fi

echo "[daily-stage] $JOB_STATUS job: refusing every derived docs change"

# A killed acquisition can leave a subset of the five-file final candidate on
# disk even though the Python exception rollback never ran. A failed daily may
# bank other raw acquisition evidence, but these exact target-value paths are
# admissible only when the frozen-parent promotion verifier closes the whole
# bundle. Otherwise restore tracked bytes and drop untracked candidate bytes
# before the broad data/raw staging boundary below.
TARGET="$($PYTHON_BIN -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat())')"
FINAL_VALUE_PATHS=(
  data/raw/gdelt_volume.csv
  data/raw/provenance.csv
  "data/raw/ngram_days/$TARGET.json"
  "data/raw/final_publication_receipts/$TARGET.json"
)
BUNDLE_PATHS=("${FINAL_VALUE_PATHS[@]}" data/raw/final_publication_status.json)
bundle_changes="$(git status --porcelain -- "${BUNDLE_PATHS[@]}" || true)"
if [ -n "$bundle_changes" ]; then
  if "$PYTHON_BIN" -m src.final_publication \
      --check-promotion-receipt "$TARGET" --trusted-parent HEAD >/dev/null; then
    echo "[daily-stage] interrupted job retained a fully verified target bundle"
  else
    echo "[daily-stage] dropping incomplete/untrusted final target bundle"
    for path in "${BUNDLE_PATHS[@]}"; do
      git reset -q -- "$path" 2>/dev/null || true
      if git cat-file -e "HEAD:$path" 2>/dev/null; then
        git restore --source=HEAD --worktree -- "$path"
      else
        rm -f -- "$path"
      fi
    done
  fi
fi

git add data/raw || true
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
