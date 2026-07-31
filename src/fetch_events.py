"""
GDELT Events v1 daily stream: what happened involving India, counted.

A second measurement modality alongside press salience. Each GDELT v1
daily export (one zip per calendar day) is reduced to one row of India
metrics: how many events the world's press recorded involving India that
day, how many were verbal or material conflict (CAMEO QuadClass 3/4),
how many were protests (root code 14), the mean Goldstein score, and
total mentions. The global row count is kept as the normalization
denominator, because GDELT's coverage grows over time and raw counts
drift with it.

Attribution convention: events are dated by the file they arrive in (the
day GDELT recorded them), matching the "when did the world's press carry
this" framing of the salience series, and stated in the codebook.

Store: data/raw/events_daily.csv, one row per day, idempotent.

CLI:
  python -m src.fetch_events --update 5      # fill recent missing days
  python -m src.fetch_events --backfill 200  # oldest missing days first
  python -m src.fetch_events 2026-07-29      # one specific day
"""
from __future__ import annotations

import csv
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "events_daily.csv"

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

FIELDS = ["date", "n_global", "n_india", "n_verbal_conflict",
          "n_material_conflict", "n_protest", "goldstein_mean",
          "mentions_sum"]


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


def compute_day(day: date) -> dict | None:
    blob = _download(day)
    if blob is None:
        return None
    n_global = n_india = n_verbal = n_material = n_protest = 0
    goldstein_total = 0.0
    goldstein_n = 0
    mentions = 0
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        with z.open(z.namelist()[0]) as f:
            for raw in io.TextIOWrapper(f, encoding="latin-1", newline=""):
                cols = raw.rstrip("\n").split("\t")
                if len(cols) < 58:
                    continue
                n_global += 1
                if not (cols[COL_A1_COUNTRY] == "IND"
                        or cols[COL_A2_COUNTRY] == "IND"
                        or cols[COL_ACTIONGEO_COUNTRY] == "IN"):
                    continue
                n_india += 1
                quad = cols[COL_QUADCLASS]
                if quad == "3":
                    n_verbal += 1
                elif quad == "4":
                    n_material += 1
                if cols[COL_ROOTCODE] == "14":
                    n_protest += 1
                try:
                    goldstein_total += float(cols[COL_GOLDSTEIN])
                    goldstein_n += 1
                except ValueError:
                    pass
                try:
                    mentions += int(cols[COL_MENTIONS])
                except ValueError:
                    pass
    return {
        "date": day.isoformat(),
        "n_global": n_global,
        "n_india": n_india,
        "n_verbal_conflict": n_verbal,
        "n_material_conflict": n_material,
        "n_protest": n_protest,
        "goldstein_mean": round(goldstein_total / goldstein_n, 3) if goldstein_n else "",
        "mentions_sum": mentions,
    }


def _load() -> dict[str, dict]:
    if not STORE.exists():
        return {}
    with STORE.open(encoding="utf-8") as f:
        return {row["date"]: row for row in csv.DictReader(f)}


def _save(rows: dict[str, dict]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])


def _missing_days(rows: dict[str, dict]) -> list[date]:
    last = date.today() - timedelta(days=PUBLISH_LAG_DAYS)
    out = []
    d = START
    while d <= last:
        if d.isoformat() not in rows:
            out.append(d)
        d += timedelta(days=1)
    return out


def run(days: list[date]) -> int:
    rows = _load()
    done = 0
    for i, day in enumerate(days):
        row = compute_day(day)
        if row is None:
            continue
        rows[row["date"]] = row
        done += 1
        print(f"[events] {day}: {row['n_india']} India events "
              f"({row['n_material_conflict']} material conflict, "
              f"{row['n_protest']} protest) of {row['n_global']} global")
        if done % 25 == 0:
            _save(rows)   # periodic saves so an interrupted batch keeps progress
        if i < len(days) - 1:
            time.sleep(SLEEP_S)
    _save(rows)
    print(f"[events] store has {len(rows)} days "
          f"({len(_missing_days(rows))} still missing)")
    return done


def main() -> None:
    args = sys.argv[1:]
    rows = _load()
    if args and args[0] == "--update":
        n = int(args[1]) if len(args) > 1 else 5
        recent = [d for d in _missing_days(rows)
                  if d >= date.today() - timedelta(days=n + PUBLISH_LAG_DAYS)]
        run(recent)
    elif args and args[0] == "--backfill":
        n = int(args[1]) if len(args) > 1 else 200
        run(_missing_days(rows)[:n])
    elif args:
        run([date.fromisoformat(args[0])])
    else:
        print("usage: fetch_events [--update N | --backfill N | YYYY-MM-DD]")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
