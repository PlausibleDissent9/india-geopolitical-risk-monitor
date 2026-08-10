from __future__ import annotations

import ast
import hashlib
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from src import live_query_admission as lq

ROOT = Path(__file__).resolve().parents[1]


def _fixed() -> lq._FixedInputs:
    return lq._capture_fixed_inputs()


def _binding(**kwargs: str) -> dict[str, Any]:
    return lq.make_binding(**kwargs)


def _reseal_template(template: dict[str, Any]) -> None:
    template["record_sha256"] = lq._typed_record_sha(template)


def _reseal_domain(domain: dict[str, Any]) -> None:
    domain["record_sha256"] = lq._typed_record_sha(domain)


def _with_docs(
    fixed: lq._FixedInputs,
    *,
    profile: dict[str, Any] | None = None,
    domains: dict[str, Any] | None = None,
    templates: dict[str, Any] | None = None,
) -> lq._FixedInputs:
    return replace(
        fixed,
        profile=profile or deepcopy(fixed.profile),
        domain_registry=domains or deepcopy(fixed.domain_registry),
        template_registry=templates or deepcopy(fixed.template_registry),
    )


def _case(case_id: str, fixed: lq._FixedInputs) -> dict[str, Any]:
    binding = _binding()
    if case_id == "valid_complete_universe":
        return lq._admit_captured(binding, fixed)
    if case_id == "argument_order_normalized":
        binding["arguments"] = list(reversed(binding["arguments"]))
        return lq._admit_captured(binding, fixed)
    if case_id == "rights_refusal_keeps_denominator":
        binding = _binding(
            country="member:country.beta",
            commodity="member:commodity.metal",
            period="member:period.two",
        )
        return lq._admit_captured(binding, fixed)
    if case_id == "template_unregistered":
        binding["template_id"] = "template:unregistered"
    elif case_id == "template_digest_drift":
        binding["template_record_sha256"] = "0" * 64
    elif case_id == "parameter_unregistered":
        binding["arguments"][0]["parameter_id"] = "parameter:selector"
    elif case_id == "required_parameter_missing":
        binding["arguments"].pop()
    elif case_id == "duplicate_parameter":
        binding["arguments"].append(deepcopy(binding["arguments"][0]))
    elif case_id == "domain_unregistered":
        binding["arguments"][0]["domain_id"] = "domain:unregistered"
    elif case_id == "domain_digest_drift":
        domains = deepcopy(fixed.domain_registry)
        domains["domains"][0]["members"].append({"member_id": "member:country.gamma"})
        _reseal_domain(domains["domains"][0])
        fixed = _with_docs(fixed, domains=domains)
    elif case_id == "member_unregistered":
        binding["arguments"][0]["member_id"] = "member:country.gamma"
    elif case_id == "selector_text":
        binding["arguments"][0]["member_id"] = "member:country.*"
    elif case_id == "universe_bound_exceeded":
        templates = deepcopy(fixed.template_registry)
        templates["templates"][0]["bounds"]["max_universe_size"] = 7
        _reseal_template(templates["templates"][0])
        fixed = _with_docs(fixed, templates=templates)
        binding["template_record_sha256"] = templates["templates"][0]["record_sha256"]
    elif case_id == "aggregation_drift":
        templates = deepcopy(fixed.template_registry)
        templates["registered_aggregations"] = ["aggregation:none", "aggregation:mean"]
        templates["templates"][0]["aggregation"] = "aggregation:mean"
        _reseal_template(templates["templates"][0])
        fixed = _with_docs(fixed, templates=templates)
    elif case_id == "source_release_unregistered":
        templates = deepcopy(fixed.template_registry)
        templates["templates"][0]["source_release_ref"]["release_id"] = "release:unknown"
        _reseal_template(templates["templates"][0])
        fixed = _with_docs(fixed, templates=templates)
    elif case_id == "source_release_refused":
        profile = deepcopy(fixed.profile)
        release = profile["source_releases"][0]
        release["status"] = "refused"
        release["record_sha256"] = lq._typed_sha(
            {
                "release_id": release["release_id"],
                "status": release["status"],
                "source_execution_performed": False,
            }
        )
        templates = deepcopy(fixed.template_registry)
        templates["templates"][0]["source_release_ref"]["record_sha256"] = release[
            "record_sha256"
        ]
        _reseal_template(templates["templates"][0])
        fixed = _with_docs(fixed, profile=profile, templates=templates)
    elif case_id == "contract_drift":
        contract = deepcopy(fixed.contract)
        contract["public_routes"] = ["/forbidden"]
        lq._validate_contract(contract)
        raise AssertionError("contract drift accepted")
    elif case_id == "profile_drift":
        raw_sha256 = dict(fixed.raw_sha256)
        raw_sha256["contract"] = "0" * 64
        changed = replace(fixed, raw_sha256=raw_sha256)
        lq._validate_profile(changed.profile, changed)
        raise AssertionError("profile drift accepted")
    elif case_id == "profile_invalid":
        profile = deepcopy(fixed.profile)
        profile["trust_boundary"]["public_authority"] = True
        lq._validate_profile(profile, fixed)
        raise AssertionError("invalid profile accepted")
    elif case_id == "domain_registry_invalid":
        domains = deepcopy(fixed.domain_registry)
        domains["domains"].append(deepcopy(domains["domains"][0]))
        lq._validate_domain_registry(domains)
        raise AssertionError("invalid domain registry accepted")
    elif case_id == "template_registry_invalid":
        templates = deepcopy(fixed.template_registry)
        templates["templates"][0]["projection"] = ["caller.value"]
        _reseal_template(templates["templates"][0])
        lq._validate_template_registry(
            templates,
            lq._validate_domain_registry(fixed.domain_registry),
            fixed.profile,
        )
        raise AssertionError("invalid template registry accepted")
    elif case_id == "vector_registry_invalid":
        vectors = deepcopy(fixed.vectors)
        vectors["cases"].append(deepcopy(vectors["cases"][0]))
        lq._validate_vectors(vectors)
        raise AssertionError("invalid vector registry accepted")
    elif case_id == "structure_invalid":
        binding["unexpected"] = "value"
    elif case_id == "typed_canonical_invalid":
        lq._typed_sha(float("nan"))
        raise AssertionError("noncanonical float accepted")
    elif case_id == "universe_not_recomputable":
        domains = deepcopy(fixed.domain_registry)
        domains["domains"][0]["members"] = []
        _reseal_domain(domains["domains"][0])
        fixed = _with_docs(fixed, domains=domains)
    elif case_id == "duplicate_json_key":
        lq._parse_json(
            b'{"schema_version":"0.1.0","schema_version":"9.9.9"}',
            "admission_structure_invalid",
        )
        raise AssertionError("duplicate JSON key accepted")
    elif case_id == "receipt_digest_invalid":
        receipt = lq._admit_captured(binding, fixed)
        receipt["requested_index"] = 1
        return lq.verify_admission(binding, receipt)
    elif case_id == "receipt_mutation":
        receipt = lq._admit_captured(binding, fixed)
        receipt["requested_index"] = 1
        receipt = lq._seal(receipt)
        return lq.verify_admission(binding, receipt)
    elif case_id == "invalid_requested_time":
        binding["requested_at"] = "2026-08-10"
    else:
        raise AssertionError(case_id)
    return lq._admit_captured(binding, fixed)


