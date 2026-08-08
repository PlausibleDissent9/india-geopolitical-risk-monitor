from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import port_commodity_marginals as marginal

ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _registry() -> dict:
    return json.loads(
        (ROOT / "governance" / "port_commodity_marginals.json").read_text()
    )


def _fixture_registry(artifact: Path) -> dict:
    registry = _registry()
    registry["source"]["registered_vintages"] = [
        {
            "url": "https://shipmin.gov.in/sites/default/files/test-major-ports.pdf",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "valid_period": "2026-02",
            "estimate_status": "advance_estimate",
            "published_on": "2026-03-20",
            "table_pages": [6, 7],
            "registered_on": "2026-08-09",
        }
    ]
    return registry


def _write_fixture_registry(directory: Path, artifact: Path) -> Path:
    implementation = directory / "src" / "port_commodity_marginals.py"
    implementation.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src" / "port_commodity_marginals.py", implementation)
    path = directory / "governance" / "port_commodity_marginals.json"
    _write(path, _fixture_registry(artifact))
    return path


def _snapshot(artifact: Path) -> dict:
    registry = _registry()
    ports = [
        {"port_id": member, "label": registry["port_frame"]["member_labels"][member], "cargo_tonnes": 100}
        for member in registry["port_frame"]["member_ids"]
    ]
    commodities = [
        {
            "commodity_id": member,
            "label": registry["commodity_frame"]["member_labels"][member],
            "cargo_tonnes": 60,
        }
        for member in registry["commodity_frame"]["member_ids"]
    ]
    return {
        "schema_version": "1.0.0",
        "snapshot_id": "major_ports_2026_02_test",
        "source_id": "india_major_ports_pdmp2",
        "rights_decision_id": "test-major-ports-decision",
        "source_artifact": {
            "url": "https://shipmin.gov.in/sites/default/files/test-major-ports.pdf",
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "published_on": "2026-03-20",
            "retrieved_at": "2026-08-09T00:00:00Z",
            "table_pages": [6, 7],
        },
        "valid_period": "2026-02",
        "knowledge_time": "2026-08-09T00:10:00Z",
        "estimate_status": "advance_estimate",
        "unit": "tonnes",
        "total_cargo_tonnes": 1200,
        "port_frame": {
            "frame_id": registry["port_frame"]["frame_id"],
            "frame_count": 12,
            "covered_count": 12,
            "members": ports,
        },
        "commodity_frame": {
            "frame_id": registry["commodity_frame"]["frame_id"],
            "frame_count": 20,
            "covered_count": 20,
            "members": commodities,
        },
        "separate_metrics": [
            {"metric_id": "container_teu", "unit": "teu", "value": 321}
        ],
        "joint_port_commodity": {"status": "not_observed", "cells": []},
        "extraction": {
            "method": "dual_method_reconciliation",
            "checks": [
                {
                    "check_id": "extractor.pdf_text",
                    "method": "pdf_text_extraction",
                    "artifact_sha256": "a" * 64,
                },
                {
                    "check_id": "reviewer.visual_table",
                    "method": "visual_table_review",
                    "artifact_sha256": "b" * 64,
                },
            ],
            "verified_at": "2026-08-09T00:05:00Z",
        },
    }


