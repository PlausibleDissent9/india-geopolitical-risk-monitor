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


def update(name: str, spec: dict[str, Any]) -> pd.DataFrame | None:
    """Incremental store update, PERSISTING EACH CHANNEL as it lands.

    This used to call fetch_gdelt.fetch_all() for every channel and
    write the store once afterwards. A backfill from 2017 is thousands
    of GDELT requests, GDELT rate-limits hard, and fetch_all raises on a
    429 -- so the write was never reached, the store was never created,
    and because the store's absence is what selects BACKFILL_START, the
    next run began the whole doomed backfill again. China ran nightly
    for days and produced nothing while the workflow step, wrapped in
    continue-on-error, reported success every time.

    Exactly the defect src/multilingual.py had. Same fix: write after
    each channel, so a run that dies on the fourth keeps three, and the
    next run only needs the rest.
    """
    dicts = _fetch_dicts(spec)
    store = _store_path(name)
    today = date.today()
    vol: pd.DataFrame | None = None
    if store.exists():
        vol = pd.read_csv(store, parse_dates=["date"]).set_index("date")

    landed = failed = 0
    for ch, chspec in dicts.items():
        # A channel already in the store only needs its revision window;
        # one that is missing needs the whole history.
        have = (vol is not None and ch in vol.columns
                and not vol[ch].dropna().empty)
        start = (today - timedelta(days=UPDATE_WINDOW_DAYS) if have
                 else BACKFILL_START)
        print(f"[country] {name}/{ch}: {start} -> {today}"
              f"{' (revision window)' if have else ' (backfill)'}")
        try:
            series = fetch_gdelt.fetch_channel(
                chspec["terms"], start, today, chspec.get("anchor"))
        except Exception as e:  # noqa: BLE001 -- 429s are expected here
            print(f"[country] {name}/{ch}: FAILED ({type(e).__name__}: {e}); "
                  "keeping what already landed")
            failed += 1
            continue
        if series.empty:
            print(f"[country] {name}/{ch}: no data returned")
            failed += 1
            continue

        frame = series.to_frame(name=ch)
        frame.index = pd.to_datetime(frame.index)
        if vol is not None:
            vol.index = pd.to_datetime(vol.index)
        # Fresh wins inside the window; combine_first prefers the caller.
        vol = frame.combine_first(vol) if vol is not None else frame
        vol = vol.sort_index()
        store.parent.mkdir(parents=True, exist_ok=True)
        vol.to_csv(store, index_label="date")
        landed += 1
        print(f"[country] {name}/{ch}: stored "
              f"({len(series.dropna())} days); {len(vol.columns)}/"
              f"{len(dicts)} channels")

    print(f"[country] {name}: {landed} channel(s) landed, {failed} failed")
    if vol is None:
        raise SystemExit(
            f"[country] {name}: no channel landed; nothing to publish")
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
        # A channel the store has not collected yet publishes as
        # score null with collected=false, rather than crashing the lane
        # or, worse, being silently omitted so the payload looks
        # complete. Backfills land channel by channel now, so a partial
        # monitor is a normal intermediate state and has to be legible
        # as one.
        "channels": {
            ch: {
                "label": spec["channels"][ch]["label"],
                "collected": ch in scores.columns,
                "score": (round(float(day[ch]), 1)
                          if ch in scores.columns and pd.notna(day[ch])
                          else None),
            }
            for ch in spec["channels"]
        },
        "n_channels_collected": sum(1 for ch in spec["channels"]
                                    if ch in scores.columns),
        "n_channels_registered": len(spec["channels"]),
        "composite": (round(float(day["composite"]), 1)
                      if "composite" in scores.columns
                      and pd.notna(day["composite"]) else None),
        "history": {
            "dates": [d.date().isoformat() for d in scores.index],
            **{ch: [None if pd.isna(x) else round(float(x), 1)
                    for x in scores[ch]]
               for ch in spec["channels"] if ch in scores.columns},
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
