"""Scenario Proof: exact constraints, rival hypotheses and fail-closed proof."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from src import (
    canonical_objects as canonical,
)
from src import (
    event_ledger_extension,
    scenario_proof,
    shock_compiler,
    shock_compiler_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/mechanism-constraint-scenario/0.1.0")


@pytest.fixture(scope="module")
def fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[shock_compiler_fixture.ShockFixture]:
    yield shock_compiler_fixture.build_fixture(tmp_path_factory.mktemp("scenario-proof"))


def _paths(fixture: shock_compiler_fixture.ShockFixture) -> dict[str, Path]:
    root = fixture.base.root
    return {
        "root": root,
        "schema_registry_path": root / "governance/canonical_schema_registry.json",
        "rights_registry_path": root / "governance/source_rights_registry.json",
        "rights_signers_path": root / "governance/rights_signers.json",
        "method_registry_path": root / "governance/canonical_method_registry.json",
        "release_signers_path": root / "governance/release_signers.json",
        "shock_registry_path": root / "governance/shock_compiler_registry.json",
    }


def _compile(
    fixture: shock_compiler_fixture.ShockFixture,
) -> dict[str, Any]:
    return shock_compiler.compile_shock(
        fixture.base.manifest,
        fixture.scenario,
        **_paths(fixture),
    )


def _constraint(
    compilation: dict[str, Any],
    fixture: shock_compiler_fixture.ShockFixture,
    *,
    constraint_id: str,
    metric: str,
    value: float,
) -> dict[str, Any]:
    path = compilation["paths"][0]
    measured = path[metric]
    if measured is None:
        if metric == "residual_duration":
            unit = "days"
            denominator = None
        else:
            unit = "percentage_points_of_edge_denominator"
            denominator = path["hops"][0]["magnitude"]["denominator"]
    else:
        unit = measured["unit"]
        denominator = measured.get("denominator")
    return scenario_proof.seal_request(
        {
            "object_type": "registered_constraint",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "constraint_id": constraint_id,
            "scenario_id": fixture.scenario["scenario_id"],
            "scenario_record_sha256": fixture.scenario["record_sha256"],
            "compilation_record_sha256": compilation["record_sha256"],
            "path_id": path["path_id"],
            "metric": metric,
            "operator": "upper_bound_lte",
            "threshold": {
                "value": value,
                "unit": unit,
                "denominator": denominator,
            },
            "epistemic_kind": "hypothetical_normative_boundary",
            "origin": "user_supplied",
            "evidence_id": None,
            "real_world_feasibility_claimed": False,
        }
    )


def _hypothesis(
    compilation: dict[str, Any],
    fixture: shock_compiler_fixture.ShockFixture,
    *,
    hypothesis_id: str,
    rival_id: str,
    mechanism_code: str,
    falsifiers: list[dict[str, Any]],
) -> dict[str, Any]:
    return scenario_proof.seal_request(
        {
            "object_type": "mechanism_hypothesis",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "hypothesis_id": hypothesis_id,
            "scenario_id": fixture.scenario["scenario_id"],
            "scenario_record_sha256": fixture.scenario["record_sha256"],
            "compilation_record_sha256": compilation["record_sha256"],
            "path_id": compilation["paths"][0]["path_id"],
            "mechanism_code": mechanism_code,
            "epistemic_status": "candidate_not_established",
            "causal_status": "not_identified",
            "registered_at": "2026-08-09T13:05:00Z",
            "registration_timing": "retrospective",
            "rival_hypothesis_ids": [rival_id],
            "falsifiers": sorted(falsifiers, key=lambda row: row["falsifier_id"]),
            "rival_set_completeness_claimed": False,
        }
    )


def _request(
    compilation: dict[str, Any],
    fixture: shock_compiler_fixture.ShockFixture,
    *,
    share_threshold: float = 4.8,
    duration_threshold: float = 8,
) -> dict[str, Any]:
    share_id = "constraint:scenario.fixture.residual_share"
    duration_id = "constraint:scenario.fixture.residual_duration"
    constraints = [
        _constraint(
            compilation,
            fixture,
            constraint_id=duration_id,
            metric="residual_duration",
            value=duration_threshold,
        ),
        _constraint(
            compilation,
            fixture,
            constraint_id=share_id,
            metric="residual_affected_share",
            value=share_threshold,
        ),
    ]
    constraints.sort(key=lambda row: row["constraint_id"])
    first_id = "hypothesis:scenario.fixture.alternative"
    second_id = "hypothesis:scenario.fixture.registered_path"
    hypotheses = [
        _hypothesis(
            compilation,
            fixture,
            hypothesis_id=first_id,
            rival_id=second_id,
            mechanism_code="alternative_pathway_candidate",
            falsifiers=[
                {
                    "falsifier_id": "falsifier:scenario.fixture.alternative_mixed_duration",
                    "predicate_id": "predicate:scenario.constraint_interval_relation_equals",
                    "expected_value": "mixed_within_registered_interval",
                    "constraint_id": duration_id,
                }
            ],
        ),
        _hypothesis(
            compilation,
            fixture,
            hypothesis_id=second_id,
            rival_id=first_id,
            mechanism_code="registered_path_transmission_candidate",
            falsifiers=[
                {
                    "falsifier_id": "falsifier:scenario.fixture.path_abstained",
                    "predicate_id": "predicate:scenario.path_quantification_status_equals",
                    "expected_value": "abstained",
                    "constraint_id": None,
                },
                {
                    "falsifier_id": "falsifier:scenario.fixture.share_violated",
                    "predicate_id": "predicate:scenario.constraint_interval_relation_equals",
                    "expected_value": "no_registered_values_satisfy",
                    "constraint_id": share_id,
                },
            ],
        ),
    ]
    hypotheses.sort(key=lambda row: row["hypothesis_id"])
    return scenario_proof.seal_request(
        {
            "object_type": "scenario_proof_request",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "request_id": "request:scenario-proof.fixture.001",
            "created_at": "2026-08-09T13:05:00Z",
            "evaluation_as_of": "2026-08-09T13:05:00Z",
            "scenario_binding": {
                "scenario_id": fixture.scenario["scenario_id"],
                "scenario_record_sha256": fixture.scenario["record_sha256"],
                "compilation_record_sha256": compilation["record_sha256"],
            },
            "constraints": constraints,
            "hypotheses": hypotheses,
            "guardrails": dict(scenario_proof._GUARDRAILS),
            "limitations": list(scenario_proof._REQUEST_LIMITATIONS),
        }
    )


def _execute(
    fixture: shock_compiler_fixture.ShockFixture,
    compilation: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    return scenario_proof.execute_scenario_proof(
        fixture.base.manifest,
        fixture.scenario,
        compilation,
        request,
        **_paths(fixture),
    )


def _mutate_request(
    request: dict[str, Any], mutate: Callable[[dict[str, Any]], None]
) -> dict[str, Any]:
    result = copy.deepcopy(request)
    mutate(result)
    for key in ("constraints", "hypotheses"):
        if key in result:
            result[key] = [scenario_proof.seal_request(row) for row in result[key]]
    return scenario_proof.seal_request(result)


def _rewrite_edge(
    fixture: shock_compiler_fixture.ShockFixture,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    edge_id = "edg:oges.fixture.origin_crude.001"
    path = fixture.base.objects[edge_id]
    edge = json.loads(path.read_text())
    mutate(edge)
    edge = canonical.seal_record(edge)
    path.write_text(json.dumps(edge, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(fixture.base.manifest.read_text())
    row = next(item for item in manifest["objects"] if item["object_id"] == edge_id)
    row["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    row["record_sha256"] = edge["record_sha256"]
    manifest = canonical.seal_record(manifest)
    fixture.base.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    fixture.base.release_signature.write_bytes(
        fixture.base.release_private_key.sign(fixture.base.manifest.read_bytes())
    )
    scenario = copy.deepcopy(fixture.scenario)
    scenario["release"] = {
        "release_id": manifest["release_id"],
        "record_sha256": manifest["record_sha256"],
        "generated_at": manifest["generated_at"],
        "effective_date": manifest["effective_date"],
    }
    scenario["knowledge_cutoff"] = manifest["generated_at"]
    fixture.scenario.clear()
    fixture.scenario.update(canonical.seal_record(scenario))


def test_exact_synthetic_proof_classifies_bounds_and_preserves_rivals(
    fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    compilation = _compile(fixture)
    request = _request(compilation, fixture)
    first = _execute(fixture, compilation, request)
    second = _execute(fixture, compilation, request)

    assert first == second
    assert event_ledger_extension.typed_record_sha256(first) == first["record_sha256"]
    constraints = {row["constraint_id"]: row for row in first["constraints"]}
    share = constraints["constraint:scenario.fixture.residual_share"]
    duration = constraints["constraint:scenario.fixture.residual_duration"]
    assert share["interval_relation"] == "all_registered_values_satisfy"
    assert share["scenario_feasibility_status"] == (
        "satisfied_under_registered_hypothetical_bounds"
    )
    assert share["margin_interval"] == {
        "lower": 0.0,
        "upper": 2.7,
        "unit": "percentage_points_of_edge_denominator",
        "denominator": "total synthetic crude-oil import volume in the period",
    }
    assert [row["value"] for row in share["corner_witnesses"]] == [2.1, 4.8]
    assert duration["interval_relation"] == "mixed_within_registered_interval"
    assert duration["scenario_feasibility_status"] == ("indeterminate_within_registered_bounds")
    hypotheses = {row["hypothesis_id"]: row for row in first["hypotheses"]}
    assert (
        hypotheses["hypothesis:scenario.fixture.alternative"]["scenario_compatibility_status"]
        == "incompatible_with_compiled_scenario_not_real_world_falsified"
    )
    assert (
        hypotheses["hypothesis:scenario.fixture.registered_path"]["scenario_compatibility_status"]
        == "compatible_with_compiled_scenario_not_supported"
    )
    assert first["result"] == {
        "status": "assessed",
        "trust_class": "unauthenticated_execution_envelope",
        "public_claim_state": "requires_claim_bundle",
        **scenario_proof._GUARDRAILS,
    }
    scenario_proof.validate_scenario_proof(
        first,
        fixture.base.manifest,
        fixture.scenario,
        compilation,
        request,
        **_paths(fixture),
    )


@pytest.mark.parametrize(
    "threshold,relation,status",
    [
        (4.8, "all_registered_values_satisfy", "satisfied_under_registered_hypothetical_bounds"),
        (2.0, "no_registered_values_satisfy", "violated_under_registered_hypothetical_bounds"),
        (3.0, "mixed_within_registered_interval", "indeterminate_within_registered_bounds"),
    ],
)
def test_upper_bound_boundary_rules_are_exact(
    fixture: shock_compiler_fixture.ShockFixture,
    threshold: float,
    relation: str,
    status: str,
) -> None:
    compilation = _compile(fixture)
    request = _request(compilation, fixture, share_threshold=threshold)
    result = _execute(fixture, compilation, request)
    row = next(
        row
        for row in result["constraints"]
        if row["constraint_id"] == "constraint:scenario.fixture.residual_share"
    )
    assert row["interval_relation"] == relation
    assert row["scenario_feasibility_status"] == status


def test_unit_or_denominator_mismatch_refuses(
    fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    compilation = _compile(fixture)
    request = _request(compilation, fixture)
    request = _mutate_request(
        request,
        lambda row: row["constraints"][1]["threshold"].update(denominator="invented denominator"),
    )
    with pytest.raises(scenario_proof.ScenarioProofError) as exc:
        _execute(fixture, compilation, request)
    assert exc.value.code == "scenario_proof_constraint_measure_mismatch"


def test_upstream_abstention_is_visible_and_never_called_satisfied(
    tmp_path: Path,
) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "abstention")
    _rewrite_edge(
        fixture,
        lambda row: row["magnitude"].update(unit="percent_of_unregistered_basis"),
    )
    compilation = _compile(fixture)
    assert compilation["paths"][0]["quantification_status"] == "abstained"
    request = _request(compilation, fixture)
    result = _execute(fixture, compilation, request)
    assert result["result"]["status"] == "partially_assessed"
    for row in result["constraints"]:
        assert row["readiness"] == "upstream_abstention"
        assert row["interval_relation"] == "not_evaluable"
        assert row["scenario_feasibility_status"] == ("indeterminate_input_unavailable")
        assert row["corner_witnesses"] == []


def test_stale_inputs_are_visible_and_never_called_satisfied(tmp_path: Path) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "stale-input")
    _rewrite_edge(
        fixture,
        lambda row: row.update(observed_at="2026-07-01T00:00:00Z"),
    )
    compilation = _compile(fixture)
    assert compilation["paths"][0]["quantification_status"] == "bounded_range"
    assert compilation["paths"][0]["hops"][0]["freshness"]["status"] == "stale"
    request = _request(compilation, fixture)
    result = _execute(fixture, compilation, request)
    assert result["result"]["status"] == "partially_assessed"
    for row in result["constraints"]:
        assert row["readiness"] == "stale_inputs"
        assert row["scenario_feasibility_status"] == "indeterminate_input_unavailable"
    assert all(
        row["scenario_compatibility_status"] == "indeterminate_missing_registered_result"
        for row in result["hypotheses"]
    )
    constraint_falsifiers = [
        falsifier
        for row in result["hypotheses"]
        for falsifier in row["falsifiers"]
        if falsifier["constraint_id"] is not None
    ]
    assert constraint_falsifiers
    assert all(row["status"] == "not_evaluable" for row in constraint_falsifiers)


def test_unknown_freshness_makes_constraint_falsifier_unevaluable() -> None:
    result = scenario_proof._falsifier_result(
        {
            "falsifier_id": "falsifier:scenario.fixture.unknown-freshness",
            "predicate_id": "predicate:scenario.constraint_interval_relation_equals",
            "expected_value": "all_registered_values_satisfy",
            "constraint_id": "constraint:scenario.fixture.unknown-freshness",
        },
        {"quantification_status": "bounded_range", "gap_codes": []},
        {
            "constraint:scenario.fixture.unknown-freshness": {
                "readiness": "unknown_freshness",
                "interval_relation": "all_registered_values_satisfy",
            }
        },
    )
    assert result["status"] == "not_evaluable"


def test_pre_scenario_registration_time_is_explicitly_self_declared(
    fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    compilation = _compile(fixture)
    request = _mutate_request(
        _request(compilation, fixture),
        lambda row: row["hypotheses"][0].update(
            registered_at="2000-01-01T00:00:00Z",
            registration_timing="self_declared_pre_scenario",
        ),
    )
    result = _execute(fixture, compilation, request)
    hypothesis = next(
        row
        for row in result["hypotheses"]
        if row["hypothesis_id"] == "hypothesis:scenario.fixture.alternative"
    )
    assert hypothesis["registration_timing"] == "self_declared_pre_scenario"


def _make_asymmetric_rival_set(row: dict[str, Any]) -> None:
    first = row["hypotheses"][0]
    second = row["hypotheses"][1]
    third = copy.deepcopy(first)
    third["hypothesis_id"] = "hypothesis:scenario.fixture.tertiary"
    third["rival_hypothesis_ids"] = [second["hypothesis_id"]]
    first["rival_hypothesis_ids"] = sorted([second["hypothesis_id"], third["hypothesis_id"]])
    row["hypotheses"].append(third)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda row: row["scenario_binding"].update(compilation_record_sha256="f" * 64),
            "scenario_proof_binding_mismatch",
        ),
        (
            lambda row: row["hypotheses"][0].update(
                rival_hypothesis_ids=[row["hypotheses"][0]["hypothesis_id"]]
            ),
            "scenario_proof_rival_invalid",
        ),
        (
            _make_asymmetric_rival_set,
            "scenario_proof_rival_asymmetric",
        ),
        (
            lambda row: row["hypotheses"][0]["falsifiers"][0].update(
                predicate_id="predicate:scenario.free_text"
            ),
            "scenario_proof_request_schema_invalid",
        ),
        (
            lambda row: row.update(evaluation_as_of="2026-08-08T12:59:59Z"),
            "scenario_proof_time_invalid",
        ),
        (
            lambda row: row["hypotheses"][0].update(
                registration_timing="self_declared_pre_scenario"
            ),
            "scenario_proof_registration_timing_invalid",
        ),
        (
            lambda row: row["hypotheses"][0].update(registered_at="2030-01-01T00:00:00Z"),
            "scenario_proof_time_invalid",
        ),
        (
            lambda row: row.update(recommendation="buy inventory"),
            "scenario_proof_request_schema_invalid",
        ),
    ],
)
def test_request_mutations_fail_closed(
    fixture: shock_compiler_fixture.ShockFixture,
    mutate: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    compilation = _compile(fixture)
    request = _mutate_request(_request(compilation, fixture), mutate)
    with pytest.raises(scenario_proof.ScenarioProofError) as exc:
        _execute(fixture, compilation, request)
    assert exc.value.code == code


def test_supplied_compilation_is_recomputed_before_any_proof(
    fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    compilation = _compile(fixture)
    request = _request(compilation, fixture)
    tampered = copy.deepcopy(compilation)
    tampered["paths"][0]["residual_affected_share"]["upper"] = 1.0
    tampered = cast(dict[str, Any], canonical.seal_record(tampered))
    with pytest.raises(shock_compiler.ShockCompilerError) as exc:
        _execute(fixture, tampered, request)
    assert exc.value.code == "shock_output_semantic_mismatch"


def test_runtime_shock_registry_must_equal_profile_bound_registry(tmp_path: Path) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "registry-drift")
    registry_path = _paths(fixture)["shock_registry_path"]
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["effective"] = "2026-08-07"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    compilation = _compile(fixture)
    request = _request(compilation, fixture)
    with pytest.raises(scenario_proof.ScenarioProofError) as exc:
        _execute(fixture, compilation, request)
    assert exc.value.code == "scenario_proof_shock_registry_drift"


def test_resealed_output_mutation_fails_full_recomputation(
    fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    compilation = _compile(fixture)
    request = _request(compilation, fixture)
    result = _execute(fixture, compilation, request)
    result["constraints"][0]["scenario_feasibility_status"] = (
        "satisfied_under_registered_hypothetical_bounds"
    )
    result = cast(dict[str, Any], event_ledger_extension.seal_record(result))
    with pytest.raises(scenario_proof.ScenarioProofError) as exc:
        scenario_proof.validate_scenario_proof(
            result,
            fixture.base.manifest,
            fixture.scenario,
            compilation,
            request,
            **_paths(fixture),
        )
    assert exc.value.code == "scenario_proof_execution_mismatch"


def test_profile_binds_every_normative_byte_and_preserves_shock_1_0() -> None:
    profile_path = ROOT / EXTENSION / "profile.json"
    profile = json.loads(profile_path.read_text())
    assert profile["extension_id"] == "oges:extension:scenario_proof"
    assert profile["status"] == "public_draft_contract_only_synthetic_fixtures"
    for row in profile["bound_files"]:
        assert row["sha256"] == hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
    for key in ("reference_implementation", "conformance_test"):
        row = profile[key]
        assert row["sha256"] == hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
    registry = json.loads((ROOT / "governance/shock_compiler_registry.json").read_text())
    assert registry["engine"]["version"] == "1.0.0"
    assert (
        registry["engine"]["implementation_sha256"]
        == hashlib.sha256((ROOT / "src/shock_compiler.py").read_bytes()).hexdigest()
    )


def test_adversarial_case_registry_is_complete_and_capability_is_not_overpromoted() -> None:
    cases = json.loads((ROOT / EXTENSION / "adversarial-cases.json").read_text())
    assert len(cases["cases"]) == 22
    assert len({row["case_id"] for row in cases["cases"]}) == 22
    capability = json.loads((ROOT / "governance/capability_attestation_registry.json").read_text())
    rules = {row["capability_id"]: row for row in capability["capability_rules"]}
    assert set(rules["constraint_feasibility"]["levels"]) == {"contract_only"}
    assert "hypothesis_falsification" not in rules
    assert "execution_receipt" not in json.dumps(rules["constraint_feasibility"], sort_keys=True)
