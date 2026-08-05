"""
Daily-score sampling uncertainty (MI3; V5 accelerated by founder order,
2026-08-05 night). The ngrams bridge estimates each day's channel share
from a pooled sample of ~30k documents, so the published score carries
sampling noise the chart should show rather than bury in a file.

Method, stated completely:
  1. For each cached sample day (data/raw/ngram_days/), the channel's
     raw share is the sum of its sub-query group shares over n sampled
     documents. The effective matched count is k = round(share/100 * n).
     Approximation, stated: the registered sum-of-groups construction
     can count one document under two groups, so k is an upper-ish
     effective count; the band inherits the construction rather than
     correcting it.
  2. Wilson 95% interval on k/n gives share bounds.
  3. Both bounds pass through the SAME transforms the point value
     passed through: divided by the channel's published splice ratio
     (ngram_calibration.json), then mapped by the same trailing
     percentile against the primary store (the day's own value included
     in its window, exactly as build_index computes it).
  4. Composite band: mean of the channel bounds. The five channels'
     sampling errors are independent, so the true composite band is
     narrower than this envelope; conservative by construction, stated.

API-era days (before the ngrams switch) have no sampling design of
this kind -- timelinevol is computed over the full monitored corpus --
so bands exist only for sample-estimated days and the payload names
the first banded date.

  python -m src.uncertainty     writes docs/data/uncertainty.json
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from .fetch_ngrams import group_specs

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DAY_CACHE = RAW / "ngram_days"
SITE_DATA = ROOT / "docs" / "data"
WINDOW_DAYS = 730  # build_index.PERCENTILE_WINDOW_DAYS; asserted in tests


def wilson95(k: float, n: float) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion, z = 1.96."""
    if n <= 0:
        return (0.0, 1.0)
    z = 1.96
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)  # exact at the boundary
    hi = 1.0 if k == n else min(1.0, centre + half)
    return (lo, hi)


def trailing_pct(window_values: pd.Series, x: float) -> float:
    """Percentile of x against a trailing window, same arithmetic as
    build_index._trailing_percentile evaluates for the day's own value."""
    v = window_values.dropna()
    if v.empty:
        return float("nan")
    return 100.0 * float((v <= x).mean())


def main() -> None:
    specs = group_specs()
    channels = sorted({s["channel"] for s in specs.values()})
    store = pd.read_csv(RAW / "gdelt_volume.csv",
                        parse_dates=["date"]).set_index("date")
    calib = json.loads((RAW / "ngram_calibration.json").read_text(encoding="utf-8"))

    days: dict[str, dict[str, list[float]]] = {}
    for cache in sorted(DAY_CACHE.glob("*.json")):
        rec = json.loads(cache.read_text(encoding="utf-8"))
        day = rec["date"]
        n = rec.get("n_docs_sampled") or 0
        ts = pd.Timestamp(day)
        if n <= 0 or ts not in store.index:
            continue
        out: dict[str, list[float]] = {}
        lo_scores, hi_scores = [], []
        for ch in channels:
            share = sum(v for g, v in rec["shares"].items()
                        if specs.get(g, {}).get("channel") == ch)
            ratio = (calib.get(ch) or {}).get("ratio")
            if ratio is None:
                continue
            k = round(share / 100.0 * n)
            p_lo, p_hi = wilson95(k, n)
            v_lo, v_hi = 100.0 * p_lo / ratio, 100.0 * p_hi / ratio
            window = store.loc[ts - pd.Timedelta(days=WINDOW_DAYS):ts, ch]
            s_lo, s_hi = trailing_pct(window, v_lo), trailing_pct(window, v_hi)
            if math.isnan(s_lo) or math.isnan(s_hi):
                continue
            out[ch] = [round(s_lo, 1), round(s_hi, 1)]
            lo_scores.append(s_lo)
            hi_scores.append(s_hi)
        if len(out) == len(channels):
            out["composite"] = [round(sum(lo_scores) / len(lo_scores), 1),
                                round(sum(hi_scores) / len(hi_scores), 1)]
        if out:
            days[day] = out

    payload = {
        "_meta": {
            "what": ("95% sampling bands for sample-estimated daily scores: "
                     "Wilson interval on the day's matched share, passed "
                     "through the same splice ratio and trailing-percentile "
                     "transform as the published point value. The composite "
                     "band is the mean of channel bounds -- an envelope, "
                     "conservative because channel sampling errors are "
                     "independent. Days before the first banded date were "
                     "computed over the full monitored corpus (no sampling "
                     "design of this kind), so they carry no band."),
            "units": "percentile score bounds [lo, hi], 0-100",
            "first_banded_date": min(days) if days else None,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "days": days,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DATA / "uncertainty.json"
    out_path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[uncertainty] wrote {out_path.name}: {len(days)} banded days"
          + (f" from {min(days)}" if days else ""))


if __name__ == "__main__":
    main()
