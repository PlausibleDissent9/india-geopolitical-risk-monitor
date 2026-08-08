"""Adversarial tests for the IGRM canonical-object and release boundary."""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(method_id: str, implementation_sha256: str) -> dict[str, object]:
    return {
        "method_id": method_id,
        "version": "1.0.0",
        "implementation_sha256": implementation_sha256,
        "run_id": "run:test.001",
    }


def _lifecycle() -> dict[str, object]:
    return {
        "revision": 1,
        "state": "active",
        "supersedes_id": None,
        "superseded_by": None,
        "correction_id": None,
    }


def _provenance(
    evidence_ids: list[str], *, method: dict[str, object], reviewed_by: list[str] | None = None
) -> dict[str, object]:
    return {
        "created_at": "2026-08-08T12:00:00Z",
        "created_by": "system:test.builder",
        "reviewed_by": reviewed_by or [],
        "adjudication_status": "single_reviewed" if reviewed_by else "unreviewed",
        "source_ids": ["test_source"],
        "evidence_ids": evidence_ids,
        "method": method,
    }


def _install_signed_rights(root: Path) -> Ed25519PrivateKey:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers = {
        "schema_version": "1.0.0",
        "effective": "2026-08-08",
        "default_policy": "deny",
        "signers": [
            {
                "signer_id": "signer:test.rights",
                "name": "Test rights signer",
                "role": "test-only rights reviewer",
                "public_key_ed25519_base64": base64.b64encode(public_key).decode(),
                "effective": "2026-08-08",
                "revoked_on": None,
            }
        ],
    }
    _write_json(root / "governance" / "rights_signers.json", signers)
    source: dict[str, Any] = {
        "source_id": "test_source",
        "name": "Synthetic official source",
        "provider": "Synthetic provider",
        "role": "official_test_evidence",
        "authority_class": "official_primary",
        "independence_group": "synthetic_provider",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "test-decision-2026-08-08",
        "decision_owner": "Test owner",
        "signer_id": "signer:test.rights",
        "decision_artifact_path": "governance/rights_decisions/test_source.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/test_source.sig",
        "reviewed_on": "2026-08-08",
        "review_due": "2027-08-08",
        "access_url": "https://example.test/source",
        "terms_url": "https://example.test/terms",
        "access_basis": "synthetic_test_authorization",
        "geographic_coverage": "Synthetic test frame",
        "historical_coverage": "One synthetic day",
        "retrieval_target": "One deterministic fixture",
        "outage_fallback": "Fail closed",
        "cost_owner": "Test owner",
        "reproducibility_tier": "open_synthetic_fixture",
        "max_current_age_days": 30,
        "permitted_uses": ["cite_metadata"],
        "notes": "Test-only source; no external rights conclusion.",
    }
    decision = {
        "schema_version": "1.0.0",
        "source_id": source["source_id"],
        "name": source["name"],
        "provider": source["provider"],
        "role": source["role"],
        "authority_class": source["authority_class"],
        "independence_group": source["independence_group"],
        "decision_id": source["decision_id"],
        "decision_owner": source["decision_owner"],
        "signer_id": source["signer_id"],
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "access_url": source["access_url"],
        "terms_url": source["terms_url"],
        "access_basis": source["access_basis"],
        "lineage_policy": source["lineage_policy"],
        "max_current_age_days": source["max_current_age_days"],
        "permitted_uses": source["permitted_uses"],
        "statement": "Synthetic authorization for one metadata-only test release.",
    }
    decision_path = root / source["decision_artifact_path"]
    _write_json(decision_path, decision)
    signature_path = root / source["decision_signature_path"]
    signature_path.write_bytes(private_key.sign(decision_path.read_bytes()))
    source["decision_artifact_sha256"] = _sha(decision_path)
    _write_json(
        root / "governance" / "source_rights_registry.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    return private_key


def _install_release_signer(root: Path) -> Ed25519PrivateKey:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    _write_json(
        root / "governance" / "release_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "signer:test.release",
                    "name": "Test release signer",
                    "role": "canonical_release_signer",
                    "public_key_ed25519_base64": base64.b64encode(public_key).decode(),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                }
            ],
        },
    )
    return private_key


