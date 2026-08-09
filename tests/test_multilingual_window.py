"""A series that cannot be fetched must not starve the ones behind it.

WHAT WENT WRONG
Bounding the work per run was correct and necessary: an unbounded batch
was killed mid-fetch by the step timeout and banked nothing. But the
bound took its slice from a FIXED end of a list that never reorders --
missing_keys() walks the registered channels in declaration order -- so
every run attempted the same first series, spent its wall clock there,
and stopped.

That turns a fetch failure into a permanent one. The head of the list
does not merely fail; it consumes the budget that everything behind it
needed, on every run, forever.

Measured on 2026-08-09, seventy-odd runs into the backfill: the store
held 6 of 15 series and the missing nine were exactly the last three
channels in declaration order --

    gulf_energy_{hin,urd,zho}  us_trade_{hin,urd,zho}  shipping_{hin,urd,zho}

-- while the attempt window was always the first four of those. The lane
was not slow at shipping_*. It had never once asked for it.

This is the same shape as the morning-watchdog eviction bug: machinery
built to retry, retrying the identical thing, and mistaking motion for
progress. The fix there was to stand down; the fix here is to move on.
"""
from __future__ import annotations

from datetime import date, timedelta

from src import multilingual

MAX = multilingual.MAX_SERIES_PER_RUN

# The exact nine the store was missing when this was diagnosed, in the
# order missing_keys() returns them.
STALLED = [
    "gulf_energy_hin", "gulf_energy_urd", "gulf_energy_zho",
    "us_trade_hin", "us_trade_urd", "us_trade_zho",
    "shipping_hin", "shipping_urd", "shipping_zho",
]


def test_a_fixed_head_slice_would_starve_the_tail():
    """The replaced behaviour, stated as arithmetic rather than left as a
    memory in a commit message.

    `todo[:MAX_SERIES_PER_RUN]` is a pure function of a list that does not
    reorder, so it returns the same window on every run of every day, and
    the series past the cap are not 'tried later' -- they are unreachable
    while the head keeps failing. Nothing about that is time-dependent,
    which is why seventy runs produced the same six series."""
    assert len({tuple(STALLED[:MAX]) for _ in range(14)}) == 1, (
        "a fixed head slice is constant across days by construction")
    assert "shipping_hin" not in STALLED[:MAX], (
        "the concrete casualty: shipping_* sits past the cap and a fixed "
        "slice can never reach it")


def test_the_window_moves_between_days():
    """The defect in one line: two different days must not hand back the
    same four series, or the tail is unreachable."""
    windows = {
        tuple(multilingual.attempt_window(STALLED, date(2026, 8, 9) + timedelta(days=d)))
        for d in range(len(STALLED))
    }
    assert len(windows) > 1, (
        "every day attempts the identical window, so a series that fails "
        "at the head of the list starves the rest permanently")


def test_every_stalled_series_comes_up_within_a_fortnight():
    """Not just 'it moves' -- it has to COVER. A rotation that revisits
    the same subset is the same starvation with extra steps."""
    seen: set[str] = set()
    for d in range(14):
        seen |= set(multilingual.attempt_window(
            STALLED, date(2026, 8, 9) + timedelta(days=d)))
    missed = sorted(set(STALLED) - seen)
    assert not missed, (
        f"{missed} would not be attempted once in a fortnight of runs")


def test_shipping_is_reachable_at_all():
    """The concrete regression: shipping_* sat at the far end of the list
    and was never requested in seventy runs."""
    reached = any(
        "shipping_hin" in multilingual.attempt_window(
            STALLED, date(2026, 8, 9) + timedelta(days=d))
        for d in range(len(STALLED)))
    assert reached, "shipping_hin is still unreachable from the head of the list"


def test_a_run_is_deterministic_for_a_given_day():
    """The chain re-dispatches itself while progressing. A window that
    wandered between dispatches would abandon half-done work, so the same
    day must always produce the same window."""
    day = date(2026, 8, 9)
    first = multilingual.attempt_window(STALLED, day)
    for _ in range(5):
        assert multilingual.attempt_window(STALLED, day) == first


def test_a_short_list_is_returned_whole():
    """Once the backfill is nearly done, fewer series remain than the cap.
    Rotating then would be pure loss -- attempt all of them."""
    short = STALLED[:MAX - 1] if MAX > 1 else STALLED[:1]
    assert multilingual.attempt_window(short, date(2026, 8, 9)) == short


def test_the_window_never_exceeds_the_budgeted_count():
    """The rotation must not quietly undo the bound that makes a batch
    survivable in the first place (see test_multilingual_budget.py)."""
    for d in range(30):
        window = multilingual.attempt_window(
            STALLED, date(2026, 8, 9) + timedelta(days=d))
        assert len(window) == min(MAX, len(STALLED))
        assert len(set(window)) == len(window)
        assert set(window) <= set(STALLED)
