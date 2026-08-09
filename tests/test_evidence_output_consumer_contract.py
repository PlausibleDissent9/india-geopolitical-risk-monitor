"""Adversarial contract tests for the inactive renderer-consumer extension."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from src import analytical_clause as ac
from src import evidence_output_consumer_contract as consumer
from src.oges_fixture import Fixture, build_fixture

ROOT = Path(__file__).resolve().parents[1]
PATH_QUERY = "query:analytical_clause.fixture.path_found"
NO_PATH_QUERY = "query:analytical_clause.fixture.no_path"


def _compiled(tmp_path: Path, query_id: str = PATH_QUERY) -> tuple[Fixture, dict[str, Any]]:
    fixture = build_fixture(tmp_path)
    source, _ = ac.compile_source_bound_clauses(
        fixture.manifest, query_id, root=fixture.root
    )
    return fixture, source


def _profile(source: dict[str, Any]) -> dict[str, Any]:
    profile, _ = consumer.load_profile(
        release_effective=date.fromisoformat(source["source_release"]["effective_date"]),
        source_bundle=source,
    )
    return profile


def _refuses(code: str):
    return pytest.raises(
        consumer.EvidenceOutputConsumerContractError, match=f"^{code}$"
    )


def test_profile_is_a_downstream_inactive_extension_not_a_source_dependency(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = _profile(source)
    analytical_source = Path(ac.__file__).read_text(encoding="utf-8")
    assert "evidence_output_consumer_contract" not in analytical_source
    assert "evidence_output_renderer_consumer_profile" not in analytical_source
    assert all(
        row["path"] != "src/evidence_outputs.py"
        for row in profile["consumer_dependencies"]
    )
    assert profile["registry_extension"]["base_engine_is_clause_authority"] is False
    assert profile["registry_extension"]["base_engine_behavior_changed"] is False
    assert profile["binding_rule"]["activation"] is False
    assert profile["migration_boundary"]["activation"] is False


def test_consumer_validator_runtime_is_exactly_pinned_without_clause_authority(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    runtime = profile["validator_runtime"]
    assert runtime["path"] == "src/evidence_output_consumer_contract.py"
    assert runtime["authority"] == "consumer_contract_validator_not_clause_authority"
    assert runtime["sha256"] == hashlib.sha256(
        Path(consumer.__file__).read_bytes()
    ).hexdigest()

    runtime["sha256"] = "0" * 64
    with _refuses("consumer_dependency_drift"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


@pytest.mark.parametrize(
    "query_id,expected_branch,coverage_rows",
    [
        (PATH_QUERY, "branch:path_found", 1),
        (NO_PATH_QUERY, "branch:no_path", 0),
    ],
)
def test_both_branches_resolve_exact_atoms_but_migration_remains_blocked(
    tmp_path: Path, query_id: str, expected_branch: str, coverage_rows: int
) -> None:
    _, source = _compiled(tmp_path, query_id)
    profile = _profile(source)
    result = consumer.validate_resolution(
        profile, source, consumer.expected_source_binding(source)
    )
    assert result["status"] == "blocked_uncovered_reader_datums"
    assert result["active_branch_id"] == expected_branch
    assert result["migration_activated"] is False
    assert result["output_equivalence_claimed"] is False
    assert source["complete_denominators"]["coverage_rows"] == coverage_rows
    assert sum(
        row["proof_binding"]["source_field"] == "coverage.row"
        for row in source["clauses"]
    ) == coverage_rows


def test_profile_uses_source_fields_not_query_specific_clause_ids(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = _profile(source)
    encoded = json.dumps(profile)
    assert '"clause_id"' not in encoded
    assert "query:analytical_clause.fixture" not in encoded
    selectors = profile["source_field_selectors"]
    assert [row["source_field"] for row in selectors] == sorted(
        row["source_field"] for row in selectors
    )
    coverage = next(row for row in selectors if row["source_field"] == "coverage.row")
    assert coverage == {
        "source_field": "coverage.row",
        "cardinality": "exact_bundle_denominator",
        "value_class": "object",
        "denominator_key": "coverage_rows",
        "atomicity": "one_complete_analytical_clause_value",
    }


@pytest.mark.parametrize("attack", ["unknown", "duplicate", "aggregate"])
def test_unknown_duplicate_or_non_atomic_selector_refuses(
    tmp_path: Path, attack: str
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    if attack == "unknown":
        profile = json.loads(
            json.dumps(profile).replace(
                "event.canonical_label", "event.canonical_label_missing"
            )
        )
    elif attack == "duplicate":
        profile["source_field_selectors"].append(
            copy.deepcopy(profile["source_field_selectors"][0])
        )
    else:
        profile["source_field_selectors"][0]["atomicity"] = "renderer_aggregate"
    with _refuses("consumer_selector_invalid"):
        if attack == "unknown":
            consumer.validate_resolution(
                profile, source, consumer.expected_source_binding(source)
            )
        else:
            consumer.validate_profile_document(
                profile, release_effective=date(2026, 8, 8), source_bundle=source
            )


@pytest.mark.parametrize("literal_class", ["integer", "date", "citation_metadata"])
def test_template_cannot_add_number_date_or_citation_as_an_undeclared_literal(
    tmp_path: Path, literal_class: str
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    classes = profile["templates"][0]["literal_value_classes"]
    classes.append(literal_class)
    classes.sort()
    with _refuses("consumer_template_invalid"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


def test_branch_predicate_mismatch_and_missing_required_atom_refuse(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    profile["branches"][0]["predicate"]["value"] = "no_path"
    with _refuses("consumer_branch_invalid"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )

    missing = copy.deepcopy(source)
    missing["clauses"] = [
        row
        for row in missing["clauses"]
        if row["proof_binding"]["source_field"] != "traversal.max_paths"
    ]
    missing["complete_denominators"]["clauses"] -= 1
    missing = ac._seal(missing)
    with _refuses("consumer_selector_invalid"):
        consumer.validate_resolution(
            _profile(source), missing, consumer.expected_source_binding(missing)
        )


@pytest.mark.parametrize("attack", ["literal", "unknown_scope", "moved_scope", "local_alias"])
def test_only_registered_limitation_scope_ids_are_consumable(
    tmp_path: Path, attack: str
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    if attack == "literal":
        profile["templates"][0]["limitation_scope_ids"].append(
            "bounded_traversal_not_complete_exposure"
        )
        profile["templates"][0]["limitation_scope_ids"].sort()
    elif attack == "unknown_scope":
        profile["templates"][0]["limitation_scope_ids"][0] = "scope:output.unknown"
        profile["templates"][0]["limitation_scope_ids"].sort()
    elif attack == "moved_scope":
        profile["consumers"][0]["limitation_scope_ids"][1] = (
            "scope:output.research_package"
        )
        profile["consumers"][0]["limitation_scope_ids"].sort()
    else:
        profile["templates"][0]["limitation_scope_ids"][0] = "scope:renderer.local"
        profile["templates"][0]["limitation_scope_ids"].sort()
    with _refuses("consumer_limitation_scope_invalid"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


@pytest.mark.parametrize("attack", ["unknown", "free_text", "overlap", "missing"])
def test_omission_reasons_are_closed_and_partition_is_unambiguous(
    tmp_path: Path, attack: str
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    consumer_row = profile["consumers"][0]
    if attack == "unknown":
        consumer_row["omitted_registered_selector_fields"][0]["reason_id"] = (
            "omission:unknown"
        )
    elif attack == "free_text":
        consumer_row["omitted_registered_selector_fields"][0]["explanation"] = (
            "not needed here"
        )
    elif attack == "overlap":
        consumer_row["omitted_registered_selector_fields"].append(
            {
                "source_field": consumer_row["required_source_fields"][0],
                "reason_id": "omission:not_used_by_consumer",
            }
        )
        consumer_row["omitted_registered_selector_fields"].sort(
            key=lambda row: row["source_field"]
        )
    else:
        consumer_row["omitted_registered_selector_fields"].pop()
    with _refuses("consumer_omission_invalid"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


@pytest.mark.parametrize(
    "dependency_kind",
    [
        "analytical_clause_contract",
        "analytical_clause_limitations",
        "analytical_clause_runtime",
        "analytical_clause_source_profile",
    ],
)
def test_every_incumbent_analytical_dependency_is_byte_pinned(
    tmp_path: Path, dependency_kind: str
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    next(
        row
        for row in profile["consumer_dependencies"]
        if row["kind"] == dependency_kind
    )["sha256"] = "0" * 64
    with _refuses("consumer_dependency_drift"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


def test_future_profile_and_cross_query_or_release_splice_refuse(
    tmp_path: Path,
) -> None:
    _, path_source = _compiled(tmp_path / "path")
    _, no_path_source = _compiled(tmp_path / "no-path", NO_PATH_QUERY)
    profile = copy.deepcopy(_profile(path_source))
    profile["effective"] = "2026-08-09"
    with _refuses("consumer_profile_not_effective"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=path_source
        )

    valid_profile = _profile(path_source)
    path_binding = consumer.expected_source_binding(path_source)
    with _refuses("consumer_source_binding_invalid"):
        consumer.validate_resolution(valid_profile, no_path_source, path_binding)
    release_splice = consumer.expected_source_binding(path_source)
    release_splice["release_record_sha256"] = "f" * 64
    with _refuses("consumer_source_binding_invalid"):
        consumer.validate_resolution(valid_profile, path_source, release_splice)


def test_all_uncovered_reader_data_are_explicit_and_block_every_consumer(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = _profile(source)
    all_ids = {
        row["datum_id"]
        for output in profile["consumers"]
        for row in output["uncovered_reader_datums"]
    }
    boundary = profile["migration_boundary"]
    assert boundary["uncovered_datum_ids"] == sorted(all_ids)
    assert boundary["uncovered_datum_denominator"] == len(all_ids) == 17
    assert all(
        output["migration_status"] == "blocked_uncovered_reader_datums"
        and output["uncovered_reader_datums"]
        for output in profile["consumers"]
    )
    for claim in (
        "output_equivalence_claimed",
        "prose_equivalence_claimed",
        "product_manifest_claimed",
        "correction_blast_claimed",
        "public_authority_claimed",
    ):
        assert boundary[claim] is False
    assert profile["binding_rule"]["selector_partition_scope"] == (
        "registered_selector_subset_not_complete_clause_denominator"
    )
    assert profile["binding_rule"]["all_source_clause_omission_receipt_available"] is False
    assert boundary["selector_partition_scope"] == (
        "registered_selector_subset_not_complete_clause_denominator"
    )
    assert boundary["all_source_clause_omission_receipt_available"] is False


def test_claiming_a_complete_all_clause_omission_partition_refuses(
    tmp_path: Path,
) -> None:
    _, source = _compiled(tmp_path)
    profile = copy.deepcopy(_profile(source))
    profile["binding_rule"]["selector_partition_scope"] = (
        "complete_clause_denominator"
    )
    profile["binding_rule"]["all_source_clause_omission_receipt_available"] = True
    with _refuses("consumer_profile_invalid"):
        consumer.validate_profile_document(
            profile, release_effective=date(2026, 8, 8), source_bundle=source
        )


def test_incumbent_registry_and_evidence_outputs_remain_non_normative_and_unchanged() -> None:
    profile = json.loads(consumer.PROFILE_PATH.read_text(encoding="utf-8"))
    base = consumer.EVIDENCE_OUTPUT_REGISTRY_PATH
    assert hashlib.sha256(base.read_bytes()).hexdigest() == profile["registry_extension"][
        "base_registry_sha256"
    ]
    engine = json.loads(base.read_text(encoding="utf-8"))["engine"]
    assert hashlib.sha256((ROOT / "src" / "evidence_outputs.py").read_bytes()).hexdigest() == (
        engine["implementation_sha256"]
    )
    contract, _ = ac.load_contract()
    assert contract["roles"] == [
        "research",
        "board",
        "newsroom",
        "public",
        "api",
        "priority_language",
        "offline",
    ]
    assert profile["registry_extension"]["base_engine_is_clause_authority"] is False
    assert profile["migration_boundary"]["public_authority_claimed"] is False


def test_every_consumer_refusal_code_is_registered() -> None:
    profile = json.loads(consumer.PROFILE_PATH.read_text(encoding="utf-8"))
    source = Path(consumer.__file__).read_text(encoding="utf-8")
    raised = {
        line.split('_fail("', 1)[1].split('"', 1)[0]
        for line in source.splitlines()
        if '_fail("' in line
    }
    assert raised == set(profile["refusal_codes"])
