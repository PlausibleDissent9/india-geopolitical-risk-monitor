"""Validate immutable canonical-object releases for IGRM Max.

The JSON Schemas define the object shapes. This module enforces the invariants
that a schema cannot establish alone: registered schema bytes, canonical record
hashes, exact release membership, source-rights approval, referential integrity,
temporal ordering, universe denominators and honest exposure quantification.

Validation is offline and emits identifiers and counts only, never evidence or
measurement values.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, Union, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import publication_guard

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_REGISTRY = ROOT / "governance" / "canonical_schema_registry.json"
RIGHTS_REGISTRY = ROOT / "governance" / "source_rights_registry.json"
RIGHTS_SIGNERS = ROOT / "governance" / "rights_signers.json"
METHOD_REGISTRY = ROOT / "governance" / "canonical_method_registry.json"
RELEASE_SIGNERS = ROOT / "governance" / "release_signers.json"

JsonValue = Union[dict[str, Any], list[Any], str, int, float, bool, None]

_OBJECT_TYPES = {
    "evidence_item",
    "entity",
    "event",
    "exposure_edge",
    "universe_release",
}
_REGISTRY_TYPES = _OBJECT_TYPES | {
    "common_definitions",
    "canonical_release",
    "universe_frame",
}
_ID_FIELD = {
    "evidence_item": "evidence_id",
    "entity": "entity_id",
    "event": "event_id",
    "exposure_edge": "edge_id",
    "universe_release": "universe_release_id",
    "canonical_release": "release_id",
}
_HEX = set("0123456789abcdef")


class CanonicalObjectError(ValueError):
    """A fail-closed release refusal with a stable code and bounded detail."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ValidatedCanonicalRelease:
    """Validated records for trusted in-process projections.

    Public validation continues to return only :attr:`summary`. Keeping the
    loaded records attached to the successful validation pass prevents a
    downstream projection from rereading mutable paths after signature and
    digest checks have completed.
    """

    manifest: Mapping[str, Any]
    objects: Mapping[str, Mapping[str, Mapping[str, Any]]]
    summary: Mapping[str, object]


def _fail(code: str, detail: str = "") -> NoReturn:
    raise CanonicalObjectError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    _fail("json_non_finite")


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(parsed, dict):
        _fail(code)
    return raw, cast(dict[str, Any], parsed), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        _fail(code)
    root_resolved = root.resolve()
    candidate = root_resolved
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _path_inside_root(root: Path, path: Path, code: str) -> Path:
    try:
        relative = str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        _fail(code)
    return _safe_file(root, relative, code)


def _sha(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in _HEX for char in value)
    ):
        _fail(code)
    return value


def _parse_date(value: object, code: str) -> date:
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
    return parsed


def canonical_record_sha256(document: Mapping[str, object]) -> str:
    """Hash canonical JSON after removing the self-referential record hash."""

    unsigned = dict(document)
    unsigned.pop("record_sha256", None)
    try:
        encoded = json.dumps(
            unsigned,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("record_not_canonical_json")
    return hashlib.sha256(encoded).hexdigest()


def seal_record(document: Mapping[str, object]) -> dict[str, object]:
    """Return a copy carrying its canonical self-hash."""

    sealed = dict(document)
    sealed["record_sha256"] = canonical_record_sha256(sealed)
    return sealed


def _schema_error_detail(error: Any) -> str:
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    if path == "/":
        path = ""
    return f"{path or '/'}:{error.validator}"


def _load_schema_registry(
    root: Path, registry_path: Path
) -> tuple[dict[str, Any], dict[str, Any], str]:
    registry_file = _path_inside_root(root, registry_path, "schema_registry_missing")
    _, document, registry_sha = _read_json(
        registry_file, "schema_registry_unreadable"
    )
    if set(document) != {
        "schema_version",
        "effective",
        "default_policy",
        "schemas",
    }:
        _fail("schema_registry_fields_invalid")
    if document["schema_version"] != "1.0.0" or document["default_policy"] != "deny":
        _fail("schema_registry_policy_invalid")
    _parse_date(document["effective"], "schema_registry_effective_invalid")
    rows = document["schemas"]
    if not isinstance(rows, list):
        _fail("schema_registry_entries_invalid")
    expected_fields = {"object_type", "schema_id", "version", "path", "sha256"}
    schemas: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            _fail("schema_registry_entry_invalid")
        object_type = raw["object_type"]
        if not isinstance(object_type, str) or object_type not in _REGISTRY_TYPES:
            _fail("schema_registry_object_type_invalid")
        if object_type in schemas:
            _fail("schema_registry_duplicate", object_type)
        if raw["version"] != "1.0.0":
            _fail("schema_registry_version_invalid", object_type)
        path = _safe_file(root, raw["path"], "schema_file_missing")
        content, schema, actual_sha = _read_json(path, "schema_file_invalid")
        expected_sha = _sha(raw["sha256"], "schema_digest_invalid")
        if hashlib.sha256(content).hexdigest() != actual_sha or actual_sha != expected_sha:
            _fail("schema_digest_mismatch", object_type)
        if schema.get("$id") != raw["schema_id"]:
            _fail("schema_id_mismatch", object_type)
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            _fail("schema_meta_validation_failed", object_type)
        schemas[object_type] = schema
    if set(schemas) != _REGISTRY_TYPES:
        _fail("schema_registry_incomplete")

    resources = [
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    ]
    reference_registry = Registry().with_resources(resources)
    validators = {
        object_type: Draft202012Validator(
            schema,
            registry=reference_registry,
            format_checker=FormatChecker(),
        )
        for object_type, schema in schemas.items()
        if object_type != "common_definitions"
    }
    return schemas, validators, registry_sha


def _load_method_registry(
    root: Path, registry_path: Path
) -> tuple[dict[tuple[str, str], dict[str, Any]], str]:
    registry_file = _path_inside_root(root, registry_path, "method_registry_missing")
    _, document, registry_sha = _read_json(
        registry_file, "method_registry_unreadable"
    )
    if set(document) != {
        "schema_version",
        "effective",
        "default_policy",
        "methods",
    }:
        _fail("method_registry_fields_invalid")
    if document["schema_version"] != "1.0.0" or document["default_policy"] != "deny":
        _fail("method_registry_policy_invalid")
    _parse_date(document["effective"], "method_registry_effective_invalid")
    rows = document["methods"]
    if not isinstance(rows, list):
        _fail("method_registry_entries_invalid")
    expected = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "allowed_object_types",
        "effective",
        "superseded_on",
    }
    methods: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != expected:
            _fail("method_registry_entry_invalid")
        method_id = raw["method_id"]
        version = raw["version"]
        if not isinstance(method_id, str) or not isinstance(version, str):
            _fail("method_registry_identity_invalid")
        key = (method_id, version)
        if key in methods:
            _fail("method_registry_duplicate", method_id)
        path = _safe_file(root, raw["implementation_path"], "method_implementation_missing")
        expected_sha = _sha(raw["implementation_sha256"], "method_digest_invalid")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            _fail("method_implementation_digest_mismatch", method_id)
        allowed = raw["allowed_object_types"]
        if (
            not isinstance(allowed, list)
            or not allowed
            or any(not isinstance(item, str) or item not in _OBJECT_TYPES for item in allowed)
            or len(allowed) != len(set(allowed))
        ):
            _fail("method_object_types_invalid", method_id)
        effective = _parse_date(raw["effective"], "method_effective_invalid")
        if raw["superseded_on"] is not None and _parse_date(
            raw["superseded_on"], "method_superseded_invalid"
        ) <= effective:
            _fail("method_superseded_invalid", method_id)
        methods[key] = raw
    return methods, registry_sha


