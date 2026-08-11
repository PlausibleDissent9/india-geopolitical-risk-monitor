"""`scripts/gate.sh --publish` must narrow exactly one thing.

A publish gate answers "is this candidate fit to serve?". The tests marked
`live` answer something else: they fetch igrm.in and assert about the payloads
the site is ALREADY serving. Including them in the gate inside
publish_push.sh closed a loop with no exit -- a stale site refused the very
pushes that would refresh it, and on 2026-08-11 that failed morning-contract
runs #45 and #46 at the "Commit and push" step with nothing wrong with either
candidate.

`--publish` removes those assertions and NOTHING else. That "nothing else" is
the whole safety argument, so it is pinned here rather than trusted: this test
runs the script's own transformation (`--publish --print`) and compares it to
the script's own extraction (`--print`), instead of restating either in
Python. A test that restates the expression under test verifies the
restatement -- the defect this repo has already paid for in
tests/test_gate_matches_ci.py.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "gate.sh"


def _run(*flags: str) -> list[str]:
    out = subprocess.run(["bash", str(GATE), *flags], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line.strip()]


def test_publish_narrows_only_the_pytest_command() -> None:
    """Every non-pytest check must survive --publish byte-identically."""
    plain = _run("--print")
    published = _run("--publish", "--print")

    assert len(plain) == len(published), (
        "--publish changed the NUMBER of checks; it must only rewrite the "
        f"pytest invocation.\nplain={plain}\npublished={published}")

    differing = [(a, b) for a, b in zip(plain, published) if a != b]
    assert len(differing) == 1, (
        f"--publish must change exactly one command, changed {len(differing)}: "
        f"{differing}")
    before, after = differing[0]
    assert "pytest" in before, (
        f"--publish rewrote a NON-pytest command: {before!r} -> {after!r}. "
        "Only the live-site assertions may be excluded from a publish gate.")


def test_publish_excludes_live_marked_tests() -> None:
    """The narrowed command must actually deselect the live suite."""
    published = _run("--publish", "--print")
    pytest_cmds = [c for c in published if "pytest" in c]
    assert len(pytest_cmds) == 1, f"expected one pytest command, got {pytest_cmds}"
    assert '-m "not live"' in pytest_cmds[0], (
        f"--publish did not exclude the live suite: {pytest_cmds[0]!r}")


def test_publish_keeps_coverage_and_every_registry_check() -> None:
    """The candidate-describing checks are the point of the gate; --publish
    must not quietly drop coverage or a --check refusal along the way."""
    published = " \n".join(_run("--publish", "--print"))
    assert "--cov=src" in published, "--publish dropped coverage"
    for required in ("check_environment", "security_integrity", "product_catalog",
                     "world_state", "event_ledger", "evolution_engine",
                     "ruff check .", "mypy"):
        assert required in published, f"--publish dropped the {required} check"


def test_plain_print_still_matches_ci_verbatim() -> None:
    """--publish must not leak into the default mode: a plain gate is still
    exactly what CI runs, which is the property gate.sh exists to hold."""
    plain = _run("--print")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for cmd in plain:
        assert cmd in ci, f"the plain gate runs {cmd!r}, which CI does not"
    assert not any('-m "not live"' in c for c in plain), (
        "the plain gate must NOT exclude live tests; only --publish may")


def test_publish_refuses_rather_than_mis_narrowing_a_compound_pytest_step() -> None:
    """The marker is APPENDED, so the pytest step must be a single command.

    Found by attacking my own change rather than by it failing: if CI's pytest
    step ever became `python -m pytest -q && echo done`, appending would
    produce `... && echo done -m "not live"`. The marker lands on echo, pytest
    runs WITH the live suite, and the deadlock returns INVISIBLY -- a gate that
    looks narrowed and is not, which is worse than the bug it replaced.

    Refusing is the only safe answer, and it is exercised here against a real
    mutated ci.yml in a scratch copy of the repo, not asserted about in prose.
    """
    import shutil
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        (work / ".github" / "workflows").mkdir(parents=True)
        (work / "scripts").mkdir()
        shutil.copy(GATE, work / "scripts" / "gate.sh")
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        # Exactly the hazardous shape, and nothing else about CI changed.
        mutated = ci.replace(
            "run: python -m pytest --cov=src --cov-report=term-missing -q",
            "run: python -m pytest --cov=src -q && echo done")
        assert mutated != ci, "the fixture no longer matches CI's pytest step"
        (work / ".github" / "workflows" / "ci.yml").write_text(mutated, encoding="utf-8")

        proc = subprocess.run(
            ["bash", str(work / "scripts" / "gate.sh"), "--publish", "--print"],
            cwd=work, capture_output=True, text=True)

    assert proc.returncode != 0, (
        "--publish accepted a compound pytest step; it would have narrowed the "
        f"wrong command.\nstdout: {proc.stdout}")
    assert "shell operator" in proc.stdout + proc.stderr, (
        f"the refusal does not explain itself: {proc.stdout}{proc.stderr}")
    assert 'echo done -m "not live"' not in proc.stdout, (
        "--publish emitted the mis-narrowed command instead of refusing")


def test_every_push_path_uses_the_publish_gate() -> None:
    """The deadlock came from the push paths calling the FULL gate. Pin both
    call sites, or the fix silently reverts the next time one is edited.

    ship.sh is here for a reason that is easy to miss: it was subject to the
    same deadlock, so while the site was stale it could not push anything --
    including the commit that fixes the deadlock.
    """
    for name in ("publish_push.sh", "ship.sh"):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert "gate.sh --publish" in text, (
            f"{name} no longer uses the publish gate; a live-site assertion "
            "can deadlock every push again")
        assert "bash scripts/gate.sh --committed" not in text, (
            f"{name} still invokes the full gate, which re-opens the deadlock")
