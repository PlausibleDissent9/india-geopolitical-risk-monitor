from __future__ import annotations

import hashlib
import io
import json
import socket
import stat
import warnings
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from src import analytical_clause as ac
from src import clause_offline_proof as proof_archive
from src import evidence_outputs_fixture

ROOT = Path(__file__).resolve().parents[1]
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_MODE = 0o100644


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inputs(tmp_path: Path, query_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path / "fixture")
    return ac.compile_source_bound_clauses(
        fixture.manifest, query_id, root=fixture.root
    )


def _build(tmp_path: Path, query_id: str = PATH_QUERY) -> bytes:
    source, role_proof = _inputs(tmp_path, query_id)
    return proof_archive.build_clause_offline_proof(source, role_proof)


def _verify(archive: bytes) -> dict[str, Any]:
    return proof_archive.verify_clause_offline_proof(
        archive, expected_sha256=_sha(archive)
    )


def _read_entries(archive: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(archive), "r") as opened:
        return [(info.filename, opened.read(info)) for info in opened.infolist()]


def _pack(
    entries: list[tuple[str, bytes]],
    *,
    changed_name: str | None = None,
    compression: int = zipfile.ZIP_STORED,
    timestamp: tuple[int, int, int, int, int, int] = FIXED_TIME,
    mode: int = FIXED_MODE,
) -> bytes:
    stream = io.BytesIO()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Duplicate name:")
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as opened:
            for name, raw in entries:
                info = zipfile.ZipInfo(
                    name,
                    date_time=timestamp if name == changed_name else FIXED_TIME,
                )
                info.compress_type = (
                    compression if name == changed_name else zipfile.ZIP_STORED
                )
                info.create_system = 3
                info.external_attr = (
                    mode if name == changed_name else FIXED_MODE
                ) << 16
                opened.writestr(info, raw)
    return stream.getvalue()


def _json(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw)
    assert isinstance(value, dict)
    return value


def _seal(value: dict[str, Any]) -> bytes:
    sealed = dict(value)
    sealed.pop("record_sha256", None)
    sealed["record_sha256"] = _sha(ac.serialize_record(sealed))
    return ac.serialize_record(sealed)


def _replace_member(
    archive: bytes,
    member_path: str,
    mutate: Callable[[bytes], bytes],
) -> bytes:
    entries = dict(_read_entries(archive))
    entries[member_path] = mutate(entries[member_path])
    receipt = _json(entries["proof-receipt.json"])
    for row in receipt["members"]:
        if row["path"] == member_path:
            row["sha256"] = _sha(entries[member_path])
            row["bytes"] = len(entries[member_path])
            break
    else:  # pragma: no cover - fixture invariant
        raise AssertionError(member_path)
    entries["proof-receipt.json"] = _seal(receipt)
    return _pack(sorted(entries.items()))


def _mutate_json(raw: bytes) -> bytes:
    value = _json(raw)
    value["test_mutation"] = True
    return ac.serialize_record(value)


def _mutate_receipt(archive: bytes, mutation: str) -> bytes:
    entries = dict(_read_entries(archive))
    receipt = _json(entries["proof-receipt.json"])
    if mutation == "receipt_denominator":
        receipt["denominators"]["archive_entry_denominator"] = 11
    elif mutation == "receipt_output_role":
        receipt["outputs"][0]["output_id"] = "output:research_package"
    else:  # pragma: no cover - closed caller
        raise AssertionError(mutation)
    entries["proof-receipt.json"] = _seal(receipt)
    return _pack(sorted(entries.items()))


def _structural_mutation(archive: bytes, mutation: str) -> bytes:
    entries = _read_entries(archive)
    target = entries[0][0]
    if mutation == "absolute_path":
        entries[0] = ("/" + target, entries[0][1])
        return _pack(entries)
    if mutation == "parent_path":
        entries[0] = ("../" + target, entries[0][1])
        return _pack(entries)
    if mutation == "backslash_path":
        entries[0] = (target.replace("/", "\\", 1), entries[0][1])
        return _pack(entries)
    if mutation == "duplicate_path":
        return _pack(entries + [entries[0]])
    if mutation == "symlink_entry":
        return _pack(entries, changed_name=target, mode=stat.S_IFLNK | 0o777)
    if mutation == "deflate_entry":
        return _pack(entries, changed_name=target, compression=zipfile.ZIP_DEFLATED)
    if mutation == "timestamp":
        return _pack(entries, changed_name=target, timestamp=(2026, 8, 10, 0, 0, 0))
    if mutation == "empty_entry":
        entries[0] = (target, b"")
        return _pack(entries)
    if mutation == "bundled_code":
        return _pack(entries + [("verify.py", b"raise SystemExit\n")])
    if mutation == "missing_member":
        return _pack(entries[1:])
    raise AssertionError(mutation)


