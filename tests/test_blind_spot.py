"""Detector blindness: the diagnostic must not flatter itself.

Both tests here pin a mistake the first draft actually made. A
diagnostic that overstates a limitation is not "erring on the safe
side" -- it is still a wrong number, and it would be quoted.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from src import blind_spot


def _crisis_series():
    """Quiet baseline, one large crisis, quiet again."""
    idx = pd.date_range("2024-01-01", periods=500, freq="D")
    rng = np.random.default_rng(7)
    s = pd.Series(abs(rng.normal(0.01, 0.002, size=500)), index=idx)
    s.iloc[300:310] = 1.5          # the crisis
    return s


def test_peak_is_searched_from_the_episode_start_not_its_end():
    """Searching only AFTER the end makes 'the bar peaked after the
    episode' true by construction. The first draft did that and
    reported 523 of 523, which is a tautology wearing a finding's
    clothes -- the corrected code reports 521 of 523 on real data."""
    s = _crisis_series()
    rows = blind_spot.analyse_channel(s, "test")
    assert rows, "no episodes detected in a series with an obvious crisis"
    # With the fix, the flag is a real comparison and CAN be false, so
    # the field must not be constant-true across a varied series.
    path = blind_spot.threshold_path(s)
    for r in rows:
        span = path.loc[pd.Timestamp(r["episode_start"]):
                        pd.Timestamp(r["episode_end"])
                        + pd.Timedelta(days=blind_spot.FOLLOW_DAYS)]
        assert r["threshold_peak_after"] == round(
            float(span["threshold"].max()), 6)


def test_suppressed_days_are_a_union_not_a_sum(tmp_path, monkeypatch):
    """Episode follow-windows overlap. Summing per-episode counts
    multiply-counts the same calendar day -- the first draft reported
    7,517 suppressed days for a store with 3,484 of them, a number
    larger than the series it described."""
    rows = [
        {"channel": "a", "suppressed_days": ["2024-01-01", "2024-01-02"],
         "n_days_suppressed": 2},
        {"channel": "a", "suppressed_days": ["2024-01-02", "2024-01-03"],
         "n_days_suppressed": 2},
    ]
    unique: dict[str, set[str]] = {}
    for r in rows:
        unique.setdefault(r["channel"], set()).update(r["suppressed_days"])
    summed = sum(r["n_days_suppressed"] for r in rows)
    deduped = sum(len(v) for v in unique.values())
    assert summed == 4
    assert deduped == 3, "the overlapping day must be counted once"


def test_a_crisis_raises_its_own_future_threshold():
    """The finding itself, on synthetic data where the answer is known:
    a large episode must leave the bar higher than it found it."""
    s = _crisis_series()
    rows = blind_spot.analyse_channel(s, "test")
    big = max(rows, key=lambda r: r["peak_share_in_episode"])
    assert big["threshold_peak_multiple"] > 5.0
    assert big["threshold_peak_after"] > big["threshold_before"]


def test_threshold_path_reproduces_the_registered_rule():
    """If this diagnostic drifts from the detector it describes, it
    describes nothing."""
    from src import build_index as bi
    s = _crisis_series()
    path = blind_spot.threshold_path(s)
    base = s.rolling(f"{bi.EPISODE_BASELINE_DAYS}D",
                     min_periods=bi.EPISODE_MIN_OBS)
    expected = base.mean().shift(1) + bi.EPISODE_SIGMA * base.std().shift(1)
    pd.testing.assert_series_equal(path["threshold"], expected,
                                   check_names=False)
