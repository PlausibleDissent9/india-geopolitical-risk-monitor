from __future__ import annotations

import ast
import hashlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from src import live_query_admission as admission
from src import live_query_admission_batch as batch

ROOT = Path(__file__).resolve().parents[1]


def _seed(**kwargs: str) -> dict[str, Any]:
    return admission.make_binding(**kwargs)


def _compiled(seed: dict[str, Any] | None = None) -> dict[str, Any]:
    return batch.compile_batch(seed or _seed())


def _fixed() -> batch._FixedInputs:
    return batch._capture_fixed_inputs()


def _case(case_id: str, fixed: batch._FixedInputs) -> dict[str, Any]:
    seed = _seed()
    compiled = _compiled(seed)
    if case_id == "valid_admitted_seed":
        return compiled
    if case_id == "valid_refused_seed_same_batch":
        refused_seed = _seed(
            country="member:country.beta",
            commodity="member:commodity.metal",
            period="member:period.two",
        )
        refused = _compiled(refused_seed)
        assert batch.serialize_record(refused) == batch.serialize_record(compiled)
        return refused
    if case_id == "admission_record_invalid":
        receipts = deepcopy(compiled["admissions"])
        receipts[0]["record_sha256"] = "0" * 64
        batch._validate_admission_set(receipts[0], compiled["binding_universe"], receipts)
    elif case_id == "denominator_shrink":
        receipts = deepcopy(compiled["admissions"][:-1])
        batch._validate_admission_set(receipts[0], compiled["binding_universe"], receipts)
    elif case_id == "duplicate_admission":
        receipts = deepcopy(compiled["admissions"])
        receipts[-1] = deepcopy(receipts[0])
        batch._validate_admission_set(receipts[0], compiled["binding_universe"], receipts)
    elif case_id == "index_reorder":
        receipts = deepcopy(compiled["admissions"])
        receipts[0], receipts[1] = receipts[1], receipts[0]
        batch._validate_admission_set(receipts[0], compiled["binding_universe"], receipts)
    elif case_id == "universe_digest_mismatch":
        universe = deepcopy(compiled["binding_universe"])
        universe[0]["arguments"][0]["member_id"] = "member:country.changed"
        batch._validate_admission_set(compiled["admissions"][0], universe, compiled["admissions"])
    elif case_id == "cross_time_universe_splice":
        later = _compiled(_seed(requested_at="2026-08-10T00:00:01Z"))
        receipts = deepcopy(compiled["admissions"])
        receipts[-1] = deepcopy(later["admissions"][-1])
        batch._validate_admission_set(receipts[0], compiled["binding_universe"], receipts)
    elif case_id == "receipt_root_mismatch":
        mutation = deepcopy(compiled)
        mutation["receipt_universe_root_sha256"] = "0" * 64
        mutation = batch._seal(mutation)
        batch._validate_batch_record(mutation, fixed)
    elif case_id == "implementation_binding_mismatch":
        mutation = deepcopy(compiled)
        mutation["implementation_binding"]["batch_runtime_sha256"] = "0" * 64
        mutation = batch._seal(mutation)
        batch._validate_batch_record(mutation, fixed)
    elif case_id == "contract_drift":
        contract = deepcopy(fixed.contract)
        contract["public_routes"] = ["/forbidden"]
        batch._validate_contract(contract)
    elif case_id == "profile_drift":
        raw = dict(fixed.raw_sha256)
        raw["admission_runtime"] = "0" * 64
        changed = replace(fixed, raw_sha256=raw)
        batch._validate_profile(changed.profile, changed)
    elif case_id == "profile_invalid":
        profile = deepcopy(fixed.profile)
        profile["trust_boundary"]["public_authority"] = True
        batch._validate_profile(profile, fixed)
    elif case_id == "vector_registry_invalid":
        vectors = deepcopy(fixed.vectors)
        vectors["cases"].append(deepcopy(vectors["cases"][0]))
        batch._validate_vectors(vectors)
    elif case_id == "duplicate_json_key":
        batch._parse_json(b'{"x":1,"x":2}', "batch_structure_invalid")
    elif case_id == "structure_invalid":
        batch.verify_batch(seed, {"object_type": "not_a_batch"})
    elif case_id == "typed_canonical_invalid":
        batch._typed_sha(float("nan"))
    elif case_id == "receipt_digest_invalid":
        mutation = deepcopy(compiled)
        mutation["receipt_count"] = 7
        batch._validate_batch_record(mutation, fixed)
    elif case_id == "receipt_recompile_mismatch":
        mutation = deepcopy(compiled)
        mutation["batch_id"] = "batch:live-query.forged"
        mutation = batch._seal(mutation)
        batch.verify_batch(seed, mutation)
    else:
        raise AssertionError(case_id)
    raise AssertionError(f"case accepted: {case_id}")


