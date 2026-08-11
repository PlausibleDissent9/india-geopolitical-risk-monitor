"""Internal one-source typed clause resolution for four future consumers.

This kernel captures one incumbent source bundle and its exact seven-role proof
once, validates only through the incumbent authorities, and builds one closed
24-field index plus four access policies from the fixed consumer profile.  It
does not reopen canonical facts, render prose, create a role projection, or
claim source replay, authentication, output equivalence, or public authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any, Generic, NoReturn, TypeVar, cast

from jsonschema import Draft202012Validator

from . import analytical_clause as ac
from . import evidence_output_consumer_contract as consumer

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "clause_source_view_contract.json"
PROFILE_PATH = consumer.PROFILE_PATH
RECEIPT_SCHEMA_PATH = (
    ROOT / "governance" / "schemas" / "clause-source-view-receipt.schema.json"
)
ADVERSARIAL_VECTORS_PATH = (
    ROOT / "governance" / "clause_source_view_adversarial_vectors.json"
)

_VERSION = "0.2.0"
_CONTRACT_ID = "igrm:clause-source-view:0.2.0"
_REGISTERED_CONTRACT_SHA256 = (
    "d9957043855874bd82a2e1b01082f11a8bf8b84eb757a6e70c0119be440845e6"
)
_OUTPUT_IDS = (
    "output:board_brief",
    "output:newsroom_claim_card",
    "output:offline_audit_bundle",
    "output:research_package",
)
_REQUIRED_ROLES = (
    "research",
    "board",
    "newsroom",
    "public",
    "api",
    "priority_language",
    "offline",
)
_QUERY_FIELDS = {
    "query_id",
    "query_sha256",
    "event_id",
    "target_entity_id",
    "max_hops",
    "max_paths",
    "selection_rule",
    "temporal_basis",
    "event_edge_temporal_relation",
}
_TRUST: dict[str, Any] = {
    "immutable_captured_inputs": True,
    "self_hash_integrity_only": True,
    "signed": False,
    "authenticated": False,
    "caller_authority_accepted": False,
}
_BOUNDARY: dict[str, Any] = {
    "structural_derivation_only": True,
    "verified_snapshot_available": True,
    "verified_snapshot_rebuilds_from_captured_source_and_proof_only": True,
    "source_replay_performed": False,
    "source_replay_verified": False,
    "source_truth_claimed": False,
    "role_projection_created": False,
    "selector_partition_scope": (
        "registered_selector_subset_not_complete_clause_denominator"
    ),
    "all_source_clause_omission_receipt_available": False,
    "prose_rendered": False,
    "output_created": False,
    "output_equivalence_claimed": False,
    "prose_equivalence_claimed": False,
    "publication_approved": False,
    "product_manifest_created": False,
    "correction_blast_radius_claimed": False,
    "production_authority": False,
    "public_authority": False,
}
_REFUSAL_CODES = {
    "view_binding_invalid",
    "view_branch_invalid",
    "view_cardinality_invalid",
    "view_consumer_policy_invalid",
    "view_contract_drift",
    "view_contract_invalid",
    "view_field_index_invalid",
    "view_field_not_required",
    "view_field_unknown",
    "view_input_invalid",
    "view_profile_refused",
    "view_proof_refused",
    "view_query_invalid",
    "view_receipt_invalid",
    "view_recompile_mismatch",
    "view_runtime_drift",
    "view_source_refused",
}

T = TypeVar("T")
_CONSTRUCTION_TOKEN = object()


class ClauseSourceViewError(ValueError):
    """Stable fail-closed refusal from the internal view kernel."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ClauseSourceViewError(code, detail)


@dataclass(frozen=True, order=True)
class ClauseRef:
    """Exact incumbent clause identity; never a copied clause payload."""

    clause_id: str
    clause_record_sha256: str


@dataclass(frozen=True)
class ClauseValue(Generic[T]):
    """Fresh typed lookup result reconstructed from immutable clause bytes."""

    clause_ref: ClauseRef
    source_field: str
    value_class: str
    value: T | None
    missingness: str
    denominator: Any
    source_object_refs: tuple[dict[str, Any], ...]
    source_identity_key: dict[str, Any] | None


@dataclass(frozen=True)
class _FieldEntry:
    source_field: str
    cardinality: str
    value_class: str
    denominator_key: str | None
    nullable_source_missing: bool
    expected_count: int
    clause_refs: tuple[ClauseRef, ...]
    clause_bytes: tuple[bytes, ...]


@dataclass(frozen=True)
class _ConsumerPolicy:
    view_id: str
    output_id: str
    role_id: str
    active_template_ids: tuple[str, ...]
    inactive_template_ids: tuple[str, ...]
    required_source_fields: frozenset[str]
    omitted_source_fields: frozenset[str]
    limitation_scope_ids: tuple[str, ...]
    uncovered_gap_ids: tuple[str, ...]
    selected_ref_count: int
    selected_ref_sha256: str


