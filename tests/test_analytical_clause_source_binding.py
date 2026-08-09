"""Source replay and all-role proof tests for the incumbent clause contract."""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest
from src import analytical_clause as ac
from src import canonical_objects as canonical
from src import evidence_outputs, exposure_graph
from src.oges_fixture import Fixture, build_fixture

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "governance" / "analytical_clause_adversarial_vectors.json"
PROFILE = ROOT / "governance" / "analytical_clause_source_profile.json"
LIMITATIONS = ROOT / "governance" / "analytical_clause_limitation_registry.json"
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _resign(fixture: Fixture, manifest: dict[str, Any]) -> None:
    sealed = canonical.seal_record(manifest)
    _write_json(fixture.manifest, sealed)
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


def _compiled(
    tmp_path: Path, query_id: str = PATH_QUERY
) -> tuple[Fixture, dict[str, Any], dict[str, Any]]:
    fixture = build_fixture(tmp_path)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, query_id, root=fixture.root)
    return fixture, source, proof


def _verify(
    fixture: Fixture,
    query_id: str,
    source: dict[str, Any],
    proof: dict[str, Any],
) -> dict[str, Any]:
    return ac.verify_source_bound_compilation(
        fixture.manifest, query_id, source, proof, root=fixture.root
    )


def _find(source: dict[str, Any], field: str) -> dict[str, Any]:
    rows = [row for row in source["clauses"] if row["proof_binding"]["source_field"] == field]
    assert len(rows) == 1, (field, len(rows))
    return rows[0]


def _find_evidence(source: dict[str, Any], field: str, evidence_id: str) -> dict[str, Any]:
    rows = [
        row
        for row in source["clauses"]
        if row["proof_binding"]["source_field"] == field
        and row["proof_binding"]["source_object_refs"]
        and row["proof_binding"]["source_object_refs"][0]["object_id"] == evidence_id
    ]
    assert len(rows) == 1, (field, evidence_id, len(rows))
    return rows[0]


def _validated_and_traversal(
    fixture: Fixture, query_id: str = PATH_QUERY
) -> tuple[canonical.ValidatedCanonicalRelease, dict[str, Any], dict[str, Any]]:
    _, _, _, queries = ac.load_source_profile(release_effective=date(2026, 8, 8))
    query = queries[query_id]
    kwargs = ac._bundle_kwargs(fixture.root)
    validated = canonical.load_validated_release(fixture.manifest, root=fixture.root, **kwargs)
    traversal = exposure_graph.project_event_exposure(
        fixture.manifest,
        query["event_id"],
        query["target_entity_id"],
        max_hops=query["max_hops"],
        max_paths=query["max_paths"],
        root=fixture.root,
        projection_registry_path=exposure_graph.PROJECTION_REGISTRY,
        **kwargs,
    )
    profile, _, _, _ = ac.load_source_profile(release_effective=date(2026, 8, 8))
    return validated, traversal, profile


