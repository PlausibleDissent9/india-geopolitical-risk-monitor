"""
The monthly series (referee finding #33, 2026-08-07).

Economists work in months. The index publishes days, and every user who
wants to put it beside CPI, IIP, trade or an event-study at monthly
frequency has to aggregate it themselves -- which means twenty
different users make twenty different decisions about the same three
traps, silently, and their results stop being comparable.

So the aggregation ships, with the traps handled in the open.

TRAP 1: SHORT MONTHS
    2025-06 is missing sixteen of its thirty days. A mean over the
    fourteen that survive is not "June 2025"; it is a mean over whichever
    fortnight the fetcher happened to get. Months below MIN_COVERAGE
    publish their row -- the date is never silently absent -- but their
    values are null and `refused_reason` says why. A gap you can see is
    a limitation; a gap you cannot see is an error.

TRAP 2: MIXED INSTRUMENTS
    Most days are DOC API counts; some were measured by the Web NGrams
    bridge and divided by an estimated splice ratio (src/provenance.py).
    A month spanning the boundary is a mean across two instruments
    joined by a constant with its own uncertainty. Every row carries the
    day counts of each, so a user can drop mixed months rather than
    discover them.

TRAP 3: AVERAGING RANKS
    The monthly composite here is the mean of daily percentiles, which
    is NOT the percentile of the monthly mean, and the two disagree
    whenever a month is skewed -- exactly the months anyone cares about.
    Both are published side by side (`composite_mean_of_ranks` and the
    share-based columns) precisely so the difference is visible instead
    of resolved by whoever aggregates first. The share columns are the
    ones that mean the same thing in every year; percentiles are ranks
    against a moving two-year window and are offered as convenience,
    not as the recommended input to a regression.

  python -m src.monthly     writes docs/data/monthly.csv + .json
"""
from __future__ import annotations

import calendar
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from src import provenance

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
SHARES = SITE_DATA / "shares.csv"
HISTORY = SITE_DATA / "history.csv"
CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade",
            "shipping"]

# A month missing more than a fifth of its days is not that month.
# 2025-06 (16 of 30 absent) is the case that forces the rule to exist.
MIN_COVERAGE = 0.80


