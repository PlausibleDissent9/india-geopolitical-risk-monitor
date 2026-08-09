"""Decision Switch: complete lattice, exact switches, and bounded information."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from src import canonical_objects as canonical
from src import decision_switch, scenario_proof, shock_compiler, shock_compiler_fixture

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/decision-switch/0.1.0")

OPTION_A = "option:decision.fixture.a"
OPTION_B = "option:decision.fixture.b"
SHARE_A = "constraint:decision.fixture.a.share"
SHARE_B = "constraint:decision.fixture.b.share"
DURATION_A = "constraint:decision.fixture.a.duration"
DURATION_B = "constraint:decision.fixture.b.duration"
ATOM_BOUNDARY = "atom:decision.boundary-a"
ATOM_MAGNITUDE = "atom:decision.magnitude"
ATOM_SUBSTITUTION = "atom:decision.substitution"
EDGE_ID = "edg:oges.fixture.origin_crude.001"


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


def _parallel_path_fixture(
    destination: Path,
) -> shock_compiler_fixture.ShockFixture:
    fixture = shock_compiler_fixture.build_fixture(destination)
    base = fixture.base
    original = json.loads(base.objects[EDGE_ID].read_text())
    parallel = copy.deepcopy(original)
    parallel_id = "edg:oges.fixture.parallel.304412"
    parallel["edge_id"] = parallel_id
    parallel["magnitude"]["value"] = 42.5
    parallel["magnitude"]["uncertainty"]["lower"] = 40.0
    parallel["magnitude"]["uncertainty"]["upper"] = 45.0
    parallel = cast(dict[str, Any], canonical.seal_record(parallel))
    parallel_path = base.root / "canonical" / f"{parallel_id.replace(':', '__')}.json"
    parallel_path.write_text(
        json.dumps(parallel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    base.objects[parallel_id] = parallel_path

    manifest = json.loads(base.manifest.read_text())
    manifest["objects"].append(
        {
            "object_type": "exposure_edge",
            "object_id": parallel_id,
            "path": str(parallel_path.relative_to(base.root)),
            "file_sha256": hashlib.sha256(parallel_path.read_bytes()).hexdigest(),
            "record_sha256": parallel["record_sha256"],
        }
    )
    manifest["objects"].sort(
        key=lambda row: (row["object_type"], row["object_id"])
    )
    manifest["counts"]["exposure_edge"] += 1
    manifest = cast(dict[str, Any], canonical.seal_record(manifest))
    base.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    base.release_signature.write_bytes(
        base.release_private_key.sign(base.manifest.read_bytes())
    )

    scenario = copy.deepcopy(fixture.scenario)
    scenario["release"] = {
        "release_id": manifest["release_id"],
        "record_sha256": manifest["record_sha256"],
        "generated_at": manifest["generated_at"],
        "effective_date": manifest["effective_date"],
    }
    scenario = cast(dict[str, Any], canonical.seal_record(scenario))
    return shock_compiler_fixture.ShockFixture(base=base, scenario=scenario)


def _constraint(
    fixture: shock_compiler_fixture.ShockFixture,
    compilation: dict[str, Any],
    option_id: str,
    metric: str,
    threshold: float,
) -> dict[str, Any]:
    suffix = "share" if metric == "residual_affected_share" else "duration"
    constraint_id = {
        (OPTION_A, "share"): SHARE_A,
        (OPTION_B, "share"): SHARE_B,
        (OPTION_A, "duration"): DURATION_A,
        (OPTION_B, "duration"): DURATION_B,
    }[(option_id, suffix)]
    path = compilation["paths"][0]
    if metric == "residual_duration":
        unit = "days"
        denominator = None
    else:
        unit = "percentage_points_of_edge_denominator"
        denominator = path["hops"][0]["magnitude"]["denominator"]
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
                "value": threshold,
                "unit": unit,
                "denominator": denominator,
            },
            "epistemic_kind": "hypothetical_normative_boundary",
            "origin": "user_supplied",
            "evidence_id": None,
            "real_world_feasibility_claimed": False,
        }
    )


def _hypotheses(
    fixture: shock_compiler_fixture.ShockFixture,
    compilation: dict[str, Any],
    option_id: str,
    share_id: str,
) -> list[dict[str, Any]]:
    path_id = compilation["paths"][0]["path_id"]
    first = f"hypothesis:decision.{option_id.rsplit('.', 1)[-1]}.alternative"
    second = f"hypothesis:decision.{option_id.rsplit('.', 1)[-1]}.registered"

    def build(
        hypothesis_id: str,
        rival_id: str,
        mechanism_code: str,
        falsifier_id: str,
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
                "path_id": path_id,
                "mechanism_code": mechanism_code,
                "epistemic_status": "candidate_not_established",
                "causal_status": "not_identified",
                "registered_at": "2026-08-09T13:05:00Z",
                "registration_timing": "retrospective",
                "rival_hypothesis_ids": [rival_id],
                "falsifiers": [
                    {
                        "falsifier_id": falsifier_id,
                        "predicate_id": "predicate:scenario.constraint_interval_relation_equals",
                        "expected_value": "no_registered_values_satisfy",
                        "constraint_id": share_id,
                    }
                ],
                "rival_set_completeness_claimed": False,
            }
        )

    return sorted(
        [
            build(
                first,
                second,
                "alternative_pathway_candidate",
                f"falsifier:decision.{option_id.rsplit('.', 1)[-1]}.alternative",
            ),
            build(
                second,
                first,
                "registered_path_transmission_candidate",
                f"falsifier:decision.{option_id.rsplit('.', 1)[-1]}.registered",
            ),
        ],
        key=lambda row: row["hypothesis_id"],
    )


def _proof_request(
    fixture: shock_compiler_fixture.ShockFixture,
    compilation: dict[str, Any],
    option_id: str,
    variant_id: str,
    *,
    boundary_active: bool,
) -> dict[str, Any]:
    share_id = SHARE_A if option_id == OPTION_A else SHARE_B
    share_threshold = 5.0 if option_id == OPTION_A and boundary_active else (
        4.5 if option_id == OPTION_A else 6.5
    )
    constraints = sorted(
        [
            _constraint(
                fixture,
                compilation,
                option_id,
                "residual_affected_share",
                share_threshold,
            ),
            _constraint(
                fixture, compilation, option_id, "residual_duration", 11.0
            ),
        ],
        key=lambda row: row["constraint_id"],
    )
    return scenario_proof.seal_request(
        {
            "object_type": "scenario_proof_request",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "request_id": f"request:decision.{option_id.rsplit('.', 1)[-1]}.{variant_id.rsplit('.', 1)[-1]}",
            "created_at": "2026-08-09T13:05:00Z",
            "evaluation_as_of": "2026-08-09T13:05:00Z",
            "scenario_binding": {
                "scenario_id": fixture.scenario["scenario_id"],
                "scenario_record_sha256": fixture.scenario["record_sha256"],
                "compilation_record_sha256": compilation["record_sha256"],
            },
            "constraints": constraints,
            "hypotheses": _hypotheses(fixture, compilation, option_id, share_id),
            "guardrails": dict(scenario_proof._GUARDRAILS),
            "limitations": list(scenario_proof._REQUEST_LIMITATIONS),
        }
    )


def _bundle(
    base: shock_compiler_fixture.ShockFixture,
    option_id: str,
    variant_id: str,
    active_atoms: set[str],
    *,
    mutate_scenario: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    scenario = copy.deepcopy(base.scenario)
    scenario["scenario_id"] = (
        f"scenario:decision.{option_id.rsplit('.', 1)[-1]}.{variant_id.rsplit('.', 1)[-1]}"
    )
    if ATOM_MAGNITUDE in active_atoms:
        scenario["shock"]["magnitude"] = {
            "lower": 40,
            "upper": 50,
            "unit": "percent_of_subject_flow_reduced",
        }
    if ATOM_SUBSTITUTION in active_atoms:
        scenario["substitutions"][0]["fraction_of_gross_effect"] = {
            "lower": 0,
            "upper": 10,
            "unit": "percent_of_gross_affected_share_substituted",
        }
    if mutate_scenario is not None:
        mutate_scenario(scenario)
    scenario = cast(dict[str, Any], canonical.seal_record(scenario))
    local = shock_compiler_fixture.ShockFixture(base=base.base, scenario=scenario)
    compilation = shock_compiler.compile_shock(
        base.base.manifest, scenario, **_paths(base)
    )
    proof_request = _proof_request(
        local,
        compilation,
        option_id,
        variant_id,
        boundary_active=ATOM_BOUNDARY in active_atoms,
    )
    proof = scenario_proof.execute_scenario_proof(
        base.base.manifest,
        scenario,
        compilation,
        proof_request,
        **_paths(base),
    )
    return decision_switch.seal_record(
        {
            "object_type": "decision_artifact_bundle",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "bundle_id": f"bundle:decision.{option_id.rsplit('.', 1)[-1]}.{variant_id.rsplit('.', 1)[-1]}",
            "option_id": option_id,
            "variant_id": variant_id,
            "scenario": scenario,
            "compilation": compilation,
            "scenario_proof_request": proof_request,
            "scenario_proof_execution": proof,
        }
    )


def _semantic_interval(
    lower: float, upper: float, unit: str, denominator: str | None = None
) -> dict[str, Any]:
    return {
        "value_kind": "interval",
        "lower": lower,
        "upper": upper,
        "unit": unit,
        "denominator": denominator,
    }


def _semantic_scalar(
    value: float, unit: str, denominator: str | None
) -> dict[str, Any]:
    return {
        "value_kind": "scalar",
        "value": value,
        "unit": unit,
        "denominator": denominator,
    }


def _value_row(
    option_id: str,
    target_id: str | None,
    baseline: dict[str, Any],
    alternative: dict[str, Any],
) -> dict[str, Any]:
    return {
        "option_id": option_id,
        "target_id": target_id,
        "baseline_value": baseline,
        "alternative_value": alternative,
        "baseline_value_sha256": decision_switch.semantic_value_sha256(baseline),
        "alternative_value_sha256": decision_switch.semantic_value_sha256(alternative),
    }


def _request(base: shock_compiler_fixture.ShockFixture) -> dict[str, Any]:
    option_ids = [OPTION_A, OPTION_B]
    atoms = [ATOM_BOUNDARY, ATOM_MAGNITUDE, ATOM_SUBSTITUTION]
    variants: list[dict[str, Any]] = []
    index = 0
    for size in range(len(atoms) + 1):
        from itertools import combinations

        for combo in combinations(atoms, size):
            variant_id = f"variant:decision.fixture.{index:03d}"
            active = set(combo)
            variants.append(
                {
                    "variant_id": variant_id,
                    "active_atom_ids": list(combo),
                    "bundles": [
                        _bundle(base, option_id, variant_id, active)
                        for option_id in option_ids
                    ],
                }
            )
            index += 1
    denominator = base.scenario["substitutions"][0]
    denominator = shock_compiler.compile_shock(
        base.base.manifest, base.scenario, **_paths(base)
    )["paths"][0]["hops"][0]["magnitude"]["denominator"]
    magnitude_base = _semantic_interval(
        30, 40, "percent_of_subject_flow_reduced"
    )
    magnitude_alt = _semantic_interval(
        40, 50, "percent_of_subject_flow_reduced"
    )
    substitution_base = _semantic_interval(
        20, 30, "percent_of_gross_affected_share_substituted"
    )
    substitution_alt = _semantic_interval(
        0, 10, "percent_of_gross_affected_share_substituted"
    )
    boundary_base = _semantic_scalar(
        4.5, "percentage_points_of_edge_denominator", denominator
    )
    boundary_alt = _semantic_scalar(
        5.0, "percentage_points_of_edge_denominator", denominator
    )
    method_sha = decision_switch.resolution_method_sha256()
    request = {
        "object_type": "decision_switch_request",
        "schema_version": "0.1.0",
        "record_sha256": "0" * 64,
        "decision_case_id": "case:decision.fixture.001",
        "created_at": "2026-08-09T14:00:00Z",
        "evaluation_as_of": "2026-08-09T14:00:00Z",
        "release": base.scenario["release"],
        "knowledge_cutoff": base.scenario["knowledge_cutoff"],
        "event_id": base.scenario["event_id"],
        "target_entity_id": base.scenario["target_entity_id"],
        "options": [
            {
                "option_id": OPTION_A,
                "option_kind": "registered_hypothetical_configuration",
                "required_slot_ids": [
                    "slot:decision.duration",
                    "slot:decision.share",
                ],
                "real_world_action_claimed": False,
            },
            {
                "option_id": OPTION_B,
                "option_kind": "registered_hypothetical_configuration",
                "required_slot_ids": [
                    "slot:decision.duration",
                    "slot:decision.share",
                ],
                "real_world_action_claimed": False,
            },
        ],
        "constraint_slots": [
            {
                "slot_id": "slot:decision.duration",
                "metric": "residual_duration",
                "operator": "upper_bound_lte",
                "unit": "days",
                "denominator": None,
                "option_bindings": [
                    {"option_id": OPTION_A, "constraint_id": DURATION_A},
                    {"option_id": OPTION_B, "constraint_id": DURATION_B},
                ],
            },
            {
                "slot_id": "slot:decision.share",
                "metric": "residual_affected_share",
                "operator": "upper_bound_lte",
                "unit": "percentage_points_of_edge_denominator",
                "denominator": denominator,
                "option_bindings": [
                    {"option_id": OPTION_A, "constraint_id": SHARE_A},
                    {"option_id": OPTION_B, "constraint_id": SHARE_B},
                ],
            },
        ],
        "atoms": [
            {
                "atom_id": ATOM_BOUNDARY,
                "atom_kind": "constraint_boundary",
                "selector_kind": "constraint.threshold",
                "epistemic_kind": "hypothetical_normative_boundary_change",
                "observation_eligibility": "not_observable_normative_boundary",
                "option_values": [
                    _value_row(OPTION_A, SHARE_A, boundary_base, boundary_alt)
                ],
                "real_world_state_claimed": False,
            },
            {
                "atom_id": ATOM_MAGNITUDE,
                "atom_kind": "shock_magnitude_assumption",
                "selector_kind": "shock.magnitude",
                "epistemic_kind": "hypothetical_assumption_change",
                "observation_eligibility": "synthetic_atom_reveal",
                "option_values": [
                    _value_row(option_id, None, magnitude_base, magnitude_alt)
                    for option_id in option_ids
                ],
                "real_world_state_claimed": False,
            },
            {
                "atom_id": ATOM_SUBSTITUTION,
                "atom_kind": "substitution_fraction_assumption",
                "selector_kind": "substitution.fraction",
                "epistemic_kind": "hypothetical_assumption_change",
                "observation_eligibility": "synthetic_atom_reveal",
                "option_values": [
                    _value_row(option_id, EDGE_ID, substitution_base, substitution_alt)
                    for option_id in option_ids
                ],
                "real_world_state_claimed": False,
            },
        ],
        "variants": variants,
        "information_candidates": [
            {
                "candidate_id": "candidate:decision.magnitude",
                "atom_ids": [ATOM_MAGNITUDE],
                "resolution_method_id": "method:decision-switch.synthetic-atom-reveal",
                "resolution_method_sha256": method_sha,
                "candidate_set_completeness_claimed": False,
                "real_observation_claimed": False,
                "probability_assigned": False,
                "cost_assigned": False,
                "utility_assigned": False,
                "recommendation_generated": False,
            },
            {
                "candidate_id": "candidate:decision.magnitude-substitution",
                "atom_ids": [ATOM_MAGNITUDE, ATOM_SUBSTITUTION],
                "resolution_method_id": "method:decision-switch.synthetic-atom-reveal",
                "resolution_method_sha256": method_sha,
                "candidate_set_completeness_claimed": False,
                "real_observation_claimed": False,
                "probability_assigned": False,
                "cost_assigned": False,
                "utility_assigned": False,
                "recommendation_generated": False,
            },
            {
                "candidate_id": "candidate:decision.substitution",
                "atom_ids": [ATOM_SUBSTITUTION],
                "resolution_method_id": "method:decision-switch.synthetic-atom-reveal",
                "resolution_method_sha256": method_sha,
                "candidate_set_completeness_claimed": False,
                "real_observation_claimed": False,
                "probability_assigned": False,
                "cost_assigned": False,
                "utility_assigned": False,
                "recommendation_generated": False,
            },
        ],
        "guardrails": dict(decision_switch._GUARDRAILS),
        "limitations": list(decision_switch._REQUEST_LIMITATIONS),
    }
    return decision_switch.seal_record(request)


@pytest.fixture(scope="module")
def decision_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]]]:
    base = shock_compiler_fixture.build_fixture(tmp_path_factory.mktemp("decision-switch"))
    yield base, _request(base)


def _execute(
    base: shock_compiler_fixture.ShockFixture, request: dict[str, Any]
) -> dict[str, Any]:
    return decision_switch.execute_decision_switch(
        base.base.manifest, request, **_paths(base)
    )


def _reseal(request: dict[str, Any]) -> dict[str, Any]:
    return decision_switch.seal_record(request)


def test_complete_lattice_emits_exact_singleton_and_multi_atom_switches(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    result = _execute(base, request)
    assert result["lattice"]["powerset_complete"] is True
    assert result["lattice"]["option_denominator"] == 2
    assert result["lattice"]["atom_denominator"] == 3
    assert result["lattice"]["expected_variant_denominator"] == 8
    assert result["lattice"]["bundle_denominator"] == 16
    assert result["lattice"]["variants"][0]["robust_option_ids"] == [OPTION_B]
    switch_atoms = [row["atom_ids"] for row in result["minimal_switch_sets"]]
    assert [ATOM_BOUNDARY] in switch_atoms
    assert [ATOM_MAGNITUDE, ATOM_SUBSTITUTION] in switch_atoms
    assert all(row["global_minimality_claimed"] is False for row in result["minimal_switch_sets"])


def test_information_relevance_is_pareto_set_reduction_not_voi(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    result = _execute(base, request)
    rows = result["information_relevance"]
    assert {row["candidate_id"] for row in rows} == {
        "candidate:decision.magnitude",
        "candidate:decision.magnitude-substitution",
        "candidate:decision.substitution",
    }
    assert min(row["pareto_layer"] for row in rows) == 1
    assert all(row["rank_kind"] == "pareto_layer_not_total_priority_or_recommendation" for row in rows)
    assert all(row["probability_assigned"] is False for row in rows)
    assert all(row["entropy_computed"] is False for row in rows)
    assert all(row["expected_value_computed"] is False for row in rows)
    assert all(row["recommendation_generated"] is False for row in rows)


def test_execution_is_deterministic_and_fully_recompiles_for_validation(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    first = _execute(base, request)
    second = _execute(base, request)
    assert first == second
    decision_switch.validate_decision_switch(
        first, base.base.manifest, request, **_paths(base)
    )
    mutated = copy.deepcopy(first)
    mutated["information_relevance"][0]["pareto_layer"] += 1
    mutated = decision_switch.seal_record(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        decision_switch.validate_decision_switch(
            mutated, base.base.manifest, request, **_paths(base)
        )
    assert exc.value.code == "decision_switch_execution_mismatch"


def test_request_hash_and_complete_powerset_are_fail_closed(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    bad_hash = copy.deepcopy(request)
    bad_hash["created_at"] = "2026-08-09T14:00:01Z"
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, bad_hash)
    assert exc.value.code == "decision_switch_request_digest_invalid"

    missing = copy.deepcopy(request)
    missing["variants"].pop()
    missing = _reseal(missing)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, missing)
    assert exc.value.code == "decision_switch_lattice_incomplete"


def test_hidden_semantic_change_is_rejected_after_valid_full_recompile(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    mutated = copy.deepcopy(request)
    variant = mutated["variants"][0]
    replacement = _bundle(
        base,
        OPTION_A,
        variant["variant_id"],
        set(),
        mutate_scenario=lambda scenario: scenario["traversal"].__setitem__(
            "max_paths", 24
        ),
    )
    variant["bundles"][0] = replacement
    mutated = _reseal(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, mutated)
    assert exc.value.code == "decision_switch_hidden_semantic_change"


def test_object_to_path_remap_is_rejected_after_valid_full_recompile(
    tmp_path: Path,
) -> None:
    base = _parallel_path_fixture(tmp_path / "parallel-path")
    request = _request(base)
    for variant in request["variants"]:
        swapped = variant["variant_id"] == "variant:decision.fixture.001"
        for index, bundle in enumerate(variant["bundles"]):
            paths = {
                tuple(row["edge_ids"]): row["path_id"]
                for row in bundle["compilation"]["paths"]
            }
            original_path = paths[(EDGE_ID,)]
            parallel_path = paths[("edg:oges.fixture.parallel.304412",)]
            proof_request = copy.deepcopy(bundle["scenario_proof_request"])
            for row in proof_request["constraints"]:
                share = row["metric"] == "residual_affected_share"
                row["path_id"] = (
                    parallel_path if share == swapped else original_path
                )
            for row in proof_request["hypotheses"]:
                alternative = row["mechanism_code"] == "alternative_pathway_candidate"
                row["path_id"] = (
                    parallel_path if alternative == swapped else original_path
                )
            proof_request["constraints"] = sorted(
                [scenario_proof.seal_request(row) for row in proof_request["constraints"]],
                key=lambda row: row["constraint_id"],
            )
            proof_request["hypotheses"] = sorted(
                [scenario_proof.seal_request(row) for row in proof_request["hypotheses"]],
                key=lambda row: row["hypothesis_id"],
            )
            proof_request = scenario_proof.seal_request(proof_request)
            proof = scenario_proof.execute_scenario_proof(
                base.base.manifest,
                bundle["scenario"],
                bundle["compilation"],
                proof_request,
                **_paths(base),
            )
            bundle["scenario_proof_request"] = proof_request
            bundle["scenario_proof_execution"] = proof
            variant["bundles"][index] = decision_switch.seal_record(bundle)
    request = _reseal(request)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, request)
    assert exc.value.code == "decision_switch_hidden_semantic_change"


def test_switch_identity_binds_case_and_decision_partition() -> None:
    first = [
        {"robust_option_ids": ["option:a"], "active_atom_ids": []},
        {
            "robust_option_ids": ["option:b"],
            "active_atom_ids": ["atom:shared.x"],
            "variant_id": "variant:first",
        },
    ]
    second = [
        {"robust_option_ids": ["option:c"], "active_atom_ids": []},
        {
            "robust_option_ids": ["option:d"],
            "active_atom_ids": ["atom:shared.x"],
            "variant_id": "variant:second",
        },
    ]
    first_id = decision_switch._minimal_switches("case:first", first)[0][
        "switch_set_id"
    ]
    second_id = decision_switch._minimal_switches("case:second", second)[0][
        "switch_set_id"
    ]
    assert first_id != second_id


def test_active_and_inactive_atom_semantics_are_exact(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    mutated = copy.deepcopy(request)
    baseline = mutated["variants"][0]
    baseline["bundles"][0] = _bundle(
        base,
        OPTION_A,
        baseline["variant_id"],
        {ATOM_MAGNITUDE},
    )
    mutated = _reseal(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, mutated)
    assert exc.value.code == "decision_switch_atom_state_mismatch"


def test_duplicate_selector_and_equal_atom_states_refuse(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    duplicate = copy.deepcopy(request)
    duplicate["atoms"][2]["selector_kind"] = "shock.magnitude"
    duplicate["atoms"][2]["atom_kind"] = "shock_magnitude_assumption"
    duplicate["atoms"][2]["option_values"] = copy.deepcopy(
        duplicate["atoms"][1]["option_values"]
    )
    duplicate = _reseal(duplicate)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, duplicate)
    assert exc.value.code == "decision_switch_atom_selector_duplicate"

    equal = copy.deepcopy(request)
    row = equal["atoms"][1]["option_values"][0]
    row["alternative_value"] = copy.deepcopy(row["baseline_value"])
    row["alternative_value_sha256"] = row["baseline_value_sha256"]
    equal = _reseal(equal)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, equal)
    assert exc.value.code == "decision_switch_atom_value_digest_invalid"


def test_normative_atom_cannot_be_laundered_as_observation(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    mutated = copy.deepcopy(request)
    mutated["information_candidates"][0]["atom_ids"] = [ATOM_BOUNDARY]
    mutated = _reseal(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, mutated)
    assert exc.value.code == "decision_switch_normative_atom_not_observable"


def test_resolution_method_and_time_are_bound(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    drift = copy.deepcopy(request)
    drift["information_candidates"][0]["resolution_method_sha256"] = "f" * 64
    drift = _reseal(drift)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, drift)
    assert exc.value.code == "decision_switch_resolution_method_drift"

    future = copy.deepcopy(request)
    future["created_at"] = "2026-08-09T14:00:01Z"
    future["evaluation_as_of"] = "2026-08-09T14:00:00Z"
    future = _reseal(future)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, future)
    assert exc.value.code == "decision_switch_time_invalid"


def test_option_slot_and_bundle_denominators_cannot_shrink(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    slot = copy.deepcopy(request)
    slot["constraint_slots"][0]["option_bindings"].pop()
    slot = _reseal(slot)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, slot)
    assert exc.value.code in {
        "decision_switch_request_schema_invalid",
        "decision_switch_slot_option_partition_invalid",
    }

    bundle = copy.deepcopy(request)
    bundle["variants"][0]["bundles"].pop()
    bundle = _reseal(bundle)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, bundle)
    assert exc.value.code in {
        "decision_switch_request_schema_invalid",
        "decision_switch_bundle_option_partition_invalid",
    }


def test_unused_slots_duplicate_bundle_ids_and_candidate_scopes_refuse(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    unused = copy.deepcopy(request)
    for option in unused["options"]:
        option["required_slot_ids"] = ["slot:decision.duration"]
    unused = _reseal(unused)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, unused)
    assert exc.value.code == "decision_switch_option_slot_invalid"

    duplicate_bundle = copy.deepcopy(request)
    duplicate_bundle["variants"][1]["bundles"][0]["bundle_id"] = (
        duplicate_bundle["variants"][0]["bundles"][0]["bundle_id"]
    )
    duplicate_bundle["variants"][1]["bundles"][0] = decision_switch.seal_record(
        duplicate_bundle["variants"][1]["bundles"][0]
    )
    duplicate_bundle = _reseal(duplicate_bundle)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, duplicate_bundle)
    assert exc.value.code == "decision_switch_bundle_id_duplicate"

    duplicate_scope = copy.deepcopy(request)
    duplicate_scope["information_candidates"][1]["atom_ids"] = copy.deepcopy(
        duplicate_scope["information_candidates"][0]["atom_ids"]
    )
    duplicate_scope = _reseal(duplicate_scope)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, duplicate_scope)
    assert exc.value.code == "decision_switch_candidate_scope_duplicate"


def test_proof_constraint_universe_must_equal_registered_slot_universe(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    mutated = copy.deepcopy(request)
    for variant in mutated["variants"]:
        bundle = next(
            row for row in variant["bundles"] if row["option_id"] == OPTION_A
        )
        scenario = bundle["scenario"]
        compilation = bundle["compilation"]
        path = compilation["paths"][0]
        extra = scenario_proof.seal_request(
            {
                "object_type": "registered_constraint",
                "schema_version": "0.1.0",
                "record_sha256": "0" * 64,
                "constraint_id": "constraint:decision.fixture.a.extra",
                "scenario_id": scenario["scenario_id"],
                "scenario_record_sha256": scenario["record_sha256"],
                "compilation_record_sha256": compilation["record_sha256"],
                "path_id": path["path_id"],
                "metric": "gross_affected_share",
                "operator": "upper_bound_lte",
                "threshold": {
                    "value": 10.0,
                    "unit": "percentage_points_of_edge_denominator",
                    "denominator": path["hops"][0]["magnitude"]["denominator"],
                },
                "epistemic_kind": "hypothetical_normative_boundary",
                "origin": "user_supplied",
                "evidence_id": None,
                "real_world_feasibility_claimed": False,
            }
        )
        proof_request = copy.deepcopy(bundle["scenario_proof_request"])
        proof_request["constraints"].append(extra)
        proof_request["constraints"].sort(key=lambda row: row["constraint_id"])
        proof_request = scenario_proof.seal_request(proof_request)
        proof = scenario_proof.execute_scenario_proof(
            base.base.manifest,
            scenario,
            compilation,
            proof_request,
            **_paths(base),
        )
        bundle["scenario_proof_request"] = proof_request
        bundle["scenario_proof_execution"] = proof
        replacement = decision_switch.seal_record(bundle)
        variant["bundles"] = [
            replacement if row["option_id"] == OPTION_A else row
            for row in variant["bundles"]
        ]
    mutated = _reseal(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, mutated)
    assert exc.value.code == "decision_switch_constraint_partition_invalid"


def test_dependency_proof_mutation_never_yields_partial_decision_output(
    decision_fixture: tuple[shock_compiler_fixture.ShockFixture, dict[str, Any]],
) -> None:
    base, request = decision_fixture
    mutated = copy.deepcopy(request)
    proof = mutated["variants"][0]["bundles"][0]["scenario_proof_execution"]
    proof["constraints"][0]["interval_relation"] = "no_registered_values_satisfy"
    proof = decision_switch.seal_record(proof)
    mutated["variants"][0]["bundles"][0]["scenario_proof_execution"] = proof
    mutated["variants"][0]["bundles"][0] = decision_switch.seal_record(
        mutated["variants"][0]["bundles"][0]
    )
    mutated = _reseal(mutated)
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        _execute(base, mutated)
    assert exc.value.code == "decision_switch_scenario_proof_invalid"


def test_profile_contract_lists_every_adversarial_boundary() -> None:
    cases = json.loads((ROOT / EXTENSION / "adversarial-cases.json").read_text())
    assert "incomplete_or_duplicate_powerset_member" in cases["refusal_cases"]
    assert "hidden_semantic_change_outside_active_atom" in cases["refusal_cases"]
    assert "proof_constraint_outside_registered_slot_universe" in cases[
        "refusal_cases"
    ]
    assert "constraint_or_hypothesis_remapped_to_different_registered_path" in cases[
        "refusal_cases"
    ]
    assert "cross_case_switch_identity_collision" in cases["refusal_cases"]
    assert "expected_voi_entropy_or_uniform_probability_inferred" in cases[
        "refusal_cases"
    ]
    assert "multi_atom_minimal_switch" in cases["valid_cases"]


def test_official_request_byte_parser_rejects_duplicate_keys_and_non_finite() -> None:
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        decision_switch.parse_request_bytes(b'{"object_type":"a","object_type":"b"}')
    assert exc.value.code == "decision_switch_json_duplicate_key"
    with pytest.raises(decision_switch.DecisionSwitchError) as exc:
        decision_switch.parse_request_bytes(b'{"value":NaN}')
    assert exc.value.code == "decision_switch_json_non_finite"


def test_contract_contains_no_total_priority_or_policy_advice_surface() -> None:
    paths = [
        ROOT / EXTENSION / "SPEC.md",
        ROOT / EXTENSION / "decision-switch-request.schema.json",
        ROOT / EXTENSION / "decision-switch-execution.schema.json",
    ]
    joined = "\n".join(path.read_text() for path in paths).lower()
    assert "pareto_layer_not_total_priority_or_recommendation" in joined
    assert "expected_value_computed" in joined
    assert "global_minimality_claimed" in joined
    assert "not_licensed_for_production_rendering" in joined


def test_profile_hashes_are_exact() -> None:
    profile_path = ROOT / EXTENSION / "profile.json"
    profile = json.loads(profile_path.read_text())
    for row in profile["bound_files"]:
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row[
            "sha256"
        ]
    for key in ("reference_implementation", "conformance_test"):
        row = profile[key]
        assert hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest() == row[
            "sha256"
        ]