def _install_methods(root: Path, implementations: dict[str, Path]) -> dict[str, dict[str, object]]:
    allowed = {
        "method:test.direct": ["evidence_item", "entity"],
        "rule:test.event": ["event"],
        "rule:test.commodity_universe": ["universe_release"],
        "method:test.exposure": ["exposure_edge"],
    }
    rows = []
    methods: dict[str, dict[str, object]] = {}
    for method_id, path in implementations.items():
        digest = _sha(path)
        rows.append(
            {
                "method_id": method_id,
                "version": "1.0.0",
                "implementation_path": str(path.relative_to(root)),
                "implementation_sha256": digest,
                "allowed_object_types": allowed[method_id],
                "effective": "2026-08-08",
                "superseded_on": None,
            }
        )
        methods[method_id] = _method(method_id, digest)
    _write_json(
        root / "governance" / "canonical_method_registry.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "methods": rows,
        },
    )
    return methods


def _entity(
    entity_id: str,
    entity_type: str,
    name: str,
    method: dict[str, object],
) -> dict[str, object]:
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
                    "scheme": "fixture",
                    "value": entity_id.split(":", 1)[1],
                    "effective_start": None,
                    "effective_end": None,
                    "evidence_ids": ["evd:test.official.001"],
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
            "identity_status": "authoritative",
            "provenance": _provenance(
                ["evd:test.official.001"], method=method
            ),
        }
    )


