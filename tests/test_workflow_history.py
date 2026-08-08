"""CI must retain the Git history required by frozen registrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    "ci.yml",
    "daily.yml",
    "morning.yml",
    "reproduce.yml",
)


def test_test_running_workflows_fetch_full_registration_history() -> None:
    for name in WORKFLOWS:
        workflow = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )
        _assert_current_full_history(name, workflow)


def _assert_current_full_history(name: str, workflow: str) -> None:
    checkout = re.search(
        r"uses:\s*actions/checkout@v(?P<version>\d+)(?P<body>.*?)(?=\n\s*- uses:)",
        workflow,
        re.S,
    )
    assert checkout, f"{name} has no actions/checkout step"
    assert int(checkout.group("version")) >= 7, f"{name} checkout action is obsolete"
    assert re.search(r"fetch-depth:\s*0\b", checkout.group("body")), (
        f"{name} must fetch complete history for frozen base-commit verification"
    )
    setup = re.search(r"uses:\s*actions/setup-python@v(\d+)", workflow)
    assert setup and int(setup.group(1)) >= 7, f"{name} setup-python action is obsolete"
