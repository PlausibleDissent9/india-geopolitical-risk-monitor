"""
V2-2 India Stress Gauge: four sources fused into one daily 0-100 line.

Components (each a trailing-730-day percentile, the index convention),
weights and every rule pre-registered in
validation/stress_gauge_weights.json BEFORE this module first computed
a hit-rate (commit history is the proof of ordering):

  press      composite press-salience percentile (build_index)
  events     conflict-event intensity from the Events stream
  market     mean of India VIX percentile and USDINR 10-day realized
             volatility percentile
  wikipedia  channel-mean Wikipedia attention share percentile

Publishing is gated on the completed events history, like the maps.
Validation runs against the 21 pre-registered episodes and publishes
the hit-rate WITH the gauge; per-day component attribution ships in
the payload.

  python -m src.stress_gauge             build, validate, publish
  python -m src.stress_gauge --force-partial   local verification ONLY
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from .build_index import _trailing_percentile, build_scores
from .fetch_events import STORE as EVENTS_STORE
from .fetch_events import _missing_days

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
SITE_DATA = ROOT / "docs" / "data"
REGISTRATION = ROOT / "validation" / "stress_gauge_weights.json"
EPISODES = ROOT / "validation" / "validation_episodes.json"

DETECT_THRESHOLD = 90.0
DETECT_WINDOW_DAYS = 3
REALIZED_VOL_DAYS = 10


def _component_press() -> pd.Series:
    vol = pd.read_csv(RAW / "gdelt_volume.csv", parse_dates=["date"])
    vol = vol.set_index("date").sort_index()
    return build_scores(vol)["composite"].rename("press")


def _component_events() -> pd.Series:
    ev = pd.read_csv(EVENTS_STORE, parse_dates=["date"]).set_index("date")
    intensity = (ev["n_verbal_conflict"] + ev["n_material_conflict"]) / ev["n_global"]
    return _trailing_percentile(intensity.sort_index()).rename("events")


def _component_market() -> pd.Series | None:
    prices = RAW / "prices.csv"
    if not prices.exists():
        return None
    px = pd.read_csv(prices, parse_dates=["date"]).set_index("date").sort_index()
    parts = []
    if "india_vix" in px.columns:
        parts.append(_trailing_percentile(px["india_vix"].dropna()))
    if "usdinr" in px.columns:
        import numpy as np
        r = np.log(px["usdinr"]).diff() * 100
        rv = r.rolling(REALIZED_VOL_DAYS).std().dropna()
        parts.append(_trailing_percentile(rv))
    if not parts:
        return None
    return pd.concat(parts, axis=1).mean(axis=1, skipna=False).rename("market")


def _component_wikipedia() -> pd.Series:
    w = pd.read_csv(RAW / "wiki_volume.csv", parse_dates=["date"]).set_index("date")
    return _trailing_percentile(w.mean(axis=1).sort_index()).rename("wikipedia")


def build_gauge() -> tuple[pd.DataFrame, dict]:
    reg = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    weights: dict[str, float] = reg["weights"]
    comps = {"press": _component_press(), "events": _component_events(),
             "wikipedia": _component_wikipedia()}
    market = _component_market()
    if market is not None:
        comps["market"] = market
    df = pd.DataFrame(comps)

    # Missing-component rule, exactly as registered: press required, at
    # least two of the other three present, weights renormalized.
    others = [c for c in weights if c != "press" and c in df.columns]
    ok = df["press"].notna() & (df[others].notna().sum(axis=1) >= 2)
    w = pd.DataFrame({c: df[c].notna() * weights[c] for c in df.columns})
    wsum = w.sum(axis=1)
    gauge = (df.fillna(0.0) * w).sum(axis=1) / wsum
    gauge[~ok] = float("nan")
    df["gauge"] = gauge.round(1)
    return df, reg


def validate(df: pd.DataFrame) -> dict:
    eps = json.loads(EPISODES.read_text(encoding="utf-8"))
    eps = eps["episodes"] if isinstance(eps, dict) and "episodes" in eps else eps
    hits: list[dict] = []
    misses: list[dict] = []
    for ep in eps:
        d0 = pd.Timestamp(ep["date"])
        win = df.loc[(df.index >= d0 - pd.Timedelta(days=DETECT_WINDOW_DAYS))
                     & (df.index <= d0 + pd.Timedelta(days=DETECT_WINDOW_DAYS)),
                     "gauge"].dropna()
        peak = float(win.max()) if len(win) else None
        rec = {"date": ep["date"], "name": ep["name"], "channel": ep["channel"],
               "gauge_peak_in_window": peak}
        (hits if (peak is not None and peak >= DETECT_THRESHOLD) else misses).append(rec)
    n = len(eps)
    return {
        "rule": (f"gauge >= {DETECT_THRESHOLD:.0f} within "
                 f"{DETECT_WINDOW_DAYS} days either side of the episode date"),
        "n_episodes": n,
        "n_detected": len(hits),
        "hit_rate": round(len(hits) / n, 3) if n else None,
        "misses": misses,
    }


def main() -> None:
    force = "--force-partial" in sys.argv
    missing = len(_missing_days())
    if missing and not force:
        raise SystemExit(
            f"[gauge] {missing} days of the events history still missing; "
            "refusing to publish a gauge whose events component has holes")
    df, reg = build_gauge()
    result = validate(df)
    last = df.dropna(subset=["gauge"]).iloc[-1]
    last_date = df.dropna(subset=["gauge"]).index[-1]
    comp_cols = [c for c in ("press", "events", "market", "wikipedia")
                 if c in df.columns]
    registered_weights = reg["weights"]
    available_latest = [c for c in registered_weights
                        if c in df.columns and not pd.isna(last.get(c))]
    missing_latest = [c for c in registered_weights
                      if c not in available_latest]
    weight_sum = sum(registered_weights[c] for c in available_latest)
    effective_weights = {
        c: round(registered_weights[c] / weight_sum, 6)
        for c in available_latest
    }
    tail = df.dropna(subset=["gauge"]).tail(365)
    payload = {
        "_meta": {
            "what": ("India Stress Gauge: four attention and stress sources "
                     "fused per the pre-registered weights in "
                     "validation/stress_gauge_weights.json. A salience and "
                     "stress measurement, not a risk prediction."),
            "generated": date.today().isoformat(),
            "partial": bool(missing or missing_latest),
            "events_history_partial": bool(missing),
            # `weights` is kept as a backwards-compatible alias for
            # existing consumers; registered_weights names the semantics.
            "weights": registered_weights,
            "registered_weights": registered_weights,
            "latest_available_components": available_latest,
            "latest_missing_components": missing_latest,
            "latest_effective_weights": effective_weights,
            "validation_status": "experimental_not_validated",
            "headline_eligible": False,
        },
        "date": str(last_date.date()),
        "gauge": float(last["gauge"]),
        "components": {c: (None if pd.isna(last[c]) else round(float(last[c]), 1))
                       for c in comp_cols},
        "validation": result,
        "history_365d": {
            "dates": [str(d.date()) for d in tail.index],
            "gauge": [None if pd.isna(v) else float(v) for v in tail["gauge"]],
        },
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "stress_gauge.json").write_text(json.dumps(payload),
                                                 encoding="utf-8")
    print(f"[gauge] {payload['date']}: gauge {payload['gauge']} "
          f"components {payload['components']} | validation "
          f"{result['n_detected']}/{result['n_episodes']}"
          + (" [PARTIAL, verification only]" if missing else ""))


if __name__ == "__main__":
    main()
