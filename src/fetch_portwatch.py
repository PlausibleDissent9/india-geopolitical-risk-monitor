"""
IMF PortWatch: daily ship transits through the chokepoints India's trade
actually rides. The physical-flow counterpart (V2) to the shipping
salience channel: satellite-AIS transit calls computed by the IMF with a
published methodology, free with attribution, no key.

Four chokepoints: Suez Canal, Bab el-Mandeb, Malacca, Hormuz. Store is
data/raw/portwatch_chokepoints.csv, one row per (date, chokepoint).
Recent days are re-fetched on every update because PortWatch revises.

CLI:
  python -m src.fetch_portwatch --update     # last 21 days, upsert
  python -m src.fetch_portwatch --backfill   # full history
"""
from __future__ import annotations

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "portwatch_chokepoints.csv"

SERVICE = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/"
           "services/Daily_Chokepoints_Data/FeatureServer/0/query")
CHOKEPOINTS = {
    "chokepoint1": "suez",
    "chokepoint4": "bab_el_mandeb",
    "chokepoint5": "malacca",
    "chokepoint6": "hormuz",
}
PAGE = 2000
RETRIES = 3
TIMEOUT_S = 60

FIELDS = ["date", "chokepoint", "n_total", "n_tanker", "n_cargo", "capacity"]


def _query(where: str, offset: int) -> list[dict]:
    params = urllib.parse.urlencode({
        "where": where,
        "outFields": "date,portid,n_total,n_tanker,n_cargo,capacity",
        "orderByFields": "date,portid",
        "returnGeometry": "false",
        "resultOffset": offset,
        "resultRecordCount": PAGE,
        "f": "json",
    })
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(f"{SERVICE}?{params}", timeout=TIMEOUT_S) as r:
                data = json.loads(r.read())
            if "features" in data:
                return [f["attributes"] for f in data["features"]]
            print(f"[portwatch] service error: {data.get('error')}")
        except Exception as e:  # noqa: BLE001 - network errors retried alike
            print(f"[portwatch] {type(e).__name__}: {e}, attempt {attempt + 1}")
        time.sleep(5 * (attempt + 1))
    return []


def fetch(since: date | None) -> list[dict]:
    ids = ",".join(f"'{k}'" for k in CHOKEPOINTS)
    where = f"portid IN ({ids})"
    if since is not None:
        where += f" AND date >= DATE '{since.isoformat()}'"
    rows: list[dict] = []
    offset = 0
    while True:
        batch = _query(where, offset)
        if not batch:
            break
        rows.extend(batch)
        # the service may cap pages below the requested size, so advance
        # by what actually arrived and stop only on an empty page
        offset += len(batch)
    out = []
    for a in rows:
        pid = a.get("portid")
        if pid not in CHOKEPOINTS or not a.get("date"):
            continue
        out.append({
            "date": str(a["date"])[:10],
            "chokepoint": CHOKEPOINTS[pid],
            "n_total": a.get("n_total") or 0,
            "n_tanker": a.get("n_tanker") or 0,
            "n_cargo": a.get("n_cargo") or 0,
            "capacity": a.get("capacity") or 0,
        })
    return out


def upsert(existing: list[dict], new: list[dict]) -> list[dict]:
    """New rows win on (date, chokepoint): PortWatch revises recent days."""
    merged = {(r["date"], r["chokepoint"]): r for r in existing}
    for r in new:
        merged[(r["date"], r["chokepoint"])] = r
    return [merged[k] for k in sorted(merged)]


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
    if args and args[0] == "--backfill":
        since = None
    elif args and args[0] == "--update":
        since = date.today() - timedelta(days=21)
    else:
        print("usage: fetch_portwatch [--update | --backfill]")
        raise SystemExit(2)
    new = fetch(since)
    if not new:
        print("[portwatch] nothing fetched; store unchanged")
        raise SystemExit(1)
    rows = upsert(_load(), new)
    _save(rows)
    span = f"{rows[0]['date']}..{rows[-1]['date']}" if rows else "empty"
    print(f"[portwatch] store: {len(rows)} rows, {span}")


if __name__ == "__main__":
    main()
