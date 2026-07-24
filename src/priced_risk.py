"""
The attention-pricing gap: press salience vs what hedging actually costs.

Priced-risk benchmark: India VIX (options-implied volatility on the
Nifty), pulled back to 2015 so the 730-day percentile window has runway
before the 2017 attention sample begins. USDINR 1-month implied
volatility was considered as a second benchmark and SKIPPED: no free,
reliable daily source exists (implied-vol surfaces are vendor data);
if one appears, it slots in beside the VIX with the same normalization.

Construction:
  - India VIX close -> trailing 730-day percentile (same function as the
    attention series, so the two are directly comparable).
  - gap = attention percentile - priced-risk percentile, daily, for the
    composite and each channel, on shared trading days.
    Positive gap: the press is louder than the market.
    Negative gap: the market is pricing something coverage has not caught.
  - Divergence episodes: days in the top decile of |gap|, split by sign,
    clustered with the same 3-day gap rule as volume spikes.
  - Lead-lag: cross-correlation of daily CHANGES in composite attention
    vs daily CHANGES in VIX percentile, lags -10..+10 trading days, with
    moving-block bootstrap bands (block length 10, 1000 resamples --
    block resampling because daily changes are serially correlated).
    Positive lag = attention change leads the VIX change.

All output language is associational. Attention and implied volatility
respond to the same underlying events; nothing here separates the two.

Run after the backfill:  python -m src.priced_risk
Output: docs/data/priced_risk.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import build_index, fetch_markets

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
OUT = ROOT / "docs" / "data" / "priced_risk.json"

VIX_START = "2015-01-01"
GAP_DECILE = 0.90
CLUSTER_GAP_DAYS = 3
MAX_LAG = 10
N_BOOT = 1000
BLOCK_LEN = 10
TOP_EPISODES = 10


def vix_percentile(vix_close: pd.Series) -> pd.Series:
    """Trailing 730-day percentile of the India VIX close -- the identical
    normalization applied to attention volumes."""
    return build_index._trailing_percentile(vix_close.dropna())


def gap_series(att_scores: pd.DataFrame, vix_pct: pd.Series) -> pd.DataFrame:
    """attention percentile - VIX percentile on shared trading days."""
    out = {}
    for col in att_scores.columns:
        joined = pd.concat([att_scores[col], vix_pct], axis=1, join="inner").dropna()
        out[col] = joined.iloc[:, 0] - joined.iloc[:, 1]
    return pd.DataFrame(out).dropna(how="all")


def _cluster_days(days: pd.DatetimeIndex) -> list[list[pd.Timestamp]]:
    clusters: list[list[pd.Timestamp]] = []
    cur: list[pd.Timestamp] = []
    for ts in days:
        if cur and (ts - cur[-1]).days > CLUSTER_GAP_DAYS:
            clusters.append(cur)
            cur = []
        cur.append(ts)
    if cur:
        clusters.append(cur)
    return clusters


def divergence_episodes(gap: pd.Series) -> dict:
    """Top-decile |gap| days, clustered, reported separately by sign."""
    g = gap.dropna()
    if g.empty:
        return {"press_louder": [], "market_ahead": []}
    cut = float(g.abs().quantile(GAP_DECILE))

    def _pack(days: pd.DatetimeIndex, sign: int) -> list[dict]:
        eps = []
        for cluster in _cluster_days(days):
            seg = g.loc[cluster[0]:cluster[-1]]
            extreme = seg.idxmax() if sign > 0 else seg.idxmin()
            eps.append({
                "start": cluster[0].date().isoformat(),
                "end": cluster[-1].date().isoformat(),
                "peak_date": extreme.date().isoformat(),
                "peak_gap": round(float(seg.loc[extreme]), 1),
                "n_days": len(cluster),
            })
        eps.sort(key=lambda e: abs(e["peak_gap"]), reverse=True)
        return eps[:TOP_EPISODES]

    return {
        "press_louder": _pack(g[(g > 0) & (g.abs() >= cut)].index, +1),
        "market_ahead": _pack(g[(g < 0) & (g.abs() >= cut)].index, -1),
    }


def _block_bootstrap_corr(x: np.ndarray, y: np.ndarray,
                          rng: np.random.Generator) -> np.ndarray:
    """Moving-block bootstrap of corr(x, y): resample aligned blocks."""
    n = len(x)
    n_blocks = int(np.ceil(n / BLOCK_LEN))
    out = np.empty(N_BOOT)
    for b in range(N_BOOT):
        starts = rng.integers(0, n - BLOCK_LEN + 1, size=n_blocks)
        idx = np.concatenate(
            [np.arange(s, s + BLOCK_LEN) for s in starts])[:n]
        xb, yb = x[idx], y[idx]
        sx, sy = xb.std(), yb.std()
        out[b] = 0.0 if sx == 0 or sy == 0 else float(np.corrcoef(xb, yb)[0, 1])
    return out


def lead_lag(att_composite: pd.Series, vix_pct: pd.Series,
             seed: int = 42) -> dict:
    """Cross-correlation of daily changes, lags -MAX_LAG..+MAX_LAG.
    Positive lag = attention change leads the VIX-percentile change."""
    joined = pd.concat([att_composite, vix_pct], axis=1, join="inner").dropna()
    d_att = joined.iloc[:, 0].diff().dropna()
    d_vix = joined.iloc[:, 1].diff().dropna()
    aligned = pd.concat([d_att, d_vix], axis=1, join="inner").dropna()
    a, v = aligned.iloc[:, 0].to_numpy(), aligned.iloc[:, 1].to_numpy()

    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | None]] = []
    for lag in range(-MAX_LAG, MAX_LAG + 1):
        if lag >= 0:
            x, y = a[:len(a) - lag or None], v[lag:]
        else:
            x, y = a[-lag:], v[:len(v) + lag]
        if len(x) < 60:
            rows.append({"lag": lag, "corr": None, "lo": None, "hi": None})
            continue
        corr = float(np.corrcoef(x, y)[0, 1])
        boots = _block_bootstrap_corr(x, y, rng)
        rows.append({
            "lag": lag,
            "corr": round(corr, 4),
            "lo": round(float(np.percentile(boots, 2.5)), 4),
            "hi": round(float(np.percentile(boots, 97.5)), 4),
        })

    usable = [r for r in rows
              if r["corr"] is not None and r["lo"] is not None
              and r["hi"] is not None and r["lag"] is not None]
    peak = max(usable, key=lambda r: abs(r["corr"] or 0.0), default=None)
    if peak is None:
        reading = "insufficient overlapping data"
    else:
        p_lag, p_lo, p_hi = int(peak["lag"] or 0), peak["lo"] or 0.0, peak["hi"] or 0.0
        if p_lo <= 0.0 <= p_hi:
            reading = ("no lag is distinguishable from zero at the 95% level; "
                       "attention and priced risk move together or not at all")
        elif p_lag > 0:
            reading = (f"largest association at lag +{p_lag}: attention "
                       "changes tend to precede VIX-percentile changes "
                       "(association, not causation)")
        elif p_lag < 0:
            reading = (f"largest association at lag {p_lag}: VIX-percentile "
                       "changes tend to precede attention changes "
                       "(association, not causation)")
        else:
            reading = ("largest association at lag 0: same-day co-movement, "
                       "consistent with both responding to the same events")
    return {"convention": "positive lag = attention leads", "ccf": rows,
            "reading": reading}


def main() -> None:
    if not STORE.exists():
        raise SystemExit("no data/raw/gdelt_volume.csv yet -- run the pipeline first")
    vol = pd.read_csv(STORE, parse_dates=["date"]).set_index("date").sort_index()
    att = build_index.build_scores(vol)

    print("[priced_risk] pulling India VIX")
    vix_close = fetch_markets._download(["^INDIAVIX"], VIX_START)["^INDIAVIX"]
    vix_pct = vix_percentile(vix_close)

    gaps = gap_series(att, vix_pct)
    print(f"[priced_risk] gap series: {len(gaps)} trading days, "
          f"cols={list(gaps.columns)}")

    payload: dict = {
        "definition": ("gap = attention percentile minus India-VIX "
                       "percentile, shared trading days. Positive: press "
                       "louder than the market. Negative: the market is "
                       "pricing risk the coverage has not caught. "
                       "Associational throughout."),
        "gap": {
            "dates": [d.date().isoformat() for d in gaps.index],
            **{col: [build_index._r1(x) for x in gaps[col]]
               for col in gaps.columns},
        },
        "divergence_episodes": divergence_episodes(gaps["composite"]),
        "lead_lag": lead_lag(att["composite"], vix_pct),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"[priced_risk] wrote {OUT}")
    print(f"[priced_risk] lead-lag reading: {payload['lead_lag']['reading']}")


if __name__ == "__main__":
    main()
