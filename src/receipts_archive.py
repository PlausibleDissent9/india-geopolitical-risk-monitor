"""
Rolling receipts archive (founder requirement 2026-08-06: minimum 100
visible articles per channel per day, never stagnant).

A single day cannot honestly guarantee 100 articles: on a dead channel
day, fewer than 100 matching articles exist anywhere. The archive is
the honest route to guaranteed depth: today's receipts stay the
primary evidence (receipts.json, unchanged), and this module publishes
the trailing week from the same committed corpus day-caches
(data/raw/receipt_days/), every article dated, so a channel page
always carries a week of enumerable evidence -- typically several
hundred articles -- without one fabricated or padded row.

Construction per day and channel is identical to receipts_ngrams
assembly (same matcher provenance, same tier sort, same syndication
dedup, same lane labels), capped at ARCHIVE_PER_DAY per channel-day to
keep the payload phone-sized. The caches are committed by the daily
lanes, so the archive deepens automatically each day and never goes
stale while the lanes run.

  python -m src.receipts_archive     writes docs/data/receipts_archive.json
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import receipts_ngrams
from .fetch_ngrams import group_specs

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
CACHE_DIR = ROOT / "data" / "raw" / "receipt_days"

ARCHIVE_DAYS = 7
ARCHIVE_PER_DAY = 40  # per channel-day; today's full list lives in receipts.json


def _cache_days() -> list[tuple[date, bool]]:
    """(day, extended) pairs available, newest first, preferring the
    extended cache when both exist for a day."""
    seen: dict[str, bool] = {}
    for p in CACHE_DIR.glob("*.json"):
        stem = p.stem
        extended = stem.endswith("-extended")
        day = stem[:-9] if extended else stem
        seen[day] = seen.get(day, False) or extended
    out = []
    for day_s in sorted(seen, reverse=True)[:ARCHIVE_DAYS]:
        try:
            out.append((date.fromisoformat(day_s), seen[day_s]))
        except ValueError:
            continue
    return out


def build() -> dict[str, Any]:
    specs = group_specs()
    with open(ROOT / "source_tiers.json", encoding="utf-8") as f:
        tiers: dict[str, int] = json.load(f)["tiers"]
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)

    days_used: list[str] = []
    channels: dict[str, dict[str, Any]] = {ch: {"days": {}, "total_articles": 0}
                                           for ch in receipts_ngrams.CHANNELS}
    for day, extended in _cache_days():
        corpus = receipts_ngrams._cache_load(day, extended)
        if corpus is None or set(corpus["matched"]) != set(specs):
            continue  # dictionary-version mismatch: never misattribute
        days_used.append(day.isoformat())
        for ch in receipts_ngrams.CHANNELS:
            keys = receipts_ngrams.channel_doc_keys(ch, specs, corpus)
            block = receipts_ngrams.assemble_channel(
                ch, dictionaries[ch], keys, corpus, tiers)
            arts = block["articles"][:ARCHIVE_PER_DAY]
            channels[ch]["days"][day.isoformat()] = {
                "n_matched": (block["n_matched_in_corpus"]
                              + block["n_matched_extended"]),
                "articles": arts,
            }
            channels[ch]["total_articles"] += len(arts)
    return {
        "_meta": {
            "what": ("Trailing-week receipts archive: per channel and day, "
                     "the matched articles from that day's committed corpus "
                     "cache, assembled identically to receipts.json (same "
                     "matcher provenance, tier sort, syndication dedup, "
                     "lane labels), capped per day. Today's full list lives "
                     "in receipts.json; this file guarantees a week of "
                     "enumerable, dated evidence per channel."),
            "days": sorted(days_used, reverse=True),
            "per_day_cap": ARCHIVE_PER_DAY,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "channels": channels,
    }


def main() -> None:
    payload = build()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = SITE_DATA / "receipts_archive.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    totals = {ch: c["total_articles"] for ch, c in payload["channels"].items()}
    print(f"[receipts-archive] wrote {out.name}: days "
          f"{payload['_meta']['days']}, totals {totals}")


if __name__ == "__main__":
    main()
