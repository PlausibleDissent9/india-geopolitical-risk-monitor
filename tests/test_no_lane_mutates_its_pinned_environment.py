"""A second pip install must not be free to move the first one's pins.

WHAT HAPPENED (2026-08-18, daily-update run 32090616610)

The run completed all 48 steps -- acquisition, every derived lane, the
stamp -- and then refused at the publish gate:

    environment differs from committed pins:
    requests==2.34.2 installed (expected 2.32.5)

scripts/check_environment.py exists because the committed gate skips
`pip install` for speed, which is only safe while the interpreter still
holds what CI installed. Two pip commands ran in that lane: the pinned
`-r requirements.txt -r requirements-dev.txt` at the top, and, ninety
minutes later, a bare `pip install --quiet google-cloud-bigquery`. pip
is entitled to upgrade an already-installed package to satisfy a new
one, and something in that resolution took requests past its pin.

The check was right. The lane had stopped being the environment CI
tested, and it had stopped silently -- the whole point of that check.

WHAT THIS ENFORCES

If a workflow installs the pinned requirements and later runs a
SEPARATE pip install, that later install must carry `-c
requirements.txt`. Constraints make the pins win: pip either resolves
the new package against them or fails immediately, in the step that
caused it, instead of succeeding and refusing a publish forty minutes
downstream.

Deliberately NOT flagged: a single `pip install -r requirements.txt ...
extra-package` command. There pip resolves everything in one pass, so a
conflict with an exact pin is an error at that moment rather than a
silent upgrade -- which is the property this file is protecting.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

PINNED = "-r requirements.txt"
CONSTRAINT = "-c requirements.txt"


def _installs(text: str) -> list[str]:
    """Every pip install command a workflow actually RUNS.

    Line based, not a regex over the whole file, and comments are
    stripped BEFORE matching. The first version regexed the raw text and
    reported three offenders, all of them prose: "pip install included.",
    "pip install can upgrade a". tests/test_every_payload_has_a_lane.py
    already carries this exact lesson about a module named inside a
    comment; writing it a second time is what this docstring is for.

    Continuations are folded by joining lines that end in a backslash,
    because the constraint flag legitimately sits on the next line.
    """
    lines = []
    for raw in text.splitlines():
        body = raw.strip()
        if body.startswith("#"):
            continue
        lines.append(raw.rstrip())
    folded: list[str] = []
    buffer = ""
    for line in lines:
        if line.endswith("\\"):
            buffer += line[:-1].strip() + " "
            continue
        folded.append((buffer + line.strip()).strip())
        buffer = ""
    if buffer:
        folded.append(buffer.strip())
    return [ln.split("pip install", 1)[1].strip()
            for ln in folded if "pip install" in ln]


def _workflows() -> list[str]:
    return sorted(p.name for p in WORKFLOWS.glob("*.yml"))


@pytest.mark.parametrize("workflow", _workflows())
def test_a_later_install_cannot_move_the_pinned_environment(workflow):
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    installs = _installs(text)
    if not any(PINNED in cmd for cmd in installs):
        return  # this lane never pins, so it has no pins to break
    offenders = [
        cmd.strip() for cmd in installs
        if PINNED not in cmd and CONSTRAINT not in cmd
    ]
    assert not offenders, (
        f".github/workflows/{workflow} installs the pinned requirements and "
        f"then runs a separate, unconstrained pip install: {offenders}. pip "
        "may upgrade an already-installed package to satisfy a new one, "
        "which takes the lane out of the environment CI tested and makes "
        "scripts/check_environment.py refuse the publish -- after the whole "
        "pipeline has run. Add `-c requirements.txt -c requirements-dev.txt` "
        "so the pins win and a genuine conflict fails HERE instead.")


def test_the_check_this_protects_still_exists():
    """Guard the guard. If check_environment.py stops comparing installed
    versions to the pins, every assertion above is enforcing a rule that
    nothing downstream relies on."""
    script = ROOT / "scripts" / "check_environment.py"
    assert script.exists(), "scripts/check_environment.py is gone"
    text = script.read_text(encoding="utf-8")
    assert "installed_mismatches" in text and "required_pins" in text, (
        "check_environment.py no longer compares installed versions to the "
        "committed pins; this file's rule has nothing left to protect")


def test_at_least_one_workflow_is_actually_covered():
    """A parametrised test that skips every case passes by matching
    nothing. At least one lane must pin, or this file is vacuous."""
    pinning = [
        w for w in _workflows()
        if any(PINNED in cmd for cmd in _installs((WORKFLOWS / w).read_text(encoding="utf-8")))
    ]
    assert len(pinning) >= 5, f"only {len(pinning)} workflows pin requirements: {pinning}"
