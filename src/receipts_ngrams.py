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
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import fetch_gdelt, receipts
from .fetch_ngrams import (
    BASE,
    HEADERS,
    _day_minute_files,
    _fetch,
    _norm_tokens,
    _subseq,
    group_specs,
)

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

MAX_PUBLISHED = receipts.MAX_ARTICLES_PUBLISHED
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


def collect_corpus(day: date, specs: dict[str, dict]) -> dict[str, Any] | None:
    """One pass over the day's sampled minute-files. Returns matched
    document metadata per sub-query group plus corpus totals, or None if
    no files exist for the day (feed gap -> caller falls back)."""
    stamps = _day_minute_files(day)
    if not stamps:
        return None

    fragments = sorted({p[0] for s in specs.values() for p in s["phrases"]})
    trigger = re.compile("|".join(re.escape(f) for f in fragments + ["india"]))

    total_en = 0
    india: set[str] = set()
    matched: dict[str, set[str]] = {g: set() for g in specs}
    meta: dict[str, dict[str, str]] = {}  # doc key -> {url, title, date}

    for ts in stamps:
        toc_gz = _fetch(f"{BASE}{ts}.toc.json.gz")
        ng_gz = _fetch(f"{BASE}{ts}.ngrams.txt.gz")
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
        time.sleep(0.2)

    if total_en == 0:
        return None
    return {"n_docs_sampled": total_en, "n_samples": len(stamps),
            "india": india, "matched": matched, "meta": meta}


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
) -> dict[str, Any]:
    """Pure assembly: corpus matches -> the published channel block, in
    the same schema (and with the same honesty fields) as the artlist
    lane, so docs/receipts.html renders either lane unchanged."""
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
        pool.setdefault(url, {
            "title": rec["title"],
            "domain": _domain(url),
            "date": rec["date"],
            "url": url,
            "_rel": i,
            "_title_hit": any(p in title_norm for p in norm_phrases),
        })
    articles = list(pool.values())
    n_matched = len(articles)
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
        "n_retrieved": len(articles),
        "n_pool_unique": n_pool_unique,
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
            "The corpus is a stratified sample of the day's monitored "
            "English web coverage ({n} half-hourly files, {d:,} "
            "articles), so match counts are sample counts, not a "
            "census of everything GDELT saw that day. An article "
            "listed here is one the day's estimator actually counted. "
            "Tiers order presentation and feed the tier 1-2 share "
            "only; they never enter any score."
        ).format(n=corpus["n_samples"], d=corpus["n_docs_sampled"]),
        "method": "ngrams-corpus",
        "n_docs_sampled": corpus["n_docs_sampled"],
        "n_samples": corpus["n_samples"],
        "partial": False,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    if len(sys.argv) == 2:
        day = date.fromisoformat(sys.argv[1])
    else:
        latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
        day = date.fromisoformat(latest["date"])
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    specs = group_specs()
    print(f"[receipts-ngrams] scanning corpus for {day}")
    corpus = collect_corpus(day, specs)
    if corpus is None:
        print("[receipts-ngrams] no corpus files for the day; "
              "falling back to the artlist lane")
        receipts.main()
        return

    channels: dict[str, Any] = {}
    for ch in CHANNELS:
        keys = channel_doc_keys(ch, specs, corpus)
        channels[ch] = assemble_channel(ch, dictionaries[ch], keys, corpus, tiers)
        print(f"[receipts-ngrams] {ch}: {channels[ch]['n_matched_in_corpus']} "
              f"matched, {channels[ch]['n_retrieved']} published")

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
