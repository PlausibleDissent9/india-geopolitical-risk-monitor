"""
One-time (and re-run-on-purpose) generator for docs/data/api_contract.json,
the frozen API contract.

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

CONTRACT_VERSION = "2.2.0"  # minor: country_china.json endpoint added; event_study.json and detector_blindness.json gained additive disclosure fields
FROZEN_DATE = "2026-08-08"

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
    "event_study.csv": "Event-study outcome cells as CSV: India-specific "
        "relative outcomes plus labelled descriptive commodity returns, one "
        "row per channel x window x market series.",
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
    "monthly.csv": "The daily series aggregated to calendar months, with "
        "the three traps handled in the open: months below 80% day "
        "coverage publish null values and a stated reason instead of a "
        "mean over the survivors, months spanning the DOC API/NGrams "
        "instrument boundary are flagged, and the mean-of-ranks composite "
        "is published beside the commensurable share means rather than "
        "instead of them.",
    "shares.csv": "The QUANTITY the index is built from: each channel's "
        "daily share of the GDELT-monitored corpus, in percent. Published "
        "so any reader can apply their own normalization; commensurable "
        "across channels and years where percentiles are not. The source "
        "column names the instrument that measured each day, because the "
        "series mixes DOC API counts with splice-linked NGrams-bridge "
        "days and a mean across that boundary inherits the linking "
        "constant's uncertainty.",
    "validation.json": "The pre-registered validation record: hit rate "
        "against the 21-episode list, cross-source and placebo checks, "
        "robustness under alternate specifications.",
}

# Endpoints intentionally excluded from the data-API contract because they
# are not analytical payloads: igrm.bib (citation download), sitemap.xml
# and robots.txt (crawler infrastructure).
EXCLUDE = {"api_contract.json", "decisions.json"}


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



# Hand-refined contract entries that the derivation must NOT regress.
#
# The generator's rule is "description = the payload's own _meta.what",
# which keeps one source of truth. ai_gpr_benchmark.json broke the rule
# honestly: it is a hash-pinned registered vintage, so its _meta cannot
# be edited to carry the fuller description the contract should serve,
# and the refined text was hand-placed in the committed contract instead.
# Without this table, rerunning the generator silently rolled that text
# back (caught 2026-08-07 by diffing generated against committed -- 34
# lines of regression, including "append-only" and "static registered
# vintage" stability labels collapsing to "stable").
#
# An entry here is the one sanctioned place for contract text that a
# frozen payload cannot carry. test_api_contract_is_derived asserts
# generated == committed, so drift in either direction now fails.
OVERRIDES: dict = {
 "data/ai_gpr_benchmark.json": {
  "description": "Static, code-frozen comparison of monthly IGRM salience with Iacoviello-Tong AI-GPR India_all: registered primary and descriptive correlations, moving-block intervals, full eligible-month list, exploratory matrix, event-month ranks and largest rank divergences. Aggregates and ranks only; no raw AI-GPR values are redistributed.",
  "stability": "static registered vintage",
  "frozen_fields": [
   "_meta",
   "sample",
   "primary",
   "descriptive_primary",
   "exploratory_correlations",
   "episode_month_ranks",
   "largest_rank_divergences"
  ]
 },
 "data/divergence_register.json": {
  "description": "Append-only register of large documented rank gaps between IGRM and independent comparators. Every row states its sample, receipt and claim limit; disagreement is an inspection target, not a superiority result.",
  "stability": "append-only",
  "frozen_fields": [
   "_meta",
   "entries"
  ]
 },
 "data/event_study.json": {
  "description": "Event study: mean cumulative India-specific relative outcomes plus separately labelled descriptive commodity returns after episode starts, with bootstrapped 95% CIs and raw per-episode windows.",
  "stability": "stable",
  "frozen_fields": [
   "_meta",
   "generated",
   "windows",
   "units",
   "language",
   "descriptive_only",
   "channels",
   "per_episode"
  ]
 },
 "data/event_study.csv": {
  "description": "Event-study outcome cells as CSV: India-specific relative outcomes plus labelled descriptive commodity-return rows, one row per channel x window x market series.",
  "stability": "stable",
  "frozen_fields": [
   "channel",
   "outcome",
   "window_trading_days",
   "mean_cum_log_return_pct",
   "ci95_lo",
   "ci95_hi",
   "p_boot",
   "bh_significant_10pct",
   "n_episodes",
   "descriptive_only"
  ]
 }
}


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

    for e in endpoints:
        if e["path"] in OVERRIDES:
            e.update(OVERRIDES[e["path"]])

    endpoints.sort(key=lambda e: e["path"])
    for e in endpoints:
        if not e["description"]:
            raise SystemExit(f"no description for {e['path']}; add one to "
                              "DESCRIPTIONS before freezing")

    return {
        "_meta": {
            "what": "The frozen v2 API contract: every endpoint IGRM "
                "serves for machine consumption, the fields promised "
                "stable within this major version, and the policy "
                "governing changes.",
            "contract_version": CONTRACT_VERSION,
            "frozen_date": FROZEN_DATE,
            "base_url": "https://igrm.in/",
            "promise": "Frozen fields are never removed, renamed, or "
                "repurposed to a different meaning within major version "
                "2. New fields may be added to any payload at any time "
                "without a version bump. Any removal, rename, or type "
                "change requires a major version bump, announced here "
                "and in methodology.md's changelog before it ships.",
            "deprecation_policy": "An analytical field or endpoint marked "
                "deprecated stays live and unchanged in meaning for at "
                "least 90 days after the date recorded here, before "
                "removal in the next major version. Operational or "
                "personal material served by mistake may be withdrawn "
                "immediately, with the removal recorded here.",
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
            "removed": [{
                "path": "data/decisions.json",
                "removed": "2026-08-07",
                "reason": (
                    "The founder's operational queue was outside the scope "
                    "of the analytical API. It was removed on the day it "
                    "was introduced; no research data were affected."
                ),
            }],
        },
        "endpoints": endpoints,
    }


def main() -> None:
    contract = build()
    out = SITE_DATA / "api_contract.json"
    out.write_text(json.dumps(contract, indent=1) + "\n")
    print(f"[api_contract] wrote {out} ({len(contract['endpoints'])} "
          "endpoints, contract v" + CONTRACT_VERSION + ")")


if __name__ == "__main__":
    main()
