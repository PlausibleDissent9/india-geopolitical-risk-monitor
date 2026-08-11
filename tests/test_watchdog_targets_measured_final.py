"""The watchdog must recover a missing measured day, not a stale write stamp.

``latest._meta.generated`` says when a file was written. A degraded run can
write it today while preserving an older ``latest.date``; treating the write
date as finality would make every later watchdog shot stand down. The morning
contract instead requires the completed UTC day D-1.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _watchdog_check_step() -> str:
    source = (WORKFLOWS / "watchdog.yml").read_text(encoding="utf-8")
    block = source.split("- name: Is the target final published?", 1)[1].split(
        "- name: Is a morning run already waiting for the lane?", 1
    )[0]
    return block.split("run: |", 1)[1]


def _nowcast_guarantor_step() -> str:
    source = (WORKFLOWS / "nowcast.yml").read_text(encoding="utf-8")
    block = source.split("- name: Morning-contract guarantor", 1)[1].split(
        "- name: Compute provisional today-so-far", 1
    )[0]
    return block.split("run: |", 1)[1]


def test_watchdog_uses_the_exact_completed_utc_day() -> None:
    step = _watchdog_check_step()
    assert 'TARGET=$(date -u -d "yesterday" +%F)' in step
    assert "json.load(open('docs/data/latest.json'))['date']" in step
    assert 'if [ "$MEASURED" = "$TARGET" ]; then' in step


def test_write_timestamp_cannot_suppress_recovery() -> None:
    for step in (_watchdog_check_step(), _nowcast_guarantor_step()):
        assert "_meta" not in step
        assert "generated" not in step


def test_nowcast_guarantor_uses_the_same_measured_target() -> None:
    step = _nowcast_guarantor_step()
    assert 'TARGET=$(date -u -d "yesterday" +%F)' in step
    assert "json.load(open('docs/data/latest.json'))['date']" in step
    assert 'if [ "$MEASURED" != "$TARGET" ]; then' in step
