"""Deterministic eight-lane public test vector for IGRM Sensor Fusion.

The fixture extends the OGES synthetic conformance release with seven further
synthetic evidence sources.  Every key, right, URL and observation in this
module is a public test vector.  It is not a production release and makes no
claim about a real event, provider, permission or sensor value.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import canonical_objects as canonical
from src import oges_fixture, sensor_fusion

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT = ROOT / "docs" / "data" / "sensor_fusion_demo.json"

_EVENT_ID = "evt:oges.fixture.policy.001"
_RELEASE_GENERATED = "2026-08-08T13:00:00Z"
_COMPLETE_WINDOW = ("2026-08-08T08:30:00Z", "2026-08-08T11:00:00Z")
_NARROW_WINDOW = ("2026-08-08T08:30:00Z", "2026-08-08T09:05:00Z")


@dataclass(frozen=True)
class SensorFixture:
    root: Path
    manifest: Path
    event_id: str
    release_private_key: Ed25519PrivateKey
    evidence_paths: dict[str, Path]


@dataclass(frozen=True)
class LaneSeed:
    lane_id: str
    source_id: str
    source_role: str
    authority_class: str
    evidence_id: str
    evidence_type: str
    observed_at: str
    retrieved_at: str


_LANE_SEEDS = (
    LaneSeed(
        "news",
        "sensor_fixture_news",
        "news_test_evidence",
        "independent_reporting",
        "evd:sensor.fixture.news.001",
        "news_article",
        "2026-08-08T09:15:00Z",
        "2026-08-08T09:20:00Z",
    ),
    LaneSeed(
        "coded_event",
        "sensor_fixture_coded_event",
        "event_dataset_test",
        "provider_coded_dataset",
        "evd:sensor.fixture.coded_event.001",
        "dataset_observation",
        "2026-08-08T09:30:00Z",
        "2026-08-08T09:35:00Z",
    ),
    LaneSeed(
        "physical_transmission",
        "sensor_fixture_physical",
        "physical_transmission_test",
        "research_dataset",
        "evd:sensor.fixture.physical.001",
        "dataset_observation",
        "2026-08-08T09:45:00Z",
        "2026-08-08T09:50:00Z",
    ),
    LaneSeed(
        "trade_transmission",
        "sensor_fixture_trade",
        "trade_transmission_test",
        "research_dataset",
        "evd:sensor.fixture.trade.001",
        "dataset_observation",
        "2026-08-08T10:00:00Z",
        "2026-08-08T10:05:00Z",
    ),
    LaneSeed(
        "energy_transmission",
        "sensor_fixture_energy",
        "energy_transmission_test",
        "research_dataset",
        "evd:sensor.fixture.energy.001",
        "dataset_observation",
        "2026-08-08T10:15:00Z",
        "2026-08-08T10:20:00Z",
    ),
    LaneSeed(
        "market_transmission",
        "sensor_fixture_market",
        "market_transmission_test",
        "market_data",
        "evd:sensor.fixture.market.001",
        "dataset_observation",
        "2026-08-08T10:30:00Z",
        "2026-08-08T10:35:00Z",
    ),
    LaneSeed(
        "public_attention",
        "sensor_fixture_attention",
        "attention_test",
        "public_platform",
        "evd:sensor.fixture.attention.001",
        "dataset_observation",
        "2026-08-08T10:45:00Z",
        "2026-08-08T10:50:00Z",
    ),
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rights_private_key() -> Ed25519PrivateKey:
    seed = hashlib.sha256(b"OGES-0.1-TEST-ONLY:rights").digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _lifecycle() -> dict[str, object]:
    return {
        "revision": 1,
        "state": "active",
        "supersedes_id": None,
        "superseded_by": None,
        "correction_id": None,
    }


def _install_fusion_contract(root: Path) -> None:
    copies = (
        ("src/sensor_fusion.py", "src/sensor_fusion.py"),
        ("governance/sensor_fusion_registry.json", "governance/sensor_fusion_registry.json"),
        ("governance/sensor_lane_registry.json", "governance/sensor_lane_registry.json"),
        ("schemas/sensor-fusion.schema.json", "schemas/sensor-fusion.schema.json"),
    )
    for source, destination in copies:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)


def _decision_and_source(seed: LaneSeed, root: Path) -> dict[str, Any]:
    decision_id = f"sensor-fixture-{seed.lane_id}-decision-2026-08-08"
    source: dict[str, Any] = {
        "source_id": seed.source_id,
        "name": f"Synthetic {seed.lane_id.replace('_', ' ')} source",
        "provider": "IGRM Sensor Fusion public test vector",
        "role": seed.source_role,
        "authority_class": seed.authority_class,
        "independence_group": f"sensor_fixture_{seed.lane_id}_provider",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": decision_id,
        "decision_owner": "IGRM Sensor Fusion public test vector",
        "signer_id": "signer:oges.fixture.rights",
        "decision_artifact_path": f"governance/rights_decisions/{seed.source_id}.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": f"governance/rights_decisions/{seed.source_id}.sig",
        "reviewed_on": "2026-08-08",
        "review_due": "2027-08-08",
        "access_url": f"https://example.test/sensor-fixture/{seed.lane_id}",
        "terms_url": "https://example.test/sensor-fixture/terms",
        "access_basis": "synthetic_test_authorization",
        "geographic_coverage": "One synthetic test frame",
        "historical_coverage": "One synthetic date",
        "retrieval_target": "One deterministic metadata-only observation",
        "outage_fallback": "Fail closed",
        "cost_owner": "Synthetic test owner",
        "reproducibility_tier": "open_synthetic_fixture",
        "max_current_age_days": 30,
        "permitted_uses": ["cite_metadata"],
        "notes": "Public test vector only; never a real legal or source decision.",
    }
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
    decision: dict[str, object] = {"schema_version": "1.0.0"}
    decision.update({field: source[field] for field in fields})
    decision["statement"] = (
        "Synthetic authorization for one metadata-only sensor-fusion test release."
    )
    decision_path = root / cast(str, source["decision_artifact_path"])
    _write_json(decision_path, decision)
    signature_path = root / cast(str, source["decision_signature_path"])
    signature_path.write_bytes(_rights_private_key().sign(decision_path.read_bytes()))
    source["decision_artifact_sha256"] = _sha(decision_path)
    return source


def _evidence(seed: LaneSeed, direct_method: dict[str, Any]) -> dict[str, Any]:
    return canonical.seal_record(
        {
            "object_type": "evidence_item",
            "schema_version": "1.0.0",
            "evidence_id": seed.evidence_id,
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_id": seed.source_id,
            "source_record_id": f"synthetic-{seed.lane_id}-001",
            "retrieval_id": f"ret:sensor.fixture.{seed.lane_id}.001",
            "evidence_type": seed.evidence_type,
            "title": f"Synthetic {seed.lane_id.replace('_', ' ')} observation",
            "publisher_entity_id": None,
            "authors": [],
            "language": "en",
            "published_at": seed.observed_at,
            "observed_at": seed.observed_at,
            "effective_start": seed.observed_at,
            "effective_end": None,
            "retrieved_at": seed.retrieved_at,
            "geography_entity_ids": [],
            "public_url": f"https://example.test/sensor-fixture/{seed.lane_id}/001",
            "artifact_path": None,
            "content_sha256": hashlib.sha256(
                f"IGRM synthetic {seed.lane_id} evidence bytes".encode()
            ).hexdigest(),
            "artifact_sha256": None,
            "content_availability": "hash_metadata_only",
            "rights_use": "cite_metadata",
            "rights_decision_id": f"sensor-fixture-{seed.lane_id}-decision-2026-08-08",
            "privacy_class": "public",
            "verification_status": "single_source",
            "extraction_method": "provider_api",
            "provenance": {
                "created_at": "2026-08-08T12:00:00Z",
                "created_by": "system:sensor.fixture_builder",
                "reviewed_by": [],
                "adjudication_status": "unreviewed",
                "source_ids": [seed.source_id],
                "evidence_ids": [],
                "method": direct_method,
            },
        }
    )


def _rewrite_event(
    fixture: oges_fixture.Fixture,
    evidence: list[dict[str, Any]],
) -> None:
    event_path = fixture.objects[_EVENT_ID]
    event = _read_json(event_path)
    event["evidence_links"].extend(
        {
            "evidence_id": row["evidence_id"],
            "role": "context",
            "asserted_at": row["observed_at"],
        }
        for row in evidence
    )
    all_evidence_ids = [cast(str, link["evidence_id"]) for link in event["evidence_links"]]
    event["provenance"]["evidence_ids"] = all_evidence_ids
    event["provenance"]["source_ids"] = sorted(
        {
            "oges_fixture_source",
            *(cast(str, row["source_id"]) for row in evidence),
        }
    )
    event = canonical.seal_record(event)
    _write_json(event_path, event)


def _rights_snapshot(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_id": row["source_id"],
            "decision_id": row["decision_id"],
            "decision_artifact_sha256": row["decision_artifact_sha256"],
            "signer_id": row["signer_id"],
            "independence_group": row["independence_group"],
            "authority_class": row["authority_class"],
        }
        for row in sorted(sources, key=lambda item: item["source_id"])
    ]


def _rewrite_manifest(
    fixture: oges_fixture.Fixture,
    evidence_paths: dict[str, Path],
    sources: list[dict[str, Any]],
) -> None:
    manifest = _read_json(fixture.manifest)
    event_path = fixture.objects[_EVENT_ID]
    event = _read_json(event_path)
    event_entry = next(row for row in manifest["objects"] if row["object_id"] == _EVENT_ID)
    event_entry["file_sha256"] = _sha(event_path)
    event_entry["record_sha256"] = event["record_sha256"]
    for evidence_id in sorted(evidence_paths):
        path = evidence_paths[evidence_id]
        row = _read_json(path)
        manifest["objects"].append(
            {
                "object_type": "evidence_item",
                "object_id": evidence_id,
                "path": str(path.relative_to(fixture.root)),
                "file_sha256": _sha(path),
                "record_sha256": row["record_sha256"],
            }
        )
    manifest["counts"]["evidence_item"] = 1 + len(evidence_paths)
    manifest["rights_registry_sha256"] = _sha(
        fixture.root / "governance" / "source_rights_registry.json"
    )
    manifest["rights_snapshot"] = _rights_snapshot(sources)
    manifest = canonical.seal_record(manifest)
    _write_json(fixture.manifest, manifest)
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def build_fixture(destination: Path) -> SensorFixture:
    """Build and independently validate the signed eight-lane fixture."""

    base = oges_fixture.build_fixture(destination)
    _install_fusion_contract(base.root)
    rights_path = base.root / "governance" / "source_rights_registry.json"
    rights = _read_json(rights_path)
    sources = cast(list[dict[str, Any]], rights["sources"])
    for seed in _LANE_SEEDS:
        sources.append(_decision_and_source(seed, base.root))
    _write_json(rights_path, rights)

    method_registry = _read_json(base.root / "governance" / "canonical_method_registry.json")
    direct_row = next(
        row
        for row in method_registry["methods"]
        if row["method_id"] == "method:oges.fixture.direct"
    )
    direct_method = {
        "method_id": direct_row["method_id"],
        "version": direct_row["version"],
        "implementation_sha256": direct_row["implementation_sha256"],
        "run_id": "run:sensor.fixture.001",
    }
    documents = [_evidence(seed, direct_method) for seed in _LANE_SEEDS]
    evidence_paths: dict[str, Path] = {}
    for document in documents:
        evidence_id = cast(str, document["evidence_id"])
        path = base.root / "canonical" / f"{evidence_id.replace(':', '__')}.json"
        _write_json(path, document)
        evidence_paths[evidence_id] = path
    _rewrite_event(base, documents)
    _rewrite_manifest(base, evidence_paths, sources)

    canonical.load_validated_release(
        base.manifest,
        root=base.root,
        schema_registry_path=base.root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=rights_path,
        rights_signers_path=base.root / "governance" / "rights_signers.json",
        method_registry_path=base.root / "governance" / "canonical_method_registry.json",
        release_signers_path=base.root / "governance" / "release_signers.json",
    )
    all_paths = {**base.objects, **evidence_paths}
    return SensorFixture(
        root=base.root,
        manifest=base.manifest,
        event_id=_EVENT_ID,
        release_private_key=base.release_private_key,
        evidence_paths=all_paths,
    )


def _fuse(fixture: SensorFixture, window: tuple[str, str]) -> dict[str, Any]:
    root = fixture.root
    return sensor_fusion.fuse_event_sensors(
        fixture.manifest,
        fixture.event_id,
        window[0],
        window[1],
        _RELEASE_GENERATED,
        root=root,
        schema_registry_path=root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=root / "governance" / "source_rights_registry.json",
        rights_signers_path=root / "governance" / "rights_signers.json",
        method_registry_path=root / "governance" / "canonical_method_registry.json",
        release_signers_path=root / "governance" / "release_signers.json",
        fusion_registry_path=root / "governance" / "sensor_fusion_registry.json",
    )


def build_demo() -> dict[str, Any]:
    """Return the deterministic synthetic public demo payload."""

    with tempfile.TemporaryDirectory(prefix="igrm-sensor-fixture-") as tmp:
        fixture = build_fixture(Path(tmp))
        complete = _fuse(fixture, _COMPLETE_WINDOW)
        narrow = _fuse(fixture, _NARROW_WINDOW)
    return {
        "_meta": {
            "schema": "igrm-sensor-fusion-demo-v1",
            "generated": "2026-08-08T13:00:00Z",
            "date": "2026-08-08",
            "what": "Deterministic synthetic Sensor Fusion conformance vector.",
            "scope": "synthetic_test_vector_only",
            "production_release": False,
            "real_source_or_rights_claims": False,
            "numeric_fusion_performed": False,
            "license": "CC BY 4.0",
            "citation": "Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/",
            "source": "https://igrm.in/data/sensor_fusion_demo.json",
            "codebook": "https://igrm.in/standard.html",
            "method": "method:igrm.sensor_fusion@1.0.0",
        },
        "complete_matrix": complete,
        "narrow_window_matrix": narrow,
    }


def main() -> None:
    _write_json(PUBLIC_OUTPUT, build_demo())
    print(PUBLIC_OUTPUT)


if __name__ == "__main__":
    main()
