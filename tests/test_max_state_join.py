"""The join must refuse the exact divergence that shipped unnoticed.

On 2026-08-08 four IGRM Max conformance artifacts were published side by
side.  `docs/data/evidence_outputs_demo.json` and
`docs/data/sensor_fusion_demo.json` both named release
`rel:oges.fixture.2026-08-08` and event `evt:oges.fixture.policy.001`.
Their release records were `e6cc1e33...` and `8fd9d220...`; their event
records were `26102763...` and `224bc5ff...`; they had compiled against
different rights registries.  Every engine gate was green.  There was no
gate that could go red, because no code in the repository had ever
compared one engine's output to another's.

These tests are that comparison.  The first group asserts the composed
world certifies; the second asserts each way of breaking it refuses, by
stable code, with the composed world as the control.  A test that only
proved the happy path would be the same defect one level up.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest
from src import canonical_objects as canonical
from src import evidence_outputs_fixture, exposure_graph
from src import max_state_join as join
from src import max_state_join_fixture as fixture

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "docs" / "data" / "max_state_join_demo.json"
REGISTRY = ROOT / "governance" / "max_state_join_registry.json"
SCHEMA = ROOT / "schemas" / "max-state-join.schema.json"
PUBLISHED_DATA = ROOT / "docs" / "data"

_EVENT_ID = "evt:oges.fixture.policy.001"
_TARGET_ID = "ent:commodity.synthetic_crude"


@pytest.fixture(scope="module")
def composed() -> Any:
    """One composed world, its engine outputs and its source records."""

    with tempfile.TemporaryDirectory(prefix="igrm-join-test-") as temporary:
        world = fixture.build_world(Path(temporary))
        yield {
            "world": world,
            "engines": fixture.run_engines(world),
            "sources": fixture.source_states(world),
            "rights_registry": world.root
            / "governance"
            / "source_rights_registry.json",
            "rights_signers": world.root / "governance" / "rights_signers.json",
        }


def _join(composed: Any, engines: Any = None, *, with_rights: bool = True) -> dict[str, Any]:
    kwargs = {}
    if with_rights:
        kwargs = {
            "rights_root": composed["world"].root,
            "rights_registry_path": composed["rights_registry"],
            "rights_signers_path": composed["rights_signers"],
        }
    return join.join_engine_states(
        composed["engines"] if engines is None else engines, **kwargs
    )


def _policy_class(composed: Any, sources: dict[str, dict[str, Any]]) -> str:
    contract = join._load_contract(join.ROOT, join.JOIN_REGISTRY)
    rights: dict[str, dict[str, str]] = {}
    for engine_id, document in composed["engines"].items():
        rights.update(join._rights_rows(engine_id, document))
    return join._evidence_class(contract, rights, sources)


# ---------------------------------------------------------------------------
# the composed world certifies
# ---------------------------------------------------------------------------


def test_one_release_read_by_every_engine_certifies_one_governed_state(composed):
    document = _join(composed)
    assert document["object_type"] == "max_state_join"
    assert document["result"]["status"] == "one_governed_state"
    assert document["identity"]["collisions"] == []
    assert {row["engine_id"] for row in document["engines"]} == {
        "exposure_traversal",
        "sensor_fusion",
        "shock_compilation",
        "evidence_output_set",
    }


def test_every_engine_reports_the_identical_release_record(composed):
    releases = {
        engine_id: document["release"]["record_sha256"]
        for engine_id, document in composed["engines"].items()
    }
    assert len(set(releases.values())) == 1, releases


def test_the_join_actually_examined_bindings_rather_than_finding_nothing(composed):
    """A detector that inspects nothing also reports no collision."""

    document = _join(composed)
    assert document["identity"]["bindings_examined"] > 50
    assert document["identity"]["distinct_identifiers"] > 5


def test_the_sealed_join_is_its_own_canonical_digest(composed):
    document = _join(composed)
    assert canonical.canonical_record_sha256(document) == document["record_sha256"]


def test_the_join_is_deterministic(composed):
    assert _join(composed) == _join(composed)


# ---------------------------------------------------------------------------
# the divergence that shipped
# ---------------------------------------------------------------------------


def test_engines_built_over_separate_worlds_are_refused(composed):
    """The 2026-08-08 defect, reconstructed.

    A traversal from its own `oges_fixture` root -- exactly how
    `evidence_outputs_fixture` and `shock_compiler_fixture` build today --
    joined to the composed world's other engines. Same release id, same
    event id, different bytes.
    """

    with tempfile.TemporaryDirectory(prefix="igrm-join-other-") as temporary:
        other = evidence_outputs_fixture.build_fixture(Path(temporary))
        governance = other.root / "governance"
        foreign = exposure_graph.project_event_exposure(
            other.manifest,
            _EVENT_ID,
            _TARGET_ID,
            root=other.root,
            schema_registry_path=governance / "canonical_schema_registry.json",
            rights_registry_path=governance / "source_rights_registry.json",
            rights_signers_path=governance / "rights_signers.json",
            method_registry_path=governance / "canonical_method_registry.json",
            release_signers_path=governance / "release_signers.json",
        )

    assert foreign["release"]["release_id"] == (
        composed["engines"]["sensor_fusion"]["release"]["release_id"]
    ), "the reconstruction is only meaningful if both claim one release id"
    assert foreign["release"]["record_sha256"] != (
        composed["engines"]["sensor_fusion"]["release"]["record_sha256"]
    ), "the reconstruction is only meaningful if the bytes differ"

    engines = dict(composed["engines"])
    engines["exposure_traversal"] = foreign
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_release_identity_disagreement"


def test_one_identifier_bound_to_two_records_is_refused(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["sensor_fusion"]["event"]["record_sha256"] = "0" * 64
    engines["sensor_fusion"] = canonical.seal_record(engines["sensor_fusion"])
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_object_identity_collision"
    assert _EVENT_ID in error.value.detail


def test_a_foreign_key_beside_a_digest_is_not_read_as_a_collision(composed):
    """The scenario carries `record_sha256` and a foreign `event_id`.

    An extractor that bound every identifier in a mapping to that
    mapping's digest would refuse the composed world for a collision it
    invented. The ownership rule exists to prevent that, and this asserts
    the scenario really does contain the shape that would trigger it.
    """

    scenario = composed["engines"]["shock_compilation"]["scenario"]
    assert scenario["event_id"] == _EVENT_ID
    assert scenario["record_sha256"] != (
        composed["engines"]["sensor_fusion"]["event"]["record_sha256"]
    )
    assert _join(composed)["result"]["status"] == "one_governed_state"


def test_an_engine_compiled_against_another_rights_registry_is_refused(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["shock_compilation"]["release"]["rights_registry_sha256"] = "1" * 64
    engines["shock_compilation"] = canonical.seal_record(engines["shock_compilation"])
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_release_identity_disagreement"
    assert error.value.detail.startswith("rights_registry_sha256:")


def test_disagreeing_rights_decisions_for_one_source_are_refused(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["shock_compilation"]["rights"][0]["decision_id"] = "some-other-decision"
    engines["shock_compilation"] = canonical.seal_record(engines["shock_compilation"])
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_rights_decision_disagreement"


# ---------------------------------------------------------------------------
# tamper, completeness and temporal boundaries
# ---------------------------------------------------------------------------


def test_an_edited_engine_output_fails_its_own_seal(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["shock_compilation"]["counts"]["gaps"] = 99
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_digest_mismatch"


def test_a_resealed_schema_invalid_engine_is_refused(composed):
    """A content hash is not a schema validation certificate."""

    engines = copy.deepcopy(composed["engines"])
    del engines["exposure_traversal"]["result"]
    engines["exposure_traversal"] = canonical.seal_record(
        engines["exposure_traversal"]
    )
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_schema_violation"


def test_a_resealed_engine_cannot_claim_an_unregistered_implementation(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["sensor_fusion"]["method"]["implementation_sha256"] = "4" * 64
    engines["sensor_fusion"] = canonical.seal_record(engines["sensor_fusion"])
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_implementation_mismatch"


def test_a_resealed_engine_cannot_claim_another_contract_registry(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["evidence_output_set"]["contract"]["output_registry_sha256"] = "5" * 64
    engines["evidence_output_set"] = canonical.seal_record(
        engines["evidence_output_set"]
    )
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_registry_digest_mismatch"


def test_a_missing_required_engine_is_refused(composed):
    engines = {
        engine_id: document
        for engine_id, document in composed["engines"].items()
        if engine_id != "exposure_traversal"
    }
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_missing"


def test_an_unregistered_engine_is_refused(composed):
    engines = dict(composed["engines"])
    engines["something_new"] = composed["engines"]["sensor_fusion"]
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_unregistered"


def test_an_engine_output_of_the_wrong_type_is_refused(composed):
    engines = dict(composed["engines"])
    engines["shock_compilation"] = composed["engines"]["sensor_fusion"]
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_engine_object_type_mismatch"


def test_a_knowledge_cutoff_after_the_release_is_refused(composed):
    engines = copy.deepcopy(composed["engines"])
    engines["shock_compilation"]["scenario"]["knowledge_cutoff"] = "2027-01-01T00:00:00Z"
    engines["shock_compilation"] = canonical.seal_record(engines["shock_compilation"])
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_knowledge_cutoff_after_release"


def test_the_reported_denominator_is_the_one_observed_not_the_one_named(composed):
    """The denominator travels as a count, not as a label.

    `named:eight_registered_semantic_lanes` is a name; the join reports
    the population it actually counted. If a lane goes missing the number
    must move, otherwise a shrinking frame keeps its old headline and the
    conflict check below has nothing to compare.
    """

    engines = copy.deepcopy(composed["engines"])
    fused = engines["sensor_fusion"]
    fused["coverage"]["observed_lane_ids"] = list(
        fused["coverage"]["observed_lane_ids"]
    )[:-1]
    engines["sensor_fusion"] = canonical.seal_record(fused)

    document = _join(composed, engines)
    observed = {
        row["population_key"]: row["denominator"] for row in document["coverage"]
    }
    assert observed["named:eight_registered_semantic_lanes"] == 7


def test_coverage_denominator_conflict_between_engines_is_refused(composed):
    """Two engines counting one population differently is a refusal.

    An engine that reports seven lanes where another reports eight is
    describing a different frame under the same name, which is how a
    coverage figure stops meaning anything.
    """

    engines = copy.deepcopy(composed["engines"])
    shock = engines["shock_compilation"]
    shock["coverage"][0]["counts"]["total_eligible"] = 2
    shock["coverage"][0]["counts"]["included"] = 2
    engines["shock_compilation"] = canonical.seal_record(shock)
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_coverage_denominator_disagreement"


# ---------------------------------------------------------------------------
# evidence class and licensed maturity are computed, never accepted
# ---------------------------------------------------------------------------


def test_a_fixture_authorised_world_is_synthetic_and_licensed_at_l0(composed):
    document = _join(composed)
    assert document["result"]["evidence_class"] == "synthetic_nonproduction"
    assert document["result"]["licensed_maturity"] == "L0"
    assert document["result"]["public_claim_state"] == "contract_conformance_only"


def test_a_world_without_provable_source_records_cannot_claim_observation(composed):
    document = _join(composed, with_rights=False)
    assert document["result"]["evidence_class"] == "synthetic_nonproduction"
    assert document["result"]["licensed_maturity"] == "L0"


def test_an_unapproved_rights_decision_makes_the_world_unpublishable(composed):
    sources = {key: dict(value) for key, value in composed["sources"].items()}
    sources["oges_fixture_source"]["decision_state"] = "review_required"
    assert _policy_class(composed, sources) == "unapproved_rights"


def test_one_unapproved_source_among_many_still_refuses(composed):
    sources = {key: dict(value) for key, value in composed["sources"].items()}
    sources["sensor_fixture_news"]["decision_state"] = "expired"
    assert _policy_class(composed, sources) == "unapproved_rights"


def test_a_source_the_release_does_not_carry_is_refused(composed):
    sources = {
        key: value
        for key, value in composed["sources"].items()
        if key != "sensor_fixture_news"
    }
    with pytest.raises(join.MaxStateJoinError) as error:
        _policy_class(composed, sources)
    assert error.value.code == "join_rights_source_not_in_release"


def test_approved_non_synthetic_sources_reach_l1_and_no_further(composed):
    """L1 is the registered ceiling for observation, not a promotion.

    Composing engines cleanly proves the contract holds; it audits no
    crosswalk, so it cannot license the L2 bounded dependency map that
    IGRM_MAX_SPEC.md defines.
    """

    sources = {key: dict(value) for key, value in composed["sources"].items()}
    for value in sources.values():
        value["access_basis"] = "government_open_data_license_india"
    assert _policy_class(composed, sources) == "observed"
    contract = join._load_contract(join.ROOT, join.JOIN_REGISTRY)
    assert join._licensed_maturity(contract, "observed") == "L1"


def test_a_synthetic_marker_anywhere_caps_the_whole_world(composed):
    sources = {key: dict(value) for key, value in composed["sources"].items()}
    for value in sources.values():
        value["access_basis"] = "government_open_data_license_india"
    sources["sensor_fixture_market"]["access_basis"] = "synthetic_test_authorization"
    assert _policy_class(composed, sources) == "synthetic_nonproduction"


def test_observation_cannot_be_promoted_with_a_caller_supplied_mapping():
    assert "source_states" not in inspect.signature(join.join_engine_states).parameters


def test_a_tampered_rights_registry_cannot_promote_the_join(composed, tmp_path):
    document = json.loads(composed["rights_registry"].read_text(encoding="utf-8"))
    document["sources"][0]["access_basis"] = "government_open_data_license_india"
    path = tmp_path / "source_rights_registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(join.MaxStateJoinError) as error:
        join.join_engine_states(
            composed["engines"],
            rights_root=composed["world"].root,
            rights_registry_path=path,
            rights_signers_path=composed["rights_signers"],
        )
    assert error.value.code in {
        "join_rights_registry_invalid",
        "join_rights_registry_digest_mismatch",
    }


def test_engine_rights_must_match_the_signed_registry(composed):
    engines = copy.deepcopy(composed["engines"])

    def rewrite(node: Any) -> None:
        if isinstance(node, dict):
            if (
                node.get("source_id") == "sensor_fixture_news"
                and all(field in node for field in join._RIGHTS_FIELDS)
            ):
                node["decision_id"] = "spoofed-decision"
            for value in node.values():
                rewrite(value)
        elif isinstance(node, list):
            for value in node:
                rewrite(value)

    for engine_id, document in engines.items():
        rewrite(document)
        engines[engine_id] = canonical.seal_record(document)
    with pytest.raises(join.MaxStateJoinError) as error:
        _join(composed, engines)
    assert error.value.code == "join_rights_decision_registry_mismatch"


def test_conflicting_rights_inside_one_engine_are_refused():
    document = {
        "rows": [
            {
                "source_id": "source:a",
                "decision_id": "decision:a",
                "decision_artifact_sha256": "1" * 64,
                "signer_id": "signer:a",
            },
            {
                "source_id": "source:a",
                "decision_id": "decision:b",
                "decision_artifact_sha256": "2" * 64,
                "signer_id": "signer:a",
            },
        ]
    }
    with pytest.raises(join.MaxStateJoinError) as error:
        join._rights_rows("engine:a", document)
    assert error.value.code == "join_rights_decision_disagreement"


def test_no_maturity_level_above_the_registered_ceiling_is_reachable():
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    policy = document["join"]["maturity_policy"]
    assert policy["synthetic_nonproduction"] == "L0"
    assert policy["unapproved_rights"] == "L0"
    assert policy["observed"] in {"L0", "L1"}, (
        "L2 and above require an audited crosswalk and external study, "
        "which no amount of engine agreement supplies"
    )


# ---------------------------------------------------------------------------
# contract integrity
# ---------------------------------------------------------------------------


def test_the_registry_pins_the_exact_implementation_and_schema_bytes():
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    row = document["join"]
    for path_key, digest_key in (
        ("implementation_path", "implementation_sha256"),
        ("output_schema_path", "output_schema_sha256"),
        ("common_schema_path", "common_schema_sha256"),
    ):
        target = ROOT / row[path_key]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == row[digest_key], (
            f"{row[path_key]} changed without repinning {digest_key}"
        )


def test_the_registry_default_policy_is_deny():
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assert document["default_policy"] == "deny"


def test_a_tampered_implementation_digest_refuses_to_load(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["join"]["implementation_sha256"] = "2" * 64
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(join.MaxStateJoinError) as error:
        join._load_contract(ROOT, path)
    assert error.value.code == "join_implementation_digest_mismatch"


def test_a_tampered_output_schema_digest_refuses_to_load(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["join"]["output_schema_sha256"] = "3" * 64
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(join.MaxStateJoinError) as error:
        join._load_contract(ROOT, path)
    assert error.value.code == "join_output_schema_digest_mismatch"


def test_a_registry_that_permits_by_default_refuses_to_load(tmp_path):
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    document["default_policy"] = "allow"
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(join.MaxStateJoinError) as error:
        join._load_contract(ROOT, path)
    assert error.value.code == "join_registry_default_policy_invalid"


def test_every_registered_engine_names_a_method_the_repository_implements():
    document = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registries = {
        "method:igrm.exposure_graph_projection": ROOT
        / "governance"
        / "exposure_projection_registry.json",
        "method:igrm.sensor_fusion": ROOT / "governance" / "sensor_fusion_registry.json",
        "method:igrm.shock_compiler": ROOT / "governance" / "shock_compiler_registry.json",
        "method:igrm.evidence_outputs": ROOT
        / "governance"
        / "evidence_output_registry.json",
    }
    for engine in document["join"]["engines"]:
        path = registries[engine["method_id"]]
        text = path.read_text(encoding="utf-8")
        assert engine["method_id"] in text, f"{engine['engine_id']} names no live method"


def test_the_identity_namespace_covers_every_object_type_the_release_carries(composed):
    """A new canonical object type must join the namespace table.

    Without an entry, `{"object_type": "x", "object_id": I}` lands in its
    own namespace and is never compared against a typed `x_id` field,
    which is silently narrower coverage rather than a failure.
    """

    world = composed["world"]
    validated = canonical.load_validated_release(
        world.manifest, root=world.root, **fixture._governance(world.root)
    )
    for object_type in validated.objects:
        assert object_type in join._OBJECT_TYPE_NAMESPACE, (
            f"canonical object type {object_type!r} is not in "
            "_OBJECT_TYPE_NAMESPACE, so the join cannot compare it across engines"
        )


# ---------------------------------------------------------------------------
# published artifact
# ---------------------------------------------------------------------------


def test_the_published_demo_is_the_current_deterministic_output():
    assert DEMO.is_file(), "docs/data/max_state_join_demo.json is missing"
    published = json.loads(DEMO.read_text(encoding="utf-8"))
    assert published == fixture.build_demo()


def test_four_published_primary_records_are_the_exact_records_joined(composed):
    """Regress the public split-world defect using committed bytes, not builders."""

    records = fixture.load_published_engine_records()
    for record in records.values():
        assert canonical.canonical_record_sha256(record) == record["record_sha256"]

    joined = join.join_engine_states(
        records,
        rights_root=composed["world"].root,
        rights_registry_path=composed["rights_registry"],
        rights_signers_path=composed["rights_signers"],
    )
    certified = {
        row["engine_id"]: row["record_sha256"] for row in joined["engines"]
    }
    committed = json.loads(DEMO.read_text(encoding="utf-8"))["join"]
    expected = {
        row["engine_id"]: row["record_sha256"] for row in committed["engines"]
    }
    assert certified == expected == {
        engine_id: record["record_sha256"]
        for engine_id, record in records.items()
    }


def test_published_records_bind_one_release_rights_digest_and_event(composed):
    records = fixture.load_published_engine_records()
    assert len({row["release"]["record_sha256"] for row in records.values()}) == 1
    assert len(
        {row["release"]["rights_registry_sha256"] for row in records.values()}
    ) == 1

    def event_references(node: object) -> list[str]:
        if isinstance(node, dict):
            own = [node["event_id"]] if isinstance(node.get("event_id"), str) else []
            return own + [
                event_id
                for value in node.values()
                for event_id in event_references(value)
            ]
        if isinstance(node, list):
            return [
                event_id for value in node for event_id in event_references(value)
            ]
        return []

    bound_events: set[str] = set()
    for engine_id, record in records.items():
        assert set(event_references(record)) == {_EVENT_ID}
        bound_events.update(
            row["identifier"]
            for row in join._identity_bindings(engine_id, record)
            if row["identifier_kind"] == "event_id"
        )
    assert bound_events == {_EVENT_ID}


def test_published_records_refuse_an_independently_regenerated_world(composed):
    records = fixture.load_published_engine_records()
    with tempfile.TemporaryDirectory(prefix="igrm-join-foreign-") as temporary:
        other = evidence_outputs_fixture.build_fixture(Path(temporary))
        governance = other.root / "governance"
        foreign = exposure_graph.project_event_exposure(
            other.manifest,
            _EVENT_ID,
            _TARGET_ID,
            root=other.root,
            schema_registry_path=governance / "canonical_schema_registry.json",
            rights_registry_path=governance / "source_rights_registry.json",
            rights_signers_path=governance / "rights_signers.json",
            method_registry_path=governance / "canonical_method_registry.json",
            release_signers_path=governance / "release_signers.json",
        )
    records["exposure_traversal"] = foreign
    with pytest.raises(join.MaxStateJoinError) as error:
        join.join_engine_states(records)
    assert error.value.code == "join_release_identity_disagreement"


def test_published_records_refuse_missing_exposure_foreign_rights_and_stale_time():
    records = fixture.load_published_engine_records()

    without_exposure = dict(records)
    del without_exposure["exposure_traversal"]
    with pytest.raises(join.MaxStateJoinError) as error:
        join.join_engine_states(without_exposure)
    assert error.value.code == "join_engine_missing"

    foreign_rights = copy.deepcopy(records)
    foreign_rights["shock_compilation"]["release"]["rights_registry_sha256"] = "1" * 64
    foreign_rights["shock_compilation"] = canonical.seal_record(
        foreign_rights["shock_compilation"]
    )
    with pytest.raises(join.MaxStateJoinError) as error:
        join.join_engine_states(foreign_rights)
    assert error.value.code == "join_release_identity_disagreement"

    stale_time = copy.deepcopy(records)
    stale_time["shock_compilation"]["scenario"]["knowledge_cutoff"] = (
        "2027-01-01T00:00:00Z"
    )
    stale_time["shock_compilation"] = canonical.seal_record(
        stale_time["shock_compilation"]
    )
    with pytest.raises(join.MaxStateJoinError) as error:
        join.join_engine_states(stale_time)
    assert error.value.code == "join_knowledge_cutoff_after_release"


def test_published_loader_refuses_a_symlinked_primary_record(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name, _ in fixture._PUBLISHED_RECORDS.values():
        source = PUBLISHED_DATA / name
        target = data / name
        if name == "exposure_traversal_demo.json":
            target.symlink_to(source)
        else:
            target.write_bytes(source.read_bytes())
    with pytest.raises(join.MaxStateJoinError) as error:
        fixture.load_published_engine_records(data)
    assert error.value.code == "join_published_path_invalid"


def test_published_exposure_traversal_is_synthetic_nonproduction():
    published = json.loads(
        (PUBLISHED_DATA / "exposure_traversal_demo.json").read_text(encoding="utf-8")
    )
    assert published["_meta"]["scope"] == "synthetic_test_vector_only"
    assert published["_meta"]["production_release"] is False
    assert published["_meta"]["real_event_entity_source_right_or_exposure_claims"] is False
    assert published["traversal"]["result"]["status"] == "paths_found"


def test_the_published_demo_labels_itself_synthetic_and_claims_nothing():
    published = json.loads(DEMO.read_text(encoding="utf-8"))
    meta = published["_meta"]
    assert meta["scope"] == "synthetic_test_vector_only"
    assert meta["production_release"] is False
    assert meta["real_event_entity_source_right_exposure_or_adoption_claims"] is False
    assert meta["numeric_fusion_averaging_or_unit_conversion_performed"] is False
    assert meta["forecast_probability_causation_advice_or_scalar_score"] is False
    assert meta["agreement_is_not_accuracy"] is True
    result = published["join"]["result"]
    assert result["evidence_class"] == "synthetic_nonproduction"
    assert result["licensed_maturity"] == "L0"


def test_the_published_demo_carries_no_real_source_identifier():
    """A fixture payload naming a real registered source would read as an
    observation of that source. The rights registry's real ids are the
    exact strings that must not appear."""

    published = DEMO.read_text(encoding="utf-8")
    registry = json.loads(
        (ROOT / "governance" / "source_rights_registry.json").read_text(encoding="utf-8")
    )
    for source in registry["sources"]:
        assert source["source_id"] not in published, (
            f"synthetic demo names the real source {source['source_id']!r}"
        )
