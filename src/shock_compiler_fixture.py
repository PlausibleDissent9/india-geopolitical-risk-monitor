"""Deterministic public conformance vector for the bounded Shock Compiler.

The vector uses only the OGES synthetic release.  Its 30--40 percent flow
reduction, 10--14 day duration, 20--30 percent substitution and 3--5 day
buffer are hypothetical test inputs.  It makes no claim about a real event,
entity, source, right, exposure, disruption, probability or recommended act.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from src import canonical_objects as canonical
from src import oges_fixture, shock_compiler

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT = ROOT / "docs" / "data" / "shock_compiler_demo.json"

_EVENT_ID = "evt:oges.fixture.policy.001"
_SUBJECT_ID = "ent:country.synthetic_origin"
_TARGET_ID = "ent:commodity.synthetic_crude"
_EDGE_ID = "edg:oges.fixture.origin_crude.001"


@dataclass(frozen=True)
class ShockFixture:
    base: oges_fixture.Fixture
    scenario: dict[str, Any]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _install_contract(root: Path) -> None:
    copies = (
        ("src/shock_compiler.py", "src/shock_compiler.py"),
        ("src/exposure_graph.py", "src/exposure_graph.py"),
        (
            "governance/shock_compiler_registry.json",
            "governance/shock_compiler_registry.json",
        ),
        (
            "governance/exposure_projection_registry.json",
            "governance/exposure_projection_registry.json",
        ),
        ("schemas/shock-scenario.schema.json", "schemas/shock-scenario.schema.json"),
        (
            "schemas/shock-compilation.schema.json",
            "schemas/shock-compilation.schema.json",
        ),
        (
            "schemas/exposure-traversal.schema.json",
            "schemas/exposure-traversal.schema.json",
        ),
    )
    for source, destination in copies:
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, target)


def build_scenario(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return the strict synthetic scenario bound to *manifest*."""

    return cast(
        dict[str, Any],
        canonical.seal_record(
            {
                "object_type": "shock_scenario",
                "schema_version": "1.0.0",
                "record_sha256": "0" * 64,
                "scenario_id": "scenario:shock.fixture.origin_flow.001",
                "created_at": "2026-08-08T13:05:00Z",
                "release": {
                    "release_id": manifest["release_id"],
                    "record_sha256": manifest["record_sha256"],
                    "generated_at": manifest["generated_at"],
                    "effective_date": manifest["effective_date"],
                },
                "knowledge_cutoff": manifest["generated_at"],
                "event_id": _EVENT_ID,
                "target_entity_id": _TARGET_ID,
                "shock_subject_entity_id": _SUBJECT_ID,
                "purpose": "bounded_stress_test",
                "shock": {
                    "assumption": {
                        "assumption_id": "assumption:shock.fixture.flow_reduction",
                        "status": "hypothetical",
                        "origin": "user_supplied",
                        "evidence_id": None,
                    },
                    "quantity": "subject_flow_reduction",
                    "magnitude": {
                        "lower": 30,
                        "upper": 40,
                        "unit": "percent_of_subject_flow_reduced",
                    },
                    "duration": {"lower": 10, "upper": 14, "unit": "days"},
                    "effective_start": "2026-08-08",
                    "effective_end": "2026-08-21",
                },
                "substitutions": [
                    {
                        "assumption": {
                            "assumption_id": "assumption:shock.fixture.substitution",
                            "status": "hypothetical",
                            "origin": "user_supplied",
                            "evidence_id": None,
                        },
                        "applies_to_edge_id": _EDGE_ID,
                        "fraction_of_gross_effect": {
                            "lower": 20,
                            "upper": 30,
                            "unit": "percent_of_gross_affected_share_substituted",
                        },
                    }
                ],
                "buffers": [
                    {
                        "assumption": {
                            "assumption_id": "assumption:shock.fixture.buffer",
                            "status": "hypothetical",
                            "origin": "user_supplied",
                            "evidence_id": None,
                        },
                        "applies_to_target_entity_id": _TARGET_ID,
                        "duration_offset": {
                            "lower": 3,
                            "upper": 5,
                            "unit": "days",
                        },
                    }
                ],
                "traversal": {"max_hops": 4, "max_paths": 25},
                "guardrails": {
                    "forecast_performed": False,
                    "probability_assigned": False,
                    "causal_attribution_performed": False,
                    "recommendation_generated": False,
                    "cross_unit_aggregation_performed": False,
                },
                "limitations": sorted(shock_compiler._SCENARIO_LIMITATIONS),
            }
        ),
    )


def build_fixture(destination: Path) -> ShockFixture:
    """Build a signed release plus one release-bound scenario."""

    base = oges_fixture.build_fixture(destination)
    _install_contract(base.root)
    manifest = cast(dict[str, Any], json.loads(base.manifest.read_text()))
    return ShockFixture(base=base, scenario=build_scenario(manifest))


def compile_fixture(fixture: ShockFixture) -> dict[str, Any]:
    """Compile *fixture* through the same strict public engine."""

    root = fixture.base.root
    return shock_compiler.compile_shock(
        fixture.base.manifest,
        fixture.scenario,
        root=root,
        schema_registry_path=root / "governance" / "canonical_schema_registry.json",
        rights_registry_path=root / "governance" / "source_rights_registry.json",
        rights_signers_path=root / "governance" / "rights_signers.json",
        method_registry_path=root / "governance" / "canonical_method_registry.json",
        release_signers_path=root / "governance" / "release_signers.json",
        shock_registry_path=root / "governance" / "shock_compiler_registry.json",
    )


def build_demo() -> dict[str, Any]:
    """Return the public payload from the one composed Max fixture world."""

    from src import max_state_join_fixture

    return max_state_join_fixture.build_published_artifacts().shock_compiler


def _build_demo_payload(
    scenario: dict[str, Any], compilation: dict[str, Any]
) -> dict[str, Any]:
    """Wrap an already-compiled shock without rebuilding a private world."""

    return {
        "_meta": {
            "schema": "igrm-shock-compiler-demo-v1",
            "generated": "2026-08-08T13:05:00Z",
            "date": "2026-08-08",
            "what": "Deterministic synthetic bounded Shock Compiler conformance vector.",
            "scope": "synthetic_test_vector_only",
            "production_release": False,
            "real_entity_source_rights_exposure_or_disruption_claims": False,
            "forecast_probability_causation_advice_or_scalar_score": False,
            "license": "CC BY 4.0",
            "citation": "Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/",
            "source": "https://igrm.in/data/shock_compiler_demo.json",
            "codebook": "https://igrm.in/standard.html",
            "method": "method:igrm.shock_compiler@1.0.0",
        },
        "synthetic_labels": {
            _EVENT_ID: "Synthetic policy action",
            _SUBJECT_ID: "Synthetic origin country",
            _TARGET_ID: "Synthetic crude input",
            _EDGE_ID: "Synthetic import-dependence edge",
        },
        "scenario": scenario,
        "compilation": compilation,
    }


def main() -> None:
    _write_json(PUBLIC_OUTPUT, build_demo())
    print(PUBLIC_OUTPUT)


if __name__ == "__main__":
    main()
