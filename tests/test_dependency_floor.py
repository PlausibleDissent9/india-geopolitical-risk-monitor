"""The published Python floor must stay true of the actual pins.

REPLICATION.md and pyproject.toml both declare the floor (3.11 since
2026-08-19; the ">=3.9" they used to claim was measured false -- the
suite fails 51 tests on 3.9, because zip(strict=) in the conformance and
admission modules is 3.10+ syntax, and no lane has ever tested anything
but 3.11). That is a promise about who can rebuild this index, not an
implementation detail. numpy stays pinned at 2.0.2: the pin is frozen
policy, no longer forced by the old floor.

Dependabot has had seven PRs open since 2026-07-28, one of which bumps
numpy to 2.5.1. That release requires **Python >= 3.12**, so merging it
would fail `pip install` on CI's 3.11 runners before a single test ran,
taking every lane down rather than just `ci`. Nothing in the repo would
have objected: the version numbers look like an ordinary bump, and the
PR's own CI result is ten days stale.

Two checks, split by what they need:

  * offline -- the floor is stated consistently everywhere it appears,
    and CI's version is at or above it. This catches the documents
    drifting apart from each other.
  * live -- each pin in requirements.txt actually supports the floor,
    resolved against PyPI. This catches the pins drifting away from the
    promise.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
REPLICATION = ROOT / "REPLICATION.md"
REQUIREMENTS = ROOT / "requirements.txt"
WORKFLOWS = ROOT / ".github" / "workflows"


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(p) for p in text.split("."))


def floor() -> tuple[int, ...]:
    m = re.search(r'requires-python\s*=\s*">=\s*([\d.]+)"',
                  PYPROJECT.read_text(encoding="utf-8"))
    assert m, "pyproject.toml no longer declares requires-python"
    return _version(m.group(1))


def test_the_replication_guide_states_the_same_floor():
    """An external reproducer reads REPLICATION.md, not pyproject.toml.
    If the two disagree, somebody follows the guide onto a version that
    cannot install the requirements."""
    declared = ".".join(str(p) for p in floor())
    text = REPLICATION.read_text(encoding="utf-8")
    assert f"Python {declared}+" in text, (
        f"pyproject.toml requires >={declared}; REPLICATION.md does not say "
        f"'Python {declared}+'. The guide is what a stranger follows.")


def test_ci_runs_at_or_above_the_floor():
    versions = set(re.findall(r'python-version:\s*"([\d.]+)"',
                              "\n".join(p.read_text(encoding="utf-8")
                                        for p in WORKFLOWS.glob("*.yml"))))
    assert versions, "no workflow declares a python-version"
    low = min(_version(v) for v in versions)
    assert low >= floor(), (
        f"a workflow runs Python {low} below the declared floor {floor()}")


def test_every_workflow_agrees_on_the_python_version():
    """Fifteen workflows, one version. A lane quietly running a different
    interpreter is how a dependency works everywhere except the one place
    it matters."""
    versions = set(re.findall(r'python-version:\s*"([\d.]+)"',
                              "\n".join(p.read_text(encoding="utf-8")
                                        for p in WORKFLOWS.glob("*.yml"))))
    assert len(versions) == 1, (
        f"workflows disagree about the Python version: {sorted(versions)}")


def test_reproduction_requirements_are_exactly_pinned():
    """A floating provider SDK changed its typed response union overnight.

    CI installed the new SDK while the local gate had no SDK installed, so
    mypy was red remotely and green locally. The reproduction file already
    promises exact pins; enforce the promise for every active requirement.
    """
    unpinned = []
    for line_number, raw in enumerate(REQUIREMENTS.read_text().splitlines(), 1):
        requirement = raw.split("#", 1)[0].strip()
        if requirement and not re.fullmatch(r"[A-Za-z0-9_.-]+==[^\s;]+", requirement):
            unpinned.append(f"line {line_number}: {requirement}")
    assert not unpinned, f"requirements.txt contains non-exact pins: {unpinned}"


def test_optional_assistant_sdk_matches_the_runtime_pin():
    runtime = re.search(r"^anthropic==([^\s]+)$", REQUIREMENTS.read_text(), re.M)
    assert runtime, "requirements.txt must pin the assistant SDK"
    assert f'brief = ["anthropic=={runtime.group(1)}"]' in PYPROJECT.read_text(), (
        "pyproject's optional assistant SDK must match requirements.txt exactly"
    )


@pytest.mark.live
def test_every_pin_supports_the_declared_floor():
    """Resolved against PyPI, because the constraint lives there and
    nowhere in this repo.

    numpy 2.5.1 (dependabot #3) requires >=3.12 against a 3.9 floor and a
    3.11 CI. This is the check that would have caught it at merge time
    rather than at the next lane run.
    """
    import json
    import urllib.request

    low = floor()
    offenders = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        m = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([\w.]+)", line)
        if not m:
            continue
        name, ver = m.groups()
        url = f"https://pypi.org/pypi/{name}/{ver}/json"
        try:
            with urllib.request.urlopen(url, timeout=20) as fh:
                info = json.load(fh)["info"]
        except Exception as e:  # noqa: BLE001 -- network flake is not a finding
            pytest.skip(f"PyPI unreachable for {name}: {e}")
        req = info.get("requires_python") or ""
        m2 = re.search(r">=\s*([\d.]+)", req)
        if m2 and _version(m2.group(1)) > low:
            offenders.append(f"{name}=={ver} requires {req}")

    declared = ".".join(str(p) for p in low)
    assert not offenders, (
        f"these pins no longer support the promised Python {declared}+: "
        f"{offenders}. Either revert the pin or move the floor "
        "deliberately -- in pyproject.toml, REPLICATION.md and every "
        "workflow, in one change.")
