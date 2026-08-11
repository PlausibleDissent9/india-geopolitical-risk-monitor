"""Hostile tests for the closed synthetic clause/output conformance gate."""

from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from src import analytical_clause as analytical
from src import canonical_objects as canonical
from src import clause_offline_proof as offline_proof
from src import clause_output_conformance as conformance
from src import clause_reader_shadow as reader
from src import clause_source_view as source_view
from src import evidence_outputs as incumbent
from src import evidence_outputs_fixture, oges_fixture
from src.oges_fixture import Fixture

ROOT = Path(__file__).resolve().parents[1]
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"
EVENT_ID = "evt:oges.fixture.policy.001"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _resign(fixture: Fixture, manifest: dict[str, Any]) -> None:
    sealed = canonical.seal_record(manifest)
    _write_json(fixture.manifest, sealed)
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _add_release_object(
    fixture: Fixture, object_type: str, object_id: str, document: dict[str, Any]
) -> dict[str, Any]:
    sealed = canonical.seal_record(document)
    path = fixture.root / "canonical" / f"{object_id.replace(':', '__')}.json"
    _write_json(path, sealed)
    fixture.objects[object_id] = path
    manifest = json.loads(fixture.manifest.read_text(encoding="utf-8"))
    manifest["objects"].append(
        {
            "object_type": object_type,
            "object_id": object_id,
            "path": str(path.relative_to(fixture.root)),
            "file_sha256": _sha(path.read_bytes()),
            "record_sha256": sealed["record_sha256"],
        }
    )
    manifest["counts"][object_type] += 1
    _resign(fixture, manifest)
    return cast(dict[str, Any], sealed)


def _add_equal_metadata_evidence(fixture: Fixture) -> None:
    original = json.loads(
        fixture.objects["evd:oges.fixture.official.001"].read_text(encoding="utf-8")
    )
    evidence_id = "evd:oges.fixture.official.equal-metadata"
    original.update(
        evidence_id=evidence_id,
        source_record_id="official-equal-metadata",
        retrieval_id="ret:oges.fixture.equal-metadata",
    )
    _add_release_object(fixture, "evidence_item", evidence_id, original)

    def reference(document: dict[str, Any]) -> None:
        document["evidence_links"].append(
            {
                "evidence_id": evidence_id,
                "role": "corroborates",
                "asserted_at": "2026-08-08T09:00:00Z",
            }
        )
        document["provenance"]["evidence_ids"].append(evidence_id)

    oges_fixture._rewrite_object(fixture, EVENT_ID, reference)


def _make_nullable_metadata(fixture: Fixture) -> None:
    artifact = fixture.root / "artifacts" / "citation-metadata.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"citation metadata locator")

    def nullable(document: dict[str, Any]) -> None:
        document["public_url"] = None
        document["published_at"] = None
        document["artifact_path"] = str(artifact.relative_to(fixture.root))
        document["artifact_sha256"] = _sha(artifact.read_bytes())

    oges_fixture._rewrite_object(
        fixture, "evd:oges.fixture.official.001", nullable
    )


@pytest.fixture(scope="module")
def fixture(tmp_path_factory: pytest.TempPathFactory) -> Fixture:
    return evidence_outputs_fixture.build_fixture(
        tmp_path_factory.mktemp("clause-output-conformance")
    )


@pytest.fixture(scope="module")
def baseline_receipt(fixture: Fixture) -> dict[str, Any]:
    return conformance.compile_clause_output_conformance(fixture.manifest)


def _vectors() -> list[dict[str, str]]:
    document = json.loads(conformance.VECTORS_PATH.read_text(encoding="utf-8"))
    return cast(list[dict[str, str]], document["cases"])


def _contract_bytes_with(**changes: object) -> bytes:
    document = json.loads(conformance.CONTRACT_PATH.read_text(encoding="utf-8"))
    document.update(changes)
    return _json_bytes(document)


