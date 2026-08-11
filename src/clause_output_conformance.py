"""Closed-universe conformance between clause readers and incumbent outputs.

This module is deliberately internal and synthetic.  It enumerates the complete
two-query authority in the incumbent AnalyticalClause source profile, compiles
both rendering paths from one immutable fixture snapshot, independently verifies
the two clause proof archives, and emits a value-free conformance receipt.  It
does not activate a public output, accept caller query semantics, or generalize
the result beyond the registered synthetic universe.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from src import analytical_clause as analytical
from src import clause_offline_proof as offline_proof
from src import clause_reader_shadow as reader
from src import clause_source_view as source_view
from src import evidence_outputs as incumbent

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "clause_output_conformance_contract.json"
RECEIPT_SCHEMA_PATH = (
    ROOT / "governance" / "schemas" / "clause-output-conformance-receipt.schema.json"
)
VECTORS_PATH = (
    ROOT / "governance" / "clause_output_conformance_adversarial_vectors.json"
)
SOURCE_PROFILE_PATH = ROOT / "governance" / "analytical_clause_source_profile.json"
LIMITATION_REGISTRY_PATH = (
    ROOT / "governance" / "analytical_clause_limitation_registry.json"
)

_CONTRACT_SHA256 = "fc390542cc05eb46c8c159f3cc75b485fa36ba5c3c10da8f073e8b9e8c07990c"
_MANIFEST_RELATIVE_PATH = "canonical/release.json"
_QUERY_IDS = (
    "query:analytical_clause.fixture.path_found",
    "query:analytical_clause.fixture.no_path",
)
_EXPECTED_BRANCHES = ("branch:path_found", "branch:no_path")
_OUTPUTS = (
    ("output:board_brief", "board", "board_brief"),
    ("output:newsroom_claim_card", "newsroom", "newsroom_claim_card"),
    ("output:research_package", "research", "research_package"),
)
_EXCLUDED_OUTPUTS = ("output:offline_audit_bundle",)
_COMMON_SCOPE = "scope:output.all_views"
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
    "closed_synthetic_universe_only": True,
    "general_equivalence": False,
    "real_data_equivalence": False,
    "public_activation": False,
    "product_manifest": False,
    "correction_blast": False,
    "publication_authority": False,
    "offline_audit_bundle_compared": False,
    "live_query_admission_consumed": False,
    "semantic_mapping_registered": False,
}


class ClauseOutputConformanceError(ValueError):
    """Typed fail-closed conformance refusal."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


class _DuplicateKey(ValueError):
    pass


