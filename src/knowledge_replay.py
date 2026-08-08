"""Validate and replay separately receipt-stamped canonical world states.

Knowledge time (when a complete signed release became available) and valid time
(the date whose state is requested) are explicit and never substituted for one
another.  Successful output contains structural identifiers and hashes only;
labels, source text, URLs, magnitudes and confidence values never cross this
boundary.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import sys
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

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]
REPLAY_REGISTRY = ROOT / "governance" / "knowledge_replay_registry.json"
KNOWLEDGE_SIGNERS = ROOT / "governance" / "knowledge_replay_signers.json"

_METHOD_ID = "method:igrm.knowledge_replay"
_METHOD_VERSION = "1.0.0"
_SELECTION_RULE = (
    "latest_separately_receipted_complete_release_at_or_before_cutoff"
)
_OBJECT_TYPES = (
    "evidence_item",
    "entity",
    "event",
    "exposure_edge",
    "universe_release",
)
_GOVERNANCE_BINDINGS = {
    "canonical_schema_registry": "schema_registry_sha256",
    "canonical_method_registry": "method_registry_sha256",
    "source_rights_registry": "rights_registry_sha256",
    "rights_signers": "rights_signers_sha256",
    "release_signers": "release_signers_sha256",
}
_HEX = set("0123456789abcdef")


class KnowledgeReplayError(ValueError):
    """A fail-closed replay refusal with a stable machine reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ReplayContract:
    row: Mapping[str, Any]
    registry_sha256: str
    ledger_validator: Draft202012Validator
    receipt_validator: Draft202012Validator
    output_validator: Draft202012Validator


@dataclass(frozen=True)
class LoadedRelease:
    entry: Mapping[str, Any]
    receipt: Mapping[str, Any]
    validated: canonical.ValidatedCanonicalRelease


@dataclass(frozen=True)
class LoadedLedger:
    document: Mapping[str, Any]
    file_sha256: str
    contract: ReplayContract
    releases: tuple[LoadedRelease, ...]


def _fail(code: str, detail: str = "") -> NoReturn:
    raise KnowledgeReplayError(code, detail)


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
    resolved_root = root.resolve()
    candidate = resolved_root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("symlink_forbidden", relative)
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
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return value


def _public_key_bytes(value: object, code: str) -> bytes:
    if not isinstance(value, str):
        _fail(code)
    try:
        public_key = base64.b64decode(value, validate=True)
        Ed25519PublicKey.from_public_bytes(public_key)
    except (ValueError, binascii.Error):
        _fail(code)
    if len(public_key) != 32:
        _fail(code)
    return public_key


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


def _schema_error(error: Any) -> str:
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    return f"{path or '/'}:{error.validator}"


