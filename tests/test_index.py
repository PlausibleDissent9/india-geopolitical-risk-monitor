"""
Correctness tests for index construction (spec Part IV, item 1).
The no-lookahead test is non-negotiable: scores and episodes as of day t
must be unchanged by data arriving after t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import build_index


def synthetic_volume(days: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=days, freq="D")
    base = rng.lognormal(mean=-3.0, sigma=0.3, size=days)
    base[300:304] *= 6.0  # planted spike cluster
    return pd.DataFrame({"chan_a": base}, index=idx)


def test_no_lookahead_in_scores():
    vol = synthetic_volume()
    full = build_index.build_scores(vol)
    truncated = build_index.build_scores(vol.iloc[:350])
    cutoff = truncated.index[-1]
    pd.testing.assert_frame_equal(full.loc[:cutoff], truncated)


def test_no_lookahead_in_episodes():
    vol = synthetic_volume()
    full = build_index.detect_all_episodes(vol.iloc[:350])
    again = [
        e for e in build_index.detect_all_episodes(vol)
        if e["end"] <= vol.index[349].date().isoformat()
    ]
    assert full == again


def test_planted_spike_is_detected():
    episodes = build_index.detect_all_episodes(synthetic_volume())
    assert any(
        e["start"] <= "2024-10-28" <= e["end"] for e in episodes
    ), f"planted spike (2024-10-27..30) not detected: {episodes}"


def test_scores_bounded_and_min_obs_respected():
    vol = synthetic_volume()
    scores = build_index.build_scores(vol)
    s = scores["chan_a"]
    assert s.iloc[: build_index.MIN_OBS - 1].isna().all()
    valid = s.dropna()
    assert not valid.empty
    assert ((valid >= 0) & (valid <= 100)).all()


def test_spike_day_does_not_inflate_its_own_baseline():
    # A single huge day must exceed a threshold computed from *lagged*
    # history; with a same-day baseline a 6x spike could mask itself.
    vol = synthetic_volume()
    episodes = build_index.detect_all_episodes(vol)
    starts = [e["start"] for e in episodes]
    assert "2024-10-27" in starts
