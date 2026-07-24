"""
Google Trends as a third attention source -- SUPPORTING EVIDENCE ONLY.

Trends returns a RELATIVE index (0-100 within the requested window and
term set), not absolute counts. Levels are therefore meaningless across
requests, windows, or sources; the series is usable only for correlation
checks against GDELT and Wikipedia, never for level comparisons or for
the published index. That limitation is structural and is why this
source is last in the build order (spec B5).

Terms live in trends_terms.json (author's to fill; dormant while empty).

Implementation notes:
  - No official API. This module uses the unofficial widget endpoints the
    pytrends project documented; Google throttles them aggressively and
    changes them without notice. Failures here are expected and NEVER
    block the pipeline -- the module is standalone.
  - Daily granularity only comes in <=9-month windows; longer ranges are
    stitched by overlapping windows and rescaling on the overlap, which
    adds error. Documented per run in the output metadata.

Run:     python -m src.fetch_trends
Output:  data/raw/trends_volume.csv (date index, one column per channel),
         and a "trends_agreement" block merged into
         docs/data/validation.json (correlation vs GDELT and Wikipedia
         percentile scores on overlapping dates).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import build_index

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SITE_DATA = ROOT / "docs" / "data"


def _load_terms() -> dict[str, list[str]]:
    with open(ROOT / "trends_terms.json", encoding="utf-8") as f:
        lists = json.load(f)
    return {ch: terms for ch, terms in lists.items() if not ch.startswith("_")}


def fetch_channel(terms: list[str]) -> pd.Series:
    """Stitched daily interest series for one channel's term set.

    Left unimplemented until the author fills trends_terms.json AND the
    Wikipedia source has proven the multi-source architecture (A3): the
    unofficial endpoints need active maintenance, and building against
    them before there are terms to fetch is wasted motion. When
    implemented: fetch each term per <=9-month window, stitch windows by
    rescaling on their overlap, average across terms, return a daily
    series."""
    raise NotImplementedError(
        "fill trends_terms.json first; implement stitching per the module "
        "docstring (pytrends' dailydata recipe is the reference)"
    )


def main() -> None:
    channels = _load_terms()
    if not any(channels.values()):
        raise SystemExit(
            "trends_terms.json is empty -- fill 2-5 search phrases per "
            "channel (author's task; see the file's _meta note), then re-run."
        )
    cols = {ch: fetch_channel(terms) for ch, terms in channels.items() if terms}
    vol = pd.DataFrame(cols).sort_index()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    vol.to_csv(RAW_DIR / "trends_volume.csv", index_label="date")

    scores = build_index.build_scores(vol)
    agreement: dict[str, dict[str, float]] = {}
    for other_name, other_file in (("gdelt", "gdelt_volume.csv"),
                                   ("wikipedia", "wiki_volume.csv")):
        path = RAW_DIR / other_file
        if not path.exists():
            continue
        other = build_index.build_scores(
            pd.read_csv(path, parse_dates=["date"]).set_index("date")
        )
        for ch in vol.columns:
            if ch in other.columns:
                joined = pd.concat([scores[ch], other[ch]],
                                   axis=1, join="inner").dropna()
                if len(joined) >= 60:
                    agreement.setdefault(ch, {})[other_name] = round(
                        float(joined.corr().iloc[0, 1]), 3
                    )

    val_path = SITE_DATA / "validation.json"
    val = json.loads(val_path.read_text(encoding="utf-8")) if val_path.exists() else {}
    val["trends_agreement"] = {
        "note": ("Correlation checks only: Trends is a relative index; "
                 "levels are not comparable to anything."),
        "per_channel": agreement,
    }
    val_path.write_text(json.dumps(val, indent=1), encoding="utf-8")
    print(f"[trends] agreement: {agreement}")


if __name__ == "__main__":
    main()
