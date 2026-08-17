#!/usr/bin/env bash
# Stage a daily run without publishing a half-updated derived-data tree.
#
# Other acquisition evidence may be banked when a downstream gate fails, but
# a finalized-publication candidate is one parent-bound transaction. Banking
# any part of it in a raw-only failure commit both exposes unapproved evidence
# and makes the complete bundle unpromotable on the next run.
set -euo pipefail

JOB_STATUS="${1:?usage: stage_daily_outputs.sh <success|failure|cancelled> <frozen-target>}"
TARGET="${2:?missing frozen final-publication target}"
PYTHON_BIN="${PYTHON:-python}"

if ! "$PYTHON_BIN" -c \
    'from datetime import date; import sys; value=sys.argv[1]; assert date.fromisoformat(value).isoformat() == value' \
    "$TARGET"; then
  echo "[daily-stage] invalid frozen target: $TARGET" >&2
  exit 1
fi

if [ "$JOB_STATUS" = "success" ]; then
  git add data/raw || true
  git add docs notes-inbox .trigger || true
  # The forecast question registry, named EXACTLY and not as `validation/`.
  #
  # src.forecasts runs in this lane and only this lane, and it writes
  # validation/forecast_questions.json to "ensure the NEXT Monday's
  # questions exist (commit-before-open)". Nothing staged it. Two
  # consequences, and the second is the serious one:
  #
  #   1. The unstaged file left the tree dirty, so publish_push.sh
  #      correctly refused before the rebase and the whole daily publish
  #      died -- run 32069493627, after all 48 steps had otherwise run.
  #   2. The registry has 5 questions, all for window_start 2026-08-10.
  #      That is the founder-signed launch commit and nothing since. Every
  #      Monday after it was generated inside a runner and discarded. The
  #      V11 experiment's entire warrant is that a question is COMMITTED
  #      before its window opens; a question that never reaches a commit
  #      is not pre-registered, it is just arithmetic.
  #
  # Named as one path rather than `git add validation`, deliberately.
  # validation/ also holds frozen registrations and signed records, and
  # sweeping those into an automated publish is exactly how a
  # methodology change disappears -- the hazard publish_push.sh refuses
  # to guess about. This lane writes one file there; it stages that file.
  git add validation/forecast_questions.json || true
  echo "[daily-stage] complete job: raw inputs and derived outputs staged"
  exit 0
fi

echo "[daily-stage] $JOB_STATUS job: refusing every derived docs change"

# A process kill can bypass Python's bundle rollback. On every unsuccessful
# publication, restore *all changed* final-contract paths to HEAD before the
# broad raw pathspec is staged. This deliberately drops even a fully valid
# target_ready bundle: its receipt is rooted in this HEAD and cannot survive a
# raw-only intermediate commit without becoming self-inconsistent.
FINAL_CONTRACT_PATHS=(
  data/raw/gdelt_volume.csv
  data/raw/provenance.csv
  data/raw/final_publication_status.json
  data/raw/ngram_days
  data/raw/final_publication_receipts
)

changed_contract_paths="$({
  git diff --name-only -- "${FINAL_CONTRACT_PATHS[@]}"
  git diff --cached --name-only -- "${FINAL_CONTRACT_PATHS[@]}"
  git ls-files --others --exclude-standard -- "${FINAL_CONTRACT_PATHS[@]}"
} | sort -u)"

while IFS= read -r path; do
  [ -n "$path" ] || continue
  case "$path" in
    data/raw/gdelt_volume.csv|data/raw/provenance.csv|data/raw/final_publication_status.json)
      ;;
    data/raw/ngram_days/*.json)
      day="${path##*/}"
      day="${day%.json}"
      if [ "$day" != "$TARGET" ]; then
        echo "[daily-stage] dropping non-target final cache $path (frozen target $TARGET)"
      fi
      ;;
    data/raw/final_publication_receipts/*.json)
      day="${path##*/}"
      day="${day%.json}"
      if [ "$day" != "$TARGET" ]; then
        echo "[daily-stage] dropping non-target final receipt $path (frozen target $TARGET)"
      fi
      ;;
    *)
      echo "[daily-stage] refusing unexpected final-contract path: $path" >&2
      exit 1
      ;;
  esac
  git reset -q -- "$path" 2>/dev/null || true
  if git cat-file -e "HEAD:$path" 2>/dev/null; then
    git restore --source=HEAD --worktree -- "$path"
  else
    rm -f -- "$path"
  fi
done <<EOF
$changed_contract_paths
EOF

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
forbidden="$(git diff --cached --name-only | grep -E \
  '^(data/raw/gdelt_volume.csv|data/raw/provenance.csv|data/raw/final_publication_status.json|data/raw/ngram_days/|data/raw/final_publication_receipts/)' || true)"
if [ -n "$forbidden" ]; then
  echo "[daily-stage] refusing failed commit containing final-contract candidate paths:" >&2
  printf '%s\n' "$forbidden" >&2
  exit 1
fi
echo "[daily-stage] failed job: non-final raw evidence only staged"
