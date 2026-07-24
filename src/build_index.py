"""
Index construction and episode detection.

Scores: per-channel trailing 730-day percentile rank of the raw GDELT
volume share (today vs the channel's own last two years). Percentile
over z-score because news volume is fat-tailed and drifts secularly.
Composite: unweighted mean across channels -- a transparency convention,
not a claim about relative importance (methodology section 4).

Episodes: detected on RAW volume shares, not percentile scores (scores
are bounded at 100, so a 2-sigma threshold on them can be unreachable).
Spike day = value > trailing-90-day mean + 2 sigma, baseline lagged one
day so a spike cannot inflate its own threshold. Spike days within a
3-day gap cluster into one episode.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

PERCENTILE_WINDOW_DAYS = 730
# Minimum trailing observations before a score is emitted; earlier days
# stay NaN rather than reporting a percentile against a thin baseline.
MIN_OBS = 180

EPISODE_BASELINE_DAYS = 90
EPISODE_MIN_OBS = 60
EPISODE_SIGMA = 2.0
EPISODE_GAP_DAYS = 3

DEFINITION = (
    "Measures press salience -- the share of global news coverage matching "
    "each channel, ranked against its own trailing two years. Not a measure "
    "of risk, and not investment advice."
)


def _trailing_percentile(
    s: pd.Series,
    window_days: int = PERCENTILE_WINDOW_DAYS,
    min_obs: int = MIN_OBS,
) -> pd.Series:
    def pct(a: np.ndarray) -> float:
        return 100.0 * float(np.mean(a <= a[-1]))

    return s.rolling(f"{window_days}D", min_periods=min_obs).apply(pct, raw=True)


def build_scores(
    volume: pd.DataFrame, window_days: int = PERCENTILE_WINDOW_DAYS
) -> pd.DataFrame:
    """Percentile scores per channel plus 'composite'. Index: DatetimeIndex.
    Non-default window_days is for secondary specifications only
    (alt_specs.py); the published index always uses the default."""
    v = volume.copy()
    v.index = pd.to_datetime(v.index)
    v = v.sort_index()
    scores = pd.DataFrame(
        {ch: _trailing_percentile(v[ch], window_days) for ch in v.columns}
    )
    scores["composite"] = scores[v.columns].mean(axis=1, skipna=False)
    return scores


def detect_episodes(
    s: pd.Series, channel: str, sigma: float = EPISODE_SIGMA
) -> list[dict]:
    s = s.dropna()
    if s.empty:
        return []
    base = s.rolling(f"{EPISODE_BASELINE_DAYS}D", min_periods=EPISODE_MIN_OBS)
    mu = base.mean().shift(1)
    sd = base.std().shift(1)
    threshold = mu + sigma * sd
    spikes = s[s > threshold].index

    episodes: list[dict] = []
    cluster: list[pd.Timestamp] = []
    for ts in spikes:
        if cluster and (ts - cluster[-1]).days > EPISODE_GAP_DAYS:
            episodes.append(_close_cluster(cluster, s, channel))
            cluster = []
        cluster.append(ts)
    if cluster:
        episodes.append(_close_cluster(cluster, s, channel))
    return episodes


def _close_cluster(cluster: list[pd.Timestamp], s: pd.Series, channel: str) -> dict:
    seg = s.loc[cluster[0]:cluster[-1]]
    peak = seg.idxmax()
    return {
        "channel": channel,
        "start": cluster[0].date().isoformat(),
        "end": cluster[-1].date().isoformat(),
        "peak_date": peak.date().isoformat(),
        "peak_value": round(float(seg.max()), 4),
        "n_spike_days": len(cluster),
    }


def detect_all_episodes(
    volume: pd.DataFrame, sigma: float = EPISODE_SIGMA
) -> list[dict]:
    v = volume.copy()
    v.index = pd.to_datetime(v.index)
    v = v.sort_index()
    out: list[dict] = []
    for ch in v.columns:
        out.extend(detect_episodes(v[ch], ch, sigma))
    out.sort(key=lambda e: e["start"])
    return out


def write_site_outputs(
    scores: pd.DataFrame, episodes: list[dict], labels: dict[str, str]
) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    channels = [c for c in scores.columns if c != "composite"]

    valid = scores.dropna(subset=["composite"])
    latest_row = valid.iloc[-1] if not valid.empty else None
    latest = {
        "date": valid.index[-1].date().isoformat() if latest_row is not None else None,
        "definition": DEFINITION,
        "composite": _r1(latest_row["composite"]) if latest_row is not None else None,
        "channels": {
            ch: {
                "label": labels.get(ch, ch),
                "score": _r1(latest_row[ch]) if latest_row is not None else None,
            }
            for ch in channels
        },
    }
    _write_json(SITE_DATA / "latest.json", latest)

    hist = scores.dropna(how="all")
    history = {
        "dates": [d.date().isoformat() for d in hist.index],
        "composite": [_r1(x) for x in hist["composite"]],
        "channels": {ch: [_r1(x) for x in hist[ch]] for ch in channels},
        "labels": {ch: labels.get(ch, ch) for ch in channels},
    }
    _write_json(SITE_DATA / "history.json", history)

    for e in episodes:
        e["label"] = labels.get(e["channel"], e["channel"])
    _write_json(SITE_DATA / "episodes.json", episodes)


def _r1(x: float) -> float | None:
    return None if pd.isna(x) else round(float(x), 1)


def _write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
