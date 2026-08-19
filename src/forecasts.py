"""
V11 forecast experiment (validation/forecast_registration.json,
founder-signed 2026-08-06). Everything here is the registration's
mechanical execution -- zero editorial judgment anywhere:

  - Each Monday 00:00 UTC, five questions: 'will channel C record at
    least one spike day (the registered episode rule) within 14
    days?' Questions are generated and COMMITTED before the window
    opens; a late question is void by rule.
  - Two arms per question, probabilities recorded at generation:
    climatology (trailing 104-week frequency of the same event) and a
    logistic model on two registered inputs (current percentile
    score, 7-day change) whose coefficients were fit once on
    pre-registration history and FROZEN in
    validation/forecast_logit_frozen.json. Refits are new
    registrations.
  - Grading is mechanical at horizon close from the committed series;
    void if the series gaps more than 4 of the 14 days; Brier scored
    per question, cumulative and rolling-26-week per arm.

SEPARATION: this experiment publishes ONLY under research/ with the
mandatory header (enforced by test). It never touches latest.json,
the front page, the brief, or the newsletter. Until the registered
criterion resolves, the presumption is that salience does NOT
forecast.

  python -m src.forecasts       generate due questions + grade matured
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src import build_index

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "validation" / "forecast_questions.json"
FROZEN = ROOT / "validation" / "forecast_logit_frozen.json"
SITE_DATA = ROOT / "docs" / "data"

HORIZON_DAYS = 14
TRAIL_WEEKS = 104
VOID_GAP_DAYS = 4
CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade",
            "shipping"]


def spike_days(share: pd.Series) -> pd.Series:
    """Boolean spike-day series under the registered episode rule:
    raw share > trailing-90-day mean + 2 sigma, baseline lagged one
    day (identical arithmetic to build_index.detect_episodes)."""
    s = share.dropna()
    base = s.rolling(f"{build_index.EPISODE_BASELINE_DAYS}D",
                     min_periods=build_index.EPISODE_MIN_OBS)
    threshold = (base.mean().shift(1)
                 + build_index.EPISODE_SIGMA * base.std().shift(1))
    return s > threshold


def _volume() -> pd.DataFrame:
    v = pd.read_csv(ROOT / "data" / "raw" / "gdelt_volume.csv",
                    parse_dates=["date"]).set_index("date")
    return v.sort_index()


def climatology_p(spikes: pd.Series, window_start: date) -> float:
    """Trailing 104-week frequency of 'any spike day within 14 days of
    a Monday', over Mondays before the window."""
    hits = 0
    n = 0
    for k in range(1, TRAIL_WEEKS + 1):
        mon = window_start - timedelta(weeks=k)
        seg = spikes.loc[pd.Timestamp(mon):
                         pd.Timestamp(mon + timedelta(days=HORIZON_DAYS - 1))]
        if len(seg) == 0:
            continue
        n += 1
        hits += int(seg.any())
    return round(hits / n, 4) if n else float("nan")


def fit_frozen_logit(scores: pd.DataFrame,
                     spikes: dict[str, pd.Series]) -> dict[str, Any]:
    """One-time pooled logistic fit on pre-registration Mondays.
    Deterministic IRLS on two registered inputs + intercept."""
    rows, ys = [], []
    mondays = pd.date_range("2018-01-07", "2026-08-03", freq="W-MON")
    for ch in CHANNELS:
        sc = scores[ch]
        for mon in mondays:
            if mon not in sc.index or pd.isna(sc.loc[mon]):
                continue
            prev = mon - pd.Timedelta(days=7)
            if prev not in sc.index or pd.isna(sc.loc[prev]):
                continue
            seg = spikes[ch].loc[mon:mon + pd.Timedelta(days=HORIZON_DAYS - 1)]
            if len(seg) < HORIZON_DAYS - VOID_GAP_DAYS:
                continue
            rows.append([1.0, float(sc.loc[mon]),
                         float(sc.loc[mon] - sc.loc[prev])])
            ys.append(int(seg.any()))
    X = np.array(rows)
    y = np.array(ys, dtype=float)
    beta = np.zeros(3)
    for _ in range(25):  # IRLS; deterministic
        p = 1.0 / (1.0 + np.exp(-np.clip(X @ beta, -35.0, 35.0)))
        W = p * (1 - p) + 1e-9
        grad = X.T @ (y - p)
        H = (X * W[:, None]).T @ X
        step = np.linalg.solve(H, grad)
        beta += step
        if float(np.max(np.abs(step))) < 1e-8:
            break
    # The fit stamps its TRUE date. Hardcoding the registered date here
    # meant a regenerated fit (frozen file deleted, module rerun) would
    # wear the original registration's date over post-registration data
    # -- forged provenance by accident. With the real date, a regenerated
    # file no longer matches the registered fit_date and the freeze pin
    # in tests/test_registration_freezes.py goes red, which is the point.
    return {"fit_date": date.today().isoformat(),
            "train_mondays": ["2018-01-07", "2026-08-03"],
            "n_obs": int(len(y)), "base_rate": round(float(y.mean()), 4),
            "inputs": ["intercept", "score_pctl", "score_change_7d"],
            "coefficients": [round(float(b), 6) for b in beta],
            "note": ("Fit once on pre-registration history, pooled across "
                     "channels, then FROZEN. Refits are new registrations, "
                     "never silent updates.")}


def logit_p(coef: list[float], score: float, change: float) -> float:
    z = float(np.clip(coef[0] + coef[1] * score + coef[2] * change,
                      -35.0, 35.0))
    return round(float(1.0 / (1.0 + np.exp(-z))), 4)


