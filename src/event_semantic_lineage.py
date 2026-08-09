"""Validate the additive OGES Event Ledger semantic-lineage sidecar.

The base Event Ledger validator remains authoritative for Claim, Episode,
Event, rights-snapshot, release, correction and count-unit semantics.  This
module validates that base bundle first and adds only registered propositions,
computed competition sets and signed lineage operations.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import event_ledger
from src import event_ledger_extension as base

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/event-semantic-lineage/0.1.0")
PROFILE_PATH = ROOT / EXTENSION / "profile.json"

_VERSION = "0.1.0"
_PROFILE_ID = "oges:extension:event_semantic_lineage"
_SELECTION_RULE = (
    "latest_authenticated_semantic_receipt_then_exact_bound_base_release_"
    "then_known_and_valid_lineage_operations"
)
_TRUST_CLASS = "synthetic_nonproduction_public_test_vector"
_STATEMENT_ID = "statement:lineage_operation_authorization_v1"
_PRODUCT_UNAVAILABLE: dict[str, Any] = {
    "status": "unavailable",
    "reason_code": "product_compiler_contract_not_bound",
    "product_compilation_ref": None,
    "affected_manifest_ids": [],
}
_HEX = set("0123456789abcdef")

ObjectKey = tuple[str, str, str]


class SemanticLineageError(ValueError):
    """Stable fail-closed semantic-lineage refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class SemanticProfile:
    document: Mapping[str, Any]
    sha256: str
    validators: Mapping[str, Draft202012Validator]
    normative_sha256: Mapping[str, str]
    predicates: Mapping[str, Mapping[str, Any]]
    opposition_rules: Mapping[str, Mapping[str, Any]]
    authorities: Mapping[str, Mapping[str, Any]]
    locators: Mapping[str, Mapping[str, Any]]
    authorization_statement: Mapping[str, Any]
    reasons: Mapping[str, Mapping[str, Any]]
    semantic_release_signers: Mapping[str, Mapping[str, Any]]
    base_profile_path: Path
    base_profile_sha256: str


@dataclass(frozen=True)
class ValidatedSemanticLineage:
    document: Mapping[str, Any]
    bundle_sha256: str
    profile: SemanticProfile
    base_validated: base.ValidatedExtension
    objects: Mapping[ObjectKey, Mapping[str, Any]]
    first_sequence: Mapping[ObjectKey, int]


def _fail(code: str, detail: str = "") -> NoReturn:
    raise SemanticLineageError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key", key)
        result[key] = value
    return result


