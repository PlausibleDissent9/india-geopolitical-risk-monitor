"""Truth and denominator checks for the public World State Matrix."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from src import evolution_engine, world_state

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_exact_matrix_rebuild_and_complete_cell_partition() -> None:
    world_state.check()
    payload = world_state.build()
    denominator = payload["denominator"]
    assert denominator["geometry_members"] == 247
    assert denominator["country_level_layers"] == 14
    assert denominator["cells"] == 3458
    assert denominator["single_world_score"] == "prohibited"
    assert payload["_meta"]["date"] == payload["_meta"]["observation_vintage"]
    assert payload["_meta"]["generated"] == (
        payload["_meta"]["observation_vintage"] + "T00:00:00Z"
    )
    assert payload["_meta"]["contract_effective"] == "2026-08-09"
    assert len(payload["members"]) == 247
    assert len(payload["layers"]) == 14

    layer_ids = {row["layer_id"] for row in payload["layers"]}
    for member in payload["members"]:
        assert set(member["layer_states"]) == layer_ids
        assert set(member["layer_states"].values()) <= {
            world_state.OBSERVED,
            world_state.MEMBER_UNAVAILABLE,
            world_state.LAYER_UNAVAILABLE,
        }


def test_only_existing_public_observations_are_populated() -> None:
    payload = world_state.build()
    observations = payload["observations"]
    assert set(observations) == {"india_partner_event_context"}
    assert len(observations["india_partner_event_context"]) == 193
    layers = {row["layer_id"]: row for row in payload["layers"]}
    assert layers["india_partner_event_context"]["observed_members"] == 193
    assert layers["india_partner_event_context"]["unavailable_members"] == 54
    assert layers["india_partner_event_context"]["coverage_share"] == 0.781377
    for layer_id, row in layers.items():
        if layer_id == "india_partner_event_context":
            continue
        assert row["observed_members"] == 0
        assert row["unavailable_members"] == 247
        assert row["coverage_share"] == 0.0
        assert row["source_payload"] is None


def test_zero_recent_events_preserve_an_unavailable_share() -> None:
    observation = world_state.build()["observations"][
        "india_partner_event_context"
    ]["PRY"]
    assert observation["event_count_recent_window"] == 0
    assert observation["conflict_share_recent_window"] is None


def test_zero_recent_events_cannot_publish_a_zero_conflict_share(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = json.loads(world_state.RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["partners"]["PRY"]["recent_conflict_share"] = 0.0
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(world_state, "RELATIONS_PATH", path)

    with pytest.raises(world_state.WorldStateError) as exc:
        world_state.build()
    assert exc.value.code == "partner_measure_invalid"


def test_partial_source_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = json.loads(world_state.RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["_meta"]["partial"] = True
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(world_state, "RELATIONS_PATH", path)

    with pytest.raises(world_state.WorldStateError) as exc:
        world_state.build()
    assert exc.value.code == "partner_payload_partial"


def test_publication_clock_follows_the_observation_vintage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = json.loads(world_state.RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["_meta"]["generated"] = "2026-08-10"
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(world_state, "RELATIONS_PATH", path)

    payload = world_state.build()
    assert payload["_meta"]["date"] == "2026-08-10"
    assert payload["_meta"]["generated"] == "2026-08-10T00:00:00Z"
    assert payload["_meta"]["contract_effective"] == "2026-08-09"


def test_invalid_observation_vintage_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = json.loads(world_state.RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["_meta"]["generated"] = "not-a-date"
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(world_state, "RELATIONS_PATH", path)

    with pytest.raises(world_state.WorldStateError) as exc:
        world_state.build()
    assert exc.value.code == "partner_observation_vintage_invalid"


def test_matrix_rebuild_has_no_generated_report_bootstrap_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing-generated-artifact.json"
    monkeypatch.setattr(evolution_engine, "CATALOG_PATH", missing)
    monkeypatch.setattr(evolution_engine, "CONTRACT_PATH", missing)
    monkeypatch.setattr(evolution_engine, "FRESHNESS_PATH", missing)
    monkeypatch.setattr(evolution_engine, "OUTPUT_PATH", missing)

    payload = world_state.build()
    assert payload["denominator"]["cells"] == 3458


def test_partner_outside_geometry_denominator_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relations = json.loads(world_state.RELATIONS_PATH.read_text(encoding="utf-8"))
    relations["partners"]["ZZZ"] = dict(relations["partners"]["AFG"])
    path = tmp_path / "map_relations.json"
    _write_json(path, relations)
    monkeypatch.setattr(world_state, "RELATIONS_PATH", path)

    with pytest.raises(world_state.WorldStateError) as exc:
        world_state.build()
    assert exc.value.code == "partner_outside_world_denominator"


def test_daily_and_ci_lanes_keep_the_matrix_current() -> None:
    daily = (ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert daily.index("python -m src.maps_data") < daily.index(
        "python -m src.world_state"
    ) < daily.index("python -m src.stamp_meta")
    assert "python -m src.world_state --check" in ci


def test_public_copy_refuses_complete_measurement_and_world_score_claims() -> None:
    payload = world_state.build()
    text = json.dumps(payload).lower()
    assert "not a world risk score" in text
    assert "does not mean every cell carries an observation" in text
    assert "complete measurement" in text
