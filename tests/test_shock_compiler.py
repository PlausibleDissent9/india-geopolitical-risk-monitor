from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from src import canonical_objects as canonical
from src import exposure_graph, shock_compiler, shock_compiler_fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def shock_fixture(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[shock_compiler_fixture.ShockFixture]:
    fixture = shock_compiler_fixture.build_fixture(
        tmp_path_factory.mktemp("shock-compiler")
    )
    yield fixture


def _paths(fixture: shock_compiler_fixture.ShockFixture) -> dict[str, Path]:
    root = fixture.base.root
    return {
        "schema_registry_path": root / "governance" / "canonical_schema_registry.json",
        "rights_registry_path": root / "governance" / "source_rights_registry.json",
        "rights_signers_path": root / "governance" / "rights_signers.json",
        "method_registry_path": root / "governance" / "canonical_method_registry.json",
        "release_signers_path": root / "governance" / "release_signers.json",
        "shock_registry_path": root / "governance" / "shock_compiler_registry.json",
    }


def _compile(
    fixture: shock_compiler_fixture.ShockFixture,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return shock_compiler.compile_shock(
        fixture.base.manifest,
        scenario or fixture.scenario,
        root=fixture.base.root,
        **_paths(fixture),
    )


def _validate(
    fixture: shock_compiler_fixture.ShockFixture,
    document: dict[str, Any],
    scenario: dict[str, Any] | None = None,
) -> None:
    shock_compiler.validate_shock_compilation(
        document,
        fixture.base.manifest,
        scenario or fixture.scenario,
        root=fixture.base.root,
        **_paths(fixture),
    )


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def _rebind_scenario(fixture: shock_compiler_fixture.ShockFixture) -> None:
    manifest = json.loads(fixture.base.manifest.read_text())
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


def _rewrite_object(
    fixture: shock_compiler_fixture.ShockFixture,
    object_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    path = fixture.base.objects[object_id]
    document = json.loads(path.read_text())
    mutate(document)
    document = canonical.seal_record(document)
    _write_json(path, document)
    manifest = json.loads(fixture.base.manifest.read_text())
    row = next(item for item in manifest["objects"] if item["object_id"] == object_id)
    row["file_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    row["record_sha256"] = document["record_sha256"]
    manifest = canonical.seal_record(manifest)
    _write_json(fixture.base.manifest, manifest)
    fixture.base.release_signature.write_bytes(
        fixture.base.release_private_key.sign(fixture.base.manifest.read_bytes())
    )
    _rebind_scenario(fixture)


def _scenario_mutation(
    fixture: shock_compiler_fixture.ShockFixture,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    scenario = copy.deepcopy(fixture.scenario)
    mutate(scenario)
    return cast(dict[str, Any], canonical.seal_record(scenario))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def test_signed_release_compiles_exact_deterministic_bounded_ranges(
    shock_fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    first = _compile(shock_fixture)
    second = _compile(shock_fixture)

    assert first == second
    assert canonical.canonical_record_sha256(first) == first["record_sha256"]
    assert first["counts"] == {
        "structural_paths": 1,
        "bounded_paths": 1,
        "abstained_paths": 0,
        "stale_hops": 0,
        "unknown_freshness_hops": 0,
        "gaps": 0,
        "assumptions": 3,
        "assumptions_used": 3,
    }
    assert first["result"] == {
        "status": "compiled",
        "public_claim_state": "requires_claim_bundle",
        "forecast_performed": False,
        "probability_assigned": False,
        "causal_attribution_performed": False,
        "recommendation_generated": False,
        "scalar_score_computed": False,
    }
    path = first["paths"][0]
    assert path["edge_ids"] == ["edg:oges.fixture.origin_crude.001"]
    assert path["gross_affected_share"] == {
        "lower": 3.0,
        "upper": 6.0,
        "unit": "percentage_points_of_edge_denominator",
        "denominator": "total synthetic crude-oil import volume in the period",
        "equation": "edge_interval * shock_percent / 100",
        "transform_id": "transform:shock.gross_affected_share",
    }
    assert path["residual_affected_share"]["lower"] == 2.1
    assert path["residual_affected_share"]["upper"] == 4.8
    assert path["residual_duration"]["lower"] == 5
    assert path["residual_duration"]["upper"] == 11
    assert len(path["sensitivity_grid"]) == 4
    assert first["gaps"] == []
    _validate(shock_fixture, first)


def test_scenario_is_hypothetical_release_bound_and_range_only(
    shock_fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    scenario = shock_fixture.scenario
    assert scenario["release"]["record_sha256"] == json.loads(
        shock_fixture.base.manifest.read_text()
    )["record_sha256"]
    assert scenario["knowledge_cutoff"] == scenario["release"]["generated_at"]
    assert scenario["guardrails"] == shock_compiler._GUARDRAILS
    assert scenario["limitations"] == sorted(shock_compiler._SCENARIO_LIMITATIONS)
    assumptions = [
        scenario["shock"]["assumption"],
        *[row["assumption"] for row in scenario["substitutions"]],
        *[row["assumption"] for row in scenario["buffers"]],
    ]
    assert all(row["status"] == "hypothetical" for row in assumptions)
    assert all(row["origin"] == "user_supplied" for row in assumptions)
    assert all(row["evidence_id"] is None for row in assumptions)


@pytest.mark.parametrize(
    "mutate,code",
    [
        (
            lambda row: row["shock"]["magnitude"].update(lower=40, upper=40),
            "shock_primary_interval_invalid",
        ),
        (
            lambda row: row["release"].update(record_sha256="f" * 64),
            "shock_scenario_release_mismatch",
        ),
        (
            lambda row: row.update(knowledge_cutoff="2026-08-08T12:59:59Z"),
            "shock_temporal_binding_invalid",
        ),
        (
            lambda row: row["guardrails"].update(forecast_performed=True),
            "shock_scenario_schema_invalid",
        ),
        (
            lambda row: row["substitutions"][0].update(
                applies_to_edge_id="edg:shock.fixture.invented"
            ),
            "shock_substitution_edge_not_in_release",
        ),
        (
            lambda row: row.update(
                shock_subject_entity_id="ent:country.synthetic_india"
            ),
            "shock_subject_not_event_entry",
        ),
    ],
)
def test_scenario_mutations_fail_closed(
    shock_fixture: shock_compiler_fixture.ShockFixture,
    mutate: Callable[[dict[str, Any]], None],
    code: str,
) -> None:
    scenario = _scenario_mutation(shock_fixture, mutate)
    with pytest.raises(shock_compiler.ShockCompilerError) as exc:
        _compile(shock_fixture, scenario)
    assert exc.value.code == code


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row["counts"].update(bounded_paths=0),
        lambda row: row["paths"][0]["gross_affected_share"].update(lower=1.0),
        lambda row: row["paths"][0]["hops"][0]["freshness"].update(status="stale"),
        lambda row: row["paths"][0]["hops"][0]["coverage"]["counts"].update(
            total_eligible=2
        ),
        lambda row: row["assumption_ledger"][0].update(used_by_path_ids=[]),
        lambda row: row["result"].update(status="partially_compiled"),
    ],
)
def test_resealed_output_mutations_fail_exact_semantic_recompilation(
    shock_fixture: shock_compiler_fixture.ShockFixture,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    result = _compile(shock_fixture)
    mutate(result)
    result = cast(dict[str, Any], canonical.seal_record(result))
    with pytest.raises(shock_compiler.ShockCompilerError) as exc:
        _validate(shock_fixture, result)
    assert exc.value.code == "shock_output_semantic_mismatch"


def test_release_object_tamper_is_refused_before_compilation(tmp_path: Path) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "release-tamper")
    edge_path = fixture.base.objects["edg:oges.fixture.origin_crude.001"]
    edge_path.write_text(edge_path.read_text() + "\n", encoding="utf-8")

    with pytest.raises(canonical.CanonicalObjectError) as exc:
        _compile(fixture)
    assert exc.value.code == "release_object_file_digest_mismatch"


def test_unsupported_unit_keeps_path_but_abstains_and_marks_unused_assumptions(
    tmp_path: Path,
) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "unsupported-unit")
    _rewrite_object(
        fixture,
        "edg:oges.fixture.origin_crude.001",
        lambda row: row["magnitude"].update(unit="percent_of_unregistered_basis"),
    )
    result = _compile(fixture)

    assert result["result"]["status"] == "structural_only"
    assert result["counts"]["bounded_paths"] == 0
    assert result["counts"]["abstained_paths"] == 1
    assert result["paths"][0]["quantification_status"] == "abstained"
    assert result["paths"][0]["gross_affected_share"] is None
    assert "gap:shock.edge_unit_unsupported" in result["paths"][0]["gap_codes"]
    assert all(not row["used_by_path_ids"] for row in result["assumption_ledger"])
    assert Counter(row["gap_code"] for row in result["gaps"])[
        "gap:shock.unused_assumption"
    ] == 3


def test_stale_edge_remains_visible_and_makes_compilation_partial(tmp_path: Path) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "stale-edge")
    _rewrite_object(
        fixture,
        "edg:oges.fixture.origin_crude.001",
        lambda row: row.update(observed_at="2026-07-01T00:00:00Z"),
    )
    result = _compile(fixture)

    assert result["result"]["status"] == "partially_compiled"
    assert result["counts"]["bounded_paths"] == 1
    assert result["counts"]["stale_hops"] == 1
    assert result["paths"][0]["hops"][0]["freshness"]["status"] == "stale"
    assert [row["gap_code"] for row in result["gaps"]] == [
        "gap:shock.stale_edge"
    ]


def _add_multi_hop_target(fixture: shock_compiler_fixture.ShockFixture) -> None:
    root = fixture.base.root
    entity = json.loads(
        fixture.base.objects["ent:country.synthetic_india"].read_text()
    )
    entity["entity_id"] = "ent:company.synthetic_downstream"
    entity["entity_type"] = "company"
    entity["canonical_name"] = "Synthetic downstream company"
    entity["identifiers"][0]["value"] = "company.synthetic_downstream"
    entity = canonical.seal_record(entity)

    edge = json.loads(
        fixture.base.objects["edg:oges.fixture.origin_crude.001"].read_text()
    )
    edge["edge_id"] = "edg:shock.fixture.crude_company.001"
    edge["source_entity_id"] = "ent:commodity.synthetic_crude"
    edge["target_entity_id"] = entity["entity_id"]
    edge["edge_type"] = "input_dependency"
    edge["magnitude"]["unit"] = "percent_of_input_volume"
    edge["magnitude"]["denominator"] = "total synthetic company input volume"
    edge = canonical.seal_record(edge)

    documents = [entity, edge]
    manifest = json.loads(fixture.base.manifest.read_text())
    counts = Counter()
    for document in documents:
        object_type = document["object_type"]
        object_id = document[canonical._ID_FIELD[object_type]]
        path = root / "canonical" / f"{object_id.replace(':', '__')}.json"
        _write_json(path, document)
        fixture.base.objects[object_id] = path
        manifest["objects"].append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "path": str(path.relative_to(root)),
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "record_sha256": document["record_sha256"],
            }
        )
        counts[object_type] += 1
    manifest["objects"].sort(key=lambda row: (row["object_type"], row["object_id"]))
    for object_type, count in counts.items():
        manifest["counts"][object_type] += count
    manifest = canonical.seal_record(manifest)
    _write_json(fixture.base.manifest, manifest)
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
    scenario["target_entity_id"] = entity["entity_id"]
    scenario["substitutions"][0]["applies_to_edge_id"] = edge["edge_id"]
    scenario["buffers"][0]["applies_to_target_entity_id"] = entity["entity_id"]
    fixture.scenario.clear()
    fixture.scenario.update(canonical.seal_record(scenario))


def test_multi_hop_path_is_structural_only_and_non_subject_entry_is_excluded(
    tmp_path: Path,
) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "multi-hop")
    _add_multi_hop_target(fixture)
    result = _compile(fixture)

    assert result["counts"]["structural_paths"] == 1
    assert result["paths"][0]["edge_ids"] == [
        "edg:oges.fixture.origin_crude.001",
        "edg:shock.fixture.crude_company.001",
    ]
    assert result["paths"][0]["quantification_status"] == "abstained"
    assert result["paths"][0]["reason_code"] == (
        "reason:shock.multi_hop_transform_unregistered"
    )
    assert {row["gap_code"] for row in result["gaps"]} >= {
        "gap:shock.multi_hop_transform_unregistered",
        "gap:shock.non_subject_entry_paths_excluded",
    }
    assert result["result"]["status"] == "structural_only"


