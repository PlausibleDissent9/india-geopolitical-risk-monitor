from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from src import consequence_plan as cp
from src import evidence_assistant as assistant
from src import knowledge_replay
from src.knowledge_replay_fixture import build_fixture

ROOT = Path(__file__).resolve().parents[1]
FIXED_COMPILED = "2026-08-09T12:00:00Z"
FIXED_EXECUTED = "2026-08-09T12:00:01Z"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _seal(plan: dict[str, Any]) -> dict[str, Any]:
    plan["integrity"]["value_sha256"] = "0" * 64
    plan["integrity"]["value_sha256"] = cp._typed_digest(plan)
    return plan


def _assistant_plans() -> list[assistant.Plan]:
    plans = [
        assistant.plan_question("latest headline"),
        assistant.plan_question("what does IGRM measure"),
        assistant.plan_question("Pakistan reading"),
        assistant.plan_question("Compare Pakistan versus China"),
        assistant.plan_question("Pakistan evidence"),
        assistant.plan_question("Why is the current Pakistan score here?"),
        assistant.plan_question("forecast the market"),
        assistant.plan_question("write me a poem"),
    ]
    assert {plan.template_id for plan in plans} == {
        "latest_headline",
        "instrument_scope",
        "channel_reading",
        "channel_comparison",
        "receipt_evidence",
        "current_receipt_evidence",
        "refusal_forbidden",
        "refusal_unsupported",
    }
    return plans


@pytest.mark.parametrize("legacy", _assistant_plans(), ids=lambda plan: plan.template_id)
def test_legacy_adapter_is_exact_and_never_publication_eligible(
    legacy: assistant.Plan,
) -> None:
    plan = cp.from_legacy_assistant_plan(legacy, compiled_at=FIXED_COMPILED)
    execution = cp.execute_plan(plan, executed_at=FIXED_EXECUTED)
    assert execution["execution_status"] == "succeeded"
    assert execution["publication_eligible"] is False
    assert execution["trust_class"] == "legacy_unverified"
    assert execution["result"]["output"] == assistant.answer_plan(legacy).to_dict()
    expected_kind = (
        "registered_refusal"
        if assistant.answer_plan(legacy).status == "refused"
        else "descriptive_registered_answer"
    )
    assert execution["result"]["output_kind"] == expected_kind
    cp._verify_integrity(plan, "plan_integrity_mismatch")
    cp._verify_integrity(execution, "execution_integrity_mismatch")


def test_current_receipt_plan_binds_both_exact_source_files() -> None:
    legacy = assistant.plan_question("Why is the current Pakistan score here?")
    plan = cp.from_legacy_assistant_plan(legacy, compiled_at=FIXED_COMPILED)
    assert [row["source_registry_id"] for row in plan["source_bindings"]] == [
        "source:igrm.latest_payload",
        "source:igrm.receipts_payload",
    ]
    assert plan["steps"][0]["input_refs"] == [
        "binding:igrm.latest_json",
        "binding:igrm.receipts_json",
        "request:facts",
    ]


def test_plan_refuses_self_hash_and_literal_smuggling() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    broken = copy.deepcopy(plan)
    broken["request"]["fact_ids"][:2] = reversed(
        broken["request"]["fact_ids"][:2]
    )
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(broken)
    assert exc.value.code == "plan_integrity_mismatch"

    literal = copy.deepcopy(plan)
    literal["request"]["literal_value"] = 99.9
    _seal(literal)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(literal)
    assert exc.value.code == "plan_schema_refused"


def test_plan_loader_rejects_duplicate_keys_and_noncanonical_transport(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"object_type":"a","object_type":"b"}\n', encoding="utf-8")
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.load_plan(duplicate)
    assert exc.value.code == "json_duplicate_key"

    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.load_plan(noncanonical)
    assert exc.value.code == "plan_transport_noncanonical"

    canonical = tmp_path / "canonical.json"
    canonical.write_bytes(cp.serialize_plan(plan))
    assert cp.load_plan(canonical) == plan


