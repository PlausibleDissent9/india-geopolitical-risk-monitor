"""Build the public IGRM Continuous Evolution state.

The engine is deliberately an observer before it is an actor.  It computes a
stable, reviewable capability and coverage ledger from committed public
surfaces.  The hourly workflow may additionally emit a runtime audit artifact,
but this module has no network, Git mutation, merge, publication, signing or
method-changing authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "governance" / "evolution_engine.json"
LAYER_PATH = ROOT / "governance" / "global_atlas_layers.json"
WORLD_PATH = ROOT / "docs" / "geo" / "world.json"
RELATIONS_PATH = ROOT / "docs" / "data" / "map_relations.json"
HISTORY_PATH = ROOT / "docs" / "data" / "back_extension.json"
CATALOG_PATH = ROOT / "docs" / "data" / "product_catalog.json"
CONTRACT_PATH = ROOT / "docs" / "data" / "api_contract.json"
FRESHNESS_PATH = ROOT / "docs" / "data" / "freshness.json"
OUTPUT_PATH = ROOT / "docs" / "data" / "evolution.json"

_HEX = set("0123456789abcdef")
_RISK_CLASSES = (
    "R0_observe",
    "R1_reversible_implementation",
    "R2_product_or_data_expansion",
    "R3_method_claim_rights_or_security_boundary",
    "R4_external_outcome",
)
_STATES = (
    "observed",
    "specified",
    "implemented",
    "adversarially_tested",
    "authority_satisfied",
    "release_eligible",
    "released",
    "post_release_measured",
    "accepted_or_rolled_back",
)
_INDEX_STATES = {"not_an_index", "not_registered"}
_SELF_ENDPOINT = "data/evolution.json"


class EvolutionError(ValueError):
    """Stable refusal raised when the evolution contract cannot be trusted."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise EvolutionError(code)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("json_duplicate_key")
        value[key] = item
    return value


def _read(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvolutionError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: object) -> str:
    """Hash only the canonical evidence slice used by a measurement.

    Rolling payload values may change every day without changing a capability
    denominator.  Binding the public capability report to whole rolling files
    would manufacture stale-report failures.  Each caller therefore supplies
    the exact member/domain slice that supports the published count.
    """

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _unique_rows(rows: object, key: str, code: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not rows:
        _fail(code)
    typed: list[dict[str, Any]] = []
    identifiers: list[object] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str):
            _fail(code)
        typed.append(cast(dict[str, Any], row))
        identifiers.append(row[key])
    if len(set(identifiers)) != len(identifiers):
        _fail(code)
    return typed


def _validate_engine(engine: dict[str, Any]) -> None:
    if (
        engine.get("schema_version") != "1.0.0"
        or engine.get("engine_id") != "igrm-continuous-evolution"
        or engine.get("status")
        != "public_design_contract_observer_live_promotion_not_live"
    ):
        _fail("engine_identity_invalid")
    _day(engine.get("effective"), "engine_effective_invalid")
    floor = engine.get("launch_floor_policy")
    if not isinstance(floor, dict) or floor.get("october_contract_role") != (
        "minimum_capability_floor_not_ceiling"
    ):
        _fail("launch_floor_policy_invalid")
    cadence = _unique_rows(engine.get("cadence"), "cadence_id", "cadence_invalid")
    if {row["cadence_id"] for row in cadence} != {
        "hourly_scout",
        "per_change_adversary",
        "daily_green_batch",
        "weekly_challenge",
        "monthly_research_review",
        "quarterly_category_reset",
    }:
        _fail("cadence_set_invalid")
    dimensions = _unique_rows(
        engine.get("quality_dimensions"), "dimension_id", "quality_dimensions_invalid"
    )
    if len(dimensions) != 8:
        _fail("quality_dimension_count_invalid")
    risks = _unique_rows(engine.get("risk_classes"), "risk_class", "risk_classes_invalid")
    if tuple(row["risk_class"] for row in risks) != _RISK_CLASSES:
        _fail("risk_class_order_invalid")
    for row in risks:
        if row["risk_class"] in {"R3_method_claim_rights_or_security_boundary", "R4_external_outcome"}:
            authority = str(row.get("automatic_authority", ""))
            if authority not in {"observe_and_propose_only", "none"}:
                _fail("high_risk_automatic_authority_forbidden")
    if tuple(engine.get("candidate_state_machine", [])) != _STATES:
        _fail("candidate_state_machine_invalid")
    boundary = engine.get("current_automation_boundary")
    if not isinstance(boundary, dict) or (
        boundary.get("hourly_observer") != "live_read_only"
        or boundary.get("automatic_code_change") != "not_authorized"
        or boundary.get("automatic_publication") != "not_authorized"
    ):
        _fail("automation_boundary_invalid")
    _unique_rows(
        engine.get("strategic_programs"), "program_id", "strategic_programs_invalid"
    )


