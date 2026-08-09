from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator
from src import dependency_observation as dep

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/dependency-observation/0.1.0")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approved_rights(
    root: Path,
    *,
    reviewed_on: str = "2026-08-09",
    review_due: str = "2027-08-09",
    rights_registry_effective: str = "2026-08-09",
    signers_registry_effective: str = "2026-08-09",
) -> tuple[Path, Path, dict[str, str]]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers_path = root / "governance/rights_signers.json"
    _write_json(
        signers_path,
        {
            "schema_version": "1.0.0",
            "effective": signers_registry_effective,
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "fixture_rights_reviewer",
                    "name": "Fixture rights reviewer",
                    "role": "test-only rights reviewer",
                    "public_key_ed25519_base64": base64.b64encode(public).decode(),
                    "effective": "2026-08-09",
                    "revoked_on": None,
                }
            ],
        },
    )
    source = {
        "source_id": "fixture_port_table",
        "name": "Fixture official port table",
        "provider": "Fixture ministry",
        "role": "official_port_country_commodity_observations",
        "authority_class": "official_primary",
        "independence_group": "fixture_ministry",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "fixture-port-rights-2026-08-09",
        "decision_owner": "Fixture owner",
        "signer_id": "fixture_rights_reviewer",
        "decision_artifact_path": "governance/rights_decisions/fixture_port.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/fixture_port.sig",
        "reviewed_on": reviewed_on,
        "review_due": review_due,
        "access_url": "https://example.gov.test/port-table",
        "terms_url": "https://example.gov.test/open-data-terms",
        "access_basis": "synthetic_open_data_fixture",
        "geographic_coverage": "Synthetic table frame",
        "historical_coverage": "One synthetic fiscal year",
        "retrieval_target": "Synthetic joint observations",
        "outage_fallback": "Fail closed",
        "cost_owner": "Fixture owner",
        "reproducibility_tier": "open_fixture",
        "max_current_age_days": 3650,
        "permitted_uses": ["cite_metadata", "publish_derived_value", "publish_extract"],
        "notes": "Synthetic test-only authorization.",
    }
    decision_fields = (
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
    decision = {field: source[field] for field in decision_fields}
    decision.update(
        schema_version="1.0.0",
        statement="Synthetic authorization for the exact three registered uses.",
    )
    decision_path = root / str(source["decision_artifact_path"])
    _write_json(decision_path, decision)
    source["decision_artifact_sha256"] = _sha(decision_path)
    signature_path = root / str(source["decision_signature_path"])
    signature_path.write_bytes(private.sign(decision_path.read_bytes()))
    rights_path = root / "governance/source_rights_registry.json"
    _write_json(
        rights_path,
        {
            "schema_version": "1.0.0",
            "effective": rights_registry_effective,
            "default_policy": "deny",
            "sources": [source],
        },
    )
    return (
        rights_path,
        signers_path,
        {
            "source_id": str(source["source_id"]),
            "rights_decision_id": str(source["decision_id"]),
            "rights_decision_artifact_sha256": str(source["decision_artifact_sha256"]),
            "rights_registry_sha256": _sha(rights_path),
            "rights_signers_sha256": _sha(signers_path),
        },
    )


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    shutil.copy2(ROOT / "src/dependency_observation.py", root / "src/dependency_observation.py")
    (root / EXTENSION.parent).mkdir(parents=True)
    shutil.copytree(ROOT / EXTENSION, root / EXTENSION)
    base = root / "standard/oges/0.1.0/profile.json"
    base.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "standard/oges/0.1.0/profile.json", base)
    return root


def _method(root: Path) -> dict[str, str]:
    path = root / "src/dependency_observation.py"
    return {
        "method_id": "dependency_observation_fixture",
        "version": "0.1.0",
        "implementation_path": "src/dependency_observation.py",
        "implementation_sha256": _sha(path),
        "run_id": "fixture_run_20260809",
    }