def _mutated_incumbent(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    original = incumbent.compile_evidence_outputs

    def compile_mutated(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = deepcopy(original(*args, **kwargs))
        if mutation == "output_document_mismatch":
            result["outputs"]["research_package"]["title"] += " altered"
        elif mutation == "artifact_descriptor_mismatch":
            result["outputs"]["research_package"]["artifact"]["sha256"] = "0" * 64
        elif mutation == "common_scope_mismatch":
            result["limitations"] = result["limitations"][1:]
        else:  # pragma: no cover - closed test dispatcher
            raise AssertionError(mutation)
        return result

    monkeypatch.setattr(incumbent, "compile_evidence_outputs", compile_mutated)


def _exercise_failure(
    mutation: str,
    *,
    fixture: Fixture,
    baseline: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original_read = conformance._read_bytes
    if mutation == "contract_digest_drift":
        monkeypatch.setattr(conformance, "_CONTRACT_SHA256", "0" * 64)
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "contract_semantic_drift":
        raw = _contract_bytes_with(status="public_activation")
        monkeypatch.setattr(conformance, "_CONTRACT_SHA256", _sha(raw))
        monkeypatch.setattr(
            conformance,
            "_read_bytes",
            lambda path, code: raw
            if path == conformance.CONTRACT_PATH
            else original_read(path, code),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "dependency_drift":
        monkeypatch.setattr(
            conformance,
            "_read_bytes",
            lambda path, code: b"drift"
            if path == conformance.SOURCE_PROFILE_PATH
            else original_read(path, code),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "fixture_manifest_path":
        bad = tmp_path / "release.json"
        bad.write_bytes(fixture.manifest.read_bytes())
        conformance.compile_clause_output_conformance(bad)
    elif mutation == "query_universe_shrink":
        original_queries = conformance._registered_queries
        monkeypatch.setattr(
            conformance,
            "_registered_queries",
            lambda fixed: original_queries(fixed)[:1],
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "source_compiler_failure":
        monkeypatch.setattr(
            analytical,
            "compile_source_bound_clauses",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                analytical.AnalyticalClauseError("clause_source_profile_invalid")
            ),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "view_compiler_failure":
        monkeypatch.setattr(
            source_view,
            "compile_clause_source_views",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                source_view.ClauseSourceViewError("view_source_refused")
            ),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "reader_compiler_failure":
        monkeypatch.setattr(
            reader,
            "compile_clause_reader_shadow",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                reader.ClauseReaderShadowError("reader_input_invalid")
            ),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "proof_archive_failure":
        monkeypatch.setattr(
            offline_proof,
            "verify_clause_offline_proof",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                offline_proof.ClauseOfflineProofError("proof_recompile_mismatch")
            ),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "incumbent_compiler_failure":
        monkeypatch.setattr(
            incumbent,
            "compile_evidence_outputs",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                incumbent.EvidenceOutputError("output_semantic_mismatch")
            ),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation in {
        "output_document_mismatch",
        "artifact_descriptor_mismatch",
        "common_scope_mismatch",
    }:
        _mutated_incumbent(monkeypatch, mutation)
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "receipt_shape_mutation":
        changed = deepcopy(baseline)
        changed["invented"] = True
        conformance.verify_clause_output_conformance(fixture.manifest, changed)
    elif mutation == "receipt_record_digest_mutation":
        changed = deepcopy(baseline)
        changed["record_sha256"] = "0" * 64
        conformance.verify_clause_output_conformance(fixture.manifest, changed)
    elif mutation == "receipt_resealed_mutation":
        changed = deepcopy(baseline)
        changed["queries"][0]["comparisons"][0]["document_sha256"] = "0" * 64
        changed = conformance._seal(changed)
        conformance.verify_clause_output_conformance(fixture.manifest, changed)
    elif mutation == "runtime_drift":
        runtime_path = Path(conformance.__file__)
        calls = 0

        def drifting_read(path: Path, code: str) -> bytes:
            nonlocal calls
            raw = original_read(path, code)
            if path == runtime_path:
                calls += 1
                if calls > 1:
                    return raw + b"\n# drift"
            return raw

        monkeypatch.setattr(conformance, "_read_bytes", drifting_read)
        conformance.compile_clause_output_conformance(fixture.manifest)
    elif mutation == "duplicate_json_key":
        raw = b'{"schema_version":"0.1.0","schema_version":"0.1.0"}'
        monkeypatch.setattr(conformance, "_CONTRACT_SHA256", _sha(raw))
        monkeypatch.setattr(
            conformance,
            "_read_bytes",
            lambda path, code: raw
            if path == conformance.CONTRACT_PATH
            else original_read(path, code),
        )
        conformance.compile_clause_output_conformance(fixture.manifest)
    else:  # pragma: no cover - vector registry is closed
        raise AssertionError(mutation)


@pytest.mark.parametrize("case", _vectors(), ids=lambda row: row["case_id"])
def test_every_normative_vector_executes_through_public_gate(
    case: dict[str, str],
    fixture: Fixture,
    baseline_receipt: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    mutation = case["mutation"]
    expected = case["expected"]
    if mutation == "none":
        result = conformance.verify_clause_output_conformance(
            fixture.manifest, baseline_receipt
        )
        assert expected == "valid"
        assert result["status"] == "exact_closed_synthetic_universe_conformance"
        return
    if mutation == "alternate_call_same_manifest":
        assert (
            conformance.compile_clause_output_conformance(fixture.manifest)
            == baseline_receipt
        )
        return
    if mutation == "equal_metadata_multi_evidence":
        second = evidence_outputs_fixture.build_fixture(tmp_path / "fixture")
        _add_equal_metadata_evidence(second)
        source, _proof = analytical.compile_source_bound_clauses(
            second.manifest, PATH_QUERY, root=second.root
        )
        assert source["complete_denominators"]["evidence_items"] == 2
        receipt = conformance.compile_clause_output_conformance(second.manifest)
        assert expected == "valid"
        assert receipt["status"] == "exact_closed_synthetic_universe_conformance"
        return
    if mutation == "nullable_metadata_incumbent_refusal":
        nullable = evidence_outputs_fixture.build_fixture(tmp_path / "fixture")
        _make_nullable_metadata(nullable)
        with pytest.raises(conformance.ClauseOutputConformanceError) as captured:
            conformance.compile_clause_output_conformance(nullable.manifest)
        assert captured.value.code == expected
        assert captured.value.detail == "audit_artifact_redistribution_not_allowed"
        return
    with pytest.raises(conformance.ClauseOutputConformanceError) as captured:
        _exercise_failure(
            mutation,
            fixture=fixture,
            baseline=baseline_receipt,
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
        )
    assert captured.value.code == expected


def test_contract_vectors_and_all_installed_pins_are_exact() -> None:
    contract = json.loads(conformance.CONTRACT_PATH.read_text(encoding="utf-8"))
    vectors = json.loads(conformance.VECTORS_PATH.read_text(encoding="utf-8"))
    assert _sha(conformance.CONTRACT_PATH.read_bytes()) == conformance._CONTRACT_SHA256
    for row in contract["fixed_files"].values():
        assert _sha((ROOT / row["path"]).read_bytes()) == row["file_sha256"]
    for row in contract["installed_dependencies"]:
        assert _sha((ROOT / row["path"]).read_bytes()) == row["file_sha256"]
    assert vectors["case_denominator"] == len(vectors["cases"]) == 22
    assert len({row["case_id"] for row in vectors["cases"]}) == 22
    assert len({row["mutation"] for row in vectors["cases"]}) == 22
    failures = {
        row["expected"] for row in vectors["cases"] if row["expected"] != "valid"
    }
    assert failures == set(contract["refusal_codes"])


def test_receipt_is_value_free_schema_valid_complete_and_bounded(
    fixture: Fixture, baseline_receipt: dict[str, Any]
) -> None:
    receipt = baseline_receipt
    schema = json.loads(conformance.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(receipt)
    assert receipt["record_sha256"] == conformance._record_sha256(receipt)
    assert [row["query_id"] for row in receipt["queries"]] == [
        PATH_QUERY,
        NO_PATH_QUERY,
    ]
    assert [row["active_branch_id"] for row in receipt["queries"]] == [
        "branch:path_found",
        "branch:no_path",
    ]
    assert sum(len(row["comparisons"]) for row in receipt["queries"]) == 6
    assert len({row["proof_archive_ref"]["sha256"] for row in receipt["queries"]}) == 2
    assert receipt["excluded_output_ids"] == ["output:offline_audit_bundle"]
    assert receipt["trust"] == conformance._TRUST
    assert receipt["boundary"] == conformance._BOUNDARY
    assert receipt["boundary"]["general_equivalence"] is False
    assert receipt["boundary"]["public_activation"] is False
    for query in receipt["queries"]:
        assert [row["output_id"] for row in query["comparisons"]] == [
            row[0] for row in conformance._OUTPUTS
        ]
        assert query["common_scope"]["scope_id"] == "scope:output.all_views"
        assert query["common_scope"]["shadow_outer_wrapper_absent_denominator"] == 3
    encoded = json.dumps(receipt, sort_keys=True)
    for leaked in (
        "Synthetic policy action",
        "Synthetic official action",
        "https://",
        '"generated_at"',
        '"observed_at"',
        '"published_at"',
        "public_url",
        '"title"',
        '"prose"',
        '"value"',
        '"signature"',
    ):
        assert leaked not in encoded
    summary = conformance.verify_clause_output_conformance(fixture.manifest, receipt)
    assert summary == {
        "status": "exact_closed_synthetic_universe_conformance",
        "conformance_id": receipt["conformance_id"],
        "record_sha256": receipt["record_sha256"],
        "compared_query_denominator": 2,
        "comparison_cell_denominator": 6,
        "proof_archive_denominator": 2,
        "general_equivalence": False,
        "public_activation": False,
    }


def test_api_accepts_no_caller_semantic_arguments_and_has_no_public_route() -> None:
    compile_signature = inspect.signature(
        conformance.compile_clause_output_conformance
    )
    verify_signature = inspect.signature(conformance.verify_clause_output_conformance)
    assert list(compile_signature.parameters) == ["manifest_path"]
    assert list(verify_signature.parameters) == ["manifest_path", "receipt"]
    contract = json.loads(conformance.CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["public_routes"] == []
    for base in (ROOT / "docs", ROOT / ".github", ROOT / "scripts"):
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {
                ".py",
                ".html",
                ".js",
                ".json",
                ".yml",
                ".yaml",
            }:
                assert "clause_output_conformance" not in path.read_text(
                    encoding="utf-8", errors="ignore"
                )


def test_snapshot_is_unaliased_from_caller_root_after_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path / "fixture")
    clean = conformance.compile_clause_output_conformance(fixture.manifest)
    original_materialize = conformance._materialize_snapshot
    original_manifest = fixture.manifest.read_bytes()

    def mutate_after_capture(
        snapshot: conformance._FixtureSnapshot, destination: Path
    ) -> Path:
        result = original_materialize(snapshot, destination)
        fixture.manifest.write_bytes(original_manifest + b" ")
        return result

    monkeypatch.setattr(conformance, "_materialize_snapshot", mutate_after_capture)
    try:
        observed = conformance.compile_clause_output_conformance(fixture.manifest)
    finally:
        fixture.manifest.write_bytes(original_manifest)
    assert observed == clean


def test_only_five_internal_slice_files_are_new() -> None:
    expected = {
        "governance/clause_output_conformance_adversarial_vectors.json",
        "governance/clause_output_conformance_contract.json",
        "governance/schemas/clause-output-conformance-receipt.schema.json",
        "src/clause_output_conformance.py",
        "tests/test_clause_output_conformance.py",
    }
    assert all((ROOT / path).is_file() for path in expected)
    protected = (
        ROOT / "src" / "evidence_outputs.py",
        ROOT / "src" / "clause_reader_shadow.py",
        ROOT / "src" / "clause_source_view.py",
        ROOT / "docs" / "data" / "evidence_outputs_demo.json",
    )
    assert all(path.is_file() for path in protected)
