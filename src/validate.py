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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import build_index, fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
RAW_DIR = ROOT / "data" / "raw"
BACKFILL_START = date(2022, 1, 1)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _previous_drift_domain_stats() -> dict:
    """The domain samples the site already publishes, so a rerun whose
    rate-limit gaps land on different channel-years cannot delete them."""
    out = SITE_DATA / "validation.json"
    if not out.exists():
        return {}
    existing = _load_json(out)
    stats = existing.get("drift", {}).get("per_channel_domains", {})
    return stats if isinstance(stats, dict) else {}


def _merge_results(key: str, payload) -> None:
    out = SITE_DATA / "validation.json"
    existing = _load_json(out) if out.exists() else {}
    existing[key] = payload
    # validation.json is assembled by merging one block at a time, so it
    # never had a top-level _meta and therefore carried no date. It is
    # the credibility payload -- hit rate, placebo, robustness, drift --
    # and until 2026-08-07 nothing could tell whether the numbers on the
    # validation page were computed this morning or six months ago.
    # Stamped on every merge; the last block to land dates the file.
    existing["_meta"] = {
        "generated": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Assembled block by block; this stamp is the time of "
                 "the most recent block written, not of every block."),
        "blocks_present": sorted(k for k in existing if k != "_meta"),
    }
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


