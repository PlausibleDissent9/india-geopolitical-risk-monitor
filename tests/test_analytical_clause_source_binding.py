"""Source replay and all-role proof tests for the incumbent clause contract."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pytest
from src import analytical_clause as ac
from src import canonical_objects as canonical
from src.oges_fixture import Fixture, build_fixture

ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "governance" / "analytical_clause_adversarial_vectors.json"
PROFILE = ROOT / "governance" / "analytical_clause_source_profile.json"
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
        "rights_rows": 1,
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
    assert len(executed) == 34


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
    assert contract["roles"] == list(ac._REQUIRED_ROLES)
    assert "protected_fields" not in contract
    for row in profile["normative_files"]:
        assert row["sha256"] == hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest()
