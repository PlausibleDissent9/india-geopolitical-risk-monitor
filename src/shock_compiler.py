"""Compile bounded shock assumptions over signed exposure paths.

The compiler is a deterministic stress-test engine, not a forecasting model.
It revalidates a signed canonical release, asks the registered exposure graph
for stored-direction paths, and applies only three registered interval
transforms.  A numeric path is permitted only when it is one hop, the edge has
an interval-valued magnitude in an explicitly supported unit, and every input
is carried into the result.  Every other path remains visible but abstains.

Scenario magnitudes, substitution fractions and buffers are hypothetical user
inputs.  They never become facts, probabilities, causal effects, advice or a
scalar risk score.  Non-synthetic public rendering additionally requires a
separate claim bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical
from src import exposure_graph

ROOT = Path(__file__).resolve().parents[1]
SHOCK_REGISTRY = ROOT / "governance" / "shock_compiler_registry.json"

_METHOD_ID = "method:igrm.shock_compiler"
_METHOD_VERSION = "1.0.0"
_INPUT_SCHEMA_ID = "https://igrm.in/schemas/shock-scenario.schema.json"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/shock-compilation.schema.json"
_INPUT_SCHEMA_SHA256 = "01c242e74ba84b77f94e0772d6c08606fc6e2c70408074a71e7cf6fb712e914d"
_OUTPUT_SCHEMA_SHA256 = "f5391b08f226d1292213a63c07e742798d47690a5f94c9164f9b095a7416abe1"
_COMMON_SCHEMA_SHA256 = "56e167e287f4d670ac654ac5118d6b9688c801518038e5ac2f3ec55bca9f83d1"
_EXPOSURE_TRAVERSAL_SCHEMA_SHA256 = (
    "ad0ff5d1988f05b0368bef4bb69e1f916357f19b14c0066f00be1a1553491f69"
)
_MAX_DURATION_DAYS = 365
_MAX_SUBSTITUTIONS = 20
_MAX_BUFFERS = 20
_SUPPORTED_EDGE_UNITS = (
    "percent_of_import_volume",
    "percent_of_input_volume",
    "percent_of_procurement_value",
    "percent_of_routed_volume",
)
_TRANSFORMS = (
    {
        "transform_id": "transform:shock.gross_affected_share",
        "equation": "edge_interval * shock_percent / 100",
    },
    {
        "transform_id": "transform:shock.residual_after_substitution",
        "equation": "gross_interval * (1 - substitution_percent / 100)",
    },
    {
        "transform_id": "transform:shock.residual_duration",
        "equation": "max(0, shock_duration - buffer_duration)",
    },
)
_SCENARIO_LIMITATIONS = (
    "not_a_forecast",
    "not_a_probability_distribution",
    "not_advice_or_recommendation",
    "not_causal_attribution",
    "scenario_values_are_hypothetical_assumptions",
)
_OUTPUT_LIMITATIONS = (
    "bounded_scenario_not_forecast",
    "edge_magnitudes_retain_original_denominators",
    "event_status_not_ground_truth",
    "no_advice_or_recommendation",
    "no_cross_unit_aggregation_or_scalar_score",
    "path_search_is_bounded",
    "requires_claim_bundle_before_non_synthetic_public_rendering",
    "scenario_values_are_not_probabilities",
    "stored_edge_direction_only",
    "structural_paths_are_not_causal_attribution",
    "unsupported_propagation_abstains",
)
_GUARDRAILS = {
    "forecast_performed": False,
    "probability_assigned": False,
    "causal_attribution_performed": False,
    "recommendation_generated": False,
    "cross_unit_aggregation_performed": False,
}


class ShockCompilerError(ValueError):
    """A fail-closed compiler refusal with a stable non-content code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ShockCompilerError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("shock_json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    _fail("shock_json_non_finite")


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
            _fail("shock_contract_symlink_forbidden", relative)
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
        _fail("shock_contract_file_missing")


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


def _schema_validator(
    common: Mapping[str, Any],
    schema: Mapping[str, Any],
    references: Sequence[Mapping[str, Any]] = (),
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(common)
        Draft202012Validator.check_schema(schema)
        for reference in references:
            Draft202012Validator.check_schema(reference)
    except SchemaError:
        _fail("shock_schema_meta_invalid")
    resources = Registry().with_resources(
        (
            (cast(str, common["$id"]), Resource.from_contents(common)),
            (cast(str, schema["$id"]), Resource.from_contents(schema)),
            *(
                (cast(str, reference["$id"]), Resource.from_contents(reference))
                for reference in references
            ),
        )
    )
    return Draft202012Validator(
        schema,
        registry=resources,
        format_checker=FormatChecker(),
    )


def _load_contract(
    root: Path,
    registry_path: Path,
    release_day: date,
) -> tuple[
    dict[str, Any],
    str,
    Draft202012Validator,
    Draft202012Validator,
    tuple[dict[str, str], ...],
]:
    registry_file = _inside_root(root, registry_path, "shock_registry_missing")
    _, registry, registry_sha = _read_json(registry_file, "shock_registry_invalid")
    if set(registry) != {
        "schema_version",
        "effective",
        "default_policy",
        "engine",
        "transforms",
    }:
        _fail("shock_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("shock_registry_policy_invalid")
    if _parse_day(registry["effective"], "shock_registry_effective_invalid") > release_day:
        _fail("shock_registry_not_effective")

    row = registry["engine"]
    expected = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "effective",
        "superseded_on",
        "input_schema_id",
        "input_schema_version",
        "input_schema_path",
        "input_schema_sha256",
        "output_schema_id",
        "output_schema_version",
        "output_schema_path",
        "output_schema_sha256",
        "common_schema_path",
        "common_schema_sha256",
        "exposure_traversal_schema_path",
        "exposure_traversal_schema_sha256",
        "exposure_graph_implementation_path",
        "exposure_graph_implementation_sha256",
        "exposure_projection_registry_path",
        "exposure_projection_registry_sha256",
        "max_duration_days",
        "max_substitutions",
        "max_buffers",
        "supported_edge_units",
    }
    if not isinstance(row, dict) or set(row) != expected:
        _fail("shock_registry_engine_invalid")
    if (
        row["method_id"] != _METHOD_ID
        or row["version"] != _METHOD_VERSION
        or row["input_schema_id"] != _INPUT_SCHEMA_ID
        or row["input_schema_version"] != "1.0.0"
        or row["input_schema_sha256"] != _INPUT_SCHEMA_SHA256
        or row["output_schema_id"] != _OUTPUT_SCHEMA_ID
        or row["output_schema_version"] != "1.0.0"
        or row["output_schema_sha256"] != _OUTPUT_SCHEMA_SHA256
        or row["common_schema_sha256"] != _COMMON_SCHEMA_SHA256
        or row["exposure_traversal_schema_sha256"]
        != _EXPOSURE_TRAVERSAL_SCHEMA_SHA256
        or row["max_duration_days"] != _MAX_DURATION_DAYS
        or row["max_substitutions"] != _MAX_SUBSTITUTIONS
        or row["max_buffers"] != _MAX_BUFFERS
        or tuple(row["supported_edge_units"]) != _SUPPORTED_EDGE_UNITS
    ):
        _fail("shock_engine_identity_invalid")
    effective = _parse_day(row["effective"], "shock_engine_effective_invalid")
    if release_day < effective:
        _fail("shock_engine_not_effective")
    if row["superseded_on"] is not None and release_day >= _parse_day(
        row["superseded_on"], "shock_engine_superseded_invalid"
    ):
        _fail("shock_engine_superseded")

    implementation = _safe_file(
        root, row["implementation_path"], "shock_implementation_missing"
    )
    if _sha(implementation) != row["implementation_sha256"] or _sha(
        Path(__file__).resolve()
    ) != row["implementation_sha256"]:
        _fail("shock_implementation_digest_mismatch")
    graph_path = _safe_file(
        root,
        row["exposure_graph_implementation_path"],
        "shock_exposure_graph_missing",
    )
    if (
        _sha(graph_path) != row["exposure_graph_implementation_sha256"]
        or _sha(Path(exposure_graph.__file__).resolve())
        != row["exposure_graph_implementation_sha256"]
    ):
        _fail("shock_exposure_graph_digest_mismatch")
    projection_registry_path = _safe_file(
        root,
        row["exposure_projection_registry_path"],
        "shock_projection_registry_missing",
    )
    if (
        _sha(projection_registry_path)
        != row["exposure_projection_registry_sha256"]
        or _sha(exposure_graph.PROJECTION_REGISTRY)
        != row["exposure_projection_registry_sha256"]
    ):
        _fail("shock_projection_registry_digest_mismatch")

    common_path = _safe_file(root, row["common_schema_path"], "shock_common_schema_missing")
    input_path = _safe_file(root, row["input_schema_path"], "shock_input_schema_missing")
    output_path = _safe_file(root, row["output_schema_path"], "shock_output_schema_missing")
    traversal_schema_path = _safe_file(
        root,
        row["exposure_traversal_schema_path"],
        "shock_exposure_traversal_schema_missing",
    )
    if _sha(common_path) != row["common_schema_sha256"]:
        _fail("shock_common_schema_digest_mismatch")
    if _sha(input_path) != row["input_schema_sha256"]:
        _fail("shock_input_schema_digest_mismatch")
    if _sha(output_path) != row["output_schema_sha256"]:
        _fail("shock_output_schema_digest_mismatch")
    if _sha(traversal_schema_path) != row["exposure_traversal_schema_sha256"]:
        _fail("shock_exposure_traversal_schema_digest_mismatch")
    _, common, _ = _read_json(common_path, "shock_common_schema_invalid")
    _, input_schema, _ = _read_json(input_path, "shock_input_schema_invalid")
    _, output_schema, _ = _read_json(output_path, "shock_output_schema_invalid")
    _, traversal_schema, _ = _read_json(
        traversal_schema_path, "shock_exposure_traversal_schema_invalid"
    )
    if input_schema.get("$id") != _INPUT_SCHEMA_ID or output_schema.get("$id") != _OUTPUT_SCHEMA_ID:
        _fail("shock_schema_id_mismatch")

    raw_transforms = registry["transforms"]
    if raw_transforms != list(_TRANSFORMS):
        _fail("shock_transform_registry_mismatch")
    transform_ids = [item["transform_id"] for item in raw_transforms]
    if transform_ids != sorted(transform_ids) or len(transform_ids) != len(set(transform_ids)):
        _fail("shock_transform_registry_order_invalid")
    return (
        cast(dict[str, Any], row),
        registry_sha,
        _schema_validator(common, input_schema),
        _schema_validator(common, output_schema, (input_schema, traversal_schema)),
        tuple(cast(list[dict[str, str]], raw_transforms)),
    )


def _schema_check(
    document: Mapping[str, Any],
    validator: Draft202012Validator,
    code: str,
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail(code, f"{path or '/'}:{error.validator}")


def _release_binding(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "release_id": manifest["release_id"],
        "record_sha256": manifest["record_sha256"],
        "generated_at": manifest["generated_at"],
        "effective_date": manifest["effective_date"],
    }


def _release_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_release_binding(manifest),
        "release_signer_id": manifest["release_signer_id"],
        "schema_registry_sha256": manifest["schema_registry_sha256"],
        "method_registry_sha256": manifest["method_registry_sha256"],
        "rights_registry_sha256": manifest["rights_registry_sha256"],
        "rights_signers_sha256": manifest["rights_signers_sha256"],
        "release_signers_sha256": manifest["release_signers_sha256"],
    }


def _interval_is_strict(interval: Mapping[str, Any]) -> bool:
    return cast(float, interval["lower"]) < cast(float, interval["upper"])


def _assumption_identity(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], row["assumption"])


def _validate_scenario(
    scenario: Mapping[str, Any],
    manifest: Mapping[str, Any],
    validator: Draft202012Validator,
) -> None:
    _schema_check(scenario, validator, "shock_scenario_schema_invalid")
    if canonical.canonical_record_sha256(scenario) != scenario["record_sha256"]:
        _fail("shock_scenario_digest_mismatch")
    if scenario["release"] != _release_binding(manifest):
        _fail("shock_scenario_release_mismatch")
    knowledge_cutoff = _parse_time(
        scenario["knowledge_cutoff"], "shock_knowledge_cutoff_invalid"
    )
    release_generated = _parse_time(
        manifest["generated_at"], "shock_release_generated_invalid"
    )
    created_at = _parse_time(scenario["created_at"], "shock_created_at_invalid")
    if knowledge_cutoff != release_generated or created_at < knowledge_cutoff:
        _fail("shock_temporal_binding_invalid")

    shock = scenario["shock"]
    magnitude = shock["magnitude"]
    duration = shock["duration"]
    start = _parse_day(shock["effective_start"], "shock_effective_start_invalid")
    end = _parse_day(shock["effective_end"], "shock_effective_end_invalid")
    release_day = _parse_day(manifest["effective_date"], "shock_release_day_invalid")
    if start < release_day or end < start:
        _fail("shock_effective_window_invalid")
    window_days = (end - start).days + 1
    if (
        not _interval_is_strict(magnitude)
        or magnitude["lower"] <= 0
        or magnitude["upper"] > 100
        or not _interval_is_strict(duration)
        or duration["upper"] > _MAX_DURATION_DAYS
        or window_days != duration["upper"]
    ):
        _fail("shock_primary_interval_invalid")

    substitutions = scenario["substitutions"]
    buffers = scenario["buffers"]
    if len(substitutions) > _MAX_SUBSTITUTIONS or len(buffers) > _MAX_BUFFERS:
        _fail("shock_assumption_bound_exceeded")
    if substitutions != sorted(
        substitutions, key=lambda row: row["assumption"]["assumption_id"]
    ) or buffers != sorted(buffers, key=lambda row: row["assumption"]["assumption_id"]):
        _fail("shock_assumption_order_invalid")
    if len({row["applies_to_edge_id"] for row in substitutions}) != len(substitutions):
        _fail("shock_duplicate_substitution_target")
    if len({row["applies_to_target_entity_id"] for row in buffers}) != len(buffers):
        _fail("shock_duplicate_buffer_target")
    for row in substitutions:
        interval = row["fraction_of_gross_effect"]
        if not _interval_is_strict(interval) or interval["upper"] > 100:
            _fail("shock_substitution_interval_invalid")
    for row in buffers:
        interval = row["duration_offset"]
        if (
            not _interval_is_strict(interval)
            or interval["upper"] > duration["upper"]
            or row["applies_to_target_entity_id"] != scenario["target_entity_id"]
        ):
            _fail("shock_buffer_interval_invalid")

    assumptions = [
        _assumption_identity(shock),
        *(_assumption_identity(row) for row in substitutions),
        *(_assumption_identity(row) for row in buffers),
    ]
    assumption_ids = [row["assumption_id"] for row in assumptions]
    if len(assumption_ids) != len(set(assumption_ids)):
        _fail("shock_assumption_id_duplicate")
    if scenario["shock_subject_entity_id"] == scenario["target_entity_id"]:
        _fail("shock_subject_equals_target")
    if scenario["guardrails"] != _GUARDRAILS:
        _fail("shock_guardrails_invalid")
    if scenario["limitations"] != sorted(_SCENARIO_LIMITATIONS):
        _fail("shock_scenario_limitations_invalid")


def _source_policies(
    root: Path,
    rights_registry_path: Path,
    expected_sha: str,
) -> dict[str, int | None]:
    safe = _inside_root(root, rights_registry_path, "shock_rights_registry_missing")
    _, registry, digest = _read_json(safe, "shock_rights_registry_invalid")
    if digest != expected_sha:
        _fail("shock_rights_registry_digest_mismatch")
    policies: dict[str, int | None] = {}
    for row in registry.get("sources", []):
        source_id = row.get("source_id")
        days = row.get("max_current_age_days")
        if not isinstance(source_id, str) or (
            days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 1)
        ):
            _fail("shock_rights_freshness_policy_invalid")
        policies[source_id] = days
    return policies


