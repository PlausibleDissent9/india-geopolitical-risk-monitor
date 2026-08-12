"""Adversarial tests for the internal Clause-backed reader shadow compiler."""

from __future__ import annotations

import hashlib
import inspect
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from jsonschema import Draft202012Validator
from src import (
    analytical_clause as ac,
)
from src import (
    canonical_objects as canonical,
)
from src import (
    clause_reader_shadow as reader,
)
from src import (
    clause_source_view as csv,
)
from src import (
    evidence_outputs,
    evidence_outputs_fixture,
    oges_fixture,
)
from src.oges_fixture import Fixture

ROOT = Path(__file__).resolve().parents[1]
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"
EVENT_ID = "evt:oges.fixture.policy.001"
PATH_TARGET = "ent:commodity.synthetic_crude"
NO_PATH_TARGET = "ent:country.synthetic_india"


def _views(
    tmp_path: Path, query_id: str = PATH_QUERY
) -> tuple[Fixture, dict[str, Any], dict[str, Any], csv.ClauseSourceViews]:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path)
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, query_id, root=fixture.root
    )
    return fixture, source, proof, csv.compile_clause_source_views(source, proof)


def _legacy(fixture: Fixture, target_id: str) -> dict[str, Any]:
    governance = fixture.root / "governance"
    return evidence_outputs.compile_evidence_outputs(
        fixture.manifest,
        EVENT_ID,
        target_id,
        root=fixture.root,
        schema_registry_path=governance / "canonical_schema_registry.json",
        rights_registry_path=governance / "source_rights_registry.json",
        rights_signers_path=governance / "rights_signers.json",
        method_registry_path=governance / "canonical_method_registry.json",
        release_signers_path=governance / "release_signers.json",
        output_registry_path=governance / "evidence_output_registry.json",
    )