class _ConsumerClauseSourceView:
    """One fixed profile-derived access policy over the shared global index."""

    __slots__ = ("_entries", "_policy")
    _entries: Mapping[str, _FieldEntry]
    _policy: _ConsumerPolicy

    def __init__(
        self,
        entries: Mapping[str, _FieldEntry],
        policy: _ConsumerPolicy,
        *,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _CONSTRUCTION_TOKEN:
            raise TypeError("consumer clause views are factory-only")
        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_policy", policy)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("consumer clause views are immutable")

    @property
    def view_id(self) -> str:
        return self._policy.view_id

    @property
    def output_id(self) -> str:
        return self._policy.output_id

    @property
    def role_id(self) -> str:
        return self._policy.role_id

    @property
    def active_template_ids(self) -> tuple[str, ...]:
        return tuple(self._policy.active_template_ids)

    @property
    def inactive_template_ids(self) -> tuple[str, ...]:
        return tuple(self._policy.inactive_template_ids)

    def _required_entry(self, source_field: object) -> _FieldEntry:
        if not isinstance(source_field, str) or source_field not in self._entries:
            _fail("view_field_unknown")
        if source_field not in self._policy.required_source_fields:
            _fail("view_field_not_required", source_field)
        return self._entries[source_field]

    def one(self, source_field: str) -> ClauseValue[Any]:
        """Return a fresh copy of one required singleton registered clause."""

        entry = self._required_entry(source_field)
        if entry.cardinality != "exactly_one" or len(entry.clause_bytes) != 1:
            _fail("view_cardinality_invalid", source_field)
        return _resolve_clause(entry, 0)

    def many(self, source_field: str) -> tuple[ClauseValue[Any], ...]:
        """Return every required multirow clause independently by clause id."""

        entry = self._required_entry(source_field)
        if entry.cardinality != "exact_bundle_denominator":
            _fail("view_cardinality_invalid", source_field)
        return tuple(_resolve_clause(entry, index) for index in range(len(entry.clause_bytes)))


class ClauseSourceViews:
    """All four access policies and their immutable captured verification inputs."""

    __slots__ = (
        "_entries",
        "_policies",
        "_source_bytes",
        "_proof_bytes",
        "_profile_bytes",
        "_contract_bytes",
        "_receipt_bytes",
        "_runtime_sha256",
    )
    _entries: Mapping[str, _FieldEntry]
    _policies: Mapping[str, _ConsumerPolicy]
    _source_bytes: bytes
    _proof_bytes: bytes
    _profile_bytes: bytes
    _contract_bytes: bytes
    _receipt_bytes: bytes
    _runtime_sha256: str

    def __init__(
        self,
        *,
        _construction_token: object,
        entries: Mapping[str, _FieldEntry],
        policies: Mapping[str, _ConsumerPolicy],
        source_bytes: bytes,
        proof_bytes: bytes,
        profile_bytes: bytes,
        contract_bytes: bytes,
        receipt_bytes: bytes,
        runtime_sha256: str,
    ) -> None:
        if _construction_token is not _CONSTRUCTION_TOKEN:
            raise TypeError("clause source views are factory-only")
        object.__setattr__(self, "_entries", entries)
        object.__setattr__(self, "_policies", policies)
        object.__setattr__(self, "_source_bytes", source_bytes)
        object.__setattr__(self, "_proof_bytes", proof_bytes)
        object.__setattr__(self, "_profile_bytes", profile_bytes)
        object.__setattr__(self, "_contract_bytes", contract_bytes)
        object.__setattr__(self, "_receipt_bytes", receipt_bytes)
        object.__setattr__(self, "_runtime_sha256", runtime_sha256)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("clause source views are immutable")

    def _view(self, output_id: str) -> _ConsumerClauseSourceView:
        policy = self._policies.get(output_id)
        if policy is None:
            _fail("view_consumer_policy_invalid", output_id)
        return _ConsumerClauseSourceView(
            self._entries,
            policy,
            _construction_token=_CONSTRUCTION_TOKEN,
        )

    @property
    def board(self) -> _ConsumerClauseSourceView:
        return self._view("output:board_brief")

    @property
    def newsroom(self) -> _ConsumerClauseSourceView:
        return self._view("output:newsroom_claim_card")

    @property
    def offline(self) -> _ConsumerClauseSourceView:
        return self._view("output:offline_audit_bundle")

    @property
    def research(self) -> _ConsumerClauseSourceView:
        return self._view("output:research_package")

    @property
    def receipt(self) -> dict[str, Any]:
        """Return a fresh receipt copy; internal receipt bytes remain immutable."""

        return _decode_object(self._receipt_bytes, "view_receipt_invalid")

    def verify(self) -> ClauseSourceViews:
        """Reopen exact captures, revalidate, and require byte-identical recompilation."""

        _verify_compiled(self)
        return self

    def verified_snapshot(self) -> ClauseSourceViews:
        """Return a fresh verified view set rebuilt only from captured input bytes."""

        try:
            source_bytes = bytes(self._source_bytes)
            proof_bytes = bytes(self._proof_bytes)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ClauseSourceViewError("view_input_invalid", type(exc).__name__) from exc
        contract_bytes, contract, profile_bytes, profile, profile_sha = (
            _load_fixed_inputs()
        )
        snapshot = _compile_captured(
            source_bytes,
            proof_bytes,
            contract_bytes,
            contract,
            profile_bytes,
            profile,
            profile_sha,
        )
        if type(snapshot) is not ClauseSourceViews or snapshot is self:
            _fail("view_recompile_mismatch", "verified_snapshot")
        return snapshot


def _runtime_sha256() -> str:
    try:
        return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    except OSError as exc:
        raise ClauseSourceViewError("view_runtime_drift", str(exc)) from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Mapping[str, Any], code: str) -> bytes:
    try:
        return ac.serialize_record(value)
    except Exception as exc:
        raise ClauseSourceViewError(code, type(exc).__name__) from exc