def _read(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fnum(v: str | None) -> float | None:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _days_in(month: str) -> int:
    y, m = int(month[:4]), int(month[5:7])
    return calendar.monthrange(y, m)[1]


def build() -> list[dict[str, Any]]:
    shares = _read(SHARES)
    hist = {r["date"]: r for r in _read(HISTORY)}
    source_by_day = provenance.by_day()

    by_month: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in shares:
        by_month[r["date"][:7]].append(r)
    if not by_month:
        return []

    rows: list[dict[str, Any]] = []
    for month in sorted(by_month):
        days = by_month[month]
        expected = _days_in(month)
        # The final month of the series is partial by construction, not
        # by failure; judging it against a full month would refuse every
        # current month forever.
        today = date.today()
        if month == f"{today.year:04d}-{today.month:02d}":
            expected = today.day
        present = len(days)
        coverage = present / expected if expected else 0.0

        n_api = sum(1 for d in days
                    if source_by_day.get(d["date"]) == provenance.DOC_API)
        n_bridge = sum(
            1 for d in days
            if source_by_day.get(d["date"]) == provenance.NGRAM_BRIDGE)

        row: dict[str, Any] = {
            "month": month,
            "n_days_present": present,
            "n_days_expected": expected,
            "coverage": round(coverage, 4),
            "n_days_doc_api": n_api,
            "n_days_ngram_bridge": n_bridge,
            "mixed_instruments": bool(n_api and n_bridge),
        }

        # Share coverage and ranked-score coverage are different.  The
        # share store begins before the trailing window can produce a
        # composite score, so calling the former `coverage` and leaving
        # the latter implicit made early 2017 look fully populated when
        # its composite was based on zero (or, in June, two) days.
        comps = [c for c in (_fnum((hist.get(d["date"]) or {}).get("composite"))
                             for d in days) if c is not None]
        composite_coverage = len(comps) / expected if expected else 0.0
        row["n_days_composite_present"] = len(comps)
        row["composite_coverage"] = round(composite_coverage, 4)

        if coverage < MIN_COVERAGE:
            for ch in CHANNELS:
                row[f"share_{ch}"] = ""
            row["composite_mean_of_ranks"] = ""
            row["composite_refused_reason"] = (
                "share coverage failed, so no monthly composite is "
                "published")
            row["refused_reason"] = (
                f"coverage {coverage:.0%} below the {MIN_COVERAGE:.0%} "
                f"floor ({expected - present} of {expected} days absent "
                "from the store); a mean over the surviving days would "
                "describe those days, not this month")
            rows.append(row)
            continue

        for ch in CHANNELS:
            vals = [v for v in (_fnum(d.get(ch)) for d in days)
                    if v is not None]
            row[f"share_{ch}"] = (round(sum(vals) / len(vals), 6)
                                  if vals else "")
        if composite_coverage < MIN_COVERAGE:
            row["composite_mean_of_ranks"] = ""
            row["composite_refused_reason"] = (
                f"composite coverage {composite_coverage:.0%} below the "
                f"{MIN_COVERAGE:.0%} floor ({expected - len(comps)} of "
                f"{expected} daily composite scores unavailable)")
        else:
            row["composite_mean_of_ranks"] = round(
                sum(comps) / len(comps), 2)
            row["composite_refused_reason"] = ""
        row["refused_reason"] = ""
        rows.append(row)
    return rows


FIELDS = (["month", "n_days_present", "n_days_expected", "coverage",
           "n_days_doc_api", "n_days_ngram_bridge", "mixed_instruments"]
          + [f"share_{c}" for c in CHANNELS]
          + ["n_days_composite_present", "composite_coverage",
             "composite_mean_of_ranks", "composite_refused_reason",
             "refused_reason"])


def main() -> None:
    rows = build()
    if not rows:
        raise SystemExit("[monthly] no shares to aggregate; refusing")

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    with (SITE_DATA / "monthly.csv").open("w", encoding="utf-8",
                                          newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    refused = [r for r in rows if r["refused_reason"]]
    mixed = [r for r in rows if r["mixed_instruments"]]
    # CSV blanks are the conventional representation of missing numeric
    # values.  JSON has a real missing-value type; publishing empty
    # strings there created mixed numeric/string columns for consumers.
    json_rows = [
        {k: (None if v == "" else v) for k, v in row.items()}
        for row in rows
    ]
    payload = {
        "_meta": {
            "what": (
                "Monthly aggregation of the daily series, published so "
                "that every user is not silently making their own "
                "decisions about short months, mixed instruments and "
                "averaged ranks."),
            "units": ("share_* are means of the daily percent-of-corpus "
                      "shares; composite_mean_of_ranks is the mean of "
                      "daily composite percentiles"),
            "coverage_rule": (
                f"A month with less than {MIN_COVERAGE:.0%} of its days "
                "in the store publishes its row with null values and a "
                "stated reason, never a mean over the survivors. The "
                "current month is judged against days elapsed, not "
                "against its full length."),
            "composite_coverage_rule": (
                "n_days_composite_present and composite_coverage count "
                "only days with a ranked daily composite. A monthly "
                f"composite below {MIN_COVERAGE:.0%} coverage is null "
                "even when the underlying share series is complete."),
            "averaging_ranks_warning": (
                "composite_mean_of_ranks is the mean of daily "
                "percentiles, which is NOT the percentile of the monthly "
                "mean; the two diverge most in skewed months, which are "
                "the months of interest. The share_* columns are "
                "commensurable across channels and years and are the "
                "recommended input to anything estimated; percentiles "
                "are ranks against a moving two-year window."),
            "instrument_warning": (
                "mixed_instruments marks months spanning the DOC "
                "API/NGrams-bridge boundary, joined by an estimated "
                "splice ratio. See shares.json for the ratios."),
            "n_months": len(rows),
            "n_months_refused": len(refused),
            "months_refused": [r["month"] for r in refused],
            "n_months_mixed_instruments": len(mixed),
            "first_month": rows[0]["month"],
            "last_month": rows[-1]["month"],
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "csv": "monthly.csv",
        "months": json_rows,
    }
    (SITE_DATA / "monthly.json").write_text(json.dumps(payload, indent=1),
                                            encoding="utf-8")
    print(f"[monthly] {len(rows)} months {rows[0]['month']}..{rows[-1]['month']}; "
          f"{len(refused)} refused for coverage, {len(mixed)} mixed-instrument")
    for r in refused:
        print(f"[monthly]   refused {r['month']}: "
              f"{r['n_days_present']}/{r['n_days_expected']} days")


if __name__ == "__main__":
    main()
