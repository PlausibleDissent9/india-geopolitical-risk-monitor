"""
GDELT Events v1 daily stream: what happened involving India, counted,
in three layers from one pass over each daily file.

  1. National (data/raw/events_daily.csv): how many events the world's
     press recorded involving India that day, split into verbal and
     material conflict (CAMEO QuadClass 3/4) and protest (root 14), with
     mean Goldstein score, total mentions, and the global row count as
     the normalization denominator (GDELT's coverage grows over time, so
     raw counts drift without it).
  2. Dyads (data/raw/events_dyads.csv): for every partner country, the
     day's India-partner events split cooperative (QuadClass 1/2) versus
     conflictual (3/4), with mean Goldstein and mentions. The relations
     layer: no dictionaries, no curation, just actor codes.
  3. States (data/raw/events_states.csv): events geolocated to an Indian
     state (FIPS ADM1), with conflict and protest counts. The internal
     layer.

Attribution convention: events are dated by the file they arrive in (the
day GDELT recorded them), matching the "when did the world's press carry
this" framing of the salience series, and stated in the codebook.

A day is complete only when it appears in all three stores, so days
collected before a layer existed are reprocessed automatically by the
next backfill batch.

CLI:
  python -m src.fetch_events --update 5      # fill recent missing days
  python -m src.fetch_events --backfill 200  # oldest missing days first
  python -m src.fetch_events 2026-07-29      # one specific day
"""
from __future__ import annotations

import csv
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

from src import geo_split

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
STORE = RAW / "events_daily.csv"
STORE_DYADS = RAW / "events_dyads.csv"
STORE_STATES = RAW / "events_states.csv"

BASE_URL = "http://data.gdeltproject.org/events"
START = date(2017, 1, 1)     # matches the salience series
PUBLISH_LAG_DAYS = 2         # day D's file lands early on D+1 US time
SLEEP_S = 1.0                # static CDN files, not the rate-limited API
RETRIES = 3
TIMEOUT_S = 120

# v1 export column positions (58-column layout)
COL_A1_COUNTRY = 7
COL_A2_COUNTRY = 17
COL_ROOTCODE = 28
COL_QUADCLASS = 29
COL_GOLDSTEIN = 30
COL_MENTIONS = 31
COL_ACTIONGEO_COUNTRY = 51   # FIPS code: India is "IN"
COL_ACTIONGEO_ADM1 = 52      # FIPS state code, e.g. "IN25"
# V20: coordinates beside the FIPS code. GDELT's admin-1 geocoding
# predates Telangana (2014) and Ladakh (2019), so those events land
# under parent codes and their states render grey; the point places
# them correctly (src/geo_split.py). Captured now so the re-split has
# data going forward without a second pass over the archives.
COL_ACTIONGEO_LAT = 53
COL_ACTIONGEO_LON = 54

# GDELT publishes, per event, both the number of ARTICLES mentioning it
# and the number of distinct SOURCES those articles came from. Summed,
# articles_sum/sources_sum is coverage concentration: how many articles
# the average covering outlet contributed.
#
# This is a NEIGHBOUR of src/syndication.py's multiplier, not a
# replication of it, and the distinction matters enough to state before
# anyone treats agreement between them as corroboration. That module
# divides articles by distinct HEADLINES and so measures republication
# of one story; this divides articles by distinct SOURCES and so also
# counts an outlet running three different pieces on one event. Both
# bear on "was that spike more newsrooms or more copies" and neither
# subsumes the other. They are reported separately, never averaged.
#
# Both columns sat unread in a file this fetcher already downloads.
#
# ADDED 2026-08-07: rows stored before this date carry empty values.
# The series is inhomogeneous by construction and says so rather than
# letting a user discover it in an aggregate.
COL_SOURCES = 32
COL_ARTICLES = 33

FIELDS = ["date", "n_global", "n_india", "n_verbal_conflict",
          "n_material_conflict", "n_protest", "goldstein_mean",
          "mentions_sum", "sources_sum", "articles_sum"]
FIELDS_DYADS = ["date", "partner", "n", "n_coop", "n_conflict",
                "goldstein_mean", "mentions_sum", "sources_sum",
                "articles_sum"]
FIELDS_STATES = ["date", "adm1", "n", "n_conflict", "n_protest"]


def _download(day: date) -> bytes | None:
    url = f"{BASE_URL}/{day.strftime('%Y%m%d')}.export.CSV.zip"
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "igrm-research"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"[events] {day} not published yet (404)")
                return None
            print(f"[events] {day} HTTP {e.code}, attempt {attempt + 1}")
        except Exception as e:  # noqa: BLE001 - network errors retried alike
            print(f"[events] {day} {type(e).__name__}: {e}, attempt {attempt + 1}")
        time.sleep(5 * (attempt + 1))
    return None


