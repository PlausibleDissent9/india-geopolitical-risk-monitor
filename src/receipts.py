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
MAX_ARTICLES_PER_QUERY = 20
MAX_ARTICLES_PUBLISHED = 25
UNRANKED = 5  # sorts after every registered tier (1-4); never assumed tier 3


def _tier_sort_key(article: dict[str, Any]) -> tuple[int, str]:
    tier = article["tier"]
    return (tier if tier is not None else UNRANKED, article["domain"])


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
            if a["url"]:
                pool.setdefault(a["url"], a)
    articles = list(pool.values())
    for a in articles:
        a["tier"] = tiers.get(a["domain"])
    articles.sort(key=_tier_sort_key)
    articles = articles[:MAX_ARTICLES_PUBLISHED]
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


def build(day: date) -> dict[str, Any]:
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]

    channels = {}
    for ch in CHANNELS:
        channels[ch] = channel_receipts(ch, dictionaries[ch], day, tiers)

    return {
        "_meta": {
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
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "date": day.isoformat(),
        "channels": channels,
    }


def main() -> None:
    latest = json.loads((SITE_DATA / "latest.json").read_text(encoding="utf-8"))
    day = date.fromisoformat(latest["date"])
    payload = build(day)
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "receipts.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8"
    )
    print(f"[receipts] wrote docs/data/receipts.json for {day}")


if __name__ == "__main__":
    main()
