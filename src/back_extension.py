"""
M1 build: the historical attention proxy, 1979-2019 (registration
FROZEN in analysis/back_extension_memo.md, founder-signed 2026-08-06,
before any query ran -- this module's filters commit before
credentials exist locally, so the ex-ante order is git-verifiable).

A DIFFERENT construct from the live instrument, and named so
everywhere: monthly share of global event-MENTIONS involving the
registered actor-pair filters, from GDELT 1.0 (1979-2015-02) and
GDELT 2.0 (2015-02-2019-12; the tail exists solely for the overlap
audit). Four channels; shipping is excluded because chokepoint
salience has no actor coding, stated on every surface. Never spliced
into, averaged with, or drawn on the same axis as the 2017+
instrument.

  python -m src.back_extension --build     one-time BQ aggregation (CI)
  python -m src.back_extension --publish   grade anchors + overlap, publish
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "back_extension_monthly.csv"
SITE_DATA = ROOT / "docs" / "data"
MAX_BYTES = 25 * 10**9  # one-time backfill; first run self-reported
# bytesBilledLimitExceeded at 22.25GB actual vs a 20GB guess -- the cap
# is sized to the measured need (~2.2% of the monthly free tier, once);
# the exact bytes-billed number publishes in the study's methods.

# Frozen actor-pair filters (memo decision B). ECON_ROOTS implements
# the memo's "economic cooperation/conflict roots" as CAMEO roots 06
# (engage in material cooperation) and 16 (reduce relations, incl.
# sanctions/boycotts) -- frozen here before the first query runs.
GULF = ("SAU", "IRN", "ARE", "QAT", "KWT", "IRQ")
CHANNELS: dict[str, str] = {
    "pakistan_west": ("((Actor1CountryCode='IND' AND Actor2CountryCode='PAK')"
                      " OR (Actor1CountryCode='PAK' AND Actor2CountryCode='IND'))"),
    "china_east": ("((Actor1CountryCode='IND' AND Actor2CountryCode='CHN')"
                   " OR (Actor1CountryCode='CHN' AND Actor2CountryCode='IND'))"),
    "us_trade": ("((Actor1CountryCode='IND' AND Actor2CountryCode='USA')"
                 " OR (Actor1CountryCode='USA' AND Actor2CountryCode='IND'))"
                 " AND SUBSTR(CAST(EventRootCode AS STRING),1,2) IN ('06','16')"),
    "gulf_energy": (f"((Actor1CountryCode='IND' AND Actor2CountryCode IN {str(GULF)})"
                    f" OR (Actor1CountryCode IN {str(GULF)} AND Actor2CountryCode='IND'))"
                    ),
}
ANCHORS = [  # memo decision C, frozen; graded top-decile trailing-10y
    ("1984-06", "pakistan_west", "Operation Blue Star + aftermath"),
    ("1987-01", "pakistan_west", "Brasstacks crisis"),
    ("1998-05", "pakistan_west", "Pokhran-II tests + sanctions"),
    ("1998-05", "us_trade", "Pokhran-II sanctions (US leg)"),
    ("1999-06", "pakistan_west", "Kargil war"),
    ("2001-12", "pakistan_west", "Parliament attack + Op. Parakram"),
    ("2008-11", "pakistan_west", "Mumbai 26/11"),
    ("1986-10", "china_east", "Sumdorong Chu standoff"),
    ("2017-06", "china_east", "Doklam (overlap check vs live instrument)"),
]
OVERLAP_THRESHOLDS = {"tracks": 0.6, "partial": 0.4}  # memo decision D


def _bq_client():
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(os.environ["GCP_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(info)
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"],
                           credentials=creds)


def build() -> None:
    """One-time monthly aggregation from both GDELT generations."""
    from google.cloud import bigquery

    client = _bq_client()
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)
    frames = []
    for table, monthcol, lo, hi in (
            ("gdelt-bq.full.events", "MonthYear", 197901, 201501),
            ("gdelt-bq.gdeltv2.events", "MonthYear", 201502, 201912)):
        sel = ", ".join(
            f"SUM(IF({flt}, NumMentions, 0)) AS {ch}"
            for ch, flt in CHANNELS.items())
        q = (f"SELECT {monthcol} AS month, SUM(NumMentions) AS total, {sel} "
             f"FROM `{table}` WHERE {monthcol} BETWEEN {lo} AND {hi} "
             f"GROUP BY month ORDER BY month")
        df = client.query(q, job_config=cfg).to_dataframe()
        df["generation"] = "1.0" if table.endswith("full.events") else "2.0"
        frames.append(df)
        print(f"[backext] {table}: {len(df)} months")
    out = pd.concat(frames, ignore_index=True)
    for ch in CHANNELS:
        out[ch] = out[ch] / out["total"] * 100.0
    STORE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(STORE, index=False)
    print(f"[backext] wrote {STORE.name}: {len(out)} months, "
          "committed once, never re-queried")


def _pct_10y(s: pd.Series) -> pd.Series:
    return s.rolling(120, min_periods=60).apply(
        lambda a: 100.0 * float((a[:-1] <= a[-1]).mean()) if len(a) > 1 else float("nan"),
        raw=True)


def publish() -> None:
    if not STORE.exists():
        raise SystemExit("[backext] no store; run --build in CI first")
    df = pd.read_csv(STORE)
    df["month"] = pd.PeriodIndex(df["month"].astype(str), freq="M")
    df = df.set_index("month").sort_index()
    # Per-generation percentile normalization (memo decision A), seam
    # published, raw shares published beside percentiles.
    pcts = {}
    for ch in CHANNELS:
        parts = [
            _pct_10y(df.loc[df["generation"] == g, ch]) for g in ("1.0", "2.0")]
        pcts[ch] = pd.concat(parts).sort_index()
    anchor_grades = []
    for month, ch, name in ANCHORS:
        p = pcts[ch].get(pd.Period(month, freq="M"))
        anchor_grades.append({
            "anchor": name, "month": month, "channel": ch,
            "pctl_trailing_10y": None if p is None or pd.isna(p) else round(float(p), 1),
            "top_decile": None if p is None or pd.isna(p) else bool(p >= 90.0),
        })
    # Overlap audit vs the live instrument, monthly means, 2017-2019.
    from src import build_index
    v = pd.read_csv(ROOT / "data" / "raw" / "gdelt_volume.csv",
                    parse_dates=["date"]).set_index("date")
    live = build_index.build_scores(v).resample("MS").mean()
    live.index = pd.PeriodIndex(live.index, freq="M")
    overlap = {}
    for ch in CHANNELS:
        joint = pd.concat([pcts[ch], live[ch]], axis=1,
                          keys=["proxy", "live"]).dropna()
        joint = joint[(joint.index >= pd.Period("2017-01", freq="M"))
                      & (joint.index <= pd.Period("2019-12", freq="M"))]
        if len(joint) < 24:
            overlap[ch] = {"months": int(len(joint)), "verdict": "insufficient"}
            continue
        r = float(joint["proxy"].corr(joint["live"]))
        verdict = ("tracks" if r >= OVERLAP_THRESHOLDS["tracks"]
                   else "partial" if r >= OVERLAP_THRESHOLDS["partial"]
                   else "DOES NOT PUBLISH (negative finding)")
        overlap[ch] = {"months": int(len(joint)), "r": round(r, 3),
                       "verdict": verdict}
    payload: dict[str, Any] = {
        "_meta": {
            "what": ("Historical attention proxy 1979-2016 (M1; "
                     "registration frozen before first computation, "
                     "analysis/back_extension_memo.md). A DIFFERENT "
                     "construct from the live instrument -- monthly "
                     "event-mention shares by frozen actor-pair filters "
                     "-- never spliced into or drawn with the 2017+ "
                     "series. Four channels; shipping has no defensible "
                     "event analog and is excluded. Channels whose "
                     "2017-2019 overlap correlation is under 0.4 do not "
                     "publish a historical series; that negative is the "
                     "finding."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "anchor_grades": anchor_grades,
        "overlap_audit": overlap,
        "series": {
            ch: {"months": [str(m) for m in pcts[ch].index],
                 "pctl_10y": [None if pd.isna(x) else round(float(x), 1)
                              for x in pcts[ch]],
                 "raw_share": [None if pd.isna(x) else round(float(x), 5)
                               for x in df[ch]]}
            for ch in CHANNELS
            if overlap.get(ch, {}).get("verdict") in ("tracks", "partial")
        },
    }
    (SITE_DATA / "back_extension.json").write_text(json.dumps(payload),
                                                   encoding="utf-8")
    print("[backext] anchors:", [(a["anchor"], a["top_decile"])
                                 for a in anchor_grades])
    print("[backext] overlap:", {c: o.get("verdict") for c, o in overlap.items()})


def main() -> None:
    if "--build" in sys.argv:
        if not os.environ.get("GCP_SA_JSON"):
            print("[backext] no GCP credentials; skipping build (fail-closed)")
            return
        build()
    if "--publish" in sys.argv:
        publish()


if __name__ == "__main__":
    main()
