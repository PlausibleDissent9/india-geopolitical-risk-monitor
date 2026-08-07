"""
Receipts at construction depth: enumerate the day's evidence from the
same sampled ngrams corpus the day's scores are computed from.

The DOC API's artlist mode caps out near 38 articles/day/sub-query
(measured 2026-08-04, both sorts identical), so receipts built on it
could only ever show a sliver. But the score itself is computed by
src.fetch_ngrams over ~48 half-hourly minute-files whose toc records
carry every document's url and title -- meaning the articles behind the
number are already flowing through the pipeline. This module re-scans
that corpus for the published day and publishes, per channel, every
English article whose quadgrams matched a registered phrase (anchor
applied per document, exactly as the series matcher does).

What this buys, honestly stated:
  - The receipts are construction-identical: an article listed here is
    an article the day's estimator counted, matched by the same
    tokenizer, the same contiguous-subsequence test, the same anchor.
  - Depth is the corpus's true match count, not an API ceiling. The
    page can say "all N matches in the scored sample" and mean it.
  - No credentials, no rate limits: the files are public GCS objects,
    and this runs anywhere the heal already runs.

Fallback: if the day's minute-files are unavailable (feed gap), this
module delegates to src.receipts (artlist lane) so the payload is never
silently absent -- a bounded sample beats nothing, and _meta.method
says which lane produced the file.

Run by CI daily, or manually:
  python -m src.receipts_ngrams              # latest published day
  python -m src.receipts_ngrams 2026-08-05   # explicit day (debug)
"""
from __future__ import annotations

import gzip
import io
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import fetch_gdelt, receipts
from .fetch_ngrams import (
    _day_minute_files,
    _norm_tokens,
    _subseq,
    group_specs,
    prefetch_pairs,
    scoring_stamps,
)

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

# 150, not the artlist lane's 75: with the extended scan a loud channel
# has hundreds of genuine matches, and capping the page at 75 hid depth
# that exists (founder order 2026-08-06, "articles galore"). The payload
# stays a few hundred KB; n_pool_unique still tells the full count.
MAX_PUBLISHED = 150
UNRANKED = receipts.UNRANKED
CHANNELS = receipts.CHANNELS


def _domain(url: str) -> str:
    """Bare registrable-ish domain, matching artlist's 'domain' field
    (source_tiers.json is keyed on artlist domains, without www)."""
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


CORPUS_CACHE = ROOT / "data" / "raw" / "receipt_days"


def _cache_path(day: date, extended: bool) -> Path:
    suffix = "-extended" if extended else ""
    return CORPUS_CACHE / f"{day.isoformat()}{suffix}.json"


def _cache_load(day: date, extended: bool) -> dict[str, Any] | None:
    path = _cache_path(day, extended)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["india"] = set(raw["india"])
    raw["matched"] = {g: set(v) for g, v in raw["matched"].items()}
    raw["scored_stamps"] = set(raw.get("scored_stamps") or [])
    return raw


def _cache_save(day: date, corpus: dict[str, Any], extended: bool) -> None:
    CORPUS_CACHE.mkdir(parents=True, exist_ok=True)
    ser = dict(corpus)
    ser["india"] = sorted(corpus["india"])
    ser["matched"] = {g: sorted(v) for g, v in corpus["matched"].items()}
    ser["scored_stamps"] = sorted(corpus.get("scored_stamps") or [])
    _cache_path(day, extended).write_text(json.dumps(ser), encoding="utf-8")


