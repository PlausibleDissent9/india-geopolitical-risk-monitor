"""
IGRM pipeline entrypoint.

Daily:     python -m src.run_daily
Backfill:  python -m src.run_daily --backfill        (from 2017-01-01)
           python -m src.run_daily --backfill --from 2018-06-01

Order: GDELT volumes -> markets -> index -> episodes -> event study ->
publish notes -> site outputs in docs/data/.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import build_index, event_study, fetch_gdelt, fetch_markets, render_site

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"


def publish_latest_note() -> None:
    """Copy the newest notes/*.md into docs/data/note_latest.json so the
    site can render it. Notes are Ishan's writing; this only publishes."""
    notes_dir = ROOT / "notes"
    site_data = ROOT / "docs" / "data"
    site_data.mkdir(parents=True, exist_ok=True)
    mds = sorted(p for p in notes_dir.glob("*.md") if not p.name.endswith(".example"))
    payload = {"filename": None, "markdown": ""}
    if mds:
        latest = mds[-1]
        payload = {"filename": latest.name,
                   "markdown": latest.read_text(encoding="utf-8")}
    (site_data / "note_latest.json").write_text(
        json.dumps(payload), encoding="utf-8")


def _fail_loudly_on_partial_data(volume: pd.DataFrame) -> None:
    """A silently thin dataset must fail the workflow, not publish
    (spec B7): partial data on the site is worse than a red run."""
    problems = []
    if volume.empty:
        problems.append("volume store is empty")
    else:
        idx = pd.to_datetime(volume.index)
        last = idx.max()
        # An incremental run on a store that was never backfilled would
        # otherwise publish an all-null site (percentiles need 180+ days).
        if (last - idx.min()).days < 400:
            problems.append(
                f"store spans only {(last - idx.min()).days} days -- "
                "run the backfill first"
            )
        # Staleness is only a failure once the site has published before:
        # a first backfill whose recent tail was throttled still carries a
        # decade of history and should go live, stale-dated and honest,
        # rather than not at all. Subsequent runs must stay fresh.
        stale_days = (pd.Timestamp(date.today()) - last).days
        first_publish = not (SITE_DATA / "latest.json").exists()
        if stale_days > 5:
            if first_publish:
                print(f"[warn] first publish: data ends {last.date()} "
                      f"({stale_days} days ago); the next run fills the tail")
            else:
                problems.append(f"data ends {last.date()}, more than 5 days ago")
        tail = volume.loc[pd.to_datetime(volume.index)
                          >= last - pd.Timedelta(days=30)]
        for ch in volume.columns:
            if tail[ch].dropna().empty:
                problems.append(f"channel {ch!r} has no data in its last 30 days")
    if problems:
        raise SystemExit("[fail-loud] refusing to publish partial data: "
                         + "; ".join(problems))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    # Full GDELT DOC API range. The per-chunk cache in fetch_gdelt plus its
    # resume logic (only missing dates are fetched) make the 2017 range
    # feasible where a single uncached run previously was not: an interrupted
    # backfill restarts where it stopped instead of re-spending the rate
    # budget from scratch.
    ap.add_argument("--from", dest="from_date", default="2017-01-01")
    args = ap.parse_args()

    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    backfill_from = None
    if args.backfill:
        y, m, d = (int(x) for x in args.from_date.split("-"))
        backfill_from = date(y, m, d)

    print("[1/5] GDELT volumes")
    store = Path(fetch_gdelt.RAW_DIR) / "gdelt_volume.csv"
    try:
        volume = fetch_gdelt.load_or_update(dictionaries, backfill_from=backfill_from)
    except (RuntimeError, SystemExit) as e:
        # DOC API down (July 2026 disruption): fall back to the store,
        # which the ngram bridge (src/fetch_ngrams, run by CI before this)
        # keeps current per the GDELT maintainer's guidance. The fail-loud
        # gate below still refuses stale or partial data.
        if backfill_from is not None or not store.exists():
            raise
        print(f"[warn] DOC API unavailable ({e}); using ngram-healed store")
        volume = pd.read_csv(store, parse_dates=["date"]).set_index("date")
        volume.index = [d.date() for d in volume.index]

    print("[2/5] Markets")
    _, derived = fetch_markets.load_or_update(start=args.from_date)

    print("[3/5] Index + episodes")
    _fail_loudly_on_partial_data(volume)
    scores = build_index.build_scores(volume)
    episodes = build_index.detect_all_episodes(volume)

    print("[4/5] Event study")
    results = event_study.run_event_study(episodes, derived)
    event_study.write_output(results)

    print("[5/5] Publish")
    labels = {ch: spec["label"] for ch, spec in dictionaries.items()
              if not ch.startswith("_")}
    build_index.write_site_outputs(scores, episodes, labels,
                                   scores7=build_index.build_scores7(volume))
    publish_latest_note()
    render_site.main()
    print("[done] site data written to docs/data/")


if __name__ == "__main__":
    main()
