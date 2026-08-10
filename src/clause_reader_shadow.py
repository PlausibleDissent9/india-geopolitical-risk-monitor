"""Compile three internal reader shadows from fixed role-scoped clause handles.

The compiler has one input and no caller-selected semantics.  It verifies the
captured view set once, reads a closed set of pinned governance files, then
renders research, board and newsroom documents independently from their own
role handles.  The result is internal, synthetic, unsigned and nonpublic.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn, Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .clause_source_view import ClauseSourceViewError, ClauseSourceViews, ClauseValue

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "clause_reader_shadow_contract.json"
TEMPLATE_PROFILE_PATH = ROOT / "governance" / "clause_reader_template_profile.json"
LIMITATION_REGISTRY_PATH = (
    ROOT / "governance" / "analytical_clause_limitation_registry.json"
)
PUBLIC_SCHEMA_PATH = ROOT / "schemas" / "evidence-output-set.schema.json"
PUBLIC_COMMON_SCHEMA_PATH = ROOT / "schemas" / "common.schema.json"
RECEIPT_SCHEMA_PATH = (
    ROOT / "governance" / "schemas" / "clause-reader-compilation-receipt.schema.json"
)
ADVERSARIAL_VECTORS_PATH = (
    ROOT / "governance" / "clause_reader_shadow_adversarial_vectors.json"
)
VIEW_CONTRACT_PATH = ROOT / "governance" / "clause_source_view_contract.json"
VIEW_RUNTIME_PATH = ROOT / "src" / "clause_source_view.py"
CONSUMER_PROFILE_PATH = (
    ROOT / "governance" / "evidence_output_renderer_consumer_profile.json"
)
CONSUMER_VALIDATOR_PATH = ROOT / "src" / "evidence_output_consumer_contract.py"

_VERSION = "0.1.0"
_CONTRACT_ID = "igrm:clause-reader-shadow:0.1.0"
_REGISTERED_CONTRACT_SHA256 = (
    "c7a2b4bdb9aad312a43f23059dc9446b3e67de72edccd2d3ddecf259d8f21333"
)
_REGISTERED_TEMPLATE_SEMANTIC_PROJECTION_SHA256 = (
    "5124eb47b7669b60f864246f9c6164def3003bdc0616268d7eab5be13382b2d7"
)
_CONSTRUCTION_TOKEN = object()
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATE_TEXT = re.compile(r"(?:^|[^0-9])\d{4}-\d{2}-\d{2}(?:[^0-9]|$)")

_OUTPUT_ROLES: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "board": ("output:board_brief", "board"),
        "newsroom": ("output:newsroom_claim_card", "newsroom"),
        "research": ("output:research_package", "research"),
    }
)
_PUBLIC_OUTPUT_SCHEMA_DEFS: Mapping[str, str] = MappingProxyType(
    {
        "output:board_brief": "boardBrief",
        "output:newsroom_claim_card": "claimCard",
        "output:research_package": "researchPackage",
    }
)
_MANY_FIELDS = frozenset(
    {
        "coverage.row",
        "evidence.content_availability",
        "evidence.identity",
        "evidence.observed_at",
        "evidence.public_url",
        "evidence.published_at",
        "evidence.rights_use",
        "evidence.source_id",
        "evidence.title",
        "evidence.verification_status",
        "provenance.source_object_ref",
    }
)
_NULLABLE_FIELDS = frozenset({"evidence.public_url", "evidence.published_at"})
_VALUE_TYPES: Mapping[str, str] = MappingProxyType(
    {
        "coverage.row": "object",
        "event.canonical_label": "text",
        "event.class": "identifier",
        "event.last_verified_at": "datetime",
        "event.record_status": "identifier",
        "event.starts_at": "datetime",
        "evidence.content_availability": "identifier",
        "evidence.identity": "object",
        "evidence.observed_at": "datetime",
        "evidence.public_url": "citation_metadata",
        "evidence.published_at": "datetime",
        "evidence.rights_use": "identifier",
        "evidence.source_id": "identifier",
        "evidence.title": "citation_metadata",
        "evidence.verification_status": "identifier",
        "provenance.source_object_ref": "object",
        "release.generated_at": "datetime",
        "target.canonical_name": "text",
        "target.identity": "object",
        "traversal.max_hops": "integer",
        "traversal.max_paths": "integer",
        "traversal.returned_paths": "integer",
        "traversal.status": "identifier",
        "traversal.truncated": "boolean",
    }
)
_OPERATOR_SIGNATURES: Mapping[str, tuple[str, str]] = MappingProxyType(
    {
        "operator:artifact.json.v1": ("object", "artifact_descriptor"),
        "operator:artifact.stem.v1": ("source_ref_tuple", "identifier"),
        "operator:branch.exactly_one.v1": ("traversal_status", "branch_id"),
        "operator:evidence.identity_join.v1": (
            "evidence_clause_sets",
            "evidence_rows",
        ),
        "operator:limitation.scope.v1": (
            "limitation_scope_id",
            "identifier_list",
        ),
        "operator:object_ref.source.v1": ("clause_source_ref", "object_ref"),
        "operator:object_ref.union.v1": ("object_ref_sets", "object_ref_list"),
        "operator:token.literal.v1": ("registered_literal", "text"),
        "operator:token.slot.v1": ("registered_typed_slot", "text"),
    }
)
_SLOT_SIGNATURES: Mapping[str, tuple[str, str, str | None]] = MappingProxyType(
    {
        "slot:event.canonical_label": ("event.canonical_label", "text", None),
        "slot:event.class": ("event.class", "identifier", None),
        "slot:event.last_verified_at": (
            "event.last_verified_at",
            "datetime",
            None,
        ),
        "slot:event.object_id": (
            "event.canonical_label",
            "identifier",
            "operator:object_ref.source.v1",
        ),
        "slot:event.record_status": ("event.record_status", "identifier", None),
        "slot:event.starts_at": ("event.starts_at", "datetime", None),
        "slot:release.generated_at": ("release.generated_at", "datetime", None),
        "slot:release.object_id": (
            "release.generated_at",
            "identifier",
            "operator:object_ref.source.v1",
        ),
        "slot:release.record_sha256": (
            "release.generated_at",
            "sha256",
            "operator:object_ref.source.v1",
        ),
        "slot:target.canonical_name": ("target.canonical_name", "text", None),
        "slot:target.object_id": (
            "target.identity_or_canonical_name",
            "identifier",
            "operator:object_ref.source.v1",
        ),
        "slot:traversal.max_hops": ("traversal.max_hops", "integer", None),
        "slot:traversal.returned_paths": (
            "traversal.returned_paths",
            "integer",
            None,
        ),
    }
)
_TEMPLATE_IDS = frozenset(
    {
        "template:board.brief.shell.v1",
        "template:board.decision.boundary.v1",
        "template:board.event.record.v1",
        "template:board.linkage.no_path.v1",
        "template:board.linkage.path_found.v1",
        "template:newsroom.card.shell.v1",
        "template:newsroom.event.record.v1",
        "template:newsroom.release_structure.no_path.v1",
        "template:newsroom.release_structure.path_found.v1",
        "template:research.package.shell.v1",
    }
)
_REFUSAL_CODES = frozenset(
    {
        "reader_artifact_invalid",
        "reader_branch_invalid",
        "reader_clause_invalid",
        "reader_contract_drift",
        "reader_contract_invalid",
        "reader_governance_drift",
        "reader_handle_invalid",
        "reader_identity_join_invalid",
        "reader_input_invalid",
        "reader_limitation_invalid",
        "reader_receipt_invalid",
        "reader_recompile_mismatch",
        "reader_runtime_drift",
        "reader_template_invalid",
        "reader_value_leakage",
    }
)
_TRUST: Mapping[str, Any] = MappingProxyType(
    {
        "synthetic": True,
        "self_hash_integrity_only": True,
        "signed": False,
        "authenticated": False,
        "nonpublic": True,
        "nonproduction": True,
        "offline": False,
        "product_manifest": False,
    }
)
_BOUNDARY: Mapping[str, Any] = MappingProxyType(
    {
        "shadow_only": True,
        "public_behavior_changed": False,
        "publication_approved": False,
        "comparison_performed": False,
        "comparison_result": "not_performed",
        "standalone_activation_requires_common_scope_wrapper": True,
        "general_equivalence_claimed": False,
        "prose_equivalence_claimed": False,
        "public_authority": False,
        "production_authority": False,
        "offline_bundle_created": False,
        "product_manifest_created": False,
    }
)


class ClauseReaderShadowError(ValueError):
    """Stable fail-closed refusal from the internal reader shadow."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ClauseReaderShadowError(code, detail)


class _RoleHandle(Protocol):
    @property
    def view_id(self) -> str: ...

    @property
    def output_id(self) -> str: ...

    @property
    def role_id(self) -> str: ...

    @property
    def active_template_ids(self) -> tuple[str, ...]: ...

    @property
    def inactive_template_ids(self) -> tuple[str, ...]: ...

    def one(self, source_field: str) -> ClauseValue[Any]: ...

    def many(self, source_field: str) -> tuple[ClauseValue[Any], ...]: ...


@dataclass(frozen=True)
class _FixedInputs:
    contract_bytes: bytes
    contract: Mapping[str, Any]
    template_bytes: bytes
    template: Mapping[str, Any]
    limitation_bytes: bytes
    limitations: Mapping[str, Any]
    public_common_schema_bytes: bytes
    public_common_schema: Mapping[str, Any]
    public_schema_bytes: bytes
    public_schema: Mapping[str, Any]
    public_output_validators: Mapping[str, Draft202012Validator]
    receipt_schema_bytes: bytes
    receipt_schema: Mapping[str, Any]
    vectors_bytes: bytes
    view_contract_bytes: bytes
    view_runtime_bytes: bytes
    consumer_profile_bytes: bytes
    consumer_validator_bytes: bytes

    def captured_bytes(self) -> tuple[bytes, ...]:
        return (
            self.contract_bytes,
            self.template_bytes,
            self.limitation_bytes,
            self.public_common_schema_bytes,
            self.public_schema_bytes,
            self.receipt_schema_bytes,
            self.vectors_bytes,
            self.view_contract_bytes,
            self.view_runtime_bytes,
            self.consumer_profile_bytes,
            self.consumer_validator_bytes,
        )


