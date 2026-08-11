"""The contract lane must regenerate every payload whose CI check can refuse it.

THE FAILURE THIS PREVENTS
`morning.yml` publishes the daily number. It gates its own candidate with the
full CI gate, so any `python -m src.X --check` in ci.yml can refuse that
candidate -- and a --check refuses precisely when the payload it verifies is
stale against the tree. The lane advances the measured day, so any registry
derived from the day goes stale the moment the pipeline runs.

The lane's "Derived lanes" block was assembled from the payloads whose TESTS
rebuild and compare them. It missed the registries whose CI step is a --check.
On 2026-08-11 that stopped the publish four times in a row:

    publish refused: the committed CI gate is red on 68294b02.
    Failing check: python -m src.event_ledger --check
    EventLedgerError: event_ledger_report_stale

The lane computed a correct number, spent 25 minutes building it, and was then
refused by a check on a payload it had never been told to rebuild. From the
outside that is indistinguishable from a broken pipeline.

WHY THIS SHAPE OF TEST
Not "morning.yml contains src.event_ledger" -- that pins today's symptom and
says nothing about the next --check somebody adds. The invariant is the
relation: for every X where ci.yml runs `src.X --check`, the contract lane must
run `src.X`. A new --check then fails HERE, in a test, rather than at 05:35 in
a lane nobody is watching.

Deliberately NOT the reverse: the lane may regenerate payloads CI never
--checks (most of the derived block), and daily.yml may run far more.
"""
from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
CI = WORKFLOWS / "ci.yml"
CONTRACT = WORKFLOWS / "morning.yml"

_CHECKED = re.compile(r"python -m (src\.[a-z_0-9]+) --check")
_RUN = re.compile(r"python -m (src\.[a-z_0-9]+)(?! --check)")


def _checked_modules() -> set[str]:
    return set(_CHECKED.findall(CI.read_text(encoding="utf-8")))


def _regenerated_by_contract_lane() -> set[str]:
    return set(_RUN.findall(CONTRACT.read_text(encoding="utf-8")))


def test_the_relation_has_something_to_check() -> None:
    """If the patterns stop matching, every assertion below passes vacuously."""
    checked = _checked_modules()
    assert len(checked) >= 4, (
        f"only {len(checked)} `--check` modules found in ci.yml; the pattern "
        "has drifted and this suite is now vacuous")
    assert len(_regenerated_by_contract_lane()) >= 10, (
        "morning.yml appears to regenerate almost nothing; pattern drifted")


def test_contract_lane_regenerates_every_payload_ci_can_refuse_it_for() -> None:
    checked = _checked_modules()
    regenerated = _regenerated_by_contract_lane()
    missing = sorted(checked - regenerated)
    assert not missing, (
        "ci.yml can refuse the morning candidate over these payloads, and the "
        "contract lane never rebuilds them -- so the daily number will be "
        "computed correctly and then refused at the publish step, exactly as "
        "on 2026-08-11:\n  "
        + "\n  ".join(f"python -m {m} --check" for m in missing)
        + "\n\nAdd `python -m <module>` to morning.yml's derived-lanes step "
          "if it is offline and cheap. If it is NOT (network, corpus scan), "
          "that is a real design question: the contract lane cannot afford it, "
          "so the --check does not belong in the publish gate either.")
