"""Keep the public detection record current and interpretation-bounded."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_detection_claims_distinguish_the_original_and_combined_registers() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "nef" / "REVIEWERS_GUIDE.md").read_text(encoding="utf-8")
    homepage = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    paper = (ROOT / "paper" / "WORKING_PAPER.md").read_text(encoding="utf-8")

    assert "24/29" in readme and "18/21" in readme and "6/8" in readme
    assert "24/29" in guide and "19/29" in guide and "6.8 expected" in guide
    assert "evaluated on a registered episode record with baselines" in homepage
    assert "evaluated on registered episode lists" in " ".join(paper.split())
    combined = "\n".join((readme, guide, homepage, paper)).lower()
    assert "pre-registered validation hit rate" not in combined
    assert "validated against a pre-registered episode list" not in combined


def test_latest_payload_does_not_turn_one_anecdote_into_validation() -> None:
    latest = json.loads((ROOT / "docs" / "data" / "latest.json").read_text())
    what = latest["_meta"]["what"].lower()
    assert "not a validation or forecasting result" in what
    assert "pahalgam" not in what
    assert "verified to reach" not in what
