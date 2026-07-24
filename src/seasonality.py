"""
Anniversary-effect quantification (methodology s7: turns an asserted
limitation into a measured one).

Per channel, on log volume share:
  1. remove a linear time trend (OLS),
  2. estimate day-of-year effects as circular-smoothed (7-day window)
     month-day group means of the trend residuals,
  3. report the share of detrended variance the day-of-year terms explain
     (partial R^2), and the top recurring calendar dates,
  4. build a deseasonalized volume variant, run the standard percentile
     normalization on it, and report its correlation with the primary.

The smoothing exists because each calendar date has only ~9 observations
in a 2017- sample; unsmoothed group means would overfit noise and inflate
partial R^2. Feb 29 folds into Feb 28. The deseasonalized index is a
SECONDARY specification: published for comparison, never replacing the
primary (an anniversary is still attention; methodology s7 discusses).

Run after the backfill:  python -m src.seasonality
Output: docs/data/seasonality.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import build_index

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
OUT = ROOT / "docs" / "data" / "seasonality.json"

SMOOTH_DAYS = 7  # circular window for day-of-year effect estimates
TOP_N_DATES = 5
LOG_FLOOR = 1e-6  # shares can be zero; floor before log


def _detrend(y: np.ndarray) -> np.ndarray:
    t = np.arange(len(y), dtype=float)
    slope, intercept = np.polyfit(t, y, 1)
    return y - (slope * t + intercept)


def _doy_key(idx: pd.DatetimeIndex) -> pd.Series:
    md = idx.strftime("%m-%d")
    return pd.Series(np.where(md == "02-29", "02-28", md), index=idx)


def _circular_smooth(effects: pd.Series) -> pd.Series:
    """Smooth month-day effects with a centered circular rolling mean."""
    ordered = effects.sort_index()
    n = len(ordered)
    pad = SMOOTH_DAYS // 2
    wrapped = pd.concat([ordered.iloc[-pad:], ordered, ordered.iloc[:pad]])
    sm = wrapped.rolling(SMOOTH_DAYS, center=True, min_periods=1).mean()
    return sm.iloc[pad:pad + n]


def analyze_channel(s: pd.Series) -> tuple[dict, pd.Series]:
    s = s.dropna()
    y = np.log(np.maximum(s.to_numpy(dtype=float), LOG_FLOOR))
    r = pd.Series(_detrend(y), index=s.index)

    keys = _doy_key(s.index)
    raw_effects = r.groupby(keys.to_numpy()).mean()
    effects = _circular_smooth(raw_effects)
    fitted = keys.map(effects).to_numpy(dtype=float)

    ss_res = float(((r.to_numpy() - fitted) ** 2).sum())
    ss_tot = float((r.to_numpy() ** 2).sum())
    partial_r2 = max(0.0, 1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    top = effects.sort_values(ascending=False).head(TOP_N_DATES)
    deseason = pd.Series(np.exp(y - fitted), index=s.index)

    report = {
        "partial_r2": round(partial_r2, 4),
        "top_recurring_dates": [
            {"month_day": k, "log_effect": round(float(v), 4)}
            for k, v in top.items()
        ],
    }
    return report, deseason


def main() -> None:
    if not STORE.exists():
        raise SystemExit("no data/raw/gdelt_volume.csv yet -- run the pipeline first")
    vol = pd.read_csv(STORE, parse_dates=["date"]).set_index("date").sort_index()

    reports: dict = {}
    deseason_cols: dict = {}
    for ch in vol.columns:
        reports[ch], deseason_cols[ch] = analyze_channel(vol[ch])
        print(f"[seasonality] {ch}: partial R^2 = {reports[ch]['partial_r2']:.3f}")

    primary = build_index.build_scores(vol)
    deseason_scores = build_index.build_scores(pd.DataFrame(deseason_cols))
    for ch in vol.columns:
        joined = pd.concat(
            [primary[ch], deseason_scores[ch]], axis=1, join="inner"
        ).dropna()
        reports[ch]["corr_seasonal_vs_deseasonalized"] = round(
            float(joined.corr().iloc[0, 1]), 4
        )

    payload = {
        "note": ("Day-of-year effects on log volume share after removing a "
                 "linear trend; 7-day circular smoothing. Deseasonalized "
                 "index is a secondary specification only."),
        "channels": reports,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"[seasonality] wrote {OUT}")


if __name__ == "__main__":
    main()
