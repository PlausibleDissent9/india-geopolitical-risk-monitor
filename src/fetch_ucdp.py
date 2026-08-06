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
    # "true" for rows from Candidate monthlies (preliminary, revisable);
    # the annual release overwrites them with finalized rows ("false").
    # Mixing preliminary rows in unflagged would be dishonest storage.
    "preliminary",
]

# Candidate monthlies (preliminary, ~1 month lag), probed per month
# after the annual release's coverage ends; a 404 means the month is
# not published yet -- a lag statement, not an error.
CANDIDATE_URL = ("https://ucdp.uu.se/downloads/candidateged/"
                 "GEDEvent_v{y}_0_{m}.csv")
CANDIDATE_YEARS = (25, 26)


def fetch_india_rows() -> list[dict]:
    resp = requests.get(GED_URL, timeout=TIMEOUT_S)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open(GED_CSV_NAME) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))
            return [filter_row(row) for row in reader if row.get("country") == "India"]


def filter_row(row: dict, preliminary: bool = False) -> dict:
    out = {k: row.get(k, "") for k in FIELDS}
    # UCDP timestamps carry a zero time-of-day; the date is the fact.
    out["date_start"] = str(out["date_start"])[:10]
    out["date_end"] = str(out["date_end"])[:10]
    out["preliminary"] = "true" if preliminary else "false"
    return out


def fetch_candidate_rows(after_date: str) -> list[dict]:
    """India rows from Candidate monthlies strictly after the annual
    coverage end (ISO date), flagged preliminary."""
    rows: list[dict] = []
    for y in CANDIDATE_YEARS:
        for m in range(1, 13):
            if f"20{y}-{m:02d}" <= after_date[:7]:
                continue
            r = requests.get(CANDIDATE_URL.format(y=y, m=m),
                             timeout=TIMEOUT_S)
            if r.status_code != 200:
                continue
            reader = csv.DictReader(io.StringIO(r.text))
            got = [filter_row(x, preliminary=True) for x in reader
                   if x.get("country") == "India"]
            rows.extend(got)
            print(f"[ucdp] candidate 20{y}-{m:02d}: {len(got)} India rows")
    return rows


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


def publish_context() -> None:
    """Monthly aggregates from the store to docs/data/ucdp_context.json:
    descriptive CONTEXT BESIDE the salience index, never an input.
    Corridor mapping and outcome variables remain founder-gated V10
    construct decisions; a monthly count of recorded events in India is
    a description of the store, not a construct."""
    import json
    from datetime import datetime, timezone

    months: dict[str, dict] = {}
    for r in _load():
        if (r.get("date_start") or "") < "2017-01":
            continue
        mkey = r["date_start"][:7]
        cell = months.setdefault(
            mkey, {"events": 0, "deaths_best": 0, "preliminary": False})
        cell["events"] += 1
        try:
            cell["deaths_best"] += int(float(r.get("best") or 0))
        except ValueError:
            pass
        if (r.get("preliminary") or "false") == "true":
            cell["preliminary"] = True
    payload = {
        "_meta": {
            "what": ("Monthly organized-violence event counts and "
                     "best-estimate fatalities located in India, from "
                     "UCDP GED (finalized annual release) extended by "
                     "UCDP Candidate monthlies (flagged preliminary per "
                     "month; replaced when finalized). Context BESIDE "
                     "the salience index, never an input: divergence "
                     "between recorded violence and press salience is a "
                     "documented finding, not an error in either."),
            "source": (f"UCDP GED {GED_VERSION} + Candidate, "
                       "https://ucdp.uu.se/downloads/ -- cite UCDP for "
                       "these numbers"),
            "units": "events: count; deaths_best: UCDP point estimate",
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "india": dict(sorted(months.items())),
    }
    out = ROOT / "docs" / "data" / "ucdp_context.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[ucdp] wrote ucdp_context.json: {len(months)} months")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] not in ("--backfill", "--candidates", "--publish"):
        print("usage: fetch_ucdp --backfill | --candidates | --publish")
        raise SystemExit(2)
    if args[0] == "--publish":
        publish_context()
        return
    if args[0] == "--backfill":
        new = fetch_india_rows()
    else:
        existing = _load()
        latest_final = max((r["date_start"] for r in existing
                            if (r.get("preliminary") or "false") == "false"),
                           default="1989-01-01")
        new = fetch_candidate_rows(after_date=latest_final)
    if not new:
        print("[ucdp] nothing fetched; store unchanged")
        raise SystemExit(1)
    rows = upsert(_load(), new)
    _save(rows)
    span = f"{rows[0]['date_start']}..{rows[-1]['date_start']}" if rows else "empty"
    print(f"[ucdp] store: {len(rows)} rows, {span}, GED {GED_VERSION}")


if __name__ == "__main__":
    main()
