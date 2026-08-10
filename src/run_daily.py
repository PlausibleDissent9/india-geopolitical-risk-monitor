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
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from . import (
    build_index,
    event_study,
    fetch_gdelt,
    fetch_markets,
    final_publication,
    render_site,
)

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


def _fail_loudly_on_partial_data(
    volume: pd.DataFrame, required_final_day: date
) -> pd.DataFrame:
    """A silently thin dataset must fail the workflow, not publish
    (spec B7): partial data on the site is worse than a red run."""
    problems = []
    finalized = volume.copy()
    if volume.empty:
        problems.append("volume store is empty")
    else:
        idx = pd.to_datetime(volume.index)
        # D0 may exist in a third-party response or a pre-fix store.  It is
        # never eligible for a finalized run, even if it happens to contain
        # non-null values at the instant this process reads it.
        if any(day > required_final_day for day in idx.date):
            problems.append(
                f"volume store contains rows after exact final target "
                f"{required_final_day}"
            )
        finalized = volume.loc[idx.date <= required_final_day].copy()
        if finalized.empty:
            problems.append("volume store has no rows at or before the final target")
            idx = pd.DatetimeIndex([])
        else:
            idx = pd.to_datetime(finalized.index)
        if required_final_day not in set(idx.date):
            problems.append(
                f"exact D-1 target {required_final_day} is absent from the volume store"
            )
        else:
            target_row = finalized.loc[idx.date == required_final_day]
            if len(target_row) != 1 or target_row.isna().any(axis=None):
                problems.append(
                    f"exact D-1 target {required_final_day} is incomplete"
                )
        if not idx.empty and idx.max().date() != required_final_day:
            problems.append(
                f"finalized frame ends {idx.max().date()}, expected {required_final_day}"
            )
    if not finalized.empty:
        idx = pd.to_datetime(finalized.index)
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
        tail = finalized.loc[pd.to_datetime(finalized.index)
                             >= last - pd.Timedelta(days=30)]
        for ch in finalized.columns:
            if tail[ch].dropna().empty:
                problems.append(f"channel {ch!r} has no data in its last 30 days")
    if problems:
        raise SystemExit("[fail-loud] refusing to publish partial data: "
                         + "; ".join(problems))
    return finalized


def _require_exact_target_scores(
    scores: pd.DataFrame,
    scores7: pd.DataFrame,
    target: date,
) -> None:
    """Refuse a target whose daily or headline composite is unpublishable."""

    problems: list[str] = []
    for label, frame in (("daily", scores), ("headline", scores7)):
        idx = pd.to_datetime(frame.index)
        target_rows = frame.loc[idx.date == target]
        if len(target_rows) != 1:
            problems.append(f"{label} score frame has no unique target row")
            continue
        if target_rows.isna().any(axis=None):
            problems.append(f"{label} target score row contains nulls")
        composite = target_rows.iloc[0].get("composite")
        if pd.isna(composite):
            problems.append(f"{label} target composite is null")
    if problems:
        raise SystemExit(
            "[fail-loud] refusing unscorable D-1 target: " + "; ".join(problems)
        )


def _require_written_target(
    target: date,
    *,
    site_data: Path = SITE_DATA,
) -> None:
    """Reopen the public bytes and prove they publish the exact target."""

    try:
        final_publication.require_written_final_target(target, site_data=site_data)
    except final_publication.FinalPublicationError as exc:
        raise SystemExit(
            "[fail-loud] written latest/history do not end at finite exact D-1 target: "
            f"{exc.detail}"
        ) from exc