def _replace_clause(
    source: dict[str, Any],
    proof: dict[str, Any],
    clause_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_mutation = deepcopy(source)
    proof_mutation = deepcopy(proof)
    clause = next(row for row in source_mutation["clauses"] if row["clause_id"] == clause_id)
    mutate(clause)
    replacement = ac._seal(clause)
    source_mutation["clauses"] = [
        replacement if row["clause_id"] == clause_id else row for row in source_mutation["clauses"]
    ]
    source_mutation = ac._seal(source_mutation)
    proof_mutation["source_bundle_ref"]["record_sha256"] = source_mutation["record_sha256"]
    for role in proof_mutation["roles"]:
        for ref in role["included_clause_refs"]:
            if ref["clause_id"] == clause_id:
                ref["clause_record_sha256"] = replacement["record_sha256"]
    for pair in proof_mutation["cross_role_proof"]["pairs"]:
        for ref in pair["shared_clause_refs"]:
            if ref["clause_id"] == clause_id:
                ref["clause_record_sha256"] = replacement["record_sha256"]
    contract, _ = ac.load_contract()
    views = {
        row["role_id"]: ac.validate_role_view(
            row["role_id"],
            row["included_clause_refs"],
            source_mutation["clauses"],
            contract,
        )
        for row in proof_mutation["roles"]
    }
    invariant = ac.cross_role_invariant(views)
    proof_mutation["cross_role_proof"]["shared_clause_digest_sha256"] = invariant[
        "shared_clause_digest_sha256"
    ]
    return source_mutation, ac._seal(proof_mutation)


def _reseal_changed_source(
    source: dict[str, Any],
    mutations: Mapping[str, Callable[[dict[str, Any]], None]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = deepcopy(source)
    replaced = 0
    clauses = []
    for original in changed["clauses"]:
        clause = deepcopy(original)
        mutate = mutations.get(clause["clause_id"])
        if mutate is not None:
            mutate(clause)
            clause = ac._seal(clause)
            replaced += 1
        clauses.append(clause)
    assert replaced == len(mutations)
    changed["clauses"] = sorted(clauses, key=lambda row: row["clause_id"])
    changed = ac._seal(changed)
    contract, _ = ac.load_contract()
    return changed, ac._compile_role_proof_bundle(changed, contract)


def _add_parallel_edges(fixture: Fixture, total: int = 26) -> None:
    original_path = fixture.objects["edg:oges.fixture.origin_crude.001"]
    original = json.loads(original_path.read_text(encoding="utf-8"))
    manifest = json.loads(fixture.manifest.read_text(encoding="utf-8"))
    for index in range(2, total + 1):
        edge = deepcopy(original)
        edge_id = f"edg:oges.fixture.parallel.{index:03d}"
        edge["edge_id"] = edge_id
        edge = canonical.seal_record(edge)
        path = fixture.root / "canonical" / f"{edge_id.replace(':', '__')}.json"
        _write_json(path, edge)
        fixture.objects[edge_id] = path
        manifest["objects"].append(
            {
                "object_type": "exposure_edge",
                "object_id": edge_id,
                "path": str(path.relative_to(fixture.root)),
                "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "record_sha256": edge["record_sha256"],
            }
        )
    manifest["counts"]["exposure_edge"] = total
    _resign(fixture, manifest)


def _off_path_fixture(root: Path) -> tuple[Fixture, dict[str, Any], dict[str, Any]]:
    fixture = build_fixture(root)
    original_id = "edg:oges.fixture.origin_crude.001"
    alternate_id = "edg:oges.fixture.alternate_crude.001"
    original_path = fixture.objects[original_id]
    original = json.loads(original_path.read_text(encoding="utf-8"))
    alternate = deepcopy(original)
    alternate["edge_id"] = alternate_id
    alternate = canonical.seal_record(alternate)
    alternate_path = fixture.root / "canonical" / "edg__oges.fixture.alternate_crude.001.json"
    _write_json(alternate_path, alternate)
    fixture.objects[alternate_id] = alternate_path

    original["lifecycle"]["state"] = "withdrawn"
    original = canonical.seal_record(original)
    _write_json(original_path, original)

    manifest = json.loads(fixture.manifest.read_text(encoding="utf-8"))
    original_entry = next(row for row in manifest["objects"] if row["object_id"] == original_id)
    original_entry["file_sha256"] = hashlib.sha256(original_path.read_bytes()).hexdigest()
    original_entry["record_sha256"] = original["record_sha256"]
    manifest["objects"].append(
        {
            "object_type": "exposure_edge",
            "object_id": alternate_id,
            "path": str(alternate_path.relative_to(fixture.root)),
            "file_sha256": hashlib.sha256(alternate_path.read_bytes()).hexdigest(),
            "record_sha256": alternate["record_sha256"],
        }
    )
    manifest["counts"]["exposure_edge"] = 2
    _resign(fixture, manifest)
    return fixture, original, alternate


def _add_release_object(
    fixture: Fixture, object_type: str, object_id: str, document: dict[str, Any]
) -> dict[str, Any]:
    sealed = canonical.seal_record(document)
    path = fixture.root / "canonical" / f"{object_id.replace(':', '__')}.json"
    _write_json(path, sealed)
    fixture.objects[object_id] = path
    manifest = json.loads(fixture.manifest.read_text(encoding="utf-8"))
    manifest["objects"].append(
        {
            "object_type": object_type,
            "object_id": object_id,
            "path": str(path.relative_to(fixture.root)),
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "record_sha256": sealed["record_sha256"],
        }
    )
    manifest["counts"][object_type] += 1
    _resign(fixture, manifest)
    return sealed


def _add_unreferenced_evidence(fixture: Fixture) -> dict[str, Any]:
    original = json.loads(
        fixture.objects["evd:oges.fixture.official.001"].read_text(encoding="utf-8")
    )
    evidence_id = "evd:oges.fixture.official.unreferenced"
    original.update(
        evidence_id=evidence_id,
        source_record_id="official-unreferenced",
        retrieval_id="ret:oges.fixture.unreferenced",
        title="Synthetic unreferenced official action",
        public_url="https://example.test/oges-fixture/official-unreferenced",
        published_at="2026-08-08T08:00:00Z",
        observed_at="2026-08-08T08:30:00Z",
    )
    return _add_release_object(fixture, "evidence_item", evidence_id, original)


def _reference_second_evidence(fixture: Fixture) -> dict[str, Any]:
    second = _add_unreferenced_evidence(fixture)
    second_id = second["evidence_id"]

    def reference(document: dict[str, Any]) -> None:
        document["evidence_links"].append(
            {
                "evidence_id": second_id,
                "role": "corroborates",
                "asserted_at": "2026-08-08T09:00:00Z",
            }
        )
        document["provenance"]["evidence_ids"].append(second_id)

    from src import oges_fixture

    oges_fixture._rewrite_object(fixture, "evt:oges.fixture.policy.001", reference)
    return second


def _add_unreferenced_event(fixture: Fixture) -> dict[str, Any]:
    original = json.loads(
        fixture.objects["evt:oges.fixture.policy.001"].read_text(encoding="utf-8")
    )
    event_id = "evt:oges.fixture.policy.unreferenced"
    original.update(event_id=event_id, canonical_label="Synthetic alternate policy action")
    return _add_release_object(fixture, "event", event_id, original)


def _make_nullable_citation_fixture(root: Path) -> Fixture:
    fixture = build_fixture(root)
    artifact = fixture.root / "artifacts" / "citation-metadata.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"citation metadata locator")

    def make_nullable(document: dict[str, Any]) -> None:
        document["public_url"] = None
        document["published_at"] = None
        document["artifact_path"] = str(artifact.relative_to(fixture.root))
        document["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

    from src import oges_fixture

    oges_fixture._rewrite_object(fixture, "evd:oges.fixture.official.001", make_nullable)
    return fixture


def test_valid_replay_uses_incumbent_clauses_and_all_seven_roles(tmp_path: Path) -> None:
    fixture, source, proof = _compiled(tmp_path)
    second_source, second_proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    contract, _ = ac.load_contract()

    assert ac.serialize_record(source) == ac.serialize_record(second_source)
    assert ac.serialize_record(proof) == ac.serialize_record(second_proof)
    assert _verify(fixture, PATH_QUERY, source, proof)["status"] == "valid"
    assert source["complete_denominators"] == {
        "clauses": len(source["clauses"]),
        "paths": 1,
        "hops": 1,
        "coverage_rows": 1,
        "object_evidence_rows": 5,
        "evidence_rows": 1,
        "evidence_items": 1,
        "evidence_metadata_fields": 11,
        "evidence_metadata_clauses": 11,
        "rights_rows": 1,
        "output_limitation_ids": 16,
        "output_limitation_scope_memberships": 21,
        "guardrail_ids": 3,
    }
    assert all(ac.compile_clauses(source["clauses"], contract).values())
    assert proof["required_role_ids"] == contract["roles"]
    assert proof["complete_role_denominator"] == 7
    assert len(proof["cross_role_proof"]["pairs"]) == 21
    assert proof["trust"]["authenticated"] is False
    assert proof["trust"]["production_authority"] is False
    for role in proof["roles"]:
        assert set(role) == {
            "role_id",
            "included_clause_refs",
            "omitted_clause_refs",
        }
        assert role["omitted_clause_refs"] == []
        assert all(
            set(ref) == {"clause_id", "clause_record_sha256"}
            for ref in role["included_clause_refs"]
        )

    assert _find(source, "event.canonical_label")["value"] == "Synthetic policy action"
    assert _find(source, "target.canonical_name")["value"] == "Synthetic crude oil"
    assert (
        _find(source, "release.generated_at")["value"] == source["source_release"]["generated_at"]
    )
    evidence_clauses = [
        row
        for row in source["clauses"]
        if row["proof_binding"]["source_field"] in ac._EVIDENCE_METADATA_FIELDS
    ]
    assert len(evidence_clauses) == 11
    assert {row["proof_binding"]["source_field"] for row in evidence_clauses} == set(
        ac._EVIDENCE_METADATA_FIELDS
    )
    output_limitations = [
        row
        for row in source["clauses"]
        if row["proof_binding"]["source_field"].startswith("output_limitation:")
    ]
    assert len(output_limitations) == 16


def test_no_path_is_bounded_refusal_not_no_exposure(tmp_path: Path) -> None:
    fixture, source, proof = _compiled(tmp_path, NO_PATH_QUERY)
    assert _find(source, "traversal.status")["value"] == "no_path"
    assert source["complete_denominators"]["hops"] == 0
    assert source["complete_denominators"]["coverage_rows"] == 0
    assert not any(
        row["proof_binding"]["source_field"].startswith("edge.") for row in source["clauses"]
    )
    assert "no_exposure" not in json.dumps(source)
    assert _verify(fixture, NO_PATH_QUERY, source, proof)["status"] == "valid"


def test_nullable_citation_fields_remain_null_with_explicit_missingness(
    tmp_path: Path,
) -> None:
    fixture = _make_nullable_citation_fixture(tmp_path)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    evidence_id = "evd:oges.fixture.official.001"
    for field in ("evidence.public_url", "evidence.published_at"):
        clause = _find_evidence(source, field, evidence_id)
        assert clause["value"] is None
        assert clause["missingness"] == "source_missing"
        assert clause["value"] not in ("", 0)
    assert _find_evidence(source, "evidence.observed_at", evidence_id)["value"] == (
        "2026-08-08T09:00:00Z"
    )
    assert _verify(fixture, PATH_QUERY, source, proof)["status"] == "valid"


def test_every_union_evidence_record_emits_exactly_one_registered_field_set(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    second = _reference_second_evidence(fixture)
    source, _ = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    for evidence_id in (
        "evd:oges.fixture.official.001",
        second["evidence_id"],
    ):
        clauses = [
            row
            for row in source["clauses"]
            if row["proof_binding"]["source_field"] in ac._EVIDENCE_METADATA_FIELDS
            and row["proof_binding"]["source_object_refs"][0]["object_id"] == evidence_id
        ]
        assert len(clauses) == 11
        assert {row["proof_binding"]["source_field"] for row in clauses} == set(
            ac._EVIDENCE_METADATA_FIELDS
        )
        assert all(
            row["proof_binding"]["source_object_refs"]
            == [
                {
                    "object_type": "evidence_item",
                    "object_id": evidence_id,
                    "record_sha256": next(
                        entry["record_sha256"]
                        for entry in json.loads(fixture.manifest.read_text(encoding="utf-8"))[
                            "objects"
                        ]
                        if entry["object_id"] == evidence_id
                    ),
                }
            ]
            for row in clauses
        )
    assert source["complete_denominators"]["evidence_items"] == 2
    assert source["complete_denominators"]["evidence_metadata_clauses"] == 22


def test_unreferenced_release_evidence_emits_nothing_and_injection_refuses(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    unreferenced = _add_unreferenced_evidence(fixture)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    assert unreferenced["evidence_id"] not in json.dumps(source)
    assert _verify(fixture, PATH_QUERY, source, proof)["status"] == "valid"

    injected = deepcopy(source)
    clause = deepcopy(_find_evidence(source, "evidence.title", "evd:oges.fixture.official.001"))
    unreferenced_ref = {
        "object_type": "evidence_item",
        "object_id": unreferenced["evidence_id"],
        "record_sha256": unreferenced["record_sha256"],
    }
    clause["clause_id"] = ac._clause_identifier(
        PATH_QUERY,
        "evidence.title",
        {"evidence_ref": unreferenced_ref, "field": "evidence.title"},
    )
    clause["value"] = unreferenced["title"]
    clause["proof_binding"]["source_object_refs"] = [unreferenced_ref]
    clause = ac._seal(clause)
    injected["clauses"].append(clause)
    injected["clauses"].sort(key=lambda row: row["clause_id"])
    injected["complete_denominators"]["clauses"] += 1
    injected = ac._seal(injected)
    contract, _ = ac.load_contract()
    injected_proof = ac._compile_role_proof_bundle(injected, contract)
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_evidence_binding_invalid$"):
        _verify(fixture, PATH_QUERY, injected, injected_proof)


@pytest.mark.parametrize(
    "field",
    [
        "evidence.title",
        "evidence.public_url",
        "evidence.published_at",
        "evidence.observed_at",
    ],
)
def test_metadata_from_record_a_cannot_be_spliced_into_record_b(tmp_path: Path, field: str) -> None:
    fixture = build_fixture(tmp_path)
    second = _reference_second_evidence(fixture)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    first_id = "evd:oges.fixture.official.001"
    second_id = second["evidence_id"]
    first_value = _find_evidence(source, field, first_id)["value"]
    second_clause = _find_evidence(source, field, second_id)
    assert first_value != second_clause["value"]
    changed = _replace_clause(
        source,
        proof,
        second_clause["clause_id"],
        lambda row: row.update(value=first_value),
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _verify(fixture, PATH_QUERY, *changed)


def test_publication_and_observation_timestamps_cannot_be_swapped(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    second = _reference_second_evidence(fixture)
    source, _ = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    published = _find_evidence(source, "evidence.published_at", second["evidence_id"])
    observed = _find_evidence(source, "evidence.observed_at", second["evidence_id"])
    assert published["value"] != observed["value"]
    changed = _reseal_changed_source(
        source,
        {
            published["clause_id"]: lambda row: row.update(value=observed["value"]),
            observed["clause_id"]: lambda row: row.update(value=published["value"]),
        },
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _verify(fixture, PATH_QUERY, *changed)


def test_traversal_evidence_must_equal_object_evidence_union(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path)
    validated, traversal, profile = _validated_and_traversal(fixture)
    traversal["evidence"] = []
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_evidence_binding_invalid$"):
        ac._evidence_documents(validated, traversal, profile["citation_metadata_policy"])


@pytest.mark.parametrize(
    "privacy_class,rights_use",
    [
        ("restricted", "cite_metadata"),
        ("prohibited", "cite_metadata"),
        ("restricted", "model_processing"),
        ("public_with_redactions", "publish_extract"),
    ],
)
def test_nonpublishable_citation_metadata_refuses_before_clause_bundle(
    tmp_path: Path, privacy_class: str, rights_use: str
) -> None:
    fixture = build_fixture(tmp_path)
    validated, traversal, profile = _validated_and_traversal(fixture)
    objects: dict[str, Mapping[str, Mapping[str, Any]]] = {
        object_type: dict(rows) for object_type, rows in validated.objects.items()
    }
    evidence_id = "evd:oges.fixture.official.001"
    evidence_objects = dict(objects["evidence_item"])
    document = dict(evidence_objects[evidence_id])
    document["privacy_class"] = privacy_class
    document["rights_use"] = rights_use
    evidence_objects[evidence_id] = document
    objects["evidence_item"] = evidence_objects
    for row in traversal["evidence"]:
        if row["evidence_id"] == evidence_id:
            row["privacy_class"] = privacy_class
            row["rights_use"] = rights_use
    mutated = canonical.ValidatedCanonicalRelease(
        manifest=validated.manifest,
        objects=objects,
        summary=validated.summary,
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_evidence_metadata_not_publishable$",
    ):
        ac._evidence_documents(mutated, traversal, profile["citation_metadata_policy"])


def test_future_evidence_time_refuses_release_before_clause_creation(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)

    def move_future(document: dict[str, Any]) -> None:
        document["observed_at"] = "2026-08-08T14:00:00Z"
        document["retrieved_at"] = "2026-08-08T14:00:00Z"

    from src import oges_fixture

    oges_fixture._rewrite_object(fixture, "evd:oges.fixture.official.001", move_future)
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_release_refused$"):
        ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)


def test_event_label_from_other_release_record_cannot_keep_event_a_ref(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    other = _add_unreferenced_event(fixture)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    clause = _find(source, "event.canonical_label")
    assert clause["proof_binding"]["source_object_refs"][0]["object_id"] == (
        "evt:oges.fixture.policy.001"
    )
    changed = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row.update(value=other["canonical_label"]),
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _verify(fixture, PATH_QUERY, *changed)


def test_same_type_target_name_substitution_refuses(tmp_path: Path) -> None:
    fixture, source, proof = _compiled(tmp_path, NO_PATH_QUERY)
    wrong = json.loads(fixture.objects["ent:country.synthetic_origin"].read_text(encoding="utf-8"))
    clause = _find(source, "target.canonical_name")
    assert clause["proof_binding"]["source_object_refs"][0]["object_id"] == (
        "ent:country.synthetic_india"
    )
    changed = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row.update(value=wrong["canonical_name"]),
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _verify(fixture, NO_PATH_QUERY, *changed)


def test_release_generated_at_cannot_be_current_clock_or_source_spliced(
    tmp_path: Path,
) -> None:
    fixture, source, proof = _compiled(tmp_path)
    clause = _find(source, "release.generated_at")
    changed = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row.update(value="2026-08-10T12:34:56Z"),
    )
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_binding_invalid$"):
        _verify(fixture, PATH_QUERY, *changed)

    source_splice = deepcopy(source)
    source_splice["source_release"]["generated_at"] = "2026-08-10T12:34:56Z"
    source_splice = ac._seal(source_splice)
    contract, _ = ac.load_contract()
    proof_splice = ac._compile_role_proof_bundle(source_splice, contract)
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_binding_invalid$"):
        _verify(fixture, PATH_QUERY, source_splice, proof_splice)


def test_citation_url_swap_refuses_even_when_all_roles_are_resealed(
    tmp_path: Path,
) -> None:
    fixture, source, proof = _compiled(tmp_path)
    clause = _find(source, "event.canonical_label")
    changed = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row["citation"][0].update(public_url="https://example.test/swapped-citation"),
    )
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _verify(fixture, PATH_QUERY, *changed)


def test_limitation_deletion_alias_and_scope_movement_all_refuse(
    tmp_path: Path,
) -> None:
    fixture, source, proof = _compiled(tmp_path)
    clause = _find(
        source,
        "output_limitation:draft_requires_human_review",
    )

    deleted = deepcopy(source)
    deleted["clauses"] = [
        row for row in deleted["clauses"] if row["clause_id"] != clause["clause_id"]
    ]
    deleted["complete_denominators"]["clauses"] -= 1
    deleted = ac._seal(deleted)
    contract, _ = ac.load_contract()
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_binding_invalid$"):
        _verify(
            fixture,
            PATH_QUERY,
            deleted,
            ac._compile_role_proof_bundle(deleted, contract),
        )

    aliased = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row.update(value="human_review_suggested"),
    )
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_binding_invalid$"):
        _verify(fixture, PATH_QUERY, *aliased)

    moved = _replace_clause(
        source,
        proof,
        clause["clause_id"],
        lambda row: row["proof_binding"]["limitation_binding"].update(
            applicable_scope_ids=["scope:output.newsroom_claim_card"]
        ),
    )
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_limitation_scope_invalid$"):
        _verify(fixture, PATH_QUERY, *moved)


def test_priority_language_is_not_an_optional_role(tmp_path: Path) -> None:
    fixture, source, proof = _compiled(tmp_path)
    mutation = deepcopy(proof)
    mutation["roles"] = [row for row in mutation["roles"] if row["role_id"] != "priority_language"]
    mutation = ac._seal(mutation)
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_role_proof_invalid$"):
        _verify(fixture, PATH_QUERY, source, mutation)


def test_new_measurement_limitation_rights_and_provenance_atoms_are_protected(
    tmp_path: Path,
) -> None:
    _, source, _ = _compiled(tmp_path)
    contract, _ = ac.load_contract()
    fields = {
        "event.canonical_label": "measurement",
        "output_limitation:draft_requires_human_review": "limitation",
        "evidence.rights_use": "rights",
        "release.generated_at": "provenance",
    }
    for field, kind in fields.items():
        clause = _find(source, field)
        assert clause["kind"] == kind
        original_ref = {
            "clause_id": clause["clause_id"],
            "clause_record_sha256": clause["record_sha256"],
        }
        checked = 0
        for path in _leaf_paths(clause):
            mutation = deepcopy(clause)
            current: object = mutation
            for part in path:
                current = current[part]  # type: ignore[index]
            _set_path(mutation, path, _mutate_leaf(current))
            resealed = ac._seal(mutation)
            with pytest.raises(ac.AnalyticalClauseError):
                ac.validate_role_view("research", [original_ref], [resealed], contract)
            checked += 1
        assert checked >= 70, field


def test_self_hash_only_forgery_refuses_without_semantic_mutation(
    tmp_path: Path,
) -> None:
    _, source, _ = _compiled(tmp_path)
    contract, _ = ac.load_contract()
    clause = deepcopy(_find(source, "event.canonical_label"))
    clause["record_sha256"] = "f" * 64
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_record_digest_mismatch$"):
        ac.validate_clause(clause, contract)


def _renderer_limitation_profiles() -> dict[str, list[str]]:
    tree = ast.parse(Path(evidence_outputs.__file__).read_text(encoding="utf-8"))
    constants: dict[str, list[str]] = {}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        if isinstance(target, ast.Name) and target.id in {
            "_LIMITATIONS",
            "_RESEARCH_LIMITATIONS",
            "_BRIEF_LIMITATIONS",
            "_CLAIM_LIMITATIONS",
            "_AUDIT_LIMITATIONS",
        }:
            constants[target.id] = list(ast.literal_eval(statement.value))
    claim_profiles: dict[str, list[str]] = {}
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Dict):
            continue
        pairs = {
            key.value: value
            for key, value in zip(candidate.keys, candidate.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        claim_id_node = pairs.get("claim_id")
        limitations_node = pairs.get("limitations")
        if (
            isinstance(claim_id_node, ast.Constant)
            and isinstance(claim_id_node.value, str)
            and limitations_node is not None
        ):
            claim_profiles[claim_id_node.value] = list(ast.literal_eval(limitations_node))
    return {
        "scope:output.all_views": constants["_LIMITATIONS"],
        "scope:output.research_package": constants["_RESEARCH_LIMITATIONS"],
        "scope:output.board_brief": constants["_BRIEF_LIMITATIONS"],
        "scope:output.newsroom_claim_card": constants["_CLAIM_LIMITATIONS"],
        "scope:output.offline_audit_bundle": constants["_AUDIT_LIMITATIONS"],
        "scope:claim.card.event_record": claim_profiles["claim:card.event_record"],
        "scope:claim.card.release_structure": claim_profiles["claim:card.release_structure"],
    }


def test_governance_limitation_vocabulary_is_exact_renderer_parity_target() -> None:
    registry = json.loads(LIMITATIONS.read_text(encoding="utf-8"))
    ac._validate_limitation_registry(registry, release_effective=date(2026, 8, 8))
    profiles = _renderer_limitation_profiles()
    ac.validate_limitation_parity(registry, profiles)
    assert len(registry["output_clause_ids"]) == 16
    assert sum(map(len, registry["output_profiles"].values())) == 21
    source = Path(evidence_outputs.__file__).read_text(encoding="utf-8")
    assert '"review_status": "draft_requires_human_review"' in source


def test_renderer_local_limitation_injection_is_not_governance(
    tmp_path: Path,
) -> None:
    del tmp_path
    registry = json.loads(LIMITATIONS.read_text(encoding="utf-8"))
    profiles = _renderer_limitation_profiles()
    profiles["scope:output.newsroom_claim_card"].append("renderer_local_injection")
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_limitation_parity_invalid$"):
        ac.validate_limitation_parity(registry, profiles)


def _same_universe_off_path_attack(tmp_path: Path) -> None:
    fixture, off_path, alternate = _off_path_fixture(tmp_path)
    source, proof = ac.compile_source_bound_clauses(fixture.manifest, PATH_QUERY, root=fixture.root)
    edge_clause = _find(source, "edge.id")
    assert edge_clause["value"] == alternate["edge_id"]
    assert off_path["edge_id"] not in json.dumps(source)
    assert (
        edge_clause["proof_binding"]["coverage_binding"]["universe_release_id"]
        == (off_path["coverage_basis"]["universe_release_id"])
    )

    def substitute(row: dict[str, Any]) -> None:
        edge_ref = next(
            ref
            for ref in row["proof_binding"]["source_object_refs"]
            if ref["object_type"] == "exposure_edge"
        )
        edge_ref["object_id"] = off_path["edge_id"]
        edge_ref["record_sha256"] = off_path["record_sha256"]

    changed = _replace_clause(source, proof, edge_clause["clause_id"], substitute)
    _verify(fixture, PATH_QUERY, *changed)


def test_same_universe_off_path_edge_is_not_compiled_or_launderable(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ac.AnalyticalClauseError,
        match="^clause_source_bundle_recompile_mismatch$",
    ):
        _same_universe_off_path_attack(tmp_path)


def _case_refusal(
    case_id: str,
    fixture: Fixture,
    source: dict[str, Any],
    proof: dict[str, Any],
    tmp_path: Path,
) -> None:
    if case_id == "same_clause_id_different_record":
        mutation = deepcopy(proof)
        mutation["roles"][0]["included_clause_refs"][0]["clause_record_sha256"] = mutation["roles"][
            0
        ]["included_clause_refs"][1]["clause_record_sha256"]
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "one_digit_rounded":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source, proof, clause["clause_id"], lambda row: row.update(value=13.0)
            ),
        )
    elif case_id == "percent_replaced_by_fraction":
        clause = _find(source, "edge.magnitude.unit")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value="fraction_of_import_volume"),
            ),
        )
    elif case_id == "changed_as_of":
        clause = _find(source, "edge.observed_at")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["observed_period"].update(as_of="2026-08-09T00:00:00Z"),
            ),
        )
    elif case_id == "denominator_omitted":
        clause = _find(source, "edge.magnitude.value")

        def omit(row: dict[str, Any]) -> None:
            del row["denominator"]

        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(source, proof, clause["clause_id"], omit),
        )
    elif case_id == "point_replaces_interval":
        clause = _find(source, "edge.magnitude.uncertainty")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source, proof, clause["clause_id"], lambda row: row.update(value=12.5)
            ),
        )
    elif case_id == "unknown_becomes_zero":
        clause = _find(source, "event.intensity.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value=0.0, missingness="present"),
            ),
        )
    elif case_id == "citation_or_source_hash_changed":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["citation"][0].update(record_sha256="a" * 64),
            ),
        )
    elif case_id == "rights_public_use_escalation":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["rights_state"].update(
                    publication_authority="public_use_authorized"
                ),
            ),
        )
    elif case_id == "proof_digest_drift":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["proof_binding"]["upstream"].update(record_sha256="b" * 64),
            ),
        )
    elif case_id == "hidden_limitation_dropped":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["proof_binding"]["limitations"].remove(
                    "structural_connection_not_causation"
                ),
            ),
        )
    elif case_id == "model_authored_clause_or_prose":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(model_prose="generated claim"),
            ),
        )
    elif case_id == "role_specific_literal_injection":
        mutation = deepcopy(proof)
        mutation["roles"][0]["literal"] = "role-only prose"
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "omission_without_registered_reason":
        mutation = deepcopy(proof)
        role = mutation["roles"][0]
        ref = role["included_clause_refs"].pop()
        role["omitted_clause_refs"].append({**ref, "omission_reason_id": "omission:unregistered"})
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "resealed_projection_mutation":
        mutation = deepcopy(proof)
        mutation["limitations"] = [*mutation["limitations"], "forged_limitation"]
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "self_hash_claims_production_trust":
        mutation = deepcopy(proof)
        mutation["trust"]["authenticated"] = True
        mutation["trust"]["production_authority"] = True
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "duplicate_clause_ids":
        mutation = deepcopy(source)
        mutation["clauses"].append(deepcopy(mutation["clauses"][0]))
        mutation["complete_denominators"]["clauses"] += 1
        _verify(fixture, PATH_QUERY, ac._seal(mutation), proof)
    elif case_id == "duplicate_role_clause_refs":
        mutation = deepcopy(proof)
        mutation["roles"][0]["included_clause_refs"].append(
            deepcopy(mutation["roles"][0]["included_clause_refs"][0])
        )
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "unknown_role":
        mutation = deepcopy(proof)
        mutation["roles"][0]["role_id"] = "marketing"
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "unknown_template":
        mutation = deepcopy(proof)
        mutation["roles"][0]["template_id"] = "template:unknown"
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "cross_release_query_universe_splice":
        clause = _find(source, "coverage.reference_date")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["proof_binding"]["coverage_binding"].update(record_sha256="c" * 64),
            ),
        )
    elif case_id == "template_drift_or_free_prose":
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile["dynamic_binding_rules"]["role_payload"] = "free_prose"
        ac._validate_source_profile_document(profile, release_effective=date(2026, 8, 8))
    elif case_id == "future_registry":
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile["effective"] = "2026-08-09"
        ac._validate_source_profile_document(profile, release_effective=date(2026, 8, 8))
    elif case_id == "later_rights_back_authorization":
        clause = _find(source, "rights.release_snapshot")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["value"]["rights_snapshot"].update(
                    decision_id="decision:later.authorization"
                ),
            ),
        )
    elif case_id == "no_path_rewritten_as_no_exposure":
        no_fixture, no_source, no_proof = _compiled(tmp_path, NO_PATH_QUERY)
        clause = _find(no_source, "traversal.status")
        _verify(
            no_fixture,
            NO_PATH_QUERY,
            *_replace_clause(
                no_source,
                no_proof,
                clause["clause_id"],
                lambda row: row.update(value="no_exposure"),
            ),
        )
    elif case_id == "truncated_traversal_hidden":
        truncated = build_fixture(tmp_path)
        _add_parallel_edges(truncated)
        truncated_source, truncated_proof = ac.compile_source_bound_clauses(
            truncated.manifest, PATH_QUERY, root=truncated.root
        )
        clause = _find(truncated_source, "traversal.truncated")
        assert clause["value"] is True
        _verify(
            truncated,
            PATH_QUERY,
            *_replace_clause(
                truncated_source,
                truncated_proof,
                clause["clause_id"],
                lambda row: row.update(value=False),
            ),
        )
    elif case_id == "profile_runtime_or_upstream_substitution":
        mutation = deepcopy(source)
        mutation["contract"]["exposure_runtime_sha256"] = "d" * 64
        _verify(fixture, PATH_QUERY, ac._seal(mutation), proof)
    elif case_id == "one_role_claims_cross_role_proof":
        mutation = deepcopy(proof)
        mutation["roles"][0]["cross_role_proof"] = True
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "clause_denominator_shrunk":
        mutation = deepcopy(source)
        mutation["complete_denominators"]["clauses"] -= 1
        _verify(fixture, PATH_QUERY, ac._seal(mutation), proof)
    elif case_id == "required_role_missing":
        mutation = deepcopy(proof)
        mutation["roles"].pop()
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "caller_authored_rights_time_universe":
        clause = _find(source, "edge.magnitude.value")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["rights_state"].update(sources=[]),
            ),
        )
    elif case_id == "same_universe_off_path_edge_substitution":
        _same_universe_off_path_attack(tmp_path)
    elif case_id == "event_label_from_wrong_record":
        clause = _find(source, "event.canonical_label")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value="Synthetic alternate policy action"),
            ),
        )
    elif case_id == "same_type_target_name_substitution":
        no_fixture, no_source, no_proof = _compiled(tmp_path, NO_PATH_QUERY)
        clause = _find(no_source, "target.canonical_name")
        _verify(
            no_fixture,
            NO_PATH_QUERY,
            *_replace_clause(
                no_source,
                no_proof,
                clause["clause_id"],
                lambda row: row.update(value="Synthetic origin country"),
            ),
        )
    elif case_id == "evidence_metadata_from_wrong_record":
        two = build_fixture(tmp_path)
        second = _reference_second_evidence(two)
        two_source, two_proof = ac.compile_source_bound_clauses(
            two.manifest, PATH_QUERY, root=two.root
        )
        first = _find_evidence(two_source, "evidence.title", "evd:oges.fixture.official.001")
        second_clause = _find_evidence(two_source, "evidence.title", second["evidence_id"])
        _verify(
            two,
            PATH_QUERY,
            *_replace_clause(
                two_source,
                two_proof,
                second_clause["clause_id"],
                lambda row: row.update(value=first["value"]),
            ),
        )
    elif case_id == "unreferenced_evidence_clause_injection":
        unreferenced_fixture = build_fixture(tmp_path)
        unreferenced = _add_unreferenced_evidence(unreferenced_fixture)
        clean_source, _ = ac.compile_source_bound_clauses(
            unreferenced_fixture.manifest, PATH_QUERY, root=unreferenced_fixture.root
        )
        injected = deepcopy(clean_source)
        clause = deepcopy(
            _find_evidence(
                clean_source,
                "evidence.title",
                "evd:oges.fixture.official.001",
            )
        )
        ref = {
            "object_type": "evidence_item",
            "object_id": unreferenced["evidence_id"],
            "record_sha256": unreferenced["record_sha256"],
        }
        clause["clause_id"] = ac._clause_identifier(
            PATH_QUERY,
            "evidence.title",
            {"evidence_ref": ref, "field": "evidence.title"},
        )
        clause["value"] = unreferenced["title"]
        clause["proof_binding"]["source_object_refs"] = [ref]
        injected["clauses"].append(ac._seal(clause))
        injected["clauses"].sort(key=lambda row: row["clause_id"])
        injected["complete_denominators"]["clauses"] += 1
        injected = ac._seal(injected)
        contract, _ = ac.load_contract()
        _verify(
            unreferenced_fixture,
            PATH_QUERY,
            injected,
            ac._compile_role_proof_bundle(injected, contract),
        )
    elif case_id == "traversal_evidence_union_mismatch":
        validated, traversal, profile = _validated_and_traversal(fixture)
        traversal["evidence"] = []
        ac._evidence_documents(validated, traversal, profile["citation_metadata_policy"])
    elif case_id == "citation_url_swapped":
        clause = _find(source, "event.canonical_label")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["citation"][0].update(
                    public_url="https://example.test/swapped-citation"
                ),
            ),
        )
    elif case_id == "publication_observation_dates_swapped":
        two = build_fixture(tmp_path)
        second = _reference_second_evidence(two)
        two_source, _ = ac.compile_source_bound_clauses(two.manifest, PATH_QUERY, root=two.root)
        published = _find_evidence(two_source, "evidence.published_at", second["evidence_id"])
        observed = _find_evidence(two_source, "evidence.observed_at", second["evidence_id"])
        _verify(
            two,
            PATH_QUERY,
            *_reseal_changed_source(
                two_source,
                {
                    published["clause_id"]: lambda row: row.update(value=observed["value"]),
                    observed["clause_id"]: lambda row: row.update(value=published["value"]),
                },
            ),
        )
    elif case_id == "future_evidence_timestamp":
        future = build_fixture(tmp_path)

        def move_future(row: dict[str, Any]) -> None:
            row["observed_at"] = "2026-08-08T14:00:00Z"
            row["retrieved_at"] = "2026-08-08T14:00:00Z"

        from src import oges_fixture

        oges_fixture._rewrite_object(future, "evd:oges.fixture.official.001", move_future)
        ac.compile_source_bound_clauses(future.manifest, PATH_QUERY, root=future.root)
    elif case_id == "generated_at_current_clock":
        clause = _find(source, "release.generated_at")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value="2026-08-10T12:34:56Z"),
            ),
        )
    elif case_id == "source_release_generated_at_splice":
        mutation = deepcopy(source)
        mutation["source_release"]["generated_at"] = "2026-08-10T12:34:56Z"
        mutation = ac._seal(mutation)
        contract, _ = ac.load_contract()
        _verify(
            fixture,
            PATH_QUERY,
            mutation,
            ac._compile_role_proof_bundle(mutation, contract),
        )
    elif case_id == "limitation_id_deleted":
        clause = _find(source, "output_limitation:draft_requires_human_review")
        mutation = deepcopy(source)
        mutation["clauses"] = [
            row for row in mutation["clauses"] if row["clause_id"] != clause["clause_id"]
        ]
        mutation["complete_denominators"]["clauses"] -= 1
        mutation = ac._seal(mutation)
        contract, _ = ac.load_contract()
        _verify(
            fixture,
            PATH_QUERY,
            mutation,
            ac._compile_role_proof_bundle(mutation, contract),
        )
    elif case_id == "limitation_id_aliased":
        clause = _find(source, "output_limitation:draft_requires_human_review")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value="human_review_suggested"),
            ),
        )
    elif case_id == "limitation_scope_moved":
        clause = _find(source, "output_limitation:draft_requires_human_review")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row["proof_binding"]["limitation_binding"].update(
                    applicable_scope_ids=["scope:output.newsroom_claim_card"]
                ),
            ),
        )
    elif case_id == "renderer_local_limitation_injection":
        registry = json.loads(LIMITATIONS.read_text(encoding="utf-8"))
        profiles = _renderer_limitation_profiles()
        profiles["scope:output.newsroom_claim_card"].append("renderer_local_injection")
        ac.validate_limitation_parity(registry, profiles)
    elif case_id == "source_blank_not_coerced":
        blank = build_fixture(tmp_path)
        from src import oges_fixture

        oges_fixture._rewrite_object(
            blank,
            "evd:oges.fixture.official.001",
            lambda row: row.update(title=""),
        )
        ac.compile_source_bound_clauses(blank.manifest, PATH_QUERY, root=blank.root)
    elif case_id == "citation_metadata_not_publishable":
        validated, traversal, profile = _validated_and_traversal(fixture)
        objects: dict[str, Mapping[str, Mapping[str, Any]]] = {
            object_type: dict(rows) for object_type, rows in validated.objects.items()
        }
        evidence_id = "evd:oges.fixture.official.001"
        evidence_objects = dict(objects["evidence_item"])
        document = dict(evidence_objects[evidence_id])
        document["privacy_class"] = "restricted"
        evidence_objects[evidence_id] = document
        objects["evidence_item"] = evidence_objects
        traversal["evidence"][0]["privacy_class"] = "restricted"
        mutated = canonical.ValidatedCanonicalRelease(
            manifest=validated.manifest,
            objects=objects,
            summary=validated.summary,
        )
        ac._evidence_documents(mutated, traversal, profile["citation_metadata_policy"])
    elif case_id == "arbitrary_query_tuple":
        ac.compile_source_bound_clauses(
            fixture.manifest,
            "query:analytical_clause.caller.event-target-1-100",
            root=fixture.root,
        )
    elif case_id == "duplicate_registered_query_tuple":
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        profile["query_profiles"][1].update(
            {
                key: profile["query_profiles"][0][key]
                for key in ("event_id", "target_entity_id", "max_hops", "max_paths")
            }
        )
        ac._validate_source_profile_document(profile, release_effective=date(2026, 8, 8))
    elif case_id == "limitation_registry_profile_drift":
        ac.load_limitation_registry("0" * 64, release_effective=date(2026, 8, 8))
    elif case_id == "priority_language_role_missing":
        mutation = deepcopy(proof)
        mutation["roles"] = [
            row for row in mutation["roles"] if row["role_id"] != "priority_language"
        ]
        _verify(fixture, PATH_QUERY, source, ac._seal(mutation))
    elif case_id == "coordinated_all_role_new_clause_mutation":
        clause = _find(source, "evidence.title")
        _verify(
            fixture,
            PATH_QUERY,
            *_replace_clause(
                source,
                proof,
                clause["clause_id"],
                lambda row: row.update(value="Coordinated all-role forged title"),
            ),
        )
    else:
        raise AssertionError(f"unimplemented adversarial case: {case_id}")