def _fixture(tmp_path: Path) -> dict[str, Any]:
    root = tmp_path / "root"
    shutil.copytree(ROOT / "schemas", root / "schemas")
    (root / "governance").mkdir(parents=True)
    shutil.copy2(
        ROOT / "governance" / "canonical_schema_registry.json",
        root / "governance" / "canonical_schema_registry.json",
    )
    rights_private_key = _install_signed_rights(root)
    rule = root / "rules" / "commodity_universe.py"
    rule.parent.mkdir(parents=True)
    rule.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    documentation = root / "rules" / "commodity_universe.md"
    documentation.write_text("# Synthetic commodity universe rule\n", encoding="utf-8")
    direct_method_file = root / "methods" / "direct.py"
    direct_method_file.parent.mkdir(parents=True)
    direct_method_file.write_text("def apply(value):\n    return value\n", encoding="utf-8")
    event_method_file = root / "methods" / "event.py"
    event_method_file.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    edge_method_file = root / "methods" / "exposure.py"
    edge_method_file.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    methods = _install_methods(
        root,
        {
            "method:test.direct": direct_method_file,
            "rule:test.event": event_method_file,
            "rule:test.commodity_universe": rule,
            "method:test.exposure": edge_method_file,
        },
    )
    release_private_key = _install_release_signer(root)

    evidence = canonical.seal_record(
        {
            "object_type": "evidence_item",
            "schema_version": "1.0.0",
            "evidence_id": "evd:test.official.001",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_id": "test_source",
            "source_record_id": "official-001",
            "retrieval_id": "ret:test.001",
            "evidence_type": "official_document",
            "title": "Synthetic official action",
            "publisher_entity_id": None,
            "authors": [],
            "language": "en",
            "published_at": "2026-08-08T09:00:00Z",
            "observed_at": "2026-08-08T09:00:00Z",
            "effective_start": "2026-08-08T09:00:00Z",
            "effective_end": None,
            "retrieved_at": "2026-08-08T10:00:00Z",
            "geography_entity_ids": ["ent:country.iran"],
            "public_url": "https://example.test/source/official-001",
            "artifact_path": None,
            "content_sha256": hashlib.sha256(b"synthetic official bytes").hexdigest(),
            "artifact_sha256": None,
            "content_availability": "hash_metadata_only",
            "rights_use": "cite_metadata",
            "rights_decision_id": "test-decision-2026-08-08",
            "privacy_class": "public",
            "verification_status": "official_record",
            "extraction_method": "provider_api",
            "provenance": _provenance([], method=methods["method:test.direct"]),
        }
    )
    entities = [
        _entity("ent:country.india", "country", "India", methods["method:test.direct"]),
        _entity("ent:country.iran", "country", "Iran", methods["method:test.direct"]),
        _entity(
            "ent:commodity.crude_oil",
            "commodity",
            "Crude oil",
            methods["method:test.direct"],
        ),
    ]
    event = canonical.seal_record(
        {
            "object_type": "event",
            "schema_version": "1.0.0",
            "event_id": "evt:test.policy.001",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "canonical_label": "Synthetic policy action",
            "event_class": "policy_action",
            "secondary_classes": [],
            "record_status": "confirmed",
            "publication_phase": "final",
            "direction": "neutral",
            "starts_at": "2026-08-08T09:00:00Z",
            "ends_at": None,
            "temporal_precision": "hour",
            "first_known_at": "2026-08-08T10:00:00Z",
            "last_verified_at": "2026-08-08T11:00:00Z",
            "actor_entity_ids": ["ent:country.iran"],
            "target_entity_ids": [],
            "affected_entity_ids": ["ent:commodity.crude_oil"],
            "locations": [
                {
                    "entity_id": "ent:country.iran",
                    "role": "primary",
                    "precision": "country",
                    "evidence_ids": ["evd:test.official.001"],
                }
            ],
            "intensity": {
                "status": "not_estimated",
                "scheme": None,
                "value": None,
                "unit": None,
                "denominator": None,
                "uncertainty": {
                    "status": "not_estimated",
                    "meaning": "No event-intensity estimate is licensed.",
                    "lower": None,
                    "upper": None,
                    "category": None,
                },
            },
            "evidence_links": [
                {
                    "evidence_id": "evd:test.official.001",
                    "role": "official_confirmation",
                    "asserted_at": "2026-08-08T09:00:00Z",
                }
            ],
            "coding": {
                "rule_id": "rule:test.event",
                "rule_version": "1.0.0",
                "implementation_sha256": methods["rule:test.event"][
                    "implementation_sha256"
                ],
                "status": "human_coded",
                "coder_ids": ["person:test.coder"],
                "adjudicator_ids": [],
                "limitation_codes": [],
            },
            "provenance": _provenance(
                ["evd:test.official.001"],
                method=methods["rule:test.event"],
                reviewed_by=["person:test.coder"],
            ),
        }
    )
    universe_method = methods["rule:test.commodity_universe"]
    frame = canonical.seal_record(
        {
            "object_type": "universe_frame",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "universe_id": "universe:test.commodities",
            "entity_type": "commodity",
            "reference_date": "2026-08-08",
            "source_evidence_id": "evd:test.official.001",
            "source_version": "synthetic-v1",
            "extraction_query": "all rows in the one-row synthetic source frame",
            "extracted_at": "2026-08-08T11:30:00Z",
            "entity_ids": ["ent:commodity.crude_oil"],
        }
    )
    frame_path = root / "frames" / "commodity_frame.json"
    _write_json(frame_path, frame)
    universe = canonical.seal_record(
        {
            "object_type": "universe_release",
            "schema_version": "1.0.0",
            "universe_release_id": "unv:test.commodities.1",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "universe_id": "universe:test.commodities",
            "version": "1.0.0",
            "name": "Synthetic India commodity frame",
            "entity_type": "commodity",
            "reference_date": "2026-08-08",
            "denominator_definition": "Every commodity in the one-row synthetic frame.",
            "inclusion_rule": {
                "rule_id": "rule:test.commodity_universe",
                "version": "1.0.0",
                "implementation_path": "rules/commodity_universe.py",
                "implementation_sha256": _sha(rule),
                "documentation_path": "rules/commodity_universe.md",
            },
            "frame_artifact": {
                "path": "frames/commodity_frame.json",
                "sha256": _sha(frame_path),
                "format": "igrm_universe_frame_v1",
            },
            "source_evidence_ids": ["evd:test.official.001"],
            "members": [
                {
                    "entity_id": "ent:commodity.crude_oil",
                    "status": "included",
                    "reason_code": "reason:test.in_frame",
                    "assessed_on": "2026-08-08",
                }
            ],
            "counts": {
                "total_eligible": 1,
                "included": 1,
                "excluded": 0,
                "unmappable": 0,
                "stale": 0,
            },
            "provenance": _provenance(
                ["evd:test.official.001"], method=universe_method
            ),
        }
    )
    edge_method = methods["method:test.exposure"]
    edge = canonical.seal_record(
        {
            "object_type": "exposure_edge",
            "schema_version": "1.0.0",
            "edge_id": "edg:test.iran_crude.001",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_entity_id": "ent:country.iran",
            "target_entity_id": "ent:commodity.crude_oil",
            "edge_type": "import_dependence",
            "exposure_direction": "inbound_to_india",
            "quantification_status": "quantified",
            "magnitude": {
                "value": 12.5,
                "unit": "percent_of_import_volume",
                "denominator": "total India crude-oil import volume in the stated period",
                "period_start": "2026-01-01",
                "period_end": "2026-06-30",
                "currency": None,
                "price_basis": None,
                "uncertainty": {
                    "status": "interval",
                    "meaning": "Synthetic test interval.",
                    "lower": 10.0,
                    "upper": 15.0,
                    "category": None,
                },
            },
            "derivation_type": "calculated",
            "effective_start": "2026-06-30",
            "effective_end": None,
            "observed_at": "2026-08-08T10:00:00Z",
            "coverage_basis": {
                "universe_release_id": "unv:test.commodities.1",
                "covered_entity_id": "ent:commodity.crude_oil",
                "member_status": "included",
            },
            "evidence_ids": ["evd:test.official.001"],
            "method": edge_method,
            "confidence": {
                "status": "categorical",
                "meaning": "Synthetic evidence-confidence category, not a probability.",
                "lower": None,
                "upper": None,
                "category": "test_only",
            },
            "limitation_codes": [],
            "provenance": _provenance(
                ["evd:test.official.001"], method=edge_method
            ),
        }
    )
    documents = [evidence, *entities, event, universe, edge]
    paths: dict[str, Path] = {}
    entries = []
    for document in documents:
        object_type = document["object_type"]
        id_field = canonical._ID_FIELD[object_type]
        object_id = document[id_field]
        path = root / "canonical" / f"{object_id.replace(':', '__')}.json"
        _write_json(path, document)
        paths[object_id] = path
        entries.append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "path": str(path.relative_to(root)),
                "file_sha256": _sha(path),
                "record_sha256": document["record_sha256"],
            }
        )
    counts = Counter(document["object_type"] for document in documents)
    rights = json.loads(
        (root / "governance" / "source_rights_registry.json").read_text()
    )["sources"][0]
    manifest = canonical.seal_record(
        {
            "object_type": "canonical_release",
            "schema_version": "1.0.0",
            "release_id": "rel:test.2026-08-08",
            "record_sha256": "0" * 64,
            "generated_at": "2026-08-08T13:00:00Z",
            "effective_date": "2026-08-08",
            "schema_registry_sha256": _sha(
                root / "governance" / "canonical_schema_registry.json"
            ),
            "method_registry_sha256": _sha(
                root / "governance" / "canonical_method_registry.json"
            ),
            "rights_registry_sha256": _sha(
                root / "governance" / "source_rights_registry.json"
            ),
            "rights_signers_sha256": _sha(
                root / "governance" / "rights_signers.json"
            ),
            "release_signers_sha256": _sha(
                root / "governance" / "release_signers.json"
            ),
            "release_signer_id": "signer:test.release",
            "release_signature_path": "canonical/release.sig",
            "rights_snapshot": [
                {
                    "source_id": rights["source_id"],
                    "decision_id": rights["decision_id"],
                    "decision_artifact_sha256": rights[
                        "decision_artifact_sha256"
                    ],
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
    manifest_path = root / "canonical" / "release.json"
    _write_json(manifest_path, manifest)
    signature_path = root / "canonical" / "release.sig"
    signature_path.write_bytes(release_private_key.sign(manifest_path.read_bytes()))
    return {
        "root": root,
        "manifest": manifest_path,
        "objects": paths,
        "frame": frame_path,
        "release_signature": signature_path,
        "release_private_key": release_private_key,
        "rights_private_key": rights_private_key,
    }


def _validate(paths: dict[str, Any]) -> dict[str, object]:
    root = paths["root"]
    return canonical.validate_release(
        paths["manifest"],
        root=root,
        schema_registry_path=root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=root / "governance" / "source_rights_registry.json",
        rights_signers_path=root / "governance" / "rights_signers.json",
        method_registry_path=root / "governance" / "canonical_method_registry.json",
        release_signers_path=root / "governance" / "release_signers.json",
    )


def _refuses(paths: dict[str, Any], reason: str) -> None:
    with pytest.raises(canonical.CanonicalObjectError) as exc:
        _validate(paths)
    assert exc.value.code == reason


def _rewrite_object(
    paths: dict[str, Any], object_id: str, mutate: Callable[[dict[str, Any]], None]
) -> None:
    path = paths["objects"][object_id]
    document = json.loads(path.read_text())
    mutate(document)
    document = canonical.seal_record(document)
    _write_json(path, document)
    manifest = json.loads(paths["manifest"].read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == object_id)
    entry["file_sha256"] = _sha(path)
    entry["record_sha256"] = document["record_sha256"]
    _write_manifest(paths, manifest)


def _write_manifest(paths: dict[str, Any], manifest: dict[str, Any]) -> None:
    _write_json(paths["manifest"], canonical.seal_record(manifest))
    paths["release_signature"].write_bytes(
        paths["release_private_key"].sign(paths["manifest"].read_bytes())
    )


def _signed_decision_for(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "source_id": source["source_id"],
        "name": source["name"],
        "provider": source["provider"],
        "role": source["role"],
        "authority_class": source["authority_class"],
        "independence_group": source["independence_group"],
        "decision_id": source["decision_id"],
        "decision_owner": source["decision_owner"],
        "signer_id": source["signer_id"],
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "access_url": source["access_url"],
        "terms_url": source["terms_url"],
        "access_basis": source["access_basis"],
        "lineage_policy": source["lineage_policy"],
        "max_current_age_days": source["max_current_age_days"],
        "permitted_uses": source["permitted_uses"],
        "statement": "Synthetic authorization for one metadata-only test release.",
    }


def _rights_snapshot(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": source["source_id"],
            "decision_id": source["decision_id"],
            "decision_artifact_sha256": source["decision_artifact_sha256"],
            "signer_id": source["signer_id"],
            "independence_group": source["independence_group"],
            "authority_class": source["authority_class"],
        }
        for source in sorted(sources, key=lambda item: item["source_id"])
    ]


def _add_same_group_corroborator(paths: dict[str, Any]) -> str:
    root = paths["root"]
    rights_path = root / "governance" / "source_rights_registry.json"
    rights = json.loads(rights_path.read_text())
    source = json.loads(json.dumps(rights["sources"][0]))
    source.update(
        source_id="test_source_mirror",
        name="Synthetic mirror source",
        provider="Synthetic mirror operator",
        role="independent_test_reporting",
        authority_class="independent_reporting",
        independence_group="synthetic_provider",
        decision_id="test-decision-mirror-2026-08-08",
        decision_artifact_path="governance/rights_decisions/test_source_mirror.json",
        decision_artifact_sha256="0" * 64,
        decision_signature_path="governance/rights_decisions/test_source_mirror.sig",
        access_url="https://mirror.example.test/source",
        terms_url="https://mirror.example.test/terms",
    )
    decision_path = root / source["decision_artifact_path"]
    _write_json(decision_path, _signed_decision_for(source))
    signature_path = root / source["decision_signature_path"]
    signature_path.write_bytes(paths["rights_private_key"].sign(decision_path.read_bytes()))
    source["decision_artifact_sha256"] = _sha(decision_path)
    rights["sources"].append(source)
    _write_json(rights_path, rights)

    original_path = paths["objects"]["evd:test.official.001"]
    evidence = json.loads(original_path.read_text())
    evidence.update(
        evidence_id="evd:test.mirror.002",
        source_id="test_source_mirror",
        source_record_id="mirror-002",
        retrieval_id="ret:test.002",
        evidence_type="news_article",
        title="Synthetic mirror report",
        content_sha256=hashlib.sha256(b"synthetic mirror bytes").hexdigest(),
        rights_decision_id=source["decision_id"],
        verification_status="single_source",
    )
    evidence["provenance"]["source_ids"] = ["test_source_mirror"]
    evidence = canonical.seal_record(evidence)
    evidence_path = root / "canonical" / "evd__test.mirror.002.json"
    _write_json(evidence_path, evidence)
    paths["objects"][evidence["evidence_id"]] = evidence_path

    manifest = json.loads(paths["manifest"].read_text())
    manifest["objects"].append(
        {
            "object_type": "evidence_item",
            "object_id": evidence["evidence_id"],
            "path": str(evidence_path.relative_to(root)),
            "file_sha256": _sha(evidence_path),
            "record_sha256": evidence["record_sha256"],
        }
    )
    manifest["counts"]["evidence_item"] += 1
    manifest["rights_registry_sha256"] = _sha(rights_path)
    manifest["rights_snapshot"] = _rights_snapshot(rights["sources"])
    _write_manifest(paths, manifest)
    return cast(str, evidence["evidence_id"])


def test_complete_release_is_valid_without_emitting_measurement_values(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = _validate(paths)

    assert result == {
        "status": "valid",
        "release_id": "rel:test.2026-08-08",
        "record_sha256": json.loads(paths["manifest"].read_text())["record_sha256"],
        "object_count": 7,
        "counts": {
            "entity": 3,
            "event": 1,
            "evidence_item": 1,
            "exposure_edge": 1,
            "universe_release": 1,
        },
    }
    assert "12.5" not in json.dumps(result)


def test_schema_and_record_hashes_reject_extra_or_changed_content(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _rewrite_object(
        paths,
        "ent:country.india",
        lambda document: document.update(unregistered_claim="India is safe"),
    )
    _refuses(paths, "object_schema_invalid")

    paths = _fixture(tmp_path / "hash")
    document = json.loads(paths["objects"]["ent:country.india"].read_text())
    document["canonical_name"] = "Changed after sealing"
    _write_json(paths["objects"]["ent:country.india"], document)
    manifest = json.loads(paths["manifest"].read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == "ent:country.india")
    entry["file_sha256"] = _sha(paths["objects"]["ent:country.india"])
    _write_manifest(paths, manifest)
    _refuses(paths, "record_digest_mismatch")


def test_schema_registry_and_rule_implementation_are_byte_locked(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    schema = paths["root"] / "schemas" / "event.schema.json"
    schema.write_text(schema.read_text() + "\n")
    _refuses(paths, "schema_digest_mismatch")

    paths = _fixture(tmp_path / "rule")
    rule = paths["root"] / "rules" / "commodity_universe.py"
    rule.write_text("RULE_VERSION = 'changed'\n")
    _refuses(paths, "method_implementation_digest_mismatch")


def test_manifest_requires_exact_file_membership_hashes_and_counts(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["objects"]["evt:test.policy.001"].unlink()
    _refuses(paths, "release_object_missing")

    paths = _fixture(tmp_path / "count")
    manifest = json.loads(paths["manifest"].read_text())
    manifest["counts"]["event"] = 0
    _write_manifest(paths, manifest)
    _refuses(paths, "release_counts_mismatch")


def test_public_release_refuses_unapproved_or_mismatched_rights(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    rights_path = paths["root"] / "governance" / "source_rights_registry.json"
    rights = json.loads(rights_path.read_text())
    source = rights["sources"][0]
    source.update(
        decision_state="review_required",
        signer_id=None,
        decision_artifact_path=None,
        decision_artifact_sha256=None,
        decision_signature_path=None,
        reviewed_on=None,
        review_due=None,
        max_current_age_days=None,
        permitted_uses=[],
    )
    _write_json(rights_path, rights)
    _refuses(paths, "release_rights_registry_digest_mismatch")

    paths = _fixture(tmp_path / "decision")
    _rewrite_object(
        paths,
        "evd:test.official.001",
        lambda document: document.update(rights_decision_id="different-decision"),
    )
    _refuses(paths, "evidence_rights_decision_mismatch")


def test_release_signature_and_policy_snapshots_cannot_be_rewritten(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    paths["release_signature"].write_bytes(b"0" * 64)
    _refuses(paths, "release_signature_invalid")

    paths = _fixture(tmp_path / "manifest")
    manifest = json.loads(paths["manifest"].read_text())
    manifest["generated_at"] = "2026-08-08T13:01:00Z"
    _write_json(paths["manifest"], canonical.seal_record(manifest))
    _refuses(paths, "release_signature_invalid")

    paths = _fixture(tmp_path / "registry")
    rights_path = paths["root"] / "governance" / "source_rights_registry.json"
    rights_path.write_text(rights_path.read_text() + "\n")
    _refuses(paths, "release_rights_registry_digest_mismatch")


def test_release_and_evidence_temporal_privacy_boundaries_fail_closed(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    manifest = json.loads(paths["manifest"].read_text())
    manifest["effective_date"] = "2026-08-09"
    _write_manifest(paths, manifest)
    _refuses(paths, "release_effective_after_generation")

    paths = _fixture(tmp_path / "restricted")

    def expose_restricted_bytes(document: dict[str, Any]) -> None:
        document.update(
            privacy_class="restricted",
            content_availability="restricted",
            public_url=None,
            artifact_path="canonical/restricted.bin",
            artifact_sha256="e" * 64,
        )

    _rewrite_object(paths, "evd:test.official.001", expose_restricted_bytes)
    _refuses(paths, "restricted_evidence_bytes_forbidden")

    paths = _fixture(tmp_path / "published")
    _rewrite_object(
        paths,
        "evd:test.official.001",
        lambda document: document.update(published_at="2026-08-08T10:30:00Z"),
    )
    _refuses(paths, "evidence_published_after_retrieval")


def test_event_confirmation_needs_official_or_independent_sources(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def allegation_only(document: dict[str, Any]) -> None:
        document["evidence_links"][0]["role"] = "allegation"

    _rewrite_object(paths, "evt:test.policy.001", allegation_only)
    _refuses(paths, "event_confirmation_evidence_insufficient")


def test_official_confirmation_requires_official_evidence_and_source_class(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    def relabel_as_news(document: dict[str, Any]) -> None:
        document["evidence_type"] = "news_article"
        document["verification_status"] = "single_source"

    _rewrite_object(paths, "evd:test.official.001", relabel_as_news)
    _refuses(paths, "event_official_confirmation_ineligible")


def test_every_official_confirmation_link_must_be_eligible(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    mirror_id = _add_same_group_corroborator(paths)

    def mix_valid_and_invalid_official_links(document: dict[str, Any]) -> None:
        document["evidence_links"].append(
            {
                "evidence_id": mirror_id,
                "role": "official_confirmation",
                "asserted_at": "2026-08-08T09:15:00Z",
            }
        )
        document["provenance"]["evidence_ids"].append(mirror_id)
        document["provenance"]["source_ids"].append("test_source_mirror")

    _rewrite_object(
        paths, "evt:test.policy.001", mix_valid_and_invalid_official_links
    )
    _refuses(paths, "event_official_confirmation_ineligible")


def test_two_source_ids_in_one_independence_group_do_not_confirm_event(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    mirror_id = _add_same_group_corroborator(paths)

    def use_two_mirrors(document: dict[str, Any]) -> None:
        document["evidence_links"][0]["role"] = "corroborates"
        document["evidence_links"].append(
            {
                "evidence_id": mirror_id,
                "role": "corroborates",
                "asserted_at": "2026-08-08T09:15:00Z",
            }
        )
        document["provenance"]["evidence_ids"].append(mirror_id)
        document["provenance"]["source_ids"].append("test_source_mirror")

    _rewrite_object(paths, "evt:test.policy.001", use_two_mirrors)
    _refuses(paths, "event_confirmation_evidence_insufficient")


def test_event_coding_and_temporal_claims_fail_closed(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def fake_dual_coding(document: dict[str, Any]) -> None:
        document["coding"]["status"] = "dual_coded"

    _rewrite_object(paths, "evt:test.policy.001", fake_dual_coding)
    _refuses(paths, "event_dual_coding_invalid")

    paths = _fixture(tmp_path / "time")
    _rewrite_object(
        paths,
        "evt:test.policy.001",
        lambda document: document.update(ends_at="2026-08-08T08:00:00Z"),
    )
    _refuses(paths, "event_period_invalid")


def test_universe_counts_keep_excluded_unmappable_and_stale_in_denominator(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    def lie_about_count(document: dict[str, Any]) -> None:
        document["counts"]["total_eligible"] = 2

    _rewrite_object(paths, "unv:test.commodities.1", lie_about_count)
    _refuses(paths, "universe_counts_mismatch")

    paths = _fixture(tmp_path / "excluded")

    def exclude_member(document: dict[str, Any]) -> None:
        document["members"][0]["status"] = "excluded"
        document["counts"].update(included=0, excluded=1)

    _rewrite_object(paths, "unv:test.commodities.1", exclude_member)
    _refuses(paths, "edge_covered_entity_not_included")


def test_universe_members_must_partition_the_immutable_source_frame(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    frame = json.loads(paths["frame"].read_text())
    frame["entity_ids"].append("ent:country.india")
    _write_json(paths["frame"], canonical.seal_record(frame))

    def accept_changed_frame_hash(document: dict[str, Any]) -> None:
        document["frame_artifact"]["sha256"] = _sha(paths["frame"])

    _rewrite_object(
        paths, "unv:test.commodities.1", accept_changed_frame_hash
    )
    _refuses(paths, "universe_frame_membership_mismatch")


def test_exposure_edges_cannot_fake_quantification_or_coverage(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def qualitative_with_number(document: dict[str, Any]) -> None:
        document["quantification_status"] = "qualitative"

    _rewrite_object(paths, "edg:test.iran_crude.001", qualitative_with_number)
    _refuses(paths, "object_schema_invalid")

    paths = _fixture(tmp_path / "coverage")

    def wrong_covered_entity(document: dict[str, Any]) -> None:
        document["coverage_basis"]["covered_entity_id"] = "ent:country.india"

    _rewrite_object(paths, "edg:test.iran_crude.001", wrong_covered_entity)
    _refuses(paths, "edge_covered_entity_not_endpoint")

    paths = _fixture(tmp_path / "unknown")

    def unknown_without_limitation(document: dict[str, Any]) -> None:
        document["quantification_status"] = "unknown"
        document["magnitude"] = None
        document["confidence"] = {
            "status": "not_estimated",
            "meaning": "Magnitude is unknown.",
            "lower": None,
            "upper": None,
            "category": None,
        }

    _rewrite_object(paths, "edg:test.iran_crude.001", unknown_without_limitation)
    _refuses(paths, "edge_unknown_limitation_missing")

    paths = _fixture(tmp_path / "qualitative")

    def qualitative_without_boundary(document: dict[str, Any]) -> None:
        document["quantification_status"] = "qualitative"
        document["magnitude"] = None
        document["confidence"] = {
            "status": "interval",
            "meaning": "Improper numeric-looking confidence.",
            "lower": 0.7,
            "upper": 0.9,
            "category": None,
        }

    _rewrite_object(paths, "edg:test.iran_crude.001", qualitative_without_boundary)
    _refuses(paths, "object_schema_invalid")

    paths = _fixture(tmp_path / "qualitative_missing_code")

    def qualitative_without_code(document: dict[str, Any]) -> None:
        document["quantification_status"] = "qualitative"
        document["magnitude"] = None
        document["confidence"] = {
            "status": "categorical",
            "meaning": "Qualitative evidence confidence only.",
            "lower": None,
            "upper": None,
            "category": "test_only",
        }

    _rewrite_object(paths, "edg:test.iran_crude.001", qualitative_without_code)
    _refuses(paths, "object_schema_invalid")

    paths = _fixture(tmp_path / "future_magnitude")

    def use_unobserved_measurement_period(document: dict[str, Any]) -> None:
        document["magnitude"]["period_end"] = "2026-08-09"

    _rewrite_object(
        paths, "edg:test.iran_crude.001", use_unobserved_measurement_period
    )
    _refuses(paths, "edge_magnitude_after_observation")


def test_calculated_edge_method_must_resolve_to_registered_bytes(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def invent_method(document: dict[str, Any]) -> None:
        invented = {
            "method_id": "method:test.invented",
            "version": "1.0.0",
            "implementation_sha256": "d" * 64,
            "run_id": "run:test.001",
        }
        document["method"] = invented
        document["provenance"]["method"] = invented

    _rewrite_object(paths, "edg:test.iran_crude.001", invent_method)
    _refuses(paths, "method_unregistered")


def test_references_and_provenance_must_resolve_inside_the_release(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def missing_actor(document: dict[str, Any]) -> None:
        document["actor_entity_ids"] = ["ent:country.missing"]

    _rewrite_object(paths, "evt:test.policy.001", missing_actor)
    _refuses(paths, "event_entity_reference_missing")

    paths = _fixture(tmp_path / "provenance")

    def hide_edge_evidence(document: dict[str, Any]) -> None:
        document["provenance"]["evidence_ids"] = []

    _rewrite_object(paths, "edg:test.iran_crude.001", hide_edge_evidence)
    _refuses(paths, "provenance_evidence_mismatch")


def test_strict_json_rejects_duplicate_keys_nonfinite_values_and_symlinks(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    entity_path = paths["objects"]["ent:country.india"]
    entity_path.write_text('{"object_type":"entity","object_type":"entity"}\n')
    manifest = json.loads(paths["manifest"].read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == "ent:country.india")
    entry["file_sha256"] = _sha(entity_path)
    _write_manifest(paths, manifest)
    _refuses(paths, "json_duplicate_key")

    paths = _fixture(tmp_path / "nan")
    entity_path = paths["objects"]["ent:country.india"]
    entity_path.write_text('{"record_sha256":"' + "0" * 64 + '","bad":NaN}\n')
    manifest = json.loads(paths["manifest"].read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == "ent:country.india")
    entry["file_sha256"] = _sha(entity_path)
    _write_manifest(paths, manifest)
    _refuses(paths, "json_non_finite")

    paths = _fixture(tmp_path / "symlink")
    target = paths["objects"]["ent:country.india"]
    link = paths["root"] / "canonical" / "linked.json"
    link.symlink_to(target)
    manifest = json.loads(paths["manifest"].read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == "ent:country.india")
    entry["path"] = str(link.relative_to(paths["root"]))
    _write_manifest(paths, manifest)
    _refuses(paths, "symlink_forbidden")


def test_committed_schema_registry_is_complete_and_byte_exact() -> None:
    schemas, validators, _ = canonical._load_schema_registry(
        ROOT, ROOT / "governance" / "canonical_schema_registry.json"
    )
    assert set(schemas) == canonical._REGISTRY_TYPES
    assert set(validators) == canonical._REGISTRY_TYPES - {"common_definitions"}
    for row in json.loads(
        (ROOT / "governance" / "canonical_schema_registry.json").read_text()
    )["schemas"]:
        assert _sha(ROOT / row["path"]) == row["sha256"]
        if row["object_type"] != "common_definitions":
            schema = json.loads((ROOT / row["path"]).read_text())
            assert schema["additionalProperties"] is False

    method_registry = json.loads(
        (ROOT / "governance" / "canonical_method_registry.json").read_text()
    )
    release_signers = json.loads(
        (ROOT / "governance" / "release_signers.json").read_text()
    )
    assert method_registry["default_policy"] == "deny"
    assert method_registry["methods"] == []
    assert release_signers["default_policy"] == "deny"
    assert release_signers["signers"] == []
