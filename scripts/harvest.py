"""
Patient chunk harvester for the first backfill.

GDELT's limiter is intermittent: most requests 429, occasional ones sail
through. A normal backfill pass is all-or-nothing -- one exhausted chunk
aborts the run and the pass's other successes are wasted effort. This
script inverts that: it walks the list of still-missing historical
chunks, tries ONE request each, banks every success into the same cache
run_daily reads, and keeps circling until nothing is missing.

Progress is monotone: a cached chunk is never refetched (keys are
month-end anchored, so they survive date rollovers). Once every chunk is
cached, `python -m src.run_daily --backfill` completes from cache with
only the short recent tail hitting the network.

Usage:  python scripts/harvest.py [seconds_between_requests]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.fetch_gdelt import (  # noqa: E402
    API,
    CACHE_SETTLE_DAYS,
    CHUNK_CACHE_DIR,
    HEADERS,
    build_queries,
)

ROOT = Path(__file__).resolve().parents[1]
START = date(2017, 1, 1)
DEFAULT_SPACING_S = 20.0
PASS_COOLDOWN_S = 120.0


def settle_split(today: date) -> date:
    """Same stable month-end boundary src.fetch_gdelt uses."""
    split = date(today.year, today.month, 1) - timedelta(days=1)
    if (today - split).days <= CACHE_SETTLE_DAYS:
        split = date(split.year, split.month, 1) - timedelta(days=1)
    return split


def needed_chunks() -> list[tuple[str, str, date, date]]:
    """(label, query, start, end) for every historical chunk not cached."""
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dicts = json.load(f)
    split = settle_split(date.today())
    out = []
    for ch, spec in dicts.items():
        if ch.startswith("_"):
            continue
        for qi, query in enumerate(build_queries(spec["terms"], spec.get("anchor")), 1):
            key = hashlib.sha1(f"{query}|{START}|{split}".encode()).hexdigest()[:16]
            if not (CHUNK_CACHE_DIR / f"{key}.json").exists():
                out.append((f"{ch} q{qi}", query, START, split))
    return out


def try_fetch(query: str, start: date, end: date) -> list[dict] | None:
    """One request. Returns rows on success, None on throttle/failure."""
    params = {
        "query": query,
        "mode": "timelinevol",
        "format": "json",
        "startdatetime": start.strftime("%Y%m%d") + "000000",
        "enddatetime": end.strftime("%Y%m%d") + "235959",
    }
    try:
        r = requests.get(API, params=params, timeout=120, headers=HEADERS)
    except requests.RequestException as e:
        print(f"    network error: {e}")
        return None
    if r.status_code != 200:
        return None
    if not r.text.lstrip().startswith("{"):
        return None
    try:
        timeline = r.json().get("timeline", [])
    except ValueError:
        return None
    return timeline[0].get("data", []) if timeline else []


def bank(query: str, start: date, end: date, rows: list[dict]) -> Path:
    key = hashlib.sha1(f"{query}|{start}|{end}".encode()).hexdigest()[:16]
    CHUNK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CHUNK_CACHE_DIR / f"{key}.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def main() -> None:
    spacing = float(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SPACING_S
    attempts = 0
    while True:
        missing = needed_chunks()
        if not missing:
            print("[harvest] COMPLETE: every historical chunk is cached")
            return
        print(f"[harvest] {len(missing)} chunk(s) missing: "
              f"{', '.join(m[0] for m in missing)}")
        for label, query, start, end in missing:
            attempts += 1
            rows = try_fetch(query, start, end)
            if rows:
                bank(query, start, end, rows)
                print(f"[harvest] BANKED {label} ({len(rows)} days) "
                      f"after {attempts} attempts", flush=True)
            else:
                print(f"[harvest]   throttled: {label}", flush=True)
            time.sleep(spacing)
        print(f"[harvest] pass done; cooling {PASS_COOLDOWN_S:.0f}s", flush=True)
        time.sleep(PASS_COOLDOWN_S)


if __name__ == "__main__":
    main()
