"""
V3 comparator series: one shared risk vocabulary, four country anchors.

Registered in comparators.json before the first fetch. Same GDELT
machinery as the channels (fetch_gdelt.fetch_channel), same trailing
percentile convention downstream. India runs through the identical
instrument so cross-country lines are comparable by construction; the
five-channel index stays the primary product.

Store: data/raw/comparator_salience.csv   date x country, GDELT share
Site:  docs/data/comparators.json         weekly percentiles per country

  python -m src.comparators --backfill    full 2017-present fetch
  python -m src.comparators --update      14-day tail merge, then publish
  python -m src.comparators --publish     recompute site JSON only
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import fetch_gdelt
from .build_index import _trailing_percentile

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "comparators.json"
STORE = ROOT / "data" / "raw" / "comparator_salience.csv"
SITE_JSON = ROOT / "docs" / "data" / "comparators.json"

START = date(2017, 1, 1)


def _spec() -> dict:
    with open(SPEC, encoding="utf-8") as f:
        return json.load(f)


def _load_store() -> pd.DataFrame | None:
    if not STORE.exists():
        return None
    df = pd.read_csv(STORE, parse_dates=["date"])
    df["date"] = df["date"].dt.date
    return df.set_index("date").sort_index()


def update(
    backfill: bool = False,
    *,
    deadline_monotonic: float | None = None,
) -> pd.DataFrame:
    spec = _spec()
    terms = spec["shared_terms"]
    existing = _load_store()
    today = date.today()
    start = START if (backfill or existing is None) else today - timedelta(days=14)
    merged = existing.copy() if existing is not None and not backfill else None
    landed = 0
    failed = 0
    for key, c in spec["countries"].items():
        print(f"[comparators] {key}: {start} -> {today}")
        try:
            series = fetch_gdelt.fetch_channel(
                terms,
                start,
                today,
                c["anchor"],
                deadline_monotonic=deadline_monotonic,
            )
        except fetch_gdelt.AcquisitionDeadlineExceeded as exc:
            print(f"[comparators] acquisition budget exhausted: {exc}")
            failed += 1
            break
        except Exception as exc:  # noqa: BLE001 -- one country must bank others
            print(f"[comparators] {key}: FAILED "
                  f"({type(exc).__name__}: {exc})")
            failed += 1
            continue
        if series.empty:
            print(f"[comparators] {key}: no data returned")
            failed += 1
            continue

        frame = series.to_frame(name=key)
        frame.index = pd.Index(frame.index, name="date")
        merged = frame.combine_first(merged) if merged is not None else frame
        merged = merged.sort_index()
        STORE.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(STORE, index_label="date")
        landed += 1
        print(f"[comparators] {key}: stored; {landed} country series landed")

    if merged is None:
        raise RuntimeError(
            "[comparators] no country series landed and no prior store exists"
        )
    if landed == 0 and failed:
        raise RuntimeError(
            "[comparators] acquisition failed before any country series landed"
        )
    return merged


def publish() -> None:
    sal = _load_store()
    if sal is None:
        raise SystemExit("[comparators] no store; run --backfill first")
    spec = _spec()
    sal.index = pd.to_datetime(sal.index)
    out: dict = {
        "_meta": {
            "what": ("Comparator country salience: one shared risk vocabulary "
                     "anchored per country (comparators.json v1.0.0), each "
                     "series a percentile of its own trailing 730 days, then "
                     "weekly means. Cross-country levels reflect Anglophone "
                     "press attention; association, not risk."),
            "generated": date.today().isoformat(),
        },
        "countries": {},
    }
    for key, c in spec["countries"].items():
        if key not in sal.columns:
            continue
        series = sal[key].sort_index()
        pct = _trailing_percentile(series)
        wk = pct.resample("W-MON").mean().dropna().round(1)
        # A trailing week whose label postdates the last observed day is
        # a partial week wearing a full week's date; publishing it would
        # compare one country's half-week against another's complete
        # one. Drop it.
        last_obs = series.dropna().index.max()
        wk = wk[wk.index <= last_obs]
        if len(wk) < 26:
            continue
        out["countries"][key] = {
            "label": c["label"],
            "weeks": [d.date().isoformat() for d in wk.index],
            "pct": wk.tolist(),
            "latest": float(wk.iloc[-1]),
        }
    SITE_JSON.parent.mkdir(parents=True, exist_ok=True)
    SITE_JSON.write_text(json.dumps(out), encoding="utf-8")
    print(f"[comparators] wrote comparators.json: "
          f"{ {k: v['latest'] for k, v in out['countries'].items()} }")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument(
        "--deadline-seconds",
        type=float,
        default=None,
        help="hard acquisition budget; leaves workflow time to persist and publish",
    )
    args = ap.parse_args()
    if args.backfill or args.update:
        deadline = (time.monotonic() + args.deadline_seconds
                    if args.deadline_seconds is not None else None)
        update(backfill=args.backfill, deadline_monotonic=deadline)
        publish()
    elif args.publish:
        publish()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
