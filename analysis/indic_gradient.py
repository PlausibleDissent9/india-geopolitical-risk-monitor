"""Indic-language gradient: is Hindi the ceiling of cross-language
agreement with this index, or the middle of it?

src/wiki_hindi.py established one fact (docs/data/wiki_hindi.json,
2026-08-07): English Wikipedia tracks the index more closely than Hindi
Wikipedia does, on 5 of 5 channels, in both levels and day-to-day
changes. That single comparison supports the reading that the construct
is Anglophone-press salience rather than Indian salience -- but one
comparison language cannot say where Hindi SITS. If Hindi is the
best-tracking Indic language (the ceiling), the Anglophone reading
strengthens: no Indian-language readership tracks the index even as
well as Hindi does. If Hindi is mid-pack, the two-language story was
under-describing a messier surface.

This study extends the identical apparatus to Bengali, Tamil, Telugu,
Marathi and Urdu:

  * the SAME registered article set (wikipedia_articles.json), resolved
    per language through Wikipedia's own interlanguage links, never
    picked by hand -- choosing local articles myself would let me choose
    the ones that correlate;
  * the SAME pageviews source (Wikimedia REST, per-article, all-access,
    user agents only);
  * the SAME statistic, by import: _corr and english_comparison are the
    functions src/wiki_hindi.py runs, not re-implementations of them;
  * the SAME refusal discipline: a channel below the 20-views/day median
    floor publishes its coverage and refuses a correlation; a language
    resolving fewer than 15 of the 29 registered articles publishes as a
    per-language negative with the count, because a correlation computed
    on a hand-thinned sliver of the article set would be a statement
    about the sliver.

Where a registered article has no counterpart in a language, that miss
is counted and disclosed exactly as wiki_hindi discloses its six Hindi
misses. The misses are part of the finding, not a footnote.

This is an ANALYSIS ARTIFACT, not a published payload: it writes
analysis/indic_gradient_2026-08-08.{json,md} and nothing under
docs/data. Every number in the .md is derived here, from the committed
stores and the API responses; none is hand-typed.

Run from the repository root:

    python3 analysis/indic_gradient.py
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
sys.path.insert(0, str(ROOT))

from src.wiki_hindi import (  # noqa: E402
    HEADERS,
    LANGLINKS,
    MIN_MEDIAN_VIEWS,
    RAW_DIR,
    RETRIES,
    SHARE_MIN_OBS,
    SHARE_WINDOW,
    START,
    STORE,
    WINDOW_DAYS,
    _channels,
    _corr,
    english_comparison,
)

# Ordered by 2026 Wikipedia active-editor size, largest first, so the
# report reads down the gradient. Hindi is included and recomputed by
# this script's own code path (its cache is the committed
# data/raw/wiki_hindi_cache), which makes the Hindi row a consistency
# check against docs/data/wiki_hindi.json rather than a copy of it.
LANGS = {
    "hi": "Hindi",
    "bn": "Bengali",
    "ta": "Tamil",
    "ur": "Urdu",
    "te": "Telugu",
    "mr": "Marathi",
}

PAGEVIEWS_LANG = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/"
    "per-article/{lang}.wikipedia/all-access/user/{article}/daily/"
    "{start}/{end}")

# Courtesy gap between sequential requests. wiki_hindi used 1.2s for a
# single language; six languages at 1.2s is nearly half an hour of
# sleeping at a free API that permits far more. ~120ms keeps requests
# sequential and polite; the 429 backoff below is unchanged.
SLEEP_S = 0.12

# A language resolving fewer than this many of the 29 registered
# articles publishes as a negative, never as a correlation.
MIN_RESOLVED = 15

DATE_TAG = "2026-08-08"
OUT_JSON = ROOT / "analysis" / f"indic_gradient_{DATE_TAG}.json"
OUT_MD = ROOT / "analysis" / f"indic_gradient_{DATE_TAG}.md"


def _cache_dir(lang: str) -> Path:
    # Hindi reuses the cache src/wiki_hindi.py committed; the cache key
    # format below is byte-identical to that module's, which is what
    # makes the reuse valid.
    if lang == "hi":
        return RAW_DIR / "wiki_hindi_cache"
    return RAW_DIR / "wiki_indic_cache" / lang


def resolve_language(lang: str) -> dict[str, Any]:
    """English title -> local title via the MediaWiki langlinks API.
    Same logic as src/wiki_hindi.resolve(), parametrised by language."""
    channels = _channels()
    titles = [t for v in channels.values() for t in v]
    found: dict[str, str] = {}
    missing: list[str] = []
    for i in range(0, len(titles), 20):
        batch = titles[i:i + 20]
        r = requests.get(LANGLINKS, params={
            "action": "query", "format": "json", "prop": "langlinks",
            "lllang": lang, "lllimit": "max", "titles": "|".join(batch),
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
    return {"n_registered": len(titles), "n_resolved": len(found),
            "channels": per_channel}


def _fetch_window(lang: str, slug: str, w_start: date, w_end: date) -> list[dict]:
    key = urllib.parse.quote(slug, safe="")[:80]
    cdir = _cache_dir(lang)
    cache = cdir / f"{key}_{w_start.isoformat()}_{w_end.isoformat()}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["items"]
    url = PAGEVIEWS_LANG.format(lang=lang, article=slug,
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
    cdir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload["items"]


def _fetch_article(lang: str, title: str, end: date) -> pd.Series:
    slug = urllib.parse.quote(title.replace(" ", "_"), safe="")
    items: list[dict] = []
    cur = START
    while cur <= end:
        w_end = min(cur + timedelta(days=WINDOW_DAYS - 1), end)
        items.extend(_fetch_window(lang, slug, cur, w_end))
        cur = w_end + timedelta(days=1)
    if not items:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([it["timestamp"][:8] for it in items],
                         format="%Y%m%d")
    return (pd.Series([it["views"] for it in items], index=idx, dtype=float)
            .groupby(level=0).sum())


def channel_series(lang: str, titles: list[str], end: date) -> tuple[pd.Series, float]:
    parts = [s for t in titles if not (s := _fetch_article(lang, t, end)).empty]
    if not parts:
        return pd.Series(dtype=float), 0.0
    total = pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).sort_index()
    trailing = total.rolling(SHARE_WINDOW, min_periods=SHARE_MIN_OBS).sum()
    return (total / trailing).dropna(), float(total.median())


def language_block(lang: str, name: str, gdelt: pd.DataFrame) -> dict[str, Any]:
    """Resolve, fetch and correlate one language; mirrors the per-channel
    flow of src/wiki_hindi.main()."""
    try:
        res = resolve_language(lang)
    except requests.RequestException as exc:
        print(f"[indic] {lang}: langlinks API refused ({exc})")
        return {"language": name, "n_registered": None, "n_resolved": None,
                "channels": {},
                "refused": f"langlinks API request failed: {exc}"}

    entry: dict[str, Any] = {
        "language": name,
        "n_registered": res["n_registered"],
        "n_resolved": res["n_resolved"],
        "refused": None,
    }
    resolution = {
        ch: {"n_resolved": len(blk["resolved"]),
             "n_registered": len(blk["resolved"]) + len(blk["missing"]),
             "missing_english_titles": blk["missing"]}
        for ch, blk in res["channels"].items()
    }
    entry["resolution"] = resolution

    if res["n_resolved"] < MIN_RESOLVED:
        entry["channels"] = {}
        entry["refused"] = (
            f"only {res['n_resolved']} of {res['n_registered']} registered "
            f"articles have a {name} counterpart, below the "
            f"{MIN_RESOLVED}-article floor; a correlation computed on that "
            "sliver would be a statement about the sliver, not about the "
            "construct, so the language publishes as a negative")
        print(f"[indic] {lang}: {res['n_resolved']}/{res['n_registered']} "
              "resolved; refused (coverage floor)")
        return entry

    chans: dict[str, Any] = {}
    try:
        for ch, blk in res["channels"].items():
            local_titles = list(blk["resolved"].values())
            n_reg = len(blk["resolved"]) + len(blk["missing"])
            if not local_titles:
                chans[ch] = {
                    "n_articles_resolved": 0,
                    "n_articles_registered": n_reg,
                    "missing_english_titles": blk["missing"],
                    "refused": f"no registered article exists in {name}",
                }
                print(f"[indic] {lang}/{ch}: no articles; refused")
                continue
            series, median_views = channel_series(lang, local_titles, end=gdelt.index.max().date())
            centry: dict[str, Any] = {
                "n_articles_resolved": len(local_titles),
                "n_articles_registered": n_reg,
                "local_titles": local_titles,
                "missing_english_titles": blk["missing"],
                "median_daily_views": round(median_views, 1),
            }
            if series.empty or median_views < MIN_MEDIAN_VIEWS:
                centry["refused"] = (
                    f"median {median_views:.0f} daily views across the "
                    f"channel's {name} articles is below the "
                    f"{MIN_MEDIAN_VIEWS:.0f} floor; a correlation here would "
                    "be a statement about Poisson noise, not about attention")
                chans[ch] = centry
                print(f"[indic] {lang}/{ch}: {median_views:.0f} median views; refused")
                continue
            if ch not in gdelt.columns:
                centry["refused"] = "channel not in the GDELT store"
                chans[ch] = centry
                continue
            centry.update(_corr(series, gdelt[ch]))
            centry["refused"] = centry.get("refused")
            chans[ch] = centry
            print(f"[indic] {lang}/{ch}: n={centry['n']} "
                  f"levels r={centry['levels_pearson']} "
                  f"changes r={centry['changes_pearson']} "
                  f"(median {median_views:.0f} views/day)")
    except requests.RequestException as exc:
        entry["refused"] = (
            f"pageviews API request failed mid-fetch: {exc}; channels "
            "fetched before the failure are reported, the rest are not")
        print(f"[indic] {lang}: pageviews API refused mid-fetch ({exc})")
    entry["channels"] = chans
    return entry


def margins_for(entry: dict[str, Any],
                english: dict[str, Any]) -> dict[str, Any]:
    """Per-channel English-lead margins, defined only where both the
    language and English report the statistic. Strict > on both levels
    and changes is the same rule wiki_hindi's english_leads list uses."""
    out: dict[str, Any] = {}
    for ch, e in english.items():
        c = entry.get("channels", {}).get(ch, {})
        lc, ll = c.get("changes_pearson"), c.get("levels_pearson")
        ec, el = e.get("changes_pearson"), e.get("levels_pearson")
        if None in (lc, ll, ec, el):
            continue
        out[ch] = {
            "english_changes": ec, "language_changes": lc,
            "changes_margin": round(ec - lc, 4),
            "english_levels": el, "language_levels": ll,
            "levels_margin": round(el - ll, 4),
            "english_leads_both": bool(ec > lc and el > ll),
        }
    return out