def _fail(code: str, detail: str | None = None) -> NoReturn:
    raise ClauseOutputConformanceError(code, detail)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _decode_json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except _DuplicateKey as exc:
        raise ClauseOutputConformanceError(
            "conformance_json_duplicate_key", str(exc)
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClauseOutputConformanceError(code, type(exc).__name__) from exc
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
        raise ClauseOutputConformanceError(code, type(exc).__name__) from exc


def _artifact_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ClauseOutputConformanceError(
            "conformance_artifact_mismatch", type(exc).__name__
        ) from exc


def _record_sha256(value: Mapping[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("record_sha256", None)
    return _sha(_canonical_bytes(unsigned, "conformance_receipt_invalid"))


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    sealed = dict(value)
    sealed["record_sha256"] = _record_sha256(sealed)
    return sealed


def _read_bytes(path: Path, code: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise ClauseOutputConformanceError(code, str(path)) from exc


def _registered_path(raw: object, code: str) -> Path:
    if not isinstance(raw, str):
        _fail(code)
    path = PurePosixPath(raw)
    if (
        not raw
        or raw.startswith("/")
        or "\\" in raw
        or "\x00" in raw
        or ":" in raw
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
    ):
        _fail(code, raw)
    return ROOT.joinpath(*path.parts)


@dataclass(frozen=True)
class _FixedInputs:
    contract: dict[str, Any]
    contract_raw: bytes
    schema: dict[str, Any]
    schema_raw: bytes
    vectors_raw: bytes
    dependencies: dict[str, bytes]
    runtime_raw: bytes


def _exact_keys(value: Mapping[str, Any], keys: Sequence[str], code: str) -> None:
    if set(value) != set(keys):
        _fail(code)


def _load_fixed_inputs() -> _FixedInputs:
    contract_raw = _read_bytes(CONTRACT_PATH, "conformance_contract_drift")
    if _sha(contract_raw) != _CONTRACT_SHA256:
        _fail("conformance_contract_drift")
    contract = _decode_json(contract_raw, "conformance_contract_invalid")
    _exact_keys(
        contract,
        (
            "schema_version",
            "contract_id",
            "effective",
            "status",
            "default_policy",
            "public_routes",
            "api",
            "fixed_files",
            "installed_dependencies",
            "fixture_snapshot",
            "closed_query_universe",
            "comparison",
            "proof",
            "verification",
            "trust",
            "boundary",
            "claim_boundary",
            "refusal_codes",
        ),
        "conformance_contract_invalid",
    )
    if (
        contract.get("schema_version") != "0.1.0"
        or contract.get("contract_id") != "igrm:clause-output-conformance:0.1.0"
        or contract.get("status") != "internal_synthetic_contract_only"
        or contract.get("default_policy") != "deny"
        or contract.get("public_routes") != []
        or contract.get("trust") != _TRUST
        or contract.get("boundary") != _BOUNDARY
    ):
        _fail("conformance_contract_invalid")
    universe = contract.get("closed_query_universe")
    comparison = contract.get("comparison")
    api = contract.get("api")
    if not all(isinstance(row, dict) for row in (universe, comparison, api)):
        _fail("conformance_contract_invalid")
    universe_map = cast(dict[str, Any], universe)
    comparison_map = cast(dict[str, Any], comparison)
    api_map = cast(dict[str, Any], api)
    if (
        universe_map.get("registered_query_ids") != list(_QUERY_IDS)
        or universe_map.get("registered_query_denominator") != 2
        or universe_map.get("expected_branches") != list(_EXPECTED_BRANCHES)
        or comparison_map.get("compared_output_ids")
        != [output_id for output_id, _role, _key in _OUTPUTS]
        or comparison_map.get("excluded_output_ids") != list(_EXCLUDED_OUTPUTS)
        or api_map.get("compiler_positional_inputs") != ["manifest_path"]
        or api_map.get("verifier_positional_inputs")
        != ["manifest_path", "receipt"]
    ):
        _fail("conformance_contract_invalid")

    fixed_files = contract.get("fixed_files")
    if not isinstance(fixed_files, dict) or set(fixed_files) != {
        "receipt_schema",
        "adversarial_vectors",
    }:
        _fail("conformance_contract_invalid")
    loaded_fixed: dict[str, bytes] = {}
    for key in ("receipt_schema", "adversarial_vectors"):
        row = fixed_files.get(key)
        if not isinstance(row, dict) or set(row) != {"path", "file_sha256"}:
            _fail("conformance_contract_invalid")
        path = _registered_path(row["path"], "conformance_contract_invalid")
        raw = _read_bytes(path, "conformance_contract_invalid")
        if _sha(raw) != row.get("file_sha256"):
            _fail("conformance_contract_invalid", cast(str, row["path"]))
        loaded_fixed[key] = raw
    schema = _decode_json(
        loaded_fixed["receipt_schema"], "conformance_contract_invalid"
    )
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ClauseOutputConformanceError(
            "conformance_contract_invalid", "receipt_schema"
        ) from exc

    refusal_codes = contract.get("refusal_codes")
    vectors = _decode_json(
        loaded_fixed["adversarial_vectors"], "conformance_contract_invalid"
    )
    cases = vectors.get("cases")
    if (
        not isinstance(refusal_codes, list)
        or refusal_codes != sorted(set(refusal_codes))
        or not isinstance(cases, list)
        or vectors.get("case_denominator") != len(cases)
        or len(cases) != 22
    ):
        _fail("conformance_contract_invalid")
    case_ids: set[str] = set()
    mutations: set[str] = set()
    failures: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) != {
            "case_id",
            "mutation",
            "expected",
        }:
            _fail("conformance_contract_invalid")
        case_id = case.get("case_id")
        mutation = case.get("mutation")
        expected = case.get("expected")
        if (
            not isinstance(case_id, str)
            or not isinstance(mutation, str)
            or not isinstance(expected, str)
            or case_id in case_ids
            or mutation in mutations
        ):
            _fail("conformance_contract_invalid")
        case_ids.add(case_id)
        mutations.add(mutation)
        if expected != "valid":
            failures.add(expected)
    if failures != set(cast(list[str], refusal_codes)):
        _fail("conformance_contract_invalid")

    rows = contract.get("installed_dependencies")
    if not isinstance(rows, list) or len(rows) != 16:
        _fail("conformance_contract_invalid")
    dependencies: dict[str, bytes] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "file_sha256"}:
            _fail("conformance_contract_invalid")
        relative = row.get("path")
        if not isinstance(relative, str) or relative in dependencies:
            _fail("conformance_contract_invalid")
        path = _registered_path(relative, "conformance_contract_invalid")
        raw = _read_bytes(path, "conformance_dependency_drift")
        if _sha(raw) != row.get("file_sha256"):
            _fail("conformance_dependency_drift", relative)
        dependencies[relative] = raw
    required = {str(SOURCE_PROFILE_PATH.relative_to(ROOT)), str(LIMITATION_REGISTRY_PATH.relative_to(ROOT))}
    if not required.issubset(dependencies):
        _fail("conformance_contract_invalid")
    runtime_raw = _read_bytes(Path(__file__), "conformance_runtime_drift")
    return _FixedInputs(
        contract=contract,
        contract_raw=contract_raw,
        schema=schema,
        schema_raw=loaded_fixed["receipt_schema"],
        vectors_raw=loaded_fixed["adversarial_vectors"],
        dependencies=dependencies,
        runtime_raw=runtime_raw,
    )


def _check_fixed_unchanged(fixed: _FixedInputs) -> None:
    if _read_bytes(CONTRACT_PATH, "conformance_contract_drift") != fixed.contract_raw:
        _fail("conformance_contract_drift")
    fixed_files = cast(Mapping[str, Mapping[str, Any]], fixed.contract["fixed_files"])
    if _read_bytes(
        _registered_path(fixed_files["receipt_schema"]["path"], "conformance_contract_invalid"),
        "conformance_contract_invalid",
    ) != fixed.schema_raw or _read_bytes(
        _registered_path(fixed_files["adversarial_vectors"]["path"], "conformance_contract_invalid"),
        "conformance_contract_invalid",
    ) != fixed.vectors_raw:
        _fail("conformance_contract_invalid")
    for relative, expected in fixed.dependencies.items():
        if _read_bytes(ROOT / relative, "conformance_dependency_drift") != expected:
            _fail("conformance_dependency_drift", relative)
    if _read_bytes(Path(__file__), "conformance_runtime_drift") != fixed.runtime_raw:
        _fail("conformance_runtime_drift")


@dataclass(frozen=True)
class _FixtureSnapshot:
    files: dict[str, bytes]
    root_sha256: str
    total_bytes: int


def _safe_fixture_relative(relative: str) -> None:
    path = PurePosixPath(relative)
    normalized = unicodedata.normalize("NFC", relative)
    if (
        not relative
        or relative.startswith("/")
        or relative != normalized
        or "\\" in relative
        or "\x00" in relative
        or ":" in relative
        or path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
    ):
        _fail("conformance_fixture_invalid", relative)


def _capture_fixture(manifest_path: Path, contract: Mapping[str, Any]) -> _FixtureSnapshot:
    if not isinstance(manifest_path, Path):
        _fail("conformance_fixture_invalid")
    if manifest_path.is_symlink() or manifest_path.parent.is_symlink():
        _fail("conformance_fixture_invalid", "symlink")
    try:
        manifest = manifest_path.resolve(strict=True)
    except OSError as exc:
        raise ClauseOutputConformanceError(
            "conformance_fixture_invalid", str(manifest_path)
        ) from exc
    root = manifest.parent.parent
    if manifest != root / _MANIFEST_RELATIVE_PATH:
        _fail("conformance_fixture_invalid", "manifest_path")
    rule = contract.get("fixture_snapshot")
    if not isinstance(rule, dict):
        _fail("conformance_contract_invalid")
    max_files = rule.get("max_file_denominator")
    max_entry = rule.get("max_entry_bytes")
    max_total = rule.get("max_total_bytes")
    if not all(type(value) is int and value > 0 for value in (max_files, max_entry, max_total)):
        _fail("conformance_contract_invalid")
    max_files_int = cast(int, max_files)
    max_entry_int = cast(int, max_entry)
    max_total_int = cast(int, max_total)
    files: dict[str, bytes] = {}
    total = 0
    for current, directory_names, file_names in os.walk(root, followlinks=False):
        directory_names.sort()
        file_names.sort()
        current_path = Path(current)
        for name in directory_names:
            directory = current_path / name
            try:
                mode = directory.lstat().st_mode
            except OSError as exc:
                raise ClauseOutputConformanceError(
                    "conformance_fixture_invalid", str(directory)
                ) from exc
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                _fail("conformance_fixture_invalid", "nonregular_directory")
        for name in file_names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            _safe_fixture_relative(relative)
            try:
                before = path.lstat()
            except OSError as exc:
                raise ClauseOutputConformanceError(
                    "conformance_fixture_invalid", relative
                ) from exc
            if not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                _fail("conformance_fixture_invalid", "nonregular_file")
            if before.st_size > max_entry_int:
                _fail("conformance_fixture_invalid", "entry_too_large")
            raw = _read_bytes(path, "conformance_fixture_invalid")
            try:
                after = path.lstat()
            except OSError as exc:
                raise ClauseOutputConformanceError(
                    "conformance_fixture_invalid", relative
                ) from exc
            identity_before = (
                before.st_mode,
                before.st_size,
                before.st_mtime_ns,
                before.st_ino,
            )
            identity_after = (
                after.st_mode,
                after.st_size,
                after.st_mtime_ns,
                after.st_ino,
            )
            if identity_before != identity_after or len(raw) != before.st_size:
                _fail("conformance_fixture_invalid", "capture_race")
            files[relative] = raw
            total += len(raw)
            if len(files) > max_files_int or total > max_total_int:
                _fail("conformance_fixture_invalid", "snapshot_too_large")
    if _MANIFEST_RELATIVE_PATH not in files:
        _fail("conformance_fixture_invalid", "manifest_missing")
    rows = [
        {"path": path, "bytes": len(raw), "sha256": _sha(raw)}
        for path, raw in sorted(files.items())
    ]
    return _FixtureSnapshot(
        files=files,
        root_sha256=_sha(_canonical_bytes(rows, "conformance_fixture_invalid")),
        total_bytes=total,
    )


def _materialize_snapshot(snapshot: _FixtureSnapshot, destination: Path) -> Path:
    for relative, raw in snapshot.files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(raw)
        except OSError as exc:
            raise ClauseOutputConformanceError(
                "conformance_fixture_invalid", relative
            ) from exc
    return destination / _MANIFEST_RELATIVE_PATH


def _registered_queries(fixed: _FixedInputs) -> tuple[dict[str, Any], ...]:
    profile_raw = fixed.dependencies[str(SOURCE_PROFILE_PATH.relative_to(ROOT))]
    profile = _decode_json(profile_raw, "conformance_query_universe_invalid")
    rows = profile.get("query_profiles")
    boundary = profile.get("registered_query_boundary")
    if not isinstance(rows, list) or not isinstance(boundary, dict):
        _fail("conformance_query_universe_invalid")
    queries: list[dict[str, Any]] = []
    seen_tuples: set[tuple[object, ...]] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "query_id",
            "event_id",
            "target_entity_id",
            "max_hops",
            "max_paths",
        }:
            _fail("conformance_query_universe_invalid")
        query_tuple = (
            row["event_id"],
            row["target_entity_id"],
            row["max_hops"],
            row["max_paths"],
        )
        if query_tuple in seen_tuples:
            _fail("conformance_query_universe_invalid")
        seen_tuples.add(query_tuple)
        queries.append(dict(row))
    if (
        tuple(row.get("query_id") for row in queries) != _QUERY_IDS
        or boundary.get("registered_query_ids") != list(_QUERY_IDS)
        or boundary.get("accepted_input") != "exact_registered_query_id_only"
        or boundary.get("tuple_resolver") != "none"
        or boundary.get("caller_authored_event_target_bounds_or_selectors") is not False
    ):
        _fail("conformance_query_universe_invalid")
    return tuple(queries)


def _incumbent_kwargs(root: Path) -> dict[str, Any]:
    governance = root / "governance"
    return {
        "root": root,
        "schema_registry_path": governance / "canonical_schema_registry.json",
        "rights_registry_path": governance / "source_rights_registry.json",
        "rights_signers_path": governance / "rights_signers.json",
        "method_registry_path": governance / "canonical_method_registry.json",
        "release_signers_path": governance / "release_signers.json",
        "output_registry_path": governance / "evidence_output_registry.json",
    }


def _compare_document(
    *,
    output_id: str,
    role_id: str,
    shadow: Mapping[str, Any],
    legacy: Mapping[str, Any],
    reader_row: Mapping[str, Any],
) -> dict[str, Any]:
    shadow_body = dict(shadow)
    legacy_body = dict(legacy)
    shadow_artifact = shadow_body.pop("artifact", None)
    legacy_artifact = legacy_body.pop("artifact", None)
    if _canonical_bytes(shadow_body, "conformance_output_mismatch") != _canonical_bytes(
        legacy_body, "conformance_output_mismatch"
    ):
        _fail("conformance_output_mismatch", output_id)
    if not isinstance(shadow_artifact, dict) or not isinstance(legacy_artifact, dict):
        _fail("conformance_artifact_mismatch", output_id)
    expected_artifact = _artifact_bytes(shadow_body)
    if (
        shadow_artifact != legacy_artifact
        or set(shadow_artifact) != {"filename", "media_type", "sha256", "bytes"}
        or shadow_artifact.get("media_type") != "application/json"
        or shadow_artifact.get("sha256") != _sha(expected_artifact)
        or shadow_artifact.get("bytes") != len(expected_artifact)
        or reader_row.get("artifact_sha256") != shadow_artifact.get("sha256")
        or cast(Mapping[str, Any], reader_row.get("denominators", {})).get(
            "artifact_bytes"
        )
        != len(expected_artifact)
    ):
        _fail("conformance_artifact_mismatch", output_id)
    shadow_document_bytes = _canonical_bytes(shadow, "conformance_output_mismatch")
    if shadow_document_bytes != _canonical_bytes(
        legacy, "conformance_output_mismatch"
    ):
        _fail("conformance_output_mismatch", output_id)
    body_sha = _sha(_canonical_bytes(shadow_body, "conformance_output_mismatch"))
    if reader_row.get("body_sha256") != body_sha:
        _fail("conformance_output_mismatch", output_id)
    if (
        reader_row.get("output_id") != output_id
        or reader_row.get("role_id") != role_id
    ):
        _fail("conformance_output_mismatch", output_id)
    return {
        "output_id": output_id,
        "role_id": role_id,
        "document_sha256": _sha(shadow_document_bytes),
        "body_sha256": body_sha,
        "artifact_sha256": shadow_artifact["sha256"],
        "artifact_bytes": shadow_artifact["bytes"],
        "artifact_descriptor_sha256": _sha(
            _canonical_bytes(shadow_artifact, "conformance_artifact_mismatch")
        ),
        "comparison_status": (
            "exact_document_body_artifact_descriptor_and_limitations"
        ),
    }


def _common_scope(
    fixed: _FixedInputs,
    output_set: Mapping[str, Any],
    reader_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    raw = fixed.dependencies[str(LIMITATION_REGISTRY_PATH.relative_to(ROOT))]
    registry = _decode_json(raw, "conformance_common_scope_mismatch")
    profiles = registry.get("output_profiles")
    if not isinstance(profiles, dict):
        _fail("conformance_common_scope_mismatch")
    expected = profiles.get(_COMMON_SCOPE)
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) != len(set(expected))
        or expected != sorted(expected)
        or output_set.get("limitations") != expected
    ):
        _fail("conformance_common_scope_mismatch")
    output_rows = reader_receipt.get("outputs")
    if not isinstance(output_rows, list) or len(output_rows) != 3:
        _fail("conformance_common_scope_mismatch")
    for row in output_rows:
        if (
            not isinstance(row, dict)
            or row.get("applicable_but_outer_wrapper_absent_scope_ids")
            != [_COMMON_SCOPE]
        ):
            _fail("conformance_common_scope_mismatch")
    return {
        "scope_id": _COMMON_SCOPE,
        "limitation_ids": expected,
        "limitation_denominator": len(expected),
        "limitation_digest_sha256": _sha(
            _canonical_bytes(expected, "conformance_common_scope_mismatch")
        ),
        "shadow_outer_wrapper_absent_denominator": 3,
    }