def test_fixed_governance_is_closed_pinned_and_nonpublic() -> None:
    fixed = _fixed()
    assert fixed.contract["status"] == "synthetic_contract_only"
    assert fixed.contract["public_routes"] == []
    assert fixed.contract["trust_boundary"] == {
        "signed": False,
        "authenticated": False,
        "synthetic": True,
        "contract_only": True,
        "source_execution_performed": False,
        "production_authority": False,
        "public_authority": False,
        "requested_at_semantics": "caller_declared_unauthenticated",
        "record_sha256_is_authentication": False,
    }
    assert "visible, not impossible" in fixed.contract["claim_boundary"]
    profile_sha = hashlib.sha256(lq.PROFILE_PATH.read_bytes()).hexdigest()
    assert profile_sha == lq._PROFILE_SHA256
    rows = {row["kind"]: row for row in fixed.profile["normative_files"]}
    for kind, relative in lq._NORMATIVE_PATHS.items():
        path = ROOT / relative
        assert rows[kind]["path"] == relative
        assert rows[kind]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    for public_runtime in ("src/api.py", "src/evidence_outputs.py", "src/web.py"):
        path = ROOT / public_runtime
        if path.exists():
            assert "live_query_admission" not in path.read_text(encoding="utf-8")


def test_every_runtime_refusal_is_registered() -> None:
    tree = ast.parse((ROOT / "src/live_query_admission.py").read_text(encoding="utf-8"))
    raised: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else ""
        if name not in {"_fail", "LiveQueryAdmissionError"}:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            raised.add(first.value)
    registered = set(_fixed().contract["active_refusal_codes"])
    assert not (raised - registered), sorted(raised - registered)


def test_valid_admission_materializes_the_complete_question_denominator() -> None:
    binding = _binding()
    receipt = lq.admit(binding)
    assert receipt["universe_size"] == 8
    assert len(receipt["binding_universe"]) == 8
    assert len(receipt["rights_state_per_binding"]) == 8
    assert receipt["requested_index"] == 0
    assert receipt["universe_truncated"] is False
    assert receipt["admitted"] is True
    assert receipt["refusal_code"] is None
    assert receipt["trust_boundary"]["source_execution_performed"] is False
    assert lq._typed_sha(receipt["binding_universe"]) == receipt["universe_digest_sha256"]
    assert lq.verify_admission(binding, receipt)["status"] == "valid"