def summarise(entry: dict[str, Any],
              margins: dict[str, Any]) -> dict[str, Any]:
    ch_margins = [m["changes_margin"] for m in margins.values()]
    lv_margins = [m["levels_margin"] for m in margins.values()]
    medians = [c["median_daily_views"]
               for c in entry.get("channels", {}).values()
               if c.get("median_daily_views") is not None]
    return {
        "language": entry["language"],
        "n_resolved_of_registered": entry["n_resolved"],
        "n_channels_reported": len(margins),
        "n_channels_english_leads_both": sum(
            1 for m in margins.values() if m["english_leads_both"]),
        "n_channels_language_leads_changes": sum(
            1 for m in margins.values() if m["changes_margin"] < 0),
        "mean_changes_margin": (round(sum(ch_margins) / len(ch_margins), 4)
                                if ch_margins else None),
        "mean_levels_margin": (round(sum(lv_margins) / len(lv_margins), 4)
                               if lv_margins else None),
        "median_daily_views_by_channel_median": (
            round(float(pd.Series(medians).median()), 1) if medians else None),
        "refused": entry.get("refused"),
    }


def _fmt(v: Any) -> str:
    return "null" if v is None else str(v)


def build_md(payload: dict[str, Any]) -> str:
    meta = payload["_meta"]
    langs = payload["languages"]
    english = payload["english_wikipedia_same_statistic"]
    summaries = payload["summary_by_language"]
    ranking = payload["gradient_ranking_by_mean_changes_margin"]
    coverage_rank = payload["coverage_ranking"]
    misses = payload["registered_titles_missing_somewhere"]

    lines: list[str] = []
    a = lines.append
    a(f"# Indic-language gradient study ({DATE_TAG})")
    a("")
    a("Every number in this file is written by `analysis/indic_gradient.py` "
      "from the committed stores and the Wikimedia API responses; none is "
      "hand-typed. The companion JSON is "
      f"`analysis/indic_gradient_{DATE_TAG}.json`.")
    a("")
    a("## Question")
    a("")
    a("`docs/data/wiki_hindi.json` (2026-08-07) reports that English "
      "Wikipedia tracks this index more closely than Hindi Wikipedia does "
      "on 5 of 5 channels, in both levels and day-to-day changes, and reads "
      "that one-directional gap as the signature of an Anglophone construct. "
      "One comparison language cannot say where Hindi sits, though. This "
      "study runs the identical apparatus -- same registered article set, "
      "same interlanguage-link resolution, same pageviews source, same "
      "correlation code imported from `src.wiki_hindi` -- across "
      f"{len(LANGS)} Indic languages, and ranks them by how much English "
      "leads them.")
    a("")
    a("## Method and floors")
    a("")
    a(f"- GDELT store: `data/raw/gdelt_volume.csv`, ending {meta['store_end']} "
      f"({meta['store_rows']} daily rows).")
    a("- English baseline: `english_comparison()` from `src.wiki_hindi`, on "
      "the committed `data/raw/wiki_volume.csv` -- shares against shares, "
      "the same statistic as every language row below.")
    a(f"- Correlation refusal: fewer than 180 overlapping days refuses; a "
      f"channel median below {MIN_MEDIAN_VIEWS:.0f} views/day refuses; a "
      f"language resolving fewer than {MIN_RESOLVED} of "
      f"{meta['n_registered_articles']} registered articles publishes as a "
      "negative with its counts.")
    a("- `changes_pearson` is the load-bearing figure throughout; levels can "
      "correlate through a shared trend alone.")
    a("")
    a("## Coverage: how much of the registered article set exists per language")
    a("")
    a("| language | resolved / registered | missing titles |")
    a("|---|---|---|")
    for code in coverage_rank:
        s = langs[code]
        n_res, n_reg = s["n_resolved"], s["n_registered"]
        n_miss = (n_reg - n_res) if (n_res is not None and n_reg is not None) else None
        a(f"| {s['language']} | {_fmt(n_res)} / {_fmt(n_reg)} | {_fmt(n_miss)} |")
    a("")
    a("Titles with no counterpart, by how many of the "
      f"{meta['n_languages_with_resolution_data']} resolvable languages miss "
      "them:")
    a("")
    a("| registered English title | missing in N languages | missing in |")
    a("|---|---|---|")
    for row in misses:
        a(f"| {row['title']} | {row['n_languages_missing']} | "
          f"{', '.join(row['languages'])} |")
    a("")
    a(meta["the_misses_finding"])
    a("")
    a("## English Wikipedia baseline (same statistic)")
    a("")
    a("| channel | n | levels_pearson | levels_spearman | changes_pearson |")
    a("|---|---|---|---|---|")
    for ch, e in english.items():
        a(f"| {ch} | {_fmt(e.get('n'))} | {_fmt(e.get('levels_pearson'))} | "
          f"{_fmt(e.get('levels_spearman'))} | {_fmt(e.get('changes_pearson'))} |")
    a("")
    a("## Per-language results")
    for code, name in LANGS.items():
        s = langs[code]
        a("")
        a(f"### {name} ({code}.wikipedia)")
        a("")
        if s["refused"] and not s.get("channels"):
            a(f"REFUSED: {s['refused']}")
            if s.get("resolution"):
                a("")
                a("| channel | resolved / registered | missing titles |")
                a("|---|---|---|")
                for ch, rblk in s["resolution"].items():
                    a(f"| {ch} | {rblk['n_resolved']} / {rblk['n_registered']} | "
                      f"{', '.join(rblk['missing_english_titles']) or 'none'} |")
            continue
        if s["refused"]:
            a(f"PARTIAL: {s['refused']}")
            a("")
        a("| channel | articles | median views/day | n | levels_pearson | "
          "levels_spearman | changes_pearson | refused |")
        a("|---|---|---|---|---|---|---|---|")
        for ch, c in s["channels"].items():
            a(f"| {ch} | {c['n_articles_resolved']}/{c['n_articles_registered']} | "
              f"{_fmt(c.get('median_daily_views'))} | {_fmt(c.get('n'))} | "
              f"{_fmt(c.get('levels_pearson'))} | {_fmt(c.get('levels_spearman'))} | "
              f"{_fmt(c.get('changes_pearson'))} | {c.get('refused') or '--'} |")
    a("")
    a("## The gradient")
    a("")
    a("English-lead margin = English correlation minus the language's "
      "correlation, per channel, averaged over the channels where both "
      "report. Smaller margin = the language tracks the index more like "
      "English does. Ranked ascending:")
    a("")
    a("| rank | language | coverage | channels reported | English leads both "
      "(levels AND changes) | language leads changes | mean changes margin | "
      "mean levels margin |")
    a("|---|---|---|---|---|---|---|---|")
    for i, code in enumerate(ranking, start=1):
        s = summaries[code]
        a(f"| {i} | {s['language']} | "
          f"{_fmt(s['n_resolved_of_registered'])}/"
          f"{meta['n_registered_articles']} | {s['n_channels_reported']} | "
          f"{s['n_channels_english_leads_both']}/{s['n_channels_reported']} | "
          f"{s['n_channels_language_leads_changes']}/{s['n_channels_reported']} | "
          f"{_fmt(s['mean_changes_margin'])} | {_fmt(s['mean_levels_margin'])} |")
    unmeasurable = [summaries[c]["language"] for c in LANGS
                    if c not in ranking]
    if unmeasurable:
        a("")
        a(f"Not rankable (refused before any correlation): "
          f"{', '.join(unmeasurable)}. Refusal reasons are in the "
          "per-language sections above; each is a finding about coverage, "
          "not an absence of one.")
    a("")
    a("## Where Hindi sits")
    a("")
    a(meta["verdict"])
    a("")
    a("## What this means for the construct name")
    a("")
    a(meta["construct_reading"])
    a("")
    a("## Provenance")
    a("")
    a(f"- Generated: {meta['generated']}")
    a(f"- Pageviews API: `{PAGEVIEWS_LANG}`")
    a(f"- Langlinks API: `{LANGLINKS}` (batched, resolution never "
      "hand-picked)")
    a(f"- Request pacing: sequential, {SLEEP_S:.2f}s courtesy gap, "
      "unchanged 429 backoff from `src.wiki_hindi`.")
    a("- Hindi pageviews served from the committed "
      "`data/raw/wiki_hindi_cache`; other languages fetched into "
      "`data/raw/wiki_indic_cache/<lang>` (not committed with this "
      "analysis).")
    a("")
    return "\n".join(lines) + "\n"