def _valid_bundle(
    tmp_path: Path,
    *,
    reviewed_on: str = "2026-08-09",
    review_due: str = "2027-08-09",
    rights_registry_effective: str = "2026-08-09",
    signers_registry_effective: str = "2026-08-09",
) -> tuple[Path, Path, Path, dict[str, Any]]:
    root = _fixture_root(tmp_path)
    rights_path, signers_path, source_rights = _approved_rights(
        root,
        reviewed_on=reviewed_on,
        review_due=review_due,
        rights_registry_effective=rights_registry_effective,
        signers_registry_effective=signers_registry_effective,
    )
    artifact_sha = "a" * 64
    method = _method(root)
    labels = {
        "country": (
            "role:country_of_origin",
            [("Iraq", "country:irq"), ("Kuwait", "country:kwt")],
        ),
        "commodity": (
            "role:principal_commodity",
            [("Crude petroleum", "commodity:crude_petroleum"), ("Coal", "commodity:coal")],
        ),
        "port": (
            "role:india_major_port_table_column",
            [("Deendayal", "port:deendayal"), ("Mumbai", "port:mumbai")],
        ),
    }
    frames: list[dict[str, Any]] = []
    crosswalks: list[dict[str, Any]] = []
    entry_ids: dict[tuple[str, str], str] = {}
    known_entities: set[str] = set()
    for slot, (semantic_role_id, members) in labels.items():
        frame = dep.seal_record(
            {
                "object_type": "source_label_frame",
                "schema_version": "0.1.0",
                "frame_id": f"labelframe:fixture:{slot}",
                "source_id": source_rights["source_id"],
                "source_artifact_sha256": artifact_sha,
                "slot": slot,
                "semantic_role_id": semantic_role_id,
                "provider_values": [provider for provider, _ in members],
                "member_count": len(members),
                "extraction_method": copy.deepcopy(method),
            }
        )
        frames.append(frame)
        entries = []
        for index, (provider, entity_id) in enumerate(members, start=1):
            entry_id = f"xwe:{slot}:{index}"
            entry_ids[(slot, provider)] = entry_id
            known_entities.add(entity_id)
            entries.append(
                {
                    "entry_id": entry_id,
                    "provider_value": provider,
                    "resolution_status": "matched",
                    "canonical_entity_id": entity_id,
                    "evidence_ids": [f"evidence:{slot}:{index}"],
                    "reviewed_by": ["reviewer:fixture"],
                    "limitation_codes": [],
                }
            )
        crosswalks.append(
            dep.seal_record(
                {
                    "object_type": "entity_crosswalk_release",
                    "schema_version": "0.1.0",
                    "crosswalk_id": f"crosswalk:fixture:{slot}",
                    "frame_id": frame["frame_id"],
                    "frame_record_sha256": frame["record_sha256"],
                    "source_id": source_rights["source_id"],
                    "slot": slot,
                    "semantic_role_id": semantic_role_id,
                    "entries": entries,
                    "entry_count": len(entries),
                    "resolution_counts": {
                        "matched": len(entries),
                        "unmatched": 0,
                        "ambiguous": 0,
                        "withheld": 0,
                    },
                }
            )
        )

    cells = [
        ("observed_positive", "Iraq", "Crude petroleum", "Deendayal", 5.0),
        ("observed_zero", "Kuwait", "Crude petroleum", "Mumbai", 0.0),
        ("source_missing", "Iraq", "Coal", "Mumbai", None),
        ("suppressed", "Kuwait", "Coal", "Deendayal", None),
        ("source_blank", "Iraq", "Coal", "Deendayal", None),
        ("not_applicable", "Kuwait", "Crude petroleum", "Deendayal", None),
    ]
    observations: list[dict[str, Any]] = []
    for index, (status, country, commodity, port, value) in enumerate(cells, start=1):
        roles = []
        for slot, provider in (
            ("country", country),
            ("commodity", commodity),
            ("port", port),
        ):
            semantic_role_id, members = labels[slot]
            entity_id = dict(members)[provider]
            roles.append(
                {
                    "slot": slot,
                    "semantic_role_id": semantic_role_id,
                    "provider_value": provider,
                    "crosswalk_entry_id": entry_ids[(slot, provider)],
                    "resolution_status": "matched",
                    "canonical_entity_id": entity_id,
                    "interpretation_status": "resolved",
                }
            )
        observations.append(
            {
                "object_type": "dependency_observation",
                "schema_version": "0.1.0",
                "observation_id": f"depobs:fixture:{index}",
                "record_sha256": "0" * 64,
                "relation_type": "joint_physical_flow_observation",
                "flow_semantics_id": "flow:overseas_cargo_unloaded_at_india_major_port",
                "value_status": status,
                "measure": (
                    {
                        "value": value,
                        "unit": "thousand_metric_tonnes",
                        "scale_factor": 1000,
                        "denominator": "exact source joint cell",
                    }
                    if value is not None
                    else None
                ),
                "roles": roles,
                "period": {
                    "label": "2024-25",
                    "start": "2024-04-01",
                    "end": "2025-03-31",
                    "time_basis": "fiscal_year",
                },
                "observed_at": "2025-06-01T00:00:00Z",
                "knowledge_available_at": "2025-06-02T00:00:00Z",
                "compiled_at": "2026-08-09T00:00:00Z",
                "source": {
                    **source_rights,
                    "artifact_sha256": artifact_sha,
                    "locator": {
                        "document_id": "fixture-port-table-2024-25",
                        "table_id": "fixture-table-1",
                        "page": 1,
                        "row": index,
                        "column": port,
                    },
                },
                "coverage": {
                    "joint_frame_id": "frame:fixture:port-cells",
                    "joint_frame_sha256": "0" * 64,
                    "joint_frame_count": len(cells),
                    "frame_member_id": f"member:fixture:{index}",
                    "value_partition": {
                        "observed_positive": 1,
                        "observed_zero": 1,
                        "source_missing": 1,
                        "suppressed": 1,
                    },
                },
                "method": copy.deepcopy(method),
                "relation_compilation_status": (
                    "eligible_for_separate_registered_projection"
                    if status == "observed_positive"
                    else "blocked_nonpositive_or_missing"
                ),
                "guarantees": {
                    "binary_edge_implied": False,
                    "causal_attribution_performed": False,
                    "forecast_performed": False,
                    "risk_score_assigned": False,
                },
                "limitation_codes": ["synthetic_fixture"],
            }
        )
    bundle = {
        "observations": observations,
        "frames": frames,
        "crosswalks": crosswalks,
        "known_entity_ids": sorted(known_entities),
    }
    _reframe(bundle)
    return root, rights_path, signers_path, bundle


