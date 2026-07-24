"""
Validation harness (spec layer 4): the difference between a dashboard and
an instrument.

  python -m src.validate hit-rate    offline; needs docs/data/episodes.json
  python -m src.validate placebo     fetches placebo channels from GDELT
  python -m src.validate robustness  fetches broad/narrow dictionary variants

hit-rate  -- detection rate of the pre-registered episode list
             (validation/validation_episodes.json) within +/-3 days.
placebo   -- placebo channels must NOT spike around geopolitical episodes;
             reports the overlap fraction.
robustness -- correlation of the primary percentile scores with broad and
             narrower dictionary constructions; >0.9 means results are not
             term-dependent.

Results are printed and merged into docs/data/validation.json.
GDELT fetches are cached in data/raw/ (delete the cache to refetch).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import build_index, fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
RAW_DIR = ROOT / "data" / "raw"
BACKFILL_START = date(2022, 1, 1)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _merge_results(key: str, payload) -> None:
    out = SITE_DATA / "validation.json"
    existing = _load_json(out) if out.exists() else {}
    existing[key] = payload
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(existing, indent=1), encoding="utf-8")
    print(f"[validate] merged '{key}' into {out}")


def _fetch_cached(dictionaries: dict, cache_name: str) -> pd.DataFrame:
    cache = RAW_DIR / cache_name
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"]).set_index("date")
        print(f"[validate] using cache {cache}")
        return df
    df = fetch_gdelt.fetch_all(dictionaries, BACKFILL_START, date.today())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache, index_label="date")
    return df


def hit_rate() -> None:
    reg = _load_json(ROOT / "validation" / "validation_episodes.json")
    ep_path = SITE_DATA / "episodes.json"
    if not ep_path.exists():
        sys.exit("no docs/data/episodes.json yet -- run the pipeline first")
    detected = _load_json(ep_path)
    window = reg["_meta"]["window_days"]

    rows, hits = [], 0
    for ev in reg["episodes"]:
        d = pd.Timestamp(ev["date"])
        lo, hi = d - pd.Timedelta(days=window), d + pd.Timedelta(days=window)
        hit = any(
            e["channel"] == ev["channel"]
            and pd.Timestamp(e["start"]) <= hi
            and pd.Timestamp(e["end"]) >= lo
            for e in detected
        )
        hits += hit
        rows.append({**ev, "hit": bool(hit)})
        print(f"  {'HIT ' if hit else 'MISS'}  {ev['channel']:14s} {ev['date']}  {ev['name']}")

    per_channel: dict[str, dict] = {}
    for r in rows:
        c = per_channel.setdefault(r["channel"], {"n": 0, "hits": 0})
        c["n"] += 1
        c["hits"] += r["hit"]
    n = len(rows)
    print(f"[validate] overall hit rate: {hits}/{n} = {hits / n:.0%}")
    _merge_results("hit_rate", {
        "window_days": window, "overall": {"n": n, "hits": hits},
        "per_channel": per_channel, "episodes": rows,
    })


def placebo() -> None:
    placebos = _load_json(ROOT / "dictionaries_placebo.json")
    vol = _fetch_cached(placebos, "gdelt_volume_placebo.csv")
    placebo_eps = build_index.detect_all_episodes(vol)

    geo = _load_json(SITE_DATA / "episodes.json")
    geo_days = set()
    for e in geo:
        for d in pd.date_range(e["start"], e["end"]):
            geo_days.add(d.date().isoformat())

    overlapping = [
        e for e in placebo_eps
        if any(d.date().isoformat() in geo_days
               for d in pd.date_range(e["start"], e["end"]))
    ]
    frac = len(overlapping) / len(placebo_eps) if placebo_eps else 0.0
    print(f"[validate] placebo episodes: {len(placebo_eps)}, "
          f"overlapping geopolitical episode days: {len(overlapping)} ({frac:.0%})")
    print("  (a high overlap means the pipeline measures general news volume)")
    _merge_results("placebo", {
        "n_placebo_episodes": len(placebo_eps),
        "n_overlapping": len(overlapping),
        "overlap_fraction": round(frac, 3),
        "episodes": placebo_eps,
    })


def robustness() -> None:
    primary_store = RAW_DIR / "gdelt_volume.csv"
    if not primary_store.exists():
        sys.exit("no data/raw/gdelt_volume.csv yet -- run the pipeline first")
    primary_vol = pd.read_csv(primary_store, parse_dates=["date"]).set_index("date")
    primary = build_index.build_scores(primary_vol)

    alts = _load_json(ROOT / "dictionaries_alt.json")
    report: dict = {}
    for variant in ("narrow", "broad"):
        vol = _fetch_cached(alts[variant], f"gdelt_volume_{variant}.csv")
        scores = build_index.build_scores(vol)
        cors = {}
        for ch in primary_vol.columns:
            if ch in scores.columns:
                joined = pd.concat(
                    [primary[ch], scores[ch]], axis=1, join="inner"
                ).dropna()
                cors[ch] = round(float(joined.corr().iloc[0, 1]), 3)
        comp = pd.concat(
            [primary["composite"], scores["composite"]], axis=1, join="inner"
        ).dropna()
        cors["composite"] = round(float(comp.corr().iloc[0, 1]), 3)
        report[variant] = cors
        print(f"[validate] {variant}: {cors}")
    print("  (>0.9 per channel means the index is not term-dependent)")
    _merge_results("robustness", report)


def precision() -> None:
    """Layer 4 precision audit (recall's missing half): sample 20 articles
    per channel from random windows across the sample period and write them
    with BLANK relevance fields. The Y/N judgments are the author's; below
    ~70% relevant means the terms are too loose (methodology s8)."""
    import random

    random.seed()  # deliberately unseeded: a fresh sample each audit
    d = _load_json(ROOT / "dictionaries.json")
    out_dir = ROOT / "validation"
    today = date.today()
    span_days = (today - BACKFILL_START).days - 60

    for ch, spec in d.items():
        if ch.startswith("_"):
            continue
        queries = fetch_gdelt.build_queries(spec["terms"], spec.get("anchor"))
        pool: dict[str, dict] = {}
        for _ in range(6):
            off = random.randrange(max(span_days, 1))
            w_start = BACKFILL_START + timedelta(days=off)
            w_end = min(w_start + timedelta(days=60), today)
            for q in queries:
                for a in fetch_gdelt.fetch_articles(q, w_start, w_end, maxrecords=8):
                    if a["url"]:
                        pool.setdefault(a["url"], a)
            if len(pool) >= 40:
                break
        sample = random.sample(list(pool.values()), min(20, len(pool)))
        lines = [
            f"# Precision sample: {ch}",
            "",
            f"Sampled {today.isoformat()} from random windows, "
            f"{BACKFILL_START}..{today}. Mark each [RELEVANT? ] Y or N by",
            "hand, then report the per-channel rate in methodology s8.",
            "",
        ]
        for i, a in enumerate(sample, 1):
            lines += [
                f"{i}. **{a['title']}**  ",
                f"   {a['domain']} · {a['date']} · {a['url']}  ",
                "   [RELEVANT? ]",
                "",
            ]
        path = out_dir / f"precision_sample_{ch}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[validate] wrote {path} ({len(sample)} articles)")


def drift() -> None:
    """Coverage-drift diagnostics (methodology s7.7): GDELT's monitored
    corpus and per-channel source composition over time.

    Per year: mean daily corpus size (the share denominator, from
    timelinevolraw), distinct source domains in a relevance sample of
    channel articles, and top-10 domain concentration (Herfindahl over
    sampled domain counts -- an approximation from the relevance sample,
    stated as such). Plus, per channel: correlation of the volume share
    with corpus size (a systematic trend would mean shares are absorbing
    composition change, not just world events)."""
    d = _load_json(ROOT / "dictionaries.json")
    channels = {ch: spec for ch, spec in d.items() if not ch.startswith("_")}
    today = date.today()

    first_ch, first_spec = next(iter(channels.items()))
    norm_q = fetch_gdelt.build_queries(first_spec["terms"], first_spec.get("anchor"))[0]
    print(f"[validate] corpus norm via {first_ch} query, {BACKFILL_START}..{today}")
    raw = fetch_gdelt.fetch_corpus_norm(norm_q, BACKFILL_START, today)
    norm = raw["norm"]
    norm.index = pd.to_datetime(norm.index)
    by_year = {
        str(y): int(v) for y, v in
        norm.groupby(norm.index.year).mean().round().items()
    }

    domain_stats: dict = {}
    for ch, spec in channels.items():
        q = fetch_gdelt.build_queries(spec["terms"], spec.get("anchor"))[0]
        per_year: dict = {}
        for y in sorted({ts.year for ts in norm.index}):
            arts = fetch_gdelt.fetch_articles(
                q, date(y, 1, 1), min(date(y, 12, 31), today), maxrecords=100
            )
            domains = pd.Series([a["domain"] for a in arts if a["domain"]])
            if domains.empty:
                continue
            shares = domains.value_counts(normalize=True)
            per_year[str(y)] = {
                "n_articles_sampled": int(len(domains)),
                "n_distinct_domains": int(domains.nunique()),
                "herfindahl_top10": round(float((shares.head(10) ** 2).sum()), 4),
            }
        domain_stats[ch] = per_year
        print(f"[validate] drift domains: {ch} ({len(per_year)} years)")

    vol_corr = {}
    store = RAW_DIR / "gdelt_volume.csv"
    if store.exists():
        vol = pd.read_csv(store, parse_dates=["date"]).set_index("date")
        for ch in vol.columns:
            joined = pd.concat([vol[ch], norm], axis=1, join="inner").dropna()
            if len(joined) >= 60:
                vol_corr[ch] = round(float(joined.corr().iloc[0, 1]), 3)

    _merge_results("drift", {
        "note": ("Domain stats are approximations from relevance-sorted "
                 "samples (first sub-query per channel), not a census."),
        "mean_daily_corpus_by_year": by_year,
        "per_channel_domains": domain_stats,
        "share_vs_corpus_corr": vol_corr,
    })


def main() -> None:
    modes = {"hit-rate": hit_rate, "placebo": placebo,
             "robustness": robustness, "precision": precision,
             "drift": drift}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(f"usage: python -m src.validate [{'|'.join(modes)}]")
    modes[sys.argv[1]]()


if __name__ == "__main__":
    main()
