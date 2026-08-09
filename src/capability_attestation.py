"""Compute evidence-bound maturity and mandatory gaps for IGRM Max capabilities.

States are never accepted from the registry.  They are derived from the exact
launch-contract denominator and hash-bound evidence bundles.  Missing or
changed evidence lowers only the affected capability; it cannot silently keep
the former state or make the denominator smaller.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker

from src.max_launch_contract import MaxLaunchContractError, validate_contract

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_RELATIVE = Path("governance/capability_attestation_registry.json")
ATTESTATION_SCHEMA = ROOT / "governance/schemas/capability-attestation.schema.json"
GAP_SCHEMA = ROOT / "governance/schemas/gap-atom.schema.json"

# These are independent trust anchors for the initial unsigned proposal.  A
# coordinated edit to the launch scope and its evidence registry must not be
# able to redefine the denominator or relabel evidence without changing this
# reviewed implementation as well.
EXPECTED_REGISTRY_SHA256 = (
    "45fb5b893554c7d977c58e4e063fcd3bb41691dd06d9ff54dec0ccae7b41c525"
)
EXPECTED_LAUNCH_SHA256 = (
    "d99fc11864b97beb31b7067914b1d06458331113773d050b3bae78150def96fc"
)
EXPECTED_CAPABILITY_PROJECTION_SHA256 = (
    "6bcc17df8fbd867ef929272fc8b712a9abfd4bbf9c6d18a24277a83c5ad0540b"
)

STATE_ORDER = (
    "target_only",
    "contract_only",
    "synthetic_verified",
    "real_bounded",
    "externally_validated",
    "operational",
)
EVIDENCE_CLASSES = {
    "contract",
    "implementation",
    "adversarial_test",
    "execution_receipt",
    "real_bounded_data",
    "rights_decision",
    "external_validation",
    "operational_record",
}
LEVEL_CLASS_FLOORS = {
    "contract_only": {"contract"},
    "synthetic_verified": {
        "contract",
        "implementation",
        "adversarial_test",
        "execution_receipt",
    },
    "real_bounded": {"real_bounded_data", "rights_decision"},
    "externally_validated": {"external_validation"},
    "operational": {"operational_record"},
}
RISK_CLASSES = (
    "R2_product_or_data_expansion",
    "R3_method_claim_rights_or_security_boundary",
    "R4_external_outcome",
)


class CapabilityAttestationError(ValueError):
    """Stable fail-closed contract error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise CapabilityAttestationError(code)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("json_duplicate_key")
        value[key] = item
    return value