def collect_corpus(day: date, specs: dict[str, dict],
                   extended: bool = False) -> dict[str, Any] | None:
    """One pass over the day's minute-files. Standard mode reads the
    same half-hourly sample the score used; extended mode (founder
    order 2026-08-06: "articles galore") reads EVERY existing file for
    the day (~5x the data) and records which stamps belong to the
    scoring sample, so each article can honestly say whether the
    estimator counted it or it merely exists in the day's corpus.
    Returns None if no files exist (feed gap -> caller falls back).
    Cached per day and mode (data/raw/receipt_days); delete the cache
    file to force a fresh scan."""
    cached = _cache_load(day, extended)
    if cached is not None:
        # A cache written for a different registered dictionary version
        # would silently misattribute matches; the group keys must agree.
        if set(cached["matched"]) == set(specs):
            print(f"[receipts-ngrams] corpus cache hit for {day}"
                  f"{' (extended)' if extended else ''}")
            return cached
        print("[receipts-ngrams] corpus cache stale (dictionary change); rescanning")
    if extended:
        stamps = _day_minute_files(day, samples=1440)
        scored = scoring_stamps(stamps, day)
    else:
        stamps = _day_minute_files(day)
        scored = set(stamps)  # the standard scan IS the scoring sample
    if not stamps:
        return None

    fragments = sorted({p[0] for s in specs.values() for p in s["phrases"]})
    trigger = re.compile("|".join(re.escape(f) for f in fragments + ["india"]))

    total_en = 0
    india: set[str] = set()
    matched: dict[str, set[str]] = {g: set() for g in specs}
    meta: dict[str, dict[str, str]] = {}  # doc key -> {url, title, date}

    for ts, toc_gz, ng_gz in prefetch_pairs(stamps):
        if not toc_gz or not ng_gz:
            continue
        toc_en: dict[str, dict[str, str]] = {}
        for line in gzip.decompress(toc_gz).decode("utf-8", "replace").splitlines():
            line = line.strip().rstrip(",")
            if not line or line in "[]":
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("lang") == "en":
                raw_date = re.sub(r"[^0-9]", "", str(rec.get("date") or ""))[:8]
                toc_en[str(rec.get("ID"))] = {
                    "url": str(rec.get("url") or ""),
                    "title": str(rec.get("title") or ""),
                    "date": raw_date or f"{day:%Y%m%d}",
                }
        total_en += len(toc_en)

        with gzip.open(io.BytesIO(ng_gz), "rt", encoding="utf-8",
                       errors="replace") as fh:
            for raw in fh:
                low = raw.lower()
                if not trigger.search(low):
                    continue
                parts = raw.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                docid, quad = parts[0], parts[1]
                rec2 = toc_en.get(docid)
                if rec2 is None:
                    continue
                key = f"{ts}:{docid}"
                tokens = _norm_tokens(quad)
                if "india" in tokens:
                    india.add(key)
                for g, s in specs.items():
                    if key in matched[g]:
                        continue
                    for ph in s["phrases"]:
                        if len(ph) <= len(tokens) and _subseq(ph, tokens):
                            matched[g].add(key)
                            meta.setdefault(key, rec2)
                            break

    if total_en == 0:
        return None
    corpus = {"n_docs_sampled": total_en, "n_samples": len(stamps),
              "extended": extended, "scored_stamps": scored,
              "india": india, "matched": matched, "meta": meta}
    _cache_save(day, corpus, extended)
    return corpus


def channel_doc_keys(
    channel: str, specs: dict[str, dict], corpus: dict[str, Any],
) -> set[str]:
    """Union of the channel's sub-query matches, anchor applied per
    document -- the same set arithmetic compute_day scores with."""
    keys: set[str] = set()
    anchored = False
    for g, s in specs.items():
        if s["channel"] != channel:
            continue
        keys |= corpus["matched"][g]
        anchored = anchored or (s["anchor"] == "india")
    return keys & corpus["india"] if anchored else keys