def _compile_query(
    manifest: Path,
    root: Path,
    query: Mapping[str, Any],
    fixed: _FixedInputs,
) -> tuple[dict[str, Any], dict[str, Any]]:
    query_id = cast(str, query["query_id"])
    try:
        source, role_proof = analytical.compile_source_bound_clauses(
            manifest, query_id, root=root
        )
    except analytical.AnalyticalClauseError as exc:
        raise ClauseOutputConformanceError("conformance_source_invalid", exc.code) from exc
    try:
        views = source_view.compile_clause_source_views(source, role_proof)
        views.verify()
    except source_view.ClauseSourceViewError as exc:
        raise ClauseOutputConformanceError("conformance_view_invalid", exc.code) from exc
    try:
        shadow = reader.compile_clause_reader_shadow(views)
        shadow.verify()
    except reader.ClauseReaderShadowError as exc:
        raise ClauseOutputConformanceError("conformance_reader_invalid", exc.code) from exc
    try:
        archive = offline_proof.build_clause_offline_proof(source, role_proof)
        archive_sha = _sha(archive)
        proof_summary = offline_proof.verify_clause_offline_proof(
            archive, expected_sha256=archive_sha
        )
    except offline_proof.ClauseOfflineProofError as exc:
        raise ClauseOutputConformanceError("conformance_proof_invalid", exc.code) from exc
    if proof_summary.get("status") != "valid_internal_clause_recompilation":
        _fail("conformance_proof_invalid")
    try:
        output_set = incumbent.compile_evidence_outputs(
            manifest,
            cast(str, query["event_id"]),
            cast(str, query["target_entity_id"]),
            max_hops=cast(int, query["max_hops"]),
            max_paths=cast(int, query["max_paths"]),
            **_incumbent_kwargs(root),
        )
    except incumbent.EvidenceOutputError as exc:
        raise ClauseOutputConformanceError(
            "conformance_incumbent_invalid", exc.code
        ) from exc
    expected_query = {
        key: query[key]
        for key in ("event_id", "target_entity_id", "max_hops", "max_paths")
    }
    if output_set.get("query") != expected_query:
        _fail("conformance_incumbent_invalid", "query")
    outputs = output_set.get("outputs")
    reader_receipt = shadow.receipt
    reader_rows_raw = reader_receipt.get("outputs")
    if (
        not isinstance(outputs, dict)
        or set(outputs) != {
            "research_package",
            "board_brief",
            "newsroom_claim_card",
            "offline_audit_bundle",
        }
        or not isinstance(reader_rows_raw, list)
        or len(reader_rows_raw) != 3
    ):
        _fail("conformance_output_mismatch")
    reader_rows = {
        row.get("output_id"): row for row in reader_rows_raw if isinstance(row, dict)
    }
    if set(reader_rows) != {row[0] for row in _OUTPUTS}:
        _fail("conformance_output_mismatch")
    shadow_documents: dict[str, Mapping[str, Any]] = {
        "board_brief": shadow.board_brief,
        "newsroom_claim_card": shadow.newsroom_claim_card,
        "research_package": shadow.research_package,
    }
    comparisons = [
        _compare_document(
            output_id=output_id,
            role_id=role_id,
            shadow=shadow_documents[key],
            legacy=cast(Mapping[str, Any], outputs[key]),
            reader_row=cast(Mapping[str, Any], reader_rows[output_id]),
        )
        for output_id, role_id, key in _OUTPUTS
    ]
    common_scope = _common_scope(fixed, output_set, reader_receipt)
    branch = reader_receipt.get("active_branch_id")
    source_query = source.get("query")
    if (
        branch not in _EXPECTED_BRANCHES
        or not isinstance(source_query, dict)
        or source_query.get("query_id") != query_id
    ):
        _fail("conformance_query_universe_invalid", query_id)
    query_receipt = {
        "query_id": query_id,
        "active_branch_id": branch,
        "source_bundle_ref": {"record_sha256": source["record_sha256"]},
        "role_proof_bundle_ref": {"record_sha256": role_proof["record_sha256"]},
        "view_receipt_ref": {"record_sha256": views.receipt["record_sha256"]},
        "reader_receipt_ref": {"record_sha256": reader_receipt["record_sha256"]},
        "proof_archive_ref": {
            "proof_id": proof_summary["proof_id"],
            "sha256": archive_sha,
            "bytes": len(archive),
            "verification_status": proof_summary["status"],
        },
        "incumbent_output_set_ref": {
            "record_sha256": output_set["record_sha256"]
        },
        "comparisons": comparisons,
        "common_scope": common_scope,
    }
    return query_receipt, source


