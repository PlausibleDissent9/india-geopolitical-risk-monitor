#!/usr/bin/env bash
# Run exactly what CI runs, by reading ci.yml rather than remembering it.
#
# WHY THIS EXISTS
# On 2026-08-07 six consecutive pushes went red while every commit message
# said "ruff clean, mypy clean, N passing". All three claims were true of
# the commands I ran and false of the commands CI runs:
#
#   I ran                        CI runs
#   mypy src/one_new_file.py     mypy                 (all 67 files)
#   pytest -m "not live"         pytest --cov=src     (11 more tests)
#   ruff check src tests         ruff check .         (the whole tree)
#
# Two of my own annotations and one typing error in another agent's module
# sat red for half an hour because a narrower command passed. Reporting a
# green gate from a command that is not the gate is the same defect this
# repo keeps finding everywhere else: a check that cannot fail the way the
# real one does.
#
# So this does not restate the commands. It EXTRACTS them from
# .github/workflows/ci.yml, in order, and runs them. If CI changes, this
# changes with it; tests/test_gate_matches_ci.py fails if the extraction
# ever stops finding them.
#
#   scripts/gate.sh          run every CI check, stop at the first failure
#
#   scripts/gate.sh --committed   run them against HEAD, not the worktree
#
#   scripts/gate.sh --publish     as --committed, minus the live-site
#                                 assertions (see WHY --publish EXISTS)
#
# WHY --committed EXISTS
# Another agent works in this same checkout, so the working tree contains
# edits that are not mine and will not be committed. On 2026-08-07 that
# made the local gate red for an unrelated reason (an asset hash pinned
# to someone's uncommitted redesign), I REASONED that CI would be green
# on the committed tree, pushed, and ci #351 went red on a different
# failure the reasoning had not covered.
#
# The lesson is the one this repo keeps relearning: verify, do not
# reason. --committed extracts HEAD with `git archive` and runs the same
# checks against exactly what CI will check out.
#
# WHY --publish EXISTS
# A PUBLISH gate and a CI gate answer different questions. CI asks "is the
# repository healthy?". A publish gate asks "is THIS CANDIDATE fit to
# serve?". Those coincide for every check here except one class: the tests
# marked `live`, which fetch igrm.in and assert about the payloads the site
# is ALREADY SERVING.
#
# A live-site assertion cannot say anything about the candidate -- it
# describes the state the candidate is about to replace. Worse, it is
# anti-correlated with the thing it blocks: it fails exactly when the site
# is stale, which is exactly when publishing is most urgent. That closes a
# loop with no exit:
#
#   the site is stale -> the live freshness test fails -> the gate inside
#   publish_push.sh is red -> the push is refused -> the site stays stale
#
# Measured on 2026-08-11: morning-contract runs #45 and #46 both reached
# "Commit and push" and died there, with six payloads (comparators,
# episode_terms, receipts, receipts_archive, spike_breadth, validation)
# stale on the live site. Nothing was wrong with either candidate. Thirteen
# lanes call publish_push.sh, so this deadlocks ALL publishing, including
# the very lanes that would refresh those six payloads.
#
# This is not a new opinion about gates -- it is morning.yml's, applied
# where it was missed. That workflow already excludes live tests from its
# first gate step and says why: "a test that reaches outside the code it
# tests does not belong in the contract's gate." publish_push.sh then
# re-introduced them by calling the full gate.
#
# So --publish runs EVERY other check unchanged -- the registry --check
# refusals, the conformance-artifact diffs, ruff, mypy, and the whole
# non-live suite with coverage. It removes nothing that describes the
# candidate. The live assertions still run, unchanged, in ci.yml on every
# push to main, where they are what they should be: monitoring that reports
# a stale site, rather than a lock that guarantees one.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
CI=".github/workflows/ci.yml"

# Flags may be combined, so they are parsed rather than positional. In
# particular `--publish --print` emits the NARROWED command list, which is
# what tests/test_gate_publish_mode.py inspects: the test runs this script's
# own transformation instead of restating it, the same reason --print exists.
PUBLISH=0
PRINT=0
COMMITTED=0
for arg in "$@"; do
  case "$arg" in
    --publish)   PUBLISH=1; COMMITTED=1 ;;
    --committed) COMMITTED=1 ;;
    --print)     PRINT=1 ;;
  esac
done

