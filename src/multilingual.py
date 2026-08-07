"""
V5 measurement quality: the English-bias audit.

For each channel and each registered language (languages.json,
registered before the first fetch), the identical frozen dictionary is
fetched with a sourcelang operator, giving that language's own
coverage-share series. Each series ranks against its own trailing 730
days; the published number per channel is the divergence between the
English percentile and the mean non-English percentile, weekly. A
large positive divergence means the story is louder in English than in
the registered languages; negative means the non-English press is
carrying it harder. The audit measures the instrument's own bias and
never enters the composite.

Store: data/raw/multilingual_salience.csv (date x channel_lang)
Site:  docs/data/multilingual.json

  python -m src.multilingual --backfill
  python -m src.multilingual --update
  python -m src.multilingual --publish
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import fetch_gdelt
from .build_index import _trailing_percentile, build_scores

ROOT = Path(__file__).resolve().parents[1]
LANGS = ROOT / "languages.json"
DICTS = ROOT / "dictionaries.json"
STORE = ROOT / "data" / "raw" / "multilingual_salience.csv"

# How much one run may attempt. The CI step allows 45 minutes; these
# leave room to finish cleanly inside it and are overridable so a
# quieter window can do more without a code change.
MAX_SERIES_PER_RUN = int(os.environ.get("IGRM_ML_MAX_SERIES", "4"))
# The budget must leave room for the LAST series to finish after it
# starts. A series that is throttled the whole way costs
# RETRIES backoffs (30s, 60s ... 180s) plus RETRIES x SLEEP_S -- twelve
# minutes today, per chunk. The CI step allows 45.
#
# At 30 minutes the arithmetic was 30 + 12 = 42 against 45: three minutes
# of margin, and being killed mid-series is exactly the failure this
# bound exists to prevent (2026-08-07, 09:44:14 to 10:29:27, killed at
# the timeout with zero series completed). 25 leaves eight.
#
# test_multilingual_budget.py recomputes this from the real constants
# rather than trusting the comment, and fails when the arithmetic stops
# working -- including on the day the 2019-onward range grows past
# CHUNK_DAYS and the worst case per series doubles.
DEADLINE_SECONDS = int(os.environ.get("IGRM_ML_DEADLINE_S", str(25 * 60)))
SITE_JSON = ROOT / "docs" / "data" / "multilingual.json"

START = date(2019, 1, 1)  # three-language roster; extend range with roster


def _specs() -> tuple[dict, dict]:
    with open(LANGS, encoding="utf-8") as f:
        langs = json.load(f)["languages"]
    with open(DICTS, encoding="utf-8") as f:
        dicts = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    return langs, dicts


def _load_store() -> pd.DataFrame | None:
    if not STORE.exists():
        return None
    df = pd.read_csv(STORE, parse_dates=["date"])
    return df.set_index("date").sort_index()


def expected_keys() -> list[str]:
    langs, dicts = _specs()
    return [f"{ch}_{lg}" for ch in dicts for lg in langs]


def missing_keys() -> list[str]:
    """Series the store still lacks. This, not the store's existence, is
    what 'done' means -- see the note in update()."""
    store = _load_store()
    if store is None:
        return expected_keys()
    return [k for k in expected_keys()
            if k not in store.columns or store[k].dropna().empty]


def update(backfill: bool = False) -> pd.DataFrame | None:
    """Fetch the registered per-language series, PERSISTING EACH ONE as
    it lands.

    This function used to build all fifteen series into a dict and write
    the store once at the end. Fifteen series x seven years is a lot of
    GDELT requests, and a single 429 anywhere in the loop raised past the
    write -- so the store was never created, not once, while every
    completed fetch still landed in the chunk cache.

    The workflow around it then read that growing chunk cache as
    progress, re-dispatched itself, and stayed green because the fetch
    step is continue-on-error. Seventy runs across seven days,
    twenty-six on 2026-08-06 alone, none of which could ever have
    finished: a loop that cost real CI minutes to look busy.

    Writing after each series makes the work cumulative. A batch that
    dies on its ninth series keeps the first eight, and the next run
    skips them and starts at the ninth -- so the store converges instead
    of restarting.
    """
    langs, dicts = _specs()
    store = _load_store()
    today = date.today()
    start = START if backfill else today - timedelta(days=14)

    todo = missing_keys() if backfill else expected_keys()
    if not todo:
        print("[multilingual] every registered series is in the store")
        return store

    print(f"[multilingual] {len(todo)} series to fetch "
          f"({len(expected_keys()) - len(todo)} already stored)")

    # BOUNDED WORK PER RUN. The first version of this fix made progress
    # cumulative but not achievable: the CI step allows 45 minutes and
    # attempting all fifteen series took longer than that whenever GDELT
    # throttled, so the run was KILLED mid-series (measured 2026-08-07:
    # 09:44:14 to 10:29:27, exactly the timeout) and not one series ever
    # completed. Per-series persistence cannot help if no series
    # finishes.
    #
    # Each request can burn six attempts at SLEEP_S=15 plus backoff, so
    # a throttled series costs minutes. A run now attempts a handful,
    # stops starting new ones well before the axe falls, saves what it
    # got, and lets the chain come back for the rest.
    deadline = time.monotonic() + DEADLINE_SECONDS
    todo = todo[:MAX_SERIES_PER_RUN]
    print(f"[multilingual] this run attempts {len(todo)}: "
          f"{', '.join(todo)} (budget {DEADLINE_SECONDS // 60} min)")

    landed = failed = 0
    out_of_time = False
    for ch, spec in dicts.items():
        if out_of_time:
            break
        for lg in langs:
            key = f"{ch}_{lg}"
            if key not in todo:
                continue
            if time.monotonic() > deadline:
                # Both loops, not just this one: a bare break here would
                # exit the language loop and cheerfully start the next
                # channel, past the deadline it just refused to cross.
                print(f"[multilingual] budget spent; stopping before {key} "
                      "rather than being killed mid-fetch")
                out_of_time = True
                break
            print(f"[multilingual] {key}: {start} -> {today}")
            try:
                series = fetch_gdelt.fetch_channel(
                    spec["terms"], start, today, spec.get("anchor"),
                    query_suffix=f" sourcelang:{lg}")
            except Exception as e:  # noqa: BLE001 -- 429s are expected
                print(f"[multilingual] {key}: FAILED ({type(e).__name__}: "
                      f"{e}); keeping what already landed")
                failed += 1
                continue
            if series.empty:
                print(f"[multilingual] {key}: no data returned")
                failed += 1
                continue

            frame = series.to_frame(name=key)
            store = (frame.combine_first(store) if store is not None
                     else frame).sort_index()
            STORE.parent.mkdir(parents=True, exist_ok=True)
            store.to_csv(STORE, index_label="date")
            landed += 1
            print(f"[multilingual] {key}: stored "
                  f"({len(series.dropna())} days); store now "
                  f"{len(store.columns)}/{len(expected_keys())} series")

    still = missing_keys()
    print(f"[multilingual] batch done: {landed} landed, {failed} failed, "
          f"{len(still)} series still missing")
    if landed == 0 and failed:
        # Nothing gained and something broke: say so with a non-zero
        # exit rather than letting the lane re-dispatch itself forever
        # on the strength of a chunk cache that grew.
        raise SystemExit(
            f"[multilingual] no series landed and {failed} failed; "
            "upstream is refusing us, so this batch made no progress")
    return store


def publish() -> None:
    ml = _load_store()
    if ml is None:
        raise SystemExit("[multilingual] no store; run --backfill first")
    langs, dicts = _specs()
    ml.index = pd.to_datetime(ml.index)

    vol = pd.read_csv(ROOT / "data" / "raw" / "gdelt_volume.csv",
                      parse_dates=["date"]).set_index("date")
    eng = build_scores(vol)

    out: dict = {"_meta": {
        "what": ("English-bias audit: per-language percentile of each "
                 "channel's own-language coverage history vs the English "
                 "percentile, weekly means; divergence is English minus "
                 "mean non-English. Registered in languages.json. Measures "
                 "the instrument's bias; association, not risk."),
        "generated": date.today().isoformat(),
        "languages": {k: v["label"] for k, v in langs.items()},
    }, "channels": {}}

    for ch in dicts:
        lang_pcts = {}
        for lg in langs:
            key = f"{ch}_{lg}"
            if key not in ml.columns:
                continue
            series = ml[key].sort_index()
            if series.dropna().empty:
                continue
            pct = _trailing_percentile(series)
            wk = pct.resample("W-MON").mean().dropna().round(1)
            wk = wk[wk.index <= series.dropna().index.max()]
            if len(wk) >= 26:
                lang_pcts[lg] = wk
        if not lang_pcts:
            continue
        eng_wk = eng[ch].resample("W-MON").mean().dropna().round(1)
        joint = pd.concat({"eng": eng_wk, **lang_pcts}, axis=1).dropna()
        if len(joint) < 26:
            continue
        non_eng = joint[[c for c in joint.columns if c != "eng"]].mean(axis=1)
        div = (joint["eng"] - non_eng).round(1)
        out["channels"][ch] = {
            "weeks": [d.date().isoformat() for d in joint.index],
            "english_pct": joint["eng"].tolist(),
            "lang_pct": {lg: joint[lg].tolist() for lg in lang_pcts},
            "divergence": div.tolist(),
            "latest_divergence": float(div.iloc[-1]),
        }
    SITE_JSON.write_text(json.dumps(out), encoding="utf-8")
    print("[multilingual] wrote multilingual.json:",
          {k: v["latest_divergence"] for k, v in out["channels"].items()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="exit 0 when every registered series is stored")
    args = ap.parse_args()
    if args.status:
        # The workflow's completeness test. It used to be "does the
        # store file exist", which is wrong the moment the store is
        # written incrementally -- one series in would read as finished.
        still = missing_keys()
        total = len(expected_keys())
        print(f"[multilingual] {total - len(still)}/{total} series stored")
        if still:
            print(f"[multilingual] missing: {', '.join(still)}")
        raise SystemExit(1 if still else 0)
    if args.backfill or args.update:
        update(backfill=args.backfill)
        # Publishing is best-effort while the store is partial: publish()
        # already skips any channel without 26 weeks across its
        # languages, so a half-built store yields a smaller payload
        # rather than a broken one.
        try:
            publish()
        except SystemExit as e:
            print(f"[multilingual] publish skipped: {e}")
    elif args.publish:
        publish()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