def test_plan_refuses_graph_operator_and_planner_authority_mutations() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    graph = copy.deepcopy(plan)
    graph["steps"][0]["operator_id"] = "op:igrm.render_registered_template"
    _seal(graph)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(graph)
    assert exc.value.code == "plan_graph_invalid"

    model = copy.deepcopy(plan)
    model["planner"]["kind"] = "verified_model_selector"
    model["planner"]["candidate_only"] = False
    _seal(model)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(model)
    assert exc.value.code == "planner_unregistered"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("knowledge_cutoff", "2099-01-01T00:00:00Z"),
        ("valid_on", "2099-01-01"),
        ("object_type", "entity"),
        ("object_id", "entity:invented"),
        ("refusal_code", "unsupported_question"),
    ],
)
def test_legacy_profile_rejects_every_replay_or_refusal_field(
    field: str, value: str
) -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    plan["request"][field] = value
    plan["plan_id"] = cp._expected_plan_id(plan)
    plan = _seal(plan)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(plan)
    assert exc.value.code == "assistant_request_fields_invalid"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("knowledge_cutoff", "2099-01-01T00:00:00Z"),
        ("valid_on", "2099-01-01"),
        ("object_type", "entity"),
        ("object_id", "entity:invented"),
    ],
)
def test_registered_refusal_rejects_every_replay_field(
    field: str, value: str
) -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("forecast the market"), compiled_at=FIXED_COMPILED
    )
    plan["request"][field] = value
    plan["plan_id"] = cp._expected_plan_id(plan)
    plan = _seal(plan)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(plan)
    assert exc.value.code == "registered_refusal_request_fields_invalid"


def _payload_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    for relative in ("docs/data/latest.json", "docs/data/receipts.json"):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_execution_refuses_source_drift_after_compile(tmp_path: Path) -> None:
    root = _payload_root(tmp_path)
    legacy = assistant.plan_question("latest headline")
    plan = cp.from_legacy_assistant_plan(
        legacy, root, compiled_at=FIXED_COMPILED
    )
    latest = root / "docs/data/latest.json"
    latest.write_bytes(latest.read_bytes() + b" ")
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.execute_plan(plan, root, executed_at=FIXED_EXECUTED)
    assert exc.value.code == "source_bytes_drift"


def test_execution_compiles_mixed_source_dates_to_the_registered_refusal(
    tmp_path: Path,
) -> None:
    root = _payload_root(tmp_path)
    receipts_path = root / "docs/data/receipts.json"
    receipts = json.loads(receipts_path.read_text(encoding="utf-8"))
    receipts["date"] = "2026-08-06"
    _write_json(receipts_path, receipts)
    legacy = assistant.plan_question("Why is the current Pakistan score here?")
    plan = cp.from_legacy_assistant_plan(
        legacy, root, compiled_at=FIXED_COMPILED
    )
    execution = cp.execute_plan(plan, root, executed_at=FIXED_EXECUTED)
    expected = assistant.answer_plan(legacy, root).to_dict()
    assert expected["refusal_code"] == "evidence_date_mismatch"
    assert execution["result"]["output"] == expected
    assert execution["result"]["output_kind"] == "registered_refusal"
    assert execution["temporal"]["actual_source_as_of"] is None
    assert [proof["output_kind"] for proof in execution["step_proofs"]] == [
        "integrity_verified_payload_fact_set",
        "registered_refusal",
        "registered_refusal",
    ]


def test_fact_catalog_is_a_hash_bound_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog = json.loads(cp.FACT_CATALOG_PATH.read_text(encoding="utf-8"))
    catalog["fact_count"] -= 1
    path = tmp_path / "fact-catalog.json"
    _write_json(path, catalog)
    monkeypatch.setattr(cp, "FACT_CATALOG_PATH", path)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.from_legacy_assistant_plan(
            assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
        )
    assert exc.value.code == "fact_catalog_drift"


def test_profile_and_operator_bytes_are_not_self_attested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = json.loads(cp.PROFILE_PATH.read_text(encoding="utf-8"))
    profile["reference_implementation"]["sha256"] = "0" * 64
    path = tmp_path / "profile.json"
    _write_json(path, profile)
    monkeypatch.setattr(cp, "PROFILE_PATH", path)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.from_legacy_assistant_plan(
            assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
        )
    assert exc.value.code == "extension_profile_binding_invalid"


