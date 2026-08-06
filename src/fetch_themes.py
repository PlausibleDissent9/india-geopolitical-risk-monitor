"""
G4: narrative composition. What THEMES carried each channel's day --
GKG's V2Themes joined by URL onto the exact articles the registered
dictionaries matched (the tone lane's proven join, one more column).
No new selection: themes are an annotation, never a filter, and enter
no score. Industrializes what V6's term attribution does by hand:
where episode_terms says which registered PHRASES fired, this says
which of GDELT's coded narrative frames the matched coverage carried.

Fail-closed without GCP credentials; capped bytes per query.

  python -m src.fetch_themes            annotate latest cached day
  python -m src.fetch_themes 2026-08-05 specific day
Writes docs/data/episode_themes.json (trailing 30 days kept).
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DAYS = ROOT / "data" / "raw" / "receipt_days"
SITE_DATA = ROOT / "docs" / "data"

MAX_BYTES = 3 * 10**9
TOP_THEMES = 12
KEEP_DAYS = 30
# GDELT theme codes are screamy internals (TAX_FNCACT_...); the top-N
# published keep their raw code for auditability -- renaming them would
# be editorializing.


def _day_urls(day: str) -> dict[str, list[str]]:
    from src.fetch_tone import _day_urls as tone_day_urls
    return tone_day_urls(day)


def fetch_day_themes(day: str,
                     urls_by_group: dict[str, list[str]]) -> dict[str, Any]:
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(os.environ["GCP_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"],
                             credentials=creds)
    all_urls = sorted({u for urls in urls_by_group.values() for u in urls})
    if not all_urls:
        return {}
    cfg = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES,
        query_parameters=[
            bigquery.ArrayQueryParameter("urls", "STRING", all_urls),
            bigquery.ScalarQueryParameter("day", "TIMESTAMP",
                                          day + " 00:00:00"),
        ],
    )
    q = (
        "SELECT DocumentIdentifier AS url, V2Themes AS themes "
        "FROM `gdelt-bq.gdeltv2.gkg_partitioned` "
        "WHERE _PARTITIONTIME >= @day "
        "  AND _PARTITIONTIME < TIMESTAMP_ADD(@day, INTERVAL 1 DAY) "
        "  AND DocumentIdentifier IN UNNEST(@urls) "
        "  AND V2Themes != ''"
    )
    themes_by_url: dict[str, set[str]] = {}
    for r in client.query(q, job_config=cfg):
        themes_by_url[r["url"]] = {
            seg.split(",")[0] for seg in (r["themes"] or "").split(";")
            if seg and seg.split(",")[0]}

    out: dict[str, Any] = {}
    for group, urls in sorted(urls_by_group.items()):
        counts: Counter[str] = Counter()
        found = 0
        for u in set(urls):
            codes: set[str] | None = themes_by_url.get(u)
            if codes is None:
                continue
            found += 1
            counts.update(codes)
        if not found:
            continue
        out[group] = {
            "n_matched": len(set(urls)), "n_themed": found,
            "top_themes": [
                {"code": c, "share": round(n / found, 3)}
                for c, n in counts.most_common(TOP_THEMES)
            ],
        }
    return out


def main() -> None:
    if not (os.environ.get("GCP_SA_JSON") and os.environ.get("GCP_PROJECT_ID")):
        print("[themes] no GCP credentials; skipping (fail-closed, the "
              "narrative axis is simply absent)")
        return
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        cached = sorted(p.stem.replace("-extended", "")
                        for p in DAYS.glob("*.json"))
        if not cached:
            sys.exit("[themes] no receipt day caches")
        day = cached[-1]
    date.fromisoformat(day)
    urls = _day_urls(day)
    if not urls:
        sys.exit(f"[themes] no matched URLs cached for {day}")
    day_out = fetch_day_themes(day, urls)

    path = SITE_DATA / "episode_themes.json"
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8")).get("days", {})
    existing[day] = day_out
    kept = dict(sorted(existing.items())[-KEEP_DAYS:])
    payload = {
        "_meta": {
            "what": ("Narrative composition (G4): per channel per day, "
                     "the GKG theme codes carried by the MATCHED "
                     "articles -- the registered dictionaries choose "
                     "every article, BigQuery only reads its V2Themes; "
                     "an annotation, never a filter, entering no score. "
                     "share = fraction of themed matched articles "
                     "carrying the code; codes stay raw GDELT "
                     "identifiers for auditability. n_themed vs "
                     "n_matched discloses the join rate."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "days": kept,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[themes] wrote episode_themes.json day {day}: "
          f"{ {g: v['n_themed'] for g, v in day_out.items()} }")


if __name__ == "__main__":
    main()