def _validate_layers(layers: dict[str, Any]) -> list[dict[str, Any]]:
    if (
        layers.get("schema_version") != "1.0.0"
        or layers.get("registry_id") != "igrm-global-atlas-layers"
    ):
        _fail("layer_registry_identity_invalid")
    _day(layers.get("effective"), "layer_registry_effective_invalid")
    composition = layers.get("composition_policy")
    if not isinstance(composition, dict) or (
        composition.get("single_world_score") != "prohibited"
        or composition.get("cross_domain_averaging") != "prohibited"
    ):
        _fail("layer_composition_policy_invalid")
    rows = _unique_rows(layers.get("layers"), "layer_id", "layers_invalid")
    if len(rows) < 15:
        _fail("layer_denominator_too_small")
    for row in rows:
        required = {
            "layer_id",
            "label",
            "family",
            "kind",
            "construct",
            "current_state",
            "index_state",
            "country_level",
            "source_payload",
            "update_target",
            "subdimensions",
            "candidate_source_families",
            "missingness_rule",
            "prohibited_interpretation",
            "safety_rule",
        }
        if set(row) != required:
            _fail("layer_fields_invalid")
        if row["index_state"] not in _INDEX_STATES:
            _fail("layer_index_state_invalid")
        state = row["current_state"]
        source = row["source_payload"]
        if not isinstance(state, str):
            _fail("layer_state_invalid")
        if state.startswith("published_"):
            if not isinstance(source, str):
                _fail("published_layer_source_missing")
            path = (ROOT / source).resolve()
            try:
                path.relative_to(ROOT.resolve())
            except ValueError:
                _fail("published_layer_source_outside_root")
            if not path.is_file() or path.is_symlink():
                _fail("published_layer_source_missing")
        elif source is not None:
            _fail("unpublished_layer_source_must_be_null")
    return rows


def _published_layer_state(row: dict[str, Any]) -> bool:
    return str(row["current_state"]).startswith("published_")


def validate_static_contracts() -> None:
    """Validate the immutable engine and Atlas registries only.

    Generated products may call this while they are being recreated.  It must
    therefore never depend on the product catalog, API contract, public report,
    or any other generated output whose existence would create a bootstrap
    cycle.
    """

    engine, _ = _read(ENGINE_PATH, "engine_unreadable")
    layers, _ = _read(LAYER_PATH, "layer_registry_unreadable")
    _validate_engine(engine)
    _validate_layers(layers)


