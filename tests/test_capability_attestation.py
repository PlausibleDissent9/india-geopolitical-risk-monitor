"""Adversarial checks for computed IGRM Max capability maturity."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from src import capability_attestation as ca

ROOT = Path(__file__).resolve().parents[1]


def _copy_bound_tree(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    registry = json.loads(
        (ROOT / ca.REGISTRY_RELATIVE).read_text(encoding="utf-8")
    )
    paths = {
        registry["launch_contract"]["path"],
        "governance/capability_attestation_registry.json",
        "governance/schemas/capability-attestation.schema.json",
        "governance/schemas/gap-atom.schema.json",
        *(row["path"] for row in registry["artifacts"]),
    }
    for relative in paths:
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _by_id(report: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        row["capability_id"]: row
        for row in report["capabilities"]  # type: ignore[index,union-attr]
    }


def test_all_38_launch_capabilities_are_measured_and_none_is_complete_by_assertion() -> None:
    report = ca.build_report()
    launch = json.loads(
        (ROOT / "design/igrm_max_launch_contract.json").read_text(encoding="utf-8")
    )
    expected_ids = [row["id"] for row in launch["required_capabilities"]]
    rows = report["capabilities"]
    assert [row["capability_id"] for row in rows] == expected_ids
    assert report["summary"] == {
        "capability_denominator": 38,
        "denominator_status": "proposed_launch_scope_not_founder_authorized",
        "scope_authority": "proposed_unsigned",
        "state_counts": {
            "target_only": 21,
            "contract_only": 17,
            "synthetic_verified": 0,
            "real_bounded": 0,
            "externally_validated": 0,
            "operational": 0,
        },
        "gap_atoms": 38,
    }
    assert report["_meta"]["partial"] is True
    assert all(row["computed_state"] != "operational" for row in rows)
    assert all(row["computed_state"] != "synthetic_verified" for row in rows)


def test_foundry_evidence_stops_at_contract_only() -> None:
    rows = _by_id(ca.build_report())
    foundry = rows["declared_universe_partition"]
    assert foundry["computed_state"] == "contract_only"
    assert {row["evidence_class"] for row in foundry["evidence"]} == {"contract"}
    assert foundry["next_state"] == "synthetic_verified"
    assert foundry["counterevidence"] == [
        "unregistered_evidence_bundle:synthetic_verified"
    ]
    assert rows["dependency_flow_reconciliation"]["computed_state"] == "contract_only"
    assert rows["edge_evidence"]["computed_state"] == "contract_only"


def test_unsigned_fabricated_receipt_cannot_promote_with_rehashed_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _copy_bound_tree(tmp_path)
    fake_engine = root / "src/fake_foundry.py"
    fake_test = root / "tests/test_fake_foundry.py"
    fake_receipt = root / "validation/fake_foundry_receipt.json"
    for path, content in (
        (fake_engine, "VALUE = True\n"),
        (fake_test, "def test_pass():\n    assert True\n"),
        (fake_receipt, '{"exit_code": 0, "status": "pass", "passed_tests": 999}\n'),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    registry_path = root / ca.REGISTRY_RELATIVE
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["artifacts"].extend(
        [
            {
                "artifact_id": "fake_foundry_implementation",
                "path": "src/fake_foundry.py",
                "sha256": hashlib.sha256(fake_engine.read_bytes()).hexdigest(),
                "evidence_class": "implementation",
            },
            {
                "artifact_id": "fake_foundry_test",
                "path": "tests/test_fake_foundry.py",
                "sha256": hashlib.sha256(fake_test.read_bytes()).hexdigest(),
                "evidence_class": "adversarial_test",
            },
            {
                "artifact_id": "fake_foundry_receipt",
                "path": "validation/fake_foundry_receipt.json",
                "sha256": hashlib.sha256(fake_receipt.read_bytes()).hexdigest(),
                "evidence_class": "execution_receipt",
            },
        ]
    )
    rule = next(
        row
        for row in registry["capability_rules"]
        if row["capability_id"] == "declared_universe_partition"
    )
    rule["levels"]["synthetic_verified"] = [
        "foundry_profile",
        "fake_foundry_implementation",
        "fake_foundry_test",
        "fake_foundry_receipt",
    ]
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(
        ca,
        "EXPECTED_REGISTRY_SHA256",
        hashlib.sha256(registry_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "unsigned_synthetic_evidence_forbidden"


def test_capability_registry_cannot_declare_its_own_state(tmp_path: Path) -> None:
    root = _copy_bound_tree(tmp_path)
    path = root / ca.REGISTRY_RELATIVE
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["capability_rules"][0]["computed_state"] = "operational"
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "capability_registry_drift"


def test_mutated_contract_lowers_only_affected_capabilities(tmp_path: Path) -> None:
    root = _copy_bound_tree(tmp_path)
    event_contract = root / "governance/event_ledger_contract.json"
    event_contract.write_bytes(event_contract.read_bytes() + b"\n")
    report = ca.build_report(root)
    rows = _by_id(report)
    assert rows["typed_event"]["computed_state"] == "target_only"
    assert rows["epistemic_status"]["computed_state"] == "target_only"
    assert rows["open_conformance"]["computed_state"] == "contract_only"
    evidence = rows["typed_event"]["evidence"]
    mutated = next(row for row in evidence if row["artifact_id"] == "event_contract")
    assert mutated["status"] == "hash_mismatch"
    assert rows["typed_event"]["counterevidence"] == ["event_contract"]
    assert report["summary"]["capability_denominator"] == 38


def test_missing_artifact_lowers_state_instead_of_shrinking_denominator(
    tmp_path: Path,
) -> None:
    root = _copy_bound_tree(tmp_path)
    (root / "governance/knowledge_replay_registry.json").unlink()
    report = ca.build_report(root)
    row = _by_id(report)["knowledge_replay"]
    assert row["computed_state"] == "target_only"
    assert row["counterevidence"] == ["replay_contract"]
    assert report["summary"]["capability_denominator"] == 38


def test_event_ledger_extension_profile_is_contract_only_evidence(
    tmp_path: Path,
) -> None:
    root = _copy_bound_tree(tmp_path)
    profile = root / "standard/oges/extensions/event-ledger/0.1.0/profile.json"
    profile.write_bytes(profile.read_bytes() + b"\n")
    rows = _by_id(ca.build_report(root))
    for capability_id in (
        "typed_event",
        "epistemic_status",
        "knowledge_replay",
        "contradiction_preservation",
    ):
        assert rows[capability_id]["computed_state"] == "target_only"
        assert rows[capability_id]["counterevidence"] == [
            "event_ledger_extension_profile"
        ]
    assert rows["open_conformance"]["computed_state"] == "contract_only"


def test_launch_contract_denominator_is_hash_bound(tmp_path: Path) -> None:
    root = _copy_bound_tree(tmp_path)
    path = root / "design/igrm_max_launch_contract.json"
    launch = json.loads(path.read_text(encoding="utf-8"))
    launch["required_capabilities"].pop()
    path.write_text(json.dumps(launch), encoding="utf-8")
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "launch_contract_drift"


def test_coordinated_launch_and_registry_substitution_is_refused(
    tmp_path: Path,
) -> None:
    root = _copy_bound_tree(tmp_path)
    launch_path = root / "design/igrm_max_launch_contract.json"
    launch = json.loads(launch_path.read_text(encoding="utf-8"))
    launch["required_capabilities"][0] = {
        "id": "placeholder_capability",
        "requirement": "A coordinated substitute must not redefine the proposed launch denominator.",
    }
    launch_path.write_text(json.dumps(launch), encoding="utf-8")
    registry_path = root / ca.REGISTRY_RELATIVE
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["launch_contract"]["sha256"] = hashlib.sha256(
        launch_path.read_bytes()
    ).hexdigest()
    registry["capability_rules"][0]["capability_id"] = "placeholder_capability"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "capability_registry_drift"


def test_unrelated_rule_bundle_cannot_be_relabelled_as_capability_evidence(
    tmp_path: Path,
) -> None:
    root = _copy_bound_tree(tmp_path)
    path = root / ca.REGISTRY_RELATIVE
    registry = json.loads(path.read_text(encoding="utf-8"))
    rule = next(
        row
        for row in registry["capability_rules"]
        if row["capability_id"] == "knowledge_replay"
    )
    rule["levels"]["contract_only"] = ["shock_contract"]
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "capability_registry_drift"


def test_test_source_bytes_cannot_claim_synthetic_verification(
    tmp_path: Path,
) -> None:
    root = _copy_bound_tree(tmp_path)
    fake_test = root / "tests/fake_capability_test.py"
    fake_test.parent.mkdir(parents=True, exist_ok=True)
    fake_test.write_text("def test_pass():\n    assert True\n", encoding="utf-8")
    fake_engine = root / "src/fake_capability.py"
    fake_engine.parent.mkdir(parents=True, exist_ok=True)
    fake_engine.write_text("VALUE = True\n", encoding="utf-8")
    path = root / ca.REGISTRY_RELATIVE
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["artifacts"].extend(
        [
            {
                "artifact_id": "fake_engine",
                "path": "src/fake_capability.py",
                "sha256": hashlib.sha256(fake_engine.read_bytes()).hexdigest(),
                "evidence_class": "implementation",
            },
            {
                "artifact_id": "fake_test",
                "path": "tests/fake_capability_test.py",
                "sha256": hashlib.sha256(fake_test.read_bytes()).hexdigest(),
                "evidence_class": "adversarial_test",
            },
        ]
    )
    registry["capability_rules"][0]["levels"]["synthetic_verified"] = [
        "event_contract",
        "fake_engine",
        "fake_test",
    ]
    path.write_text(json.dumps(registry), encoding="utf-8")
    with pytest.raises(ca.CapabilityAttestationError) as exc:
        ca.build_report(root)
    assert exc.value.code == "capability_registry_drift"


def test_semantically_supported_event_claims_do_not_exceed_contract() -> None:
    rows = _by_id(ca.build_report())
    assert rows["typed_event"]["computed_state"] == "contract_only"
    assert rows["epistemic_status"]["computed_state"] == "contract_only"
    assert rows["contradiction_preservation"]["computed_state"] == "contract_only"
    assert rows["signed_release_provenance"]["computed_state"] == "target_only"


def test_every_incomplete_capability_has_a_typed_gap_atom() -> None:
    report = ca.build_report()
    rows = _by_id(report)
    gaps = {row["capability_id"]: row for row in report["gap_atoms"]}
    assert set(gaps) == set(rows)
    for capability_id, gap in gaps.items():
        row = rows[capability_id]
        assert gap["observed_state"] == row["computed_state"]
        assert gap["target_state"] == row["next_state"]
        assert gap["failure_ids"]
        assert gap["rollback"].startswith(f"retain_{row['computed_state']}")
        assert gap["authority_class"] == row["authority_class"]


def test_external_outcomes_cannot_be_promoted_without_external_evidence() -> None:
    rows = _by_id(ca.build_report())
    for capability_id in ("benchmark_losses", "blinded_utility", "evaluation_exchange"):
        row = rows[capability_id]
        assert row["computed_state"] == "target_only"
        assert row["risk_class"] == "R4_external_outcome"
        assert row["authority_class"] == "independent_external_evidence_required"
