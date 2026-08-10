"""Validate one inactive evidence-output consumer registry extension.

Dependency direction is deliberately one-way: this downstream contract pins
the unchanged incumbent evidence-output registry and the incumbent analytical
clause artifacts.  The analytical clause compiler never imports, loads or pins
this module or its profile.  Validation prepares a later migration but creates
no ClauseSourceView, renderer, receipt, artifact, route or public authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn, cast

from . import analytical_clause as ac

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "governance" / "evidence_output_renderer_consumer_profile.json"
EVIDENCE_OUTPUT_REGISTRY_PATH = ROOT / "governance" / "evidence_output_registry.json"

_VERSION = "0.1.0"
_PROFILE_ID = "igrm:evidence-output-renderer-consumers:0.1.0"
_DEPENDENCY_KINDS = {
    "analytical_clause_contract",
    "analytical_clause_limitations",
    "analytical_clause_runtime",
    "analytical_clause_source_profile",
}
_OUTPUT_ROLES = {
    "output:research_package": "research",
    "output:board_brief": "board",
    "output:newsroom_claim_card": "newsroom",
    "output:offline_audit_bundle": "offline",
}
_BRANCH_IDS = ("branch:path_found", "branch:no_path")
_ATOMICITY = "one_complete_analytical_clause_value"
_REGISTERED_SOURCE_FIELD_SIGNATURES: Mapping[
    str, tuple[str, str, str | None, str]
] = MappingProxyType(
    {
        "coverage.row": ("exact_bundle_denominator", "object", "coverage_rows", _ATOMICITY),
        "event.canonical_label": ("exactly_one", "text", None, _ATOMICITY),
        "event.class": ("exactly_one", "identifier", None, _ATOMICITY),
        "event.last_verified_at": ("exactly_one", "datetime", None, _ATOMICITY),
        "event.record_status": ("exactly_one", "identifier", None, _ATOMICITY),
        "event.starts_at": ("exactly_one", "datetime", None, _ATOMICITY),
        "evidence.content_availability": (
            "exact_bundle_denominator",
            "identifier",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.identity": (
            "exact_bundle_denominator",
            "object",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.observed_at": (
            "exact_bundle_denominator",
            "datetime",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.public_url": (
            "exact_bundle_denominator",
            "citation_metadata",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.published_at": (
            "exact_bundle_denominator",
            "datetime",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.rights_use": (
            "exact_bundle_denominator",
            "identifier",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.source_id": (
            "exact_bundle_denominator",
            "identifier",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.title": (
            "exact_bundle_denominator",
            "citation_metadata",
            "evidence_items",
            _ATOMICITY,
        ),
        "evidence.verification_status": (
            "exact_bundle_denominator",
            "identifier",
            "evidence_items",
            _ATOMICITY,
        ),
        "provenance.source_object_ref": (
            "exact_bundle_denominator",
            "object",
            "object_evidence_rows",
            _ATOMICITY,
        ),
        "release.generated_at": ("exactly_one", "datetime", None, _ATOMICITY),
        "target.canonical_name": ("exactly_one", "text", None, _ATOMICITY),
        "target.identity": ("exactly_one", "object", None, _ATOMICITY),
        "traversal.max_hops": ("exactly_one", "integer", None, _ATOMICITY),
        "traversal.max_paths": ("exactly_one", "integer", None, _ATOMICITY),
        "traversal.returned_paths": ("exactly_one", "integer", None, _ATOMICITY),
        "traversal.status": ("exactly_one", "identifier", None, _ATOMICITY),
        "traversal.truncated": ("exactly_one", "boolean", None, _ATOMICITY),
    }
)
_LITERAL_VALUE_CLASSES = {"fixed_identifier", "fixed_nonfactual_text"}
_REGISTERED_OMISSION_REASON_IDS = (
    "omission:archive_construction_not_clause_backed",
    "omission:not_used_by_consumer",
    "omission:reader_datum_not_clause_backed",
    "omission:template_body_not_registered",
)
_REGISTERED_TEMPLATE_SCOPE_SIGNATURES: Mapping[
    str, tuple[str, tuple[str, ...]]
] = MappingProxyType(
    {
        "template:audit.bundle.shell.v1": (
            "output:offline_audit_bundle",
            ("scope:output.all_views", "scope:output.offline_audit_bundle"),
        ),
        "template:board.brief.shell.v1": (
            "output:board_brief",
            ("scope:output.all_views", "scope:output.board_brief"),
        ),
        "template:board.decision.boundary.v1": (
            "output:board_brief",
            ("scope:output.all_views", "scope:output.board_brief"),
        ),
        "template:board.event.record.v1": (
            "output:board_brief",
            ("scope:output.all_views", "scope:output.board_brief"),
        ),
        "template:board.linkage.no_path.v1": (
            "output:board_brief",
            ("scope:output.all_views", "scope:output.board_brief"),
        ),
        "template:board.linkage.path_found.v1": (
            "output:board_brief",
            ("scope:output.all_views", "scope:output.board_brief"),
        ),
        "template:newsroom.card.shell.v1": (
            "output:newsroom_claim_card",
            ("scope:output.all_views", "scope:output.newsroom_claim_card"),
        ),
        "template:newsroom.event.record.v1": (
            "output:newsroom_claim_card",
            (
                "scope:claim.card.event_record",
                "scope:output.all_views",
                "scope:output.newsroom_claim_card",
            ),
        ),
        "template:newsroom.release_structure.no_path.v1": (
            "output:newsroom_claim_card",
            (
                "scope:claim.card.release_structure",
                "scope:output.all_views",
                "scope:output.newsroom_claim_card",
            ),
        ),
        "template:newsroom.release_structure.path_found.v1": (
            "output:newsroom_claim_card",
            (
                "scope:claim.card.release_structure",
                "scope:output.all_views",
                "scope:output.newsroom_claim_card",
            ),
        ),
        "template:research.package.shell.v1": (
            "output:research_package",
            ("scope:output.all_views", "scope:output.research_package"),
        ),
    }
)
_REFUSAL_CODES = {
    "consumer_branch_invalid",
    "consumer_dependency_drift",
    "consumer_dependency_invalid",
    "consumer_limitation_scope_invalid",
    "consumer_migration_boundary_invalid",
    "consumer_omission_invalid",
    "consumer_profile_invalid",
    "consumer_profile_not_effective",
    "consumer_selector_invalid",
    "consumer_source_binding_invalid",
    "consumer_template_invalid",
}


class EvidenceOutputConsumerContractError(ValueError):
    """Stable fail-closed refusal from the inactive consumer contract."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EvidenceOutputConsumerContractError(code, detail)


