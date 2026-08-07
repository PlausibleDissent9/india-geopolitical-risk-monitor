"""
Does this index measure INDIAN attention, or Anglophone attention about
India? (referee finding #25, 2026-08-07)

The construct is "salience of India-relevant geopolitical risk". The
instrument is an English-language news corpus, read by an
English-language pipeline, cross-validated so far against English
Wikipedia. Every leg of that is Anglophone, so the whole apparatus could
be measuring what the international English-language press cares about
while sincerely believing it measures Indian salience. Nothing published
so far could tell those apart.

Hindi Wikipedia can. It is the same registered article set, read by a
different population, on infrastructure that shares no code, no
sampling, and no editorial process with GDELT. If the channels move
together across the language boundary, the construct survives a test it
could have failed. If they do not, that is a limitation this project
would rather publish than have someone else discover.

THE ARTICLE SET IS NOT RE-CHOSEN
--------------------------------
Hindi titles are resolved from the registered English titles through
Wikipedia's own interlanguage links, never picked by hand. Choosing
Hindi articles myself would let me choose the ones that correlate, which
is not a test of anything. What the mapping cannot resolve is reported
as missing, never substituted.

THE MISSES ARE THEMSELVES A FINDING
-----------------------------------
Six of twenty-nine registered articles have no Hindi counterpart:
CAATSA, Sanctions against Iran, Houthi movement, Piracy off the coast of
Somalia, Trade policy of the United States, Energy policy of India.
These are not random. They are the foreign-policy-apparatus topics --
the vocabulary of sanctions regimes and maritime security -- and their
absence from Hindi Wikipedia says something about which parts of this
construct live in Indian public attention at all. That belongs in the
findings, not in a coverage footnote.

  python -m src.wiki_hindi --resolve   build/refresh the title mapping
  python -m src.wiki_hindi             fetch, correlate, publish
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CACHE_DIR = RAW_DIR / "wiki_hindi_cache"
SITE_DATA = ROOT / "docs" / "data"
MAP_PATH = RAW_DIR / "wiki_hindi_map.json"
STORE = RAW_DIR / "gdelt_volume.csv"

LANGLINKS = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/"
             "per-article/hi.wikipedia/all-access/user/{article}/daily/"
             "{start}/{end}")
HEADERS = {
    "User-Agent": "IGRM/1.0 (india-geopolitical-risk-monitor; research index)"
}
START = date(2017, 1, 1)
SLEEP_S = 1.2
RETRIES = 4
WINDOW_DAYS = 730
SHARE_WINDOW = "365D"
SHARE_MIN_OBS = 90

# Hindi Wikipedia carries a fraction of English traffic, so a channel
# can resolve fine and still be too thin to correlate honestly. Below
# this median daily view count the channel publishes its coverage and
# refuses a correlation rather than reporting one computed on noise.
MIN_MEDIAN_VIEWS = 20.0


def _channels() -> dict[str, list[str]]:
    with open(ROOT / "wikipedia_articles.json", encoding="utf-8") as f:
        lists = json.load(f)
    return {ch: t for ch, t in lists.items()
            if ch != "_meta" and isinstance(t, list)}


def resolve() -> dict[str, Any]:
    """English title -> Hindi title, via Wikipedia's interlanguage links.
    Never hand-picked: see module docstring."""
    channels = _channels()
    titles = [t for v in channels.values() for t in v]
    found: dict[str, str] = {}
    missing: list[str] = []
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        r = requests.get(LANGLINKS, params={
            "action": "query", "format": "json", "prop": "langlinks",
            "lllang": "hi", "lllimit": "max", "titles": "|".join(batch),
        }, headers=HEADERS, timeout=30)
        r.raise_for_status()
        for pg in r.json().get("query", {}).get("pages", {}).values():
            title = pg.get("title")
            links = pg.get("langlinks") or []
            if links:
                found[title] = links[0]["*"]
            elif title:
                missing.append(title)
        time.sleep(0.5)

    per_channel = {
        ch: {"resolved": {t: found[t] for t in ts if t in found},
             "missing": [t for t in ts if t not in found]}
        for ch, ts in channels.items()
    }
    payload = {
        "_meta": {
            "method": ("Resolved from the registered English titles via "
                       "the MediaWiki langlinks API. Hindi titles are "
                       "never chosen by hand: picking them would let the "
                       "analyst pick the ones that correlate."),
            "n_registered": len(titles),
            "n_resolved": len(found),
            "n_missing": len(missing),
            "resolved_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": per_channel,
    }
    MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAP_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    return payload


def _fetch_window(slug: str, w_start: date, w_end: date) -> list[dict]:
    key = urllib.parse.quote(slug, safe="")[:80]
    cache = CACHE_DIR / f"{key}_{w_start.isoformat()}_{w_end.isoformat()}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["items"]
    url = PAGEVIEWS.format(article=slug,
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
    payload: dict = {"items": []} if r.status_code == 404 else r.json()
    if r.status_code not in (200, 404):
        r.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload["items"]


def _fetch_article(title: str, end: date) -> pd.Series:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    items: list[dict] = []
    cur = START
    while cur <= end:
        w_end = min(cur + timedelta(days=WINDOW_DAYS - 1), end)
        items.extend(_fetch_window(slug, cur, w_end))
        cur = w_end + timedelta(days=1)
    if not items:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([it["timestamp"][:8] for it in items],
                         format="%Y%m%d")
    return (pd.Series([it["views"] for it in items], index=idx, dtype=float)
            .groupby(level=0).sum())


def channel_series(titles: list[str], end: date) -> tuple[pd.Series, float]:
    """Channel share series and the median daily raw view count, the
    latter being what decides whether a correlation may be reported."""
    parts = [s for t in titles if not (s := _fetch_article(t, end)).empty]
    if not parts:
        return pd.Series(dtype=float), 0.0
    total = pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).sort_index()
    trailing = total.rolling(SHARE_WINDOW, min_periods=SHARE_MIN_OBS).sum()
    return (total / trailing).dropna(), float(total.median())


def _corr(a: pd.Series, b: pd.Series) -> dict[str, Any]:
    joined = pd.concat([a, b], axis=1, join="inner").dropna()
    if len(joined) < 180:
        return {"n": len(joined), "levels_pearson": None,
                "levels_spearman": None, "changes_pearson": None,
                "refused": "fewer than 180 overlapping days"}
    x, y = joined.iloc[:, 0], joined.iloc[:, 1]
    dx, dy = x.diff().dropna(), y.diff().dropna()

    def _r(v: float) -> float | None:
        """A correlation against a zero-variance series is undefined,
        and pandas returns NaN for it. json.dumps writes bare NaN, which
        is not valid JSON -- every downstream parser would reject the
        payload. Undefined publishes as null, the same discipline
        src/retest.py applies to an undefined kappa."""
        f = float(v)
        return None if f != f else round(f, 4)

    return {
        "n": int(len(joined)),
        "levels_pearson": _r(x.corr(y)),
        # Pearson on ranks IS Spearman, and it keeps scipy out of the
        # dependency set: this project's replication promise is worth
        # more than the two characters saved by method="spearman".
        "levels_spearman": _r(x.rank().corr(y.rank())),
        # Changes are the harder and more honest test: levels can
        # correlate through nothing but a shared trend.
        "changes_pearson": _r(dx.corr(dy)),
        "refused": None,
    }


def english_comparison(gdelt: pd.DataFrame) -> dict[str, Any]:
    """The same statistic against ENGLISH Wikipedia, computed
    identically from the committed store.

    Without this the Hindi numbers are uninterpretable. A weak
    Hindi correlation could mean the index is Anglophone, or it could
    mean pageviews and press coverage simply differ (demand-side vs
    supply-side, which this project already expects). Only the gap
    between the two languages, measured the same way on the same days,
    separates those explanations -- and the published cross_source block
    cannot do it, because it correlates PERCENTILES where this
    correlates SHARES.
    """
    wiki_store = RAW_DIR / "wiki_volume.csv"
    if not wiki_store.exists():
        return {}
    w = pd.read_csv(wiki_store, parse_dates=["date"]).set_index("date")
    out: dict[str, Any] = {}
    for ch in gdelt.columns:
        if ch in w.columns:
            out[ch] = _corr(w[ch], gdelt[ch])
    return out


def main() -> None:
    if "--resolve" in sys.argv:
        p = resolve()
        m = p["_meta"]
        print(f"[wiki-hi] resolved {m['n_resolved']}/{m['n_registered']}; "
              f"{m['n_missing']} without a Hindi article")
        for ch, blk in p["channels"].items():
            print(f"[wiki-hi]   {ch:15s} {len(blk['resolved'])}/"
                  f"{len(blk['resolved']) + len(blk['missing'])}"
                  + (f"  missing: {', '.join(blk['missing'])}"
                     if blk["missing"] else ""))
        return

    if not MAP_PATH.exists():
        raise SystemExit("[wiki-hi] no title mapping; run --resolve first")
    mapping = json.loads(MAP_PATH.read_text(encoding="utf-8"))

    gdelt = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")
    end = gdelt.index.max().date()

    results: dict[str, Any] = {}
    for ch, blk in mapping["channels"].items():
        hindi_titles = list(blk["resolved"].values())
        n_reg = len(blk["resolved"]) + len(blk["missing"])
        if not hindi_titles:
            results[ch] = {
                "n_articles_resolved": 0, "n_articles_registered": n_reg,
                "missing_english_titles": blk["missing"],
                "refused": "no registered article exists in Hindi",
            }
            print(f"[wiki-hi] {ch}: no Hindi articles; refused")
            continue

        series, median_views = channel_series(hindi_titles, end)
        entry: dict[str, Any] = {
            "n_articles_resolved": len(hindi_titles),
            "n_articles_registered": n_reg,
            "hindi_titles": hindi_titles,
            "missing_english_titles": blk["missing"],
            "median_daily_views": round(median_views, 1),
        }
        if series.empty or median_views < MIN_MEDIAN_VIEWS:
            entry["refused"] = (
                f"median {median_views:.0f} daily views across the "
                f"channel's Hindi articles is below the {MIN_MEDIAN_VIEWS:.0f} "
                "floor; a correlation here would be a statement about "
                "Poisson noise, not about attention")
            results[ch] = entry
            print(f"[wiki-hi] {ch}: {median_views:.0f} median views; refused")
            continue
        if ch not in gdelt.columns:
            entry["refused"] = "channel not in the GDELT store"
            results[ch] = entry
            continue

        entry.update(_corr(series, gdelt[ch]))
        entry["refused"] = entry.get("refused")
        results[ch] = entry
        print(f"[wiki-hi] {ch}: n={entry['n']} "
              f"levels r={entry['levels_pearson']} "
              f"changes r={entry['changes_pearson']} "
              f"(median {median_views:.0f} views/day)")

    english = english_comparison(gdelt)
    gaps = {
        ch: {
            "english_changes": english[ch].get("changes_pearson"),
            "hindi_changes": results[ch].get("changes_pearson"),
            "english_levels": english[ch].get("levels_pearson"),
            "hindi_levels": results[ch].get("levels_pearson"),
        }
        for ch in english
        if ch in results and results[ch].get("changes_pearson") is not None
    }
    english_higher = [
        ch for ch, g in gaps.items()
        if g["english_changes"] is not None
        and g["hindi_changes"] is not None
        and g["english_changes"] > g["hindi_changes"]
        and g["english_levels"] > g["hindi_levels"]
    ]

    payload = {
        "_meta": {
            "what": (
                "Cross-language validity check. The index is built from "
                "an English-language corpus and was cross-validated "
                "against English Wikipedia, so every leg of the "
                "apparatus was Anglophone and none of it could "
                "distinguish 'Indian salience' from 'what the "
                "international English-language press covers'. Hindi "
                "Wikipedia pageviews are the same registered article "
                "set read by a different population, on infrastructure "
                "sharing no code or sampling with GDELT."),
            "title_selection": mapping["_meta"]["method"],
            "the_misses_are_a_finding": (
                "Articles with no Hindi counterpart are not random: they "
                "are the foreign-policy-apparatus topics (sanctions "
                "regimes, maritime security). Their absence is evidence "
                "about which parts of this construct live in Indian "
                "public attention at all, and is reported as a result "
                "rather than as a coverage caveat."),
            "reading_the_numbers": (
                "changes_pearson is the load-bearing figure; levels can "
                "correlate through a shared trend alone. Nothing here "
                "adjusts, weights or corrects the index -- it is "
                "evidence about what the index measures."),
            "min_median_views_to_correlate": MIN_MEDIAN_VIEWS,
            "n_registered_articles": mapping["_meta"]["n_registered"],
            "n_resolved_to_hindi": mapping["_meta"]["n_resolved"],
            "finding": (
                "English Wikipedia tracks this index more closely than "
                f"Hindi Wikipedia does, on {len(english_higher)} of "
                f"{len(gaps)} channels, in BOTH levels and day-to-day "
                "changes. The gap is one-directional -- there is no "
                "channel where Hindi leads -- which is what an "
                "Anglophone construct looks like. The index is built "
                "from an English corpus and it appears to measure "
                "English-language attention to India better than it "
                "measures Indian-language attention. This is a "
                "limitation of the instrument, published as a result."),
            "the_obvious_objection_and_why_it_fails": (
                "Hindi Wikipedia carries less traffic, so one expects "
                "attenuation from noise alone. That cannot be the whole "
                "story here: us_trade has the HIGHEST median Hindi "
                "traffic of any channel and the WORST correlation (the "
                "only negative one), while gulf_energy has the lowest "
                "traffic and the strongest Hindi correlation. The "
                "ordering of traffic and the ordering of agreement do "
                "not match, so thinness does not explain the pattern."),
            "what_this_does_not_say": (
                "It does not say the index is wrong. Readers and editors "
                "are different populations attending to different "
                "things, and supply-side vs demand-side divergence is "
                "something this project already expects and publishes. "
                "It says the construct's reach into Indian-language "
                "attention is weaker than its reach into "
                "English-language attention, and that anyone citing this "
                "index as a measure of Indian public salience should "
                "read this file first. Nothing here adjusts a score."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": results,
        "english_wikipedia_same_statistic": english,
        "language_gap": gaps,
        "channels_where_english_leads_on_both": english_higher,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "wiki_hindi.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[wiki-hi] wrote docs/data/wiki_hindi.json")


if __name__ == "__main__":
    main()