def test_ordering_and_transport_are_byte_deterministic() -> None:
    normal = _binding()
    reversed_binding = deepcopy(normal)
    reversed_binding["arguments"] = list(reversed(reversed_binding["arguments"]))
    first = lq.admit(normal)
    second = lq.admit(normal)
    reordered = lq.admit(reversed_binding)
    assert lq.serialize_record(first) == lq.serialize_record(second)
    assert lq.serialize_record(first) == lq.serialize_record(reordered)
    assert [row["arguments"][0]["member_id"] for row in first["binding_universe"]] == [
        "member:country.alpha",
        "member:country.alpha",
        "member:country.alpha",
        "member:country.alpha",
        "member:country.beta",
        "member:country.beta",
        "member:country.beta",
        "member:country.beta",
    ]


def test_caller_declared_time_is_not_authenticated_and_cannot_collide_ids() -> None:
    first = lq.admit(_binding(requested_at="2026-08-10T00:00:00Z"))
    later = lq.admit(_binding(requested_at="2026-08-10T00:00:01Z"))
    assert first["trust_boundary"]["requested_at_semantics"] == "caller_declared_unauthenticated"
    assert first["admission_id"] != later["admission_id"]
    assert first["record_sha256"] != later["record_sha256"]


def test_rights_refusal_changes_answerability_not_the_universe() -> None:
    binding = _binding(
        country="member:country.beta",
        commodity="member:commodity.metal",
        period="member:period.two",
    )
    receipt = lq.admit(binding)
    assert receipt["universe_size"] == 8
    assert receipt["requested_index"] == 7
    assert receipt["rights_state_per_binding"][7]["state"] == "refused_rights"
    assert receipt["admitted"] is False
    assert receipt["refusal_code"] == "admission_binding_rights_ineligible"
    assert lq.verify_admission(binding, receipt)["status"] == "valid"


@pytest.mark.parametrize(
    "selector",
    ["*", "member:country.*", "SELECT country", "filter:alpha", "regex:.*", "a=b"],
)
def test_selector_shaped_member_values_refuse(selector: str) -> None:
    binding = _binding()
    binding["arguments"][0]["member_id"] = selector
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_selector_text_supplied$"):
        lq.admit(binding)


@pytest.mark.parametrize(
    "field",
    ["filter", "projection", "bounds", "domain_restriction", "relation", "universe"],
)
def test_caller_semantic_fields_get_the_explicit_selector_refusal(field: str) -> None:
    binding = _binding()
    binding[field] = "caller-authored"
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_selector_text_supplied$"):
        lq.admit(binding)


def test_domain_digest_is_a_caller_pin_not_a_current_state_claim() -> None:
    fixed = _fixed()
    binding = _binding()
    domains = deepcopy(fixed.domain_registry)
    domains["domains"][0]["members"].append({"member_id": "member:country.gamma"})
    _reseal_domain(domains["domains"][0])
    changed = _with_docs(fixed, domains=domains)
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_domain_digest_mismatch$"):
        lq._admit_captured(binding, changed)


def test_receipt_self_hash_is_integrity_only_and_recompile_is_authority() -> None:
    binding = _binding()
    receipt = lq.admit(binding)
    receipt["requested_index"] = 1
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_receipt_digest_mismatch$"):
        lq.verify_admission(binding, receipt)
    resealed = lq._seal(receipt)
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_receipt_recompile_mismatch$"):
        lq.verify_admission(binding, resealed)


def test_duplicate_json_keys_refuse_before_document_use() -> None:
    raw = b'{"schema_version":"0.1.0","schema_version":"9.9.9"}'
    with pytest.raises(lq.LiveQueryAdmissionError, match="^admission_json_duplicate_key$"):
        lq._parse_json(raw, "admission_structure_invalid")


def test_every_normative_adversarial_case_executes() -> None:
    fixed = _fixed()
    vectors = fixed.vectors
    executed: set[str] = set()
    for row in vectors["cases"]:
        case_id = row["case_id"]
        if row["expected_status"] == "valid":
            receipt = _case(case_id, fixed)
            assert receipt["object_type"] == "live_query_admission"
        elif case_id == "rights_refusal_keeps_denominator":
            receipt = _case(case_id, fixed)
            assert receipt["refusal_code"] == row["expected_reason"]
            assert receipt["universe_size"] == 8
        else:
            with pytest.raises(lq.LiveQueryAdmissionError) as exc:
                _case(case_id, fixed)
            assert exc.value.code == row["expected_reason"], case_id
        executed.add(case_id)
    assert executed == {row["case_id"] for row in vectors["cases"]}
    assert len(executed) == 29
    expected_reasons = {
        row["expected_reason"] for row in vectors["cases"] if row["expected_status"] == "refused"
    }
    assert expected_reasons == set(fixed.contract["active_refusal_codes"])
