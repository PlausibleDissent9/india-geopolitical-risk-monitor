"""The chokepoint deadline must refuse, never half-write.

The daily lane caps this step at 15 minutes while fetch_gdelt allows 420s
per request across roughly four channels -- a worst case near 29 minutes.
The step was being SIGKILLed mid-request on slow GDELT days: nothing
written, nothing diagnosable, a quarter hour gone.

A deadline is only an improvement if it refuses. combine_first would
cheerfully fill missing channels from the existing store, producing a
file where some chokepoints are today's and others are last week's with
nothing recording which. These tests pin that it does not do that.
"""
from __future__ import annotations

import time
from unittest import mock

import pandas as pd
import pytest
from src import chokepoints, fetch_gdelt


def _series() -> pd.Series:
    return pd.Series(dtype=float)


def test_no_deadline_keeps_the_previous_behaviour() -> None:
    # A backfill under the supervisor script must not acquire a deadline
    # it never asked for.
    calls: list = []

    def fetch(terms, start, end):
        calls.append(terms)
        return _series()

    with mock.patch.object(fetch_gdelt, "fetch_channel", fetch), \
         mock.patch.object(chokepoints, "_load_store", lambda: None), \
         mock.patch.object(pd.DataFrame, "to_csv", lambda *a, **k: None):
        chokepoints.update(deadline_seconds=None)
    assert len(calls) >= 1, "every channel should be attempted with no deadline"


def test_a_deadline_that_cannot_fit_a_fetch_refuses_before_starting() -> None:
    calls: list = []

    def fetch(terms, start, end):
        calls.append(terms)
        return _series()

    with mock.patch.object(fetch_gdelt, "fetch_channel", fetch), \
         mock.patch.object(fetch_gdelt, "TIMEOUT_S", 1.0):
        with pytest.raises(chokepoints.ChokepointDeadlineExceeded):
            chokepoints.update(deadline_seconds=0.0)
    assert calls == [], (
        "a fetch that cannot finish inside the budget must not be started"
    )


def test_the_store_is_not_written_when_the_deadline_bites(tmp_path) -> None:
    # The property that matters. A partial merge would be silently
    # half-fresh, which is worse than no refresh at all.
    written: list = []

    def fetch(terms, start, end):
        time.sleep(0.02)
        return _series()

    with mock.patch.object(fetch_gdelt, "fetch_channel", fetch), \
         mock.patch.object(fetch_gdelt, "TIMEOUT_S", 5.0), \
         mock.patch.object(pd.DataFrame, "to_csv",
                           lambda *a, **k: written.append(1)):
        with pytest.raises(chokepoints.ChokepointDeadlineExceeded):
            chokepoints.update(deadline_seconds=0.01)
    assert written == [], "the store must keep one vintage, not become half-fresh"


def test_the_refusal_names_what_it_managed(tmp_path) -> None:
    def fetch(terms, start, end):
        return _series()

    with mock.patch.object(fetch_gdelt, "fetch_channel", fetch), \
         mock.patch.object(fetch_gdelt, "TIMEOUT_S", 9999.0):
        with pytest.raises(chokepoints.ChokepointDeadlineExceeded) as excinfo:
            chokepoints.update(deadline_seconds=1.0)
    message = str(excinfo.value)
    # A refusal a human cannot act on is only marginally better than a kill.
    assert "channels fetched" in message
    assert "Store left unchanged" in message


def test_the_cap_arithmetic_is_still_the_reason_this_exists() -> None:
    # If somebody raises the step cap past the worst case, this deadline
    # becomes unnecessary and the comment above it becomes wrong. Pin the
    # numbers so that change is deliberate.
    assert fetch_gdelt.TIMEOUT_S == 420
    assert fetch_gdelt.SLEEP_S == 15.0
    worst_case_seconds = 4 * (fetch_gdelt.TIMEOUT_S + fetch_gdelt.SLEEP_S)
    assert worst_case_seconds > 15 * 60, (
        "the step cap no longer being smaller than the worst case would "
        "make this deadline redundant; revisit rather than keep both"
    )
