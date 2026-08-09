"""One composed synthetic world that every IGRM Max engine reads at once.

Before this fixture each engine built its own world.  `oges_fixture`
produced a signed release; `sensor_fusion_fixture` then rewrote the event
and the rights registry to add seven lanes; `shock_compiler_fixture` and
`evidence_outputs_fixture` each installed their contract over a *fresh*
`oges_fixture` root.  All four called their release
`rel:oges.fixture.2026-08-08` and their event
`evt:oges.fixture.policy.001`, and two of those releases were different
bytes.  Conformance was per engine; the composite was never assembled,
so nothing could notice.

This builds the composite instead: one temporary root, one signing key,
one manifest, one rights registry, with every engine contract installed
over it.  The engines then run against that single release and the join
in `src/max_state_join.py` certifies that they agree.

The world is synthetic and says so.  Its sources carry fixture
authorisations, which is exactly why the join computes
`synthetic_nonproduction` and licenses L0 -- the contract level -- no
matter how many engines composed cleanly over it.  Composition is
evidence that the contract holds together.  It is not evidence about
India, about any dependency, or about anything observed.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict, cast

from src import canonical_objects as canonical
from src import (
    evidence_outputs,
    evidence_outputs_fixture,
    exposure_graph,
    max_state_join,
    sensor_fusion,
    sensor_fusion_fixture,
    shock_compiler,
    shock_compiler_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "data" / "max_state_join_demo.json"

_EVENT_ID = sensor_fusion_fixture._EVENT_ID
_TARGET_ID = shock_compiler_fixture._TARGET_ID
_SUBJECT_ID = shock_compiler_fixture._SUBJECT_ID
_EDGE_ID = shock_compiler_fixture._EDGE_ID

# The fusion window and cutoff the composed world uses. The cutoff must
# equal the release generation time; sensor_fusion enforces that itself
# and the join re-checks it across every engine.
_WINDOW = ("2026-08-08T00:00:00Z", "2026-08-08T12:00:00Z")
_CUTOFF = "2026-08-08T13:00:00Z"


@dataclass(frozen=True)
class ComposedWorld:
    """One signed release with every Max engine contract installed."""

    root: Path
    manifest: Path
    scenario: dict[str, Any]


class _Governance(TypedDict):
    """The five registry paths every Max engine takes by the same names."""

    schema_registry_path: Path
    rights_registry_path: Path
    rights_signers_path: Path
    method_registry_path: Path
    release_signers_path: Path


def _governance(root: Path) -> _Governance:
    governance = root / "governance"
    return _Governance(
        schema_registry_path=governance / "canonical_schema_registry.json",
        rights_registry_path=governance / "source_rights_registry.json",
        rights_signers_path=governance / "rights_signers.json",
        method_registry_path=governance / "canonical_method_registry.json",
        release_signers_path=governance / "release_signers.json",
    )


def build_world(destination: Path) -> ComposedWorld:
    """Build the single release every engine will read.

    The sensor fixture is built first because it is the only builder that
    *rewrites* the event and manifest; installing the remaining contracts
    afterwards leaves one manifest that satisfies all four engines. Any
    other order would silently produce the divergence this module exists
    to eliminate.
    """

    fixture = sensor_fusion_fixture.build_fixture(destination)
    shock_compiler_fixture._install_contract(fixture.root)
    evidence_outputs_fixture._install_contract(fixture.root)
    manifest = cast(dict[str, Any], json.loads(fixture.manifest.read_text()))
    scenario = shock_compiler_fixture.build_scenario(manifest)
    return ComposedWorld(root=fixture.root, manifest=fixture.manifest, scenario=scenario)


def run_engines(world: ComposedWorld) -> dict[str, dict[str, Any]]:
    """Run every registered engine against the one composed release."""

    governance = _governance(world.root)
    traversal = exposure_graph.project_event_exposure(
        world.manifest,
        _EVENT_ID,
        _TARGET_ID,
        root=world.root,
        **governance,
    )
    fusion = sensor_fusion.fuse_event_sensors(
        world.manifest,
        _EVENT_ID,
        _WINDOW[0],
        _WINDOW[1],
        _CUTOFF,
        root=world.root,
        **governance,
        fusion_registry_path=world.root / "governance" / "sensor_fusion_registry.json",
    )
    compilation = shock_compiler.compile_shock(
        world.manifest,
        world.scenario,
        root=world.root,
        **governance,
        shock_registry_path=world.root / "governance" / "shock_compiler_registry.json",
    )
    outputs = evidence_outputs.compile_evidence_outputs(
        world.manifest,
        _EVENT_ID,
        _TARGET_ID,
        root=world.root,
        **governance,
        output_registry_path=world.root / "governance" / "evidence_output_registry.json",
    )
    return {
        "exposure_traversal": traversal,
        "sensor_fusion": fusion,
        "shock_compilation": compilation,
        "evidence_output_set": outputs,
    }


def source_states(world: ComposedWorld) -> dict[str, dict[str, Any]]:
    """Return the source records of the exact rights registry the release seals.

    Reading whichever registry happens to be on disk would defeat the
    point: the digest is checked against the one the signed manifest
    committed to, so a swapped registry refuses instead of quietly
    re-classifying the world.
    """

    governance = _governance(world.root)
    validated = canonical.load_validated_release(
        world.manifest, root=world.root, **governance
    )
    rights_path = governance["rights_registry_path"]
    registry, registry_sha = max_state_join._read_json(
        rights_path, "join_rights_registry_unreadable"
    )
    if registry_sha != validated.manifest.get("rights_registry_sha256"):
        raise max_state_join.MaxStateJoinError("join_rights_registry_digest_mismatch")
    return {
        cast(str, record["source_id"]): record
        for record in cast(list[dict[str, Any]], registry["sources"])
        if isinstance(record.get("source_id"), str)
    }


def join_world(world: ComposedWorld) -> dict[str, Any]:
    """Run every engine over *world* and certify one governed state."""

    return max_state_join.join_engine_states(
        run_engines(world),
        rights_root=world.root,
        rights_registry_path=world.root / "governance" / "source_rights_registry.json",
        rights_signers_path=world.root / "governance" / "rights_signers.json",
    )


def build_demo() -> dict[str, Any]:
    """Return the deterministic synthetic public conformance vector."""

    with tempfile.TemporaryDirectory(prefix="igrm-max-state-join-") as temporary:
        world = build_world(Path(temporary))
        join = join_world(world)
    return {
        "_meta": {
            "schema": "igrm-max-state-join-demo-v1",
            "generated": "2026-08-09T09:00:00Z",
            "date": "2026-08-09",
            "what": (
                "Deterministic synthetic certificate that one signed release read "
                "by the exposure traversal, sensor fusion, shock compiler and "
                "evidence output engines yields one governed state: one release "
                "identity, no object-identity collision, one rights position and "
                "one temporal boundary."
            ),
            "scope": "synthetic_test_vector_only",
            "production_release": False,
            "real_event_entity_source_right_exposure_or_adoption_claims": False,
            "numeric_fusion_averaging_or_unit_conversion_performed": False,
            "forecast_probability_causation_advice_or_scalar_score": False,
            "agreement_is_not_accuracy": True,
            "license": "CC BY 4.0",
            "citation": (
                "Krishna, Ishan (2026). India Geopolitical Risk Monitor. https://igrm.in/"
            ),
            "source": "https://igrm.in/data/max_state_join_demo.json",
            "codebook": "https://igrm.in/standard.html",
            "method": "method:igrm.max_state_join@1.0.0",
        },
        "synthetic_labels": {
            _EVENT_ID: "Synthetic policy action",
            _SUBJECT_ID: "Synthetic origin country",
            _TARGET_ID: "Synthetic crude input",
            _EDGE_ID: "Synthetic import-dependence edge",
        },
        "join": join,
    }


def write_demo(path: Path = DEMO) -> None:
    """Write the byte-deterministic public demo payload."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_demo(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:  # pragma: no cover - CLI
    write_demo()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
