"""CI must retain the Git history required by frozen registrations."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_checkout_is_current_and_fetches_full_history() -> None:
    workflow = CI.read_text(encoding="utf-8")
    checkout = re.search(
        r"uses:\s*actions/checkout@v(?P<version>\d+)(?P<body>.*?)(?=\n\s*- uses:)",
        workflow,
        re.S,
    )
    assert checkout, "CI has no actions/checkout step"
    assert int(checkout.group("version")) >= 7, "CI checkout action is obsolete"
    assert re.search(r"fetch-depth:\s*0\b", checkout.group("body")), (
        "CI must fetch complete history for frozen base-commit verification"
    )
    setup = re.search(r"uses:\s*actions/setup-python@v(\d+)", workflow)
    assert setup and int(setup.group(1)) >= 7, "CI setup-python action is obsolete"
