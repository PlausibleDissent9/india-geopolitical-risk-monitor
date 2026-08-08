"""Deterministic two-vintage public test vector for India Exposure DNA.

The fixture is entirely synthetic.  It extends the signed OGES conformance
release with one synthetic company, a declared four-company frame and direct
edges to a commodity, country, port, route, sector, state, technology and (in
the later vintage) critical asset.  It makes no claim about a real entity,
source, right, exposure value or operational feed.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import canonical_objects as canonical
from src import exposure_dna, oges_fixture

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT = ROOT / "docs" / "data" / "exposure_dna_demo.json"

_TARGET_ID = "ent:company.synthetic_india_anchor"
_EVIDENCE_ID = "evd:oges.fixture.official.001"
_COMPANY_UNIVERSE_ID = "unv:exposure.dna.fixture.companies.1"
_BEFORE_GENERATED = "2026-08-08T12:30:00Z"
_AFTER_GENERATED = "2026-08-08T13:00:00Z"


@dataclass(frozen=True)
class DNAFixture:
    root: Path
    manifest: Path
    target_entity_id: str
    objects: dict[str, Path]
    release_private_key: Ed25519PrivateKey


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _lifecycle() -> dict[str, object]:
    return {
        "revision": 1,
        "state": "active",
        "supersedes_id": None,
        "superseded_by": None,
        "correction_id": None,
    }


def _provenance(method: dict[str, Any]) -> dict[str, Any]:
    return {
        "created_at": "2026-08-08T12:00:00Z",
        "created_by": "system:exposure.dna.fixture_builder",
        "reviewed_by": [],
        "adjudication_status": "unreviewed",
        "source_ids": ["oges_fixture_source"],
        "evidence_ids": [_EVIDENCE_ID],
        "method": method,
    }


def _install_dna_contract(root: Path) -> None:
    copies = (
        ("src/exposure_dna.py", "src/exposure_dna.py"),
        (
            "governance/exposure_dna_registry.json",
            "governance/exposure_dna_registry.json",
        ),
        ("schemas/exposure-dna.schema.json", "schemas/exposure-dna.schema.json"),
    )
    for source, destination in copies:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)


def _method(
    method_id: str,
    implementation_sha256: str,
    run_id: str,
) -> dict[str, Any]:
    return {
        "method_id": method_id,
        "version": "1.0.0",
        "implementation_sha256": implementation_sha256,
        "run_id": run_id,
    }


def _install_company_universe_method(root: Path) -> dict[str, Any]:
    registry_path = root / "governance" / "canonical_method_registry.json"
    registry = _read_json(registry_path)
    implementation = root / "rules" / "exposure_dna_company_universe.py"
    documentation = root / "rules" / "exposure_dna_company_universe.md"
    implementation.parent.mkdir(parents=True, exist_ok=True)
    implementation.write_text("RULE_VERSION = '1.0.0'\n", encoding="utf-8")
    documentation.write_text(
        "# Synthetic four-company Exposure DNA universe rule\n",
        encoding="utf-8",
    )
    digest = _sha(implementation)
    method_id = "rule:exposure.dna.fixture.company_universe"
    registry["methods"].append(
        {
            "method_id": method_id,
            "version": "1.0.0",
            "implementation_path": "rules/exposure_dna_company_universe.py",
            "implementation_sha256": digest,
            "allowed_object_types": ["universe_release"],
            "effective": "2026-08-08",
            "superseded_on": None,
        }
    )
    _write_json(registry_path, registry)
    return _method(method_id, digest, "run:exposure.dna.fixture.universe.001")


def _registered_method(root: Path, method_id: str, run_id: str) -> dict[str, Any]:
    registry = _read_json(root / "governance" / "canonical_method_registry.json")
    row = next(item for item in registry["methods"] if item["method_id"] == method_id)
    return _method(method_id, row["implementation_sha256"], run_id)


def _entity(
    entity_id: str,
    entity_type: str,
    name: str,
    method: dict[str, Any],
    *,
    parent_ids: list[str] | None = None,
    jurisdiction_ids: list[str] | None = None,
    identity_status: str = "authoritative",
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
                    "scheme": "exposure_dna_fixture",
                    "value": entity_id.split(":", 1)[1],
                    "effective_start": None,
                    "effective_end": None,
                    "evidence_ids": [_EVIDENCE_ID],
                }
            ],
            "parent_entity_ids": parent_ids or [],
            "jurisdiction_entity_ids": jurisdiction_ids or [],
            "geometry": {
                "artifact_path": None,
                "artifact_sha256": None,
                "geometry_type": "none",
                "precision": "not_applicable",
            },
            "effective_start": None,
            "effective_end": None,
            "identity_status": identity_status,
            "provenance": _provenance(method),
        }
    )


def _measure(
    value: float,
    unit: str,
    denominator: str,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "denominator": denominator,
        "period_start": period_start,
        "period_end": period_end,
        "currency": None,
        "price_basis": None,
        "uncertainty": {
            "status": "interval",
            "meaning": "Synthetic test interval; not calibrated uncertainty.",
            "lower": max(0.0, value - 5.0),
            "upper": value + 5.0,
            "category": None,
        },
    }


def _edge(
    edge_id: str,
    source_entity_id: str,
    target_entity_id: str,
    edge_type: str,
    method: dict[str, Any],
    *,
    quantification_status: Literal["quantified", "qualitative", "unknown"],
    magnitude: dict[str, Any] | None,
    observed_at: str = "2026-08-08T10:00:00Z",
    effective_start: str = "2026-08-08",
    exposure_direction: str = "inbound_to_india",
) -> dict[str, Any]:
    if quantification_status == "qualitative":
        confidence = {
            "status": "categorical",
            "meaning": "Synthetic qualitative relationship; not a probability.",
            "lower": None,
            "upper": None,
            "category": "test_only",
        }
        limitations = ["magnitude_not_quantified"]
    elif quantification_status == "unknown":
        confidence = {
            "status": "not_estimated",
            "meaning": "Synthetic relationship with no magnitude estimate.",
            "lower": None,
            "upper": None,
            "category": None,
        }
        limitations = ["magnitude_unknown"]
    else:
        confidence = {
            "status": "categorical",
            "meaning": "Synthetic quantified component; confidence is not probability.",
            "lower": None,
            "upper": None,
            "category": "test_only",
        }
        limitations = []
    return canonical.seal_record(
        {
            "object_type": "exposure_edge",
            "schema_version": "1.0.0",
            "edge_id": edge_id,
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "source_entity_id": source_entity_id,
            "target_entity_id": target_entity_id,
            "edge_type": edge_type,
            "exposure_direction": exposure_direction,
            "quantification_status": quantification_status,
            "magnitude": magnitude,
            "derivation_type": "calculated",
            "effective_start": effective_start,
            "effective_end": None,
            "observed_at": observed_at,
            "coverage_basis": {
                "universe_release_id": _COMPANY_UNIVERSE_ID,
                "covered_entity_id": _TARGET_ID,
                "member_status": "included",
            },
            "evidence_ids": [_EVIDENCE_ID],
            "method": method,
            "confidence": confidence,
            "limitation_codes": limitations,
            "provenance": _provenance(method),
        }
    )


def _fixture_entities(method: dict[str, Any]) -> list[dict[str, Any]]:
    state_id = "ent:state.synthetic_coast"
    sector_id = "ent:sector.synthetic_manufacturing"
    return [
        _entity(state_id, "state_or_ut", "Synthetic coastal state", method),
        _entity(sector_id, "sector", "Synthetic manufacturing sector", method),
        _entity(
            _TARGET_ID,
            "company",
            "Synthetic India Anchor Limited",
            method,
            parent_ids=[sector_id],
            jurisdiction_ids=[state_id],
        ),
        _entity(
            "ent:company.synthetic_peer_a",
            "company",
            "Synthetic peer A",
            method,
            parent_ids=[sector_id],
            jurisdiction_ids=[state_id],
        ),
        _entity(
            "ent:company.synthetic_peer_b",
            "company",
            "Synthetic peer B",
            method,
            parent_ids=[sector_id],
            jurisdiction_ids=[state_id],
            identity_status="provisional",
        ),
        _entity(
            "ent:company.synthetic_peer_c",
            "company",
            "Synthetic peer C",
            method,
            parent_ids=[sector_id],
            jurisdiction_ids=[state_id],
            identity_status="provisional",
        ),
        _entity("ent:port.synthetic_gateway", "port", "Synthetic gateway port", method),
        _entity("ent:route.synthetic_sea_lane", "route", "Synthetic sea lane", method),
        _entity(
            "ent:critical_asset.synthetic_grid",
            "critical_asset",
            "Synthetic grid asset",
            method,
        ),
        _entity(
            "ent:technology.synthetic_platform",
            "technology",
            "Synthetic technology platform",
            method,
        ),
    ]


def _company_universe(
    root: Path,
    method: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    members = [
        (_TARGET_ID, "included", "reason:exposure.dna.fixture.in_frame"),
        (
            "ent:company.synthetic_peer_a",
            "included",
            "reason:exposure.dna.fixture.in_frame",
        ),
        (
            "ent:company.synthetic_peer_b",
            "excluded",
            "reason:exposure.dna.fixture.out_of_scope",
        ),
        (
            "ent:company.synthetic_peer_c",
            "unmappable",
            "reason:exposure.dna.fixture.identity_unresolved",
        ),
    ]
    frame = canonical.seal_record(
        {
            "object_type": "universe_frame",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "universe_id": "universe:exposure.dna.fixture.companies",
            "entity_type": "company",
            "reference_date": "2026-08-08",
            "source_evidence_id": _EVIDENCE_ID,
            "source_version": "synthetic-v1",
            "extraction_query": "all four rows in the synthetic company frame",
            "extracted_at": "2026-08-08T11:30:00Z",
            "entity_ids": sorted(item[0] for item in members),
        }
    )
    frame_path = root / "frames" / "exposure_dna_company_frame.json"
    _write_json(frame_path, frame)
    status_counts = Counter(item[1] for item in members)
    universe = canonical.seal_record(
        {
            "object_type": "universe_release",
            "schema_version": "1.0.0",
            "universe_release_id": _COMPANY_UNIVERSE_ID,
            "record_sha256": "0" * 64,
            "lifecycle": _lifecycle(),
            "universe_id": "universe:exposure.dna.fixture.companies",
            "version": "1.0.0",
            "name": "Synthetic four-company Exposure DNA frame",
            "entity_type": "company",
            "reference_date": "2026-08-08",
            "denominator_definition": "Every row in the four-company synthetic frame.",
            "inclusion_rule": {
                "rule_id": method["method_id"],
                "version": method["version"],
                "implementation_path": "rules/exposure_dna_company_universe.py",
                "implementation_sha256": method["implementation_sha256"],
                "documentation_path": "rules/exposure_dna_company_universe.md",
            },
            "frame_artifact": {
                "path": str(frame_path.relative_to(root)),
                "sha256": _sha(frame_path),
                "format": "igrm_universe_frame_v1",
            },
            "source_evidence_ids": [_EVIDENCE_ID],
            "members": [
                {
                    "entity_id": entity_id,
                    "status": status,
                    "reason_code": reason,
                    "assessed_on": "2026-08-08",
                }
                for entity_id, status, reason in members
            ],
            "counts": {
                "total_eligible": len(members),
                "included": status_counts["included"],
                "excluded": status_counts["excluded"],
                "unmappable": status_counts["unmappable"],
                "stale": status_counts["stale"],
            },
            "provenance": _provenance(method),
        }
    )
    return universe, frame_path


def _fixture_edges(method: dict[str, Any], vintage: Literal["before", "after"]) -> list[dict[str, Any]]:
    input_share = 40.0 if vintage == "before" else 45.0
    rows = [
        _edge(
            "edg:exposure.dna.fixture.crude_company.001",
            "ent:commodity.synthetic_crude",
            _TARGET_ID,
            "input_dependency",
            method,
            quantification_status="quantified",
            magnitude=_measure(
                input_share,
                "percent_of_input_volume",
                "total synthetic input volume in the period",
                "2026-01-01",
                "2026-06-30",
            ),
            effective_start="2026-06-30",
        ),
        _edge(
            "edg:exposure.dna.fixture.origin_company.001",
            "ent:country.synthetic_origin",
            _TARGET_ID,
            "supplier_concentration",
            method,
            quantification_status="quantified",
            magnitude=_measure(
                28.0,
                "percent_of_procurement_value",
                "total synthetic procurement value in the period",
                "2026-01-01",
                "2026-06-30",
            ),
            effective_start="2026-06-30",
        ),
        _edge(
            "edg:exposure.dna.fixture.port_company.001",
            "ent:port.synthetic_gateway",
            _TARGET_ID,
            "freight_dependence",
            method,
            quantification_status="qualitative",
            magnitude=None,
        ),
        _edge(
            "edg:exposure.dna.fixture.route_company.001",
            "ent:route.synthetic_sea_lane",
            _TARGET_ID,
            "route_dependency",
            method,
            quantification_status="quantified",
            magnitude=_measure(
                60.0,
                "percent_of_routed_volume",
                "total synthetic routed volume in May 2026",
                "2026-05-01",
                "2026-05-31",
            ),
            observed_at="2026-06-01T00:00:00Z",
            effective_start="2026-05-31",
        ),
        _edge(
            "edg:exposure.dna.fixture.company_sector.001",
            _TARGET_ID,
            "ent:sector.synthetic_manufacturing",
            "operational_presence",
            method,
            quantification_status="qualitative",
            magnitude=None,
            exposure_direction="non_directional",
        ),
        _edge(
            "edg:exposure.dna.fixture.company_state.001",
            _TARGET_ID,
            "ent:state.synthetic_coast",
            "policy_jurisdiction",
            method,
            quantification_status="qualitative",
            magnitude=None,
            exposure_direction="jurisdictional",
        ),
        _edge(
            "edg:exposure.dna.fixture.technology_company.001",
            "ent:technology.synthetic_platform",
            _TARGET_ID,
            "technology_dependency",
            method,
            quantification_status="qualitative",
            magnitude=None,
        ),
    ]
    if vintage == "after":
        rows.append(
            _edge(
                "edg:exposure.dna.fixture.grid_company.001",
                "ent:critical_asset.synthetic_grid",
                _TARGET_ID,
                "energy_dependence",
                method,
                quantification_status="unknown",
                magnitude=None,
            )
        )
    return rows


def _append_objects(
    fixture: oges_fixture.Fixture,
    documents: list[dict[str, Any]],
) -> dict[str, Path]:
    manifest = _read_json(fixture.manifest)
    paths: dict[str, Path] = {}
    additions = Counter[str]()
    for document in documents:
        object_type = cast(str, document["object_type"])
        object_id = cast(str, document[canonical._ID_FIELD[object_type]])
        path = fixture.root / "canonical" / f"{object_id.replace(':', '__')}.json"
        _write_json(path, document)
        paths[object_id] = path
        manifest["objects"].append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "path": str(path.relative_to(fixture.root)),
                "file_sha256": _sha(path),
                "record_sha256": document["record_sha256"],
            }
        )
        additions[object_type] += 1
    manifest["objects"].sort(key=lambda row: (row["object_type"], row["object_id"]))
    for object_type, count in additions.items():
        manifest["counts"][object_type] += count
    _write_json(fixture.manifest, manifest)
    return paths


def _finalize_manifest(
    fixture: oges_fixture.Fixture,
    vintage: Literal["before", "after"],
) -> None:
    manifest = _read_json(fixture.manifest)
    manifest["release_id"] = f"rel:exposure.dna.fixture.{vintage}"
    manifest["generated_at"] = (
        _BEFORE_GENERATED if vintage == "before" else _AFTER_GENERATED
    )
    manifest["method_registry_sha256"] = _sha(
        fixture.root / "governance" / "canonical_method_registry.json"
    )
    manifest = canonical.seal_record(manifest)
    _write_json(fixture.manifest, manifest)
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def build_fixture(
    destination: Path,
    vintage: Literal["before", "after"],
) -> DNAFixture:
    """Build and validate one signed synthetic Exposure DNA vintage."""

    base = oges_fixture.build_fixture(destination)
    _install_dna_contract(base.root)
    universe_method = _install_company_universe_method(base.root)
    direct_method = _registered_method(
        base.root,
        "method:oges.fixture.direct",
        "run:exposure.dna.fixture.direct.001",
    )
    edge_method = _registered_method(
        base.root,
        "method:oges.fixture.exposure",
        "run:exposure.dna.fixture.edges.001",
    )
    entities = _fixture_entities(direct_method)
    universe, _ = _company_universe(base.root, universe_method)
    edges = _fixture_edges(edge_method, vintage)
    added_paths = _append_objects(base, [*entities, universe, *edges])
    _finalize_manifest(base, vintage)

    canonical.load_validated_release(
        base.manifest,
        root=base.root,
        schema_registry_path=base.root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=base.root / "governance" / "source_rights_registry.json",
        rights_signers_path=base.root / "governance" / "rights_signers.json",
        method_registry_path=base.root / "governance" / "canonical_method_registry.json",
        release_signers_path=base.root / "governance" / "release_signers.json",
    )
    return DNAFixture(
        root=base.root,
        manifest=base.manifest,
        target_entity_id=_TARGET_ID,
        objects={**base.objects, **added_paths},
        release_private_key=base.release_private_key,
    )


def _snapshot(fixture: DNAFixture) -> dict[str, Any]:
    root = fixture.root
    return exposure_dna.build_exposure_dna(
        fixture.manifest,
        fixture.target_entity_id,
        root=root,
        schema_registry_path=root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=root / "governance" / "source_rights_registry.json",
        rights_signers_path=root / "governance" / "rights_signers.json",
        method_registry_path=root / "governance" / "canonical_method_registry.json",
        release_signers_path=root / "governance" / "release_signers.json",
        dna_registry_path=root / "governance" / "exposure_dna_registry.json",
    )


def build_demo() -> dict[str, Any]:
    """Return a deterministic synthetic two-vintage public demo."""

    with tempfile.TemporaryDirectory(prefix="igrm-dna-before-") as before_tmp:
        with tempfile.TemporaryDirectory(prefix="igrm-dna-after-") as after_tmp:
            before_fixture = build_fixture(Path(before_tmp), "before")
            after_fixture = build_fixture(Path(after_tmp), "after")
            before = _snapshot(before_fixture)
            after = _snapshot(after_fixture)
            delta = exposure_dna.compare_exposure_dna(
                before_fixture.manifest,
                after_fixture.manifest,
                _TARGET_ID,
                before_root=before_fixture.root,
                after_root=after_fixture.root,
            )
    return {
        "_meta": {
            "schema": "igrm-exposure-dna-demo-v1",
            "generated": _AFTER_GENERATED,
            "date": "2026-08-08",
            "what": "Deterministic synthetic two-vintage India Exposure DNA conformance vector.",
            "scope": "synthetic_test_vector_only",
            "production_release": False,
            "real_entity_source_rights_or_exposure_claims": False,
            "scalar_score_computed": False,
            "license": "CC BY 4.0",
            "citation": "Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/",
            "source": "https://igrm.in/data/exposure_dna_demo.json",
            "codebook": "https://igrm.in/standard.html",
            "method": "method:igrm.exposure_dna@1.0.0",
        },
        "synthetic_labels": {
            _TARGET_ID: "Synthetic India Anchor Limited",
            "ent:commodity.synthetic_crude": "Synthetic crude input",
            "ent:country.synthetic_origin": "Synthetic origin country",
            "ent:port.synthetic_gateway": "Synthetic gateway port",
            "ent:route.synthetic_sea_lane": "Synthetic sea lane",
            "ent:sector.synthetic_manufacturing": "Synthetic manufacturing sector",
            "ent:state.synthetic_coast": "Synthetic coastal state",
            "ent:technology.synthetic_platform": "Synthetic technology platform",
            "ent:critical_asset.synthetic_grid": "Synthetic grid asset",
        },
        "before_snapshot": before,
        "after_snapshot": after,
        "delta": delta,
    }


def main() -> None:
    _write_json(PUBLIC_OUTPUT, build_demo())
    print(PUBLIC_OUTPUT)


if __name__ == "__main__":
    main()
