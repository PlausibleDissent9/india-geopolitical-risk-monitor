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

# Patch: daily_brief withdrawn with a stable-shaped tombstone and explicit
# deprecation record.
CONTRACT_VERSION = "2.2.8"
FROZEN_DATE = "2026-08-08"

# api_contract.json is deliberately skipped by the daily metadata stamper:
# a frozen promise must not drift as a side effect of a pipeline run. Keep
# its self-citation fields here and lock them against src.stamp_meta in tests.
UNIVERSAL_META = {
    "license": "CC BY 4.0",
    "citation": ("Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/"),
    "codebook": "https://igrm.in/codebook.html",
    "source": "https://igrm.in/data/api_contract.json",
}

# Fallback descriptions for payloads with no _meta.what/_meta.definition to
# borrow from. Kept short; the full construction lives in codebook.md.
DESCRIPTIONS = {
    "alt_specs.json": "Robustness bundle: composite under alternate channel "
    "weightings, episode-detection sigma thresholds, and percentile "
    "window lengths, published beside the frozen defaults.",
    "episodes.json": "Detected coverage episodes (array): channel, start "
    "and end dates, and peak percentile, from the frozen 2sigma/90-day "
    "spike rule.",
    "episodes.csv": "The same detected episodes as CSV, one row per episode.",
    "event_study.csv": "Event-study outcome cells as CSV: India-specific "
    "relative outcomes plus labelled descriptive commodity returns, one "
    "row per channel x window x market series.",
    "history.csv": "The full daily series (composite and five channels) "
    "as CSV, one row per day, since 2017.",
    "feed.xml": "RSS 2.0 feed of the weekly analytical notes.",
    "note_latest.json": "The most recent published weekly note: filename and raw markdown body.",
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
    "validation.json": "The registered episode-detection record: 24 of 29 "
    "events under the +/-3-day corresponding-channel criterion (the "
    "original pre-registered tranche was 18 of 21; the later registered "
    "tranche was 6 of 8), plus baselines, cross-source comparisons, "
    "placebo checks and robustness under alternate specifications.",
}

# Endpoints intentionally excluded from the data-API contract because they
# are not analytical payloads: igrm.bib (citation download), sitemap.xml
# and robots.txt (crawler infrastructure).
EXCLUDE = {"api_contract.json", "decisions.json"}

# Versioned public-standard files live outside docs/data/ but are still
# machine-consumption endpoints.  Keep the inventory explicit: adding a file
# under docs/oges or docs/schemas must be an intentional API-contract change,
# not an implicit directory walk that silently expands the public promise.
PUBLIC_STANDARD_JSON: dict[str, dict[str, str]] = {
    "oges/0.1.0/adversarial-cases.json": {
        "description": (
            "The eleven registered OGES 0.1.0 conformance vectors: one valid "
            "bundle and ten exact fail-closed mutations with their required "
            "refusal codes. Synthetic test material only; not empirical "
            "evidence or an adoption claim."
        ),
        "stability": "static versioned public draft 0.1.0",
    },
    "oges/0.1.0/profile.json": {
        "description": (
            "The hash-pinned OGES 0.1.0 reference profile: required canonical "
            "object types, normative schema and validator digests, conformance "
            "suite digest, and explicit non-adoption boundary."
        ),
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/canonical-release.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a signed canonical release manifest.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/common.schema.json": {
        "description": "OGES 0.1.0 shared JSON Schema definitions and primitives.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/entity.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a typed, versioned entity.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/event.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a typed, evidence-linked event.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/evidence-item.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a rights-aware evidence item.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/exposure-edge.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a bounded, method-linked exposure edge.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/exposure-dna.schema.json": {
        "description": (
            "JSON Schema for non-scalar India Exposure DNA snapshots and "
            "release-to-release deltas that retain original units, declared-universe "
            "coverage, source-policy freshness and explicit gaps."
        ),
        "stability": "static synthetic foundation 1.0.0",
    },
    "schemas/exposure-traversal.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a bounded exposure traversal result.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/evidence-output-set.schema.json": {
        "description": (
            "JSON Schema for one deterministic four-product compilation from a "
            "signed canonical evidence release: research package, board-brief draft, "
            "newsroom claim card and authenticated offline audit bundle."
        ),
        "stability": "static synthetic foundation 1.0.0",
    },
    "schemas/shock-scenario.schema.json": {
        "description": (
            "JSON Schema for a release-bound hypothetical shock scenario with strict "
            "magnitude, duration, substitution, buffer and non-forecast guardrails."
        ),
        "stability": "static synthetic foundation 1.0.0",
    },
    "schemas/shock-compilation.schema.json": {
        "description": (
            "JSON Schema for deterministic bounded shock compilations over signed "
            "exposure paths, including assumptions, ranges, freshness and explicit gaps."
        ),
        "stability": "static synthetic foundation 1.0.0",
    },
    "schemas/knowledge-availability-receipt.schema.json": {
        "description": (
            "JSON Schema for a separately signed, hash-chained canonical-release "
            "availability receipt used by the synthetic knowledge-replay foundation."
        ),
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/knowledge-replay-ledger.schema.json": {
        "description": (
            "JSON Schema for the signed complete-release ledger used by the "
            "synthetic knowledge-replay foundation."
        ),
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/knowledge-replay.schema.json": {
        "description": (
            "JSON Schema for a structural bitemporal replay result that separates "
            "knowledge cutoff from valid date and emits no claim values."
        ),
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/sensor-fusion.schema.json": {
        "description": (
            "JSON Schema for a structural eight-lane Sensor Fusion matrix that "
            "keeps unlike evidence semantically separate, publishes lane "
            "coverage and emits no observed values or numeric fusion."
        ),
        "stability": "static synthetic foundation 1.0.0",
    },
    "schemas/universe-frame.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for an enumerated source-universe frame.",
        "stability": "static versioned public draft 0.1.0",
    },
    "schemas/universe-release.schema.json": {
        "description": "OGES 0.1.0 JSON Schema for a reconciled, versioned universe release.",
        "stability": "static versioned public draft 0.1.0",
    },
}


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
    "data/daily_brief.json": {
        "description": "WITHDRAWN machine-brief experiment. Generated prose failed factual grounding; a stable-shaped null tombstone preserves the frozen-v2 endpoint during its deprecation window.",
        "stability": "deprecated; null tombstone through at least 2026-11-06",
        "frozen_fields": ["_meta", "date", "composite", "channels"],
    },
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
            "largest_rank_divergences",
        ],
    },
    "data/divergence_register.json": {
        "description": "Append-only register of large documented rank gaps between IGRM and independent comparators. Every row states its sample, receipt and claim limit; disagreement is an inspection target, not a superiority result.",
        "stability": "append-only",
        "frozen_fields": ["_meta", "entries"],
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
            "available_outcomes",
            "unavailable_outcomes",
            "channels",
            "per_episode",
        ],
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
            "descriptive_only",
        ],
    },
}


