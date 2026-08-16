"""fetch_events stops on a deadline and KEEPS what it fetched.

daily.yml caps this step at 15 minutes against a worst case of
5 * (3*TIMEOUT_S + 5 + 10 + 15 + SLEEP_S) = 32.6 minutes, so a slow CDN
day SIGKILLs it and the run reports nothing.

The opposite choice to src/chokepoints.py, deliberately. There, a partial
store would publish a comparison across chokepoints of two different
weeks, so it refuses. Here days are independent: each lands whole or is
skipped, _download returns None rather than half a file, and
_missing_days finds anything absent next run. Throwing away landed days
to punish a slow network would be the wrong kind of strictness.
"""
from __future__ import annotations

import time
from datetime import date
from unittest import mock

from src import fetch_events


def test_an_expired_deadline_starts_no_day() -> None:
    attempted: list[date] = []
    with mock.patch.object(fetch_events, "compute_day",
                           lambda d: attempted.append(d) or None):
        fetch_events.run([date(2026, 1, 1), date(2026, 1, 2)],
                         deadline_monotonic=time.monotonic() - 1)
    assert attempted == []


def test_no_deadline_attempts_every_day() -> None:
    attempted: list[date] = []
    with mock.patch.object(fetch_events, "compute_day",
                           lambda d: attempted.append(d) or None):
        fetch_events.run([date(2026, 1, 1), date(2026, 1, 2)])
    assert len(attempted) == 2


def test_days_that_landed_before_the_deadline_are_saved() -> None:
    """The property that separates this module from chokepoints.

    A controllable clock, not a real sleep: the loop checks
    time.monotonic() before each day, so advancing it past the budget
    after the first day lands proves the stop happens mid-run AND that
    the day already fetched survives it.
    """
    saved: list[int] = []
    attempted: list[date] = []
    # Inside the budget for the first check, past it for every later one.
    # Counting calls is brittle; this states the intent directly.
    checks = {"n": 0}

    def clock() -> float:
        checks["n"] += 1
        return 0.0 if checks["n"] == 1 else 1000.0

    def compute(day: date):
        attempted.append(day)
        return ({"date": day.isoformat(), "n_india": 1}, [], [])

    with mock.patch.object(fetch_events, "compute_day", compute), \
         mock.patch.object(fetch_events.time, "monotonic", clock), \
         mock.patch.object(fetch_events.time, "sleep", lambda s: None), \
         mock.patch.object(fetch_events, "_save",
                           lambda *a, **k: saved.append(1)):
        done = fetch_events.run(
            [date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)],
            deadline_monotonic=10.0,
        )
    assert attempted == [date(2026, 1, 1)], (
        "the clock passes the budget after day one, so no later day starts"
    )
    assert done == 1
    assert saved, "the day that landed must be written, not discarded"


def test_the_arithmetic_that_justifies_this_is_pinned() -> None:
    # If the cap is ever raised past the worst case this becomes redundant.
    # Fail then, so it is removed deliberately rather than left to rot.
    worst = 5 * (3 * fetch_events.TIMEOUT_S + 5 + 10 + 15 + fetch_events.SLEEP_S)
    assert fetch_events.TIMEOUT_S == 120
    assert fetch_events.RETRIES == 3
    assert worst > 15 * 60, (
        "the daily cap is no longer smaller than the worst case; revisit "
        "whether this deadline is still needed"
    )


def test_this_module_does_not_borrow_another_modules_constants() -> None:
    # The audit error that produced a fabricated 36-minute figure: I read
    # fetch_gdelt's TIMEOUT_S for a module that never imports it.
    source = (
        __import__("pathlib").Path(fetch_events.__file__)
    ).read_text(encoding="utf-8")
    assert "fetch_gdelt" not in source
