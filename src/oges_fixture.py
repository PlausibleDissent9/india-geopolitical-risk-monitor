"""Deterministic synthetic fixtures for the OGES 0.1 conformance profile.

The private keys in this module are intentionally public test vectors.  They
must never appear in a production trust registry.  Fixture generation performs
no network access and makes no assertion about real sources, rights or events.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]


class OgesFixtureError(ValueError):
    """Stable fixture-construction refusal."""


@dataclass(frozen=True)
class Fixture:
    root: Path
    manifest: Path
    objects: dict[str, Path]
    frame: Path
    release_signature: Path
    release_private_key: Ed25519PrivateKey


def _fail(code: str) -> NoReturn:
    raise OgesFixtureError(code)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_private_key(label: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(f"OGES-0.1-TEST-ONLY:{label}".encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _public_key(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _method(method_id: str, implementation_sha256: str) -> dict[str, object]:
    return {
        "method_id": method_id,
        "version": "1.0.0",
        "implementation_sha256": implementation_sha256,
        "run_id": "run:oges.fixture.001",
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
    evidence_ids: list[str],
    *,
    method: dict[str, object],
    reviewed_by: list[str] | None = None,
) -> dict[str, object]:
    return {
        "created_at": "2026-08-08T12:00:00Z",
        "created_by": "system:oges.fixture_builder",
        "reviewed_by": reviewed_by or [],
        "adjudication_status": "single_reviewed" if reviewed_by else "unreviewed",
        "source_ids": ["oges_fixture_source"],
        "evidence_ids": evidence_ids,
        "method": method,
    }


def _install_signed_rights(root: Path) -> None:
    private_key = _fixture_private_key("rights")
    _write_json(
        root / "governance" / "rights_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "signer:oges.fixture.rights",
                    "name": "OGES public test-vector rights signer",
                    "role": "test-only rights reviewer",
                    "public_key_ed25519_base64": _public_key(private_key),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                }
            ],
        },
    )
    source: dict[str, Any] = {
        "source_id": "oges_fixture_source",
        "name": "OGES synthetic official source",
        "provider": "OGES conformance fixture",
        "role": "official_test_evidence",
        "authority_class": "official_primary",
        "independence_group": "oges_fixture_provider",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "oges-fixture-decision-2026-08-08",
        "decision_owner": "OGES public test vector",
        "signer_id": "signer:oges.fixture.rights",
        "decision_artifact_path": "governance/rights_decisions/oges_fixture_source.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/oges_fixture_source.sig",
        "reviewed_on": "2026-08-08",
        "review_due": "2027-08-08",
        "access_url": "https://example.test/oges-fixture/source",
        "terms_url": "https://example.test/oges-fixture/terms",
        "access_basis": "synthetic_test_authorization",
        "geographic_coverage": "One synthetic test frame",
        "historical_coverage": "One synthetic date",
        "retrieval_target": "One deterministic metadata-only fixture",
        "outage_fallback": "Fail closed",
        "cost_owner": "Synthetic test owner",
        "reproducibility_tier": "open_synthetic_fixture",
        "max_current_age_days": 30,
        "permitted_uses": ["cite_metadata"],
        "notes": "Public test vector only; never a real legal or source decision.",
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
    decision_path = root / cast(str, source["decision_artifact_path"])
    _write_json(decision_path, decision)
    signature_path = root / cast(str, source["decision_signature_path"])
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


def _install_release_signer(root: Path) -> Ed25519PrivateKey:
    private_key = _fixture_private_key("release")
    _write_json(
        root / "governance" / "release_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "signer:oges.fixture.release",
                    "name": "OGES public test-vector release signer",
                    "role": "canonical_release_signer",
                    "public_key_ed25519_base64": _public_key(private_key),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                }
            ],
        },
    )
    return private_key


def _install_methods(root: Path) -> dict[str, dict[str, object]]:
    definitions = {
        "method:oges.fixture.direct": (
            ["evidence_item", "entity"],
            "methods/direct.py",
            "def apply(value):\n    return value\n",
        ),
        "rule:oges.fixture.event": (
            ["event"],
            "methods/event.py",
            "RULE_VERSION = '1.0.0'\n",
        ),
        "rule:oges.fixture.commodity_universe": (
            ["universe_release"],
            "rules/commodity_universe.py",
            "RULE_VERSION = '1.0.0'\n",
        ),
        "method:oges.fixture.exposure": (
            ["exposure_edge"],
            "methods/exposure.py",
            "RULE_VERSION = '1.0.0'\n",
        ),
    }
    rows: list[dict[str, object]] = []
    methods: dict[str, dict[str, object]] = {}
    for method_id, (object_types, relative, content) in definitions.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        digest = _sha(path)
        rows.append(
            {
                "method_id": method_id,
                "version": "1.0.0",
                "implementation_path": relative,
                "implementation_sha256": digest,
                "allowed_object_types": object_types,
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
    documentation = root / "rules" / "commodity_universe.md"
    documentation.write_text("# OGES synthetic commodity universe rule\n", encoding="utf-8")
    return methods


def _entity(
    entity_id: str,
    entity_type: str,
    name: str,
    method: dict[str, object],
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
                    "scheme": "oges_fixture",
                    "value": entity_id.split(":", 1)[1],
                    "effective_start": None,
                    "effective_end": None,
                    "evidence_ids": ["evd:oges.fixture.official.001"],
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
                ["evd:oges.fixture.official.001"], method=method
            ),
        }
    )


def build_fixture(destination: Path) -> Fixture:
    """Build the complete deterministic OGES synthetic release at *destination*."""

    if destination.is_symlink():
        _fail("fixture_destination_symlink")
    if destination.exists() and any(destination.iterdir()):
        _fail("fixture_destination_not_empty")
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    shutil.copytree(ROOT / "schemas", root / "schemas")
    (root / "governance").mkdir(parents=True)
    shutil.copy2(
        ROOT / "governance" / "canonical_schema_registry.json",
        root / "governance" / "canonical_schema_registry.json",
    )
    _install_signed_rights(root)
    release_private_key = _install_release_signer(root)
    methods = _install_methods(root)

    evidence = canonical.seal_record(
        {
            "object_type": "evidence_item",
            "schema_version": "1.0.0",
            "evidence_id": "evd:oges.fixture.official.001",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_id": "oges_fixture_source",
            "source_record_id": "official-001",
            "retrieval_id": "ret:oges.fixture.001",
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
            "geography_entity_ids": ["ent:country.synthetic_origin"],
            "public_url": "https://example.test/oges-fixture/official-001",
            "artifact_path": None,
            "content_sha256": hashlib.sha256(b"OGES synthetic official bytes").hexdigest(),
            "artifact_sha256": None,
            "content_availability": "hash_metadata_only",
            "rights_use": "cite_metadata",
            "rights_decision_id": "oges-fixture-decision-2026-08-08",
            "privacy_class": "public",
            "verification_status": "official_record",
            "extraction_method": "provider_api",
            "provenance": _provenance(
                [], method=methods["method:oges.fixture.direct"]
            ),
        }
    )
    entities = [
        _entity(
            "ent:country.synthetic_india",
            "country",
            "Synthetic India",
            methods["method:oges.fixture.direct"],
        ),
        _entity(
            "ent:country.synthetic_origin",
            "country",
            "Synthetic origin country",
            methods["method:oges.fixture.direct"],
        ),
        _entity(
            "ent:commodity.synthetic_crude",
            "commodity",
            "Synthetic crude oil",
            methods["method:oges.fixture.direct"],
        ),
    ]
    event = canonical.seal_record(
        {
            "object_type": "event",
            "schema_version": "1.0.0",
            "event_id": "evt:oges.fixture.policy.001",
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
            "actor_entity_ids": ["ent:country.synthetic_origin"],
            "target_entity_ids": [],
            "affected_entity_ids": ["ent:commodity.synthetic_crude"],
            "locations": [
                {
                    "entity_id": "ent:country.synthetic_origin",
                    "role": "primary",
                    "precision": "country",
                    "evidence_ids": ["evd:oges.fixture.official.001"],
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
                    "evidence_id": "evd:oges.fixture.official.001",
                    "role": "official_confirmation",
                    "asserted_at": "2026-08-08T09:00:00Z",
                }
            ],
            "coding": {
                "rule_id": "rule:oges.fixture.event",
                "rule_version": "1.0.0",
                "implementation_sha256": methods["rule:oges.fixture.event"][
                    "implementation_sha256"
                ],
                "status": "human_coded",
                "coder_ids": ["person:oges.fixture.coder"],
                "adjudicator_ids": [],
                "limitation_codes": [],
            },
            "provenance": _provenance(
                ["evd:oges.fixture.official.001"],
                method=methods["rule:oges.fixture.event"],
                reviewed_by=["person:oges.fixture.coder"],
            ),
        }
    )
    frame = canonical.seal_record(
        {
            "object_type": "universe_frame",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "universe_id": "universe:oges.fixture.commodities",
            "entity_type": "commodity",
            "reference_date": "2026-08-08",
            "source_evidence_id": "evd:oges.fixture.official.001",
            "source_version": "synthetic-v1",
            "extraction_query": "all rows in the one-row synthetic source frame",
            "extracted_at": "2026-08-08T11:30:00Z",
            "entity_ids": ["ent:commodity.synthetic_crude"],
        }
    )
    frame_path = root / "frames" / "commodity_frame.json"
    _write_json(frame_path, frame)
    universe_method = methods["rule:oges.fixture.commodity_universe"]
    universe = canonical.seal_record(
        {
            "object_type": "universe_release",
            "schema_version": "1.0.0",
            "universe_release_id": "unv:oges.fixture.commodities.1",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "universe_id": "universe:oges.fixture.commodities",
            "version": "1.0.0",
            "name": "OGES synthetic commodity frame",
            "entity_type": "commodity",
            "reference_date": "2026-08-08",
            "denominator_definition": "Every commodity in the one-row synthetic frame.",
            "inclusion_rule": {
                "rule_id": "rule:oges.fixture.commodity_universe",
                "version": "1.0.0",
                "implementation_path": "rules/commodity_universe.py",
                "implementation_sha256": universe_method["implementation_sha256"],
                "documentation_path": "rules/commodity_universe.md",
            },
            "frame_artifact": {
                "path": "frames/commodity_frame.json",
                "sha256": _sha(frame_path),
                "format": "igrm_universe_frame_v1",
            },
            "source_evidence_ids": ["evd:oges.fixture.official.001"],
            "members": [
                {
                    "entity_id": "ent:commodity.synthetic_crude",
                    "status": "included",
                    "reason_code": "reason:oges.fixture.in_frame",
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
                ["evd:oges.fixture.official.001"], method=universe_method
            ),
        }
    )
    edge_method = methods["method:oges.fixture.exposure"]
    edge = canonical.seal_record(
        {
            "object_type": "exposure_edge",
            "schema_version": "1.0.0",
            "edge_id": "edg:oges.fixture.origin_crude.001",
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_entity_id": "ent:country.synthetic_origin",
            "target_entity_id": "ent:commodity.synthetic_crude",
            "edge_type": "import_dependence",
            "exposure_direction": "inbound_to_india",
            "quantification_status": "quantified",
            "magnitude": {
                "value": 12.5,
                "unit": "percent_of_import_volume",
                "denominator": "total synthetic crude-oil import volume in the period",
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
                "universe_release_id": "unv:oges.fixture.commodities.1",
                "covered_entity_id": "ent:commodity.synthetic_crude",
                "member_status": "included",
            },
            "evidence_ids": ["evd:oges.fixture.official.001"],
            "method": edge_method,
            "confidence": {
                "status": "categorical",
                "meaning": "Synthetic evidence confidence, not a probability.",
                "lower": None,
                "upper": None,
                "category": "test_only",
            },
            "limitation_codes": [],
            "provenance": _provenance(
                ["evd:oges.fixture.official.001"], method=edge_method
            ),
        }
    )

    documents = [evidence, *entities, event, universe, edge]
    object_paths: dict[str, Path] = {}
    entries: list[dict[str, object]] = []
    for document in documents:
        object_type = cast(str, document["object_type"])
        object_id = cast(str, document[canonical._ID_FIELD[object_type]])
        path = root / "canonical" / f"{object_id.replace(':', '__')}.json"
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
    counts = Counter(cast(str, document["object_type"]) for document in documents)
    rights = json.loads(
        (root / "governance" / "source_rights_registry.json").read_text()
    )["sources"][0]
    manifest = canonical.seal_record(
        {
            "object_type": "canonical_release",
            "schema_version": "1.0.0",
            "release_id": "rel:oges.fixture.2026-08-08",
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
            "rights_signers_sha256": _sha(root / "governance" / "rights_signers.json"),
            "release_signers_sha256": _sha(
                root / "governance" / "release_signers.json"
            ),
            "release_signer_id": "signer:oges.fixture.release",
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
    manifest_path = root / "canonical" / "release.json"
    _write_json(manifest_path, manifest)
    signature_path = root / "canonical" / "release.sig"
    signature_path.write_bytes(release_private_key.sign(manifest_path.read_bytes()))
    return Fixture(
        root=root,
        manifest=manifest_path,
        objects=object_paths,
        frame=frame_path,
        release_signature=signature_path,
        release_private_key=release_private_key,
    )


def _write_manifest(fixture: Fixture, manifest: dict[str, Any]) -> None:
    _write_json(fixture.manifest, canonical.seal_record(manifest))
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _rewrite_object(
    fixture: Fixture,
    object_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    path = fixture.objects[object_id]
    document = json.loads(path.read_text())
    mutate(document)
    document = canonical.seal_record(document)
    _write_json(path, document)
    manifest = json.loads(fixture.manifest.read_text())
    entry = next(row for row in manifest["objects"] if row["object_id"] == object_id)
    entry["file_sha256"] = _sha(path)
    entry["record_sha256"] = document["record_sha256"]
    _write_manifest(fixture, manifest)


def apply_operation(fixture: Fixture, operation: str) -> None:
    """Apply one registered adversarial operation to a valid fixture."""

    if operation == "none":
        return
    if operation == "tamper_release_signature":
        fixture.release_signature.write_bytes(b"0" * 64)
        return
    if operation == "spoof_official_confirmation":
        def relabel(document: dict[str, Any]) -> None:
            document["evidence_type"] = "news_article"
            document["verification_status"] = "single_source"

        _rewrite_object(fixture, "evd:oges.fixture.official.001", relabel)
        return
    if operation == "omit_universe_member":
        frame = json.loads(fixture.frame.read_text())
        frame["entity_ids"].append("ent:commodity.fixture_omitted")
        _write_json(fixture.frame, canonical.seal_record(frame))

        def accept_frame_hash(document: dict[str, Any]) -> None:
            document["frame_artifact"]["sha256"] = _sha(fixture.frame)

        _rewrite_object(
            fixture, "unv:oges.fixture.commodities.1", accept_frame_hash
        )
        return
    if operation == "invent_exposure_method":
        def invent(document: dict[str, Any]) -> None:
            method = {
                "method_id": "method:oges.fixture.invented",
                "version": "1.0.0",
                "implementation_sha256": "d" * 64,
                "run_id": "run:oges.fixture.001",
            }
            document["method"] = method
            document["provenance"]["method"] = method

        _rewrite_object(fixture, "edg:oges.fixture.origin_crude.001", invent)
        return
    if operation == "qualitative_edge_with_number":
        _rewrite_object(
            fixture,
            "edg:oges.fixture.origin_crude.001",
            lambda document: document.update(quantification_status="qualitative"),
        )
        return
    if operation == "future_measurement_period":
        def move_period(document: dict[str, Any]) -> None:
            document["magnitude"]["period_end"] = "2026-08-09"

        _rewrite_object(fixture, "edg:oges.fixture.origin_crude.001", move_period)
        return
    if operation == "tamper_rights_registry":
        path = fixture.root / "governance" / "source_rights_registry.json"
        path.write_text(path.read_text() + "\n")
        return
    if operation == "duplicate_json_key":
        path = fixture.objects["ent:country.synthetic_india"]
        path.write_text('{"object_type":"entity","object_type":"entity"}\n')
        manifest = json.loads(fixture.manifest.read_text())
        entry = next(
            row
            for row in manifest["objects"]
            if row["object_id"] == "ent:country.synthetic_india"
        )
        entry["file_sha256"] = _sha(path)
        _write_manifest(fixture, manifest)
        return
    if operation == "false_release_count":
        manifest = json.loads(fixture.manifest.read_text())
        manifest["counts"]["event"] = 0
        _write_manifest(fixture, manifest)
        return
    if operation == "expose_restricted_evidence":
        def expose(document: dict[str, Any]) -> None:
            document.update(
                privacy_class="restricted",
                content_availability="restricted",
                public_url="https://example.test/should-not-be-public",
                artifact_path=None,
                artifact_sha256=None,
            )

        _rewrite_object(fixture, "evd:oges.fixture.official.001", expose)
        return
    _fail("fixture_operation_unregistered")