def test_profile_pins_all_batch_and_upstream_authorities() -> None:
    fixed = _fixed()
    assert fixed.contract["public_routes"] == []
    assert fixed.contract["trust_boundary"]["result_execution_performed"] is False
    assert "does not execute a source query" in fixed.contract["claim_boundary"]
    assert hashlib.sha256(batch.PROFILE_PATH.read_bytes()).hexdigest() == batch._PROFILE_SHA256
    rows = {row["kind"]: row for row in fixed.profile["normative_files"]}
    for kind, relative in batch._NORMATIVE_PATHS.items():
        assert rows[kind]["path"] == relative
        assert rows[kind]["sha256"] == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_batch_calls_only_public_admit_exactly_once_per_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = admission.admit
    calls: list[dict[str, Any]] = []

    def spy(value: dict[str, Any]) -> dict[str, Any]:
        calls.append(deepcopy(value))
        return real(value)

    monkeypatch.setattr(batch.admission, "admit", spy)
    compiled = batch.compile_batch(_seed())
    assert len(calls) == compiled["universe_size"] == 8
    assert {receipt["requested_index"] for receipt in compiled["admissions"]} == set(range(8))
    source = (ROOT / "src/live_query_admission_batch.py").read_text(encoding="utf-8")
    assert "admission._capture" not in source
    assert "admission._enumerate" not in source
    assert "admission._admit" not in source


def test_complete_batch_retains_every_admission_and_refusal() -> None:
    compiled = _compiled()
    assert compiled["receipt_count"] == compiled["universe_size"] == 8
    assert compiled["admitted_count"] == 7
    assert compiled["refused_rights_count"] == 1
    assert compiled["indexes"] == list(range(8))
    assert compiled["all_questions_materialized"] is True
    assert compiled["seed_member_choice_affects_batch"] is False
    assert len(compiled["admissions"]) == 8
    assert compiled["implementation_binding"] == batch._implementation_binding(_fixed())
    assert compiled["trust_boundary"]["implementation_binding_authenticated"] is False
    assert compiled["binding_universe_digest_sha256"] == batch._typed_sha(
        compiled["binding_universe"]
    )
    assert compiled["receipt_universe_root_sha256"] == batch._typed_sha(
        batch._admission_refs(compiled["admissions"])
    )
    assert batch.verify_batch(_seed(), compiled)["status"] == "valid"


def test_seed_choice_and_argument_order_cannot_change_batch_bytes() -> None:
    first = _compiled(_seed())
    refused = _compiled(
        _seed(
            country="member:country.beta",
            commodity="member:commodity.metal",
            period="member:period.two",
        )
    )
    reversed_seed = _seed()
    reversed_seed["arguments"] = list(reversed(reversed_seed["arguments"]))
    reordered = _compiled(reversed_seed)
    assert batch.serialize_record(first) == batch.serialize_record(refused)
    assert batch.serialize_record(first) == batch.serialize_record(reordered)


def test_caller_seed_mutation_after_capture_cannot_change_returned_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = _seed()
    real_capture = batch._capture_fixed_inputs

    def mutate_after_snapshot() -> batch._FixedInputs:
        seed["arguments"][0]["member_id"] = "member:country.*"
        return real_capture()

    monkeypatch.setattr(batch, "_capture_fixed_inputs", mutate_after_snapshot)
    compiled = batch.compile_batch(seed)
    assert compiled["receipt_count"] == 8
    assert (
        compiled["admissions"][0]["requested_arguments"][0]["member_id"] == "member:country.alpha"
    )


def test_invalid_seed_propagates_the_exact_incumbent_refusal() -> None:
    seed = _seed()
    seed["filter"] = "country=*"
    with pytest.raises(
        admission.LiveQueryAdmissionError,
        match="^admission_selector_text_supplied$",
    ):
        batch.compile_batch(seed)


def test_every_batch_runtime_refusal_is_registered() -> None:
    tree = ast.parse((ROOT / "src/live_query_admission_batch.py").read_text(encoding="utf-8"))
    raised: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        if name not in {"_fail", "LiveQueryAdmissionBatchError"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            raised.add(first.value)
    assert raised <= set(_fixed().contract["active_refusal_codes"])


def test_every_normative_batch_case_executes_and_covers_every_code() -> None:
    fixed = _fixed()
    executed: set[str] = set()
    for row in fixed.vectors["cases"]:
        case_id = row["case_id"]
        if row["expected_status"] == "valid":
            assert _case(case_id, fixed)["object_type"] == "live_query_admission_batch"
        else:
            with pytest.raises(batch.LiveQueryAdmissionBatchError) as exc:
                _case(case_id, fixed)
            assert exc.value.code == row["expected_reason"], case_id
        executed.add(case_id)
    assert executed == {row["case_id"] for row in fixed.vectors["cases"]}
    expected = {
        row["expected_reason"]
        for row in fixed.vectors["cases"]
        if row["expected_status"] == "refused"
    }
    assert expected == set(fixed.contract["active_refusal_codes"])


def test_no_public_or_existing_runtime_imports_the_batch() -> None:
    allowed = {
        "src/live_query_admission_batch.py",
        "tests/test_live_query_admission_batch.py",
        "governance/live_query_admission_batch_contract.json",
        "governance/live_query_admission_batch_profile.json",
        "governance/live_query_admission_batch_adversarial_vectors.json",
    }
    for directory in (ROOT / "src", ROOT / "docs", ROOT / ".github"):
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative in allowed:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            assert "live_query_admission_batch" not in text, relative