def _validate_receipt(receipt: Mapping[str, Any], fixed: _FixedInputs) -> None:
    try:
        Draft202012Validator(fixed.schema).validate(receipt)
    except ValidationError as exc:
        raise ClauseOutputConformanceError(
            "conformance_receipt_invalid", "/".join(str(item) for item in exc.path)
        ) from exc
    if receipt.get("record_sha256") != _record_sha256(receipt):
        _fail("conformance_record_digest_mismatch")
    queries = receipt.get("queries")
    if not isinstance(queries, list) or tuple(
        row.get("query_id") for row in queries if isinstance(row, dict)
    ) != _QUERY_IDS:
        _fail("conformance_receipt_invalid", "query_order")
    for row, branch in zip(queries, _EXPECTED_BRANCHES, strict=True):
        if not isinstance(row, dict) or row.get("active_branch_id") != branch:
            _fail("conformance_receipt_invalid", "branch_order")
        comparisons = row.get("comparisons")
        if not isinstance(comparisons, list) or [
            item.get("output_id") for item in comparisons if isinstance(item, dict)
        ] != [item[0] for item in _OUTPUTS]:
            _fail("conformance_receipt_invalid", "output_order")
        common = row.get("common_scope")
        if (
            not isinstance(common, dict)
            or common.get("limitation_denominator")
            != len(cast(Sequence[object], common.get("limitation_ids", [])))
            or common.get("limitation_digest_sha256")
            != _sha(
                _canonical_bytes(
                    common.get("limitation_ids"),
                    "conformance_receipt_invalid",
                )
            )
        ):
            _fail("conformance_receipt_invalid", "common_scope")
    if receipt.get("trust") != _TRUST or receipt.get("boundary") != _BOUNDARY:
        _fail("conformance_receipt_invalid", "boundary")


