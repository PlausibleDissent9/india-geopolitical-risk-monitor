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
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import fetch_gdelt
from .build_index import _trailing_percentile, build_scores

ROOT = Path(__file__).resolve().parents[1]
LANGS = ROOT / "languages.json"
DICTS = ROOT / "dictionaries.json"
STORE = ROOT / "data" / "raw" / "multilingual_salience.csv"
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


def update(backfill: bool = False) -> pd.DataFrame:
    langs, dicts = _specs()
    existing = _load_store()
    today = date.today()
    start = START if (backfill or existing is None) else today - timedelta(days=14)
    cols = {}
    for ch, spec in dicts.items():
        for lg in langs:
            key = f"{ch}_{lg}"
            print(f"[multilingual] {key}: {start} -> {today}")
            cols[key] = fetch_gdelt.fetch_channel(
                spec["terms"], start, today, spec.get("anchor"),
                query_suffix=f" sourcelang:{lg}")
    fetched = pd.DataFrame(cols)
    merged = (fetched.combine_first(existing)
              if existing is not None and not backfill else fetched).sort_index()
    STORE.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(STORE, index_label="date")
    return merged


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
    args = ap.parse_args()
    if args.backfill or args.update:
        update(backfill=args.backfill)
        publish()
    elif args.publish:
        publish()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
