"""Adversarial tests for semantically separated eight-lane Sensor Fusion."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
from src import canonical_objects as canonical
from src import sensor_fusion
from src.sensor_fusion_fixture import SensorFixture, build_demo, build_fixture

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LANES = [
    "official",
    "news",
    "coded_event",
    "physical_transmission",
    "trade_transmission",
    "energy_transmission",
    "market_transmission",
    "public_attention",
]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kwargs(fixture: SensorFixture) -> dict[str, Path]:
    root = fixture.root
    return {
        "root": root,
        "schema_registry_path": root / "governance" / "canonical_schema_registry.json",
        "rights_registry_path": root / "governance" / "source_rights_registry.json",
        "rights_signers_path": root / "governance" / "rights_signers.json",
        "method_registry_path": root / "governance" / "canonical_method_registry.json",
        "release_signers_path": root / "governance" / "release_signers.json",
        "fusion_registry_path": root / "governance" / "sensor_fusion_registry.json",
    }


def _fuse(
    fixture: SensorFixture,
    *,
    start: str = "2026-08-08T08:30:00Z",
    end: str = "2026-08-08T11:00:00Z",
    cutoff: str = "2026-08-08T13:00:00Z",
) -> dict[str, Any]:
    return sensor_fusion.fuse_event_sensors(
        fixture.manifest,
        fixture.event_id,
        start,
        end,
        cutoff,
        **_kwargs(fixture),
    )


def _mutate_lane_registry(fixture: SensorFixture, mutate: Callable[[dict[str, Any]], None]) -> None:
    lane_path = fixture.root / "governance" / "sensor_lane_registry.json"
    lanes = json.loads(lane_path.read_text(encoding="utf-8"))
    mutate(lanes)
    _write_json(lane_path, lanes)
    registry_path = fixture.root / "governance" / "sensor_fusion_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["fusion"]["lane_registry_sha256"] = _sha(lane_path)
    _write_json(registry_path, registry)


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for nested in value.values() for key in _all_keys(nested)}
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def test_complete_fixture_has_one_observation_in_each_exact_lane(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    result = _fuse(fixture)
    assert [row["lane_id"] for row in result["lanes"]] == EXPECTED_LANES
    assert [row["observation_count"] for row in result["lanes"]] == [1] * 8
    assert result["counts"] == {
        "registered_lanes": 8,
        "present_lanes": 8,
        "absent_lanes": 0,
        "event_evidence_links": 8,
        "eligible_observations": 8,
        "excluded_observations": 0,
    }
    assert result["coverage"] == {
        "denominator": "eight_registered_semantic_lanes",
        "observed_lane_ids": EXPECTED_LANES,
        "missing_lane_ids": [],
        "fraction": 1.0,
    }
    assert result["result"] == {
        "status": "matrix_complete",
        "semantic_join": "collation_only",
        "numeric_fusion_performed": False,
    }


def test_narrow_window_exposes_missing_lanes_instead_of_backfilling(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    result = _fuse(fixture, end="2026-08-08T09:05:00Z")
    assert result["coverage"]["observed_lane_ids"] == ["official"]
    assert result["coverage"]["missing_lane_ids"] == EXPECTED_LANES[1:]
    assert result["coverage"]["fraction"] == 0.125
    assert result["result"]["status"] == "matrix_partial"
    assert result["counts"]["excluded_observations"] == 7
    assert {row["reason"] for row in result["excluded_evidence"]} == {"outside_observation_window"}


def test_output_is_deterministic_structural_and_contains_no_evidence_content(
    tmp_path: Path,
) -> None:
    first = _fuse(build_fixture(tmp_path / "first"))
    second = _fuse(build_fixture(tmp_path / "second"))
    assert first == second
    forbidden = {
        "title",
        "authors",
        "public_url",
        "artifact_path",
        "magnitude",
        "value",
        "unit",
        "denominator_value",
        "probability",
        "risk_score",
        "forecast_value",
        "causal_claim",
    }
    assert forbidden.isdisjoint(_all_keys(first))
    serialized = json.dumps(first, sort_keys=True)
    assert "example.test" not in serialized
    assert "Synthetic official action" not in serialized
    assert "12.5" not in serialized


def test_unknown_and_ambiguous_source_roles_fail_closed(tmp_path: Path) -> None:
    unknown = build_fixture(tmp_path / "unknown")

    def remove_news_role(document: dict[str, Any]) -> None:
        lane = next(row for row in document["lanes"] if row["lane_id"] == "news")
        lane["source_roles"].remove("news_test_evidence")

    _mutate_lane_registry(unknown, remove_news_role)
    with pytest.raises(sensor_fusion.SensorFusionError) as missing:
        _fuse(unknown)
    assert missing.value.code == "sensor_source_role_unregistered"

    ambiguous = build_fixture(tmp_path / "ambiguous")

    def duplicate_official_role(document: dict[str, Any]) -> None:
        lane = next(row for row in document["lanes"] if row["lane_id"] == "news")
        lane["source_roles"].append("official_test_evidence")

    _mutate_lane_registry(ambiguous, duplicate_official_role)
    with pytest.raises(sensor_fusion.SensorFusionError) as duplicate:
        _fuse(ambiguous)
    assert duplicate.value.code == "sensor_source_role_ambiguous"


def test_lane_cannot_accept_an_incompatible_evidence_type(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "bundle")

    def forbid_news_article(document: dict[str, Any]) -> None:
        lane = next(row for row in document["lanes"] if row["lane_id"] == "news")
        lane["permitted_evidence_types"] = ["web_page"]

    _mutate_lane_registry(fixture, forbid_news_article)
    with pytest.raises(sensor_fusion.SensorFusionError) as exc:
        _fuse(fixture)
    assert exc.value.code == "sensor_evidence_type_incompatible_with_lane"


@pytest.mark.parametrize(
    ("start", "end", "cutoff", "reason"),
    [
        (
            "2026-08-08T08:30:00Z",
            "2026-08-08T11:00:00Z",
            "2026-08-08T12:59:59Z",
            "sensor_cutoff_must_equal_release_generation",
        ),
        (
            "2026-08-08T08:30:00Z",
            "2026-08-08T13:00:01Z",
            "2026-08-08T13:00:00Z",
            "sensor_time_window_invalid",
        ),
        (
            "2026-08-08T11:00:00Z",
            "2026-08-08T08:30:00Z",
            "2026-08-08T13:00:00Z",
            "sensor_time_window_invalid",
        ),
    ],
)
def test_temporal_boundary_refuses_invalid_queries(
    tmp_path: Path, start: str, end: str, cutoff: str, reason: str
) -> None:
    fixture = build_fixture(tmp_path / reason)
    with pytest.raises(sensor_fusion.SensorFusionError) as exc:
        _fuse(fixture, start=start, end=end, cutoff=cutoff)
    assert exc.value.code == reason


def test_registered_bounds_and_duplicate_roles_are_enforced(tmp_path: Path) -> None:
    bounded = build_fixture(tmp_path / "bounded")
    registry_path = bounded.root / "governance" / "sensor_fusion_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["fusion"]["max_event_evidence_links"] = 7
    _write_json(registry_path, registry)
    with pytest.raises(sensor_fusion.SensorFusionError) as bound:
        _fuse(bounded)
    assert bound.value.code == "sensor_event_evidence_bound_exceeded"

    with pytest.raises(sensor_fusion.SensorFusionError) as duplicate:
        sensor_fusion._link_roles(
            {
                "evidence_links": [
                    {"evidence_id": "evd:test.001", "role": "context"},
                    {"evidence_id": "evd:test.001", "role": "context"},
                ]
            }
        )
    assert duplicate.value.code == "sensor_event_evidence_role_duplicate"


@pytest.mark.parametrize(
    ("relative", "reason"),
    [
        (
            "governance/sensor_lane_registry.json",
            "sensor_lane_registry_digest_mismatch",
        ),
        (
            "schemas/sensor-fusion.schema.json",
            "sensor_output_schema_digest_mismatch",
        ),
        (
            "src/sensor_fusion.py",
            "sensor_fusion_implementation_digest_mismatch",
        ),
    ],
)
def test_registered_contract_bytes_are_rehashed(tmp_path: Path, relative: str, reason: str) -> None:
    fixture = build_fixture(tmp_path / relative.replace("/", "_"))
    path = fixture.root / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(sensor_fusion.SensorFusionError) as exc:
        _fuse(fixture)
    assert exc.value.code == reason


def test_signed_canonical_rights_snapshot_is_reverified(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "rights")
    path = fixture.root / "governance" / "source_rights_registry.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(canonical.CanonicalObjectError) as exc:
        _fuse(fixture)
    assert exc.value.code == "release_rights_registry_digest_mismatch"


def test_public_demo_is_exact_generated_synthetic_contract() -> None:
    public = json.loads(
        (ROOT / "docs" / "data" / "sensor_fusion_demo.json").read_text(encoding="utf-8")
    )
    assert public == build_demo()
    assert public["_meta"]["scope"] == "synthetic_test_vector_only"
    assert public["_meta"]["production_release"] is False
    assert public["_meta"]["real_source_or_rights_claims"] is False
    assert public["complete_matrix"]["counts"]["present_lanes"] == 8
    assert public["narrow_window_matrix"]["counts"]["present_lanes"] == 1


def test_public_surface_states_the_production_boundary_and_is_catalogued() -> None:
    page = (ROOT / "docs" / "sensors.html").read_text(encoding="utf-8")
    assert "implemented synthetic conformance foundation" in page
    assert "not live multi-source intelligence" in page
    assert "performs no cross-lane" in page
    assert "not a live world-state engine" in page
    assert "sensor_fusion_demo.json" in page
    assert "sensors.js" in page
    catalog = json.loads(
        (ROOT / "design" / "public_product_catalog.json").read_text(encoding="utf-8")
    )
    row = next(row for row in catalog["routes"] if row["path"] == "sensors.html")
    assert row["status"] == "public_draft"
    assert "sensors.html" in catalog["protected_routes"]
    assert (ROOT / "docs" / "schemas" / "sensor-fusion.schema.json").read_bytes() == (
        ROOT / "schemas" / "sensor-fusion.schema.json"
    ).read_bytes()


def test_public_sensor_script_parses_when_node_is_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available in this environment")
    result = subprocess.run(
        [node, "--check", str(ROOT / "docs" / "sensors.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_emits_structural_json_and_stable_refusal(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    command = [
        sys.executable,
        "-m",
        "src.sensor_fusion",
        str(fixture.manifest),
        fixture.event_id,
        "--root",
        str(fixture.root),
        "--window-start",
        "2026-08-08T08:30:00Z",
        "--window-end",
        "2026-08-08T11:00:00Z",
    ]
    success = subprocess.run(
        [*command, "--knowledge-cutoff", "2026-08-08T13:00:00Z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout)["counts"]["present_lanes"] == 8

    refusal = subprocess.run(
        [*command, "--knowledge-cutoff", "2026-08-08T12:59:59Z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refusal.returncode == 2
    assert json.loads(refusal.stderr) == {
        "status": "refused",
        "stage": "sensor_fusion",
        "reason": "sensor_cutoff_must_equal_release_generation",
    }


def test_reordered_or_renamed_lane_partition_cannot_validate() -> None:
    document = build_demo()["complete_matrix"]
    altered = copy.deepcopy(document)
    altered["lanes"] = list(reversed(altered["lanes"]))
    altered = canonical.seal_record(altered)
    contract = sensor_fusion._load_contract(
        ROOT, ROOT / "governance" / "sensor_fusion_registry.json"
    )
    with pytest.raises(sensor_fusion.SensorFusionError) as exc:
        sensor_fusion._validate_output(altered, contract)
    assert exc.value.code == "sensor_output_lane_partition_invalid"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("rename_lane_label", "sensor_output_lane_semantics_invalid"),
        ("move_source_role", "sensor_output_lane_semantics_invalid"),
        ("inflate_event_link_count", "sensor_output_counts_invalid"),
        ("reverse_exclusions", "sensor_output_evidence_partition_invalid"),
    ],
)
def test_resealed_output_cannot_rewrite_registered_semantics_or_counts(
    mutation: str, reason: str
) -> None:
    document = copy.deepcopy(
        build_demo()[
            "narrow_window_matrix" if mutation == "reverse_exclusions" else "complete_matrix"
        ]
    )
    if mutation == "rename_lane_label":
        document["lanes"][0]["label"] = "Official truth"
    elif mutation == "move_source_role":
        document["lanes"][0]["observations"][0]["source_role"] = "news_test_evidence"
    elif mutation == "inflate_event_link_count":
        document["counts"]["event_evidence_links"] = 9
    elif mutation == "reverse_exclusions":
        document["excluded_evidence"] = list(reversed(document["excluded_evidence"]))
    document = canonical.seal_record(document)
    contract = sensor_fusion._load_contract(
        ROOT, ROOT / "governance" / "sensor_fusion_registry.json"
    )
    with pytest.raises(sensor_fusion.SensorFusionError) as exc:
        sensor_fusion._validate_output(document, contract)
    assert exc.value.code == reason
