"""Fail-closed locks for the VMax execution ledger.

The ledger's whole purpose is to stop optimistic self-scoring, so the
attacks worth writing are the ones where the ledger flatters us: an
entry that awards itself points without an external acceptance record, a
score summary that disagrees with the entries beneath it, an evidence
state invented outside the declared vocabulary, or a decision packet
that asks the founder for time without saying what it buys.

These tests read the committed ledger. They are not fixtures of a
hypothetical ledger: a real entry that drifts must fail here.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "governance/vmax_execution_ledger.json"

SHA_FIELDS = ("parent_sha", "candidate_sha", "tree_sha")


@pytest.fixture(scope="module")
def ledger() -> dict[str, Any]:
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def _entries(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    entries = ledger["entries"]
    assert isinstance(entries, list) and entries
    return entries


def test_only_externally_accepted_evidence_may_carry_admissible_points(
    ledger: dict[str, Any],
) -> None:
    for entry in _entries(ledger):
        admissible = entry.get("admissible_points", 0)
        assert isinstance(admissible, int)
        if entry.get("evidence_state") != "accepted":
            assert admissible == 0, (
                f"{entry['entry_id']} claims {admissible} admissible points in "
                f"state {entry.get('evidence_state')!r}; only 'accepted' may score"
            )


def test_summary_total_equals_the_sum_of_its_entries(ledger: dict[str, Any]) -> None:
    claimed = ledger["scoring_position"]["admissible_points_recorded_in_this_ledger"]
    assert claimed == sum(e.get("admissible_points", 0) for e in _entries(ledger)), (
        "the headline admissible total must be the arithmetic sum of the "
        "entries, not a separately maintained number"
    )


def test_every_evidence_state_is_from_the_declared_vocabulary(
    ledger: dict[str, Any],
) -> None:
    allowed = set(ledger["evidence_states"])
    for entry in _entries(ledger):
        state = entry.get("evidence_state")
        assert state in allowed, f"{entry['entry_id']}: undeclared state {state!r}"


def test_shas_are_full_forty_hex_digits(ledger: dict[str, Any]) -> None:
    # An abbreviated sha in a ledger entry is ambiguous forever. Run and job
    # ids stay strings, but anything named *_sha must be exact.
    for entry in _entries(ledger):
        for field in SHA_FIELDS:
            value = entry.get(field)
            if value is None:
                continue
            assert len(value) == 40 and all(
                c in "0123456789abcdef" for c in value
            ), f"{entry['entry_id']}.{field} is not a full sha: {value!r}"


def test_entries_that_claim_a_candidate_declare_clean_status_and_paths(
    ledger: dict[str, Any],
) -> None:
    for entry in _entries(ledger):
        if "candidate_sha" not in entry:
            continue
        assert isinstance(entry.get("clean"), bool), (
            f"{entry['entry_id']}: a candidate without a clean/dirty verdict "
            "cannot be reproduced"
        )
        assert "paths_changed" in entry or "paths_changed_count" in entry


def test_decision_packets_state_the_cost_and_the_no_response_path(
    ledger: dict[str, Any],
) -> None:
    for packet in ledger.get("founder_decision_packets", []):
        assert packet.get("exact_question", "").endswith("?")
        assert packet.get("recommended_option")
        assert isinstance(packet.get("estimated_founder_minutes"), int)
        assert packet.get("what_continues_without_a_response"), (
            f"{packet['packet_id']}: a packet that does not say what proceeds "
            "without an answer turns founder silence into a full stop"
        )


def test_planned_founder_time_stays_inside_the_charter_cap(
    ledger: dict[str, Any],
) -> None:
    # Four to seven hours planned, ten the hard cap. Entries and packets both
    # spend it, so both are counted.
    minutes = sum(e.get("founder_minutes", 0) for e in _entries(ledger))
    minutes += sum(
        p.get("estimated_founder_minutes", 0)
        for p in ledger.get("founder_decision_packets", [])
    )
    assert minutes <= 600, f"planned founder time {minutes} min exceeds the 10h cap"