def _leaf_paths(value: object, prefix: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    if isinstance(value, dict):
        return [
            path
            for key, nested in value.items()
            if not (prefix == () and key == "record_sha256")
            for path in _leaf_paths(nested, (*prefix, key))
        ]
    if isinstance(value, list):
        return [
            path
            for index, nested in enumerate(value)
            for path in _leaf_paths(nested, (*prefix, index))
        ]
    return [prefix]


def _mutate_leaf(value: object) -> object:
    if value is None:
        return "mutated"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.125
    if isinstance(value, str):
        if len(value) == 64 and set(value) <= set("0123456789abcdef"):
            return ("0" if value[0] != "0" else "1") + value[1:]
        return value + "x"
    raise AssertionError(type(value))


def _set_path(document: object, path: tuple[object, ...], value: object) -> None:
    current = document
    for part in path[:-1]:
        current = current[part]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]


def test_every_clause_field_except_self_hash_is_protected(tmp_path: Path) -> None:
    _, source, _ = _compiled(tmp_path)
    original = _find(source, "edge.magnitude.value")
    contract, _ = ac.load_contract()
    original_ref = {
        "clause_id": original["clause_id"],
        "clause_record_sha256": original["record_sha256"],
    }
    checked = 0
    for path in _leaf_paths(original):
        mutation = deepcopy(original)
        current: object = mutation
        for part in path:
            current = current[part]  # type: ignore[index]
        _set_path(mutation, path, _mutate_leaf(current))
        resealed = ac._seal(mutation)
        assert resealed["record_sha256"] != original["record_sha256"], path
        with pytest.raises(ac.AnalyticalClauseError):
            ac.validate_role_view("research", [original_ref], [resealed], contract)
        checked += 1
    assert checked >= 75


