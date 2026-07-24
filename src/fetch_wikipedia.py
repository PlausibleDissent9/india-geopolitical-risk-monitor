"""
Wikipedia pageviews as a second, demand-side attention source.

GDELT measures what editors chose to publish; pageviews measure what
readers chose to look up. Divergence between the two is a finding about
supply- vs demand-side attention, not noise (methodology s8c planned).

Source: Wikimedia REST pageviews per-article API, daily, user traffic
only (excludes spiders/bots), English Wikipedia. Data exists from July
2015, so the 2017 backfill floor is safe.

Article lists live in wikipedia_articles.json and are the author's to
fill; with empty lists this module prints an instruction and exits.

Per channel: sum daily views across the channel's articles, then express
each day as a share of the channel's trailing 365-day total (min 90
observations). The share, like GDELT's volume share, makes the series
comparable across years of secular pageview drift; levels are NOT
comparable across sources, which is why the two are normalized to
percentiles independently (build_index.build_scores) and never blended.

Caching: per-article JSON in data/raw/wiki_cache/, keyed by article and
end date -- re-runs only refetch the current tail.

Run:     python -m src.fetch_wikipedia
Output:  data/raw/wiki_volume.csv (date index, one column per channel),
         a "wikipedia" block added to docs/data/history.json, and a
         "cross_source" block (per-channel GDELT-vs-Wikipedia score
         correlation) merged into docs/data/validation.json.
"""
from __future__ import annotations

import json
import time
import urllib.parse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import build_index

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CACHE_DIR = RAW_DIR / "wiki_cache"
SITE_DATA = ROOT / "docs" / "data"

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "en.wikipedia/all-access/user/{article}/daily/{start}/{end}")
# Wikimedia asks API clients for a descriptive User-Agent.
HEADERS = {
    "User-Agent": "IGRM/1.0 (india-geopolitical-risk-monitor; research index)"
}
START = date(2017, 1, 1)
# Wikimedia throttles unauthenticated pageview clients well below its
# documented limits (observed 429 bursts after ~8 quick requests,
# 2026-07-24); pace politely and retry through the bursts.
SLEEP_S = 1.2
RETRIES = 4
SHARE_WINDOW = "365D"
SHARE_MIN_OBS = 90


# The API intermittently 404s very long ranges (observed: 'OPEC'
# 2017-2026 404s while each half 200s), so fetch in <=2-year windows,
# cached per (article, window), and concatenate.
WINDOW_DAYS = 730


def _fetch_window(slug: str, w_start: date, w_end: date) -> list[dict]:
    cache = CACHE_DIR / f"{slug}_{w_start.isoformat()}_{w_end.isoformat()}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["items"]
    url = API.format(article=slug,
                     start=w_start.strftime("%Y%m%d"),
                     end=w_end.strftime("%Y%m%d"))
    r = None
    for attempt in range(1, RETRIES + 1):
        r = requests.get(url, headers=HEADERS, timeout=60)
        time.sleep(SLEEP_S)
        if r.status_code != 429:
            break
        time.sleep(8 * attempt)
    assert r is not None
    payload: dict
    if r.status_code == 404:
        payload = {"items": []}
    else:
        r.raise_for_status()
        payload = r.json()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload["items"]


def _fetch_article(title: str, end: date) -> pd.Series:
    """Daily views for one article, windowed and cached per window."""
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    items: list[dict] = []
    cur = START
    while cur <= end:
        w_end = min(cur + timedelta(days=WINDOW_DAYS - 1), end)
        items.extend(_fetch_window(slug, cur, w_end))
        cur = w_end + timedelta(days=1)
    if not items:
        print(f"[wiki] WARNING: no pageview data for {title!r} "
              "(renamed or missing) -- skipping")
        return pd.Series(dtype=float)
    idx = pd.to_datetime([it["timestamp"][:8] for it in items], format="%Y%m%d")
    return (pd.Series([it["views"] for it in items], index=idx, dtype=float)
            .groupby(level=0).sum())


