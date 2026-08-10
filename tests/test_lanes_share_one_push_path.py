"""Eleven lanes push to main. There must be one implementation.

Every publishing workflow hand-rolled its own retry loop, and they had
drifted into three different shapes with three different bugs:

  seven lanes   `git pull --rebase origin main || true` then `git push`
                -- the `|| true` swallows a FAILED rebase, so the push
                runs from a repo stopped mid-rebase with conflict markers
                on disk. daily.yml carried a comment warning that a push
                inside an interrupted rebase "reports vacuous success";
                the other lanes never got the lesson.

  three lanes   a 3-attempt loop that aborts the rebase properly but
                still retries the identical conflict.

  validate.yml  no retry at all: one `pull || true`, one `push`.

And none of them resolved anything. The conflict these lanes hit is
DETERMINISTIC -- they rewrite generated files while main moves under them
-- so retrying an identical rebase cannot work. Measured on daily.yml
before the fix: 13 of 20 runs failed, five of the eight inspected at
exactly this step.

I fixed daily.yml inline first, which made it the twelfth variant rather
than the fix. `scripts/publish_push.sh` is now the only implementation
and every lane calls it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = ROOT / "scripts" / "publish_push.sh"


def _pushing_lanes() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in sorted(WORKFLOWS.glob("*.yml"))
            if "git push" in p.read_text(encoding="utf-8")
            or "publish_push.sh" in p.read_text(encoding="utf-8")}


def test_the_lane_set_is_not_empty():
    """The audit's finding: _pushing_lanes() keys on strings a refactor
    could remove, and every downstream test would then pass on zero
    lanes. Its sibling file has this guard; this one did not."""
    lanes = _pushing_lanes()
    assert len(lanes) >= 8, (
        f"only {len(lanes)} pushing lanes detected; eleven existed when "
        "this was written. Either lanes were really removed, or the "
        "detector's markers no longer match how lanes push.")


def test_the_shared_push_script_exists_and_is_executable():
    assert SCRIPT.exists(), "scripts/publish_push.sh is gone"
    assert SCRIPT.stat().st_mode & 0o111, "publish_push.sh is not executable"


def test_no_lane_hand_rolls_an_unregistered_push():
    """The final-recovery lane is the one deliberate CAS-only exception.

    It cannot use the generic derived-file conflict resolver for final/history
    bytes. Its frozen-parent, exact-gate path is independently checked by the
    security-integrity registry and the publication-contract tests.
    """
    offenders = [
        name
        for name, text in _pushing_lanes().items()
        if "publish_push.sh" not in text
        and not (
            name == "morning.yml"
            and "git push origin HEAD:main" in text
            and 'REMOTE_COMMIT=$(git rev-parse origin/main)' in text
            and "bash scripts/gate.sh --committed" in text
            and "git pull --rebase" not in text
        )
    ]
    assert not offenders, (
        f"these lanes push without the shared script: {offenders}. Three "
        "hand-rolled shapes with three different bugs is what this "
        "replaced; a fourth would drift the same way.")


def test_no_lane_pushes_from_a_possibly_broken_rebase():
    """The specific bug in seven of them: `|| true` on the rebase, then
    push regardless. A push inside an interrupted rebase reports vacuous
    success -- the run goes green with the work unpushed."""
    offenders = []
    for name, text in _pushing_lanes().items():
        for m in re.finditer(r"git pull --rebase[^\n]*", text):
            line = m.group(0).strip()
            if "publish_push.sh" in line:
                continue
            # The one legitimate best-effort case: daily.yml's backfill
            # loop banks the chunk cache mid-run against a job timeout, so
            # a failure there must not kill the pass. It must still ABORT
            # the rebase -- left in place, the repo sits half-applied and
            # the next pass's commit behaves unpredictably.
            if "|| git rebase --abort" in line:
                continue
            if re.search(r"\|\|\s*true\s*$", line):
                offenders.append(f"{name}: {line}")
    assert not offenders, (
        f"rebase failure swallowed with no abort: {offenders}")


def test_the_script_resolves_only_derived_paths():
    """The resolution is safe *because* it is narrow. If it ever widens to
    the whole tree, a machine starts silently resolving conflicts in src/
    and workflows -- which is how a methodology change disappears."""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"DERIVED_RE='([^']+)'", text)
    assert m, "publish_push.sh no longer declares DERIVED_RE"
    assert m.group(1) == "^(docs/|data/raw/)", (
        f"the auto-resolved paths changed to {m.group(1)!r}; only generated "
        "output may be resolved automatically")
    assert "rebase --abort" in text, (
        "the script no longer aborts on a conflict it cannot safely resolve")


def test_the_script_uses_theirs_not_ours():
    """During a rebase the sides invert: 'ours' is the upstream being
    replayed onto, 'theirs' is the commit being replayed -- this run's
    work. Getting it backwards publishes upstream's older numbers and
    looks like a successful run. Verified in a scratch repo before it
    shipped; pinned here so nobody 'corrects' it later."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "checkout --theirs" in text, "the resolution no longer takes this run's version"
    assert "checkout --ours" not in text, (
        "publish_push.sh resolves to --ours, which is UPSTREAM during a "
        "rebase; the lane would publish older numbers than it computed")


def test_a_failed_push_still_fails_the_lane():
    """The original loops ended with `[ "$pushed" = "1" ]` for a reason: a
    lane that exits 0 with its work unpushed loses the computed day while
    reporting success."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'pushed"?\s*!=\s*"1"', text) and "exit 1" in text, (
        "publish_push.sh can exit 0 without having pushed")


def test_every_rebased_candidate_runs_the_committed_gate_before_push():
    """Bot pushes do not trigger ordinary push CI. The shared lane must
    therefore test the exact post-rebase commit itself, and a red candidate
    must exit rather than trading integrity for the day's availability."""

    text = SCRIPT.read_text(encoding="utf-8")
    # --publish, not --committed, since 2026-08-11. It still gates the exact
    # COMMITTED candidate (--publish implies --committed inside gate.sh); the
    # only difference is that assertions about the ALREADY-SERVED site are
    # excluded, because a stale site was refusing the very pushes that would
    # refresh it. The property this test defends -- a red candidate exits
    # rather than trading integrity for availability -- is unchanged, and
    # tests/test_gate_publish_mode.py pins that nothing else was narrowed.
    assert "bash scripts/gate.sh --publish" in text
    assert "SECURITY REFUSAL" in text
    assert text.count("if ! gate_candidate; then exit 1; fi") == 2
    assert "unset IGRM_PUBLISH_TOKEN" in text
    assert not re.search(r"^\s*if git push", text, re.M)
    pushes = list(re.finditer(r"^\s*if git_push", text, re.M))
    assert len(pushes) == 2
    for push in pushes:
        preceding = text[max(0, push.start() - 120) : push.start()]
        assert "gate_candidate" in preceding, (
            "a push path exists without an immediately preceding committed gate"
        )
