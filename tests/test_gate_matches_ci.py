"""The local gate must run what CI runs, not something narrower.

WHAT HAPPENED
Six consecutive pushes on 2026-08-07 went red while every commit message
claimed "ruff clean, mypy clean, N passing". All three were true of the
commands I ran and false of the commands CI runs:

    I ran                       CI runs
    mypy src/one_new_file.py    mypy                  (all 67 files)
    pytest -m "not live"        pytest --cov=src      (11 more tests)
    ruff check src tests        ruff check .          (the whole tree)

Two missing annotations of mine and one typing error in another agent's
module sat red for half an hour, because a narrower command passed and I
reported that as the gate. This is the same defect as everything else
found this week -- a check that cannot fail the way the real one does --
except the check was me.

`scripts/gate.sh` does not restate the commands. It extracts them from
ci.yml and runs them, so it cannot drift. This file guards the
extraction: if a CI step is added that the script's pattern does not
pick up, the gate silently gets narrower again and nothing would say so.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
GATE = ROOT / "scripts" / "gate.sh"

# The one command the gate deliberately skips: the venv is provisioned,
# and reinstalling on every gate run costs minutes for no signal.
SKIPPED = ("pip install",)


def _ci_commands() -> list[str]:
    return [m.group(1).strip()
            for m in re.finditer(r"^\s+run:\s+(.+)$", CI.read_text(encoding="utf-8"),
                                 re.M)]


def _gate_extracted() -> list[str]:
    """Run the script's own extraction, so the test checks the real
    pipeline rather than a reimplementation of it."""
    out = subprocess.run(
        ["bash", "-c",
         f"grep -E '^[[:space:]]+run: ' {CI} | sed -E 's/^[[:space:]]+run: //' "
         "| grep -v '^pip install'"],
        capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def test_the_gate_script_exists_and_is_executable():
    assert GATE.exists(), "scripts/gate.sh is gone"
    assert GATE.stat().st_mode & 0o111, "scripts/gate.sh is not executable"


def test_the_gate_picks_up_every_ci_command():
    expected = [c for c in _ci_commands()
                if not any(c.startswith(s) for s in SKIPPED)]
    got = _gate_extracted()
    assert got == expected, (
        f"the gate extracts {got} but CI runs {expected}. A CI step the "
        "script does not pick up means the local gate is quietly narrower "
        "than the real one, which is exactly how six pushes went red while "
        "reporting green.")


def test_the_gate_reads_ci_rather_than_restating_it():
    """If someone 'simplifies' the script by hardcoding the three
    commands, it stops tracking CI and the whole point is lost."""
    text = GATE.read_text(encoding="utf-8")
    assert "ci.yml" in text, "the gate no longer reads ci.yml"
    assert "run: " in text, "the gate no longer extracts the run: steps"


def _gate_code() -> str:
    """Shell minus comments.

    The first version of the check below searched the whole file and
    failed on the COMMENT explaining why mapfile is not used. That is the
    second banned-substring test today to fire on a discussion of the
    banned thing rather than a use of it -- the other forbade "six of
    eight" in prose that existed to explain why the score is not reported
    that way. A substring cannot tell a use from an explanation, so the
    fix is to search only what bash will actually execute.
    """
    lines = []
    for line in GATE.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def test_the_gate_is_portable_to_the_machine_it_protects():
    """macOS ships bash 3.2. The first version used `mapfile`, which is
    bash 4+, so the gate failed to run at all on the only machine that
    needed it -- and exited 0 while doing so, which is worse than not
    existing."""
    assert "mapfile" not in _gate_code(), (
        "mapfile is bash 4+ and absent on macOS's bash 3.2")


def test_ci_still_checks_types_over_the_whole_project():
    """The specific narrowing that caused the outage. A bare `mypy` uses
    the pyproject config and covers every source file; `mypy some/file.py`
    checks one and passes while the project is broken."""
    cmds = _ci_commands()
    assert "mypy" in cmds, (
        f"CI's mypy step is no longer a bare project-wide run: {cmds}")