def _compile_captured(
    snapshot: _FixtureSnapshot, fixed: _FixedInputs
) -> dict[str, Any]:
    queries = _registered_queries(fixed)
    with tempfile.TemporaryDirectory(prefix="igrm-clause-conformance-") as temporary:
        root = Path(temporary)
        manifest = _materialize_snapshot(snapshot, root)
        query_rows: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        for query in queries:
            query_receipt, source = _compile_query(
                manifest, root, query, fixed
            )
            query_rows.append(query_receipt)
            source_rows.append(source)
    branches = [row["active_branch_id"] for row in query_rows]
    if branches != list(_EXPECTED_BRANCHES):
        _fail("conformance_query_universe_invalid", "branch_denominator")
    release_refs = {
        (
            cast(Mapping[str, Any], source["source_release"])["release_id"],
            cast(Mapping[str, Any], source["source_release"])["record_sha256"],
        )
        for source in source_rows
    }
    if len(release_refs) != 1:
        _fail("conformance_query_universe_invalid", "release_splice")
    release_id, release_sha = next(iter(release_refs))
    contract_sha = _sha(fixed.contract_raw)
    runtime_sha = _sha(fixed.runtime_raw)
    source_profile_sha = _sha(
        fixed.dependencies[str(SOURCE_PROFILE_PATH.relative_to(ROOT))]
    )
    identity = {
        "contract_sha256": contract_sha,
        "runtime_sha256": runtime_sha,
        "source_profile_sha256": source_profile_sha,
        "fixture_root_sha256": snapshot.root_sha256,
        "release_record_sha256": release_sha,
        "query_refs": [
            {
                "query_id": row["query_id"],
                "source_record_sha256": row["source_bundle_ref"]["record_sha256"],
                "proof_archive_sha256": row["proof_archive_ref"]["sha256"],
                "incumbent_record_sha256": row["incumbent_output_set_ref"][
                    "record_sha256"
                ],
            }
            for row in query_rows
        ],
    }
    receipt = _seal(
        {
            "object_type": "clause_output_conformance_receipt",
            "schema_version": "0.1.0",
            "conformance_id": (
                "clause-output-conformance:"
                + _sha(_canonical_bytes(identity, "conformance_receipt_invalid"))[:24]
            ),
            "status": "exact_closed_synthetic_universe_conformance",
            "bindings": {
                "contract_ref": {
                    "path": str(CONTRACT_PATH.relative_to(ROOT)),
                    "file_sha256": contract_sha,
                },
                "runtime_ref": {
                    "path": str(Path(__file__).relative_to(ROOT)),
                    "file_sha256": runtime_sha,
                },
                "source_profile_ref": {
                    "path": str(SOURCE_PROFILE_PATH.relative_to(ROOT)),
                    "file_sha256": source_profile_sha,
                },
                "release_ref": {
                    "release_id": release_id,
                    "record_sha256": release_sha,
                },
                "fixture_snapshot_ref": {
                    "root_sha256": snapshot.root_sha256,
                    "file_denominator": len(snapshot.files),
                    "total_bytes": snapshot.total_bytes,
                    "manifest_path": _MANIFEST_RELATIVE_PATH,
                },
            },
            "queries": query_rows,
            "denominators": {
                "registered_query_denominator": 2,
                "compared_query_denominator": 2,
                "comparison_cell_denominator": 6,
                "proof_archive_denominator": 2,
                "path_found_branch_denominator": 1,
                "no_path_branch_denominator": 1,
                "compared_output_denominator": 3,
                "excluded_output_denominator": 1,
            },
            "excluded_output_ids": list(_EXCLUDED_OUTPUTS),
            "trust": dict(_TRUST),
            "boundary": dict(_BOUNDARY),
        }
    )
    _validate_receipt(receipt, fixed)
    return receipt


