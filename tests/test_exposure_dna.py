from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from src import canonical_objects as canonical
from src import exposure_dna, exposure_dna_fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dna_pair(tmp_path_factory: pytest.TempPathFactory) -> Iterator[
    tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture]
]:
    root = tmp_path_factory.mktemp("exposure-dna-pair")
    before = exposure_dna_fixture.build_fixture(root / "before", "before")
    after = exposure_dna_fixture.build_fixture(root / "after", "after")
    yield before, after


def _snapshot(fixture: exposure_dna_fixture.DNAFixture) -> dict[str, Any]:
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


def _compare(
    before: exposure_dna_fixture.DNAFixture,
    after: exposure_dna_fixture.DNAFixture,
) -> dict[str, Any]:
    return exposure_dna.compare_exposure_dna(
        before.manifest,
        after.manifest,
        before.target_entity_id,
        before_root=before.root,
        after_root=after.root,
    )


def _contract(fixture: exposure_dna_fixture.DNAFixture) -> tuple[Any, ...]:
    manifest = json.loads(fixture.manifest.read_text())
    release_day = exposure_dna._parse_day(
        manifest["effective_date"], "test_release_day_invalid"
    )
    return exposure_dna._load_contract(
        fixture.root,
        fixture.root / "governance" / "exposure_dna_registry.json",
        release_day,
    )


