"""The proposed October scope must not shrink or self-certify authorization.

The contract, validator and refusal tests land before the founder signs. Scope
text is hash-registered, authorization is detached, and completed progress
resolves to immutable regular-file blobs at an ancestor commit rather than
whichever bytes happen to be at HEAD.
"""
from __future__ import annotations

import base64
import copy
import hashlib
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.max_launch_contract import (
    AUTHORIZATION_SIGNATURE,
    AUTHORIZATION_STATEMENT,
    CONTRACT,
    EXPECTED_SCOPE_SHA256,
    FOUNDER_SIGNERS,
    REQUIRED_AUTHORIZATION_POLICY,
    MaxLaunchContractError,
    build_authorization_statement,
    canonical_json_bytes,
    load_contract,
    scope_sha256,
    validate_contract,
    validate_scope,
)


def _document() -> dict[str, object]:
    return copy.deepcopy(load_contract())


def _signed_paths(
    tmp_path: Path, document: dict[str, object]
) -> tuple[Path, Path, Path, Ed25519PrivateKey]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    registry = {
        "schema_version": "1.0.0",
        "effective": "2026-08-08",
        "default_policy": "deny",
        "signers": [
            {
                "signer_id": REQUIRED_AUTHORIZATION_POLICY["required_signer_id"],
                "name": "Ishan Krishna",
                "role": REQUIRED_AUTHORIZATION_POLICY["required_role"],
                "public_key_ed25519_base64": base64.b64encode(public_key).decode(),
                "public_key_sha256": hashlib.sha256(public_key).hexdigest(),
                "effective": "2026-08-08",
                "revoked_on": None,
            }
        ],
    }
    registry_path = tmp_path / "founder_signers.json"
    registry_bytes = canonical_json_bytes(registry)
    registry_path.write_bytes(registry_bytes)
    statement = build_authorization_statement(
        document,  # type: ignore[arg-type]
        signer_registry_bytes=registry_bytes,
        authorized_on="2026-08-08",
    )
    statement_path = tmp_path / "authorization.json"
    statement_bytes = canonical_json_bytes(statement)
    statement_path.write_bytes(statement_bytes)
    signature_path = tmp_path / "authorization.sig"
    signature_path.write_bytes(private_key.sign(statement_bytes))
    return registry_path, statement_path, signature_path, private_key


def test_october_scope_is_registered_but_founder_authorization_is_pending() -> None:
    document = _document()
    summary = validate_scope(document)

    assert summary == {
        "program_id": "igrm-max-2026-10-24",
        "launch_date": "2026-10-24",
        "pillars": 8,
        "engines": 11,
        "required_capabilities": 20,
        "completed_deliverables": 1,
        "status": "scope_valid_authorization_pending",
    }
    assert document["status"] == "founder_authorization_pending"
    assert document["program_scope_sha256"] == EXPECTED_SCOPE_SHA256
    assert scope_sha256(document) == EXPECTED_SCOPE_SHA256
    policy = document["founder_contact_policy"]
    assert policy["action_queue"] == {
        "id": "igrm-max-founder-actions-2026-10-24",
        "visibility": "founder_private",
        "repository_path": None,
    }
    assert load_contract()["authorization_policy"] == REQUIRED_AUTHORIZATION_POLICY
    assert not AUTHORIZATION_STATEMENT.exists()
    assert not AUTHORIZATION_SIGNATURE.exists()
    assert load_contract(FOUNDER_SIGNERS)["signers"] == []
    with pytest.raises(MaxLaunchContractError, match="authorization_statement_missing"):
        validate_contract(document)


def test_valid_detached_founder_signature_authorizes_only_the_registered_scope(
    tmp_path: Path,
) -> None:
    document = _document()
    registry, statement, signature, _private_key = _signed_paths(tmp_path, document)
    summary = validate_contract(
        document,
        signer_registry_path=registry,
        authorization_statement_path=statement,
        authorization_signature_path=signature,
    )
    assert summary["status"] == "founder_authorized_contract_valid"
    assert summary["authorized_on"] == "2026-08-08"
    assert len(summary["authorization_statement_sha256"]) == 64
    assert len(summary["authorization_signature_sha256"]) == 64


def test_authorization_refuses_absent_or_tampered_signature(tmp_path: Path) -> None:
    document = _document()
    registry, statement, signature, _private_key = _signed_paths(tmp_path, document)
    signature.unlink()
    with pytest.raises(MaxLaunchContractError, match="authorization_signature_missing"):
        validate_contract(
            document,
            signer_registry_path=registry,
            authorization_statement_path=statement,
            authorization_signature_path=signature,
        )

    signature.write_bytes(b"0" * 64)
    with pytest.raises(MaxLaunchContractError, match="authorization_signature_invalid"):
        validate_contract(
            document,
            signer_registry_path=registry,
            authorization_statement_path=statement,
            authorization_signature_path=signature,
        )


def test_signed_statement_cannot_change_scope_date_budget_or_registry(
    tmp_path: Path,
) -> None:
    document = _document()
    registry, statement, signature, _private_key = _signed_paths(tmp_path, document)
    value = load_contract(statement)
    value["budget"]["ceiling"] = 1
    statement.write_bytes(canonical_json_bytes(value))
    with pytest.raises(MaxLaunchContractError, match="authorization_statement_scope_mismatch"):
        validate_contract(
            document,
            signer_registry_path=registry,
            authorization_statement_path=statement,
            authorization_signature_path=signature,
        )

    registry, statement, signature, _private_key = _signed_paths(tmp_path / "registry", document)
    registry_value = load_contract(registry)
    registry_value["effective"] = "2026-08-07"
    registry.write_bytes(canonical_json_bytes(registry_value))
    with pytest.raises(MaxLaunchContractError, match="authorization_statement_scope_mismatch"):
        validate_contract(
            document,
            signer_registry_path=registry,
            authorization_statement_path=statement,
            authorization_signature_path=signature,
        )


