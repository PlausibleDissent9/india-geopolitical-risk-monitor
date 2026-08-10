"""Build and verify an internal clause-reader proof archive.

The archive is a deterministic transport for two already-compiled clause
inputs, their existing receipts and the three internal reader shadows.  It is
not the incumbent offline audience output.  Verification uses only separately
installed, hash-pinned code and governance; archive members are never imported,
executed or extracted.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator

from . import analytical_clause as ac
from . import clause_reader_shadow as reader
from . import clause_source_view as source_view

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "clause_offline_proof_contract.json"

_VERSION = "0.1.0"
_CONTRACT_ID = "igrm:clause-reader-proof-archive:0.1.0"
_REGISTERED_CONTRACT_SHA256 = (
    "0e3cdb66cd5984bb3ed13665a80d474ce451649af400de6568c248047d9ae34b"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONSTRUCTION_DATE = (1980, 1, 1, 0, 0, 0)
_REGULAR_MODE = 0o100644

_INPUT_PATHS = {
    "source": "inputs/source-bundle.json",
    "proof": "inputs/role-proof-bundle.json",
    "view_receipt": "receipts/clause-source-view.json",
    "reader_receipt": "receipts/clause-reader-compilation.json",
}
_OUTPUTS: Mapping[str, tuple[str, str, str]] = {
    "output:board_brief": (
        "board_brief",
        "artifacts/board-brief.json",
        "shadow_artifact:board",
    ),
    "output:newsroom_claim_card": (
        "newsroom_claim_card",
        "artifacts/newsroom-claim-card.json",
        "shadow_artifact:newsroom",
    ),
    "output:research_package": (
        "research_package",
        "artifacts/research-package.json",
        "shadow_artifact:research",
    ),
}
_AUTHORITY_ROLES = {
    "source_profile": "authority:source_profile",
    "consumer_profile": "authority:consumer_profile",
    "template_profile": "authority:template_profile",
    "limitation_registry": "authority:limitation_registry",
}
_TRUST = {
    "synthetic": True,
    "contract_only": True,
    "self_hash_integrity_only": True,
    "signed": False,
    "authenticated": False,
    "nonpublic": True,
    "nonproduction": True,
}
_BOUNDARY = {
    "proof_transport_only": True,
    "public_behavior_changed": False,
    "publication_approved": False,
    "offline_audience_output_created": False,
    "product_manifest_created": False,
    "source_replay_performed": False,
    "source_truth_claimed": False,
    "rights_approval_claimed": False,
    "output_equivalence_claimed": False,
    "production_authority": False,
    "public_authority": False,
}
_VERIFICATION = {
    "external_archive_digest_required": True,
    "separately_trusted_installed_verifier_required": True,
    "network_required": False,
    "archive_extraction_required": False,
    "bundled_code_execution_required": False,
    "exact_clause_recompilation_required": True,
}


class ClauseOfflineProofError(ValueError):
    """Stable fail-closed refusal from the internal proof archive."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ClauseOfflineProofError(code, detail)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _runtime_sha256() -> str:
    try:
        return _sha(Path(__file__).resolve().read_bytes())
    except OSError as exc:
        raise ClauseOfflineProofError("proof_runtime_drift", str(exc)) from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, nested in pairs:
        if key in value:
            raise ValueError("duplicate_key")
        value[key] = nested
    return value


def _decode_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ValueError("nonfinite_constant")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClauseOfflineProofError(code, type(exc).__name__) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _canonical_bytes(value: Mapping[str, Any], code: str) -> bytes:
    try:
        return ac.serialize_record(value)
    except Exception as exc:
        raise ClauseOfflineProofError(code, type(exc).__name__) from exc


def _reader_body_bytes(value: Mapping[str, Any]) -> bytes:
    """Serialize a reader body exactly as the incumbent reader compiler does."""
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClauseOfflineProofError(
            "proof_recompile_mismatch", type(exc).__name__
        ) from exc


def _capture_mapping(value: Mapping[str, Any], *, limit: int) -> tuple[bytes, dict[str, Any]]:
    if not isinstance(value, Mapping):
        _fail("proof_input_invalid")
    raw = _canonical_bytes(value, "proof_input_invalid")
    if not raw or len(raw) > limit:
        _fail("proof_archive_entry_size_invalid")
    decoded = _decode_object(raw, "proof_input_invalid")
    if _canonical_bytes(decoded, "proof_input_invalid") != raw:
        _fail("proof_input_invalid")
    return raw, decoded