def _read_json(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        value, digest = ac._read_json(path, code)
    except ac.AnalyticalClauseError as exc:
        raise EvidenceOutputConsumerContractError(code, exc.code) from exc
    return value, digest


def _day(value: object, code: str) -> date:
    try:
        return ac._day(value, code)
    except ac.AnalyticalClauseError as exc:
        raise EvidenceOutputConsumerContractError(code, exc.detail) from exc


def _instant(value: object, code: str) -> None:
    try:
        ac._instant(value, code)
    except ac.AnalyticalClauseError as exc:
        raise EvidenceOutputConsumerContractError(code, exc.detail) from exc


def _registered_selector_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_field in sorted(_REGISTERED_SOURCE_FIELD_SIGNATURES):
        signature = _REGISTERED_SOURCE_FIELD_SIGNATURES[source_field]
        rows.append(
            {
                "source_field": source_field,
                "cardinality": signature[0],
                "value_class": signature[1],
                "denominator_key": signature[2],
                "atomicity": signature[3],
            }
        )
    return rows


def _validate_selected_clause(
    source_field: str,
    clause: Mapping[str, Any],
    signature: tuple[str, str, str | None, str],
) -> None:
    proof = clause.get("proof_binding")
    if not isinstance(proof, dict) or proof.get("source_field") != source_field:
        _fail("consumer_selector_invalid", source_field)
    value = clause.get("value")
    missingness = clause.get("missingness")
    value_class = signature[1]
    if value is None:
        if missingness != "source_missing" or value_class not in {
            "citation_metadata",
            "datetime",
        }:
            _fail("consumer_selector_invalid", source_field)
        return
    if missingness != "present":
        _fail("consumer_selector_invalid", source_field)

    valid = False
    if value_class == "boolean":
        valid = isinstance(value, bool)
    elif value_class == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif value_class in {"citation_metadata", "identifier", "text"}:
        valid = isinstance(value, str)
    elif value_class == "object":
        valid = isinstance(value, dict)
    elif value_class == "date":
        try:
            _day(value, "consumer_selector_invalid")
        except EvidenceOutputConsumerContractError:
            valid = False
        else:
            valid = True
    elif value_class == "datetime":
        try:
            _instant(value, "consumer_selector_invalid")
        except EvidenceOutputConsumerContractError:
            valid = False
        else:
            valid = True
    if not valid:
        _fail("consumer_selector_invalid", source_field)


def _safe_file(relative: object, code: str) -> Path:
    try:
        return ac._safe_file(relative)
    except ac.AnalyticalClauseError as exc:
        raise EvidenceOutputConsumerContractError(code, exc.detail) from exc


def _sha(path: Path, code: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvidenceOutputConsumerContractError(code, str(path)) from exc


def _closed_string_list(value: object, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        _fail(code)
    return cast(list[str], value)


def _nested_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for nested in value.values() for item in _nested_strings(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in _nested_strings(nested)]
    return []


def _source_release_day(source_bundle: Mapping[str, Any]) -> date:
    release = source_bundle.get("source_release")
    if not isinstance(release, dict):
        _fail("consumer_source_binding_invalid")
    return _day(release.get("effective_date"), "consumer_source_binding_invalid")


def _validate_dependencies(
    profile: Mapping[str, Any], source_bundle: Mapping[str, Any] | None
) -> dict[str, str]:
    validator_runtime = profile.get("validator_runtime")
    if not isinstance(validator_runtime, dict) or set(validator_runtime) != {
        "kind",
        "path",
        "sha256",
        "authority",
    }:
        _fail("consumer_dependency_invalid")
    validator_path = _safe_file(
        validator_runtime.get("path"), "consumer_dependency_invalid"
    )
    if (
        validator_runtime.get("kind") != "evidence_output_consumer_contract_validator"
        or validator_path != Path(__file__).resolve()
        or validator_runtime.get("authority")
        != "consumer_contract_validator_not_clause_authority"
    ):
        _fail("consumer_dependency_invalid")
    if _sha(validator_path, "consumer_dependency_invalid") != validator_runtime.get(
        "sha256"
    ):
        _fail("consumer_dependency_drift", "evidence_output_consumer_contract_validator")

    extension = profile.get("registry_extension")
    if not isinstance(extension, dict) or set(extension) != {
        "base_registry_path",
        "base_registry_sha256",
        "base_method_id",
        "relationship",
        "base_engine_is_clause_authority",
        "base_engine_behavior_changed",
    }:
        _fail("consumer_profile_invalid")
    base_path = _safe_file(extension["base_registry_path"], "consumer_dependency_invalid")
    if (
        base_path != EVIDENCE_OUTPUT_REGISTRY_PATH.resolve()
        or _sha(base_path, "consumer_dependency_invalid")
        != extension["base_registry_sha256"]
        or extension["base_method_id"] != "method:igrm.evidence_outputs"
        or extension["relationship"]
        != "closed_consumer_extension_of_unchanged_incumbent_registry"
        or extension["base_engine_is_clause_authority"] is not False
        or extension["base_engine_behavior_changed"] is not False
    ):
        _fail("consumer_dependency_invalid")

    rows = profile.get("consumer_dependencies")
    if not isinstance(rows, list):
        _fail("consumer_dependency_invalid")
    dependencies: dict[str, str] = {}
    observed_paths: dict[str, Path] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"kind", "path", "sha256", "authority"}
            or not isinstance(row.get("kind"), str)
            or row["kind"] in dependencies
            or row.get("authority") != "consumer_dependency_not_clause_authority"
        ):
            _fail("consumer_dependency_invalid")
        path = _safe_file(row.get("path"), "consumer_dependency_invalid")
        if path.name == "evidence_outputs.py" or "evidence_output_runtime" in row["kind"]:
            _fail("consumer_dependency_invalid")
        digest = _sha(path, "consumer_dependency_invalid")
        if digest != row.get("sha256"):
            _fail("consumer_dependency_drift", cast(str, row["kind"]))
        dependencies[cast(str, row["kind"])] = digest
        observed_paths[cast(str, row["kind"])] = path
    expected_paths = {
        "analytical_clause_contract": ac.CONTRACT_PATH.resolve(),
        "analytical_clause_limitations": ac.LIMITATION_REGISTRY_PATH.resolve(),
        "analytical_clause_runtime": Path(ac.__file__).resolve(),
        "analytical_clause_source_profile": ac.SOURCE_PROFILE_PATH.resolve(),
    }
    if set(dependencies) != _DEPENDENCY_KINDS or observed_paths != expected_paths:
        _fail("consumer_dependency_invalid")
    if source_bundle is not None:
        binding = source_bundle.get("contract")
        if not isinstance(binding, dict) or any(
            dependencies[kind] != binding.get(field)
            for kind, field in (
                ("analytical_clause_contract", "clause_contract_sha256"),
                ("analytical_clause_limitations", "analytical_clause_limitations_sha256"),
                ("analytical_clause_runtime", "analytical_clause_runtime_sha256"),
                ("analytical_clause_source_profile", "source_profile_sha256"),
            )
        ):
            _fail("consumer_dependency_invalid")
    return dependencies


def validate_profile_document(
    profile: Mapping[str, Any],
    *,
    release_effective: date,
    source_bundle: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Validate the closed preparatory profile without activating a consumer."""

    expected = {
        "schema_version",
        "profile_id",
        "effective",
        "status",
        "default_policy",
        "validator_runtime",
        "registry_extension",
        "consumer_dependencies",
        "binding_rule",
        "source_field_selectors",
        "branches",
        "omission_reason_ids",
        "templates",
        "consumers",
        "migration_boundary",
        "claim_boundary",
        "refusal_codes",
    }
    profile_day = _day(profile.get("effective"), "consumer_profile_invalid")
    if profile_day > release_effective:
        _fail("consumer_profile_not_effective")
    if (
        set(profile) != expected
        or profile.get("schema_version") != _VERSION
        or profile.get("profile_id") != _PROFILE_ID
        or profile.get("status") != "contract_only_inactive"
        or profile.get("default_policy") != "deny"
        or set(_closed_string_list(profile.get("refusal_codes"), "consumer_profile_invalid"))
        != _REFUSAL_CODES
    ):
        _fail("consumer_profile_invalid")
    _validate_dependencies(profile, source_bundle)
    if profile.get("binding_rule") != {
        "accepted_input": "one_validated_source_bound_clause_bundle",
        "selector_key": "proof_binding.source_field",
        "selector_scope": "one_exact_source_bundle_and_query",
        "clause_ids_in_profile": False,
        "aggregate_synthesis": False,
        "cross_query_or_release_splice": "refuse",
        "selector_partition_scope": "registered_selector_subset_not_complete_clause_denominator",
        "all_source_clause_omission_receipt_available": False,
        "activation": False,
    }:
        _fail("consumer_profile_invalid")

    limitation_registry, _ = _read_json(
        ac.LIMITATION_REGISTRY_PATH, "consumer_dependency_invalid"
    )
    try:
        ac._validate_limitation_registry(
            limitation_registry, release_effective=release_effective
        )
    except ac.AnalyticalClauseError as exc:
        raise EvidenceOutputConsumerContractError(
            "consumer_dependency_invalid", exc.code
        ) from exc
    allowed_limitation_ids = set(limitation_registry["allowed_ids"])
    if any(item in allowed_limitation_ids for item in _nested_strings(profile)):
        _fail("consumer_limitation_scope_invalid")
    valid_scope_ids = set(limitation_registry["output_profiles"])

    selector_rows = profile.get("source_field_selectors")
    if selector_rows != _registered_selector_rows():
        _fail("consumer_selector_invalid")
    selectors = {
        cast(str, row["source_field"]): cast(Mapping[str, Any], row)
        for row in cast(list[dict[str, Any]], selector_rows)
    }

    branch_rows = profile.get("branches")
    if not isinstance(branch_rows, list):
        _fail("consumer_branch_invalid")
    branches: dict[str, Mapping[str, Any]] = {}
    branch_required = {
        "coverage.row",
        "traversal.max_hops",
        "traversal.max_paths",
        "traversal.returned_paths",
        "traversal.status",
        "traversal.truncated",
    }
    for row in branch_rows:
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "branch_id",
                "predicate",
                "returned_paths_relation",
                "required_source_fields",
                "coverage_source_field",
                "coverage_denominator_key",
                "truncation_source_field",
                "bounded_semantics",
            }
            or row.get("branch_id") not in _BRANCH_IDS
            or row["branch_id"] in branches
            or row.get("coverage_source_field") != "coverage.row"
            or row.get("coverage_denominator_key") != "coverage_rows"
            or row.get("truncation_source_field") != "traversal.truncated"
            or row.get("bounded_semantics")
            != "bounded_result_never_global_exposure_claim"
        ):
            _fail("consumer_branch_invalid")
        required = _closed_string_list(
            row.get("required_source_fields"), "consumer_branch_invalid"
        )
        if not branch_required <= set(required) or not set(required) <= set(selectors):
            _fail("consumer_branch_invalid")
        expected_status = (
            "paths_found" if row["branch_id"] == "branch:path_found" else "no_path"
        )
        expected_relation = (
            {"operator": "minimum", "value": 1}
            if expected_status == "paths_found"
            else {"operator": "equals", "value": 0}
        )
        if row.get("predicate") != {
            "source_field": "traversal.status",
            "operator": "equals",
            "value": expected_status,
        } or row.get("returned_paths_relation") != expected_relation:
            _fail("consumer_branch_invalid")
        branches[cast(str, row["branch_id"])] = row
    if tuple(branches) != _BRANCH_IDS:
        _fail("consumer_branch_invalid")

    omission_value = profile.get("omission_reason_ids")
    if omission_value != list(_REGISTERED_OMISSION_REASON_IDS):
        _fail("consumer_omission_invalid")
    omission_ids = list(_REGISTERED_OMISSION_REASON_IDS)

    template_rows = profile.get("templates")
    if not isinstance(template_rows, list):
        _fail("consumer_template_invalid")
    templates: dict[str, Mapping[str, Any]] = {}
    for row in template_rows:
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "template_id",
                "consumer_id",
                "branch_id",
                "required_source_fields",
                "limitation_scope_ids",
                "literal_value_classes",
                "template_body_status",
            }
            or not isinstance(row.get("template_id"), str)
            or row["template_id"] in templates
            or row.get("consumer_id") not in _OUTPUT_ROLES
            or row.get("branch_id") not in {None, *_BRANCH_IDS}
            or row.get("template_body_status") != "identifier_only_not_activated"
        ):
            _fail("consumer_template_invalid")
        required = _closed_string_list(
            row.get("required_source_fields"), "consumer_template_invalid"
        )
        scopes = _closed_string_list(
            row.get("limitation_scope_ids"), "consumer_limitation_scope_invalid"
        )
        literals = _closed_string_list(
            row.get("literal_value_classes"), "consumer_template_invalid"
        )
        if not set(scopes) <= valid_scope_ids:
            _fail("consumer_limitation_scope_invalid")
        scope_signature = _REGISTERED_TEMPLATE_SCOPE_SIGNATURES.get(
            cast(str, row["template_id"])
        )
        if (
            scope_signature is None
            or row.get("consumer_id") != scope_signature[0]
            or scopes != list(scope_signature[1])
        ):
            _fail("consumer_limitation_scope_invalid")
        if not set(required) <= set(selectors) or not set(
            literals
        ) <= _LITERAL_VALUE_CLASSES:
            _fail("consumer_template_invalid")
        branch_id = row["branch_id"]
        if branch_id is not None and not set(
            cast(Sequence[str], branches[branch_id]["required_source_fields"])
        ) <= set(required):
            _fail("consumer_branch_invalid", cast(str, row["template_id"]))
        templates[cast(str, row["template_id"])] = row
    if list(templates) != sorted(_REGISTERED_TEMPLATE_SCOPE_SIGNATURES):
        _fail("consumer_template_invalid")

    consumers_value = profile.get("consumers")
    if not isinstance(consumers_value, list):
        _fail("consumer_profile_invalid")
    consumers: dict[str, Mapping[str, Any]] = {}
    uncovered_ids: set[str] = set()
    for row in consumers_value:
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "output_id",
                "role_id",
                "template_ids",
                "required_source_fields",
                "omitted_registered_selector_fields",
                "limitation_scope_ids",
                "uncovered_reader_datums",
                "migration_status",
            }
            or row.get("output_id") not in _OUTPUT_ROLES
            or row["output_id"] in consumers
            or row.get("role_id") != _OUTPUT_ROLES[row["output_id"]]
            or row.get("migration_status") != "blocked_uncovered_reader_datums"
        ):
            _fail("consumer_profile_invalid")
        output_id = cast(str, row["output_id"])
        template_ids = _closed_string_list(
            row.get("template_ids"), "consumer_template_invalid"
        )
        if set(template_ids) != {
            template_id
            for template_id, template in templates.items()
            if template["consumer_id"] == output_id
        }:
            _fail("consumer_template_invalid", output_id)
        required = _closed_string_list(
            row.get("required_source_fields"), "consumer_selector_invalid"
        )
        expected_required = sorted(
            {
                source_field
                for template_id in template_ids
                for source_field in templates[template_id]["required_source_fields"]
            }
        )
        if required != expected_required:
            _fail("consumer_selector_invalid", output_id)
        omitted_rows = row.get("omitted_registered_selector_fields")
        if not isinstance(omitted_rows, list):
            _fail("consumer_omission_invalid")
        omitted: dict[str, str] = {}
        for omitted_row in omitted_rows:
            if (
                not isinstance(omitted_row, dict)
                or set(omitted_row) != {"source_field", "reason_id"}
                or omitted_row.get("source_field") in omitted
                or omitted_row.get("source_field") not in selectors
                or omitted_row.get("reason_id") not in omission_ids
            ):
                _fail("consumer_omission_invalid")
            omitted[cast(str, omitted_row["source_field"])] = cast(
                str, omitted_row["reason_id"]
            )
        if (
            list(omitted) != sorted(omitted)
            or set(required) & set(omitted)
            or set(required) | set(omitted) != set(selectors)
        ):
            _fail("consumer_omission_invalid", output_id)
        scopes = _closed_string_list(
            row.get("limitation_scope_ids"), "consumer_limitation_scope_invalid"
        )
        specific_scope = {
            "output:research_package": "scope:output.research_package",
            "output:board_brief": "scope:output.board_brief",
            "output:newsroom_claim_card": "scope:output.newsroom_claim_card",
            "output:offline_audit_bundle": "scope:output.offline_audit_bundle",
        }[output_id]
        if scopes != sorted(["scope:output.all_views", specific_scope]):
            _fail("consumer_limitation_scope_invalid")
        uncovered_rows = row.get("uncovered_reader_datums")
        if not isinstance(uncovered_rows, list) or not uncovered_rows:
            _fail("consumer_migration_boundary_invalid")
        local_uncovered: set[str] = set()
        for uncovered in uncovered_rows:
            if (
                not isinstance(uncovered, dict)
                or set(uncovered) != {"datum_id", "reason_id"}
                or not isinstance(uncovered.get("datum_id"), str)
                or uncovered["datum_id"] in local_uncovered
                or uncovered.get("reason_id") not in omission_ids
            ):
                _fail("consumer_migration_boundary_invalid")
            local_uncovered.add(cast(str, uncovered["datum_id"]))
        if [item["datum_id"] for item in uncovered_rows] != sorted(local_uncovered):
            _fail("consumer_migration_boundary_invalid")
        uncovered_ids.update(local_uncovered)
        consumers[output_id] = row
    if set(consumers) != set(_OUTPUT_ROLES):
        _fail("consumer_profile_invalid")

    if profile.get("migration_boundary") != {
        "activation": False,
        "status": "blocked_uncovered_reader_datums",
        "uncovered_datum_denominator": len(uncovered_ids),
        "uncovered_datum_ids": sorted(uncovered_ids),
        "output_equivalence_claimed": False,
        "prose_equivalence_claimed": False,
        "product_manifest_claimed": False,
        "correction_blast_claimed": False,
        "public_authority_claimed": False,
        "selector_partition_scope": "registered_selector_subset_not_complete_clause_denominator",
        "all_source_clause_omission_receipt_available": False,
    }:
        _fail("consumer_migration_boundary_invalid")
    return selectors, templates


def load_profile(
    *,
    release_effective: date,
    source_bundle: Mapping[str, Any] | None = None,
    path: Path = PROFILE_PATH,
) -> tuple[dict[str, Any], str]:
    """Load the inactive extension; no source compiler calls this function."""

    profile, digest = _read_json(path, "consumer_profile_invalid")
    validate_profile_document(
        profile, release_effective=release_effective, source_bundle=source_bundle
    )
    return profile, digest


def expected_source_binding(source_bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact caller-held binding required by contract assessment."""

    release = source_bundle.get("source_release")
    query = source_bundle.get("query")
    if not isinstance(release, dict) or not isinstance(query, dict):
        _fail("consumer_source_binding_invalid")
    return {
        "bundle_id": source_bundle.get("bundle_id"),
        "bundle_record_sha256": source_bundle.get("record_sha256"),
        "release_id": release.get("release_id"),
        "release_record_sha256": release.get("record_sha256"),
        "query_id": query.get("query_id"),
        "query_sha256": query.get("query_sha256"),
    }


def validate_resolution(
    profile: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    expected_binding: Mapping[str, Any],
) -> dict[str, Any]:
    """Assess source-field coverage and remain blocked; render nothing."""

    release_day = _source_release_day(source_bundle)
    contract, _ = ac.load_contract()
    _, source_profile_sha, pins, _ = ac.load_source_profile(
        release_effective=release_day
    )
    limitations, limitations_sha = ac.load_limitation_registry(
        pins["analytical_clause_limitations"], release_effective=release_day
    )
    ac.validate_source_bundle(
        source_bundle,
        contract,
        source_profile_sha,
        pins,
        limitations,
        limitations_sha,
    )
    selectors, templates = validate_profile_document(
        profile, release_effective=release_day, source_bundle=source_bundle
    )
    if dict(expected_binding) != expected_source_binding(source_bundle):
        _fail("consumer_source_binding_invalid")

    clauses = cast(Sequence[Mapping[str, Any]], source_bundle["clauses"])
    denominators = cast(Mapping[str, Any], source_bundle["complete_denominators"])
    by_field: dict[str, list[Mapping[str, Any]]] = {}
    for clause in clauses:
        proof = clause.get("proof_binding")
        if not isinstance(proof, dict) or not isinstance(proof.get("source_field"), str):
            _fail("consumer_selector_invalid")
        by_field.setdefault(cast(str, proof["source_field"]), []).append(clause)
    for source_field in selectors:
        signature = _REGISTERED_SOURCE_FIELD_SIGNATURES[source_field]
        selected = by_field.get(source_field, [])
        expected_count = (
            1
            if signature[0] == "exactly_one"
            else denominators.get(cast(str, signature[2]))
        )
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count < 0
            or len(selected) != expected_count
            or len({clause["clause_id"] for clause in selected}) != len(selected)
        ):
            _fail("consumer_selector_invalid", source_field)
        for clause in selected:
            _validate_selected_clause(source_field, clause, signature)
    coverage_clauses = by_field.get("coverage.row", [])
    if any(
        clause.get("value") != clause["proof_binding"].get("coverage_binding")
        or not isinstance(clause.get("value"), dict)
        or set(clause["value"]) != set(ac._COVERAGE_ROW_FIELDS)
        for clause in coverage_clauses
    ):
        _fail("consumer_selector_invalid", "coverage.row")

    status_rows = by_field.get("traversal.status", [])
    returned_rows = by_field.get("traversal.returned_paths", [])
    truncated_rows = by_field.get("traversal.truncated", [])
    if len(status_rows) != 1 or len(returned_rows) != 1 or len(truncated_rows) != 1:
        _fail("consumer_branch_invalid")
    status = status_rows[0]["value"]
    if status not in {"paths_found", "no_path"}:
        _fail("consumer_branch_invalid")
    branch_id = "branch:path_found" if status == "paths_found" else "branch:no_path"
    branches = {row["branch_id"]: row for row in profile["branches"]}
    relation = branches[branch_id]["returned_paths_relation"]
    returned = returned_rows[0]["value"]
    relation_holds = (
        isinstance(returned, int)
        and not isinstance(returned, bool)
        and (
            returned >= relation["value"]
            if relation["operator"] == "minimum"
            else returned == relation["value"]
        )
    )
    if (
        not relation_holds
        or not isinstance(truncated_rows[0]["value"], bool)
        or (branch_id == "branch:no_path" and truncated_rows[0]["value"] is not False)
        or (branch_id == "branch:no_path" and denominators.get("coverage_rows") != 0)
        or any(
            not set(branches[branch_id]["required_source_fields"])
            <= set(template["required_source_fields"])
            for template in templates.values()
            if template["branch_id"] == branch_id
        )
    ):
        _fail("consumer_branch_invalid")
    return {
        "status": "blocked_uncovered_reader_datums",
        "profile_id": profile["profile_id"],
        "active_branch_id": branch_id,
        "source_bundle_id": source_bundle["bundle_id"],
        "source_bundle_record_sha256": source_bundle["record_sha256"],
        "query_id": source_bundle["query"]["query_id"],
        "release_record_sha256": source_bundle["source_release"]["record_sha256"],
        "consumer_denominator": len(_OUTPUT_ROLES),
        "migration_activated": False,
        "output_equivalence_claimed": False,
    }


def main() -> None:
    profile, digest = load_profile(release_effective=date(2026, 8, 8))
    print(
        json.dumps(
            {
                "status": profile["status"],
                "profile_id": profile["profile_id"],
                "profile_sha256": digest,
                "activation": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
