"""No lane that PUBLISHES may gate itself on the already-served site.

THE LOOP THIS CLOSES
A test that asserts "the live site is fresh" cannot judge a candidate -- it
describes the world the candidate is about to change. Put it in front of a
publisher and it becomes self-sustaining:

  daily.yml PRODUCES comparators, episode_terms, receipts, receipts_archive,
  spike_breadth and validation. Those six went stale. The live freshness test
  failed. It ran as daily.yml's FIRST step, so the lane died before the heal
  and before the pipeline -- unable to refresh the payloads whose staleness
  was killing it. Measured on 2026-08-11: daily #106, #107 and #109 all failed
  at "Enforce dictionary rules (ex-ante rule)".

  Every publisher then failed too, because the gate inside publish_push.sh ran
  the same assertions against the same six payloads (fixed separately in
  98a0050 via scripts/gate.sh --publish).

morning.yml had already learned this and says so in a comment. daily.yml had
the same step, unfixed, for as long as it existed. One lane learning a lesson
privately is how it comes back, so the rule is enforced here for every lane at
once rather than left to whoever edits a workflow next.

ci.yml is deliberately NOT exempted by name: it is covered by the rule itself,
because it does not publish. That is exactly where these assertions belong --
running on main as monitoring, where a stale site is an alert and not a lock.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"

# A lane publishes if it pushes, directly or through the shared push script.
_PUBLISHES = ("publish_push.sh", "git push", "ship.sh")
_PYTEST = re.compile(r"^\s*run:\s*(.*\bpytest\b.*)$", re.M)


def _publishing_workflows() -> list[Path]:
    out = []
    for wf in sorted(WORKFLOWS.glob("*.yml")):
        text = wf.read_text(encoding="utf-8")
        if any(marker in text for marker in _PUBLISHES):
            out.append(wf)
    return out


def test_the_rule_has_something_to_check() -> None:
    """If the markers stop matching, every assertion below passes vacuously."""
    publishing = _publishing_workflows()
    assert len(publishing) >= 5, (
        f"only {len(publishing)} publishing workflows found; the detection "
        "markers have probably drifted and this suite is now vacuous")
    with_tests = [w for w in publishing if _PYTEST.search(w.read_text("utf-8"))]
    assert with_tests, "no publishing workflow runs pytest; markers drifted"


def test_no_publishing_lane_runs_the_live_suite_in_its_gate() -> None:
    offenders = []
    for wf in _publishing_workflows():
        for cmd in _PYTEST.findall(wf.read_text(encoding="utf-8")):
            if 'not live' not in cmd:
                offenders.append(f"{wf.name}: {cmd.strip()}")
    assert not offenders, (
        "these publishing lanes gate on assertions about the ALREADY-SERVED "
        "site, which cannot judge their candidate and deadlocks them exactly "
        "when publishing matters most. Add -m \"not live\"; the live "
        "assertions belong in ci.yml, which does not publish:\n  "
        + "\n  ".join(offenders))


def test_ci_still_runs_the_live_suite_somewhere() -> None:
    """Excluding the live assertions from publishers is only honest if they
    still run. If ci.yml ever narrows too, the site could rot unwatched."""
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "publish_push.sh" not in ci and "git push" not in ci, (
        "ci.yml now publishes, so it is subject to the rule above and can no "
        "longer be the place the live assertions run")
    cmds = _PYTEST.findall(ci)
    assert cmds, "ci.yml no longer runs pytest at all"
    assert any("not live" not in c for c in cmds), (
        "ci.yml no longer runs the live suite; nothing is watching whether "
        "the served site is fresh")