def _published_day() -> date | None:
    try:
        value = json.loads(
            (SITE_DATA / "latest.json").read_text(encoding="utf-8")
        )["date"]
        day = date.fromisoformat(value)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return day if day.isoformat() == value else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--final-only", action="store_true")
    ap.add_argument("--target", type=date.fromisoformat)
    ap.add_argument(
        "--contract-today",
        type=date.fromisoformat,
        help="frozen UTC date paired with --target for one publication attempt",
    )
    # Full GDELT DOC API range. The per-chunk cache in fetch_gdelt plus its
    # resume logic (only missing dates are fetched) make the 2017 range
    # feasible where a single uncached run previously was not: an interrupted
    # backfill restarts where it stopped instead of re-spending the rate
    # budget from scratch.
    ap.add_argument("--from", dest="from_date", default="2017-01-01")
    args = ap.parse_args()
    today_utc = args.contract_today or datetime.now(timezone.utc).date()
    target = args.target or final_publication.required_target(today_utc)
    final_publication.require_exact_target(target, today_utc)

    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    backfill_from = None
    if args.backfill:
        y, m, d = (int(x) for x in args.from_date.split("-"))
        backfill_from = date(y, m, d)

    print("[1/5] GDELT volumes")
    store = Path(fetch_gdelt.RAW_DIR) / "gdelt_volume.csv"
    if args.final_only:
        volume = pd.read_csv(store, parse_dates=["date"]).set_index("date")
        volume.index = [d.date() for d in volume.index]
    else:
        published = _published_day()
        if backfill_from is None and store.exists() and published is None:
            raise SystemExit(
                "[fail-loud] published final boundary is unreadable; "
                "refusing an incremental fetch that could revise prior finals"
            )
        try:
            volume = fetch_gdelt.load_or_update(
                dictionaries,
                backfill_from=backfill_from,
                end_date=target,
                immutable_through=(None if backfill_from else published),
            )
        except (RuntimeError, SystemExit) as e:
            # DOC API down (July 2026 disruption): fall back to the store,
            # which the ngram bridge keeps current. Exact D-1 validation
            # below still refuses an unavailable or partial target frame.
            if backfill_from is not None or not store.exists():
                raise
            print(f"[warn] DOC API unavailable ({e}); using ngram-healed store")
            volume = pd.read_csv(store, parse_dates=["date"]).set_index("date")
            volume.index = [d.date() for d in volume.index]

    try:
        volume = _fail_loudly_on_partial_data(volume, target)
    except SystemExit:
        # The source acquisition step may already have recorded the more
        # specific source_unavailable/acquisition_failed state.  Do not
        # overwrite it with a less informative pipeline label.
        raise
    # A target measured by the registered ngram bridge may be promoted only
    # from the exact 48/48, hash-bound candidate prepared above.  This also
    # fails closed over legacy heal caches that were written before promotion
    # receipts existed. DOC-only publication has no registered proof mode yet
    # and is refused rather than silently exempted.
    try:
        final_publication.require_promotion_receipt(
            target,
            require_bridge_receipt=True,
        )
    except final_publication.FinalPublicationError as exc:
        raise SystemExit(
            "[fail-loud] refusing unverified D-1 promotion: "
            f"{exc.classification}: {exc.detail}"
        ) from exc

    print("[3/5] Index + episodes")
    scores = build_index.build_scores(volume)
    scores7 = build_index.build_scores7(volume)
    _require_exact_target_scores(scores, scores7, target)
    episodes = build_index.detect_all_episodes(volume)

    if not args.final_only:
        print("[2/5] Markets")
        _, derived = fetch_markets.load_or_update(start=args.from_date)
        print("[4/5] Event study")
        results = event_study.run_event_study(episodes, derived)
        event_study.write_output(results)
    else:
        print("[2/5] Markets skipped (final-only lane; no score dependency)")
        print("[4/5] Event study unchanged (final-only lane)")

    print("[5/5] Publish")
    labels = {ch: spec["label"] for ch, spec in dictionaries.items()
              if not ch.startswith("_")}
    build_index.write_site_outputs(scores, episodes, labels,
                                   scores7=scores7)
    _require_written_target(target)
    if not args.final_only:
        publish_latest_note()
    render_site.main()
    final_publication.mark_finalized(target)
    print("[done] site data written to docs/data/")


if __name__ == "__main__":
    main()