def robustness_series() -> None:
    """MI2 (founder QA 2026-08-05): a bare correlation is illegible to a
    reader; publish the overlay series behind each robustness number so
    the validation page can SHOW primary vs variant instead of asserting
    a coefficient. Offline: reads the cached variant volume stores the
    robustness mode already fetched. Weekly means keep the payload small
    and the chart honest (daily wiggle is not the construct question).
    The variants exist from 2022-01-01, so the overlap window is
    disclosed rather than silently extended."""
    primary_vol = pd.read_csv(RAW_DIR / "gdelt_volume.csv",
                              parse_dates=["date"]).set_index("date")
    series = {"primary": build_index.build_scores(primary_vol)}
    for variant in ("narrow", "broad"):
        store = RAW_DIR / f"gdelt_volume_{variant}.csv"
        if not store.exists():
            sys.exit(f"no {store.name} -- run 'validate robustness' first")
        vol = pd.read_csv(store, parse_dates=["date"]).set_index("date")
        series[variant] = build_index.build_scores(vol)

    start = max(s.index.min() for s in series.values())
    end = min(s.index.max() for s in series.values())
    weekly = {k: s.loc[start:end].resample("W-MON").mean()
              for k, s in series.items()}
    weeks = [ts.date().isoformat() for ts in weekly["primary"].index]

    channels: dict = {}
    for ch in list(primary_vol.columns) + ["composite"]:
        block = {}
        for k, s in weekly.items():
            if ch in s.columns:
                block[k] = [None if pd.isna(x) else round(float(x), 2)
                            for x in s[ch].reindex(weekly["primary"].index)]
        channels[ch] = block
    payload = {
        "_meta": {
            "what": ("Weekly mean percentile scores of the primary index "
                     "and its narrow/broad dictionary variants, over the "
                     "window where all three exist. The overlay behind "
                     "validation.json's robustness correlations."),
            "window": [start.date().isoformat(), end.date().isoformat()],
            "generated": date.today().isoformat(),
        },
        "weeks": weeks,
        "channels": channels,
    }
    out = SITE_DATA / "robustness_series.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[validate] wrote {out.name}: {len(weeks)} weeks, "
          f"{len(channels)} channels, {out.stat().st_size // 1024} KB")


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
    try:
        raw = fetch_gdelt.fetch_corpus_norm(norm_q, BACKFILL_START, today)
    except RuntimeError as exc:
        # The artlist sampling below fails soft per-year because it is a
        # bonus diagnostic. THIS fetch is the promised denominator, so
        # failing is correct -- but three weekly lane runs (drift #14-#16,
        # 2026-08-07..09) died here as a bare exit 1 and were diagnosed by
        # reproduction rather than by their own logs. The same command
        # succeeded from a residential IP while CI failed at ~12 minutes:
        # GDELT throttles shared runner IPs far harder, and the retry
        # ladder exhausts. Name the site, name the cause, use a dedicated
        # exit code the workflow can annotate.
        print(f"[validate] drift ABORTED at the corpus-norm fetch "
              f"(timelinevolraw): {exc}. Nothing was published. On a GitHub "
              "runner a persistent DOC-API 429 is the usual cause; the "
              "artlist sampling never ran, so its soft-fail is not the "
              "story here.")
        raise SystemExit(4) from exc
    norm = raw["norm"]
    norm.index = pd.to_datetime(norm.index)
    by_year = {
        str(y): int(v) for y, v in
        norm.groupby(norm.index.year).mean().round().items()
    }

    # The two statistics the validation page PROMISES (corpus size by
    # year; share-vs-corpus correlation) need no artlist calls at all.
    # The per-domain concentration numbers are bonus diagnostics served
    # by GDELT's heavily rate-limited artlist mode -- 2026-08-06: two
    # full drift runs died on artlist 429s AFTER the promised stats
    # were computable, which is the wrong thing to be hostage to. Each
    # year's sample now fails soft; whatever resolves publishes, and
    # the payload notes any gap.
    # Which channel-years 429 varies run to run, so a wholesale replace
    # DELETES previously published samples whenever this run's gaps land
    # on years an earlier run measured. Found 2026-08-10: a local rerun
    # would have removed four published channel-years (pakistan/2022,
    # china/2025, gulf/2025, shipping/2025) that its own 429s missed.
    # Same rule as the ngram heal: a rerun appends and refreshes, it
    # never un-publishes. Carried entries keep their original sample
    # date so a fresh timestamp cannot silently re-date an old sample.
    previous = _previous_drift_domain_stats()
    domain_stats: dict = {}
    domain_gaps = 0
    domain_carried = 0
    for ch, spec in channels.items():
        q = fetch_gdelt.build_queries(spec["terms"], spec.get("anchor"))[0]
        per_year: dict = {}
        for y in sorted({ts.year for ts in norm.index}):
            try:
                arts = fetch_gdelt.fetch_articles(
                    q, date(y, 1, 1), min(date(y, 12, 31), today),
                    maxrecords=100,
                )
            except RuntimeError as e:
                kept = previous.get(ch, {}).get(str(y))
                if kept is not None:
                    per_year[str(y)] = {**kept, "sampled_on":
                                        kept.get("sampled_on", "before 2026-08-10")}
                    domain_carried += 1
                    print(f"[validate] drift domains {ch}/{y} unavailable "
                          f"({str(e)[:80]}); carrying the published sample "
                          "forward unchanged")
                else:
                    domain_gaps += 1
                    print(f"[validate] drift domains {ch}/{y} unavailable "
                          f"({str(e)[:80]}); continuing")
                continue
            domains = pd.Series([a["domain"] for a in arts if a["domain"]])
            if domains.empty:
                continue
            shares = domains.value_counts(normalize=True)
            per_year[str(y)] = {
                "n_articles_sampled": int(len(domains)),
                "n_distinct_domains": int(domains.nunique()),
                "herfindahl_top10": round(float((shares.head(10) ** 2).sum()), 4),
                "sampled_on": today.isoformat(),
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

    note = ("Domain stats are approximations from relevance-sorted "
            "samples (first sub-query per channel), not a census. Each "
            "year entry carries sampled_on: entries this run could not "
            "refresh keep their published values and dates rather than "
            "being deleted by a rate limit.")
    if domain_carried:
        note += (f" {domain_carried} channel-year samples carried forward "
                 "unchanged from the published payload this run.")
    if domain_gaps:
        note += (f" {domain_gaps} channel-year domain samples were "
                 "unavailable at computation time (source rate limits), "
                 "have no published predecessor, and are omitted rather "
                 "than guessed.")
    _merge_results("drift", {
        "note": note,
        "mean_daily_corpus_by_year": by_year,
        "per_channel_domains": domain_stats,
        "share_vs_corpus_corr": vol_corr,
    })


def main() -> None:
    modes = {"hit-rate": hit_rate, "placebo": placebo,
             "robustness": robustness, "robustness-series": robustness_series,
             "precision": precision, "drift": drift}
    if len(sys.argv) != 2 or sys.argv[1] not in modes:
        sys.exit(f"usage: python -m src.validate [{'|'.join(modes)}]")
    modes[sys.argv[1]]()


if __name__ == "__main__":
    main()
