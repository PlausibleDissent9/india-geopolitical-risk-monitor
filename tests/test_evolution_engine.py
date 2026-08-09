"""Adversarial checks for the bounded Continuous Evolution observer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from src import evolution_engine

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_public_report_refuses_event_values_until_source_rights_are_signed() -> None:
    evolution_engine.check_report()
    report = evolution_engine.build_report()
    state = report["measured_state"]

    assert state["public_product_routes"] == {
        "registered": 36,
        "present": 36,
        "missing": [],
    }
    assert state["public_api_endpoints"] == {
        "registered": 116,
        "present": 116,
        "missing": [],
    }
    atlas = state["global_atlas"]
    assert atlas["country_area_geometries"] == 247
    assert atlas["india_partner_event_context_observed"] == 193
    assert atlas["india_partner_event_context_unavailable"] == 54
    assert len(atlas["unavailable_geometry_ids"]) == 54
    assert atlas["registered_layers"] == 15
    assert atlas["published_layers"] == 2
    assert atlas["registered_country_level_layers"] == 14
    assert atlas["published_country_level_layers"] == 1
    assert atlas["single_world_score"] == "prohibited"
    assert state["historical_intelligence"]["source_start"] == "1979-01"
    assert state["historical_intelligence"]["source_end"] == "2019-12"
    assert state["historical_intelligence"]["published_proxy_channels"] == 2
    assert state["historical_intelligence"]["capability_state"] == (
        "released_v1_bounded"
    )
    assert state["historical_intelligence"]["registered_calendar_periods"] == 4
    assert state["historical_intelligence"]["baseline_rows"] == 16
    assert state["historical_intelligence"]["structural_break_diagnostic_rows"] == 2
    assert state["historical_intelligence"]["analog_queries"] == 984
    assert state["historical_intelligence"]["analog_queries_available"] == 960
    assert state["historical_intelligence"]["human_authored_archetype_rows"] == 9
    ledger = state["global_event_episode_ledger"]
    assert ledger["artifact_status"] == "public_release_blocked_rights_review"
    assert ledger["frame_start"] is None
    assert ledger["frame_end"] is None
    assert ledger["calendar_days"] is None
    assert ledger["observed_aggregate_days"] is None
    assert ledger["legacy_unavailable_days"] is None
    assert ledger["detected_salience_episodes"] is None
    assert ledger["deduplicated_source_event_count"] is None
    assert ledger["canonical_geopolitical_event_count"] is None
    assert "no source-derived" in ledger["current_boundary"]
    assert "freshness_ledger" not in state
    capability = state["max_capability_attestation"]
    assert capability["capability_denominator"] == 38
    assert capability["denominator_status"] == (
        "proposed_launch_scope_not_founder_authorized"
    )
    assert capability["scope_authority"] == "proposed_unsigned"
    assert capability["state_counts"] == {
        "target_only": 21,
        "contract_only": 17,
        "synthetic_verified": 0,
        "real_bounded": 0,
        "externally_validated": 0,
        "operational": 0,
    }
    assert capability["gap_atoms"] == 38
    assert len(report["capability_attestations"]) == 38
    assert len(report["gap_atoms"]) == 38
    assert not any(
        row["computed_state"] == "operational"
        for row in report["capability_attestations"]
    )


def test_layer_registry_requires_truthful_publication_and_no_world_score() -> None:
    registry = json.loads(
        (ROOT / "governance" / "global_atlas_layers.json").read_text(
            encoding="utf-8"
        )
    )
    assert registry["composition_policy"]["single_world_score"] == "prohibited"
    assert registry["composition_policy"]["cross_domain_averaging"] == "prohibited"
    assert len(registry["layers"]) == 15
    assert len({row["layer_id"] for row in registry["layers"]}) == 15
    for row in registry["layers"]:
        if row["current_state"].startswith("published_"):
            assert row["source_payload"]
        else:
            assert row["source_payload"] is None
        assert row["missingness_rule"]
        assert row["prohibited_interpretation"]
        assert row["safety_rule"]


def test_high_risk_class_cannot_acquire_automatic_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = json.loads(evolution_engine.ENGINE_PATH.read_text(encoding="utf-8"))
    risk = next(
        row
        for row in engine["risk_classes"]
        if row["risk_class"] == "R3_method_claim_rights_or_security_boundary"
    )
    risk["automatic_authority"] = "may_prepare_and_test"
    path = tmp_path / "evolution_engine.json"
    _write_json(path, engine)
    monkeypatch.setattr(evolution_engine, "ENGINE_PATH", path)

    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "high_risk_automatic_authority_forbidden"


def test_static_program_cannot_call_released_history_merely_specified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = json.loads(evolution_engine.ENGINE_PATH.read_text(encoding="utf-8"))
    program = next(
        row
        for row in engine["strategic_programs"]
        if row["program_id"] == "historical_intelligence_activation"
    )
    program["state"] = "specified"
    path = tmp_path / "evolution_engine.json"
    _write_json(path, engine)
    monkeypatch.setattr(evolution_engine, "ENGINE_PATH", path)

    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "historical_intelligence_program_state_stale"


def test_unpublished_layer_cannot_smuggle_a_source_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(evolution_engine.LAYER_PATH.read_text(encoding="utf-8"))
    row = next(
        item
        for item in registry["layers"]
        if not item["current_state"].startswith("published_")
    )
    row["source_payload"] = "docs/data/latest.json"
    path = tmp_path / "global_atlas_layers.json"
    _write_json(path, registry)
    monkeypatch.setattr(evolution_engine, "LAYER_PATH", path)

    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "unpublished_layer_source_must_be_null"


def test_layer_index_state_is_a_closed_refusal_enum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(evolution_engine.LAYER_PATH.read_text(encoding="utf-8"))
    registry["layers"][0]["index_state"] = "published_index"
    path = tmp_path / "global_atlas_layers.json"
    path.write_text(json.dumps(registry), encoding="utf-8")
    monkeypatch.setattr(evolution_engine, "LAYER_PATH", path)

    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "layer_index_state_invalid"


def test_evolution_report_can_recreate_itself_but_not_ignore_other_missing_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = Path.is_file

    def only_evolution_missing(path: Path) -> bool:
        if path.resolve() == evolution_engine.OUTPUT_PATH.resolve():
            return False
        return original(path)

    monkeypatch.setattr(Path, "is_file", only_evolution_missing)
    assert evolution_engine.build_report()["_meta"]["partial"] is False

    def world_state_missing(path: Path) -> bool:
        if path.resolve() in {
            evolution_engine.OUTPUT_PATH.resolve(),
            (ROOT / "docs" / "data" / "world_state.json").resolve(),
        }:
            return False
        return original(path)

    monkeypatch.setattr(Path, "is_file", world_state_missing)
    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "api_endpoint_missing"


def test_hourly_audit_is_read_only_and_separates_live_health() -> None:
    audit = evolution_engine.build_runtime_audit(
        datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc)
    )
    freshness = json.loads(
        evolution_engine.FRESHNESS_PATH.read_text(encoding="utf-8")
    )
    assert audit["audited_at"] == "2026-08-09T12:00:00Z"
    assert audit["commit_publication_authority"] == "none"
    assert audit["automatic_change_authority"] == "none"
    assert audit["public_report_current"] is True
    assert audit["current_freshness_ledger"]["payloads"] == len(
        freshness["payloads"]
    )
    assert audit["runtime_input_sha256"].keys() == {"freshness"}
    assert "freshness" not in audit["capability_input_sha256"]


def test_released_observer_and_world_matrix_are_not_reported_as_pending() -> None:
    registry = json.loads(
        evolution_engine.ENGINE_PATH.read_text(encoding="utf-8")
    )
    assert registry["current_automation_boundary"]["hourly_observer"] == (
        "live_read_only"
    )
    report = evolution_engine.build_report()
    world = next(
        row for row in report["priority_queue"] if row["candidate_id"] == "world_state_matrix"
    )
    assert world["state"] == "released"
    assert "after publication" in world["next_gate"]
    history = next(
        row
        for row in report["priority_queue"]
        if row["candidate_id"] == "historical_intelligence_activation"
    )
    assert history["state"] == "released"
    assert "after publication" in history["next_gate"]
    assert history["evidence"]["analog_queries_available"] == 960


@pytest.mark.parametrize(
    "mutation",
    ["source_sha", "contract_sha", "implementation_sha", "baseline_rows"],
)
def test_evolution_refuses_a_historical_capability_claim_without_exact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    payload = json.loads(
        evolution_engine.HISTORICAL_INTELLIGENCE_PATH.read_text(encoding="utf-8")
    )
    if mutation == "baseline_rows":
        payload["regime_baselines"]["rows"] = []
    else:
        field = {
            "source_sha": "source_sha256",
            "contract_sha": "contract_sha256",
            "implementation_sha": "implementation_sha256",
        }[mutation]
        payload["_meta"][field] = "0" * 64
    path = tmp_path / "historical_intelligence.json"
    _write_json(path, payload)
    monkeypatch.setattr(evolution_engine, "HISTORICAL_INTELLIGENCE_PATH", path)

    with pytest.raises(evolution_engine.EvolutionError) as exc:
        evolution_engine.build_report()
    assert exc.value.code == "historical_intelligence_capability_invalid"


def test_hourly_workflow_observes_without_repository_authority() -> None:
    workflow = (ROOT / ".github" / "workflows" / "evolution.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "37 * * * *"' in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "fetch-depth: 0" in workflow
    assert "persist-credentials: false" in workflow
    assert "python -m src.evolution_engine --audit" in workflow
    assert "python -m src.evolution_engine --check" not in workflow
    assert "git diff --exit-code" in workflow
    for forbidden in ("git push", "git commit", "contents: write", "pull-requests: write"):
        assert forbidden not in workflow


def test_ci_enforces_the_public_capability_snapshot() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "python -m src.evolution_engine --check" in ci


def test_launch_contract_is_a_floor_and_history_is_an_active_program() -> None:
    spec = (ROOT / "IGRM_MAX_SPEC.md").read_text(encoding="utf-8").lower()
    design = (ROOT / "design" / "continuous_evolution.md").read_text(
        encoding="utf-8"
    ).lower()
    assert "minimum capability floor" in spec
    assert "not a capability ceiling" in spec
    assert "1979" in spec
    assert "structural break" in spec
    assert "hourly" in design
    assert "modify the repository or public site" in design
    assert "regime" in design


def test_category_architecture_and_independent_review_are_governing_surfaces() -> None:
    architecture = (ROOT / "design" / "category_architecture.md").read_text(
        encoding="utf-8"
    ).lower()
    review = (ROOT / "design" / "claude_adversarial_review_protocol.md").read_text(
        encoding="utf-8"
    ).lower()
    review_words = " ".join(review.split())
    engine = json.loads(evolution_engine.ENGINE_PATH.read_text(encoding="utf-8"))
    program_ids = {row["program_id"] for row in engine["strategic_programs"]}

    for plane in (
        "evidence mesh",
        "observation twin",
        "global event and episode ledger",
        "world state matrix",
        "india consequence twin",
        "mechanism and decision lab",
        "proof-carrying product compiler",
        "evolution and institution",
    ):
        assert plane in architecture
    assert "unique events, active episodes and event observations as different counts" in architecture
    assert "correction blast-radius" in architecture
    assert "uncommitted working-tree state is not evidence" in review_words
    assert "event, episode and observation counts interchanged" in review_words
    assert {
        "global_event_episode_ledger",
        "observation_twin",
        "proof_carrying_product_compiler",
        "mechanism_decision_lab",
    } <= program_ids