def test_progress_is_explicitly_outside_founder_scope_signature(tmp_path: Path) -> None:
    document = _document()
    registry, statement, signature, _private_key = _signed_paths(tmp_path, document)
    document["evidence_backed_progress"].append(
        {
            "deliverable_id": "future_progress_row",
            "pillar_ids": ["atlas"],
            "capability_ids": ["bounded_scenarios"],
            "state": "in_progress",
        }
    )
    assert scope_sha256(document) == EXPECTED_SCOPE_SHA256
    summary = validate_contract(
        document,
        signer_registry_path=registry,
        authorization_statement_path=statement,
        authorization_signature_path=signature,
    )
    assert summary["status"] == "founder_authorized_contract_valid"


def test_public_spec_points_to_the_executable_scope_lock() -> None:
    spec = (CONTRACT.parents[1] / "IGRM_MAX_SPEC.md").read_text(encoding="utf-8")
    assert "design/igrm_max_launch_contract.json" in spec
    assert "python -m src.max_launch_contract" in spec
    assert "24 October 2026" in spec
    assert "governance/FOUNDER_AUTHORIZATION.md" in spec


def test_founder_private_key_cannot_be_created_inside_the_repository() -> None:
    from scripts.founder_authorize import AuthorizationToolError, _outside_repository

    with pytest.raises(AuthorizationToolError, match="private_key_must_be_outside"):
        _outside_repository(CONTRACT.parents[1] / "forbidden-private-key.pem")
    tracked_private_keys = [
        path
        for path in CONTRACT.parents[1].rglob("*")
        if ".git" not in path.parts
        and ".venv" not in path.parts
        and path.is_file()
        and path.suffix in {".pem", ".key"}
    ]
    assert tracked_private_keys == []


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda document: document["required_capabilities"].pop(),
            "capability_denominator_changed",
        ),
        (
            lambda document: document["milestones"][0]["required_engine_ids"].append(
                "forecast_lab"
            ),
            "engine_schedule_not_exact_partition",
        ),
        (
            lambda document: next(
                row for row in document["engines"] if row["id"] == "forecast_lab"
            ).__setitem__("human_expert_tournament_required", True),
            "human_forecast_dependency_reintroduced",
        ),
        (
            lambda document: document["required_capabilities"][0].__setitem__(
                "requirement", "A typed object may be added later."
            ),
            "program_scope_digest_mismatch",
        ),
        (
            lambda document: document["founder_contact_policy"][
                "interrupt_only_for"
            ].append("routine_technical_review"),
            "founder_interrupt_boundary_changed",
        ),
    ],
)
def test_scope_shrinkage_and_exam_interrupt_drift_refuse(
    mutate: object, error: str
) -> None:
    document = _document()
    mutate(document)  # type: ignore[operator]
    with pytest.raises(MaxLaunchContractError, match=error):
        validate_scope(document)


def test_completed_work_cannot_be_relabelled_or_self_attested() -> None:
    document = _document()
    workbench = document["evidence_backed_progress"][0]

    workbench["capability_ids"] = ["bounded_scenarios"]
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_capabilities_changed"
    ):
        validate_scope(document)

    document = _document()
    workbench = document["evidence_backed_progress"][0]
    workbench["commit"] = "0" * 40
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_commit_changed"
    ):
        validate_scope(document)

    document = _document()
    workbench = document["evidence_backed_progress"][0]
    workbench["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_artifacts_changed"
    ):
        validate_scope(document)

    document = _document()
    fake = copy.deepcopy(document["evidence_backed_progress"][0])
    fake["deliverable_id"] = "unbuilt_world_state_engine"
    document["evidence_backed_progress"].append(fake)
    with pytest.raises(MaxLaunchContractError, match="completed_deliverable_unregistered"):
        validate_scope(document)


def test_completed_artifact_hash_is_checked_against_its_commit(monkeypatch: object) -> None:
    document = _document()
    workbench = document["evidence_backed_progress"][0]

    # Preserve the registered row comparison, then demonstrate that the
    # independent blob verifier would refuse different committed bytes.
    from src import max_launch_contract as module

    registration = module.REGISTERED_COMPLETE_DELIVERABLES[
        "citation_ready_research_workbench"
    ]
    mutated_artifacts = set(registration["artifacts"])
    role, path, _digest = next(iter(mutated_artifacts))
    mutated_artifacts.remove((role, path, _digest))
    mutated_artifacts.add((role, path, "0" * 64))
    monkeypatch.setitem(registration, "artifacts", mutated_artifacts)  # type: ignore[attr-defined]
    workbench["artifacts"] = [
        {"role": artifact_role, "path": artifact_path, "sha256": artifact_hash}
        for artifact_role, artifact_path, artifact_hash in sorted(mutated_artifacts)
    ]

    with pytest.raises(MaxLaunchContractError, match="progress_artifact_hash_mismatch"):
        validate_scope(document)


def test_duplicate_json_keys_are_refused_before_validation(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"1.0.0","schema_version":"1.0.0"}',
        encoding="utf-8",
    )
    with pytest.raises(MaxLaunchContractError, match="duplicate_json_key:schema_version"):
        load_contract(duplicate)


def test_contract_file_is_the_validator_default() -> None:
    assert CONTRACT.is_file()
    assert load_contract() == load_contract(CONTRACT)