def test_signed_replay_adapter_is_exact_and_synthetic_only() -> None:
    fixture_root = ROOT / "validation/consequence_plan/replay_fixture"
    ledger = fixture_root / "knowledge/ledger.json"
    cutoff = "2026-08-09T12:30:00Z"
    plan = cp.from_knowledge_replay(
        "source:fixture.knowledge_replay_v1",
        cutoff,
        "2026-08-09",
        object_type="event",
        compiled_at=FIXED_COMPILED,
    )
    execution = cp.execute_plan(plan, executed_at=FIXED_EXECUTED)
    expected = knowledge_replay.replay(
        ledger,
        cutoff,
        "2026-08-09",
        object_type="event",
        root=fixture_root,
        replay_registry_path=fixture_root
        / "governance/knowledge_replay_registry.json",
        knowledge_signers_path=fixture_root
        / "governance/knowledge_replay_signers.json",
    )
    assert execution["result"]["output"] == expected
    assert execution["trust_class"] == "synthetic_nonproduction"
    assert execution["publication_eligible"] is False
    assert execution["temporal"]["knowledge_cutoff"] == cutoff
    assert execution["temporal"]["valid_on"] == "2026-08-09"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intent_id", "latest_headline"),
        ("fact_ids", ["latest.date"]),
        ("refusal_code", "unsupported_question"),
        ("knowledge_cutoff", None),
        ("valid_on", None),
    ],
)
def test_replay_profile_rejects_every_irrelevant_or_missing_field(
    field: str, value: object
) -> None:
    plan = cp.from_knowledge_replay(
        "source:fixture.knowledge_replay_v1",
        "2026-08-09T12:30:00Z",
        "2026-08-09",
        object_type="event",
        compiled_at=FIXED_COMPILED,
    )
    plan["request"][field] = value
    plan["plan_id"] = cp._expected_plan_id(plan)
    plan = _seal(plan)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(plan)
    assert exc.value.code == "replay_request_fields_invalid"


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".gitattributes"
    }


def test_committed_replay_fixture_is_byte_deterministic(tmp_path: Path) -> None:
    built = build_fixture(tmp_path / "fixture")
    committed = ROOT / "validation/consequence_plan/replay_fixture"
    assert _file_hashes(built.root) == _file_hashes(committed)


