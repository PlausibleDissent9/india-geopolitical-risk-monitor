"""One incumbent AnalyticalClause record, seven exact-reference audiences.

The core record is closed and atomic.  Every field except ``record_sha256`` is
protected by the typed record digest.  Role projections never copy clause
payloads: they carry only ``{clause_id, clause_record_sha256}`` references.

The source-binding extension in this module is synthetic and contract-only.
It reopens one signed OGES fixture release, reruns the registered exposure
traversal, derives clauses from every returned path hop and exact coverage
entity including one complete ``coverage.row`` atom, compiles all seven
incumbent roles, and byte-compares a replay.

It publishes no route and claims neither source truth nor production trust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from itertools import combinations
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from . import canonical_objects as canonical
from . import event_ledger, event_ledger_extension, exposure_graph

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_RELATIVE = Path("governance") / "analytical_clause_contract.json"
CONTRACT_PATH = ROOT / CONTRACT_RELATIVE
SOURCE_PROFILE_RELATIVE = Path("governance") / "analytical_clause_source_profile.json"
SOURCE_PROFILE_PATH = ROOT / SOURCE_PROFILE_RELATIVE
LIMITATION_REGISTRY_RELATIVE = Path("governance") / "analytical_clause_limitation_registry.json"
LIMITATION_REGISTRY_PATH = ROOT / LIMITATION_REGISTRY_RELATIVE

_VERSION = "0.1.0"
_SOURCE_METHOD_ID = "method:igrm.analytical_clause_source_binding"
_CLAUSE_FIELDS = (
    "object_type",
    "schema_version",
    "clause_id",
    "record_sha256",
    "kind",
    "value",
    "unit",
    "denominator",
    "observed_period",
    "epistemic_type",
    "uncertainty",
    "missingness",
    "citation",
    "rights_state",
    "proof_binding",
)
_REF_FIELDS = ("clause_id", "clause_record_sha256")
_REQUIRED_ROLES = (
    "research",
    "board",
    "newsroom",
    "public",
    "api",
    "priority_language",
    "offline",
)
_MANDATORY_GUARDS = (
    "guardrail:bounded_no_path_not_absence",
    "guardrail:no_forecast_or_advice",
    "guardrail:structural_path_not_causation",
)
_TRUST = {
    "trust_class": "self_hashed_unauthenticated_synthetic_compilation",
    "signed": False,
    "authenticated": False,
    "synthetic": True,
    "contract_only": True,
    "production_authority": False,
    "public_authority": False,
    "caller_authority_accepted": False,
    "record_sha256_is_authentication": False,
}
_PRODUCT_BOUNDARY: dict[str, Any] = {
    "status": "unavailable",
    "reason_code": "product_manifest_and_correction_scope_not_bound",
    "product_manifest_ref": None,
    "artifact_refs": [],
    "correction_blast_available": False,
}
_CLAIM_LIMITATIONS = (
    "bounded_no_path_is_not_absence",
    "clause_identity_is_not_source_truth",
    "cross_role_agreement_is_not_accuracy",
    "no_forecast_or_advice",
    "structural_path_is_not_causation",
    "synthetic_contract_only_no_production_claim",
)
_EVIDENCE_METADATA_FIELDS = (
    "evidence.identity",
    "evidence.source_id",
    "evidence.title",
    "evidence.public_url",
    "evidence.published_at",
    "evidence.observed_at",
    "evidence.verification_status",
    "evidence.content_availability",
    "evidence.rights_use",
    "evidence.privacy_class",
    "evidence.rights_decision_id",
)
_COVERAGE_ROW_FIELDS = (
    "universe_release_id",
    "record_sha256",
    "entity_type",
    "reference_date",
    "covered_entity_id",
    "member_status",
    "counts",
)
_COVERAGE_COUNT_FIELDS = (
    "total_eligible",
    "included",
    "excluded",
    "unmappable",
    "stale",
)
_REGISTERED_QUERY_IDS = (
    "query:analytical_clause.fixture.path_found",
    "query:analytical_clause.fixture.no_path",
)
_OUTPUT_SCOPE_IDS = (
    "scope:output.all_views",
    "scope:output.research_package",
    "scope:output.board_brief",
    "scope:output.newsroom_claim_card",
    "scope:output.offline_audit_bundle",
    "scope:claim.card.event_record",
    "scope:claim.card.release_structure",
)
_PROFILE_PIN_KINDS = {
    "adversarial_vectors",
    "analytical_clause_contract",
    "analytical_clause_limitations",
    "analytical_clause_runtime",
    "canonical_runtime",
    "canonical_schema_registry",
    "exposure_projection_registry",
    "exposure_runtime",
    "exposure_schema",
    "synthetic_fixture_runtime",
    "typed_canonical_runtime",
    "typed_record_runtime",
}


class AnalyticalClauseError(ValueError):
    """Stable fail-closed analytical clause refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise AnalyticalClauseError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("clause_json_duplicate_key", key)
        result[key] = value
    return result


def _read_json(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("clause_structure_invalid"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AnalyticalClauseError(code, str(path)) from exc
    if not isinstance(value, dict):
        _fail(code, str(path))
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _sha(path: Path, code: str = "clause_source_profile_drift") -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise AnalyticalClauseError(code, str(path)) from exc


def _safe_file(relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail("clause_source_profile_invalid")
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail("clause_source_profile_invalid")
    candidate = ROOT.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("clause_source_profile_invalid")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        _fail("clause_source_profile_invalid")
    if not resolved.is_file() or resolved.is_symlink():
        _fail("clause_source_profile_invalid")
    return resolved


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


def _instant(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    return parsed


def _typed_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise AnalyticalClauseError("clause_typed_canonical_invalid", exc.code) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], event_ledger_extension.seal_record(value))
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise AnalyticalClauseError("clause_record_digest_mismatch", exc.code) from exc


def _verify_digest(value: Mapping[str, Any], code: str) -> None:
    try:
        observed = event_ledger_extension.typed_record_sha256(value)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise AnalyticalClauseError(code, exc.code) from exc
    if observed != value.get("record_sha256"):
        _fail(code)


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], code: str) -> None:
    if set(value) != set(expected):
        _fail(code, f"expected={sorted(expected)!r} observed={sorted(value)!r}")


def serialize_record(value: Mapping[str, Any]) -> bytes:
    """Deterministic transport bytes used for exact replay equality."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def load_contract(path: Path = CONTRACT_PATH) -> tuple[dict[str, Any], str]:
    """Load and close the single incumbent AnalyticalClause contract."""

    contract, digest = _read_json(path, "clause_contract_digest_mismatch")
    expected = {
        "schema_version",
        "contract_id",
        "what",
        "canonicalization_profile_id",
        "status",
        "public_routes",
        "roles",
        "analytical_clause_fields",
        "protected_field_rule",
        "role_reference_fields",
        "role_reference_rule",
        "clause_kinds",
        "mandatory_guardrail_ids",
        "epistemic_types",
        "missingness_states",
        "rendering_rule",
        "omission_rule",
        "additive_bundle_objects",
        "claim_boundary",
        "product_manifest_future_seam",
        "refusal_codes",
        "limitations",
    }
    if (
        set(contract) != expected
        or contract.get("schema_version") != _VERSION
        or contract.get("contract_id") != "igrm:analytical-clause:0.1.0"
        or contract.get("status") != "synthetic_contract_only"
        or contract.get("public_routes") != []
        or tuple(contract.get("roles", ())) != _REQUIRED_ROLES
        or tuple(contract.get("analytical_clause_fields", ())) != _CLAUSE_FIELDS
        or tuple(contract.get("role_reference_fields", ())) != _REF_FIELDS
        or tuple(contract.get("mandatory_guardrail_ids", ())) != _MANDATORY_GUARDS
        or "protected_fields" in contract
        or contract.get("rendering_rule")
        != "v0.1_emits_exact_clause_refs_only_no_prose_or_shortening"
        or contract.get("additive_bundle_objects")
        != ["source_bound_clause_bundle", "cross_role_clause_proof_bundle"]
    ):
        _fail("clause_contract_digest_mismatch", str(path))
    kinds = contract.get("clause_kinds")
    if not isinstance(kinds, dict) or set(kinds) != {
        "measurement",
        "limitation",
        "rights",
        "provenance",
    }:
        _fail("clause_contract_digest_mismatch", str(path))
    return contract, digest


def _closed_string_list(value: object, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        _fail(code)
    return cast(list[str], value)


def _validate_limitation_registry(registry: Mapping[str, Any], *, release_effective: date) -> None:
    expected = {
        "schema_version",
        "registry_id",
        "effective",
        "default_policy",
        "allowed_ids",
        "guardrail_ids",
        "compiler_bundle_ids",
        "upstream_traversal_ids",
        "output_profiles",
        "output_clause_ids",
        "limitation_scopes",
        "evidence_output_parity_targets",
        "claim_boundary",
    }
    if (
        set(registry) != expected
        or registry.get("schema_version") != _VERSION
        or registry.get("registry_id") != "igrm:analytical-clause-limitations:0.1.0"
        or registry.get("default_policy") != "deny"
        or _day(registry.get("effective"), "clause_limitation_registry_invalid") > release_effective
    ):
        _fail("clause_limitation_registry_invalid")
    allowed = _closed_string_list(registry.get("allowed_ids"), "clause_limitation_registry_invalid")
    guards = _closed_string_list(
        registry.get("guardrail_ids"), "clause_limitation_registry_invalid"
    )
    compiler = _closed_string_list(
        registry.get("compiler_bundle_ids"), "clause_limitation_registry_invalid"
    )
    upstream = _closed_string_list(
        registry.get("upstream_traversal_ids"), "clause_limitation_registry_invalid"
    )
    output_ids = _closed_string_list(
        registry.get("output_clause_ids"), "clause_limitation_registry_invalid"
    )
    if (
        guards != sorted(_MANDATORY_GUARDS)
        or compiler != sorted(_CLAIM_LIMITATIONS)
        or len(output_ids) != 16
    ):
        _fail("clause_limitation_registry_invalid")
    profiles = registry.get("output_profiles")
    if not isinstance(profiles, dict) or set(profiles) != set(_OUTPUT_SCOPE_IDS):
        _fail("clause_limitation_registry_invalid")
    normalized_profiles: dict[str, list[str]] = {}
    for scope_id, ids in profiles.items():
        normalized_profiles[scope_id] = _closed_string_list(
            ids, "clause_limitation_registry_invalid"
        )
    derived_ids = sorted(
        {limitation_id for ids in normalized_profiles.values() for limitation_id in ids}
    )
    if derived_ids != output_ids or sum(map(len, normalized_profiles.values())) != 21:
        _fail("clause_limitation_registry_invalid")
    scopes = registry.get("limitation_scopes")
    if not isinstance(scopes, dict) or set(scopes) != set(output_ids):
        _fail("clause_limitation_scope_invalid")
    for limitation_id, scope_ids in scopes.items():
        observed_scopes = _closed_string_list(scope_ids, "clause_limitation_scope_invalid")
        expected_scopes = sorted(
            scope_id
            for scope_id, profile_ids in normalized_profiles.items()
            if limitation_id in profile_ids
        )
        if observed_scopes != expected_scopes:
            _fail("clause_limitation_scope_invalid", limitation_id)
    parity = registry.get("evidence_output_parity_targets")
    expected_parity = {
        "_LIMITATIONS": "scope:output.all_views",
        "_RESEARCH_LIMITATIONS": "scope:output.research_package",
        "_BRIEF_LIMITATIONS": "scope:output.board_brief",
        "_CLAIM_LIMITATIONS": "scope:output.newsroom_claim_card",
        "_AUDIT_LIMITATIONS": "scope:output.offline_audit_bundle",
        "claim:card.event_record.limitations": "scope:claim.card.event_record",
        "claim:card.release_structure.limitations": "scope:claim.card.release_structure",
    }
    if parity != expected_parity:
        _fail("clause_limitation_registry_invalid")
    vocabulary = set(guards) | set(compiler) | set(upstream) | set(output_ids)
    if set(allowed) != vocabulary:
        _fail("clause_limitation_registry_invalid")


def load_limitation_registry(
    expected_sha256: str,
    *,
    release_effective: date,
) -> tuple[dict[str, Any], str]:
    """Load the one deny-by-default limitation vocabulary pinned by the profile."""

    registry, digest = _read_json(LIMITATION_REGISTRY_PATH, "clause_limitation_registry_invalid")
    if digest != expected_sha256:
        _fail("clause_source_profile_drift", "analytical_clause_limitations")
    _validate_limitation_registry(registry, release_effective=release_effective)
    return registry, digest


def validate_limitation_parity(
    registry: Mapping[str, Any], profiles: Mapping[str, Sequence[str]]
) -> None:
    """Compare extracted renderer literals to the registry without importing it."""

    expected_profiles = registry.get("output_profiles")
    if not isinstance(expected_profiles, dict) or set(profiles) != set(expected_profiles):
        _fail("clause_limitation_parity_invalid")
    for scope_id, expected_ids in expected_profiles.items():
        observed = profiles.get(scope_id)
        if not isinstance(observed, Sequence) or isinstance(observed, (str, bytes)):
            _fail("clause_limitation_parity_invalid", scope_id)
        if list(observed) != list(expected_ids):
            _fail("clause_limitation_parity_invalid", scope_id)


def seal_clause(clause: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one exact incumbent clause after closing its field set."""

    _exact_keys(clause, _CLAUSE_FIELDS, "clause_structure_invalid")
    return _seal(clause)


