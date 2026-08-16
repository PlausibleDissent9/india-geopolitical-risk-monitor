"""Fail-closed locks for the pilot instance ledger.

The federation domain is worth 3 points and is the easiest place in the
whole project to lie to yourself: a demo feels like adoption, a warm
conversation feels like authority, and an artifact that was generated
feels like an artifact that was used. These tests make each of those
impossible to record by accident.

The rule they encode: Claude may prepare everything except the human act.
An instance becomes real when a named user at a real institution did a
registered task -- and that fact arrives from the institution, never from
us.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "governance/pilots/instances.json"

SUCCESSFUL = {"user_acted", "outcome_recorded"}


@pytest.fixture(scope="module")
def ledger() -> dict[str, Any]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def test_no_instance_claims_success_without_a_confirmed_named_user(
    ledger: dict[str, Any],
) -> None:
    for inst in ledger["instances"]:
        if inst.get("outcome_status") in SUCCESSFUL:
            assert inst.get("named_user_confirmed") is True, (
                f"{inst.get('instance_id')} claims a successful outcome without "
                "a confirmed named user; a generated artifact is not a use"
            )
            assert inst.get("decision_owner"), "a use with no decision owner is a demo"


def test_an_institution_without_authority_evidence_has_no_instances(
    ledger: dict[str, Any],
) -> None:
    # Testimony that a director approved something is not evidence that a
    # director approved something. Until the document exists, the
    # institution cannot carry recorded instances.
    holds_evidence = {
        i["institution_id"]
        for i in ledger["institutions"]
        if not str(i.get("authority_evidence", "")).startswith("NOT YET HELD")
    }
    for inst in ledger["instances"]:
        assert inst.get("institution") in holds_evidence, (
            f"{inst.get('instance_id')} is recorded against an institution whose "
            "authority is still testimony"
        )


def test_recorded_counts_match_the_instance_list(ledger: dict[str, Any]) -> None:
    actual: dict[str, int] = {}
    for inst in ledger["instances"]:
        actual[inst.get("institution")] = actual.get(inst.get("institution"), 0) + 1
    for institution in ledger["institutions"]:
        claimed = institution["instances_recorded"]
        assert claimed == actual.get(institution["institution_id"], 0), (
            f"{institution['institution_id']} claims {claimed} instances; the list "
            f"holds {actual.get(institution['institution_id'], 0)}"
        )


def test_every_instance_carries_every_required_field(ledger: dict[str, Any]) -> None:
    required = set(ledger["required_fields"])
    for inst in ledger["instances"]:
        missing = required - set(inst)
        assert not missing, f"{inst.get('instance_id')} missing {sorted(missing)}"


def test_declared_states_are_the_only_states_used(ledger: dict[str, Any]) -> None:
    allowed = set(ledger["instance_states"])
    for inst in ledger["instances"]:
        assert inst.get("outcome_status") in allowed, (
            f"{inst.get('instance_id')} uses an undeclared state "
            f"{inst.get('outcome_status')!r}"
        )


def test_failures_are_retained_not_pruned(ledger: dict[str, Any]) -> None:
    # The counting rules promise failed, refused, null and abandoned
    # instances stay in the denominator. If the list is ever all-success
    # once it is non-trivial, something is being dropped.
    instances = ledger["instances"]
    if len(instances) >= 4:
        assert any(
            i.get("outcome_status") in {"refused", "failed", "null_outcome", "abandoned"}
            for i in instances
        ), (
            "four or more instances and not one failure, refusal, null or "
            "abandonment -- verify none were pruned before trusting this"
        )


def test_the_counting_rules_survive_in_the_ledger(ledger: dict[str, Any]) -> None:
    # These rules are the whole defence against inflated adoption. Deleting
    # one should break the build, not pass quietly.
    text = " ".join(ledger["counting_rules"]).lower()
    for phrase in ("never instances", "denominator", "one adoption"):
        assert phrase in text, f"counting rule mentioning {phrase!r} was removed"


def test_target_is_not_quietly_reduced(ledger: dict[str, Any]) -> None:
    assert ledger["target"]["instances"] == 6
    assert ledger["target"]["institutions"] == 2
    assert ledger["target"]["points_available"] == 3