def assemble_channel(
    channel: str, spec: dict[str, Any], doc_keys: set[str],
    corpus: dict[str, Any], tiers: dict[str, int],
    supplement: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure assembly: corpus matches -> the published channel block, in
    the same schema (and with the same honesty fields) as the artlist
    lane, so docs/receipts.html renders either lane unchanged.

    supplement: artlist-lane articles (receipts.channel_receipts output)
    merged in AFTER the corpus pool, deduped by URL, lane-labeled. The
    sample sees the same match RATE as the full day but a smaller
    absolute count, so on thin channels the tier-1 wire original often
    sits outside the sampled files while a syndicated copy sits inside;
    the supplement restores the originals without diluting the corpus
    lane's construction-identity claim -- every article says which lane
    produced it."""
    norm_phrases = [" " + re.sub(r"[^a-z0-9 ]+", " ", t.strip('"').lower()).strip() + " "
                    for t in spec["terms"]]
    pool: dict[str, dict[str, Any]] = {}
    for i, key in enumerate(sorted(doc_keys)):
        rec = corpus["meta"].get(key)
        if rec is None:
            continue
        url = rec["url"]
        # Scheme allowlist: with 'unsafe-inline' in the CSP, a
        # javascript: URL from crawled third-party data would execute
        # on click; only http(s) ever renders.
        if not url.startswith(("http://", "https://")):
            continue
        title_norm = " " + re.sub(r"[^a-z0-9 ]+", " ", rec["title"].lower()).strip() + " "
        # "corpus" = the estimator counted this article; "corpus-extended"
        # = it exists in the day's full corpus but fell outside the
        # scoring sample. The distinction is the identity claim.
        scored = corpus.get("scored_stamps") or set()
        in_scored = key.split(":", 1)[0] in scored if scored else True
        pool.setdefault(url, {
            "title": rec["title"],
            "domain": _domain(url),
            "date": rec["date"],
            "url": url,
            "lane": "corpus" if in_scored else "corpus-extended",
            "_rel": i,
            "_title_hit": any(p in title_norm for p in norm_phrases),
        })
    n_matched = sum(1 for a in pool.values() if a["lane"] == "corpus")
    n_extended = sum(1 for a in pool.values() if a["lane"] == "corpus-extended")
    n_supplement = 0
    for i, a in enumerate(supplement or []):
        url = a.get("url") or ""
        if not url.startswith(("http://", "https://")) or url in pool:
            continue
        pool[url] = {
            "title": a.get("title") or "",
            "domain": a.get("domain") or _domain(url),
            "date": a.get("date") or "",
            "url": url,
            "lane": "artlist",
            "_rel": 10 ** 5 + i,  # after every corpus article at equal tier
            "_title_hit": a.get("match") == "headline",
        }
        n_supplement += 1
    articles = list(pool.values())
    # The syndication multiplier, which this function has always
    # computed and always discarded (referee finding, 2026-08-07). The
    # index counts ARTICLES, so a single wire story republished by two
    # hundred outlets moves a channel exactly as much as two hundred
    # newsrooms independently deciding a thing mattered. Those are not
    # the same event and the index cannot tell them apart.
    #
    # `pool` is keyed by URL, so its size is distinct articles; the
    # title-collapse below turns that into distinct STORIES. The ratio
    # is a direct measurement of republication inside the index's own
    # retrieval path -- not an estimate from a side sample.
    n_pool_urls = len(articles)
    n_pool_domains = len({a["domain"] for a in articles})
    by_title: dict[str, dict[str, Any]] = {}
    for a in articles:
        a["tier"] = tiers.get(a["domain"])
        dedupe_key = (a.get("title") or a["url"]).strip().lower()[:120]
        best = by_title.get(dedupe_key)
        if best is None or (a["tier"] or UNRANKED) < (best["tier"] or UNRANKED):
            by_title[dedupe_key] = a
    articles = list(by_title.values())
    n_pool_unique = len(articles)
    articles.sort(key=receipts._tier_sort_key)
    articles = articles[:MAX_PUBLISHED]
    for a in articles:
        a["match"] = "headline" if a.pop("_title_hit", False) else "full-text"
        a.pop("_rel", None)
    tier12 = sum(1 for a in articles if a["tier"] in (1, 2))
    return {
        "label": spec["label"],
        "anchor": spec.get("anchor"),
        "terms": spec["terms"],
        "queries": fetch_gdelt.build_queries(spec["terms"], spec.get("anchor")),
        "n_matched_in_corpus": n_matched,
        "n_matched_extended": n_extended,
        "n_artlist_supplement": n_supplement,
        "n_retrieved": len(articles),
        "n_pool_unique": n_pool_unique,
        "n_pool_urls": n_pool_urls,
        "n_pool_domains": n_pool_domains,
        # Articles per distinct story. 1.0 = every article is its own
        # story; 3.0 = the average story appears three times. Rises when
        # a channel's volume is wire copy rather than newsrooms.
        "syndication_multiplier": (
            round(n_pool_urls / n_pool_unique, 3) if n_pool_unique else None
        ),
        "pool_exhausted": n_pool_unique <= MAX_PUBLISHED,
        "articles": articles,
        "spike_quality_tier12_share": (
            round(tier12 / len(articles), 3) if articles else None
        ),
    }


def _meta(corpus: dict[str, Any]) -> dict[str, Any]:
    return {
        "what": (
            "Per-channel receipts for the latest published day, drawn "
            "from the same sampled ngrams corpus the day's scores are "
            "computed from: every English article in the sample whose "
            "text matched a registered channel phrase (channel anchor "
            "applied per document, identically to the series matcher), "
            "tier-sorted using source_tiers.json."
        ),
        "caveat": (
            "Drawn from {n} minute-files covering {d:,} English "
            "articles. An article labeled 'in scored sample' is one "
            "the day's estimator actually counted; 'in day's corpus' "
            "means it exists in the full day's monitored coverage but "
            "fell outside the half-hourly scoring sample; 'retrieved' "
            "comes from GDELT's bounded relevance search and restores "
            "wire originals whose syndicated copies the corpus caught. "
            "Tiers order presentation and feed the tier 1-2 share "
            "only; they never enter any score."
        ).format(n=corpus["n_samples"], d=corpus["n_docs_sampled"]),
        "method": ("ngrams-corpus-extended+artlist"
                   if corpus.get("extended") else "ngrams-corpus+artlist"),
        "n_docs_sampled": corpus["n_docs_sampled"],
        "n_samples": corpus["n_samples"],
        "partial": False,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--extended"]
    extended = "--extended" in sys.argv[1:]
    if len(args) == 1:
        day = date.fromisoformat(args[0])
    else:
        latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
        day = date.fromisoformat(latest["date"])
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    specs = group_specs()
    print(f"[receipts-ngrams] scanning corpus for {day}"
          f"{' (extended: every file in the day)' if extended else ''}")
    corpus = collect_corpus(day, specs, extended=extended)
    if corpus is None:
        print("[receipts-ngrams] no corpus files for the day; "
              "falling back to the artlist lane")
        receipts.main()
        return

    # Same-day artlist carry-forward: a supplement retrieved earlier
    # today (say, by the VPS's clean address) is not forfeited to a
    # later rerun's rate limit -- the retrieval already happened for
    # this same measured day. Only the artlist lane carries forward;
    # corpus lanes always rebuild from the scan.
    prior_artlist: dict[str, list[dict[str, Any]]] = {}
    prior_path = SITE_DATA / "receipts.json"
    if prior_path.exists():
        try:
            prior = json.loads(prior_path.read_text(encoding="utf-8"))
            if prior.get("date") == day.isoformat():
                for pch, blk in (prior.get("channels") or {}).items():
                    arts = [a for a in blk.get("articles", [])
                            if a.get("lane") == "artlist"]
                    if arts:
                        prior_artlist[pch] = arts
        except (json.JSONDecodeError, OSError):
            pass

    channels: dict[str, Any] = {}
    for ch in CHANNELS:
        keys = channel_doc_keys(ch, specs, corpus)
        # Artlist supplement: restores tier-1/2 wire originals the sample
        # missed. A failed fetch never loses the corpus lane.
        supplement: list[dict[str, Any]] = []
        try:
            supplement = receipts.channel_receipts(
                ch, dictionaries[ch], day, tiers)["articles"]
        except Exception as e:  # noqa: BLE001 -- supplement is optional
            print(f"[receipts-ngrams] {ch} artlist supplement failed: {e}")
            if ch in prior_artlist:
                supplement = prior_artlist[ch]
                print(f"[receipts-ngrams] {ch}: carrying forward "
                      f"{len(supplement)} retrieved articles from today's "
                      "earlier payload")
        channels[ch] = assemble_channel(
            ch, dictionaries[ch], keys, corpus, tiers, supplement)
        print(f"[receipts-ngrams] {ch}: {channels[ch]['n_matched_in_corpus']} "
              f"scored + {channels[ch]['n_matched_extended']} extended + "
              f"{channels[ch]['n_artlist_supplement']} artlist, "
              f"{channels[ch]['n_retrieved']} published")

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "receipts.json").write_text(
        json.dumps({"_meta": _meta(corpus), "date": day.isoformat(),
                    "channels": channels}, indent=1),
        encoding="utf-8",
    )
    print(f"[receipts-ngrams] wrote docs/data/receipts.json for {day} "
          f"({len(channels)}/{len(CHANNELS)} channels, "
          f"{corpus['n_docs_sampled']:,} docs sampled)")


if __name__ == "__main__":
    main()
