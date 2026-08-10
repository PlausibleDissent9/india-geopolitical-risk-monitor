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
FROZEN_CANDIDATE_SHA=""

require_frozen_base() {
  local current_head
  current_head=$(git rev-parse HEAD)
  if [ "$current_head" != "$BASE_COMMIT" ]; then
    echo "::error::candidate construction refusal: local HEAD $current_head is not frozen base $BASE_COMMIT"
    return 1
  fi
}

push_frozen_parent() {
  local candidate_head parent_count candidate_parent remote_commit
  candidate_head=$(git rev-parse HEAD)
  if [ -z "$FROZEN_CANDIDATE_SHA" ] || [ "$candidate_head" != "$FROZEN_CANDIDATE_SHA" ]; then
    echo "::error::CAS refusal: gated candidate SHA is not current HEAD"
    return 1
  fi
  parent_count=$(git rev-list --parents -n 1 "$FROZEN_CANDIDATE_SHA" | awk '{print NF - 1}')
  if [ "$parent_count" != "1" ]; then
    echo "::error::CAS refusal: candidate must have exactly one parent"
    return 1
  fi
  candidate_parent=$(git rev-parse "$FROZEN_CANDIDATE_SHA^")
  if [ "$candidate_parent" != "$BASE_COMMIT" ]; then
    echo "::error::CAS refusal: candidate parent $candidate_parent is not frozen base $BASE_COMMIT"
    return 1
  fi
  git fetch --quiet origin main
  remote_commit=$(git rev-parse origin/main)
  if [ "$remote_commit" != "$BASE_COMMIT" ]; then
    echo "::error::CAS refusal: candidate parent $BASE_COMMIT, current main $remote_commit; rebuild required"
    return 1
  fi
  GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0='http.https://github.com/.extraheader' \
    GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
    git push origin "$FROZEN_CANDIDATE_SHA:main"
}

publish_gated_candidate() {
  local message="$1" parent_count candidate_parent
  git commit -m "$message"
  FROZEN_CANDIDATE_SHA=$(git rev-parse HEAD)
  parent_count=$(git rev-list --parents -n 1 "$FROZEN_CANDIDATE_SHA" | awk '{print NF - 1}')
  if [ "$parent_count" != "1" ]; then
    echo "::error::candidate refusal: publisher commit must have exactly one parent"
    return 1
  fi
  candidate_parent=$(git rev-parse "$FROZEN_CANDIDATE_SHA^")
  if [ "$candidate_parent" != "$BASE_COMMIT" ]; then
    echo "::error::candidate refusal: publisher commit parent $candidate_parent is not frozen base $BASE_COMMIT"
    return 1
  fi
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

require_frozen_base
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