@dataclass(frozen=True)
class _RoleCompilation:
    output_id: str
    role_id: str
    view_id: str
    document: dict[str, Any]
    document_bytes: bytes
    body_bytes: bytes
    artifact_bytes: bytes
    active_template_ids: tuple[str, ...]
    consumed_fields: tuple[str, ...]
    clause_refs: tuple[dict[str, str], ...]
    operator_ids: tuple[str, ...]
    rendered_limitation_scope_ids: tuple[str, ...]
    applicable_but_outer_wrapper_absent_scope_ids: tuple[str, ...]
    evidence_count: int
    coverage_count: int
    object_evidence_count: int


class ClauseReaderCompilation:
    """Immutable factory-only capture of three documents and a value-free receipt."""

    __slots__ = (
        "_snapshot",
        "_fixed_bytes",
        "_runtime_sha256",
        "_research_bytes",
        "_research_artifact_bytes",
        "_board_bytes",
        "_board_artifact_bytes",
        "_newsroom_bytes",
        "_newsroom_artifact_bytes",
        "_receipt_bytes",
    )
    _snapshot: ClauseSourceViews
    _fixed_bytes: tuple[bytes, ...]
    _runtime_sha256: str
    _research_bytes: bytes
    _research_artifact_bytes: bytes
    _board_bytes: bytes
    _board_artifact_bytes: bytes
    _newsroom_bytes: bytes
    _newsroom_artifact_bytes: bytes
    _receipt_bytes: bytes

    def __init__(
        self,
        *,
        _construction_token: object,
        snapshot: ClauseSourceViews,
        fixed_bytes: tuple[bytes, ...],
        runtime_sha256: str,
        research_bytes: bytes,
        research_artifact_bytes: bytes,
        board_bytes: bytes,
        board_artifact_bytes: bytes,
        newsroom_bytes: bytes,
        newsroom_artifact_bytes: bytes,
        receipt_bytes: bytes,
    ) -> None:
        if _construction_token is not _CONSTRUCTION_TOKEN:
            raise TypeError("clause reader compilations are factory-only")
        object.__setattr__(self, "_snapshot", snapshot)
        object.__setattr__(self, "_fixed_bytes", fixed_bytes)
        object.__setattr__(self, "_runtime_sha256", runtime_sha256)
        object.__setattr__(self, "_research_bytes", research_bytes)
        object.__setattr__(self, "_research_artifact_bytes", research_artifact_bytes)
        object.__setattr__(self, "_board_bytes", board_bytes)
        object.__setattr__(self, "_board_artifact_bytes", board_artifact_bytes)
        object.__setattr__(self, "_newsroom_bytes", newsroom_bytes)
        object.__setattr__(self, "_newsroom_artifact_bytes", newsroom_artifact_bytes)
        object.__setattr__(self, "_receipt_bytes", receipt_bytes)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("clause reader compilations are immutable")

    @property
    def research_package(self) -> dict[str, Any]:
        return _decode_object(self._research_bytes, "reader_recompile_mismatch")

    @property
    def board_brief(self) -> dict[str, Any]:
        return _decode_object(self._board_bytes, "reader_recompile_mismatch")

    @property
    def newsroom_claim_card(self) -> dict[str, Any]:
        return _decode_object(self._newsroom_bytes, "reader_recompile_mismatch")

    @property
    def receipt(self) -> dict[str, Any]:
        return _decode_object(self._receipt_bytes, "reader_receipt_invalid")

    def verify(self) -> ClauseReaderCompilation:
        """Recompile the captured view against the unchanged fixed governance bytes."""

        _verify_compilation(self)
        return self


def _runtime_sha256() -> str:
    try:
        return hashlib.sha256(Path(__file__).resolve().read_bytes()).hexdigest()
    except OSError as exc:
        raise ClauseReaderShadowError("reader_runtime_drift", str(exc)) from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _decode_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("constant")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClauseReaderShadowError(code, type(exc).__name__) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _canonical_bytes(value: object, code: str) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClauseReaderShadowError(code, type(exc).__name__) from exc


def _artifact_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClauseReaderShadowError("reader_artifact_invalid", type(exc).__name__) from exc


