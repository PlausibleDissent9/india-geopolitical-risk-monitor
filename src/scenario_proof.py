"""Prove bounded constraint and mechanism predicates over Shock Compiler output.

This module is a strict OGES sidecar.  It revalidates the exact signed release
and recomputes the supplied ShockCompilation before evaluating any constraint
or falsifier.  It does not establish real-world feasibility, mechanism support,
causality, probability, optimality, advice, or rival-set completeness.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import event_ledger_extension, shock_compiler

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "standard" / "oges" / "extensions" / "mechanism-constraint-scenario" / "0.1.0"
PROFILE_PATH = EXTENSION / "profile.json"

_BOUND_KINDS = {
    "specification",
    "base_oges_profile",
    "constraint_schema",
    "hypothesis_schema",
    "request_schema",
    "execution_schema",
    "operator_registry",
    "predicate_registry",
    "adversarial_cases",
    "shock_registry",
    "shock_scenario_schema",
    "shock_compilation_schema",
    "common_schema",
    "shock_compiler",
    "typed_canonical_implementation",
    "typed_record_implementation",
    "typed_canonical_fixture",
}
_OPERATORS = (
    "operator:scenario.verify_shock_compilation",
    "operator:scenario.evaluate_upper_bound",
    "operator:scenario.certify_monotone_corners",
    "operator:scenario.evaluate_registered_falsifier",
    "operator:scenario.preserve_symmetric_rivals",
)
_PREDICATES = (
    "predicate:scenario.path_quantification_status_equals",
    "predicate:scenario.path_gap_code_present",
    "predicate:scenario.constraint_interval_relation_equals",
)
_REQUEST_LIMITATIONS = sorted(
    (
        "hypothetical_scenario_feasibility_not_real_world_feasibility",
        "mechanism_compatibility_not_support_or_causality",
        "no_forecast_probability_recommendation_or_optimization",
        "non_synthetic_rendering_requires_claim_bundle",
    )
)
_EXECUTION_LIMITATIONS = sorted(
    (
        "constraint_status_applies_only_to_registered_hypothetical_bounds",
        "interval_corners_are_not_probabilities_or_confidence_intervals",
        "mechanism_status_is_not_support_confirmation_or_causality",
        "no_real_world_feasibility_forecast_advice_or_optimization",
        "non_synthetic_rendering_requires_claim_bundle",
    )
)
_GUARDRAILS = {
    "real_world_feasibility_claimed": False,
    "mechanism_support_claimed": False,
    "causal_attribution_performed": False,
    "forecast_performed": False,
    "probability_assigned": False,
    "recommendation_generated": False,
    "objective_optimized": False,
}
_MAX_SAFE_INTEGER = 9_007_199_254_740_991


class ScenarioProofError(ValueError):
    """Stable fail-closed Scenario Proof refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ScenarioProofError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("scenario_proof_json_duplicate_key", key)
        result[key] = value
    return result


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("scenario_proof_json_non_finite"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScenarioProofError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail(code)
    candidate = root.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file() or resolved.is_symlink():
        _fail(code)
    return resolved


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


def _number(value: object, code: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(code)
    if isinstance(value, float) and not math.isfinite(value):
        _fail(code)
    if abs(value) > _MAX_SAFE_INTEGER:
        _fail(code)
    return Decimal(str(value))


def _rounded(value: Decimal) -> float:
    result = float(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
    return 0.0 if result == 0 else result


def _schema_validator(
    primary: Mapping[str, Any], references: Sequence[Mapping[str, Any]]
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(primary)
        for reference in references:
            Draft202012Validator.check_schema(reference)
    except SchemaError as exc:
        raise ScenarioProofError("scenario_proof_schema_meta_invalid") from exc
    registry = Registry().with_resources(
        [(cast(str, row["$id"]), Resource.from_contents(row)) for row in (primary, *references)]
    )
    return Draft202012Validator(primary, registry=registry, format_checker=FormatChecker())


def _schema_check(document: Mapping[str, Any], validator: Draft202012Validator, code: str) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(code, f"{path or '/'}:{errors[0].validator}")


def _typed_check(document: Mapping[str, Any], code: str) -> None:
    try:
        digest = event_ledger_extension.typed_record_sha256(document)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise ScenarioProofError(code, exc.code) from exc
    if digest != document.get("record_sha256"):
        _fail(code)


def _profile() -> tuple[
    dict[str, Any],
    str,
    dict[str, str],
    dict[str, Any],
    dict[str, Any],
    Draft202012Validator,
    Draft202012Validator,
]:
    raw, profile, profile_sha = _read_json(PROFILE_PATH, "scenario_proof_profile_invalid")
    if (
        profile.get("schema_version") != "0.1.0"
        or profile.get("extension_id") != "oges:extension:scenario_proof"
        or profile.get("version") != "0.1.0"
        or profile.get("effective") != "2026-08-09"
        or profile.get("status") != "public_draft_contract_only_synthetic_fixtures"
    ):
        _fail("scenario_proof_profile_identity_invalid")
    rows = profile.get("bound_files")
    if not isinstance(rows, list):
        _fail("scenario_proof_profile_files_invalid")
    by_kind: dict[str, str] = {}
    documents: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"kind", "path", "sha256"}:
            _fail("scenario_proof_profile_files_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in by_kind:
            _fail("scenario_proof_profile_files_invalid")
        path = _safe_file(ROOT, row["path"], "scenario_proof_profile_path_invalid")
        captured, document, digest = (
            _read_json(path, "scenario_proof_profile_file_invalid")
            if path.suffix == ".json"
            else (path.read_bytes(), {}, hashlib.sha256(path.read_bytes()).hexdigest())
        )
        del captured
        if digest != row["sha256"]:
            _fail("scenario_proof_profile_digest_mismatch", kind)
        by_kind[kind] = digest
        if document:
            documents[kind] = document
    if set(by_kind) != _BOUND_KINDS:
        _fail("scenario_proof_profile_files_invalid")

    implementation = profile.get("reference_implementation")
    conformance = profile.get("conformance_test")
    for row, code in (
        (implementation, "scenario_proof_implementation_invalid"),
        (conformance, "scenario_proof_conformance_test_invalid"),
    ):
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            _fail(code)
        path = _safe_file(ROOT, row["path"], code)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            _fail("scenario_proof_profile_digest_mismatch", code)

    operators = documents["operator_registry"]
    predicates = documents["predicate_registry"]
    if (
        operators.get("registry_id") != "oges:scenario-proof:operators"
        or operators.get("default_policy") != "deny"
        or tuple(row.get("operator_id") for row in operators.get("operators", [])) != _OPERATORS
    ):
        _fail("scenario_proof_operator_registry_invalid")
    if (
        predicates.get("registry_id") != "oges:scenario-proof:predicates"
        or predicates.get("default_policy") != "deny"
        or tuple(row.get("predicate_id") for row in predicates.get("predicates", [])) != _PREDICATES
    ):
        _fail("scenario_proof_predicate_registry_invalid")

    common = documents["common_schema"]
    constraint = documents["constraint_schema"]
    hypothesis = documents["hypothesis_schema"]
    request = documents["request_schema"]
    execution = documents["execution_schema"]
    request_validator = _schema_validator(request, (common, constraint, hypothesis))
    execution_validator = _schema_validator(execution, (common,))
    del raw
    return (
        profile,
        profile_sha,
        by_kind,
        operators,
        predicates,
        request_validator,
        execution_validator,
    )


def _validate_request(
    request: Mapping[str, Any],
    scenario: Mapping[str, Any],
    compilation: Mapping[str, Any],
    validator: Draft202012Validator,
    predicate_registry: Mapping[str, Any],
) -> None:
    _schema_check(request, validator, "scenario_proof_request_schema_invalid")
    _typed_check(request, "scenario_proof_request_digest_invalid")
    if request["guardrails"] != _GUARDRAILS or request["limitations"] != _REQUEST_LIMITATIONS:
        _fail("scenario_proof_guardrails_invalid")
    binding = request["scenario_binding"]
    expected_binding = {
        "scenario_id": scenario["scenario_id"],
        "scenario_record_sha256": scenario["record_sha256"],
        "compilation_record_sha256": compilation["record_sha256"],
    }
    if binding != expected_binding:
        _fail("scenario_proof_binding_mismatch")
    scenario_created = _utc(scenario["created_at"], "scenario_proof_time_invalid")
    request_created = _utc(request["created_at"], "scenario_proof_time_invalid")
    evaluation = _utc(request["evaluation_as_of"], "scenario_proof_time_invalid")
    release_generated = _utc(compilation["release"]["generated_at"], "scenario_proof_time_invalid")
    if not (scenario_created <= request_created <= evaluation) or release_generated > evaluation:
        _fail("scenario_proof_time_invalid")

    constraints = request["constraints"]
    hypotheses = request["hypotheses"]
    if constraints != sorted(constraints, key=lambda row: row["constraint_id"]):
        _fail("scenario_proof_constraint_order_invalid")
    if hypotheses != sorted(hypotheses, key=lambda row: row["hypothesis_id"]):
        _fail("scenario_proof_hypothesis_order_invalid")
    constraint_ids = [row["constraint_id"] for row in constraints]
    hypothesis_ids = [row["hypothesis_id"] for row in hypotheses]
    if len(constraint_ids) != len(set(constraint_ids)):
        _fail("scenario_proof_constraint_duplicate")
    if len(hypothesis_ids) != len(set(hypothesis_ids)):
        _fail("scenario_proof_hypothesis_duplicate")
    path_ids = {row["path_id"] for row in compilation["paths"]}
    for row in constraints:
        _typed_check(row, "scenario_proof_constraint_digest_invalid")
        if (
            row["scenario_id"] != scenario["scenario_id"]
            or row["scenario_record_sha256"] != scenario["record_sha256"]
            or row["compilation_record_sha256"] != compilation["record_sha256"]
        ):
            _fail("scenario_proof_binding_mismatch")
        if row["path_id"] not in path_ids:
            _fail("scenario_proof_constraint_path_missing")
        _number(row["threshold"]["value"], "scenario_proof_number_invalid")
    allowed = {row["predicate_id"]: row for row in predicate_registry["predicates"]}
    hypothesis_id_set = set(hypothesis_ids)
    constraint_id_set = set(constraint_ids)
    for row in hypotheses:
        _typed_check(row, "scenario_proof_hypothesis_digest_invalid")
        if (
            row["scenario_id"] != scenario["scenario_id"]
            or row["scenario_record_sha256"] != scenario["record_sha256"]
            or row["compilation_record_sha256"] != compilation["record_sha256"]
        ):
            _fail("scenario_proof_binding_mismatch")
        if row["path_id"] not in path_ids:
            _fail("scenario_proof_hypothesis_path_missing")
        registered_at = _utc(row["registered_at"], "scenario_proof_time_invalid")
        expected_timing = "prospective" if registered_at <= scenario_created else "retrospective"
        if row["registration_timing"] != expected_timing:
            _fail("scenario_proof_registration_timing_invalid")
        rivals = row["rival_hypothesis_ids"]
        if (
            rivals != sorted(rivals)
            or row["hypothesis_id"] in rivals
            or not set(rivals) <= hypothesis_id_set
        ):
            _fail("scenario_proof_rival_invalid")
        reverse = {rival["hypothesis_id"]: rival["rival_hypothesis_ids"] for rival in hypotheses}
        if any(row["hypothesis_id"] not in reverse[rival_id] for rival_id in rivals):
            _fail("scenario_proof_rival_asymmetric")
        falsifiers = row["falsifiers"]
        if falsifiers != sorted(falsifiers, key=lambda item: item["falsifier_id"]):
            _fail("scenario_proof_falsifier_order_invalid")
        falsifier_ids = [item["falsifier_id"] for item in falsifiers]
        if len(falsifier_ids) != len(set(falsifier_ids)):
            _fail("scenario_proof_falsifier_duplicate")
        for falsifier in falsifiers:
            predicate = allowed.get(falsifier["predicate_id"])
            if (
                predicate is None
                or falsifier["expected_value"] not in predicate["allowed_expected_values"]
            ):
                _fail("scenario_proof_predicate_invalid")
            requires_constraint = predicate["constraint_required"]
            constraint_id = falsifier["constraint_id"]
            if requires_constraint:
                if constraint_id not in constraint_id_set:
                    _fail("scenario_proof_falsifier_constraint_missing")
            elif constraint_id is not None:
                _fail("scenario_proof_falsifier_constraint_forbidden")


def _readiness(path: Mapping[str, Any]) -> str:
    if path["quantification_status"] != "bounded_range":
        return "upstream_abstention"
    states = {hop["freshness"]["status"] for hop in path["hops"]}
    if "stale" in states:
        return "stale_inputs"
    if "unknown_policy" in states:
        return "unknown_freshness"
    return "current_inputs"


def _interval(path: Mapping[str, Any], metric: str) -> dict[str, Any] | None:
    value = path[metric]
    if value is None:
        return None
    return {
        "lower": value["lower"],
        "upper": value["upper"],
        "unit": value["unit"],
        "denominator": value.get("denominator"),
    }


def _corner_witnesses(
    scenario: Mapping[str, Any], path: Mapping[str, Any], metric: str
) -> list[dict[str, Any]]:
    actual = _interval(path, metric)
    if actual is None or len(path["hops"]) != 1:
        return []
    edge = path["hops"][0]
    magnitude = edge["magnitude"]
    if magnitude is None or magnitude["uncertainty"]["status"] != "interval":
        return []
    edge_lower = _number(magnitude["uncertainty"]["lower"], "scenario_proof_number_invalid")
    edge_upper = _number(magnitude["uncertainty"]["upper"], "scenario_proof_number_invalid")
    shock_lower = _number(scenario["shock"]["magnitude"]["lower"], "scenario_proof_number_invalid")
    shock_upper = _number(scenario["shock"]["magnitude"]["upper"], "scenario_proof_number_invalid")
    substitution = next(
        (row for row in scenario["substitutions"] if row["applies_to_edge_id"] == edge["edge_id"]),
        None,
    )
    sub_lower = _number(
        substitution["fraction_of_gross_effect"]["lower"] if substitution else 0,
        "scenario_proof_number_invalid",
    )
    sub_upper = _number(
        substitution["fraction_of_gross_effect"]["upper"] if substitution else 0,
        "scenario_proof_number_invalid",
    )
    buffer = next(
        (
            row
            for row in scenario["buffers"]
            if row["applies_to_target_entity_id"] == scenario["target_entity_id"]
        ),
        None,
    )
    buffer_lower = _number(
        buffer["duration_offset"]["lower"] if buffer else 0,
        "scenario_proof_number_invalid",
    )
    buffer_upper = _number(
        buffer["duration_offset"]["upper"] if buffer else 0,
        "scenario_proof_number_invalid",
    )
    duration_lower = _number(
        scenario["shock"]["duration"]["lower"], "scenario_proof_number_invalid"
    )
    duration_upper = _number(
        scenario["shock"]["duration"]["upper"], "scenario_proof_number_invalid"
    )

    lower_inputs: tuple[
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
    ]
    upper_inputs: tuple[
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
        Decimal | None,
    ]
    if metric == "gross_affected_share":
        lower = edge_lower * shock_lower / Decimal(100)
        upper = edge_upper * shock_upper / Decimal(100)
        lower_inputs = (edge_lower, shock_lower, None, None, None)
        upper_inputs = (edge_upper, shock_upper, None, None, None)
        transforms = ["transform:shock.gross_affected_share"]
    elif metric == "residual_affected_share":
        lower = edge_lower * shock_lower / Decimal(100) * (Decimal(1) - sub_upper / Decimal(100))
        upper = edge_upper * shock_upper / Decimal(100) * (Decimal(1) - sub_lower / Decimal(100))
        lower_inputs = (edge_lower, shock_lower, sub_upper, None, None)
        upper_inputs = (edge_upper, shock_upper, sub_lower, None, None)
        transforms = [
            "transform:shock.gross_affected_share",
            "transform:shock.residual_after_substitution",
        ]
    else:
        lower = max(Decimal(0), duration_lower - buffer_upper)
        upper = max(Decimal(0), duration_upper - buffer_lower)
        lower_inputs = (None, None, None, duration_lower, buffer_upper)
        upper_inputs = (None, None, None, duration_upper, buffer_lower)
        transforms = ["transform:shock.residual_duration"]

    if _rounded(lower) != actual["lower"] or _rounded(upper) != actual["upper"]:
        _fail("scenario_proof_corner_recomputation_mismatch")

    def witness(bound: str, value: Decimal, inputs: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "bound": bound,
            "value": _rounded(value),
            "inputs": {
                "edge_value": None if inputs[0] is None else _rounded(inputs[0]),
                "shock_value": None if inputs[1] is None else _rounded(inputs[1]),
                "substitution_value": None if inputs[2] is None else _rounded(inputs[2]),
                "duration_value": None if inputs[3] is None else _rounded(inputs[3]),
                "buffer_value": None if inputs[4] is None else _rounded(inputs[4]),
            },
            "transform_ids": transforms,
        }

    return [witness("lower", lower, lower_inputs), witness("upper", upper, upper_inputs)]


def _constraint_result(
    constraint: Mapping[str, Any],
    path: Mapping[str, Any],
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    metric = cast(str, constraint["metric"])
    actual = _interval(path, metric)
    threshold = dict(constraint["threshold"])
    readiness = _readiness(path)
    if metric == "residual_duration":
        valid_measure = threshold["unit"] == "days" and threshold["denominator"] is None
    else:
        hop_magnitude = path["hops"][0]["magnitude"] if len(path["hops"]) == 1 else None
        expected_denominator = (
            actual["denominator"]
            if actual is not None
            else hop_magnitude.get("denominator")
            if hop_magnitude is not None
            else None
        )
        valid_measure = (
            expected_denominator is not None
            and threshold["unit"] == "percentage_points_of_edge_denominator"
            and threshold["denominator"] == expected_denominator
        )
    if not valid_measure:
        _fail("scenario_proof_constraint_measure_mismatch")

    if actual is None:
        relation = "not_evaluable"
        margin = None
        witnesses: list[dict[str, Any]] = []
    else:
        lower = _number(actual["lower"], "scenario_proof_number_invalid")
        upper = _number(actual["upper"], "scenario_proof_number_invalid")
        limit = _number(threshold["value"], "scenario_proof_number_invalid")
        if upper <= limit:
            relation = "all_registered_values_satisfy"
        elif lower > limit:
            relation = "no_registered_values_satisfy"
        else:
            relation = "mixed_within_registered_interval"
        margin = {
            "lower": _rounded(limit - upper),
            "upper": _rounded(limit - lower),
            "unit": actual["unit"],
            "denominator": actual["denominator"],
        }
        witnesses = _corner_witnesses(scenario, path, metric)

    if readiness != "current_inputs" or relation == "not_evaluable":
        status = "indeterminate_input_unavailable"
    elif relation == "all_registered_values_satisfy":
        status = "satisfied_under_registered_hypothetical_bounds"
    elif relation == "no_registered_values_satisfy":
        status = "violated_under_registered_hypothetical_bounds"
    else:
        status = "indeterminate_within_registered_bounds"
    return {
        "constraint_id": constraint["constraint_id"],
        "constraint_record_sha256": constraint["record_sha256"],
        "path_id": constraint["path_id"],
        "metric": metric,
        "operator": constraint["operator"],
        "threshold": threshold,
        "actual_interval": actual,
        "margin_interval": margin,
        "interval_relation": relation,
        "readiness": readiness,
        "scenario_feasibility_status": status,
        "corner_witnesses": witnesses,
        "real_world_feasibility_claimed": False,
    }


def _falsifier_result(
    falsifier: Mapping[str, Any],
    path: Mapping[str, Any],
    constraints: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    predicate = falsifier["predicate_id"]
    expected = falsifier["expected_value"]
    if predicate == "predicate:scenario.path_quantification_status_equals":
        status = "triggered" if path["quantification_status"] == expected else "not_triggered"
    elif predicate == "predicate:scenario.path_gap_code_present":
        status = "triggered" if expected in path["gap_codes"] else "not_triggered"
    else:
        constraint = constraints[falsifier["constraint_id"]]
        actual = constraint["interval_relation"]
        if actual == "not_evaluable":
            status = "not_evaluable"
        else:
            status = "triggered" if actual == expected else "not_triggered"
    return {
        "falsifier_id": falsifier["falsifier_id"],
        "predicate_id": predicate,
        "expected_value": expected,
        "constraint_id": falsifier["constraint_id"],
        "status": status,
    }


def _build_execution(
    request: Mapping[str, Any],
    scenario: Mapping[str, Any],
    compilation: Mapping[str, Any],
    profile_sha: str,
    hashes: Mapping[str, str],
    implementation_sha: str,
) -> dict[str, Any]:
    paths = {row["path_id"]: row for row in compilation["paths"]}
    constraint_results = [
        _constraint_result(row, paths[row["path_id"]], scenario) for row in request["constraints"]
    ]
    by_constraint = {row["constraint_id"]: row for row in constraint_results}
    hypothesis_results = []
    for hypothesis in request["hypotheses"]:
        falsifiers = [
            _falsifier_result(row, paths[hypothesis["path_id"]], by_constraint)
            for row in hypothesis["falsifiers"]
        ]
        statuses = {row["status"] for row in falsifiers}
        if "triggered" in statuses:
            compatibility = "incompatible_with_compiled_scenario_not_real_world_falsified"
        elif "not_evaluable" in statuses:
            compatibility = "indeterminate_missing_registered_result"
        else:
            compatibility = "compatible_with_compiled_scenario_not_supported"
        hypothesis_results.append(
            {
                "hypothesis_id": hypothesis["hypothesis_id"],
                "hypothesis_record_sha256": hypothesis["record_sha256"],
                "path_id": hypothesis["path_id"],
                "mechanism_code": hypothesis["mechanism_code"],
                "epistemic_status": hypothesis["epistemic_status"],
                "causal_status": hypothesis["causal_status"],
                "registered_at": hypothesis["registered_at"],
                "registration_timing": hypothesis["registration_timing"],
                "rival_hypothesis_ids": list(hypothesis["rival_hypothesis_ids"]),
                "falsifiers": falsifiers,
                "scenario_compatibility_status": compatibility,
                "support_claimed": False,
                "probability_assigned": False,
            }
        )
    triggered = sum(
        row["status"] == "triggered"
        for hypothesis in hypothesis_results
        for row in hypothesis["falsifiers"]
    )
    unevaluable = sum(
        row["status"] == "not_evaluable"
        for hypothesis in hypothesis_results
        for row in hypothesis["falsifiers"]
    )
    partial = any(
        row["scenario_feasibility_status"] == "indeterminate_input_unavailable"
        for row in constraint_results
    ) or any(
        row["scenario_compatibility_status"] == "indeterminate_missing_registered_result"
        for row in hypothesis_results
    )
    identity = event_ledger_extension.typed_record_sha256(
        {
            "request_record_sha256": request["record_sha256"],
            "compilation_record_sha256": compilation["record_sha256"],
            "profile_sha256": profile_sha,
        }
    )
    return {
        "object_type": "scenario_proof_execution",
        "schema_version": "0.1.0",
        "record_sha256": "0" * 64,
        "execution_id": f"execution:scenario-proof.{identity[:24]}",
        "profile": {
            "extension_id": "oges:extension:scenario_proof",
            "version": "0.1.0",
            "profile_sha256": profile_sha,
            "request_schema_sha256": hashes["request_schema"],
            "execution_schema_sha256": hashes["execution_schema"],
            "constraint_schema_sha256": hashes["constraint_schema"],
            "hypothesis_schema_sha256": hashes["hypothesis_schema"],
            "operator_registry_sha256": hashes["operator_registry"],
            "predicate_registry_sha256": hashes["predicate_registry"],
            "shock_registry_sha256": hashes["shock_registry"],
            "shock_compiler_sha256": hashes["shock_compiler"],
            "reference_implementation_sha256": implementation_sha,
        },
        "request": {
            "request_id": request["request_id"],
            "record_sha256": request["record_sha256"],
            "created_at": request["created_at"],
            "evaluation_as_of": request["evaluation_as_of"],
        },
        "compilation": {
            "scenario_id": scenario["scenario_id"],
            "scenario_record_sha256": scenario["record_sha256"],
            "compilation_record_sha256": compilation["record_sha256"],
            "release_id": compilation["release"]["release_id"],
            "release_record_sha256": compilation["release"]["record_sha256"],
        },
        "constraints": constraint_results,
        "hypotheses": hypothesis_results,
        "counts": {
            "constraints": len(request["constraints"]),
            "constraint_results": len(constraint_results),
            "hypotheses": len(request["hypotheses"]),
            "hypothesis_results": len(hypothesis_results),
            "rival_links": sum(len(row["rival_hypothesis_ids"]) for row in request["hypotheses"]),
            "falsifiers": sum(len(row["falsifiers"]) for row in request["hypotheses"]),
            "falsifiers_triggered": triggered,
            "falsifiers_unevaluable": unevaluable,
        },
        "result": {
            "status": "partially_assessed" if partial else "assessed",
            "trust_class": "unauthenticated_execution_envelope",
            "public_claim_state": "requires_claim_bundle",
            **_GUARDRAILS,
        },
        "limitations": _EXECUTION_LIMITATIONS,
    }


def execute_scenario_proof(
    manifest_path: Path,
    scenario: Mapping[str, Any],
    compilation: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    root: Path,
    schema_registry_path: Path,
    rights_registry_path: Path,
    rights_signers_path: Path,
    method_registry_path: Path,
    release_signers_path: Path,
    shock_registry_path: Path,
) -> dict[str, Any]:
    """Return the exact typed proof after full Shock recompilation."""

    (
        profile,
        profile_sha,
        hashes,
        _,
        predicates,
        request_validator,
        execution_validator,
    ) = _profile()
    shock_compiler.validate_shock_compilation(
        compilation,
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
    _validate_request(request, scenario, compilation, request_validator, predicates)
    implementation_sha = cast(str, profile["reference_implementation"]["sha256"])
    document = event_ledger_extension.seal_record(
        _build_execution(
            request,
            scenario,
            compilation,
            profile_sha,
            hashes,
            implementation_sha,
        )
    )
    _schema_check(document, execution_validator, "scenario_proof_execution_schema_invalid")
    _typed_check(document, "scenario_proof_execution_digest_invalid")
    return cast(dict[str, Any], document)


def validate_scenario_proof(
    document: Mapping[str, Any],
    manifest_path: Path,
    scenario: Mapping[str, Any],
    compilation: Mapping[str, Any],
    request: Mapping[str, Any],
    **kwargs: Any,
) -> None:
    """Recompute the complete proof and require exact equality."""

    expected = execute_scenario_proof(manifest_path, scenario, compilation, request, **kwargs)
    if document != expected:
        _fail("scenario_proof_execution_mismatch")


def seal_request(document: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a request or nested profile object with the shared typed hash."""

    return cast(dict[str, Any], event_ledger_extension.seal_record(document))