def _load_questions() -> list[dict[str, Any]]:
    if QUESTIONS.exists():
        return json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]
    return []


def _save_questions(qs: list[dict[str, Any]]) -> None:
    QUESTIONS.write_text(json.dumps(
        {"_meta": {"what": ("Committed question registry for the V11 "
                            "experiment; every question's commit predates "
                            "its window or the question is void by rule.")},
         "questions": qs}, indent=1), encoding="utf-8")


def generate(today: date, scores: pd.DataFrame,
             spikes: dict[str, pd.Series]) -> list[dict[str, Any]]:
    """Ensure the NEXT Monday's questions exist (commit-before-open)."""
    days_ahead = (7 - today.weekday()) % 7 or 7
    window_start = today + timedelta(days=days_ahead)
    qs = _load_questions()
    if any(q["window_start"] == window_start.isoformat() for q in qs):
        return []
    coef = json.loads(FROZEN.read_text(encoding="utf-8"))["coefficients"]
    last_day = scores.dropna(how="all").index.max()
    prev_day = last_day - pd.Timedelta(days=7)
    # The 7-day change is a REGISTERED input; no substitute anchor is allowed.
    # When the anchor lands on a disclosed gap day (absent from the series or
    # NaN), this window's questions cannot be generated under the registration
    # yet: refuse loudly and commit nothing.  The anchor moves forward one day
    # per run, so generation resumes by itself while the window is still open,
    # and a question that never gets committed in time is void by rule --
    # exactly the registration's own remedy for a late question.
    if (
        prev_day not in scores.index
        or scores.loc[prev_day, CHANNELS].isna().any()
        or scores.loc[last_day, CHANNELS].isna().any()
    ):
        print(f"[forecasts] window {window_start} not generated: registered "
              f"7-day-change anchor {prev_day.date()} is a disclosed gap day "
              "(or a channel is unscored on the anchor/latest day); "
              "will retry while the window remains open")
        return []
    fresh = []
    for ch in CHANNELS:
        score = float(scores[ch].loc[last_day])
        change = score - float(scores[ch].loc[prev_day])
        fresh.append({
            "id": f"{window_start}-{ch}",
            "channel": ch,
            "window_start": window_start.isoformat(),
            "window_end": (window_start
                           + timedelta(days=HORIZON_DAYS - 1)).isoformat(),
            "generated": today.isoformat(),
            "features": {"score_pctl": round(score, 1),
                         "score_change_7d": round(change, 1),
                         "as_of": str(last_day.date())},
            "p_climatology": climatology_p(spikes[ch], window_start),
            "p_salience": logit_p(coef, score, change),
            "outcome": None, "void": False,
        })
    _save_questions(qs + fresh)
    return fresh


def grade(today: date, spikes: dict[str, pd.Series],
          last_data_day: date) -> int:
    qs = _load_questions()
    graded = 0
    for q in qs:
        if q["outcome"] is not None or q.get("void"):
            continue
        end = date.fromisoformat(q["window_end"])
        if end > last_data_day:
            continue
        seg = spikes[q["channel"]].loc[q["window_start"]:q["window_end"]]
        if len(seg) < HORIZON_DAYS - VOID_GAP_DAYS:
            q["void"] = True
        else:
            q["outcome"] = int(seg.any())
        graded += 1
    if graded:
        _save_questions(qs)
    return graded


def publish() -> None:
    qs = _load_questions()
    resolved = [q for q in qs if q["outcome"] is not None]
    briers = {}
    for arm in ("p_climatology", "p_salience"):
        scores_ = [(q[arm] - q["outcome"]) ** 2 for q in resolved]
        briers[arm.replace("p_", "brier_")] = (
            round(float(np.mean(scores_)), 4) if scores_ else None)
    payload = {
        "_meta": {
            "what": ("V11 forecast experiment record (registration: "
                     "validation/forecast_registration.json, signed "
                     "2026-08-06). RESEARCH PAGE ONLY: this is an "
                     "experiment about the index, not advice, and until "
                     "the registered criterion resolves it should be "
                     "presumed to show that salience does not forecast. "
                     "Questions are mechanical, committed before their "
                     "windows, graded by the registered detector; the "
                     "frozen-logit arm's coefficients are in "
                     "validation/forecast_logit_frozen.json."),
            "n_questions": len(qs),
            "n_resolved": len(resolved),
            "n_void": sum(1 for q in qs if q.get("void")),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "cumulative": briers,
        "questions": qs,
    }
    (SITE_DATA / "forecasts.json").write_text(json.dumps(payload),
                                              encoding="utf-8")
    print(f"[forecasts] {len(qs)} question(s), {len(resolved)} resolved, "
          f"briers {briers}")


def main() -> None:
    vol = _volume()
    scores = build_index.build_scores(vol)
    spikes = {ch: spike_days(vol[ch]) for ch in CHANNELS}
    if not FROZEN.exists():
        FROZEN.write_text(json.dumps(fit_frozen_logit(scores, spikes),
                                     indent=1), encoding="utf-8")
        print("[forecasts] frozen logit fitted and registered "
              "(one-time; refits are new registrations)")
    today = datetime.now(timezone.utc).date()
    fresh = generate(today, scores, spikes)
    if fresh:
        print(f"[forecasts] generated {len(fresh)} question(s) for "
              f"window {fresh[0]['window_start']}")
    last_data_day = scores.dropna(how="all").index.max().date()
    graded = grade(today, spikes, last_data_day)
    if graded:
        print(f"[forecasts] graded {graded} question(s)")
    publish()


if __name__ == "__main__":
    main()