def _record_sha256(value: Mapping[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("record_sha256", None)
    return _sha(_canonical_bytes(unsigned, "reader_receipt_invalid"))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["record_sha256"] = _record_sha256(sealed)
    return sealed


def _read_bytes(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ClauseReaderShadowError(code, str(path)) from exc


def _template_semantic_projection_sha256(profile: Mapping[str, Any]) -> str:
    fields = (
        "rendering_rule",
        "operators",
        "slots",
        "fixed_values",
        "templates",
        "branches",
        "limitation_registry",
        "boundary",
    )
    return _sha(
        _canonical_bytes(
            {field: profile.get(field) for field in fields},
            "reader_template_invalid",
        )
    )


def _closed_strings(value: object, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or any(not isinstance(item, str) or not item for item in value)
        or value != sorted(set(value))
    ):
        _fail(code)
    return cast(list[str], value)


def _validate_template_profile(profile: Mapping[str, Any]) -> None:
    if (
        set(profile)
        != {
            "schema_version",
            "profile_id",
            "effective",
            "status",
            "default_policy",
            "rendering_rule",
            "operators",
            "slots",
            "fixed_values",
            "templates",
            "branches",
            "limitation_registry",
            "boundary",
        }
        or profile.get("schema_version") != _VERSION
        or profile.get("profile_id")
        != "igrm:clause-reader-template-profile:0.1.0"
        or profile.get("status") != "internal_shadow_only"
        or profile.get("default_policy") != "deny"
        or profile.get("rendering_rule")
        != "closed_literal_and_typed_slot_token_stream_no_free_prose"
        or _template_semantic_projection_sha256(profile)
        != _REGISTERED_TEMPLATE_SEMANTIC_PROJECTION_SHA256
    ):
        _fail("reader_template_invalid")

    operators = profile.get("operators")
    if not isinstance(operators, list):
        _fail("reader_template_invalid")
    observed_operators: dict[str, tuple[str, str]] = {}
    for row in operators:
        if (
            not isinstance(row, dict)
            or set(row) != {"operator_id", "input_type", "output_type"}
            or not isinstance(row.get("operator_id"), str)
            or row["operator_id"] in observed_operators
        ):
            _fail("reader_template_invalid")
        observed_operators[row["operator_id"]] = (
            cast(str, row.get("input_type")),
            cast(str, row.get("output_type")),
        )
    if observed_operators != dict(_OPERATOR_SIGNATURES):
        _fail("reader_template_invalid")

    slots = profile.get("slots")
    if not isinstance(slots, list):
        _fail("reader_template_invalid")
    observed_slots: dict[str, tuple[str, str, str | None]] = {}
    for row in slots:
        if not isinstance(row, dict) or set(row) not in (
            {"slot_id", "source_field", "value_type"},
            {"slot_id", "source_field", "value_type", "operator_id"},
        ):
            _fail("reader_template_invalid")
        slot_id = row.get("slot_id")
        if not isinstance(slot_id, str) or slot_id in observed_slots:
            _fail("reader_template_invalid")
        operator_id = row.get("operator_id")
        if operator_id is not None and operator_id not in _OPERATOR_SIGNATURES:
            _fail("reader_template_invalid")
        observed_slots[slot_id] = (
            cast(str, row.get("source_field")),
            cast(str, row.get("value_type")),
            operator_id if isinstance(operator_id, str) else None,
        )
    if observed_slots != dict(_SLOT_SIGNATURES):
        _fail("reader_template_invalid")

    fixed = profile.get("fixed_values")
    if not isinstance(fixed, list):
        _fail("reader_template_invalid")
    fixed_ids: list[str] = []
    for row in fixed:
        if (
            not isinstance(row, dict)
            or set(row) != {"value_id", "value_type", "value"}
            or row.get("value_type") not in {"fixed_identifier", "fixed_nonfactual_text"}
            or not isinstance(row.get("value_id"), str)
            or not isinstance(row.get("value"), str)
            or not row["value"]
        ):
            _fail("reader_template_invalid")
        fixed_ids.append(row["value_id"])
    if fixed_ids != sorted(set(fixed_ids)):
        _fail("reader_template_invalid")

    templates_value = profile.get("templates")
    if not isinstance(templates_value, list):
        _fail("reader_template_invalid")
    templates: dict[str, Mapping[str, Any]] = {}
    for row in templates_value:
        if (
            not isinstance(row, dict)
            or set(row)
            != {
                "template_id",
                "output_id",
                "branch_id",
                "consumed_source_fields",
                "rendered_limitation_scope_ids",
                "applicable_but_outer_wrapper_absent_scope_ids",
                "operator_ids",
                "rendered_strings",
            }
            or not isinstance(row.get("template_id"), str)
            or row["template_id"] in templates
            or row.get("output_id")
            not in {value[0] for value in _OUTPUT_ROLES.values()}
            or row.get("branch_id") not in {None, "branch:no_path", "branch:path_found"}
        ):
            _fail("reader_template_invalid")
        consumed = _closed_strings(row.get("consumed_source_fields"), "reader_template_invalid")
        rendered_scopes = _closed_strings(
            row.get("rendered_limitation_scope_ids"), "reader_template_invalid"
        )
        absent_scopes = _closed_strings(
            row.get("applicable_but_outer_wrapper_absent_scope_ids"),
            "reader_template_invalid",
        )
        operator_ids = _closed_strings(row.get("operator_ids"), "reader_template_invalid")
        if (
            not set(consumed) <= set(_VALUE_TYPES)
            or not set(operator_ids) <= set(_OPERATOR_SIGNATURES)
            or set(rendered_scopes) & set(absent_scopes)
            or "scope:output.all_views" in rendered_scopes
            or not set(absent_scopes) <= {"scope:output.all_views"}
            or (
                "operator:limitation.scope.v1" in operator_ids
            )
            is not bool(rendered_scopes)
        ):
            _fail("reader_template_invalid")
        rendered = row.get("rendered_strings")
        if not isinstance(rendered, list) or not rendered:
            _fail("reader_template_invalid")
        field_ids: list[str] = []
        for rendered_row in rendered:
            if (
                not isinstance(rendered_row, dict)
                or set(rendered_row) != {"field_id", "tokens"}
                or not isinstance(rendered_row.get("field_id"), str)
                or not isinstance(rendered_row.get("tokens"), list)
                or not rendered_row["tokens"]
            ):
                _fail("reader_template_invalid")
            field_ids.append(rendered_row["field_id"])
            for token in rendered_row["tokens"]:
                if not isinstance(token, dict) or token.get("kind") not in {
                    "literal",
                    "slot",
                }:
                    _fail("reader_template_invalid")
                if token["kind"] == "literal":
                    if (
                        set(token) != {"kind", "value"}
                        or not isinstance(token.get("value"), str)
                        or "{" in token["value"]
                        or "}" in token["value"]
                    ):
                        _fail("reader_template_invalid")
                elif (
                    set(token) != {"kind", "slot_id"}
                    or token.get("slot_id") not in _SLOT_SIGNATURES
                ):
                    _fail("reader_template_invalid")
        if len(field_ids) != len(set(field_ids)):
            _fail("reader_template_invalid")
        templates[row["template_id"]] = row
    if set(templates) != _TEMPLATE_IDS or list(templates) != sorted(templates):
        _fail("reader_template_invalid")

    branches_value = profile.get("branches")
    if not isinstance(branches_value, list):
        _fail("reader_branch_invalid")
    branches: dict[str, Mapping[str, Any]] = {}
    for row in branches_value:
        if (
            not isinstance(row, dict)
            or set(row) != {"branch_id", "predicate", "active_template_ids"}
            or row.get("branch_id") not in {"branch:no_path", "branch:path_found"}
            or row["branch_id"] in branches
        ):
            _fail("reader_branch_invalid")
        expected_status = "no_path" if row["branch_id"] == "branch:no_path" else "paths_found"
        if row.get("predicate") != {
            "source_field": "traversal.status",
            "operator_id": "operator:branch.exactly_one.v1",
            "value": expected_status,
        }:
            _fail("reader_branch_invalid")
        active = _closed_strings(row.get("active_template_ids"), "reader_branch_invalid")
        expected = sorted(
            template_id
            for template_id, template in templates.items()
            if template["branch_id"] in {None, row["branch_id"]}
        )
        if active != expected:
            _fail("reader_branch_invalid")
        branches[row["branch_id"]] = row
    if set(branches) != {"branch:no_path", "branch:path_found"}:
        _fail("reader_branch_invalid")

    if profile.get("limitation_registry") != {
        "path": "governance/analytical_clause_limitation_registry.json",
        "selection": "exact_pinned_output_profile_scope_only",
        "duplicate_literal_lists": False,
    } or profile.get("boundary") != {
        "comparison_performed": False,
        "comparison_result": "not_performed",
        "standalone_activation_requires_common_scope_wrapper": True,
        "general_equivalence_claimed": False,
        "offline_output_created": False,
        "public_activation": False,
        "model_call": False,
        "free_prose": False,
    }:
        _fail("reader_template_invalid")


def _validate_limitations(registry: Mapping[str, Any]) -> None:
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
        or registry.get("schema_version") != "0.1.0"
        or registry.get("registry_id")
        != "igrm:analytical-clause-limitations:0.1.0"
        or registry.get("default_policy") != "deny"
    ):
        _fail("reader_limitation_invalid")
    allowed = set(_closed_strings(registry.get("allowed_ids"), "reader_limitation_invalid"))
    profiles = registry.get("output_profiles")
    scopes = registry.get("limitation_scopes")
    if not isinstance(profiles, dict) or not isinstance(scopes, dict):
        _fail("reader_limitation_invalid")
    required_scopes = {
        "scope:output.research_package",
        "scope:output.board_brief",
        "scope:output.newsroom_claim_card",
        "scope:claim.card.event_record",
        "scope:claim.card.release_structure",
    }
    if not required_scopes <= set(profiles):
        _fail("reader_limitation_invalid")
    for scope_id, value in profiles.items():
        identifiers = _closed_strings(value, "reader_limitation_invalid")
        if not set(identifiers) <= allowed:
            _fail("reader_limitation_invalid", cast(str, scope_id))
        for identifier in identifiers:
            registered_scopes = scopes.get(identifier)
            if not isinstance(registered_scopes, list) or scope_id not in registered_scopes:
                _fail("reader_limitation_invalid", identifier)
    for identifier, registered_scopes in scopes.items():
        if identifier not in allowed or not isinstance(registered_scopes, list):
            _fail("reader_limitation_invalid", cast(str, identifier))
        for scope_id in registered_scopes:
            inverse_ids = profiles.get(scope_id)
            if not isinstance(inverse_ids, list) or identifier not in inverse_ids:
                _fail("reader_limitation_invalid", cast(str, identifier))


def _validate_contract(contract: Mapping[str, Any]) -> None:
    if (
        contract.get("schema_version") != _VERSION
        or contract.get("contract_id") != _CONTRACT_ID
        or contract.get("status") != "internal_shadow_only"
        or contract.get("default_policy") != "deny"
        or contract.get("public_routes") != []
        or contract.get("compiler")
        != {
            "function": "compile_clause_reader_shadow",
            "positional_inputs": ["views"],
            "input_type": "ClauseSourceViews",
            "output_type": "ClauseReaderCompilation",
            "caller_semantic_arguments": False,
            "query_output_template_path_or_caller_selectors": False,
            "consumer_outputs": [
                "output:board_brief",
                "output:newsroom_claim_card",
                "output:research_package",
            ],
            "offline_output": False,
        }
        or set(contract.get("refusal_codes", ())) != _REFUSAL_CODES
    ):
        _fail("reader_contract_invalid")
    authorities = contract.get("fixed_authorities")
    if not isinstance(authorities, dict) or set(authorities) != {
        "consumer_profile",
        "consumer_validator",
        "limitation_registry",
        "public_common_schema",
        "public_output_schema",
        "receipt_schema",
        "template_profile",
        "view_contract",
        "view_runtime",
        "adversarial_vectors",
    }:
        _fail("reader_contract_invalid")
    if contract.get("trust") != dict(_TRUST):
        _fail("reader_contract_invalid")
    boundary = contract.get("boundary")
    if not isinstance(boundary, dict) or any(
        boundary.get(key) is not value
        for key, value in {
            "shadow_only": True,
            "public_behavior_changed": False,
            "publication_approved": False,
            "comparison_performed": False,
            "standalone_activation_requires_common_scope_wrapper": True,
            "general_equivalence_claimed": False,
            "prose_equivalence_claimed": False,
            "public_authority": False,
            "production_authority": False,
            "offline_bundle_created": False,
            "product_manifest_created": False,
        }.items()
    ) or boundary.get("comparison_result") != "not_performed":
        _fail("reader_contract_invalid")


def _authority_sha(contract: Mapping[str, Any], name: str) -> str:
    authorities = contract.get("fixed_authorities")
    row = authorities.get(name) if isinstance(authorities, dict) else None
    digest = row.get("file_sha256") if isinstance(row, dict) else None
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        _fail("reader_contract_invalid", name)
    return digest


def _build_public_output_validators(
    common: Mapping[str, Any], schema: Mapping[str, Any]
) -> Mapping[str, Draft202012Validator]:
    common_id = common.get("$id")
    schema_id = schema.get("$id")
    if (
        common_id != "https://igrm.in/schemas/common.schema.json"
        or schema_id != "https://igrm.in/schemas/evidence-output-set.schema.json"
    ):
        _fail("reader_contract_invalid", "public_schema_id")
    try:
        registry = Registry().with_resources(
            [
                (cast(str, common_id), Resource.from_contents(common)),
                (cast(str, schema_id), Resource.from_contents(schema)),
            ]
        )
        validators = {
            output_id: Draft202012Validator(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "$ref": f"{schema_id}#/$defs/{definition}",
                },
                registry=registry,
                format_checker=FormatChecker(),
            )
            for output_id, definition in _PUBLIC_OUTPUT_SCHEMA_DEFS.items()
        }
    except Exception as exc:
        raise ClauseReaderShadowError(
            "reader_contract_invalid", type(exc).__name__
        ) from exc
    return MappingProxyType(validators)


def _load_fixed_inputs() -> _FixedInputs:
    contract_bytes = _read_bytes(CONTRACT_PATH, "reader_contract_drift")
    if _sha(contract_bytes) != _REGISTERED_CONTRACT_SHA256:
        _fail("reader_contract_drift")
    contract = _decode_object(contract_bytes, "reader_contract_invalid")
    _validate_contract(contract)
    paths = {
        "template_profile": TEMPLATE_PROFILE_PATH,
        "limitation_registry": LIMITATION_REGISTRY_PATH,
        "public_common_schema": PUBLIC_COMMON_SCHEMA_PATH,
        "public_output_schema": PUBLIC_SCHEMA_PATH,
        "receipt_schema": RECEIPT_SCHEMA_PATH,
        "adversarial_vectors": ADVERSARIAL_VECTORS_PATH,
        "view_contract": VIEW_CONTRACT_PATH,
        "view_runtime": VIEW_RUNTIME_PATH,
        "consumer_profile": CONSUMER_PROFILE_PATH,
        "consumer_validator": CONSUMER_VALIDATOR_PATH,
    }
    captured: dict[str, bytes] = {}
    for name, path in paths.items():
        raw = _read_bytes(path, "reader_governance_drift")
        if _sha(raw) != _authority_sha(contract, name):
            _fail("reader_governance_drift", name)
        captured[name] = raw
    template = _decode_object(captured["template_profile"], "reader_template_invalid")
    _validate_template_profile(template)
    authorities = cast(Mapping[str, Any], contract["fixed_authorities"])
    template_row = cast(Mapping[str, Any], authorities["template_profile"])
    if (
        template_row.get("semantic_projection_sha256")
        != _REGISTERED_TEMPLATE_SEMANTIC_PROJECTION_SHA256
    ):
        _fail("reader_contract_invalid", "template_semantic_projection")
    limitations = _decode_object(
        captured["limitation_registry"], "reader_limitation_invalid"
    )
    _validate_limitations(limitations)
    public_common_schema = _decode_object(
        captured["public_common_schema"], "reader_contract_invalid"
    )
    public_schema = _decode_object(
        captured["public_output_schema"], "reader_contract_invalid"
    )
    try:
        Draft202012Validator.check_schema(public_common_schema)
        Draft202012Validator.check_schema(public_schema)
    except Exception as exc:
        raise ClauseReaderShadowError(
            "reader_contract_invalid", type(exc).__name__
        ) from exc
    public_output_validators = _build_public_output_validators(
        public_common_schema, public_schema
    )
    receipt_schema = _decode_object(
        captured["receipt_schema"], "reader_contract_invalid"
    )
    try:
        Draft202012Validator.check_schema(receipt_schema)
    except Exception as exc:
        raise ClauseReaderShadowError(
            "reader_contract_invalid", type(exc).__name__
        ) from exc
    return _FixedInputs(
        contract_bytes=contract_bytes,
        contract=contract,
        template_bytes=captured["template_profile"],
        template=template,
        limitation_bytes=captured["limitation_registry"],
        limitations=limitations,
        public_common_schema_bytes=captured["public_common_schema"],
        public_common_schema=public_common_schema,
        public_schema_bytes=captured["public_output_schema"],
        public_schema=public_schema,
        public_output_validators=public_output_validators,
        receipt_schema_bytes=captured["receipt_schema"],
        receipt_schema=receipt_schema,
        vectors_bytes=captured["adversarial_vectors"],
        view_contract_bytes=captured["view_contract"],
        view_runtime_bytes=captured["view_runtime"],
        consumer_profile_bytes=captured["consumer_profile"],
        consumer_validator_bytes=captured["consumer_validator"],
    )


def _templates(profile: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        cast(str, row["template_id"]): row
        for row in cast(Sequence[Mapping[str, Any]], profile["templates"])
    }


def _fixed_values(profile: Mapping[str, Any]) -> dict[str, str]:
    return {
        cast(str, row["value_id"]): cast(str, row["value"])
        for row in cast(Sequence[Mapping[str, Any]], profile["fixed_values"])
    }


def _render(
    template: Mapping[str, Any], field_id: str, slots: Mapping[str, object]
) -> str:
    matches = [
        row
        for row in cast(Sequence[Mapping[str, Any]], template["rendered_strings"])
        if row["field_id"] == field_id
    ]
    if len(matches) != 1:
        _fail("reader_template_invalid", cast(str, template["template_id"]))
    parts: list[str] = []
    for token in cast(Sequence[Mapping[str, Any]], matches[0]["tokens"]):
        if token["kind"] == "literal":
            parts.append(cast(str, token["value"]))
        else:
            slot_id = cast(str, token["slot_id"])
            if slot_id not in slots:
                _fail("reader_template_invalid", slot_id)
            value = slots[slot_id]
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                _fail("reader_template_invalid", slot_id)
            parts.append(str(value))
    return "".join(parts)


def _object_ref(value: object, *, object_type: str | None = None) -> dict[str, str]:
    if (
        not isinstance(value, dict)
        or set(value) != {"object_type", "object_id", "record_sha256"}
        or not isinstance(value.get("object_type"), str)
        or not isinstance(value.get("object_id"), str)
        or not value["object_id"]
        or not isinstance(value.get("record_sha256"), str)
        or not _SHA256.fullmatch(value["record_sha256"])
        or (object_type is not None and value["object_type"] != object_type)
    ):
        _fail("reader_clause_invalid", "source_object_ref")
    return {
        "object_type": value["object_type"],
        "object_id": value["object_id"],
        "record_sha256": value["record_sha256"],
    }


def _validate_clause_value(source_field: str, row: ClauseValue[Any]) -> None:
    if (
        not isinstance(row, ClauseValue)
        or row.source_field != source_field
        or row.value_class != _VALUE_TYPES[source_field]
        or not isinstance(row.clause_ref.clause_id, str)
        or not row.clause_ref.clause_id
        or not _SHA256.fullmatch(row.clause_ref.clause_record_sha256)
    ):
        _fail("reader_clause_invalid", source_field)
    value = row.value
    if value is None:
        if source_field not in _NULLABLE_FIELDS or row.missingness != "source_missing":
            _fail("reader_clause_invalid", source_field)
    elif row.missingness != "present":
        _fail("reader_clause_invalid", source_field)
    value_type = _VALUE_TYPES[source_field]
    if value is not None:
        if value_type == "boolean":
            valid = isinstance(value, bool)
        elif value_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif value_type == "object":
            valid = isinstance(value, dict)
        else:
            valid = isinstance(value, str) and bool(value)
        if not valid:
            _fail("reader_clause_invalid", source_field)
    refs = tuple(_object_ref(ref) for ref in row.source_object_refs)
    if not refs:
        _fail("reader_clause_invalid", source_field)
    if source_field in _MANY_FIELDS:
        identity = row.source_identity_key
        if not isinstance(identity, dict):
            _fail("reader_identity_join_invalid", source_field)
        if source_field.startswith("evidence."):
            if (
                identity
                != {"identity_kind": "evidence_item", "source_object_ref": refs[0]}
                or len(refs) != 1
            ):
                _fail("reader_identity_join_invalid", source_field)
        elif source_field == "provenance.source_object_ref":
            if identity != {
                "identity_kind": "source_object",
                "source_object_ref": refs[0],
            } or len(refs) != 1:
                _fail("reader_identity_join_invalid", source_field)


def _capture_fields(
    handle: _RoleHandle, consumed_fields: Sequence[str]
) -> dict[str, tuple[ClauseValue[Any], ...]]:
    captured: dict[str, tuple[ClauseValue[Any], ...]] = {}
    for source_field in consumed_fields:
        rows = (
            handle.many(source_field)
            if source_field in _MANY_FIELDS
            else (handle.one(source_field),)
        )
        for row in rows:
            _validate_clause_value(source_field, row)
        captured[source_field] = rows
    return captured


def _one(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]], source_field: str
) -> ClauseValue[Any]:
    rows = fields.get(source_field)
    if rows is None or len(rows) != 1:
        _fail("reader_clause_invalid", source_field)
    return rows[0]


