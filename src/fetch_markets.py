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
    """Returns (prices, derived). Fetches the full range each run."""
    prices = _download(list(TICKERS.values()) + DEFENCE_TICKERS, start)
    prices = prices.rename(columns={v: k for k, v in TICKERS.items()})

    rets = pd.DataFrame(index=prices.index)
    for name in TICKERS:
        if name in prices.columns:
            rets[name] = _log_ret_pct(prices[name])

    member_rets = pd.DataFrame(
        {t: _log_ret_pct(prices[t]) for t in DEFENCE_TICKERS if t in prices.columns}
    )
    rets["defence"] = member_rets.mean(axis=1)

    derived = pd.DataFrame(index=prices.index)
    derived["nifty_minus_em"] = rets["nifty"] - rets["em"]
    derived["defence_minus_nifty"] = rets["defence"] - rets["nifty"]
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