def build() -> dict:
    endpoints = []

    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in EXCLUDE:
            continue
        data = json.loads(path.read_text())
        endpoints.append(
            {
                "path": f"data/{path.name}",
                "format": "json",
                "description": _description(path.name, data) or DESCRIPTIONS.get(path.name, ""),
                "frozen_fields": _fields(data),
                "stability": "stable",
            }
        )

    for path in sorted(SITE_DATA.glob("*.csv")):
        with path.open() as f:
            columns = next(csv.reader(f))
        endpoints.append(
            {
                "path": f"data/{path.name}",
                "format": "csv",
                "description": DESCRIPTIONS.get(path.name, ""),
                "frozen_fields": columns,
                "stability": "stable",
            }
        )

    for relative, contract_fields in PUBLIC_STANDARD_JSON.items():
        path = DOCS / relative
        if not path.is_file():
            raise SystemExit(f"public standard endpoint is missing: {relative}")
        data = json.loads(path.read_text(encoding="utf-8"))
        endpoints.append(
            {
                "path": relative,
                "format": "json",
                "description": contract_fields["description"],
                "frozen_fields": _fields(data),
                "stability": contract_fields["stability"],
            }
        )

    endpoints.append(
        {
            "path": "feed.xml",
            "format": "rss",
            "description": DESCRIPTIONS["feed.xml"],
            "frozen_fields": ["title", "link", "pubDate", "description", "guid"],
            "stability": "stable",
        }
    )

    for e in endpoints:
        if e["path"] in OVERRIDES:
            e.update(OVERRIDES[e["path"]])

    endpoints.sort(key=lambda e: e["path"])
    for e in endpoints:
        if not e["description"]:
            raise SystemExit(
                f"no description for {e['path']}; add one to DESCRIPTIONS before freezing"
            )

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
                "rate_limit": "none stated; ordinary politeness (poll daily, not per-request)",
                "refresh": "daily by 06:00 IST (00:30 UTC) for the final "
                "day; nowcast.json refreshes about every two hours "
                "after and is excluded from this freeze (payload "
                "shape may still change, disclosed in its own "
                "_meta)",
            },
            "deprecated": [
                {
                    "path": "data/daily_brief.json",
                    "deprecated": "2026-08-08",
                    "earliest_removal": "2026-11-06",
                    "reason": (
                        "Generated prose failed factual grounding: unsupported "
                        "numbers, selection-induced source-share interpretation, "
                        "display-count/score-denominator conflation, and a "
                        "cross-date score/receipt join. The prose is withdrawn; "
                        "a stable-shaped null tombstone remains during the v2 "
                        "deprecation window."
                    ),
                }
            ],
            "removed": [
                {
                    "path": "data/decisions.json",
                    "removed": "2026-08-07",
                    "reason": (
                        "The founder's operational queue was outside the scope "
                        "of the analytical API. It was removed on the day it "
                        "was introduced; no research data were affected."
                    ),
                }
            ],
            **UNIVERSAL_META,
        },
        "endpoints": endpoints,
    }


def main() -> None:
    contract = build()
    out = SITE_DATA / "api_contract.json"
    out.write_text(json.dumps(contract, indent=1) + "\n")
    print(
        f"[api_contract] wrote {out} ({len(contract['endpoints'])} "
        "endpoints, contract v" + CONTRACT_VERSION + ")"
    )


if __name__ == "__main__":
    main()