def _validate_method(
    method: Mapping[str, Any],
    object_type: str,
    effective_date: date,
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    registered = methods.get((method["method_id"], method["version"]))
    if registered is None:
        _fail("method_unregistered", cast(str, method["method_id"]))
    if object_type not in registered["allowed_object_types"]:
        _fail("method_object_type_forbidden", object_type)
    if method["implementation_sha256"] != registered["implementation_sha256"]:
        _fail("method_digest_mismatch", cast(str, method["method_id"]))
    if effective_date < _parse_date(registered["effective"], "method_effective_invalid"):
        _fail("method_not_effective", cast(str, method["method_id"]))
    superseded = registered["superseded_on"]
    if superseded is not None and effective_date >= _parse_date(
        superseded, "method_superseded_invalid"
    ):
        _fail("method_superseded", cast(str, method["method_id"]))


def _validate_schema(
    document: Mapping[str, object], object_type: str, validators: Mapping[str, Any]
) -> None:
    validator = validators.get(object_type)
    if validator is None:
        _fail("object_type_unregistered", object_type)
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        _fail("object_schema_invalid", f"{object_type}:{_schema_error_detail(errors[0])}")
    expected_hash = _sha(document.get("record_sha256"), "record_digest_invalid")
    if canonical_record_sha256(document) != expected_hash:
        _fail("record_digest_mismatch", object_type)


def _validate_lifecycle(document: Mapping[str, Any], object_id: str) -> None:
    lifecycle = document["lifecycle"]
    revision = lifecycle["revision"]
    state = lifecycle["state"]
    supersedes = lifecycle["supersedes_id"]
    superseded_by = lifecycle["superseded_by"]
    if supersedes == object_id or superseded_by == object_id:
        _fail("lifecycle_self_reference", object_id)
    if revision == 1 and supersedes is not None:
        _fail("lifecycle_first_revision_supersedes", object_id)
    if revision > 1 and supersedes is None:
        _fail("lifecycle_revision_parent_missing", object_id)
    if state == "active" and superseded_by is not None:
        _fail("lifecycle_active_has_successor", object_id)
    if state == "superseded" and superseded_by is None:
        _fail("lifecycle_successor_missing", object_id)


def _validate_uncertainty(
    uncertainty: Mapping[str, Any], *, value: float | None = None
) -> None:
    status = uncertainty["status"]
    if value is not None and status == "not_applicable":
        _fail("numeric_uncertainty_not_applicable")
    if status == "interval":
        lower = uncertainty["lower"]
        upper = uncertainty["upper"]
        if (
            isinstance(lower, bool)
            or isinstance(upper, bool)
            or not isinstance(lower, (int, float))
            or not isinstance(upper, (int, float))
            or not math.isfinite(float(lower))
            or not math.isfinite(float(upper))
            or float(lower) > float(upper)
        ):
            _fail("uncertainty_interval_invalid")
        if value is not None and not float(lower) <= value <= float(upper):
            _fail("uncertainty_excludes_value")


def _validate_period(
    start: object, end: object, code: str, *, date_only: bool
) -> None:
    if end is None:
        return
    if date_only:
        if _parse_date(start, code) > _parse_date(end, code):
            _fail(code)
    elif _parse_time(start, code) > _parse_time(end, code):
        _fail(code)


def _provenance_sources(
    evidence_ids: set[str], evidence: Mapping[str, Mapping[str, Any]]
) -> set[str]:
    return {cast(str, evidence[evidence_id]["source_id"]) for evidence_id in evidence_ids}


def _require_exact_provenance(
    document: Mapping[str, Any],
    evidence_ids: set[str],
    evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    provenance = document["provenance"]
    if set(provenance["evidence_ids"]) != evidence_ids:
        _fail("provenance_evidence_mismatch", cast(str, next(iter(document.values()))))
    if set(provenance["source_ids"]) != _provenance_sources(evidence_ids, evidence):
        _fail("provenance_source_mismatch")


def _validate_rights(
    root: Path,
    rights_path: Path,
    signers_path: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
    str,
    date,
    date,
]:
    try:
        safe_signers = _path_inside_root(root, signers_path, "rights_signers_missing")
        safe_rights = _path_inside_root(root, rights_path, "rights_registry_missing")
        _, signers_doc, signers_sha = publication_guard._read_json(
            safe_signers, "signer_registry_unreadable"
        )
        signers = publication_guard._validate_signers(signers_doc)
        _, rights_doc, rights_sha = publication_guard._read_json(
            safe_rights, "rights_registry_unreadable"
        )
        rights = publication_guard._validate_rights_registry(rights_doc, root, signers)
        return (
            rights,
            signers,
            rights_sha,
            signers_sha,
            _parse_date(rights_doc["effective"], "rights_registry_effective_invalid"),
            _parse_date(
                signers_doc["effective"], "rights_signers_effective_invalid"
            ),
        )
    except publication_guard.PublicationGuardError as exc:
        _fail("rights_registry_invalid", exc.code)


def _load_release_signers(
    root: Path, signers_path: Path
) -> tuple[dict[str, dict[str, Any]], str]:
    safe_path = _path_inside_root(root, signers_path, "release_signers_missing")
    try:
        _, document, digest = publication_guard._read_json(
            safe_path, "release_signers_unreadable"
        )
        signers = publication_guard._validate_signers(document)
    except publication_guard.PublicationGuardError as exc:
        _fail("release_signers_invalid", exc.code)
    for signer in signers.values():
        if signer["role"] != "canonical_release_signer":
            _fail("release_signer_role_invalid", signer["signer_id"])
    return signers, digest


def _verify_release_signature(
    manifest_bytes: bytes,
    manifest: Mapping[str, Any],
    root: Path,
    signers: Mapping[str, Mapping[str, Any]],
    effective_date: date,
) -> None:
    signer_id = manifest["release_signer_id"]
    signer = signers.get(signer_id)
    if signer is None:
        _fail("release_signer_unregistered", cast(str, signer_id))
    signer_effective = _parse_date(signer["effective"], "release_signer_effective_invalid")
    revoked = signer["revoked_on"]
    if signer_effective > effective_date or (
        revoked is not None
        and effective_date >= _parse_date(revoked, "release_signer_revoked_invalid")
    ):
        _fail("release_signer_inactive", cast(str, signer_id))
    signature_path = _safe_file(
        root, manifest["release_signature_path"], "release_signature_missing"
    )
    signature = signature_path.read_bytes()
    if len(signature) != 64:
        _fail("release_signature_invalid")
    try:
        public_key = base64.b64decode(
            cast(str, signer["public_key_ed25519_base64"]), validate=True
        )
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, manifest_bytes)
    except (binascii.Error, InvalidSignature, ValueError):
        _fail("release_signature_invalid")


def _validate_evidence(
    document: Mapping[str, Any],
    root: Path,
    release_generated: datetime,
    release_effective: date,
    entities: Mapping[str, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
    rights_signers: Mapping[str, Mapping[str, Any]],
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    evidence_id = cast(str, document["evidence_id"])
    _validate_lifecycle(document, evidence_id)
    source = rights.get(document["source_id"])
    if source is None:
        _fail("evidence_source_unregistered", evidence_id)
    if source["decision_state"] != "approved":
        _fail("evidence_source_not_approved", evidence_id)
    if document["rights_decision_id"] != source["decision_id"]:
        _fail("evidence_rights_decision_mismatch", evidence_id)
    if document["rights_use"] not in source["permitted_uses"]:
        _fail("evidence_rights_use_forbidden", evidence_id)
    if release_generated.date() < _parse_date(
        source["reviewed_on"], "evidence_rights_reviewed_invalid"
    ):
        _fail("evidence_rights_not_yet_effective", evidence_id)
    if release_generated.date() > _parse_date(
        source["review_due"], "evidence_rights_due_invalid"
    ):
        _fail("evidence_rights_expired", evidence_id)
    rights_signer = rights_signers.get(source["signer_id"])
    if rights_signer is None:
        _fail("evidence_rights_signer_unregistered", evidence_id)
    signer_effective = _parse_date(
        rights_signer["effective"], "evidence_rights_signer_effective_invalid"
    )
    signer_revoked = rights_signer["revoked_on"]
    if signer_effective > release_generated.date() or (
        signer_revoked is not None
        and release_generated.date()
        >= _parse_date(signer_revoked, "evidence_rights_signer_revoked_invalid")
    ):
        _fail("evidence_rights_signer_inactive", evidence_id)
    if document["privacy_class"] == "prohibited":
        _fail("prohibited_evidence_in_release", evidence_id)
    if document["privacy_class"] == "restricted" and (
        document["content_availability"] != "restricted"
        or document["artifact_path"] is not None
        or document["public_url"] is not None
    ):
        _fail("restricted_evidence_bytes_forbidden", evidence_id)
    if (
        document["content_availability"] == "restricted"
        and document["privacy_class"] != "restricted"
    ):
        _fail("restricted_availability_privacy_mismatch", evidence_id)
    if (
        document["privacy_class"] == "public_with_redactions"
        and document["content_availability"] != "public_extract"
    ):
        _fail("redacted_evidence_extract_required", evidence_id)

    allowed_use = {
        "full_bytes": {"redistribute_full_record"},
        "public_extract": {"publish_extract"},
        "hash_metadata_only": {"cite_metadata", "publish_derived_value"},
        "restricted": {"cite_metadata", "model_processing"},
    }
    if document["rights_use"] not in allowed_use[document["content_availability"]]:
        _fail("evidence_availability_rights_mismatch", evidence_id)
    if (
        document["public_url"] is None
        and document["artifact_path"] is None
        and document["content_availability"] != "restricted"
    ):
        _fail("evidence_locator_missing", evidence_id)
    if document["artifact_path"] is not None:
        artifact = _safe_file(root, document["artifact_path"], "evidence_artifact_missing")
        actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != document["artifact_sha256"]:
            _fail("evidence_artifact_digest_mismatch", evidence_id)
        if document["content_availability"] == "full_bytes" and actual != document["content_sha256"]:
            _fail("evidence_content_digest_mismatch", evidence_id)

    if document["publisher_entity_id"] is not None and document[
        "publisher_entity_id"
    ] not in entities:
        _fail("evidence_publisher_missing", evidence_id)
    for entity_id in document["geography_entity_ids"]:
        if entity_id not in entities:
            _fail("evidence_geography_missing", entity_id)
    _validate_period(
        document["effective_start"],
        document["effective_end"],
        "evidence_effective_period_invalid",
        date_only=False,
    )
    observed = _parse_time(document["observed_at"], "evidence_observed_invalid")
    retrieved = _parse_time(document["retrieved_at"], "evidence_retrieved_invalid")
    published = (
        _parse_time(document["published_at"], "evidence_published_invalid")
        if document["published_at"] is not None
        else None
    )
    if observed > retrieved or retrieved > release_generated:
        _fail("evidence_knowledge_time_invalid", evidence_id)
    if published is not None and published > retrieved:
        _fail("evidence_published_after_retrieval", evidence_id)
    provenance = document["provenance"]
    if provenance["evidence_ids"] or set(provenance["source_ids"]) != {
        document["source_id"]
    }:
        _fail("evidence_provenance_invalid", evidence_id)
    if provenance["method"] is None:
        _fail("evidence_method_missing", evidence_id)
    _validate_method(provenance["method"], "evidence_item", release_effective, methods)
    if _parse_time(
        provenance["created_at"], "evidence_created_at_invalid"
    ) > release_generated:
        _fail("evidence_created_after_release", evidence_id)


def _validate_entity(
    document: Mapping[str, Any],
    root: Path,
    release_generated: datetime,
    release_effective: date,
    evidence: Mapping[str, Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    entity_id = cast(str, document["entity_id"])
    _validate_lifecycle(document, entity_id)
    if entity_id in document["parent_entity_ids"] or entity_id in document[
        "jurisdiction_entity_ids"
    ]:
        _fail("entity_self_reference", entity_id)
    for reference in document["parent_entity_ids"] + document[
        "jurisdiction_entity_ids"
    ]:
        if reference not in entities:
            _fail("entity_reference_missing", reference)
    evidence_ids = set(document["provenance"]["evidence_ids"])
    if not evidence_ids:
        _fail("entity_evidence_missing", entity_id)
    for identifier in document["identifiers"]:
        identifier_evidence = set(identifier["evidence_ids"])
        if not identifier_evidence <= evidence_ids:
            _fail("entity_identifier_evidence_mismatch", entity_id)
        _validate_period(
            identifier["effective_start"],
            identifier["effective_end"],
            "entity_identifier_period_invalid",
            date_only=True,
        )
    if not evidence_ids <= set(evidence):
        _fail("entity_evidence_reference_missing", entity_id)
    _require_exact_provenance(document, evidence_ids, evidence)
    _validate_period(
        document["effective_start"],
        document["effective_end"],
        "entity_effective_period_invalid",
        date_only=True,
    )
    geometry = document["geometry"]
    if geometry["artifact_path"] is not None:
        path = _safe_file(root, geometry["artifact_path"], "entity_geometry_missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != geometry["artifact_sha256"]:
            _fail("entity_geometry_digest_mismatch", entity_id)
    method = document["provenance"]["method"]
    if method is None:
        _fail("entity_method_missing", entity_id)
    _validate_method(method, "entity", release_effective, methods)
    if _parse_time(
        document["provenance"]["created_at"], "entity_created_at_invalid"
    ) > release_generated:
        _fail("entity_created_after_release", entity_id)


def _validate_coding(document: Mapping[str, Any], event_id: str) -> None:
    coding = document["coding"]
    coders = set(coding["coder_ids"])
    adjudicators = set(coding["adjudicator_ids"])
    status = coding["status"]
    if coders & adjudicators:
        _fail("event_coder_role_collision", event_id)
    if status == "machine_candidate" and (coders or adjudicators):
        _fail("event_machine_candidate_has_coders", event_id)
    if status == "human_coded" and (len(coders) != 1 or adjudicators):
        _fail("event_human_coding_invalid", event_id)
    if status == "dual_coded" and (len(coders) < 2 or adjudicators):
        _fail("event_dual_coding_invalid", event_id)
    if status == "adjudicated" and (len(coders) < 2 or not adjudicators):
        _fail("event_adjudication_invalid", event_id)
    reviewers = set(document["provenance"]["reviewed_by"])
    if not coders | adjudicators <= reviewers:
        _fail("event_reviewer_provenance_mismatch", event_id)


def _validate_event(
    document: Mapping[str, Any],
    release_generated: datetime,
    release_effective: date,
    evidence: Mapping[str, Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    event_id = cast(str, document["event_id"])
    _validate_lifecycle(document, event_id)
    entity_refs = set(document["actor_entity_ids"])
    entity_refs.update(document["target_entity_ids"])
    entity_refs.update(document["affected_entity_ids"])
    entity_refs.update(location["entity_id"] for location in document["locations"])
    missing_entities = entity_refs - set(entities)
    if missing_entities:
        _fail("event_entity_reference_missing", sorted(missing_entities)[0])
    if len({location["entity_id"] for location in document["locations"]}) != len(
        document["locations"]
    ):
        _fail("event_location_duplicate", event_id)

    link_ids = [link["evidence_id"] for link in document["evidence_links"]]
    if len(link_ids) != len(set(link_ids)):
        _fail("event_evidence_duplicate", event_id)
    evidence_ids = set(link_ids)
    evidence_ids.update(
        evidence_id
        for location in document["locations"]
        for evidence_id in location["evidence_ids"]
    )
    if not evidence_ids <= set(evidence):
        _fail("event_evidence_reference_missing", event_id)
    _require_exact_provenance(document, evidence_ids, evidence)

    roles = {link["role"] for link in document["evidence_links"]}
    if document["record_status"] == "confirmed":
        official_links = [
            link
            for link in document["evidence_links"]
            if link["role"] == "official_confirmation"
        ]
        eligible_official = [
            link
            for link in official_links
            if evidence[link["evidence_id"]]["evidence_type"]
            in {"official_document", "official_statement"}
            and evidence[link["evidence_id"]]["verification_status"]
            == "official_record"
            and rights[evidence[link["evidence_id"]]["source_id"]][
                "authority_class"
            ]
            == "official_primary"
        ]
        if official_links and len(eligible_official) != len(official_links):
            _fail("event_official_confirmation_ineligible", event_id)
        corroborating_links = [
            link
            for link in document["evidence_links"]
            if link["role"] == "corroborates"
        ]
        eligible_corroborating = [
            link
            for link in corroborating_links
            if evidence[link["evidence_id"]]["verification_status"]
            in {"single_source", "independently_corroborated", "official_record"}
            and evidence[link["evidence_id"]]["evidence_type"]
            in {
                "dataset_observation",
                "news_article",
                "official_document",
                "official_statement",
                "research_paper",
                "web_page",
            }
        ]
        if corroborating_links and len(eligible_corroborating) != len(
            corroborating_links
        ):
            _fail("event_corroboration_evidence_ineligible", event_id)
        independence_groups = {
            rights[evidence[link["evidence_id"]]["source_id"]]["independence_group"]
            for link in eligible_corroborating
        }
        if not eligible_official and len(independence_groups) < 2:
            _fail("event_confirmation_evidence_insufficient", event_id)
    if document["record_status"] == "candidate" and document[
        "publication_phase"
    ] == "final":
        _fail("event_candidate_final_forbidden", event_id)
    if document["record_status"] == "withdrawn" and document["lifecycle"][
        "state"
    ] != "withdrawn":
        _fail("event_withdrawal_state_mismatch", event_id)
    if roles <= {"allegation", "context", "contradicts"} and document[
        "record_status"
    ] == "confirmed":
        _fail("event_confirmation_evidence_insufficient", event_id)

    _validate_period(
        document["starts_at"],
        document["ends_at"],
        "event_period_invalid",
        date_only=False,
    )
    first_known = _parse_time(document["first_known_at"], "event_first_known_invalid")
    last_verified = _parse_time(
        document["last_verified_at"], "event_last_verified_invalid"
    )
    if first_known > last_verified or last_verified > release_generated:
        _fail("event_knowledge_time_invalid", event_id)
    if any(
        not (
            _parse_time(
                evidence[link["evidence_id"]]["observed_at"],
                "event_evidence_observed_at_invalid",
            )
            <= _parse_time(link["asserted_at"], "event_asserted_at_invalid")
            <= last_verified
        )
        for link in document["evidence_links"]
    ):
        _fail("event_evidence_assertion_time_invalid", event_id)
    _validate_coding(document, event_id)
    coding = document["coding"]
    method = document["provenance"]["method"]
    if method is None or any(
        method[field] != coding[coding_field]
        for field, coding_field in (
            ("method_id", "rule_id"),
            ("version", "rule_version"),
            ("implementation_sha256", "implementation_sha256"),
        )
    ):
        _fail("event_method_provenance_mismatch", event_id)
    _validate_method(method, "event", release_effective, methods)
    intensity = document["intensity"]
    if (
        intensity["status"] == "coded"
        and isinstance(intensity["value"], str)
        and intensity["uncertainty"]["status"] == "interval"
    ):
        _fail("event_categorical_intensity_interval", event_id)
    numeric_value = (
        float(intensity["value"])
        if intensity["status"] == "coded"
        and isinstance(intensity["value"], (int, float))
        and not isinstance(intensity["value"], bool)
        else None
    )
    _validate_uncertainty(intensity["uncertainty"], value=numeric_value)
    if _parse_time(
        document["provenance"]["created_at"], "event_created_at_invalid"
    ) > release_generated:
        _fail("event_created_after_release", event_id)


def _validate_universe(
    document: Mapping[str, Any],
    root: Path,
    release_generated: datetime,
    release_effective: date,
    evidence: Mapping[str, Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    validators: Mapping[str, Any],
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    release_id = cast(str, document["universe_release_id"])
    _validate_lifecycle(document, release_id)
    member_ids = [member["entity_id"] for member in document["members"]]
    if len(member_ids) != len(set(member_ids)):
        _fail("universe_member_duplicate", release_id)
    if not set(member_ids) <= set(entities):
        _fail("universe_member_entity_missing", release_id)
    if any(
        entities[entity_id]["entity_type"] != document["entity_type"]
        for entity_id in member_ids
    ):
        _fail("universe_member_type_mismatch", release_id)
    actual = Counter(member["status"] for member in document["members"])
    counts = document["counts"]
    if counts["total_eligible"] != len(member_ids) or any(
        counts[status] != actual[status]
        for status in ("included", "excluded", "unmappable", "stale")
    ):
        _fail("universe_counts_mismatch", release_id)
    evidence_ids = set(document["source_evidence_ids"])
    if not evidence_ids <= set(evidence):
        _fail("universe_evidence_reference_missing", release_id)
    if any(
        evidence[evidence_id]["evidence_type"]
        not in {"dataset_observation", "official_document", "research_paper"}
        for evidence_id in evidence_ids
    ):
        _fail("universe_frame_source_ineligible", release_id)
    _require_exact_provenance(document, evidence_ids, evidence)
    frame_ref = document["frame_artifact"]
    frame_path = _safe_file(root, frame_ref["path"], "universe_frame_missing")
    frame_bytes, frame, frame_sha = _read_json(frame_path, "universe_frame_invalid")
    if (
        hashlib.sha256(frame_bytes).hexdigest() != frame_sha
        or frame_sha != frame_ref["sha256"]
    ):
        _fail("universe_frame_digest_mismatch", release_id)
    _validate_schema(frame, "universe_frame", validators)
    frame_ids = frame["entity_ids"]
    if (
        frame["universe_id"] != document["universe_id"]
        or frame["entity_type"] != document["entity_type"]
        or frame["reference_date"] != document["reference_date"]
        or frame["source_evidence_id"] not in evidence_ids
        or set(frame_ids) != set(member_ids)
        or len(frame_ids) != len(member_ids)
    ):
        _fail("universe_frame_membership_mismatch", release_id)
    if _parse_time(frame["extracted_at"], "universe_frame_extracted_at_invalid") > release_generated:
        _fail("universe_frame_after_release", release_id)
    if _parse_date(
        document["reference_date"], "universe_reference_date_invalid"
    ) > release_generated.date():
        _fail("universe_reference_after_release", release_id)
    if any(
        _parse_date(member["assessed_on"], "universe_member_assessed_on_invalid")
        > release_generated.date()
        for member in document["members"]
    ):
        _fail("universe_member_assessed_after_release", release_id)
    rule = document["inclusion_rule"]
    implementation = _safe_file(
        root, rule["implementation_path"], "universe_rule_implementation_missing"
    )
    if hashlib.sha256(implementation.read_bytes()).hexdigest() != rule[
        "implementation_sha256"
    ]:
        _fail("universe_rule_digest_mismatch", release_id)
    _safe_file(root, rule["documentation_path"], "universe_rule_documentation_missing")
    method = document["provenance"]["method"]
    if method is None or any(
        method[field] != rule[rule_field]
        for field, rule_field in (
            ("method_id", "rule_id"),
            ("version", "version"),
            ("implementation_sha256", "implementation_sha256"),
        )
    ):
        _fail("universe_rule_provenance_mismatch", release_id)
    _validate_method(method, "universe_release", release_effective, methods)
    if _parse_time(
        document["provenance"]["created_at"], "universe_created_at_invalid"
    ) > release_generated:
        _fail("universe_created_after_release", release_id)


def _validate_edge(
    document: Mapping[str, Any],
    release_generated: datetime,
    release_effective: date,
    evidence: Mapping[str, Mapping[str, Any]],
    entities: Mapping[str, Mapping[str, Any]],
    universes: Mapping[str, Mapping[str, Any]],
    methods: Mapping[tuple[str, str], Mapping[str, Any]],
) -> None:
    edge_id = cast(str, document["edge_id"])
    _validate_lifecycle(document, edge_id)
    source_id = document["source_entity_id"]
    target_id = document["target_entity_id"]
    if source_id == target_id:
        _fail("edge_self_reference", edge_id)
    if source_id not in entities or target_id not in entities:
        _fail("edge_entity_reference_missing", edge_id)
    coverage = document["coverage_basis"]
    covered_id = coverage["covered_entity_id"]
    if covered_id not in {source_id, target_id}:
        _fail("edge_covered_entity_not_endpoint", edge_id)
    universe = universes.get(coverage["universe_release_id"])
    if universe is None:
        _fail("edge_universe_missing", edge_id)
    member = {
        row["entity_id"]: row["status"] for row in universe["members"]
    }.get(covered_id)
    if member != "included":
        _fail("edge_covered_entity_not_included", edge_id)
    if entities[covered_id]["entity_type"] != universe["entity_type"]:
        _fail("edge_universe_type_mismatch", edge_id)

    evidence_ids = set(document["evidence_ids"])
    if not evidence_ids <= set(evidence):
        _fail("edge_evidence_reference_missing", edge_id)
    _require_exact_provenance(document, evidence_ids, evidence)
    if document["method"] != document["provenance"]["method"]:
        _fail("edge_method_provenance_mismatch", edge_id)
    _validate_method(document["method"], "exposure_edge", release_effective, methods)
    _validate_period(
        document["effective_start"],
        document["effective_end"],
        "edge_effective_period_invalid",
        date_only=True,
    )
    observed_at = _parse_time(document["observed_at"], "edge_observed_at_invalid")
    if observed_at > release_generated:
        _fail("edge_observed_after_release", edge_id)
    magnitude = document["magnitude"]
    if document["quantification_status"] == "quantified":
        if magnitude is None:
            _fail("edge_quantified_magnitude_missing", edge_id)
        _validate_period(
            magnitude["period_start"],
            magnitude["period_end"],
            "edge_magnitude_period_invalid",
            date_only=True,
        )
        if _parse_date(
            magnitude["period_end"], "edge_magnitude_period_invalid"
        ) > observed_at.date():
            _fail("edge_magnitude_after_observation", edge_id)
        _validate_uncertainty(magnitude["uncertainty"], value=float(magnitude["value"]))
    elif magnitude is not None:
        _fail("edge_nonquantified_magnitude_forbidden", edge_id)
    _validate_uncertainty(document["confidence"])
    if document["quantification_status"] == "unknown" and "magnitude_unknown" not in document[
        "limitation_codes"
    ]:
        _fail("edge_unknown_limitation_missing", edge_id)
    if document["quantification_status"] == "qualitative":
        if document["confidence"]["status"] not in {"categorical", "not_estimated"}:
            _fail("edge_qualitative_confidence_invalid", edge_id)
        if "magnitude_not_quantified" not in document["limitation_codes"]:
            _fail("edge_qualitative_limitation_missing", edge_id)
    if document["derivation_type"] == "expert_judgment" and document[
        "provenance"
    ]["adjudication_status"] not in {"dual_reviewed", "adjudicated", "disputed"}:
        _fail("edge_expert_review_insufficient", edge_id)
    if _parse_time(
        document["provenance"]["created_at"], "edge_created_at_invalid"
    ) > release_generated:
        _fail("edge_created_after_release", edge_id)


def load_validated_release(
    manifest_path: Path,
    *,
    root: Path = ROOT,
    schema_registry_path: Path = SCHEMA_REGISTRY,
    rights_registry_path: Path = RIGHTS_REGISTRY,
    rights_signers_path: Path = RIGHTS_SIGNERS,
    method_registry_path: Path = METHOD_REGISTRY,
    release_signers_path: Path = RELEASE_SIGNERS,
) -> ValidatedCanonicalRelease:
    """Validate and load one canonical release for a trusted transformation."""

    _, validators, registry_sha = _load_schema_registry(root, schema_registry_path)
    methods, method_registry_sha = _load_method_registry(root, method_registry_path)
    (
        rights,
        rights_signers,
        rights_sha,
        rights_signers_sha,
        rights_registry_effective,
        rights_signers_effective,
    ) = _validate_rights(root, rights_registry_path, rights_signers_path)
    release_signers, release_signers_sha = _load_release_signers(
        root, release_signers_path
    )
    manifest_file = _path_inside_root(root, manifest_path, "release_manifest_missing")
    manifest_bytes, manifest, _ = _read_json(
        manifest_file, "release_manifest_invalid"
    )
    _validate_schema(manifest, "canonical_release", validators)
    if manifest["schema_registry_sha256"] != registry_sha:
        _fail("release_schema_registry_digest_mismatch")
    if manifest["method_registry_sha256"] != method_registry_sha:
        _fail("release_method_registry_digest_mismatch")
    if manifest["rights_registry_sha256"] != rights_sha:
        _fail("release_rights_registry_digest_mismatch")
    if manifest["rights_signers_sha256"] != rights_signers_sha:
        _fail("release_rights_signers_digest_mismatch")
    if manifest["release_signers_sha256"] != release_signers_sha:
        _fail("release_signers_digest_mismatch")
    generated = _parse_time(manifest["generated_at"], "release_generated_at_invalid")
    release_effective = _parse_date(
        manifest["effective_date"], "release_effective_date_invalid"
    )
    if release_effective > generated.date():
        _fail("release_effective_after_generation")
    if rights_registry_effective > generated.date():
        _fail("release_rights_registry_not_yet_effective")
    if rights_signers_effective > generated.date():
        _fail("release_rights_signers_not_yet_effective")
    _verify_release_signature(
        manifest_bytes, manifest, root, release_signers, release_effective
    )

    entries = manifest["objects"]
    if len({entry["path"] for entry in entries}) != len(entries):
        _fail("release_object_path_duplicate")
    if len({entry["object_id"] for entry in entries}) != len(entries):
        _fail("release_object_id_duplicate")
    objects: dict[str, dict[str, Mapping[str, Any]]] = {
        object_type: {} for object_type in _OBJECT_TYPES
    }
    for entry in entries:
        path = _safe_file(root, entry["path"], "release_object_missing")
        raw, document, file_sha = _read_json(path, "release_object_invalid")
        if hashlib.sha256(raw).hexdigest() != file_sha or file_sha != entry["file_sha256"]:
            _fail("release_object_file_digest_mismatch", entry["object_id"])
        object_type = entry["object_type"]
        if document.get("object_type") != object_type:
            _fail("release_object_type_mismatch", entry["object_id"])
        _validate_schema(document, object_type, validators)
        identifier = document[_ID_FIELD[object_type]]
        if identifier != entry["object_id"]:
            _fail("release_object_id_mismatch", entry["object_id"])
        if document["record_sha256"] != entry["record_sha256"]:
            _fail("release_object_record_digest_mismatch", entry["object_id"])
        objects[object_type][identifier] = document

    actual_counts = {object_type: len(rows) for object_type, rows in objects.items()}
    if manifest["counts"] != actual_counts:
        _fail("release_counts_mismatch")
    all_ids = [object_id for rows in objects.values() for object_id in rows]
    if len(all_ids) != len(set(all_ids)):
        _fail("release_global_id_collision")

    evidence = objects["evidence_item"]
    entities = objects["entity"]
    events = objects["event"]
    universes = objects["universe_release"]
    edges = objects["exposure_edge"]
    used_sources = sorted({row["source_id"] for row in evidence.values()})
    expected_snapshot = [
        {
            "source_id": source_id,
            "decision_id": rights[source_id]["decision_id"],
            "decision_artifact_sha256": rights[source_id][
                "decision_artifact_sha256"
            ],
            "signer_id": rights[source_id]["signer_id"],
            "independence_group": rights[source_id]["independence_group"],
            "authority_class": rights[source_id]["authority_class"],
        }
        for source_id in used_sources
        if source_id in rights
    ]
    if manifest["rights_snapshot"] != expected_snapshot:
        _fail("release_rights_snapshot_mismatch")
    for row in evidence.values():
        _validate_evidence(
            row,
            root,
            generated,
            release_effective,
            entities,
            rights,
            rights_signers,
            methods,
        )
    for row in entities.values():
        _validate_entity(
            row,
            root,
            generated,
            release_effective,
            evidence,
            entities,
            methods,
        )
    for row in events.values():
        _validate_event(
            row,
            generated,
            release_effective,
            evidence,
            entities,
            rights,
            methods,
        )
    for row in universes.values():
        _validate_universe(
            row,
            root,
            generated,
            release_effective,
            evidence,
            entities,
            validators,
            methods,
        )
    for row in edges.values():
        _validate_edge(
            row,
            generated,
            release_effective,
            evidence,
            entities,
            universes,
            methods,
        )

    summary: dict[str, object] = {
        "status": "valid",
        "release_id": manifest["release_id"],
        "record_sha256": manifest["record_sha256"],
        "object_count": len(entries),
        "counts": actual_counts,
    }
    return ValidatedCanonicalRelease(manifest=manifest, objects=objects, summary=summary)


def validate_release(
    manifest_path: Path,
    *,
    root: Path = ROOT,
    schema_registry_path: Path = SCHEMA_REGISTRY,
    rights_registry_path: Path = RIGHTS_REGISTRY,
    rights_signers_path: Path = RIGHTS_SIGNERS,
    method_registry_path: Path = METHOD_REGISTRY,
    release_signers_path: Path = RELEASE_SIGNERS,
) -> dict[str, object]:
    """Validate one complete canonical release or fail without partial success."""

    validated = load_validated_release(
        manifest_path,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
    )
    return dict(validated.summary)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Validate an immutable IGRM canonical-object release"
    )
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_release(args.manifest)
    except CanonicalObjectError as exc:
        print(
            json.dumps(
                {"status": "refused", "reason": exc.code, "detail": exc.detail},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
