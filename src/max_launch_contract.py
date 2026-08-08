"""Fail-closed validator for the proposed IGRM Max launch program.

The contract is not a motivational roadmap.  It prevents the October scope from
quietly shrinking and prevents repository activity from being relabelled as an
external outcome.  A completed deliverable must name committed product, contract
and test surfaces together; every engine and required capability remains in the
machine-readable denominator until it is genuinely evidenced.

The scope lock and founder authorization are deliberately separate.  Scope can
be inspected while authorization is pending; the full validator succeeds only
after the founder's registered Ed25519 key verifies a detached authorization
statement over the immutable scope digest.  Progress rows remain mutable and
are explicitly outside that signature.

Standalone::

    python -m src.max_launch_contract --scope-only
    python -m src.max_launch_contract
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "design" / "igrm_max_launch_contract.json"
FOUNDER_SIGNERS = ROOT / "governance" / "founder_signers.json"
AUTHORIZATION_STATEMENT = (
    ROOT / "governance" / "authorizations" / "igrm-max-2026-10-24.authorization.json"
)
AUTHORIZATION_SIGNATURE = (
    ROOT / "governance" / "authorizations" / "igrm-max-2026-10-24.authorization.sig"
)
EXPECTED_SCOPE_SHA256 = "1f3ccea2e2f67980bf13d0d581fac0ff5dab2ef9c4d51a8b4d9ae2f845af9ec6"
REQUIRED_AUTHORIZATION_POLICY = {
    "mechanism": "detached_ed25519",
    "required_signer_id": "founder:ishan-krishna",
    "required_role": "igrm_max_scope_authorizer",
    "signer_registry_path": "governance/founder_signers.json",
    "statement_path": (
        "governance/authorizations/igrm-max-2026-10-24.authorization.json"
    ),
    "signature_path": (
        "governance/authorizations/igrm-max-2026-10-24.authorization.sig"
    ),
    "scope_only": True,
    "progress_excluded": True,
}
AUTHORIZATION_TEXT = (
    "I, Ishan Krishna, authorize the exact IGRM Max scope, launch date and "
    "INR budget ceiling identified by this statement. I understand that this "
    "does not approve any individual purchase or establish validation, legal "
    "clearance, external adoption, citation, award or government endorsement."
)
AUTHORIZATION_LIMITATIONS = [
    "no_individual_purchase_approved",
    "not_scientific_validation",
    "not_legal_clearance",
    "not_external_adoption",
    "not_citation_or_award",
    "not_government_endorsement",
]

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
    "dependency_twin",
    "contradiction_uncertainty",
    "decision_compiler",
    "federated_evidence_network",
    "institutional_memory",
    "security_integrity_plane",
    "evaluation_exchange",
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
    "declared_universe_partition",
    "dependency_flow_reconciliation",
    "contradiction_preservation",
    "uncertainty_decomposition",
    "proof_carrying_clauses",
    "constraint_feasibility",
    "substitution_capacity_lag",
    "role_invariant_outputs",
    "value_of_information",
    "federated_signed_modules",
    "restricted_evidence_boundary",
    "signed_release_provenance",
    "publication_quorum",
    "secure_build_supply_chain",
    "prompt_injection_boundary",
    "incident_recovery",
    "institutional_memory",
    "evaluation_exchange",
}
BUDGET_ALLOCATIONS = {
    "independent_measurement": 70_000,
    "flagship_vertical_data_and_review": 40_000,
    "security_privacy_accessibility": 50_000,
    "blinded_pilot_operations": 35_000,
    "hosting_archival_monitoring": 15_000,
    "methods_editor_translation": 15_000,
    "contingency": 25_000,
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
        "launch_date": document.get("launch_date"),
        "objective": document.get("objective"),
        "category_definition": document.get("category_definition"),
        "budget": {
            "currency": budget.get("currency"),
            "ceiling": budget.get("ceiling"),
            "state": budget.get("state"),
            "purchase_rule": budget.get("purchase_rule"),
            "legal_cost_assumption": budget.get("legal_cost_assumption"),
            "allocation_envelope": budget.get("allocation_envelope"),
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


def validate_scope(
    document: dict[str, Any], *, repo_root: Path = ROOT
) -> dict[str, object]:
    if document.get("schema_version") != "1.2.0":
        _fail("schema_version_invalid")
    if document.get("program_id") != "igrm-max-2026-10-24":
        _fail("program_id_invalid")
    if document.get("status") != "founder_authorization_pending":
        _fail("authorization_state_invalid")
    if _day(document.get("proposed_on"), "proposal_date_invalid") != date(2026, 8, 8):
        _fail("proposal_date_changed")
    if document.get("authorization_policy") != REQUIRED_AUTHORIZATION_POLICY:
        _fail("authorization_policy_changed")
    launch = _day(document.get("launch_date"), "launch_date_invalid")
    if launch != date(2026, 10, 24):
        _fail("launch_date_changed")
    category = document.get("category_definition")
    if not isinstance(category, str) or len(category) < 250:
        _fail("category_definition_too_weak")

    budget = document.get("budget")
    if not isinstance(budget, dict) or set(budget) != {
        "currency",
        "ceiling",
        "state",
        "purchase_rule",
        "legal_cost_assumption",
        "allocation_envelope",
    }:
        _fail("budget_contract_invalid")
    if (
        budget.get("currency") != "INR"
        or budget.get("ceiling") != 250_000
        or budget.get("state") != "ceiling_proposed_no_purchase_approved"
        or not isinstance(budget.get("purchase_rule"), str)
        or not isinstance(budget.get("legal_cost_assumption"), str)
    ):
        _fail("budget_contract_invalid")
    allocations = budget.get("allocation_envelope")
    if not isinstance(allocations, list) or len(allocations) != len(BUDGET_ALLOCATIONS):
        _fail("budget_allocation_invalid")
    observed_allocations: dict[str, int] = {}
    for row in allocations:
        if not isinstance(row, dict) or set(row) != {"id", "ceiling", "buys"}:
            _fail("budget_allocation_invalid")
        allocation_id = row.get("id")
        ceiling = row.get("ceiling")
        buys = row.get("buys")
        if (
            not isinstance(allocation_id, str)
            or allocation_id in observed_allocations
            or not isinstance(ceiling, int)
            or isinstance(ceiling, bool)
            or ceiling <= 0
            or not isinstance(buys, str)
            or len(buys) < 60
        ):
            _fail("budget_allocation_invalid")
        observed_allocations[allocation_id] = ceiling
    if observed_allocations != BUDGET_ALLOCATIONS:
        _fail("budget_allocation_changed")
    if sum(observed_allocations.values()) != budget["ceiling"]:
        _fail("budget_allocation_sum_mismatch")

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
        "status": "scope_valid_authorization_pending",
    }


def canonical_json_bytes(document: dict[str, Any]) -> bytes:
    """The one byte representation that may be signed."""

    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _read_strict_json_file(path: Path, code: str) -> tuple[bytes, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        _fail(code)
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MaxLaunchContractError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value)


def _authorization_day(value: object, proposed: date, launch: date) -> date:
    authorized = _day(value, "authorization_date_invalid")
    if not proposed <= authorized <= launch:
        _fail("authorization_date_outside_program")
    return authorized


def _founder_public_key(
    registry: dict[str, Any], *, authorized_on: date
) -> Ed25519PublicKey:
    if set(registry) != {"schema_version", "effective", "default_policy", "signers"}:
        _fail("founder_signer_registry_invalid")
    if (
        registry.get("schema_version") != "1.0.0"
        or registry.get("default_policy") != "deny"
        or _day(registry.get("effective"), "founder_signer_registry_invalid")
        > authorized_on
    ):
        _fail("founder_signer_registry_invalid")
    rows = registry.get("signers")
    if not isinstance(rows, list):
        _fail("founder_signer_registry_invalid")
    ids: set[str] = set()
    required: dict[str, Any] | None = None
    for value in rows:
        if not isinstance(value, dict) or set(value) != {
            "signer_id",
            "name",
            "role",
            "public_key_ed25519_base64",
            "public_key_sha256",
            "effective",
            "revoked_on",
        }:
            _fail("founder_signer_entry_invalid")
        signer_id = value.get("signer_id")
        if not isinstance(signer_id, str) or signer_id in ids:
            _fail("founder_signer_entry_invalid")
        ids.add(signer_id)
        if signer_id == REQUIRED_AUTHORIZATION_POLICY["required_signer_id"]:
            required = value
    if required is None:
        _fail("founder_signer_missing")
    if (
        required.get("name") != "Ishan Krishna"
        or required.get("role") != REQUIRED_AUTHORIZATION_POLICY["required_role"]
    ):
        _fail("founder_signer_identity_invalid")
    effective = _day(required.get("effective"), "founder_signer_effective_invalid")
    revoked_raw = required.get("revoked_on")
    revoked = (
        _day(revoked_raw, "founder_signer_revocation_invalid")
        if revoked_raw is not None
        else None
    )
    if effective > authorized_on or (revoked is not None and revoked <= authorized_on):
        _fail("founder_signer_not_effective")
    encoded_key = required.get("public_key_ed25519_base64")
    if not isinstance(encoded_key, str):
        _fail("founder_public_key_invalid")
    try:
        raw_key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise MaxLaunchContractError("founder_public_key_invalid") from exc
    if len(raw_key) != 32 or base64.b64encode(raw_key).decode("ascii") != encoded_key:
        _fail("founder_public_key_invalid")
    if required.get("public_key_sha256") != hashlib.sha256(raw_key).hexdigest():
        _fail("founder_public_key_fingerprint_invalid")
    try:
        return Ed25519PublicKey.from_public_bytes(raw_key)
    except ValueError as exc:
        raise MaxLaunchContractError("founder_public_key_invalid") from exc


def build_authorization_statement(
    document: dict[str, Any],
    *,
    signer_registry_bytes: bytes,
    authorized_on: str,
) -> dict[str, Any]:
    """Build the exact statement the founder must personally sign."""

    validate_scope(document)
    authorization_date = _authorization_day(
        authorized_on,
        _day(document.get("proposed_on"), "proposal_date_invalid"),
        _day(document.get("launch_date"), "launch_date_invalid"),
    )
    budget = document["budget"]
    return {
        "schema_version": "1.0.0",
        "authorization_id": "founder-authorization:igrm-max-2026-10-24",
        "program_id": document["program_id"],
        "signer_id": REQUIRED_AUTHORIZATION_POLICY["required_signer_id"],
        "signer_role": REQUIRED_AUTHORIZATION_POLICY["required_role"],
        "authorized_on": authorization_date.isoformat(),
        "proposal_date": document["proposed_on"],
        "launch_date": document["launch_date"],
        "program_scope_sha256": scope_sha256(document),
        "scope_projection": "src.max_launch_contract._scope_projection",
        "progress_excluded": True,
        "signer_registry_path": REQUIRED_AUTHORIZATION_POLICY["signer_registry_path"],
        "signer_registry_sha256": hashlib.sha256(signer_registry_bytes).hexdigest(),
        "budget": {
            "currency": budget["currency"],
            "ceiling": budget["ceiling"],
            "purchase_rule": budget["purchase_rule"],
            "individual_purchases_approved": False,
        },
        "statement": AUTHORIZATION_TEXT,
        "limitations": AUTHORIZATION_LIMITATIONS,
    }


def validate_contract(
    document: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    signer_registry_path: Path = FOUNDER_SIGNERS,
    authorization_statement_path: Path = AUTHORIZATION_STATEMENT,
    authorization_signature_path: Path = AUTHORIZATION_SIGNATURE,
) -> dict[str, object]:
    """Validate immutable scope and the founder's detached authorization."""

    summary = validate_scope(document, repo_root=repo_root)
    statement_raw, statement = _read_strict_json_file(
        authorization_statement_path, "authorization_statement_missing"
    )
    if statement_raw != canonical_json_bytes(statement):
        _fail("authorization_statement_not_canonical")
    authorized = _authorization_day(
        statement.get("authorized_on"),
        _day(document.get("proposed_on"), "proposal_date_invalid"),
        _day(document.get("launch_date"), "launch_date_invalid"),
    )
    registry_raw, registry = _read_strict_json_file(
        signer_registry_path, "founder_signer_registry_missing"
    )
    public_key = _founder_public_key(registry, authorized_on=authorized)
    expected_statement = build_authorization_statement(
        document,
        signer_registry_bytes=registry_raw,
        authorized_on=authorized.isoformat(),
    )
    if statement != expected_statement:
        _fail("authorization_statement_scope_mismatch")
    if authorization_signature_path.is_symlink() or not authorization_signature_path.is_file():
        _fail("authorization_signature_missing")
    try:
        signature = authorization_signature_path.read_bytes()
    except OSError as exc:
        raise MaxLaunchContractError("authorization_signature_missing") from exc
    if len(signature) != 64:
        _fail("authorization_signature_invalid")
    try:
        public_key.verify(signature, statement_raw)
    except InvalidSignature as exc:
        raise MaxLaunchContractError("authorization_signature_invalid") from exc
    return {
        **summary,
        "status": "founder_authorized_contract_valid",
        "authorized_on": authorized.isoformat(),
        "authorization_statement_sha256": hashlib.sha256(statement_raw).hexdigest(),
        "authorization_signature_sha256": hashlib.sha256(signature).hexdigest(),
    }


def main() -> None:
    try:
        summary = (
            validate_scope(load_contract())
            if "--scope-only" in sys.argv
            else validate_contract(load_contract())
        )
    except MaxLaunchContractError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
