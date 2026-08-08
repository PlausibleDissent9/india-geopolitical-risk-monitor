"""Compile one entity's exposure fingerprint from signed canonical releases.

Exposure DNA is a projection, not a second truth store and not a score.  Each
snapshot consumes the exact objects returned by the canonical release validator,
keeps every edge in its original unit and denominator, publishes declared-
universe gaps, and applies only a registered source-age policy.  A comparison
builds both snapshots independently before reporting added, removed or revised
edges.  It never infers missing links, aggregates unlike magnitudes, attributes
causation, predicts an outcome or emits a recommendation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, Optional, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]
DNA_REGISTRY = ROOT / "governance" / "exposure_dna_registry.json"

_METHOD_ID = "method:igrm.exposure_dna"
_METHOD_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/exposure-dna.schema.json"
_OUTPUT_SCHEMA_SHA256 = "9f137907d3ef3b5316784af11e0e93ca767b5868675550d5840bc6467f63d170"
_COMMON_SCHEMA_SHA256 = "56e167e287f4d670ac654ac5118d6b9688c801518038e5ac2f3ec55bca9f83d1"
_MAX_DIRECT_EDGES = 5000
_SNAPSHOT_SELECTION = "active_direct_edges_effective_on_canonical_release_date"
_FRESHNESS_RULE = (
    "edge_observed_at_against_release_generated_at_using_all_evidence_source_policies"
)
_COMPARISON_RULE = "same_entity_two_independently_validated_snapshots"
_TARGET_TYPES = (
    "state_or_ut",
    "sector",
    "company",
    "critical_asset",
    "route",
    "chokepoint",
    "port",
    "border_crossing",
    "commodity",
    "technology",
)
_EDGE_TYPES = (
    "import_dependence",
    "export_dependence",
    "freight_dependence",
    "energy_dependence",
    "supplier_concentration",
    "ownership",
    "operational_presence",
    "border_proximity",
    "treaty_obligation",
    "sanctions_reach",
    "cyber_dependency",
    "policy_jurisdiction",
    "input_dependency",
    "route_dependency",
    "technology_dependency",
)
_CHANGE_ASPECT_ORDER = (
    "semantics",
    "quantification",
    "effective_interval",
    "freshness",
    "coverage",
    "confidence",
    "evidence_or_method",
    "limitations",
)
_DIMENSIONS = (
    {
        "dimension_id": "dim:exposure.cross_border_supply",
        "label": "Cross-border supply",
        "definition": (
            "Direct supply, input, energy and trade-dependence edges retained "
            "in their original units and denominators."
        ),
        "edge_types": [
            "import_dependence",
            "export_dependence",
            "energy_dependence",
            "supplier_concentration",
            "input_dependency",
        ],
    },
    {
        "dimension_id": "dim:exposure.logistics",
        "label": "Logistics and access",
        "definition": (
            "Direct freight, route and border-access edges without inferring "
            "throughput, substitution or realized disruption."
        ),
        "edge_types": [
            "freight_dependence",
            "border_proximity",
            "route_dependency",
        ],
    },
    {
        "dimension_id": "dim:exposure.corporate_footprint",
        "label": "Corporate footprint",
        "definition": (
            "Direct ownership and operational-presence relationships, distinct "
            "from supply dependence or policy authority."
        ),
        "edge_types": ["ownership", "operational_presence"],
    },
    {
        "dimension_id": "dim:exposure.policy_legal",
        "label": "Policy and legal reach",
        "definition": (
            "Direct treaty, sanctions and policy-jurisdiction edges without "
            "interpreting legal effect or predicting enforcement."
        ),
        "edge_types": [
            "treaty_obligation",
            "sanctions_reach",
            "policy_jurisdiction",
        ],
    },
    {
        "dimension_id": "dim:exposure.digital_infrastructure",
        "label": "Digital and technology",
        "definition": (
            "Direct cyber and technology-dependence edges, kept separate from "
            "physical infrastructure and market outcomes."
        ),
        "edge_types": ["cyber_dependency", "technology_dependency"],
    },
)
_BASE_LIMITATIONS = (
    "absence_means_no_eligible_edge_in_release_not_no_real_world_exposure",
    "canonical_release_generation_is_not_external_availability_proof",
    "coverage_counts_are_not_aggregated_across_unlike_universes",
    "edge_confidence_is_not_probability",
    "edge_direction_is_not_shock_direction",
    "exposure_is_not_realized_loss",
    "freshness_is_source_policy_age_not_decision_materiality",
    "no_causal_attribution",
    "no_cross_unit_aggregation_or_scalar_score",
    "no_forecast_recommendation_or_advice",
    "requires_claim_bundle_before_non_synthetic_public_rendering",
    "structural_fingerprint_not_measured_decision_utility",
)


class ExposureDNAError(ValueError):
    """A fail-closed Exposure DNA refusal with a stable reason code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ExposureDNAError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("dna_json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    _fail("dna_json_non_finite")


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        _fail(code)
    resolved_root = root.resolve()
    candidate = resolved_root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("dna_contract_symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _inside_root(root: Path, path: Path, code: str) -> Path:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        _fail(code)
    return _safe_file(root, relative, code)


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("dna_contract_file_missing")


def _parse_day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _parse_time(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


def _date_effective(
    document: Mapping[str, Any],
    on_day: date,
    *,
    start_field: str,
    end_field: str,
) -> bool:
    if document["lifecycle"]["state"] != "active":
        return False
    start = document[start_field]
    end = document[end_field]
    if start is not None and _parse_day(start, "dna_effective_date_invalid") > on_day:
        return False
    return end is None or _parse_day(end, "dna_effective_date_invalid") >= on_day


def _load_contract(
    root: Path,
    registry_path: Path,
    release_day: date,
) -> tuple[dict[str, Any], str, Draft202012Validator, tuple[dict[str, Any], ...]]:
    registry_file = _inside_root(root, registry_path, "dna_registry_missing")
    _, registry, registry_sha = _read_json(registry_file, "dna_registry_invalid")
    if set(registry) != {
        "schema_version",
        "effective",
        "default_policy",
        "engine",
        "dimensions",
    }:
        _fail("dna_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("dna_registry_policy_invalid")
    if _parse_day(registry["effective"], "dna_registry_effective_invalid") > release_day:
        _fail("dna_registry_not_effective")

    row = registry["engine"]
    expected = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "effective",
        "superseded_on",
        "output_schema_id",
        "output_schema_version",
        "output_schema_path",
        "output_schema_sha256",
        "common_schema_path",
        "common_schema_sha256",
        "max_direct_edges",
        "allowed_target_entity_types",
        "freshness_policy",
    }
    if not isinstance(row, dict) or set(row) != expected:
        _fail("dna_registry_engine_invalid")
    if (
        row["method_id"] != _METHOD_ID
        or row["version"] != _METHOD_VERSION
        or row["output_schema_id"] != _OUTPUT_SCHEMA_ID
        or row["output_schema_version"] != "1.0.0"
        or row["output_schema_sha256"] != _OUTPUT_SCHEMA_SHA256
        or row["common_schema_sha256"] != _COMMON_SCHEMA_SHA256
        or row["max_direct_edges"] != _MAX_DIRECT_EDGES
        or tuple(row["allowed_target_entity_types"]) != _TARGET_TYPES
        or row["freshness_policy"] != _FRESHNESS_RULE
    ):
        _fail("dna_engine_identity_invalid")
    effective = _parse_day(row["effective"], "dna_engine_effective_invalid")
    if release_day < effective:
        _fail("dna_engine_not_effective")
    if row["superseded_on"] is not None and release_day >= _parse_day(
        row["superseded_on"], "dna_engine_superseded_invalid"
    ):
        _fail("dna_engine_superseded")
    implementation = _safe_file(root, row["implementation_path"], "dna_implementation_missing")
    if _sha(implementation) != row["implementation_sha256"] or _sha(
        Path(__file__).resolve()
    ) != row["implementation_sha256"]:
        _fail("dna_implementation_digest_mismatch")
    common_path = _safe_file(root, row["common_schema_path"], "dna_common_schema_missing")
    output_path = _safe_file(root, row["output_schema_path"], "dna_output_schema_missing")
    if _sha(common_path) != row["common_schema_sha256"]:
        _fail("dna_common_schema_digest_mismatch")
    if _sha(output_path) != row["output_schema_sha256"]:
        _fail("dna_output_schema_digest_mismatch")
    _, common, _ = _read_json(common_path, "dna_common_schema_invalid")
    _, output, _ = _read_json(output_path, "dna_output_schema_invalid")
    if output.get("$id") != _OUTPUT_SCHEMA_ID:
        _fail("dna_output_schema_id_mismatch")
    try:
        Draft202012Validator.check_schema(common)
        Draft202012Validator.check_schema(output)
    except SchemaError:
        _fail("dna_schema_meta_invalid")
    resources = Registry().with_resources(
        [
            (cast(str, common["$id"]), Resource.from_contents(common)),
            (cast(str, output["$id"]), Resource.from_contents(output)),
        ]
    )
    validator = Draft202012Validator(
        output,
        registry=resources,
        format_checker=FormatChecker(),
    )

    dimensions_raw = registry["dimensions"]
    if dimensions_raw != list(_DIMENSIONS):
        _fail("dna_dimension_registry_mismatch")
    dimensions = [dict(dimension) for dimension in _DIMENSIONS]
    assigned = [
        edge_type
        for dimension in dimensions
        for edge_type in cast(list[str], dimension["edge_types"])
    ]
    if sorted(assigned) != sorted(_EDGE_TYPES) or len(assigned) != len(set(assigned)):
        _fail("dna_dimension_partition_invalid")
    return cast(dict[str, Any], row), registry_sha, validator, tuple(dimensions)


def _source_age_policies(
    root: Path,
    rights_registry_path: Path,
    expected_sha: object,
) -> dict[str, int | None]:
    safe = _inside_root(root, rights_registry_path, "dna_rights_registry_missing")
    _, document, digest = _read_json(safe, "dna_rights_registry_invalid")
    if digest != expected_sha:
        _fail("dna_rights_registry_digest_mismatch")
    rows = document.get("sources")
    if not isinstance(rows, list):
        _fail("dna_rights_registry_invalid")
    result: dict[str, int | None] = {}
    for row in rows:
        if not isinstance(row, dict):
            _fail("dna_rights_registry_invalid")
        source_id = row.get("source_id")
        days = row.get("max_current_age_days")
        if (
            not isinstance(source_id, str)
            or source_id in result
            or (
                days is not None
                and (isinstance(days, bool) or not isinstance(days, int) or days < 1)
            )
        ):
            _fail("dna_rights_registry_invalid")
        result[source_id] = cast(Optional[int], days)
    return result


def _release_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "release_id": manifest["release_id"],
        "record_sha256": manifest["record_sha256"],
        "generated_at": manifest["generated_at"],
        "effective_date": manifest["effective_date"],
        "release_signer_id": manifest["release_signer_id"],
        "schema_registry_sha256": manifest["schema_registry_sha256"],
        "method_registry_sha256": manifest["method_registry_sha256"],
        "rights_registry_sha256": manifest["rights_registry_sha256"],
        "rights_signers_sha256": manifest["rights_signers_sha256"],
        "release_signers_sha256": manifest["release_signers_sha256"],
    }


def _contract_identity(row: Mapping[str, Any], registry_sha: str) -> dict[str, Any]:
    return {
        "schema_id": row["output_schema_id"],
        "schema_version": row["output_schema_version"],
        "schema_sha256": row["output_schema_sha256"],
        "common_schema_sha256": row["common_schema_sha256"],
        "dna_registry_sha256": registry_sha,
    }


def _method_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "method_id": row["method_id"],
        "version": row["version"],
        "implementation_sha256": row["implementation_sha256"],
    }


def _target_row(entity: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": entity["entity_id"],
        "record_sha256": entity["record_sha256"],
        "entity_type": entity["entity_type"],
        "lifecycle_state": entity["lifecycle"]["state"],
        "identity_status": entity["identity_status"],
        "effective_start": entity["effective_start"],
        "effective_end": entity["effective_end"],
        "parent_entity_ids": list(entity["parent_entity_ids"]),
        "jurisdiction_entity_ids": list(entity["jurisdiction_entity_ids"]),
        "evidence_ids": list(entity["provenance"]["evidence_ids"]),
    }


def _universe_rows(
    target_id: str,
    target_type: str,
    universes: Mapping[str, Mapping[str, Any]],
    release_day: date,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for universe in universes.values():
        if (
            universe["lifecycle"]["state"] != "active"
            or universe["entity_type"] != target_type
            or _parse_day(universe["reference_date"], "dna_universe_date_invalid")
            > release_day
        ):
            continue
        member = next(
            (item for item in universe["members"] if item["entity_id"] == target_id),
            None,
        )
        rows.append(
            {
                "universe_release_id": universe["universe_release_id"],
                "record_sha256": universe["record_sha256"],
                "reference_date": universe["reference_date"],
                "member_status": member["status"] if member else "not_listed",
                "reason_code": member["reason_code"] if member else None,
                "assessed_on": member["assessed_on"] if member else None,
                "counts": dict(universe["counts"]),
            }
        )
    return sorted(rows, key=lambda item: cast(str, item["universe_release_id"]))


def _freshness_row(
    edge: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    source_policies: Mapping[str, int | None],
    generated_at: datetime,
) -> dict[str, Any]:
    observed_at = _parse_time(edge["observed_at"], "dna_edge_observed_at_invalid")
    age_seconds = int((generated_at - observed_at).total_seconds())
    if age_seconds < 0:
        _fail("dna_edge_observed_after_release", cast(str, edge["edge_id"]))
    source_ids = sorted(
        {
            cast(str, evidence_by_id[evidence_id]["source_id"])
            for evidence_id in edge["evidence_ids"]
        }
    )
    policies = []
    unknown_policy = False
    thresholds: list[int] = []
    for source_id in source_ids:
        if source_id not in source_policies:
            _fail("dna_evidence_source_missing_from_rights_registry", source_id)
        days = source_policies[source_id]
        policies.append({"source_id": source_id, "max_current_age_days": days})
        if days is None:
            unknown_policy = True
        else:
            thresholds.append(days)
    threshold = None if unknown_policy or not thresholds else min(thresholds)
    if threshold is None:
        status = "unknown_policy"
    elif age_seconds > threshold * 86_400:
        status = "stale"
    else:
        status = "current"
    return {
        "basis": _FRESHNESS_RULE,
        "observed_at": edge["observed_at"],
        "observation_age_seconds": age_seconds,
        "max_current_age_days": threshold,
        "status": status,
        "source_policies": policies,
    }


def _edge_row(
    edge: Mapping[str, Any],
    target_id: str,
    entities: Mapping[str, Mapping[str, Any]],
    universes: Mapping[str, Mapping[str, Any]],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    source_policies: Mapping[str, int | None],
    generated_at: datetime,
) -> dict[str, Any]:
    source_id = cast(str, edge["source_entity_id"])
    target_edge_id = cast(str, edge["target_entity_id"])
    if source_id == target_id and target_edge_id == target_id:
        _fail("dna_self_edge_forbidden", cast(str, edge["edge_id"]))
    if source_id == target_id:
        orientation = "outgoing"
        counterpart_id = target_edge_id
    elif target_edge_id == target_id:
        orientation = "incoming"
        counterpart_id = source_id
    else:
        _fail("dna_edge_not_incident_to_target", cast(str, edge["edge_id"]))
    counterpart = entities[counterpart_id]
    universe = universes[edge["coverage_basis"]["universe_release_id"]]
    evidence_ids = list(edge["evidence_ids"])
    source_ids = sorted(
        {cast(str, evidence_by_id[evidence_id]["source_id"]) for evidence_id in evidence_ids}
    )
    return {
        "edge_id": edge["edge_id"],
        "record_sha256": edge["record_sha256"],
        "orientation": orientation,
        "source_entity_id": source_id,
        "target_entity_id": target_edge_id,
        "counterpart": {
            "entity_id": counterpart_id,
            "record_sha256": counterpart["record_sha256"],
            "entity_type": counterpart["entity_type"],
            "identity_status": counterpart["identity_status"],
        },
        "edge_type": edge["edge_type"],
        "exposure_direction": edge["exposure_direction"],
        "quantification_status": edge["quantification_status"],
        "magnitude": dict(edge["magnitude"]) if edge["magnitude"] is not None else None,
        "derivation_type": edge["derivation_type"],
        "effective_start": edge["effective_start"],
        "effective_end": edge["effective_end"],
        "observed_at": edge["observed_at"],
        "freshness": _freshness_row(
            edge, evidence_by_id, source_policies, generated_at
        ),
        "coverage": {
            "universe_release_id": universe["universe_release_id"],
            "universe_record_sha256": universe["record_sha256"],
            "universe_entity_type": universe["entity_type"],
            "reference_date": universe["reference_date"],
            "covered_entity_id": edge["coverage_basis"]["covered_entity_id"],
            "member_status": edge["coverage_basis"]["member_status"],
            "counts": dict(universe["counts"]),
        },
        "evidence_ids": evidence_ids,
        "source_ids": source_ids,
        "method": dict(edge["method"]),
        "confidence": dict(edge["confidence"]),
        "limitation_codes": list(edge["limitation_codes"]),
    }


def _dimension_rows(
    edge_rows: Sequence[Mapping[str, Any]],
    dimensions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for dimension in dimensions:
        edge_types = set(dimension["edge_types"])
        selected = [row for row in edge_rows if row["edge_type"] in edge_types]
        quantification = Counter(cast(str, row["quantification_status"]) for row in selected)
        freshness = Counter(cast(str, row["freshness"]["status"]) for row in selected)
        rows.append(
            {
                "dimension_id": dimension["dimension_id"],
                "label": dimension["label"],
                "definition": dimension["definition"],
                "edge_types": list(dimension["edge_types"]),
                "edge_ids": [row["edge_id"] for row in selected],
                "counts": {
                    "edges": len(selected),
                    "quantified": quantification["quantified"],
                    "qualitative": quantification["qualitative"],
                    "unknown": quantification["unknown"],
                    "current": freshness["current"],
                    "stale": freshness["stale"],
                    "unknown_freshness": freshness["unknown_policy"],
                },
            }
        )
    return rows


def _gaps(
    universes: Sequence[Mapping[str, Any]],
    edge_rows: Sequence[Mapping[str, Any]],
    dimensions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "target_universe_not_declared": len(universes) == 0,
        "target_universe_not_included_ids": [
            row["universe_release_id"]
            for row in universes
            if row["member_status"] != "included"
        ],
        "unknown_quantification_edge_ids": [
            row["edge_id"]
            for row in edge_rows
            if row["quantification_status"] == "unknown"
        ],
        "stale_edge_ids": [
            row["edge_id"]
            for row in edge_rows
            if row["freshness"]["status"] == "stale"
        ],
        "unknown_freshness_edge_ids": [
            row["edge_id"]
            for row in edge_rows
            if row["freshness"]["status"] == "unknown_policy"
        ],
        "missing_dimension_ids": [
            row["dimension_id"] for row in dimensions if not row["edge_ids"]
        ],
    }


def _validate_document(document: Mapping[str, Any], validator: Draft202012Validator) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("dna_output_schema_invalid", f"{path or '/'}:{error.validator}")
    if canonical.canonical_record_sha256(document) != document["record_sha256"]:
        _fail("dna_output_digest_mismatch")


def _validate_snapshot(
    document: Mapping[str, Any],
    validator: Draft202012Validator,
    dimensions: Sequence[Mapping[str, Any]],
) -> None:
    _validate_document(document, validator)
    if document["object_type"] != "exposure_dna_snapshot":
        _fail("dna_snapshot_object_type_invalid")
    if (
        document["query"]["target_entity_id"] != document["target"]["entity_id"]
        or document["limitations"] != sorted(_BASE_LIMITATIONS)
    ):
        _fail("dna_snapshot_identity_invalid")
    universes = document["target_universes"]
    universe_ids = [row["universe_release_id"] for row in universes]
    if universe_ids != sorted(universe_ids) or len(universe_ids) != len(set(universe_ids)):
        _fail("dna_snapshot_universe_order_invalid")
    edges = document["edges"]
    edge_ids = [row["edge_id"] for row in edges]
    expected_edges = sorted(edges, key=lambda row: (row["orientation"], row["edge_type"], row["edge_id"]))
    if len(edge_ids) != len(set(edge_ids)) or edges != expected_edges:
        _fail("dna_snapshot_edge_order_invalid")
    target_id = document["target"]["entity_id"]
    for edge in edges:
        policies = edge["freshness"]["source_policies"]
        policy_sources = [row["source_id"] for row in policies]
        if (
            policy_sources != sorted(policy_sources)
            or len(policy_sources) != len(set(policy_sources))
            or edge["source_ids"] != policy_sources
            or edge["observed_at"] != edge["freshness"]["observed_at"]
        ):
            _fail("dna_snapshot_source_policy_invalid", cast(str, edge["edge_id"]))
        policy_days = [row["max_current_age_days"] for row in policies]
        expected_threshold = (
            None
            if any(days is None for days in policy_days)
            else min(cast(list[int], policy_days))
        )
        threshold = edge["freshness"]["max_current_age_days"]
        age = edge["freshness"]["observation_age_seconds"]
        expected_status = (
            "unknown_policy"
            if threshold is None
            else "stale"
            if age > threshold * 86_400
            else "current"
        )
        if threshold != expected_threshold or edge["freshness"]["status"] != expected_status:
            _fail("dna_snapshot_freshness_invalid", cast(str, edge["edge_id"]))
        if edge["orientation"] == "incoming":
            expected_counterpart = edge["source_entity_id"]
            incident = edge["target_entity_id"] == target_id
        else:
            expected_counterpart = edge["target_entity_id"]
            incident = edge["source_entity_id"] == target_id
        if not incident or edge["counterpart"]["entity_id"] != expected_counterpart:
            _fail("dna_snapshot_edge_incidence_invalid", cast(str, edge["edge_id"]))
    expected_dimensions = _dimension_rows(edges, dimensions)
    if document["dimensions"] != expected_dimensions:
        _fail("dna_snapshot_dimensions_invalid")
    expected_gaps = _gaps(document["target_universes"], edges, expected_dimensions)
    if document["gaps"] != expected_gaps:
        _fail("dna_snapshot_gaps_invalid")
    counts = document["counts"]
    orientation = Counter(cast(str, row["orientation"]) for row in edges)
    quantification = Counter(cast(str, row["quantification_status"]) for row in edges)
    freshness = Counter(cast(str, row["freshness"]["status"]) for row in edges)
    expected_counts = {
        "direct_edges": len(edges),
        "incoming_edges": orientation["incoming"],
        "outgoing_edges": orientation["outgoing"],
        "quantified_edges": quantification["quantified"],
        "qualitative_edges": quantification["qualitative"],
        "unknown_edges": quantification["unknown"],
        "current_edges": freshness["current"],
        "stale_edges": freshness["stale"],
        "unknown_freshness_edges": freshness["unknown_policy"],
        "target_universes": len(document["target_universes"]),
    }
    if counts != expected_counts:
        _fail("dna_snapshot_counts_invalid")
    expected_status = "fingerprint_present" if edges else "fingerprint_empty"
    if (
        document["result"]["status"] != expected_status
        or document["result"]["scalar_score_computed"] is not False
    ):
        _fail("dna_snapshot_result_invalid")


def build_exposure_dna(
    manifest_path: Path,
    target_entity_id: str,
    *,
    root: Path = canonical.ROOT,
    schema_registry_path: Path = canonical.SCHEMA_REGISTRY,
    rights_registry_path: Path = canonical.RIGHTS_REGISTRY,
    rights_signers_path: Path = canonical.RIGHTS_SIGNERS,
    method_registry_path: Path = canonical.METHOD_REGISTRY,
    release_signers_path: Path = canonical.RELEASE_SIGNERS,
    dna_registry_path: Path = DNA_REGISTRY,
) -> dict[str, Any]:
    """Build one non-aggregated Exposure DNA snapshot."""

    validated = canonical.load_validated_release(
        manifest_path,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
    )
    manifest = validated.manifest
    objects = validated.objects
    entities = objects["entity"]
    if target_entity_id not in entities:
        _fail("dna_target_not_in_release")
    target = entities[target_entity_id]
    target_type = cast(str, target["entity_type"])
    if target_type not in _TARGET_TYPES:
        _fail("dna_target_type_not_supported", target_type)
    release_day = _parse_day(manifest["effective_date"], "dna_release_date_invalid")
    generated_at = _parse_time(manifest["generated_at"], "dna_release_generated_invalid")
    if not _date_effective(
        target,
        release_day,
        start_field="effective_start",
        end_field="effective_end",
    ):
        _fail("dna_target_not_effective")
    contract, registry_sha, validator, dimensions = _load_contract(
        root, dna_registry_path, release_day
    )
    source_policies = _source_age_policies(
        root, rights_registry_path, manifest["rights_registry_sha256"]
    )

    universes = objects["universe_release"]
    effective_entities = {
        entity_id
        for entity_id, entity in entities.items()
        if _date_effective(
            entity,
            release_day,
            start_field="effective_start",
            end_field="effective_end",
        )
    }
    eligible_universes = {
        universe_id
        for universe_id, universe in universes.items()
        if universe["lifecycle"]["state"] == "active"
        and _parse_day(universe["reference_date"], "dna_universe_date_invalid")
        <= release_day
    }
    edge_rows = []
    for edge in objects["exposure_edge"].values():
        if not _date_effective(
            edge,
            release_day,
            start_field="effective_start",
            end_field="effective_end",
        ):
            continue
        source_id = cast(str, edge["source_entity_id"])
        target_edge_id = cast(str, edge["target_entity_id"])
        if source_id not in effective_entities or target_edge_id not in effective_entities:
            _fail("dna_active_edge_endpoint_not_effective", cast(str, edge["edge_id"]))
        universe_id = cast(str, edge["coverage_basis"]["universe_release_id"])
        if universe_id not in eligible_universes:
            _fail("dna_active_edge_universe_not_effective", cast(str, edge["edge_id"]))
        if target_entity_id not in (source_id, target_edge_id):
            continue
        edge_rows.append(
            _edge_row(
                edge,
                target_entity_id,
                entities,
                universes,
                objects["evidence_item"],
                source_policies,
                generated_at,
            )
        )
    if len(edge_rows) > contract["max_direct_edges"]:
        _fail("dna_direct_edge_bound_exceeded")
    edge_rows.sort(key=lambda row: (row["orientation"], row["edge_type"], row["edge_id"]))
    target_universes = _universe_rows(
        target_entity_id, target_type, universes, release_day
    )
    dimension_rows = _dimension_rows(edge_rows, dimensions)
    gaps = _gaps(target_universes, edge_rows, dimension_rows)
    orientation = Counter(cast(str, row["orientation"]) for row in edge_rows)
    quantification = Counter(cast(str, row["quantification_status"]) for row in edge_rows)
    freshness = Counter(cast(str, row["freshness"]["status"]) for row in edge_rows)
    document = canonical.seal_record(
        {
            "object_type": "exposure_dna_snapshot",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "release": _release_identity(manifest),
            "contract": _contract_identity(contract, registry_sha),
            "method": _method_identity(contract),
            "query": {
                "target_entity_id": target_entity_id,
                "selection_rule": _SNAPSHOT_SELECTION,
                "freshness_rule": _FRESHNESS_RULE,
            },
            "target": _target_row(target),
            "target_universes": target_universes,
            "edges": edge_rows,
            "dimensions": dimension_rows,
            "gaps": gaps,
            "counts": {
                "direct_edges": len(edge_rows),
                "incoming_edges": orientation["incoming"],
                "outgoing_edges": orientation["outgoing"],
                "quantified_edges": quantification["quantified"],
                "qualitative_edges": quantification["qualitative"],
                "unknown_edges": quantification["unknown"],
                "current_edges": freshness["current"],
                "stale_edges": freshness["stale"],
                "unknown_freshness_edges": freshness["unknown_policy"],
                "target_universes": len(target_universes),
            },
            "result": {
                "status": "fingerprint_present" if edge_rows else "fingerprint_empty",
                "scalar_score_computed": False,
                "public_claim_state": "requires_claim_bundle",
            },
            "limitations": sorted(_BASE_LIMITATIONS),
        }
    )
    _validate_snapshot(document, validator, dimensions)
    return cast(dict[str, Any], document)


def _changed_aspects(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    aspects = []
    if any(
        before[key] != after[key]
        for key in (
            "orientation",
            "source_entity_id",
            "target_entity_id",
            "counterpart",
            "edge_type",
            "exposure_direction",
            "derivation_type",
        )
    ):
        aspects.append("semantics")
    if any(before[key] != after[key] for key in ("quantification_status", "magnitude")):
        aspects.append("quantification")
    if any(before[key] != after[key] for key in ("effective_start", "effective_end")):
        aspects.append("effective_interval")
    if any(before[key] != after[key] for key in ("observed_at", "freshness")):
        aspects.append("freshness")
    if before["coverage"] != after["coverage"]:
        aspects.append("coverage")
    if before["confidence"] != after["confidence"]:
        aspects.append("confidence")
    if any(
        before[key] != after[key]
        for key in ("evidence_ids", "source_ids", "method")
    ):
        aspects.append("evidence_or_method")
    if before["limitation_codes"] != after["limitation_codes"]:
        aspects.append("limitations")
    return [aspect for aspect in _CHANGE_ASPECT_ORDER if aspect in aspects]


def _gap_tokens(snapshot: Mapping[str, Any]) -> list[str]:
    gaps = snapshot["gaps"]
    tokens = []
    if gaps["target_universe_not_declared"]:
        tokens.append("target_universe_not_declared")
    tokens.extend(
        f"target_universe_not_included:{item}"
        for item in gaps["target_universe_not_included_ids"]
    )
    tokens.extend(
        f"unknown_quantification:{item}"
        for item in gaps["unknown_quantification_edge_ids"]
    )
    tokens.extend(f"stale_edge:{item}" for item in gaps["stale_edge_ids"])
    tokens.extend(
        f"unknown_freshness:{item}" for item in gaps["unknown_freshness_edge_ids"]
    )
    tokens.extend(
        f"missing_dimension:{item}" for item in gaps["missing_dimension_ids"]
    )
    return sorted(tokens)


def _validate_delta(
    document: Mapping[str, Any],
    validator: Draft202012Validator,
) -> None:
    _validate_document(document, validator)
    if document["object_type"] != "exposure_dna_delta":
        _fail("dna_delta_object_type_invalid")
    changes = document["edge_changes"]
    added = [row["edge_id"] for row in changes["added"]]
    removed = [row["edge_id"] for row in changes["removed"]]
    revised = [row["edge_id"] for row in changes["revised"]]
    unchanged = changes["unchanged_edge_ids"]
    if (
        added != sorted(added)
        or removed != sorted(removed)
        or revised != sorted(revised)
        or unchanged != sorted(unchanged)
        or len(set(added + removed + revised + unchanged))
        != len(added + removed + revised + unchanged)
        or any(
            row["changed_aspects"]
            != [item for item in _CHANGE_ASPECT_ORDER if item in row["changed_aspects"]]
            or not row["changed_aspects"]
            for row in changes["revised"]
        )
    ):
        _fail("dna_delta_change_partition_invalid")
    gap_changes = document["gap_changes"]
    opened = gap_changes["opened"]
    resolved = gap_changes["resolved"]
    persistent = gap_changes["persistent"]
    if (
        opened != sorted(opened)
        or resolved != sorted(resolved)
        or persistent != sorted(persistent)
        or len(set(opened + resolved + persistent))
        != len(opened + resolved + persistent)
    ):
        _fail("dna_delta_gap_partition_invalid")
    dimension_ids = [row["dimension_id"] for row in document["dimension_changes"]]
    if dimension_ids != [row["dimension_id"] for row in _DIMENSIONS]:
        _fail("dna_delta_dimensions_invalid")
    for row in document["dimension_changes"]:
        for side in ("before_counts", "after_counts"):
            values = row[side]
            if (
                values["edges"]
                != values["quantified"] + values["qualitative"] + values["unknown"]
                or values["edges"]
                != values["current"] + values["stale"] + values["unknown_freshness"]
            ):
                _fail("dna_delta_dimension_counts_invalid")
    counts = document["counts"]
    if counts != {
        "added_edges": len(added),
        "removed_edges": len(removed),
        "revised_edges": len(revised),
        "unchanged_edges": len(unchanged),
        "opened_gaps": len(opened),
        "resolved_gaps": len(resolved),
    }:
        _fail("dna_delta_counts_invalid")
    changed = len(added) + len(removed) + len(revised) > 0
    expected_limitations = sorted(
        {*_BASE_LIMITATIONS, "delta_is_release_difference_not_real_world_change_attribution"}
    )
    if (
        document["query"]["target_entity_id"] != document["target"]["entity_id"]
        or document["limitations"] != expected_limitations
        or document["result"]["status"] != ("changed" if changed else "unchanged")
    ):
        _fail("dna_delta_result_invalid")


def compare_exposure_dna(
    before_manifest_path: Path,
    after_manifest_path: Path,
    target_entity_id: str,
    *,
    before_root: Path = canonical.ROOT,
    after_root: Path = canonical.ROOT,
) -> dict[str, Any]:
    """Compare the same target across two independently validated releases."""

    def snapshot(manifest: Path, root: Path) -> dict[str, Any]:
        return build_exposure_dna(
            manifest,
            target_entity_id,
            root=root,
            schema_registry_path=root / "governance" / "canonical_schema_registry.json",
            rights_registry_path=root / "governance" / "source_rights_registry.json",
            rights_signers_path=root / "governance" / "rights_signers.json",
            method_registry_path=root / "governance" / "canonical_method_registry.json",
            release_signers_path=root / "governance" / "release_signers.json",
            dna_registry_path=root / "governance" / "exposure_dna_registry.json",
        )

    before = snapshot(before_manifest_path, before_root)
    after = snapshot(after_manifest_path, after_root)
    before_time = _parse_time(before["release"]["generated_at"], "dna_before_time_invalid")
    after_time = _parse_time(after["release"]["generated_at"], "dna_after_time_invalid")
    if after_time <= before_time:
        _fail("dna_comparison_order_invalid")
    before_day = _parse_day(before["release"]["effective_date"], "dna_before_day_invalid")
    after_day = _parse_day(after["release"]["effective_date"], "dna_after_day_invalid")
    if after_day < before_day:
        _fail("dna_comparison_effective_date_reversed")
    if before["target"]["entity_type"] != after["target"]["entity_type"]:
        _fail("dna_comparison_target_type_changed")

    before_edges = {row["edge_id"]: row for row in before["edges"]}
    after_edges = {row["edge_id"]: row for row in after["edges"]}
    added_ids = sorted(set(after_edges) - set(before_edges))
    removed_ids = sorted(set(before_edges) - set(after_edges))
    shared_ids = sorted(set(before_edges) & set(after_edges))
    revised_ids = [
        edge_id
        for edge_id in shared_ids
        if before_edges[edge_id]["record_sha256"] != after_edges[edge_id]["record_sha256"]
    ]
    unchanged_ids = [edge_id for edge_id in shared_ids if edge_id not in revised_ids]
    added = [
        {"edge_id": edge_id, "after_record_sha256": after_edges[edge_id]["record_sha256"]}
        for edge_id in added_ids
    ]
    removed = [
        {"edge_id": edge_id, "before_record_sha256": before_edges[edge_id]["record_sha256"]}
        for edge_id in removed_ids
    ]
    revised = []
    for edge_id in revised_ids:
        aspects = _changed_aspects(before_edges[edge_id], after_edges[edge_id])
        if not aspects:
            _fail("dna_revised_edge_has_no_visible_change", edge_id)
        revised.append(
            {
                "edge_id": edge_id,
                "before_record_sha256": before_edges[edge_id]["record_sha256"],
                "after_record_sha256": after_edges[edge_id]["record_sha256"],
                "changed_aspects": aspects,
            }
        )
    before_dimensions = {row["dimension_id"]: row for row in before["dimensions"]}
    after_dimensions = {row["dimension_id"]: row for row in after["dimensions"]}
    dimension_changes = [
        {
            "dimension_id": dimension_id,
            "before_counts": before_dimensions[dimension_id]["counts"],
            "after_counts": after_dimensions[dimension_id]["counts"],
        }
        for dimension_id in before_dimensions
    ]
    before_gaps = set(_gap_tokens(before))
    after_gaps = set(_gap_tokens(after))
    gap_changes = {
        "opened": sorted(after_gaps - before_gaps),
        "resolved": sorted(before_gaps - after_gaps),
        "persistent": sorted(before_gaps & after_gaps),
    }
    changed = bool(added or removed or revised)

    contract, registry_sha, validator, _ = _load_contract(
        after_root,
        after_root / "governance" / "exposure_dna_registry.json",
        after_day,
    )
    document = canonical.seal_record(
        {
            "object_type": "exposure_dna_delta",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "contract": _contract_identity(contract, registry_sha),
            "method": _method_identity(contract),
            "query": {
                "target_entity_id": target_entity_id,
                "comparison_rule": _COMPARISON_RULE,
            },
            "target": {
                "entity_id": target_entity_id,
                "entity_type": after["target"]["entity_type"],
                "before_record_sha256": before["target"]["record_sha256"],
                "after_record_sha256": after["target"]["record_sha256"],
                "record_changed": before["target"]["record_sha256"]
                != after["target"]["record_sha256"],
            },
            "before": {
                "release": before["release"],
                "snapshot_record_sha256": before["record_sha256"],
            },
            "after": {
                "release": after["release"],
                "snapshot_record_sha256": after["record_sha256"],
            },
            "edge_changes": {
                "added": added,
                "removed": removed,
                "revised": revised,
                "unchanged_edge_ids": unchanged_ids,
            },
            "dimension_changes": dimension_changes,
            "gap_changes": gap_changes,
            "counts": {
                "added_edges": len(added),
                "removed_edges": len(removed),
                "revised_edges": len(revised),
                "unchanged_edges": len(unchanged_ids),
                "opened_gaps": len(gap_changes["opened"]),
                "resolved_gaps": len(gap_changes["resolved"]),
            },
            "result": {
                "status": "changed" if changed else "unchanged",
                "scalar_score_computed": False,
                "causal_interpretation_performed": False,
            },
            "limitations": sorted(
                {
                    *_BASE_LIMITATIONS,
                    "delta_is_release_difference_not_real_world_change_attribution",
                }
            ),
        }
    )
    _validate_delta(document, validator)
    return cast(dict[str, Any], document)


def _emit_refusal(stage: str, reason: str) -> None:
    print(
        json.dumps(
            {"status": "refused", "stage": stage, "reason": reason},
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build signed-release Exposure DNA")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("manifest", type=Path)
    snapshot_parser.add_argument("target_entity_id")
    snapshot_parser.add_argument("--root", type=Path, default=ROOT)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("before_manifest", type=Path)
    compare_parser.add_argument("after_manifest", type=Path)
    compare_parser.add_argument("target_entity_id")
    compare_parser.add_argument("--before-root", type=Path, default=ROOT)
    compare_parser.add_argument("--after-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            root = args.root
            result = build_exposure_dna(
                args.manifest,
                args.target_entity_id,
                root=root,
                schema_registry_path=root / "governance" / "canonical_schema_registry.json",
                rights_registry_path=root / "governance" / "source_rights_registry.json",
                rights_signers_path=root / "governance" / "rights_signers.json",
                method_registry_path=root / "governance" / "canonical_method_registry.json",
                release_signers_path=root / "governance" / "release_signers.json",
                dna_registry_path=root / "governance" / "exposure_dna_registry.json",
            )
        else:
            result = compare_exposure_dna(
                args.before_manifest,
                args.after_manifest,
                args.target_entity_id,
                before_root=args.before_root,
                after_root=args.after_root,
            )
    except canonical.CanonicalObjectError as exc:
        _emit_refusal("canonical_release", exc.code)
        raise SystemExit(2) from None
    except ExposureDNAError as exc:
        _emit_refusal("exposure_dna", exc.code)
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
