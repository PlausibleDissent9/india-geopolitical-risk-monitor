"""
UCDP Georeferenced Event Dataset (GED): the ground-truth conflict-event
record IGRM's V10 outcome layer will be scored against. Uppsala Conflict
Data Program, free with attribution, no key, via the versioned bulk CSV
release (not the live API, which now requires an x-ucdp-access-token --
see NOTES_FOR_ISHAN.md for that standing ask).

Scope note: this module only fetches and filters to country == India.
It does NOT define adverse-outcome variables, does NOT pick a corridor
(e.g. pakistan_west) or dyad split, and is NOT wired into run_daily.py.
Those are V10 construct decisions and go through the founder-decides
process (mission spec 4a) before anything is registered or scored.

Store is data/raw/ucdp_events.csv, one row per GED event id, India only.
Coverage is whatever the pinned release covers (GED 25.1: 1989-2024);
each new UCDP release is a new pinned version, never a silent swap.

CLI:
  python -m src.fetch_ucdp --backfill   # download the pinned release, filter, save
"""
from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "ucdp_events.csv"

# Pinned release. Bump deliberately when a new GED version ships; UCDP
# revises prior years on each annual release, so re-running --backfill
# after a version bump can change historical rows, same as any other
# versioned dataset here (dated methodology note expected on bump).
GED_VERSION = "25.1"
GED_URL = (
    f"https://ucdp.uu.se/downloads/ged/"
    f"ged{GED_VERSION.replace('.', '')}-csv.zip"
)
GED_CSV_NAME = f"GEDEvent_v{GED_VERSION.replace('.', '_')}.csv"
TIMEOUT_S = 300

FIELDS = [
    "id", "year", "type_of_violence", "conflict_name", "dyad_name",
    "side_a", "side_b", "country", "region", "date_start", "date_end",
    "deaths_a", "deaths_b", "deaths_civilians", "deaths_unknown",
    "best", "high", "low", "where_coordinates", "latitude", "longitude",
]


def fetch_india_rows() -> list[dict]:
    resp = requests.get(GED_URL, timeout=TIMEOUT_S)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open(GED_CSV_NAME) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            return [filter_row(row) for row in reader if row.get("country") == "India"]


def filter_row(row: dict) -> dict:
    out = {k: row.get(k, "") for k in FIELDS}
    # UCDP timestamps carry a zero time-of-day; the date is the fact.
    out["date_start"] = str(out["date_start"])[:10]
    out["date_end"] = str(out["date_end"])[:10]
    return out


def upsert(existing: list[dict], new: list[dict]) -> list[dict]:
    """New rows win on id: a version bump can revise a prior GED event."""
    merged = {r["id"]: r for r in existing}
    for r in new:
        merged[r["id"]] = r
    return [merged[k] for k in sorted(merged, key=lambda x: (merged[x]["date_start"], x))]


def _load() -> list[dict]:
    if not STORE.exists():
        return []
    with STORE.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _save(rows: list[dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] != "--backfill":
        print("usage: fetch_ucdp --backfill")
        raise SystemExit(2)
    new = fetch_india_rows()
    if not new:
        print("[ucdp] nothing fetched; store unchanged")
        raise SystemExit(1)
    rows = upsert(_load(), new)
    _save(rows)
    span = f"{rows[0]['date_start']}..{rows[-1]['date_start']}" if rows else "empty"
    print(f"[ucdp] store: {len(rows)} rows, {span}, GED {GED_VERSION}")


if __name__ == "__main__":
    main()
