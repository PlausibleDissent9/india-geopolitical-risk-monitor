from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from src import canonical_objects as canonical
from src import exposure_graph

from test_canonical_objects import _fixture, _rewrite_object

ROOT = Path(__file__).resolve().parents[1]


def _project(
    paths: dict[str, Any],
    *,
    event_id: str = "evt:test.policy.001",
    target_entity_id: str = "ent:commodity.crude_oil",
    max_hops: int = 4,
    max_paths: int = 25,
) -> dict[str, Any]:
    root = paths["root"]
    return exposure_graph.project_event_exposure(
        paths["manifest"],
        event_id,
        target_entity_id,
        max_hops=max_hops,
        max_paths=max_paths,
        root=root,
        schema_registry_path=root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=root / "governance" / "source_rights_registry.json",
        rights_signers_path=root / "governance" / "rights_signers.json",
        method_registry_path=root / "governance" / "canonical_method_registry.json",
        release_signers_path=root / "governance" / "release_signers.json",
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for nested in value.values()
            for key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def test_signed_release_projects_deterministic_exact_evidence_paths(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    first = _project(paths)
    second = _project(paths)

    assert first == second
    assert canonical.canonical_record_sha256(first) == first["record_sha256"]
    assert first["release"]["release_id"] == "rel:test.2026-08-08"
    assert first["release"]["release_signer_id"] == "signer:test.release"
    assert first["result"] == {
        "status": "paths_found",
        "returned_paths": 1,
        "truncated": False,
    }
    assert [path["edge_ids"] for path in first["paths"]] == [
        ["edg:test.iran_crude.001"],
    ]
    edge_path = first["paths"][0]
    assert edge_path["entity_ids"] == [
        "ent:country.iran",
        "ent:commodity.crude_oil",
    ]
    assert edge_path["hops"][0]["coverage"]["counts"] == {
        "total_eligible": 1,
        "included": 1,
        "excluded": 0,
        "unmappable": 0,
        "stale": 0,
    }
    assert first["evidence"] == [
        {
            "evidence_id": "evd:test.official.001",
            "record_sha256": json.loads(
                paths["objects"]["evd:test.official.001"].read_text()
            )["record_sha256"],
            "source_id": "test_source",
            "rights_use": "cite_metadata",
            "rights_decision_id": "test-decision-2026-08-08",
            "content_sha256": hashlib.sha256(b"synthetic official bytes").hexdigest(),
            "content_availability": "hash_metadata_only",
            "privacy_class": "public",
            "verification_status": "official_record",
        }
    ]
    assert first["rights"][0]["decision_artifact_sha256"]
    assert "structural_connection_not_causation" in first["limitations"]
    assert "exposure_not_realized_loss" in first["limitations"]


def test_projection_does_not_emit_values_labels_urls_or_confidence(tmp_path: Path) -> None:
    result = _project(_fixture(tmp_path))
    forbidden_keys = {
        "magnitude",
        "value",
        "unit",
        "denominator",
        "confidence",
        "canonical_label",
        "canonical_name",
        "title",
        "public_url",
        "artifact_path",
    }

    assert forbidden_keys.isdisjoint(_all_keys(result))
    encoded = json.dumps(result, sort_keys=True)
    assert "12.5" not in encoded
    assert "Synthetic policy action" not in encoded
    assert "Synthetic official action" not in encoded
    assert "https://example.test" not in encoded


def test_projection_revalidates_release_before_consuming_records(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    edge_path = paths["objects"]["edg:test.iran_crude.001"]
    edge_path.write_text(edge_path.read_text() + "\n", encoding="utf-8")

    with pytest.raises(canonical.CanonicalObjectError) as exc:
        _project(paths)
    assert exc.value.code == "release_object_file_digest_mismatch"


def test_reverse_relationship_is_not_inferred_from_semantic_direction(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def make_commodity_the_only_entry(document: dict[str, Any]) -> None:
        document["actor_entity_ids"] = ["ent:commodity.crude_oil"]
        document["affected_entity_ids"] = []
        document["locations"] = [
            {
                "entity_id": "ent:commodity.crude_oil",
                "role": "primary",
                "precision": "unknown",
                "evidence_ids": ["evd:test.official.001"],
            }
        ]

    _rewrite_object(paths, "evt:test.policy.001", make_commodity_the_only_entry)
    result = _project(paths, target_entity_id="ent:country.iran")

    assert result["result"] == {
        "status": "no_path",
        "returned_paths": 0,
        "truncated": False,
    }
    assert result["paths"] == []
    assert "stored_edge_direction_only" in result["limitations"]


def test_release_date_filter_is_explicit_and_does_not_forward_fill_edges(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _rewrite_object(
        paths,
        "evt:test.policy.001",
        lambda document: document.update(affected_entity_ids=[]),
    )
    _rewrite_object(
        paths,
        "edg:test.iran_crude.001",
        lambda document: document.update(effective_start="2026-08-09"),
    )
    result = _project(paths)

    assert result["query"]["temporal_basis"] == "canonical_release_effective_date"
    assert result["projection_counts"]["edge_records_projected"] == 0
    assert result["projection_counts"]["edge_records_temporal_excluded"] == 1
    assert result["result"]["status"] == "no_path"


def test_target_outside_its_effective_interval_is_refused(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _rewrite_object(
        paths,
        "ent:commodity.crude_oil",
        lambda document: document.update(
            effective_start="2026-01-01", effective_end="2026-08-07"
        ),
    )

    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(paths)
    assert exc.value.code == "target_entity_not_effective"


def test_superseded_and_future_targets_are_refused(tmp_path: Path) -> None:
    superseded = _fixture(tmp_path / "superseded")

    def supersede(document: dict[str, Any]) -> None:
        document["lifecycle"]["state"] = "superseded"
        document["lifecycle"]["superseded_by"] = "ent:commodity.crude_oil.2"

    _rewrite_object(superseded, "ent:commodity.crude_oil", supersede)
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(superseded)
    assert exc.value.code == "target_entity_not_effective"

    future = _fixture(tmp_path / "future")
    _rewrite_object(
        future,
        "ent:commodity.crude_oil",
        lambda document: document.update(effective_start="2026-08-09"),
    )
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(future)
    assert exc.value.code == "target_entity_not_effective"


def test_withdrawn_event_cannot_be_a_projection_entry(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    def withdraw(document: dict[str, Any]) -> None:
        document["record_status"] = "withdrawn"
        document["lifecycle"]["state"] = "withdrawn"

    _rewrite_object(paths, "evt:test.policy.001", withdraw)
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(paths)
    assert exc.value.code == "event_not_active"


def test_path_and_hop_bounds_fail_closed_and_truncation_is_visible(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(paths, max_hops=7)
    assert exc.value.code == "max_hops_invalid"
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(paths, max_hops=0)
    assert exc.value.code == "max_hops_invalid"
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _project(paths, max_paths=0)
    assert exc.value.code == "max_paths_invalid"

    entries = [{"entity_id": "ent:test.root", "effective_on_release": True}]
    adjacency = {
        "ent:test.root": [
            {
                "edge_id": f"edg:test.{index}",
                "target_entity_id": "ent:test.target",
            }
            for index in range(3)
        ]
    }
    found, truncated = exposure_graph._bounded_paths(
        adjacency,
        entries,
        "ent:test.target",
        max_hops=1,
        max_paths=2,
    )
    assert [path[2][0]["edge_id"] for path in found] == ["edg:test.0", "edg:test.1"]
    assert truncated is True


def test_event_root_identity_is_not_an_exposure_path() -> None:
    entries = [{"entity_id": "ent:test.target", "effective_on_release": True}]
    found, truncated = exposure_graph._bounded_paths(
        {},
        entries,
        "ent:test.target",
        max_hops=1,
        max_paths=2,
    )

    assert found == []
    assert truncated is False


def test_queued_traversal_states_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exposure_graph, "_MAX_EXPANSIONS", 2)
    entries = [{"entity_id": "ent:test.root", "effective_on_release": True}]
    adjacency = {
        "ent:test.root": [
            {"edge_id": "edg:test.0", "target_entity_id": "ent:test.one"},
            {"edge_id": "edg:test.1", "target_entity_id": "ent:test.two"},
        ]
    }

    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        exposure_graph._bounded_paths(
            adjacency,
            entries,
            "ent:test.missing",
            max_hops=1,
            max_paths=2,
        )
    assert exc.value.code == "traversal_budget_exceeded"


def test_committed_projection_contract_is_deny_by_default_and_byte_exact() -> None:
    registry_path = ROOT / "governance" / "exposure_projection_registry.json"
    registry = json.loads(registry_path.read_text())
    row = registry["projection"]

    assert registry["default_policy"] == "deny"
    assert row["implementation_sha256"] == hashlib.sha256(
        (ROOT / row["implementation_path"]).read_bytes()
    ).hexdigest()
    assert row["output_schema_sha256"] == hashlib.sha256(
        (ROOT / row["output_schema_path"]).read_bytes()
    ).hexdigest()
    assert row["common_schema_sha256"] == hashlib.sha256(
        (ROOT / row["common_schema_path"]).read_bytes()
    ).hexdigest()


def test_output_schema_refuses_undeclared_fields(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = _project(paths)
    release_day = exposure_graph._parse_day(
        result["release"]["effective_date"], "test_invalid_date"
    )
    _, _, validator = exposure_graph._load_projection_contract(release_day)
    result["claim"] = "not licensed"
    result = canonical.seal_record(result)

    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        exposure_graph._validate_output(result, validator)
    assert exc.value.code == "projection_output_schema_invalid"


def test_output_semantics_refuse_false_path_counts(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    result = _project(paths)
    release_day = exposure_graph._parse_day(
        result["release"]["effective_date"], "test_invalid_date"
    )
    _, _, validator = exposure_graph._load_projection_contract(release_day)
    result["result"]["returned_paths"] = 0
    result = canonical.seal_record(result)

    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        exposure_graph._validate_output(result, validator)
    assert exc.value.code == "projection_output_result_mismatch"
