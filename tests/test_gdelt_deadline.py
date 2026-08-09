"""The multilingual runner's budget must reach the actual HTTP call.

The first bounded implementation checked time only between full series while
each request could still block for 420 seconds. A series begun near the outer
deadline was therefore killed by GitHub's 45-minute axe before its store write.
These tests pin the deadline through every layer that previously swallowed it.
"""
from __future__ import annotations

from datetime import date

import pytest
import requests
from src import fetch_gdelt


def test_network_timeout_is_capped_by_the_caller_deadline(monkeypatch):
    clock = {"now": 100.0}
    observed: list[float] = []

    monkeypatch.setattr(fetch_gdelt.time, "monotonic", lambda: clock["now"])

    def timeout_after_budget_was_assigned(*args, **kwargs):
        observed.append(float(kwargs["timeout"]))
        clock["now"] = 103.1
        raise requests.Timeout("simulated slow accepted request")

    monkeypatch.setattr(fetch_gdelt.requests, "get", timeout_after_budget_was_assigned)

    with pytest.raises(fetch_gdelt.AcquisitionDeadlineExceeded):
        fetch_gdelt._fetch_chunk_network(
            "test",
            date(2026, 1, 1),
            date(2026, 1, 2),
            retries=6,
            deadline_monotonic=103.0,
        )

    assert observed == [3.0]


def test_deadline_is_not_reinterpreted_as_a_retryable_wide_chunk(monkeypatch):
    calls = []

    def expired(*args, **kwargs):
        calls.append((args, kwargs))
        raise fetch_gdelt.AcquisitionDeadlineExceeded("spent")

    monkeypatch.setattr(fetch_gdelt, "_fetch_chunk", expired)

    with pytest.raises(fetch_gdelt.AcquisitionDeadlineExceeded):
        fetch_gdelt._fetch_query_series(
            "test",
            date(2020, 1, 1),
            date(2026, 1, 1),
            deadline_monotonic=200.0,
        )

    assert len(calls) == 1, "deadline exhaustion must not fan out into yearly retries"


def test_successful_chunk_is_not_discarded_at_the_deadline(monkeypatch, tmp_path):
    rows = [{"date": "20260809T000000Z", "value": 1.0}]
    sleeps = []

    monkeypatch.setattr(fetch_gdelt, "CHUNK_CACHE_DIR", tmp_path)
    monkeypatch.setattr(fetch_gdelt.time, "monotonic", lambda: 102.9)
    monkeypatch.setattr(fetch_gdelt.time, "sleep", sleeps.append)
    monkeypatch.setattr(fetch_gdelt, "_fetch_chunk_network", lambda *a, **k: rows)

    observed = fetch_gdelt._fetch_chunk(
        "test",
        date.today(),
        date.today(),
        retries=1,
        deadline_monotonic=103.0,
    )

    assert observed == rows
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.11


def test_no_deadline_preserves_the_registered_request_timeout(monkeypatch):
    observed = []

    class Response:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {"timeline": []}

    def respond(*args, **kwargs):
        observed.append(kwargs["timeout"])
        return Response()

    monkeypatch.setattr(fetch_gdelt.requests, "get", respond)
    assert fetch_gdelt._fetch_chunk_network(
        "test", date(2026, 1, 1), date(2026, 1, 2), retries=1
    ) == []
    assert observed == [fetch_gdelt.TIMEOUT_S]