def _clause_id(clause: Mapping[str, Any]) -> str:
    clause_id = clause.get("clause_id")
    if not isinstance(clause_id, str) or not clause_id:
        _fail("clause_unknown_id_in_role", repr(clause_id))
    return clause_id


def protected_digest(clause: Mapping[str, Any], contract: Mapping[str, Any]) -> str:
    """Digest every clause field except its self-hash; no allowlist exists."""

    if tuple(contract.get("analytical_clause_fields", ())) != _CLAUSE_FIELDS:
        _fail("clause_contract_digest_mismatch")
    _exact_keys(clause, _CLAUSE_FIELDS, "clause_structure_invalid")
    payload = {name: clause[name] for name in _CLAUSE_FIELDS if name != "record_sha256"}
    return _typed_sha(payload)


def validate_clause(clause: Mapping[str, Any], contract: Mapping[str, Any]) -> None:
    """Validate one immutable incumbent clause."""

    _exact_keys(clause, _CLAUSE_FIELDS, "clause_structure_invalid")
    clause_id = _clause_id(clause)
    if clause.get("object_type") != "analytical_clause" or clause.get("schema_version") != _VERSION:
        _fail("clause_structure_invalid", clause_id)
    kinds = cast(Mapping[str, Any], contract["clause_kinds"])
    if clause.get("kind") not in kinds:
        _fail("clause_kind_unregistered", f"{clause_id}: {clause.get('kind')!r}")
    if clause.get("epistemic_type") not in contract["epistemic_types"]:
        _fail("clause_epistemic_type_unregistered", clause_id)
    missingness = clause.get("missingness")
    if missingness not in contract["missingness_states"]:
        _fail("clause_missingness_unregistered", clause_id)
    if missingness == "present" and clause.get("value") is None:
        _fail("clause_value_absent_despite_presence", clause_id)
    if missingness != "present" and clause.get("value") is not None:
        _fail("clause_value_present_despite_missingness", clause_id)
    expected = protected_digest(clause, contract)
    if expected != clause.get("record_sha256"):
        _fail("clause_record_digest_mismatch", clause_id)
    _verify_digest(clause, "clause_record_digest_mismatch")


def compile_clauses(
    clauses: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> dict[str, str]:
    """Validate the incumbent clause set and return exact record references."""

    compiled: dict[str, str] = {}
    for clause in clauses:
        validate_clause(clause, contract)
        clause_id = _clause_id(clause)
        if clause_id in compiled:
            _fail("clause_duplicate_id", clause_id)
        compiled[clause_id] = cast(str, clause["record_sha256"])
    return compiled


def _mandatory_ids(clauses: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]) -> set[str]:
    kinds = cast(Mapping[str, Mapping[str, Any]], contract["clause_kinds"])
    return {
        _clause_id(clause)
        for clause in clauses
        if kinds[cast(str, clause["kind"])]["never_omittable"]
    }


def validate_role_view(
    role: str,
    view: Sequence[Mapping[str, Any]],
    clauses: Sequence[Mapping[str, Any]],
    contract: Mapping[str, Any],
) -> dict[str, str]:
    """Validate one role's exact clause references against the compiled set."""

    if role not in contract["roles"]:
        _fail("clause_role_unregistered", role)
    compiled = compile_clauses(clauses, contract)
    seen: dict[str, str] = {}
    for ref in view:
        _exact_keys(ref, _REF_FIELDS, "clause_ref_invalid")
        clause_id = _clause_id(ref)
        if clause_id not in compiled:
            _fail("clause_unknown_id_in_role", f"{role}: {clause_id}")
        if clause_id in seen:
            _fail("clause_duplicate_id", f"{role}: {clause_id}")
        digest = ref.get("clause_record_sha256")
        if digest != compiled[clause_id]:
            _fail("clause_protected_field_divergence", f"{role}: {clause_id}")
        seen[clause_id] = cast(str, digest)
    missing = sorted(_mandatory_ids(clauses, contract) - set(seen))
    if missing:
        _fail("clause_mandatory_omitted", f"{role}: {', '.join(missing)}")
    return seen


