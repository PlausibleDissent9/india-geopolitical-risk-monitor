"""
Country monitor machinery (V8). Generic over countries/<name>.json.

A country monitor tracks a country's own registered risk channels on
the same substrate and the same construction as the India instrument
(share of monitored coverage, trailing-percentile transform). It is a
MONITOR, never a comparator: its payload stands alone, its numbers
never enter any India series, and the comparator placebo panel is
untouched (countries/RECIPE.md states why).

REFUSE-UNSIGNED, the load-bearing rule: a country file whose _meta
carries no registration (frozen_on date or REGISTERED status) is
skipped with a loud line. The founder's signature is what turns a
draft into an instrument; this module fetching for an unsigned draft
would let the machine make a construct decision, which it never does.

  python -m src.country_monitor            update+publish all registered
  python -m src.country_monitor china      one country (if registered)
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src import build_index, fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = ROOT / "countries"
RAW = ROOT / "data" / "raw"
SITE_DATA = ROOT / "docs" / "data"

# Same revision tolerance as the India lane: recent days refetch.
UPDATE_WINDOW_DAYS = 14
BACKFILL_START = date(2017, 1, 1)


def registered(meta: dict[str, Any]) -> bool:
    status = str(meta.get("status", ""))
    return bool(meta.get("frozen_on")) or status.startswith("REGISTERED")


def discover() -> dict[str, dict[str, Any]]:
    """All country files, registered or not -- the caller decides how
    loudly to refuse the drafts."""
    out = {}
    for path in sorted(COUNTRIES.glob("*.json")):
        name = path.stem.replace("_DRAFT", "").lower()
        out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def _fetch_dicts(spec: dict[str, Any]) -> dict[str, Any]:
    """Adapt a country registration to fetch_gdelt's dictionary shape:
    registered files may carry terms as {term: rationale} (the rationale
    is the registration's evidence, not query input)."""
    out = {}
    for ch, s in spec["channels"].items():
        terms = s["terms"]
        term_list = list(terms.keys()) if isinstance(terms, dict) else list(terms)
        out[ch] = {"terms": term_list, "anchor": s.get("anchor")}
    return out


def _store_path(name: str) -> Path:
    return RAW / f"country_{name}_volume.csv"


def update(name: str, spec: dict[str, Any]) -> pd.DataFrame:
    """Incremental store update, same pattern as the India lane:
    refetch a trailing revision window, keep settled history."""
    dicts = _fetch_dicts(spec)
    store = _store_path(name)
    today = date.today()
    if store.exists():
        vol = pd.read_csv(store, parse_dates=["date"]).set_index("date")
        start = today - timedelta(days=UPDATE_WINDOW_DAYS)
    else:
        vol = None
        start = BACKFILL_START
    fresh = fetch_gdelt.fetch_all(dicts, start, today)
    if vol is not None and not fresh.empty:
        fresh.index = pd.to_datetime(fresh.index)
        vol = fresh.combine_first(vol)
        # Fresh values win inside the window; combine_first prefers the
        # caller, so this is fresh-over-stored by construction.
    elif vol is None:
        vol = fresh
    vol = vol.sort_index()
    store.parent.mkdir(parents=True, exist_ok=True)
    vol.to_csv(store, index_label="date")
    return vol


def publish(name: str, spec: dict[str, Any], vol: pd.DataFrame) -> None:
    scores = build_index.build_scores(vol)
    last = scores.dropna(how="all").index.max()
    day = scores.loc[last]
    payload = {
        "_meta": {
            "what": (f"Country monitor: {name}. Same substrate and same "
                     "construction as the India instrument (share of "
                     "monitored English coverage per registered channel, "
                     "trailing-730-day percentile). A monitor stands "
                     "beside the India index and never enters any India "
                     "score; channels are this country's own registered "
                     "risk themes. " + build_index.DEFINITION),
            "registration": spec["_meta"].get("status"),
            "frozen_on": spec["_meta"].get("frozen_on"),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "date": last.date().isoformat(),
        "channels": {
            ch: {"label": spec["channels"][ch]["label"],
                 "score": round(float(day[ch]), 1)
                 if pd.notna(day[ch]) else None}
            for ch in spec["channels"]
        },
        "composite": round(float(day["composite"]), 1)
        if pd.notna(day["composite"]) else None,
        "history": {
            "dates": [d.date().isoformat() for d in scores.index],
            **{ch: [None if pd.isna(x) else round(float(x), 1)
                    for x in scores[ch]] for ch in spec["channels"]},
        },
    }
    (SITE_DATA / f"country_{name}.json").write_text(
        json.dumps(payload), encoding="utf-8")
    print(f"[country] wrote country_{name}.json through {payload['date']}")


def main() -> None:
    want = [a.lower() for a in sys.argv[1:]]
    ran = 0
    for name, spec in discover().items():
        if want and name not in want:
            continue
        meta = spec.get("_meta", {})
        if not registered(meta):
            print(f"[country] {name}: UNSIGNED draft -- refused. The "
                  "founder's signature registers it; nothing fetches "
                  "until then.")
            continue
        vol = update(name, spec)
        publish(name, spec, vol)
        ran += 1
    if want and not ran:
        sys.exit(f"[country] nothing ran for {want} (unknown or unsigned)")


if __name__ == "__main__":
    main()
