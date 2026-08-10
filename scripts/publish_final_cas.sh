#!/usr/bin/env bash
# Frozen-parent publisher for the finalized daily contract.
set -euo pipefail

TARGET="${1:?usage: publish_final_cas.sh <target> <base> <source> <pipeline> <audit> <derived>}"
BASE_COMMIT="${2:?missing frozen base commit}"
SOURCE_OUTCOME="${3:?missing source outcome}"
PIPELINE_OUTCOME="${4:?missing pipeline outcome}"
AUDIT_OUTCOME="${5:?missing audit outcome}"
DERIVED_OUTCOME="${6:?missing derived outcome}"

PUBLISH_TOKEN="${IGRM_PUBLISH_TOKEN:?IGRM_PUBLISH_TOKEN is required}"
AUTH_HEADER="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$PUBLISH_TOKEN" | base64 | tr -d '\n')"
unset IGRM_PUBLISH_TOKEN PUBLISH_TOKEN GH_TOKEN GITHUB_TOKEN

push_frozen_parent() {
  git fetch --quiet origin main
  REMOTE_COMMIT=$(git rev-parse origin/main)
  if [ "$REMOTE_COMMIT" != "$BASE_COMMIT" ]; then
    echo "::error::CAS refusal: candidate parent $BASE_COMMIT, current main $REMOTE_COMMIT; rebuild required"
    return 1
  fi
  GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0='http.https://github.com/.extraheader' \
    GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
    git push origin HEAD:main
}

publish_gated_candidate() {
  local message="$1"
  git commit -m "$message"
  # One exact gate over the one candidate SHA. A changed remote is a refusal,
  # never authority to rebase or auto-resolve final/history bytes.
  /usr/bin/time -v bash scripts/gate.sh --committed
  push_frozen_parent
}

publish_final() {
  git config user.name "igrm-bot"
  git config user.email "actions@github.com"
  git add docs data/raw
  publish_gated_candidate "data: final $TARGET via morning-contract lane"
}

publish_refusal() {
  local status_parent status_root failure_stage
  status_parent=$(mktemp -d)
  status_root="$status_parent/status-candidate"
  git worktree add --detach "$status_root" "$BASE_COMMIT"
  if [ -f data/raw/final_publication_status.json ]; then
    mkdir -p "$status_root/data/raw"
    cp data/raw/final_publication_status.json \
      "$status_root/data/raw/final_publication_status.json"
  fi
  cd "$status_root"
  git config user.name "igrm-bot"
  git config user.email "actions@github.com"

  failure_stage=pipeline
  if [ "$SOURCE_OUTCOME" != "success" ]; then
    failure_stage=source
  elif [ "$PIPELINE_OUTCOME" != "success" ]; then
    failure_stage=pipeline
  elif [ "$AUDIT_OUTCOME" != "success" ]; then
    failure_stage=audit
  elif [ "$DERIVED_OUTCOME" != "success" ]; then
    failure_stage=derived
  fi
  python -m src.final_publication \
    --record-pipeline-failed "$TARGET" \
    --failure-stage "$failure_stage" \
    --base-commit "$BASE_COMMIT"
  python -m src.final_publication --write-public-status \
    --today "$(date -u -d "$TARGET + 1 day" +%F)"
  git add data/raw/final_publication_status.json docs/data/status.json \
    docs/index.html docs/status.html
  if git diff --cached --name-only | grep -Eq \
    '^(data/raw/gdelt_volume.csv|data/raw/provenance.csv|data/raw/ngram_days/|data/raw/final_publication_receipts/)'; then
    echo "::error::failure disclosure attempted to stage candidate value bytes"
    return 1
  fi
  publish_gated_candidate "status: final $TARGET unavailable"
}

if [ "$SOURCE_OUTCOME" = "success" ] && \
   [ "$PIPELINE_OUTCOME" = "success" ] && \
   [ "$AUDIT_OUTCOME" = "success" ] && \
   [ "$DERIVED_OUTCOME" = "success" ]; then
  # A gate/CAS refusal exits red. The watchdog owns any later disclosure; this
  # job never starts a second full gate after a successful candidate reaches it.
  publish_final
else
  publish_refusal
fi
