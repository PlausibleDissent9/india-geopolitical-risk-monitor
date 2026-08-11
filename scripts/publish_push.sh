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

# TURN A RED GATE LOG INTO A ONE-LINE DIAGNOSIS.
#
# Kept as its own function, and reachable as
#
#   scripts/publish_push.sh --explain-gate-log <file>
#
# so its test can run THIS code against fixture logs instead of re-typing
# the patterns. gate.sh grew --print for exactly this reason: a test that
# restates the expression under test verifies the restatement.
#
# gate.sh prints "FAILED: <cmd>" for the check that failed; pytest prints
# "FAILED tests/x.py::y" per failing test. Take both. Everything else --
# a --check refusal, a `git diff --exit-code` -- says its piece in the
# closing lines instead of a summary block, so fall back to those.
explain_gate_log() {
  local log="$1" failing detail
  failing="$(grep '^FAILED: ' "$log" | tail -1 | sed 's/^FAILED: //')"
  detail="$(grep -E '^(FAILED|ERROR) (tests|src)/' "$log" | head -5 | tr '\n' ' ')"
  if [ -z "$detail" ]; then
    detail="$(grep -vE '^[[:space:]]*$' "$log" | tail -4 | tr '\n' ' ')"
  fi
  printf 'Failing check: %s. Detail: %s' \
    "${failing:-none reported (the gate died before it ran a check)}" \
    "${detail:-see the step log}"
}

# Before MSG and before the token requirement: this mode reads a file and
# prints, and must not need a publish credential to do it.
if [ "${1:-}" = "--explain-gate-log" ]; then
  explain_gate_log "${2:?usage: publish_push.sh --explain-gate-log <gate log>}"
  echo
  exit 0
fi

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
#
# GATE ONCE PER CANDIDATE, NOT ONCE PER PUSH ATTEMPT.
# The retry loop below calls this before every push, and a push is rejected
# whenever main moved in the seconds since the rebase. On a busy night that
# is often: two agents pushed roughly fifteen times in a few hours on
# 2026-08-09, and nowcast #79 died at its 30-minute cap with 19.8 minutes
# inside this step. The committed gate measured 7m32s locally that night --
# against the ~5.2 minutes every lane's cap was originally budgeted for --
# and a runner is slower than the machine it was measured on. Two gates do
# not fit in thirty minutes.
#
# So a candidate is gated once. If HEAD is unchanged since the last green
# gate IN THIS RUN, the push is retried without re-running it. Keyed on the
# commit sha rather than the tree: a no-op rebase leaves the sha alone, and
# anything that actually moves -- a real rebase, a new parent, an amended
# tree -- changes it and is gated again. That is the conservative choice;
# tree-keying would skip more and is harder to argue is safe, and this is
# the publish path.
#
# What this does NOT do is weaken the guarantee. Every push is still
# preceded by a green gate over exactly the bytes being pushed. It removes
# only the case where those bytes were already proven green a minute ago.
LAST_GREEN_COMMIT=""

gate_candidate() {
  local commit tree log rc explanation
  commit=$(git rev-parse --verify HEAD) || return 1
  tree=$(git rev-parse --verify 'HEAD^{tree}') || return 1
  # ${...:-} so the function stands alone under `set -u`: the memo is an
  # optimisation, not a precondition, and a caller that never declared it
  # should get the un-memoised behaviour rather than an unbound-variable
  # crash on the publish path.
  if [ -n "${LAST_GREEN_COMMIT:-}" ] && [ "$commit" = "${LAST_GREEN_COMMIT:-}" ]; then
    echo "[publish] candidate $commit already passed the committed gate in this run; retrying the push without re-running it"
    return 0
  fi
  echo "[publish] verifying exact candidate commit=$commit tree=$tree"
  log="$(mktemp)"
  # Deliberately not piped into tee: a pipeline reports the LAST command's
  # status, and laundering a gate's exit status through a pipe is the exact
  # defect this repo has already paid for once.
  # --publish, not --committed: identical except that the live-site
  # assertions are excluded. They describe the payloads igrm.in is ALREADY
  # serving, so they cannot judge this candidate, and including them
  # deadlocked every publisher on 2026-08-11 (a stale site refused the
  # pushes that would have refreshed it). gate.sh documents the reasoning;
  # ci.yml still runs them on main as monitoring.
  bash scripts/gate.sh --publish > "$log" 2>&1
  rc=$?
  cat "$log"
  if [ "$rc" -ne 0 ]; then
    # REPORT WHAT FAILED, NOT WHAT STARTED.
    # The first version grepped '^-- ' -- the line gate.sh prints when it
    # BEGINS a check -- and took the last match. pytest's own warnings
    # footer ends with "-- Docs: https://docs.pytest.org/...", which
    # matches. So morning-contract #34 refused with
    #   "Last check started: Docs: https://docs.pytest.org/..."
    # naming a documentation URL instead of a check. The refusal was
    # correct and completely unactionable: it said the gate was red
    # without saying what was red, which is the failure this ::error::
    # was added to prevent in the first place.
    explanation="$(explain_gate_log "$log")"
    rm -f "$log"
    echo "::error::publish refused: the committed CI gate is red on ${commit:0:8}. $explanation"
    echo "[publish] SECURITY REFUSAL: candidate failed the committed CI gate"
    return 1
  fi
  rm -f "$log"
  LAST_GREEN_COMMIT="$commit"
  echo "[publish] exact candidate passed the committed CI gate"
}

git commit -m "$MSG" || echo "[publish] no changes to commit"

# UNSTAGED CHANGES STOP A REBASE DEAD, AND USED TO DO IT SILENTLY.
#
# `git pull --rebase` refuses outright -- "cannot pull with rebase: You have
# unstaged changes" -- and returns instantly. The loop below then finds no
# conflicted paths, fails `git rebase --continue` because no rebase is in
# progress, aborts, and sleeps. Five attempts sleep 10+20+30+40+50 = 150
# seconds and the lane exits 1 having never called gate_candidate at all.
#
# That is precisely what happened on 2026-08-09: morning-contract #27, #32
# and #33 and receipts-extended #1 each failed at their push step in 2.5
# minutes -- the sleep total, not a gate that ran -- while the site served
# 2026-08-07 for a third day. #33 carried the gate's new ::error:: reporting
# and emitted nothing, which is how the path was identified: the gate was
# never reached.
#
# The usual source is a lane staging narrower than it writes. stamp_assets
# rewrites every docs/*.html when an asset hash changes, and a lane staging
# only `docs/data data/raw` leaves those modifications behind.
#
# Do not stage them here. What a lane publishes is that lane's decision, and
# silently sweeping stray files into a publish commit is how something
# unreviewed reaches the site. Refuse, name the files, and say which lane.
unstaged="$(git diff --name-only)"
if [ -n "$unstaged" ]; then
  echo "::error::publish refused before rebase: the working tree has unstaged changes, which makes 'git pull --rebase' fail instantly and burns all five retries without ever running the gate. Files: $(printf '%s' "$unstaged" | tr '\n' ' ')"
  echo "[publish] REFUSING: unstaged changes would silently defeat the rebase:"
  printf '%s\n' "$unstaged" | sed 's/^/[publish]   /'
  echo "[publish] stage them in the lane's own 'git add' if they belong in"
  echo "[publish] this publish, or leave them out of the runner deliberately."
  exit 1
fi

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
