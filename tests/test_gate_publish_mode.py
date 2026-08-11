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


def test_publisher_uses_the_publish_gate_not_the_full_one() -> None:
    """The deadlock came from publish_push.sh calling the full gate. Pin the
    call site, or the fix silently reverts the next time it is edited."""
    pp = (ROOT / "scripts" / "publish_push.sh").read_text(encoding="utf-8")
    assert "gate.sh --publish" in pp, (
        "publish_push.sh no longer uses the publish gate; a live-site "
        "assertion can deadlock every publisher again")
    assert "gate.sh --committed" not in pp, (
        "publish_push.sh still calls the full gate somewhere")
