"""Sampling-band arithmetic: Wilson interval sanity and the constant
that must track build_index's percentile window."""
from __future__ import annotations

import pandas as pd

from src import build_index, uncertainty


def test_window_matches_build_index():
    # The band maps bounds through "the same trailing percentile" -- that
    # claim is false the day the two constants diverge.
    assert uncertainty.WINDOW_DAYS == build_index.PERCENTILE_WINDOW_DAYS


def test_wilson_contains_point_and_orders():
    lo, hi = uncertainty.wilson95(30, 30000)
    p = 30 / 30000
    assert 0.0 < lo < p < hi < 1.0


def test_wilson_zero_count_starts_at_zero():
    lo, hi = uncertainty.wilson95(0, 30000)
    assert lo == 0.0 and hi > 0.0


def test_trailing_pct_matches_build_index_for_own_value():
    s = pd.Series(
        [1.0, 2.0, 3.0, 4.0, 5.0],
        index=pd.date_range("2026-01-01", periods=5, freq="D"),
    )
    # Percentile of the last value against its own window, both ways.
    ours = uncertainty.trailing_pct(s, 5.0)
    theirs = build_index._trailing_percentile(s, window_days=10, min_obs=1).iloc[-1]
    assert abs(ours - float(theirs)) < 1e-9
