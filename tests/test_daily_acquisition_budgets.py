"""Network enrichment must stop before GitHub kills its process.

The runner timeout is an axe: a process killed there cannot persist partial
progress or explain which upstream failed. These tests bind the workflow's
outer budgets to the in-process deadlines and keep the full-day receipts scan
out of the atomic daily publication lane.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / ".github" / "workflows" / "daily.yml"
EXTENDED = ROOT / ".github" / "workflows" / "receipts-extended.yml"


def test_gdelt_enrichments_leave_runner_cleanup_margin() -> None:
    workflow = DAILY.read_text(encoding="utf-8")
    comparator = re.search(
        r"Comparator tails.*?timeout-minutes:\s*(\d+).*?"
        r"src\.comparators --update --deadline-seconds (\d+)",
        workflow,
        re.S,
    )
    china = re.search(
        r"China monitor.*?timeout-minutes:\s*(\d+).*?"
        r"src\.country_monitor china --deadline-seconds (\d+)",
        workflow,
        re.S,
    )
    assert comparator and china
    for step_minutes, inner_seconds in (comparator.groups(), china.groups()):
        assert int(step_minutes) * 60 - int(inner_seconds) >= 180


def test_atomic_daily_lane_does_not_run_the_full_day_receipts_scan() -> None:
    workflow = DAILY.read_text(encoding="utf-8")
    match = re.search(
        r"Receipts at scoring depth.*?run:\s*\|(?P<body>.*?)\n\s*- name:",
        workflow,
        re.S,
    )
    assert match
    body = match.group("body")
    assert "python -m src.receipts_ngrams || rc=$?\n" in body
    assert "--extended" not in body
    # receipts_ngrams exits 1 by design while a backlog scan banks progress;
    # under bash -e that refusal starved the four sibling lanes for the whole
    # catch-up window (measured 2026-08-19: all four 12 days stale). Every
    # sibling must keep its own refusal-capture, and the step must still
    # surface the last refusal as its exit code -- silence is not success.
    for module in ("receipts_archive", "episode_attribution",
                   "spike_breadth", "syndication"):
        assert f"python -m src.{module} || rc=$?\n" in body
    assert 'exit "$rc"' in body


def test_full_day_receipts_remain_a_separate_gated_product() -> None:
    workflow = EXTENDED.read_text(encoding="utf-8")
    assert "python -m src.receipts_ngrams --extended" in workflow
    assert "timeout-minutes: 210" in workflow
    assert "timeout-minutes: 150" in workflow
    assert 'IGRM_RECEIPTS_DEADLINE_S: "8400"' in workflow
    assert "Publish complete view or bank incomplete checkpoint" in workflow
    assert "extended receipts scan incomplete; raw checkpoint was banked" in workflow
    assert "bash scripts/publish_push.sh" in workflow
    assert "persist-credentials: false" in workflow


# Worst per-file rate ever measured for the standard scan: 38 windows in
# the 600s budget on 2026-08-15 (data/raw/receipt_days/2026-08-15.json).
# Used as the floor a budget must clear, not as a prediction.
WORST_SECONDS_PER_WINDOW = 600 / 38


def test_the_receipts_budget_can_actually_finish_one_day() -> None:
    """A budget below the day's size is a scan that never finishes.

    The standard scan needs fetch_ngrams.SAMPLES_PER_DAY windows and
    refuses to publish a partial corpus. Its resume cache only converges
    if some run completes the day, and this lane runs once per day while
    latest.json advances every morning -- so a single pass MUST finish.

    Measured before this test existed: every committed cache was
    incomplete (2026-08-15 n_samples=38, 2026-08-18 39, 2026-08-19 43,
    never 48) and docs/data/receipts.json stayed frozen at 2026-08-07 for
    thirteen days as a direct result.
    """
    from src.fetch_ngrams import SAMPLES_PER_DAY

    workflow = DAILY.read_text(encoding="utf-8")
    match = re.search(
        r"Receipts at scoring depth.*?timeout-minutes:\s*(?P<minutes>\d+)"
        r".*?IGRM_RECEIPTS_DEADLINE_S:\s*\"(?P<deadline>\d+)\"",
        workflow,
        re.S,
    )
    assert match, "the daily receipts step no longer declares both budgets"
    deadline = int(match.group("deadline"))
    step_seconds = int(match.group("minutes")) * 60

    needed = SAMPLES_PER_DAY * WORST_SECONDS_PER_WINDOW
    assert deadline >= needed, (
        f"IGRM_RECEIPTS_DEADLINE_S={deadline}s cannot finish a "
        f"{SAMPLES_PER_DAY}-window day at the worst measured rate "
        f"({WORST_SECONDS_PER_WINDOW:.1f}s/window needs {needed:.0f}s). "
        "The scan will bank a partial cache every night, refuse to "
        "publish, and receipts.json will freeze -- which is exactly what "
        "happened from 2026-08-07 to 2026-08-20.")

    # The four sibling modules share this step and took 636s on run
    # 32326976462. The step ceiling has to cover the scan AND them, or
    # the runner's axe lands mid-sibling and banks nothing.
    assert step_seconds - deadline >= 636, (
        f"step ceiling {step_seconds}s leaves only {step_seconds - deadline}s "
        "for receipts_archive, episode_attribution, spike_breadth and "
        "syndication after the scan; they measured 636s")


def test_a_refused_extended_publish_still_banks_the_completed_scan() -> None:
    """The scan costs 73 minutes; the publish costs seconds.

    Run 32342408405 (2026-08-20) completed a 4408s extended scan --
    5/5 channels, 130,662 docs, the richest receipts payload the project
    has produced -- and the gate refused the candidate over a missing
    cascade. Nothing was committed, so the banked cache stayed
    complete=false n_samples=45 and the whole pass was lost. The failure
    branch had always banked its checkpoint; the success branch banked
    nothing. publish_push.sh commits and rebases the candidate before
    gating, so on refusal the completed cache is sitting in a clean
    local commit and can be recovered onto main.
    """
    workflow = EXTENDED.read_text(encoding="utf-8")
    publish = workflow[workflow.index("Publish complete view"):]

    assert 'if bash scripts/publish_push.sh' in publish, (
        "the success branch calls publish_push.sh unconditionally again; a "
        "red gate there discards the completed scan")
    for fragment in (
        'CANDIDATE="$(git rev-parse HEAD)"',
        "git reset -q --hard origin/main",
        'git checkout "$CANDIDATE" -- data/raw/receipt_days',
    ):
        assert fragment in publish, (
            f"the scan-preserving recovery lost its {fragment!r} step")

    # docs must NOT be recovered: the gate refused those bytes, and they
    # are cheap to recompute. Only the scan cache is expensive.
    recovery = publish[publish.index('CANDIDATE="$(git rev-parse HEAD)"'):]
    assert 'git checkout "$CANDIDATE" -- docs' not in recovery, (
        "the recovery re-stages docs bytes the gate just refused")
