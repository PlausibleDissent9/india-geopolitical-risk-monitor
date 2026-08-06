"""
One-time (and re-run-on-purpose) generator for docs/data/api_contract.json,
the frozen v1 API contract (V7).

This is NOT part of the daily pipeline. The contract is a committed,
hand-reviewed snapshot: fields recorded here are a promise, not a live
readout, so the file is regenerated only when a maintainer deliberately
freezes a new baseline or bumps CONTRACT_VERSION for a breaking change.
Running it day-to-day would let the "frozen" list drift silently, which
is exactly what the contract exists to prevent.

Run:  python -m scripts.generate_api_contract
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
DOCS = ROOT / "docs"

CONTRACT_VERSION = "1.14.0"  # + forecasts.json (V11 experiment, signed registration)
FROZEN_DATE = "2026-08-04"

# Fallback descriptions for payloads with no _meta.what/_meta.definition to
# borrow from. Kept short; the full construction lives in codebook.md.
DESCRIPTIONS = {
    "alt_specs.json": "Robustness bundle: composite under alternate channel "
        "weightings, episode-detection sigma thresholds, and percentile "
        "window lengths, published beside the frozen defaults.",
    "episodes.json": "Detected coverage episodes (array): channel, start "
        "and end dates, and peak percentile, from the frozen 2sigma/90-day "
        "spike rule.",
    "episodes.csv": "The same detected episodes as CSV, one row per "
        "episode.",
    "event_study.csv": "Event-study relative-return cells as CSV, one row "
        "per channel x window x market series.",
    "history.csv": "The full daily series (composite and five channels) "
        "as CSV, one row per day, since 2017.",
    "feed.xml": "RSS 2.0 feed of the weekly analytical notes.",
    "note_latest.json": "The most recent published weekly note: filename "
        "and raw markdown body.",
    "notes.json": "Index of published weekly notes (array): ISO week "
        "label and the full markdown body of each note.",
    "priced_risk.json": "The attention-pricing gap: press-salience "
        "percentile vs India VIX percentile on shared trading days, plus "
        "divergence episodes and a lead-lag cross-correlation study.",
    "seasonality.json": "Day-of-week and month-of-year salience means, "
        "descriptive only, no seasonal adjustment applied anywhere else.",
    "validation.json": "The pre-registered validation record: hit rate "
        "against the 21-episode list, cross-source and placebo checks, "
        "robustness under alternate specifications.",
}

# Endpoints intentionally excluded from the data-API contract because they
# are not analytical payloads: igrm.bib (citation download), sitemap.xml
# and robots.txt (crawler infrastructure).
EXCLUDE = {"api_contract.json"}


def _fields(data) -> list[str] | str:
    if isinstance(data, dict):
        return list(data.keys())
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return list(data[0].keys())
        return f"array, {len(data)} items"
    return "scalar"


def _description(name: str, data) -> str:
    if isinstance(data, dict):
        meta = data.get("_meta")
        if isinstance(meta, dict):
            for key in ("what", "definition"):
                if meta.get(key):
                    return meta[key]
        for key in ("definition", "note"):
            if data.get(key):
                return data[key]
    return DESCRIPTIONS.get(name, "")


def build() -> dict:
    endpoints = []

    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in EXCLUDE:
            continue
        data = json.loads(path.read_text())
        endpoints.append({
            "path": f"data/{path.name}",
            "format": "json",
            "description": _description(path.name, data)
                or DESCRIPTIONS.get(path.name, ""),
            "frozen_fields": _fields(data),
            "stability": "stable",
        })

    for path in sorted(SITE_DATA.glob("*.csv")):
        with path.open() as f:
            columns = next(csv.reader(f))
        endpoints.append({
            "path": f"data/{path.name}",
            "format": "csv",
            "description": DESCRIPTIONS.get(path.name, ""),
            "frozen_fields": columns,
            "stability": "stable",
        })

    endpoints.append({
        "path": "feed.xml",
        "format": "rss",
        "description": DESCRIPTIONS["feed.xml"],
        "frozen_fields": ["title", "link", "pubDate", "description", "guid"],
        "stability": "stable",
    })

    endpoints.sort(key=lambda e: e["path"])
    for e in endpoints:
        if not e["description"]:
            raise SystemExit(f"no description for {e['path']}; add one to "
                              "DESCRIPTIONS before freezing")

    return {
        "_meta": {
            "what": "The frozen v1 API contract: every endpoint IGRM "
                "serves for machine consumption, the fields promised "
                "stable within this major version, and the policy "
                "governing changes.",
            "contract_version": CONTRACT_VERSION,
            "frozen_date": FROZEN_DATE,
            "base_url": "https://igrm.in/",
            "promise": "Frozen fields are never removed, renamed, or "
                "repurposed to a different meaning within major version "
                "1. New fields may be added to any payload at any time "
                "without a version bump. Any removal, rename, or type "
                "change requires a major version bump, announced here "
                "and in methodology.md's changelog before it ships.",
            "deprecation_policy": "A field or endpoint marked deprecated "
                "stays live and unchanged in meaning for at least 90 "
                "days after the deprecation date recorded here, before "
                "removal in the next major version.",
            "access": {
                "auth": "none",
                "cors": "Access-Control-Allow-Origin: *",
                "rate_limit": "none stated; ordinary politeness (poll "
                    "daily, not per-request)",
                "refresh": "daily by 06:00 IST (00:30 UTC) for the final "
                    "day; nowcast.json refreshes about every two hours "
                    "after and is excluded from this freeze (payload "
                    "shape may still change, disclosed in its own "
                    "_meta)",
            },
            "deprecated": [],
        },
        "endpoints": endpoints,
    }


def main() -> None:
    contract = build()
    out = SITE_DATA / "api_contract.json"
    out.write_text(json.dumps(contract, indent=2) + "\n")
    print(f"[api_contract] wrote {out} ({len(contract['endpoints'])} "
          "endpoints, contract v" + CONTRACT_VERSION + ")")


if __name__ == "__main__":
    main()