def _parse_json_bytes(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticLineageError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    """Capture bytes once, then parse and hash that same capture."""

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SemanticLineageError(code, str(path)) from exc
    return raw, _parse_json_bytes(raw, code), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail(code)
    candidate = root.resolve()
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
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


def _sha(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return value


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


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


def typed_sha256(document: Mapping[str, object]) -> str:
    """Use the already registered Event Ledger typed canonical profile."""

    try:
        return event_ledger._typed_canonical_sha256(document)
    except event_ledger.EventLedgerError as exc:
        raise SemanticLineageError("typed_projection_invalid", exc.code) from exc


def seal_record(document: Mapping[str, object]) -> dict[str, object]:
    result = dict(document)
    result.pop("record_sha256", None)
    result["record_sha256"] = typed_sha256(result)
    return result


def _schema_error(error: Any) -> str:
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    return f"{path or '/'}:{error.validator}"


def _validate_schema(
    document: Mapping[str, Any], validator: Draft202012Validator, code: str
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        _fail(code, _schema_error(errors[0]))
    projected = dict(document)
    expected = projected.pop("record_sha256", None)
    if typed_sha256(projected) != expected:
        _fail("typed_record_digest_mismatch", str(document.get("object_type")))


def _validate_predicate_registry(
    document: Mapping[str, Any],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if (
        set(document)
        != {
            "schema_version",
            "registry_id",
            "default_policy",
            "opposition_rules",
            "predicates",
        }
        or document.get("schema_version") != _VERSION
        or document.get("registry_id") != "oges:event-semantic-lineage:predicates"
        or document.get("default_policy") != "deny"
    ):
        _fail("predicate_registry_invalid")
    rules: dict[str, Mapping[str, Any]] = {}
    for row in document["opposition_rules"]:
        if not isinstance(row, dict) or set(row) != {
            "opposition_rule_id",
            "left_stance",
            "right_stance",
            "requires_identical_ordered_arguments",
        }:
            _fail("opposition_registry_invalid")
        rule_id = row["opposition_rule_id"]
        if (
            not isinstance(rule_id, str)
            or rule_id in rules
            or {row["left_stance"], row["right_stance"]} != {"affirms", "denies"}
            or row["requires_identical_ordered_arguments"] is not True
        ):
            _fail("opposition_registry_invalid")
        rules[rule_id] = row
    predicates: dict[str, Mapping[str, Any]] = {}
    for row in document["predicates"]:
        if not isinstance(row, dict) or set(row) != {
            "predicate_id",
            "ordered_arguments",
            "opposition_rule_id",
        }:
            _fail("predicate_registry_entry_invalid")
        predicate_id = row["predicate_id"]
        arguments = row["ordered_arguments"]
        if (
            not isinstance(predicate_id, str)
            or predicate_id in predicates
            or row["opposition_rule_id"] not in rules
            or not isinstance(arguments, list)
            or not arguments
        ):
            _fail("predicate_registry_entry_invalid")
        for position, argument in enumerate(arguments):
            if not isinstance(argument, dict) or set(argument) != {
                "position",
                "name_id",
                "argument_type",
                "semantic_role",
                "allowed_value_ids",
            }:
                _fail("predicate_argument_registry_invalid", predicate_id)
            allowed = argument["allowed_value_ids"]
            if (
                argument["position"] != position
                or argument["argument_type"]
                not in {"entity_ref", "registered_term", "utc_datetime"}
                or argument["semantic_role"] not in {"context", "answer"}
                or (
                    argument["argument_type"] == "registered_term"
                    and (
                        not isinstance(allowed, list)
                        or not allowed
                        or len(allowed) != len(set(allowed))
                    )
                )
                or (argument["argument_type"] != "registered_term" and allowed is not None)
            ):
                _fail("predicate_argument_registry_invalid", predicate_id)
        roles = [argument["semantic_role"] for argument in arguments]
        if "context" not in roles or "answer" not in roles:
            _fail("predicate_argument_roles_incomplete", predicate_id)
        predicates[predicate_id] = row
    if not predicates:
        _fail("predicate_registry_empty")
    return predicates, rules


def _validate_authority_registry(
    document: Mapping[str, Any],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
    Mapping[str, Any],
]:
    if (
        set(document)
        != {
            "schema_version",
            "registry_id",
            "default_policy",
            "authorization_statement",
            "locators",
            "authorities",
        }
        or document.get("schema_version") != _VERSION
        or document.get("registry_id") != "oges:event-semantic-lineage:authorities"
        or document.get("default_policy") != "deny"
    ):
        _fail("semantic_authority_registry_invalid")
    statement = document["authorization_statement"]
    if statement != {
        "statement_id": _STATEMENT_ID,
        "trust_class": _TRUST_CLASS,
        "signed_projection": "typed_canonical_statement_v1",
    }:
        _fail("authorization_statement_registry_invalid")
    locators: dict[str, Mapping[str, Any]] = {}
    for row in document["locators"]:
        if not isinstance(row, dict) or set(row) != {
            "locator_id",
            "unit",
            "bounds",
            "locator_evidence_class",
            "allowed_actor_kinds",
        }:
            _fail("locator_registry_invalid")
        locator_id = row["locator_id"]
        if (
            not isinstance(locator_id, str)
            or locator_id in locators
            or row["unit"] not in {"utf8_byte", "metadata_field"}
            or row["bounds"] not in {"required_half_open", "forbidden"}
            or row["locator_evidence_class"]
            not in {
                "verified_source_bytes",
                "verified_evidence_metadata",
                "hash_bound_locator_unverified_span",
            }
            or not isinstance(row["allowed_actor_kinds"], list)
            or not row["allowed_actor_kinds"]
            or not set(row["allowed_actor_kinds"])
            <= {"named_entity", "publisher_only", "explicit_unknown"}
        ):
            _fail("locator_registry_invalid")
        locators[locator_id] = row
    authorities: dict[str, Mapping[str, Any]] = {}
    signer_ids: set[str] = set()
    for row in document["authorities"]:
        if not isinstance(row, dict) or set(row) != {
            "authority_id",
            "authority_kind",
            "roles",
            "allowed_locator_ids",
            "effective_from",
            "revoked_at",
            "signer_id",
            "trust_class",
            "public_key_ed25519_base64",
        }:
            _fail("semantic_authority_registry_entry_invalid")
        authority_id = row["authority_id"]
        signer_id = row["signer_id"]
        if (
            not isinstance(authority_id, str)
            or authority_id in authorities
            or not isinstance(signer_id, str)
            or signer_id in signer_ids
            or row["authority_kind"] not in {"human", "registered_deterministic_method"}
            or not isinstance(row["roles"], list)
            or not row["roles"]
            or len(row["roles"]) != len(set(row["roles"]))
            or not set(row["allowed_locator_ids"]) <= set(locators)
            or row["trust_class"] != _TRUST_CLASS
        ):
            _fail("semantic_authority_registry_entry_invalid")
        effective = _utc(row["effective_from"], "semantic_authority_time_invalid")
        revoked = (
            _utc(row["revoked_at"], "semantic_authority_time_invalid")
            if row["revoked_at"] is not None
            else None
        )
        if revoked is not None and revoked <= effective:
            _fail("semantic_authority_time_invalid")
        try:
            public = base64.b64decode(row["public_key_ed25519_base64"], validate=True)
            Ed25519PublicKey.from_public_bytes(public)
        except (ValueError, TypeError):
            _fail("semantic_authority_public_key_invalid")
        authorities[authority_id] = row
        signer_ids.add(signer_id)
    if not authorities:
        _fail("semantic_authority_registry_empty")
    return authorities, locators, statement


def _validate_reason_registry(
    document: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    if (
        set(document)
        != {
            "schema_version",
            "registry_id",
            "default_policy",
            "reasons",
        }
        or document.get("schema_version") != _VERSION
        or document.get("registry_id") != "oges:event-semantic-lineage:lineage-reasons"
        or document.get("default_policy") != "deny"
    ):
        _fail("lineage_reason_registry_invalid")
    reasons: dict[str, Mapping[str, Any]] = {}
    for row in document["reasons"]:
        if not isinstance(row, dict) or set(row) != {
            "reason_code",
            "allowed_topologies",
            "eligible_evidence_types",
            "eligible_verification_statuses",
            "required_rights_use",
        }:
            _fail("lineage_reason_registry_entry_invalid")
        code = row["reason_code"]
        if (
            not isinstance(code, str)
            or code in reasons
            or not set(row["allowed_topologies"]) <= {"supersede", "merge", "split"}
            or not row["allowed_topologies"]
            or not isinstance(row["eligible_evidence_types"], list)
            or not row["eligible_evidence_types"]
            or not isinstance(row["eligible_verification_statuses"], list)
            or not row["eligible_verification_statuses"]
            or row["required_rights_use"] != "cite_metadata"
        ):
            _fail("lineage_reason_registry_entry_invalid")
        reasons[code] = row
    return reasons


def _validate_semantic_release_signers(
    document: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    if (
        set(document)
        != {
            "schema_version",
            "registry_id",
            "default_policy",
            "signers",
        }
        or document.get("schema_version") != _VERSION
        or document.get("registry_id") != "oges:event-semantic-lineage:release-signers"
        or document.get("default_policy") != "deny"
    ):
        _fail("semantic_release_signer_registry_invalid")
    signers: dict[str, Mapping[str, Any]] = {}
    for row in document["signers"]:
        if not isinstance(row, dict) or set(row) != {
            "signer_id",
            "role",
            "effective_from",
            "revoked_at",
            "trust_class",
            "public_key_ed25519_base64",
        }:
            _fail("semantic_release_signer_invalid")
        signer_id = row["signer_id"]
        if (
            not isinstance(signer_id, str)
            or signer_id in signers
            or row["role"] != "semantic_availability_signer"
            or row["trust_class"] != _TRUST_CLASS
        ):
            _fail("semantic_release_signer_invalid")
        effective = _utc(row["effective_from"], "semantic_release_signer_time_invalid")
        revoked = (
            _utc(row["revoked_at"], "semantic_release_signer_time_invalid")
            if row["revoked_at"] is not None
            else None
        )
        if revoked is not None and revoked <= effective:
            _fail("semantic_release_signer_time_invalid")
        try:
            public = base64.b64decode(row["public_key_ed25519_base64"], validate=True)
            Ed25519PublicKey.from_public_bytes(public)
        except (ValueError, TypeError):
            _fail("semantic_release_signer_key_invalid")
        signers[signer_id] = row
    if not signers:
        _fail("semantic_release_signer_registry_empty")
    return signers


def _load_profile(root: Path, profile_path: Path) -> SemanticProfile:
    profile_file = _inside_root(root, profile_path, "semantic_profile_missing")
    _, profile, profile_sha = _read_json(profile_file, "semantic_profile_invalid")
    if set(profile) != {
        "schema_version",
        "extension_id",
        "version",
        "effective",
        "status",
        "base_event_ledger",
        "normative_files",
        "reference_implementation",
        "trust_boundary",
        "product_compiler_boundary",
        "meaning_boundary",
    }:
        _fail("semantic_profile_fields_invalid")
    if (
        profile["schema_version"] != _VERSION
        or profile["extension_id"] != _PROFILE_ID
        or profile["version"] != _VERSION
        or profile["status"] != "synthetic_nonproduction_contract_only"
    ):
        _fail("semantic_profile_identity_invalid")
    _day(profile["effective"], "semantic_profile_effective_invalid")
    base_profile = profile["base_event_ledger"]
    if (
        not isinstance(base_profile, dict)
        or set(base_profile)
        != {
            "extension_id",
            "version",
            "profile_path",
            "profile_sha256",
        }
        or base_profile["extension_id"] != "oges:extension:event_ledger"
        or base_profile["version"] != "0.1.0"
    ):
        _fail("semantic_profile_base_invalid")
    # Resolve the registered path now, but let the base validator perform the
    # single read whose captured digest is compared below.
    base_profile_path = _safe_file(
        root, base_profile["profile_path"], "semantic_profile_base_missing"
    )
    base_profile_sha = _sha(base_profile["profile_sha256"], "semantic_profile_base_digest_invalid")

    rows = profile["normative_files"]
    if not isinstance(rows, list) or not rows:
        _fail("semantic_profile_normative_files_invalid")
    documents: dict[str, dict[str, Any]] = {}
    schema_documents: dict[str, dict[str, Any]] = {}
    normative_sha: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"kind", "path", "sha256"}:
            _fail("semantic_profile_normative_file_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in normative_sha:
            _fail("semantic_profile_normative_file_duplicate")
        path = _safe_file(root, row["path"], "semantic_profile_normative_file_missing")
        try:
            raw = path.read_bytes()
        except OSError:
            _fail("semantic_profile_normative_file_missing", kind)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != _sha(row["sha256"], "semantic_profile_normative_digest_invalid"):
            _fail("semantic_profile_normative_digest_mismatch", kind)
        normative_sha[kind] = digest
        if kind not in {"specification", "test_suite"}:
            documents[kind] = _parse_json_bytes(raw, "semantic_profile_normative_file_invalid")
        if kind.endswith("_schema"):
            schema = documents[kind]
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError:
                _fail("semantic_profile_schema_meta_invalid", kind)
            schema_documents[kind] = schema
    required = {
        "common_schema",
        "claim_proposition_schema",
        "competition_set_schema",
        "lineage_operation_schema",
        "bundle_schema",
        "replay_schema",
        "predicate_registry",
        "semantic_authority_registry",
        "lineage_reason_registry",
        "semantic_release_signer_registry",
        "specification",
        "adversarial_cases",
        "test_suite",
    }
    if set(normative_sha) != required:
        _fail("semantic_profile_normative_files_incomplete")
    resources = Registry().with_resources(
        [
            (cast(str, schema["$id"]), Resource.from_contents(schema))
            for schema in schema_documents.values()
        ]
    )
    validators = {
        kind: Draft202012Validator(schema, registry=resources, format_checker=FormatChecker())
        for kind, schema in schema_documents.items()
        if kind != "common_schema"
    }
    implementation = profile["reference_implementation"]
    if not isinstance(implementation, dict) or set(implementation) != {"path", "sha256"}:
        _fail("semantic_profile_implementation_invalid")
    implementation_path = _safe_file(
        root, implementation["path"], "semantic_profile_implementation_missing"
    )
    implementation_bytes = implementation_path.read_bytes()
    implementation_sha = hashlib.sha256(implementation_bytes).hexdigest()
    if (
        implementation_sha
        != _sha(implementation["sha256"], "semantic_profile_implementation_digest_invalid")
        or implementation_sha != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ):
        _fail("semantic_profile_implementation_digest_mismatch")
    predicates, opposition = _validate_predicate_registry(documents["predicate_registry"])
    authorities, locators, statement = _validate_authority_registry(
        documents["semantic_authority_registry"]
    )
    reasons = _validate_reason_registry(documents["lineage_reason_registry"])
    semantic_release_signers = _validate_semantic_release_signers(
        documents["semantic_release_signer_registry"]
    )
    if (
        profile["trust_boundary"]
        != {
            "accepted_bundle_class": "synthetic_nonproduction",
            "production_trust": False,
            "truth_selection_authority": False,
            "event_authority": False,
            "public_value_route": False,
        }
        or profile["product_compiler_boundary"] != _PRODUCT_UNAVAILABLE
    ):
        _fail("semantic_profile_boundary_invalid")
    meaning = profile["meaning_boundary"]
    if not isinstance(meaning, dict) or set(meaning) != {
        "pass_means",
        "pass_does_not_mean",
    }:
        _fail("semantic_profile_meaning_invalid")
    return SemanticProfile(
        document=profile,
        sha256=profile_sha,
        validators=validators,
        normative_sha256=normative_sha,
        predicates=predicates,
        opposition_rules=opposition,
        authorities=authorities,
        locators=locators,
        authorization_statement=statement,
        reasons=reasons,
        semantic_release_signers=semantic_release_signers,
        base_profile_path=base_profile_path,
        base_profile_sha256=base_profile_sha,
    )


def _object_key(reference: Mapping[str, Any]) -> ObjectKey:
    return (
        cast(str, reference["object_type"]),
        cast(str, reference["object_id"]),
        cast(str, reference["record_sha256"]),
    )


def _record_ref(object_type: str, document: Mapping[str, Any]) -> dict[str, str]:
    field = {
        "event": "event_id",
        "entity": "entity_id",
        "evidence_item": "evidence_id",
        "claim": "claim_id",
        "episode": "episode_id",
    }[object_type]
    return {
        "object_type": object_type,
        "object_id": cast(str, document[field]),
        "record_sha256": cast(str, document["record_sha256"]),
    }


def _catalogs(
    validated: base.ValidatedExtension,
) -> tuple[dict[ObjectKey, Mapping[str, Any]], dict[ObjectKey, int]]:
    objects: dict[ObjectKey, Mapping[str, Any]] = {}
    first: dict[ObjectKey, int] = {}
    for sequence, loaded in enumerate(validated.ledger.releases, start=1):
        for object_type in ("entity", "evidence_item", "event"):
            for document in loaded.validated.objects[object_type].values():
                key = _object_key(_record_ref(object_type, document))
                if key in objects and objects[key] != document:
                    _fail("semantic_base_object_collision", key[1])
                objects[key] = document
                first.setdefault(key, sequence)
        snapshot = validated.document["snapshots"][sequence - 1]
        for object_type, field in (("claim", "claims"), ("episode", "episodes")):
            for document in snapshot[field]:
                key = _object_key(_record_ref(object_type, document))
                if key in objects and objects[key] != document:
                    _fail("semantic_base_object_collision", key[1])
                objects[key] = document
                first.setdefault(key, sequence)
    return objects, first


def _prefix_objects(
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    first: Mapping[ObjectKey, int],
    sequence: int,
) -> dict[ObjectKey, Mapping[str, Any]]:
    return {key: value for key, value in objects.items() if first[key] <= sequence}


def _source_rights_at(
    source: Mapping[str, Any] | None,
    when: datetime,
    required_use: str,
    code: str,
) -> None:
    if (
        source is None
        or source.get("decision_state") != "approved"
        or required_use not in source.get("permitted_uses", [])
    ):
        _fail(code)
    reviewed = _day(source.get("reviewed_on"), code)
    due = _day(source.get("review_due"), code)
    if not reviewed <= when.date() <= due:
        _fail(code)


def _authority_at(
    profile: SemanticProfile,
    authority_kind: object,
    authority_id: object,
    when: datetime,
    role: str,
    *,
    forbidden_code: str,
    missing_code: str,
    role_code: str,
    time_code: str,
) -> Mapping[str, Any]:
    if authority_kind in {"model", "agent"}:
        _fail(forbidden_code)
    row = profile.authorities.get(cast(str, authority_id))
    if row is None or row["authority_kind"] != authority_kind:
        _fail(missing_code)
    if role not in row["roles"]:
        _fail(role_code)
    effective = _utc(row["effective_from"], time_code)
    revoked = _utc(row["revoked_at"], time_code) if row["revoked_at"] is not None else None
    if when < effective or (revoked is not None and when >= revoked):
        _fail(time_code)
    return row


def locator_sha256(
    evidence_ref: Mapping[str, Any],
    content_span_sha256: str,
    locator_evidence_class: str,
    locator: Mapping[str, Any],
) -> str:
    return typed_sha256(
        {
            "evidence_ref": dict(evidence_ref),
            "content_span_sha256": content_span_sha256,
            "locator_evidence_class": locator_evidence_class,
            "locator": {
                "locator_id": locator["locator_id"],
                "start": locator["start"],
                "end": locator["end"],
                "unit": locator["unit"],
            },
        }
    )


def _validate_attribution(
    attribution: Mapping[str, Any],
    proposition: Mapping[str, Any],
    claim: Mapping[str, Any],
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
    profile: SemanticProfile,
    ledger_root: Path,
) -> None:
    actor_kind = attribution["actor_kind"]
    actor_ref = attribution["actor_entity_ref"]
    evidence_key = _object_key(attribution["evidence_ref"])
    evidence = objects.get(evidence_key)
    if evidence is None:
        _fail("attribution_evidence_record_missing")
    linked = {
        (link["evidence_id"], link["evidence_record_sha256"]) for link in claim["evidence_links"]
    }
    if (evidence_key[1], evidence_key[2]) not in linked:
        _fail("attribution_evidence_not_bound_to_claim")
    proposition_known = _utc(proposition["known_at"], "proposition_known_at_invalid")
    asserted = _utc(attribution["asserted_at"], "attribution_time_invalid")
    observed = _utc(evidence["observed_at"], "attribution_time_invalid")
    if not observed <= asserted <= proposition_known:
        _fail("attribution_time_invalid")
    _source_rights_at(
        rights.get(cast(str, evidence["source_id"])),
        proposition_known,
        "cite_metadata",
        "attribution_rights_ineligible",
    )
    locator = attribution["locator"]
    locator_id = locator["locator_id"]
    locator_rule = profile.locators.get(cast(str, locator_id))
    if locator_rule is None:
        _fail("attribution_locator_unregistered")
    if actor_kind not in locator_rule["allowed_actor_kinds"]:
        _fail("attribution_locator_actor_kind_invalid")
    if (
        locator["unit"] != locator_rule["unit"]
        or attribution["locator_evidence_class"] != locator_rule["locator_evidence_class"]
    ):
        _fail("attribution_locator_class_invalid")
    if locator_rule["bounds"] == "required_half_open":
        if (
            not isinstance(locator["start"], int)
            or isinstance(locator["start"], bool)
            or not isinstance(locator["end"], int)
            or isinstance(locator["end"], bool)
            or locator["end"] <= locator["start"]
        ):
            _fail("attribution_locator_bounds_invalid")
    elif locator["start"] is not None or locator["end"] is not None:
        _fail("attribution_locator_bounds_invalid")
    if locator["locator_sha256"] != locator_sha256(
        attribution["evidence_ref"],
        attribution["content_span_sha256"],
        attribution["locator_evidence_class"],
        locator,
    ):
        _fail("attribution_locator_digest_mismatch")
    authority = attribution["extraction_authority"]
    authority_row = _authority_at(
        profile,
        authority["authority_kind"],
        authority["authority_id"],
        proposition_known,
        "claim_attribution_extractor",
        forbidden_code="attribution_model_or_agent_authority_forbidden",
        missing_code="attribution_authority_unregistered",
        role_code="attribution_authority_role_invalid",
        time_code="attribution_authority_time_invalid",
    )
    if locator_id not in authority_row["allowed_locator_ids"]:
        _fail("attribution_authority_locator_forbidden")

    actor: Mapping[str, Any] | None = None
    if actor_ref is not None:
        actor = objects.get(_object_key(actor_ref))
        if actor is None:
            _fail("attribution_entity_record_missing")
    if actor_kind == "explicit_unknown":
        if actor_ref is not None:
            _fail("attribution_unknown_entity_forbidden")
    elif actor is None:
        _fail("attribution_entity_record_missing")

    evidence_class = attribution["locator_evidence_class"]
    if evidence_class == "verified_evidence_metadata":
        if (
            actor_kind != "publisher_only"
            or evidence["publisher_entity_id"] != actor_ref["object_id"]
            or attribution["content_span_sha256"]
            != typed_sha256({"publisher_entity_id": actor_ref["object_id"]})
        ):
            _fail("attribution_publisher_metadata_mismatch")
    elif evidence_class == "hash_bound_locator_unverified_span":
        if evidence["artifact_path"] is not None or evidence["artifact_sha256"] is not None:
            _fail("attribution_weak_locator_downgrade_forbidden")
    elif evidence_class == "verified_source_bytes":
        if evidence["artifact_path"] is None or evidence["artifact_sha256"] is None:
            _fail("attribution_source_bytes_unavailable")
        source = rights.get(cast(str, evidence["source_id"]))
        _source_rights_at(
            source,
            proposition_known,
            "model_processing",
            "attribution_rights_ineligible",
        )
        artifact = _safe_file(
            ledger_root, evidence["artifact_path"], "attribution_source_artifact_missing"
        )
        try:
            raw = artifact.read_bytes()
        except OSError:
            _fail("attribution_source_artifact_missing")
        if hashlib.sha256(raw).hexdigest() != evidence["artifact_sha256"]:
            _fail("attribution_source_artifact_digest_mismatch")
        start = cast(int, locator["start"])
        end = cast(int, locator["end"])
        if (
            end > len(raw)
            or hashlib.sha256(raw[start:end]).hexdigest() != attribution["content_span_sha256"]
        ):
            _fail("attribution_content_span_digest_mismatch")
    else:
        _fail("attribution_locator_class_invalid")


def _argument_partitions(
    proposition: Mapping[str, Any], predicate: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    context: list[Mapping[str, Any]] = []
    answers: list[Mapping[str, Any]] = []
    for value, definition in zip(proposition["ordered_arguments"], predicate["ordered_arguments"]):
        (context if definition["semantic_role"] == "context" else answers).append(value)
    return context, answers


def proposition_hashes(
    predicate_id: str,
    ordered_arguments: Sequence[Mapping[str, Any]],
    stance: str,
    predicate: Mapping[str, Any],
    event_ref: Mapping[str, Any],
) -> tuple[str, str]:
    proposition = {"ordered_arguments": list(ordered_arguments)}
    context, answers = _argument_partitions(proposition, predicate)
    competition = typed_sha256(
        {
            "predicate_id": predicate_id,
            "context_arguments": context,
            "subject_event_component_sha256": _event_component_sha256([event_ref]),
        }
    )
    position = typed_sha256({"stance": stance, "answer_arguments": answers})
    return position, competition


def _validate_proposition(
    proposition: Mapping[str, Any],
    snapshot_available: datetime,
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
    profile: SemanticProfile,
    ledger_root: Path,
) -> None:
    claim = objects.get(_object_key(proposition["claim_ref"]))
    event = objects.get(_object_key(proposition["event_ref"]))
    if claim is None:
        _fail("proposition_claim_record_missing")
    if event is None:
        _fail("proposition_event_record_missing")
    subject_key = (
        "event",
        claim["subject_event"]["event_id"],
        claim["subject_event"]["record_sha256"],
    )
    if subject_key != _object_key(proposition["event_ref"]):
        _fail("proposition_claim_event_mismatch")
    known = _utc(proposition["known_at"], "proposition_known_at_invalid")
    claim_known = _utc(claim["known_at"], "proposition_claim_known_at_invalid")
    if not claim_known <= known <= snapshot_available:
        _fail("proposition_time_invalid")
    predicate = profile.predicates.get(cast(str, proposition["predicate_id"]))
    if predicate is None:
        _fail("proposition_predicate_unregistered")
    supplied = proposition["ordered_arguments"]
    definitions = predicate["ordered_arguments"]
    if len(supplied) != len(definitions):
        _fail("proposition_argument_denominator_mismatch")
    for value, definition in zip(supplied, definitions):
        if (
            value["position"] != definition["position"]
            or value["name_id"] != definition["name_id"]
            or value["argument_type"] != definition["argument_type"]
        ):
            _fail("proposition_argument_contract_mismatch")
        if value["argument_type"] == "registered_term":
            if value["value"] not in definition["allowed_value_ids"]:
                _fail("proposition_argument_value_unregistered")
        elif value["argument_type"] == "entity_ref":
            if objects.get(_object_key(value["value"])) is None:
                _fail("proposition_argument_entity_missing")
        else:
            _utc(value["value"], "proposition_argument_time_invalid")
    expected_position, expected_competition = proposition_hashes(
        cast(str, proposition["predicate_id"]),
        supplied,
        proposition["stance"],
        predicate,
        proposition["event_ref"],
    )
    if proposition["position_sha256"] != expected_position:
        _fail("proposition_position_digest_mismatch")
    if proposition["competition_sha256"] != expected_competition:
        _fail("proposition_competition_digest_mismatch")
    seen: set[tuple[str, str, str]] = set()
    for attribution in proposition["attributions"]:
        identity = (
            attribution["actor_kind"],
            attribution["evidence_ref"]["record_sha256"],
            attribution["locator"]["locator_sha256"],
        )
        if identity in seen:
            _fail("proposition_attribution_duplicate")
        seen.add(identity)
        _validate_attribution(
            attribution, proposition, claim, objects, rights, profile, ledger_root
        )


def _proposition_ref(proposition: Mapping[str, Any]) -> dict[str, str]:
    return {
        "proposition_id": cast(str, proposition["proposition_id"]),
        "record_sha256": cast(str, proposition["record_sha256"]),
    }


def _sorted_event_refs(references: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "object_type": "event",
            "object_id": cast(str, reference["object_id"]),
            "record_sha256": cast(str, reference["record_sha256"]),
        }
        for reference in sorted(
            references,
            key=lambda row: (row["object_id"], row["record_sha256"]),
        )
    ]


def _event_component_sha256(
    references: Sequence[Mapping[str, Any]],
    status: str = "exact_event_identity",
) -> str:
    return typed_sha256({"status": status, "event_refs": _sorted_event_refs(references)})


def _event_components(
    propositions: Sequence[Mapping[str, Any]],
    operations: Sequence[Mapping[str, Any]],
) -> dict[ObjectKey, tuple[str, str, list[dict[str, str]]]]:
    parent: dict[ObjectKey, ObjectKey] = {}
    split_predecessors: set[ObjectKey] = set()
    split_successors: set[ObjectKey] = set()

    def find(key: ObjectKey) -> ObjectKey:
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    def union(left: ObjectKey, right: ObjectKey) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for proposition in propositions:
        find(_object_key(proposition["event_ref"]))
    for operation in operations:
        predecessors = [
            _object_key(row) for row in operation["predecessors"] if row["object_type"] == "event"
        ]
        successors = [
            _object_key(row) for row in operation["successors"] if row["object_type"] == "event"
        ]
        references = predecessors + successors
        if not references:
            continue
        first = references[0]
        find(first)
        for key in references[1:]:
            find(key)
        if operation["topology"] == "split":
            # A split declares the predecessor ambiguous; it does not declare
            # either successor to be the same semantic Event as the predecessor
            # or as its sibling. Only a later signed supersede/merge may create
            # such an identity mapping.
            split_predecessors.update(predecessors)
            split_successors.update(successors)
        else:
            for key in references[1:]:
                union(first, key)
    members: dict[ObjectKey, list[dict[str, str]]] = defaultdict(list)
    for key in parent:
        root = find(key)
        members[root].append({"object_type": "event", "object_id": key[1], "record_sha256": key[2]})
    result: dict[ObjectKey, tuple[str, str, list[dict[str, str]]]] = {}
    for key in parent:
        component_keys = {
            ("event", row["object_id"], row["record_sha256"]) for row in members[find(key)]
        }
        refs = _sorted_event_refs(members[find(key)])
        if component_keys & split_predecessors:
            status = "ambiguous_split_ancestor"
        elif len(refs) > 1:
            status = "normalized_lineage_identity"
        elif component_keys & split_successors:
            status = "distinct_split_branch"
        else:
            status = "exact_event_identity"
        result[key] = (_event_component_sha256(refs, status), status, refs)
    return result


def compile_competition_sets(
    propositions: Sequence[Mapping[str, Any]],
    profile: SemanticProfile,
    operations: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Compute complete, non-truth-selecting CompetitionSet objects."""

    components = _event_components(propositions, operations)
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    component_by_competition: dict[str, tuple[str, str, list[dict[str, str]]]] = {}
    for proposition in propositions:
        predicate = profile.predicates[cast(str, proposition["predicate_id"])]
        context, _ = _argument_partitions(proposition, predicate)
        component_sha, component_status, component_refs = components[
            _object_key(proposition["event_ref"])
        ]
        competition_sha = typed_sha256(
            {
                "predicate_id": proposition["predicate_id"],
                "context_arguments": context,
                "subject_event_component_sha256": component_sha,
            }
        )
        groups[competition_sha].append(proposition)
        component_by_competition[competition_sha] = (
            component_sha,
            component_status,
            component_refs,
        )
    result: list[dict[str, Any]] = []
    for competition_sha, members in sorted(groups.items()):
        predicate_id = cast(str, members[0]["predicate_id"])
        predicate = profile.predicates[predicate_id]
        context, _ = _argument_partitions(members[0], predicate)
        component_sha, component_status, component_refs = component_by_competition[competition_sha]
        positions: dict[str, dict[str, Any]] = {}
        for proposition in members:
            if proposition["predicate_id"] != predicate_id:
                _fail("competition_digest_collision")
            candidate_context, answers = _argument_partitions(proposition, predicate)
            if candidate_context != context:
                _fail("competition_digest_collision")
            position_sha = cast(str, proposition["position_sha256"])
            semantic = {
                "stance": proposition["stance"],
                "ordered_arguments": answers,
            }
            existing = positions.get(position_sha)
            if existing is None:
                positions[position_sha] = {
                    "position_sha256": position_sha,
                    **semantic,
                    "proposition_refs": [_proposition_ref(proposition)],
                }
            elif (
                existing["stance"] != semantic["stance"]
                or existing["ordered_arguments"] != semantic["ordered_arguments"]
            ):
                _fail("position_digest_collision")
            else:
                existing["proposition_refs"].append(_proposition_ref(proposition))
        position_rows = sorted(positions.values(), key=lambda row: row["position_sha256"])
        for row in position_rows:
            row["proposition_refs"] = sorted(
                row["proposition_refs"],
                key=lambda ref: (ref["proposition_id"], ref["record_sha256"]),
            )
        relations: list[dict[str, Any]] = []
        rule_id = cast(str, predicate["opposition_rule_id"])
        for left_index, left in enumerate(position_rows):
            for right in position_rows[left_index + 1 :]:
                opposed = left["ordered_arguments"] == right["ordered_arguments"] and {
                    left["stance"],
                    right["stance"],
                } == {"affirms", "denies"}
                relations.append(
                    {
                        "left_position_sha256": left["position_sha256"],
                        "right_position_sha256": right["position_sha256"],
                        "relation": "registered_opposition" if opposed else "divergence",
                        "opposition_rule_id": rule_id if opposed else None,
                    }
                )
        document = {
            "object_type": "competition_set",
            "schema_version": _VERSION,
            "competition_set_id": f"cmp:{competition_sha}",
            "record_sha256": "0" * 64,
            "predicate_id": predicate_id,
            "competition_sha256": competition_sha,
            "subject_event_component_sha256": component_sha,
            "subject_event_component_status": component_status,
            "subject_event_refs": component_refs,
            "competition_key_arguments": context,
            "positions": position_rows,
            "relations": relations,
            "proposition_denominator": len(members),
            "truth_selected": False,
        }
        result.append(cast(dict[str, Any], seal_record(document)))
    return result


def lineage_authorization_payload(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "operation_id": operation["operation_id"],
        "topology": operation["topology"],
        "predecessors": operation["predecessors"],
        "successors": operation["successors"],
        "known_at": operation["known_at"],
        "valid_from": operation["valid_from"],
        "reason_code": operation["reason_code"],
        "basis_evidence_refs": operation["basis_evidence_refs"],
        "unit_count_delta": operation["unit_count_delta"],
        "product_closure": operation["product_closure"],
    }


def lineage_authorization_statement(operation: Mapping[str, Any]) -> dict[str, Any]:
    authorization = operation["authorization"]
    return {
        "statement_id": authorization["statement_id"],
        "payload_sha256": typed_sha256(lineage_authorization_payload(operation)),
        "authority_registry_sha256": authorization["authority_registry_sha256"],
        "signer_id": authorization["signer_id"],
        "authority_id": authorization["authority_id"],
        "authority_kind": authorization["authority_kind"],
        "authority_role": authorization["authority_role"],
        "trust_class": authorization["trust_class"],
    }


def lineage_authorization_signing_bytes(operation: Mapping[str, Any]) -> bytes:
    return event_ledger._typed_canonical_bytes(lineage_authorization_statement(operation))


def semantic_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    """Hash the exact semantic snapshot content, excluding its receipt."""

    projection = dict(snapshot)
    projection.pop("semantic_receipt", None)
    return typed_sha256(projection)


def semantic_receipt_statement(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: receipt[key]
        for key in (
            "object_type",
            "schema_version",
            "receipt_id",
            "sequence",
            "previous_receipt_record_sha256",
            "snapshot_sha256",
            "semantic_available_at",
            "profile_sha256",
            "base_bundle_file_sha256",
            "base_bundle_record_sha256",
            "base_release_id",
            "base_release_manifest_record_sha256",
            "signer_registry_sha256",
            "signer_id",
            "trust_class",
        )
    }


def semantic_receipt_signing_bytes(receipt: Mapping[str, Any]) -> bytes:
    return event_ledger._typed_canonical_bytes(semantic_receipt_statement(receipt))


def _validate_semantic_receipt(
    snapshot: Mapping[str, Any],
    profile: SemanticProfile,
    base_binding: Mapping[str, Any],
    base_snapshot: Mapping[str, Any],
    sequence: int,
    previous_receipt: Mapping[str, Any] | None,
) -> None:
    receipt = snapshot["semantic_receipt"]
    projected = dict(receipt)
    expected_record_sha = projected.pop("record_sha256", None)
    if typed_sha256(projected) != expected_record_sha:
        _fail("semantic_receipt_record_digest_mismatch")
    expected_previous = previous_receipt["record_sha256"] if previous_receipt is not None else None
    if (
        receipt["sequence"] != sequence
        or receipt["previous_receipt_record_sha256"] != expected_previous
        or receipt["snapshot_sha256"] != semantic_snapshot_sha256(snapshot)
    ):
        _fail("semantic_receipt_snapshot_digest_mismatch")
    if (
        receipt["profile_sha256"] != profile.sha256
        or receipt["base_bundle_file_sha256"] != base_binding["bundle_file_sha256"]
        or receipt["base_bundle_record_sha256"] != base_binding["bundle_record_sha256"]
        or receipt["base_release_id"] != base_snapshot["release_id"]
        or receipt["base_release_manifest_record_sha256"]
        != base_snapshot["release_manifest_record_sha256"]
        or receipt["signer_registry_sha256"]
        != profile.normative_sha256["semantic_release_signer_registry"]
        or receipt["trust_class"] != _TRUST_CLASS
    ):
        _fail("semantic_receipt_binding_mismatch")
    statement_sha = typed_sha256(semantic_receipt_statement(receipt))
    if receipt["statement_sha256"] != statement_sha:
        _fail("semantic_receipt_statement_digest_mismatch")
    available = _utc(receipt["semantic_available_at"], "semantic_receipt_available_at_invalid")
    base_available = _utc(
        base_snapshot["knowledge_available_at"], "semantic_receipt_available_at_invalid"
    )
    profile_effective = _utc(
        f"{profile.document['effective']}T00:00:00Z",
        "semantic_profile_effective_invalid",
    )
    if available < base_available or available < profile_effective:
        _fail("semantic_receipt_predates_authority")
    if previous_receipt is not None and available <= _utc(
        previous_receipt["semantic_available_at"],
        "semantic_receipt_available_at_invalid",
    ):
        _fail("semantic_receipt_time_not_increasing")
    signer = profile.semantic_release_signers.get(cast(str, receipt["signer_id"]))
    if signer is None or signer["role"] != "semantic_availability_signer":
        _fail("semantic_receipt_signer_unregistered")
    signer_effective = _utc(signer["effective_from"], "semantic_receipt_signer_time_invalid")
    signer_revoked = (
        _utc(signer["revoked_at"], "semantic_receipt_signer_time_invalid")
        if signer["revoked_at"] is not None
        else None
    )
    if available < signer_effective or (signer_revoked is not None and available >= signer_revoked):
        _fail("semantic_receipt_signer_time_invalid")
    try:
        signature = base64.b64decode(receipt["signature_ed25519_base64"], validate=True)
        public = base64.b64decode(signer["public_key_ed25519_base64"], validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, semantic_receipt_signing_bytes(receipt)
        )
    except (ValueError, TypeError, InvalidSignature):
        _fail("semantic_receipt_signature_invalid")


def _intrinsic_children(
    objects: Mapping[ObjectKey, Mapping[str, Any]],
) -> dict[ObjectKey, set[ObjectKey]]:
    by_type_id: dict[tuple[str, str], ObjectKey] = {}
    for key in objects:
        if (key[0], key[1]) in by_type_id and by_type_id[(key[0], key[1])] != key:
            _fail("lineage_object_id_rewritten", key[1])
        by_type_id[(key[0], key[1])] = key
    children: dict[ObjectKey, set[ObjectKey]] = defaultdict(set)
    for key, document in objects.items():
        parent_id: object = None
        if key[0] == "event":
            parent_id = document["lifecycle"]["supersedes_id"]
        elif key[0] == "claim":
            parent_id = document["supersedes_claim_id"]
        elif key[0] == "episode":
            parent_id = document["supersedes_episode_id"]
        if parent_id is not None:
            parent = by_type_id.get((key[0], cast(str, parent_id)))
            if parent is None:
                _fail("lineage_intrinsic_parent_missing", key[1])
            children[parent].add(key)
    return children


def _object_known_at(key: ObjectKey, document: Mapping[str, Any]) -> datetime:
    if key[0] in {"claim", "episode"}:
        return _utc(document["known_at"], "lineage_successor_time_invalid")
    first_known = _utc(document["first_known_at"], "lineage_successor_time_invalid")
    created = _utc(document["provenance"]["created_at"], "lineage_successor_time_invalid")
    return max(first_known, created)


def _validate_lineage_authorization(
    operation: Mapping[str, Any], profile: SemanticProfile, known_at: datetime
) -> Mapping[str, Any]:
    authorization = operation["authorization"]
    if (
        authorization["authority_registry_sha256"]
        != profile.normative_sha256["semantic_authority_registry"]
    ):
        _fail("lineage_authority_registry_digest_mismatch")
    if (
        authorization["statement_id"] != profile.authorization_statement["statement_id"]
        or authorization["trust_class"] != profile.authorization_statement["trust_class"]
    ):
        _fail("lineage_authorization_statement_invalid")
    required_role = (
        "lineage_adjudicator"
        if operation["topology"] in {"merge", "split"}
        else authorization["authority_role"]
    )
    if operation["topology"] in {"merge", "split"} and (
        authorization["authority_kind"] != "human"
        or authorization["authority_role"] != "lineage_adjudicator"
    ):
        _fail("lineage_human_adjudicator_required")
    authority = _authority_at(
        profile,
        authorization["authority_kind"],
        authorization["authority_id"],
        known_at,
        required_role,
        forbidden_code="lineage_model_or_agent_authority_forbidden",
        missing_code="lineage_authority_unregistered",
        role_code="lineage_authority_role_invalid",
        time_code="lineage_authority_time_invalid",
    )
    if (
        authorization["authority_role"] not in authority["roles"]
        or authorization["signer_id"] != authority["signer_id"]
        or authorization["trust_class"] != authority["trust_class"]
    ):
        _fail("lineage_authority_role_invalid")
    payload_sha = typed_sha256(lineage_authorization_payload(operation))
    statement = lineage_authorization_statement(operation)
    statement_sha = typed_sha256(statement)
    if authorization["payload_sha256"] != payload_sha:
        _fail("lineage_authorization_payload_mismatch")
    if authorization["statement_sha256"] != statement_sha:
        _fail("lineage_authorization_statement_mismatch")
    try:
        signature = base64.b64decode(authorization["signature_ed25519_base64"], validate=True)
        public = base64.b64decode(authority["public_key_ed25519_base64"], validate=True)
        Ed25519PublicKey.from_public_bytes(public).verify(
            signature, lineage_authorization_signing_bytes(operation)
        )
    except (ValueError, TypeError, InvalidSignature):
        _fail("lineage_authorization_signature_invalid")
    return authority


def _validate_lineage_operation(
    operation: Mapping[str, Any],
    snapshot_available: datetime,
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
    profile: SemanticProfile,
    intrinsic: Mapping[ObjectKey, set[ObjectKey]],
) -> None:
    topology = operation["topology"]
    predecessors = [_object_key(row) for row in operation["predecessors"]]
    successors = [_object_key(row) for row in operation["successors"]]
    if len(predecessors) != len(set(predecessors)) or len(successors) != len(set(successors)):
        _fail("lineage_endpoint_duplicate")
    cardinality = (len(predecessors), len(successors))
    if not (
        (topology == "supersede" and cardinality == (1, 1))
        or (topology == "merge" and cardinality[0] >= 2 and cardinality[1] == 1)
        or (topology == "split" and cardinality[0] == 1 and cardinality[1] >= 2)
    ):
        _fail("lineage_topology_invalid")
    if set(predecessors) & set(successors):
        _fail("lineage_self_reference")
    object_types = {key[0] for key in predecessors + successors}
    if len(object_types) != 1:
        _fail("lineage_object_type_mismatch")
    object_type = next(iter(object_types))
    if object_type not in {"event", "episode", "claim"}:
        _fail("lineage_object_type_invalid")
    for key in predecessors + successors:
        if key not in objects:
            _fail("lineage_endpoint_record_missing", key[1])
    known = _utc(operation["known_at"], "lineage_known_at_invalid")
    valid_from = _utc(operation["valid_from"], "lineage_valid_from_invalid")
    if known > snapshot_available:
        _fail("lineage_snapshot_time_invalid")
    authority = _validate_lineage_authorization(operation, profile, known)
    reason = profile.reasons.get(cast(str, operation["reason_code"]))
    if reason is None or topology not in reason["allowed_topologies"]:
        _fail("lineage_reason_unregistered")
    basis_keys = [_object_key(row) for row in operation["basis_evidence_refs"]]
    if len(basis_keys) != len(set(basis_keys)):
        _fail("lineage_basis_evidence_duplicate")
    for key in basis_keys:
        evidence = objects.get(key)
        if evidence is None:
            _fail("lineage_basis_evidence_missing")
        observed = _utc(evidence["observed_at"], "lineage_basis_time_invalid")
        if observed > known:
            _fail("lineage_basis_time_invalid")
        if (
            evidence["evidence_type"] not in reason["eligible_evidence_types"]
            or evidence["verification_status"] not in reason["eligible_verification_statuses"]
        ):
            _fail("lineage_basis_evidence_ineligible")
        _source_rights_at(
            rights.get(cast(str, evidence["source_id"])),
            known,
            cast(str, reason["required_rights_use"]),
            "lineage_basis_rights_ineligible",
        )
    expected_delta = {"event": 0, "episode": 0, "claim": 0}
    expected_delta[object_type] = len(successors) - len(predecessors)
    if operation["unit_count_delta"] != expected_delta:
        _fail("lineage_unit_count_delta_mismatch")
    if operation["product_closure"] != _PRODUCT_UNAVAILABLE:
        _fail("product_compiler_contract_not_bound")

    for successor_key in successors:
        successor = objects[successor_key]
        if _object_known_at(successor_key, successor) > known:
            _fail("lineage_successor_future", successor_key[1])
        if (
            successor_key[0] in {"claim", "episode"}
            and _utc(successor["valid_from"], "lineage_successor_valid_from_invalid") != valid_from
        ):
            _fail("lineage_successor_valid_time_mismatch")
        if successor_key[0] == "event":
            coding = successor["coding"]
            reviewed = set(successor["provenance"]["reviewed_by"])
            named = set(coding["coder_ids"]) | set(coding["adjudicator_ids"])
            authority_id = authority["authority_id"]
            if (
                coding["status"] == "machine_candidate"
                or authority_id not in named
                or authority_id not in reviewed
                or (
                    topology in {"merge", "split"}
                    and authority_id not in set(coding["adjudicator_ids"])
                )
            ):
                _fail("lineage_event_signed_human_provenance_mismatch")

    if topology == "supersede":
        if intrinsic.get(predecessors[0], set()) != {successors[0]}:
            _fail("lineage_intrinsic_supersession_mismatch")
    else:
        if any(intrinsic.get(predecessor, set()) for predecessor in predecessors):
            _fail("lineage_hidden_intrinsic_fork")
        for successor_key in successors:
            successor = objects[successor_key]
            parent = (
                successor["lifecycle"]["supersedes_id"]
                if successor_key[0] == "event"
                else successor[
                    {
                        "claim": "supersedes_claim_id",
                        "episode": "supersedes_episode_id",
                    }[successor_key[0]]
                ]
            )
            if parent is not None:
                _fail("lineage_merge_split_successor_not_root")


def _validate_lineage_graph(operations: Sequence[Mapping[str, Any]]) -> None:
    consumed: dict[ObjectKey, str] = {}
    produced: dict[ObjectKey, str] = {}
    adjacency: dict[ObjectKey, set[ObjectKey]] = defaultdict(set)
    known_by_operation: dict[str, datetime] = {}
    valid_by_operation: dict[str, datetime] = {}
    producer: dict[ObjectKey, str] = {}
    for operation in operations:
        operation_id = cast(str, operation["operation_id"])
        known_by_operation[operation_id] = _utc(operation["known_at"], "lineage_known_at_invalid")
        valid_by_operation[operation_id] = _utc(
            operation["valid_from"], "lineage_valid_from_invalid"
        )
        predecessors = [_object_key(row) for row in operation["predecessors"]]
        successors = [_object_key(row) for row in operation["successors"]]
        for predecessor in predecessors:
            if predecessor in consumed:
                _fail("lineage_predecessor_double_consumed", predecessor[1])
            consumed[predecessor] = operation_id
            for successor in successors:
                adjacency[predecessor].add(successor)
        for successor in successors:
            if successor in produced:
                _fail("lineage_successor_double_produced", successor[1])
            produced[successor] = operation_id
            producer[successor] = operation_id
    for predecessor, consumer_id in consumed.items():
        producer_id = producer.get(predecessor)
        if producer_id is not None and (
            known_by_operation[consumer_id] < known_by_operation[producer_id]
            or valid_by_operation[consumer_id] < valid_by_operation[producer_id]
        ):
            _fail("lineage_chain_time_invalid", predecessor[1])
    indegree: dict[ObjectKey, int] = defaultdict(int)
    nodes = set(adjacency)
    for outgoing in adjacency.values():
        nodes.update(outgoing)
        for successor in outgoing:
            indegree[successor] += 1
    pending = deque(sorted(node for node in nodes if indegree[node] == 0))
    visited = 0
    while pending:
        current = pending.popleft()
        visited += 1
        for successor in sorted(adjacency.get(current, set())):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                pending.append(successor)
    if visited != len(nodes):
        _fail("lineage_cycle")


def _validate_cumulative_history(snapshots: Sequence[Mapping[str, Any]]) -> None:
    previous_propositions: dict[str, str] = {}
    previous_operations: dict[str, str] = {}
    for snapshot in snapshots:
        propositions = {
            cast(str, row["proposition_id"]): cast(str, row["record_sha256"])
            for row in snapshot["claim_propositions"]
        }
        operations = {
            cast(str, row["operation_id"]): cast(str, row["record_sha256"])
            for row in snapshot["lineage_operations"]
        }
        if len(propositions) != len(snapshot["claim_propositions"]):
            _fail("proposition_id_duplicate")
        if len(operations) != len(snapshot["lineage_operations"]):
            _fail("lineage_operation_id_duplicate")
        missing_propositions = set(previous_propositions) - set(propositions)
        missing_operations = set(previous_operations) - set(operations)
        if missing_propositions:
            _fail("proposition_archive_removed", sorted(missing_propositions)[0])
        if missing_operations:
            _fail("lineage_archive_operation_removed", sorted(missing_operations)[0])
        for proposition_id in set(previous_propositions) & set(propositions):
            if previous_propositions[proposition_id] != propositions[proposition_id]:
                _fail("proposition_archive_rewritten", proposition_id)
        for operation_id in set(previous_operations) & set(operations):
            if previous_operations[operation_id] != operations[operation_id]:
                _fail("lineage_archive_operation_rewritten", operation_id)
        previous_propositions = propositions
        previous_operations = operations


def _validate_snapshot_identity(
    snapshot: Mapping[str, Any], base_snapshot: Mapping[str, Any], sequence: int
) -> None:
    if snapshot["sequence"] != sequence or any(
        snapshot[field] != base_snapshot[field]
        for field in (
            "release_id",
            "release_manifest_record_sha256",
            "knowledge_available_at",
        )
    ):
        _fail("semantic_snapshot_identity_mismatch")
    if snapshot["archive_counts"] != {
        "claim_propositions": len(snapshot["claim_propositions"]),
        "competition_sets": len(snapshot["competition_sets"]),
        "lineage_operations": len(snapshot["lineage_operations"]),
    }:
        _fail("semantic_snapshot_archive_counts_mismatch")
    if snapshot["source_count_units"] != base_snapshot["count_units"]:
        _fail("source_count_units_mismatch")


def validate_bundle(
    bundle_path: Path,
    *,
    base_bundle_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> ValidatedSemanticLineage:
    """Validate one synthetic semantic-lineage sidecar and its exact base."""

    profile = _load_profile(root, profile_path)
    bundle_file = _inside_root(root, bundle_path, "semantic_bundle_missing")
    _, bundle, bundle_sha = _read_json(bundle_file, "semantic_bundle_invalid")
    _validate_schema(bundle, profile.validators["bundle_schema"], "object_schema_invalid")
    if bundle["profile_sha256"] != profile.sha256:
        _fail("semantic_profile_digest_mismatch")
    if bundle["product_compiler_boundary"] != _PRODUCT_UNAVAILABLE:
        _fail("product_compiler_contract_not_bound")
    base_file = _inside_root(root, base_bundle_path, "base_event_ledger_bundle_missing")
    try:
        validated_base = base.validate_bundle(
            base_file,
            root=root,
            profile_path=profile.base_profile_path,
        )
    except base.EventLedgerExtensionError as exc:
        raise SemanticLineageError("base_event_ledger_invalid", exc.code) from exc
    base_binding = bundle["base_event_ledger"]
    if (
        validated_base.profile.sha256 != profile.base_profile_sha256
        or base_binding["profile_sha256"] != profile.base_profile_sha256
    ):
        _fail("base_event_ledger_profile_digest_mismatch")
    if base_binding["bundle_file_sha256"] != validated_base.bundle_sha256:
        _fail("base_event_ledger_bundle_digest_mismatch")
    if base_binding["bundle_record_sha256"] != validated_base.document["record_sha256"]:
        _fail("base_event_ledger_record_digest_mismatch")
    snapshots = cast(list[Mapping[str, Any]], bundle["snapshots"])
    base_snapshots = validated_base.document["snapshots"]
    if len(snapshots) != len(base_snapshots):
        _fail("semantic_snapshot_release_denominator_mismatch")
    _validate_cumulative_history(snapshots)
    objects, first = _catalogs(validated_base)
    proposition_validator = profile.validators["claim_proposition_schema"]
    competition_validator = profile.validators["competition_set_schema"]
    operation_validator = profile.validators["lineage_operation_schema"]
    previous_receipt: Mapping[str, Any] | None = None
    for sequence, (snapshot, base_snapshot, loaded) in enumerate(
        zip(snapshots, base_snapshots, validated_base.ledger.releases), start=1
    ):
        _validate_snapshot_identity(snapshot, base_snapshot, sequence)
        _validate_semantic_receipt(
            snapshot,
            profile,
            base_binding,
            base_snapshot,
            sequence,
            previous_receipt,
        )
        previous_receipt = snapshot["semantic_receipt"]
        available = _utc(snapshot["knowledge_available_at"], "semantic_snapshot_available_invalid")
        prefix = _prefix_objects(objects, first, sequence)
        intrinsic = _intrinsic_children(prefix)
        try:
            rights = base._rights_for_release(validated_base.ledger_root, loaded)
        except base.EventLedgerExtensionError as exc:
            raise SemanticLineageError("semantic_rights_registry_invalid", exc.code) from exc
        for proposition in snapshot["claim_propositions"]:
            _validate_schema(proposition, proposition_validator, "object_schema_invalid")
            _validate_proposition(
                proposition,
                available,
                prefix,
                rights,
                profile,
                validated_base.ledger_root,
            )
        for operation in snapshot["lineage_operations"]:
            _validate_schema(operation, operation_validator, "object_schema_invalid")
            _validate_lineage_operation(operation, available, prefix, rights, profile, intrinsic)
        _validate_lineage_graph(snapshot["lineage_operations"])
        expected_competitions = compile_competition_sets(
            snapshot["claim_propositions"],
            profile,
            snapshot["lineage_operations"],
        )
        for competition in snapshot["competition_sets"]:
            _validate_schema(competition, competition_validator, "object_schema_invalid")
        if snapshot["competition_sets"] != expected_competitions:
            _fail("competition_sets_recomputation_mismatch")
    return ValidatedSemanticLineage(
        document=bundle,
        bundle_sha256=bundle_sha,
        profile=profile,
        base_validated=validated_base,
        objects=objects,
        first_sequence=first,
    )


def _effective(document: Mapping[str, Any], valid_on: date, object_type: str) -> bool:
    if object_type == "event":
        start = _utc(document["starts_at"], "semantic_event_start_invalid").date()
        end = (
            _utc(document["ends_at"], "semantic_event_end_invalid").date()
            if document["ends_at"] is not None
            else None
        )
        return valid_on >= start and (end is None or valid_on <= end)
    start = _utc(document["valid_from"], "semantic_object_valid_from_invalid").date()
    end = (
        _utc(document["valid_to"], "semantic_object_valid_to_invalid").date()
        if document["valid_to"] is not None
        else None
    )
    return valid_on >= start and (end is None or valid_on <= end)


def _base_active_keys(base_replay: Mapping[str, Any]) -> dict[str, set[ObjectKey]]:
    result: dict[str, set[ObjectKey]] = {"event": set(), "episode": set(), "claim": set()}
    for row in base_replay["events"]:
        if row["effective_on_valid_date"]:
            result["event"].add(("event", row["event_id"], row["record_sha256"]))
    for row in base_replay["episodes"]:
        if row["effective_on_valid_date"]:
            result["episode"].add(("episode", row["episode_id"], row["record_sha256"]))
    for row in base_replay["claims"]:
        if row["effective_on_valid_date"]:
            result["claim"].add(("claim", row["claim_id"], row["record_sha256"]))
    return result


def _operation_ref(operation: Mapping[str, Any]) -> dict[str, str]:
    return {
        "operation_id": cast(str, operation["operation_id"]),
        "record_sha256": cast(str, operation["record_sha256"]),
    }


def _operation_temporal_key(operation: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        cast(str, operation["known_at"]),
        cast(str, operation["valid_from"]),
        cast(str, operation["operation_id"]),
    )


def _topological_operation_order(
    operations: Sequence[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], dict[ObjectKey, str]]:
    """Order producer operations before consumers with deterministic tie breaks."""

    by_id = {cast(str, row["operation_id"]): row for row in operations}
    producer: dict[ObjectKey, str] = {}
    for operation in operations:
        operation_id = cast(str, operation["operation_id"])
        for successor in operation["successors"]:
            producer[_object_key(successor)] = operation_id
    dependencies: dict[str, set[str]] = {operation_id: set() for operation_id in by_id}
    dependents: dict[str, set[str]] = defaultdict(set)
    for operation in operations:
        operation_id = cast(str, operation["operation_id"])
        for predecessor in operation["predecessors"]:
            producer_id = producer.get(_object_key(predecessor))
            if producer_id is not None and producer_id != operation_id:
                dependencies[operation_id].add(producer_id)
                dependents[producer_id].add(operation_id)
    ready = sorted(
        (operation_id for operation_id, rows in dependencies.items() if not rows),
        key=lambda operation_id: _operation_temporal_key(by_id[operation_id]),
    )
    ordered: list[Mapping[str, Any]] = []
    while ready:
        operation_id = ready.pop(0)
        ordered.append(by_id[operation_id])
        for dependent_id in sorted(dependents.get(operation_id, set())):
            dependencies[dependent_id].discard(operation_id)
            if not dependencies[dependent_id]:
                ready.append(dependent_id)
        ready.sort(key=lambda row: _operation_temporal_key(by_id[row]))
    if len(ordered) != len(operations):
        _fail("lineage_cycle")
    return ordered, producer


def _apply_operations(
    active: dict[str, set[ObjectKey]],
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    operations: Sequence[Mapping[str, Any]],
    cutoff: datetime,
    valid_day: date,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    ordered, producer = _topological_operation_order(operations)
    applied: list[dict[str, str]] = []
    pending: list[dict[str, str]] = []
    applied_ids: set[str] = set()
    for operation in ordered:
        applicable = (
            _utc(operation["known_at"], "lineage_known_at_invalid") <= cutoff
            and _utc(operation["valid_from"], "lineage_valid_from_invalid").date() <= valid_day
        )
        if not applicable:
            pending.append(_operation_ref(operation))
            continue
        for predecessor in operation["predecessors"]:
            producer_id = producer.get(_object_key(predecessor))
            if producer_id is not None and producer_id not in applied_ids:
                _fail("lineage_consumer_producer_unavailable")
        for predecessor in operation["predecessors"]:
            key = _object_key(predecessor)
            active[key[0]].discard(key)
        for successor in operation["successors"]:
            key = _object_key(successor)
            if _effective(objects[key], valid_day, key[0]):
                active[key[0]].add(key)
        applied.append(_operation_ref(operation))
        applied_ids.add(cast(str, operation["operation_id"]))
    return applied, pending


def replay_validated(
    validated: ValidatedSemanticLineage,
    knowledge_cutoff: str,
    valid_on: str,
) -> dict[str, Any]:
    cutoff = _utc(knowledge_cutoff, "semantic_knowledge_cutoff_invalid")
    valid_day = _day(valid_on, "semantic_valid_on_invalid")
    eligible = [
        (index, snapshot)
        for index, snapshot in enumerate(validated.document["snapshots"])
        if _utc(
            snapshot["semantic_receipt"]["semantic_available_at"],
            "semantic_receipt_available_at_invalid",
        )
        <= cutoff
    ]
    if not eligible:
        _fail("semantic_knowledge_cutoff_before_first_receipt")
    selected_index, snapshot = eligible[-1]
    selected_base = validated.base_validated.ledger.releases[selected_index]
    base_cutoff = cast(str, selected_base.entry["available_at"])
    base_replay = base.replay_validated(validated.base_validated, base_cutoff, valid_on)
    selected_sequence = selected_index + 1
    if base_replay["selected_release"]["sequence"] != selected_sequence:
        _fail("semantic_replay_base_selection_mismatch")
    active = _base_active_keys(base_replay)
    operations = list(snapshot["lineage_operations"])
    all_successors = {
        _object_key(successor) for operation in operations for successor in operation["successors"]
    }
    all_predecessors = {
        _object_key(predecessor)
        for operation in operations
        for predecessor in operation["predecessors"]
    }
    for key in all_successors:
        active[key[0]].discard(key)
    for key in all_predecessors - all_successors:
        predecessor_document = validated.objects[key]
        if _effective(predecessor_document, valid_day, key[0]):
            active[key[0]].add(key)
    applied, pending = _apply_operations(active, validated.objects, operations, cutoff, valid_day)
    active_sets = {
        object_type: [
            {
                "object_type": key[0],
                "object_id": key[1],
                "record_sha256": key[2],
            }
            for key in sorted(active[object_type])
        ]
        for object_type in ("event", "episode", "claim")
    }
    receipt = snapshot["semantic_receipt"]
    query = {
        "knowledge_cutoff": knowledge_cutoff,
        "valid_on": valid_on,
        "selection_rule": _SELECTION_RULE,
    }
    base_binding = validated.document["base_event_ledger"]
    document: dict[str, Any] = {
        "object_type": "event_semantic_lineage_replay",
        "schema_version": _VERSION,
        "record_sha256": "0" * 64,
        "trust_class": "synthetic_nonproduction",
        "production_trust": False,
        "query": query,
        "selected_release": {
            "sequence": selected_sequence,
            "release_id": base_replay["selected_release"]["release_id"],
            "manifest_record_sha256": base_replay["selected_release"]["manifest_record_sha256"],
            "base_available_at": base_replay["selected_release"]["available_at"],
            "semantic_available_at": receipt["semantic_available_at"],
            "semantic_receipt_id": receipt["receipt_id"],
            "semantic_receipt_record_sha256": receipt["record_sha256"],
        },
        "proof": {
            "verification_method": "full_offline_recomputation_v1",
            "semantic_profile_sha256": validated.profile.sha256,
            "semantic_runtime_sha256": validated.profile.document["reference_implementation"][
                "sha256"
            ],
            "semantic_bundle_file_sha256": validated.bundle_sha256,
            "semantic_bundle_record_sha256": validated.document["record_sha256"],
            "semantic_snapshot_sha256": semantic_snapshot_sha256(snapshot),
            "semantic_receipt_record_sha256": receipt["record_sha256"],
            "base_profile_sha256": validated.base_validated.profile.sha256,
            "base_runtime_sha256": validated.base_validated.profile.document[
                "reference_implementation"
            ]["sha256"],
            "base_bundle_file_sha256": base_binding["bundle_file_sha256"],
            "base_bundle_record_sha256": base_binding["bundle_record_sha256"],
            "query_sha256": typed_sha256(query),
        },
        "active_sets": active_sets,
        "active_counts": {
            object_type: len(active_sets[object_type])
            for object_type in ("event", "episode", "claim")
        },
        "claim_proposition_refs": sorted(
            [_proposition_ref(row) for row in snapshot["claim_propositions"]],
            key=lambda row: (row["proposition_id"], row["record_sha256"]),
        ),
        "competition_sets": snapshot["competition_sets"],
        "applied_lineage_operation_refs": applied,
        "pending_lineage_operation_refs": pending,
        "source_count_units": snapshot["source_count_units"],
        "product_compiler_boundary": _PRODUCT_UNAVAILABLE,
        "truth_selected": False,
        "limitations": sorted(
            [
                "limitation:competition_is_not_truth_selection",
                "limitation:event_episode_claim_counts_are_separate",
                "limitation:hash_bound_locator_may_be_unverified",
                "limitation:lineage_operation_is_not_substantive_truth",
                "limitation:product_compiler_contract_not_bound",
                "limitation:synthetic_fixture_is_not_production_trust",
                "limitation:valid_time_is_separate_from_knowledge_time",
            ]
        ),
    }
    sealed = cast(dict[str, Any], seal_record(document))
    _validate_schema(
        sealed,
        validated.profile.validators["replay_schema"],
        "semantic_replay_schema_invalid",
    )
    return sealed


def verify_replay(
    replay_document: Mapping[str, Any],
    bundle_path: Path,
    *,
    base_bundle_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    """Fully recompute a supplied replay from its exact proof-bound inputs."""

    validated = validate_bundle(
        bundle_path,
        base_bundle_path=base_bundle_path,
        root=root,
        profile_path=profile_path,
    )
    _validate_schema(
        replay_document,
        validated.profile.validators["replay_schema"],
        "semantic_replay_schema_invalid",
    )
    query = replay_document["query"]
    expected = replay_validated(
        validated,
        query["knowledge_cutoff"],
        query["valid_on"],
    )
    if replay_document != expected:
        _fail("semantic_replay_recomputation_mismatch")
    return {
        "status": "verified_full_semantic_replay_recomputation",
        "record_sha256": replay_document["record_sha256"],
        "semantic_bundle_file_sha256": replay_document["proof"]["semantic_bundle_file_sha256"],
        "base_bundle_file_sha256": replay_document["proof"]["base_bundle_file_sha256"],
        "production_trust": False,
    }


def replay(
    bundle_path: Path,
    knowledge_cutoff: str,
    valid_on: str,
    *,
    base_bundle_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    return replay_validated(
        validate_bundle(
            bundle_path,
            base_bundle_path=base_bundle_path,
            root=root,
            profile_path=profile_path,
        ),
        knowledge_cutoff,
        valid_on,
    )


def summary(validated: ValidatedSemanticLineage) -> dict[str, Any]:
    latest = validated.document["snapshots"][-1]
    return {
        "status": "conformant_synthetic_event_semantic_lineage",
        "extension_id": _PROFILE_ID,
        "version": _VERSION,
        "profile_sha256": validated.profile.sha256,
        "base_event_ledger_bundle_sha256": validated.base_validated.bundle_sha256,
        "snapshots": len(validated.document["snapshots"]),
        "latest_archive_counts": latest["archive_counts"],
        "product_compiler_boundary": _PRODUCT_UNAVAILABLE,
        "truth_selection_authority": False,
        "production_trust": False,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate or replay the OGES Event Ledger semantic-lineage sidecar"
    )
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--base-event-bundle", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--knowledge-cutoff")
    parser.add_argument("--valid-on")
    args = parser.parse_args(argv)
    try:
        if (args.knowledge_cutoff is None) != (args.valid_on is None):
            _fail("semantic_replay_query_incomplete")
        kwargs = {
            "base_bundle_path": args.base_event_bundle,
            "root": args.root,
            "profile_path": args.root / EXTENSION / "profile.json",
        }
        if args.knowledge_cutoff is None:
            result = summary(validate_bundle(args.bundle, **kwargs))
        else:
            result = replay(
                args.bundle,
                args.knowledge_cutoff,
                args.valid_on,
                **kwargs,
            )
    except (SemanticLineageError, base.EventLedgerExtensionError) as exc:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": getattr(exc, "code", "base_event_ledger_invalid"),
                    "detail": getattr(exc, "detail", ""),
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