def _validate_schema(
    document: Mapping[str, Any],
    validator: Draft202012Validator,
    code: str,
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        _fail(code, _schema_error(errors[0]))
    if canonical.canonical_record_sha256(document) != document.get("record_sha256"):
        _fail(f"{code}_digest")


def _load_contract(root: Path, registry_path: Path) -> ReplayContract:
    safe_registry = _inside_root(root, registry_path, "replay_registry_missing")
    _, registry, registry_sha = _read_json(
        safe_registry, "replay_registry_invalid"
    )
    if set(registry) != {
        "schema_version",
        "effective",
        "default_policy",
        "replay",
    }:
        _fail("replay_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("replay_registry_policy_invalid")
    _parse_day(registry["effective"], "replay_registry_effective_invalid")
    row = registry["replay"]
    expected = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "effective",
        "superseded_on",
        "max_releases",
        "max_output_records",
        "common_schema_path",
        "common_schema_sha256",
        "ledger_schema_path",
        "ledger_schema_id",
        "ledger_schema_sha256",
        "receipt_schema_path",
        "receipt_schema_id",
        "receipt_schema_sha256",
        "output_schema_path",
        "output_schema_id",
        "output_schema_sha256",
    }
    if not isinstance(row, dict) or set(row) != expected:
        _fail("replay_registry_entry_invalid")
    if row["method_id"] != _METHOD_ID or row["version"] != _METHOD_VERSION:
        _fail("replay_method_identity_invalid")
    _parse_day(row["effective"], "replay_method_effective_invalid")
    superseded = row["superseded_on"]
    if superseded is not None:
        _parse_day(superseded, "replay_method_superseded_invalid")
    if (
        isinstance(row["max_releases"], bool)
        or not isinstance(row["max_releases"], int)
        or not 1 <= row["max_releases"] <= 100_000
        or isinstance(row["max_output_records"], bool)
        or not isinstance(row["max_output_records"], int)
        or not 1 <= row["max_output_records"] <= 100_000
    ):
        _fail("replay_registry_bounds_invalid")

    implementation = _safe_file(
        root, row["implementation_path"], "replay_implementation_missing"
    )
    running_sha = _sha(Path(__file__).resolve())
    if (
        _sha(implementation) != row["implementation_sha256"]
        or running_sha != row["implementation_sha256"]
    ):
        _fail("replay_implementation_digest_mismatch")

    schema_specs = {
        "common": ("common_schema_path", "common_schema_sha256", None),
        "ledger": (
            "ledger_schema_path",
            "ledger_schema_sha256",
            "ledger_schema_id",
        ),
        "receipt": (
            "receipt_schema_path",
            "receipt_schema_sha256",
            "receipt_schema_id",
        ),
        "output": (
            "output_schema_path",
            "output_schema_sha256",
            "output_schema_id",
        ),
    }
    schemas: dict[str, dict[str, Any]] = {}
    for name, (path_key, digest_key, id_key) in schema_specs.items():
        path = _safe_file(root, row[path_key], f"replay_{name}_schema_missing")
        _, schema, actual_sha = _read_json(path, f"replay_{name}_schema_invalid")
        if actual_sha != row[digest_key]:
            _fail(f"replay_{name}_schema_digest_mismatch")
        if id_key is not None and schema.get("$id") != row[id_key]:
            _fail(f"replay_{name}_schema_id_mismatch")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError:
            _fail(f"replay_{name}_schema_meta_invalid")
        schemas[name] = schema
    resources = Registry().with_resources(
        [
            (cast(str, schemas[name]["$id"]), Resource.from_contents(schemas[name]))
            for name in schemas
        ]
    )
    validators = {
        name: Draft202012Validator(
            schemas[name], registry=resources, format_checker=FormatChecker()
        )
        for name in ("ledger", "receipt", "output")
    }
    return ReplayContract(
        row=row,
        registry_sha256=registry_sha,
        ledger_validator=validators["ledger"],
        receipt_validator=validators["receipt"],
        output_validator=validators["output"],
    )


def _load_signers(root: Path, path: Path) -> tuple[dict[str, dict[str, Any]], str]:
    safe = _inside_root(root, path, "knowledge_signers_missing")
    _, document, digest = _read_json(safe, "knowledge_signers_invalid")
    if set(document) != {"schema_version", "effective", "default_policy", "signers"}:
        _fail("knowledge_signers_fields_invalid")
    if document["schema_version"] != "1.0.0" or document["default_policy"] != "deny":
        _fail("knowledge_signers_policy_invalid")
    _parse_day(document["effective"], "knowledge_signers_effective_invalid")
    if not isinstance(document["signers"], list):
        _fail("knowledge_signers_entries_invalid")
    rows: dict[str, dict[str, Any]] = {}
    expected = {
        "signer_id",
        "name",
        "roles",
        "public_key_ed25519_base64",
        "effective",
        "revoked_on",
    }
    allowed_roles = {"knowledge_availability_signer", "knowledge_ledger_signer"}
    public_keys: set[bytes] = set()
    for raw in document["signers"]:
        if not isinstance(raw, dict) or set(raw) != expected:
            _fail("knowledge_signer_entry_invalid")
        signer_id = raw["signer_id"]
        roles = raw["roles"]
        if (
            not isinstance(signer_id, str)
            or signer_id in rows
            or not isinstance(raw["name"], str)
            or not raw["name"].strip()
            or not isinstance(roles, list)
            or len(roles) != 1
            or not set(roles) <= allowed_roles
        ):
            _fail("knowledge_signer_entry_invalid")
        effective = _parse_day(
            raw["effective"], "knowledge_signer_effective_invalid"
        )
        if raw["revoked_on"] is not None:
            revoked = _parse_day(
                raw["revoked_on"], "knowledge_signer_revoked_invalid"
            )
            if revoked <= effective:
                _fail("knowledge_signer_revoked_invalid")
        key = _public_key_bytes(
            raw["public_key_ed25519_base64"], "knowledge_signer_key_invalid"
        )
        if key in public_keys:
            _fail("knowledge_signer_key_duplicate")
        public_keys.add(key)
        rows[signer_id] = raw
    return rows, digest


def _release_signer_key(path: Path, signer_id: object) -> bytes:
    _, registry, _ = _read_json(path, "release_signers_invalid")
    rows = registry.get("signers")
    if not isinstance(signer_id, str) or not isinstance(rows, list):
        _fail("release_signer_unregistered")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("signer_id") == signer_id
    ]
    if len(matches) != 1:
        _fail("release_signer_unregistered", signer_id)
    return _public_key_bytes(
        matches[0].get("public_key_ed25519_base64"),
        "release_signer_key_invalid",
    )


