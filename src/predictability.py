"""
V3 predictability study: does press salience lead anything, or follow?

Research findings, association language throughout. For each directed
pair (x leads y), daily changes are regressed on five own-lags of y
with and without five lags of x; the reported statistic is the R2
increment from adding x, with a permutation p-value (x's lag block
shuffled in time, 300 draws) instead of an F distribution, keeping
scipy out of the dependency set. Granger-style predictability is NOT
causality and the payload says so.

Pairs: composite salience vs conflict-event intensity, India VIX
percentile, and INR 10-day realized volatility, both directions each.

Output: docs/data/predictability.json

  python -m src.predictability
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .build_index import build_scores

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data" / "predictability.json"

LAGS = 5
PERMS = 300
SEED = 20260731


def _ols_r2(y: np.ndarray, X: np.ndarray) -> float:
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) @ (y - y.mean())) or 1e-12)
    return 1.0 - ss_res / ss_tot


def _lag_matrix(s: np.ndarray, lags: int) -> np.ndarray:
    return np.column_stack([np.roll(s, k)[lags:] for k in range(1, lags + 1)])


def study_pair(x: pd.Series, y: pd.Series) -> dict:
    df = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    dx = df["x"].diff().dropna()
    dy = df["y"].diff().dropna()
    joint = pd.concat([dx.rename("x"), dy.rename("y")], axis=1).dropna()
    xv, yv = joint["x"].to_numpy(), joint["y"].to_numpy()
    n = len(joint)
    if n < 200:
        return {"n": n, "insufficient": True}
    y_dep = yv[LAGS:]
    own = _lag_matrix(yv, LAGS)
    xl = _lag_matrix(xv, LAGS)
    r2_own = _ols_r2(y_dep, own)
    r2_full = _ols_r2(y_dep, np.column_stack([own, xl]))
    inc = r2_full - r2_own
    rng = np.random.default_rng(SEED)
    null = []
    for _ in range(PERMS):
        shift = int(rng.integers(30, len(xv) - 30))
        xs = np.roll(xv, shift)
        null.append(_ols_r2(y_dep, np.column_stack([own, _lag_matrix(xs, LAGS)]))
                    - r2_own)
    p = float((np.sum(np.array(null) >= inc) + 1) / (PERMS + 1))
    return {"n": n, "r2_increment": round(float(inc), 4),
            "p_permutation": round(p, 3)}


def main() -> None:
    vol = pd.read_csv(RAW / "gdelt_volume.csv", parse_dates=["date"]).set_index("date")
    sal = build_scores(vol)["composite"].rename("salience")

    ev = pd.read_csv(RAW / "events_daily.csv", parse_dates=["date"]).set_index("date")
    events = ((ev["n_verbal_conflict"] + ev["n_material_conflict"])
              / ev["n_global"]).rename("events")

    series = {"salience": sal, "events": events}
    px_path = RAW / "prices.csv"
    if px_path.exists():
        px = pd.read_csv(px_path, parse_dates=["date"]).set_index("date").sort_index()
        if "india_vix" in px.columns:
            series["vix"] = px["india_vix"].dropna().rename("vix")
        if "usdinr" in px.columns:
            r = np.log(px["usdinr"]).diff() * 100
            series["inr_vol"] = r.rolling(10).std().dropna().rename("inr_vol")

    pairs = {}
    names = list(series)
    for a in names:
        for b in names:
            if a != b and "salience" in (a, b):
                pairs[f"{a}_leads_{b}"] = study_pair(series[a], series[b])

    payload = {
        "_meta": {
            "what": ("Directed lead-lag predictability on daily changes: R2 "
                     "increment from adding five lags of the leading series "
                     "to five own-lags, permutation p-values (time-shifted "
                     "null, 300 draws). Predictability in this sense is an "
                     "association across time, never causality, and none of "
                     "this is a forecast or investment advice."),
            "lags": LAGS, "permutations": PERMS,
            "generated": date.today().isoformat(),
        },
        "pairs": pairs,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    for k, v in pairs.items():
        print(f"[predictability] {k}: {v}")


if __name__ == "__main__":
    main()