def compute_day(day: date) -> tuple[dict, list[dict], list[dict]] | None:
    blob = _download(day)
    if blob is None:
        return None
    # Polygons load once per day-file, not per row. Cost MEASURED
    # before enabling, because the morning contract is a promise:
    # 0.09 ms per point with bounding-box rejection, ~0.5 s for a
    # 5,000-event day-file, ~2.5 s for the daily --update 5 window.
    # That is affordable, so it runs by default; IGRM_GEO_SPLIT=0 is
    # the escape hatch if a server ever disagrees.
    geo_states = None
    if os.environ.get("IGRM_GEO_SPLIT", "1") != "0":
        try:
            geo_states = geo_split.load_states()
        except (OSError, ValueError) as e:
            print(f"[events] geometry unavailable ({e}); FIPS codes only")
    n_global = n_india = n_verbal = n_material = n_protest = 0
    goldstein_total = 0.0
    goldstein_n = 0
    mentions = 0
    sources = articles = 0
    # partner -> [n, n_coop, n_conflict, goldstein_sum, goldstein_n,
    #             mentions, sources, articles]
    dyads: dict[str, list[float]] = {}
    # adm1 -> [n, n_conflict, n_protest]
    states: dict[str, list[int]] = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            for raw in io.TextIOWrapper(f, encoding="latin-1", newline=""):
                cols = raw.rstrip("\n").split("\t")
                if len(cols) < 58:
                    continue
                n_global += 1
                a1, a2 = cols[COL_A1_COUNTRY], cols[COL_A2_COUNTRY]
                geo_in = cols[COL_ACTIONGEO_COUNTRY] == "IN"
                if not (a1 == "IND" or a2 == "IND" or geo_in):
                    continue
                n_india += 1
                quad = cols[COL_QUADCLASS]
                root = cols[COL_ROOTCODE]
                if quad == "3":
                    n_verbal += 1
                elif quad == "4":
                    n_material += 1
                if root == "14":
                    n_protest += 1
                try:
                    gold = float(cols[COL_GOLDSTEIN])
                except ValueError:
                    gold = None
                try:
                    ment = int(cols[COL_MENTIONS])
                except ValueError:
                    ment = 0
                try:
                    srcs = int(cols[COL_SOURCES])
                    arts = int(cols[COL_ARTICLES])
                except (ValueError, IndexError):
                    srcs = arts = 0
                if gold is not None:
                    goldstein_total += gold
                    goldstein_n += 1
                mentions += ment
                sources += srcs
                articles += arts
                # dyad layer: a real actor pair with India on one side
                partner = a2 if a1 == "IND" else (a1 if a2 == "IND" else "")
                if partner and partner != "IND":
                    d = dyads.setdefault(partner, [0, 0, 0, 0.0, 0, 0, 0, 0])
                    d[0] += 1
                    if quad in ("1", "2"):
                        d[1] += 1
                    elif quad in ("3", "4"):
                        d[2] += 1
                    if gold is not None:
                        d[3] += gold
                        d[4] += 1
                    d[5] += ment
                    d[6] += srcs
                    d[7] += arts
                # state layer: action geolocated to an Indian state.
                # Placement prefers the POINT (V20): FIPS codes predate
                # Telangana and Ladakh, coordinates do not. The FIPS code
                # remains the fallback when coordinates are absent or fall
                # outside every polygon -- never a snap to the nearest.
                adm1 = cols[COL_ACTIONGEO_ADM1]
                if geo_in and adm1.startswith("IN") and len(adm1) == 4:
                    key = adm1
                    if geo_states is not None:
                        try:
                            lat = float(cols[COL_ACTIONGEO_LAT])
                            lon = float(cols[COL_ACTIONGEO_LON])
                        except (ValueError, IndexError):
                            lat = lon = None  # type: ignore[assignment]
                        if lat is not None and lon is not None:
                            placed = geo_split.place(lat, lon, geo_states)
                            if placed:
                                key = "NE:" + placed
                    s = states.setdefault(key, [0, 0, 0])
                    s[0] += 1
                    if quad in ("3", "4"):
                        s[1] += 1
                    if root == "14":
                        s[2] += 1
    iso = day.isoformat()
    national = {
        "date": iso,
        "n_global": n_global,
        "n_india": n_india,
        "n_verbal_conflict": n_verbal,
        "n_material_conflict": n_material,
        "n_protest": n_protest,
        "goldstein_mean": round(goldstein_total / goldstein_n, 3) if goldstein_n else "",
        "mentions_sum": mentions,
        "sources_sum": sources,
        "articles_sum": articles,
    }
    dyad_rows = [
        {"date": iso, "partner": p, "n": int(d[0]), "n_coop": int(d[1]),
         "n_conflict": int(d[2]),
         "goldstein_mean": round(d[3] / d[4], 3) if d[4] else "",
         "mentions_sum": int(d[5]), "sources_sum": int(d[6]),
         "articles_sum": int(d[7])}
        for p, d in sorted(dyads.items())
    ]
    state_rows = [
        {"date": iso, "adm1": a, "n": s[0], "n_conflict": s[1], "n_protest": s[2]}
        for a, s in sorted(states.items())
    ]
    return national, dyad_rows, state_rows