def _reframe(bundle: dict[str, Any]) -> None:
    observations = bundle["observations"]
    partition = Counter(row["value_status"] for row in observations)
    digest = dep.canonical_joint_frame_sha256(observations)
    for row in observations:
        row["coverage"]["joint_frame_count"] = len(observations)
        row["coverage"]["joint_frame_sha256"] = digest
        row["coverage"]["value_partition"] = {
            status: partition[status]
            for status in (
                "observed_positive",
                "observed_zero",
                "source_blank",
                "source_missing",
                "suppressed",
                "not_applicable",
            )
        }
        sealed = dep.seal_record(row)
        row.clear()
        row.update(sealed)


def _reseal(record: dict[str, Any]) -> None:
    sealed = dep.seal_record(record)
    record.clear()
    record.update(sealed)


def _validate(
    root: Path, rights_path: Path, signers_path: Path, bundle: dict[str, Any]
) -> dict[str, Any]:
    return dep.validate_bundle(
        observations=bundle["observations"],
        frames=bundle["frames"],
        crosswalks=bundle["crosswalks"],
        known_entity_ids=set(bundle["known_entity_ids"]),
        root=root,
        profile_path=root / EXTENSION / "profile.json",
        rights_path=rights_path,
        signers_path=signers_path,
    )


