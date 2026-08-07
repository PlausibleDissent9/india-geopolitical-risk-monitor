"""
Market data pull (Yahoo Finance) and derived relative-return series.

Relative outcomes only (methodology section 6):
  nifty_minus_em       Nifty - MSCI EM     strips global equity beta
  defence_minus_nifty  defence basket - Nifty   the India-specific hypothesis
  usdinr_minus_dxy     USDINR - DXY        strips broad dollar moves
Brent, gold, India VIX are descriptive-only: no India-specific component
is separable in a global commodity.

Defence basket: equal-weight, daily-rebalanced mean of member log returns.
Returns are log returns in percent, aligned on shared trading days.
Outputs are cached to data/raw/ but gitignored -- cheap to re-fetch.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

TICKERS = {
    "nifty": "^NSEI",
    "india_vix": "^INDIAVIX",
    "em": "EEM",
    "usdinr": "USDINR=X",
    "dxy": "DX-Y.NYB",
    "brent": "BZ=F",
    "gold": "GC=F",
}
DEFENCE_TICKERS = ["HAL.NS", "BEL.NS", "BDL.NS", "MAZDOCK.NS", "COCHINSHIP.NS"]

# V2 sector baskets: equal-weight, daily-rebalanced, fixed before any
# sector cell was computed (validation/sector_hypotheses.json holds the
# registration and the channel-to-basket hypotheses). Members are the
# largest liquid NSE names with the cleanest exposure to each channel's
# transmission path; changes are append-only with a changelog entry.
SECTOR_BASKETS = {
    "defence": DEFENCE_TICKERS,
    "energy_omc": ["IOC.NS", "BPCL.NS", "HINDPETRO.NS"],
    "it_services": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS"],
    "ports_logistics": ["ADANIPORTS.NS", "CONCOR.NS"],
}


class OfflineMarketDataUnavailable(RuntimeError):
    """Raised when an offline run has no lawful frozen market cache."""


def _download(tickers: list[str], start: str) -> pd.DataFrame:
    data = yf.download(
        tickers, start=start, auto_adjust=True, progress=False, group_by="column"
    )
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def _log_ret_pct(s: pd.Series) -> pd.Series:
    return 100.0 * np.log(s / s.shift(1))


def load_or_update(start: str = "2022-01-01") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (prices, derived). Fetches the full range each run.
    IGRM_OFFLINE=1 returns the cached CSVs unchanged: reproduce's cached
    mode must freeze every input, and a live Yahoo tail shifts returns
    enough to wiggle seeded bootstrap p-values (observed 2026-08-01)."""
    import os
    if os.environ.get("IGRM_OFFLINE"):
        p_path, d_path = RAW_DIR / "prices.csv", RAW_DIR / "derived_returns.csv"
        if p_path.exists() and d_path.exists():
            print("[markets] OFFLINE: using cached prices and derived returns")
            prices = pd.read_csv(p_path, parse_dates=["date"]).set_index("date")
            derived = pd.read_csv(d_path, parse_dates=["date"]).set_index("date")
            return prices, derived
        raise OfflineMarketDataUnavailable(
            "IGRM_OFFLINE is set but prices.csv/derived_returns.csv are absent; "
            "refusing a live market fetch"
        )
    all_members = sorted({t for members in SECTOR_BASKETS.values() for t in members})
    prices = _download(list(TICKERS.values()) + all_members, start)
    prices = prices.rename(columns={v: k for k, v in TICKERS.items()})

    rets = pd.DataFrame(index=prices.index)
    for name in TICKERS:
        if name in prices.columns:
            rets[name] = _log_ret_pct(prices[name])

    for basket, members in SECTOR_BASKETS.items():
        member_rets = pd.DataFrame(
            {t: _log_ret_pct(prices[t]) for t in members if t in prices.columns}
        )
        rets[basket] = member_rets.mean(axis=1)

    derived = pd.DataFrame(index=prices.index)
    derived["nifty_minus_em"] = rets["nifty"] - rets["em"]
    for basket in SECTOR_BASKETS:
        derived[f"{basket}_minus_nifty"] = rets[basket] - rets["nifty"]
    derived["usdinr_minus_dxy"] = rets["usdinr"] - rets["dxy"]
    derived["brent_ret"] = rets["brent"]
    derived["gold_ret"] = rets["gold"]
    derived["india_vix"] = prices.get("india_vix")
    derived["india_vix_chg"] = derived["india_vix"].diff()
    derived = derived.dropna(how="all")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    prices.to_csv(RAW_DIR / "prices.csv", index_label="date")
    derived.to_csv(RAW_DIR / "derived_returns.csv", index_label="date")
    return prices, derived


if __name__ == "__main__":
    p, d = load_or_update()
    print(d.tail())
