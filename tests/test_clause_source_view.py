"""Adversarial tests for the one-source internal ClauseSourceView kernel."""

from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import pytest
from jsonschema import Draft202012Validator
from src import analytical_clause as ac
from src import canonical_objects as canonical
from src import clause_source_view as csv
from src.oges_fixture import Fixture, build_fixture

ROOT = Path(__file__).resolve().parents[1]
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"


def _compiled(
    tmp_path: Path, query_id: str = PATH_QUERY
) -> tuple[Fixture, dict[str, Any], dict[str, Any]]:
    fixture = build_fixture(tmp_path)
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, query_id, root=fixture.root
    )
    return fixture, source, proof


def _refuses(code: str):
    return pytest.raises(csv.ClauseSourceViewError, match=f"^{code}$")


class _CacheMutatingBytes:
    def __init__(self, raw: bytes, mutate: Callable[[], None]) -> None:
        self._raw = raw
        self._mutate = mutate

    def __bytes__(self) -> bytes:
        self._mutate()
        return self._raw


def _swap_view_caches(
    target: csv.ClauseSourceViews, source: csv.ClauseSourceViews
) -> None:
    for attribute in ("_entries", "_policies", "_receipt_bytes"):
        object.__setattr__(target, attribute, getattr(source, attribute))


def _find(source: dict[str, Any], source_field: str) -> dict[str, Any]:
    rows = [
        row
        for row in source["clauses"]
        if row["proof_binding"]["source_field"] == source_field
    ]
    assert len(rows) == 1, (source_field, len(rows))
    return rows[0]


