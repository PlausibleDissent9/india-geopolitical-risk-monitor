"""
Alternative specifications, published beside the primary (never replacing
it). Pre-empts three "what if you had chosen differently" objections:

  (a) composite weighting -- equal (primary) vs trade-exposure vs
      import-exposure, weights from alt_weights.json (author's to fill);
  (b) episode threshold -- 1.5 sigma and 2.5 sigma beside the primary 2.0;
  (c) percentile window -- 365 and 1095 days beside the primary 730.

For each alternative: correlation with the primary specification (and for
episode thresholds, episode counts and overlap with the primary set).
High correlations mean conclusions are not specification-dependent; low
ones get reported, not hidden (methodology s4, s5, s8d).

Run after the backfill:  python -m src.alt_specs
Output: docs/data/alt_specs.json
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import build_index

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
OUT = ROOT / "docs" / "data" / "alt_specs.json"

ALT_SIGMAS = (1.5, 2.5)
ALT_WINDOWS = (365, 1095)


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(joined) < 60:
        return None
    return round(float(joined.corr().iloc[0, 1]), 4)


def weighting_block(scores: pd.DataFrame, channels: list[str]) -> dict:
    with open(ROOT / "alt_weights.json", encoding="utf-8") as f:
        cfg = json.load(f)
    out: dict = {"equal": {"note": "primary specification", "corr_with_primary": 1.0}}
    for name in ("trade_exposure", "import_exposure"):
        w = cfg.get(name) or {}
        if not w:
            out[name] = {"skipped": "weights not filled in alt_weights.json"}
            continue
        missing = [ch for ch in channels if ch not in w]
        if missing:
            out[name] = {"skipped": f"missing weights for {missing}"}
            continue
        vec = pd.Series({ch: float(w[ch]) for ch in channels})
        vec = vec / vec.sum()
        composite = (scores[channels] * vec).sum(axis=1, skipna=False)
        out[name] = {
            "weights": {ch: round(float(x), 4) for ch, x in vec.items()},
            "corr_with_primary": _corr(composite, scores["composite"]),
        }
    return out


def episode_block(vol: pd.DataFrame) -> dict:
    primary = build_index.detect_all_episodes(vol)
    p_days = {(e["channel"], d.date().isoformat())
              for e in primary
              for d in pd.date_range(e["start"], e["end"])}
    out = {"2.0": {"note": "primary specification", "n_episodes": len(primary)}}
    for sigma in ALT_SIGMAS:
        eps = build_index.detect_all_episodes(vol, sigma=sigma)
        a_days = {(e["channel"], d.date().isoformat())
                  for e in eps
                  for d in pd.date_range(e["start"], e["end"])}
        inter = len(p_days & a_days)
        union = len(p_days | a_days)
        out[str(sigma)] = {
            "n_episodes": len(eps),
            "episode_day_jaccard_vs_primary":
                round(inter / union, 3) if union else None,
        }
    return out


def window_block(vol: pd.DataFrame, primary: pd.DataFrame) -> dict:
    out = {"730": {"note": "primary specification", "corr_with_primary": 1.0}}
    for wd in ALT_WINDOWS:
        alt = build_index.build_scores(vol, window_days=wd)
        out[str(wd)] = {
            "corr_with_primary": _corr(alt["composite"], primary["composite"]),
            "per_channel": {
                ch: _corr(alt[ch], primary[ch])
                for ch in vol.columns
            },
        }
    return out


def main() -> None:
    if not STORE.exists():
        raise SystemExit("no data/raw/gdelt_volume.csv yet -- run the pipeline first")
    vol = pd.read_csv(STORE, parse_dates=["date"]).set_index("date").sort_index()
    primary = build_index.build_scores(vol)
    channels = list(vol.columns)

    windows = window_block(vol, primary)
    payload: dict = {
        "note": ("Secondary specifications beside the primary; the primary "
                 "never changes here. Correlations answer 'does the choice "
                 "drive the result?'"),
        "composite_weightings": weighting_block(primary, channels),
        "episode_thresholds_sigma": episode_block(vol),
        "percentile_windows_days": windows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    for k, v in windows.items():
        print(f"[alt_specs] window {k}: corr={v.get('corr_with_primary')}")
    print(f"[alt_specs] wrote {OUT}")


if __name__ == "__main__":
    main()