def test_compiler_does_not_emit_names_urls_titles_or_source_content(
    shock_fixture: shock_compiler_fixture.ShockFixture,
) -> None:
    result = _compile(shock_fixture)
    forbidden = {
        "canonical_name",
        "canonical_label",
        "title",
        "public_url",
        "artifact_path",
        "content",
        "recommendation",
        "probability",
        "forecast",
    }
    assert forbidden.isdisjoint(_all_keys(result))
    encoded = json.dumps(result, sort_keys=True)
    assert "Synthetic official action" not in encoded
    assert "https://example.test" not in encoded


def test_contract_is_deny_by_default_and_every_registered_byte_is_exact() -> None:
    registry = json.loads(
        (ROOT / "governance" / "shock_compiler_registry.json").read_text()
    )
    engine = registry["engine"]
    assert registry["default_policy"] == "deny"
    for path_key, digest_key in (
        ("implementation_path", "implementation_sha256"),
        ("input_schema_path", "input_schema_sha256"),
        ("output_schema_path", "output_schema_sha256"),
        ("common_schema_path", "common_schema_sha256"),
        (
            "exposure_traversal_schema_path",
            "exposure_traversal_schema_sha256",
        ),
        (
            "exposure_graph_implementation_path",
            "exposure_graph_implementation_sha256",
        ),
        (
            "exposure_projection_registry_path",
            "exposure_projection_registry_sha256",
        ),
    ):
        assert engine[digest_key] == hashlib.sha256(
            (ROOT / engine[path_key]).read_bytes()
        ).hexdigest()
    assert registry["transforms"] == list(shock_compiler._TRANSFORMS)


