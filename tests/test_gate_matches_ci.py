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
    """gate.sh --print IS the script's extraction. The first version of
    this helper re-typed the grep|sed pipeline inside the test -- two
    derivations of ci.yml that would agree forever while the script's
    real extraction drifted. The test audit caught it: the file whose
    purpose is 'a check that cannot fail the way the real one does'
    contained one."""
    out = subprocess.run(["bash", str(GATE), "--print"],
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


# YAML block scalars: `run: |` and friends put the command on the FOLLOWING
# lines, so the extraction captures the marker alone.
BLOCK_SCALARS = ("|", "|-", "|+", ">", ">-", ">+")


def test_every_extracted_command_is_runnable_shell():
    """WHAT HAPPENED (2026-08-16)

    I added emitter checks to ci.yml as `run: |` blocks. Both extractions
    above captured the bare `|`, agreed with each other, and passed --
    then gate.sh evaled it, `syntax error near unexpected token '|'`, and
    the publish lane refused the daily contract for about an hour.

    The tests above guard COMPLETENESS: the gate picks up every CI
    command. Nothing guarded EXECUTABILITY. And completeness could not
    catch this, because _ci_commands() re-derives `|` from the same line
    by the same rule -- two extractions agreeing on a value neither can
    run. The file whose thesis is "a check that cannot fail the way the
    real one does" had one more.
    """
    bad = []
    for cmd in _gate_extracted():
        proc = subprocess.run(["bash", "-n", "-c", cmd], capture_output=True,
                              text=True)
        if proc.returncode != 0:
            bad.append((cmd, proc.stderr.strip()))
    assert not bad, (
        f"gate.sh evals every extracted line; these are not valid shell: {bad}. "
        "A multi-line CI step must be written as a single `run:` line "
        "(joined with && or ;), because the gate's input format is ci.yml "
        "itself.")


def test_no_extracted_command_is_a_yaml_block_marker():
    """The variant `bash -n` cannot see.

    `>-` is valid shell: a redirect that creates a file named `-` and
    exits 0. So a `run: >-` step would extract to `>-`, eval cleanly, and
    the gate would report that check GREEN while running nothing -- a
    silently narrower gate, which is the exact outage this file was
    opened for, arriving by a route the syntax check above misses.

    Not hypothetical: .github/workflows/canonical-graph.yml already uses
    `run: >-`, so the idiom is in the author's hands today.
    """
    offenders = [c for c in _gate_extracted() if c in BLOCK_SCALARS]
    assert not offenders, (
        f"ci.yml has block-scalar run: steps {offenders}. The gate extracts "
        "the marker, not the command beneath it. `>-` is the dangerous one: "
        "it runs clean and reports success having executed nothing.")
