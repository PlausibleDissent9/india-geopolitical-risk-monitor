"""
Which instrument measured each day? (referee finding #10, 2026-08-07)

The store is not one series. Most days were measured by the GDELT DOC
API; a minority were measured by the Web NGrams bridge and divided by a
per-channel splice ratio to put them on the API's scale. Those are two
instruments with different sampling, different coverage, and a linking
constant estimated from a handful of overlap days -- and until now the
published CSV made them indistinguishable. A user computing a monthly
mean, a variance, or a regression was mixing them without being told.

That is a defect in `docs/data/shares.csv` as shipped 2026-08-07, not a
hypothetical: `fetch_ngrams.heal()` writes bridged values straight into
the store and records nothing about having done so.

This module makes the mixture visible.

RECORDED vs RECONSTRUCTED
-------------------------
Going forward, `heal()` writes a provenance row at the moment it splices
a day. That is a RECORDED fact.

For days already in the store there is no such record, so provenance is
RECONSTRUCTED from the presence of a day-cache file in
data/raw/ngram_days/ -- the bridge caches every day it samples. The
reconstruction has one known impurity, stated rather than smoothed: the
splice calibration also sampled overlap days on which the API value was
retained, so at most five of the reconstructed days may carry an API
measurement while being labelled bridged. Five is not an estimate, it is
the n from data/raw/ngram_calibration.json. An exact reconstruction is
possible from the store's git history (a day whose value changed after
the bridge era opened was healed) and is deliberately not attempted
here, because a slow exact answer that never ships is worth less than a
fast bounded one that does.

Every row says which kind it is. A reader who needs certainty can use
the recorded rows and discard the rest.

  python -m src.provenance            build/refresh the record
  python -m src.provenance --summary  print the mixture
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STORE = RAW / "gdelt_volume.csv"
NGRAM_DAYS = RAW / "ngram_days"
CALIB = RAW / "ngram_calibration.json"
RECORD = RAW / "provenance.csv"

DOC_API = "doc_api"
NGRAM_BRIDGE = "ngram_bridge"
FIELDS = ["date", "source", "basis"]


def _rows() -> dict[str, dict[str, str]]:
    if not RECORD.exists():
        return {}
    with RECORD.open(encoding="utf-8") as f:
        return {r["date"]: r for r in csv.DictReader(f)}


def _write(rows: dict[str, dict[str, str]]) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    with RECORD.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for d in sorted(rows):
            w.writerow(rows[d])


def record_bridged(day: str) -> None:
    """Called by fetch_ngrams.heal at the moment of splicing. A recorded
    row always wins over a reconstructed one for the same day."""
    rows = _rows()
    rows[day] = {"date": day, "source": NGRAM_BRIDGE, "basis": "recorded"}
    _write(rows)


def store_days() -> list[str]:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8") as f:
        return [r["date"] for r in csv.DictReader(f)]


def cached_bridge_days() -> set[str]:
    if not NGRAM_DAYS.exists():
        return set()
    return {p.stem for p in NGRAM_DAYS.glob("*.json")}


def calibration_overlap_n() -> int:
    """The upper bound on reconstruction impurity, read from the
    calibration record rather than assumed."""
    if not CALIB.exists():
        return 0
    calib = json.loads(CALIB.read_text(encoding="utf-8"))
    return max((v.get("n_days", 0) for v in calib.values()), default=0)


def build() -> dict[str, dict[str, str]]:
    """Reconstruct provenance for every store day, preserving any row
    already recorded authoritatively."""
    existing = _rows()
    bridged = cached_bridge_days()
    rows: dict[str, dict[str, str]] = {}
    for day in store_days():
        prior = existing.get(day)
        if prior and prior.get("basis") == "recorded":
            rows[day] = prior
            continue
        if day in bridged:
            rows[day] = {"date": day, "source": NGRAM_BRIDGE,
                         "basis": "reconstructed"}
        else:
            rows[day] = {"date": day, "source": DOC_API,
                         "basis": "reconstructed"}
    _write(rows)
    return rows


def by_day() -> dict[str, str]:
    """date -> source, for joining onto any published series."""
    rows = _rows() or build()
    return {d: r["source"] for d, r in rows.items()}


def summary() -> dict[str, object]:
    rows = _rows() or build()
    bridged = [d for d, r in rows.items() if r["source"] == NGRAM_BRIDGE]
    recorded = sum(1 for r in rows.values() if r["basis"] == "recorded")
    n_overlap = calibration_overlap_n()
    return {
        "n_days": len(rows),
        "n_doc_api": len(rows) - len(bridged),
        "n_ngram_bridge": len(bridged),
        "n_recorded": recorded,
        "n_reconstructed": len(rows) - recorded,
        "bridge_first_day": min(bridged) if bridged else None,
        "bridge_last_day": max(bridged) if bridged else None,
        "reconstruction_impurity_bound": n_overlap,
        "what": (
            "Which instrument measured each day. Most days are GDELT DOC "
            "API counts; bridged days were measured by the Web NGrams "
            "feed and divided by a per-channel splice ratio to reach the "
            "API's scale. These are different instruments and the "
            "linking constant is estimated, so any statistic computed "
            "across the boundary inherits that uncertainty."),
        "basis_note": (
            "'recorded' rows were written at the moment of splicing. "
            "'reconstructed' rows are inferred from day-cache presence; "
            f"at most {n_overlap} of the days labelled bridged may in "
            "fact carry a retained API value, because the splice "
            "calibration also sampled overlap days. The bound is the n "
            "from the calibration record, not an estimate."),
        "splice_ratios": (
            json.loads(CALIB.read_text(encoding="utf-8"))
            if CALIB.exists() else {}),
        "generated": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    rows = build()
    s = summary()
    print(f"[provenance] {s['n_days']} store days: "
          f"{s['n_doc_api']} doc_api, {s['n_ngram_bridge']} ngram_bridge "
          f"({s['bridge_first_day']}..{s['bridge_last_day']})")
    print(f"[provenance] {s['n_recorded']} recorded, "
          f"{s['n_reconstructed']} reconstructed "
          f"(impurity bound {s['reconstruction_impurity_bound']} days)")
    if "--summary" in sys.argv:
        print(json.dumps(s, indent=1))
    _ = rows


if __name__ == "__main__":
    main()