def test_replay_uses_the_once_captured_ledger_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    fixture_relative = Path("validation/consequence_plan/replay_fixture")
    shutil.copytree(ROOT / fixture_relative, root / fixture_relative)
    original = root / fixture_relative / "knowledge/ledger.json"
    expected_sha = hashlib.sha256(original.read_bytes()).hexdigest()
    plan = cp.from_knowledge_replay(
        "source:fixture.knowledge_replay_v1",
        "2026-08-09T12:30:00Z",
        "2026-08-09",
        object_type="event",
        compiled_at=FIXED_COMPILED,
        root=root,
    )
    real_replay = knowledge_replay.replay

    def raced_replay(ledger_path: Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        original.write_bytes(b"{}\n")
        assert ledger_path != original
        assert hashlib.sha256(ledger_path.read_bytes()).hexdigest() == expected_sha
        return real_replay(ledger_path, *args, **kwargs)

    monkeypatch.setattr(cp.knowledge_replay, "replay", raced_replay)
    execution = cp.execute_plan(plan, root, executed_at=FIXED_EXECUTED)
    assert execution["inputs"][0]["file_sha256"] == expected_sha
    assert execution["result"]["output"]["ledger"]["file_sha256"] == expected_sha


def test_pinned_replay_source_cannot_be_substituted_by_a_resealed_plan() -> None:
    plan = cp.from_knowledge_replay(
        "source:fixture.knowledge_replay_v1",
        "2026-08-09T12:30:00Z",
        "2026-08-09",
        object_type="event",
        compiled_at=FIXED_COMPILED,
    )
    substituted = copy.deepcopy(plan)
    substituted["source_bindings"][0]["expected_file_sha256"] = "1" * 64
    substituted["plan_id"] = cp._expected_plan_id(substituted)
    substituted = _seal(substituted)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(substituted)
    assert exc.value.code == "registered_source_file_drift"


def test_plan_id_is_recomputed_from_source_binding_semantics() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    substituted = copy.deepcopy(plan)
    substituted["source_bindings"][0]["expected_file_sha256"] = "1" * 64
    substituted = _seal(substituted)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_plan(substituted)
    assert exc.value.code == "plan_identity_mismatch"


def test_profile_refuses_an_unpinned_runtime_source_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copied = tmp_path / "source-registry.json"
    shutil.copy2(cp.SOURCE_REGISTRY_PATH, copied)
    monkeypatch.setattr(cp, "SOURCE_REGISTRY_PATH", copied)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.from_legacy_assistant_plan(
            assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
        )
    assert exc.value.code == "active_source_registry_unpinned"


def test_plan_transport_digest_binds_exact_serialized_bytes() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    execution = cp.execute_plan(plan, executed_at=FIXED_EXECUTED)
    assert execution["plan_binding"]["plan_file_sha256"] == hashlib.sha256(
        cp.serialize_plan(plan)
    ).hexdigest()
    assert execution["plan_binding"]["plan_integrity_sha256"] == plan["integrity"][
        "value_sha256"
    ]
    cp.validate_execution(execution, plan)


def test_resealed_mutated_execution_does_not_verify() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    execution = cp.execute_plan(plan, executed_at=FIXED_EXECUTED)
    execution["result"]["output"]["text"] = "Invented but resealed."
    execution = cp._seal(execution)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_execution(execution, plan)
    assert exc.value.code == "execution_recompile_mismatch"


def test_invalid_plan_returns_a_value_free_engine_refusal() -> None:
    plan = cp.from_legacy_assistant_plan(
        assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
    )
    plan["request"]["literal_value"] = 99.9
    plan = cp._seal(plan)
    execution = cp.execute_or_refuse(plan, executed_at=FIXED_EXECUTED)
    assert execution["execution_status"] == "refused"
    assert execution["result"] is None
    assert execution["inputs"] == []
    assert execution["step_proofs"] == []
    assert execution["refusal"] == {
        "stage": "plan",
        "code": "plan_schema_refused",
    }
    assert set(execution) == {
        "object_type", "schema_version", "integrity", "plan_binding",
        "contract", "engine", "inputs", "step_proofs", "temporal",
        "universe", "trust_class", "publication_eligible",
        "execution_status", "result", "refusal", "limitations",
    }
    cp.validate_execution(execution, plan)

    mutation = copy.deepcopy(execution)
    mutation["refusal"]["code"] = "operator_unregistered"
    mutation = cp._seal(mutation)
    with pytest.raises(cp.ConsequencePlanError) as exc:
        cp.validate_execution(mutation, plan)
    assert exc.value.code == "execution_recompile_mismatch"


def test_step_proofs_obey_the_executable_operator_type_registry() -> None:
    plans = [
        cp.from_legacy_assistant_plan(
            assistant.plan_question("latest headline"), compiled_at=FIXED_COMPILED
        ),
        cp.from_legacy_assistant_plan(
            assistant.plan_question("forecast the market"),
            compiled_at=FIXED_COMPILED,
        ),
        cp.from_knowledge_replay(
            "source:fixture.knowledge_replay_v1",
            "2026-08-09T12:30:00Z",
            "2026-08-09",
            object_type="event",
            compiled_at=FIXED_COMPILED,
        ),
    ]
    operators = cp._operator_rows()
    outputs = cp._output_rows()
    for plan in plans:
        execution = cp.execute_plan(plan, executed_at=FIXED_EXECUTED)
        for proof in execution["step_proofs"]:
            row = operators[proof["operator_id"]]
            assert proof["input_kinds"] in row["input_kind_sequences"]
            assert proof["output_kind"] in row["output_kinds"]
        assert execution["result"]["output_kind"] in outputs[
            plan["output_profile_id"]
        ]["output_kinds"]


def test_no_consequence_or_decision_language_is_licensed() -> None:
    spec = (cp.EXTENSION / "SPEC.md").read_text(encoding="utf-8").lower()
    profile = json.loads(cp.PROFILE_PATH.read_text(encoding="utf-8"))
    assert profile["production_endpoint"] is False
    for claim in (
        "does **not**\nprove that an input is true",
        "compute a geopolitical consequence",
        "causality or completeness",
        "forecast, probability, recommendation",
    ):
        assert claim in spec