def _semantic_mutation(archive: bytes, mutation: str) -> bytes:
    member_paths = {
        "source_record": "inputs/source-bundle.json",
        "proof_record": "inputs/role-proof-bundle.json",
        "view_receipt": "receipts/clause-source-view.json",
        "reader_receipt": "receipts/clause-reader-compilation.json",
        "research_artifact": "artifacts/research-package.json",
        "board_artifact": "artifacts/board-brief.json",
        "newsroom_artifact": "artifacts/newsroom-claim-card.json",
        "authority_profile": "authority/clause-reader-template-profile.json",
    }
    if mutation in member_paths:
        return _replace_member(archive, member_paths[mutation], _mutate_json)
    if mutation == "duplicate_json_key":
        return _replace_member(
            archive,
            "inputs/source-bundle.json",
            lambda _raw: b'{"duplicate":1,"duplicate":2}\n',
        )
    if mutation in {"receipt_denominator", "receipt_output_role"}:
        return _mutate_receipt(archive, mutation)
    raise AssertionError(mutation)


def _copy_registered_root(tmp_path: Path) -> Path:
    isolated = tmp_path / "installed-root"
    contract = json.loads(
        (ROOT / "governance/clause_offline_proof_contract.json").read_text(
            encoding="utf-8"
        )
    )
    relative_paths = {
        "governance/clause_offline_proof_contract.json",
        *(row["path"] for row in contract["fixed_files"].values()),
        *(row["source_path"] for row in contract["archive_authorities"]),
        *(row["path"] for row in contract["installed_dependencies"]),
    }
    for relative in relative_paths:
        target = isolated / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return isolated


@pytest.mark.parametrize("query_id", [PATH_QUERY, NO_PATH_QUERY])
def test_archive_is_deterministic_and_recompiles_both_branches(
    tmp_path: Path, query_id: str
) -> None:
    source, role_proof = _inputs(tmp_path, query_id)
    first = proof_archive.build_clause_offline_proof(source, role_proof)
    second = proof_archive.build_clause_offline_proof(source, role_proof)
    assert first == second
    summary = _verify(first)
    assert summary["status"] == "valid_internal_clause_recompilation"
    assert summary["active_branch_id"] == (
        "branch:no_path" if query_id == NO_PATH_QUERY else "branch:path_found"
    )
    assert summary["output_denominator"] == 3
    assert summary["role_denominator"] == 7
    assert summary["role_pair_denominator"] == 21
    assert summary["trust"]["contract_only"] is True
    assert summary["boundary"]["offline_audience_output_created"] is False
    assert summary["boundary"]["public_behavior_changed"] is False


def test_archive_has_closed_deterministic_nonexecutable_shape(tmp_path: Path) -> None:
    archive = _build(tmp_path)
    with zipfile.ZipFile(io.BytesIO(archive), "r") as opened:
        infos = opened.infolist()
        assert [row.filename for row in infos] == sorted(row.filename for row in infos)
        assert len(infos) == 12
        assert opened.comment == b""
        for row in infos:
            assert row.compress_type == zipfile.ZIP_STORED
            assert row.date_time == FIXED_TIME
            assert row.create_system == 3
            assert row.external_attr >> 16 == FIXED_MODE
            assert not row.extra
            assert not row.comment
            assert not row.filename.endswith((".py", ".so", ".sh"))


def test_builder_captures_inputs_without_retained_aliases(tmp_path: Path) -> None:
    source, role_proof = _inputs(tmp_path, PATH_QUERY)
    archive = proof_archive.build_clause_offline_proof(source, role_proof)
    source.clear()
    role_proof.clear()
    assert _verify(archive)["status"] == "valid_internal_clause_recompilation"


def test_receipt_is_counts_hashes_ids_only(tmp_path: Path) -> None:
    archive = _build(tmp_path)
    receipt = _json(dict(_read_entries(archive))["proof-receipt.json"])
    encoded = json.dumps(receipt, sort_keys=True)
    assert set(receipt["denominators"]) == {
        "archive_entry_denominator",
        "authority_denominator",
        "input_denominator",
        "installed_dependency_denominator",
        "listed_member_denominator",
        "output_denominator",
        "role_denominator",
        "role_pair_denominator",
        "source_clause_denominator",
        "upstream_receipt_denominator",
    }
    assert len(receipt["members"]) == 11
    assert all(token not in encoded.lower() for token in ("https://", "signature", "source_content", '"prose"'))


def test_runtime_has_no_public_or_reverse_dependency(tmp_path: Path) -> None:
    runtime = (ROOT / "src/clause_offline_proof.py").read_text(encoding="utf-8")
    assert "evidence_outputs" not in runtime
    assert "ProductManifest" not in runtime
    assert "docs/" not in runtime
    assert not any(
        "clause_offline_proof" in path.read_text(encoding="utf-8", errors="ignore")
        for path in ROOT.glob("src/*.py")
        if path.name != "clause_offline_proof.py"
    )
    assert _verify(_build(tmp_path))["boundary"]["product_manifest_created"] is False


