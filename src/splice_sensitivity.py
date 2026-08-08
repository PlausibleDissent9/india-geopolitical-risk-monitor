"""Publish the score-level sensitivity to independent splice ratios.

This never changes the primary series. It applies the independently
estimated ratios from analysis/splice_overlap_audit.py only to store days
that can be identified as mechanically bridged from NGrams under the
production ratio, rebuilds daily and 7-day scores, and publishes the
difference beside the frozen vintage.

    python3 -m src.splice_sensitivity
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
from analysis.splice_overlap_audit import audit as calibration_audit

from src import fetch_ngrams
from src.build_index import build_scores, build_scores7

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
OUT = SITE_DATA / "splice_sensitivity.json"
CHANNELS = ("pakistan_west", "china_east", "gulf_energy")
MATCH_TOLERANCE = 0.001


def _r(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def build() -> dict:
    volume = pd.read_csv(
        fetch_ngrams.STORE, parse_dates=["date"]
    ).set_index("date")
    production = json.loads(
        (fetch_ngrams.RAW_DIR / "ngram_calibration.json").read_text(
            encoding="utf-8"
        )
    )
    recovered = calibration_audit()
    alternative = volume.copy()
    specs = fetch_ngrams.group_specs()
    adjusted_days: set[pd.Timestamp] = set()

    for path in sorted(fetch_ngrams.DAY_CACHE.glob("*.json")):
        day = date.fromisoformat(path.stem)
        ts = pd.Timestamp(day)
        cached = fetch_ngrams._cached_day(day, specs)
        if cached is None or ts not in volume.index:
            continue
        sums = fetch_ngrams._channel_sums(cached, specs)
        for channel in CHANNELS:
            stored = volume.loc[ts, channel]
            if pd.isna(stored) or stored <= 0 or sums[channel] <= 0:
                continue
            implied_ratio = sums[channel] / stored
            frozen_ratio = float(production[channel]["ratio"])
            # The pre-bridge API observation on 2026-06-30 must not be
            # rescaled. Mechanically bridged rows recover the production
            # ratio within store-rounding tolerance; independent rows do not.
            if abs(implied_ratio / frozen_ratio - 1) >= MATCH_TOLERANCE:
                continue
            # calibration_audit() builds a dict whose values span float,
            # int and None -- the None belongs to relative_change_pct, not
            # to this key, but the inferred value type is the union of all
            # three and float() rejects it. Narrowed by an actual check
            # rather than a cast: if a channel ever does arrive without an
            # independent ratio, skipping it is right, and silently
            # rescaling by None is not.
            raw_ratio = recovered[channel]["independent_ratio"]
            if raw_ratio is None:
                continue
            independent_ratio = float(raw_ratio)
            alternative.loc[ts, channel] = sums[channel] / independent_ratio
            adjusted_days.add(ts)

    if not adjusted_days:
        raise RuntimeError("no mechanically bridged days found; refusing empty audit")

    primary_daily = build_scores(volume)
    audit_daily = build_scores(alternative)
    primary_weekly = build_scores7(volume)
    audit_weekly = build_scores7(alternative)
    start, end = min(adjusted_days), max(adjusted_days)
    adjusted_store_dates = [
        day.date().isoformat() for day in sorted(adjusted_days)
    ]
    dates = pd.date_range(start, end, freq="D")
    reported = list(CHANNELS) + ["composite"]

    def series_block(primary: pd.DataFrame, sensitivity: pd.DataFrame) -> dict:
        p = primary.reindex(dates)
        s = sensitivity.reindex(dates)
        return {
            "primary": {
                channel: [None if pd.isna(v) else _r(v, 1) for v in p[channel]]
                for channel in reported
            },
            "independent_ratio_sensitivity": {
                channel: [None if pd.isna(v) else _r(v, 1) for v in s[channel]]
                for channel in reported
            },
            "delta": {
                channel: [
                    None if pd.isna(v) else _r(v, 1)
                    for v in (s[channel] - p[channel])
                ]
                for channel in reported
            },
        }

    def summary(primary: pd.DataFrame, sensitivity: pd.DataFrame) -> dict:
        p = primary.loc[start:end]
        s = sensitivity.loc[start:end]
        out = {}
        for channel in reported:
            delta = (s[channel] - p[channel]).dropna()
            out[channel] = {
                "median_absolute_shift": _r(delta.abs().median()),
                "maximum_absolute_shift": _r(delta.abs().max()),
                "latest_shift": _r(delta.iloc[-1]),
            }
        return out

    return {
        "_meta": {
            "what": (
                "Score-level sensitivity to the independently audited splice "
                "ratios. The primary series is frozen and unchanged. This "
                "alternative rescales only mechanically identified NGrams-"
                "bridge rows for Pakistan, China and Gulf; US Trade and "
                "Shipping have no additional independent overlap and are "
                "therefore left at production values."
            ),
            "status": "sensitivity analysis, not a replacement series",
            "independent_denominator": (
                "Last pre-bridge DOC-API store, git commit 091c25e, paired "
                "with retained NGrams day caches"
            ),
            "known_limitations": (
                "Only 18 independent days are available for the three "
                "re-estimated channels; daily observations may be serially "
                "dependent. US Trade and Shipping remain untested beyond n=1."
            ),
            "affected_start": start.date().isoformat(),
            "affected_end": end.date().isoformat(),
            "n_adjusted_store_days": len(adjusted_store_dates),
            "adjusted_store_dates": adjusted_store_dates,
            "generated": date.today().isoformat(),
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). India Geopolitical Risk Monitor. "
                "https://igrm.in/"
            ),
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/splice_sensitivity.json",
        },
        "calibration_audit": recovered,
        "dates": [day.date().isoformat() for day in dates],
        "daily": series_block(primary_daily, audit_daily),
        "trailing_7_day": series_block(primary_weekly, audit_weekly),
        "summary": {
            "daily": summary(primary_daily, audit_daily),
            "trailing_7_day": summary(primary_weekly, audit_weekly),
        },
    }


def main() -> None:
    payload = build()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(
        "[splice_sensitivity] wrote "
        f"{OUT} ({payload['_meta']['n_adjusted_store_days']} adjusted days)"
    )


if __name__ == "__main__":
    main()
