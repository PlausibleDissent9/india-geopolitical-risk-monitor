"""Exact finite-lattice Decision Switch over fully recomputed Scenario Proofs.

The module proves only registered hypothetical option partitions, minimal
switches inside a complete binary lattice, and finite-set information
relevance.  It does not compute real-world feasibility, probability, entropy,
expected value, advice, optimization, acquisition value, or a forecast.
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import event_ledger, event_ledger_extension, scenario_proof

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "standard" / "oges" / "extensions" / "decision-switch" / "0.1.0"
PROFILE_PATH = EXTENSION / "profile.json"

_BOUND_KINDS = {
    "specification",
    "base_oges_profile",
    "registered_option_schema",
    "constraint_slot_schema",
    "switch_atom_schema",
    "artifact_bundle_schema",
    "information_candidate_schema",
    "request_schema",
    "execution_schema",
    "operator_registry",
    "resolution_method_registry",
    "adversarial_cases",
    "scenario_proof_profile",
    "scenario_proof_request_schema",
    "scenario_proof_execution_schema",
    "scenario_proof_implementation",
    "common_schema",
    "typed_canonical_implementation",
    "typed_record_implementation",
    "typed_canonical_fixture",
}
_OPERATORS = (
    "operator:decision_switch.verify_scenario_proof",
    "operator:decision_switch.verify_complete_option_universe",
    "operator:decision_switch.verify_complete_binary_lattice",
    "operator:decision_switch.verify_registered_atom_diff",
    "operator:decision_switch.classify_registered_option_conjunction",
    "operator:decision_switch.find_inclusion_minimal_switch_sets",
    "operator:decision_switch.partition_decision_signatures",
    "operator:decision_switch.compute_registered_information_relevance",
    "operator:decision_switch.assign_pareto_layers",
)
_ATOM_RULES = {
    "shock_magnitude_assumption": (
        "shock.magnitude",
        "hypothetical_assumption_change",
        "synthetic_atom_reveal",
    ),
    "shock_duration_assumption": (
        "shock.duration",
        "hypothetical_assumption_change",
        "synthetic_atom_reveal",
    ),
    "substitution_fraction_assumption": (
        "substitution.fraction",
        "hypothetical_assumption_change",
        "synthetic_atom_reveal",
    ),
    "buffer_duration_assumption": (
        "buffer.duration_offset",
        "hypothetical_assumption_change",
        "synthetic_atom_reveal",
    ),
    "constraint_boundary": (
        "constraint.threshold",
        "hypothetical_normative_boundary_change",
        "not_observable_normative_boundary",
    ),
}
_REQUEST_LIMITATIONS = sorted(
    (
        "registered_binary_lattice_not_real_world_state_space",
        "robust_option_set_not_real_world_feasibility_or_advice",
        "minimal_switches_only_within_registered_lattice",
        "information_relevance_is_set_reduction_not_expected_value_entropy_or_probability",
        "no_forecast_recommendation_optimization_or_purchase_decision",
        "non_synthetic_rendering_requires_claim_bundle",
    )
)
_EXECUTION_LIMITATIONS = sorted(
    (
        "robust_option_sets_apply_only_to_registered_hypothetical_bounds",
        "minimality_is_only_within_complete_registered_binary_lattice",
        "decision_signature_reduction_is_not_entropy_probability_expected_value_or_utility",
        "pareto_layers_are_not_total_priority_recommendation_or_purchase_advice",
        "no_real_world_feasibility_joint_distribution_forecast_or_optimization",
        "non_synthetic_rendering_requires_claim_bundle",
    )
)
_GUARDRAILS = {
    "real_world_feasibility_claimed": False,
    "joint_feasibility_claimed": False,
    "causal_attribution_performed": False,
    "forecast_performed": False,
    "probability_assigned": False,
    "entropy_computed": False,
    "expected_value_computed": False,
    "recommendation_generated": False,
    "objective_optimized": False,
    "purchase_recommended": False,
    "candidate_set_completeness_claimed": False,
    "global_minimality_claimed": False,
}


class DecisionSwitchError(ValueError):
    """Stable fail-closed Decision Switch refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise DecisionSwitchError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("decision_switch_json_duplicate_key", key)
        result[key] = value
    return result


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("decision_switch_json_non_finite"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DecisionSwitchError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def parse_request_bytes(raw: bytes) -> dict[str, Any]:
    """Parse request bytes with duplicate-key and non-finite rejection."""

    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("decision_switch_json_non_finite"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DecisionSwitchError("decision_switch_request_json_invalid") from exc
    if not isinstance(value, dict):
        _fail("decision_switch_request_json_invalid")
    return cast(dict[str, Any], value)


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


def _semantic_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except Exception as exc:  # normalized into the extension's stable refusal
        raise DecisionSwitchError("decision_switch_typed_value_invalid") from exc


def _typed_check(document: Mapping[str, Any], code: str) -> None:
    try:
        digest = event_ledger_extension.typed_record_sha256(document)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise DecisionSwitchError(code, exc.code) from exc
    if digest != document.get("record_sha256"):
        _fail(code)


def _schema_validator(
    primary: Mapping[str, Any], references: Sequence[Mapping[str, Any]]
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(primary)
        for reference in references:
            Draft202012Validator.check_schema(reference)
    except SchemaError as exc:
        raise DecisionSwitchError("decision_switch_schema_meta_invalid") from exc
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


def _profile() -> tuple[
    dict[str, Any],
    str,
    dict[str, str],
    dict[str, Any],
    Draft202012Validator,
    Draft202012Validator,
]:
    _, profile, profile_sha = _read_json(PROFILE_PATH, "decision_switch_profile_invalid")
    if (
        profile.get("schema_version") != "0.1.0"
        or profile.get("extension_id")
        != "oges:extension:decision-switch-information-priority"
        or profile.get("version") != "0.1.0"
        or profile.get("effective") != "2026-08-09"
        or profile.get("status") != "public_draft_contract_only_synthetic_fixtures"
    ):
        _fail("decision_switch_profile_identity_invalid")
    rows = profile.get("bound_files")
    if not isinstance(rows, list):
        _fail("decision_switch_profile_files_invalid")
    by_kind: dict[str, str] = {}
    documents: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"kind", "path", "sha256"}:
            _fail("decision_switch_profile_files_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in by_kind:
            _fail("decision_switch_profile_files_invalid")
        path = _safe_file(ROOT, row["path"], "decision_switch_profile_path_invalid")
        if path.suffix == ".json":
            _, document, digest = _read_json(path, "decision_switch_profile_file_invalid")
            documents[kind] = document
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != row["sha256"]:
            _fail("decision_switch_profile_digest_mismatch", kind)
        by_kind[kind] = digest
    if set(by_kind) != _BOUND_KINDS:
        _fail("decision_switch_profile_files_invalid")

    for field, code in (
        ("reference_implementation", "decision_switch_implementation_invalid"),
        ("conformance_test", "decision_switch_conformance_test_invalid"),
    ):
        row = profile.get(field)
        if not isinstance(row, dict) or set(row) != {"path", "sha256"}:
            _fail(code)
        path = _safe_file(ROOT, row["path"], code)
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            _fail("decision_switch_profile_digest_mismatch", field)

    operators = documents["operator_registry"]
    if (
        operators.get("registry_id")
        != "oges:decision-switch-information-priority:operators"
        or operators.get("default_policy") != "deny"
        or tuple(row.get("operator_id") for row in operators.get("operators", []))
        != _OPERATORS
    ):
        _fail("decision_switch_operator_registry_invalid")
    methods = documents["resolution_method_registry"]
    method_rows = methods.get("methods")
    if (
        methods.get("registry_id") != "oges:decision-switch:resolution-methods"
        or methods.get("default_policy") != "deny"
        or not isinstance(method_rows, list)
        or len(method_rows) != 1
        or method_rows[0].get("method_id")
        != "method:decision-switch.synthetic-atom-reveal"
        or method_rows[0].get("trust_class") != "synthetic_contract_only"
    ):
        _fail("decision_switch_resolution_registry_invalid")

    common = documents["common_schema"]
    request = documents["request_schema"]
    execution = documents["execution_schema"]
    request_refs = (
        common,
        documents["registered_option_schema"],
        documents["constraint_slot_schema"],
        documents["switch_atom_schema"],
        documents["artifact_bundle_schema"],
        documents["information_candidate_schema"],
    )
    return (
        profile,
        profile_sha,
        by_kind,
        methods,
        _schema_validator(request, request_refs),
        _schema_validator(execution, (common,)),
    )


def _method_sha(row: Mapping[str, Any]) -> str:
    return _semantic_sha(dict(row))


def _interval(value: Mapping[str, Any], denominator: str | None = None) -> dict[str, Any]:
    return {
        "value_kind": "interval",
        "lower": value["lower"],
        "upper": value["upper"],
        "unit": value["unit"],
        "denominator": denominator,
    }


def _semantic_value(bundle: Mapping[str, Any], selector: str, target_id: str | None) -> dict[str, Any]:
    scenario = bundle["scenario"]
    proof_request = bundle["scenario_proof_request"]
    if selector == "shock.magnitude" and target_id is None:
        return _interval(scenario["shock"]["magnitude"])
    if selector == "shock.duration" and target_id is None:
        return _interval(scenario["shock"]["duration"])
    if selector == "substitution.fraction" and target_id is not None:
        rows = [
            row
            for row in scenario["substitutions"]
            if row["applies_to_edge_id"] == target_id
        ]
        if len(rows) == 1:
            return _interval(rows[0]["fraction_of_gross_effect"])
    if selector == "buffer.duration_offset" and target_id is not None:
        rows = [
            row
            for row in scenario["buffers"]
            if row["applies_to_target_entity_id"] == target_id
        ]
        if len(rows) == 1:
            return _interval(rows[0]["duration_offset"])
    if selector == "constraint.threshold" and target_id is not None:
        rows = [row for row in proof_request["constraints"] if row["constraint_id"] == target_id]
        if len(rows) == 1:
            threshold = rows[0]["threshold"]
            return {
                "value_kind": "scalar",
                "value": threshold["value"],
                "unit": threshold["unit"],
                "denominator": threshold["denominator"],
            }
    _fail("decision_switch_atom_selector_invalid")


def _mask_selector(
    scenario: dict[str, Any],
    proof_request: dict[str, Any],
    selector: str,
    target_id: str | None,
    atom_id: str,
) -> None:
    marker = {"registered_atom_id": atom_id}
    if selector == "shock.magnitude" and target_id is None:
        scenario["shock"]["magnitude"] = marker
        return
    if selector == "shock.duration" and target_id is None:
        scenario["shock"]["duration"] = marker
        return
    if selector == "substitution.fraction" and target_id is not None:
        for row in scenario["substitutions"]:
            if row["applies_to_edge_id"] == target_id:
                row["fraction_of_gross_effect"] = marker
                return
    if selector == "buffer.duration_offset" and target_id is not None:
        for row in scenario["buffers"]:
            if row["applies_to_target_entity_id"] == target_id:
                row["duration_offset"] = marker
                return
    if selector == "constraint.threshold" and target_id is not None:
        for row in proof_request["constraints"]:
            if row["constraint_id"] == target_id:
                row["threshold"] = marker
                return
    _fail("decision_switch_atom_selector_invalid")


def _semantic_skeleton(
    bundle: Mapping[str, Any], atom_rows: Sequence[tuple[str, str, str | None]]
) -> str:
    scenario = copy.deepcopy(bundle["scenario"])
    proof_request = copy.deepcopy(bundle["scenario_proof_request"])
    path_semantics = _path_semantic_projections(bundle)
    scenario.pop("record_sha256", None)
    scenario.pop("scenario_id", None)
    proof_request.pop("record_sha256", None)
    proof_request.pop("request_id", None)
    proof_request.pop("scenario_binding", None)
    for row in proof_request["constraints"]:
        row.pop("record_sha256", None)
        row.pop("scenario_id", None)
        row.pop("scenario_record_sha256", None)
        row.pop("compilation_record_sha256", None)
        path_id = row.pop("path_id")
        if path_id not in path_semantics:
            _fail("decision_switch_path_binding_invalid")
        row["path_semantic_sha256"] = _semantic_sha(path_semantics[path_id])
    for row in proof_request["hypotheses"]:
        row.pop("record_sha256", None)
        row.pop("scenario_id", None)
        row.pop("scenario_record_sha256", None)
        row.pop("compilation_record_sha256", None)
        path_id = row.pop("path_id")
        if path_id not in path_semantics:
            _fail("decision_switch_path_binding_invalid")
        row["path_semantic_sha256"] = _semantic_sha(path_semantics[path_id])
    for atom_id, selector, target_id in atom_rows:
        _mask_selector(scenario, proof_request, selector, target_id, atom_id)
    return _semantic_sha({"scenario": scenario, "scenario_proof_request": proof_request})


def _path_semantic_projections(
    bundle: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return each referenced path's normalized non-scenario-derived semantics."""

    compilation = bundle["compilation"]
    proof_request = bundle["scenario_proof_request"]
    referenced = {
        row["path_id"]
        for kind in ("constraints", "hypotheses")
        for row in proof_request[kind]
    }
    by_id = {row["path_id"]: row for row in compilation["paths"]}
    if not referenced <= set(by_id):
        _fail("decision_switch_path_binding_invalid")
    projected: dict[str, dict[str, Any]] = {}
    for path_id in sorted(referenced):
        path = by_id[path_id]
        projected[path_id] = {
            "entry_entity_id": path["entry_entity_id"],
            "entity_ids": path["entity_ids"],
            "edge_ids": path["edge_ids"],
            "hops": [
                {
                    "edge_id": hop["edge_id"],
                    "source_entity_id": hop["source_entity_id"],
                    "target_entity_id": hop["target_entity_id"],
                    "edge_type": hop["edge_type"],
                    "quantification_status": hop["quantification_status"],
                    "magnitude": hop["magnitude"],
                    "freshness": hop["freshness"],
                    "coverage": hop["coverage"],
                    "evidence_ids": hop["evidence_ids"],
                    "limitation_codes": hop["limitation_codes"],
                }
                for hop in path["hops"]
            ],
            "quantification_status": path["quantification_status"],
            "reason_code": path["reason_code"],
            "gap_codes": path["gap_codes"],
            "limitation_codes": path["limitation_codes"],
        }
    return projected


def _path_semantics(bundle: Mapping[str, Any]) -> str:
    """Bind the complete referenced path set independent of ephemeral path IDs."""

    projections = _path_semantic_projections(bundle)
    return _semantic_sha(
        sorted(projections.values(), key=lambda row: _semantic_sha(row))
    )


def _powerset(atom_ids: Sequence[str]) -> list[tuple[str, ...]]:
    return [
        tuple(combo)
        for size in range(len(atom_ids) + 1)
        for combo in itertools.combinations(atom_ids, size)
    ]


def _validate_structure(
    request: Mapping[str, Any],
    validator: Draft202012Validator,
    methods: Mapping[str, Any],
) -> tuple[
    list[str],
    list[str],
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
]:
    _schema_check(request, validator, "decision_switch_request_schema_invalid")
    _typed_check(request, "decision_switch_request_digest_invalid")
    if request["guardrails"] != _GUARDRAILS or request["limitations"] != _REQUEST_LIMITATIONS:
        _fail("decision_switch_guardrails_invalid")
    created = _utc(request["created_at"], "decision_switch_time_invalid")
    evaluated = _utc(request["evaluation_as_of"], "decision_switch_time_invalid")
    generated = _utc(request["release"]["generated_at"], "decision_switch_time_invalid")
    cutoff = _utc(request["knowledge_cutoff"], "decision_switch_time_invalid")
    if not (generated <= cutoff <= created <= evaluated):
        _fail("decision_switch_time_invalid")

    options = request["options"]
    if options != sorted(options, key=lambda row: row["option_id"]):
        _fail("decision_switch_option_order_invalid")
    option_ids = [row["option_id"] for row in options]
    if len(option_ids) != len(set(option_ids)):
        _fail("decision_switch_option_duplicate")
    slots = request["constraint_slots"]
    if slots != sorted(slots, key=lambda row: row["slot_id"]):
        _fail("decision_switch_slot_order_invalid")
    slot_by_id = {row["slot_id"]: row for row in slots}
    if len(slot_by_id) != len(slots):
        _fail("decision_switch_slot_duplicate")
    for option in options:
        ids = option["required_slot_ids"]
        if ids != sorted(ids) or set(ids) != set(slot_by_id):
            _fail("decision_switch_option_slot_invalid")
    per_option_constraints: dict[str, set[str]] = {option_id: set() for option_id in option_ids}
    for slot in slots:
        bindings = slot["option_bindings"]
        if bindings != sorted(bindings, key=lambda row: row["option_id"]):
            _fail("decision_switch_slot_binding_order_invalid")
        if [row["option_id"] for row in bindings] != option_ids:
            _fail("decision_switch_slot_option_partition_invalid")
        for row in bindings:
            if row["constraint_id"] in per_option_constraints[row["option_id"]]:
                _fail("decision_switch_constraint_reused_across_slots")
            per_option_constraints[row["option_id"]].add(row["constraint_id"])

    atoms = request["atoms"]
    if atoms != sorted(atoms, key=lambda row: row["atom_id"]):
        _fail("decision_switch_atom_order_invalid")
    atom_by_id = {row["atom_id"]: row for row in atoms}
    if len(atom_by_id) != len(atoms):
        _fail("decision_switch_atom_duplicate")
    ownership: set[tuple[str, str, str | None]] = set()
    for atom in atoms:
        if (
            atom["selector_kind"],
            atom["epistemic_kind"],
            atom["observation_eligibility"],
        ) != _ATOM_RULES[atom["atom_kind"]]:
            _fail("decision_switch_atom_semantics_invalid")
        values = atom["option_values"]
        if values != sorted(values, key=lambda row: row["option_id"]):
            _fail("decision_switch_atom_value_order_invalid")
        scoped_ids = [row["option_id"] for row in values]
        if len(scoped_ids) != len(set(scoped_ids)) or not set(scoped_ids) <= set(option_ids):
            _fail("decision_switch_atom_option_scope_invalid")
        for row in values:
            target = row["target_id"]
            selector = atom["selector_kind"]
            if (selector.startswith("shock.") and target is not None) or (
                not selector.startswith("shock.") and target is None
            ):
                _fail("decision_switch_atom_target_invalid")
            key = (row["option_id"], selector, target)
            if key in ownership:
                _fail("decision_switch_atom_selector_duplicate")
            ownership.add(key)
            baseline_sha = _semantic_sha(row["baseline_value"])
            alternative_sha = _semantic_sha(row["alternative_value"])
            if (
                baseline_sha != row["baseline_value_sha256"]
                or alternative_sha != row["alternative_value_sha256"]
                or baseline_sha == alternative_sha
            ):
                _fail("decision_switch_atom_value_digest_invalid")

    atom_ids = list(atom_by_id)
    expected_sets = _powerset(atom_ids)
    variants = request["variants"]
    actual_sets = [tuple(row["active_atom_ids"]) for row in variants]
    if actual_sets != expected_sets or len(variants) * len(option_ids) > 384:
        _fail("decision_switch_lattice_incomplete")
    variant_by_id: dict[str, Mapping[str, Any]] = {}
    bundle_ids: set[str] = set()
    for variant in variants:
        if variant["variant_id"] in variant_by_id:
            _fail("decision_switch_variant_duplicate")
        variant_by_id[variant["variant_id"]] = variant
        bundles = variant["bundles"]
        if bundles != sorted(bundles, key=lambda row: row["option_id"]):
            _fail("decision_switch_bundle_order_invalid")
        if [row["option_id"] for row in bundles] != option_ids:
            _fail("decision_switch_bundle_option_partition_invalid")
        for bundle in bundles:
            _typed_check(bundle, "decision_switch_bundle_digest_invalid")
            if bundle["variant_id"] != variant["variant_id"]:
                _fail("decision_switch_bundle_variant_mismatch")
            if bundle["bundle_id"] in bundle_ids:
                _fail("decision_switch_bundle_id_duplicate")
            bundle_ids.add(bundle["bundle_id"])

    method_row = cast(list[dict[str, Any]], methods["methods"])[0]
    method_sha = _method_sha(method_row)
    candidates = request["information_candidates"]
    if candidates != sorted(candidates, key=lambda row: row["candidate_id"]):
        _fail("decision_switch_candidate_order_invalid")
    candidate_by_id: dict[str, Mapping[str, Any]] = {}
    candidate_scopes: set[tuple[str, ...]] = set()
    for candidate in candidates:
        if candidate["candidate_id"] in candidate_by_id:
            _fail("decision_switch_candidate_duplicate")
        candidate_by_id[candidate["candidate_id"]] = candidate
        candidate_atoms = candidate["atom_ids"]
        if candidate_atoms != sorted(candidate_atoms) or not set(candidate_atoms) <= set(atom_ids):
            _fail("decision_switch_candidate_atom_invalid")
        scope = tuple(candidate_atoms)
        if scope in candidate_scopes:
            _fail("decision_switch_candidate_scope_duplicate")
        candidate_scopes.add(scope)
        if candidate["resolution_method_sha256"] != method_sha:
            _fail("decision_switch_resolution_method_drift")
        if any(
            atom_by_id[atom_id]["observation_eligibility"]
            != "synthetic_atom_reveal"
            for atom_id in candidate_atoms
        ):
            _fail("decision_switch_normative_atom_not_observable")
    return option_ids, atom_ids, slot_by_id, atom_by_id, variant_by_id


def _validate_bundle_context(
    bundle: Mapping[str, Any],
    request: Mapping[str, Any],
    manifest_path: Path,
    kwargs: Mapping[str, Any],
) -> None:
    scenario = bundle["scenario"]
    compilation = bundle["compilation"]
    proof_request = bundle["scenario_proof_request"]
    proof_execution = bundle["scenario_proof_execution"]
    try:
        scenario_proof.validate_scenario_proof(
            proof_execution,
            manifest_path,
            scenario,
            compilation,
            proof_request,
            **kwargs,
        )
    except scenario_proof.ScenarioProofError as exc:
        raise DecisionSwitchError("decision_switch_scenario_proof_invalid", exc.code) from exc
    if (
        scenario["release"] != request["release"]
        or scenario["knowledge_cutoff"] != request["knowledge_cutoff"]
        or scenario["event_id"] != request["event_id"]
        or scenario["target_entity_id"] != request["target_entity_id"]
        or _utc(proof_request["evaluation_as_of"], "decision_switch_time_invalid")
        > _utc(request["evaluation_as_of"], "decision_switch_time_invalid")
    ):
        _fail("decision_switch_bundle_context_mismatch")


def _atom_rows_for_option(
    atoms: Sequence[Mapping[str, Any]], option_id: str
) -> list[tuple[str, str, str | None, Mapping[str, Any]]]:
    rows: list[tuple[str, str, str | None, Mapping[str, Any]]] = []
    for atom in atoms:
        for value in atom["option_values"]:
            if value["option_id"] == option_id:
                rows.append(
                    (atom["atom_id"], atom["selector_kind"], value["target_id"], value)
                )
    return rows


def _validate_variant_semantics(
    request: Mapping[str, Any], option_ids: Sequence[str], atom_ids: Sequence[str]
) -> None:
    variants = request["variants"]
    baseline = {row["option_id"]: row for row in variants[0]["bundles"]}
    atoms = request["atoms"]
    for option_id in option_ids:
        rows = _atom_rows_for_option(atoms, option_id)
        skeleton_rows = [(atom_id, selector, target) for atom_id, selector, target, _ in rows]
        baseline_skeleton = _semantic_skeleton(baseline[option_id], skeleton_rows)
        baseline_paths = _path_semantics(baseline[option_id])
        for variant in variants:
            active = set(variant["active_atom_ids"])
            bundle = next(row for row in variant["bundles"] if row["option_id"] == option_id)
            if _semantic_skeleton(bundle, skeleton_rows) != baseline_skeleton:
                _fail("decision_switch_hidden_semantic_change")
            if _path_semantics(bundle) != baseline_paths:
                _fail("decision_switch_path_semantics_changed")
            for atom_id, selector, target, value in rows:
                actual = _semantic_value(bundle, selector, target)
                expected = value[
                    "alternative_value" if atom_id in active else "baseline_value"
                ]
                if actual != expected or _semantic_sha(actual) != value[
                    "alternative_value_sha256"
                    if atom_id in active
                    else "baseline_value_sha256"
                ]:
                    _fail("decision_switch_atom_state_mismatch")
    if set(atom_ids) != {row["atom_id"] for row in atoms}:
        _fail("decision_switch_atom_partition_invalid")


def _slot_bindings(request: Mapping[str, Any]) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for slot in request["constraint_slots"]:
        for binding in slot["option_bindings"]:
            result[(binding["option_id"], slot["slot_id"])] = binding["constraint_id"]
    return result


def _variant_result(
    request: Mapping[str, Any], variant: Mapping[str, Any], slot_by_id: Mapping[str, Any]
) -> dict[str, Any]:
    binding = _slot_bindings(request)
    bundle_by_option = {row["option_id"]: row for row in variant["bundles"]}
    option_states: list[dict[str, Any]] = []
    for option in request["options"]:
        option_id = option["option_id"]
        proof_constraints = {
            row["constraint_id"]: row
            for row in bundle_by_option[option_id]["scenario_proof_execution"]["constraints"]
        }
        expected_constraint_ids = {
            binding[(option_id, slot_id)] for slot_id in slot_by_id
        }
        if set(proof_constraints) != expected_constraint_ids:
            _fail("decision_switch_constraint_partition_invalid")
        slot_states: list[dict[str, Any]] = []
        unavailable = False
        violated = False
        mixed = False
        for slot_id in option["required_slot_ids"]:
            slot = slot_by_id[slot_id]
            constraint_id = binding[(option_id, slot_id)]
            if constraint_id not in proof_constraints:
                _fail("decision_switch_constraint_missing")
            row = proof_constraints[constraint_id]
            if (
                row["metric"] != slot["metric"]
                or row["operator"] != slot["operator"]
                or row["threshold"]["unit"] != slot["unit"]
                or row["threshold"]["denominator"] != slot["denominator"]
            ):
                _fail("decision_switch_constraint_slot_mismatch")
            state = {
                "slot_id": slot_id,
                "constraint_id": constraint_id,
                "interval_relation": row["interval_relation"],
                "readiness": row["readiness"],
                "scenario_feasibility_status": row["scenario_feasibility_status"],
            }
            slot_states.append(state)
            unavailable |= row["readiness"] != "current_inputs" or row[
                "interval_relation"
            ] == "not_evaluable"
            violated |= row["interval_relation"] == "no_registered_values_satisfy"
            mixed |= row["interval_relation"] == "mixed_within_registered_interval"
        if unavailable:
            status = "indeterminate_due_to_mixed_or_unavailable_registered_inputs"
        elif violated:
            status = "excluded_by_registered_hypothetical_violation"
        elif mixed:
            status = "indeterminate_due_to_mixed_or_unavailable_registered_inputs"
        else:
            status = "robustly_satisfies_all_registered_hypothetical_bounds"
        option_states.append(
            {
                "option_id": option_id,
                "status": status,
                "slot_states": slot_states,
                "real_world_feasibility_claimed": False,
                "joint_feasibility_claimed": False,
            }
        )
    robust = [
        row["option_id"]
        for row in option_states
        if row["status"] == "robustly_satisfies_all_registered_hypothetical_bounds"
    ]
    excluded = [
        row["option_id"]
        for row in option_states
        if row["status"] == "excluded_by_registered_hypothetical_violation"
    ]
    indeterminate = [
        row["option_id"]
        for row in option_states
        if row["status"] == "indeterminate_due_to_mixed_or_unavailable_registered_inputs"
    ]
    signature = _semantic_sha(
        {"robust": robust, "excluded": excluded, "indeterminate": indeterminate}
    )
    return {
        "variant_id": variant["variant_id"],
        "active_atom_ids": variant["active_atom_ids"],
        "option_states": option_states,
        "robust_option_ids": robust,
        "excluded_option_ids": excluded,
        "indeterminate_option_ids": indeterminate,
        "decision_signature_sha256": signature,
    }


def _minimal_switches(
    decision_case_id: str, variants: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    baseline = variants[0]
    baseline_atoms: set[str] = set()
    baseline_robust = set(baseline["robust_option_ids"])
    baseline_sha = _semantic_sha({"robust_option_ids": sorted(baseline_robust)})
    changed = [
        row
        for row in variants[1:]
        if set(row["robust_option_ids"]) != baseline_robust
    ]
    changed_sets = [set(row["active_atom_ids"]) for row in changed]
    result: list[dict[str, Any]] = []
    for row, atoms in zip(changed, changed_sets):
        if any(other < atoms and other != baseline_atoms for other in changed_sets):
            continue
        robust = set(row["robust_option_ids"])
        resulting_sha = _semantic_sha({"robust_option_ids": sorted(robust)})
        token = _semantic_sha(
            {
                "decision_case_id": decision_case_id,
                "atom_ids": sorted(atoms),
                "baseline_robust_set_sha256": baseline_sha,
                "resulting_robust_set_sha256": resulting_sha,
            }
        )[:24]
        result.append(
            {
                "switch_set_id": f"switch:decision.{token}",
                "atom_ids": sorted(atoms),
                "witness_variant_id": row["variant_id"],
                "baseline_robust_set_sha256": baseline_sha,
                "resulting_robust_set_sha256": resulting_sha,
                "added_option_ids": sorted(robust - baseline_robust),
                "removed_option_ids": sorted(baseline_robust - robust),
                "minimal_within": "complete_registered_binary_lattice",
                "global_minimality_claimed": False,
            }
        )
    return sorted(result, key=lambda row: (len(row["atom_ids"]), row["atom_ids"]))


def _candidate_vector(
    candidate: Mapping[str, Any],
    variants: Sequence[Mapping[str, Any]],
    option_ids: Sequence[str],
    all_atom_ids: Sequence[str],
) -> dict[str, Any]:
    candidate_atoms = set(candidate["atom_ids"])
    global_signatures = {row["decision_signature_sha256"] for row in variants}
    cells: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    fibers: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    for row in variants:
        active = set(row["active_atom_ids"])
        cell_key = tuple(sorted(active & candidate_atoms))
        fiber_key = tuple(sorted(active - candidate_atoms))
        cells.setdefault(cell_key, []).append(row)
        fibers.setdefault(fiber_key, []).append(row)
    outcome_cells = [
        {
            "active_candidate_atom_ids": list(key),
            "variant_count": len(rows),
            "distinct_decision_signatures": len(
                {row["decision_signature_sha256"] for row in rows}
            ),
        }
        for key, rows in sorted(cells.items())
    ]
    remaining: list[int] = [
        cast(int, row["distinct_decision_signatures"]) for row in outcome_cells
    ]
    changed_fibers = 0
    affected: set[str] = set()
    for rows in fibers.values():
        if len({row["decision_signature_sha256"] for row in rows}) > 1:
            changed_fibers += 1
        for option_id in option_ids:
            statuses = {
                next(
                    state["status"]
                    for state in row["option_states"]
                    if state["option_id"] == option_id
                )
                for row in rows
            }
            if len(statuses) > 1:
                affected.add(option_id)
    before = len(global_signatures)
    return {
        "candidate_id": candidate["candidate_id"],
        "atom_ids": candidate["atom_ids"],
        "resolution_method_id": candidate["resolution_method_id"],
        "resolution_method_sha256": candidate["resolution_method_sha256"],
        "decision_signatures_before": before,
        "outcome_cells": outcome_cells,
        "worst_case_remaining_signatures": max(remaining),
        "best_case_remaining_signatures": min(remaining),
        "guaranteed_signature_reduction": before - max(remaining),
        "maximum_signature_reduction": before - min(remaining),
        "changed_background_fibers": changed_fibers,
        "background_fiber_denominator": 2 ** (len(all_atom_ids) - len(candidate_atoms)),
        "affected_option_ids": sorted(affected),
        "pareto_layer": 0,
        "rank_kind": "pareto_layer_not_total_priority_or_recommendation",
        "probability_assigned": False,
        "entropy_computed": False,
        "expected_value_computed": False,
        "recommendation_generated": False,
    }


def _dominates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_fraction = left["changed_background_fibers"] * right["background_fiber_denominator"]
    right_fraction = right["changed_background_fibers"] * left["background_fiber_denominator"]
    left_dims = (
        left["guaranteed_signature_reduction"],
        left_fraction,
        len(left["affected_option_ids"]),
        -len(left["atom_ids"]),
    )
    right_dims = (
        right["guaranteed_signature_reduction"],
        right_fraction,
        len(right["affected_option_ids"]),
        -len(right["atom_ids"]),
    )
    return all(a >= b for a, b in zip(left_dims, right_dims)) and any(
        a > b for a, b in zip(left_dims, right_dims)
    )


def _pareto_layers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    remaining = list(rows)
    layer = 1
    while remaining:
        front = [
            row
            for row in remaining
            if not any(_dominates(other, row) for other in remaining if other is not row)
        ]
        if not front:
            _fail("decision_switch_pareto_invalid")
        for row in front:
            row["pareto_layer"] = layer
        remaining = [row for row in remaining if row not in front]
        layer += 1
    return sorted(rows, key=lambda row: (row["pareto_layer"], row["candidate_id"]))


def _build_execution(
    request: Mapping[str, Any],
    profile: Mapping[str, Any],
    profile_sha: str,
    hashes: Mapping[str, str],
    slot_by_id: Mapping[str, Any],
    option_ids: Sequence[str],
    atom_ids: Sequence[str],
) -> dict[str, Any]:
    variant_results = [
        _variant_result(request, variant, slot_by_id) for variant in request["variants"]
    ]
    switches = _minimal_switches(request["decision_case_id"], variant_results)
    information = _pareto_layers(
        [
            _candidate_vector(candidate, variant_results, option_ids, atom_ids)
            for candidate in request["information_candidates"]
        ]
    )
    baseline = variant_results[0]
    implementation_sha = cast(str, profile["reference_implementation"]["sha256"])
    return {
        "object_type": "decision_switch_execution",
        "schema_version": "0.1.0",
        "record_sha256": "0" * 64,
        "execution_id": f"execution:{request['decision_case_id']}",
        "profile": {
            "extension_id": "oges:extension:decision-switch-information-priority",
            "version": "0.1.0",
            "profile_sha256": profile_sha,
            "request_schema_sha256": hashes["request_schema"],
            "execution_schema_sha256": hashes["execution_schema"],
            "operator_registry_sha256": hashes["operator_registry"],
            "resolution_method_registry_sha256": hashes[
                "resolution_method_registry"
            ],
            "scenario_proof_profile_sha256": hashes["scenario_proof_profile"],
            "scenario_proof_implementation_sha256": hashes[
                "scenario_proof_implementation"
            ],
            "reference_implementation_sha256": implementation_sha,
        },
        "decision_case": {
            "decision_case_id": request["decision_case_id"],
            "request_record_sha256": request["record_sha256"],
            "created_at": request["created_at"],
            "evaluation_as_of": request["evaluation_as_of"],
            "release_id": request["release"]["release_id"],
            "release_record_sha256": request["release"]["record_sha256"],
            "knowledge_cutoff": request["knowledge_cutoff"],
            "event_id": request["event_id"],
            "target_entity_id": request["target_entity_id"],
        },
        "lattice": {
            "option_denominator": len(option_ids),
            "atom_denominator": len(atom_ids),
            "expected_variant_denominator": 2 ** len(atom_ids),
            "observed_variant_denominator": len(variant_results),
            "bundle_denominator": len(option_ids) * len(variant_results),
            "baseline_variant_id": baseline["variant_id"],
            "baseline_decision_signature_sha256": baseline[
                "decision_signature_sha256"
            ],
            "variants": variant_results,
            "powerset_complete": True,
        },
        "minimal_switch_sets": switches,
        "information_relevance": information,
        "counts": {
            "options": len(option_ids),
            "constraint_slots": len(slot_by_id),
            "atoms": len(atom_ids),
            "variants": len(variant_results),
            "bundles": len(option_ids) * len(variant_results),
            "minimal_switch_sets": len(switches),
            "information_candidates": len(information),
            "pareto_layers": max(row["pareto_layer"] for row in information),
        },
        "result": {
            "status": "complete_registered_lattice_assessed",
            "trust_class": "unauthenticated_contract_execution",
            "public_claim_state": "not_licensed_for_production_rendering",
            **_GUARDRAILS,
        },
        "limitations": _EXECUTION_LIMITATIONS,
    }


def execute_decision_switch(
    manifest_path: Path,
    request: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Return the exact typed finite-lattice execution or refuse entirely."""

    profile, profile_sha, hashes, methods, request_validator, execution_validator = (
        _profile()
    )
    option_ids, atom_ids, slot_by_id, _, _ = _validate_structure(
        request, request_validator, methods
    )
    for variant in request["variants"]:
        for bundle in variant["bundles"]:
            _validate_bundle_context(bundle, request, manifest_path, kwargs)
    _validate_variant_semantics(request, option_ids, atom_ids)
    document = event_ledger_extension.seal_record(
        _build_execution(
            request,
            profile,
            profile_sha,
            hashes,
            slot_by_id,
            option_ids,
            atom_ids,
        )
    )
    _schema_check(document, execution_validator, "decision_switch_execution_schema_invalid")
    _typed_check(document, "decision_switch_execution_digest_invalid")
    return cast(dict[str, Any], document)


def validate_decision_switch(
    document: Mapping[str, Any],
    manifest_path: Path,
    request: Mapping[str, Any],
    **kwargs: Any,
) -> None:
    """Recompute the complete lattice and require exact output equality."""

    expected = execute_decision_switch(manifest_path, request, **kwargs)
    if document != expected:
        _fail("decision_switch_execution_mismatch")


def seal_record(document: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a request, bundle, or nested record with shared typed canonicalization."""

    return cast(dict[str, Any], event_ledger_extension.seal_record(document))


def semantic_value_sha256(value: Mapping[str, Any]) -> str:
    """Return the shared typed-canonical digest for an atom semantic value."""

    return _semantic_sha(value)


def resolution_method_sha256() -> str:
    """Return the exact sole synthetic resolution-method row digest."""

    _, methods, _ = _read_json(
        EXTENSION / "resolution-method-registry.json",
        "decision_switch_resolution_registry_invalid",
    )
    rows = methods.get("methods")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        _fail("decision_switch_resolution_registry_invalid")
    return _method_sha(rows[0])