def _one_ref(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]],
    source_field: str,
    object_type: str,
) -> dict[str, str]:
    row = _one(fields, source_field)
    if len(row.source_object_refs) != 1:
        _fail("reader_clause_invalid", source_field)
    return _object_ref(row.source_object_refs[0], object_type=object_type)


def _consistent_ref(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]],
    source_fields: Sequence[str],
    object_type: str,
) -> dict[str, str]:
    refs = [_one_ref(fields, source_field, object_type) for source_field in source_fields]
    if any(ref != refs[0] for ref in refs[1:]):
        _fail("reader_identity_join_invalid", object_type)
    return refs[0]


def _identity_key(row: ClauseValue[Any]) -> bytes:
    return _canonical_bytes(row.source_identity_key, "reader_identity_join_invalid")


def _evidence_citations(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]]
) -> list[dict[str, Any]]:
    source_fields = (
        "evidence.identity",
        "evidence.source_id",
        "evidence.title",
        "evidence.public_url",
        "evidence.published_at",
        "evidence.observed_at",
        "evidence.verification_status",
        "evidence.content_availability",
        "evidence.rights_use",
    )
    joined: dict[str, dict[bytes, ClauseValue[Any]]] = {}
    for source_field in source_fields:
        rows = fields.get(source_field)
        if rows is None:
            _fail("reader_identity_join_invalid", source_field)
        by_identity: dict[bytes, ClauseValue[Any]] = {}
        for row in rows:
            key = _identity_key(row)
            if key in by_identity:
                _fail("reader_identity_join_invalid", source_field)
            by_identity[key] = row
        joined[source_field] = by_identity
    identity_keys = set(joined["evidence.identity"])
    if any(set(rows) != identity_keys for rows in joined.values()):
        _fail("reader_identity_join_invalid", "evidence_identity_denominator")
    citations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for key in identity_keys:
        identity = joined["evidence.identity"][key]
        reference = _object_ref(identity.value, object_type="evidence_item")
        if reference != _object_ref(identity.source_object_refs[0]):
            _fail("reader_identity_join_invalid", "evidence.identity")
        evidence_id = reference["object_id"]
        if evidence_id in seen_ids:
            _fail("reader_identity_join_invalid", "evidence.object_id")
        seen_ids.add(evidence_id)
        citations.append(
            {
                "evidence_id": evidence_id,
                "record_sha256": reference["record_sha256"],
                "source_id": joined["evidence.source_id"][key].value,
                "title": joined["evidence.title"][key].value,
                "public_url": joined["evidence.public_url"][key].value,
                "published_at": joined["evidence.published_at"][key].value,
                "observed_at": joined["evidence.observed_at"][key].value,
                "verification_status": joined["evidence.verification_status"][key].value,
                "content_availability": joined["evidence.content_availability"][key].value,
                "rights_use": joined["evidence.rights_use"][key].value,
            }
        )
    return sorted(citations, key=lambda row: cast(str, row["evidence_id"]))


def _evidence_ids(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]]
) -> list[str]:
    rows = fields.get("evidence.identity")
    if rows is None:
        _fail("reader_identity_join_invalid", "evidence.identity")
    values: list[str] = []
    seen: set[bytes] = set()
    for row in rows:
        key = _identity_key(row)
        if key in seen:
            _fail("reader_identity_join_invalid", "evidence.identity")
        seen.add(key)
        reference = _object_ref(row.value, object_type="evidence_item")
        if reference != _object_ref(row.source_object_refs[0]):
            _fail("reader_identity_join_invalid", "evidence.identity")
        values.append(reference["object_id"])
    if len(values) != len(set(values)):
        _fail("reader_identity_join_invalid", "evidence.object_id")
    return sorted(values)


