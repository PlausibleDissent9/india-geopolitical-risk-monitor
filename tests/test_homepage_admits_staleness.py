"""The front page must say when the finalized measure is late.

WHAT HAPPENED
On 2026-08-07 the publishing lane stopped. For three days the homepage kept
presenting a three-day-old number under the heading "Latest final measure",
with a same-day provisional nowcast beside it making the panel look current.
Nothing on the page said the series was behind. The founder found out by
reading the date and asking why it still said the 7th.

The nowcast already refused to render unless its payload was genuinely
today's. The finalized number had no equivalent check -- so the provisional
value was better guarded than the published one, which is exactly backwards.

WHY IT IS COMPUTED IN THE BROWSER
A page baked on the 7th cannot know it is being read on the 10th. Staleness
is a property of when you look, so it is derived at read time from
latest.date. Same reason status.html recomputes payload age client-side
rather than trusting the status it was published with.

DOWNGRADE ONLY
The check can add a warning. It can never remove one, and it never makes the
series look fresher than it is.

WHAT THIS FILE CHECKS
That the guard is wired in and its deadline rule survives. The arithmetic
itself was verified in a browser against five fixed clocks, including the
two that matter most: silent when the data is current, and silent before the
00:30 UTC deadline when the newest day is not late but merely not yet due.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "docs" / "app.js"
STYLE = ROOT / "docs" / "style.css"


def _source() -> str:
    return APP.read_text(encoding="utf-8")


def test_the_staleness_check_exists_and_is_called() -> None:
    """A helper nobody calls is decoration."""
    src = _source()
    assert "function markIfBehindTarget(" in src, (
        "the finalized-measure staleness check is gone from docs/app.js")
    assert "markIfBehindTarget(latest.date)" in src, (
        "markIfBehindTarget is defined but never called from renderLatest, so "
        "a stale headline would render silently again")


def test_the_publication_deadline_rule_survives() -> None:
    """The measured day closes 00:00 UTC and publishes by 00:30 UTC. Before
    that the newest day is NOT late, it is not due -- warning there would
    cry wolf every night and train readers to ignore the flag."""
    src = _source()
    block = re.search(r"function markIfBehindTarget\(.*?\n\}", src, re.S)
    assert block, "markIfBehindTarget body not found"
    body = block.group(0)
    assert "getUTCMinutes() >= 30" in body and "getUTCHours() > 0" in body, (
        "the 00:30 UTC publication deadline is no longer part of the rule")
    assert "behind >= 1" in body, (
        "the guard no longer requires a full day behind before warning")


def test_it_only_ever_adds_a_warning() -> None:
    """Downgrade-only, asserted at the source level: this function must not
    touch the score, the date, or any existing element's content."""
    block = re.search(r"function markIfBehindTarget\(.*?\n\}", _source(), re.S)
    assert block
    body = block.group(0)
    for forbidden in ("latest-date\").textContent =",
                      "composite-score",
                      "innerHTML ="):
        assert forbidden not in body, (
            f"the staleness check writes {forbidden!r}; it may only APPEND a "
            "warning, never rewrite what the page already states")
    assert "appendChild" in body


def test_the_warning_is_visible_and_styled() -> None:
    """An unstyled span inherits muted body text and reads as a footnote."""
    assert ".stale-flag" in STYLE.read_text(encoding="utf-8"), (
        "no .stale-flag rule in style.css, so the warning renders as ordinary "
        "muted prose next to the number it is warning about")


def test_the_nowcast_guard_is_still_there_too() -> None:
    """The provisional value's own freshness check predates this one and
    must not be lost while tidying: both halves of the panel need it."""
    assert "renderNowcast" in _source()
