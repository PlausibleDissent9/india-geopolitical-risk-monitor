"""
G1: tone as a second axis, construction-identical by design.

The G-track rule says every layer is a registered measurement
addition. This lane sidesteps the hardest registration entirely: it
introduces NO new article selection. The day's matched articles --
chosen by the registered phrase dictionaries, cached in
data/raw/receipt_days/ -- are annotated with GDELT GKG's V2Tone by
joining on the article URL in BigQuery. Same articles the estimator
counted; tone is an annotation, not a filter.

Honesty constraints:
  - Context axis only. Tone never enters any score, any percentile,
    or the composite (a founder-signed memo is the only thing that
    could ever change that, per the G-track registration).
  - Fail-closed: without GCP_SA_JSON / GCP_PROJECT_ID in the
    environment this module prints a skip line and writes nothing.
  - Every query is partition-scoped with maximum_bytes_billed capped;
    a query that would scan more dies rather than spends.
  - Coverage is disclosed per day: n_matched vs n_tone_found (GKG
    does not carry every URL; the join rate publishes).

  python -m src.fetch_tone             annotate latest cached day
  python -m src.fetch_tone 2026-08-05  specific day
Writes/updates data/raw/tone_daily.csv and docs/data/tone.json.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DAYS = RAW / "receipt_days"
STORE = RAW / "tone_daily.csv"
SITE_DATA = ROOT / "docs" / "data"

MAX_BYTES = 3 * 10**9  # per-query cap; the cap is the budget discipline
PUBLISH_DAYS = 90


def _day_urls(day: str) -> dict[str, list[str]]:
    """Per-channel matched URLs from the committed day cache (extended
    preferred -- deeper census, same construction)."""
    for suffix in ("-extended", ""):
        path = DAYS / f"{day}{suffix}.json"
        if path.exists():
            cache = json.loads(path.read_text(encoding="utf-8"))
            meta = cache.get("meta") or {}
            out: dict[str, list[str]] = {}
            for group, keys in (cache.get("matched") or {}).items():
                urls = [meta[k]["url"] for k in keys if k in meta]
                out.setdefault(group, []).extend(urls)
            return out
    return {}


def fetch_day_tone(day: str, urls_by_group: dict[str, list[str]]) -> list[dict]:
    """One partition-scoped query joining V2Tone by DocumentIdentifier."""
    from google.cloud import bigquery
    from google.oauth2 import service_account

    info = json.loads(os.environ["GCP_SA_JSON"])
    creds = service_account.Credentials.from_service_account_info(info)
    client = bigquery.Client(project=os.environ["GCP_PROJECT_ID"],
                             credentials=creds)
    all_urls = sorted({u for urls in urls_by_group.values() for u in urls})
    if not all_urls:
        return []
    cfg = bigquery.QueryJobConfig(
        maximum_bytes_billed=MAX_BYTES,
        query_parameters=[
            bigquery.ArrayQueryParameter("urls", "STRING", all_urls),
            bigquery.ScalarQueryParameter("day", "TIMESTAMP", day + " 00:00:00"),
        ],
    )
    q = (
        "SELECT DocumentIdentifier AS url, "
        "  CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64) AS tone "
        "FROM `gdelt-bq.gdeltv2.gkg_partitioned` "
        "WHERE _PARTITIONTIME >= @day "
        "  AND _PARTITIONTIME < TIMESTAMP_ADD(@day, INTERVAL 1 DAY) "
        "  AND DocumentIdentifier IN UNNEST(@urls)"
    )
    tone_by_url = {r["url"]: r["tone"] for r in client.query(q, job_config=cfg)}

    rows = []
    for group, urls in sorted(urls_by_group.items()):
        found = [tone_by_url[u] for u in urls if u in tone_by_url]
        rows.append({
            "date": day, "channel": group,
            "n_matched": len(set(urls)), "n_tone_found": len(found),
            "mean_tone": round(sum(found) / len(found), 3) if found else "",
        })
    return rows


def _upsert_store(rows: list[dict]) -> list[dict]:
    fields = ["date", "channel", "n_matched", "n_tone_found", "mean_tone"]
    existing: dict[tuple[str, str], dict] = {}
    if STORE.exists():
        with STORE.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing[(r["date"], r["channel"])] = r
    for r in rows:
        existing[(r["date"], r["channel"])] = {k: str(r[k]) for k in fields}
    allrows = [existing[k] for k in sorted(existing)]
    with STORE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(allrows)
    return allrows


def publish(allrows: list[dict]) -> None:
    days = sorted({r["date"] for r in allrows})[-PUBLISH_DAYS:]
    payload: dict[str, Any] = {
        "_meta": {
            "what": ("Mean V2Tone of each channel's MATCHED articles -- "
                     "the same articles the registered dictionaries "
                     "selected and the receipts pages enumerate; tone is "
                     "an annotation joined by URL in GDELT's GKG, never "
                     "a filter. Context axis only: tone enters no score, "
                     "no percentile, and no composite. n_tone_found vs "
                     "n_matched discloses the join rate; GKG does not "
                     "carry every URL. Negative tone is conventional "
                     "GDELT scaling (roughly -10 very negative to +10 "
                     "very positive)."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "days": {
            d: {r["channel"]: {
                "mean_tone": float(r["mean_tone"]) if r["mean_tone"] else None,
                "n_matched": int(r["n_matched"]),
                "n_tone_found": int(r["n_tone_found"]),
            } for r in allrows if r["date"] == d}
            for d in days
        },
    }
    (SITE_DATA / "tone.json").write_text(json.dumps(payload),
                                         encoding="utf-8")
    print(f"[tone] wrote tone.json: {len(days)} day(s)")


def main() -> None:
    if not (os.environ.get("GCP_SA_JSON") and os.environ.get("GCP_PROJECT_ID")):
        print("[tone] no GCP credentials in env; skipping (fail-closed, "
              "context axis simply absent)")
        return
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        cached = sorted(p.stem.replace("-extended", "")
                        for p in DAYS.glob("*.json"))
        if not cached:
            sys.exit("[tone] no receipt day caches to annotate")
        day = cached[-1]
    date.fromisoformat(day)  # validates
    urls = _day_urls(day)
    if not urls:
        sys.exit(f"[tone] no matched URLs cached for {day}")
    rows = fetch_day_tone(day, urls)
    allrows = _upsert_store(rows)
    publish(allrows)
    for r in rows:
        print(f"[tone] {r['channel']}: {r['n_tone_found']}/{r['n_matched']} "
              f"joined, mean {r['mean_tone']}")


if __name__ == "__main__":
    main()