def _verify_signature(
    raw: bytes,
    signature_path: Path,
    signer_id: object,
    required_role: str,
    at_time: datetime,
    signers: Mapping[str, Mapping[str, Any]],
) -> None:
    if not isinstance(signer_id, str) or signer_id not in signers:
        _fail("knowledge_signer_unregistered")
    signer = signers[signer_id]
    if required_role not in signer["roles"]:
        _fail("knowledge_signer_role_invalid", signer_id)
    effective = _parse_day(signer["effective"], "knowledge_signer_effective_invalid")
    revoked = signer["revoked_on"]
    if at_time.date() < effective or (
        revoked is not None
        and at_time.date() >= _parse_day(revoked, "knowledge_signer_revoked_invalid")
    ):
        _fail("knowledge_signer_inactive", signer_id)
    try:
        signature = signature_path.read_bytes()
        public_bytes = base64.b64decode(
            signer["public_key_ed25519_base64"], validate=True
        )
        Ed25519PublicKey.from_public_bytes(public_bytes).verify(signature, raw)
    except (OSError, TypeError, ValueError, binascii.Error, InvalidSignature):
        _fail("knowledge_signature_invalid", signer_id)


def _governance_paths(
    root: Path,
    entry: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Path]:
    resolved: dict[str, Path] = {}
    for name, manifest_field in _GOVERNANCE_BINDINGS.items():
        row = entry["governance"][name]
        path = _safe_file(root, row["path"], "release_governance_file_missing")
        actual = _sha(path)
        if actual != row["sha256"] or actual != manifest[manifest_field]:
            _fail("release_governance_snapshot_mismatch", name)
        resolved[name] = path
    return resolved


