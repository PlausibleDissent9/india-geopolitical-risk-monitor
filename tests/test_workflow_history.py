"""CI must retain the Git history required by frozen registrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
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
        r"uses:\s*actions/checkout@(?P<sha>[0-9a-f]{40})(?P<body>.*?)(?=\n\s*- uses:)",
        workflow,
        re.S,
    )
    assert checkout, f"{name} has no actions/checkout step"
    assert checkout.group("sha") == CHECKOUT_SHA, (
        f"{name} checkout action is not the reviewed immutable commit"
    )
    assert re.search(r"fetch-depth:\s*0\b", checkout.group("body")), (
        f"{name} must fetch complete history for frozen base-commit verification"
    )
    assert re.search(r"persist-credentials:\s*false\b", checkout.group("body")), (
        f"{name} must not leave a repository credential available to later steps"
    )
    setup = re.search(r"uses:\s*actions/setup-python@([0-9a-f]{40})", workflow)
    assert setup and setup.group(1) == SETUP_PYTHON_SHA, (
        f"{name} setup-python action is not the reviewed immutable commit"
    )
