"""Fail-closed validator for the founder-authorized IGRM Max launch program.

The contract is not a motivational roadmap.  It prevents the October scope from
quietly shrinking and prevents repository activity from being relabelled as an
external outcome.  A completed deliverable must name committed product, contract
and test surfaces together; every engine and required capability remains in the
machine-readable denominator until it is genuinely evidenced.

Standalone: ``python -m src.max_launch_contract``.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "design" / "igrm_max_launch_contract.json"
EXPECTED_SCOPE_SHA256 = "8dabe5401d505564df84721acfc8c60bd7521b5b004a812102331c91757ebc1e"

PILLARS = {
    "core",
    "atlas",
    "evidence_engine",
    "research_copilot",
    "observatory",
    "benchmark_lab",
    "institution",
    "distribution",
}
ENGINES = {
    "world_state",
    "sensor_fusion",
    "knowledge_time_machine",
    "india_exposure_dna",
    "shock_compiler",
    "causal_lab",
    "strategy_resilience",
    "forecast_lab",
    "verified_copilot",
    "institutional_network",
    "open_evidence_standard",
}
CAPABILITIES = {
    "typed_event",
    "epistemic_status",
    "source_semantics",
    "india_dependency_traversal",
    "edge_evidence",
    "time_varying_exposure",
    "bounded_scenarios",
    "knowledge_replay",
    "hypothesis_falsification",
    "causal_boundary",
    "four_outputs",
    "verified_natural_language",
    "research_subsets",
    "forecast_separation",
    "benchmark_losses",
    "multilingual_access",
    "event_to_recovery",
    "blinded_utility",
    "global_shock_india",
    "open_conformance",
}
PROGRESS_ARTIFACT_ROLES = {
    "public_surface",
    "executable_implementation",
    "contract_and_refusal_test",
}
REGISTERED_COMPLETE_DELIVERABLES: dict[str, dict[str, object]] = {
    "citation_ready_research_workbench": {
        "pillar_ids": {"core", "distribution"},
        "capability_ids": {"research_subsets"},
        "commit": "077883df5d3a588b8264e116209c1871154a5e52",
        "artifacts": {
            (
                "public_surface",
                "docs/workbench.html",
                "0f86da3e6878d846b1139f911585e560e8e6f8b18bb0adbcc5d0a4bc9478a9a0",
            ),
            (
                "executable_implementation",
                "docs/workbench.js",
                "9b5966bfcd49999fcbf272d832e9600fa769d31972bf0f4503976cdaef25cf9a",
            ),
            (
                "contract_and_refusal_test",
                "tests/test_research_workbench.py",
                "7f9b42c0cfccf9e9133f2d674fc9b96f5124647b65cc17228ab60e060ea7fed7",
            ),
        },
    }
}


class MaxLaunchContractError(ValueError):
    """Stable fail-closed contract error."""


def _fail(code: str) -> NoReturn:
    raise MaxLaunchContractError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail(f"duplicate_json_key:{key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> NoReturn:
    _fail(f"nonfinite_json_value:{value}")


def load_contract(path: Path = CONTRACT) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise MaxLaunchContractError("contract_unreadable") from exc
    if not isinstance(value, dict):
        _fail("contract_not_object")
    return value


def _ids(rows: object, kind: str) -> list[str]:
    if not isinstance(rows, list) or not rows:
        _fail(f"{kind}_rows_invalid")
    found: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            _fail(f"{kind}_row_invalid")
        found.append(row["id"])
    if len(found) != len(set(found)):
        _fail(f"{kind}_id_duplicate")
    return found


def _day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail(code)


def _relative_artifact_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.startswith(("/", "~"))
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", value)
    ):
        _fail("progress_artifact_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        _fail("progress_artifact_path_escapes_root")
    return value


def _commit_is_ancestor(root: Path, value: object) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(
        character not in "0123456789abcdef" for character in value
    ):
        _fail("progress_commit_invalid")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{value}^{{commit}}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        _fail("progress_commit_missing")
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", value, "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if ancestry.returncode != 0:
        _fail("progress_commit_not_ancestor")
    return value


def _committed_artifact(root: Path, commit: str, artifact: object) -> str:
    if not isinstance(artifact, dict):
        _fail("progress_artifact_invalid")
    role = artifact.get("role")
    if role not in PROGRESS_ARTIFACT_ROLES:
        _fail("progress_artifact_role_invalid")
    path = _relative_artifact_path(artifact.get("path"))
    expected = artifact.get("sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        _fail("progress_artifact_hash_invalid")

    tree = subprocess.run(
        ["git", "ls-tree", commit, "--", path],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    metadata, separator, tree_path = tree.stdout.rstrip("\n").partition("\t")
    fields = metadata.split()
    if (
        tree.returncode != 0
        or not separator
        or tree_path != path
        or len(fields) != 3
        or fields[0] not in {"100644", "100755"}
        or fields[1] != "blob"
    ):
        _fail("progress_artifact_missing_at_commit")
    content = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if content.returncode != 0:
        _fail("progress_artifact_missing_at_commit")
    if hashlib.sha256(content.stdout).hexdigest() != expected:
        _fail("progress_artifact_hash_mismatch")
    return str(role)


def _scope_projection(document: dict[str, Any]) -> dict[str, object]:
    budget = document.get("budget")
    policy = document.get("founder_contact_policy")
    if not isinstance(budget, dict) or not isinstance(policy, dict):
        _fail("program_scope_invalid")
    return {
        "program_id": document.get("program_id"),
        "status": document.get("status"),
        "authorized_on": document.get("authorized_on"),
        "launch_date": document.get("launch_date"),
        "objective": document.get("objective"),
        "budget": {
            "currency": budget.get("currency"),
            "ceiling": budget.get("ceiling"),
            "purchase_rule": budget.get("purchase_rule"),
        },
        "launch_boundary": document.get("launch_boundary"),
        "pillars": document.get("pillars"),
        "engines": document.get("engines"),
        "required_capabilities": document.get("required_capabilities"),
        "milestones": document.get("milestones"),
        "founder_contact_policy": {
            "default": policy.get("default"),
            "interrupt_only_for": policy.get("interrupt_only_for"),
            "action_queue": policy.get("action_queue"),
        },
        "proof_rule": document.get("proof_rule"),
    }


def scope_sha256(document: dict[str, Any]) -> str:
    encoded = json.dumps(
        _scope_projection(document),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_contract(
    document: dict[str, Any], *, repo_root: Path = ROOT
) -> dict[str, object]:
    if document.get("schema_version") != "1.0.0":
        _fail("schema_version_invalid")
    if document.get("program_id") != "igrm-max-2026-10-24":
        _fail("program_id_invalid")
    if document.get("status") != "founder_authorized":
        _fail("authorization_state_invalid")
    if _day(document.get("authorized_on"), "authorization_date_invalid") != date(2026, 8, 8):
        _fail("authorization_date_changed")
    launch = _day(document.get("launch_date"), "launch_date_invalid")
    if launch != date(2026, 10, 24):
        _fail("launch_date_changed")

    pillar_ids = set(_ids(document.get("pillars"), "pillar"))
    engine_ids = set(_ids(document.get("engines"), "engine"))
    capability_ids = set(_ids(document.get("required_capabilities"), "capability"))
    if pillar_ids != PILLARS:
        _fail("pillar_denominator_changed")
    if engine_ids != ENGINES:
        _fail("engine_denominator_changed")
    if capability_ids != CAPABILITIES:
        _fail("capability_denominator_changed")

    engine_rows = document["engines"]
    for engine in engine_rows:
        mapped = engine.get("pillars")
        if not isinstance(mapped, list) or not mapped or not set(mapped) <= PILLARS:
            _fail("engine_pillar_mapping_invalid")
        if not isinstance(engine.get("launch_definition"), str) or len(
            engine["launch_definition"]
        ) < 80:
            _fail("engine_launch_definition_too_weak")
    forecast = next(row for row in engine_rows if row["id"] == "forecast_lab")
    if forecast.get("allowed_model_classes") != ["statistical", "ai_ensemble"]:
        _fail("forecast_model_boundary_changed")
    if forecast.get("human_expert_tournament_required") is not False:
        _fail("human_forecast_dependency_reintroduced")

    milestones = document.get("milestones")
    if not isinstance(milestones, list) or len(milestones) != 3:
        _fail("milestone_count_invalid")
    milestone_days = [_day(row.get("date"), "milestone_date_invalid") for row in milestones]
    if milestone_days != sorted(milestone_days) or milestone_days[-1] != launch:
        _fail("milestone_dates_invalid")
    scheduled: list[str] = []
    for row in milestones:
        values = row.get("required_engine_ids")
        if not isinstance(values, list) or not values:
            _fail("milestone_engine_list_invalid")
        scheduled.extend(values)
    if len(scheduled) != len(set(scheduled)) or set(scheduled) != ENGINES:
        _fail("engine_schedule_not_exact_partition")

    progress = document.get("evidence_backed_progress")
    if not isinstance(progress, list):
        _fail("progress_invalid")
    progress_ids: set[str] = set()
    completed_ids: set[str] = set()
    for row in progress:
        if not isinstance(row, dict):
            _fail("progress_row_invalid")
        deliverable_id = row.get("deliverable_id")
        if not isinstance(deliverable_id, str) or not deliverable_id:
            _fail("progress_deliverable_id_invalid")
        if deliverable_id in progress_ids:
            _fail("progress_deliverable_id_duplicate")
        progress_ids.add(deliverable_id)
        state = row.get("state")
        if state not in {"not_started", "in_progress", "blocked", "complete"}:
            _fail("progress_state_invalid")
        if state != "complete":
            continue
        registration = REGISTERED_COMPLETE_DELIVERABLES.get(deliverable_id)
        if registration is None:
            _fail("completed_deliverable_unregistered")
        completed_ids.add(deliverable_id)
        pillars = row.get("pillar_ids")
        capabilities = row.get("capability_ids")
        artifacts = row.get("artifacts")
        if not isinstance(pillars, list) or not set(pillars) <= PILLARS:
            _fail("progress_pillar_invalid")
        if not isinstance(capabilities, list) or not set(capabilities) <= CAPABILITIES:
            _fail("progress_capability_invalid")
        if not isinstance(artifacts, list) or len(artifacts) < 3:
            _fail("complete_progress_evidence_insufficient")
        if set(pillars) != registration["pillar_ids"]:
            _fail("completed_deliverable_pillars_changed")
        if set(capabilities) != registration["capability_ids"]:
            _fail("completed_deliverable_capabilities_changed")
        if row.get("commit") != registration["commit"]:
            _fail("completed_deliverable_commit_changed")
        artifact_registration: set[tuple[object, object, object]] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                _fail("progress_artifact_invalid")
            artifact_registration.add(
                (artifact.get("role"), artifact.get("path"), artifact.get("sha256"))
            )
        if artifact_registration != registration["artifacts"]:
            _fail("completed_deliverable_artifacts_changed")
        commit = _commit_is_ancestor(repo_root, row.get("commit"))
        roles: set[str] = set()
        for artifact in artifacts:
            roles.add(_committed_artifact(repo_root, commit, artifact))
        if not PROGRESS_ARTIFACT_ROLES <= roles:
            _fail("complete_progress_evidence_roles_missing")
    if completed_ids != set(REGISTERED_COMPLETE_DELIVERABLES):
        _fail("registered_completed_deliverable_missing")

    policy = document.get("founder_contact_policy")
    if not isinstance(policy, dict) or policy.get("default") != "continue_and_consolidate":
        _fail("founder_contact_policy_invalid")
    expected_interrupts = {
        "spending",
        "legal_or_licensing_authority",
        "external_communication",
        "identity_authorship_or_deposit",
        "fundamental_scope_choice",
        "critical_external_blocker",
    }
    if set(policy.get("interrupt_only_for", [])) != expected_interrupts:
        _fail("founder_interrupt_boundary_changed")
    if policy.get("action_queue") != {
        "id": "igrm-max-founder-actions-2026-10-24",
        "visibility": "founder_private",
        "repository_path": None,
    }:
        _fail("founder_action_queue_boundary_changed")

    declared_scope_hash = document.get("program_scope_sha256")
    if declared_scope_hash != EXPECTED_SCOPE_SHA256:
        _fail("program_scope_registration_changed")
    if scope_sha256(document) != EXPECTED_SCOPE_SHA256:
        _fail("program_scope_digest_mismatch")

    return {
        "program_id": document["program_id"],
        "launch_date": document["launch_date"],
        "pillars": len(pillar_ids),
        "engines": len(engine_ids),
        "required_capabilities": len(capability_ids),
        "completed_deliverables": len(completed_ids),
        "status": "contract_valid",
    }


def main() -> None:
    summary = validate_contract(load_contract())
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
