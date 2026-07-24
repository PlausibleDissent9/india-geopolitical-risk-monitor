"""A4 acceptance tests: gap bounded, lead-lag shape, no lookahead."""
from __future__ import annotations

import numpy as np
import pandas as pd
from src import build_index, priced_risk


def _fake_scores(n: int = 900, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    vol = pd.DataFrame(
        {ch: rng.lognormal(0, 0.4, n) for ch in ["a", "b"]}, index=idx
    )
    return build_index.build_scores(vol)


def _fake_vix(n: int = 900, seed: int = 8) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.Series(15 + np.abs(rng.normal(0, 4, n)).cumsum() * 0.01, index=idx)


def test_gap_is_bounded():
    scores = _fake_scores()
    vix_pct = priced_risk.vix_percentile(_fake_vix())
    gaps = priced_risk.gap_series(scores, vix_pct)
    assert not gaps.empty
    assert float(gaps.max().max()) <= 100.0
    assert float(gaps.min().min()) >= -100.0


def test_lead_lag_is_symmetric_in_length():
    scores = _fake_scores()
    vix_pct = priced_risk.vix_percentile(_fake_vix())
    ll = priced_risk.lead_lag(scores["composite"], vix_pct)
    lags = [r["lag"] for r in ll["ccf"]]
    assert len(lags) == 2 * priced_risk.MAX_LAG + 1
    assert lags == sorted(lags)
    assert -min(lags) == max(lags) == priced_risk.MAX_LAG


def test_vix_percentile_has_no_lookahead():
    vix = _fake_vix()
    full = priced_risk.vix_percentile(vix)
    truncated = priced_risk.vix_percentile(vix.iloc[:600])
    tail = truncated.dropna().index[-1]
    pd.testing.assert_series_equal(
        full.loc[:tail], truncated.loc[:tail], check_freq=False
    )


def test_divergence_episodes_split_by_sign():
    scores = _fake_scores()
    vix_pct = priced_risk.vix_percentile(_fake_vix())
    gaps = priced_risk.gap_series(scores, vix_pct)
    eps = priced_risk.divergence_episodes(gaps["composite"])
    assert set(eps) == {"press_louder", "market_ahead"}
    for e in eps["press_louder"]:
        assert e["peak_gap"] > 0
    for e in eps["market_ahead"]:
        assert e["peak_gap"] < 0
