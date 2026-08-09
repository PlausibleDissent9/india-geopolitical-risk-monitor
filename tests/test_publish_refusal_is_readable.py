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

These tests run the real function out of the real script against stub
gates, rather than asserting on the source text, because a message that
is never reached is not a message.
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
        + _gate_candidate_source()
        + "\nif ! gate_candidate; then exit 7; fi\n"
    )
    (tmp_path / "harness.sh").write_text(harness, encoding="utf-8")
    return subprocess.run(["bash", "harness.sh"], cwd=tmp_path,
                          capture_output=True, text=True)


GATE_RED_MIDWAY = """#!/usr/bin/env bash
echo "gate: running 3 checks from ci.yml"
echo "-- python scripts/check_environment.py"
echo "-- ruff check ."
echo "-- python -m pytest --cov=src -q"
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
    assert "::error::" in r.stdout, (
        "the refusal never reaches the annotations API, so diagnosing it "
        "still requires an authenticated log download")
    assert "python -m pytest --cov=src -q" in r.stdout, (
        f"the annotation does not name the failing check: {r.stdout}")


def test_a_gate_that_never_ran_says_so(tmp_path):
    """The distinction daily #102 turned on. 'The gate ran and pytest
    failed' and 'the gate died before running anything' are different
    incidents, and a refusal that cannot tell them apart sends the next
    reader hunting for a failing test that never ran."""
    r = _run(tmp_path, GATE_DIED_EARLY)
    assert r.returncode == 7
    assert "::error::" in r.stdout
    assert "unknown" in r.stdout and "before running any check" in r.stdout, (
        f"an early gate abort is not distinguished: {r.stdout}")


def test_a_green_gate_still_passes_and_says_nothing_alarming(tmp_path):
    """Diagnostics must not change the verdict."""
    r = _run(tmp_path, GATE_GREEN)
    assert r.returncode == 0, "a green gate must still pass"
    assert "::error::" not in r.stdout
    assert "passed the committed CI gate" in r.stdout


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
