"""A publish refusal has to be readable without a repository token.

WHAT WENT WRONG
On 2026-08-09 the site served 2026-08-07 for a third day. daily-update
#102 completed all 44 steps and then failed at "Commit data" in two
seconds -- too fast for the gate, too fast for the retry loop's sleeps.
gate.sh already names each check as it starts it, so the answer was
sitting in the step log the whole time.

Step logs need an authenticated token to fetch. Run ANNOTATIONS do not.
That difference was the entire distance between a three-day outage and a
diagnosis: the annotations API, read without credentials, gave up the
three steps that had timed out within seconds, while the one line that
mattered stayed behind an authenticated download.

So a refusal now also emits a `::error::` workflow command, which GitHub
promotes into the annotations. The point is not prettier logs. It is that
the next person looking at a red publisher -- human or agent, with or
without a token -- can see WHICH check refused, and specifically can tell
"the gate ran and check X failed" apart from "the gate never ran at all",
which is exactly the distinction #102 turned on and nobody could make.

AND THEN THE ANNOTATION ITSELF SHIPPED BROKEN
The first version reported the last line matching `^-- `, which is what
gate.sh prints when it STARTS a check. pytest's own warnings footer ends

    -- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html

so morning-contract #34 refused with "Last check started: Docs:
https://docs.pytest.org/...", naming a documentation URL. Correct
refusal, zero diagnosis -- the failure this annotation exists to prevent,
reproduced inside the fix for it.

The stubs below were complicit: GATE_RED_MIDWAY printed the `-- ` lines
but never gate.sh's actual `FAILED: <cmd>` line, and never pytest's
footer, so the broken version passed. A stub that omits the output the
code reads is not a test of that code. They now transcribe what gate.sh
really emits.

These tests run the real function out of the real script against stub
gates, rather than asserting on the source text, because a message that
is never reached is not a message. Assertions read the `::error::` line
specifically, not the whole of stdout -- the refusal `cat`s the gate log
too, so asserting against stdout passes on text the annotation never
carried.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_push.sh"


def _gate_candidate_source() -> str:
    """The real function, lifted from the real script."""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"^gate_candidate\(\) \{.*?^\}", text, re.S | re.M)
    assert m, "gate_candidate() not found in scripts/publish_push.sh"
    return m.group(0)


def _explain_source() -> str:
    """gate_candidate delegates the reading, so the harness needs both."""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"^explain_gate_log\(\) \{.*?^\}", text, re.S | re.M)
    assert m, "explain_gate_log() not found in scripts/publish_push.sh"
    return m.group(0)


def _annotation(proc: subprocess.CompletedProcess[str]) -> str:
    """The ::error:: line alone.

    The refusal also echoes the whole gate log, so a naive `in r.stdout`
    passes on text that never reached the annotations API -- which is the
    one surface this entire mechanism exists to populate.
    """
    for line in proc.stdout.splitlines():
        if line.startswith("::error::"):
            return line
    return ""


def _run(tmp_path: Path, gate_body: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "gate.sh").write_text(gate_body, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    harness = (
        "set -uo pipefail\n"
        + _explain_source()
        + "\n"
        + _gate_candidate_source()
        + "\nif ! gate_candidate; then exit 7; fi\n"
    )
    (tmp_path / "harness.sh").write_text(harness, encoding="utf-8")
    return subprocess.run(["bash", "harness.sh"], cwd=tmp_path,
                          capture_output=True, text=True)


# What gate.sh really prints when a check fails: the `-- ` line as it
# STARTS each check, then `FAILED: <cmd>` for the one that failed. The
# pytest footer is included because it is the line that broke the first
# version of the reader.
GATE_RED_MIDWAY = """#!/usr/bin/env bash
echo "gate: running 3 checks from ci.yml"
echo "-- python scripts/check_environment.py"
echo "-- ruff check ."
echo "-- python -m pytest --cov=src -q"
echo "=========================== short test summary info ============================"
echo "FAILED tests/test_vintages.py::test_published_history_is_never_rewritten - ..."
echo "FAILED: python -m pytest --cov=src -q"
echo ""
echo "-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html"
echo "gate: CI would be red. Do not push."
exit 1
"""

# A refusal that is not pytest at all, so there is no summary block.
GATE_RED_ON_A_CHECK = """#!/usr/bin/env bash
echo "gate: running 3 checks from ci.yml"
echo "-- python -m src.evolution_engine --check"
echo "__main__.EvolutionError: evolution_report_stale"
echo "FAILED: python -m src.evolution_engine --check"
echo "gate: CI would be red. Do not push."
exit 1
"""

GATE_DIED_EARLY = """#!/usr/bin/env bash
echo "gate: extracting HEAD to /tmp/x"
echo "gate: git archive failed"
exit 1
"""

GATE_GREEN = """#!/usr/bin/env bash
echo "-- ruff check ."
echo "gate: all 11 CI checks pass"
"""


def test_a_refusal_names_the_failing_check_in_an_annotation(tmp_path):
    r = _run(tmp_path, GATE_RED_MIDWAY)
    assert r.returncode == 7, "a red gate must refuse"
    note = _annotation(r)
    assert note, (
        "the refusal never reaches the annotations API, so diagnosing it "
        "still requires an authenticated log download")
    assert "python -m pytest --cov=src -q" in note, (
        f"the annotation does not name the failing check: {note}")


def test_the_pytest_docs_footer_is_never_mistaken_for_a_check(tmp_path):
    """The morning-contract #34 regression, as one assertion.

    pytest's warnings footer starts with `-- `, so a reader that takes the
    last `-- ` line reports a documentation URL as the failing check.
    """
    note = _annotation(_run(tmp_path, GATE_RED_MIDWAY))
    assert "docs.pytest.org" not in note, (
        f"the annotation names pytest's docs footer as a check: {note}")


def test_the_annotation_carries_the_failing_test_names(tmp_path):
    """Naming the command is not enough: `pytest` is the whole suite."""
    note = _annotation(_run(tmp_path, GATE_RED_MIDWAY))
    assert "test_published_history_is_never_rewritten" in note, (
        f"the annotation names no failing test: {note}")


def test_a_non_pytest_refusal_is_explained_too(tmp_path):
    """A `--check` refusal prints no summary block, only an exception."""
    r = _run(tmp_path, GATE_RED_ON_A_CHECK)
    assert r.returncode == 7
    note = _annotation(r)
    assert "python -m src.evolution_engine --check" in note, note
    assert "evolution_report_stale" in note, (
        f"the annotation gives the check but not the reason: {note}")


def test_a_gate_that_never_ran_says_so(tmp_path):
    """The distinction daily #102 turned on. 'The gate ran and pytest
    failed' and 'the gate died before running anything' are different
    incidents, and a refusal that cannot tell them apart sends the next
    reader hunting for a failing test that never ran."""
    r = _run(tmp_path, GATE_DIED_EARLY)
    assert r.returncode == 7
    note = _annotation(r)
    assert "none reported" in note and "before it ran a check" in note, (
        f"an early gate abort is not distinguished: {note}")
    assert "git archive failed" in note, (
        f"the annotation drops the reason the gate died: {note}")


def test_a_green_gate_still_passes_and_says_nothing_alarming(tmp_path):
    """Diagnostics must not change the verdict."""
    r = _run(tmp_path, GATE_GREEN)
    assert r.returncode == 0, "a green gate must still pass"
    assert "::error::" not in r.stdout
    assert "passed the committed CI gate" in r.stdout


def test_reading_a_log_needs_no_publish_credential(tmp_path):
    """`--explain-gate-log` sits above the IGRM_PUBLISH_TOKEN requirement
    deliberately: reading a file and printing must never need the token
    that authorises a push. If it drifts below, this exits non-zero."""
    log = tmp_path / "gate.log"
    log.write_text(GATE_RED_ON_A_CHECK, encoding="utf-8")
    r = subprocess.run(
        ["bash", str(SCRIPT), "--explain-gate-log", str(log)],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path)},
    )
    assert r.returncode == 0, (
        f"explaining a log required a publish credential: {r.stderr}")
    assert "Failing check:" in r.stdout


def test_the_gate_status_is_not_laundered_through_a_pipe(tmp_path):
    """A pipeline reports the LAST command's status. Sending the gate
    through `| tee` to capture it would report tee's success and publish
    unverified bytes -- the precise defect this repo has already paid for.
    The capture must therefore not introduce a pipe."""
    body = _gate_candidate_source()
    assert "gate.sh --committed >" in body, (
        "the gate output is not captured by redirection")
    assert not re.search(r"gate\.sh --committed[^\n]*\|", body), (
        "the gate is piped, which launders its exit status")


def test_unstaged_changes_are_refused_before_the_rebase(tmp_path):
    """The 2026-08-09 outage, as one assertion.

    `git pull --rebase` refuses instantly when the tree has unstaged
    changes. The retry loop then sleeps 10+20+30+40+50 = 150 seconds and
    exits, having never called gate_candidate -- so the lane fails in
    exactly 2.5 minutes with nothing in the log about a gate, because no
    gate ran. Four runs across two workflows did that while the site
    served a three-day-old number.

    The usual cause is a lane staging narrower than it writes:
    stamp_assets rewrites every docs/*.html, and morning.yml stages only
    docs/data and data/raw.
    """
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.html").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    # What stamp_assets does, and what a narrow `git add` leaves behind.
    (tmp_path / "docs" / "index.html").write_text("v2 stamped", encoding="utf-8")

    script = (tmp_path / "scripts" / "publish_push.sh")
    script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    r = subprocess.run(["bash", "scripts/publish_push.sh", "data: test"],
                       cwd=tmp_path, capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                            "HOME": str(tmp_path),
                            "IGRM_PUBLISH_TOKEN": "dummy-not-used"})
    assert r.returncode != 0, "unstaged changes must refuse, not proceed"
    assert "::error::" in r.stdout, (
        "the refusal is invisible in annotations, which is how this cost "
        f"three days: {r.stdout}")
    assert "docs/index.html" in r.stdout, (
        f"the refusal does not name the offending file: {r.stdout}")
    assert "sleep" not in r.stdout.lower() or r.returncode == 1