def _release_identity(
    entry: Mapping[str, Any], receipt: Mapping[str, Any], loaded: LoadedRelease
) -> dict[str, Any]:
    manifest = loaded.validated.manifest
    return {
        "sequence": entry["sequence"],
        "release_id": entry["release_id"],
        "manifest_file_sha256": entry["manifest_file_sha256"],
        "manifest_record_sha256": entry["manifest_record_sha256"],
        "generated_at": entry["generated_at"],
        "effective_date": entry["effective_date"],
        "available_at": entry["available_at"],
        "receipt_id": receipt["receipt_id"],
        "receipt_file_sha256": entry["receipt_file_sha256"],
        "receipt_signer_id": receipt["signer_id"],
        "release_signer_id": manifest["release_signer_id"],
        "schema_registry_sha256": manifest["schema_registry_sha256"],
        "method_registry_sha256": manifest["method_registry_sha256"],
        "rights_registry_sha256": manifest["rights_registry_sha256"],
        "rights_signers_sha256": manifest["rights_signers_sha256"],
        "release_signers_sha256": manifest["release_signers_sha256"],
    }


def _all_objects(
    loaded: LoadedRelease,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    return {
        (object_type, object_id): document
        for object_type, rows in loaded.validated.objects.items()
        for object_id, document in rows.items()
    }


def _validate_release_history(releases: Sequence[LoadedRelease]) -> None:
    seen: dict[tuple[str, str], tuple[str, int]] = {}
    successors: dict[tuple[str, str], tuple[str, str]] = {}
    previous: dict[tuple[str, str], Mapping[str, Any]] | None = None
    for loaded in releases:
        current = _all_objects(loaded)
        prior_seen = dict(seen)
        for key, document in current.items():
            digest = cast(str, document["record_sha256"])
            revision = cast(int, document["lifecycle"]["revision"])
            if key in seen and seen[key][0] != digest:
                _fail("object_id_reused_with_different_record", key[1])
            parent_id = document["lifecycle"]["supersedes_id"]
            if revision > 1:
                parent_key = (key[0], cast(str, parent_id))
                if parent_key not in prior_seen:
                    _fail("object_revision_parent_not_in_prior_release", key[1])
                if revision != prior_seen[parent_key][1] + 1:
                    _fail("object_revision_not_contiguous", key[1])
                if parent_key in current:
                    _fail("object_revision_parent_retained_in_complete_snapshot", key[1])
                existing = successors.get(parent_key)
                if existing is not None and existing != key:
                    _fail("object_revision_lineage_fork", parent_key[1])
                successors[parent_key] = key
            seen[key] = (digest, revision)
        if previous is not None:
            removed = set(previous) - set(current)
            for key in removed:
                old = previous[key]
                successor = successors.get(key)
                if (
                    old["lifecycle"]["state"] != "withdrawn"
                    and (successor is None or successor not in current)
                ):
                    _fail("complete_snapshot_object_removed_without_successor", key[1])
        previous = current


def load_ledger(
    ledger_path: Path,
    *,
    root: Path = ROOT,
    replay_registry_path: Path = REPLAY_REGISTRY,
    knowledge_signers_path: Path = KNOWLEDGE_SIGNERS,
) -> LoadedLedger:
    """Validate a complete signed replay ledger and every canonical release."""

    contract = _load_contract(root, replay_registry_path)
    signers, signers_sha = _load_signers(root, knowledge_signers_path)
    ledger_file = _inside_root(root, ledger_path, "knowledge_ledger_missing")
    ledger_raw, ledger, ledger_sha = _read_json(
        ledger_file, "knowledge_ledger_invalid"
    )
    _validate_schema(ledger, contract.ledger_validator, "knowledge_ledger_schema_invalid")
    if ledger["replay_registry_sha256"] != contract.registry_sha256:
        _fail("knowledge_ledger_registry_digest_mismatch")
    if ledger["availability_signers_sha256"] != signers_sha:
        _fail("knowledge_ledger_signers_digest_mismatch")
    entries = ledger["entries"]
    if len(entries) > contract.row["max_releases"]:
        _fail("knowledge_ledger_release_bound_exceeded")
    if ledger["counts"] != {"releases": len(entries)}:
        _fail("knowledge_ledger_counts_mismatch")
    created_at = _parse_time(ledger["created_at"], "knowledge_ledger_created_at_invalid")
    method_effective = _parse_day(
        contract.row["effective"], "replay_method_effective_invalid"
    )
    method_superseded = contract.row["superseded_on"]
    if created_at.date() < method_effective:
        _fail("replay_method_not_effective")
    if method_superseded is not None and created_at.date() >= _parse_day(
        method_superseded, "replay_method_superseded_invalid"
    ):
        _fail("replay_method_superseded")
    ledger_signature = _safe_file(
        root, ledger["ledger_signature_path"], "knowledge_ledger_signature_missing"
    )
    _verify_signature(
        ledger_raw,
        ledger_signature,
        ledger["ledger_signer_id"],
        "knowledge_ledger_signer",
        created_at,
        signers,
    )
    ledger_signer = signers[cast(str, ledger["ledger_signer_id"])]
    ledger_signer_key = _public_key_bytes(
        ledger_signer["public_key_ed25519_base64"],
        "knowledge_signer_key_invalid",
    )

    if [row["sequence"] for row in entries] != list(range(1, len(entries) + 1)):
        _fail("knowledge_receipt_sequence_gap")
    release_ids = [row["release_id"] for row in entries]
    if len(release_ids) != len(set(release_ids)):
        _fail("knowledge_release_id_duplicate")

    loaded_releases: list[LoadedRelease] = []
    previous_receipt_sha: str | None = None
    previous_available: datetime | None = None
    previous_generated: datetime | None = None
    for entry in entries:
        receipt_file = _safe_file(
            root, entry["receipt_path"], "knowledge_receipt_missing"
        )
        receipt_raw, receipt, receipt_sha = _read_json(
            receipt_file, "knowledge_receipt_invalid"
        )
        if receipt_sha != entry["receipt_file_sha256"]:
            _fail("knowledge_receipt_digest_mismatch")
        _validate_schema(
            receipt, contract.receipt_validator, "knowledge_receipt_schema_invalid"
        )
        receipt_signature = _safe_file(
            root, receipt["signature_path"], "knowledge_receipt_signature_missing"
        )
        available_at = _parse_time(
            receipt["available_at"], "knowledge_receipt_available_at_invalid"
        )
        _verify_signature(
            receipt_raw,
            receipt_signature,
            receipt["signer_id"],
            "knowledge_availability_signer",
            available_at,
            signers,
        )
        if receipt["sequence"] != entry["sequence"]:
            _fail("knowledge_receipt_sequence_mismatch")
        if receipt["previous_receipt_file_sha256"] != previous_receipt_sha:
            _fail("knowledge_receipt_chain_mismatch")
        if previous_available is not None and available_at <= previous_available:
            _fail("knowledge_receipt_time_not_increasing")
        if available_at > created_at:
            _fail("knowledge_receipt_after_ledger")

        manifest_file = _safe_file(
            root, entry["manifest_path"], "knowledge_release_manifest_missing"
        )
        _, manifest, manifest_sha = _read_json(
            manifest_file, "knowledge_release_manifest_invalid"
        )
        if manifest_sha != entry["manifest_file_sha256"]:
            _fail("knowledge_release_manifest_digest_mismatch")
        if canonical.canonical_record_sha256(manifest) != manifest["record_sha256"]:
            _fail("knowledge_release_manifest_record_digest_mismatch")
        identity = {
            "release_id": manifest["release_id"],
            "manifest_file_sha256": manifest_sha,
            "manifest_record_sha256": manifest["record_sha256"],
            "generated_at": manifest["generated_at"],
        }
        receipt_identity = {
            "release_id": receipt["release_id"],
            "manifest_file_sha256": receipt["release_manifest_file_sha256"],
            "manifest_record_sha256": receipt["release_record_sha256"],
            "generated_at": receipt["release_generated_at"],
        }
        entry_identity = {
            "release_id": entry["release_id"],
            "manifest_file_sha256": entry["manifest_file_sha256"],
            "manifest_record_sha256": entry["manifest_record_sha256"],
            "generated_at": entry["generated_at"],
        }
        if identity != receipt_identity or identity != entry_identity:
            _fail("knowledge_release_identity_mismatch")
        if entry["effective_date"] != manifest["effective_date"]:
            _fail("knowledge_release_effective_date_mismatch")
        if entry["available_at"] != receipt["available_at"]:
            _fail("knowledge_release_available_at_mismatch")
        generated_at = _parse_time(
            manifest["generated_at"], "knowledge_release_generated_at_invalid"
        )
        if generated_at > available_at:
            _fail("knowledge_receipt_before_release_generation")
        if previous_generated is not None and generated_at <= previous_generated:
            _fail("knowledge_release_generated_at_not_increasing")
        governance = _governance_paths(root, entry, manifest)
        validated = canonical.load_validated_release(
            manifest_file,
            root=root,
            schema_registry_path=governance["canonical_schema_registry"],
            method_registry_path=governance["canonical_method_registry"],
            rights_registry_path=governance["source_rights_registry"],
            rights_signers_path=governance["rights_signers"],
            release_signers_path=governance["release_signers"],
        )
        receipt_signer = signers[cast(str, receipt["signer_id"])]
        receipt_signer_key = _public_key_bytes(
            receipt_signer["public_key_ed25519_base64"],
            "knowledge_signer_key_invalid",
        )
        release_signer_key = _release_signer_key(
            governance["release_signers"], manifest["release_signer_id"]
        )
        if (
            receipt["signer_id"] == manifest["release_signer_id"]
            or receipt_signer_key == release_signer_key
        ):
            _fail("knowledge_receipt_not_separate_from_release_signer")
        if (
            ledger["ledger_signer_id"] == manifest["release_signer_id"]
            or ledger_signer_key == release_signer_key
        ):
            _fail("knowledge_ledger_not_separate_from_release_signer")
        loaded_releases.append(
            LoadedRelease(entry=entry, receipt=receipt, validated=validated)
        )
        previous_receipt_sha = receipt_sha
        previous_available = available_at
        previous_generated = generated_at

    _validate_release_history(loaded_releases)
    return LoadedLedger(
        document=ledger,
        file_sha256=ledger_sha,
        contract=contract,
        releases=tuple(loaded_releases),
    )


def _record_effective(
    object_type: str, document: Mapping[str, Any], valid_on: date
) -> tuple[bool, str]:
    if document["lifecycle"]["state"] != "active":
        return False, "inactive_lifecycle"
    if object_type == "event":
        start = _parse_time(document["starts_at"], "replay_event_start_invalid").date()
        end_value = document["ends_at"]
        if valid_on < start:
            return False, "before_event_start"
        if end_value is not None and valid_on > _parse_time(
            end_value, "replay_event_end_invalid"
        ).date():
            return False, "after_event_end"
        return True, "active_and_effective"
    if object_type == "universe_release":
        if valid_on != _parse_day(
            document["reference_date"], "replay_universe_reference_invalid"
        ):
            return False, "universe_reference_date_mismatch"
        return True, "active_and_effective"
    if object_type == "evidence_item":
        start = _parse_time(
            document["effective_start"], "replay_evidence_start_invalid"
        ).date()
        end_value = document["effective_end"]
        if valid_on < start:
            return False, "before_effective_start"
        if end_value is not None and valid_on > _parse_time(
            end_value, "replay_evidence_end_invalid"
        ).date():
            return False, "after_effective_end"
        return True, "active_and_effective"
    start_value = document["effective_start"]
    end_value = document["effective_end"]
    if start_value is not None and valid_on < _parse_day(
        start_value, "replay_effective_start_invalid"
    ):
        return False, "before_effective_start"
    if end_value is not None and valid_on > _parse_day(
        end_value, "replay_effective_end_invalid"
    ):
        return False, "after_effective_end"
    return True, "active_and_effective"


def _record_row(
    object_type: str, object_id: str, document: Mapping[str, Any], valid_on: date
) -> dict[str, Any]:
    effective, reason = _record_effective(object_type, document, valid_on)
    return {
        "object_type": object_type,
        "object_id": object_id,
        "record_sha256": document["record_sha256"],
        "lifecycle_revision": document["lifecycle"]["revision"],
        "lifecycle_state": document["lifecycle"]["state"],
        "record_status": document["record_status"] if object_type == "event" else None,
        "publication_phase": (
            document["publication_phase"] if object_type == "event" else None
        ),
        "verification_status": (
            document["verification_status"]
            if object_type == "evidence_item"
            else None
        ),
        "effective_on_valid_date": effective,
        "selection_status": "included" if effective else "excluded",
        "selection_reason": reason,
    }


def _scope_objects(
    loaded: LoadedRelease,
    object_type: str | None,
    object_id: str | None,
) -> dict[tuple[str, str], Mapping[str, Any]]:
    objects = _all_objects(loaded)
    if object_type is not None:
        objects = {key: row for key, row in objects.items() if key[0] == object_type}
    if object_id is not None:
        objects = {key: row for key, row in objects.items() if key[1] == object_id}
    return objects


def _validate_output(document: Mapping[str, Any], contract: ReplayContract) -> None:
    _validate_schema(document, contract.output_validator, "knowledge_replay_output_invalid")
    records = document["records"]
    result = document["result"]
    included = sum(row["selection_status"] == "included" for row in records)
    if (
        len(records) != result["records_considered"]
        or included != result["included"]
        or len(records) - included != result["excluded"]
        or document["changes"]["same_id_changed_ids"]
    ):
        _fail("knowledge_replay_output_semantics_invalid")


def replay(
    ledger_path: Path,
    knowledge_cutoff: str,
    valid_on: str,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    root: Path = ROOT,
    replay_registry_path: Path = REPLAY_REGISTRY,
    knowledge_signers_path: Path = KNOWLEDGE_SIGNERS,
) -> dict[str, Any]:
    """Return the exact signed snapshot available by ``knowledge_cutoff``."""

    cutoff = _parse_time(knowledge_cutoff, "knowledge_cutoff_invalid")
    valid_day = _parse_day(valid_on, "knowledge_valid_on_invalid")
    if object_type is not None and object_type not in _OBJECT_TYPES:
        _fail("knowledge_object_type_invalid")
    if object_id is not None and (
        not isinstance(object_id, str)
        or not 3 <= len(object_id) <= 128
        or not object_id[0].isalpha()
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_.:-" for character in object_id)
    ):
        _fail("knowledge_object_id_invalid")

    ledger = load_ledger(
        ledger_path,
        root=root,
        replay_registry_path=replay_registry_path,
        knowledge_signers_path=knowledge_signers_path,
    )
    ledger_created = _parse_time(
        ledger.document["created_at"], "knowledge_ledger_created_at_invalid"
    )
    if cutoff > ledger_created:
        _fail("knowledge_cutoff_after_ledger_close")
    eligible = [
        loaded
        for loaded in ledger.releases
        if _parse_time(
            loaded.receipt["available_at"], "knowledge_receipt_available_at_invalid"
        )
        <= cutoff
    ]
    if not eligible:
        _fail("knowledge_cutoff_before_first_receipt")
    selected = eligible[-1]
    selected_index = ledger.releases.index(selected)
    previous = ledger.releases[selected_index - 1] if selected_index else None
    selected_objects = _scope_objects(selected, object_type, object_id)
    if len(selected_objects) > ledger.contract.row["max_output_records"]:
        _fail("knowledge_replay_output_bound_exceeded")
    records = [
        _record_row(key[0], key[1], selected_objects[key], valid_day)
        for key in sorted(selected_objects)
    ]
    previous_objects = (
        _scope_objects(previous, object_type, object_id) if previous is not None else {}
    )
    selected_ids = {key[1] for key in selected_objects}
    previous_ids = {key[1] for key in previous_objects}
    common = set(selected_objects) & set(previous_objects)
    changed = sorted(
        key[1]
        for key in common
        if selected_objects[key]["record_sha256"]
        != previous_objects[key]["record_sha256"]
    )
    requested_present = object_id in selected_ids if object_id is not None else None
    included_count = sum(row["selection_status"] == "included" for row in records)
    if object_id is not None and not requested_present:
        status = "object_absent"
    elif included_count:
        status = "state_found"
    else:
        status = "state_empty"

    row = ledger.contract.row
    document: dict[str, Any] = {
        "object_type": "knowledge_replay",
        "schema_version": "1.0.0",
        "record_sha256": "0" * 64,
        "ledger": {
            "ledger_id": ledger.document["ledger_id"],
            "record_sha256": ledger.document["record_sha256"],
            "file_sha256": ledger.file_sha256,
            "created_at": ledger.document["created_at"],
            "ledger_signer_id": ledger.document["ledger_signer_id"],
            "replay_registry_sha256": ledger.contract.registry_sha256,
            "availability_signers_sha256": ledger.document[
                "availability_signers_sha256"
            ],
        },
        "contract": {
            "schema_id": row["output_schema_id"],
            "schema_version": "1.0.0",
            "schema_sha256": row["output_schema_sha256"],
            "common_schema_sha256": row["common_schema_sha256"],
        },
        "method": {
            "method_id": _METHOD_ID,
            "version": _METHOD_VERSION,
            "implementation_sha256": row["implementation_sha256"],
        },
        "query": {
            "knowledge_cutoff": knowledge_cutoff,
            "valid_on": valid_on,
            "object_type": object_type,
            "object_id": object_id,
            "selection_rule": _SELECTION_RULE,
        },
        "selected_release": _release_identity(
            selected.entry, selected.receipt, selected
        ),
        "previous_release": (
            _release_identity(previous.entry, previous.receipt, previous)
            if previous is not None
            else None
        ),
        "records": records,
        "changes": {
            "basis_release_id": (
                previous.entry["release_id"] if previous is not None else None
            ),
            "added_ids": sorted(selected_ids - previous_ids),
            "removed_ids": sorted(previous_ids - selected_ids),
            "same_id_changed_ids": changed,
        },
        "result": {
            "status": status,
            "requested_object_present": requested_present,
            "records_considered": len(records),
            "included": included_count,
            "excluded": len(records) - included_count,
        },
        "limitations": sorted(
            [
                "complete_signed_snapshot_not_global_ground_truth",
                "knowledge_cutoff_uses_separate_receipt_time",
                "no_automatic_causal_forecast_or_truth_inference",
                "signed_chain_not_external_transparency_log",
                "separate_signer_identity_not_institutional_independence",
                "structural_metadata_only_no_claim_values",
                "valid_time_separate_from_knowledge_time",
            ]
        ),
    }
    document = canonical.seal_record(document)
    _validate_output(document, ledger.contract)
    return document


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Replay a signed canonical world state without hindsight"
    )
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--knowledge-cutoff", required=True)
    parser.add_argument("--valid-on", required=True)
    parser.add_argument("--object-type", choices=_OBJECT_TYPES)
    parser.add_argument("--object-id")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = replay(
            args.ledger,
            args.knowledge_cutoff,
            args.valid_on,
            object_type=args.object_type,
            object_id=args.object_id,
            root=args.root,
            replay_registry_path=args.root / "governance" / "knowledge_replay_registry.json",
            knowledge_signers_path=args.root / "governance" / "knowledge_replay_signers.json",
        )
    except (KnowledgeReplayError, canonical.CanonicalObjectError) as exc:
        reason = exc.code
        print(
            json.dumps(
                {"status": "refused", "stage": "knowledge_replay", "reason": reason},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
