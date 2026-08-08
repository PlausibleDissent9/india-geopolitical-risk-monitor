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
    "Measures press salience: the share of global news coverage matching "
    "each channel, ranked against its own trailing two years. Not a measure "
    "of risk, and not investment advice."
)


def _trailing_percentile(
    s: pd.Series,
    window_days: int = PERCENTILE_WINDOW_DAYS,
    min_obs: int = MIN_OBS,
) -> pd.Series:
    def pct(a: np.ndarray) -> float:
        # A missing day must stay missing: comparing against NaN counts
        # as False and would silently score a data gap as 0th percentile,
        # deflating the composite (observed with a ragged channel tail).
        if np.isnan(a[-1]):
            return float("nan")
        v = a[~np.isnan(a)]
        return 100.0 * float(np.mean(v <= a[-1]))

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


def build_scores7(
    volume: pd.DataFrame, window_days: int = PERCENTILE_WINDOW_DAYS
) -> pd.DataFrame:
    """The HEADLINE series (founder-signed 2026-08-06): trailing-7-day
    mean of each channel's raw share, passed through the identical
    percentile transform. Seven days is the minimal window that
    cancels global press volume's weekly periodicity; the daily series
    remains fully published as the tape (episodes, receipts, alerts
    all stay daily). This smoothing choice is a presentation rule, not
    independent validation or evidence of forecasting performance."""
    v = volume.copy()
    v.index = pd.to_datetime(v.index)
    v = v.sort_index()
    weekly = pd.DataFrame(
        {ch: v[ch].rolling("7D", min_periods=4).mean() for ch in v.columns}
    )
    scores = pd.DataFrame(
        {ch: _trailing_percentile(weekly[ch], window_days)
         for ch in weekly.columns}
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


SITE_URL = "https://igrm.in"


def _file_meta(what: str, units: str) -> dict:
    """Self-description block embedded in every published dict-shaped
    JSON: a downloaded file must explain itself without the website."""
    from datetime import date as _date

    return {
        "what": what,
        "units": units,
        "license": "CC BY 4.0",
        "citation": ("Krishna, Ishan (2026). India Geopolitical Risk "
                     f"Monitor. {SITE_URL}/"),
        "codebook": f"{SITE_URL}/codebook.html",
        "generated": _date.today().isoformat(),
    }


def write_site_outputs(
    scores: pd.DataFrame, episodes: list[dict], labels: dict[str, str],
    scores7: pd.DataFrame | None = None,
) -> None:
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    channels = [c for c in scores.columns if c != "composite"]

    valid = scores.dropna(subset=["composite"])
    latest_row = valid.iloc[-1] if not valid.empty else None
    # Weekly headline fields are ADDITIVE (contract stays intact: the
    # daily `score`/`composite` keep their frozen meaning forever).
    row7 = None
    if scores7 is not None and latest_row is not None:
        v7 = scores7.dropna(subset=["composite"])
        if not v7.empty:
            row7 = v7.iloc[-1]
    latest = {
        "_meta": _file_meta(
            "Today's IGRM scores. HEADLINE (founder-signed 2026-08-06): "
            "composite7/score7, the trailing-7-day mean share through "
            "the identical percentile transform -- persistent salience, "
            "less sensitive to single-day news-cycle noise. This smoothing "
            "rule is not a validation or forecasting result. The daily "
            "composite/score fields are the tape: same construction on "
            "single days, where episodes, receipts, and alerts live.",
            "percentile of the channel's own trailing 730 days, 0-100",
        ),
        "date": valid.index[-1].date().isoformat() if latest_row is not None else None,
        "definition": DEFINITION,
        "composite": _r1(latest_row["composite"]) if latest_row is not None else None,
        "composite7": _r1(row7["composite"]) if row7 is not None else None,
        "channels": {
            ch: {
                "label": labels.get(ch, ch),
                "score": _r1(latest_row[ch]) if latest_row is not None else None,
                "score7": _r1(row7[ch]) if row7 is not None else None,
            }
            for ch in channels
        },
    }
    _write_json(SITE_DATA / "latest.json", latest, pretty=True)

    hist = scores.dropna(how="all")
    history = {
        "_meta": _file_meta(
            "Full daily IGRM score history; parallel arrays share the "
            "dates index. Machine feed for the site chart -- researchers "
            "should prefer history.csv.",
            "percentile of each channel's own trailing 730 days, 0-100",
        ),
        "dates": [d.date().isoformat() for d in hist.index],
        "composite": [_r1(x) for x in hist["composite"]],
        "channels": {ch: [_r1(x) for x in hist[ch]] for ch in channels},
        "labels": {ch: labels.get(ch, ch) for ch in channels},
    }
    if scores7 is not None:
        h7 = scores7.reindex(hist.index)
        history["composite7"] = [_r1(x) for x in h7["composite"]]
        history["channels7"] = {ch: [_r1(x) for x in h7[ch]]
                                for ch in channels}
    # Second source rides along whenever its store exists, so no rebuild
    # can silently drop the site's source toggle again.
    wiki_store = ROOT / "data" / "raw" / "wiki_volume.csv"
    if wiki_store.exists():
        wvol = pd.read_csv(wiki_store, parse_dates=["date"]).set_index("date")
        wh = build_scores(wvol).dropna(how="all")
        history["wikipedia"] = {
            "dates": [d.date().isoformat() for d in wh.index],
            "composite": [_r1(x) for x in wh["composite"]],
            "channels": {ch: [_r1(x) for x in wh[ch]]
                         for ch in wvol.columns},
        }
    _write_json(SITE_DATA / "history.json", history)

    for e in episodes:
        e["label"] = labels.get(e["channel"], e["channel"])
    _write_json(SITE_DATA / "episodes.json", episodes)

    # The open-data CSVs -- the citeable artifacts. One row per day /
    # per episode; column definitions in docs/codebook.md.
    hist.round(1).to_csv(SITE_DATA / "history.csv", index_label="date")
    if episodes:
        pd.DataFrame(episodes)[
            ["channel", "label", "start", "end", "peak_date",
             "peak_value", "n_spike_days"]
        ].to_csv(SITE_DATA / "episodes.csv", index=False)


def _r1(x: float) -> float | None:
    return None if pd.isna(x) else round(float(x), 1)


def _write_json(path: Path, payload, pretty: bool = False) -> None:
    if pretty:
        path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, separators=(",", ":")),
                        encoding="utf-8")
