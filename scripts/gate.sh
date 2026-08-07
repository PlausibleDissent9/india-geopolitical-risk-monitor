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
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
CI=".github/workflows/ci.yml"

if [ "${1:-}" = "--committed" ]; then
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

# Every `run:` under the checks job, minus the pip install (the local venv
# is already provisioned and reinstalling on every gate is minutes wasted).
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
if [ "${1:-}" = "--print" ]; then cat "$CMDS_FILE"; exit 0; fi
[ "$N" -gt 0 ] || { echo "gate: no commands extracted from $CI"; exit 1; }

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
