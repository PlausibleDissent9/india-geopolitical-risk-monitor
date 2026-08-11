"""Deterministic Git-candidate byte inventory for the public data API.

This is a repository-consistency primitive, not a signature or deployment
attestation.  A build consumes one captured Git index/tree object map and
never re-opens endpoint paths through the mutable filesystem.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_REPOSITORY_PATH = "docs/data/public_api_byte_manifest.json"
MANIFEST_API_PATH = "data/public_api_byte_manifest.json"
CONTRACT_PATH = "governance/public_api_byte_manifest_contract.json"
PROFILE_PATH = "governance/public_api_byte_manifest_profile.json"
SCHEMA_PATH = "governance/schemas/public-api-byte-manifest.schema.json"
GENERATOR_PATH = "scripts/generate_public_api_byte_manifest.py"
RUNTIME_PATH = "src/public_api_byte_manifest.py"
API_CONTRACT_PATH = "docs/data/api_contract.json"
VERSION = "0.1.0"
MAX_ENTRY_BYTES = 4 * 1024 * 1024
MAX_HASHED_BYTES = 12 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class PublicAPIByteManifestError(ValueError):
    """Stable fail-closed refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise PublicAPIByteManifestError(code, detail)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _json_object(raw: bytes, code: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(code, f"duplicate_key:{key}")
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PublicAPIByteManifestError(code, "json") from exc
    if not isinstance(value, dict):
        _fail(code, "root")
    return cast(dict[str, Any], value)


def _safe_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or ":" in value
    ):
        _fail("candidate_path_invalid")
    if unicodedata.normalize("NFC", value) != value:
        _fail("candidate_path_invalid", value)
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or parsed.parts != tuple(value.split("/")) or any(
        part in {"", ".", ".."} for part in parsed.parts
    ):
        _fail("candidate_path_invalid", value)
    return value


@dataclass(frozen=True)
class GitBlob:
    mode: str
    oid: str
    raw: bytes


@dataclass(frozen=True)
class GitSnapshot:
    root: Path
    identity: str
    files: dict[str, GitBlob]

    def require(self, path: str) -> GitBlob:
        try:
            return self.files[path]
        except KeyError as exc:
            raise PublicAPIByteManifestError(
                "candidate_required_path_missing", path
            ) from exc


def _git(root: Path, args: list[str], *, binary: bool = True) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, check=False
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace")[-300:]
        _fail("candidate_git_read_failed", detail)
    return result.stdout if binary else result.stdout


def _capture_blobs(root: Path, rows: list[tuple[str, str, str]], identity: str) -> GitSnapshot:
    files: dict[str, GitBlob] = {}
    folded: dict[str, str] = {}
    normalized: list[tuple[str, str, str]] = []
    for mode, oid, path_value in rows:
        path = _safe_path(path_value)
        folded_key = path.casefold()
        if path in files or (folded_key in folded and folded[folded_key] != path):
            _fail("candidate_path_collision", path)
        if not SHA256_RE.fullmatch(oid):
            # Git SHA-1 repositories are currently used by IGRM; object IDs
            # are identity only, never the public content digest.
            if not re.fullmatch(r"[0-9a-f]{40}", oid):
                _fail("candidate_git_object_invalid", path)
        folded[folded_key] = path
        normalized.append((mode, oid, path))
    unique_oids = list(dict.fromkeys(oid for _mode, oid, _path in normalized))
    process = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        input=("\n".join(unique_oids) + "\n").encode("ascii"),
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        _fail(
            "candidate_git_read_failed",
            process.stderr.decode("utf-8", errors="replace")[-300:],
        )
    cursor = 0
    objects: dict[str, bytes] = {}
    for requested_oid in unique_oids:
        header_end = process.stdout.find(b"\n", cursor)
        if header_end < 0:
            _fail("candidate_git_read_failed", "batch_header")
        header = process.stdout[cursor:header_end].decode("ascii", errors="replace")
        cursor = header_end + 1
        parts = header.split()
        if len(parts) != 3 or parts[0] != requested_oid or parts[1] != "blob":
            _fail("candidate_git_read_failed", header)
        try:
            size = int(parts[2])
        except ValueError as exc:
            raise PublicAPIByteManifestError(
                "candidate_git_read_failed", header
            ) from exc
        end = cursor + size
        if end >= len(process.stdout) or process.stdout[end : end + 1] != b"\n":
            _fail("candidate_git_read_failed", "batch_body")
        objects[requested_oid] = process.stdout[cursor:end]
        cursor = end + 1
    if cursor != len(process.stdout):
        _fail("candidate_git_read_failed", "batch_trailing")
    for mode, oid, path in normalized:
        files[path] = GitBlob(mode=mode, oid=oid, raw=objects[oid])
    return GitSnapshot(root=root, identity=identity, files=files)


