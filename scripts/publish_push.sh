#!/usr/bin/env bash
# Commit and push a lane's output, resolving the one conflict class that
# actually happens. Used by every publishing workflow.
#
#   scripts/publish_push.sh "notes: publish 2026-08-07"
#
# WHY THIS EXISTS
# Eleven workflows push to main. Ten of them hand-rolled the same loop:
#
#     for i in 1 2 3 4 5; do
#       git pull --rebase origin main || true
#       if git push; then pushed=1; break; fi
#       sleep $((10 * i))
#     done
#
# Two things are wrong with it, and both were already known in this repo
# and fixed in exactly one place.
#
# 1. `|| true` swallows a FAILED rebase, leaving the repo stopped
#    mid-rebase with conflict markers on disk -- and then runs `git push`
#    from that state. daily.yml carries a comment warning that a push
#    inside an interrupted rebase "reports vacuous success". The other ten
#    lanes never got the lesson.
#
# 2. The conflict is DETERMINISTIC. These lanes rewrite generated files;
#    main moves under them (nowcast every two hours, permanence, notes,
#    and more than one agent). Retrying an identical rebase five times
#    cannot resolve a collision that will recur identically. Measured on
#    daily.yml: 13 of 20 runs failed, five of the eight inspected at this
#    exact step.
#
# THE RESOLUTION
# Conflicts under docs/ and data/raw/ are always in derived files, and
# this run's version comes from a store that is a superset of upstream's,
# so regenerating is the correct answer. Those resolve to this run's work.
#
# Anything still conflicted afterwards is NOT derived -- source,
# workflows, registrations -- and the lane aborts rather than guessing. A
# machine silently resolving a conflict in src/ is how a methodology
# change disappears.
#
# --theirs, NOT --ours. During a rebase the sides invert: "ours" is the
# upstream being replayed onto, "theirs" is the commit being replayed --
# this run's work. Verified in a scratch repo before this shipped;
# getting it backwards would quietly publish upstream's older numbers.
set -uo pipefail

MSG="${1:?usage: publish_push.sh <commit message>}"
DERIVED_RE='^(docs/|data/raw/)'

# Checkout uses persist-credentials:false, so build, generation and tests never
# inherit a repository write credential through Git configuration. The token is
# supplied only to the final workflow step. Convert it to one ephemeral Git
# header, then remove every token variable before any repository code or test
# process runs. AUTH_HEADER is a non-exported shell variable; only git_push's
# single subprocess receives it.
PUBLISH_TOKEN="${IGRM_PUBLISH_TOKEN:?IGRM_PUBLISH_TOKEN is required}"
AUTH_HEADER="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$PUBLISH_TOKEN" | base64 | tr -d '\n')"
unset IGRM_PUBLISH_TOKEN PUBLISH_TOKEN GH_TOKEN GITHUB_TOKEN

git_push() {
  GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0='http.https://github.com/.extraheader' \
    GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
    git push
}

# A GITHUB_TOKEN push does not trigger another push workflow. Before this
# guard, a publisher could therefore rebase generated files onto a newer main
# commit and push that exact combined tree without CI ever testing it. Checks
# earlier in the lane were evidence about the pre-rebase tree only.
#
# Run the canonical CI gate against HEAD after EVERY successful rebase and
# immediately before each push attempt. --committed ignores caches and other
# runner state and tests the exact Git tree that will be published. If it is
# red, losing this scheduled output is the safe result: availability pressure
# must never become authority to publish unverified bytes.
#
# A refusal also has to be READABLE. gate.sh names each check as it starts
# it, so the failing one is already in the step log -- but a step log needs
# an authenticated token to fetch, and on 2026-08-09 that was the whole
# distance between a three-day outage and a diagnosis. Run annotations are
# served without one. So the refusal is emitted as a workflow ::error::
# too, which puts the failing check in the annotations API where anyone
# looking at a red publisher can read it directly.
gate_candidate() {
  local commit tree log rc failing
  commit=$(git rev-parse --verify HEAD) || return 1
  tree=$(git rev-parse --verify 'HEAD^{tree}') || return 1
  echo "[publish] verifying exact candidate commit=$commit tree=$tree"
  log="$(mktemp)"
  # Deliberately not piped into tee: a pipeline reports the LAST command's
  # status, and laundering a gate's exit status through a pipe is the exact
  # defect this repo has already paid for once.
  bash scripts/gate.sh --committed > "$log" 2>&1
  rc=$?
  cat "$log"
  if [ "$rc" -ne 0 ]; then
    failing="$(grep '^-- ' "$log" | tail -1 | sed 's/^-- //')"
    rm -f "$log"
    echo "::error::publish refused: the committed CI gate is red on ${commit:0:8}. Last check started: ${failing:-unknown (gate failed before running any check)}"
    echo "[publish] SECURITY REFUSAL: candidate failed the committed CI gate"
    return 1
  fi
  rm -f "$log"
  echo "[publish] exact candidate passed the committed CI gate"
}

git commit -m "$MSG" || echo "[publish] no changes to commit"

pushed=0
for i in 1 2 3 4 5; do
  if git pull --rebase origin main; then
    if ! gate_candidate; then exit 1; fi
    if git_push; then pushed=1; break; fi
  else
    # Resolve only the derived paths, to this run's computation.
    if git diff --name-only --diff-filter=U | grep -qE "$DERIVED_RE"; then
      git diff --name-only --diff-filter=U | grep -E "$DERIVED_RE" \
        | xargs -r git checkout --theirs -- || true
      git diff --name-only --diff-filter=U | grep -E "$DERIVED_RE" \
        | xargs -r git add || true
    fi
    if git diff --name-only --diff-filter=U | grep -q .; then
      echo "[publish] unresolved conflict outside derived paths:"
      git diff --name-only --diff-filter=U | sed 's/^/[publish]   /'
      git rebase --abort || true
    elif ! GIT_EDITOR=true git rebase --continue; then
      git rebase --abort || true
    else
      if ! gate_candidate; then exit 1; fi
      if git_push; then pushed=1; break; fi
    fi
  fi
  echo "[publish] push attempt $i failed; retrying"
  sleep $((10 * i))
done

# Never exit 0 with the work unpushed: the computed day would die with
# the runner while the lane reported success.
if [ "$pushed" != "1" ]; then
  echo "[publish] five attempts failed; the run's output is NOT on main"
  exit 1
fi
echo "[publish] pushed"