def _artifact_bytes(document: dict[str, Any]) -> bytes:
    body = {key: value for key, value in document.items() if key != "artifact"}
    return (
        json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _assert_parity(
    shadow: reader.ClauseReaderCompilation, legacy: dict[str, Any]
) -> None:
    pairs = (
        ("research_package", shadow.research_package),
        ("board_brief", shadow.board_brief),
        ("newsroom_claim_card", shadow.newsroom_claim_card),
    )
    for output_key, observed in pairs:
        expected = legacy["outputs"][output_key]
        assert observed == expected
        raw = _artifact_bytes(observed)
        assert raw == _artifact_bytes(expected)
        assert len(raw) == expected["artifact"]["bytes"]
        assert hashlib.sha256(raw).hexdigest() == expected["artifact"]["sha256"]


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
    return cast(dict[str, Any], sealed)


def _reference_equal_metadata_evidence(fixture: Fixture) -> dict[str, Any]:
    original = json.loads(
        fixture.objects["evd:oges.fixture.official.001"].read_text(encoding="utf-8")
    )
    evidence_id = "evd:oges.fixture.official.equal-metadata"
    original.update(
        evidence_id=evidence_id,
        source_record_id="official-equal-metadata",
        retrieval_id="ret:oges.fixture.equal-metadata",
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

    oges_fixture._rewrite_object(fixture, EVENT_ID, reference)
    return second


def _make_nullable_metadata(fixture: Fixture) -> None:
    artifact = fixture.root / "artifacts" / "citation-metadata.bin"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"citation metadata locator")

    def nullable(document: dict[str, Any]) -> None:
        document["public_url"] = None
        document["published_at"] = None
        document["artifact_path"] = str(artifact.relative_to(fixture.root))
        document["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

    oges_fixture._rewrite_object(
        fixture, "evd:oges.fixture.official.001", nullable
    )


def _make_max_length_event_label(fixture: Fixture) -> None:
    oges_fixture._rewrite_object(
        fixture,
        EVENT_ID,
        lambda document: document.__setitem__("canonical_label", "x" * 300),
    )


def _compile_nullable_shadow_and_assert_public_offline_refusal(
    fixture: Fixture,
) -> reader.ClauseReaderCompilation:
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    views = csv.compile_clause_source_views(source, proof)
    for role in (views.research, views.newsroom):
        for field in ("evidence.public_url", "evidence.published_at"):
            row = role.many(field)[0]
            assert row.value is None
            assert row.missingness == "source_missing"
    shadow = reader.compile_clause_reader_shadow(views)
    for document in (shadow.research_package, shadow.newsroom_claim_card):
        assert document["evidence"][0]["public_url"] is None
        assert document["evidence"][0]["published_at"] is None
    with pytest.raises(
        evidence_outputs.EvidenceOutputError,
        match="^audit_artifact_redistribution_not_allowed$",
    ) as refusal:
        _legacy(fixture, PATH_TARGET)
    assert refusal.value.code == "audit_artifact_redistribution_not_allowed"
    assert refusal.value.detail == "evd:oges.fixture.official.001"
    return shadow


def _swap_outer_view_state(
    target: csv.ClauseSourceViews, source: csv.ClauseSourceViews
) -> None:
    for attribute in ("_entries", "_policies", "_receipt_bytes"):
        object.__setattr__(target, attribute, getattr(source, attribute))


class _CacheMutatingBytes:
    def __init__(self, raw: bytes, mutate: Callable[[], None]) -> None:
        self._raw = raw
        self._mutate = mutate

    def __bytes__(self) -> bytes:
        self._mutate()
        return self._raw


def _policies(view_receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["role_id"]: row for row in view_receipt["consumer_policies"]}


def _refuses(code: str):
    return pytest.raises(reader.ClauseReaderShadowError, match=f"^{code}$")


def test_one_argument_factory_only_api_and_dependency_boundary() -> None:
    signature = inspect.signature(reader.compile_clause_reader_shadow)
    assert list(signature.parameters) == ["views"]
    assert signature.parameters["views"].default is inspect.Parameter.empty
    assert (
        signature.parameters["views"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )
    with pytest.raises(TypeError):
        reader.compile_clause_reader_shadow(  # type: ignore[call-arg]
            object(), query_id=PATH_QUERY
        )

    source = Path(reader.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "canonical_objects",
        "exposure_graph",
        "evidence_outputs",
        "analytical_clause.py",
        "views._entries",
        "views._policies",
        "views._source_bytes",
        "views._proof_bytes",
        "views._profile_bytes",
    ):
        assert forbidden not in source
    assert "compile_clause_reader_shadow(views: ClauseSourceViews)" in source
    assert "format(" not in source
    assert "eval(" not in source


@pytest.mark.parametrize(
    "query_id,target_id,branch",
    [
        (PATH_QUERY, PATH_TARGET, "branch:path_found"),
        (NO_PATH_QUERY, NO_PATH_TARGET, "branch:no_path"),
    ],
)
def test_both_registered_queries_match_three_legacy_documents_and_artifact_bytes(
    tmp_path: Path, query_id: str, target_id: str, branch: str
) -> None:
    fixture, _, _, views = _views(tmp_path, query_id)
    shadow = reader.compile_clause_reader_shadow(views)
    _assert_parity(shadow, _legacy(fixture, target_id))
    assert shadow.verify() is shadow
    assert shadow.receipt["active_branch_id"] == branch
    assert shadow.receipt["comparison_performed"] is False
    assert shadow.receipt["comparison_result"] == "not_performed"
    assert shadow.receipt["boundary"]["comparison_performed"] is False
    assert shadow.receipt["boundary"]["comparison_result"] == "not_performed"
    assert shadow.receipt["boundary"]["general_equivalence_claimed"] is False
    if branch == "branch:no_path":
        linkage = shadow.board_brief["sections"][1]["text"]
        assert "bounded non-result" in linkage
        assert "not evidence that exposure is absent" in linkage


def test_multi_evidence_equal_metadata_uses_identity_join_without_dedup(
    tmp_path: Path,
) -> None:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path)
    second = _reference_equal_metadata_evidence(fixture)
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    shadow = reader.compile_clause_reader_shadow(
        csv.compile_clause_source_views(source, proof)
    )
    _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
    citations = shadow.research_package["evidence"]
    assert len(citations) == 2
    assert {row["evidence_id"] for row in citations} == {
        "evd:oges.fixture.official.001",
        second["evidence_id"],
    }
    metadata = [
        {
            key: value
            for key, value in row.items()
            if key not in {"evidence_id", "record_sha256"}
        }
        for row in citations
    ]
    assert metadata[0] == metadata[1]
    assert shadow.receipt["outputs"][2]["denominators"][
        "evidence_item_denominator"
    ] == 2


def test_nullable_metadata_is_preserved_while_public_offline_compile_refuses(
    tmp_path: Path,
) -> None:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path)
    _make_nullable_metadata(fixture)
    _compile_nullable_shadow_and_assert_public_offline_refusal(fixture)


def test_valid_shadow_documents_pass_the_pinned_public_subdocument_schemas(
    tmp_path: Path,
) -> None:
    _, _, _, views = _views(tmp_path)
    shadow = reader.compile_clause_reader_shadow(views)
    fixed = reader._load_fixed_inputs()
    documents = (
        shadow.research_package,
        shadow.board_brief,
        shadow.newsroom_claim_card,
    )
    for document in documents:
        validator = fixed.public_output_validators[document["output_id"]]
        assert list(validator.iter_errors(document)) == []


def test_max_length_source_label_refuses_schema_invalid_shadow_and_public_output(
    tmp_path: Path,
) -> None:
    fixture = evidence_outputs_fixture.build_fixture(tmp_path)
    _make_max_length_event_label(fixture)
    source, proof = ac.compile_source_bound_clauses(
        fixture.manifest, PATH_QUERY, root=fixture.root
    )
    views = csv.compile_clause_source_views(source, proof)
    with pytest.raises(
        reader.ClauseReaderShadowError, match="^reader_artifact_invalid$"
    ) as shadow_refusal:
        reader.compile_clause_reader_shadow(views)
    assert shadow_refusal.value.detail == "output:board_brief:/title:maxLength"
    with pytest.raises(
        evidence_outputs.EvidenceOutputError, match="^output_schema_invalid$"
    ) as public_refusal:
        _legacy(fixture, PATH_TARGET)
    assert public_refusal.value.code == "output_schema_invalid"
    assert public_refusal.value.detail.endswith(":maxLength")


def test_reader_uses_only_unaliased_verified_snapshot_under_cache_aba(
    tmp_path: Path,
) -> None:
    path_fixture, _, _, path_views = _views(tmp_path / "path")
    _, _, _, no_path_views = _views(tmp_path / "no-path", NO_PATH_QUERY)
    clean = reader.compile_clause_reader_shadow(path_views)
    _assert_parity(clean, _legacy(path_fixture, PATH_TARGET))
    assert clean._snapshot is not path_views
    assert clean._snapshot._entries is not path_views._entries
    assert clean._snapshot._policies is not path_views._policies
    assert clean._snapshot._receipt_bytes is not path_views._receipt_bytes

    corrupt = csv.compile_clause_source_views(
        json.loads(path_views._source_bytes), json.loads(path_views._proof_bytes)
    )
    _swap_outer_view_state(corrupt, no_path_views)
    corrupt_shadow = reader.compile_clause_reader_shadow(corrupt)
    assert corrupt_shadow.research_package == clean.research_package
    assert corrupt_shadow.board_brief == clean.board_brief
    assert corrupt_shadow.newsroom_claim_card == clean.newsroom_claim_card

    aba = csv.compile_clause_source_views(
        json.loads(path_views._source_bytes), json.loads(path_views._proof_bytes)
    )
    mutations = 0

    def mutate_cache() -> None:
        nonlocal mutations
        mutations += 1
        _swap_outer_view_state(aba, no_path_views)

    object.__setattr__(
        aba, "_source_bytes", _CacheMutatingBytes(aba._source_bytes, mutate_cache)
    )
    aba_shadow = reader.compile_clause_reader_shadow(aba)
    assert mutations == 1
    assert aba_shadow.research_package == clean.research_package
    assert aba_shadow.board_brief == clean.board_brief
    assert aba_shadow.newsroom_claim_card == clean.newsroom_claim_card


def test_reader_snapshot_cross_pair_refuses_and_outer_mutation_cannot_rebind(
    tmp_path: Path,
) -> None:
    _, _, _, path_views = _views(tmp_path / "path")
    _, _, _, no_path_views = _views(tmp_path / "no-path", NO_PATH_QUERY)
    spliced = path_views.verified_snapshot()
    object.__setattr__(spliced, "_proof_bytes", no_path_views._proof_bytes)
    with _refuses("reader_input_invalid"):
        reader.compile_clause_reader_shadow(spliced)

    shadow = reader.compile_clause_reader_shadow(path_views)
    expected = (
        shadow.research_package,
        shadow.board_brief,
        shadow.newsroom_claim_card,
        shadow.receipt,
    )
    _swap_outer_view_state(path_views, no_path_views)
    object.__setattr__(path_views, "_source_bytes", no_path_views._source_bytes)
    object.__setattr__(path_views, "_proof_bytes", no_path_views._proof_bytes)
    assert shadow.verify() is shadow
    assert (
        shadow.research_package,
        shadow.board_brief,
        shadow.newsroom_claim_card,
        shadow.receipt,
    ) == expected


def test_receipt_is_schema_valid_value_free_and_binds_exact_program(
    tmp_path: Path,
) -> None:
    _, source, proof, views = _views(tmp_path)
    shadow = reader.compile_clause_reader_shadow(views)
    receipt = shadow.receipt
    schema = json.loads(reader.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(receipt)
    assert receipt["record_sha256"] == reader._record_sha256(receipt)
    encoded = json.dumps(receipt, sort_keys=True)
    for leaked in (
        "Synthetic policy action",
        "https://",
        "2026-08-08",
        '"value"',
        '"prose"',
        '"signature"',
    ):
        assert leaked not in encoded
    assert receipt["trust"] == dict(reader._TRUST)
    assert receipt["boundary"] == dict(reader._BOUNDARY)
    assert receipt["comparison_performed"] is False
    assert receipt["comparison_result"] == "not_performed"
    assert receipt["denominators"]["output_denominator"] == 3
    assert [row["output_id"] for row in receipt["outputs"]] == sorted(
        value[0] for value in reader._OUTPUT_ROLES.values()
    )
    assert all(row["clause_refs"] for row in receipt["outputs"])
    assert all(row["operator_ids"] for row in receipt["outputs"])
    assert all(row["rendered_limitation_scope_ids"] for row in receipt["outputs"])
    assert all(
        row["applicable_but_outer_wrapper_absent_scope_ids"]
        == ["scope:output.all_views"]
        for row in receipt["outputs"]
    )
    assert receipt["bindings"]["source_bundle_ref"]["record_sha256"] == source[
        "record_sha256"
    ]
    assert receipt["bindings"]["role_proof_bundle_ref"]["record_sha256"] == proof[
        "record_sha256"
    ]
    assert receipt["bindings"]["view_receipt_ref"]["record_sha256"] == views.receipt[
        "record_sha256"
    ]
    assert receipt["bindings"]["public_common_schema_ref"]["file_sha256"] == hashlib.sha256(
        reader.PUBLIC_COMMON_SCHEMA_PATH.read_bytes()
    ).hexdigest()


def test_compilation_is_immutable_factory_only_and_returns_fresh_copies(
    tmp_path: Path,
) -> None:
    _, _, _, views = _views(tmp_path)
    shadow = reader.compile_clause_reader_shadow(views)
    research = shadow.research_package
    board = shadow.board_brief
    newsroom = shadow.newsroom_claim_card
    receipt = shadow.receipt
    research["title"] = "mutated"
    board["sections"][0]["text"] = "mutated"
    newsroom["claims"].clear()
    receipt["outputs"].clear()
    assert shadow.research_package["title"] != "mutated"
    assert shadow.board_brief["sections"][0]["text"] != "mutated"
    assert shadow.newsroom_claim_card["claims"]
    assert len(shadow.receipt["outputs"]) == 3
    with pytest.raises(AttributeError, match="immutable"):
        shadow._board_bytes = b"{}"  # type: ignore[misc]
    with pytest.raises(TypeError, match="factory-only"):
        reader.ClauseReaderCompilation(
            _construction_token=object(),
            snapshot=views,
            fixed_bytes=(),
            runtime_sha256="0" * 64,
            research_bytes=b"{}",
            research_artifact_bytes=b"{}",
            board_bytes=b"{}",
            board_artifact_bytes=b"{}",
            newsroom_bytes=b"{}",
            newsroom_artifact_bytes=b"{}",
            receipt_bytes=b"{}",
        )


def test_input_is_snapshotted_once_and_each_output_uses_only_its_role_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, _, views = _views(tmp_path)
    snapshot_calls = 0
    captured_snapshot: csv.ClauseSourceViews | None = None
    original_snapshot = csv.ClauseSourceViews.verified_snapshot

    def counted_snapshot(self: csv.ClauseSourceViews) -> csv.ClauseSourceViews:
        nonlocal snapshot_calls, captured_snapshot
        snapshot_calls += 1
        captured_snapshot = original_snapshot(self)
        return captured_snapshot

    handle_type = type(views.research)
    original_one = handle_type.one
    original_many = handle_type.many
    accesses: list[tuple[str, str]] = []

    def logged_one(self: Any, source_field: str) -> csv.ClauseValue[Any]:
        accesses.append((self.role_id, source_field))
        return original_one(self, source_field)

    def logged_many(
        self: Any, source_field: str
    ) -> tuple[csv.ClauseValue[Any], ...]:
        accesses.append((self.role_id, source_field))
        return original_many(self, source_field)

    monkeypatch.setattr(csv.ClauseSourceViews, "verified_snapshot", counted_snapshot)
    monkeypatch.setattr(handle_type, "one", logged_one)
    monkeypatch.setattr(handle_type, "many", logged_many)
    shadow = reader.compile_clause_reader_shadow(views)
    assert snapshot_calls == 1
    assert captured_snapshot is shadow._snapshot
    assert captured_snapshot is not views
    receipt_policies = _policies(shadow._snapshot.receipt)
    assert {role for role, _ in accesses} == {"research", "board", "newsroom"}
    assert all(
        field in receipt_policies[role]["required_source_field_ids"]
        for role, field in accesses
    )
    assert all(role != "offline" for role, _ in accesses)


def test_limitations_and_review_status_derive_from_the_single_pinned_registry(
    tmp_path: Path,
) -> None:
    _, _, _, views = _views(tmp_path)
    shadow = reader.compile_clause_reader_shadow(views)
    registry = json.loads(reader.LIMITATION_REGISTRY_PATH.read_text(encoding="utf-8"))
    assert shadow.research_package["limitations"] == registry["output_profiles"][
        "scope:output.research_package"
    ]
    assert shadow.board_brief["limitations"] == registry["output_profiles"][
        "scope:output.board_brief"
    ]
    assert shadow.newsroom_claim_card["limitations"] == registry["output_profiles"][
        "scope:output.newsroom_claim_card"
    ]
    assert shadow.board_brief["review_status"] in registry["output_profiles"][
        "scope:output.board_brief"
    ]
    receipt = shadow.receipt
    assert receipt["boundary"][
        "standalone_activation_requires_common_scope_wrapper"
    ] is True
    rows = {row["output_id"]: row for row in receipt["outputs"]}
    observed_by_output = {
        "output:research_package": {
            "scope:output.research_package": shadow.research_package["limitations"]
        },
        "output:board_brief": {
            "scope:output.board_brief": shadow.board_brief["limitations"]
        },
        "output:newsroom_claim_card": {
            "scope:claim.card.event_record": shadow.newsroom_claim_card["claims"][0][
                "limitations"
            ],
            "scope:claim.card.release_structure": shadow.newsroom_claim_card[
                "claims"
            ][1]["limitations"],
            "scope:output.newsroom_claim_card": shadow.newsroom_claim_card[
                "limitations"
            ],
        },
    }
    for output_id, executions in observed_by_output.items():
        row = rows[output_id]
        assert row["applicable_but_outer_wrapper_absent_scope_ids"] == [
            "scope:output.all_views"
        ]
        assert "scope:output.all_views" not in row["rendered_limitation_scope_ids"]
        assert sorted(executions) == row["rendered_limitation_scope_ids"]
        for scope_id, limitation_ids in executions.items():
            assert limitation_ids == registry["output_profiles"][scope_id]
        assert "operator:limitation.scope.v1" in row["operator_ids"]
    source = Path(reader.__file__).read_text(encoding="utf-8")
    assert "_RESEARCH_LIMITATIONS" not in source
    assert "_BRIEF_LIMITATIONS" not in source
    assert "_CLAIM_LIMITATIONS" not in source


def _capture_role_fields(
    views: csv.ClauseSourceViews, role: str
) -> dict[str, tuple[csv.ClauseValue[Any], ...]]:
    fixed = reader._load_fixed_inputs()
    branch = views.receipt["active_branch_id"]
    _, consumed, _, _, _ = reader._role_program(fixed.template, role, branch)
    return reader._capture_fields(getattr(views, role), consumed)


def _run_refusal_case(
    case_id: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if case_id in {"handle_swap", "role_crossing"}:
        _, _, _, views = _views(tmp_path)
        fixed = reader._load_fixed_inputs()
        receipt = views.receipt
        policies = _policies(receipt)
        if case_id == "handle_swap":
            reader._compile_board(
                views.newsroom,
                fixed.template,
                fixed.limitations,
                receipt["active_branch_id"],
                policies["board"],
                receipt,
            )
        else:
            reader._compile_newsroom(
                views.board,
                fixed.template,
                fixed.limitations,
                receipt["active_branch_id"],
                policies["newsroom"],
                receipt,
            )
    elif case_id == "handle_mutation":
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        object.__setattr__(shadow, "_board_bytes", b"{}")
        shadow.verify()
    elif case_id == "cross_release_query_view_splice":
        _, _, _, views = _views(tmp_path / "path")
        _, _, _, other = _views(tmp_path / "other", NO_PATH_QUERY)
        object.__setattr__(views, "_source_bytes", other._source_bytes)
        reader.compile_clause_reader_shadow(views)
    elif case_id == "snapshot_cross_pair_splice":
        _, _, _, views = _views(tmp_path / "path")
        _, _, _, other = _views(tmp_path / "other", NO_PATH_QUERY)
        object.__setattr__(views, "_proof_bytes", other._proof_bytes)
        reader.compile_clause_reader_shadow(views)
    elif case_id == "post_capture_mutation":
        _, _, _, views = _views(tmp_path / "path")
        shadow = reader.compile_clause_reader_shadow(views)
        _, _, _, other = _views(tmp_path / "other", NO_PATH_QUERY)
        object.__setattr__(shadow, "_snapshot", other.verified_snapshot())
        shadow.verify()
    elif case_id == "coordinated_template_contract_self_attestation":
        original = reader._read_bytes

        def drift(path: Path, code: str) -> bytes:
            raw = original(path, code)
            if path in {reader.CONTRACT_PATH, reader.TEMPLATE_PROFILE_PATH}:
                return raw + b" "
            return raw

        monkeypatch.setattr(reader, "_read_bytes", drift)
        reader._load_fixed_inputs()
    elif case_id in {"missing_clause_ref", "extra_clause_ref"}:
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        receipt = shadow.receipt
        refs = receipt["outputs"][0]["clause_refs"]
        if case_id == "missing_clause_ref":
            refs.pop()
        else:
            refs.append(deepcopy(refs[0]))
        receipt = reader._seal(receipt)
        reader._validate_receipt(receipt, reader._load_fixed_inputs())
    elif case_id == "resealed_body_mutation":
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        body = shadow.research_package
        body["title"] = "resealed mutation"
        object.__setattr__(
            shadow,
            "_research_bytes",
            reader._canonical_bytes(body, "reader_recompile_mismatch"),
        )
        shadow.verify()
    elif case_id in {
        "resealed_receipt_mutation",
        "comparison_success_self_attestation",
    }:
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        receipt = shadow.receipt
        if case_id == "resealed_receipt_mutation":
            receipt["denominators"]["output_denominator"] = 4
        else:
            receipt["comparison_performed"] = True
            receipt["comparison_result"] = "passed"
        reader._validate_receipt(reader._seal(receipt), reader._load_fixed_inputs())
    elif case_id == "multi_evidence_equal_value_dedup":
        fixture = evidence_outputs_fixture.build_fixture(tmp_path)
        _reference_equal_metadata_evidence(fixture)
        source, proof = ac.compile_source_bound_clauses(
            fixture.manifest, PATH_QUERY, root=fixture.root
        )
        views = csv.compile_clause_source_views(source, proof)
        fields = _capture_role_fields(views, "research")
        fields["evidence.title"] = fields["evidence.title"][:1]
        reader._evidence_citations(fields)
    elif case_id == "null_laundering":
        _, _, _, views = _views(tmp_path)
        row = views.research.many("evidence.public_url")[0]
        mutation = replace(row, value=None, missingness="present")
        reader._validate_clause_value("evidence.public_url", mutation)
    elif case_id == "off_path_evidence_injection":
        fixture = evidence_outputs_fixture.build_fixture(tmp_path)
        _reference_equal_metadata_evidence(fixture)
        source, proof = ac.compile_source_bound_clauses(
            fixture.manifest, PATH_QUERY, root=fixture.root
        )
        views = csv.compile_clause_source_views(source, proof)
        fields = _capture_role_fields(views, "research")
        injected = replace(
            fields["evidence.title"][0],
            source_identity_key={
                "identity_kind": "evidence_item",
                "source_object_ref": {
                    "object_type": "evidence_item",
                    "object_id": "evd:off-path",
                    "record_sha256": "0" * 64,
                },
            },
        )
        fields["evidence.title"] = (injected, *fields["evidence.title"][1:])
        reader._evidence_citations(fields)
    elif case_id in {"limitation_omission", "limitation_scope_alias"}:
        registry = json.loads(
            reader.LIMITATION_REGISTRY_PATH.read_text(encoding="utf-8")
        )
        identifier = registry["output_profiles"]["scope:output.board_brief"][0]
        if case_id == "limitation_omission":
            registry["output_profiles"]["scope:output.board_brief"].remove(identifier)
        else:
            registry["limitation_scopes"][identifier] = ["scope:output.alias"]
        reader._validate_limitations(registry)
    elif case_id == "outer_scope_rendered_laundering":
        profile = json.loads(reader.TEMPLATE_PROFILE_PATH.read_text(encoding="utf-8"))
        template = next(
            row
            for row in profile["templates"]
            if row["template_id"] == "template:research.package.shell.v1"
        )
        template["rendered_limitation_scope_ids"].append(
            "scope:output.all_views"
        )
        reader._validate_template_profile(profile)
    elif case_id in {"both_branch_templates", "neither_branch_template"}:
        _, _, _, views = _views(tmp_path)
        fields = _capture_role_fields(views, "board")
        wrong = (
            "branch:no_path"
            if case_id == "both_branch_templates"
            else "branch:neither"
        )
        reader._branch(fields, wrong)
    elif case_id == "no_path_no_exposure_laundering":
        profile = json.loads(reader.TEMPLATE_PROFILE_PATH.read_text(encoding="utf-8"))
        template = next(
            row
            for row in profile["templates"]
            if row["template_id"] == "template:board.linkage.no_path.v1"
        )
        template["rendered_strings"][0]["tokens"][-1]["value"] = (
            " hop(s). This proves there is no exposure."
        )
        reader._validate_template_profile(profile)
    elif case_id == "hidden_truncation":
        _, _, _, views = _views(tmp_path, NO_PATH_QUERY)
        fields = _capture_role_fields(views, "board")
        fields["traversal.truncated"] = (
            replace(fields["traversal.truncated"][0], value=True),
        )
        reader._branch(fields, "branch:no_path")
    elif case_id == "receipt_value_leakage":
        reader._assert_value_free({"leaked": "https://example.test/source"})
    elif case_id == "public_schema_invalid_render":
        fixture = evidence_outputs_fixture.build_fixture(tmp_path)
        _make_max_length_event_label(fixture)
        source, proof = ac.compile_source_bound_clauses(
            fixture.manifest, PATH_QUERY, root=fixture.root
        )
        reader.compile_clause_reader_shadow(
            csv.compile_clause_source_views(source, proof)
        )
    elif case_id == "public_common_schema_drift":
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        original = reader._read_bytes

        def drift_common(path: Path, code: str) -> bytes:
            raw = original(path, code)
            return raw + b" " if path == reader.PUBLIC_COMMON_SCHEMA_PATH else raw

        monkeypatch.setattr(reader, "_read_bytes", drift_common)
        shadow.verify()
    elif case_id == "public_byte_drift":
        _, _, _, views = _views(tmp_path)
        shadow = reader.compile_clause_reader_shadow(views)
        original = reader._read_bytes

        def drift(path: Path, code: str) -> bytes:
            raw = original(path, code)
            return raw + b" " if path == reader.PUBLIC_SCHEMA_PATH else raw

        monkeypatch.setattr(reader, "_read_bytes", drift)
        shadow.verify()
    else:
        raise AssertionError(case_id)


def test_normative_adversarial_vectors_are_complete_and_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = json.loads(
        reader.ADVERSARIAL_VECTORS_PATH.read_text(encoding="utf-8")
    )
    required = {
        "handle_swap",
        "handle_mutation",
        "cross_release_query_view_splice",
        "role_crossing",
        "post_capture_mutation",
        "corrupt_outer_cache_ignored",
        "snapshot_cross_pair_splice",
        "outer_cache_aba_during_snapshot",
        "outer_mutation_after_snapshot",
        "coordinated_template_contract_self_attestation",
        "missing_clause_ref",
        "extra_clause_ref",
        "resealed_body_mutation",
        "resealed_receipt_mutation",
        "comparison_success_self_attestation",
        "multi_evidence_equal_value_join",
        "multi_evidence_equal_value_dedup",
        "nullable_metadata_preserved_public_offline_refused",
        "null_laundering",
        "off_path_evidence_injection",
        "limitation_omission",
        "limitation_scope_alias",
        "outer_scope_rendered_laundering",
        "both_branch_templates",
        "neither_branch_template",
        "no_path_no_exposure_laundering",
        "hidden_truncation",
        "receipt_value_leakage",
        "public_schema_invalid_render",
        "public_common_schema_drift",
        "public_byte_drift",
    }
    assert required <= {row["case_id"] for row in registry["cases"]}
    executed: set[str] = set()
    valid_cases = {
        "valid_path_found_fixture_parity",
        "valid_no_path_fixture_parity",
        "corrupt_outer_cache_ignored",
        "outer_cache_aba_during_snapshot",
        "outer_mutation_after_snapshot",
        "multi_evidence_equal_value_join",
        "nullable_metadata_preserved_public_offline_refused",
    }
    for row in registry["cases"]:
        case_id = row["case_id"]
        monkeypatch.undo()
        case_root = tmp_path / case_id.replace(":", "_")
        if case_id == "valid_path_found_fixture_parity":
            fixture, _, _, views = _views(case_root)
            shadow = reader.compile_clause_reader_shadow(views)
            _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
        elif case_id == "valid_no_path_fixture_parity":
            fixture, _, _, views = _views(case_root, NO_PATH_QUERY)
            shadow = reader.compile_clause_reader_shadow(views)
            _assert_parity(shadow, _legacy(fixture, NO_PATH_TARGET))
        elif case_id == "corrupt_outer_cache_ignored":
            fixture, _, _, views = _views(case_root / "path")
            _, _, _, other = _views(case_root / "other", NO_PATH_QUERY)
            _swap_outer_view_state(views, other)
            shadow = reader.compile_clause_reader_shadow(views)
            _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
        elif case_id == "outer_cache_aba_during_snapshot":
            fixture, _, _, views = _views(case_root / "path")
            _, _, _, other = _views(case_root / "other", NO_PATH_QUERY)
            mutations = 0

            def mutate_cache(
                target: csv.ClauseSourceViews = views,
                replacement: csv.ClauseSourceViews = other,
            ) -> None:
                nonlocal mutations
                mutations += 1
                _swap_outer_view_state(target, replacement)

            object.__setattr__(
                views,
                "_source_bytes",
                _CacheMutatingBytes(views._source_bytes, mutate_cache),
            )
            shadow = reader.compile_clause_reader_shadow(views)
            assert mutations == 1
            _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
        elif case_id == "outer_mutation_after_snapshot":
            fixture, _, _, views = _views(case_root / "path")
            _, _, _, other = _views(case_root / "other", NO_PATH_QUERY)
            shadow = reader.compile_clause_reader_shadow(views)
            expected = (
                shadow.research_package,
                shadow.board_brief,
                shadow.newsroom_claim_card,
                shadow.receipt,
            )
            _swap_outer_view_state(views, other)
            object.__setattr__(views, "_source_bytes", other._source_bytes)
            object.__setattr__(views, "_proof_bytes", other._proof_bytes)
            assert shadow.verify() is shadow
            assert (
                shadow.research_package,
                shadow.board_brief,
                shadow.newsroom_claim_card,
                shadow.receipt,
            ) == expected
            _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
        elif case_id == "multi_evidence_equal_value_join":
            fixture = evidence_outputs_fixture.build_fixture(case_root)
            _reference_equal_metadata_evidence(fixture)
            source, proof = ac.compile_source_bound_clauses(
                fixture.manifest, PATH_QUERY, root=fixture.root
            )
            shadow = reader.compile_clause_reader_shadow(
                csv.compile_clause_source_views(source, proof)
            )
            _assert_parity(shadow, _legacy(fixture, PATH_TARGET))
        elif case_id == "nullable_metadata_preserved_public_offline_refused":
            fixture = evidence_outputs_fixture.build_fixture(case_root)
            _make_nullable_metadata(fixture)
            _compile_nullable_shadow_and_assert_public_offline_refusal(fixture)
        else:
            with _refuses(row["expected_reason"]):
                _run_refusal_case(case_id, case_root, monkeypatch)
        assert row["expected_status"] == (
            "valid" if case_id in valid_cases else "refused"
        )
        executed.add(case_id)
    assert executed == {row["case_id"] for row in registry["cases"]}


def test_public_evidence_output_surface_remains_byte_identical() -> None:
    expected = {
        "src/evidence_outputs.py": "d483f6b6f6fa210e30d91da04fe830009616dd49603e8a2fbf4edbc3afe3da9f",
        "governance/evidence_output_registry.json": "24d5c1367f50546ee8188e0e7a9b4ff574f3369ec75c7f0e8807dd14c1c00447",
        "schemas/evidence-output-set.schema.json": "eb044a106b8846de0464fdd32261200c392b0ccf78cb4ad5ed176b247298a780",
        "docs/schemas/evidence-output-set.schema.json": "eb044a106b8846de0464fdd32261200c392b0ccf78cb4ad5ed176b247298a780",
        "src/evidence_outputs_fixture.py": "26b6d7a7882f2221d7f05f51b2d7efd2b43ea94a46c8180b0d47575cd62a9e64",
        "docs/data/evidence_outputs_demo.json": "ef3b2bfc18200e0671b4fab24edeb781b6b1d4a5efc8a41acc97a310778b33e3",
        "docs/downloads/igrm-evidence-outputs-demo.zip": "095154edbed552cb35a388e4141315bbf3302754a2b33e8a89c9f3ec54bf7eed",
    }
    assert {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in expected
    } == expected


def test_incumbent_consumer_and_view_identities_are_versioned_not_silently_mutated() -> None:
    profile = json.loads(reader.CONSUMER_PROFILE_PATH.read_text(encoding="utf-8"))
    contract = json.loads(reader.VIEW_CONTRACT_PATH.read_text(encoding="utf-8"))
    board = next(
        row for row in profile["consumers"] if row["output_id"] == "output:board_brief"
    )
    assert profile["schema_version"] == "0.2.0"
    assert profile["profile_id"].endswith(":0.2.0")
    assert contract["schema_version"] == "0.2.0"
    assert contract["contract_id"].endswith(":0.2.0")
    assert "evidence.identity" in board["required_source_fields"]
    assert "evidence.identity" not in {
        row["source_field"] for row in board["omitted_registered_selector_fields"]
    }
    assert board["required_source_fields"] == sorted(board["required_source_fields"])