def _read(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CapabilityAttestationError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail(code)
    candidate = root.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _file_sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _declared_path(root: Path, relative: object, code: str) -> Path:
    """Resolve a pinned relative path without requiring the leaf to exist."""
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail(code)
    candidate = root.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    try:
        candidate.resolve(strict=False).relative_to(root.resolve())
    except ValueError:
        _fail(code)
    return candidate


def _scope_authority(root: Path, launch: dict[str, Any]) -> dict[str, Any]:
    """Return signed authority only after the existing founder verifier passes."""
    policy = launch.get("authorization_policy")
    if not isinstance(policy, dict):
        _fail("scope_authorization_policy_invalid")
    _declared_path(
        root, policy.get("signer_registry_path"), "scope_authorization_path_invalid"
    )
    statement_path = _declared_path(
        root, policy.get("statement_path"), "scope_authorization_path_invalid"
    )
    signature_path = _declared_path(
        root, policy.get("signature_path"), "scope_authorization_path_invalid"
    )
    if not statement_path.exists() and not signature_path.exists():
        return {
            "scope_authority": "proposed_unsigned",
            "authorization_statement_sha256": None,
            "authorization_signature_sha256": None,
        }
    try:
        summary = validate_contract(
            launch,
            repo_root=root,
            signer_registry_path=_safe_file(
                root,
                cast(str, policy.get("signer_registry_path")),
                "scope_authorization_invalid",
            ),
            authorization_statement_path=_safe_file(
                root,
                cast(str, policy.get("statement_path")),
                "scope_authorization_invalid",
            ),
            authorization_signature_path=_safe_file(
                root,
                cast(str, policy.get("signature_path")),
                "scope_authorization_invalid",
            ),
        )
    except (CapabilityAttestationError, MaxLaunchContractError) as exc:
        raise CapabilityAttestationError("scope_authorization_invalid") from exc
    return {
        "scope_authority": "founder_authorized",
        "authorization_statement_sha256": summary[
            "authorization_statement_sha256"
        ],
        "authorization_signature_sha256": summary[
            "authorization_signature_sha256"
        ],
    }


def _validator(path: Path) -> Draft202012Validator:
    document, _ = _read(path, "capability_schema_unreadable")
    try:
        Draft202012Validator.check_schema(document)
    except Exception as exc:
        raise CapabilityAttestationError("capability_schema_invalid") from exc
    return Draft202012Validator(document, format_checker=FormatChecker())


def _validate_document(
    value: dict[str, Any], validator: Draft202012Validator, code: str
) -> None:
    if next(validator.iter_errors(value), None) is not None:
        _fail(code)


def _rows(value: object, key: str, code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail(code)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get(key), str):
            _fail(code)
        identifier = cast(str, item[key])
        if identifier in seen:
            _fail(code)
        seen.add(identifier)
        rows.append(cast(dict[str, Any], item))
    return rows


def _risk_map(
    capability_ids: set[str], overrides: object
) -> dict[str, str]:
    if not isinstance(overrides, dict) or set(overrides) != set(RISK_CLASSES[1:]):
        _fail("capability_risk_registry_invalid")
    result = {capability_id: RISK_CLASSES[0] for capability_id in capability_ids}
    overridden: set[str] = set()
    for risk_class in RISK_CLASSES[1:]:
        ids = overrides[risk_class]
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            _fail("capability_risk_registry_invalid")
        typed = cast(list[str], ids)
        if len(typed) != len(set(typed)) or not set(typed) <= capability_ids:
            _fail("capability_risk_registry_invalid")
        if overridden & set(typed):
            _fail("capability_risk_registry_invalid")
        overridden.update(typed)
        for capability_id in typed:
            result[capability_id] = risk_class
    return result


def _authority(risk_class: str) -> str:
    return {
        "R2_product_or_data_expansion": "human_scope_review_required",
        "R3_method_claim_rights_or_security_boundary": "founder_or_named_human_authority_required",
        "R4_external_outcome": "independent_external_evidence_required",
    }[risk_class]


def build_report(root: Path = ROOT) -> dict[str, Any]:
    """Compute all 38 capability states and mandatory incomplete-state gaps."""
    registry_path = _safe_file(root, REGISTRY_RELATIVE.as_posix(), "capability_registry_missing")
    registry, registry_sha = _read(registry_path, "capability_registry_invalid")
    if registry_sha != EXPECTED_REGISTRY_SHA256:
        _fail("capability_registry_drift")
    if (
        set(registry)
        != {
            "schema_version",
            "registry_id",
            "revision",
            "predecessor_registry_sha256",
            "authority_status",
            "effective",
            "launch_contract",
            "state_order",
            "artifacts",
            "capability_rules",
            "risk_overrides",
        }
        or
        registry.get("schema_version") != "0.2.0"
        or registry.get("registry_id") != "igrm-max-capability-attestation"
        or registry.get("revision") != 2
        or registry.get("predecessor_registry_sha256")
        != "8b41600670d163096742ed5f2567b525f96aacfebbcc8eacad388f7beca5855d"
        or registry.get("authority_status") != "repository_review_only_unsigned"
        or tuple(registry.get("state_order", [])) != STATE_ORDER
    ):
        _fail("capability_registry_identity_invalid")

    launch_binding = registry.get("launch_contract")
    if not isinstance(launch_binding, dict) or set(launch_binding) != {"path", "sha256"}:
        _fail("launch_contract_binding_invalid")
    launch_path = _safe_file(
        root, launch_binding.get("path"), "launch_contract_path_invalid"
    )
    launch, launch_sha = _read(launch_path, "launch_contract_unreadable")
    if (
        launch_sha != launch_binding.get("sha256")
        or launch_sha != EXPECTED_LAUNCH_SHA256
    ):
        _fail("launch_contract_drift")
    capabilities = _rows(
        launch.get("required_capabilities"), "id", "launch_capabilities_invalid"
    )
    if len(capabilities) != 38:
        _fail("launch_capability_denominator_invalid")
    projection = [
        {"id": row["id"], "requirement": row.get("requirement")}
        for row in capabilities
    ]
    if _canonical_sha(projection) != EXPECTED_CAPABILITY_PROJECTION_SHA256:
        _fail("launch_capability_projection_drift")
    capability_ids = {cast(str, row["id"]) for row in capabilities}
    scope = _scope_authority(root, launch)

    artifacts = _rows(registry.get("artifacts"), "artifact_id", "artifact_registry_invalid")
    artifact_rows = {cast(str, row["artifact_id"]): row for row in artifacts}
    artifact_status: dict[str, dict[str, Any]] = {}
    for artifact_id, row in artifact_rows.items():
        if set(row) != {
            "artifact_id",
            "path",
            "sha256",
            "evidence_class",
        } or row.get("evidence_class") not in EVIDENCE_CLASSES:
            _fail("artifact_evidence_class_invalid")
        path_value = row.get("path")
        observed: str | None = None
        status = "missing"
        try:
            path = _safe_file(root, path_value, "artifact_path_invalid")
            observed = _file_sha(path)
            status = "verified" if observed == row.get("sha256") else "hash_mismatch"
        except CapabilityAttestationError as exc:
            if exc.code != "artifact_path_invalid":
                raise
        artifact_status[artifact_id] = {
            "artifact_id": artifact_id,
            "path": path_value,
            "evidence_class": row["evidence_class"],
            "expected_sha256": row.get("sha256"),
            "observed_sha256": observed,
            "status": status,
        }

    rules = _rows(
        registry.get("capability_rules"), "capability_id", "capability_rules_invalid"
    )
    if not {cast(str, row["capability_id"]) for row in rules} <= capability_ids:
        _fail("capability_rules_invalid")
    rule_map = {cast(str, row["capability_id"]): row for row in rules}
    referenced_artifacts: set[str] = set()
    for rule in rules:
        if set(rule) != {"capability_id", "levels"}:
            _fail("capability_rules_invalid")
        levels = rule.get("levels")
        if not isinstance(levels, dict) or not levels:
            _fail("capability_levels_invalid")
        state_keys = list(levels)
        expected_prefix = list(STATE_ORDER[1 : 1 + len(state_keys)])
        if state_keys != expected_prefix:
            _fail("capability_level_sequence_invalid")
        for level, evidence_ids in levels.items():
            if (
                not isinstance(evidence_ids, list)
                or not evidence_ids
                or not all(isinstance(item, str) for item in evidence_ids)
                or len(evidence_ids) != len(set(evidence_ids))
                or not set(cast(list[str], evidence_ids)) <= set(artifact_rows)
            ):
                _fail("capability_level_evidence_invalid")
            classes = {
                cast(str, artifact_rows[item]["evidence_class"])
                for item in cast(list[str], evidence_ids)
            }
            referenced_artifacts.update(cast(list[str], evidence_ids))
            if not LEVEL_CLASS_FLOORS[level] <= classes:
                _fail("capability_level_class_floor_invalid")
    if referenced_artifacts != set(artifact_rows):
        _fail("unreferenced_artifact_evidence")

    risks = _risk_map(capability_ids, registry.get("risk_overrides"))
    output_rows: list[dict[str, Any]] = []
    gap_atoms: list[dict[str, Any]] = []
    for capability in capabilities:
        capability_id = cast(str, capability["id"])
        selected_rule = rule_map.get(capability_id)
        levels = (
            cast(dict[str, list[str]], selected_rule["levels"])
            if selected_rule
            else {}
        )
        state = "target_only"
        evidence: list[dict[str, Any]] = []
        for candidate in STATE_ORDER[1:]:
            evidence_ids = levels.get(candidate)
            if evidence_ids is None:
                break
            rows = [artifact_status[item] for item in evidence_ids]
            evidence.extend(row for row in rows if row not in evidence)
            if not all(row["status"] == "verified" for row in rows):
                break
            state = candidate
        state_index = STATE_ORDER.index(state)
        next_state = STATE_ORDER[state_index + 1] if state_index + 1 < len(STATE_ORDER) else None
        next_ids = levels.get(next_state, []) if next_state else []
        failures = [
            artifact_status[item]["artifact_id"]
            for item in next_ids
            if artifact_status[item]["status"] != "verified"
        ]
        if next_state is not None and not next_ids:
            failures = [f"unregistered_evidence_bundle:{next_state}"]
        risk_class = risks[capability_id]
        row = {
            "capability_id": capability_id,
            "requirement": capability["requirement"],
            "computed_state": state,
            "evidence": evidence,
            "counterevidence": failures,
            "next_state": next_state,
            "next_gate": (
                None
                if next_state is None
                else f"verify_complete_registered_evidence_bundle_for_{next_state}"
            ),
            "risk_class": risk_class,
            "authority_class": _authority(risk_class),
        }
        output_rows.append(row)
        if next_state is not None:
            gap_atoms.append(
                {
                    "gap_id": f"gap:{capability_id}:{next_state}",
                    "capability_id": capability_id,
                    "observed_state": state,
                    "target_state": next_state,
                    "measured_denominator": {
                        "registered_evidence": len(next_ids),
                        "verified_evidence": sum(
                            artifact_status[item]["status"] == "verified"
                            for item in next_ids
                        ),
                    },
                    "failure_ids": failures,
                    "risk_class": risk_class,
                    "acceptance_test": f"all_registered_{next_state}_evidence_matches_and_class_gate_passes",
                    "rollback": f"retain_{state}_and_remove_stronger_public_claims",
                    "post_release_observation": "recompute_after_each_committed_artifact_change",
                    "authority_class": _authority(risk_class),
                }
            )

    attestation_validator = _validator(
        _safe_file(
            root,
            ATTESTATION_SCHEMA.relative_to(ROOT).as_posix(),
            "capability_schema_missing",
        )
    )
    gap_validator = _validator(
        _safe_file(
            root, GAP_SCHEMA.relative_to(ROOT).as_posix(), "gap_schema_missing"
        )
    )
    for row in output_rows:
        _validate_document(row, attestation_validator, "capability_attestation_invalid")
    for gap in gap_atoms:
        _validate_document(gap, gap_validator, "gap_atom_invalid")
    counts = Counter(row["computed_state"] for row in output_rows)
    return {
        "_meta": {
            "schema": "igrm-capability-attestation-v0.1",
            "generated": registry["effective"],
            "partial": scope["scope_authority"] != "founder_authorized",
            **scope,
            "launch_contract_sha256": launch_sha,
            "registry_sha256": registry_sha,
            "implementation_sha256": _file_sha(Path(__file__)),
            "attestation_schema_sha256": _file_sha(
                root / ATTESTATION_SCHEMA.relative_to(ROOT)
            ),
            "gap_schema_sha256": _file_sha(root / GAP_SCHEMA.relative_to(ROOT)),
            "definition": "States are computed against a code-pinned proposed scope and exact evidence bytes. The denominator is not founder-authorized, and synthetic verification requires a capability-specific execution receipt.",
        },
        "state_order": list(STATE_ORDER),
        "summary": {
            "capability_denominator": len(output_rows),
            "denominator_status": (
                "founder_authorized_launch_scope"
                if scope["scope_authority"] == "founder_authorized"
                else "proposed_launch_scope_not_founder_authorized"
            ),
            "scope_authority": scope["scope_authority"],
            "state_counts": {state: counts[state] for state in STATE_ORDER},
            "gap_atoms": len(gap_atoms),
        },
        "capabilities": output_rows,
        "gap_atoms": gap_atoms,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = build_report()
    if not args.check:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