def _load_keyed(path: Path) -> dict[str, dict]:
    """National store: one row per date."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return {row["date"]: row for row in csv.DictReader(f)}


def _load_grouped(path: Path) -> dict[str, list[dict]]:
    """Dyad/state stores: many rows per date."""
    out: dict[str, list[dict]] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.setdefault(row["date"], []).append(row)
    return out


def _save(path: Path, fields: list[str], rows_by_date: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for k in sorted(rows_by_date):
            v = rows_by_date[k]
            for row in v if isinstance(v, list) else [v]:
                w.writerow(row)


def _load() -> dict[str, dict]:
    return _load_keyed(STORE)


def _missing_days(rows: dict[str, dict] | None = None) -> list[date]:
    """A day counts as done only when all three layers have it. A day
    processed when the day had no state rows would re-run forever, so
    completeness for grouped stores means 'the date key exists', and
    compute_day always emits at least an empty marker for it."""
    national = rows if rows is not None else _load()
    dyads = _load_grouped(STORE_DYADS)
    states = _load_grouped(STORE_STATES)
    # Days GDELT never published (verified permanent 404s) are not
    # missing, they are nonexistent: completeness means every published
    # day is in the store. The list is committed, dated, append-only.
    unavailable_path = RAW / "events_unavailable_days.json"
    unavailable: set[str] = set()
    if unavailable_path.exists():
        import json
        unavailable = set(json.loads(
            unavailable_path.read_text(encoding="utf-8"))["days"])
    last = date.today() - timedelta(days=PUBLISH_LAG_DAYS)
    out = []
    d = START
    while d <= last:
        k = d.isoformat()
        if k not in unavailable and (
                k not in national or k not in dyads or k not in states):
            out.append(d)
        d += timedelta(days=1)
    return out


def run(days: list[date]) -> int:
    national = _load_keyed(STORE)
    dyads = _load_grouped(STORE_DYADS)
    states = _load_grouped(STORE_STATES)
    done = 0

    def save_all() -> None:
        _save(STORE, FIELDS, national)
        _save(STORE_DYADS, FIELDS_DYADS, dyads)
        _save(STORE_STATES, FIELDS_STATES, states)

    for i, day in enumerate(days):
        result = compute_day(day)
        if result is None:
            continue
        nat, dy, st = result
        k = nat["date"]
        national[k] = nat
        # empty layers still get a marker row so the day reads as done
        dyads[k] = dy or [{"date": k, "partner": "", "n": 0, "n_coop": 0,
                           "n_conflict": 0, "goldstein_mean": "",
                           "mentions_sum": 0, "sources_sum": 0,
                           "articles_sum": 0}]
        states[k] = st or [{"date": k, "adm1": "", "n": 0,
                            "n_conflict": 0, "n_protest": 0}]
        done += 1
        print(f"[events] {day}: {nat['n_india']} India events, "
              f"{len(dy)} partner dyads, {len(st)} states")
        if done % 25 == 0:
            save_all()   # periodic saves so an interrupted batch keeps progress
        if i < len(days) - 1:
            time.sleep(SLEEP_S)
    save_all()
    print(f"[events] store has {len(national)} days "
          f"({len(_missing_days(national))} incomplete)")
    return done


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--update":
        n = int(args[1]) if len(args) > 1 else 5
        recent = [d for d in _missing_days()
                  if d >= date.today() - timedelta(days=n + PUBLISH_LAG_DAYS)]
        run(recent)
    elif args and args[0] == "--backfill":
        n = int(args[1]) if len(args) > 1 else 200
        run(_missing_days()[:n])
    elif args:
        run([date.fromisoformat(args[0])])
    else:
        print("usage: fetch_events [--update N | --backfill N | YYYY-MM-DD]")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