def _freshness(
    edge: Mapping[str, Any],
    evidence: Mapping[str, Mapping[str, Any]],
    source_policies: Mapping[str, int | None],
    generated_at: datetime,
) -> dict[str, Any]:
    observed_at = _parse_time(edge["observed_at"], "shock_edge_observed_invalid")
    age_seconds = int((generated_at - observed_at).total_seconds())
    if age_seconds < 0:
        _fail("shock_edge_observed_after_release", cast(str, edge["edge_id"]))
    source_ids = sorted(
        {
            cast(str, evidence[evidence_id]["source_id"])
            for evidence_id in edge["evidence_ids"]
        }
    )
    rows: list[dict[str, Any]] = []
    thresholds: list[int] = []
    unknown = False
    for source_id in source_ids:
        if source_id not in source_policies:
            _fail("shock_edge_source_policy_missing", source_id)
        days = source_policies[source_id]
        rows.append({"source_id": source_id, "max_current_age_days": days})
        if days is None:
            unknown = True
        else:
            thresholds.append(days)
    threshold = None if unknown or not thresholds else min(thresholds)
    status = (
        "unknown_policy"
        if threshold is None
        else "stale"
        if age_seconds > threshold * 86_400
        else "current"
    )
    return {
        "observed_at": edge["observed_at"],
        "observation_age_seconds": age_seconds,
        "max_current_age_days": threshold,
        "status": status,
        "source_policies": rows,
    }