def test_valid_bundle_is_complete_lossless_and_not_an_edge(tmp_path: Path) -> None:
    root, rights, signers, bundle = _valid_bundle(tmp_path)
    result = _validate(root, rights, signers, bundle)
    assert result["status"] == "conformant_dependency_observation_frame"
    assert result["observation_count"] == 6
    assert result["value_partition"] == {
        "observed_positive": 1,
        "observed_zero": 1,
        "source_blank": 1,
        "source_missing": 1,
        "suppressed": 1,
        "not_applicable": 1,
    }
    assert result["claim_boundary"] == "structural_source_observations_not_dependency_edges"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reviewed_on": "2026-12-01", "review_due": "2027-12-01"},
        {"rights_registry_effective": "2026-12-01"},
        {"signers_registry_effective": "2026-12-01"},
    ],
)
def test_future_rights_state_cannot_authorize_earlier_observations(
    tmp_path: Path, kwargs: dict[str, str]
) -> None:
    root, rights, signers, bundle = _valid_bundle(tmp_path, **kwargs)
    with pytest.raises(dep.DependencyObservationError) as exc:
        _validate(root, rights, signers, bundle)
    assert exc.value.code == "observation_rights_invalid"


def test_schema_binds_every_value_status_to_its_measure(tmp_path: Path) -> None:
    _, _, _, bundle = _valid_bundle(tmp_path)
    schema = json.loads(
        (ROOT / EXTENSION / "dependency-observation.schema.json").read_text()
    )
    validator = Draft202012Validator(schema)
    invalid = []
    positive_null = copy.deepcopy(bundle["observations"][0])
    positive_null["measure"] = None
    invalid.append(positive_null)
    zero_positive = copy.deepcopy(bundle["observations"][1])
    zero_positive["measure"]["value"] = 7
    invalid.append(zero_positive)
    for index in (2, 3, 4, 5):
        hidden = copy.deepcopy(bundle["observations"][index])
        hidden["measure"] = {
            "value": 7,
            "unit": "thousand_metric_tonnes",
            "scale_factor": 1000,
            "denominator": "exact source joint cell",
        }
        invalid.append(hidden)
    assert all(not validator.is_valid(row) for row in invalid)


