"""Hostile conformance tests for the OGES Source Frame / Entity Foundry."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import canonical_objects as canonical
from src import dependency_observation as dep
from src import source_frame_entity_foundry as foundry

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_EXTENSION = Path("standard/oges/extensions/dependency-observation/0.1.0")
FOUNDRY_EXTENSION = Path("standard/oges/extensions/source-frame-entity-foundry/0.1.0")


@dataclass
class Fixture:
    root: Path
    profile: Path
    contract: Path
    package: Path
    manifest: Path
    rights_private_key: Ed25519PrivateKey
    release_private_key: Ed25519PrivateKey
    objects: dict[str, Path]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(label.encode()).digest())


def _public(private: Ed25519PrivateKey) -> str:
    raw = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode()


def _lifecycle() -> dict[str, object]:
    return {
        "revision": 1,
        "state": "active",
        "supersedes_id": None,
        "superseded_by": None,
        "correction_id": None,
    }


def _method(method_id: str, path: Path) -> dict[str, object]:
    return {
        "method_id": method_id,
        "version": "1.0.0",
        "implementation_sha256": _sha(path),
        "run_id": "run:foundry.fixture.001",
    }


def _provenance(
    evidence_ids: list[str], method: dict[str, object], reviewed: bool = False
) -> dict[str, object]:
    return {
        "created_at": "2026-08-09T11:00:00Z",
        "created_by": "system:foundry.fixture",
        "reviewed_by": ["person:foundry.fixture.reviewer"] if reviewed else [],
        "adjudication_status": "single_reviewed" if reviewed else "unreviewed",
        "source_ids": ["fixture_foundry_source"],
        "evidence_ids": evidence_ids,
        "method": method,
    }


def _decision_source() -> dict[str, Any]:
    return {
        "source_id": "fixture_foundry_source",
        "name": "Synthetic foundry source",
        "provider": "Synthetic Ministry",
        "role": "official_synthetic_joint_cargo_frame",
        "authority_class": "official_primary",
        "independence_group": "fixture_foundry_provider",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "fixture-foundry-rights-2026-08-09",
        "decision_owner": "Fixture rights owner",
        "signer_id": "signer:fixture.foundry.rights",
        "decision_artifact_path": "governance/rights_decisions/fixture_foundry.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/fixture_foundry.sig",
        "reviewed_on": "2026-08-09",
        "review_due": "2027-08-09",
        "access_url": "https://example.test/foundry/source",
        "terms_url": "https://example.test/foundry/terms",
        "access_basis": "synthetic_test_authorization",
        "geographic_coverage": "One synthetic table frame",
        "historical_coverage": "One synthetic fiscal period",
        "retrieval_target": "Six synthetic n-ary joint cells",
        "outage_fallback": "Fail closed",
        "cost_owner": "Fixture owner",
        "reproducibility_tier": "open_synthetic_fixture",
        "max_current_age_days": 3650,
        "permitted_uses": ["cite_metadata", "publish_derived_value", "publish_extract"],
        "notes": "Synthetic test-only decision; not legal advice.",
    }


def _write_rights(fixture: Fixture | None, root: Path, source: dict[str, Any]) -> Ed25519PrivateKey:
    private = fixture.rights_private_key if fixture is not None else _private("foundry-rights")
    signers_path = root / "governance/rights_signers.json"
    if not signers_path.exists():
        _write_json(
            signers_path,
            {
                "schema_version": "1.0.0",
                "effective": "2026-08-09",
                "default_policy": "deny",
                "signers": [
                    {
                        "signer_id": "signer:fixture.foundry.rights",
                        "name": "Fixture foundry rights signer",
                        "role": "test-only rights reviewer",
                        "public_key_ed25519_base64": _public(private),
                        "effective": "2026-08-09",
                        "revoked_on": None,
                    }
                ],
            },
        )
    fields = (
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
    decision = {field: source[field] for field in fields}
    decision.update(
        schema_version="1.0.0",
        statement="Synthetic authorization for the exact registered fixture uses.",
    )
    decision_path = root / source["decision_artifact_path"]
    _write_json(decision_path, decision)
    source["decision_artifact_sha256"] = _sha(decision_path)
    signature_path = root / source["decision_signature_path"]
    signature_path.write_bytes(private.sign(decision_path.read_bytes()))
    _write_json(
        root / "governance/source_rights_registry.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    return private


def _entity(
    entity_id: str,
    entity_type: str,
    name: str,
    direct_method: dict[str, object],
) -> dict[str, Any]:
    return canonical.seal_record(
        {
            "object_type": "entity",
            "schema_version": "1.0.0",
            "entity_id": entity_id,
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "entity_type": entity_type,
            "canonical_name": name,
            "aliases": [],
            "identifiers": [
                {
                    "scheme": "fixture_foundry",
                    "value": entity_id.split(":", 1)[1],
                    "effective_start": None,
                    "effective_end": None,
                    "evidence_ids": ["evd:fixture.foundry.source"],
                }
            ],
            "parent_entity_ids": [],
            "jurisdiction_entity_ids": [],
            "geometry": {
                "artifact_path": None,
                "artifact_sha256": None,
                "geometry_type": "none",
                "precision": "not_applicable",
            },
            "effective_start": None,
            "effective_end": None,
            "identity_status": "crosswalked",
            "provenance": _provenance(
                ["evd:fixture.foundry.source"], direct_method, reviewed=True
            ),
        }
    )


def _evidence(
    evidence_id: str,
    *,
    title: str,
    content_sha: str,
    direct_method: dict[str, object],
    artifact_path: str | None,
) -> dict[str, Any]:
    is_package = artifact_path is not None
    return canonical.seal_record(
        {
            "object_type": "evidence_item",
            "schema_version": "1.0.0",
            "evidence_id": evidence_id,
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_id": "fixture_foundry_source",
            "source_record_id": evidence_id,
            "retrieval_id": f"ret:{evidence_id.split(':', 1)[1]}",
            "evidence_type": "dataset_observation",
            "title": title,
            "publisher_entity_id": None,
            "authors": [],
            "language": "en",
            "published_at": "2026-08-09T09:00:00Z",
            "observed_at": "2026-08-09T09:00:00Z",
            "effective_start": "2026-08-09T09:00:00Z",
            "effective_end": None,
            "retrieved_at": "2026-08-09T10:00:00Z",
            "geography_entity_ids": [],
            "public_url": None if is_package else "https://example.test/foundry/source.json",
            "artifact_path": artifact_path,
            "content_sha256": content_sha,
            "artifact_sha256": content_sha if is_package else None,
            "content_availability": "public_extract" if is_package else "hash_metadata_only",
            "rights_use": "publish_extract" if is_package else "cite_metadata",
            "rights_decision_id": "fixture-foundry-rights-2026-08-09",
            "privacy_class": "public_with_redactions" if is_package else "public",
            "verification_status": "official_record",
            "extraction_method": "structured_export",
            "provenance": _provenance([], direct_method),
        }
    )


def _universe(
    root: Path,
    *,
    slot: str,
    entity_type: str,
    entity_ids: list[str],
    universe_method: dict[str, object],
) -> tuple[dict[str, Any], Path]:
    frame = canonical.seal_record(
        {
            "object_type": "universe_frame",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "universe_id": f"universe:fixture.foundry.{slot}",
            "entity_type": entity_type,
            "reference_date": "2026-08-09",
            "source_evidence_id": "evd:fixture.foundry.source",
            "source_version": "fixture-v1",
            "extraction_query": f"every distinct matched canonical {slot} identity",
            "extracted_at": "2026-08-09T11:00:00Z",
            "entity_ids": entity_ids,
        }
    )
    frame_path = root / f"frames/{slot}.json"
    _write_json(frame_path, frame)
    release = canonical.seal_record(
        {
            "object_type": "universe_release",
            "schema_version": "1.0.0",
            "universe_release_id": f"unv:fixture.foundry.{slot}.1",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "universe_id": f"universe:fixture.foundry.{slot}",
            "version": "1.0.0",
            "name": f"Synthetic foundry {slot} universe",
            "entity_type": entity_type,
            "reference_date": "2026-08-09",
            "denominator_definition": f"Every distinct matched canonical {slot} identity; unresolved raw labels remain in the source denominator.",
            "inclusion_rule": {
                "rule_id": "rule:fixture.foundry.universe",
                "version": "1.0.0",
                "implementation_path": "rules/foundry_universe.py",
                "implementation_sha256": universe_method["implementation_sha256"],
                "documentation_path": "rules/foundry_universe.md",
            },
            "frame_artifact": {
                "path": str(frame_path.relative_to(root)),
                "sha256": _sha(frame_path),
                "format": "igrm_universe_frame_v1",
            },
            "source_evidence_ids": ["evd:fixture.foundry.source"],
            "members": [
                {
                    "entity_id": entity_id,
                    "status": "included",
                    "reason_code": "reason:fixture.foundry.in_frame",
                    "assessed_on": "2026-08-09",
                }
                for entity_id in entity_ids
            ],
            "counts": {
                "total_eligible": len(entity_ids),
                "included": len(entity_ids),
                "excluded": 0,
                "unmappable": 0,
                "stale": 0,
            },
            "provenance": _provenance(
                ["evd:fixture.foundry.source"], universe_method
            ),
        }
    )
    return release, frame_path


def _dependency_bundle(
    root: Path,
    contract: dict[str, Any],
    source: dict[str, Any],
    entity_ids: list[str],
) -> dict[str, Any]:
    parser = contract["parser"]
    method = {
        "method_id": parser["method_id"],
        "version": parser["version"],
        "implementation_path": parser["path"],
        "implementation_sha256": parser["sha256"],
        "run_id": "run:foundry.fixture.parse.001",
    }
    labels = {
        "country": (
            "role:country_of_origin",
            [("Alpha", "matched", "ent:country.alpha"), ("Beta", "unmatched", None)],
        ),
        "commodity": (
            "role:principal_commodity",
            [
                ("X", "matched", "ent:commodity.x"),
                ("Y", "matched", "ent:commodity.y"),
            ],
        ),
        "port": (
            "role:india_major_port_table_column",
            [
                ("P1", "matched", "ent:port.p1"),
                ("P2", "matched", "ent:port.p2"),
                ("P3", "matched", "ent:port.p3"),
            ],
        ),
    }
    frames: list[dict[str, Any]] = []
    crosswalks: list[dict[str, Any]] = []
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for slot, (role_id, members) in labels.items():
        frame = dep.seal_record(
            {
                "object_type": "source_label_frame",
                "schema_version": "0.1.0",
                "frame_id": f"labelframe:fixture.foundry.{slot}",
                "source_id": source["source_id"],
                "source_artifact_sha256": contract["source"]["artifact_sha256"],
                "slot": slot,
                "semantic_role_id": role_id,
                "provider_values": [raw for raw, _, _ in members],
                "member_count": len(members),
                "extraction_method": copy.deepcopy(method),
            }
        )
        frames.append(frame)
        crosswalk_entries: list[dict[str, Any]] = []
        for index, (raw, status, entity_id) in enumerate(members, start=1):
            entry = {
                "entry_id": f"xwe:fixture.{slot}.{index}",
                "provider_value": raw,
                "resolution_status": status,
                "canonical_entity_id": entity_id,
                "evidence_ids": ["evd:fixture.foundry.source"] if status == "matched" else [],
                "reviewed_by": ["person:foundry.fixture.reviewer"] if status == "matched" else [],
                "limitation_codes": [] if status == "matched" else ["unresolved_source_label"],
            }
            entries[(slot, raw)] = entry
            crosswalk_entries.append(entry)
        counts = Counter(row["resolution_status"] for row in crosswalk_entries)
        crosswalks.append(
            dep.seal_record(
                {
                    "object_type": "entity_crosswalk_release",
                    "schema_version": "0.1.0",
                    "crosswalk_id": f"crosswalk:fixture.foundry.{slot}",
                    "frame_id": frame["frame_id"],
                    "frame_record_sha256": frame["record_sha256"],
                    "source_id": source["source_id"],
                    "slot": slot,
                    "semantic_role_id": role_id,
                    "entries": crosswalk_entries,
                    "entry_count": len(crosswalk_entries),
                    "resolution_counts": {
                        status: counts[status]
                        for status in ("matched", "unmatched", "ambiguous", "withheld")
                    },
                }
            )
        )
    cells = [
        ("Alpha", "X", "P1", "observed_positive", 5),
        ("Alpha", "X", "P2", "observed_zero", 0),
        ("Alpha", "X", "P3", "source_blank", None),
        ("Beta", "Y", "P1", "source_missing", None),
        ("Beta", "Y", "P2", "suppressed", None),
        ("Beta", "Y", "P3", "not_applicable", None),
    ]
    row_by_pair = {
        (row["country_provider_value"], row["commodity_provider_value"]): row
        for row in contract["scope"]["row_tuple_frame"]["tuples"]
    }
    observations: list[dict[str, Any]] = []
    rights_registry_sha = _sha(root / "governance/source_rights_registry.json")
    rights_signers_sha = _sha(root / "governance/rights_signers.json")
    for index, (country, commodity, port, status, value) in enumerate(cells, start=1):
        source_row = row_by_pair[(country, commodity)]
        roles = []
        unresolved = False
        for slot, raw in (("country", country), ("commodity", commodity), ("port", port)):
            entry = entries[(slot, raw)]
            role_id = labels[slot][0]
            unresolved = unresolved or entry["resolution_status"] != "matched"
            roles.append(
                {
                    "slot": slot,
                    "semantic_role_id": role_id,
                    "provider_value": raw,
                    "crosswalk_entry_id": entry["entry_id"],
                    "resolution_status": entry["resolution_status"],
                    "canonical_entity_id": entry["canonical_entity_id"],
                    "interpretation_status": "resolved",
                }
            )
        observations.append(
            {
                "object_type": "dependency_observation",
                "schema_version": "0.1.0",
                "observation_id": f"depobs:fixture.foundry.{index}",
                "record_sha256": "0" * 64,
                "relation_type": "joint_physical_flow_observation",
                "flow_semantics_id": contract["scope"]["flow_semantics_id"],
                "value_status": status,
                "measure": (
                    {
                        "value": value,
                        "unit": "thousand_metric_tonnes",
                        "scale_factor": 1000,
                        "denominator": "exact synthetic joint source cell",
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
                "observed_at": "2025-04-01T00:00:00Z",
                "knowledge_available_at": "2026-08-09T09:00:00Z",
                "compiled_at": "2026-08-09T11:00:00Z",
                "source": {
                    "source_id": source["source_id"],
                    "artifact_sha256": contract["source"]["artifact_sha256"],
                    "rights_decision_id": source["decision_id"],
                    "rights_registry_sha256": rights_registry_sha,
                    "rights_signers_sha256": rights_signers_sha,
                    "rights_decision_artifact_sha256": source[
                        "decision_artifact_sha256"
                    ],
                    "locator": {
                        "document_id": contract["source"]["document_id"],
                        "table_id": contract["scope"]["table_id"],
                        "page": source_row["page"],
                        "row": source_row["row"],
                        "column": port,
                    },
                },
                "coverage": {
                    "joint_frame_id": "frame:fixture.foundry.cells",
                    "joint_frame_sha256": "0" * 64,
                    "joint_frame_count": len(cells),
                    "frame_member_id": f"member:fixture.foundry.{index}",
                    "value_partition": {value_status: 1 for value_status in foundry._VALUE_STATUSES},
                },
                "method": copy.deepcopy(method),
                "relation_compilation_status": (
                    "blocked_unresolved_roles"
                    if unresolved
                    else "eligible_for_separate_registered_projection"
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
        "known_entity_ids": entity_ids,
    }
    _reframe(bundle)
    return bundle


def _reframe(bundle: dict[str, Any]) -> None:
    observations = bundle["observations"]
    partition = Counter(row["value_status"] for row in observations)
    digest = dep.canonical_joint_frame_sha256(observations)
    for row in observations:
        unresolved = any(
            role["resolution_status"] != "matched" for role in row["roles"]
        )
        row["relation_compilation_status"] = (
            "blocked_unresolved_roles"
            if unresolved
            else "blocked_nonpositive_or_missing"
            if row["value_status"] != "observed_positive"
            else "eligible_for_separate_registered_projection"
        )
        row["coverage"]["joint_frame_count"] = len(observations)
        row["coverage"]["joint_frame_sha256"] = digest
        row["coverage"]["value_partition"] = {
            status: partition[status] for status in foundry._VALUE_STATUSES
        }
        sealed = dep.seal_record(row)
        row.clear()
        row.update(sealed)


def _reseal(record: dict[str, Any]) -> None:
    sealed = dep.seal_record(record)
    record.clear()
    record.update(sealed)


def _build_fixture(tmp_path: Path) -> Fixture:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copytree(ROOT / "schemas", root / "schemas")
    (root / DEPENDENCY_EXTENSION.parent).mkdir(parents=True)
    shutil.copytree(ROOT / DEPENDENCY_EXTENSION, root / DEPENDENCY_EXTENSION)
    (root / FOUNDRY_EXTENSION.parent).mkdir(parents=True)
    shutil.copytree(ROOT / FOUNDRY_EXTENSION, root / FOUNDRY_EXTENSION)
    base_profile = root / "standard/oges/0.1.0/profile.json"
    base_profile.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "standard/oges/0.1.0/profile.json", base_profile)
    for relative in (
        "src/dependency_observation.py",
        "src/source_frame_entity_foundry.py",
        "tests/test_source_frame_entity_foundry.py",
        "governance/canonical_schema_registry.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)

    direct_path = root / "methods/direct.py"
    direct_path.parent.mkdir(parents=True)
    direct_path.write_text("def apply(value):\n    return value\n", encoding="utf-8")
    universe_path = root / "rules/foundry_universe.py"
    universe_path.parent.mkdir(parents=True)
    universe_path.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    (root / "rules/foundry_universe.md").write_text(
        "# Synthetic foundry universe rule\n", encoding="utf-8"
    )
    edge_path = root / "methods/edge.py"
    edge_path.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    method_rows = [
        {
            "method_id": "method:fixture.foundry.direct",
            "version": "1.0.0",
            "implementation_path": "methods/direct.py",
            "implementation_sha256": _sha(direct_path),
            "allowed_object_types": ["evidence_item", "entity"],
            "effective": "2026-08-09",
            "superseded_on": None,
        },
        {
            "method_id": "rule:fixture.foundry.universe",
            "version": "1.0.0",
            "implementation_path": "rules/foundry_universe.py",
            "implementation_sha256": _sha(universe_path),
            "allowed_object_types": ["universe_release"],
            "effective": "2026-08-09",
            "superseded_on": None,
        },
        {
            "method_id": "method:fixture.foundry.edge",
            "version": "1.0.0",
            "implementation_path": "methods/edge.py",
            "implementation_sha256": _sha(edge_path),
            "allowed_object_types": ["exposure_edge"],
            "effective": "2026-08-09",
            "superseded_on": None,
        },
    ]
    _write_json(
        root / "governance/canonical_method_registry.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "methods": method_rows,
        },
    )
    release_private = _private("foundry-release")
    _write_json(
        root / "governance/release_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "signer:fixture.foundry.release",
                    "name": "Fixture foundry release signer",
                    "role": "canonical_release_signer",
                    "public_key_ed25519_base64": _public(release_private),
                    "effective": "2026-08-09",
                    "revoked_on": None,
                }
            ],
        },
    )
    source = _decision_source()
    rights_private = _write_rights(None, root, source)

    source_artifact = root / "foundry/source.json"
    row_tuple_frame = {
        "frame_id": "rowframe:fixture.foundry.unloaded",
        "status": "enumerated",
        "tuple_count": 2,
        "record_sha256": "0" * 64,
        "tuples": [
            {
                "row_tuple_id": "rowtuple:fixture.alpha.x",
                "country_provider_value": "Alpha",
                "commodity_provider_value": "X",
                "page": 10,
                "row": 1,
            },
            {
                "row_tuple_id": "rowtuple:fixture.beta.y",
                "country_provider_value": "Beta",
                "commodity_provider_value": "Y",
                "page": 10,
                "row": 2,
            },
        ],
    }
    row_tuple_frame["record_sha256"] = foundry.canonical_row_tuple_frame_sha256(
        row_tuple_frame
    )
    _write_json(
        source_artifact,
        {
            "table_id": "fixture-2.1.6",
            "row_tuples": row_tuple_frame["tuples"],
            "columns": ["P1", "P2", "P3"],
        },
    )
    source_registry = root / "foundry/source-registry.json"
    _write_json(
        source_registry,
        {"schema_version": "0.1.0", "artifact_sha256": _sha(source_artifact)},
    )
    parser_path = root / "src/dependency_observation.py"
    contract = {
        "schema_version": "0.1.0",
        "contract_id": "contract:fixture_foundry_unloaded",
        "effective": "2026-08-09",
        "status": "enumerated_synthetic_fixture",
        "evidence_class": "synthetic_fixture",
        "source": {
            "source_id": source["source_id"],
            "document_id": "fixture-bps-2024-25",
            "artifact_sha256": _sha(source_artifact),
        },
        "source_registry": {
            "path": str(source_registry.relative_to(root)),
            "sha256": _sha(source_registry),
        },
        "parser": {
            "method_id": "method:fixture.foundry.parser",
            "version": "0.1.0",
            "path": "src/dependency_observation.py",
            "sha256": _sha(parser_path),
        },
        "scope": {
            "flow_semantics_id": "flow:overseas_cargo_unloaded_at_india_major_port",
            "provider_flow": "unloaded",
            "table_id": "fixture-2.1.6",
            "pdf_pages": [10],
            "dock_columns": ["P1", "P2", "P3"],
            "expected_detail_rows": 2,
            "expected_joint_cells": 6,
            "source_labels_status": "enumerated_synthetic_fixture",
            "row_tuple_frame": row_tuple_frame,
            "slots": [
                {
                    "slot": "country",
                    "semantic_role_id": "role:country_of_origin",
                    "entity_type": "country",
                    "normalization_rule_id": "normalization:unicode_nfkc_casefold_space",
                    "provider_values": ["Alpha", "Beta"],
                },
                {
                    "slot": "commodity",
                    "semantic_role_id": "role:principal_commodity",
                    "entity_type": "commodity",
                    "normalization_rule_id": "normalization:unicode_nfkc_casefold_space",
                    "provider_values": ["X", "Y"],
                },
                {
                    "slot": "port",
                    "semantic_role_id": "role:india_major_port_table_column",
                    "entity_type": "port",
                    "normalization_rule_id": "normalization:exact_identity",
                    "provider_values": ["P1", "P2", "P3"],
                },
            ],
        },
        "rights": {
            "required_uses": ["cite_metadata", "publish_derived_value", "publish_extract"],
            "human_signature_is_legal_determination": False,
        },
        "forbidden_semantics": [
            "loaded_cargo",
            "binary_dependency_edge",
            "causality",
            "live_state",
        ],
        "limits": ["Synthetic fixture only."],
    }
    contract_path = root / "foundry/source-contract.json"
    _write_json(contract_path, contract)
    profile_path = root / FOUNDRY_EXTENSION / "profile.json"
    profile = json.loads(profile_path.read_text())
    bound_paths = {
        "specification": root / FOUNDRY_EXTENSION / "SPEC.md",
        "reference_source_contract": contract_path,
        "foundry_package_schema": root / FOUNDRY_EXTENSION / "foundry-package.schema.json",
        "normalization_registry": root / FOUNDRY_EXTENSION / "normalization-registry.json",
        "dependency_profile": root / DEPENDENCY_EXTENSION / "profile.json",
        "universe_release_schema": root / "schemas/universe-release.schema.json",
        "canonical_release_schema": root / "schemas/canonical-release.schema.json",
        "adversarial_cases": root / FOUNDRY_EXTENSION / "adversarial-cases.json",
    }
    for row in profile["bound_files"]:
        bound = bound_paths[row["kind"]]
        row["path"] = str(bound.relative_to(root))
        row["sha256"] = _sha(bound)
    profile["reference_implementation"] = {
        "path": "src/source_frame_entity_foundry.py",
        "sha256": _sha(root / "src/source_frame_entity_foundry.py"),
    }
    profile["conformance_test"] = {
        "path": "tests/test_source_frame_entity_foundry.py",
        "sha256": _sha(root / "tests/test_source_frame_entity_foundry.py"),
    }
    _write_json(profile_path, profile)

    direct_method = _method("method:fixture.foundry.direct", direct_path)
    universe_method = _method("rule:fixture.foundry.universe", universe_path)
    entity_specs = [
        ("ent:country.alpha", "country", "Alpha"),
        ("ent:commodity.x", "commodity", "X"),
        ("ent:commodity.y", "commodity", "Y"),
        ("ent:port.p1", "port", "Port 1"),
        ("ent:port.p2", "port", "Port 2"),
        ("ent:port.p3", "port", "Port 3"),
    ]
    entities = [
        _entity(entity_id, entity_type, name, direct_method)
        for entity_id, entity_type, name in entity_specs
    ]
    entity_ids = [row[0] for row in entity_specs]
    bundle = _dependency_bundle(root, contract, source, entity_ids)
    normalizations = []
    for slot in contract["scope"]["slots"]:
        frame = next(row for row in bundle["frames"] if row["slot"] == slot["slot"])
        operation = (
            "exact_identity"
            if slot["normalization_rule_id"] == "normalization:exact_identity"
            else "unicode_nfkc_casefold_space"
        )
        normalizations.append(
            {
                "slot": slot["slot"],
                "frame_id": frame["frame_id"],
                "entries": [
                    {
                        "provider_value": value,
                        "rule_id": slot["normalization_rule_id"],
                        "normalized_value": foundry._normalize(value, operation),
                    }
                    for value in frame["provider_values"]
                ],
            }
        )
    universe_specs = {
        "country": ("country", ["ent:country.alpha"]),
        "commodity": ("commodity", ["ent:commodity.x", "ent:commodity.y"]),
        "port": ("port", ["ent:port.p1", "ent:port.p2", "ent:port.p3"]),
    }
    universes = []
    universe_bindings = []
    for slot, (entity_type, ids) in universe_specs.items():
        universe, _ = _universe(
            root,
            slot=slot,
            entity_type=entity_type,
            entity_ids=ids,
            universe_method=universe_method,
        )
        universes.append(universe)
        crosswalk = next(row for row in bundle["crosswalks"] if row["slot"] == slot)
        counts = crosswalk["resolution_counts"]
        universe_bindings.append(
            {
                "slot": slot,
                "universe_release_id": universe["universe_release_id"],
                "universe_record_sha256": universe["record_sha256"],
                "source_label_count": crosswalk["entry_count"],
                "matched": counts["matched"],
                "unmatched": counts["unmatched"],
                "ambiguous": counts["ambiguous"],
                "withheld": counts["withheld"],
                "canonical_member_count": len(ids),
            }
        )
    package = {
        "object_type": "source_frame_entity_foundry_package",
        "schema_version": "0.1.0",
        "package_id": "foundry:fixture.unloaded.001",
        "package_evidence_id": "evd:fixture.foundry.package",
        "source_evidence_id": "evd:fixture.foundry.source",
        "source_contract_sha256": _sha(contract_path),
        "normalization_registry_sha256": _sha(
            root / FOUNDRY_EXTENSION / "normalization-registry.json"
        ),
        "row_tuple_frame_sha256": row_tuple_frame["record_sha256"],
        "dependency_bundle": bundle,
        "normalizations": normalizations,
        "canonical_convergences": [],
        "universe_bindings": universe_bindings,
        "coverage": {
            "row_tuple_count": 2,
            "dock_column_count": 3,
            "joint_cell_count": 6,
            "value_partition": {status: 1 for status in foundry._VALUE_STATUSES},
        },
        "guarantees": {
            "loaded_cargo_included": False,
            "binary_edges_emitted": False,
            "national_port_completeness_claimed": False,
            "causal_claim_emitted": False,
            "live_state_claimed": False,
        },
        "limitation_codes": ["synthetic_fixture_only"],
    }
    package_path = root / "foundry/package.json"
    _write_json(package_path, package)
    evidence = [
        _evidence(
            "evd:fixture.foundry.source",
            title="Synthetic source frame",
            content_sha=_sha(source_artifact),
            direct_method=direct_method,
            artifact_path=None,
        ),
        _evidence(
            "evd:fixture.foundry.package",
            title="Synthetic foundry package",
            content_sha=_sha(package_path),
            direct_method=direct_method,
            artifact_path=str(package_path.relative_to(root)),
        ),
    ]
    documents = [*evidence, *entities, *universes]
    object_paths: dict[str, Path] = {}
    entries = []
    for document in documents:
        object_type = document["object_type"]
        object_id = document[canonical._ID_FIELD[object_type]]
        path = root / f"canonical/{object_id.replace(':', '__')}.json"
        _write_json(path, document)
        object_paths[object_id] = path
        entries.append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "path": str(path.relative_to(root)),
                "file_sha256": _sha(path),
                "record_sha256": document["record_sha256"],
            }
        )
    rights = json.loads((root / "governance/source_rights_registry.json").read_text())[
        "sources"
    ][0]
    counts = Counter(document["object_type"] for document in documents)
    manifest = canonical.seal_record(
        {
            "object_type": "canonical_release",
            "schema_version": "1.0.0",
            "release_id": "rel:fixture.foundry.2026-08-09",
            "record_sha256": "0" * 64,
            "generated_at": "2026-08-09T12:00:00Z",
            "effective_date": "2026-08-09",
            "schema_registry_sha256": _sha(
                root / "governance/canonical_schema_registry.json"
            ),
            "method_registry_sha256": _sha(
                root / "governance/canonical_method_registry.json"
            ),
            "rights_registry_sha256": _sha(
                root / "governance/source_rights_registry.json"
            ),
            "rights_signers_sha256": _sha(root / "governance/rights_signers.json"),
            "release_signers_sha256": _sha(root / "governance/release_signers.json"),
            "release_signer_id": "signer:fixture.foundry.release",
            "release_signature_path": "canonical/release.sig",
            "rights_snapshot": [
                {
                    "source_id": rights["source_id"],
                    "decision_id": rights["decision_id"],
                    "decision_artifact_sha256": rights["decision_artifact_sha256"],
                    "signer_id": rights["signer_id"],
                    "independence_group": rights["independence_group"],
                    "authority_class": rights["authority_class"],
                }
            ],
            "objects": entries,
            "counts": {
                object_type: counts[object_type]
                for object_type in sorted(canonical._OBJECT_TYPES)
            },
        }
    )
    manifest_path = root / "canonical/release.json"
    _write_json(manifest_path, manifest)
    (root / "canonical/release.sig").write_bytes(
        release_private.sign(manifest_path.read_bytes())
    )
    return Fixture(
        root=root,
        profile=profile_path,
        contract=contract_path,
        package=package_path,
        manifest=manifest_path,
        rights_private_key=rights_private,
        release_private_key=release_private,
        objects=object_paths,
    )


def _resign_release(fixture: Fixture, *, rebind_package: bool = True) -> None:
    if rebind_package:
        evidence_path = fixture.objects["evd:fixture.foundry.package"]
        evidence = json.loads(evidence_path.read_text())
        digest = _sha(fixture.package)
        evidence["content_sha256"] = digest
        evidence["artifact_sha256"] = digest
        _write_json(evidence_path, canonical.seal_record(evidence))
    manifest = json.loads(fixture.manifest.read_text())
    for entry in manifest["objects"]:
        path = fixture.root / entry["path"]
        document = json.loads(path.read_text())
        entry["file_sha256"] = _sha(path)
        entry["record_sha256"] = document["record_sha256"]
    manifest["rights_registry_sha256"] = _sha(
        fixture.root / "governance/source_rights_registry.json"
    )
    manifest["rights_signers_sha256"] = _sha(
        fixture.root / "governance/rights_signers.json"
    )
    rights = json.loads(
        (fixture.root / "governance/source_rights_registry.json").read_text()
    )["sources"][0]
    manifest["rights_snapshot"] = [
        {
            "source_id": rights["source_id"],
            "decision_id": rights["decision_id"],
            "decision_artifact_sha256": rights["decision_artifact_sha256"],
            "signer_id": rights["signer_id"],
            "independence_group": rights["independence_group"],
            "authority_class": rights["authority_class"],
        }
    ]
    _write_json(fixture.manifest, canonical.seal_record(manifest))
    (fixture.root / "canonical/release.sig").write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _write_package(fixture: Fixture, package: dict[str, Any]) -> None:
    _write_json(fixture.package, package)
    _resign_release(fixture)


def _validate(fixture: Fixture) -> dict[str, Any]:
    return foundry.validate_foundry_release(
        manifest_path=fixture.manifest,
        package_path=fixture.package,
        root=fixture.root,
        profile_path=fixture.profile,
    )


def test_real_reference_is_metadata_only_rights_refusal() -> None:
    result = foundry.reference_status()
    assert result["status"] == "refused_contract_only"
    assert result["reason"] == "exact_signed_rights_decision_absent"
    assert result["public_value_artifact_allowed"] is False
    assert result["rights_authorized"] is False
    assert result["frame_contract_buildable"] is False
    assert result["publication_release_eligible"] is False
    assert result["capability_ceiling"] == "contract_only_l0"
    assert result["source_label_frames_emitted"] == 0
    assert result["crosswalks_emitted"] == 0
    assert result["universe_releases_emitted"] == 0
    assert result["dependency_observations_emitted"] == 0
    assert result["binary_edges_emitted"] == 0
    assert result["legal_correctness_claimed"] is False


def test_valid_signed_synthetic_release_composes_existing_machinery(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    result = _validate(fixture)
    assert result["status"] == "conformant_source_frame_entity_foundry_package"
    assert result["joint_cell_count"] == 6
    assert result["source_label_count"] == 7
    assert result["row_tuple_count"] == 2
    assert result["profile_sha256"] == _sha(fixture.profile)
    assert result["manifest_sha256"] == _sha(fixture.manifest)
    assert result["package_sha256"] == _sha(fixture.package)
    assert result["release_id"] == json.loads(fixture.manifest.read_text())["release_id"]
    assert result["package_id"] == json.loads(fixture.package.read_text())["package_id"]
    assert result["unresolved_label_count"] == 1
    assert result["universe_release_count"] == 3
    assert result["binary_edges_emitted"] == 0
    assert result["claim_boundary"] == (
        "signed_synthetic_structural_conformance_not_real_dependency"
    )
    package = json.loads(fixture.package.read_text())
    pairs = {
        tuple(
            next(role for role in row["roles"] if role["slot"] == slot)[
                "provider_value"
            ]
            for slot in ("country", "commodity")
        )
        for row in package["dependency_bundle"]["observations"]
    }
    assert pairs == {("Alpha", "X"), ("Beta", "Y")}
    assert ("Alpha", "Y") not in pairs
    assert ("Beta", "X") not in pairs


def test_manifest_capture_refuses_valid_a_b_a_validation_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_fixture(tmp_path)
    assert _validate(fixture)["joint_cell_count"] == 6
    signature = fixture.root / "canonical/release.sig"
    package_evidence = fixture.objects["evd:fixture.foundry.package"]
    watched = [fixture.package, package_evidence, fixture.manifest, signature]
    version_a = {path: path.read_bytes() for path in watched}
    package = json.loads(fixture.package.read_text())
    package["package_id"] = "foundry:fixture.unloaded.002"
    _write_package(fixture, package)
    version_b = {path: path.read_bytes() for path in watched}
    for path, payload in version_a.items():
        path.write_bytes(payload)
    original = foundry.canonical_objects.load_validated_release

    def validate_version_b(*args: Any, **kwargs: Any) -> Any:
        for path, payload in version_b.items():
            path.write_bytes(payload)
        try:
            return original(*args, **kwargs)
        finally:
            for path, payload in version_a.items():
                path.write_bytes(payload)

    monkeypatch.setattr(
        foundry.canonical_objects, "load_validated_release", validate_version_b
    )
    with pytest.raises(foundry.SourceFrameEntityFoundryError) as exc:
        _validate(fixture)
    assert exc.value.code == "release_manifest_validated_content_mismatch"


def test_status_refuses_expired_rights_at_explicit_as_of(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2027-08-10"),
    )
    assert result["status"] == "refused_contract_only"
    assert result["reason"] == "rights_decision_expired"
    assert result["rights_authorized"] is False
    assert result["frame_contract_buildable"] is True
    assert result["public_value_artifact_allowed"] is False


def test_status_refuses_future_rights_decision_and_registries(
    tmp_path: Path,
) -> None:
    decision_root = tmp_path / "decision"
    decision_root.mkdir()
    fixture = _build_fixture(decision_root)
    rights_path = fixture.root / "governance/source_rights_registry.json"
    source = json.loads(rights_path.read_text())["sources"][0]
    source["reviewed_on"] = "2026-12-01"
    source["review_due"] = "2027-12-01"
    _write_rights(fixture, fixture.root, source)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2026-08-09"),
    )
    assert result["reason"] == "rights_decision_not_yet_effective"
    assert result["rights_authorized"] is False

    rights_registry_root = tmp_path / "rights-registry"
    rights_registry_root.mkdir()
    fixture = _build_fixture(rights_registry_root)
    rights_path = fixture.root / "governance/source_rights_registry.json"
    registry = json.loads(rights_path.read_text())
    registry["effective"] = "2026-12-01"
    _write_json(rights_path, registry)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2026-08-09"),
    )
    assert result["reason"] == "rights_registry_not_yet_effective"
    assert result["rights_authorized"] is False

    signers_registry_root = tmp_path / "signers-registry"
    signers_registry_root.mkdir()
    fixture = _build_fixture(signers_registry_root)
    signers_path = fixture.root / "governance/rights_signers.json"
    registry = json.loads(signers_path.read_text())
    registry["effective"] = "2026-12-01"
    _write_json(signers_path, registry)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2026-08-09"),
    )
    assert result["reason"] == "rights_registry_not_yet_effective"
    assert result["rights_authorized"] is False


def test_status_refuses_revoked_signer_at_explicit_as_of(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    signers_path = fixture.root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text())
    signers["signers"][0]["revoked_on"] = "2026-08-10"
    _write_json(signers_path, signers)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2026-08-10"),
    )
    assert result["status"] == "refused_contract_only"
    assert result["reason"] == "rights_signer_revoked_or_inactive"
    assert result["rights_authorized"] is False
    assert result["public_value_artifact_allowed"] is False


def test_approved_rights_do_not_make_metadata_only_contract_buildable(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path)
    contract = json.loads(fixture.contract.read_text())
    contract["status"] = "rights_blocked_contract_only"
    contract["evidence_class"] = "contract_only"
    contract["scope"]["source_labels_status"] = (
        "withheld_pending_exact_signed_rights_decision"
    )
    for slot in contract["scope"]["slots"]:
        slot["provider_values"] = None
    contract["scope"]["row_tuple_frame"].update(
        status="withheld_rights_blocked", record_sha256=None, tuples=None
    )
    _write_json(fixture.contract, contract)
    profile = json.loads(fixture.profile.read_text())
    binding = next(
        row
        for row in profile["bound_files"]
        if row["kind"] == "reference_source_contract"
    )
    binding["sha256"] = _sha(fixture.contract)
    _write_json(fixture.profile, profile)
    result = foundry.reference_status(
        root=fixture.root,
        profile_path=fixture.profile,
        as_of=date.fromisoformat("2026-08-09"),
    )
    assert result["rights_authorized"] is True
    assert result["frame_contract_buildable"] is False
    assert result["publication_release_eligible"] is False
    assert result["public_value_artifact_allowed"] is False
    assert result["reason"] == "source_frame_contract_not_buildable"


def _omitted_frame_member(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    country_frame = next(row for row in bundle["frames"] if row["slot"] == "country")
    country_frame["provider_values"].pop()
    country_frame["member_count"] = 1
    _reseal(country_frame)
    country_crosswalk = next(row for row in bundle["crosswalks"] if row["slot"] == "country")
    country_crosswalk["frame_record_sha256"] = country_frame["record_sha256"]
    country_crosswalk["entries"].pop()
    country_crosswalk["entry_count"] = 1
    country_crosswalk["resolution_counts"]["unmatched"] = 0
    _reseal(country_crosswalk)
    bundle["observations"] = [
        row
        for row in bundle["observations"]
        if next(role for role in row["roles"] if role["slot"] == "country")[
            "provider_value"
        ]
        != "Beta"
    ]
    _reframe(bundle)
    package["normalizations"][0]["entries"].pop()
    package["universe_bindings"][0].update(source_label_count=1, unmatched=0)
    partition = Counter(row["value_status"] for row in bundle["observations"])
    package["coverage"].update(
        row_tuple_count=1,
        joint_cell_count=3,
        value_partition={status: partition[status] for status in foundry._VALUE_STATUSES},
    )
    _write_package(fixture, package)


def _coordinated_shrink(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    package["source_contract_sha256"] = "f" * 64
    _write_package(fixture, package)


def _unregistered_convergence(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    crosswalk = next(row for row in bundle["crosswalks"] if row["slot"] == "country")
    entry = crosswalk["entries"][1]
    entry.update(
        resolution_status="matched",
        canonical_entity_id="ent:country.alpha",
        evidence_ids=["evd:fixture.foundry.source"],
        reviewed_by=["person:foundry.fixture.reviewer"],
        limitation_codes=["alias_candidate"],
    )
    crosswalk["resolution_counts"].update(matched=2, unmatched=0)
    _reseal(crosswalk)
    for row in bundle["observations"]:
        role = next(role for role in row["roles"] if role["slot"] == "country")
        if role["provider_value"] == "Beta":
            role.update(resolution_status="matched", canonical_entity_id="ent:country.alpha")
    _reframe(bundle)
    package["universe_bindings"][0].update(matched=2, unmatched=0)
    _write_package(fixture, package)


def _raw_label_rewrite(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    frame = next(row for row in bundle["frames"] if row["slot"] == "country")
    frame["provider_values"][0] = "ALPHA"
    _reseal(frame)
    crosswalk = next(row for row in bundle["crosswalks"] if row["slot"] == "country")
    crosswalk["frame_record_sha256"] = frame["record_sha256"]
    crosswalk["entries"][0]["provider_value"] = "ALPHA"
    _reseal(crosswalk)
    for row in bundle["observations"]:
        role = next(role for role in row["roles"] if role["slot"] == "country")
        if role["provider_value"] == "Alpha":
            role["provider_value"] = "ALPHA"
    _reframe(bundle)
    normalization = next(row for row in package["normalizations"] if row["slot"] == "country")
    normalization["frame_id"] = frame["frame_id"]
    normalization["entries"][0].update(provider_value="ALPHA", normalized_value="alpha")
    _write_package(fixture, package)


def _normalization_collision(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    normalization = next(row for row in package["normalizations"] if row["slot"] == "country")
    normalization["entries"][1]["normalized_value"] = normalization["entries"][0][
        "normalized_value"
    ]
    _write_package(fixture, package)


def _guessed_ambiguous(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    crosswalk = next(
        row for row in package["dependency_bundle"]["crosswalks"] if row["slot"] == "country"
    )
    crosswalk["entries"][1].update(
        resolution_status="matched", canonical_entity_id="ent:country.alpha"
    )
    crosswalk["resolution_counts"].update(matched=2, unmatched=0)
    _reseal(crosswalk)
    _write_package(fixture, package)


def _unmatched_row_dropped(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    removed = bundle["observations"].pop()
    duplicate = copy.deepcopy(bundle["observations"][0])
    duplicate["observation_id"] = removed["observation_id"]
    duplicate["coverage"]["frame_member_id"] = removed["coverage"]["frame_member_id"]
    bundle["observations"].append(duplicate)
    _reframe(bundle)
    _write_package(fixture, package)


def _invented_cross_pair(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    country_crosswalk = next(
        row for row in bundle["crosswalks"] if row["slot"] == "country"
    )
    alpha = country_crosswalk["entries"][0]
    row = bundle["observations"][3]
    country_role = next(role for role in row["roles"] if role["slot"] == "country")
    country_role.update(
        provider_value=alpha["provider_value"],
        crosswalk_entry_id=alpha["entry_id"],
        resolution_status=alpha["resolution_status"],
        canonical_entity_id=alpha["canonical_entity_id"],
    )
    _reframe(bundle)
    _write_package(fixture, package)


def _registered_row_tuple_omitted(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    bundle["observations"] = bundle["observations"][:3]
    _reframe(bundle)
    partition = Counter(row["value_status"] for row in bundle["observations"])
    package["coverage"].update(
        row_tuple_count=1,
        joint_cell_count=3,
        value_partition={status: partition[status] for status in foundry._VALUE_STATUSES},
    )
    _write_package(fixture, package)


def _row_tuple_frame_digest_substitution(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    package["row_tuple_frame_sha256"] = "b" * 64
    _write_package(fixture, package)


def _universe_record_digest_substitution(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    package["universe_bindings"][0]["universe_record_sha256"] = "b" * 64
    _write_package(fixture, package)


def _extra_unbound_release_entity(fixture: Fixture) -> None:
    direct_path = fixture.root / "methods/direct.py"
    entity = _entity(
        "ent:country.unbound",
        "country",
        "Unbound country",
        _method("method:fixture.foundry.direct", direct_path),
    )
    path = fixture.root / "canonical/ent__country.unbound.json"
    _write_json(path, entity)
    fixture.objects[entity["entity_id"]] = path
    package = json.loads(fixture.package.read_text())
    package["dependency_bundle"]["known_entity_ids"].append(entity["entity_id"])
    _write_package(fixture, package)
    manifest = json.loads(fixture.manifest.read_text())
    manifest["objects"].append(
        {
            "object_type": "entity",
            "object_id": entity["entity_id"],
            "path": str(path.relative_to(fixture.root)),
            "file_sha256": entity["record_sha256"],
            "record_sha256": entity["record_sha256"],
        }
    )
    manifest["counts"]["entity"] += 1
    _write_json(fixture.manifest, manifest)
    _resign_release(fixture, rebind_package=False)


def _blank_to_zero(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    row = bundle["observations"][2]
    row["value_status"] = "observed_zero"
    _reframe(bundle)
    package["coverage"]["value_partition"] = copy.deepcopy(
        bundle["observations"][0]["coverage"]["value_partition"]
    )
    _write_package(fixture, package)


def _hidden_value_under_blank(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    bundle["observations"][2]["measure"] = {
        "value": 7,
        "unit": "thousand_metric_tonnes",
        "scale_factor": 1000,
        "denominator": "exact synthetic joint source cell",
    }
    _reframe(bundle)
    _write_package(fixture, package)


def _zero_labelled_positive(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    bundle["observations"][1]["measure"]["value"] = 7
    _reframe(bundle)
    _write_package(fixture, package)


def _positive_only(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    bundle["observations"] = [bundle["observations"][0]]
    _reframe(bundle)
    package["coverage"] = {
        "row_tuple_count": 1,
        "dock_column_count": 1,
        "joint_cell_count": 1,
        "value_partition": {
            status: int(status == "observed_positive") for status in foundry._VALUE_STATUSES
        },
    }
    _write_package(fixture, package)


def _source_hash_drift(fixture: Fixture) -> None:
    path = fixture.objects["evd:fixture.foundry.source"]
    evidence = json.loads(path.read_text())
    evidence["content_sha256"] = "b" * 64
    _write_json(path, canonical.seal_record(evidence))
    _resign_release(fixture, rebind_package=False)


def _parser_hash_drift(fixture: Fixture) -> None:
    path = fixture.root / "src/dependency_observation.py"
    path.write_text(path.read_text() + "\n# drift\n", encoding="utf-8")


def _locator(fixture: Fixture, field: str, value: object) -> None:
    package = json.loads(fixture.package.read_text())
    package["dependency_bundle"]["observations"][0]["source"]["locator"][field] = value
    _reseal(package["dependency_bundle"]["observations"][0])
    _write_package(fixture, package)


def _wrong_page(fixture: Fixture) -> None:
    _locator(fixture, "page", 11)


def _wrong_table(fixture: Fixture) -> None:
    _locator(fixture, "table_id", "fixture-2.1.7")


def _wrong_column(fixture: Fixture) -> None:
    _locator(fixture, "column", "P9")


def _loaded(fixture: Fixture) -> None:
    package = json.loads(fixture.package.read_text())
    package["dependency_bundle"]["observations"][0]["flow_semantics_id"] = (
        "flow:overseas_cargo_loaded_at_india_major_port_country_role_unresolved"
    )
    _reseal(package["dependency_bundle"]["observations"][0])
    _write_package(fixture, package)


def _rights_missing(fixture: Fixture) -> None:
    registry = json.loads(
        (fixture.root / "governance/source_rights_registry.json").read_text()
    )
    registry["sources"] = []
    _write_json(fixture.root / "governance/source_rights_registry.json", registry)


def _rights_expired(fixture: Fixture) -> None:
    manifest = json.loads(fixture.manifest.read_text())
    manifest["generated_at"] = "2027-08-10T00:00:00Z"
    _write_json(fixture.manifest, canonical.seal_record(manifest))
    (fixture.root / "canonical/release.sig").write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _rights_revoked(fixture: Fixture) -> None:
    signers_path = fixture.root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text())
    signers["signers"][0]["revoked_on"] = "2026-08-10"
    _write_json(signers_path, signers)
    package = json.loads(fixture.package.read_text())
    for row in package["dependency_bundle"]["observations"]:
        row["compiled_at"] = "2026-08-10T00:00:00Z"
        row["source"]["rights_signers_sha256"] = _sha(signers_path)
    _reframe(package["dependency_bundle"])
    _write_package(fixture, package)


def _rights_wrong_use(fixture: Fixture) -> None:
    registry_path = fixture.root / "governance/source_rights_registry.json"
    source = json.loads(registry_path.read_text())["sources"][0]
    source["permitted_uses"] = ["cite_metadata", "publish_derived_value"]
    _write_rights(fixture, fixture.root, source)
    _resign_release(fixture, rebind_package=False)


def _hidden_binary_edge(fixture: Fixture) -> None:
    method_path = fixture.root / "methods/edge.py"
    method = _method("method:fixture.foundry.edge", method_path)
    edge = canonical.seal_record(
        {
            "object_type": "exposure_edge",
            "schema_version": "1.0.0",
            "edge_id": "edg:fixture.foundry.hidden",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_entity_id": "ent:country.alpha",
            "target_entity_id": "ent:commodity.x",
            "edge_type": "import_dependence",
            "exposure_direction": "inbound_to_india",
            "quantification_status": "unknown",
            "magnitude": None,
            "derivation_type": "calculated",
            "effective_start": "2026-08-09",
            "effective_end": None,
            "observed_at": "2026-08-09T10:00:00Z",
            "coverage_basis": {
                "universe_release_id": "unv:fixture.foundry.commodity.1",
                "covered_entity_id": "ent:commodity.x",
                "member_status": "included",
            },
            "evidence_ids": ["evd:fixture.foundry.source"],
            "method": method,
            "confidence": {
                "status": "not_estimated",
                "meaning": "No estimate is licensed.",
                "lower": None,
                "upper": None,
                "category": None,
            },
            "limitation_codes": ["hidden_binary_projection", "magnitude_unknown"],
            "provenance": _provenance(["evd:fixture.foundry.source"], method),
        }
    )
    path = fixture.root / "canonical/edg__fixture.foundry.hidden.json"
    _write_json(path, edge)
    fixture.objects[edge["edge_id"]] = path
    manifest = json.loads(fixture.manifest.read_text())
    manifest["objects"].append(
        {
            "object_type": "exposure_edge",
            "object_id": edge["edge_id"],
            "path": str(path.relative_to(fixture.root)),
            "file_sha256": _sha(path),
            "record_sha256": edge["record_sha256"],
        }
    )
    manifest["counts"]["exposure_edge"] = 1
    _write_json(fixture.manifest, canonical.seal_record(manifest))
    (fixture.root / "canonical/release.sig").write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _test_surface_drift(fixture: Fixture) -> None:
    path = fixture.root / "tests/test_source_frame_entity_foundry.py"
    path.write_text(path.read_text() + "\n# unbound drift\n", encoding="utf-8")


def _alternate_profile_substitution(fixture: Fixture) -> None:
    contract = json.loads(fixture.contract.read_text())
    contract["scope"]["expected_detail_rows"] = 1
    contract["scope"]["expected_joint_cells"] = 3
    contract["scope"]["slots"][0]["provider_values"] = ["Alpha"]
    alternate_contract = fixture.root / "foundry/substitute-contract.json"
    _write_json(alternate_contract, contract)
    profile = json.loads(fixture.profile.read_text())
    binding = next(
        row
        for row in profile["bound_files"]
        if row["kind"] == "reference_source_contract"
    )
    binding["path"] = str(alternate_contract.relative_to(fixture.root))
    binding["sha256"] = _sha(alternate_contract)
    alternate_profile = fixture.root / "foundry/alternate-profile.json"
    _write_json(alternate_profile, profile)
    fixture.profile = alternate_profile


MUTATIONS: dict[str, Callable[[Fixture], None]] = {
    "omitted_frame_member": _omitted_frame_member,
    "coordinated_denominator_shrink": _coordinated_shrink,
    "unregistered_many_to_one_convergence": _unregistered_convergence,
    "raw_label_rewrite": _raw_label_rewrite,
    "normalization_collision": _normalization_collision,
    "guessed_ambiguous_mapping": _guessed_ambiguous,
    "unmatched_row_dropped": _unmatched_row_dropped,
    "invented_country_commodity_cross_pair": _invented_cross_pair,
    "registered_row_tuple_omitted": _registered_row_tuple_omitted,
    "row_tuple_frame_digest_substitution": _row_tuple_frame_digest_substitution,
    "universe_record_digest_substitution": _universe_record_digest_substitution,
    "extra_unbound_release_entity": _extra_unbound_release_entity,
    "blank_to_zero": _blank_to_zero,
    "hidden_value_under_blank": _hidden_value_under_blank,
    "zero_labelled_positive": _zero_labelled_positive,
    "positive_only_completeness_claim": _positive_only,
    "source_hash_drift": _source_hash_drift,
    "parser_hash_drift": _parser_hash_drift,
    "wrong_page_provenance": _wrong_page,
    "wrong_table_provenance": _wrong_table,
    "wrong_column_provenance": _wrong_column,
    "loaded_cargo_inclusion": _loaded,
    "rights_missing": _rights_missing,
    "rights_expired": _rights_expired,
    "rights_revoked": _rights_revoked,
    "rights_wrong_use": _rights_wrong_use,
    "hidden_binary_decomposition": _hidden_binary_edge,
    "test_or_contract_surface_not_bound": _test_surface_drift,
    "alternate_profile_source_contract_substitution": _alternate_profile_substitution,
}


def _registered_cases() -> dict[str, str | None]:
    document = json.loads((ROOT / FOUNDRY_EXTENSION / "adversarial-cases.json").read_text())
    return {row["case_id"]: row["expected_reason"] for row in document["cases"]}


@pytest.mark.parametrize("case_id", sorted(MUTATIONS))
def test_registered_hostile_cases_refuse_exact_reason(tmp_path: Path, case_id: str) -> None:
    registered = _registered_cases()
    assert set(registered) == {"valid_signed_synthetic_foundry_release", *MUTATIONS}
    fixture = _build_fixture(tmp_path)
    MUTATIONS[case_id](fixture)
    with pytest.raises(foundry.SourceFrameEntityFoundryError) as exc_info:
        _validate(fixture)
    assert exc_info.value.code == registered[case_id]


def test_reviewed_many_to_one_alias_convergence_preserves_raw_denominator(
    tmp_path: Path,
) -> None:
    fixture = _build_fixture(tmp_path)
    package = json.loads(fixture.package.read_text())
    bundle = package["dependency_bundle"]
    crosswalk = next(row for row in bundle["crosswalks"] if row["slot"] == "country")
    entry = crosswalk["entries"][1]
    entry.update(
        resolution_status="matched",
        canonical_entity_id="ent:country.alpha",
        evidence_ids=["evd:fixture.foundry.source"],
        reviewed_by=["person:foundry.fixture.reviewer"],
        limitation_codes=["reviewed_alias"],
    )
    crosswalk["resolution_counts"].update(matched=2, unmatched=0)
    _reseal(crosswalk)
    for row in bundle["observations"]:
        role = next(role for role in row["roles"] if role["slot"] == "country")
        if role["provider_value"] == "Beta":
            role.update(resolution_status="matched", canonical_entity_id="ent:country.alpha")
    _reframe(bundle)
    package["canonical_convergences"] = [
        {
            "slot": "country",
            "canonical_entity_id": "ent:country.alpha",
            "provider_values": ["Alpha", "Beta"],
            "evidence_ids": ["evd:fixture.foundry.source"],
            "reviewed_by": ["person:foundry.fixture.reviewer"],
            "limitation_codes": ["many_to_one_alias_convergence"],
        }
    ]
    package["universe_bindings"][0].update(matched=2, unmatched=0)
    _write_package(fixture, package)
    result = _validate(fixture)
    assert result["source_label_count"] == 7
    assert result["canonical_entity_count"] == 6
    assert result["unresolved_label_count"] == 0


def test_package_file_must_be_bound_into_the_exact_signed_release(tmp_path: Path) -> None:
    fixture = _build_fixture(tmp_path)
    package = json.loads(fixture.package.read_text())
    package["limitation_codes"].append("changed_after_release")
    _write_json(fixture.package, package)
    with pytest.raises(
        foundry.SourceFrameEntityFoundryError,
        match="canonical_release_invalid",
    ):
        _validate(fixture)