def _rounded(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _measure(
    lower: Decimal,
    upper: Decimal,
    denominator: str,
    transform: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "lower": _rounded(lower),
        "upper": _rounded(upper),
        "unit": "percentage_points_of_edge_denominator",
        "denominator": denominator,
        "equation": transform["equation"],
        "transform_id": transform["transform_id"],
    }


def _duration_measure(
    lower: int,
    upper: int,
    transform: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "lower": lower,
        "upper": upper,
        "unit": "days",
        "equation": transform["equation"],
        "transform_id": transform["transform_id"],
    }


def _path_id(scenario_id: str, edge_ids: Sequence[str]) -> str:
    raw = json.dumps([scenario_id, *edge_ids], separators=(",", ":")).encode()
    return f"path:shock.{hashlib.sha256(raw).hexdigest()[:24]}"


def _gap(
    code: str,
    path_id: str | None,
    edge_id: str | None,
    assumption_id: str | None = None,
) -> dict[str, Any]:
    raw = json.dumps(
        [code, path_id, edge_id, assumption_id], separators=(",", ":")
    ).encode()
    return {
        "gap_id": f"gap:shock.{hashlib.sha256(raw).hexdigest()[:24]}",
        "gap_code": code,
        "path_id": path_id,
        "edge_id": edge_id,
        "assumption_id": assumption_id,
    }


def _scenario_output(scenario: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: scenario[key]
        for key in (
            "scenario_id",
            "record_sha256",
            "created_at",
            "knowledge_cutoff",
            "event_id",
            "target_entity_id",
            "shock_subject_entity_id",
            "purpose",
            "shock",
            "substitutions",
            "buffers",
            "guardrails",
            "limitations",
        )
    }


def _path_hops(
    path: Mapping[str, Any],
    edges: Mapping[str, Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
    policies: Mapping[str, int | None],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    rows = []
    for traversal_hop in path["hops"]:
        edge_id = cast(str, traversal_hop["edge_id"])
        edge = edges[edge_id]
        rows.append(
            {
                "edge_id": edge_id,
                "record_sha256": edge["record_sha256"],
                "source_entity_id": edge["source_entity_id"],
                "target_entity_id": edge["target_entity_id"],
                "edge_type": edge["edge_type"],
                "quantification_status": edge["quantification_status"],
                "magnitude": dict(edge["magnitude"]) if edge["magnitude"] is not None else None,
                "freshness": _freshness(edge, evidence, policies, generated_at),
                "coverage": dict(traversal_hop["coverage"]),
                "evidence_ids": list(edge["evidence_ids"]),
                "limitation_codes": list(edge["limitation_codes"]),
            }
        )
    return rows


def _bounded_path(
    scenario: Mapping[str, Any],
    structural_path: Mapping[str, Any],
    hops: list[dict[str, Any]],
    transforms: Sequence[Mapping[str, str]],
    substitution_by_edge: Mapping[str, Mapping[str, Any]],
    buffer: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path_id = _path_id(cast(str, scenario["scenario_id"]), structural_path["edge_ids"])
    gap_rows: list[dict[str, Any]] = []
    gap_codes: set[str] = set()
    limitation_codes = set(structural_path["limitation_codes"])
    for hop in hops:
        freshness = hop["freshness"]["status"]
        if freshness == "stale":
            code = "gap:shock.stale_edge"
            gap_rows.append(_gap(code, path_id, hop["edge_id"]))
            gap_codes.add(code)
        elif freshness == "unknown_policy":
            code = "gap:shock.unknown_freshness_policy"
            gap_rows.append(_gap(code, path_id, hop["edge_id"]))
            gap_codes.add(code)

    reason = "reason:shock.bounded_transform_applied"
    gross: dict[str, Any] | None = None
    residual: dict[str, Any] | None = None
    residual_duration: dict[str, Any] | None = None
    grid: list[dict[str, Any]] = []
    used = [scenario["shock"]["assumption"]["assumption_id"]]

    if len(hops) != 1:
        reason = "reason:shock.multi_hop_transform_unregistered"
    else:
        edge = hops[0]
        magnitude = edge["magnitude"]
        if edge["quantification_status"] != "quantified" or magnitude is None:
            reason = "reason:shock.edge_magnitude_unavailable"
        elif magnitude["unit"] not in _SUPPORTED_EDGE_UNITS:
            reason = "reason:shock.edge_unit_unsupported"
        elif magnitude["uncertainty"]["status"] != "interval":
            reason = "reason:shock.edge_interval_required"

    if reason != "reason:shock.bounded_transform_applied":
        gap_rows.append(_gap(reason.replace("reason:", "gap:"), path_id, hops[-1]["edge_id"]))
        gap_codes.add(reason.replace("reason:", "gap:"))
        used = []
        status = "abstained"
    else:
        status = "bounded_range"
        edge = hops[0]
        magnitude = cast(Mapping[str, Any], edge["magnitude"])
        edge_lower = _decimal(magnitude["uncertainty"]["lower"])
        edge_upper = _decimal(magnitude["uncertainty"]["upper"])
        shock_interval = scenario["shock"]["magnitude"]
        shock_lower = _decimal(shock_interval["lower"])
        shock_upper = _decimal(shock_interval["upper"])
        gross_lower = edge_lower * shock_lower / Decimal(100)
        gross_upper = edge_upper * shock_upper / Decimal(100)
        gross = _measure(gross_lower, gross_upper, magnitude["denominator"], transforms[0])

        substitution = substitution_by_edge.get(cast(str, edge["edge_id"]))
        if substitution is None:
            sub_lower = sub_upper = Decimal(0)
        else:
            sub_interval = substitution["fraction_of_gross_effect"]
            sub_lower = _decimal(sub_interval["lower"])
            sub_upper = _decimal(sub_interval["upper"])
            used.append(substitution["assumption"]["assumption_id"])
        residual_lower = gross_lower * (Decimal(1) - sub_upper / Decimal(100))
        residual_upper = gross_upper * (Decimal(1) - sub_lower / Decimal(100))
        residual = _measure(
            residual_lower,
            residual_upper,
            magnitude["denominator"],
            transforms[1],
        )

        duration = scenario["shock"]["duration"]
        if buffer is None:
            buffer_lower = buffer_upper = 0
        else:
            buffer_lower = buffer["duration_offset"]["lower"]
            buffer_upper = buffer["duration_offset"]["upper"]
            used.append(buffer["assumption"]["assumption_id"])
        duration_lower = max(0, duration["lower"] - buffer_upper)
        duration_upper = max(0, duration["upper"] - buffer_lower)
        residual_duration = _duration_measure(
            duration_lower, duration_upper, transforms[2]
        )

        for shock_value in (shock_interval["lower"], shock_interval["upper"]):
            fixed_shock = _decimal(shock_value)
            cell_gross_lower = edge_lower * fixed_shock / Decimal(100)
            cell_gross_upper = edge_upper * fixed_shock / Decimal(100)
            cell_residual_lower = cell_gross_lower * (
                Decimal(1) - sub_upper / Decimal(100)
            )
            cell_residual_upper = cell_gross_upper * (
                Decimal(1) - sub_lower / Decimal(100)
            )
            for duration_value in (duration["lower"], duration["upper"]):
                grid.append(
                    {
                        "shock_magnitude_percent": shock_value,
                        "duration_days": duration_value,
                        "gross_affected_share": _measure(
                            cell_gross_lower,
                            cell_gross_upper,
                            magnitude["denominator"],
                            transforms[0],
                        ),
                        "residual_affected_share": _measure(
                            cell_residual_lower,
                            cell_residual_upper,
                            magnitude["denominator"],
                            transforms[1],
                        ),
                        "residual_duration_days": _duration_measure(
                            max(0, duration_value - buffer_upper),
                            max(0, duration_value - buffer_lower),
                            transforms[2],
                        ),
                    }
                )

    return (
        {
            "path_id": path_id,
            "entry_entity_id": structural_path["entry_entity_id"],
            "entity_ids": list(structural_path["entity_ids"]),
            "edge_ids": list(structural_path["edge_ids"]),
            "hops": hops,
            "quantification_status": status,
            "reason_code": reason,
            "gross_affected_share": gross,
            "residual_affected_share": residual,
            "residual_duration": residual_duration,
            "sensitivity_grid": grid,
            "assumption_ids_used": sorted(used),
            "gap_codes": sorted(gap_codes),
            "limitation_codes": sorted(limitation_codes),
        },
        gap_rows,
    )


def _assumption_rows(
    scenario: Mapping[str, Any],
    paths: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    uses: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        for assumption_id in path["assumption_ids_used"]:
            uses[assumption_id].append(path["path_id"])
    typed = [
        (scenario["shock"]["assumption"], "shock"),
        *((row["assumption"], "substitution") for row in scenario["substitutions"]),
        *((row["assumption"], "buffer") for row in scenario["buffers"]),
    ]
    rows = []
    for assumption, assumption_type in typed:
        assumption_id = assumption["assumption_id"]
        used_by = sorted(uses[assumption_id])
        rows.append(
            {
                "assumption_id": assumption_id,
                "assumption_type": assumption_type,
                "status": assumption["status"],
                "origin": assumption["origin"],
                "used_by_path_ids": used_by,
                "unused_reason": None if used_by else "reason:shock.no_eligible_bounded_path",
            }
        )
    return sorted(rows, key=lambda row: row["assumption_id"])


def _coverage_rows(paths: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        for hop in path["hops"]:
            coverage = dict(hop["coverage"])
            key = (
                cast(str, coverage["universe_release_id"]),
                cast(str, coverage["covered_entity_id"]),
            )
            rows[key] = coverage
    return [rows[key] for key in sorted(rows)]


def _evidence_and_rights(
    scenario: Mapping[str, Any],
    paths: Sequence[Mapping[str, Any]],
    traversal: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    object_ids = {
        scenario["event_id"],
        scenario["shock_subject_entity_id"],
        scenario["target_entity_id"],
    }
    for path in paths:
        object_ids.update(path["entity_ids"])
        object_ids.update(path["edge_ids"])
        object_ids.update(
            hop["coverage"]["universe_release_id"] for hop in path["hops"]
        )
    needed_evidence = {
        evidence_id
        for row in traversal["object_evidence"]
        if row["object_id"] in object_ids
        for evidence_id in row["evidence_ids"]
    }
    evidence = [
        dict(row)
        for row in traversal["evidence"]
        if row["evidence_id"] in needed_evidence
    ]
    needed_sources = {row["source_id"] for row in evidence}
    rights = [
        dict(row)
        for row in traversal["rights"]
        if row["source_id"] in needed_sources
    ]
    return evidence, rights


def _build_unsealed(
    scenario: Mapping[str, Any],
    manifest: Mapping[str, Any],
    objects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    traversal: Mapping[str, Any],
    contract: Mapping[str, Any],
    registry_sha: str,
    transforms: Sequence[Mapping[str, str]],
    policies: Mapping[str, int | None],
) -> dict[str, Any]:
    subject = scenario["shock_subject_entity_id"]
    event_entries = {row["entity_id"] for row in traversal["event"]["entry_entities"]}
    if subject not in event_entries:
        _fail("shock_subject_not_event_entry")
    selected = [
        path for path in traversal["paths"] if path["entry_entity_id"] == subject
    ]
    gaps: list[dict[str, Any]] = []
    if len(selected) != len(traversal["paths"]):
        gaps.append(_gap("gap:shock.non_subject_entry_paths_excluded", None, None))
    if traversal["result"]["truncated"]:
        gaps.append(_gap("gap:shock.traversal_truncated", None, None))
    if not selected:
        gaps.append(_gap("gap:shock.no_subject_to_target_path", None, None))

    substitution_by_edge = {
        row["applies_to_edge_id"]: row for row in scenario["substitutions"]
    }
    buffer_by_target = {
        row["applies_to_target_entity_id"]: row for row in scenario["buffers"]
    }
    generated_at = _parse_time(manifest["generated_at"], "shock_generated_invalid")
    compiled_paths = []
    for path in selected:
        hops = _path_hops(
            path,
            objects["exposure_edge"],
            objects["evidence_item"],
            policies,
            generated_at,
        )
        compiled, path_gaps = _bounded_path(
            scenario,
            path,
            hops,
            transforms,
            substitution_by_edge,
            buffer_by_target.get(scenario["target_entity_id"]),
        )
        compiled_paths.append(compiled)
        gaps.extend(path_gaps)
    compiled_paths.sort(key=lambda row: row["path_id"])
    assumptions = _assumption_rows(scenario, compiled_paths)
    for assumption in assumptions:
        if not assumption["used_by_path_ids"]:
            gaps.append(
                _gap(
                    "gap:shock.unused_assumption",
                    None,
                    None,
                    cast(str, assumption["assumption_id"]),
                )
            )
    gaps.sort(key=lambda row: row["gap_id"])
    evidence_rows, rights_rows = _evidence_and_rights(
        scenario, compiled_paths, traversal
    )
    bounded = sum(row["quantification_status"] == "bounded_range" for row in compiled_paths)
    abstained = len(compiled_paths) - bounded
    stale = sum(
        hop["freshness"]["status"] == "stale"
        for path in compiled_paths
        for hop in path["hops"]
    )
    unknown = sum(
        hop["freshness"]["status"] == "unknown_policy"
        for path in compiled_paths
        for hop in path["hops"]
    )
    used_count = sum(bool(row["used_by_path_ids"]) for row in assumptions)
    if not compiled_paths:
        status = "no_path"
    elif bounded == 0:
        status = "structural_only"
    elif abstained or gaps:
        status = "partially_compiled"
    else:
        status = "compiled"
    return {
        "object_type": "shock_compilation",
        "schema_version": "1.0.0",
        "record_sha256": "0" * 64,
        "release": _release_identity(manifest),
        "contract": {
            "input_schema_id": contract["input_schema_id"],
            "input_schema_sha256": contract["input_schema_sha256"],
            "output_schema_id": contract["output_schema_id"],
            "output_schema_sha256": contract["output_schema_sha256"],
            "common_schema_sha256": contract["common_schema_sha256"],
            "compiler_registry_sha256": registry_sha,
            "exposure_traversal_schema_sha256": contract[
                "exposure_traversal_schema_sha256"
            ],
            "exposure_projection_registry_sha256": contract[
                "exposure_projection_registry_sha256"
            ],
        },
        "method": {
            "method_id": contract["method_id"],
            "version": contract["version"],
            "implementation_sha256": contract["implementation_sha256"],
            "transform_ids": [row["transform_id"] for row in transforms],
        },
        "scenario": _scenario_output(scenario),
        "traversal": {
            "record_sha256": traversal["record_sha256"],
            "method_id": traversal["method"]["method_id"],
            "method_version": traversal["method"]["version"],
            "selection_rule": traversal["query"]["selection_rule"],
            "max_hops": traversal["query"]["max_hops"],
            "max_paths": traversal["query"]["max_paths"],
            "truncated": traversal["result"]["truncated"],
        },
        "paths": compiled_paths,
        "assumption_ledger": assumptions,
        "coverage": _coverage_rows(compiled_paths),
        "evidence": evidence_rows,
        "rights": rights_rows,
        "gaps": gaps,
        "counts": {
            "structural_paths": len(compiled_paths),
            "bounded_paths": bounded,
            "abstained_paths": abstained,
            "stale_hops": stale,
            "unknown_freshness_hops": unknown,
            "gaps": len(gaps),
            "assumptions": len(assumptions),
            "assumptions_used": used_count,
        },
        "result": {
            "status": status,
            "public_claim_state": "requires_claim_bundle",
            "forecast_performed": False,
            "probability_assigned": False,
            "causal_attribution_performed": False,
            "recommendation_generated": False,
            "scalar_score_computed": False,
        },
        "limitations": sorted(_OUTPUT_LIMITATIONS),
    }


def _dependencies(
    manifest_path: Path,
    scenario: Mapping[str, Any],
    *,
    root: Path,
    schema_registry_path: Path,
    rights_registry_path: Path,
    rights_signers_path: Path,
    method_registry_path: Path,
    release_signers_path: Path,
    shock_registry_path: Path,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Mapping[str, Mapping[str, Any]]],
    dict[str, Any],
    Draft202012Validator,
    tuple[dict[str, str], ...],
    dict[str, Any],
    str,
    dict[str, int | None],
]:
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
    if scenario["shock_subject_entity_id"] not in validated.objects["entity"]:
        _fail("shock_subject_not_in_release")
    for row in scenario["substitutions"]:
        if row["applies_to_edge_id"] not in validated.objects["exposure_edge"]:
            _fail("shock_substitution_edge_not_in_release")
    for row in scenario["buffers"]:
        if row["applies_to_target_entity_id"] not in validated.objects["entity"]:
            _fail("shock_buffer_target_not_in_release")
    release_day = _parse_day(manifest["effective_date"], "shock_release_day_invalid")
    contract, registry_sha, input_validator, output_validator, transforms = _load_contract(
        root, shock_registry_path, release_day
    )
    _validate_scenario(scenario, manifest, input_validator)
    traversal = exposure_graph.project_event_exposure(
        manifest_path,
        cast(str, scenario["event_id"]),
        cast(str, scenario["target_entity_id"]),
        max_hops=scenario["traversal"]["max_hops"],
        max_paths=scenario["traversal"]["max_paths"],
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
    )
    policies = _source_policies(
        root,
        rights_registry_path,
        cast(str, manifest["rights_registry_sha256"]),
    )
    return (
        manifest,
        validated.objects,
        traversal,
        output_validator,
        transforms,
        contract,
        registry_sha,
        policies,
    )


def compile_shock(
    manifest_path: Path,
    scenario: Mapping[str, Any],
    *,
    root: Path = canonical.ROOT,
    schema_registry_path: Path = canonical.SCHEMA_REGISTRY,
    rights_registry_path: Path = canonical.RIGHTS_REGISTRY,
    rights_signers_path: Path = canonical.RIGHTS_SIGNERS,
    method_registry_path: Path = canonical.METHOD_REGISTRY,
    release_signers_path: Path = canonical.RELEASE_SIGNERS,
    shock_registry_path: Path = SHOCK_REGISTRY,
) -> dict[str, Any]:
    """Compile one strict hypothetical scenario against a signed release."""

    (
        manifest,
        objects,
        traversal,
        output_validator,
        transforms,
        contract,
        registry_sha,
        policies,
    ) = _dependencies(
        manifest_path,
        scenario,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
        shock_registry_path=shock_registry_path,
    )
    document = canonical.seal_record(
        _build_unsealed(
            scenario,
            manifest,
            objects,
            traversal,
            contract,
            registry_sha,
            transforms,
            policies,
        )
    )
    _schema_check(document, output_validator, "shock_output_schema_invalid")
    if canonical.canonical_record_sha256(document) != document["record_sha256"]:
        _fail("shock_output_digest_mismatch")
    return cast(dict[str, Any], document)


def validate_shock_compilation(
    document: Mapping[str, Any],
    manifest_path: Path,
    scenario: Mapping[str, Any],
    *,
    root: Path = canonical.ROOT,
    schema_registry_path: Path = canonical.SCHEMA_REGISTRY,
    rights_registry_path: Path = canonical.RIGHTS_REGISTRY,
    rights_signers_path: Path = canonical.RIGHTS_SIGNERS,
    method_registry_path: Path = canonical.METHOD_REGISTRY,
    release_signers_path: Path = canonical.RELEASE_SIGNERS,
    shock_registry_path: Path = SHOCK_REGISTRY,
) -> None:
    """Recompile from signed inputs and require byte-semantic equality."""

    (
        manifest,
        objects,
        traversal,
        output_validator,
        transforms,
        contract,
        registry_sha,
        policies,
    ) = _dependencies(
        manifest_path,
        scenario,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
        shock_registry_path=shock_registry_path,
    )
    expected = canonical.seal_record(
        _build_unsealed(
            scenario,
            manifest,
            objects,
            traversal,
            contract,
            registry_sha,
            transforms,
            policies,
        )
    )
    _schema_check(document, output_validator, "shock_output_schema_invalid")
    if document != expected:
        _fail("shock_output_semantic_mismatch")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compile a bounded hypothetical shock over signed exposure paths"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    _, scenario, _ = _read_json(args.scenario, "shock_scenario_file_invalid")
    try:
        result = compile_shock(args.manifest, scenario)
    except (ShockCompilerError, canonical.CanonicalObjectError, exposure_graph.ExposureGraphError) as exc:
        detail = getattr(exc, "detail", "")
        suffix = f":{detail}" if detail else ""
        print(f"REFUSE:{exc.code}{suffix}", file=sys.stderr)
        raise SystemExit(2) from None
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
