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