def _coverage_rows(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]]
) -> list[dict[str, Any]]:
    rows = fields.get("coverage.row")
    if rows is None:
        _fail("reader_clause_invalid", "coverage.row")
    values: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    for row in rows:
        key = _identity_key(row)
        if key in seen or not isinstance(row.value, dict):
            _fail("reader_identity_join_invalid", "coverage.row")
        seen.add(key)
        values.append(dict(row.value))
    return sorted(
        values,
        key=lambda row: (
            cast(str, row.get("universe_release_id")),
            cast(str, row.get("covered_entity_id")),
        ),
    )


def _research_object_index(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]]
) -> list[dict[str, str]]:
    provenance_rows = fields.get("provenance.source_object_ref")
    evidence_rows = fields.get("evidence.identity")
    if provenance_rows is None or evidence_rows is None:
        _fail("reader_identity_join_invalid", "object_index")
    indexed: dict[bytes, dict[str, str]] = {}
    object_ids: set[str] = set()
    for row in (*provenance_rows, *evidence_rows):
        reference = _object_ref(row.value)
        if reference != _object_ref(row.source_object_refs[0]):
            _fail("reader_identity_join_invalid", "object_index")
        key = _canonical_bytes(reference, "reader_identity_join_invalid")
        if key in indexed or reference["object_id"] in object_ids:
            _fail("reader_identity_join_invalid", "object_index")
        indexed[key] = reference
        object_ids.add(reference["object_id"])
    return sorted(indexed.values(), key=lambda row: row["object_id"])


def _limitation_scope(registry: Mapping[str, Any], scope_id: str) -> list[str]:
    profiles = registry.get("output_profiles")
    value = profiles.get(scope_id) if isinstance(profiles, dict) else None
    return _closed_strings(value, "reader_limitation_invalid")


def _execute_limitation_scopes(
    registry: Mapping[str, Any],
    rendered_scope_ids: Sequence[str],
    expected_scope_ids: Sequence[str],
) -> dict[str, list[str]]:
    if tuple(rendered_scope_ids) != tuple(sorted(expected_scope_ids)):
        _fail("reader_limitation_invalid", "rendered_scope_execution")
    return {
        scope_id: _limitation_scope(registry, scope_id)
        for scope_id in rendered_scope_ids
    }


def _branch(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]], active_branch_id: str
) -> str:
    status = _one(fields, "traversal.status").value
    returned = _one(fields, "traversal.returned_paths").value
    truncated = _one(fields, "traversal.truncated").value
    coverage_count = len(fields.get("coverage.row", ()))
    expected = "branch:path_found" if status == "paths_found" else "branch:no_path"
    if (
        status not in {"paths_found", "no_path"}
        or active_branch_id != expected
        or isinstance(returned, bool)
        or not isinstance(returned, int)
        or not isinstance(truncated, bool)
    ):
        _fail("reader_branch_invalid")
    if expected == "branch:no_path":
        if returned != 0 or truncated is not False or coverage_count != 0:
            _fail("reader_branch_invalid")
    elif returned < 1 or coverage_count < 1:
        _fail("reader_branch_invalid")
    return expected


def _artifact_stem(
    release_ref: Mapping[str, str],
    event_ref: Mapping[str, str],
    target_ref: Mapping[str, str],
    max_hops: object,
    max_paths: object,
) -> str:
    if (
        isinstance(max_hops, bool)
        or not isinstance(max_hops, int)
        or isinstance(max_paths, bool)
        or not isinstance(max_paths, int)
    ):
        _fail("reader_artifact_invalid")
    raw = (
        f"{release_ref['record_sha256']}:{event_ref['object_id']}:"
        f"{target_ref['object_id']}:{max_hops}:{max_paths}"
    ).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def _attach_artifact(
    body: Mapping[str, Any], filename: str, media_type: str
) -> tuple[dict[str, Any], bytes, bytes]:
    artifact_raw = _artifact_bytes(body)
    document = dict(body)
    document["artifact"] = {
        "filename": filename,
        "media_type": media_type,
        "sha256": _sha(artifact_raw),
        "bytes": len(artifact_raw),
    }
    return (
        document,
        _canonical_bytes(body, "reader_artifact_invalid"),
        artifact_raw,
    )


def _validate_public_output_documents(
    outputs: Sequence[_RoleCompilation],
    validators: Mapping[str, Draft202012Validator],
) -> None:
    if {row.output_id for row in outputs} != set(_PUBLIC_OUTPUT_SCHEMA_DEFS):
        _fail("reader_artifact_invalid", "output_schema_role_set")
    for compiled in outputs:
        validator = validators.get(compiled.output_id)
        if validator is None:
            _fail("reader_artifact_invalid", "output_schema_role")
        try:
            errors = sorted(
                validator.iter_errors(compiled.document),
                key=lambda item: (
                    tuple(str(part) for part in item.absolute_path),
                    tuple(str(part) for part in item.absolute_schema_path),
                ),
            )
        except Exception as exc:
            raise ClauseReaderShadowError(
                "reader_artifact_invalid", type(exc).__name__
            ) from exc
        if errors:
            first = errors[0]
            path = "/" + "/".join(str(part) for part in first.absolute_path)
            _fail(
                "reader_artifact_invalid",
                f"{compiled.output_id}:{path or '/'}:{first.validator}",
            )


def _validate_rendered_limitation_execution(
    outputs: Sequence[_RoleCompilation], registry: Mapping[str, Any]
) -> None:
    for compiled in outputs:
        document = compiled.document
        if compiled.output_id == "output:research_package":
            observed = {
                "scope:output.research_package": document.get("limitations")
            }
        elif compiled.output_id == "output:board_brief":
            observed = {"scope:output.board_brief": document.get("limitations")}
        elif compiled.output_id == "output:newsroom_claim_card":
            claims = document.get("claims")
            if not isinstance(claims, list):
                _fail("reader_limitation_invalid", "newsroom_claims")
            by_id = {
                row.get("claim_id"): row
                for row in claims
                if isinstance(row, dict) and isinstance(row.get("claim_id"), str)
            }
            event_claim = by_id.get("claim:card.event_record")
            release_claim = by_id.get("claim:card.release_structure")
            if not isinstance(event_claim, dict) or not isinstance(release_claim, dict):
                _fail("reader_limitation_invalid", "newsroom_claims")
            observed = {
                "scope:claim.card.event_record": event_claim.get("limitations"),
                "scope:claim.card.release_structure": release_claim.get("limitations"),
                "scope:output.newsroom_claim_card": document.get("limitations"),
            }
        else:
            _fail("reader_limitation_invalid", "output_scope")
        if tuple(sorted(observed)) != compiled.rendered_limitation_scope_ids:
            _fail("reader_limitation_invalid", "rendered_scope_execution")
        if (
            "scope:output.all_views" in observed
            or compiled.applicable_but_outer_wrapper_absent_scope_ids
            != ("scope:output.all_views",)
        ):
            _fail("reader_limitation_invalid", "standalone_scope_accounting")
        for scope_id, limitation_ids in observed.items():
            if limitation_ids != _limitation_scope(registry, scope_id):
                _fail("reader_limitation_invalid", scope_id)


