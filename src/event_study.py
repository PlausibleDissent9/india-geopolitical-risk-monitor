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


def _bootstrap(values: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    """95% CI and a two-sided bootstrap p-value for mean != 0 (the share
    of resampled means on the far side of zero, doubled)."""
    means = np.array(
        [values[rng.integers(0, len(values), len(values))].mean() for _ in range(N_BOOT)]
    )
    lo, hi = float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
    frac_le = float(np.mean(means <= 0))
    p = 2.0 * min(frac_le, 1.0 - frac_le)
    return lo, hi, min(max(p, 1.0 / N_BOOT), 1.0)


def _benjamini_hochberg(cells: list[dict], alpha: float = 0.10) -> None:
    """FDR correction across the full test grid of RELATIVE outcomes
    (channels x outcomes x windows), flagging each cell in place.
    Descriptive outcomes are excluded -- they make no inferential claim."""
    tested = [c for c in cells if not c["descriptive"] and c.get("p") is not None]
    tested.sort(key=lambda c: c["p"])
    m = len(tested)
    threshold_rank = 0
    for i, c in enumerate(tested, start=1):
        if c["p"] <= alpha * i / m:
            threshold_rank = i
    for i, c in enumerate(tested, start=1):
        c["cell"]["bh_significant_10pct"] = i <= threshold_rank


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

    all_cells: list[dict] = []
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
                if len(arr) > 1:
                    lo, hi, p = _bootstrap(arr, rng)
                else:
                    lo = hi = float(arr[0])
                    p = None
                cell = {
                    "mean": round(float(arr.mean()), 3),
                    "ci95": [round(lo, 3), round(hi, 3)],
                    "n": int(len(arr)),
                }
                if p is not None:
                    cell["p_boot"] = round(p, 4)
                per_window[str(w)] = cell
                all_cells.append({
                    "cell": cell, "p": p,
                    "descriptive": outcome in DESCRIPTIVE_OUTCOMES,
                })
            ch_out["outcomes"][outcome] = per_window
        results["channels"][ch] = ch_out

    # FDR control across the whole grid of inferential tests, so "which
    # windows are significant" survives the multiplicity of this table.
    _benjamini_hochberg(all_cells)

    # Per-episode raw window returns (no CI -- n=1 by construction), for
    # the site's episode detail pages. Same windows, same outcomes.
    per_episode: dict[str, list[dict]] = {}
    for ch, eps in sorted(by_channel.items()):
        rows = []
        for e in eps:
            t = pd.Timestamp(e["start"])
            rows.append({
                "start": e["start"],
                "outcomes": {
                    outcome: {
                        str(w): (None if (v := _cum_return(derived[outcome], t, w)) is None
                                 else round(v, 3))
                        for w in WINDOWS
                    }
                    for outcome in outcomes
                },
            })
        per_episode[ch] = rows
    results["per_episode"] = per_episode
    return results


def write_output(results: dict) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    from .build_index import _file_meta

    results = {"_meta": _file_meta(
        "Event study: mean cumulative India-specific relative returns "
        "after episode starts, with bootstrapped 95% CIs, plus raw "
        "per-episode window returns.",
        "cumulative log return, percent, over trading-day windows",
    ), **results}
    (SITE_DATA / "event_study.json").write_text(
        json.dumps(results, indent=1), encoding="utf-8"
    )

    # Flat research-grade CSV: one row per channel x outcome x window.
    rows = []
    for ch, data in results["channels"].items():
        for outcome, wins in data["outcomes"].items():
            for w, cell in wins.items():
                if cell is None:
                    continue
                rows.append({
                    "channel": ch, "outcome": outcome,
                    "window_trading_days": int(w),
                    "mean_cum_log_return_pct": cell["mean"],
                    "ci95_lo": cell["ci95"][0], "ci95_hi": cell["ci95"][1],
                    "p_boot": cell.get("p_boot"),
                    "bh_significant_10pct": cell.get("bh_significant_10pct"),
                    "n_episodes": cell["n"],
                    "descriptive_only": outcome in results["descriptive_only"],
                })
    pd.DataFrame(rows).to_csv(SITE_DATA / "event_study.csv", index=False)