if [ "$COMMITTED" -eq 1 ] && [ "$PRINT" -eq 0 ]; then
  TREE="$(mktemp -d)"
  trap 'rm -rf "$TREE"' EXIT
  echo "gate: extracting HEAD to $TREE (ignores the working tree)"
  git archive HEAD | tar -x -C "$TREE" || { echo "gate: git archive failed"; exit 1; }
  # The suite reads git history in two places (vintages, sitemap dates),
  # so give the extract a usable .git rather than letting those fail for
  # a reason that has nothing to do with the change under test.
  cp -R .git "$TREE/.git" 2>/dev/null || true
  VENV="$PWD/.venv"
  cd "$TREE" || exit 1
  export PATH="$VENV/bin:$PATH"
fi
[ -f "$CI" ] || { echo "gate: $CI not found"; exit 1; }

# Prefer the project venv, as CI installs into a clean environment.
if [ -x .venv/bin/activate ] || [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  . .venv/bin/activate
fi

# Every `run:` under the checks job, minus the pip install. CI and the local
# gate both run check_environment.py immediately afterward, so a stale or
# partially provisioned local venv fails instead of making missing package
# types disappear from mypy. Reinstalling on every gate remains unnecessary.
#
# Written as a while-read loop rather than `mapfile`, which is bash 4+ and
# absent from the bash 3.2 macOS still ships -- the gate has to run on the
# machine it is meant to protect.
CMDS_FILE="$(mktemp)"
trap 'rm -f "$CMDS_FILE"' EXIT
grep -E "^[[:space:]]+run: " "$CI" \
  | sed -E 's/^[[:space:]]+run: //' \
  | grep -v '^pip install' > "$CMDS_FILE"

N=$(wc -l < "$CMDS_FILE" | tr -d ' ')

# --print: emit the extracted commands and exit, so the test that checks
# the extraction can run THIS extraction rather than re-typing it. The
# test audit found test_gate_matches_ci comparing a Python regex against
# a shell regex over the same file -- two derivations of one source,
# never touching the script under test.
[ "$N" -gt 0 ] || { echo "gate: no commands extracted from $CI"; exit 1; }

# --publish: narrow the pytest invocation to the non-live suite, and ONLY
# that invocation. Every other extracted command runs verbatim.
#
# Appending the marker rather than rewriting the command keeps CI as the
# single source of the command: if CI's pytest step changes flags, those
# flags still arrive here. `-m "not live"` composes with pytest's own
# default marker expression, and CI's step carries no -m of its own (a
# second -m would silently win, so the test below pins that).
if [ "$PUBLISH" -eq 1 ]; then
  if ! grep -q 'pytest' "$CMDS_FILE"; then
    echo "gate: --publish found no pytest command to narrow"; exit 1
  fi
  # Only a marker flag AFTER the word pytest counts. `python -m pytest` also
  # contains "-m ", and an earlier version of this guard matched that and
  # refused every publish -- caught by tests/test_gate_publish_mode.py before
  # it ever ran in a lane.
  if grep -E 'pytest' "$CMDS_FILE" | sed -E 's/^.*pytest//' | grep -q -- '-m '; then
    echo "gate: --publish refuses to append a second -m to CI's pytest command"
    exit 1
  fi
  NARROWED="$(mktemp)"
  # shellcheck disable=SC2016
  sed -E 's/(^.*pytest.*$)/\1 -m "not live"/' "$CMDS_FILE" > "$NARROWED"
  mv "$NARROWED" "$CMDS_FILE"
  if [ "$PRINT" -eq 0 ]; then
    echo "gate: --publish mode -- live-site assertions excluded (they describe"
    echo "      the site being replaced, not this candidate; ci.yml still runs them)"
  fi
fi

if [ "$PRINT" -eq 1 ]; then cat "$CMDS_FILE"; exit 0; fi

echo "gate: running $N checks from $CI"
FAILED=0
while IFS= read -r cmd; do
  [ -n "$cmd" ] || continue
  echo
  echo "-- $cmd"
  if ! eval "$cmd"; then
    echo "FAILED: $cmd"
    FAILED=1
    break
  fi
done < "$CMDS_FILE"

echo
if [ "$FAILED" -eq 0 ]; then
  echo "gate: all $N CI checks pass"
else
  echo "gate: CI would be red. Do not push."
fi
exit "$FAILED"
