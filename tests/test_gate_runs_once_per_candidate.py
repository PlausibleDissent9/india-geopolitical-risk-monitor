"""A candidate is gated once, and a moved candidate is gated again.

WHAT HAPPENED
`publish_push.sh` retries a push five times, and calls the full committed
gate before every attempt. A push is rejected whenever main moved in the
seconds since the rebase, which on a busy night is often: two agents pushed
roughly fifteen times in a few hours on 2026-08-09.

nowcast #79 was cancelled at its 30-minute cap with **19.8 minutes** inside
that one step. The committed gate measured **7m32s** locally the same night,
against the ~5.2 minutes every lane's cap was budgeted for, and a hosted
runner is slower than the machine it was measured on. Two gates do not fit
in thirty minutes, so contention alone could kill a lane that had nothing
wrong with it.

THE FIX UNDER TEST
Gate once per candidate. If HEAD has not moved since the last green gate in
the same run, retry the push without re-running the gate.

WHY THIS IS SAFE, AND WHAT WOULD MAKE IT UNSAFE
The guarantee is "every push is preceded by a green gate over exactly the
bytes being pushed". Skipping a re-gate of an UNCHANGED commit preserves
that exactly. Skipping after HEAD moved would destroy it -- that is the
case the second test exists for, and it is the one that would let a rebase
carry in someone else's untested commit under a stale green verdict.

Keyed on commit sha, not tree: a no-op rebase leaves the sha alone, while a
real rebase, a new parent or an amended tree all change it. Tree-keying
would skip more and is harder to argue; this is the publish path.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "publish_push.sh"

# A stub gate that records every invocation, so the test counts real calls
# rather than trusting a log line.
COUNTING_GATE = """#!/usr/bin/env bash
echo "run" >> "$PWD/gate_calls"
echo "-- ruff check ."
echo "gate: all 11 CI checks pass"
"""


def _memo_source() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    memo = re.search(r"^LAST_GREEN_COMMIT=.*$", text, re.M)
    assert memo, "LAST_GREEN_COMMIT initialiser not found in publish_push.sh"
    gate = re.search(r"^gate_candidate\(\) \{.*?^\}", text, re.S | re.M)
    assert gate, "gate_candidate() not found"
    explain = re.search(r"^explain_gate_log\(\) \{.*?^\}", text, re.S | re.M)
    assert explain, "explain_gate_log() not found"
    return f"{explain.group(0)}\n{memo.group(0)}\n{gate.group(0)}\n"


def _repo(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "gate.sh").write_text(COUNTING_GATE, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)


def _harness(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "harness.sh").write_text(
        "set -uo pipefail\n" + _memo_source() + body, encoding="utf-8")
    return subprocess.run(["bash", "harness.sh"], cwd=tmp_path,
                          capture_output=True, text=True)


def _calls(tmp_path: Path) -> int:
    path = tmp_path / "gate_calls"
    return len(path.read_text(encoding="utf-8").split()) if path.exists() else 0


def test_an_unchanged_candidate_is_gated_once_however_many_push_attempts(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    result = _harness(tmp_path, "gate_candidate\ngate_candidate\ngate_candidate\n")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _calls(tmp_path) == 1, (
        f"the gate ran {_calls(tmp_path)} times for one unchanged candidate; "
        "each extra run is a full CI suite inside a capped lane")
    assert "already passed the committed gate" in result.stdout


def test_a_moved_candidate_is_gated_again(tmp_path: Path) -> None:
    """The safety case. A rebase that brings in another agent's commit must
    never inherit the previous verdict."""
    _repo(tmp_path)
    body = (
        "gate_candidate\n"
        "echo y >> f.txt && git add f.txt && git commit -qm second\n"
        "gate_candidate\n"
    )
    result = _harness(tmp_path, body)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _calls(tmp_path) == 2, (
        "HEAD moved and the gate did not re-run: a push would ship bytes "
        "that were never gated")


def test_a_red_gate_is_not_memoised(tmp_path: Path) -> None:
    """A refusal must not be cached as if it were a verdict to reuse, and
    must not poison the memo so a later green is skipped."""
    _repo(tmp_path)
    (tmp_path / "scripts" / "gate.sh").write_text(
        "#!/usr/bin/env bash\n"
        'echo "run" >> "$PWD/gate_calls"\n'
        'echo "FAILED: python -m pytest -q"\n'
        "exit 1\n",
        encoding="utf-8")
    result = _harness(tmp_path, "gate_candidate || true\ngate_candidate || true\n")
    assert _calls(tmp_path) == 2, (
        "a red gate was memoised; the next attempt skipped it")
    assert result.stdout.count("::error::") == 2