def test_public_demo_is_exactly_regenerated_and_synthetic_only() -> None:
    expected = shock_compiler_fixture.build_demo()
    committed = json.loads(
        (ROOT / "docs" / "data" / "shock_compiler_demo.json").read_text()
    )
    assert committed == expected
    assert committed["_meta"]["production_release"] is False
    assert (
        committed["_meta"]["real_entity_source_rights_exposure_or_disruption_claims"]
        is False
    )
    assert committed["compilation"]["result"]["forecast_performed"] is False


def test_public_surface_is_bounded_catalogued_and_machine_listed() -> None:
    page = (ROOT / "docs" / "shock.html").read_text(encoding="utf-8")
    normalized_page = " ".join(page.split())
    assert "implemented synthetic conformance foundation" in normalized_page
    assert "not a view of a real disruption" in normalized_page
    assert "Compile assumptions. Never predict" in normalized_page
    assert "not real-world coverage" in normalized_page
    assert "shock_compiler_demo.json" in normalized_page
    assert "shock.js" in normalized_page
    script = (ROOT / "docs" / "shock.js").read_text(encoding="utf-8")
    assert "bounded arithmetic mismatch" in script
    assert 'fetch("data/shock_compiler_demo.json"' in script
    assert "innerHTML" not in script

    catalog = json.loads(
        (ROOT / "design" / "public_product_catalog.json").read_text(encoding="utf-8")
    )
    row = next(row for row in catalog["routes"] if row["path"] == "shock.html")
    assert row["status"] == "public_draft"
    assert row["pillar_id"] == "atlas"
    assert "shock.html" in catalog["protected_routes"]

    contract = json.loads(
        (ROOT / "docs" / "data" / "api_contract.json").read_text(encoding="utf-8")
    )
    endpoints = {row["path"]: row for row in contract["endpoints"]}
    assert endpoints["data/shock_compiler_demo.json"]["stability"] == "stable"
    for name in ("shock-scenario.schema.json", "shock-compilation.schema.json"):
        path = f"schemas/{name}"
        assert endpoints[path]["stability"] == "static synthetic foundation 1.0.0"
        assert (ROOT / "docs" / path).read_bytes() == (ROOT / "schemas" / name).read_bytes()


def test_public_shock_script_parses_when_node_is_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available in this environment")
    result = subprocess.run(
        [node, "--check", str(ROOT / "docs" / "shock.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_fixture_cli_is_deterministic(tmp_path: Path) -> None:
    output = ROOT / "docs" / "data" / "shock_compiler_demo.json"
    before = output.read_bytes()
    result = subprocess.run(
        [sys.executable, "-m", "src.shock_compiler_fixture"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_bytes() == before
    assert str(output) in result.stdout


def test_exposure_projection_refusal_is_not_swallowed(tmp_path: Path) -> None:
    fixture = shock_compiler_fixture.build_fixture(tmp_path / "withdrawn-event")
    _rewrite_object(
        fixture,
        "evt:oges.fixture.policy.001",
        lambda row: (row["lifecycle"].update(state="withdrawn"), row.update(record_status="withdrawn")),
    )
    with pytest.raises(exposure_graph.ExposureGraphError) as exc:
        _compile(fixture)
    assert exc.value.code == "event_not_active"
