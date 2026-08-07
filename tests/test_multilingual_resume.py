"""The multilingual backfill must make cumulative progress.

The original update() built all fifteen series into a dict and wrote the
store once at the end, so a single GDELT 429 anywhere in the loop raised
past the write and the store was never created. Every completed fetch
still landed in the chunk cache, the workflow read that growing cache as
progress, and the chain re-dispatched itself 70 times over 7 days
without ever producing the artifact.

These tests pin the two properties that make the loop terminate: a
partial batch keeps what it got, and "done" means every series present.
"""
from __future__ import annotations

import pandas as pd
import pytest
from src import multilingual


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setattr(multilingual, "STORE", tmp_path / "ml.csv")
    monkeypatch.setattr(multilingual, "_specs", lambda: (
        {"hin": {"label": "Hindi"}, "urd": {"label": "Urdu"}},
        {"pakistan_west": {"terms": ["x"], "anchor": None},
         "china_east": {"terms": ["y"], "anchor": None}},
    ))
    return tmp_path / "ml.csv"


def _series(n=40):
    idx = pd.date_range("2019-01-01", periods=n, freq="D")
    return pd.Series(range(n), index=idx, dtype=float)


def test_a_batch_that_dies_midway_keeps_what_it_got(wired, monkeypatch):
    """The whole defect, inverted: three series land, the fourth raises,
    and the three must survive on disk."""
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("HTTP 429 rate limit")
        return _series()

    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel", flaky)
    multilingual.update(backfill=True)

    assert wired.exists(), "a partial batch wrote nothing at all"
    stored = pd.read_csv(wired)
    assert len([c for c in stored.columns if c != "date"]) == 3


def test_the_next_run_skips_what_is_already_stored(wired, monkeypatch):
    """Resume, not restart: the second batch must only fetch the
    series the first one missed."""
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("HTTP 429 rate limit")
        return _series()

    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel", flaky)
    multilingual.update(backfill=True)
    assert multilingual.missing_keys() == ["china_east_urd"]

    fetched: list = []

    def ok(*a, **k):
        fetched.append(1)
        return _series()

    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel", ok)
    multilingual.update(backfill=True)
    assert len(fetched) == 1, "the resume refetched series already stored"
    assert multilingual.missing_keys() == []


def test_a_batch_that_gains_nothing_fails_loudly(wired, monkeypatch):
    """No series landed and something broke: the lane must not be able
    to call that progress and re-dispatch itself."""
    def always_429(*a, **k):
        raise RuntimeError("HTTP 429 rate limit")

    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel",
                        always_429)
    with pytest.raises(SystemExit):
        multilingual.update(backfill=True)


def test_done_means_every_series_not_merely_a_file(wired, monkeypatch):
    """The workflow's old completeness test was 'does the store file
    exist', which incremental writes make true after one series."""
    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel",
                        lambda *a, **k: _series())
    assert len(multilingual.missing_keys()) == 4
    multilingual.update(backfill=True)
    assert multilingual.missing_keys() == []


def test_an_empty_series_counts_as_missing_not_stored(wired, monkeypatch):
    """A column of NaNs is not data; it must not satisfy completeness."""
    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel",
                        lambda *a, **k: pd.Series(dtype=float))
    with pytest.raises(SystemExit):
        multilingual.update(backfill=True)
    assert len(multilingual.missing_keys()) == 4


def test_a_run_attempts_only_a_bounded_number_of_series(wired, monkeypatch):
    """Cumulative progress is useless if no single unit ever completes.

    Measured 2026-08-07: the CI step allows 45 minutes, attempting all
    fifteen series took longer whenever GDELT throttled, and the run was
    killed at exactly 45m13s having finished none. Per-series
    persistence cannot save work that never finishes.
    """
    monkeypatch.setattr(multilingual, "MAX_SERIES_PER_RUN", 2)
    attempted = []

    def spy(*a, **k):
        attempted.append(1)
        return _series()

    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel", spy)
    multilingual.update(backfill=True)
    assert len(attempted) == 2, "a run must not attempt more than its cap"
    assert len(multilingual.missing_keys()) == 2, "the rest wait for next run"


def test_the_deadline_stops_starting_new_series(wired, monkeypatch):
    """It must stop CLEANLY before the workflow kills it, so whatever
    landed is committed and the chain can continue."""
    monkeypatch.setattr(multilingual, "MAX_SERIES_PER_RUN", 99)
    monkeypatch.setattr(multilingual, "DEADLINE_SECONDS", 0)
    calls = []
    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel",
                        lambda *a, **k: (calls.append(1), _series())[1])
    multilingual.update(backfill=True)
    assert not calls, "an expired budget must not start a single fetch"


def test_the_deadline_breaks_out_of_both_loops(wired, monkeypatch):
    """A bare break would leave the language loop and start the next
    CHANNEL, crossing the deadline it had just refused to cross."""
    monkeypatch.setattr(multilingual, "MAX_SERIES_PER_RUN", 99)
    calls = []

    class Clock:
        def __init__(self): self.t = 0.0
        def __call__(self):
            self.t += 10_000  # every check is past any deadline
            return self.t

    monkeypatch.setattr(multilingual.time, "monotonic", Clock())
    monkeypatch.setattr(multilingual.fetch_gdelt, "fetch_channel",
                        lambda *a, **k: (calls.append(1), _series())[1])
    multilingual.update(backfill=True)
    assert not calls, "the deadline leaked into a second channel"