def _role_program(
    profile: Mapping[str, Any], role: str, active_branch_id: str
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    output_id, _ = _OUTPUT_ROLES[role]
    templates = _templates(profile)
    active = tuple(
        sorted(
            template_id
            for template_id, template in templates.items()
            if template["output_id"] == output_id
            and template["branch_id"] in {None, active_branch_id}
        )
    )
    consumed = tuple(
        sorted(
            {
                field
                for template_id in active
                for field in cast(Sequence[str], templates[template_id]["consumed_source_fields"])
            }
        )
    )
    operators = tuple(
        sorted(
            {
                operator
                for template_id in active
                for operator in cast(Sequence[str], templates[template_id]["operator_ids"])
            }
        )
    )
    rendered_scopes = tuple(
        sorted(
            {
                scope
                for template_id in active
                for scope in cast(
                    Sequence[str],
                    templates[template_id]["rendered_limitation_scope_ids"],
                )
            }
        )
    )
    absent_scopes = tuple(
        sorted(
            {
                scope
                for template_id in active
                for scope in cast(
                    Sequence[str],
                    templates[template_id][
                        "applicable_but_outer_wrapper_absent_scope_ids"
                    ],
                )
            }
        )
    )
    if (
        set(rendered_scopes) & set(absent_scopes)
        or absent_scopes != ("scope:output.all_views",)
    ):
        _fail("reader_limitation_invalid", "standalone_scope_accounting")
    return active, consumed, operators, rendered_scopes, absent_scopes


def _validate_handle(
    handle: _RoleHandle,
    role: str,
    active_templates: Sequence[str],
    policy: Mapping[str, Any],
    consumed_fields: Sequence[str],
) -> None:
    output_id, role_id = _OUTPUT_ROLES[role]
    if (
        handle.output_id != output_id
        or handle.role_id != role_id
        or not isinstance(handle.view_id, str)
        or not handle.view_id.startswith("clause-source-view:")
        or tuple(handle.active_template_ids) != tuple(active_templates)
        or policy.get("output_id") != output_id
        or policy.get("role_id") != role_id
        or policy.get("view_id") != handle.view_id
        or policy.get("active_template_ids") != list(active_templates)
        or policy.get("required_source_field_ids") != list(consumed_fields)
    ):
        _fail("reader_handle_invalid", role)


def _clause_refs(
    fields: Mapping[str, tuple[ClauseValue[Any], ...]],
    consumed_fields: Sequence[str],
    view_receipt: Mapping[str, Any],
) -> tuple[dict[str, str], ...]:
    observed = sorted(
        (
            {
                "clause_id": row.clause_ref.clause_id,
                "clause_record_sha256": row.clause_ref.clause_record_sha256,
            }
            for field in consumed_fields
            for row in fields[field]
        ),
        key=lambda row: (row["clause_id"], row["clause_record_sha256"]),
    )
    if len({_canonical_bytes(row, "reader_receipt_invalid") for row in observed}) != len(
        observed
    ):
        _fail("reader_receipt_invalid", "duplicate_clause_ref")
    field_index = view_receipt.get("field_index")
    if not isinstance(field_index, list):
        _fail("reader_input_invalid")
    by_field = {
        row["source_field"]: row
        for row in field_index
        if isinstance(row, dict) and isinstance(row.get("source_field"), str)
    }
    expected = sorted(
        (
            dict(ref)
            for field in consumed_fields
            for ref in cast(Sequence[Mapping[str, str]], by_field[field]["clause_refs"])
        ),
        key=lambda row: (row["clause_id"], row["clause_record_sha256"]),
    )
    if observed != expected:
        _fail("reader_receipt_invalid", "clause_ref_set")
    return tuple(observed)


def _compile_research(
    handle: _RoleHandle,
    profile: Mapping[str, Any],
    limitations: Mapping[str, Any],
    active_branch_id: str,
    policy: Mapping[str, Any],
    view_receipt: Mapping[str, Any],
) -> _RoleCompilation:
    active, consumed, operators, rendered_scopes, absent_scopes = _role_program(
        profile, "research", active_branch_id
    )
    _validate_handle(handle, "research", active, policy, consumed)
    fields = _capture_fields(handle, consumed)
    _branch(fields, active_branch_id)
    templates = _templates(profile)
    fixed = _fixed_values(profile)
    template = templates["template:research.package.shell.v1"]
    event_ref = _one_ref(fields, "event.canonical_label", "event")
    target_ref = _one_ref(fields, "target.identity", "entity")
    if _one(fields, "target.identity").value != target_ref:
        _fail("reader_identity_join_invalid", "target.identity")
    release_ref = _one_ref(fields, "release.generated_at", "canonical_release")
    slots = {
        "slot:event.canonical_label": _one(fields, "event.canonical_label").value,
        "slot:event.object_id": event_ref["object_id"],
        "slot:target.object_id": target_ref["object_id"],
        "slot:release.object_id": release_ref["object_id"],
        "slot:release.record_sha256": release_ref["record_sha256"],
        "slot:release.generated_at": _one(fields, "release.generated_at").value,
    }
    citations = _evidence_citations(fields)
    coverage = _coverage_rows(fields)
    executed_limitations = _execute_limitation_scopes(
        limitations, rendered_scopes, ("scope:output.research_package",)
    )
    body = {
        "output_id": fixed["fixed:output.research"],
        "title": _render(template, "title", slots),
        "as_of": _one(fields, "release.generated_at").value,
        "object_index": _research_object_index(fields),
        "evidence": citations,
        "coverage": {
            "traversal_status": _one(fields, "traversal.status").value,
            "returned_paths": _one(fields, "traversal.returned_paths").value,
            "truncated": _one(fields, "traversal.truncated").value,
            "declared_universes": coverage,
        },
        "citation": _render(template, "citation", slots),
        "limitations": executed_limitations["scope:output.research_package"],
    }
    stem = _artifact_stem(
        release_ref,
        event_ref,
        target_ref,
        _one(fields, "traversal.max_hops").value,
        _one(fields, "traversal.max_paths").value,
    )
    document, body_bytes, artifact_bytes = _attach_artifact(
        body, f"igrm-research-{stem}.json", fixed["fixed:media_type.json"]
    )
    return _RoleCompilation(
        output_id=fixed["fixed:output.research"],
        role_id="research",
        view_id=handle.view_id,
        document=document,
        document_bytes=_canonical_bytes(document, "reader_artifact_invalid"),
        body_bytes=body_bytes,
        artifact_bytes=artifact_bytes,
        active_template_ids=active,
        consumed_fields=consumed,
        clause_refs=_clause_refs(fields, consumed, view_receipt),
        operator_ids=operators,
        rendered_limitation_scope_ids=rendered_scopes,
        applicable_but_outer_wrapper_absent_scope_ids=absent_scopes,
        evidence_count=len(citations),
        coverage_count=len(coverage),
        object_evidence_count=len(fields["provenance.source_object_ref"]),
    )


def _compile_board(
    handle: _RoleHandle,
    profile: Mapping[str, Any],
    limitations: Mapping[str, Any],
    active_branch_id: str,
    policy: Mapping[str, Any],
    view_receipt: Mapping[str, Any],
) -> _RoleCompilation:
    active, consumed, operators, rendered_scopes, absent_scopes = _role_program(
        profile, "board", active_branch_id
    )
    _validate_handle(handle, "board", active, policy, consumed)
    fields = _capture_fields(handle, consumed)
    _branch(fields, active_branch_id)
    templates = _templates(profile)
    fixed = _fixed_values(profile)
    event_fields = (
        "event.canonical_label",
        "event.class",
        "event.last_verified_at",
        "event.record_status",
        "event.starts_at",
    )
    event_ref = _consistent_ref(fields, event_fields, "event")
    target_ref = _one_ref(fields, "target.canonical_name", "entity")
    release_ref = _one_ref(fields, "release.generated_at", "canonical_release")
    slots = {
        "slot:event.canonical_label": _one(fields, "event.canonical_label").value,
        "slot:event.class": _one(fields, "event.class").value,
        "slot:event.last_verified_at": _one(fields, "event.last_verified_at").value,
        "slot:event.record_status": _one(fields, "event.record_status").value,
        "slot:event.starts_at": _one(fields, "event.starts_at").value,
        "slot:target.canonical_name": _one(fields, "target.canonical_name").value,
        "slot:traversal.max_hops": _one(fields, "traversal.max_hops").value,
        "slot:traversal.returned_paths": _one(
            fields, "traversal.returned_paths"
        ).value,
    }
    evidence_ids = _evidence_ids(fields)
    branch_template = templates[
        "template:board.linkage.path_found.v1"
        if active_branch_id == "branch:path_found"
        else "template:board.linkage.no_path.v1"
    ]
    executed_limitations = _execute_limitation_scopes(
        limitations, rendered_scopes, ("scope:output.board_brief",)
    )
    board_limitations = executed_limitations["scope:output.board_brief"]
    if "draft_requires_human_review" not in board_limitations:
        _fail("reader_limitation_invalid", "draft_requires_human_review")
    body = {
        "output_id": fixed["fixed:output.board"],
        "title": _render(templates["template:board.brief.shell.v1"], "title", slots),
        "as_of": _one(fields, "release.generated_at").value,
        "review_status": "draft_requires_human_review",
        "sections": [
            {
                "section_id": fixed["fixed:board.section.event_record"],
                "heading": fixed["fixed:board.heading.event_record"],
                "text": _render(
                    templates["template:board.event.record.v1"], "text", slots
                ),
                "object_ids": [event_ref["object_id"]],
                "evidence_ids": evidence_ids,
            },
            {
                "section_id": fixed["fixed:board.section.india_linkage"],
                "heading": fixed["fixed:board.heading.india_linkage"],
                "text": _render(branch_template, "text", slots),
                "object_ids": [event_ref["object_id"], target_ref["object_id"]],
                "evidence_ids": evidence_ids,
            },
            {
                "section_id": fixed["fixed:board.section.decision_boundary"],
                "heading": fixed["fixed:board.heading.decision_boundary"],
                "text": _render(
                    templates["template:board.decision.boundary.v1"], "text", slots
                ),
                "object_ids": [event_ref["object_id"], target_ref["object_id"]],
                "evidence_ids": evidence_ids,
            },
        ],
        "limitations": board_limitations,
    }
    stem = _artifact_stem(
        release_ref,
        event_ref,
        target_ref,
        _one(fields, "traversal.max_hops").value,
        _one(fields, "traversal.max_paths").value,
    )
    document, body_bytes, artifact_bytes = _attach_artifact(
        body, f"igrm-board-{stem}.json", fixed["fixed:media_type.json"]
    )
    return _RoleCompilation(
        output_id=fixed["fixed:output.board"],
        role_id="board",
        view_id=handle.view_id,
        document=document,
        document_bytes=_canonical_bytes(document, "reader_artifact_invalid"),
        body_bytes=body_bytes,
        artifact_bytes=artifact_bytes,
        active_template_ids=active,
        consumed_fields=consumed,
        clause_refs=_clause_refs(fields, consumed, view_receipt),
        operator_ids=operators,
        rendered_limitation_scope_ids=rendered_scopes,
        applicable_but_outer_wrapper_absent_scope_ids=absent_scopes,
        evidence_count=len(evidence_ids),
        coverage_count=len(fields["coverage.row"]),
        object_evidence_count=0,
    )


def _compile_newsroom(
    handle: _RoleHandle,
    profile: Mapping[str, Any],
    limitations: Mapping[str, Any],
    active_branch_id: str,
    policy: Mapping[str, Any],
    view_receipt: Mapping[str, Any],
) -> _RoleCompilation:
    active, consumed, operators, rendered_scopes, absent_scopes = _role_program(
        profile, "newsroom", active_branch_id
    )
    _validate_handle(handle, "newsroom", active, policy, consumed)
    fields = _capture_fields(handle, consumed)
    _branch(fields, active_branch_id)
    templates = _templates(profile)
    fixed = _fixed_values(profile)
    event_fields = (
        "event.canonical_label",
        "event.class",
        "event.record_status",
        "event.starts_at",
    )
    event_ref = _consistent_ref(fields, event_fields, "event")
    target_ref = _one_ref(fields, "target.canonical_name", "entity")
    release_ref = _one_ref(fields, "release.generated_at", "canonical_release")
    slots = {
        "slot:event.canonical_label": _one(fields, "event.canonical_label").value,
        "slot:event.class": _one(fields, "event.class").value,
        "slot:event.record_status": _one(fields, "event.record_status").value,
        "slot:event.starts_at": _one(fields, "event.starts_at").value,
        "slot:target.canonical_name": _one(fields, "target.canonical_name").value,
        "slot:traversal.returned_paths": _one(
            fields, "traversal.returned_paths"
        ).value,
    }
    evidence_ids = _evidence_ids(fields)
    citations = _evidence_citations(fields)
    branch_template = templates[
        "template:newsroom.release_structure.path_found.v1"
        if active_branch_id == "branch:path_found"
        else "template:newsroom.release_structure.no_path.v1"
    ]
    executed_limitations = _execute_limitation_scopes(
        limitations,
        rendered_scopes,
        (
            "scope:claim.card.event_record",
            "scope:claim.card.release_structure",
            "scope:output.newsroom_claim_card",
        ),
    )
    body = {
        "output_id": fixed["fixed:output.newsroom"],
        "title": _render(templates["template:newsroom.card.shell.v1"], "title", slots),
        "as_of": _one(fields, "release.generated_at").value,
        "claims": [
            {
                "claim_id": fixed["fixed:claim.event_record"],
                "statement": _render(
                    templates["template:newsroom.event.record.v1"],
                    "statement",
                    slots,
                ),
                "scope": fixed["fixed:claim.scope.release_record"],
                "object_ids": [event_ref["object_id"]],
                "evidence_ids": evidence_ids,
                "status": fixed["fixed:claim.status"],
                "limitations": executed_limitations[
                    "scope:claim.card.event_record"
                ],
            },
            {
                "claim_id": fixed["fixed:claim.release_structure"],
                "statement": _render(branch_template, "statement", slots),
                "scope": fixed["fixed:claim.scope.release_structure"],
                "object_ids": [event_ref["object_id"], target_ref["object_id"]],
                "evidence_ids": evidence_ids,
                "status": fixed["fixed:claim.status"],
                "limitations": executed_limitations[
                    "scope:claim.card.release_structure"
                ],
            },
        ],
        "evidence": citations,
        "correction_route": fixed["fixed:newsroom.correction_route"],
        "limitations": executed_limitations["scope:output.newsroom_claim_card"],
    }
    stem = _artifact_stem(
        release_ref,
        event_ref,
        target_ref,
        _one(fields, "traversal.max_hops").value,
        _one(fields, "traversal.max_paths").value,
    )
    document, body_bytes, artifact_bytes = _attach_artifact(
        body, f"igrm-claim-card-{stem}.json", fixed["fixed:media_type.json"]
    )
    return _RoleCompilation(
        output_id=fixed["fixed:output.newsroom"],
        role_id="newsroom",
        view_id=handle.view_id,
        document=document,
        document_bytes=_canonical_bytes(document, "reader_artifact_invalid"),
        body_bytes=body_bytes,
        artifact_bytes=artifact_bytes,
        active_template_ids=active,
        consumed_fields=consumed,
        clause_refs=_clause_refs(fields, consumed, view_receipt),
        operator_ids=operators,
        rendered_limitation_scope_ids=rendered_scopes,
        applicable_but_outer_wrapper_absent_scope_ids=absent_scopes,
        evidence_count=len(citations),
        coverage_count=len(fields["coverage.row"]),
        object_evidence_count=0,
    )


def _transitive_bindings(
    view_receipt: Mapping[str, Any], fixed: _FixedInputs, runtime_sha: str
) -> dict[str, Any]:
    bindings = view_receipt.get("bindings")
    if not isinstance(bindings, dict):
        _fail("reader_input_invalid")
    view_raw = _canonical_bytes(view_receipt, "reader_input_invalid")
    source = bindings.get("source_bundle_ref")
    proof = bindings.get("role_proof_bundle_ref")
    consumer = bindings.get("consumer_profile_ref")
    clause_contract = bindings.get("clause_contract_ref")
    view_contract = bindings.get("view_contract_ref")
    view_runtime = bindings.get("view_runtime_ref")
    if any(
        not isinstance(row, dict)
        for row in (source, proof, consumer, clause_contract, view_contract, view_runtime)
    ):
        _fail("reader_input_invalid")
    source = cast(Mapping[str, Any], source)
    proof = cast(Mapping[str, Any], proof)
    consumer = cast(Mapping[str, Any], consumer)
    clause_contract = cast(Mapping[str, Any], clause_contract)
    view_contract = cast(Mapping[str, Any], view_contract)
    view_runtime = cast(Mapping[str, Any], view_runtime)
    if (
        consumer.get("file_sha256") != _sha(fixed.consumer_profile_bytes)
        or consumer.get("semantic_projection_sha256")
        != fixed.contract["fixed_authorities"]["consumer_profile"][
            "semantic_projection_sha256"
        ]
        or view_contract.get("file_sha256") != _sha(fixed.view_contract_bytes)
        or view_runtime.get("implementation_sha256") != _sha(fixed.view_runtime_bytes)
    ):
        _fail("reader_input_invalid", "transitive_binding")
    return {
        "view_receipt_ref": {
            "view_set_id": view_receipt.get("view_set_id"),
            "record_sha256": view_receipt.get("record_sha256"),
            "captured_bytes_sha256": _sha(view_raw),
        },
        "source_bundle_ref": {
            "record_sha256": source.get("record_sha256"),
            "captured_bytes_sha256": source.get("captured_bytes_sha256"),
        },
        "role_proof_bundle_ref": {
            "record_sha256": proof.get("record_sha256"),
            "captured_bytes_sha256": proof.get("captured_bytes_sha256"),
        },
        "consumer_profile_ref": {
            "file_sha256": consumer.get("file_sha256"),
            "semantic_projection_sha256": consumer.get(
                "semantic_projection_sha256"
            ),
        },
        "analytical_clause_contract_ref": {
            "file_sha256": clause_contract.get("file_sha256")
        },
        "view_contract_ref": {"file_sha256": view_contract.get("file_sha256")},
        "view_runtime_ref": {
            "implementation_sha256": view_runtime.get("implementation_sha256")
        },
        "renderer_contract_ref": {"file_sha256": _sha(fixed.contract_bytes)},
        "renderer_runtime_ref": {"implementation_sha256": runtime_sha},
        "template_profile_ref": {
            "file_sha256": _sha(fixed.template_bytes),
            "semantic_projection_sha256": _template_semantic_projection_sha256(
                fixed.template
            ),
        },
        "limitation_registry_ref": {"file_sha256": _sha(fixed.limitation_bytes)},
        "public_common_schema_ref": {
            "file_sha256": _sha(fixed.public_common_schema_bytes)
        },
        "public_schema_ref": {"file_sha256": _sha(fixed.public_schema_bytes)},
    }


def _output_receipt(compiled: _RoleCompilation) -> dict[str, Any]:
    return {
        "output_id": compiled.output_id,
        "role_id": compiled.role_id,
        "view_id": compiled.view_id,
        "active_template_ids": list(compiled.active_template_ids),
        "consumed_source_field_ids": list(compiled.consumed_fields),
        "clause_refs": [dict(ref) for ref in compiled.clause_refs],
        "operator_ids": list(compiled.operator_ids),
        "rendered_limitation_scope_ids": list(
            compiled.rendered_limitation_scope_ids
        ),
        "applicable_but_outer_wrapper_absent_scope_ids": list(
            compiled.applicable_but_outer_wrapper_absent_scope_ids
        ),
        "body_sha256": _sha(compiled.body_bytes),
        "artifact_sha256": _sha(compiled.artifact_bytes),
        "denominators": {
            "active_template_denominator": len(compiled.active_template_ids),
            "consumed_source_field_denominator": len(compiled.consumed_fields),
            "clause_ref_denominator": len(compiled.clause_refs),
            "operator_denominator": len(compiled.operator_ids),
            "rendered_limitation_scope_denominator": len(
                compiled.rendered_limitation_scope_ids
            ),
            "applicable_but_outer_wrapper_absent_scope_denominator": len(
                compiled.applicable_but_outer_wrapper_absent_scope_ids
            ),
            "evidence_item_denominator": compiled.evidence_count,
            "coverage_row_denominator": compiled.coverage_count,
            "object_evidence_row_denominator": compiled.object_evidence_count,
            "body_bytes": len(compiled.body_bytes),
            "artifact_bytes": len(compiled.artifact_bytes),
        },
    }


def _assert_value_free(receipt: Mapping[str, Any]) -> None:
    forbidden_keys = {"value", "prose", "url", "date", "signature", "source_content"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = key.lower()
                if lowered in forbidden_keys or lowered.endswith("_url") or "signature" in lowered:
                    _fail("reader_value_leakage", key)
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        elif isinstance(value, str):
            if "://" in value or _DATE_TEXT.search(value):
                _fail("reader_value_leakage")

    walk(receipt)


def _build_receipt(
    view_receipt: Mapping[str, Any],
    fixed: _FixedInputs,
    runtime_sha: str,
    active_branch_id: str,
    outputs: Sequence[_RoleCompilation],
) -> dict[str, Any]:
    output_rows = [_output_receipt(row) for row in outputs]
    binding = _transitive_bindings(view_receipt, fixed, runtime_sha)
    identity = {
        "view_receipt_record_sha256": binding["view_receipt_ref"]["record_sha256"],
        "renderer_contract_sha256": binding["renderer_contract_ref"]["file_sha256"],
        "renderer_runtime_sha256": runtime_sha,
        "template_profile_sha256": binding["template_profile_ref"]["file_sha256"],
        "active_branch_id": active_branch_id,
        "output_body_sha256": [row["body_sha256"] for row in output_rows],
    }
    value = {
        "object_type": "clause_reader_compilation_receipt",
        "schema_version": _VERSION,
        "compilation_id": f"clause-reader-compilation:{_sha(_canonical_bytes(identity, 'reader_receipt_invalid'))[:24]}",
        "record_sha256": "0" * 64,
        "bindings": binding,
        "active_branch_id": active_branch_id,
        "outputs": output_rows,
        "denominators": {
            "output_denominator": len(output_rows),
            "template_denominator": sum(
                len(row.active_template_ids) for row in outputs
            ),
            "consumed_source_field_denominator": sum(
                len(row.consumed_fields) for row in outputs
            ),
            "clause_ref_denominator": sum(len(row.clause_refs) for row in outputs),
            "operator_denominator": sum(len(row.operator_ids) for row in outputs),
            "rendered_limitation_scope_denominator": sum(
                len(row.rendered_limitation_scope_ids) for row in outputs
            ),
            "applicable_but_outer_wrapper_absent_scope_denominator": sum(
                len(row.applicable_but_outer_wrapper_absent_scope_ids)
                for row in outputs
            ),
        },
        "comparison_performed": False,
        "comparison_result": "not_performed",
        "trust": dict(_TRUST),
        "boundary": dict(_BOUNDARY),
    }
    sealed = _seal(value)
    _assert_value_free(sealed)
    return sealed


def _validate_receipt(receipt: Mapping[str, Any], fixed: _FixedInputs) -> None:
    try:
        Draft202012Validator(fixed.receipt_schema).validate(dict(receipt))
    except Exception as exc:
        raise ClauseReaderShadowError("reader_receipt_invalid", type(exc).__name__) from exc
    if receipt.get("record_sha256") != _record_sha256(receipt):
        _fail("reader_receipt_invalid", "record_sha256")
    if (
        receipt.get("comparison_performed") is not False
        or receipt.get("comparison_result") != "not_performed"
    ):
        _fail("reader_receipt_invalid", "comparison_not_performed")
    outputs = receipt.get("outputs")
    if (
        not isinstance(outputs, list)
        or [row.get("output_id") for row in outputs if isinstance(row, dict)]
        != sorted(value[0] for value in _OUTPUT_ROLES.values())
    ):
        _fail("reader_receipt_invalid", "output_order")
    roles_seen: set[str] = set()
    views_seen: set[str] = set()
    totals = {
        "template_denominator": 0,
        "consumed_source_field_denominator": 0,
        "clause_ref_denominator": 0,
        "operator_denominator": 0,
        "rendered_limitation_scope_denominator": 0,
        "applicable_but_outer_wrapper_absent_scope_denominator": 0,
    }
    active_branch_id = cast(str, receipt["active_branch_id"])
    output_to_role = {output_id: role for role, (output_id, _) in _OUTPUT_ROLES.items()}
    for raw_row in outputs:
        row = cast(Mapping[str, Any], raw_row)
        role = output_to_role.get(cast(str, row.get("output_id")))
        if role is None or row.get("role_id") != role:
            _fail("reader_receipt_invalid", "role_output_binding")
        (
            expected_templates,
            expected_fields,
            expected_operators,
            expected_rendered_scopes,
            expected_absent_scopes,
        ) = _role_program(fixed.template, role, active_branch_id)
        if (
            row.get("active_template_ids") != list(expected_templates)
            or row.get("consumed_source_field_ids") != list(expected_fields)
            or row.get("operator_ids") != list(expected_operators)
            or row.get("rendered_limitation_scope_ids")
            != list(expected_rendered_scopes)
            or row.get("applicable_but_outer_wrapper_absent_scope_ids")
            != list(expected_absent_scopes)
        ):
            _fail("reader_receipt_invalid", role)
        clause_refs = cast(Sequence[Mapping[str, Any]], row["clause_refs"])
        if list(clause_refs) != sorted(
            clause_refs,
            key=lambda ref: (ref["clause_id"], ref["clause_record_sha256"]),
        ):
            _fail("reader_receipt_invalid", "clause_ref_order")
        denominators = cast(Mapping[str, Any], row["denominators"])
        observed_lengths = {
            "active_template_denominator": len(expected_templates),
            "consumed_source_field_denominator": len(expected_fields),
            "clause_ref_denominator": len(clause_refs),
            "operator_denominator": len(expected_operators),
            "rendered_limitation_scope_denominator": len(
                expected_rendered_scopes
            ),
            "applicable_but_outer_wrapper_absent_scope_denominator": len(
                expected_absent_scopes
            ),
        }
        if any(denominators.get(key) != value for key, value in observed_lengths.items()):
            _fail("reader_receipt_invalid", "output_denominator")
        roles_seen.add(cast(str, row["role_id"]))
        views_seen.add(cast(str, row["view_id"]))
        totals["template_denominator"] += len(expected_templates)
        totals["consumed_source_field_denominator"] += len(expected_fields)
        totals["clause_ref_denominator"] += len(clause_refs)
        totals["operator_denominator"] += len(expected_operators)
        totals["rendered_limitation_scope_denominator"] += len(
            expected_rendered_scopes
        )
        totals["applicable_but_outer_wrapper_absent_scope_denominator"] += len(
            expected_absent_scopes
        )
    if roles_seen != set(_OUTPUT_ROLES) or len(views_seen) != len(_OUTPUT_ROLES):
        _fail("reader_receipt_invalid", "role_or_view_denominator")
    global_denominators = receipt.get("denominators")
    if (
        not isinstance(global_denominators, dict)
        or global_denominators.get("output_denominator") != 3
    ):
        _fail("reader_receipt_invalid", "global_denominator")
    if any(global_denominators.get(key) != value for key, value in totals.items()):
        _fail("reader_receipt_invalid", "global_denominator")
    bindings = cast(Mapping[str, Any], receipt["bindings"])
    expected_fixed_hashes = {
        "renderer_contract_ref": _sha(fixed.contract_bytes),
        "template_profile_ref": _sha(fixed.template_bytes),
        "limitation_registry_ref": _sha(fixed.limitation_bytes),
        "public_common_schema_ref": _sha(fixed.public_common_schema_bytes),
        "public_schema_ref": _sha(fixed.public_schema_bytes),
    }
    for name, digest in expected_fixed_hashes.items():
        if cast(Mapping[str, Any], bindings[name]).get("file_sha256") != digest:
            _fail("reader_receipt_invalid", name)
    _assert_value_free(receipt)


def _build_candidate_from_captured(
    snapshot: ClauseSourceViews,
    fixed: _FixedInputs,
    *,
    view_receipt: Mapping[str, Any],
    research_handle: _RoleHandle,
    board_handle: _RoleHandle,
    newsroom_handle: _RoleHandle,
) -> ClauseReaderCompilation:
    active_branch_id = view_receipt.get("active_branch_id")
    if active_branch_id not in {"branch:no_path", "branch:path_found"}:
        _fail("reader_input_invalid")
    policies_value = view_receipt.get("consumer_policies")
    if not isinstance(policies_value, list):
        _fail("reader_input_invalid")
    policies = {
        row["role_id"]: row
        for row in policies_value
        if isinstance(row, dict) and row.get("role_id") in _OUTPUT_ROLES
    }
    if set(policies) != set(_OUTPUT_ROLES):
        _fail("reader_input_invalid")
    runtime_sha = _runtime_sha256()
    research = _compile_research(
        research_handle,
        fixed.template,
        fixed.limitations,
        active_branch_id,
        policies["research"],
        view_receipt,
    )
    board = _compile_board(
        board_handle,
        fixed.template,
        fixed.limitations,
        active_branch_id,
        policies["board"],
        view_receipt,
    )
    newsroom = _compile_newsroom(
        newsroom_handle,
        fixed.template,
        fixed.limitations,
        active_branch_id,
        policies["newsroom"],
        view_receipt,
    )
    outputs = tuple(sorted((research, board, newsroom), key=lambda row: row.output_id))
    _validate_rendered_limitation_execution(outputs, fixed.limitations)
    _validate_public_output_documents(outputs, fixed.public_output_validators)
    receipt = _build_receipt(
        view_receipt, fixed, runtime_sha, active_branch_id, outputs
    )
    _validate_receipt(receipt, fixed)
    return ClauseReaderCompilation(
        _construction_token=_CONSTRUCTION_TOKEN,
        snapshot=snapshot,
        fixed_bytes=fixed.captured_bytes(),
        runtime_sha256=runtime_sha,
        research_bytes=research.document_bytes,
        research_artifact_bytes=research.artifact_bytes,
        board_bytes=board.document_bytes,
        board_artifact_bytes=board.artifact_bytes,
        newsroom_bytes=newsroom.document_bytes,
        newsroom_artifact_bytes=newsroom.artifact_bytes,
        receipt_bytes=_canonical_bytes(receipt, "reader_receipt_invalid"),
    )


def _build_candidate_from_snapshot(
    snapshot: ClauseSourceViews, fixed: _FixedInputs
) -> ClauseReaderCompilation:
    try:
        view_receipt = snapshot.receipt
        research_handle = snapshot.research
        board_handle = snapshot.board
        newsroom_handle = snapshot.newsroom
        return _build_candidate_from_captured(
            snapshot,
            fixed,
            view_receipt=view_receipt,
            research_handle=research_handle,
            board_handle=board_handle,
            newsroom_handle=newsroom_handle,
        )
    except ClauseSourceViewError as exc:
        raise ClauseReaderShadowError("reader_input_invalid", exc.code) from exc


def _verify_compilation(compiled: ClauseReaderCompilation) -> None:
    if _runtime_sha256() != compiled._runtime_sha256:
        _fail("reader_runtime_drift")
    try:
        snapshot = compiled._snapshot.verified_snapshot()
    except ClauseSourceViewError as exc:
        raise ClauseReaderShadowError("reader_input_invalid", exc.code) from exc
    if type(snapshot) is not ClauseSourceViews or snapshot is compiled._snapshot:
        _fail("reader_input_invalid")
    fixed = _load_fixed_inputs()
    if fixed.captured_bytes() != compiled._fixed_bytes:
        _fail("reader_governance_drift")
    receipt = _decode_object(compiled._receipt_bytes, "reader_receipt_invalid")
    _validate_receipt(receipt, fixed)
    candidate = _build_candidate_from_snapshot(snapshot, fixed)
    observed = (
        compiled._research_bytes,
        compiled._research_artifact_bytes,
        compiled._board_bytes,
        compiled._board_artifact_bytes,
        compiled._newsroom_bytes,
        compiled._newsroom_artifact_bytes,
        compiled._receipt_bytes,
    )
    expected = (
        candidate._research_bytes,
        candidate._research_artifact_bytes,
        candidate._board_bytes,
        candidate._board_artifact_bytes,
        candidate._newsroom_bytes,
        candidate._newsroom_artifact_bytes,
        candidate._receipt_bytes,
    )
    if observed != expected:
        _fail("reader_recompile_mismatch")


def compile_clause_reader_shadow(views: ClauseSourceViews) -> ClauseReaderCompilation:
    """Compile the fixed three-output shadow from one verified view set."""

    if type(views) is not ClauseSourceViews:
        _fail("reader_input_invalid")
    try:
        snapshot = views.verified_snapshot()
    except ClauseSourceViewError as exc:
        raise ClauseReaderShadowError("reader_input_invalid", exc.code) from exc
    if type(snapshot) is not ClauseSourceViews or snapshot is views:
        _fail("reader_input_invalid")
    fixed = _load_fixed_inputs()
    return _build_candidate_from_snapshot(snapshot, fixed)


__all__ = [
    "ClauseReaderCompilation",
    "ClauseReaderShadowError",
    "compile_clause_reader_shadow",
]