def _positive_without_measure(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["measure"] = None
    _reseal(bundle["observations"][0])


def _missing_with_measure(bundle: dict[str, Any]) -> None:
    bundle["observations"][2]["measure"] = {
        "value": 1.0,
        "unit": "thousand_metric_tonnes",
        "scale_factor": 1000,
        "denominator": "exact source joint cell",
    }
    _reseal(bundle["observations"][2])


def _blank_with_hidden_measure(bundle: dict[str, Any]) -> None:
    bundle["observations"][4]["measure"] = {
        "value": 7.0,
        "unit": "thousand_metric_tonnes",
        "scale_factor": 1000,
        "denominator": "exact source joint cell",
    }
    _reseal(bundle["observations"][4])


def _zero_with_positive_measure(bundle: dict[str, Any]) -> None:
    bundle["observations"][1]["measure"]["value"] = 7.0
    _reseal(bundle["observations"][1])


def _required_role_removed(bundle: dict[str, Any]) -> None:
    row = bundle["observations"][0]
    row["roles"].pop()
    replacement = copy.deepcopy(row["roles"][0])
    replacement["slot"] = "reported_country"
    replacement["semantic_role_id"] = "role:provider_reported_country_loaded_ambiguous"
    replacement["interpretation_status"] = "provider_ambiguous"
    row["roles"].append(replacement)
    _reframe(bundle)


def _duplicate_role_slot(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["roles"].append(copy.deepcopy(bundle["observations"][0]["roles"][0]))
    _reframe(bundle)


def _unregistered_role(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["roles"][0]["semantic_role_id"] = "role:invented_country"
    _reframe(bundle)


def _loaded_relabelled_destination(bundle: dict[str, Any]) -> None:
    row = bundle["observations"][0]
    row["flow_semantics_id"] = (
        "flow:overseas_cargo_loaded_at_india_major_port_country_role_unresolved"
    )
    row["roles"][0]["slot"] = "reported_country"
    row["roles"][0]["semantic_role_id"] = "role:country_of_origin"
    _reframe(bundle)


def _crosswalk_member_omitted(bundle: dict[str, Any]) -> None:
    crosswalk = bundle["crosswalks"][0]
    crosswalk["entries"].pop()
    crosswalk["entry_count"] = 1
    crosswalk["resolution_counts"]["matched"] = 1
    _reseal(crosswalk)


def _matched_without_entity(bundle: dict[str, Any]) -> None:
    crosswalk = bundle["crosswalks"][0]
    crosswalk["entries"][0]["canonical_entity_id"] = None
    _reseal(crosswalk)


def _crosswalk_value_mismatch(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["roles"][0]["provider_value"] = "Kuwait"
    _reframe(bundle)


def _knowledge_before_observation(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["knowledge_available_at"] = "2025-05-31T00:00:00Z"
    _reseal(bundle["observations"][0])


def _rights_missing(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["source"]["rights_registry_sha256"] = "b" * 64
    _reseal(bundle["observations"][0])


def _record_tamper(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["limitation_codes"].append("tampered_after_seal")


def _partition_incomplete(bundle: dict[str, Any]) -> None:
    wrong = {
        "observed_positive": 2,
        "observed_zero": 0,
        "source_blank": 1,
        "source_missing": 1,
        "suppressed": 1,
        "not_applicable": 1,
    }
    for row in bundle["observations"]:
        row["coverage"]["value_partition"] = wrong
        _reseal(row)


def _invented_method(bundle: dict[str, Any]) -> None:
    bundle["observations"][0]["method"]["implementation_sha256"] = "c" * 64
    _reseal(bundle["observations"][0])


MUTATIONS: dict[str, Callable[[dict[str, Any]], None]] = {
    "positive_value_without_measure": _positive_without_measure,
    "source_missing_with_measure": _missing_with_measure,
    "source_blank_with_hidden_measure": _blank_with_hidden_measure,
    "zero_labelled_positive_measure": _zero_with_positive_measure,
    "required_role_removed": _required_role_removed,
    "duplicate_role_slot": _duplicate_role_slot,
    "unregistered_role_semantics": _unregistered_role,
    "loaded_country_relabelled_destination": _loaded_relabelled_destination,
    "crosswalk_member_omitted": _crosswalk_member_omitted,
    "matched_crosswalk_without_entity": _matched_without_entity,
    "observation_crosswalk_value_mismatch": _crosswalk_value_mismatch,
    "knowledge_before_observation": _knowledge_before_observation,
    "rights_snapshot_or_approval_missing": _rights_missing,
    "record_hash_tampered": _record_tamper,
    "value_partition_not_complete": _partition_incomplete,
    "invented_method_digest": _invented_method,
}


def _registered_cases() -> dict[str, str | None]:
    document = json.loads((ROOT / EXTENSION / "adversarial-cases.json").read_text())
    return {row["case_id"]: row["expected_reason"] for row in document["cases"]}


@pytest.mark.parametrize("case_id", sorted(MUTATIONS))
def test_registered_adversarial_cases_refuse_exact_reason(tmp_path: Path, case_id: str) -> None:
    registered = _registered_cases()
    assert set(registered) == {"valid_complete_joint_observation", *MUTATIONS}
    root, rights, signers, bundle = _valid_bundle(tmp_path)
    MUTATIONS[case_id](bundle)
    with pytest.raises(dep.DependencyObservationError) as exc_info:
        _validate(root, rights, signers, bundle)
    assert exc_info.value.code == registered[case_id]


def test_profile_pins_specification_and_reference_implementation(tmp_path: Path) -> None:
    root, rights, signers, bundle = _valid_bundle(tmp_path)
    spec = root / EXTENSION / "SPEC.md"
    spec.write_text(spec.read_text() + "\nmutation\n", encoding="utf-8")
    with pytest.raises(
        dep.DependencyObservationError, match="profile_specification_digest_mismatch"
    ):
        _validate(root, rights, signers, bundle)


def test_cli_honours_custom_root_profile(tmp_path: Path) -> None:
    root, rights, signers, bundle = _valid_bundle(tmp_path)
    bundle_path = tmp_path / "bundle.json"
    _write_json(bundle_path, bundle)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.dependency_observation",
            "--bundle",
            str(bundle_path),
            "--root",
            str(root),
            "--rights-registry",
            str(rights),
            "--rights-signers",
            str(signers),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["status"] == "conformant_dependency_observation_frame"