def cross_role_invariant(views: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Compare exact incumbent record references across registered roles."""

    everywhere: dict[str, str] = {}
    for role, digests in sorted(views.items()):
        if role not in _REQUIRED_ROLES:
            _fail("clause_role_unregistered", role)
        for clause_id, digest in sorted(digests.items()):
            if clause_id not in everywhere:
                everywhere[clause_id] = digest
            elif everywhere[clause_id] != digest:
                _fail("clause_protected_field_divergence", f"{clause_id}: {role}")
    return {
        "clause_ids": sorted(everywhere),
        "roles": sorted(views),
        "shared_clause_digest_sha256": _typed_sha(
            [[clause_id, everywhere[clause_id]] for clause_id in sorted(everywhere)]
        ),
        "omitted_by_role": {
            role: sorted(set(everywhere) - set(views[role])) for role in sorted(views)
        },
    }


def _validate_source_profile_document(
    profile: Mapping[str, Any],
    *,
    release_effective: date | None = None,
) -> tuple[dict[str, str], dict[str, Mapping[str, Any]]]:
    expected = {
        "schema_version",
        "profile_id",
        "effective",
        "status",
        "default_policy",
        "allowed_release",
        "normative_files",
        "query_profiles",
        "registered_query_boundary",
        "evidence_metadata_fields",
        "citation_metadata_policy",
        "limitation_vocabulary",
        "dynamic_binding_rules",
        "trust_boundary",
        "product_manifest_boundary",
        "claim_boundary",
    }
    if (
        set(profile) != expected
        or profile.get("schema_version") != _VERSION
        or profile.get("profile_id") != "igrm:analytical-clause-source-binding:0.1.0"
        or profile.get("status") != "synthetic_contract_only"
        or profile.get("default_policy") != "deny"
        or profile.get("trust_boundary") != _TRUST
        or profile.get("product_manifest_boundary") != _PRODUCT_BOUNDARY
        or profile.get("allowed_release")
        != {
            "release_id": "rel:oges.fixture.2026-08-08",
            "release_signer_id": "signer:oges.fixture.release",
        }
        or profile.get("dynamic_binding_rules")
        != {
            "edge_instances": "derive_every_paths_hops_occurrence",
            "edge_membership": "exact_edge_id_and_record_sha256_in_hop_and_object_evidence",
            "coverage_instances": "derive_every_unique_traversal_coverage_row",
            "coverage_membership": "exact_universe_release_id_record_sha256_and_covered_entity_id",
            "coverage_atom": "one_exact_source_field_coverage.row_value_per_unique_traversal_row",
            "evidence_instances": "exact_union_of_traversal_object_evidence_evidence_ids",
            "evidence_membership": "traversal_evidence_equals_union_and_exact_canonical_evidence_record",
            "evidence_metadata": "exactly_once_each_registered_field_per_union_evidence_id",
            "limitations": "one_deny_by_default_profile_pinned_vocabulary_with_exact_scope_sets",
            "role_payload": "exact_clause_refs_only",
            "omissions": "none_registered_deny",
            "caller_authored_semantics": "refuse",
            "verification": "reopen_recompute_and_require_byte_equality",
        }
    ):
        _fail("clause_source_profile_invalid")
    profile_day = _day(profile.get("effective"), "clause_source_profile_invalid")
    if release_effective is not None and profile_day > release_effective:
        _fail("clause_source_profile_not_effective")

    rows = profile.get("normative_files")
    if not isinstance(rows, list):
        _fail("clause_source_profile_invalid")
    pins: dict[str, str] = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"kind", "path", "sha256"}
            or not isinstance(row.get("kind"), str)
            or row["kind"] in pins
        ):
            _fail("clause_source_profile_invalid")
        path = _safe_file(row.get("path"))
        digest = _sha(path)
        if digest != row.get("sha256"):
            _fail("clause_source_profile_drift", cast(str, row["kind"]))
        pins[cast(str, row["kind"])] = digest
    if set(pins) != _PROFILE_PIN_KINDS:
        _fail("clause_source_profile_invalid")

    if profile.get("registered_query_boundary") != {
        "accepted_input": "exact_registered_query_id_only",
        "registered_query_ids": list(_REGISTERED_QUERY_IDS),
        "tuple_resolver": "none",
        "caller_authored_event_target_bounds_or_selectors": False,
        "unregistered_evidence_output_api_tuples": "refuse_without_claiming_coverage",
    }:
        _fail("clause_source_profile_invalid")
    if tuple(profile.get("evidence_metadata_fields", ())) != _EVIDENCE_METADATA_FIELDS:
        _fail("clause_source_profile_invalid")
    if profile.get("citation_metadata_policy") != {
        "privacy_classes": ["public"],
        "rights_uses": ["cite_metadata"],
        "public_with_redactions_field_receipt": "unavailable_refuse",
        "public_url_semantics": "metadata_locator_not_content_permission",
        "nullable_fields": ["evidence.public_url", "evidence.published_at"],
        "source_blank_policy": "preserve_null_missingness_never_empty_string_or_zero",
    }:
        _fail("clause_source_profile_invalid")
    limitation_vocabulary = profile.get("limitation_vocabulary")
    if limitation_vocabulary != {
        "registry_id": "igrm:analytical-clause-limitations:0.1.0",
        "effective": "2026-08-08",
        "default_policy": "deny",
        "normative_file_kind": "analytical_clause_limitations",
        "renderer_parity": "test_only_consumer_assertion_not_normative_input",
        "output_unique_id_denominator": 16,
        "output_scope_membership_denominator": 21,
    }:
        _fail("clause_source_profile_invalid")
    if profile_day != _day(limitation_vocabulary["effective"], "clause_source_profile_invalid"):
        _fail("clause_source_profile_invalid")

    queries_value = profile.get("query_profiles")
    if not isinstance(queries_value, list):
        _fail("clause_source_profile_invalid")
    queries: dict[str, Mapping[str, Any]] = {}
    query_tuples: set[tuple[object, ...]] = set()
    for row in queries_value:
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "query_id",
                "event_id",
                "target_entity_id",
                "max_hops",
                "max_paths",
            }
            or not isinstance(row.get("query_id"), str)
            or row["query_id"] in queries
            or isinstance(row.get("max_hops"), bool)
            or not isinstance(row.get("max_hops"), int)
            or not 1 <= row["max_hops"] <= 6
            or isinstance(row.get("max_paths"), bool)
            or not isinstance(row.get("max_paths"), int)
            or not 1 <= row["max_paths"] <= 100
        ):
            _fail("clause_source_profile_invalid")
        query_tuple = (
            row["event_id"],
            row["target_entity_id"],
            row["max_hops"],
            row["max_paths"],
        )
        if query_tuple in query_tuples:
            _fail("clause_source_profile_invalid")
        query_tuples.add(query_tuple)
        queries[cast(str, row["query_id"])] = row
    if tuple(queries) != _REGISTERED_QUERY_IDS:
        _fail("clause_source_profile_invalid")
    return pins, queries


def load_source_profile(
    *,
    release_effective: date | None = None,
) -> tuple[dict[str, Any], str, dict[str, str], dict[str, Mapping[str, Any]]]:
    profile, digest = _read_json(SOURCE_PROFILE_PATH, "clause_source_profile_invalid")
    pins, queries = _validate_source_profile_document(profile, release_effective=release_effective)
    return profile, digest, pins, queries


def _bundle_kwargs(root: Path) -> dict[str, Path]:
    return {
        "schema_registry_path": root / "governance" / "canonical_schema_registry.json",
        "rights_registry_path": root / "governance" / "source_rights_registry.json",
        "rights_signers_path": root / "governance" / "rights_signers.json",
        "method_registry_path": root / "governance" / "canonical_method_registry.json",
        "release_signers_path": root / "governance" / "release_signers.json",
    }


def _release_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: manifest[key]
        for key in (
            "release_id",
            "record_sha256",
            "generated_at",
            "effective_date",
            "release_signer_id",
            "schema_registry_sha256",
            "method_registry_sha256",
            "rights_registry_sha256",
            "rights_signers_sha256",
            "release_signers_sha256",
        )
    }


def _source_ref(object_type: str, object_id: str, document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "object_id": object_id,
        "record_sha256": document["record_sha256"],
    }


def _object_maps(
    validated: canonical.ValidatedCanonicalRelease,
) -> tuple[dict[str, tuple[str, Mapping[str, Any]]], dict[str, Mapping[str, Any]]]:
    by_id: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for object_type, rows in validated.objects.items():
        for object_id, document in rows.items():
            if object_id in by_id:
                _fail("clause_source_binding_invalid", object_id)
            by_id[object_id] = (object_type, document)
    return by_id, dict(validated.objects["evidence_item"])


def _traversal_object_rows(
    traversal: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows: dict[str, Mapping[str, Any]] = {}
    for row in traversal["object_evidence"]:
        object_id = cast(str, row["object_id"])
        if object_id in rows:
            _fail("clause_source_binding_invalid", object_id)
        rows[object_id] = row
    return rows


def _evidence_documents(
    validated: canonical.ValidatedCanonicalRelease,
    traversal: Mapping[str, Any],
    citation_policy: Mapping[str, Any],
) -> tuple[list[str], dict[str, Mapping[str, Any]]]:
    union_ids = {
        cast(str, evidence_id)
        for row in traversal["object_evidence"]
        for evidence_id in row["evidence_ids"]
    }
    traversal_rows: dict[str, Mapping[str, Any]] = {}
    for row in traversal["evidence"]:
        evidence_id = cast(str, row["evidence_id"])
        if evidence_id in traversal_rows:
            _fail("clause_evidence_binding_invalid", evidence_id)
        traversal_rows[evidence_id] = row
    if set(traversal_rows) != union_ids:
        _fail("clause_evidence_binding_invalid", "traversal evidence denominator")
    canonical_evidence = validated.objects["evidence_item"]
    documents: dict[str, Mapping[str, Any]] = {}
    release_generated = _instant(
        validated.manifest["generated_at"], "clause_evidence_temporal_invalid"
    )
    binding_fields = (
        "record_sha256",
        "source_id",
        "rights_use",
        "rights_decision_id",
        "content_sha256",
        "content_availability",
        "privacy_class",
        "verification_status",
    )
    for evidence_id in sorted(union_ids):
        document = canonical_evidence.get(evidence_id)
        binding = traversal_rows[evidence_id]
        if document is None or any(
            binding.get(field) != document.get(field) for field in binding_fields
        ):
            _fail("clause_evidence_binding_invalid", evidence_id)
        if (
            document["privacy_class"] not in citation_policy["privacy_classes"]
            or document["rights_use"] not in citation_policy["rights_uses"]
        ):
            _fail("clause_evidence_metadata_not_publishable", evidence_id)
        title = document["title"]
        public_url = document["public_url"]
        published_at = document["published_at"]
        observed_at = document["observed_at"]
        if (
            not isinstance(title, str)
            or not title.strip()
            or (public_url is not None and (not isinstance(public_url, str) or not public_url))
            or (published_at is not None and not isinstance(published_at, str))
            or not isinstance(observed_at, str)
        ):
            _fail("clause_evidence_binding_invalid", evidence_id)
        if _instant(observed_at, "clause_evidence_temporal_invalid") > release_generated:
            _fail("clause_evidence_temporal_invalid", evidence_id)
        if (
            published_at is not None
            and _instant(published_at, "clause_evidence_temporal_invalid") > release_generated
        ):
            _fail("clause_evidence_temporal_invalid", evidence_id)
        documents[evidence_id] = document
    return sorted(union_ids), documents


def _assert_source_ref(
    ref: Mapping[str, Any],
    traversal_rows: Mapping[str, Mapping[str, Any]],
    release: Mapping[str, Any],
    evidence_objects: Mapping[str, Mapping[str, Any]],
) -> None:
    if ref.get("object_type") == "canonical_release":
        if ref != {
            "object_type": "canonical_release",
            "object_id": release["release_id"],
            "record_sha256": release["record_sha256"],
        }:
            _fail("clause_source_binding_invalid", cast(str, ref.get("object_id")))
        return
    if ref.get("object_type") == "evidence_item":
        document = evidence_objects.get(cast(str, ref.get("object_id")))
        if document is None or ref != _source_ref(
            "evidence_item", cast(str, ref.get("object_id")), document
        ):
            _fail("clause_evidence_binding_invalid", cast(str, ref.get("object_id")))
        return
    row = traversal_rows.get(cast(str, ref["object_id"]))
    if row is None or any(
        row.get(field) != ref.get(field) for field in ("object_type", "object_id", "record_sha256")
    ):
        _fail("clause_source_binding_invalid", cast(str, ref.get("object_id")))


def _citations(
    source_refs: Sequence[Mapping[str, Any]],
    traversal: Mapping[str, Any],
    traversal_rows: Mapping[str, Mapping[str, Any]],
    release: Mapping[str, Any],
    evidence_objects: Mapping[str, Mapping[str, Any]],
    evidence_ids_in_scope: set[str],
) -> list[dict[str, Any]]:
    evidence_by_id = {row["evidence_id"]: row for row in traversal["evidence"]}
    evidence_ids: set[str] = set()
    for ref in source_refs:
        object_id = cast(str, ref["object_id"])
        if ref["object_type"] == "evidence_item":
            evidence_ids.add(object_id)
        elif ref["object_type"] != "canonical_release":
            evidence_ids.update(cast(Sequence[str], traversal_rows[object_id]["evidence_ids"]))
        _assert_source_ref(ref, traversal_rows, release, evidence_objects)
    if not evidence_ids <= set(evidence_by_id) or not evidence_ids <= evidence_ids_in_scope:
        _fail("clause_evidence_binding_invalid")
    citations: list[dict[str, Any]] = []
    for evidence_id in sorted(evidence_ids):
        binding = evidence_by_id[evidence_id]
        document = evidence_objects.get(evidence_id)
        if document is None or binding["record_sha256"] != document["record_sha256"]:
            _fail("clause_evidence_binding_invalid", evidence_id)
        citations.append(
            {
                "evidence_id": evidence_id,
                "record_sha256": document["record_sha256"],
                "source_id": document["source_id"],
                "title": document["title"],
                "public_url": document["public_url"],
                "published_at": document["published_at"],
                "observed_at": document["observed_at"],
                "verification_status": document["verification_status"],
                "content_availability": document["content_availability"],
                "rights_use": document["rights_use"],
            }
        )
    return citations


def _rights_state(
    citations: Sequence[Mapping[str, Any]],
    traversal: Mapping[str, Any],
    source_release: Mapping[str, Any],
) -> dict[str, Any]:
    rights = {row["source_id"]: row for row in traversal["rights"]}
    source_ids = {row["source_id"] for row in citations}
    if not source_ids <= set(rights):
        _fail("clause_source_binding_invalid")
    return {
        "status": "validated_signed_release_snapshot",
        "release_rights_identity": {
            "release_id": source_release["release_id"],
            "release_record_sha256": source_release["record_sha256"],
            "release_generated_at": source_release["generated_at"],
            "release_signer_id": source_release["release_signer_id"],
            "rights_registry_sha256": source_release["rights_registry_sha256"],
            "rights_signers_sha256": source_release["rights_signers_sha256"],
            "release_signers_sha256": source_release["release_signers_sha256"],
        },
        "sources": [dict(rights[source_id]) for source_id in sorted(source_ids)],
        "publication_authority": "synthetic_contract_only_none",
    }


def _clause_identifier(query_id: str, source_field: str, identity: object) -> str:
    query_part = query_id.rsplit(".", 1)[-1]
    field_part = source_field.replace(":", ".").replace("/", ".").replace("_", ".")
    return f"clause:{query_part}.{field_part}.{_typed_sha(identity)[:20]}"


def _make_clause(
    *,
    query_id: str,
    source_field: str,
    identity: object,
    kind: str,
    value: Any,
    unit: Any,
    denominator: Any,
    observed_period: Mapping[str, Any],
    epistemic_type: str,
    uncertainty: Any,
    missingness: str,
    source_refs: Sequence[Mapping[str, Any]],
    path_bindings: Sequence[Mapping[str, Any]],
    coverage_binding: Mapping[str, Any] | None,
    limitation_binding: Mapping[str, Any] | None,
    traversal: Mapping[str, Any],
    traversal_rows: Mapping[str, Mapping[str, Any]],
    source_release: Mapping[str, Any],
    evidence_objects: Mapping[str, Mapping[str, Any]],
    evidence_ids_in_scope: set[str],
    citation_policy: Mapping[str, Any],
    profile_sha256: str,
    runtime_sha256: str,
) -> dict[str, Any]:
    refs = [
        dict(ref)
        for ref in sorted(source_refs, key=lambda row: (row["object_type"], row["object_id"]))
    ]
    citations = _citations(
        refs,
        traversal,
        traversal_rows,
        source_release,
        evidence_objects,
        evidence_ids_in_scope,
    )
    query = dict(traversal["query"])
    proof_binding = {
        "proof_kind": "registered_exposure_traversal_recomputation",
        "source_field": source_field,
        "source_profile_sha256": profile_sha256,
        "source_release_ref": dict(source_release),
        "query": {**query, "query_sha256": _typed_sha(query)},
        "upstream": {
            "record_sha256": traversal["record_sha256"],
            "method": dict(traversal["method"]),
            "contract": dict(traversal["contract"]),
            "recomputed": True,
        },
        "source_object_refs": refs,
        "path_bindings": [dict(row) for row in path_bindings],
        "coverage_binding": None if coverage_binding is None else dict(coverage_binding),
        "limitation_binding": (None if limitation_binding is None else dict(limitation_binding)),
        "citation_metadata_policy": dict(citation_policy),
        "compiler": {
            "method_id": _SOURCE_METHOD_ID,
            "implementation_sha256": runtime_sha256,
            "model_authored": False,
            "free_prose": False,
        },
        "limitations": sorted({*_CLAIM_LIMITATIONS, *traversal["limitations"]}),
    }
    clause = {
        "object_type": "analytical_clause",
        "schema_version": _VERSION,
        "clause_id": _clause_identifier(query_id, source_field, identity),
        "record_sha256": "0" * 64,
        "kind": kind,
        "value": value,
        "unit": unit,
        "denominator": denominator,
        "observed_period": dict(observed_period),
        "epistemic_type": epistemic_type,
        "uncertainty": uncertainty,
        "missingness": missingness,
        "citation": citations,
        "rights_state": _rights_state(citations, traversal, source_release),
        "proof_binding": proof_binding,
    }
    return seal_clause(clause)


def _compile_incumbent_clauses(
    query_id: str,
    traversal: Mapping[str, Any],
    validated: canonical.ValidatedCanonicalRelease,
    profile: Mapping[str, Any],
    profile_sha256: str,
    limitation_registry: Mapping[str, Any],
    limitation_registry_sha256: str,
    runtime_sha256: str,
) -> list[dict[str, Any]]:
    by_id, evidence_objects = _object_maps(validated)
    traversal_rows = _traversal_object_rows(traversal)
    source_release = _release_identity(validated.manifest)
    if {key: value for key, value in source_release.items() if key != "generated_at"} != traversal[
        "release"
    ]:
        _fail("clause_source_binding_invalid", "release identity")
    evidence_ids, scoped_evidence = _evidence_documents(
        validated, traversal, cast(Mapping[str, Any], profile["citation_metadata_policy"])
    )
    evidence_ids_in_scope = set(evidence_ids)
    if any(
        evidence_objects[evidence_id] != scoped_evidence[evidence_id]
        for evidence_id in evidence_ids
    ):
        _fail("clause_evidence_binding_invalid")
    allowed_limitations = set(limitation_registry["allowed_ids"])
    observed_limitations = (
        set(_MANDATORY_GUARDS)
        | set(_CLAIM_LIMITATIONS)
        | set(cast(Sequence[str], traversal["limitations"]))
        | set(cast(Sequence[str], limitation_registry["output_clause_ids"]))
    )
    if not observed_limitations <= allowed_limitations:
        _fail(
            "clause_limitation_unregistered",
            ",".join(sorted(observed_limitations - allowed_limitations)),
        )
    release_day = traversal["release"]["effective_date"]
    release_generated_at = source_release["generated_at"]
    event_id = cast(str, traversal["event"]["event_id"])
    target_id = cast(str, traversal["target"]["entity_id"])
    event_type, event_doc = by_id[event_id]
    target_type, target_doc = by_id[target_id]
    event_ref = _source_ref(event_type, event_id, event_doc)
    target_ref = _source_ref(target_type, target_id, target_doc)
    release_ref = _source_ref(
        "canonical_release", cast(str, source_release["release_id"]), source_release
    )
    all_refs = [
        {key: row[key] for key in ("object_type", "object_id", "record_sha256")}
        for row in traversal["object_evidence"]
    ]
    clauses: list[dict[str, Any]] = []

    def add(
        source_field: str,
        identity: object,
        value: Any,
        *,
        kind: str = "measurement",
        unit: Any = None,
        denominator: Any = "one signed canonical release",
        as_of: Any = None,
        epistemic_type: str = "measured",
        uncertainty: Any = None,
        missingness: str | None = None,
        refs: Sequence[Mapping[str, Any]] = (),
        path_bindings: Sequence[Mapping[str, Any]] = (),
        coverage_binding: Mapping[str, Any] | None = None,
        limitation_binding: Mapping[str, Any] | None = None,
    ) -> None:
        state = missingness or ("present" if value is not None else "source_missing")
        clauses.append(
            _make_clause(
                query_id=query_id,
                source_field=source_field,
                identity=identity,
                kind=kind,
                value=value,
                unit=unit,
                denominator=denominator,
                observed_period={
                    "release_effective_date": release_day,
                    "as_of": as_of,
                },
                epistemic_type=epistemic_type,
                uncertainty=uncertainty,
                missingness=state,
                source_refs=refs,
                path_bindings=path_bindings,
                coverage_binding=coverage_binding,
                limitation_binding=limitation_binding,
                traversal=traversal,
                traversal_rows=traversal_rows,
                source_release=source_release,
                evidence_objects=scoped_evidence,
                evidence_ids_in_scope=evidence_ids_in_scope,
                citation_policy=cast(Mapping[str, Any], profile["citation_metadata_policy"]),
                profile_sha256=profile_sha256,
                runtime_sha256=runtime_sha256,
            )
        )

    def registered_limitation_binding(
        limitation_id: str, applicable_scope_ids: Sequence[str]
    ) -> dict[str, Any]:
        if limitation_id not in allowed_limitations:
            _fail("clause_limitation_unregistered", limitation_id)
        return {
            "registry_id": limitation_registry["registry_id"],
            "registry_sha256": limitation_registry_sha256,
            "effective": limitation_registry["effective"],
            "limitation_id": limitation_id,
            "applicable_scope_ids": sorted(applicable_scope_ids),
        }

    for guard in _MANDATORY_GUARDS:
        add(
            f"guardrail:{guard}",
            guard,
            guard,
            kind="limitation",
            denominator="all role projections",
            as_of=release_day,
            epistemic_type="registered_refusal",
            refs=(),
            limitation_binding=registered_limitation_binding(guard, ("scope:role.all_registered",)),
        )

    limitation_scopes = cast(Mapping[str, Sequence[str]], limitation_registry["limitation_scopes"])
    limitation_denominator = {
        "unique_limitation_ids": len(limitation_registry["output_clause_ids"]),
        "limitation_scope_memberships": sum(
            len(scope_ids) for scope_ids in limitation_registry["output_profiles"].values()
        ),
    }
    for limitation_id in limitation_registry["output_clause_ids"]:
        scope_ids = limitation_scopes[limitation_id]
        add(
            f"output_limitation:{limitation_id}",
            {"limitation_id": limitation_id, "applicable_scope_ids": list(scope_ids)},
            limitation_id,
            kind="limitation",
            denominator=limitation_denominator,
            as_of=release_generated_at,
            epistemic_type="registered_refusal",
            refs=(),
            limitation_binding=registered_limitation_binding(limitation_id, scope_ids),
        )

    event_as_of = traversal["event"]["last_verified_at"]
    event_fields = (
        ("event.canonical_label", event_doc["canonical_label"]),
        ("event.record_status", traversal["event"]["record_status"]),
        ("event.class", event_doc["event_class"]),
        ("event.starts_at", traversal["event"]["starts_at"]),
        ("event.last_verified_at", event_as_of),
        ("event.intensity.status", event_doc["intensity"]["status"]),
        ("event.intensity.value", event_doc["intensity"]["value"]),
        ("event.intensity.unit", event_doc["intensity"]["unit"]),
        ("event.intensity.denominator", event_doc["intensity"]["denominator"]),
        ("event.intensity.uncertainty", event_doc["intensity"]["uncertainty"]),
    )
    for field, value in event_fields:
        add(
            field,
            {"event_id": event_id, "field": field},
            value,
            unit=event_doc["intensity"]["unit"] if field == "event.intensity.value" else None,
            denominator=(
                event_doc["intensity"]["denominator"]
                if field == "event.intensity.value"
                else "one canonical event field"
            ),
            uncertainty=(
                event_doc["intensity"]["uncertainty"] if field == "event.intensity.value" else None
            ),
            as_of=event_as_of,
            refs=(event_ref,),
        )
    add(
        "target.identity",
        target_ref,
        target_ref,
        denominator="one traversal target",
        as_of=release_day,
        refs=(target_ref,),
    )
    add(
        "target.canonical_name",
        {"target_ref": target_ref, "field": "canonical_name"},
        target_doc["canonical_name"],
        denominator="one exact traversal target entity field",
        as_of=release_day,
        refs=(target_ref,),
    )
    add(
        "release.generated_at",
        release_ref,
        release_generated_at,
        kind="provenance",
        denominator="one exact signed canonical release",
        as_of=release_generated_at,
        epistemic_type="derived",
        refs=(release_ref,),
    )

    evidence_denominator = {
        "evidence_items": len(evidence_ids),
        "metadata_fields_per_evidence": len(_EVIDENCE_METADATA_FIELDS),
        "evidence_metadata_clauses": len(evidence_ids) * len(_EVIDENCE_METADATA_FIELDS),
    }
    evidence_field_kinds = {
        "evidence.identity": "provenance",
        "evidence.source_id": "provenance",
        "evidence.title": "provenance",
        "evidence.public_url": "provenance",
        "evidence.published_at": "provenance",
        "evidence.observed_at": "provenance",
        "evidence.verification_status": "provenance",
        "evidence.content_availability": "rights",
        "evidence.rights_use": "rights",
        "evidence.privacy_class": "rights",
        "evidence.rights_decision_id": "rights",
    }
    for evidence_id in evidence_ids:
        document = scoped_evidence[evidence_id]
        evidence_ref = _source_ref("evidence_item", evidence_id, document)
        evidence_fields = {
            "evidence.identity": evidence_ref,
            "evidence.source_id": document["source_id"],
            "evidence.title": document["title"],
            "evidence.public_url": document["public_url"],
            "evidence.published_at": document["published_at"],
            "evidence.observed_at": document["observed_at"],
            "evidence.verification_status": document["verification_status"],
            "evidence.content_availability": document["content_availability"],
            "evidence.rights_use": document["rights_use"],
            "evidence.privacy_class": document["privacy_class"],
            "evidence.rights_decision_id": document["rights_decision_id"],
        }
        if tuple(evidence_fields) != _EVIDENCE_METADATA_FIELDS:
            _fail("clause_evidence_binding_invalid", evidence_id)
        for field, value in evidence_fields.items():
            missingness = "present" if value is not None else "source_missing"
            add(
                field,
                {"evidence_ref": evidence_ref, "field": field},
                value,
                kind=evidence_field_kinds[field],
                denominator=evidence_denominator,
                as_of=document["observed_at"],
                epistemic_type="derived",
                missingness=missingness,
                refs=(evidence_ref,),
            )

    traversal_fields = (
        ("traversal.status", traversal["result"]["status"], None),
        ("traversal.returned_paths", traversal["result"]["returned_paths"], "paths"),
        ("traversal.truncated", traversal["result"]["truncated"], None),
        ("traversal.max_hops", traversal["query"]["max_hops"], "hops"),
        ("traversal.max_paths", traversal["query"]["max_paths"], "paths"),
    )
    for field, value, unit in traversal_fields:
        add(
            field,
            {"upstream": traversal["record_sha256"], "field": field},
            value,
            unit=unit,
            denominator="one complete bounded traversal",
            as_of=release_day,
            epistemic_type="derived",
            refs=all_refs,
        )
    for field, value in sorted(traversal["projection_counts"].items()):
        add(
            f"projection_counts.{field}",
            {"upstream": traversal["record_sha256"], "field": field},
            value,
            unit="records",
            denominator="complete signed release object denominator",
            as_of=release_day,
            epistemic_type="derived",
            refs=all_refs,
        )

    coverage_rows = {
        (
            row["universe_release_id"],
            row["covered_entity_id"],
            row["record_sha256"],
        ): row
        for row in traversal["coverage"]
    }
    if len(coverage_rows) != len(traversal["coverage"]):
        _fail("clause_coverage_binding_invalid")
    seen_coverage_keys: set[tuple[Any, Any, Any]] = set()
    hop_total = 0
    for path_index, path in enumerate(traversal["paths"]):
        if path["entry_entity_id"] != path["entity_ids"][0]:
            _fail("clause_path_binding_invalid")
        for hop_index, hop in enumerate(path["hops"]):
            hop_total += 1
            if (
                hop["edge_id"] != path["edge_ids"][hop_index]
                or hop["source_entity_id"] != path["entity_ids"][hop_index]
                or hop["target_entity_id"] != path["entity_ids"][hop_index + 1]
            ):
                _fail("clause_path_binding_invalid")
            edge_id = cast(str, hop["edge_id"])
            object_row = traversal_rows.get(edge_id)
            edge_row = by_id.get(edge_id)
            if (
                object_row is None
                or object_row.get("object_type") != "exposure_edge"
                or object_row.get("record_sha256") != hop["record_sha256"]
                or edge_row is None
                or edge_row[0] != "exposure_edge"
                or edge_row[1]["record_sha256"] != hop["record_sha256"]
            ):
                _fail("clause_path_binding_invalid", edge_id)
            edge = edge_row[1]
            coverage = hop["coverage"]
            coverage_key = (
                coverage["universe_release_id"],
                coverage["covered_entity_id"],
                coverage["record_sha256"],
            )
            if coverage_key not in coverage_rows or coverage_rows[coverage_key] != coverage:
                _fail("clause_coverage_binding_invalid", edge_id)
            if (
                coverage["universe_release_id"] != edge["coverage_basis"]["universe_release_id"]
                or coverage["covered_entity_id"] != edge["coverage_basis"]["covered_entity_id"]
                or coverage["member_status"] != edge["coverage_basis"]["member_status"]
            ):
                _fail("clause_coverage_binding_invalid", edge_id)
            seen_coverage_keys.add(coverage_key)
            universe_id = cast(str, coverage["universe_release_id"])
            universe_type, universe = by_id[universe_id]
            if universe["record_sha256"] != coverage["record_sha256"]:
                _fail("clause_coverage_binding_invalid", universe_id)
            source_type, source = by_id[cast(str, hop["source_entity_id"])]
            target_type_row, target = by_id[cast(str, hop["target_entity_id"])]
            edge_ref = _source_ref("exposure_edge", edge_id, edge)
            edge_refs = (
                edge_ref,
                _source_ref(universe_type, universe_id, universe),
                _source_ref(source_type, cast(str, hop["source_entity_id"]), source),
                _source_ref(target_type_row, cast(str, hop["target_entity_id"]), target),
            )
            path_binding = {
                "path_index": path_index,
                "hop_index": hop_index,
                "entry_entity_id": path["entry_entity_id"],
                "edge_id": edge_id,
                "edge_record_sha256": hop["record_sha256"],
            }
            identity = {
                "path_index": path_index,
                "hop_index": hop_index,
                "edge_id": edge_id,
                "edge_record_sha256": hop["record_sha256"],
            }
            magnitude = edge["magnitude"]
            edge_fields = (
                ("edge.id", edge_id, None, None, None, "present"),
                ("edge.type", edge["edge_type"], None, None, None, "present"),
                ("edge.direction", edge["exposure_direction"], None, None, None, "present"),
                (
                    "edge.quantification_status",
                    edge["quantification_status"],
                    None,
                    None,
                    None,
                    "present",
                ),
                ("edge.effective_start", edge["effective_start"], None, None, None, "present"),
                (
                    "edge.effective_end",
                    edge["effective_end"],
                    None,
                    None,
                    None,
                    "present" if edge["effective_end"] is not None else "not_applicable",
                ),
                ("edge.observed_at", edge["observed_at"], None, None, None, "present"),
                (
                    "edge.magnitude.value",
                    magnitude["value"],
                    magnitude["unit"],
                    magnitude["denominator"],
                    magnitude["uncertainty"],
                    "present" if magnitude["value"] is not None else "source_missing",
                ),
                (
                    "edge.magnitude.unit",
                    magnitude["unit"],
                    None,
                    "one magnitude unit field",
                    None,
                    "present",
                ),
                (
                    "edge.magnitude.denominator",
                    magnitude["denominator"],
                    None,
                    "one magnitude denominator field",
                    None,
                    "present",
                ),
                (
                    "edge.magnitude.uncertainty",
                    magnitude["uncertainty"],
                    None,
                    magnitude["denominator"],
                    None,
                    "present",
                ),
                (
                    "edge.period_start",
                    magnitude["period_start"],
                    None,
                    "one observed period",
                    None,
                    "present",
                ),
                (
                    "edge.period_end",
                    magnitude["period_end"],
                    None,
                    "one observed period",
                    None,
                    "present",
                ),
                (
                    "edge.missingness",
                    "present" if magnitude["value"] is not None else "source_missing",
                    None,
                    "one edge magnitude field",
                    None,
                    "present",
                ),
            )
            for field, value, unit, denominator, uncertainty, missingness in edge_fields:
                add(
                    field,
                    {**identity, "field": field},
                    value,
                    unit=unit,
                    denominator=denominator or "one returned path hop",
                    uncertainty=uncertainty,
                    missingness=missingness,
                    as_of=edge["observed_at"],
                    refs=edge_refs,
                    path_bindings=(path_binding,),
                    coverage_binding=coverage,
                )

    if hop_total != sum(len(path["hops"]) for path in traversal["paths"]):
        _fail("clause_path_binding_invalid")
    if seen_coverage_keys != set(coverage_rows):
        _fail("clause_coverage_binding_invalid")

    for coverage_key in sorted(coverage_rows):
        coverage = coverage_rows[coverage_key]
        _exact_keys(coverage, _COVERAGE_ROW_FIELDS, "clause_coverage_binding_invalid")
        coverage_counts = coverage.get("counts")
        if not isinstance(coverage_counts, dict):
            _fail("clause_coverage_binding_invalid")
        _exact_keys(
            coverage_counts,
            _COVERAGE_COUNT_FIELDS,
            "clause_coverage_binding_invalid",
        )
        universe_id = cast(str, coverage["universe_release_id"])
        covered_id = cast(str, coverage["covered_entity_id"])
        universe_type, universe = by_id[universe_id]
        covered_type, covered = by_id[covered_id]
        members = [row for row in universe["members"] if row["entity_id"] == covered_id]
        if (
            len(members) != 1
            or members[0]["status"] != coverage["member_status"]
            or universe["record_sha256"] != coverage["record_sha256"]
        ):
            _fail("clause_coverage_binding_invalid", covered_id)
        member = members[0]
        path_bindings = [
            {
                "path_index": path_index,
                "hop_index": hop_index,
                "entry_entity_id": path["entry_entity_id"],
                "edge_id": hop["edge_id"],
                "edge_record_sha256": hop["record_sha256"],
            }
            for path_index, path in enumerate(traversal["paths"])
            for hop_index, hop in enumerate(path["hops"])
            if (
                hop["coverage"]["universe_release_id"],
                hop["coverage"]["covered_entity_id"],
                hop["coverage"]["record_sha256"],
            )
            == coverage_key
        ]
        coverage_refs = (
            _source_ref(universe_type, universe_id, universe),
            _source_ref(covered_type, covered_id, covered),
        )
        add(
            "coverage.row",
            {"coverage_key": list(coverage_key)},
            dict(coverage),
            denominator={
                "coverage_rows": len(coverage_rows),
                "universe_denominator_definition": universe["denominator_definition"],
                "total_eligible": coverage["counts"]["total_eligible"],
            },
            as_of=coverage["reference_date"],
            epistemic_type="derived",
            refs=coverage_refs,
            path_bindings=path_bindings,
            coverage_binding=coverage,
        )
        facts = (
            ("coverage.universe_release_id", universe_id, None),
            ("coverage.reference_date", coverage["reference_date"], None),
            ("coverage.covered_entity_id", covered_id, None),
            ("coverage.member_status", coverage["member_status"], None),
            ("coverage.member_reason", member["reason_code"], None),
            ("coverage.member_assessed_on", member["assessed_on"], None),
            ("coverage.denominator_definition", universe["denominator_definition"], None),
            ("coverage.total_eligible", coverage["counts"]["total_eligible"], "records"),
            ("coverage.included", coverage["counts"]["included"], "records"),
            ("coverage.excluded", coverage["counts"]["excluded"], "records"),
            ("coverage.unmappable", coverage["counts"]["unmappable"], "records"),
            ("coverage.stale", coverage["counts"]["stale"], "records"),
        )
        for field, value, unit in facts:
            add(
                field,
                {"coverage_key": list(coverage_key), "field": field},
                value,
                unit=unit,
                denominator=universe["denominator_definition"],
                as_of=coverage["reference_date"],
                refs=coverage_refs,
                path_bindings=path_bindings,
                coverage_binding=coverage,
            )

    for object_id, row in sorted(traversal_rows.items()):
        object_type, document = by_id[object_id]
        ref = _source_ref(object_type, object_id, document)
        if any(ref[field] != row[field] for field in ("object_type", "object_id", "record_sha256")):
            _fail("clause_source_binding_invalid", object_id)
        add(
            "provenance.source_object_ref",
            ref,
            ref,
            kind="provenance",
            denominator="complete upstream object_evidence denominator",
            as_of=release_day,
            epistemic_type="derived",
            refs=(ref,),
        )

    evidence_by_id = {row["evidence_id"]: row for row in traversal["evidence"]}
    for source_id, rights in sorted((row["source_id"], row) for row in traversal["rights"]):
        evidence_refs = []
        for evidence_id, row in sorted(evidence_by_id.items()):
            if row["source_id"] != source_id:
                continue
            document = evidence_objects[evidence_id]
            if document["record_sha256"] != row["record_sha256"]:
                _fail("clause_source_binding_invalid", evidence_id)
            evidence_refs.append(_source_ref("evidence_item", evidence_id, document))
        if not evidence_refs:
            _fail("clause_source_binding_invalid", cast(str, source_id))
        add(
            "rights.release_snapshot",
            {"source_id": source_id, "rights": rights},
            {
                "source_id": source_id,
                "rights_snapshot": dict(rights),
                "release_rights_identity": {
                    key: traversal["release"][key]
                    for key in (
                        "release_id",
                        "record_sha256",
                        "release_signer_id",
                        "rights_registry_sha256",
                        "rights_signers_sha256",
                        "release_signers_sha256",
                    )
                },
            },
            kind="rights",
            denominator="complete release rights snapshot for cited source",
            as_of=release_day,
            epistemic_type="derived",
            refs=evidence_refs,
        )

    clauses.sort(key=lambda row: cast(str, row["clause_id"]))
    return clauses


def _contract_binding(
    contract: Mapping[str, Any],
    contract_sha256: str,
    profile_sha256: str,
    pins: Mapping[str, str],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "clause_contract_id": contract["contract_id"],
        "clause_contract_sha256": contract_sha256,
        "analytical_clause_runtime_sha256": pins["analytical_clause_runtime"],
        "analytical_clause_limitations_sha256": pins["analytical_clause_limitations"],
        "source_profile_sha256": profile_sha256,
        "canonical_schema_registry_sha256": manifest["schema_registry_sha256"],
        "canonical_runtime_sha256": pins["canonical_runtime"],
        "typed_canonical_runtime_sha256": pins["typed_canonical_runtime"],
        "typed_record_runtime_sha256": pins["typed_record_runtime"],
        "exposure_projection_registry_sha256": pins["exposure_projection_registry"],
        "exposure_schema_sha256": pins["exposure_schema"],
        "exposure_runtime_sha256": pins["exposure_runtime"],
        "synthetic_fixture_runtime_sha256": pins["synthetic_fixture_runtime"],
        "adversarial_vectors_sha256": pins["adversarial_vectors"],
    }


def _clause_refs(clauses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "clause_id": clause["clause_id"],
            "clause_record_sha256": clause["record_sha256"],
        }
        for clause in sorted(clauses, key=lambda row: cast(str, row["clause_id"]))
    ]


def _compile_source_bundle(
    *,
    contract: Mapping[str, Any],
    contract_sha256: str,
    profile_sha256: str,
    pins: Mapping[str, str],
    profile: Mapping[str, Any],
    limitation_registry: Mapping[str, Any],
    limitation_registry_sha256: str,
    query_id: str,
    traversal: Mapping[str, Any],
    validated: canonical.ValidatedCanonicalRelease,
) -> dict[str, Any]:
    clauses = _compile_incumbent_clauses(
        query_id,
        traversal,
        validated,
        profile,
        profile_sha256,
        limitation_registry,
        limitation_registry_sha256,
        pins["analytical_clause_runtime"],
    )
    compile_clauses(clauses, contract)
    query = dict(traversal["query"])
    denominators = {
        "clauses": len(clauses),
        "paths": len(traversal["paths"]),
        "hops": sum(len(path["hops"]) for path in traversal["paths"]),
        "coverage_rows": len(traversal["coverage"]),
        "object_evidence_rows": len(traversal["object_evidence"]),
        "evidence_rows": len(traversal["evidence"]),
        "evidence_items": len(
            {
                evidence_id
                for row in traversal["object_evidence"]
                for evidence_id in row["evidence_ids"]
            }
        ),
        "evidence_metadata_fields": len(_EVIDENCE_METADATA_FIELDS),
        "evidence_metadata_clauses": len(traversal["evidence"]) * len(_EVIDENCE_METADATA_FIELDS),
        "rights_rows": len(traversal["rights"]),
        "output_limitation_ids": len(limitation_registry["output_clause_ids"]),
        "output_limitation_scope_memberships": sum(
            len(scope_ids) for scope_ids in limitation_registry["output_profiles"].values()
        ),
        "guardrail_ids": len(_MANDATORY_GUARDS),
    }
    identity = {
        "release_record_sha256": traversal["release"]["record_sha256"],
        "query_id": query_id,
        "query_sha256": _typed_sha(query),
        "profile_sha256": profile_sha256,
    }
    value = {
        "object_type": "source_bound_clause_bundle",
        "schema_version": _VERSION,
        "bundle_id": f"clause-bundle:{_typed_sha(identity)[:24]}",
        "record_sha256": "0" * 64,
        "contract": _contract_binding(
            contract, contract_sha256, profile_sha256, pins, validated.manifest
        ),
        "source_release": _release_identity(validated.manifest),
        "query": {"query_id": query_id, "query_sha256": _typed_sha(query), **query},
        "upstream": {
            "object_type": traversal["object_type"],
            "record_sha256": traversal["record_sha256"],
            "method": dict(traversal["method"]),
            "contract": dict(traversal["contract"]),
            "recomputed": True,
        },
        "complete_denominators": denominators,
        "clauses": clauses,
        "limitations": sorted({*_CLAIM_LIMITATIONS, *traversal["limitations"]}),
        "trust": dict(_TRUST),
        "product_manifest_boundary": dict(_PRODUCT_BOUNDARY),
    }
    return _seal(value)


def _compile_role_proof_bundle(
    source_bundle: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, Any]:
    clauses = cast(Sequence[Mapping[str, Any]], source_bundle["clauses"])
    refs = _clause_refs(clauses)
    roles: list[dict[str, Any]] = [
        {
            "role_id": role,
            "included_clause_refs": [dict(ref) for ref in refs],
            "omitted_clause_refs": [],
        }
        for role in _REQUIRED_ROLES
    ]
    views: dict[str, dict[str, str]] = {}
    for role in roles:
        role_id = cast(str, role["role_id"])
        included = cast(Sequence[Mapping[str, Any]], role["included_clause_refs"])
        views[role_id] = validate_role_view(role_id, included, clauses, contract)
    invariant = cross_role_invariant(views)
    pairs = [
        {
            "left_role_id": left,
            "right_role_id": right,
            "shared_clause_refs": [dict(ref) for ref in refs],
            "left_only_registered_omissions": [],
            "right_only_registered_omissions": [],
            "status": "same_incumbent_clause_record",
        }
        for left, right in combinations(_REQUIRED_ROLES, 2)
    ]
    identity = {
        "source_bundle_record_sha256": source_bundle["record_sha256"],
        "roles": list(_REQUIRED_ROLES),
    }
    value = {
        "object_type": "cross_role_clause_proof_bundle",
        "schema_version": _VERSION,
        "proof_bundle_id": f"clause-proof:{_typed_sha(identity)[:24]}",
        "record_sha256": "0" * 64,
        "source_bundle_ref": {
            "bundle_id": source_bundle["bundle_id"],
            "record_sha256": source_bundle["record_sha256"],
        },
        "contract": dict(source_bundle["contract"]),
        "complete_clause_denominator": len(refs),
        "complete_role_denominator": len(_REQUIRED_ROLES),
        "required_role_ids": list(_REQUIRED_ROLES),
        "roles": roles,
        "cross_role_proof": {
            "invariant_id": "invariant:shared_incumbent_clause_exact_record",
            "role_pair_denominator": len(pairs),
            "pairs": pairs,
            "shared_clause_digest_sha256": invariant["shared_clause_digest_sha256"],
            "prose_equivalence_claimed": False,
            "proof_authority": "complete_set_level_recomputation_only",
        },
        "limitations": list(source_bundle["limitations"]),
        "trust": dict(_TRUST),
        "product_manifest_boundary": dict(_PRODUCT_BOUNDARY),
    }
    return _seal(value)


def compile_source_bound_clauses(
    manifest_path: Path,
    query_id: str = "query:analytical_clause.fixture.path_found",
    *,
    root: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reopen a registered synthetic release and compile both additive bundles."""

    bundle_root = root or manifest_path.resolve().parents[1]
    kwargs = _bundle_kwargs(bundle_root)
    try:
        validated = canonical.load_validated_release(manifest_path, root=bundle_root, **kwargs)
    except canonical.CanonicalObjectError as exc:
        raise AnalyticalClauseError("clause_source_release_refused", exc.code) from exc
    release_day = _day(validated.manifest["effective_date"], "clause_source_release_refused")
    profile, profile_sha, pins, queries = load_source_profile(release_effective=release_day)
    limitation_registry, limitation_registry_sha = load_limitation_registry(
        pins["analytical_clause_limitations"], release_effective=release_day
    )
    contract, contract_sha = load_contract()
    if (
        pins["analytical_clause_contract"] != contract_sha
        or pins["analytical_clause_runtime"] != _sha(Path(__file__).resolve())
        or validated.manifest["schema_registry_sha256"] != pins["canonical_schema_registry"]
        or validated.manifest["release_id"] != profile["allowed_release"]["release_id"]
        or validated.manifest["release_signer_id"]
        != profile["allowed_release"]["release_signer_id"]
    ):
        _fail("clause_source_release_unregistered")
    fixture_projection_registry = exposure_graph.PROJECTION_REGISTRY
    if _sha(fixture_projection_registry) != pins["exposure_projection_registry"]:
        _fail("clause_source_profile_drift", "exposure registry")
    query = queries.get(query_id)
    if query is None:
        _fail("clause_source_profile_invalid", query_id)
    try:
        traversal = exposure_graph.project_event_exposure(
            manifest_path,
            cast(str, query["event_id"]),
            cast(str, query["target_entity_id"]),
            max_hops=cast(int, query["max_hops"]),
            max_paths=cast(int, query["max_paths"]),
            root=bundle_root,
            projection_registry_path=fixture_projection_registry,
            **kwargs,
        )
    except canonical.CanonicalObjectError as exc:
        raise AnalyticalClauseError("clause_source_release_refused", exc.code) from exc
    except exposure_graph.ExposureGraphError as exc:
        raise AnalyticalClauseError("clause_upstream_refused", exc.code) from exc
    expected_query = {
        "event_id": query["event_id"],
        "target_entity_id": query["target_entity_id"],
        "max_hops": query["max_hops"],
        "max_paths": query["max_paths"],
        "selection_rule": "bounded_breadth_first_stored_direction_simple_paths",
        "temporal_basis": "canonical_release_effective_date",
        "event_edge_temporal_relation": "event_entities_to_release_effective_graph",
    }
    if (
        traversal["query"] != expected_query
        or traversal["method"]["implementation_sha256"] != pins["exposure_runtime"]
        or traversal["contract"]["projection_registry_sha256"]
        != pins["exposure_projection_registry"]
        or traversal["contract"]["schema_sha256"] != pins["exposure_schema"]
    ):
        _fail("clause_upstream_binding_invalid")
    source_bundle = _compile_source_bundle(
        contract=contract,
        contract_sha256=contract_sha,
        profile_sha256=profile_sha,
        pins=pins,
        profile=profile,
        limitation_registry=limitation_registry,
        limitation_registry_sha256=limitation_registry_sha,
        query_id=query_id,
        traversal=traversal,
        validated=validated,
    )
    proof_bundle = _compile_role_proof_bundle(source_bundle, contract)
    validate_source_bundle(
        source_bundle,
        contract,
        profile_sha,
        pins,
        limitation_registry,
        limitation_registry_sha,
    )
    validate_role_proof_bundle(proof_bundle, source_bundle, contract)
    return source_bundle, proof_bundle


def validate_source_bundle(
    source_bundle: Mapping[str, Any],
    contract: Mapping[str, Any],
    profile_sha256: str,
    pins: Mapping[str, str],
    limitation_registry: Mapping[str, Any],
    limitation_registry_sha256: str,
) -> None:
    expected = (
        "object_type",
        "schema_version",
        "bundle_id",
        "record_sha256",
        "contract",
        "source_release",
        "query",
        "upstream",
        "complete_denominators",
        "clauses",
        "limitations",
        "trust",
        "product_manifest_boundary",
    )
    _exact_keys(source_bundle, expected, "clause_source_binding_invalid")
    binding = source_bundle["contract"]
    _exact_keys(
        binding,
        (
            "clause_contract_id",
            "clause_contract_sha256",
            "analytical_clause_runtime_sha256",
            "analytical_clause_limitations_sha256",
            "source_profile_sha256",
            "canonical_schema_registry_sha256",
            "canonical_runtime_sha256",
            "typed_canonical_runtime_sha256",
            "typed_record_runtime_sha256",
            "exposure_projection_registry_sha256",
            "exposure_schema_sha256",
            "exposure_runtime_sha256",
            "synthetic_fixture_runtime_sha256",
            "adversarial_vectors_sha256",
        ),
        "clause_source_binding_invalid",
    )
    expected_binding = {
        "clause_contract_id": contract["contract_id"],
        "clause_contract_sha256": _sha(CONTRACT_PATH),
        "analytical_clause_runtime_sha256": pins["analytical_clause_runtime"],
        "analytical_clause_limitations_sha256": pins["analytical_clause_limitations"],
        "source_profile_sha256": profile_sha256,
        "canonical_schema_registry_sha256": pins["canonical_schema_registry"],
        "canonical_runtime_sha256": pins["canonical_runtime"],
        "typed_canonical_runtime_sha256": pins["typed_canonical_runtime"],
        "typed_record_runtime_sha256": pins["typed_record_runtime"],
        "exposure_projection_registry_sha256": pins["exposure_projection_registry"],
        "exposure_schema_sha256": pins["exposure_schema"],
        "exposure_runtime_sha256": pins["exposure_runtime"],
        "synthetic_fixture_runtime_sha256": pins["synthetic_fixture_runtime"],
        "adversarial_vectors_sha256": pins["adversarial_vectors"],
    }
    if (
        source_bundle["object_type"] != "source_bound_clause_bundle"
        or source_bundle["schema_version"] != _VERSION
        or source_bundle["trust"] != _TRUST
        or source_bundle["product_manifest_boundary"] != _PRODUCT_BOUNDARY
        or binding != expected_binding
        or source_bundle["upstream"].get("recomputed") is not True
    ):
        _fail("clause_source_binding_invalid")
    source_release = source_bundle["source_release"]
    if not isinstance(source_release, dict) or set(source_release) != {
        "release_id",
        "record_sha256",
        "generated_at",
        "effective_date",
        "release_signer_id",
        "schema_registry_sha256",
        "method_registry_sha256",
        "rights_registry_sha256",
        "rights_signers_sha256",
        "release_signers_sha256",
    }:
        _fail("clause_source_binding_invalid", "source release")
    if _instant(source_release["generated_at"], "clause_source_binding_invalid").date() < _day(
        source_release["effective_date"], "clause_source_binding_invalid"
    ):
        _fail("clause_source_binding_invalid", "release chronology")
    _verify_digest(source_bundle, "clause_source_bundle_digest_mismatch")
    clauses = cast(Sequence[Mapping[str, Any]], source_bundle["clauses"])
    compiled = compile_clauses(clauses, contract)
    denominator = source_bundle["complete_denominators"]
    if (
        not isinstance(denominator, dict)
        or set(denominator)
        != {
            "clauses",
            "paths",
            "hops",
            "coverage_rows",
            "object_evidence_rows",
            "evidence_rows",
            "evidence_items",
            "evidence_metadata_fields",
            "evidence_metadata_clauses",
            "rights_rows",
            "output_limitation_ids",
            "output_limitation_scope_memberships",
            "guardrail_ids",
        }
        or denominator["clauses"] != len(compiled)
        or denominator["evidence_items"] != denominator["evidence_rows"]
        or denominator["evidence_metadata_fields"] != len(_EVIDENCE_METADATA_FIELDS)
        or denominator["evidence_metadata_clauses"]
        != denominator["evidence_items"] * len(_EVIDENCE_METADATA_FIELDS)
        or denominator["output_limitation_ids"] != len(limitation_registry["output_clause_ids"])
        or denominator["output_limitation_scope_memberships"]
        != sum(len(scope_ids) for scope_ids in limitation_registry["output_profiles"].values())
        or denominator["guardrail_ids"] != len(_MANDATORY_GUARDS)
    ):
        _fail("clause_source_binding_invalid")
    if not set(source_bundle["limitations"]) <= set(limitation_registry["allowed_ids"]):
        _fail("clause_limitation_unregistered")
    limitation_clauses = [clause for clause in clauses if clause["kind"] == "limitation"]
    guards = {
        clause["value"]
        for clause in limitation_clauses
        if clause["proof_binding"]["source_field"].startswith("guardrail:")
    }
    output_limitations = {
        clause["value"]: clause
        for clause in limitation_clauses
        if clause["value"] in limitation_registry["output_clause_ids"]
    }
    if guards != set(_MANDATORY_GUARDS) or set(output_limitations) != set(
        limitation_registry["output_clause_ids"]
    ):
        _fail("clause_source_binding_invalid")
    for limitation_id, clause in output_limitations.items():
        expected_limitation_binding = {
            "registry_id": limitation_registry["registry_id"],
            "registry_sha256": limitation_registry_sha256,
            "effective": limitation_registry["effective"],
            "limitation_id": limitation_id,
            "applicable_scope_ids": limitation_registry["limitation_scopes"][limitation_id],
        }
        if clause["proof_binding"]["limitation_binding"] != expected_limitation_binding:
            _fail("clause_limitation_scope_invalid", cast(str, limitation_id))
    evidence_clauses = [
        clause
        for clause in clauses
        if clause["proof_binding"]["source_field"] in _EVIDENCE_METADATA_FIELDS
    ]
    evidence_refs = {
        cast(str, clause["proof_binding"]["source_object_refs"][0]["object_id"])
        for clause in evidence_clauses
    }
    evidence_pairs = [
        (
            clause["proof_binding"]["source_object_refs"][0]["object_id"],
            clause["proof_binding"]["source_field"],
        )
        for clause in evidence_clauses
    ]
    if (
        len(evidence_clauses) != denominator["evidence_metadata_clauses"]
        or len(evidence_refs) != denominator["evidence_items"]
        or len(evidence_pairs) != len(set(evidence_pairs))
        or any(
            {field for evidence_id, field in evidence_pairs if evidence_id == expected_evidence_id}
            != set(_EVIDENCE_METADATA_FIELDS)
            for expected_evidence_id in evidence_refs
        )
    ):
        _fail("clause_evidence_binding_invalid")
    coverage_row_clauses = [
        clause
        for clause in clauses
        if clause["proof_binding"]["source_field"] == "coverage.row"
    ]
    coverage_values: set[str] = set()
    for clause in coverage_row_clauses:
        value = clause["value"]
        counts = value.get("counts") if isinstance(value, dict) else None
        binding = clause["proof_binding"]["coverage_binding"]
        refs = clause["proof_binding"]["source_object_refs"]
        clause_denominator = clause["denominator"]
        if (
            not isinstance(value, dict)
            or set(value) != set(_COVERAGE_ROW_FIELDS)
            or not isinstance(counts, dict)
            or set(counts) != set(_COVERAGE_COUNT_FIELDS)
            or any(
                isinstance(count, bool) or not isinstance(count, int) or count < 0
                for count in counts.values()
            )
            or counts["total_eligible"] < 1
            or binding != value
            or not isinstance(refs, list)
            or len(refs) != 2
            or not any(
                ref.get("object_type") == "universe_release"
                and ref.get("object_id") == value["universe_release_id"]
                and ref.get("record_sha256") == value["record_sha256"]
                for ref in refs
            )
            or not any(
                ref.get("object_type") == "entity"
                and ref.get("object_id") == value["covered_entity_id"]
                for ref in refs
            )
            or not isinstance(clause_denominator, dict)
            or set(clause_denominator)
            != {
                "coverage_rows",
                "universe_denominator_definition",
                "total_eligible",
            }
            or clause_denominator["coverage_rows"] != denominator["coverage_rows"]
            or clause_denominator["total_eligible"] != counts["total_eligible"]
            or not isinstance(clause_denominator["universe_denominator_definition"], str)
            or not clause_denominator["universe_denominator_definition"]
            or not clause["proof_binding"]["path_bindings"]
        ):
            _fail("clause_coverage_binding_invalid")
        coverage_values.add(_typed_sha(value))
    if (
        len(coverage_row_clauses) != denominator["coverage_rows"]
        or len(coverage_values) != denominator["coverage_rows"]
    ):
        _fail("clause_coverage_binding_invalid")
    singleton_fields = (
        "event.canonical_label",
        "target.identity",
        "target.canonical_name",
        "release.generated_at",
    )
    if any(
        sum(clause["proof_binding"]["source_field"] == field for clause in clauses) != 1
        for field in singleton_fields
    ):
        _fail("clause_source_binding_invalid")
    release_clause = next(
        clause
        for clause in clauses
        if clause["proof_binding"]["source_field"] == "release.generated_at"
    )
    if release_clause["value"] != source_release["generated_at"]:
        _fail("clause_source_binding_invalid", "release generated_at")


def validate_role_proof_bundle(
    proof_bundle: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    expected = (
        "object_type",
        "schema_version",
        "proof_bundle_id",
        "record_sha256",
        "source_bundle_ref",
        "contract",
        "complete_clause_denominator",
        "complete_role_denominator",
        "required_role_ids",
        "roles",
        "cross_role_proof",
        "limitations",
        "trust",
        "product_manifest_boundary",
    )
    _exact_keys(proof_bundle, expected, "clause_role_proof_invalid")
    if (
        proof_bundle["object_type"] != "cross_role_clause_proof_bundle"
        or proof_bundle["schema_version"] != _VERSION
        or proof_bundle["source_bundle_ref"]
        != {
            "bundle_id": source_bundle["bundle_id"],
            "record_sha256": source_bundle["record_sha256"],
        }
        or proof_bundle["contract"] != source_bundle["contract"]
        or proof_bundle["trust"] != _TRUST
        or proof_bundle["product_manifest_boundary"] != _PRODUCT_BOUNDARY
    ):
        _fail("clause_role_proof_invalid")
    _verify_digest(proof_bundle, "clause_role_proof_digest_mismatch")
    clauses = cast(Sequence[Mapping[str, Any]], source_bundle["clauses"])
    refs = _clause_refs(clauses)
    roles = proof_bundle["roles"]
    role_ids = [row.get("role_id") for row in roles]
    if (
        role_ids != list(_REQUIRED_ROLES)
        or proof_bundle["required_role_ids"] != list(_REQUIRED_ROLES)
        or proof_bundle["complete_role_denominator"] != len(_REQUIRED_ROLES)
        or proof_bundle["complete_clause_denominator"] != len(refs)
    ):
        _fail("clause_role_proof_invalid")
    views: dict[str, dict[str, str]] = {}
    for role in roles:
        _exact_keys(
            role,
            ("role_id", "included_clause_refs", "omitted_clause_refs"),
            "clause_role_proof_invalid",
        )
        if role["omitted_clause_refs"] != [] or role["included_clause_refs"] != refs:
            _fail("clause_role_proof_invalid", cast(str, role["role_id"]))
        views[cast(str, role["role_id"])] = validate_role_view(
            cast(str, role["role_id"]), role["included_clause_refs"], clauses, contract
        )
    invariant = cross_role_invariant(views)
    expected_pairs = [
        {
            "left_role_id": left,
            "right_role_id": right,
            "shared_clause_refs": refs,
            "left_only_registered_omissions": [],
            "right_only_registered_omissions": [],
            "status": "same_incumbent_clause_record",
        }
        for left, right in combinations(_REQUIRED_ROLES, 2)
    ]
    expected_proof = {
        "invariant_id": "invariant:shared_incumbent_clause_exact_record",
        "role_pair_denominator": len(expected_pairs),
        "pairs": expected_pairs,
        "shared_clause_digest_sha256": invariant["shared_clause_digest_sha256"],
        "prose_equivalence_claimed": False,
        "proof_authority": "complete_set_level_recomputation_only",
    }
    if proof_bundle["cross_role_proof"] != expected_proof:
        _fail("clause_role_proof_invalid")


def verify_source_bound_compilation(
    manifest_path: Path,
    query_id: str,
    source_bundle: Mapping[str, Any],
    proof_bundle: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Reopen exact inputs, rerun upstream and require byte-identical bundles."""

    expected_source, expected_proof = compile_source_bound_clauses(
        manifest_path, query_id, root=root
    )
    contract, _ = load_contract()
    _, profile_sha, pins, _ = load_source_profile(
        release_effective=_day(
            expected_source["source_release"]["effective_date"],
            "clause_source_release_refused",
        )
    )
    limitation_registry, limitation_registry_sha = load_limitation_registry(
        pins["analytical_clause_limitations"],
        release_effective=_day(
            expected_source["source_release"]["effective_date"],
            "clause_source_release_refused",
        ),
    )
    validate_source_bundle(
        source_bundle,
        contract,
        profile_sha,
        pins,
        limitation_registry,
        limitation_registry_sha,
    )
    validate_role_proof_bundle(proof_bundle, source_bundle, contract)
    if serialize_record(source_bundle) != serialize_record(expected_source):
        _fail("clause_source_bundle_recompile_mismatch")
    if serialize_record(proof_bundle) != serialize_record(expected_proof):
        _fail("clause_role_proof_recompile_mismatch")
    return {
        "status": "valid",
        "claim": "all_seven_roles_reference_same_incumbent_atomic_clause_records",
        "source_bundle_id": source_bundle["bundle_id"],
        "source_bundle_record_sha256": source_bundle["record_sha256"],
        "proof_bundle_id": proof_bundle["proof_bundle_id"],
        "proof_bundle_record_sha256": proof_bundle["record_sha256"],
        "clause_denominator": source_bundle["complete_denominators"]["clauses"],
        "role_denominator": proof_bundle["complete_role_denominator"],
        "authenticated": False,
        "production_authority": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    contract, digest = load_contract()
    print(f"[clause] contract {contract['contract_id']} sha256={digest}")
    print(
        f"[clause] {len(contract['roles'])} roles, every clause field protected, "
        f"{sum(1 for value in contract['clause_kinds'].values() if value['never_omittable'])} "
        "never-omittable kinds"
    )


if __name__ == "__main__":
    main()
