"""Static guards for the two shared mobile-overflow fixes.

Playwright measured the generated Methodology and Validation pages at a
375-pixel viewport. Long inline code and the fixed-width channel toggle were
the only uncontained elements. These rules are deliberately shared so all
generated prose pages inherit the correction.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "docs" / "site.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]+)\}}", CSS)
    assert match is not None, f"missing shared rule for {selector}"
    return match.group("body")


def test_long_inline_code_can_break_without_changing_preformatted_blocks() -> None:
    assert "overflow-wrap: anywhere" in _rule("code")
    assert "white-space: pre" in _rule("pre code")
    assert "overflow-x: auto" in _rule("pre")


def test_channel_toggle_wraps_at_phone_width() -> None:
    assert "display: inline-flex" in _rule(".toggle")
    assert "flex-wrap: wrap" in _rule(".toggle")