def _capture_once(value: object) -> bytes:
    if not isinstance(value, Mapping):
        _fail("view_input_invalid")
    return _canonical_bytes(cast(Mapping[str, Any], value), "view_input_invalid")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("view_input_invalid", key)
        result[key] = value
    return result


def _decode_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail(code),
        )
    except ClauseSourceViewError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ClauseSourceViewError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _read_bytes(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ClauseSourceViewError(code, str(path)) from exc


def _validate_contract(raw: bytes) -> dict[str, Any]:
    if _sha256(raw) != _REGISTERED_CONTRACT_SHA256:
        _fail("view_contract_invalid")
    contract = _decode_object(raw, "view_contract_invalid")
    if (
        contract.get("schema_version") != _VERSION
        or contract.get("contract_id") != _CONTRACT_ID
        or contract.get("status") != "internal_contract_only"
        or contract.get("default_policy") != "deny"
        or contract.get("public_routes") != []
        or contract.get("trust") != _TRUST
        or contract.get("boundary") != _BOUNDARY
        or set(cast(Sequence[str], contract.get("refusal_codes", ()))) != _REFUSAL_CODES
        or contract.get("compiler", {}).get("function")
        != "compile_clause_source_views"
        or contract.get("compiler", {}).get("positional_inputs")
        != ["source_bundle", "role_proof_bundle"]
        or contract.get("compiler", {}).get("caller_semantic_arguments") is not False
        or contract.get("compiler", {}).get("second_source_bundle") is not False
        or contract.get("compiler", {}).get("role_projection_created") is not False
        or contract.get("field_index_rule", {}).get("source_field_denominator") != 24
        or contract.get("field_index_rule", {}).get("multirow_grouping") is not False
        or contract.get("field_index_rule", {}).get("multirow_position_join") is not False
        or contract.get("field_index_rule", {}).get("equal_value_deduplication") is not False
        or contract.get("consumer_policy_rule", {}).get("output_ids") != list(_OUTPUT_IDS)
        or contract.get("consumer_policy_rule", {}).get("consumer_denominator") != 4
        or contract.get("accessor_rule", {}).get("array_index_selector") is not False
        or contract.get("receipt_rule", {}).get("copied_clause_values") is not False
        or contract.get("verification_rule", {}).get("source_release_replay") is not False
    ):
        _fail("view_contract_invalid")
    authorities = contract.get("fixed_authorities")
    expected_paths = {
        "consumer_profile": PROFILE_PATH,
        "consumer_validator": Path(consumer.__file__).resolve(),
        "receipt_schema": RECEIPT_SCHEMA_PATH,
        "adversarial_vectors": ADVERSARIAL_VECTORS_PATH,
    }
    if not isinstance(authorities, dict) or set(authorities) != set(expected_paths):
        _fail("view_contract_invalid")
    for kind, expected_path in expected_paths.items():
        row = authorities.get(kind)
        if not isinstance(row, dict) or row.get("path") != expected_path.relative_to(ROOT).as_posix():
            _fail("view_contract_invalid", kind)
        observed = _sha256(_read_bytes(expected_path, "view_contract_drift"))
        if row.get("file_sha256") != observed:
            _fail("view_contract_drift", kind)
    profile_row = authorities["consumer_profile"]
    if profile_row.get("semantic_projection_sha256") != (
        consumer._REGISTERED_SEMANTIC_PROJECTION_SHA256
    ):
        _fail("view_contract_invalid", "consumer_profile")
    return contract


def _load_fixed_inputs() -> tuple[bytes, dict[str, Any], bytes, dict[str, Any], str]:
    contract_bytes = _read_bytes(CONTRACT_PATH, "view_contract_invalid")
    contract = _validate_contract(contract_bytes)
    profile_bytes = _read_bytes(PROFILE_PATH, "view_contract_drift")
    profile = _decode_object(profile_bytes, "view_contract_drift")
    profile_sha = _sha256(profile_bytes)
    expected_sha = contract["fixed_authorities"]["consumer_profile"]["file_sha256"]
    if profile_sha != expected_sha:
        _fail("view_contract_drift", "consumer_profile")
    if consumer._semantic_projection_sha256(profile) != contract["fixed_authorities"][
        "consumer_profile"
    ]["semantic_projection_sha256"]:
        _fail("view_contract_drift", "consumer_profile_semantic_projection")
    return contract_bytes, contract, profile_bytes, profile, profile_sha


def _release_day(source: Mapping[str, Any]) -> date:
    release = source.get("source_release")
    if not isinstance(release, dict):
        _fail("view_binding_invalid")
    value = release.get("effective_date")
    if not isinstance(value, str):
        _fail("view_binding_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ClauseSourceViewError("view_binding_invalid") from exc
    if parsed.isoformat() != value:
        _fail("view_binding_invalid")
    return parsed


def _validate_incumbent_inputs(
    source: Mapping[str, Any], proof: Mapping[str, Any], profile: Mapping[str, Any]
) -> dict[str, Any]:
    release_day = _release_day(source)
    contract, _ = ac.load_contract()
    try:
        result = consumer.validate_resolution(
            profile, source, consumer.expected_source_binding(source)
        )
    except consumer.EvidenceOutputConsumerContractError as exc:
        code = {
            "consumer_branch_invalid": "view_branch_invalid",
            "consumer_selector_invalid": "view_field_index_invalid",
            "consumer_source_binding_invalid": "view_binding_invalid",
        }.get(exc.code, "view_profile_refused")
        raise ClauseSourceViewError(code, exc.code) from exc
    except ac.AnalyticalClauseError as exc:
        raise ClauseSourceViewError("view_source_refused", exc.code) from exc
    except Exception as exc:
        raise ClauseSourceViewError("view_source_refused", type(exc).__name__) from exc
    if result.get("migration_activated") is not False or result.get(
        "output_equivalence_claimed"
    ) is not False:
        _fail("view_profile_refused")
    try:
        consumer.validate_profile_document(
            profile, release_effective=release_day, source_bundle=source
        )
    except consumer.EvidenceOutputConsumerContractError as exc:
        raise ClauseSourceViewError("view_profile_refused", exc.code) from exc
    try:
        ac.validate_role_proof_bundle(proof, source, contract)
    except Exception as exc:
        detail = exc.code if isinstance(exc, ac.AnalyticalClauseError) else type(exc).__name__
        raise ClauseSourceViewError("view_proof_refused", detail) from exc
    return result


def _validate_query_binding(
    source: Mapping[str, Any], proof: Mapping[str, Any]
) -> None:
    source_release = source.get("source_release")
    source_contract = source.get("contract")
    source_upstream = source.get("upstream")
    query = source.get("query")
    clauses = source.get("clauses")
    if (
        not isinstance(source_release, dict)
        or not isinstance(source_contract, dict)
        or not isinstance(source_upstream, dict)
        or not isinstance(query, dict)
        or set(query) != _QUERY_FIELDS
        or not isinstance(clauses, list)
    ):
        _fail("view_query_invalid")
    try:
        _, source_profile_sha, _, registered_queries = ac.load_source_profile(
            release_effective=_release_day(source)
        )
    except ac.AnalyticalClauseError as exc:
        raise ClauseSourceViewError("view_source_refused", exc.code) from exc
    query_id = query.get("query_id")
    registered = registered_queries.get(query_id) if isinstance(query_id, str) else None
    if registered is None or any(
        query.get(field) != registered.get(field)
        for field in ("event_id", "target_entity_id", "max_hops", "max_paths")
    ):
        _fail("view_query_invalid")
    query_payload = {key: query[key] for key in query if key not in {"query_id", "query_sha256"}}
    query_sha = ac._typed_sha(query_payload)
    expected_proof_query = {**query_payload, "query_sha256": query_sha}
    if (
        query.get("query_sha256") != query_sha
        or source_contract.get("source_profile_sha256") != source_profile_sha
    ):
        _fail("view_query_invalid")
    expected_upstream = {
        key: value for key, value in source_upstream.items() if key != "object_type"
    }
    expected_compiler = {
        "method_id": "method:igrm.analytical_clause_source_binding",
        "implementation_sha256": source_contract.get("analytical_clause_runtime_sha256"),
        "model_authored": False,
        "free_prose": False,
    }
    for clause in clauses:
        binding = clause.get("proof_binding") if isinstance(clause, dict) else None
        if (
            not isinstance(binding, dict)
            or binding.get("query") != expected_proof_query
            or binding.get("source_release_ref") != source_release
            or binding.get("source_profile_sha256") != source_profile_sha
            or binding.get("upstream") != expected_upstream
            or binding.get("compiler") != expected_compiler
        ):
            _fail("view_query_invalid")
    identity = {
        "release_record_sha256": source_release.get("record_sha256"),
        "query_id": query_id,
        "query_sha256": query_sha,
        "profile_sha256": source_profile_sha,
    }
    if source.get("bundle_id") != f"clause-bundle:{ac._typed_sha(identity)[:24]}":
        _fail("view_query_invalid")
    proof_identity = {
        "source_bundle_record_sha256": source.get("record_sha256"),
        "roles": list(_REQUIRED_ROLES),
    }
    if proof.get("proof_bundle_id") != f"clause-proof:{ac._typed_sha(proof_identity)[:24]}":
        _fail("view_proof_refused")


def _clause_ref(clause: Mapping[str, Any]) -> ClauseRef:
    clause_id = clause.get("clause_id")
    digest = clause.get("record_sha256")
    if not isinstance(clause_id, str) or not isinstance(digest, str):
        _fail("view_field_index_invalid")
    return ClauseRef(clause_id, digest)


def _source_ref_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "object_type",
        "object_id",
        "record_sha256",
    }:
        _fail("view_field_index_invalid")
    if any(not isinstance(value[key], str) or not value[key] for key in value):
        _fail("view_field_index_invalid")
    return cast(dict[str, Any], value)


def _multirow_identity(source_field: str, clause: Mapping[str, Any]) -> dict[str, Any]:
    proof = clause.get("proof_binding")
    if not isinstance(proof, dict):
        _fail("view_field_index_invalid")
    refs_value = proof.get("source_object_refs")
    if not isinstance(refs_value, list):
        _fail("view_field_index_invalid")
    refs = [_source_ref_record(ref) for ref in refs_value]
    if source_field.startswith("evidence."):
        if len(refs) != 1 or refs[0]["object_type"] != "evidence_item":
            _fail("view_field_index_invalid")
        if source_field == "evidence.identity" and clause.get("value") != refs[0]:
            _fail("view_field_index_invalid")
        return {"identity_kind": "evidence_item", "source_object_ref": dict(refs[0])}
    if source_field == "provenance.source_object_ref":
        if len(refs) != 1 or clause.get("value") != refs[0]:
            _fail("view_field_index_invalid")
        return {"identity_kind": "source_object", "source_object_ref": dict(refs[0])}
    if source_field == "coverage.row":
        binding = proof.get("coverage_binding")
        if not isinstance(binding, dict) or set(binding) != set(ac._COVERAGE_ROW_FIELDS):
            _fail("view_field_index_invalid")
        return {
            "identity_kind": "coverage_row",
            "universe_release_id": binding["universe_release_id"],
            "covered_entity_id": binding["covered_entity_id"],
            "record_sha256": binding["record_sha256"],
        }
    _fail("view_field_index_invalid", source_field)


def _build_field_index(
    source: Mapping[str, Any], profile: Mapping[str, Any]
) -> Mapping[str, _FieldEntry]:
    clauses = source.get("clauses")
    denominators = source.get("complete_denominators")
    selectors = profile.get("source_field_selectors")
    if not isinstance(clauses, list) or not isinstance(denominators, dict) or not isinstance(
        selectors, list
    ):
        _fail("view_field_index_invalid")
    by_field: dict[str, list[Mapping[str, Any]]] = {}
    for clause in clauses:
        proof = clause.get("proof_binding") if isinstance(clause, dict) else None
        source_field = proof.get("source_field") if isinstance(proof, dict) else None
        if not isinstance(source_field, str):
            _fail("view_field_index_invalid")
        by_field.setdefault(source_field, []).append(cast(Mapping[str, Any], clause))
    entries: dict[str, _FieldEntry] = {}
    evidence_identity_sets: list[set[bytes]] = []
    for selector in selectors:
        if not isinstance(selector, dict) or not isinstance(selector.get("source_field"), str):
            _fail("view_field_index_invalid")
        source_field = cast(str, selector["source_field"])
        cardinality = selector.get("cardinality")
        denominator_key = selector.get("denominator_key")
        value_class = selector.get("value_class")
        nullable = selector.get("nullable_source_missing")
        if (
            source_field in entries
            or cardinality not in {"exactly_one", "exact_bundle_denominator"}
            or not isinstance(value_class, str)
            or not isinstance(nullable, bool)
        ):
            _fail("view_field_index_invalid", source_field)
        expected_count: object = 1
        if cardinality == "exact_bundle_denominator":
            if not isinstance(denominator_key, str):
                _fail("view_field_index_invalid", source_field)
            expected_count = denominators.get(denominator_key)
        elif denominator_key is not None:
            _fail("view_field_index_invalid", source_field)
        if (
            isinstance(expected_count, bool)
            or not isinstance(expected_count, int)
            or expected_count < 0
        ):
            _fail("view_field_index_invalid", source_field)
        selected = sorted(by_field.get(source_field, []), key=lambda row: cast(str, row["clause_id"]))
        refs = tuple(_clause_ref(clause) for clause in selected)
        if len(selected) != expected_count or len(set(refs)) != len(refs):
            _fail("view_field_index_invalid", source_field)
        if cardinality == "exact_bundle_denominator":
            identities = [_multirow_identity(source_field, clause) for clause in selected]
            identity_bytes = {
                _canonical_bytes(identity, "view_field_index_invalid")
                for identity in identities
            }
            if len(identity_bytes) != len(identities):
                _fail("view_field_index_invalid", source_field)
            if source_field.startswith("evidence."):
                evidence_identity_sets.append(identity_bytes)
        clause_bytes = tuple(
            _canonical_bytes(clause, "view_field_index_invalid") for clause in selected
        )
        entries[source_field] = _FieldEntry(
            source_field=source_field,
            cardinality=cast(str, cardinality),
            value_class=value_class,
            denominator_key=denominator_key,
            nullable_source_missing=nullable,
            expected_count=expected_count,
            clause_refs=refs,
            clause_bytes=clause_bytes,
        )
    if len(entries) != 24 or list(entries) != sorted(entries):
        _fail("view_field_index_invalid")
    if evidence_identity_sets and any(
        identities != evidence_identity_sets[0] for identities in evidence_identity_sets[1:]
    ):
        _fail("view_field_index_invalid", "evidence_identity_union")
    return MappingProxyType(entries)


def _single_value(entries: Mapping[str, _FieldEntry], source_field: str) -> Any:
    entry = entries.get(source_field)
    if entry is None or len(entry.clause_bytes) != 1:
        _fail("view_branch_invalid")
    return _decode_object(entry.clause_bytes[0], "view_branch_invalid").get("value")


def _validate_branch(
    source: Mapping[str, Any], entries: Mapping[str, _FieldEntry], branch_id: object
) -> str:
    denominators = source.get("complete_denominators")
    query = source.get("query")
    if not isinstance(denominators, dict) or not isinstance(query, dict):
        _fail("view_branch_invalid")
    status = _single_value(entries, "traversal.status")
    returned = _single_value(entries, "traversal.returned_paths")
    truncated = _single_value(entries, "traversal.truncated")
    max_hops = _single_value(entries, "traversal.max_hops")
    max_paths = _single_value(entries, "traversal.max_paths")
    expected_branch = "branch:path_found" if status == "paths_found" else "branch:no_path"
    if (
        status not in {"paths_found", "no_path"}
        or branch_id != expected_branch
        or isinstance(returned, bool)
        or not isinstance(returned, int)
        or returned != denominators.get("paths")
        or not isinstance(truncated, bool)
        or max_hops != query.get("max_hops")
        or max_paths != query.get("max_paths")
    ):
        _fail("view_branch_invalid")
    if expected_branch == "branch:no_path":
        if (
            returned != 0
            or truncated is not False
            or denominators.get("hops") != 0
            or denominators.get("coverage_rows") != 0
        ):
            _fail("view_branch_invalid")
    elif (
        returned < 1
        or not isinstance(denominators.get("hops"), int)
        or denominators["hops"] < 1
        or not isinstance(denominators.get("coverage_rows"), int)
        or denominators["coverage_rows"] < 1
    ):
        _fail("view_branch_invalid")
    return expected_branch


def _refs_digest(refs: Sequence[ClauseRef]) -> str:
    value = [
        {
            "clause_id": ref.clause_id,
            "clause_record_sha256": ref.clause_record_sha256,
        }
        for ref in refs
    ]
    return ac._typed_sha(value)


def _build_policies(
    profile: Mapping[str, Any],
    entries: Mapping[str, _FieldEntry],
    branch_id: str,
    identity_binding: Mapping[str, Any],
) -> Mapping[str, _ConsumerPolicy]:
    consumers = profile.get("consumers")
    templates_value = profile.get("templates")
    if not isinstance(consumers, list) or not isinstance(templates_value, list):
        _fail("view_consumer_policy_invalid")
    templates = {
        row["template_id"]: row
        for row in templates_value
        if isinstance(row, dict) and isinstance(row.get("template_id"), str)
    }
    policies: dict[str, _ConsumerPolicy] = {}
    all_fields = set(entries)
    for row in consumers:
        if not isinstance(row, dict):
            _fail("view_consumer_policy_invalid")
        output_id = row.get("output_id")
        role_id = row.get("role_id")
        required = row.get("required_source_fields")
        omitted_rows = row.get("omitted_registered_selector_fields")
        template_ids = row.get("template_ids")
        scopes = row.get("limitation_scope_ids")
        gaps = row.get("uncovered_reader_datums")
        if (
            output_id not in _OUTPUT_IDS
            or output_id in policies
            or not isinstance(role_id, str)
            or not isinstance(required, list)
            or not isinstance(omitted_rows, list)
            or not isinstance(template_ids, list)
            or not isinstance(scopes, list)
            or not isinstance(gaps, list)
        ):
            _fail("view_consumer_policy_invalid")
        omitted = [item.get("source_field") for item in omitted_rows if isinstance(item, dict)]
        gap_ids = [item.get("datum_id") for item in gaps if isinstance(item, dict)]
        if (
            any(not isinstance(item, str) for item in [*required, *omitted, *template_ids, *scopes, *gap_ids])
            or set(required) & set(omitted)
            or set(required) | set(omitted) != all_fields
        ):
            _fail("view_consumer_policy_invalid", cast(str, output_id))
        active_templates: list[str] = []
        inactive_templates: list[str] = []
        for template_id in template_ids:
            template = templates.get(template_id)
            if template is None or template.get("consumer_id") != output_id:
                _fail("view_consumer_policy_invalid", cast(str, output_id))
            if template.get("branch_id") in {None, branch_id}:
                active_templates.append(template_id)
            else:
                inactive_templates.append(template_id)
        selected_refs = sorted(
            (ref for field in required for ref in entries[field].clause_refs),
            key=lambda ref: (ref.clause_id, ref.clause_record_sha256),
        )
        if len(set(selected_refs)) != len(selected_refs):
            _fail("view_consumer_policy_invalid", cast(str, output_id))
        selected_digest = _refs_digest(selected_refs)
        view_identity = {
            **identity_binding,
            "output_id": output_id,
            "role_id": role_id,
            "active_branch_id": branch_id,
            "selected_clause_ref_sha256": selected_digest,
        }
        policy = _ConsumerPolicy(
            view_id=f"clause-source-view:{ac._typed_sha(view_identity)[:24]}",
            output_id=cast(str, output_id),
            role_id=role_id,
            active_template_ids=tuple(sorted(active_templates)),
            inactive_template_ids=tuple(sorted(inactive_templates)),
            required_source_fields=frozenset(cast(list[str], required)),
            omitted_source_fields=frozenset(cast(list[str], omitted)),
            limitation_scope_ids=tuple(sorted(cast(list[str], scopes))),
            uncovered_gap_ids=tuple(sorted(cast(list[str], gap_ids))),
            selected_ref_count=len(selected_refs),
            selected_ref_sha256=selected_digest,
        )
        policies[cast(str, output_id)] = policy
    if tuple(sorted(policies)) != _OUTPUT_IDS or len({row.view_id for row in policies.values()}) != 4:
        _fail("view_consumer_policy_invalid")
    return MappingProxyType(policies)


def _ref_record(ref: ClauseRef) -> dict[str, str]:
    return {
        "clause_id": ref.clause_id,
        "clause_record_sha256": ref.clause_record_sha256,
    }


def _build_receipt(
    *,
    source: Mapping[str, Any],
    proof: Mapping[str, Any],
    source_bytes: bytes,
    proof_bytes: bytes,
    profile: Mapping[str, Any],
    profile_sha256: str,
    contract: Mapping[str, Any],
    contract_sha256: str,
    runtime_sha256: str,
    branch_id: str,
    entries: Mapping[str, _FieldEntry],
    policies: Mapping[str, _ConsumerPolicy],
) -> dict[str, Any]:
    source_release = cast(Mapping[str, Any], source["source_release"])
    query = cast(Mapping[str, Any], source["query"])
    source_contract = cast(Mapping[str, Any], source["contract"])
    proof_cross = cast(Mapping[str, Any], proof["cross_role_proof"])
    field_rows = [
        {
            "source_field": field,
            "cardinality": entry.cardinality,
            "denominator_key": entry.denominator_key,
            "clause_ref_denominator": entry.expected_count,
            "clause_refs": [_ref_record(ref) for ref in entry.clause_refs],
        }
        for field, entry in entries.items()
    ]
    policy_rows = [
        {
            "view_id": policy.view_id,
            "output_id": policy.output_id,
            "role_id": policy.role_id,
            "active_template_ids": list(policy.active_template_ids),
            "inactive_template_ids": list(policy.inactive_template_ids),
            "required_source_field_ids": sorted(policy.required_source_fields),
            "omitted_source_field_ids": sorted(policy.omitted_source_fields),
            "limitation_scope_ids": list(policy.limitation_scope_ids),
            "uncovered_gap_ids": list(policy.uncovered_gap_ids),
            "selected_clause_ref_denominator": policy.selected_ref_count,
            "selected_clause_ref_sha256": policy.selected_ref_sha256,
        }
        for _, policy in sorted(policies.items())
    ]
    binding_identity = {
        "source_bundle_record_sha256": source["record_sha256"],
        "role_proof_record_sha256": proof["record_sha256"],
        "consumer_profile_file_sha256": profile_sha256,
        "view_contract_file_sha256": contract_sha256,
        "active_branch_id": branch_id,
        "policy_view_ids": [row["view_id"] for row in policy_rows],
    }
    value = {
        "object_type": "clause_source_view_receipt",
        "schema_version": _VERSION,
        "view_set_id": f"clause-source-views:{ac._typed_sha(binding_identity)[:24]}",
        "record_sha256": "0" * 64,
        "bindings": {
            "source_bundle_ref": {
                "bundle_id": source["bundle_id"],
                "record_sha256": source["record_sha256"],
                "captured_bytes_sha256": _sha256(source_bytes),
            },
            "role_proof_bundle_ref": {
                "proof_bundle_id": proof["proof_bundle_id"],
                "record_sha256": proof["record_sha256"],
                "captured_bytes_sha256": _sha256(proof_bytes),
            },
            "consumer_profile_ref": {
                "profile_id": profile["profile_id"],
                "file_sha256": profile_sha256,
                "semantic_projection_sha256": consumer._semantic_projection_sha256(profile),
            },
            "clause_contract_ref": {
                "contract_id": source_contract["clause_contract_id"],
                "file_sha256": source_contract["clause_contract_sha256"],
            },
            "view_contract_ref": {
                "contract_id": contract["contract_id"],
                "file_sha256": contract_sha256,
            },
            "view_runtime_ref": {"implementation_sha256": runtime_sha256},
            "release_ref": {
                "release_id": source_release["release_id"],
                "record_sha256": source_release["record_sha256"],
            },
            "query_ref": {
                "query_id": query["query_id"],
                "query_sha256": query["query_sha256"],
            },
        },
        "active_branch_id": branch_id,
        "field_index": field_rows,
        "consumer_policies": policy_rows,
        "denominators": {
            "source_complete_denominators": dict(source["complete_denominators"]),
            "source_clause_denominator": source["complete_denominators"]["clauses"],
            "indexed_source_field_denominator": len(entries),
            "indexed_clause_ref_denominator": sum(
                entry.expected_count for entry in entries.values()
            ),
            "role_denominator": proof["complete_role_denominator"],
            "role_pair_denominator": proof_cross["role_pair_denominator"],
            "consumer_policy_denominator": len(policies),
        },
        "trust": dict(_TRUST),
        "boundary": dict(_BOUNDARY),
    }
    return ac._seal(value)


def _validate_receipt(receipt: Mapping[str, Any]) -> None:
    schema_raw = _read_bytes(RECEIPT_SCHEMA_PATH, "view_contract_drift")
    schema = _decode_object(schema_raw, "view_contract_drift")
    try:
        Draft202012Validator(schema).validate(dict(receipt))
        ac._verify_digest(receipt, "view_receipt_invalid")
    except Exception as exc:
        detail = exc.code if isinstance(exc, ac.AnalyticalClauseError) else type(exc).__name__
        raise ClauseSourceViewError("view_receipt_invalid", detail) from exc


def _resolve_clause(entry: _FieldEntry, index: int) -> ClauseValue[Any]:
    raw = entry.clause_bytes[index]
    clause = _decode_object(raw, "view_field_index_invalid")
    proof = clause.get("proof_binding")
    if not isinstance(proof, dict) or proof.get("source_field") != entry.source_field:
        _fail("view_field_index_invalid", entry.source_field)
    refs_value = proof.get("source_object_refs")
    if not isinstance(refs_value, list):
        _fail("view_field_index_invalid", entry.source_field)
    refs = tuple(dict(_source_ref_record(ref)) for ref in refs_value)
    identity = (
        _multirow_identity(entry.source_field, clause)
        if entry.cardinality == "exact_bundle_denominator"
        else None
    )
    return ClauseValue(
        clause_ref=entry.clause_refs[index],
        source_field=entry.source_field,
        value_class=entry.value_class,
        value=clause.get("value"),
        missingness=cast(str, clause.get("missingness")),
        denominator=clause.get("denominator"),
        source_object_refs=refs,
        source_identity_key=identity,
    )


def _compile_captured(
    source_bytes: bytes,
    proof_bytes: bytes,
    contract_bytes: bytes,
    contract: Mapping[str, Any],
    profile_bytes: bytes,
    profile: Mapping[str, Any],
    profile_sha256: str,
) -> ClauseSourceViews:
    source = _decode_object(source_bytes, "view_input_invalid")
    proof = _decode_object(proof_bytes, "view_input_invalid")
    if (
        _canonical_bytes(source, "view_input_invalid") != source_bytes
        or _canonical_bytes(proof, "view_input_invalid") != proof_bytes
    ):
        _fail("view_input_invalid")
    resolution = _validate_incumbent_inputs(source, proof, profile)
    _validate_query_binding(source, proof)
    entries = _build_field_index(source, profile)
    branch_id = _validate_branch(source, entries, resolution.get("active_branch_id"))
    runtime_sha = _runtime_sha256()
    identity_binding = {
        "source_bundle_record_sha256": source["record_sha256"],
        "role_proof_record_sha256": proof["record_sha256"],
        "consumer_profile_file_sha256": profile_sha256,
    }
    policies = _build_policies(profile, entries, branch_id, identity_binding)
    receipt = _build_receipt(
        source=source,
        proof=proof,
        source_bytes=source_bytes,
        proof_bytes=proof_bytes,
        profile=profile,
        profile_sha256=profile_sha256,
        contract=contract,
        contract_sha256=_sha256(contract_bytes),
        runtime_sha256=runtime_sha,
        branch_id=branch_id,
        entries=entries,
        policies=policies,
    )
    _validate_receipt(receipt)
    receipt_bytes = _canonical_bytes(receipt, "view_receipt_invalid")
    return ClauseSourceViews(
        _construction_token=_CONSTRUCTION_TOKEN,
        entries=entries,
        policies=policies,
        source_bytes=source_bytes,
        proof_bytes=proof_bytes,
        profile_bytes=profile_bytes,
        contract_bytes=contract_bytes,
        receipt_bytes=receipt_bytes,
        runtime_sha256=runtime_sha,
    )


def _verify_compiled(compiled: ClauseSourceViews) -> None:
    if _runtime_sha256() != compiled._runtime_sha256:
        _fail("view_runtime_drift")
    exposed = {
        "board": "output:board_brief",
        "newsroom": "output:newsroom_claim_card",
        "offline": "output:offline_audit_bundle",
        "research": "output:research_package",
    }
    for attribute, output_id in exposed.items():
        handle = getattr(compiled, attribute)
        policy = compiled._policies.get(output_id)
        if (
            not isinstance(handle, _ConsumerClauseSourceView)
            or policy is None
            or handle._entries is not compiled._entries
            or handle._policy != policy
            or handle.output_id != output_id
            or handle.role_id != policy.role_id
            or handle.view_id != policy.view_id
        ):
            _fail("view_recompile_mismatch", attribute)
    contract_bytes, contract, profile_bytes, profile, profile_sha = _load_fixed_inputs()
    if contract_bytes != compiled._contract_bytes or profile_bytes != compiled._profile_bytes:
        _fail("view_contract_drift")
    receipt = _decode_object(compiled._receipt_bytes, "view_receipt_invalid")
    _validate_receipt(receipt)
    candidate = _compile_captured(
        compiled._source_bytes,
        compiled._proof_bytes,
        contract_bytes,
        contract,
        profile_bytes,
        profile,
        profile_sha,
    )
    if (
        candidate._source_bytes != compiled._source_bytes
        or candidate._proof_bytes != compiled._proof_bytes
        or candidate._receipt_bytes != compiled._receipt_bytes
        or candidate._entries != compiled._entries
        or candidate._policies != compiled._policies
    ):
        _fail("view_recompile_mismatch")
    for attribute, output_id in exposed.items():
        observed = getattr(compiled, attribute)
        expected = getattr(candidate, attribute)
        if (
            observed.output_id != expected.output_id
            or observed.role_id != expected.role_id
            or observed.view_id != expected.view_id
            or observed._policy != expected._policy
            or observed._entries != expected._entries
            or observed.output_id != output_id
        ):
            _fail("view_recompile_mismatch", attribute)


def compile_clause_source_views(
    source_bundle: Mapping[str, Any], role_proof_bundle: Mapping[str, Any]
) -> ClauseSourceViews:
    """Compile the four fixed access policies from exactly two captured inputs."""

    source_bytes = _capture_once(source_bundle)
    proof_bytes = _capture_once(role_proof_bundle)
    contract_bytes, contract, profile_bytes, profile, profile_sha = _load_fixed_inputs()
    return _compile_captured(
        source_bytes,
        proof_bytes,
        contract_bytes,
        contract,
        profile_bytes,
        profile,
        profile_sha,
    )


__all__ = [
    "ClauseRef",
    "ClauseSourceViewError",
    "ClauseSourceViews",
    "ClauseValue",
    "compile_clause_source_views",
]