def _record_sha256(value: Mapping[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("record_sha256", None)
    return _sha(_canonical_bytes(unsigned, "proof_receipt_invalid"))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["record_sha256"] = _record_sha256(sealed)
    return sealed


def _read_registered_file(relative: str, expected_sha: str, code: str) -> bytes:
    path = ROOT / relative
    registered = ROOT.resolve() / relative
    try:
        if path.is_symlink() or path.resolve(strict=True) != registered:
            _fail(code, relative)
        mode = path.stat().st_mode
        if not stat.S_ISREG(mode):
            _fail(code, relative)
        raw = path.read_bytes()
    except OSError as exc:
        raise ClauseOfflineProofError(code, relative) from exc
    if _sha(raw) != expected_sha:
        _fail(code, relative)
    return raw


def _load_contract() -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    raw = _read_registered_file(
        "governance/clause_offline_proof_contract.json",
        _REGISTERED_CONTRACT_SHA256,
        "proof_contract_drift",
    )
    contract = _decode_object(raw, "proof_contract_invalid")
    if (
        contract.get("schema_version") != _VERSION
        or contract.get("contract_id") != _CONTRACT_ID
        or contract.get("status") != "internal_synthetic_contract_only"
        or contract.get("public_routes") != []
        or contract.get("trust") != _TRUST
        or contract.get("boundary") != _BOUNDARY
    ):
        _fail("proof_contract_invalid")
    archive = contract.get("archive")
    compiler = contract.get("compiler")
    api = contract.get("api")
    if (
        not isinstance(archive, dict)
        or archive.get("archive_entry_denominator") != 12
        or archive.get("listed_member_denominator") != 11
        or archive.get("receipt_path") != "proof-receipt.json"
        or archive.get("compression") != "stored_only"
        or archive.get("entry_timestamp") != list(_CONSTRUCTION_DATE)
        or archive.get("entry_mode_octal") != "100644"
        or archive.get("bundled_code_allowed") is not False
        or archive.get("extraction_allowed") is not False
        or not isinstance(compiler, dict)
        or compiler.get("output_ids") != sorted(_OUTPUTS)
        or compiler.get("output_denominator") != 3
        or compiler.get("role_denominator") != 7
        or compiler.get("role_pair_denominator") != 21
        or compiler.get("source_or_release_replay") is not False
        or compiler.get("canonical_store_read") is not False
        or compiler.get("network") is not False
        or not isinstance(api, dict)
        or api.get("builder_positional_inputs") != [
            "source_bundle",
            "role_proof_bundle",
        ]
        or api.get("caller_paths_profiles_selectors_queries_outputs_or_policies")
        is not False
        or api.get("caller_views_or_compilations") is not False
    ):
        _fail("proof_contract_invalid")
    fixed = contract.get("fixed_files")
    if not isinstance(fixed, dict) or set(fixed) != {
        "receipt_schema",
        "adversarial_vectors",
    }:
        _fail("proof_contract_invalid")
    schema_row = fixed["receipt_schema"]
    vector_row = fixed["adversarial_vectors"]
    if not isinstance(schema_row, dict) or not isinstance(vector_row, dict):
        _fail("proof_contract_invalid")
    schema_raw = _read_registered_file(
        cast(str, schema_row.get("path")),
        cast(str, schema_row.get("file_sha256")),
        "proof_contract_drift",
    )
    vectors_raw = _read_registered_file(
        cast(str, vector_row.get("path")),
        cast(str, vector_row.get("file_sha256")),
        "proof_contract_drift",
    )
    schema = _decode_object(schema_raw, "proof_contract_invalid")
    vectors = _decode_object(vectors_raw, "proof_contract_invalid")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise ClauseOfflineProofError(
            "proof_contract_invalid", type(exc).__name__
        ) from exc
    cases = vectors.get("cases")
    refusal_codes = contract.get("refusal_codes")
    if (
        vectors.get("status") != "normative_executable"
        or not isinstance(cases, list)
        or not all(
            isinstance(row, dict)
            and set(row) == {"case_id", "mutation", "expected"}
            and all(isinstance(row[key], str) and row[key] for key in row)
            for row in cases
        )
        or vectors.get("complete_case_denominator") != len(cases)
        or len(cases) != 33
        or len(
            {
                row.get("case_id")
                for row in cases
                if isinstance(row, dict)
            }
        )
        != 33
        or len(
            {
                row.get("mutation")
                for row in cases
                if isinstance(row, dict)
            }
        )
        != 33
        or not isinstance(refusal_codes, list)
        or not all(isinstance(code, str) and code for code in refusal_codes)
        or len(refusal_codes) != len(set(refusal_codes))
        or {
            row.get("expected")
            for row in cases
            if isinstance(row, dict) and row.get("expected") != "valid"
        }
        != set(refusal_codes)
    ):
        _fail("proof_contract_invalid")
    return contract, raw, schema


def _closed_rows(
    contract: Mapping[str, Any], key: str, *, expected_count: int
) -> list[dict[str, str]]:
    value = contract.get(key)
    if not isinstance(value, list) or len(value) != expected_count:
        _fail("proof_contract_invalid", key)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            _fail("proof_contract_invalid", key)
        path = raw.get("source_path") if key == "archive_authorities" else raw.get("path")
        digest = raw.get("file_sha256")
        if (
            not isinstance(path, str)
            or not path
            or path in seen
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            _fail("proof_contract_invalid", key)
        row = {"path": path, "file_sha256": digest}
        if key == "archive_authorities":
            authority_id = raw.get("authority_id")
            archive_path = raw.get("archive_path")
            if (
                authority_id not in _AUTHORITY_ROLES
                or not isinstance(archive_path, str)
                or not archive_path
            ):
                _fail("proof_contract_invalid", key)
            row["authority_id"] = cast(str, authority_id)
            row["archive_path"] = archive_path
        rows.append(row)
        seen.add(path)
    return rows


def _installed_snapshot(
    contract: Mapping[str, Any]
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    authorities: dict[str, bytes] = {}
    for row in _closed_rows(contract, "archive_authorities", expected_count=4):
        authorities[row["path"]] = _read_registered_file(
            row["path"], row["file_sha256"], "proof_authority_mismatch"
        )
    dependencies: dict[str, bytes] = {}
    for row in _closed_rows(contract, "installed_dependencies", expected_count=10):
        dependencies[row["path"]] = _read_registered_file(
            row["path"], row["file_sha256"], "proof_dependency_drift"
        )
    return authorities, dependencies


def _artifact_bytes(document: Mapping[str, Any]) -> tuple[bytes, bytes]:
    descriptor = document.get("artifact")
    if not isinstance(descriptor, dict) or set(descriptor) != {
        "filename",
        "media_type",
        "sha256",
        "bytes",
    }:
        _fail("proof_recompile_mismatch", "artifact_descriptor")
    body = dict(document)
    body.pop("artifact")
    body_raw = _reader_body_bytes(body)
    try:
        artifact_raw = (
            json.dumps(
                body,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClauseOfflineProofError(
            "proof_recompile_mismatch", type(exc).__name__
        ) from exc
    if (
        descriptor.get("media_type") != "application/json"
        or not isinstance(descriptor.get("filename"), str)
        or not descriptor["filename"].endswith(".json")
        or descriptor.get("sha256") != _sha(artifact_raw)
        or descriptor.get("bytes") != len(artifact_raw)
    ):
        _fail("proof_recompile_mismatch", "artifact_descriptor")
    return artifact_raw, body_raw


def _member_row(path: str, raw: bytes, role: str) -> dict[str, Any]:
    return {"path": path, "role": role, "sha256": _sha(raw), "bytes": len(raw)}


def _assert_value_free(receipt: Mapping[str, Any]) -> None:
    forbidden = {"value", "prose", "url", "date", "signature", "source_content"}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = key.lower()
                if lowered in forbidden or lowered.endswith("_url") or "signature" in lowered:
                    _fail("proof_receipt_invalid", key)
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)
        elif isinstance(value, str) and "://" in value:
            _fail("proof_receipt_invalid", "url_value")

    walk(receipt)


def _validate_receipt(
    receipt: Mapping[str, Any], schema: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    try:
        Draft202012Validator(schema).validate(dict(receipt))
    except Exception as exc:
        raise ClauseOfflineProofError(
            "proof_receipt_invalid", type(exc).__name__
        ) from exc
    if receipt.get("record_sha256") != _record_sha256(receipt):
        _fail("proof_receipt_invalid", "record_sha256")
    members = receipt.get("members")
    outputs = receipt.get("outputs")
    bindings = receipt.get("bindings")
    if (
        not isinstance(members, list)
        or [row.get("path") for row in members if isinstance(row, dict)]
        != sorted(cast(str, row["path"]) for row in cast(Sequence[Mapping[str, Any]], members))
        or not isinstance(outputs, list)
        or [row.get("output_id") for row in outputs if isinstance(row, dict)]
        != sorted(_OUTPUTS)
        or not isinstance(bindings, dict)
    ):
        _fail("proof_receipt_invalid")
    expected_authorities = [
        {"path": row["path"], "file_sha256": row["file_sha256"]}
        for row in _closed_rows(contract, "archive_authorities", expected_count=4)
    ]
    expected_dependencies = _closed_rows(
        contract, "installed_dependencies", expected_count=10
    )
    if (
        bindings.get("authority_refs") != expected_authorities
        or bindings.get("installed_dependency_refs") != expected_dependencies
        or receipt.get("trust") != _TRUST
        or receipt.get("boundary") != _BOUNDARY
        or receipt.get("verification") != _VERIFICATION
    ):
        _fail("proof_receipt_invalid")
    _assert_value_free(receipt)


def _compile_files(
    source_raw: bytes,
    source: Mapping[str, Any],
    proof_raw: bytes,
    proof: Mapping[str, Any],
    contract: Mapping[str, Any],
    contract_raw: bytes,
    schema: Mapping[str, Any],
    *,
    upstream_code: str,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    before_authorities, before_dependencies = _installed_snapshot(contract)
    try:
        views = source_view.compile_clause_source_views(source, proof)
        views.verify()
        compilation = reader.compile_clause_reader_shadow(views)
        compilation.verify()
    except (
        ac.AnalyticalClauseError,
        source_view.ClauseSourceViewError,
        reader.ClauseReaderShadowError,
    ) as exc:
        detail = getattr(exc, "code", type(exc).__name__)
        raise ClauseOfflineProofError(upstream_code, str(detail)) from exc
    after_authorities, after_dependencies = _installed_snapshot(contract)
    if before_authorities != after_authorities:
        _fail("proof_authority_mismatch", "changed_during_compile")
    if before_dependencies != after_dependencies:
        _fail("proof_dependency_drift", "changed_during_compile")

    view_receipt = views.receipt
    reader_receipt = compilation.receipt
    view_receipt_raw = _canonical_bytes(view_receipt, upstream_code)
    reader_receipt_raw = _canonical_bytes(reader_receipt, upstream_code)
    output_receipts = {
        row["output_id"]: row
        for row in cast(Sequence[Mapping[str, Any]], reader_receipt["outputs"])
    }
    if set(output_receipts) != set(_OUTPUTS):
        _fail(upstream_code, "output_denominator")

    files: dict[str, bytes] = {
        _INPUT_PATHS["source"]: source_raw,
        _INPUT_PATHS["proof"]: proof_raw,
        _INPUT_PATHS["view_receipt"]: view_receipt_raw,
        _INPUT_PATHS["reader_receipt"]: reader_receipt_raw,
    }
    roles = {
        _INPUT_PATHS["source"]: "source_bundle",
        _INPUT_PATHS["proof"]: "role_proof_bundle",
        _INPUT_PATHS["view_receipt"]: "clause_source_view_receipt",
        _INPUT_PATHS["reader_receipt"]: "clause_reader_compilation_receipt",
    }
    output_rows: list[dict[str, Any]] = []
    for output_id, (attribute, archive_path, role) in sorted(_OUTPUTS.items()):
        document = cast(Mapping[str, Any], getattr(compilation, attribute))
        artifact_raw, body_raw = _artifact_bytes(document)
        output_receipt = output_receipts[output_id]
        if (
            output_receipt.get("artifact_sha256") != _sha(artifact_raw)
            or output_receipt.get("body_sha256") != _sha(body_raw)
            or cast(Mapping[str, Any], output_receipt.get("denominators", {})).get(
                "artifact_bytes"
            )
            != len(artifact_raw)
            or cast(Mapping[str, Any], output_receipt.get("denominators", {})).get(
                "body_bytes"
            )
            != len(body_raw)
        ):
            _fail(upstream_code, output_id)
        files[archive_path] = artifact_raw
        roles[archive_path] = role
        output_rows.append(
            {
                "output_id": output_id,
                "archive_path": archive_path,
                "sha256": _sha(artifact_raw),
                "bytes": len(artifact_raw),
                "body_sha256": _sha(body_raw),
            }
        )

    authority_refs: list[dict[str, str]] = []
    for row in _closed_rows(contract, "archive_authorities", expected_count=4):
        source_path = row["path"]
        archive_path = row["archive_path"]
        authority_id = row["authority_id"]
        files[archive_path] = before_authorities[source_path]
        roles[archive_path] = _AUTHORITY_ROLES[authority_id]
        authority_refs.append(
            {"path": source_path, "file_sha256": row["file_sha256"]}
        )

    archive = cast(Mapping[str, Any], contract["archive"])
    expected_member_paths = set(cast(Sequence[str], archive["closed_member_paths"]))
    if set(files) != expected_member_paths or set(roles) != expected_member_paths:
        _fail("proof_contract_invalid", "closed_member_paths")
    members = [
        _member_row(path, files[path], roles[path]) for path in sorted(files)
    ]
    source_denominators = cast(Mapping[str, Any], source["complete_denominators"])
    view_denominators = cast(Mapping[str, Any], view_receipt["denominators"])
    proof_cross = cast(Mapping[str, Any], proof["cross_role_proof"])
    binding_identity = {
        "source_bundle_record_sha256": source["record_sha256"],
        "role_proof_record_sha256": proof["record_sha256"],
        "view_receipt_record_sha256": view_receipt["record_sha256"],
        "reader_receipt_record_sha256": reader_receipt["record_sha256"],
        "archive_contract_sha256": _sha(contract_raw),
        "archive_runtime_sha256": _runtime_sha256(),
        "member_sha256": [row["sha256"] for row in members],
    }
    receipt = _seal(
        {
            "object_type": "clause_reader_proof_archive_receipt",
            "schema_version": _VERSION,
            "proof_id": (
                "clause-reader-proof:"
                + _sha(_canonical_bytes(binding_identity, "proof_receipt_invalid"))[:24]
            ),
            "record_sha256": "0" * 64,
            "bindings": {
                "source_bundle_ref": {
                    "object_id": source["bundle_id"],
                    "record_sha256": source["record_sha256"],
                    "captured_bytes_sha256": _sha(source_raw),
                },
                "role_proof_bundle_ref": {
                    "object_id": proof["proof_bundle_id"],
                    "record_sha256": proof["record_sha256"],
                    "captured_bytes_sha256": _sha(proof_raw),
                },
                "view_receipt_ref": {
                    "object_id": view_receipt["view_set_id"],
                    "record_sha256": view_receipt["record_sha256"],
                    "captured_bytes_sha256": _sha(view_receipt_raw),
                },
                "reader_receipt_ref": {
                    "object_id": reader_receipt["compilation_id"],
                    "record_sha256": reader_receipt["record_sha256"],
                    "captured_bytes_sha256": _sha(reader_receipt_raw),
                },
                "archive_contract_ref": {
                    "contract_id": _CONTRACT_ID,
                    "file_sha256": _sha(contract_raw),
                },
                "archive_runtime_ref": {
                    "implementation_sha256": _runtime_sha256()
                },
                "authority_refs": authority_refs,
                "installed_dependency_refs": _closed_rows(
                    contract, "installed_dependencies", expected_count=10
                ),
            },
            "active_branch_id": view_receipt["active_branch_id"],
            "outputs": output_rows,
            "members": members,
            "denominators": {
                "input_denominator": 2,
                "upstream_receipt_denominator": 2,
                "output_denominator": 3,
                "authority_denominator": 4,
                "installed_dependency_denominator": 10,
                "role_denominator": view_denominators["role_denominator"],
                "role_pair_denominator": proof_cross["role_pair_denominator"],
                "source_clause_denominator": source_denominators["clauses"],
                "listed_member_denominator": len(members),
                "archive_entry_denominator": len(members) + 1,
            },
            "verification": dict(_VERIFICATION),
            "trust": dict(_TRUST),
            "boundary": dict(_BOUNDARY),
        }
    )
    _validate_receipt(receipt, schema, contract)
    return files, receipt


def _zip_bytes(
    files: Mapping[str, bytes], receipt: Mapping[str, Any], contract: Mapping[str, Any]
) -> bytes:
    archive_rule = cast(Mapping[str, Any], contract["archive"])
    values = dict(files)
    values[cast(str, archive_rule["receipt_path"])] = _canonical_bytes(
        receipt, "proof_receipt_invalid"
    )
    if len(values) != archive_rule["archive_entry_denominator"]:
        _fail("proof_archive_membership_invalid")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as opened:
        opened.comment = b""
        for name in sorted(values):
            info = zipfile.ZipInfo(name, date_time=_CONSTRUCTION_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = _REGULAR_MODE << 16
            opened.writestr(info, values[name])
    raw = stream.getvalue()
    if not raw or len(raw) > cast(int, archive_rule["max_archive_bytes"]):
        _fail("proof_archive_size_invalid")
    return raw


def build_clause_offline_proof(
    source_bundle: Mapping[str, Any], role_proof_bundle: Mapping[str, Any]
) -> bytes:
    """Build one deterministic internal proof archive from exactly two inputs."""

    contract, contract_raw, schema = _load_contract()
    archive = cast(Mapping[str, Any], contract["archive"])
    limit = cast(int, archive["max_entry_bytes"])
    source_raw, source = _capture_mapping(source_bundle, limit=limit)
    proof_raw, proof = _capture_mapping(role_proof_bundle, limit=limit)
    files, receipt = _compile_files(
        source_raw,
        source,
        proof_raw,
        proof,
        contract,
        contract_raw,
        schema,
        upstream_code="proof_input_invalid",
    )
    return _zip_bytes(files, receipt, contract)


def _safe_archive_path(name: str, seen_normalized: set[str]) -> None:
    path = PurePosixPath(name)
    normalized = unicodedata.normalize("NFC", name).casefold()
    if (
        not name
        or name.startswith("/")
        or "\\" in name
        or "\x00" in name
        or ":" in name
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or normalized in seen_normalized
    ):
        _fail("proof_archive_path_invalid", name)
    seen_normalized.add(normalized)


def _read_archive(
    archive: bytes, contract: Mapping[str, Any]
) -> dict[str, bytes]:
    rule = cast(Mapping[str, Any], contract["archive"])
    if not isinstance(archive, bytes) or not archive or len(archive) > rule["max_archive_bytes"]:
        _fail("proof_archive_size_invalid")
    try:
        opened = zipfile.ZipFile(io.BytesIO(archive), "r")
    except (zipfile.BadZipFile, OSError):
        _fail("proof_archive_invalid")
    with opened:
        if opened.comment:
            _fail("proof_archive_metadata_invalid", "archive_comment")
        infos = opened.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            _fail("proof_archive_duplicate_path")
        if len(names) != rule["archive_entry_denominator"]:
            _fail("proof_archive_membership_invalid")
        seen_normalized: set[str] = set()
        total = 0
        values: dict[str, bytes] = {}
        for info in infos:
            name = info.filename
            _safe_archive_path(name, seen_normalized)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_IFMT(mode) != stat.S_IFREG:
                _fail("proof_archive_entry_type_invalid", name)
            if info.flag_bits & 0x1:
                _fail("proof_archive_metadata_invalid", "encrypted")
            if info.compress_type != zipfile.ZIP_STORED:
                _fail("proof_archive_compression_invalid", name)
            if (
                info.date_time != _CONSTRUCTION_DATE
                or info.create_system != 3
                or mode != _REGULAR_MODE
                or info.extra
                or info.comment
            ):
                _fail("proof_archive_metadata_invalid", name)
            if info.file_size <= 0 or info.file_size > rule["max_entry_bytes"]:
                _fail("proof_archive_entry_size_invalid", name)
            total += info.file_size
            if total > rule["max_expanded_bytes"]:
                _fail("proof_archive_size_invalid")
            try:
                raw = opened.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                _fail("proof_archive_invalid", name)
            if len(raw) != info.file_size:
                _fail("proof_archive_entry_size_invalid", name)
            values[name] = raw
    expected = set(cast(Sequence[str], rule["closed_member_paths"])) | {
        cast(str, rule["receipt_path"])
    }
    if set(values) != expected or names != sorted(names):
        _fail("proof_archive_membership_invalid")
    return values


def verify_clause_offline_proof(
    archive: bytes, *, expected_sha256: str
) -> dict[str, Any]:
    """Verify and exactly recompile one proof archive using installed code only."""

    if not isinstance(expected_sha256, str) or not _SHA256.fullmatch(expected_sha256):
        _fail("proof_external_digest_invalid")
    if not isinstance(archive, bytes):
        _fail("proof_archive_invalid")
    actual_sha = _sha(archive)
    if actual_sha != expected_sha256:
        _fail("proof_external_digest_mismatch")
    contract, _contract_raw, schema = _load_contract()
    values = _read_archive(archive, contract)
    receipt_path = cast(str, cast(Mapping[str, Any], contract["archive"])["receipt_path"])
    receipt_raw = values[receipt_path]
    receipt = _decode_object(receipt_raw, "proof_receipt_invalid")
    if _canonical_bytes(receipt, "proof_receipt_invalid") != receipt_raw:
        _fail("proof_receipt_invalid", "noncanonical")
    _validate_receipt(receipt, schema, contract)
    members = cast(Sequence[Mapping[str, Any]], receipt["members"])
    member_rows = {cast(str, row["path"]): row for row in members}
    if set(member_rows) != set(values) - {receipt_path}:
        _fail("proof_archive_membership_invalid")
    for path, row in member_rows.items():
        raw = values[path]
        if row.get("sha256") != _sha(raw) or row.get("bytes") != len(raw):
            _fail("proof_receipt_invalid", path)

    for row in _closed_rows(contract, "archive_authorities", expected_count=4):
        if values[row["archive_path"]] != _read_registered_file(
            row["path"], row["file_sha256"], "proof_authority_mismatch"
        ):
            _fail("proof_authority_mismatch", row["path"])

    source_raw = values[_INPUT_PATHS["source"]]
    proof_raw = values[_INPUT_PATHS["proof"]]
    source = _decode_object(source_raw, "proof_input_invalid")
    proof = _decode_object(proof_raw, "proof_input_invalid")
    if (
        _canonical_bytes(source, "proof_input_invalid") != source_raw
        or _canonical_bytes(proof, "proof_input_invalid") != proof_raw
    ):
        _fail("proof_input_invalid", "noncanonical")
    try:
        expected_archive = build_clause_offline_proof(source, proof)
    except ClauseOfflineProofError as exc:
        if exc.code in {
            "proof_authority_mismatch",
            "proof_dependency_drift",
            "proof_runtime_drift",
        }:
            raise
        raise ClauseOfflineProofError("proof_recompile_mismatch", exc.code) from exc
    if expected_archive != archive:
        _fail("proof_recompile_mismatch")
    denominators = cast(Mapping[str, Any], receipt["denominators"])
    return {
        "status": "valid_internal_clause_recompilation",
        "proof_id": receipt["proof_id"],
        "archive_sha256": actual_sha,
        "source_bundle_record_sha256": cast(
            Mapping[str, Any], receipt["bindings"]
        )["source_bundle_ref"]["record_sha256"],
        "role_proof_record_sha256": cast(
            Mapping[str, Any], receipt["bindings"]
        )["role_proof_bundle_ref"]["record_sha256"],
        "active_branch_id": receipt["active_branch_id"],
        "output_denominator": denominators["output_denominator"],
        "role_denominator": denominators["role_denominator"],
        "role_pair_denominator": denominators["role_pair_denominator"],
        "source_clause_denominator": denominators["source_clause_denominator"],
        "trust": dict(_TRUST),
        "boundary": dict(_BOUNDARY),
    }


__all__ = [
    "ClauseOfflineProofError",
    "build_clause_offline_proof",
    "verify_clause_offline_proof",
]
