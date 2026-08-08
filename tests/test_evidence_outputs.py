"""Adversarial tests for the deterministic four-output evidence compiler."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from src import canonical_objects as canonical
from src import evidence_outputs, evidence_outputs_fixture, oges_fixture

ROOT = Path(__file__).resolve().parents[1]
EVENT_ID = "evt:oges.fixture.policy.001"
TARGET_ID = "ent:commodity.synthetic_crude"


@pytest.fixture()
def output_fixture(tmp_path: Path) -> oges_fixture.Fixture:
    return evidence_outputs_fixture.build_fixture(tmp_path / "bundle")


def _paths(fixture: oges_fixture.Fixture) -> dict[str, Path]:
    governance = fixture.root / "governance"
    return {
        "schema_registry_path": governance / "canonical_schema_registry.json",
        "rights_registry_path": governance / "source_rights_registry.json",
        "rights_signers_path": governance / "rights_signers.json",
        "method_registry_path": governance / "canonical_method_registry.json",
        "release_signers_path": governance / "release_signers.json",
        "output_registry_path": governance / "evidence_output_registry.json",
    }


def _compile(
    fixture: oges_fixture.Fixture,
    *,
    target_id: str = TARGET_ID,
) -> dict[str, Any]:
    paths = _paths(fixture)
    return evidence_outputs.compile_evidence_outputs(
        fixture.manifest,
        EVENT_ID,
        target_id,
        root=fixture.root,
        schema_registry_path=paths["schema_registry_path"],
        rights_registry_path=paths["rights_registry_path"],
        rights_signers_path=paths["rights_signers_path"],
        method_registry_path=paths["method_registry_path"],
        release_signers_path=paths["release_signers_path"],
        output_registry_path=paths["output_registry_path"],
    )


def _archive(fixture: oges_fixture.Fixture) -> bytes:
    paths = _paths(fixture)
    return evidence_outputs.build_offline_audit_bundle(
        fixture.manifest,
        EVENT_ID,
        TARGET_ID,
        root=fixture.root,
        schema_registry_path=paths["schema_registry_path"],
        rights_registry_path=paths["rights_registry_path"],
        rights_signers_path=paths["rights_signers_path"],
        method_registry_path=paths["method_registry_path"],
        release_signers_path=paths["release_signers_path"],
        output_registry_path=paths["output_registry_path"],
    )


def _validate(
    fixture: oges_fixture.Fixture, document: dict[str, Any]
) -> None:
    paths = _paths(fixture)
    evidence_outputs.validate_evidence_outputs(
        document,
        fixture.manifest,
        EVENT_ID,
        TARGET_ID,
        root=fixture.root,
        schema_registry_path=paths["schema_registry_path"],
        rights_registry_path=paths["rights_registry_path"],
        rights_signers_path=paths["rights_signers_path"],
        method_registry_path=paths["method_registry_path"],
        release_signers_path=paths["release_signers_path"],
        output_registry_path=paths["output_registry_path"],
    )


def _entries(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive), "r") as opened:
        return {name: opened.read(name) for name in opened.namelist()}


def _all_strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_strings(nested)


def test_one_release_produces_exactly_four_deterministic_bounded_outputs(
    output_fixture: oges_fixture.Fixture,
) -> None:
    first = _compile(output_fixture)
    second = _compile(output_fixture)

    assert first == second
    assert canonical.canonical_record_sha256(first) == first["record_sha256"]
    assert first["result"] == {
        "status": "compiled",
        "output_count": 4,
        "model_authored_facts": False,
        "forecast_performed": False,
        "probability_assigned": False,
        "causal_attribution_performed": False,
        "recommendation_generated": False,
        "scalar_score_computed": False,
    }
    assert set(first["outputs"]) == {
        "research_package",
        "board_brief",
        "newsroom_claim_card",
        "offline_audit_bundle",
    }
    release_hash = json.loads(output_fixture.manifest.read_text())["record_sha256"]
    assert first["release"]["record_sha256"] == release_hash
    assert first["source_index"]["structural_paths"] == 1
    _validate(output_fixture, first)


def test_every_visible_sentence_is_template_bound_to_objects_and_evidence(
    output_fixture: oges_fixture.Fixture,
) -> None:
    document = _compile(output_fixture)
    board = document["outputs"]["board_brief"]
    claims = document["outputs"]["newsroom_claim_card"]["claims"]
    evidence_ids = {row["evidence_id"] for row in document["source_index"]["evidence"]}
    object_ids = {row["object_id"] for row in document["source_index"]["objects"]}

    assert all(section["object_ids"] for section in board["sections"])
    assert all(set(section["object_ids"]) <= object_ids for section in board["sections"])
    assert all(set(section["evidence_ids"]) <= evidence_ids for section in board["sections"])
    assert all(set(claim["object_ids"]) <= object_ids for claim in claims)
    assert all(set(claim["evidence_ids"]) <= evidence_ids for claim in claims)
    assert all(claim["status"] == "compiled_from_registered_fields" for claim in claims)
    assert board["review_status"] == "draft_requires_human_review"
    text = "\n".join(_all_strings(document)).lower()
    for forbidden in (
        "investment advice",
        "recommended action is",
        "probability of disruption",
        "caused economic loss",
    ):
        assert forbidden not in text


def test_no_path_is_visible_and_never_reframed_as_no_exposure(
    output_fixture: oges_fixture.Fixture,
) -> None:
    document = _compile(output_fixture, target_id="ent:country.synthetic_india")
    assert document["result"]["status"] == "compiled_no_structural_path"
    assert document["source_index"]["structural_paths"] == 0
    linkage = document["outputs"]["board_brief"]["sections"][1]["text"]
    assert "returned no structural path" in linkage
    assert "not evidence that exposure is absent" in linkage


def test_nonpublic_evidence_refuses_before_any_public_output(
    output_fixture: oges_fixture.Fixture,
) -> None:
    def restrict(document: dict[str, Any]) -> None:
        document["privacy_class"] = "restricted"
        document["content_availability"] = "restricted"
        document["rights_use"] = "cite_metadata"
        document["public_url"] = None

    oges_fixture._rewrite_object(
        output_fixture, "evd:oges.fixture.official.001", restrict
    )
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        _compile(output_fixture)
    assert exc.value.code == "output_evidence_privacy_not_public"


def test_resealed_output_prose_or_number_mutation_fails_semantic_recompile(
    output_fixture: oges_fixture.Fixture,
) -> None:
    document = copy.deepcopy(_compile(output_fixture))
    document["outputs"]["board_brief"]["sections"][0]["text"] = "Plausible but invented."
    document = cast(dict[str, Any], canonical.seal_record(document))
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        _validate(output_fixture, document)
    assert exc.value.code == "output_semantic_mismatch"


@pytest.mark.parametrize(
    "relative,code",
    [
        ("src/evidence_outputs.py", "output_implementation_digest_mismatch"),
        ("schemas/evidence-output-set.schema.json", "output_schema_digest_mismatch"),
        (
            "governance/exposure_projection_registry.json",
            "output_projection_registry_digest_mismatch",
        ),
    ],
)
def test_registered_contract_bytes_fail_closed_on_drift(
    output_fixture: oges_fixture.Fixture,
    relative: str,
    code: str,
) -> None:
    path = output_fixture.root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        _compile(output_fixture)
    assert exc.value.code == code


def test_offline_bundle_is_deterministic_authenticated_safe_and_revalidates_release(
    output_fixture: oges_fixture.Fixture,
) -> None:
    first = _archive(output_fixture)
    second = _archive(output_fixture)
    assert first == second
    digest = hashlib.sha256(first).hexdigest()
    summary = evidence_outputs.verify_offline_audit_bundle(
        first, expected_sha256=digest
    )
    assert summary["status"] == "valid"
    assert summary["canonical_release_status"] == "valid"
    assert summary["file_count"] == 40

    with zipfile.ZipFile(io.BytesIO(first), "r") as opened:
        infos = opened.infolist()
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos)
        assert all(".." not in Path(info.filename).parts for info in infos)
        assert all(not info.is_dir() for info in infos)


def test_archive_artifacts_and_internal_manifest_match_every_byte(
    output_fixture: oges_fixture.Fixture,
) -> None:
    document = _compile(output_fixture)
    archive = _archive(output_fixture)
    entries = _entries(archive)
    manifest = json.loads(entries["bundle-manifest.json"])
    assert set(entries) == {row["path"] for row in manifest["files"]} | {
        "bundle-manifest.json"
    }
    for row in manifest["files"]:
        raw = entries[row["path"]]
        assert len(raw) == row["bytes"]
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    for output_key in ("research_package", "board_brief", "newsroom_claim_card"):
        artifact = document["outputs"][output_key]["artifact"]
        raw = entries[f"outputs/{artifact['filename']}"]
        assert len(raw) == artifact["bytes"]
        assert hashlib.sha256(raw).hexdigest() == artifact["sha256"]
    audit = document["outputs"]["offline_audit_bundle"]
    assert hashlib.sha256(archive).hexdigest() == audit["artifact"]["sha256"]
    assert len(archive) == audit["artifact"]["bytes"]
    assert hashlib.sha256(entries["bundle-manifest.json"]).hexdigest() == audit[
        "bundle_manifest_sha256"
    ]


def test_archive_authentication_and_manifest_tamper_both_refuse(
    output_fixture: oges_fixture.Fixture,
) -> None:
    archive = _archive(output_fixture)
    digest = hashlib.sha256(archive).hexdigest()
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        evidence_outputs.verify_offline_audit_bundle(
            archive + b"x", expected_sha256=digest
        )
    assert exc.value.code == "audit_external_digest_mismatch"

    entries = _entries(archive)
    entries["AUDIT.md"] += b"tampered"
    tampered = evidence_outputs._zip_bytes(entries)
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        evidence_outputs.verify_offline_audit_bundle(
            tampered, expected_sha256=hashlib.sha256(tampered).hexdigest()
        )
    assert exc.value.code == "audit_bundle_file_digest_mismatch"


def test_archive_traversal_entry_refuses_before_extraction() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as opened:
        for name, body in (("bundle-manifest.json", b"{}"), ("../escape", b"x")):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            opened.writestr(info, body)
    raw = buffer.getvalue()
    with pytest.raises(evidence_outputs.EvidenceOutputError) as exc:
        evidence_outputs.verify_offline_audit_bundle(
            raw, expected_sha256=hashlib.sha256(raw).hexdigest()
        )
    assert exc.value.code == "audit_archive_path_invalid"


def test_public_demo_and_archive_rebuild_byte_identically() -> None:
    payload, archive = evidence_outputs_fixture.build_demo_artifacts()
    assert payload == json.loads(
        evidence_outputs_fixture.PUBLIC_OUTPUT.read_text(encoding="utf-8")
    )
    assert archive == evidence_outputs_fixture.PUBLIC_ARCHIVE.read_bytes()
    assert payload["_meta"]["scope"] == "synthetic_test_vector_only"
    assert payload["_meta"]["production_release"] is False
    assert payload["output_set"]["result"]["output_count"] == 4
    assert payload["download"]["sha256"] == hashlib.sha256(archive).hexdigest()


def test_public_demo_contains_no_underlying_source_content() -> None:
    payload = evidence_outputs_fixture.build_demo()
    text = "\n".join(_all_strings(payload))
    assert "OGES synthetic official bytes" not in text
    assert "source content" not in json.dumps(payload["output_set"]["source_index"])
    assert payload["_meta"]["model_generated_facts_numbers_dates_citations_or_confidence"] is False


def test_schema_and_registry_are_publicly_mirrored_and_hash_pinned() -> None:
    registry = json.loads(
        (ROOT / "governance" / "evidence_output_registry.json").read_text()
    )["engine"]
    implementation = ROOT / registry["implementation_path"]
    schema = ROOT / registry["output_schema_path"]
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == registry[
        "implementation_sha256"
    ]
    assert hashlib.sha256(schema.read_bytes()).hexdigest() == registry[
        "output_schema_sha256"
    ]
    assert (ROOT / "docs" / "schemas" / "evidence-output-set.schema.json").read_bytes() == schema.read_bytes()