def capture_index(root: Path = ROOT) -> GitSnapshot:
    raw = _git(root, ["ls-files", "--stage", "-z"])
    rows: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_raw = record.split(b"\t", 1)
            mode_raw, oid_raw, stage_raw = header.split(b" ", 2)
            path = path_raw.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise PublicAPIByteManifestError("candidate_git_object_invalid") from exc
        if stage_raw != b"0":
            _fail("candidate_index_unmerged", path)
        rows.append((mode_raw.decode(), oid_raw.decode(), path))
    index_file = os.environ.get("GIT_INDEX_FILE", ".git/index")
    return _capture_blobs(root, rows, f"index:{index_file}")


def capture_tree(treeish: str, root: Path = ROOT) -> GitSnapshot:
    if not treeish or treeish.startswith("-"):
        _fail("candidate_git_object_invalid", "treeish")
    raw = _git(root, ["ls-tree", "-r", "-z", treeish])
    rows: list[tuple[str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_raw = record.split(b"\t", 1)
            mode_raw, kind_raw, oid_raw = header.split(b" ", 2)
            path = path_raw.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise PublicAPIByteManifestError("candidate_git_object_invalid") from exc
        if kind_raw != b"blob":
            _fail("candidate_mode_invalid", path)
        rows.append((mode_raw.decode(), oid_raw.decode(), path))
    resolved = _git(root, ["rev-parse", "--verify", f"{treeish}^{{tree}}"])
    return _capture_blobs(root, rows, f"tree:{resolved.decode().strip()}")


def _validate_profile(source: GitSnapshot) -> tuple[dict[str, Any], str]:
    profile_blob = source.require(PROFILE_PATH)
    profile = _json_object(profile_blob.raw, "profile_invalid")
    if (
        set(profile) != {"schema_version", "profile_id", "status", "effective", "dependencies"}
        or profile.get("schema_version") != VERSION
        or profile.get("profile_id") != "igrm:public-api-byte-manifest:0.1.0"
        or profile.get("status") != "repository_self_consistency_only"
        or profile.get("effective") != "2026-08-10"
        or not isinstance(profile.get("dependencies"), dict)
    ):
        _fail("profile_invalid")
    expected_paths = {CONTRACT_PATH, SCHEMA_PATH, GENERATOR_PATH, RUNTIME_PATH}
    dependencies = cast(dict[str, Any], profile["dependencies"])
    if set(dependencies) != expected_paths:
        _fail("profile_invalid", "dependencies")
    for path, expected in dependencies.items():
        blob = source.require(path)
        expected_mode = "100755" if path == GENERATOR_PATH else "100644"
        if blob.mode != expected_mode:
            _fail("candidate_mode_invalid", f"{path}:{blob.mode}")
        if not isinstance(expected, str) or expected != _sha(blob.raw):
            _fail("candidate_dependency_drift", path)
    # Refuse executing a different runtime/generator than the captured
    # candidate.  This is code-to-input parity, not external authentication.
    if _sha(Path(__file__).read_bytes()) != dependencies[RUNTIME_PATH]:
        _fail("candidate_dependency_drift", "executing_runtime")
    return profile, _sha(profile_blob.raw)


def _endpoint_rows(contract: dict[str, Any]) -> tuple[str, list[tuple[str, str]]]:
    meta = contract.get("_meta")
    endpoints = contract.get("endpoints")
    if not isinstance(meta, dict) or not isinstance(endpoints, list):
        _fail("api_contract_invalid")
    version = meta.get("contract_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        _fail("api_contract_invalid", "version")
    rows: list[tuple[str, str]] = []
    exact: set[str] = set()
    folded: set[str] = set()
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            _fail("api_contract_invalid", "endpoint")
        path = _safe_path(endpoint.get("path"))
        fmt = endpoint.get("format")
        if fmt not in {"json", "csv", "rss"}:
            _fail("api_contract_invalid", f"format:{path}")
        if path in exact or path.casefold() in folded:
            _fail("candidate_path_collision", path)
        exact.add(path)
        folded.add(path.casefold())
        rows.append((path, cast(str, fmt)))
    rows.sort(key=lambda row: row[0].encode("utf-8"))
    if sum(path == MANIFEST_API_PATH for path, _fmt in rows) != 1:
        _fail("manifest_self_exclusion_invalid")
    return version, rows


def build_manifest(source: GitSnapshot) -> dict[str, Any]:
    _profile, profile_sha = _validate_profile(source)
    contract_definition = _json_object(
        source.require(CONTRACT_PATH).raw, "manifest_contract_drift"
    )
    if (
        contract_definition.get("contract_id") != "igrm:public-api-byte-manifest:0.1.0"
        or contract_definition.get("status") != "repository_self_consistency_only"
        or contract_definition.get("public_path") != MANIFEST_REPOSITORY_PATH
        or contract_definition.get("api_path") != MANIFEST_API_PATH
        or contract_definition.get("limits")
        != {"max_entry_bytes": MAX_ENTRY_BYTES, "max_hashed_bytes": MAX_HASHED_BYTES}
    ):
        _fail("manifest_contract_drift")
    api_contract_blob = source.require(API_CONTRACT_PATH)
    api_contract = _json_object(api_contract_blob.raw, "api_contract_invalid")
    contract_version, rows = _endpoint_rows(api_contract)
    entries: list[dict[str, Any]] = []
    total = 0
    for public_path, fmt in rows:
        if public_path == MANIFEST_API_PATH:
            continue
        repository_path = _safe_path(f"docs/{public_path}")
        blob = source.require(repository_path)
        if blob.mode != "100644":
            _fail("candidate_mode_invalid", f"{repository_path}:{blob.mode}")
        size = len(blob.raw)
        if size > MAX_ENTRY_BYTES:
            _fail("candidate_size_limit_exceeded", repository_path)
        total += size
        if total > MAX_HASHED_BYTES:
            _fail("candidate_size_limit_exceeded", "aggregate")
        entries.append(
            {
                "path": public_path,
                "repository_path": repository_path,
                "format": fmt,
                "git_mode": blob.mode,
                "bytes": size,
                "sha256": _sha(blob.raw),
            }
        )
    endpoint_identity = [{"path": path, "format": fmt} for path, fmt in rows]
    return {
        "_meta": {
            "what": "Deterministic byte inventory for every other frozen API-contract endpoint; self-excluded and unsigned.",
            "license": "CC BY 4.0",
            "citation": "Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/",
            "codebook": "https://igrm.in/codebook.html",
            "source": "https://igrm.in/data/public_api_byte_manifest.json",
        },
        "object_type": "igrm.public_api_byte_manifest",
        "schema_version": VERSION,
        "profile": {"path": PROFILE_PATH, "raw_sha256": profile_sha},
        "api_contract": {
            "path": API_CONTRACT_PATH,
            "raw_sha256": _sha(api_contract_blob.raw),
            "contract_version": contract_version,
            "endpoint_denominator": len(rows),
        },
        "universe": {
            "basis": "api_contract.endpoints",
            "endpoint_denominator": len(rows),
            "hashed_endpoint_denominator": len(entries),
            "excluded_endpoint_denominator": 1,
            "order": "public_path_utf8_byte_ascending",
            "endpoint_set_sha256": _sha(canonical_json(endpoint_identity)),
        },
        "entries": entries,
        "excluded_entries": [
            {
                "path": MANIFEST_API_PATH,
                "repository_path": MANIFEST_REPOSITORY_PATH,
                "reason": "self_exclusion_avoids_recursive_digest",
            }
        ],
        "totals": {
            "hashed_entries": len(entries),
            "hashed_bytes": total,
            "max_entry_bytes": MAX_ENTRY_BYTES,
            "max_hashed_bytes": MAX_HASHED_BYTES,
        },
        "integrity": {
            "algorithm": "SHA-256",
            "entries_sha256": _sha(canonical_json(entries)),
            "external_manifest_digest_required": True,
            "signed": False,
            "authenticated_deployment": False,
            "atomic_hosted_snapshot": False,
        },
        "claim_boundary": contract_definition["claim_boundary"],
    }


def expected_manifest_bytes(source: GitSnapshot) -> bytes:
    return canonical_json(build_manifest(source))


def write_from_index(root: Path = ROOT) -> bytes:
    source = capture_index(root)
    raw = expected_manifest_bytes(source)
    destination = root / MANIFEST_REPOSITORY_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    return raw


def verify_index(root: Path = ROOT) -> dict[str, Any]:
    source = capture_index(root)
    actual = source.require(MANIFEST_REPOSITORY_PATH).raw
    expected = expected_manifest_bytes(source)
    if actual != expected:
        _fail("manifest_snapshot_mismatch", source.identity)
    return _json_object(actual, "manifest_body_invalid")


def verify_tree(treeish: str, root: Path = ROOT) -> dict[str, Any]:
    source = capture_tree(treeish, root)
    actual = source.require(MANIFEST_REPOSITORY_PATH).raw
    expected = expected_manifest_bytes(source)
    if actual != expected:
        _fail("manifest_snapshot_mismatch", source.identity)
    return _json_object(actual, "manifest_body_invalid")