def test_normative_adversarial_registry_is_complete_and_executed(
    tmp_path: Path,
) -> None:
    registry = json.loads(VECTORS.read_text(encoding="utf-8"))
    fixture, source, proof = _compiled(tmp_path / "base")
    executed: set[str] = set()
    for row in registry["cases"]:
        case_id = row["case_id"]
        if case_id == "valid_complete_all_role_compilation":
            assert _verify(fixture, PATH_QUERY, source, proof)["status"] == "valid"
        elif case_id == "every_clause_field_except_self_hash_mutated":
            test_every_clause_field_except_self_hash_is_protected(tmp_path / "every-field")
        else:
            with pytest.raises(ac.AnalyticalClauseError) as exc:
                _case_refusal(
                    case_id,
                    fixture,
                    source,
                    proof,
                    tmp_path / case_id,
                )
            assert exc.value.code == row["expected_reason"], case_id
        executed.add(case_id)
    assert executed == {row["case_id"] for row in registry["cases"]}
    assert len(executed) == 55


def test_source_profile_pins_incumbent_and_upstream_exact_bytes() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    contract = json.loads(
        (ROOT / "governance" / "analytical_clause_contract.json").read_text(encoding="utf-8")
    )
    assert profile["default_policy"] == "deny"
    assert profile["trust_boundary"]["production_authority"] is False
    assert profile["product_manifest_boundary"]["status"] == "unavailable"
    assert profile["dynamic_binding_rules"]["omissions"] == "none_registered_deny"
    assert profile["dynamic_binding_rules"]["role_payload"] == "exact_clause_refs_only"
    assert profile["registered_query_boundary"] == {
        "accepted_input": "exact_registered_query_id_only",
        "registered_query_ids": [PATH_QUERY, NO_PATH_QUERY],
        "tuple_resolver": "none",
        "caller_authored_event_target_bounds_or_selectors": False,
        "unregistered_evidence_output_api_tuples": "refuse_without_claiming_coverage",
    }
    assert profile["evidence_metadata_fields"] == list(ac._EVIDENCE_METADATA_FIELDS)
    assert profile["limitation_vocabulary"]["output_unique_id_denominator"] == 16
    assert profile["limitation_vocabulary"]["output_scope_membership_denominator"] == 21
    assert contract["roles"] == list(ac._REQUIRED_ROLES)
    assert "protected_fields" not in contract
    for row in profile["normative_files"]:
        assert row["sha256"] == hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
    pin_kinds = {row["kind"] for row in profile["normative_files"]}
    assert "analytical_clause_limitations" in pin_kinds
    assert "evidence_output_runtime" not in pin_kinds


def test_only_two_exact_query_ids_are_registered_and_arbitrary_tuple_refuses(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    assert [row["query_id"] for row in profile["query_profiles"]] == [
        PATH_QUERY,
        NO_PATH_QUERY,
    ]
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_profile_invalid$"):
        ac.compile_source_bound_clauses(
            fixture.manifest,
            "query:analytical_clause.caller.event-target-1-100",
            root=fixture.root,
        )


def test_duplicate_query_tuple_and_altered_release_authority_refuse() -> None:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    profile["query_profiles"][1].update(
        {
            key: profile["query_profiles"][0][key]
            for key in ("event_id", "target_entity_id", "max_hops", "max_paths")
        }
    )
    with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_profile_invalid$"):
        ac._validate_source_profile_document(profile, release_effective=date(2026, 8, 8))

    for field, value in (
        ("release_id", "rel:oges.fixture.other"),
        ("release_signer_id", "signer:oges.fixture.other"),
    ):
        mutation = json.loads(PROFILE.read_text(encoding="utf-8"))
        mutation["allowed_release"][field] = value
        with pytest.raises(ac.AnalyticalClauseError, match="^clause_source_profile_invalid$"):
            ac._validate_source_profile_document(mutation, release_effective=date(2026, 8, 8))
