"""A freshness limit is a promise about a lane. Check the lane exists.

Three times now a payload has carried a max-age limit that no lane could
ever satisfy, and each time the limit looked reasonable in isolation:

  * 2026-08-18 (1bea6f7): robustness_series and energy_context inherited
    the 3-day DEFAULT while their lanes run WEEKLY -- stale four days in
    seven, by construction.
  * 2026-08-19 (51e622f): the five validate-battery payloads carried
    3-to-10-day limits read off validate.yml's Sunday cron. Nobody read
    its GATE, which turns that cron into a permanent no-op once
    validation.json is complete. The battery last ran 2026-08-07.
  * 2026-08-20 (this test): back_extension.json carried 40 days
    annotated "BigQuery lane, monthly-ish". bq-backext.yml has no cron
    at all -- it is a one-shot that fires on a change to its own
    workflow file, and the module prints "committed once, never
    re-queried". It had not gone stale yet. It would have on 2026-09-17
    and stayed stale forever.

The pattern is always the same: the limit is written by reading the
lane's intent, not its trigger. This test reads the trigger.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.freshness import EXEMPT, MAX_AGE_DAYS

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _scheduled_lane_exists() -> bool:
    return any(
        'cron:' in p.read_text(encoding="utf-8")
        for p in WORKFLOWS.glob("*.yml")
    )


def test_no_payload_is_both_limited_and_exempt():
    """A payload in both tables is a contradiction: the limit says 'this
    must be fresh', the exemption says 'this cannot be'."""
    both = sorted(set(MAX_AGE_DAYS) & set(EXEMPT))
    assert not both, (
        f"{both} carry a max-age limit AND an exemption; one of the two "
        "statements about the lane is false")


# Placeholders that look like a reason and explain nothing.
_NON_REASONS = {"", "-", "n/a", "na", "todo", "fixme", "tbd", "exempt",
                "see above", "by design", "intentional"}


def test_every_exemption_states_a_reason():
    """An exemption without a reason is an unexplained silence, and this
    audit exists so silences are explained.

    This checks for a MISSING reason, not a short one. The first draft
    of this test demanded 40 characters and flagged
    freshness.json's "this audit's own output" -- which is complete,
    correct and sufficient. A length floor does not measure explanation;
    it just pressures a good terse reason into padding.
    """
    for payload, reason in EXEMPT.items():
        assert isinstance(reason, str), f"EXEMPT[{payload!r}] is not a string"
        cleaned = reason.strip().rstrip(".").lower()
        assert cleaned and cleaned not in _NON_REASONS, (
            f"EXEMPT[{payload!r}] = {reason!r} states no reason why the "
            "payload cannot go stale; a bare exemption is how a dead lane "
            "hides in a green audit")


def test_at_least_one_lane_is_scheduled():
    """Guard the guard: if no workflow declares a cron, every cadence
    claim in the limits table is vacuous and this file is asserting
    nothing."""
    assert _scheduled_lane_exists(), (
        "no workflow declares a cron; the limits table's cadence claims "
        "cannot be true and this test is guarding an empty set")


def test_the_one_shot_lanes_are_exempt_not_limited():
    """A lane with no cron cannot satisfy any max-age limit.

    Checked by trigger, not by intent: a workflow whose only triggers are
    workflow_dispatch and a paths-filtered push on its own file cannot
    refresh anything on a schedule.
    """
    one_shot = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "cron:" in text:
            continue
        # A push trigger filtered to the workflow's own file is a manual
        # rebuild switch, not a cadence.
        if re.search(r"paths:\s*\[\"\.github/workflows/", text):
            one_shot.append(path.name)
    assert one_shot, (
        "no one-shot lane detected; if bq-backext.yml was given a cron "
        "this test needs updating, not deleting")
    assert "bq-backext.yml" in one_shot
    assert "back_extension.json" in EXEMPT, (
        "back_extension.json is written by the one-shot bq-backext.yml, "
        "which has no cron and whose module refuses to re-query an "
        "existing store. Any max-age limit on it is a promise no lane "
        "can keep.")
    assert "back_extension.json" not in MAX_AGE_DAYS
