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

git commit -m "$MSG" || echo "[publish] no changes to commit"

pushed=0
for i in 1 2 3 4 5; do
  if git pull --rebase origin main; then
    if git push; then pushed=1; break; fi
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
    elif git push; then
      pushed=1; break
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