def compile_clause_output_conformance(manifest_path: Path) -> dict[str, Any]:
    """Compile the complete registered synthetic conformance receipt."""

    fixed = _load_fixed_inputs()
    snapshot = _capture_fixture(manifest_path, fixed.contract)
    receipt = _compile_captured(snapshot, fixed)
    _check_fixed_unchanged(fixed)
    return _decode_json(
        _canonical_bytes(receipt, "conformance_receipt_invalid"),
        "conformance_receipt_invalid",
    )


def verify_clause_output_conformance(
    manifest_path: Path, receipt: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate, recompile and byte-compare one conformance receipt."""

    if not isinstance(receipt, Mapping):
        _fail("conformance_receipt_invalid")
    captured = _decode_json(
        _canonical_bytes(receipt, "conformance_receipt_invalid"),
        "conformance_receipt_invalid",
    )
    fixed = _load_fixed_inputs()
    _validate_receipt(captured, fixed)
    expected = compile_clause_output_conformance(manifest_path)
    if _canonical_bytes(captured, "conformance_receipt_invalid") != _canonical_bytes(
        expected, "conformance_receipt_invalid"
    ):
        _fail("conformance_recompile_mismatch")
    _check_fixed_unchanged(fixed)
    return {
        "status": "exact_closed_synthetic_universe_conformance",
        "conformance_id": captured["conformance_id"],
        "record_sha256": captured["record_sha256"],
        "compared_query_denominator": 2,
        "comparison_cell_denominator": 6,
        "proof_archive_denominator": 2,
        "general_equivalence": False,
        "public_activation": False,
    }


__all__ = [
    "ClauseOutputConformanceError",
    "compile_clause_output_conformance",
    "verify_clause_output_conformance",
]