def build_report(root: Path = ROOT) -> dict[str, Any]:
    """Return the deterministic public capability and improvement ledger."""

    if root.resolve() != ROOT.resolve():
        _fail("alternate_root_not_supported")
    engine, engine_sha = _read(ENGINE_PATH, "engine_unreadable")
    layers, layers_sha = _read(LAYER_PATH, "layer_registry_unreadable")
    world, _ = _read(WORLD_PATH, "world_geometry_unreadable")
    relations, _ = _read(RELATIONS_PATH, "map_relations_unreadable")
    history, _ = _read(HISTORY_PATH, "historical_proxy_unreadable")
    catalog, _ = _read(CATALOG_PATH, "product_catalog_unreadable")
    contract, _ = _read(CONTRACT_PATH, "api_contract_unreadable")
    _validate_engine(engine)
    layer_rows = _validate_layers(layers)

    countries = world.get("countries")
    partners = relations.get("partners")
    if not isinstance(countries, dict) or not countries:
        _fail("world_geometry_members_invalid")
    if not isinstance(partners, dict) or not partners:
        _fail("map_relation_members_invalid")
    if not set(partners).issubset(countries):
        _fail("map_relation_member_not_in_geometry")
    if relations.get("_meta", {}).get("partial") is not False:
        _fail("map_relations_partial")

    routes = _unique_rows(catalog.get("routes"), "path", "product_routes_invalid")
    missing_routes = [
        row["path"]
        for row in routes
        if not (ROOT / "docs" / cast(str, row["path"])).is_file()
    ]
    if missing_routes:
        _fail("catalog_route_missing")
    endpoints = _unique_rows(contract.get("endpoints"), "path", "api_endpoints_invalid")
    endpoint_paths = {cast(str, row["path"]) for row in endpoints}
    if _SELF_ENDPOINT not in endpoint_paths:
        _fail("evolution_endpoint_unregistered")
    missing_endpoints = [
        row["path"]
        for row in endpoints
        if row["path"] != _SELF_ENDPOINT
        and not (ROOT / "docs" / cast(str, row["path"])).is_file()
    ]
    if missing_endpoints:
        _fail("api_endpoint_missing")

    historical_series = history.get("series")
    if not isinstance(historical_series, dict) or not historical_series:
        _fail("historical_series_invalid")
    starts: list[str] = []
    ends: list[str] = []
    for series in historical_series.values():
        if not isinstance(series, dict) or not isinstance(series.get("months"), list):
            _fail("historical_series_invalid")
        months = series["months"]
        if not months or not all(isinstance(month, str) for month in months):
            _fail("historical_series_invalid")
        starts.append(months[0])
        ends.append(months[-1])

    observed_layers = [row for row in layer_rows if _published_layer_state(row)]
    country_layers = [row for row in layer_rows if row["country_level"] is True]
    observed_country_layers = [row for row in country_layers if _published_layer_state(row)]
    missing_geometry = sorted(set(countries) - set(partners))
    programs = cast(list[dict[str, Any]], engine["strategic_programs"])

    return {
        "_meta": {
            "what": (
                "Deterministic public state of the IGRM Continuous Evolution Engine: "
                "its authority boundary, measured capability denominators and highest-value "
                "registered improvement gaps. This is not evidence that improvements or "
                "external outcomes have occurred."
            ),
            "definition": (
                "The October contract is a minimum launch floor, not a capability ceiling. "
                "The observer may measure and propose; it cannot modify methods, rights, "
                "public claims, code or releases."
            ),
            "generated": cast(str, engine["effective"]),
            "partial": False,
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). IGRM Continuous Evolution Engine. "
                "https://igrm.in/data/evolution.json"
            ),
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/evolution.json",
            "input_sha256": {
                "engine_registry": engine_sha,
                "global_layer_registry": layers_sha,
                "world_geometry_member_set": canonical_sha256(sorted(countries)),
                "map_relation_member_set": canonical_sha256(sorted(partners)),
                "historical_proxy_domain": canonical_sha256(
                    {
                        key: cast(dict[str, Any], series)["months"]
                        for key, series in sorted(historical_series.items())
                    }
                ),
                "product_route_set": canonical_sha256(
                    sorted(cast(str, row["path"]) for row in routes)
                ),
                "api_endpoint_set": canonical_sha256(
                    sorted(cast(str, row["path"]) for row in endpoints)
                ),
            },
        },
        "authority": {
            "observer": "configured_read_only",
            "automatic_code_change": "not_authorized",
            "automatic_publication": "not_authorized",
            "risk_classes": engine["risk_classes"],
            "candidate_state_machine": engine["candidate_state_machine"],
        },
        "cadence": engine["cadence"],
        "quality_dimensions": engine["quality_dimensions"],
        "measured_state": {
            "public_product_routes": {
                "registered": len(routes),
                "present": len(routes) - len(missing_routes),
                "missing": missing_routes,
            },
            "public_api_endpoints": {
                "registered": len(endpoints),
                "present": len(endpoints) - len(missing_endpoints),
                "missing": missing_endpoints,
            },
            "global_atlas": {
                "country_area_geometries": len(countries),
                "india_partner_event_context_observed": len(partners),
                "india_partner_event_context_unavailable": len(missing_geometry),
                "unavailable_geometry_ids": missing_geometry,
                "registered_layers": len(layer_rows),
                "published_layers": len(observed_layers),
                "registered_country_level_layers": len(country_layers),
                "published_country_level_layers": len(observed_country_layers),
                "single_world_score": "prohibited",
            },
            "historical_intelligence": {
                "source_start": min(starts),
                "source_end": max(ends),
                "published_proxy_channels": len(historical_series),
                "current_operating_program": "historical_intelligence_activation",
                "current_boundary": (
                    "The two published monthly proxies are different constructs from the "
                    "live index and are not spliced into it."
                ),
            },
        },
        "strategic_programs": programs,
        "priority_queue": [
            {
                "candidate_id": "world_state_matrix",
                "risk_class": "R2_product_or_data_expansion",
                "state": "released",
                "target_dimensions": ["coverage", "utility", "experience"],
                "evidence": {
                    "mapped_country_area_geometries": len(countries),
                    "observed_current_layer": len(partners),
                    "registered_layers": len(layer_rows),
                    "published_country_level_layers": len(observed_country_layers),
                },
                "next_gate": (
                    "Measure the released matrix after publication and add real source-backed "
                    "layers only after their rights, construct and independent-review gates."
                ),
            },
            {
                "candidate_id": "historical_intelligence_activation",
                "risk_class": "R2_product_or_data_expansion",
                "state": "specified",
                "target_dimensions": ["utility", "coverage", "reproducibility_citation"],
                "evidence": {
                    "source_start": min(starts),
                    "source_end": max(ends),
                    "published_proxy_channels": len(historical_series),
                },
                "next_gate": (
                    "Register regime baselines, structural-break diagnostics, event archetypes "
                    "and analog retrieval with explicit non-comparability tests."
                ),
            },
            {
                "candidate_id": "total_product_quality",
                "risk_class": "R2_product_or_data_expansion",
                "state": "in_progress",
                "target_dimensions": ["experience", "utility", "reliability"],
                "evidence": {
                    "registered_public_routes": len(routes),
                    "present_public_routes": len(routes) - len(missing_routes),
                },
                "next_gate": (
                    "Run the institutional design and interaction standard over every protected "
                    "route, followed by independent cross-viewport review."
                ),
            },
        ],
        "external_outcomes": {
            "citations": "not_inferred_by_this_engine",
            "awards": "not_inferred_by_this_engine",
            "government_adoption": "not_inferred_by_this_engine",
            "independent_study_results": "record_only_after_authentic_external_evidence",
        },
    }