def _run_vector(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[bytes, str]:
    query_id = NO_PATH_QUERY if mutation == "none_no_path" else PATH_QUERY
    source, role_proof = _inputs(tmp_path, query_id)
    archive = proof_archive.build_clause_offline_proof(source, role_proof)
    digest = _sha(archive)
    if mutation in {"none_path", "none_no_path"}:
        return archive, digest
    if mutation == "wrong_external_digest":
        return archive, "0" * 64
    if mutation == "invalid_external_digest":
        return archive, "not-a-sha256"
    if mutation == "invalid_zip":
        invalid = b"not a zip archive"
        return invalid, _sha(invalid)
    if mutation == "oversized_archive":
        oversized = b"x" * (16_777_216 + 1)
        return oversized, _sha(oversized)
    if mutation == "caller_after_capture":
        source["post_capture"] = True
        role_proof["post_capture"] = True
        return archive, digest
    if mutation == "network_disabled":
        def blocked(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("network access attempted")

        monkeypatch.setattr(socket, "socket", blocked)
        monkeypatch.setattr(socket, "create_connection", blocked)
        return archive, digest
    if mutation == "contract_digest_drift":
        monkeypatch.setattr(proof_archive, "_REGISTERED_CONTRACT_SHA256", "0" * 64)
        return archive, digest
    if mutation == "malformed_contract":
        isolated = _copy_registered_root(tmp_path)
        contract_path = isolated / "governance/clause_offline_proof_contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["status"] = "invalid_status"
        raw = (json.dumps(contract, indent=2, ensure_ascii=False) + "\n").encode()
        contract_path.write_bytes(raw)
        monkeypatch.setattr(proof_archive, "ROOT", isolated)
        monkeypatch.setattr(proof_archive, "_REGISTERED_CONTRACT_SHA256", _sha(raw))
        return archive, digest
    if mutation == "dependency_file_drift":
        isolated = _copy_registered_root(tmp_path)
        dependency = isolated / "governance/analytical_clause_contract.json"
        dependency.write_bytes(dependency.read_bytes() + b"\n")
        monkeypatch.setattr(proof_archive, "ROOT", isolated)
        return archive, digest
    if mutation == "runtime_unreadable":
        original_read_bytes = Path.read_bytes
        runtime_path = Path(proof_archive.__file__).resolve()

        def guarded_read_bytes(path: Path) -> bytes:
            if path.resolve() == runtime_path:
                raise OSError("runtime unavailable")
            return original_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
        return archive, digest
    if mutation in {
        "absolute_path",
        "parent_path",
        "backslash_path",
        "duplicate_path",
        "symlink_entry",
        "deflate_entry",
        "timestamp",
        "empty_entry",
        "bundled_code",
        "missing_member",
    }:
        mutated = _structural_mutation(archive, mutation)
    else:
        mutated = _semantic_mutation(archive, mutation)
    return mutated, _sha(mutated)


VECTORS = json.loads(
    (ROOT / "governance/clause_offline_proof_adversarial_vectors.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda row: row["case_id"])
def test_normative_adversarial_vectors_execute(
    case: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive, expected_digest = _run_vector(case["mutation"], tmp_path, monkeypatch)
    if case["expected"] == "valid":
        assert proof_archive.verify_clause_offline_proof(
            archive, expected_sha256=expected_digest
        )["status"] == "valid_internal_clause_recompilation"
    else:
        with pytest.raises(proof_archive.ClauseOfflineProofError) as caught:
            proof_archive.verify_clause_offline_proof(
                archive, expected_sha256=expected_digest
            )
        assert caught.value.code == case["expected"]


def test_normative_vector_registry_is_closed() -> None:
    cases = VECTORS["cases"]
    contract = json.loads(
        (ROOT / "governance/clause_offline_proof_contract.json").read_text(
            encoding="utf-8"
        )
    )
    assert VECTORS["status"] == "normative_executable"
    assert VECTORS["complete_case_denominator"] == 33 == len(cases)
    assert len({row["case_id"] for row in cases}) == 33
    assert len({row["mutation"] for row in cases}) == 33
    assert {row["expected"] for row in cases if row["expected"] != "valid"} == set(
        contract["refusal_codes"]
    )


def test_invalid_external_digest_format_fails_closed(tmp_path: Path) -> None:
    archive = _build(tmp_path)
    with pytest.raises(proof_archive.ClauseOfflineProofError) as caught:
        proof_archive.verify_clause_offline_proof(archive, expected_sha256="bad")
    assert caught.value.code == "proof_external_digest_invalid"
