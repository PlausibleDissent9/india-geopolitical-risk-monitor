"""
Receipts drill-down (practitioner layer item 2): for the latest published
day, reconstruct each channel's exact GDELT query, pull a relevance-sorted
sample of matched articles (mode=artlist), and sort them tier-first using
source_tiers.json. Publishes docs/data/receipts.json.

Not a historical archive: GDELT artlist is date-scoped and ad hoc (like
make_datapack's dossier), so only the latest published day is kept --
each daily run replaces it, and clicking into an older day is honestly
labeled "not available" rather than faked. Untiered domains (not yet in
source_tiers.json) sort after every registered tier and are shown as
"unranked", never assumed tier 3.

Run by CI daily, or manually: python -m src.receipts
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

CHANNELS = ["pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"]
MAX_ARTICLES_PER_QUERY = 150
MAX_ARTICLES_PUBLISHED = 75
UNRANKED = 5  # sorts after every registered tier (1-4); never assumed tier 3


def _tier_sort_key(article: dict[str, Any]) -> tuple[int, int]:
    """Credibility first, aptness second: within a tier, GDELT's own
    relevance order (capture position in the fetched pool) decides,
    never the alphabet (which buried apt stories until 2026-08-04)."""
    tier = article["tier"]
    return (tier if tier is not None else UNRANKED, article.get("_rel", 10**6))


def channel_receipts(
    channel: str, spec: dict[str, Any], day: date, tiers: dict[str, int],
) -> dict[str, Any]:
    """One channel's receipts for one day: exact query, tier-sorted matched
    articles, and the tier1-2 share (the spike-quality number). Tiers order
    presentation only; they never enter any score."""
    queries = fetch_gdelt.build_queries(spec["terms"], spec.get("anchor"))
    pool: dict[str, dict[str, Any]] = {}
    for q in queries:
        for a in fetch_gdelt.fetch_articles(
            q, day, day, maxrecords=MAX_ARTICLES_PER_QUERY
        ):
            # Scheme allowlist: with 'unsafe-inline' in the CSP, a
            # javascript: URL from crawled third-party data would
            # execute on click; only http(s) ever renders.
            if a["url"] and a["url"].startswith(("http://", "https://")):
                a["_rel"] = len(pool)  # GDELT relevance position
                pool.setdefault(a["url"], a)
    articles = list(pool.values())
    # Syndication dedup: identical headlines across mirror domains (the
    # datapacks show one ANI wire story on four domains) collapse to the
    # best-tiered instance, so depth buys breadth, not repetition.
    by_title: dict[str, dict[str, Any]] = {}
    for a in articles:
        a["tier"] = tiers.get(a["domain"])
        key = (a.get("title") or a["url"]).strip().lower()[:120]
        best = by_title.get(key)
        if best is None or (a["tier"] or UNRANKED) < (best["tier"] or UNRANKED):
            by_title[key] = a
    articles = list(by_title.values())
    articles.sort(key=_tier_sort_key)
    articles = articles[:MAX_ARTICLES_PUBLISHED]
    for a in articles:
        a.pop("_rel", None)
    tier12 = sum(1 for a in articles if a["tier"] in (1, 2))
    return {
        "label": spec["label"],
        "anchor": spec.get("anchor"),
        "terms": spec["terms"],
        "queries": queries,
        "n_retrieved": len(articles),
        "articles": articles,
        "spike_quality_tier12_share": (
            round(tier12 / len(articles), 3) if articles else None
        ),
    }


def _meta(partial: bool) -> dict[str, Any]:
    return {
        "what": (
            "Per-channel receipts for the latest published day: the "
            "exact GDELT query, a relevance-sorted sample of matched "
            "articles (mode=artlist), and each article's source tier "
            "(source_tiers.json; tiers order presentation and feed "
            "spike_quality_tier12_share only, never any score)."
        ),
        "caveat": (
            "This is a bounded relevance-sorted SAMPLE of retrievable "
            "articles, not the full set of documents the channel's "
            "score was computed over -- the underlying coverage count "
            "for an active day is typically much larger than what "
            "GDELT's artlist mode returns. Treat this as illustrative "
            "evidence, not a census."
        ),
        "partial": partial,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def main() -> None:
    """One channel's GDELT fetch can run long under rate-limit backoff, and
    a runner-level step timeout kills the whole process with no chance to
    write -- 2026-08-02: exactly this left the previous run's payload
    missing entirely, masked by continue-on-error reporting the step as
    "success". Each channel is now independent (a failure or a kill after
    it lands still keeps its receipts) and the payload is rewritten after
    every channel, so a mid-run kill leaves partial data (flagged
    _meta.partial) on disk instead of nothing."""
    latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
    day = date.fromisoformat(latest["date"])
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DATA / "receipts.json"
    channels: dict[str, Any] = {}
    for ch in CHANNELS:
        try:
            channels[ch] = channel_receipts(ch, dictionaries[ch], day, tiers)
        except Exception as e:  # noqa: BLE001 -- one bad channel must not lose the rest
            print(f"[receipts] {ch} failed, skipping: {e}")
            continue
        out_path.write_text(
            json.dumps(
                {"_meta": _meta(partial=len(channels) < len(CHANNELS)),
                 "date": day.isoformat(), "channels": channels},
                indent=1,
            ),
            encoding="utf-8",
        )
    print(f"[receipts] wrote docs/data/receipts.json for {day} "
          f"({len(channels)}/{len(CHANNELS)} channels)")


if __name__ == "__main__":
    main()
