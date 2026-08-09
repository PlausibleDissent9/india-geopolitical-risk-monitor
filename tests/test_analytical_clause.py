"""The short view and the long view must be the same claim.

Slice 1 of the Product Compiler, built to the design returned in
`analysis/product_compiler_overlap_audit.md`: the cross-role invariant first,
alone, before any renderer exists. The invariant is the product; the seven
audience views are delivery.

Of the eleven attacks in the assignment, these are the four the invariant
actually decides. The other seven belong to engines that already exist and
are asserted there, not reimplemented here:

    clause mutation in one role      -> test_a_role_may_not_change_what_a_clause_says
    hidden omitted limitation        -> test_a_short_view_may_not_drop_a_limitation
    output-profile drift             -> test_a_role_may_not_invent_a_clause
    resealed output whose clause
      proof no longer recompiles     -> test_resealing_a_mutated_clause_does_not_rescue_it
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from src import analytical_clause as ac

CONTRACT, CONTRACT_SHA = ac.load_contract()


def _clause(clause_id: str, kind: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "object_type": "analytical_clause",
        "schema_version": "0.1.0",
        "clause_id": clause_id,
        "record_sha256": "0" * 64,
        "kind": kind,
        "value": 61.5,
        "unit": "percentile_of_trailing_730_days",
        "denominator": "one completed UTC news day",
        "observed_period": "2026-08-08",
        "epistemic_type": "measured",
        "uncertainty": {"lower": 58.0, "upper": 64.9},
        "missingness": "present",
        "citation": "https://igrm.in/data/latest.json",
        "proof_binding": "sha256:" + "0" * 64,
        "rights_state": "cite_metadata",
    }
    base.update(over)
    return ac.seal_clause(base)


def _set() -> list[dict[str, Any]]:
    return [
        _clause("clause:composite7", "measurement"),
        _clause("clause:china_east", "measurement", value=26.4),
        _clause(
            "clause:not_causation",
            "limitation",
            value=None,
            missingness="not_applicable",
            epistemic_type="registered_refusal",
            uncertainty=None,
        ),
        _clause(
            "clause:rights",
            "rights",
            value=None,
            missingness="not_applicable",
            epistemic_type="registered_refusal",
            uncertainty=None,
        ),
        _clause(
            "clause:provenance",
            "provenance",
            value=None,
            missingness="not_applicable",
            epistemic_type="registered_refusal",
            uncertainty=None,
        ),
    ]


def _view(clauses: list[dict[str, Any]], length: str = "full") -> list[dict[str, Any]]:
    del length
    return [
        {
            "clause_id": clause["clause_id"],
            "clause_record_sha256": clause["record_sha256"],
        }
        for clause in clauses
    ]


def _refuses(code: str):
    return pytest.raises(ac.AnalyticalClauseError, match=f"^{code}$")


# --- the contract itself -------------------------------------------------


def test_the_contract_is_registered_and_hashable() -> None:
    assert CONTRACT["contract_id"] == "igrm:analytical-clause:0.1.0"
    assert len(CONTRACT_SHA) == 64
    assert CONTRACT["status"] == "synthetic_contract_only"
    assert CONTRACT["public_routes"] == [], (
        "slice 1 must not publish a route; the assignment says contract-only"
    )


def test_every_refusal_code_the_module_can_raise_is_registered() -> None:
    """A refusal the contract does not list is an unregistered behaviour."""
    source = (ac.ROOT / "src" / "analytical_clause.py").read_text(encoding="utf-8")
    raised = set()
    for line in source.splitlines():
        if '_fail("' in line:
            raised.add(line.split('_fail("', 1)[1].split('"', 1)[0])
    unregistered = sorted(raised - set(CONTRACT["refusal_codes"]))
    assert not unregistered, f"refusal codes missing from the contract: {unregistered}"


# --- the invariant -------------------------------------------------------


def test_roles_carrying_different_subsets_agree_on_what_they_share() -> None:
    clauses = _set()
    research = ac.validate_role_view("research", _view(clauses), clauses, CONTRACT)
    # A board sees the headline and every mandatory clause, and nothing else.
    board_clauses = [c for c in clauses if c["clause_id"] != "clause:china_east"]
    board = ac.validate_role_view("board", _view(board_clauses), clauses, CONTRACT)

    result = ac.cross_role_invariant({"research": research, "board": board})
    assert result["omitted_by_role"]["board"] == ["clause:china_east"]
    assert result["omitted_by_role"]["research"] == []
    assert len(result["shared_clause_digest_sha256"]) == 64


def test_roles_carry_exact_refs_not_rendering_payloads() -> None:
    """The role surface is an exact record reference, never copied prose."""
    clauses = _set()
    assert all(set(ref) == {"clause_id", "clause_record_sha256"} for ref in _view(clauses))
    full = ac.validate_role_view("research", _view(clauses), clauses, CONTRACT)
    short = ac.validate_role_view("newsroom", _view(clauses), clauses, CONTRACT)
    assert full == short
    ac.cross_role_invariant({"research": full, "newsroom": short})


# --- attack 1: clause mutation in one role -------------------------------


@pytest.mark.parametrize(
    "field,mutated",
    [
        ("value", 99.9),
        ("unit", "index_points"),
        ("denominator", "one calendar week"),
        ("observed_period", "2026-08-09"),
        ("epistemic_type", "derived"),
        ("uncertainty", None),
        ("citation", "https://example.invalid/other.json"),
        ("rights_state", "redistribute_full_record"),
        ("proof_binding", "sha256:" + "1" * 64),
    ],
)
def test_a_role_may_not_change_what_a_clause_says(field: str, mutated: Any) -> None:
    clauses = _set()
    view = _view(clauses)
    mutated_clauses = copy.deepcopy(clauses)
    target = next(c for c in mutated_clauses if c["clause_id"] == "clause:composite7")
    target[field] = mutated
    mutated_clauses[0] = ac.seal_clause(target)
    with _refuses("clause_protected_field_divergence"):
        ac.validate_role_view("newsroom", view, mutated_clauses, CONTRACT)


# --- attack 2: hidden omitted limitation ---------------------------------


@pytest.mark.parametrize("dropped", ["clause:not_causation", "clause:rights", "clause:provenance"])
def test_a_short_view_may_not_drop_a_limitation(dropped: str) -> None:
    """The failure this contract exists to prevent: keep the number, lose
    what the number cannot support."""
    clauses = _set()
    view = [c for c in _view(clauses) if c["clause_id"] != dropped]
    with _refuses("clause_mandatory_omitted"):
        ac.validate_role_view("public", view, clauses, CONTRACT)


def test_a_measurement_may_be_omitted_because_that_is_the_permitted_difference() -> None:
    clauses = _set()
    view = [c for c in _view(clauses) if c["clause_id"] != "clause:china_east"]
    seen = ac.validate_role_view("board", view, clauses, CONTRACT)
    assert "clause:china_east" not in seen


# --- attack 3: output-profile drift --------------------------------------


def test_a_role_may_not_invent_a_clause() -> None:
    clauses = _set()
    view = _view(clauses)
    invented = _clause("clause:invented", "measurement", value=1.0)
    view.append(
        {
            "clause_id": invented["clause_id"],
            "clause_record_sha256": invented["record_sha256"],
        }
    )
    with _refuses("clause_unknown_id_in_role"):
        ac.validate_role_view("api", view, clauses, CONTRACT)


def test_an_unregistered_role_is_refused() -> None:
    clauses = _set()
    with _refuses("clause_role_unregistered"):
        ac.validate_role_view("marketing", _view(clauses), clauses, CONTRACT)


# --- attack 4: resealed output whose clause proof no longer recompiles ----


def test_resealing_a_mutated_clause_does_not_rescue_it() -> None:
    """Recomputing the digest over the mutation is what an attacker does
    next. The comparison is against the COMPILED set, not against whatever
    the role recomputed for itself, so a consistent forgery still refuses."""
    clauses = _set()
    view = _view(clauses)
    target = next(c for c in clauses if c["clause_id"] == "clause:composite7")
    target["value"] = 99.9
    clauses[0] = ac.seal_clause(target)
    with _refuses("clause_protected_field_divergence"):
        ac.validate_role_view("research", view, clauses, CONTRACT)


def test_two_roles_that_agree_with_each_other_but_not_the_source_refuse() -> None:
    """A coordinated forgery across every role is still not the compiled
    claim. Cross-role agreement alone must never be the acceptance test."""
    clauses = _set()
    original_view = _view(clauses)
    for _ in range(2):
        mutated = copy.deepcopy(clauses)
        target = next(c for c in mutated if c["clause_id"] == "clause:composite7")
        target["value"] = 42.0
        mutated[0] = ac.seal_clause(target)
        role = ("research", "board")[_]
        with _refuses("clause_protected_field_divergence"):
            ac.validate_role_view(role, original_view, mutated, CONTRACT)


# --- structural refusals -------------------------------------------------


def test_a_zero_may_not_stand_in_for_an_absence() -> None:
    clauses = _set()
    clauses[0]["missingness"] = "source_blank"
    with _refuses("clause_value_present_despite_missingness"):
        ac.compile_clauses(clauses, CONTRACT)


def test_a_present_value_may_not_be_null() -> None:
    clauses = _set()
    clauses[0]["value"] = None
    with _refuses("clause_value_absent_despite_presence"):
        ac.compile_clauses(clauses, CONTRACT)


def test_a_missing_protected_field_is_refused_not_defaulted() -> None:
    clauses = _set()
    del clauses[0]["denominator"]
    with _refuses("clause_structure_invalid"):
        ac.compile_clauses(clauses, CONTRACT)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("kind", "editorial", "clause_kind_unregistered"),
        ("epistemic_type", "estimated", "clause_epistemic_type_unregistered"),
        ("missingness", "unknown", "clause_missingness_unregistered"),
    ],
)
def test_unregistered_vocabulary_is_refused(field: str, value: str, code: str) -> None:
    clauses = _set()
    clauses[0][field] = value
    with _refuses(code):
        ac.compile_clauses(clauses, CONTRACT)


def test_duplicate_clause_ids_are_refused() -> None:
    clauses = _set()
    clauses.append(_clause("clause:composite7", "measurement", value=1.0))
    with _refuses("clause_duplicate_id"):
        ac.compile_clauses(clauses, CONTRACT)


def test_role_specific_rendering_payload_is_refused() -> None:
    clauses = _set()
    view = _view(clauses)
    view[0]["rendering_length"] = "teaser"
    with _refuses("clause_ref_invalid"):
        ac.validate_role_view("newsroom", view, clauses, CONTRACT)


# --- the honest limit ----------------------------------------------------


def test_the_contract_states_that_agreement_is_not_accuracy() -> None:
    """If this module is ever cited, it must be cited for what it proves.
    Consistency across seven views of a wrong number is seven wrong views."""
    assert "cross_role_agreement_is_not_accuracy" in CONTRACT["limitations"]
    assert "synthetic_contract_only_no_production_claim" in CONTRACT["limitations"]
    assert "protected_fields" not in CONTRACT