def _bind_extraction_evidence(
    snapshot: dict,
    artifact: Path,
    directory: Path,
    registry: dict | None = None,
) -> list[Path]:
    validated = marginal.validate_snapshot(
        snapshot, registry if registry is not None else _fixture_registry(artifact)
    )
    paths: list[Path] = []
    for index, check in enumerate(snapshot["extraction"]["checks"]):
        path = directory / f"extraction-check-{index}.json"
        _write(
            path,
            {
                "schema_version": "1.0.0",
                "check_id": check["check_id"],
                "method": check["method"],
                "source_artifact_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                "observation_sha256": validated["observation_sha256"],
                "result": "exact_match",
            },
        )
        check["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        paths.append(path)
    return paths


def _approved_tree(tmp_path: Path) -> tuple[Path, Path, Path, Path, list[Path]]:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "governance").mkdir()
    shutil.copy2(ROOT / "src" / "port_commodity_marginals.py", root / "src")
    artifact = root / "source.pdf"
    artifact.write_bytes(b"synthetic source bytes")
    registry = _fixture_registry(artifact)
    _write(root / "governance" / "port_commodity_marginals.json", registry)
    snapshot_path = root / "snapshot.json"
    snapshot = _snapshot(artifact)
    evidence_paths = _bind_extraction_evidence(snapshot, artifact, root, registry)
    _write(snapshot_path, snapshot)

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers_path = root / "governance" / "rights_signers.json"
    _write(
        signers_path,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "test_major_ports_signer",
                    "name": "Test major-ports signer",
                    "role": "test rights reviewer",
                    "public_key_ed25519_base64": base64.b64encode(public).decode(),
                    "effective": "2026-08-09",
                    "revoked_on": None,
                }
            ],
        },
    )
    source = {
        "source_id": "india_major_ports_pdmp2",
        "name": "Test monthly major-port report",
        "provider": "Test Ministry",
        "role": "official_port_and_commodity_marginals",
        "authority_class": "official_primary",
        "independence_group": "test_ministry_ports",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "test-major-ports-decision",
        "decision_owner": "Test reviewer",
        "signer_id": "test_major_ports_signer",
        "decision_artifact_path": "governance/rights_decisions/major_ports.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/major_ports.sig",
        "reviewed_on": "2026-08-09",
        "review_due": "2027-08-09",
        "access_url": "https://shipmin.gov.in/test",
        "terms_url": "https://shipmin.gov.in/en/footer/copyrightpolicy",
        "access_basis": "test_approved_reproduction",
        "geographic_coverage": "Test 12-port frame",
        "historical_coverage": "One test month",
        "retrieval_target": "Test marginal rows",
        "outage_fallback": "Fail closed",
        "cost_owner": "Test owner",
        "reproducibility_tier": "test_exact_bytes",
        "max_current_age_days": 400,
        "permitted_uses": ["cite_metadata", "publish_derived_value", "publish_extract"],
        "notes": "Synthetic test-only authorization.",
    }
    decision = {
        key: source[key]
        for key in (
            "source_id",
            "name",
            "provider",
            "role",
            "authority_class",
            "independence_group",
            "decision_id",
            "decision_owner",
            "signer_id",
            "reviewed_on",
            "review_due",
            "access_url",
            "terms_url",
            "access_basis",
            "lineage_policy",
            "max_current_age_days",
            "permitted_uses",
        )
    }
    decision.update(
        schema_version="1.0.0",
        statement="Synthetic fixture permits the three registered uses.",
    )
    decision_path = root / source["decision_artifact_path"]
    _write(decision_path, decision)
    source["decision_artifact_sha256"] = hashlib.sha256(
        decision_path.read_bytes()
    ).hexdigest()
    (root / source["decision_signature_path"]).write_bytes(
        private.sign(decision_path.read_bytes())
    )
    rights_path = root / "governance" / "source_rights_registry.json"
    _write(
        rights_path,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    return root, snapshot_path, artifact, rights_path, evidence_paths


def _compile(tmp_path: Path) -> dict:
    root, snapshot, artifact, rights, evidence = _approved_tree(tmp_path)
    return marginal.compile_snapshot(
        snapshot,
        artifact,
        evidence,
        root=root,
        registry_path=root / "governance" / "port_commodity_marginals.json",
        rights_path=rights,
        signers_path=root / "governance" / "rights_signers.json",
    )


def test_registry_pins_exact_candidate_and_forbids_joint_inference() -> None:
    registry, _ = marginal._registry()
    assert registry["source"]["registered_vintages"][0]["sha256"] == (
        "7b067dc2a9abe49c1ddeea2f5f6cfc5a24ed8e86c7c81895e22af11337d86e88"
    )
    assert len(registry["port_frame"]["member_ids"]) == 12
    assert len(registry["commodity_frame"]["member_ids"]) == 20
    assert registry["joint_observation"]["inference_allowed"] is False


def test_source_bytes_cannot_be_relabelled_as_another_period(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["valid_period"] = "2026-03"
    with pytest.raises(marginal.PortCommodityError, match="source_vintage_unregistered"):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_source_bytes_cannot_be_relabelled_as_final(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["estimate_status"] = "final"
    with pytest.raises(marginal.PortCommodityError, match="source_vintage_unregistered"):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_source_url_rejects_query_and_encoded_path_escape(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    for url in (
        "https://shipmin.gov.in/sites/default/files/test-major-ports.pdf?revision=2",
        "https://shipmin.gov.in/sites/default/files/%2E%2E/private.pdf",
    ):
        value = _snapshot(artifact)
        value["source_artifact"]["url"] = url
        with pytest.raises(marginal.PortCommodityError, match="source_url_invalid"):
            marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_approved_compilation_emits_only_two_reconciled_marginals(tmp_path: Path) -> None:
    result = _compile(tmp_path)
    assert result["total_cargo_tonnes"] == 1200
    assert sum(row["cargo_tonnes"] for row in result["port_marginals"]) == 1200
    assert sum(row["cargo_tonnes"] for row in result["commodity_marginals"]) == 1200
    assert result["coverage"]["ports_covered"] == 12
    assert result["coverage"]["national_port_coverage"] is None
    assert result["joint_port_commodity"] == {
        "status": "not_observed",
        "cells": [],
        "dependency_edges": [],
        "inference_allowed": False,
        "reason": _registry()["joint_observation"]["reason"],
    }


def test_internal_validation_never_authorizes_publication(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    snapshot = tmp_path / "snapshot.json"
    value = _snapshot(artifact)
    evidence = _bind_extraction_evidence(value, artifact, tmp_path)
    _write(snapshot, value)
    registry_path = _write_fixture_registry(tmp_path, artifact)
    result = marginal.validate_only(
        snapshot, artifact, evidence, registry_path=registry_path
    )
    assert result["marginals_reconcile"] is True
    assert result["joint_cells"] == 0
    assert result["publication_allowed"] is False


def test_current_repository_rights_state_refuses_compilation(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    snapshot = tmp_path / "snapshot.json"
    value = _snapshot(artifact)
    value["rights_decision_id"] = "pending:india_major_ports_pdmp2"
    evidence = _bind_extraction_evidence(value, artifact, tmp_path)
    _write(snapshot, value)
    registry_path = _write_fixture_registry(tmp_path, artifact)
    with pytest.raises(marginal.PortCommodityError, match="rights_not_approved"):
        marginal.compile_snapshot(
            snapshot, artifact, evidence, registry_path=registry_path
        )


def test_nonempty_joint_cell_is_always_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["joint_port_commodity"]["cells"] = [
        {"port_id": "paradip", "commodity_id": "thermal_coal", "cargo_tonnes": 1}
    ]
    with pytest.raises(
        marginal.PortCommodityError, match="joint_observation_or_inference_refused"
    ):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_partial_or_reordered_port_frame_is_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["port_frame"]["members"] = list(reversed(value["port_frame"]["members"]))
    with pytest.raises(
        marginal.PortCommodityError, match="port_frame_order_or_coverage_invalid"
    ):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_marginal_total_mismatch_is_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["commodity_frame"]["members"][0]["cargo_tonnes"] += 1
    with pytest.raises(marginal.PortCommodityError, match="marginal_total_mismatch"):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_one_extraction_check_is_not_double_entry(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _snapshot(artifact)
    value["extraction"]["checks"] = value["extraction"]["checks"][:1]
    with pytest.raises(
        marginal.PortCommodityError, match="extraction_checks_not_independent"
    ):
        marginal.validate_snapshot(value, _fixture_registry(artifact))


def test_source_bytes_and_registered_implementation_are_hash_bound(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    snapshot = tmp_path / "snapshot.json"
    value = _snapshot(artifact)
    evidence = _bind_extraction_evidence(value, artifact, tmp_path)
    _write(snapshot, value)
    registry_path = _write_fixture_registry(tmp_path, artifact)
    artifact.write_bytes(b"changed")
    with pytest.raises(marginal.PortCommodityError, match="source_artifact_digest_mismatch"):
        marginal.validate_only(
            snapshot, artifact, evidence, registry_path=registry_path
        )

    root, snapshot, artifact, rights, evidence = _approved_tree(tmp_path / "drift")
    (root / "src" / "port_commodity_marginals.py").write_text("# drift\n")
    with pytest.raises(marginal.PortCommodityError, match="implementation_digest_mismatch"):
        marginal.compile_snapshot(
            snapshot,
            artifact,
            evidence,
            root=root,
            registry_path=root / "governance" / "port_commodity_marginals.json",
            rights_path=rights,
            signers_path=root / "governance" / "rights_signers.json",
        )


def test_missing_or_tampered_extraction_evidence_is_refused(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    snapshot = tmp_path / "snapshot.json"
    value = _snapshot(artifact)
    evidence = _bind_extraction_evidence(value, artifact, tmp_path)
    _write(snapshot, value)
    registry_path = _write_fixture_registry(tmp_path, artifact)
    with pytest.raises(
        marginal.PortCommodityError, match="extraction_evidence_count_invalid"
    ):
        marginal.validate_only(
            snapshot, artifact, evidence[:1], registry_path=registry_path
        )
    evidence[1].write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        marginal.PortCommodityError, match="extraction_evidence_digest_mismatch"
    ):
        marginal.validate_only(
            snapshot, artifact, evidence, registry_path=registry_path
        )