def _rewrite_object(
    fixture: exposure_dna_fixture.DNAFixture,
    object_id: str,
    mutate: Any,
) -> None:
    path = fixture.objects[object_id]
    document = json.loads(path.read_text())
    mutate(document)
    document = canonical.seal_record(document)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(fixture.manifest.read_text())
    row = next(item for item in manifest["objects"] if item["object_id"] == object_id)
    row["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    row["record_sha256"] = document["record_sha256"]
    manifest = canonical.seal_record(manifest)
    fixture.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    signature = fixture.root / manifest["release_signature_path"]
    signature.write_bytes(fixture.release_private_key.sign(fixture.manifest.read_bytes()))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def test_signed_snapshot_is_deterministic_coverage_bounded_and_non_scalar(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    _, after = dna_pair
    first = _snapshot(after)
    second = _snapshot(after)

    assert first == second
    assert canonical.canonical_record_sha256(first) == first["record_sha256"]
    assert first["target"]["entity_id"] == after.target_entity_id
    assert first["target"]["entity_type"] == "company"
    assert first["counts"] == {
        "direct_edges": 8,
        "incoming_edges": 6,
        "outgoing_edges": 2,
        "quantified_edges": 3,
        "qualitative_edges": 4,
        "unknown_edges": 1,
        "current_edges": 7,
        "stale_edges": 1,
        "unknown_freshness_edges": 0,
        "target_universes": 1,
    }
    assert first["result"] == {
        "status": "fingerprint_present",
        "scalar_score_computed": False,
        "public_claim_state": "requires_claim_bundle",
    }
    assert first["target_universes"][0]["counts"] == {
        "total_eligible": 4,
        "included": 2,
        "excluded": 1,
        "unmappable": 1,
        "stale": 0,
    }
    assert first["target_universes"][0]["member_status"] == "included"


def test_components_keep_original_units_and_do_not_create_composite(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    snapshot = _snapshot(dna_pair[1])
    measures = [edge["magnitude"] for edge in snapshot["edges"] if edge["magnitude"]]

    assert {measure["unit"] for measure in measures} == {
        "percent_of_input_volume",
        "percent_of_procurement_value",
        "percent_of_routed_volume",
    }
    assert len({measure["denominator"] for measure in measures}) == 3
    assert "score" not in _all_keys(snapshot)
    assert "aggregate" not in _all_keys(snapshot)
    assert snapshot["result"]["scalar_score_computed"] is False


def test_dimensions_partition_every_edge_exactly_once(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    snapshot = _snapshot(dna_pair[1])
    assigned = [edge_id for row in snapshot["dimensions"] for edge_id in row["edge_ids"]]

    assert len(snapshot["dimensions"]) == 5
    assert sorted(assigned) == sorted(edge["edge_id"] for edge in snapshot["edges"])
    assert len(assigned) == len(set(assigned))
    assert all(row["counts"]["edges"] == len(row["edge_ids"]) for row in snapshot["dimensions"])


def test_freshness_names_current_stale_and_unknown_policy() -> None:
    edge = {"edge_id": "edg:test.one", "observed_at": "2026-07-01T00:00:00Z", "evidence_ids": ["evd:test.one"]}
    evidence = {"evd:test.one": {"source_id": "source:test"}}
    generated = exposure_dna._parse_time("2026-08-08T00:00:00Z", "test_time")

    stale = exposure_dna._freshness_row(edge, evidence, {"source:test": 30}, generated)
    unknown = exposure_dna._freshness_row(edge, evidence, {"source:test": None}, generated)

    assert stale["status"] == "stale"
    assert stale["max_current_age_days"] == 30
    assert unknown["status"] == "unknown_policy"
    assert unknown["max_current_age_days"] is None


def test_two_signed_vintages_report_one_addition_one_revision_and_six_unchanged(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    before, after = dna_pair
    first = _compare(before, after)
    second = _compare(before, after)

    assert first == second
    assert canonical.canonical_record_sha256(first) == first["record_sha256"]
    assert first["counts"] == {
        "added_edges": 1,
        "removed_edges": 0,
        "revised_edges": 1,
        "unchanged_edges": 6,
        "opened_gaps": 1,
        "resolved_gaps": 0,
    }
    assert first["edge_changes"]["added"][0]["edge_id"].endswith("grid_company.001")
    assert first["edge_changes"]["revised"][0]["changed_aspects"] == [
        "quantification",
        "freshness",
    ]
    assert first["gap_changes"]["opened"] == [
        "unknown_quantification:edg:exposure.dna.fixture.grid_company.001"
    ]
    assert first["gap_changes"]["persistent"] == [
        "stale_edge:edg:exposure.dna.fixture.route_company.001"
    ]
    assert first["result"]["causal_interpretation_performed"] is False


def test_release_order_cannot_be_reversed(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    before, after = dna_pair
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        _compare(after, before)
    assert exc.value.code == "dna_comparison_order_invalid"


def test_country_is_an_event_origin_not_a_supported_fingerprint_target(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    after = dna_pair[1]
    root = after.root
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna.build_exposure_dna(
            after.manifest,
            "ent:country.synthetic_origin",
            root=root,
            schema_registry_path=root / "governance" / "canonical_schema_registry.json",
            rights_registry_path=root / "governance" / "source_rights_registry.json",
            rights_signers_path=root / "governance" / "rights_signers.json",
            method_registry_path=root / "governance" / "canonical_method_registry.json",
            release_signers_path=root / "governance" / "release_signers.json",
            dna_registry_path=root / "governance" / "exposure_dna_registry.json",
        )
    assert exc.value.code == "dna_target_type_not_supported"


def test_release_object_tamper_is_refused_before_projection(tmp_path: Path) -> None:
    fixture = exposure_dna_fixture.build_fixture(tmp_path / "tampered", "after")
    path = fixture.objects["edg:exposure.dna.fixture.crude_company.001"]
    path.write_text(path.read_text() + "\n", encoding="utf-8")

    with pytest.raises(canonical.CanonicalObjectError) as exc:
        _snapshot(fixture)
    assert exc.value.code == "release_object_file_digest_mismatch"


def test_running_implementation_and_registry_source_hash_are_mutually_checked(
    tmp_path: Path,
) -> None:
    fixture = exposure_dna_fixture.build_fixture(tmp_path / "source-drift", "after")
    source = fixture.root / "src" / "exposure_dna.py"
    source.write_text(source.read_text() + "\n", encoding="utf-8")

    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        _snapshot(fixture)
    assert exc.value.code == "dna_implementation_digest_mismatch"


def test_schema_hash_maximum_and_dimension_policy_are_hardcoded_not_self_attested(
    tmp_path: Path,
) -> None:
    cases = {
        "schema": lambda registry: registry["engine"].update(output_schema_sha256="f" * 64),
        "maximum": lambda registry: registry["engine"].update(max_direct_edges=6000),
        "dimension": lambda registry: registry["dimensions"][0].update(label="Rewritten"),
    }
    for name, mutate in cases.items():
        fixture = exposure_dna_fixture.build_fixture(tmp_path / name, "after")
        registry_path = fixture.root / "governance" / "exposure_dna_registry.json"
        registry = json.loads(registry_path.read_text())
        mutate(registry)
        registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
        with pytest.raises(exposure_dna.ExposureDNAError):
            _snapshot(fixture)


def test_snapshot_semantic_validator_refuses_resealed_counts_dimensions_and_freshness(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    after = dna_pair[1]
    _, _, validator, dimensions = _contract(after)

    bad_counts = _snapshot(after)
    bad_counts["counts"]["direct_edges"] = 0
    bad_counts = canonical.seal_record(bad_counts)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_snapshot(bad_counts, validator, dimensions)
    assert exc.value.code == "dna_snapshot_counts_invalid"

    bad_dimensions = _snapshot(after)
    bad_dimensions["dimensions"][0]["edge_ids"] = []
    bad_dimensions = canonical.seal_record(bad_dimensions)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_snapshot(bad_dimensions, validator, dimensions)
    assert exc.value.code == "dna_snapshot_dimensions_invalid"

    bad_freshness = _snapshot(after)
    bad_freshness["edges"][0]["freshness"]["status"] = "stale"
    bad_freshness = canonical.seal_record(bad_freshness)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_snapshot(bad_freshness, validator, dimensions)
    assert exc.value.code == "dna_snapshot_freshness_invalid"

    bad_threshold = _snapshot(after)
    bad_threshold["edges"][0]["freshness"]["max_current_age_days"] = 999
    bad_threshold = canonical.seal_record(bad_threshold)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_snapshot(bad_threshold, validator, dimensions)
    assert exc.value.code == "dna_snapshot_freshness_invalid"

    bad_incidence = _snapshot(after)
    bad_incidence["edges"][0]["counterpart"]["entity_id"] = after.target_entity_id
    bad_incidence = canonical.seal_record(bad_incidence)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_snapshot(bad_incidence, validator, dimensions)
    assert exc.value.code == "dna_snapshot_edge_incidence_invalid"


def test_delta_semantic_validator_refuses_reordered_change_aspects(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    before, after = dna_pair
    delta = _compare(before, after)
    _, _, validator, _ = _contract(after)
    delta["edge_changes"]["revised"][0]["changed_aspects"] = [
        "freshness",
        "quantification",
    ]
    delta = canonical.seal_record(delta)

    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_delta(delta, validator)
    assert exc.value.code == "dna_delta_change_partition_invalid"


def test_delta_semantic_validator_refuses_resealed_counts_and_gap_overlap(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    before, after = dna_pair
    _, _, validator, _ = _contract(after)

    bad_count = _compare(before, after)
    bad_count["counts"]["unchanged_edges"] = 0
    bad_count = canonical.seal_record(bad_count)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_delta(bad_count, validator)
    assert exc.value.code == "dna_delta_counts_invalid"

    bad_gaps = _compare(before, after)
    token = bad_gaps["gap_changes"]["persistent"][0]
    bad_gaps["gap_changes"]["opened"].append(token)
    bad_gaps["gap_changes"]["opened"].sort()
    bad_gaps = canonical.seal_record(bad_gaps)
    with pytest.raises(exposure_dna.ExposureDNAError) as exc:
        exposure_dna._validate_delta(bad_gaps, validator)
    assert exc.value.code == "dna_delta_gap_partition_invalid"


def test_engine_output_excludes_names_urls_titles_and_source_content(
    dna_pair: tuple[exposure_dna_fixture.DNAFixture, exposure_dna_fixture.DNAFixture],
) -> None:
    before, after = dna_pair
    documents = [_snapshot(before), _snapshot(after), _compare(before, after)]
    forbidden = {"canonical_name", "title", "public_url", "artifact_path", "content"}

    for document in documents:
        assert forbidden.isdisjoint(_all_keys(document))
        encoded = json.dumps(document, sort_keys=True)
        assert "Synthetic India Anchor Limited" not in encoded
        assert "https://example.test" not in encoded


def test_public_demo_is_exact_synthetic_and_generator_idempotent() -> None:
    committed = json.loads((ROOT / "docs" / "data" / "exposure_dna_demo.json").read_text())
    rebuilt = exposure_dna_fixture.build_demo()

    assert rebuilt == committed
    assert committed["_meta"]["scope"] == "synthetic_test_vector_only"
    assert committed["_meta"]["production_release"] is False
    assert committed["_meta"]["real_entity_source_rights_or_exposure_claims"] is False
    assert committed["_meta"]["scalar_score_computed"] is False
    assert committed["after_snapshot"]["result"]["public_claim_state"] == "requires_claim_bundle"


def test_public_surface_is_bounded_catalogued_and_machine_listed() -> None:
    page = (ROOT / "docs" / "dna.html").read_text(encoding="utf-8")
    assert "implemented synthetic conformance foundation" in page
    assert "not a production map" in page
    assert "A fingerprint, not a score" in page
    assert "not real exposure coverage" in page
    assert "exposure_dna_demo.json" in page
    assert "dna.js" in page
    script = (ROOT / "docs" / "dna.js").read_text(encoding="utf-8")
    assert "gapCount(snapshot.gaps)" in script
    assert "gapCount(snapshot)" not in script
    assert "innerHTML" not in script
    assert 'setAttribute("aria-pressed", selected ? "true" : "false")' in script

    catalog = json.loads(
        (ROOT / "design" / "public_product_catalog.json").read_text(encoding="utf-8")
    )
    row = next(row for row in catalog["routes"] if row["path"] == "dna.html")
    assert row["status"] == "public_draft"
    assert row["pillar_id"] == "atlas"
    assert "dna.html" in catalog["protected_routes"]

    contract = json.loads(
        (ROOT / "docs" / "data" / "api_contract.json").read_text(encoding="utf-8")
    )
    endpoints = {row["path"]: row for row in contract["endpoints"]}
    assert endpoints["data/exposure_dna_demo.json"]["stability"] == "stable"
    assert (
        endpoints["schemas/exposure-dna.schema.json"]["stability"]
        == "static synthetic foundation 1.0.0"
    )
    assert (ROOT / "docs" / "schemas" / "exposure-dna.schema.json").read_bytes() == (
        ROOT / "schemas" / "exposure-dna.schema.json"
    ).read_bytes()


def test_public_exposure_dna_script_parses_when_node_is_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available in this environment")
    result = subprocess.run(
        [node, "--check", str(ROOT / "docs" / "dna.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_committed_contract_hashes_are_exact_and_dimension_partition_is_complete() -> None:
    registry = json.loads((ROOT / "governance" / "exposure_dna_registry.json").read_text())
    row = registry["engine"]

    assert row["implementation_sha256"] == hashlib.sha256(
        (ROOT / row["implementation_path"]).read_bytes()
    ).hexdigest()
    assert row["output_schema_sha256"] == hashlib.sha256(
        (ROOT / row["output_schema_path"]).read_bytes()
    ).hexdigest()
    assert row["common_schema_sha256"] == hashlib.sha256(
        (ROOT / row["common_schema_path"]).read_bytes()
    ).hexdigest()
    assigned = [edge_type for dimension in registry["dimensions"] for edge_type in dimension["edge_types"]]
    assert sorted(assigned) == sorted(exposure_dna._EDGE_TYPES)
    assert len(assigned) == len(set(assigned))


def test_cli_emits_machine_json_for_success_and_refusal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = exposure_dna_fixture.build_fixture(tmp_path / "cli", "after")
    exposure_dna.main(
        [
            "snapshot",
            str(fixture.manifest),
            fixture.target_entity_id,
            "--root",
            str(fixture.root),
        ]
    )
    success = json.loads(capsys.readouterr().out)
    assert success["object_type"] == "exposure_dna_snapshot"

    fixture.manifest.write_text(fixture.manifest.read_text() + "\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        exposure_dna.main(
            [
                "snapshot",
                str(fixture.manifest),
                fixture.target_entity_id,
                "--root",
                str(fixture.root),
            ]
        )
    assert exc.value.code == 2
    refusal = json.loads(capsys.readouterr().err)
    assert refusal == {
        "status": "refused",
        "stage": "canonical_release",
        "reason": "release_signature_invalid",
    }
