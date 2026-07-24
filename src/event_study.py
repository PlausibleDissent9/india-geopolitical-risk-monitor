"""
Event study: cumulative relative returns around episode starts.

Windows are 1 / 5 / 20 TRADING days, inclusive of the first trading day
on or after the episode start (methodology section 6). Estimates carry
bootstrapped 95% CIs (resampling episodes with replacement). All output
language is association, never causation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

WINDOWS = [1, 5, 20]
RELATIVE_OUTCOMES = ["nifty_minus_em", "defence_minus_nifty", "usdinr_minus_dxy"]
DESCRIPTIVE_OUTCOMES = ["brent_ret", "gold_ret"]
N_BOOT = 1000
BOOT_SEED = 20260724


def _cum_return(series: pd.Series, start: pd.Timestamp, window: int) -> float | None:
    s = series.dropna()
    idx = s.index[s.index >= start]
    if len(idx) < window:
        return None
    return float(s.loc[idx[0]:idx[window - 1]].sum())


def _bootstrap_ci(values: np.ndarray, rng: np.random.Generator) -> tuple[float, float]:
    means = np.array(
        [values[rng.integers(0, len(values), len(values))].mean() for _ in range(N_BOOT)]
    )
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def run_event_study(episodes: list[dict], derived: pd.DataFrame) -> dict:
    derived = derived.copy()
    derived.index = pd.to_datetime(derived.index)
    rng = np.random.default_rng(BOOT_SEED)

    by_channel: dict[str, list[dict]] = {}
    for e in episodes:
        by_channel.setdefault(e["channel"], []).append(e)

    outcomes = [o for o in RELATIVE_OUTCOMES + DESCRIPTIVE_OUTCOMES
                if o in derived.columns]
    results: dict = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "windows": WINDOWS,
        "units": "cumulative log return, percent",
        "language": "associated with -- no causal claim",
        "descriptive_only": DESCRIPTIVE_OUTCOMES,
        "channels": {},
    }

    for ch, eps in sorted(by_channel.items()):
        starts = [pd.Timestamp(e["start"]) for e in eps]
        ch_out: dict = {"n_episodes": len(eps), "outcomes": {}}
        for outcome in outcomes:
            per_window: dict = {}
            for w in WINDOWS:
                vals = [_cum_return(derived[outcome], t, w) for t in starts]
                arr = np.array([v for v in vals if v is not None])
                if len(arr) == 0:
                    per_window[str(w)] = None
                    continue
                lo, hi = (_bootstrap_ci(arr, rng) if len(arr) > 1
                          else (float(arr[0]), float(arr[0])))
                per_window[str(w)] = {
                    "mean": round(float(arr.mean()), 3),
                    "ci95": [round(lo, 3), round(hi, 3)],
                    "n": int(len(arr)),
                }
            ch_out["outcomes"][outcome] = per_window
        results["channels"][ch] = ch_out
    return results


def write_output(results: dict) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "event_study.json").write_text(
        json.dumps(results, separators=(",", ":")), encoding="utf-8"
    )