def build_runtime_audit(now: datetime | None = None) -> dict[str, Any]:
    """Return an ephemeral hourly audit without mutating the public report."""

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() != timezone.utc.utcoffset(moment):
        _fail("audit_time_not_utc")
    report = build_report()
    freshness_payload, freshness_sha = _read(FRESHNESS_PATH, "freshness_unreadable")
    payloads = freshness_payload.get("payloads")
    if not isinstance(payloads, list):
        _fail("freshness_payloads_invalid")
    freshness_counts = Counter(
        str(row.get("status")) for row in payloads if isinstance(row, dict)
    )
    current_report = _encoded(report)
    try:
        public_report = OUTPUT_PATH.read_bytes()
    except OSError:
        public_report = b""
    return {
        "schema_version": "1.0.0",
        "audit_kind": "read_only_hourly_scout",
        "audited_at": moment.isoformat().replace("+00:00", "Z"),
        "commit_publication_authority": "none",
        "automatic_change_authority": "none",
        "public_report_current": public_report == current_report,
        "public_report_sha256": (
            hashlib.sha256(public_report).hexdigest() if public_report else None
        ),
        "current_report_sha256": hashlib.sha256(current_report).hexdigest(),
        "registered_priority_queue": report["priority_queue"],
        "current_freshness_ledger": {
            "payloads": len(payloads),
            "status_counts": dict(sorted(freshness_counts.items())),
        },
        "capability_input_sha256": cast(dict[str, Any], report["_meta"])[
            "input_sha256"
        ],
        "runtime_input_sha256": {"freshness": freshness_sha},
    }


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def write_report(path: Path = OUTPUT_PATH) -> None:
    path.write_bytes(_encoded(build_report()))


def check_report(path: Path = OUTPUT_PATH) -> None:
    try:
        current = path.read_bytes()
    except OSError as exc:
        raise EvolutionError("evolution_report_missing") from exc
    if current != _encoded(build_report()):
        _fail("evolution_report_stale")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="write the deterministic public report")
    group.add_argument("--check", action="store_true", help="refuse if the public report is stale")
    group.add_argument("--audit", action="store_true", help="print an ephemeral read-only audit")
    args = parser.parse_args()
    if args.audit:
        print(json.dumps(build_runtime_audit(), ensure_ascii=False, indent=2, allow_nan=False))
    elif args.check:
        check_report()
    else:
        write_report()


if __name__ == "__main__":
    main()