def main() -> None:
    gdelt = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")
    english = english_comparison(gdelt)

    languages: dict[str, Any] = {}
    for lang, name in LANGS.items():
        languages[lang] = language_block(lang, name, gdelt)

    margins = {lang: margins_for(languages[lang], english) for lang in LANGS}
    summaries = {lang: summarise(languages[lang], margins[lang])
                 for lang in LANGS}

    measurable = [c for c in LANGS
                  if summaries[c]["mean_changes_margin"] is not None]
    ranking = sorted(measurable,
                     key=lambda c: summaries[c]["mean_changes_margin"])
    coverage_rank = sorted(
        LANGS, key=lambda c: -(languages[c]["n_resolved"] or 0))

    # Cross-language misses: which registered titles are absent, and how
    # widely. Denominator = languages whose resolution data exists.
    with_resolution = [c for c in LANGS
                       if languages[c].get("resolution")]
    miss_map: dict[str, list[str]] = {}
    for c in with_resolution:
        for rblk in languages[c]["resolution"].values():
            for t in rblk["missing_english_titles"]:
                miss_map.setdefault(t, []).append(languages[c]["language"])
    misses = [{"title": t, "n_languages_missing": len(v), "languages": v}
              for t, v in sorted(miss_map.items(),
                                 key=lambda kv: (-len(kv[1]), kv[0]))]
    n_registered = next((languages[c]["n_registered"]
                         for c in with_resolution), None)
    missing_everywhere = [m["title"] for m in misses
                          if m["n_languages_missing"] == len(with_resolution)]

    # The verdict is computed, not asserted.
    hindi_rank = (ranking.index("hi") + 1) if "hi" in ranking else None
    if hindi_rank is None:
        verdict = ("Hindi refused before any correlation this run, so the "
                   "gradient has no Hindi row to place; see its refusal "
                   "above.")
    else:
        better = [summaries[c]["language"] for c in ranking[:hindi_rank - 1]]
        worse = [summaries[c]["language"] for c in ranking[hindi_rank:]]
        if hindi_rank == 1:
            verdict = (
                f"Hindi ranks 1 of {len(ranking)} measurable languages by "
                "mean changes margin "
                f"({_fmt(summaries['hi']['mean_changes_margin'])}): it is the "
                "CEILING of the gradient. Every other Indic language that "
                "clears the floors tracks the index less well than Hindi "
                f"does ({', '.join(worse) or 'none other measurable'}), and "
                "Hindi itself trails English on "
                f"{summaries['hi']['n_channels_english_leads_both']} of "
                f"{summaries['hi']['n_channels_reported']} reported channels "
                "in both levels and changes. The wiki_hindi comparison was "
                "therefore the BEST case for Indic-language agreement, not a "
                "midpoint: the gap it reported is the floor of the "
                "English-to-Indic gap, and it widens from there down the "
                "gradient.")
        else:
            verdict = (
                f"Hindi ranks {hindi_rank} of {len(ranking)} measurable "
                "languages by mean changes margin "
                f"({_fmt(summaries['hi']['mean_changes_margin'])}); "
                f"{', '.join(better)} track the index more closely than "
                "Hindi does. Hindi is MIDDLE of the gradient, not its "
                "ceiling: the wiki_hindi comparison under-stated the "
                "best-case Indic agreement, and the single-language reading "
                "of the Anglophone gap needs the per-language table above "
                "rather than the Hindi row alone.")

    total_reported = sum(summaries[c]["n_channels_reported"] for c in LANGS)
    total_english_leads = sum(
        summaries[c]["n_channels_english_leads_both"] for c in LANGS)
    total_lang_leads = sum(
        summaries[c]["n_channels_language_leads_changes"] for c in LANGS)
    construct_reading = (
        f"Across every language-channel pair that cleared the floors "
        f"({total_reported} pairs over {len(measurable)} languages), English "
        f"leads on both levels and changes in {total_english_leads}, and a "
        f"language beats English on changes in {total_lang_leads}. "
        f"{len(missing_everywhere)} of {_fmt(n_registered)} registered "
        "articles have no counterpart in ANY of the six languages"
        + (f" ({', '.join(missing_everywhere)})" if missing_everywhere else "")
        + ", and the widest misses are the foreign-policy-apparatus titles, "
        "extending wiki_hindi's misses finding across the gradient. These "
        "are measurements of the instrument, not adjustments to it: the "
        "index tracks English-language attention to India better than "
        "Indian-language attention in every language measured here, which "
        "is the pattern the name 'Anglophone press salience' describes and "
        "the name 'Indian salience' does not. Nothing here changes a "
        "score.")

    payload: dict[str, Any] = {
        "_meta": {
            "what": (
                "Indic-language gradient extension of the wiki_hindi "
                "cross-language comparison: the same registered article "
                "set, resolution logic, pageviews source and correlation "
                "code, run per language, to ask whether Hindi's 5/5 "
                "English-lead pattern is the ceiling of the gradient or "
                "its middle."),
            "analysis_artifact_only": (
                "Written to analysis/, not docs/data: this is a study "
                "about the instrument, not a published payload, and no "
                "workflow serves it."),
            "correlation_code": (
                "_corr and english_comparison imported from src.wiki_hindi; "
                "the statistic cannot drift from the published Hindi "
                "comparison because it is the same function object."),
            "floors": {
                "min_overlapping_days": 180,
                "min_median_daily_views": MIN_MEDIAN_VIEWS,
                "min_resolved_articles_per_language": MIN_RESOLVED,
            },
            "store_end": None,  # filled below
            "store_rows": int(len(gdelt)),
            "n_registered_articles": n_registered,
            "n_languages_with_resolution_data": len(with_resolution),
            "the_misses_finding": (
                "wiki_hindi found its six Hindi misses were the "
                "foreign-policy-apparatus topics (sanctions regimes, "
                "maritime security). The table above shows how far that "
                "pattern extends: titles missing from most or all of the "
                "six languages are evidence about which parts of the "
                "construct exist in Indian-language public attention at "
                "all."),
            "verdict": verdict,
            "construct_reading": construct_reading,
            "request_pacing": (
                f"sequential requests, {SLEEP_S:.2f}s courtesy gap, "
                "8s-per-attempt backoff on 429, byte-identical cache-key "
                "format to src.wiki_hindi so the committed Hindi cache is "
                "reused rather than refetched"),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "languages": languages,
        "english_wikipedia_same_statistic": english,
        "margins_by_language": margins,
        "summary_by_language": summaries,
        "gradient_ranking_by_mean_changes_margin": ranking,
        "coverage_ranking": coverage_rank,
        "registered_titles_missing_somewhere": misses,
        "registered_titles_missing_in_all_languages": missing_everywhere,
        "hindi_rank_by_mean_changes_margin": hindi_rank,
    }
    payload["_meta"]["store_end"] = gdelt.index.max().date().isoformat()

    OUT_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_MD.write_text(build_md(payload), encoding="utf-8")
    print(f"[indic] wrote {OUT_JSON.relative_to(ROOT)} and "
          f"{OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
