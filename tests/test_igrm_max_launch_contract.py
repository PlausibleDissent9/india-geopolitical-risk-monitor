"""The founder-authorized October program must not shrink or self-certify.

The contract, validator and these refusal tests land together.  Scope text is
hash-registered, while completed progress resolves to immutable regular-file
blobs at an ancestor commit rather than whichever bytes happen to be at HEAD.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest
from src.max_launch_contract import (
    CONTRACT,
    EXPECTED_SCOPE_SHA256,
    MaxLaunchContractError,
    load_contract,
    scope_sha256,
    validate_contract,
)


def _document() -> dict[str, object]:
    return copy.deepcopy(load_contract())


def test_founder_authorized_october_scope_and_proof_are_registered() -> None:
    document = _document()
    summary = validate_contract(document)

    assert summary == {
        "program_id": "igrm-max-2026-10-24",
        "launch_date": "2026-10-24",
        "pillars": 8,
        "engines": 11,
        "required_capabilities": 20,
        "completed_deliverables": 1,
        "status": "contract_valid",
    }
    assert document["program_scope_sha256"] == EXPECTED_SCOPE_SHA256
    assert scope_sha256(document) == EXPECTED_SCOPE_SHA256
    policy = document["founder_contact_policy"]
    assert policy["action_queue"] == {
        "id": "igrm-max-founder-actions-2026-10-24",
        "visibility": "founder_private",
        "repository_path": None,
    }


def test_public_spec_points_to_the_executable_scope_lock() -> None:
    spec = (CONTRACT.parents[1] / "IGRM_MAX_SPEC.md").read_text(encoding="utf-8")
    assert "design/igrm_max_launch_contract.json" in spec
    assert "python -m src.max_launch_contract" in spec
    assert "24 October 2026" in spec


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
        validate_contract(document)


def test_completed_work_cannot_be_relabelled_or_self_attested() -> None:
    document = _document()
    workbench = document["evidence_backed_progress"][0]

    workbench["capability_ids"] = ["bounded_scenarios"]
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_capabilities_changed"
    ):
        validate_contract(document)

    document = _document()
    workbench = document["evidence_backed_progress"][0]
    workbench["commit"] = "0" * 40
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_commit_changed"
    ):
        validate_contract(document)

    document = _document()
    workbench = document["evidence_backed_progress"][0]
    workbench["artifacts"][0]["sha256"] = "0" * 64
    with pytest.raises(
        MaxLaunchContractError, match="completed_deliverable_artifacts_changed"
    ):
        validate_contract(document)

    document = _document()
    fake = copy.deepcopy(document["evidence_backed_progress"][0])
    fake["deliverable_id"] = "unbuilt_world_state_engine"
    document["evidence_backed_progress"].append(fake)
    with pytest.raises(MaxLaunchContractError, match="completed_deliverable_unregistered"):
        validate_contract(document)


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
        validate_contract(document)


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