def fetch_channel(titles: list[str], end: date) -> pd.Series:
    """Sum of daily views across a channel's articles, as a share of the
    channel's own trailing-365-day total."""
    parts = [s for t in titles if not (s := _fetch_article(t, end)).empty]
    if not parts:
        return pd.Series(dtype=float)
    total = pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).sort_index()
    trailing = total.rolling(SHARE_WINDOW, min_periods=SHARE_MIN_OBS).sum()
    return (total / trailing).dropna()


def main() -> None:
    with open(ROOT / "wikipedia_articles.json", encoding="utf-8") as f:
        lists = json.load(f)
    channels = {ch: titles for ch, titles in lists.items()
                if not ch.startswith("_")}
    if not any(channels.values()):
        raise SystemExit(
            "wikipedia_articles.json is empty -- fill 3-8 article titles per "
            "channel (author's task; see the file's _meta note), then re-run."
        )

    end = date.today() - timedelta(days=1)  # pageviews lag ~a day
    cols = {}
    for ch, titles in channels.items():
        if not titles:
            print(f"[wiki] {ch}: no articles listed -- skipping")
            continue
        print(f"[wiki] {ch}: {len(titles)} articles")
        s = fetch_channel(titles, end)
        if not s.empty:
            cols[ch] = s
    if not cols:
        raise SystemExit("no channel produced data; nothing written")

    vol = pd.DataFrame(cols).sort_index()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    vol.to_csv(RAW_DIR / "wiki_volume.csv", index_label="date")
    print(f"[wiki] wrote wiki_volume.csv "
          f"({len(vol)} days x {len(vol.columns)} channels)")

    # Same normalization as GDELT, computed independently; never blended.
    wiki_scores = build_index.build_scores(vol)

    # Additive publish: the existing history.json fields stay the GDELT
    # series (the live site reads them); the Wikipedia series lands under
    # its own key until the site's source toggle (A6d) restructures both.
    hist_path = SITE_DATA / "history.json"
    if hist_path.exists():
        hist = json.loads(hist_path.read_text(encoding="utf-8"))
        wh = wiki_scores.dropna(how="all")
        hist["wikipedia"] = {
            "dates": [d.date().isoformat() for d in wh.index],
            "composite": [build_index._r1(x) for x in wh["composite"]],
            "channels": {ch: [build_index._r1(x) for x in wh[ch]]
                         for ch in vol.columns},
        }
        hist_path.write_text(json.dumps(hist, separators=(",", ":")),
                             encoding="utf-8")
        print("[wiki] added 'wikipedia' block to history.json")

    # Cross-source agreement (layer 4c): per-channel correlation of the
    # two sources' percentile scores on overlapping dates.
    gdelt_store = RAW_DIR / "gdelt_volume.csv"
    if gdelt_store.exists():
        gvol = (pd.read_csv(gdelt_store, parse_dates=["date"])
                .set_index("date").sort_index())
        gscores = build_index.build_scores(gvol)
        cors = {}
        for ch in vol.columns:
            if ch in gscores.columns:
                joined = pd.concat([gscores[ch], wiki_scores[ch]],
                                   axis=1, join="inner").dropna()
                if len(joined) >= 60:
                    cors[ch] = round(float(joined.corr().iloc[0, 1]), 3)
        val_path = SITE_DATA / "validation.json"
        val = json.loads(val_path.read_text(encoding="utf-8")) if val_path.exists() else {}
        val["cross_source"] = {
            "note": ("Correlation of GDELT and Wikipedia percentile scores, "
                     "overlapping dates. High agreement = the signal is not "
                     "a GDELT artifact; persistent divergence = a documented "
                     "supply- vs demand-side attention finding."),
            "per_channel": cors,
        }
        SITE_DATA.mkdir(parents=True, exist_ok=True)
        val_path.write_text(json.dumps(val, indent=1), encoding="utf-8")
        print(f"[wiki] cross_source correlations: {cors}")


if __name__ == "__main__":
    main()
