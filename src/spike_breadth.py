"""
G3: spike breadth -- how many distinct sources carry a channel's story.

A spike carried by 40 outlets is a different object from the same
match count produced by one wire story and its syndicated copies.
This module counts DISTINCT DOMAINS among each channel's matched
articles per day, straight from the committed receipt day-caches
(extended preferred: deeper census, same construction). No fetching,
no new selection -- the registered dictionaries chose every article
counted here.

Published measures, all descriptive:
  - n_domains: distinct domains among the day's matched articles;
  - top_domain_share: the largest single domain's share of matches
    (1.0 = a one-outlet story);
  - breadth enters no score. It is evidence about narrative structure,
    beside spike-quality, never inside any number.

  python -m src.spike_breadth      writes docs/data/spike_breadth.json
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DAYS = ROOT / "data" / "raw" / "receipt_days"
SITE_DATA = ROOT / "docs" / "data"


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def day_breadth(cache: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per CHANNEL, using the identical union-plus-anchor arithmetic
    the receipts assembly (and the day's estimator) applies -- not the
    raw per-sub-query groups the cache stores."""
    from src import receipts_ngrams

    specs = receipts_ngrams.group_specs()
    # The cache stores sets serialized as lists; channel_doc_keys does
    # set arithmetic against corpus["india"].
    corpus = {
        "matched": {g: set(keys) for g, keys in
                    (cache.get("matched") or {}).items()},
        "india": set(cache.get("india") or []),
    }
    meta = cache.get("meta") or {}
    out: dict[str, dict[str, Any]] = {}
    for ch in receipts_ngrams.CHANNELS:
        keys = receipts_ngrams.channel_doc_keys(ch, specs, corpus)
        domains = Counter(
            _domain(meta[k]["url"]) for k in keys
            if k in meta and meta[k].get("url"))
        domains.pop("", None)
        total = sum(domains.values())
        if not total:
            continue
        top, top_n = domains.most_common(1)[0]
        out[ch] = {
            "n_matched": total,
            "n_domains": len(domains),
            "top_domain": top,
            "top_domain_share": round(top_n / total, 3),
        }
    return out


def main() -> None:
    days: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    # Extended caches first so a day with both uses the deeper census.
    for path in sorted(DAYS.glob("*-extended.json")) + sorted(
            p for p in DAYS.glob("*.json") if "-extended" not in p.stem):
        day = path.stem.replace("-extended", "")
        if day in seen:
            continue
        seen.add(day)
        cache = json.loads(path.read_text(encoding="utf-8"))
        breadth = day_breadth(cache)
        if breadth:
            days[day] = breadth
    if not days:
        raise SystemExit("[breadth] no day caches; nothing to measure")
    payload = {
        "_meta": {
            "what": ("Spike breadth: distinct source domains among each "
                     "channel's matched articles per day, from the same "
                     "committed day-caches the receipts build from -- "
                     "the registered dictionaries chose every article "
                     "counted. top_domain_share near 1.0 means a "
                     "one-outlet story; many domains at low top-share "
                     "means a broad-based narrative. Descriptive "
                     "context: breadth enters no score."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "days": dict(sorted(days.items())),
    }
    (SITE_DATA / "spike_breadth.json").write_text(json.dumps(payload),
                                                  encoding="utf-8")
    for day, chans in sorted(days.items()):
        line = ", ".join(f"{ch} {v['n_domains']}d/{v['n_matched']}m"
                         for ch, v in sorted(chans.items()))
        print(f"[breadth] {day}: {line}")


if __name__ == "__main__":
    main()
