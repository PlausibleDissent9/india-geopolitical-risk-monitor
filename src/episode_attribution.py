"""
V6 term-level episode attribution, the honest version.

"Which registered phrases drove this spike?" is answerable without a
single extra fetch for any day that has a committed corpus day-cache
(data/raw/receipt_days/): every matched article's title is in the
cache, so counting which registered phrases appear in matched HEADLINES
per channel-day gives a term-attribution signal that is (a) derived
from the same corpus the score came from and (b) reproducible from the
repo alone. Limitation, stated: headline attribution undercounts
phrases that live in body text; the payload says "headline share",
never "share of matches". Days before the first cache carry no
attribution -- the record starts 2026-08-05 and deepens daily; a
historical backfill would need per-term refetches and is a registered
decision, not a default.

  python -m src.episode_attribution   writes docs/data/episode_terms.json
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import receipts_ngrams
from .fetch_ngrams import group_specs

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
CACHE_DIR = ROOT / "data" / "raw" / "receipt_days"


def _norm(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9 ]+", " ", text.lower()).strip() + " "


def day_term_hits(day: date, extended: bool,
                  dictionaries: dict, specs: dict) -> dict[str, Any] | None:
    corpus = receipts_ngrams._cache_load(day, extended)
    if corpus is None or set(corpus["matched"]) != set(specs):
        return None
    out: dict[str, Any] = {}
    for ch, spec in dictionaries.items():
        if ch.startswith("_"):
            continue
        keys = receipts_ngrams.channel_doc_keys(ch, specs, corpus)
        titles = [_norm(corpus["meta"][k]["title"])
                  for k in keys if k in corpus["meta"]]
        terms = {}
        for t in spec["terms"]:
            phrase = _norm(t.strip('"')).strip()
            n = sum(1 for title in titles if f" {phrase} " in title)
            if n:
                terms[t.strip('"')] = n
        out[ch] = {"n_matched_titles": len(titles), "term_headline_hits": terms}
    return out


def main() -> None:
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)
    specs = group_specs()

    seen: dict[str, bool] = {}
    for p in CACHE_DIR.glob("*.json"):
        stem = p.stem
        extended = stem.endswith("-extended")
        d = stem[:-9] if extended else stem
        seen[d] = seen.get(d, False) or extended

    days: dict[str, Any] = {}
    for day_s in sorted(seen):
        try:
            day = date.fromisoformat(day_s)
        except ValueError:
            continue
        hits = day_term_hits(day, seen[day_s], dictionaries, specs)
        if hits is not None:
            days[day_s] = hits

    payload = {
        "_meta": {
            "what": ("Term-level attribution per channel-day: how many "
                     "matched-article HEADLINES in the day's corpus cache "
                     "contain each registered phrase. Derived from the "
                     "same corpus the scores come from; reproducible from "
                     "the repo alone. Headline attribution undercounts "
                     "body-text phrases and the record starts at the "
                     "first committed cache day -- earlier episodes carry "
                     "no attribution rather than a refetched guess."),
            "first_day": min(days) if days else None,
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "days": days,
    }
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    out = SITE_DATA / "episode_terms.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[episode-terms] wrote {out.name}: {len(days)} day(s)")


if __name__ == "__main__":
    main()
