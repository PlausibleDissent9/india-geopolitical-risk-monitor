"""
E2: measured sector sensitivities (builds on the founder-signed
sectors.json v1.1.0 nse_index mapping, 2026-08-06).

For every sector with a signed NSE index: the index's cumulative
return RELATIVE to Nifty around the start of each episode in the
sector's registered channels -- the same windows, the same seeded
bootstrap, and the same association-never-causation language as the
main event study (src/event_study.py, methodology section 6).

Discipline, all load-bearing:
  - Only signed mappings run; sectors with nse_index null publish
    nothing (a null means no measured sensitivity shown, never a
    borrowed proxy -- the signed amendment's own words).
  - Yahoo price data is fetched, used, and NOT committed or
    redistributed (the standing Yahoo discipline); only aggregated
    statistics publish, with n and CIs.
  - Measured sensitivity lives BESIDE the exposure map, never inside
    it: no weight, score, or exposure reading changes because of
    anything computed here.

  python -m src.sector_sensitivity   writes docs/data/sector_sensitivity.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.event_study import WINDOWS, _benjamini_hochberg, _bootstrap, _cum_return

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

NIFTY = "^NSEI"
START = "2007-09-17"  # ^NSEI series start on Yahoo
SEED = 20260806


def signed_mappings() -> dict[str, dict[str, Any]]:
    d = json.loads((ROOT / "sectors.json").read_text(encoding="utf-8"))
    return {k: s for k, s in d["sectors"].items() if s.get("nse_index")}


def fetch_relative_returns(tickers: list[str]) -> pd.DataFrame:
    """Daily log returns (percent) of each ticker minus Nifty."""
    import yfinance as yf

    raw = yf.download(sorted(set(tickers + [NIFTY])), start=START,
                      progress=False, auto_adjust=True)["Close"]
    rets = (np.log(raw) - np.log(raw.shift(1))) * 100.0
    out = pd.DataFrame({t: rets[t] - rets[NIFTY]
                        for t in set(tickers) if t in rets})
    return out.dropna(how="all")


def sensitivity_cells(
    mappings: dict[str, dict[str, Any]],
    episodes: list[dict],
    relative: pd.DataFrame,
) -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    by_channel: dict[str, list[pd.Timestamp]] = {}
    for e in episodes:
        by_channel.setdefault(e["channel"], []).append(pd.Timestamp(e["start"]))

    sectors: dict[str, Any] = {}
    all_cells: list[dict] = []
    for key, spec in sorted(mappings.items()):
        ticker = spec["nse_index"]
        if ticker not in relative.columns:
            continue
        chans: dict[str, Any] = {}
        for ch in spec["channels"]:
            starts = by_channel.get(ch) or []
            if not starts:
                continue
            per_window: dict[str, Any] = {}
            for w in WINDOWS:
                vals = [_cum_return(relative[ticker], t, w) for t in starts]
                arr = np.array([v for v in vals if v is not None])
                if len(arr) < 2:
                    per_window[str(w)] = None
                    continue
                lo, hi, p = _bootstrap(arr, rng)
                cell = {
                    "mean": round(float(arr.mean()), 3),
                    "ci95": [round(lo, 3), round(hi, 3)],
                    "p_boot": round(p, 3),
                    "n": int(len(arr)),
                }
                per_window[str(w)] = cell
                # _benjamini_hochberg's expected shape: it reads "p" and
                # "descriptive", and flags via the "cell" reference.
                all_cells.append({"descriptive": False, "p": p,
                                  "cell": cell})
            if per_window:
                chans[ch] = per_window
        if chans:
            sectors[key] = {"label": spec["label"], "nse_index": ticker,
                            "channels": chans}
    # Same multiple-comparisons discipline as the main event study:
    # 39 uncorrected p-values would be a fishing licence.
    _benjamini_hochberg(all_cells)
    return sectors


def main() -> None:
    mappings = signed_mappings()
    if not mappings:
        raise SystemExit("[sensitivity] no signed nse_index mappings")
    episodes = json.loads(
        (SITE_DATA / "episodes.json").read_text(encoding="utf-8"))
    relative = fetch_relative_returns(
        [s["nse_index"] for s in mappings.values()])
    sectors = sensitivity_cells(mappings, episodes, relative)
    payload = {
        "_meta": {
            "what": ("Measured sector sensitivities (E2): each signed "
                     "sector index's cumulative return RELATIVE to Nifty "
                     "over 1/5/20 trading days from the start of episodes "
                     "in the sector's registered channels, with seeded-"
                     "bootstrap 95% CIs and two-sided p-values, n stated "
                     "per cell. ASSOCIATED WITH, never caused by. "
                     "Sensitivities live beside the exposure map and "
                     "change no weight, score, or reading. Mapping: "
                     "sectors.json v1.1.0, founder-signed 2026-08-06; "
                     "sectors without a signed index publish nothing. "
                     "Underlying prices are Yahoo's and are not "
                     "redistributed; only these aggregates publish."),
            "windows": WINDOWS,
            "units": "cumulative log return vs Nifty, percent",
            "multiple_comparisons": (
                "Benjamini-Hochberg FDR at 10% across the full cell "
                "grid, same discipline as the main event study; "
                "bh_significant_10pct per cell. On the first computation "
                "(2026-08-06, 39 cells) NO cell survived correction -- "
                "a published negative result: with this episode set, no "
                "sector index shows a sensitivity distinguishable from "
                "zero once the search is paid for."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "sectors": sectors,
    }
    (SITE_DATA / "sector_sensitivity.json").write_text(
        json.dumps(payload), encoding="utf-8")
    for k, v in sectors.items():
        cells = sum(len(pw) for pw in v["channels"].values())
        print(f"[sensitivity] {k} ({v['nse_index']}): "
              f"{len(v['channels'])} channel(s), {cells} window cells")


if __name__ == "__main__":
    main()