def _reseal_with_proof(source: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source = ac._seal(source)
    contract, _ = ac.load_contract()
    return source, ac._compile_role_proof_bundle(source, contract)


def _mutate_clause(
    source: dict[str, Any],
    source_field: str,
    mutate: Callable[[dict[str, Any]], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = deepcopy(source)
    matched = 0
    clauses = []
    for original in changed["clauses"]:
        clause = deepcopy(original)
        if clause["proof_binding"]["source_field"] == source_field:
            mutate(clause)
            clause = ac._seal(clause)
            matched += 1
        clauses.append(clause)
    assert matched == 1
    changed["clauses"] = sorted(clauses, key=lambda row: row["clause_id"])
    return _reseal_with_proof(changed)


def _delete_field(
    source: dict[str, Any], source_field: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = deepcopy(source)
    before = len(changed["clauses"])
    changed["clauses"] = [
        row
        for row in changed["clauses"]
        if row["proof_binding"]["source_field"] != source_field
    ]
    removed = before - len(changed["clauses"])
    assert removed >= 1
    changed["complete_denominators"]["clauses"] -= removed
    return _reseal_with_proof(changed)


def _mutate_query(
    source: dict[str, Any], field: str, value: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = deepcopy(source)
    payload = {
        key: item
        for key, item in changed["query"].items()
        if key not in {"query_id", "query_sha256"}
    }
    payload[field] = value
    query_sha = ac._typed_sha(payload)
    changed["query"][field] = value
    changed["query"]["query_sha256"] = query_sha
    clauses = []
    for original in changed["clauses"]:
        clause = deepcopy(original)
        clause["proof_binding"]["query"] = {**payload, "query_sha256": query_sha}
        clauses.append(ac._seal(clause))
    changed["clauses"] = sorted(clauses, key=lambda row: row["clause_id"])
    return _reseal_with_proof(changed)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _resign(fixture: Fixture, manifest: dict[str, Any]) -> None:
    sealed = canonical.seal_record(manifest)
    _write_json(fixture.manifest, sealed)
    fixture.release_signature.write_bytes(
        fixture.release_private_key.sign(fixture.manifest.read_bytes())
    )


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


def _reference_second_evidence(fixture: Fixture) -> dict[str, Any]:
    original = json.loads(
        fixture.objects["evd:oges.fixture.official.001"].read_text(encoding="utf-8")
    )
    evidence_id = "evd:oges.fixture.official.second"
    original.update(
        evidence_id=evidence_id,
        source_record_id="official-second",
        retrieval_id="ret:oges.fixture.second",
        title="Synthetic second official action",
        public_url="https://example.test/oges-fixture/official-second",
        published_at="2026-08-08T08:00:00Z",
        observed_at="2026-08-08T08:30:00Z",
    )
    second = _add_release_object(fixture, "evidence_item", evidence_id, original)

    def reference(document: dict[str, Any]) -> None:
        document["evidence_links"].append(
            {
                "evidence_id": evidence_id,
                "role": "corroborates",
                "asserted_at": "2026-08-08T09:00:00Z",
            }
        )
        document["provenance"]["evidence_ids"].append(evidence_id)

    from src import oges_fixture

    oges_fixture._rewrite_object(fixture, "evt:oges.fixture.policy.001", reference)
    return second


def test_only_two_argument_compiler_is_the_composition_entry_point() -> None:
    signature = inspect.signature(csv.compile_clause_source_views)
    assert list(signature.parameters) == ["source_bundle", "role_proof_bundle"]
    assert all(
        parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        and parameter.default is inspect.Parameter.empty
        for parameter in signature.parameters.values()
    )
    with pytest.raises(TypeError):
        csv.compile_clause_source_views({}, {}, query_id=PATH_QUERY)  # type: ignore[call-arg]
    snapshot_signature = inspect.signature(csv.ClauseSourceViews.verified_snapshot)
    assert list(snapshot_signature.parameters) == ["self"]

    analytical_source = Path(ac.__file__).read_text(encoding="utf-8")
    assert "clause_source_view" not in analytical_source
    source = Path(csv.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "load_validated_release",
        "project_event_exposure",
        "verify_source_bound_compilation",
        "ProductManifest",
        "evidence_outputs.py",
    ):
        assert forbidden not in source


def test_verified_snapshot_rebuilds_only_from_captured_input_bytes(
    tmp_path: Path,
) -> None:
    _, path_source, path_proof = _compiled(tmp_path / "path")
    _, no_path_source, no_path_proof = _compiled(
        tmp_path / "no-path", NO_PATH_QUERY
    )
    clean = csv.compile_clause_source_views(path_source, path_proof)
    snapshot = clean.verified_snapshot()
    assert snapshot is not clean
    assert snapshot.receipt == clean.receipt
    assert snapshot.receipt is not clean.receipt
    assert snapshot._entries == clean._entries
    assert snapshot._entries is not clean._entries
    assert snapshot._policies == clean._policies
    assert snapshot._policies is not clean._policies
    assert snapshot._receipt_bytes == clean._receipt_bytes
    assert snapshot._receipt_bytes is not clean._receipt_bytes
    assert snapshot.research is not clean.research
    assert snapshot.research._entries is snapshot._entries
    assert snapshot.research._entries is not clean.research._entries

    corrupt = csv.compile_clause_source_views(path_source, path_proof)
    no_path = csv.compile_clause_source_views(no_path_source, no_path_proof)
    _swap_view_caches(corrupt, no_path)
    corrupt_snapshot = corrupt.verified_snapshot()
    assert corrupt_snapshot.receipt == clean.receipt
    assert corrupt_snapshot.research.one("traversal.status").value == "paths_found"

    spliced = csv.compile_clause_source_views(path_source, path_proof)
    object.__setattr__(spliced, "_proof_bytes", no_path._proof_bytes)
    with _refuses("view_proof_refused"):
        spliced.verified_snapshot()

    aba = csv.compile_clause_source_views(path_source, path_proof)
    mutations = 0

    def mutate_cache() -> None:
        nonlocal mutations
        mutations += 1
        _swap_view_caches(aba, no_path)

    object.__setattr__(
        aba, "_source_bytes", _CacheMutatingBytes(aba._source_bytes, mutate_cache)
    )
    aba_snapshot = aba.verified_snapshot()
    assert mutations == 1
    assert aba_snapshot.receipt == clean.receipt
    assert aba_snapshot.research.one("traversal.status").value == "paths_found"

    other_pair = csv.compile_clause_source_views(path_source, path_proof)
    object.__setattr__(other_pair, "_source_bytes", no_path._source_bytes)
    object.__setattr__(other_pair, "_proof_bytes", no_path._proof_bytes)
    other_snapshot = other_pair.verified_snapshot()
    assert other_snapshot.receipt == no_path.receipt
    assert other_snapshot.research.one("traversal.status").value == "no_path"


@pytest.mark.parametrize(
    "query_id,branch,coverage_count",
    [
        (PATH_QUERY, "branch:path_found", 1),
        (NO_PATH_QUERY, "branch:no_path", 0),
    ],
)
def test_compiles_one_global_index_and_four_policies_for_both_branches(
    tmp_path: Path, query_id: str, branch: str, coverage_count: int
) -> None:
    _, source, proof = _compiled(tmp_path, query_id)
    views = csv.compile_clause_source_views(source, proof)
    assert views.verify() is views
    receipt = views.receipt
    schema = json.loads(csv.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(receipt)

    assert receipt["active_branch_id"] == branch
    assert len(receipt["field_index"]) == 24
    assert [row["source_field"] for row in receipt["field_index"]] == sorted(
        row["source_field"] for row in receipt["field_index"]
    )
    coverage = next(
        row for row in receipt["field_index"] if row["source_field"] == "coverage.row"
    )
    assert coverage["clause_ref_denominator"] == coverage_count
    assert len(coverage["clause_refs"]) == coverage_count
    assert receipt["denominators"]["source_clause_denominator"] == len(
        source["clauses"]
    )
    assert receipt["denominators"]["role_denominator"] == 7
    assert receipt["denominators"]["role_pair_denominator"] == 21
    assert receipt["denominators"]["consumer_policy_denominator"] == 4

    policies = receipt["consumer_policies"]
    assert {row["output_id"] for row in policies} == set(csv._OUTPUT_IDS)
    assert len({row["view_id"] for row in policies}) == 4
    assert {views.board.role_id, views.newsroom.role_id, views.offline.role_id, views.research.role_id} == {
        "board",
        "newsroom",
        "offline",
        "research",
    }
    assert len(views.board.many("coverage.row")) == coverage_count
    if branch == "branch:path_found":
        assert all("no_path" not in item for item in views.board.active_template_ids)
        assert all("path_found" not in item for item in views.board.inactive_template_ids)
    else:
        assert all("path_found" not in item for item in views.board.active_template_ids)
        assert all("no_path" not in item for item in views.board.inactive_template_ids)


def test_receipt_contains_only_bindings_refs_counts_ids_and_boundary_flags(
    tmp_path: Path,
) -> None:
    _, source, proof = _compiled(tmp_path)
    receipt = csv.compile_clause_source_views(source, proof).receipt
    encoded = json.dumps(receipt, sort_keys=True)
    assert "Synthetic policy action" not in encoded
    assert "https://example.test/oges-fixture" not in encoded
    assert "2026-08-08T" not in encoded
    assert '"value"' not in encoded
    assert "signature" not in encoded
    assert "timestamp" not in encoded
    assert receipt["trust"] == csv._TRUST
    assert receipt["boundary"] == csv._BOUNDARY
    assert receipt["boundary"]["role_projection_created"] is False
    assert receipt["boundary"]["source_replay_verified"] is False
    assert receipt["boundary"]["output_equivalence_claimed"] is False
    assert receipt["boundary"]["public_authority"] is False


def test_many_returns_independent_sorted_clauses_with_exact_source_identity(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    second = _reference_second_evidence(fixture)
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    rows = csv.compile_clause_source_views(source, proof).offline.many(
        "evidence.content_availability"
    )
    assert len(rows) == 2
    assert [row.clause_ref.clause_id for row in rows] == sorted(
        row.clause_ref.clause_id for row in rows
    )
    assert len({row.clause_ref for row in rows}) == 2
    assert len({row.value for row in rows}) == 1
    assert {
        row.source_object_refs[0]["object_id"] for row in rows
    } == {"evd:oges.fixture.official.001", second["evidence_id"]}
    assert all(
        row.source_identity_key == {
            "identity_kind": "evidence_item",
            "source_object_ref": row.source_object_refs[0],
        }
        for row in rows
    )


def test_only_licensed_nullable_values_preserve_null_and_source_missing(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path)
    artifact = fixture.root / "artifacts" / "citation-metadata.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"citation metadata locator")

    def make_nullable(document: dict[str, Any]) -> None:
        document["public_url"] = None
        document["published_at"] = None
        document["artifact_path"] = str(artifact.relative_to(fixture.root))
        document["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

    from src import oges_fixture

    oges_fixture._rewrite_object(
        fixture, "evd:oges.fixture.official.001", make_nullable
    )
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    view = csv.compile_clause_source_views(source, proof).offline
    for field in ("evidence.public_url", "evidence.published_at"):
        row = view.many(field)[0]
        assert row.value is None
        assert row.missingness == "source_missing"


def test_captured_inputs_and_accessor_results_are_toctou_safe(tmp_path: Path) -> None:
    _, source, proof = _compiled(tmp_path)
    views = csv.compile_clause_source_views(source, proof)
    label = views.board.one("event.canonical_label").value
    receipt = views.receipt

    _find(source, "event.canonical_label")["value"] = "post-compile mutation"
    proof["roles"].clear()
    assert views.board.one("event.canonical_label").value == label
    assert views.receipt == receipt

    identity = views.research.one("target.identity")
    assert isinstance(identity.value, dict)
    original_object_id = identity.value["object_id"]
    identity.value["object_id"] = "mutated-return"
    identity.source_object_refs[0]["object_id"] = "mutated-return"
    fresh = views.research.one("target.identity")
    assert fresh.value["object_id"] == original_object_id
    assert fresh.source_object_refs[0]["object_id"] == original_object_id

    receipt["bindings"]["source_bundle_ref"]["record_sha256"] = "0" * 64
    assert views.receipt["bindings"]["source_bundle_ref"]["record_sha256"] != "0" * 64
    assert views.verify() is views


def test_accessors_refuse_unknown_omitted_and_cardinality_mismatch(
    tmp_path: Path,
) -> None:
    _, source, proof = _compiled(tmp_path)
    views = csv.compile_clause_source_views(source, proof)
    with _refuses("view_field_unknown"):
        views.board.one("event.caller_selector")
    with _refuses("view_field_not_required"):
        views.board.many("evidence.title")
    with _refuses("view_cardinality_invalid"):
        views.board.many("event.canonical_label")
    with _refuses("view_cardinality_invalid"):
        views.offline.one("evidence.title")


def test_accessors_do_not_reread_profile_or_other_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, source, proof = _compiled(tmp_path)
    views = csv.compile_clause_source_views(source, proof)

    def refuse_read(*_args: object, **_kwargs: object) -> bytes:
        raise AssertionError("post-compile accessor disk read")

    monkeypatch.setattr(csv, "_read_bytes", refuse_read)
    assert views.board.one("event.canonical_label").value == "Synthetic policy action"
    assert views.offline.many("evidence.title")
    assert views.receipt["active_branch_id"] == "branch:path_found"


def test_view_ids_bind_policy_even_if_selected_refs_were_to_match(
    tmp_path: Path,
) -> None:
    _, source, proof = _compiled(tmp_path)
    receipt = csv.compile_clause_source_views(source, proof).receipt
    rows = receipt["consumer_policies"]
    assert len({row["view_id"] for row in rows}) == 4
    assert all(len(row["selected_clause_ref_sha256"]) == 64 for row in rows)
    assert all(row["output_id"] and row["role_id"] for row in rows)


def test_consumer_handles_are_derived_factory_only_and_not_replaceable(
    tmp_path: Path,
) -> None:
    _, source, proof = _compiled(tmp_path)
    views = csv.compile_clause_source_views(source, proof)

    with pytest.raises(TypeError):
        replace(views, board=views.offline)
    with pytest.raises(TypeError):
        replace(views, newsroom=views.research)
    with pytest.raises(AttributeError):
        views.board = views.offline  # type: ignore[misc]
    board_handle = views.board
    with pytest.raises(AttributeError, match="immutable"):
        board_handle._policy = views.offline._policy
    with _refuses("view_field_not_required"):
        board_handle.many("evidence.title")

    with pytest.raises(TypeError, match="factory-only"):
        csv.ClauseSourceViews(
            _construction_token=object(),
            entries=views._entries,
            policies=views._policies,
            source_bytes=views._source_bytes,
            proof_bytes=views._proof_bytes,
            profile_bytes=views._profile_bytes,
            contract_bytes=views._contract_bytes,
            receipt_bytes=views._receipt_bytes,
            runtime_sha256=views._runtime_sha256,
        )

    assert views.board.output_id == "output:board_brief"
    assert views.board.role_id == "board"
    assert views.newsroom.output_id == "output:newsroom_claim_card"
    assert views.newsroom.role_id == "newsroom"
    assert views.verify() is views


def test_public_evidence_output_bytes_are_unchanged() -> None:
    expected = {
        "src/evidence_outputs.py": "d483f6b6f6fa210e30d91da04fe830009616dd49603e8a2fbf4edbc3afe3da9f",
        "governance/evidence_output_registry.json": "24d5c1367f50546ee8188e0e7a9b4ff574f3369ec75c7f0e8807dd14c1c00447",
        "schemas/evidence-output-set.schema.json": "eb044a106b8846de0464fdd32261200c392b0ccf78cb4ad5ed176b247298a780",
        "docs/schemas/evidence-output-set.schema.json": "eb044a106b8846de0464fdd32261200c392b0ccf78cb4ad5ed176b247298a780",
        "docs/data/evidence_outputs_demo.json": "9c6a8b8a1d8bd1a2d07db55bcb8aca348b80fa93ace2703c50deb38a6cf52267",
        "docs/downloads/igrm-evidence-outputs-demo.zip": "e8928d75e14222416da4f6f0f8fffef88fca78b1b0cf49f1ab3fffe705c33efa",
    }
    assert {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected
    } == expected


def _run_refusal_case(
    case_id: str,
    source: dict[str, Any],
    proof: dict[str, Any],
    no_path_source: dict[str, Any],
    no_path_proof: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if case_id == "bundle_a_proof_b":
        mutation = deepcopy(proof)
        mutation["source_bundle_ref"]["record_sha256"] = "0" * 64
        csv.compile_clause_source_views(source, ac._seal(mutation))
    elif case_id == "same_release_different_query":
        csv.compile_clause_source_views(source, no_path_proof)
    elif case_id in {"missing_registered_field", "hidden_truncation_field"}:
        field = (
            "event.class"
            if case_id == "missing_registered_field"
            else "traversal.truncated"
        )
        csv.compile_clause_source_views(*_delete_field(source, field))
    elif case_id == "duplicate_registered_field":
        csv.compile_clause_source_views(
            *_mutate_clause(
                source,
                "event.intensity.status",
                lambda row: row["proof_binding"].update(
                    source_field="event.canonical_label"
                ),
            )
        )
    elif case_id == "cross_evidence_identity":
        csv.compile_clause_source_views(
            *_mutate_clause(
                source,
                "evidence.title",
                lambda row: row["proof_binding"]["source_object_refs"][0].update(
                    object_id="evd:oges.fixture.forged"
                ),
            )
        )
    elif case_id in {
        "event_substitution",
        "target_substitution",
        "max_hops_substitution",
        "max_paths_substitution",
    }:
        field, value = {
            "event_substitution": ("event_id", "evt:oges.fixture.forged"),
            "target_substitution": ("target_entity_id", "ent:country.forged"),
            "max_hops_substitution": ("max_hops", 6),
            "max_paths_substitution": ("max_paths", 99),
        }[case_id]
        csv.compile_clause_source_views(*_mutate_query(source, field, value))
    elif case_id == "branch_status_mismatch":
        csv.compile_clause_source_views(
            *_mutate_clause(
                source, "traversal.status", lambda row: row.update(value="no_path")
            )
        )
    elif case_id == "wrong_limitation_scope":
        csv.compile_clause_source_views(
            *_mutate_clause(
                source,
                "output_limitation:draft_requires_human_review",
                lambda row: row["proof_binding"]["limitation_binding"].update(
                    applicable_scope_ids=["scope:output.newsroom_claim_card"]
                ),
            )
        )
    elif case_id == "source_public_claim":
        changed = deepcopy(source)
        changed["trust"]["production_authority"] = True
        csv.compile_clause_source_views(*_reseal_with_proof(changed))
    elif case_id == "proof_equivalence_claim":
        changed = deepcopy(proof)
        changed["cross_role_proof"]["prose_equivalence_claimed"] = True
        csv.compile_clause_source_views(source, ac._seal(changed))
    elif case_id == "unknown_accessor_field":
        csv.compile_clause_source_views(source, proof).board.one("unknown.field")
    elif case_id == "omitted_accessor_field":
        csv.compile_clause_source_views(source, proof).board.many("evidence.title")
    elif case_id == "one_many_mismatch":
        csv.compile_clause_source_views(source, proof).board.many(
            "event.canonical_label"
        )
    elif case_id == "verified_snapshot_cross_pair_splice":
        views = csv.compile_clause_source_views(source, proof)
        other = csv.compile_clause_source_views(no_path_source, no_path_proof)
        object.__setattr__(views, "_proof_bytes", other._proof_bytes)
        views.verified_snapshot()
    elif case_id == "runtime_drift":
        views = csv.compile_clause_source_views(source, proof)
        monkeypatch.setattr(csv, "_runtime_sha256", lambda: "0" * 64)
        views.verify()
    elif case_id == "profile_drift":
        views = csv.compile_clause_source_views(source, proof)
        original = csv._read_bytes

        def drift(path: Path, code: str) -> bytes:
            raw = original(path, code)
            return raw + b" " if path == csv.PROFILE_PATH else raw

        monkeypatch.setattr(csv, "_read_bytes", drift)
        views.verify()
    else:
        raise AssertionError(case_id)


def test_normative_adversarial_vectors_are_complete_and_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(csv.ADVERSARIAL_VECTORS_PATH.read_text(encoding="utf-8"))
    _, source, proof = _compiled(tmp_path / "path")
    _, no_path_source, no_path_proof = _compiled(tmp_path / "no-path", NO_PATH_QUERY)
    executed: set[str] = set()
    valid_cases = {
        "valid_path_found",
        "valid_no_path",
        "post_compile_input_mutation",
        "post_accessor_return_mutation",
        "verified_snapshot_unaliased",
        "verified_snapshot_corrupt_cache_ignored",
        "verified_snapshot_cache_aba_ignored",
        "verified_snapshot_other_valid_pair",
        "deterministic_recompile",
    }
    for row in registry["cases"]:
        case_id = row["case_id"]
        monkeypatch.undo()
        if case_id == "valid_path_found":
            assert csv.compile_clause_source_views(source, proof).verify()
        elif case_id == "valid_no_path":
            assert csv.compile_clause_source_views(no_path_source, no_path_proof).verify()
        elif case_id == "post_compile_input_mutation":
            source_copy = deepcopy(source)
            proof_copy = deepcopy(proof)
            views = csv.compile_clause_source_views(source_copy, proof_copy)
            source_copy["clauses"].clear()
            proof_copy["roles"].clear()
            assert views.verify()
        elif case_id == "post_accessor_return_mutation":
            views = csv.compile_clause_source_views(source, proof)
            first = views.research.one("target.identity")
            first.value["object_id"] = "mutated"
            assert views.research.one("target.identity").value["object_id"] != "mutated"
        elif case_id == "verified_snapshot_unaliased":
            views = csv.compile_clause_source_views(source, proof)
            snapshot = views.verified_snapshot()
            assert snapshot is not views
            assert snapshot._entries == views._entries
            assert snapshot._entries is not views._entries
            assert snapshot._policies == views._policies
            assert snapshot._policies is not views._policies
            assert snapshot._receipt_bytes == views._receipt_bytes
            assert snapshot._receipt_bytes is not views._receipt_bytes
        elif case_id == "verified_snapshot_corrupt_cache_ignored":
            views = csv.compile_clause_source_views(source, proof)
            other = csv.compile_clause_source_views(no_path_source, no_path_proof)
            _swap_view_caches(views, other)
            snapshot = views.verified_snapshot()
            assert snapshot.research.one("traversal.status").value == "paths_found"
        elif case_id == "verified_snapshot_cache_aba_ignored":
            views = csv.compile_clause_source_views(source, proof)
            other = csv.compile_clause_source_views(no_path_source, no_path_proof)
            mutations = 0

            def mutate_cache(
                target: csv.ClauseSourceViews = views,
                replacement: csv.ClauseSourceViews = other,
            ) -> None:
                nonlocal mutations
                mutations += 1
                _swap_view_caches(target, replacement)

            object.__setattr__(
                views,
                "_source_bytes",
                _CacheMutatingBytes(views._source_bytes, mutate_cache),
            )
            snapshot = views.verified_snapshot()
            assert mutations == 1
            assert snapshot.research.one("traversal.status").value == "paths_found"
        elif case_id == "verified_snapshot_other_valid_pair":
            views = csv.compile_clause_source_views(source, proof)
            other = csv.compile_clause_source_views(no_path_source, no_path_proof)
            object.__setattr__(views, "_source_bytes", other._source_bytes)
            object.__setattr__(views, "_proof_bytes", other._proof_bytes)
            snapshot = views.verified_snapshot()
            assert snapshot.receipt == other.receipt
            assert snapshot.research.one("traversal.status").value == "no_path"
        elif case_id == "deterministic_recompile":
            first = csv.compile_clause_source_views(source, proof)
            second = csv.compile_clause_source_views(source, proof)
            assert first.receipt == second.receipt
            assert first.verify() and second.verify()
        else:
            with _refuses(row["expected_reason"]):
                _run_refusal_case(
                    case_id,
                    source,
                    proof,
                    no_path_source,
                    no_path_proof,
                    monkeypatch,
                )
        assert row["expected_status"] == (
            "valid" if case_id in valid_cases else "refused"
        )
        executed.add(case_id)
    assert executed == {row["case_id"] for row in registry["cases"]}
