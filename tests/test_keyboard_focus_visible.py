"""Every focusable page must show keyboard focus somewhere.

WCAG 2.4.7 Focus Visible is level AA, and a page that can be tabbed into
without a visible indicator is unusable by keyboard. embed.html failed
this: it links fonts.css and tokens.css but deliberately not style.css,
where the site's single :focus-visible rule lives, so its one link
focused invisibly.

The check resolves each page's LINKED stylesheets rather than reading the
HTML alone. An earlier pass that scanned only the markup reported all 40
pages as failing, because it never looked where the rule actually lives --
the same mistake, in a different file, as an auditor that reads only one
container.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))

FOCUSABLE = re.compile(r"<(?:a\s[^>]*href=|button\b|select\b|textarea\b|input\b)", re.I)
FOCUS_RULE = re.compile(r":focus-visible|:focus\b")
STYLESHEET = re.compile(r'<link[^>]+href="([^"?]+\.css)')


def _styles_reachable_from(page: Path) -> str:
    """The page's own markup plus every same-directory stylesheet it links."""
    text = page.read_text(encoding="utf-8")
    combined = [text]
    for href in STYLESHEET.findall(text):
        sheet = DOCS / os.path.basename(href)
        if sheet.exists():
            combined.append(sheet.read_text(encoding="utf-8"))
    return "\n".join(combined)


def test_there_are_pages_to_check() -> None:
    # Guard against the whole suite silently passing on an empty glob.
    assert len(PAGES) >= 30


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_a_page_with_focusable_elements_defines_a_focus_style(page: Path) -> None:
    text = page.read_text(encoding="utf-8")
    if not FOCUSABLE.search(text):
        pytest.skip("nothing focusable on this page")
    assert FOCUS_RULE.search(_styles_reachable_from(page)), (
        f"{page.name} can be tabbed into but no :focus-visible rule is "
        "reachable from it; keyboard users get no indicator"
    )


def test_embed_page_carries_its_own_rule_because_it_skips_the_site_stylesheet() -> None:
    # Pinned specifically: embed.html is intentionally minimal and must not
    # be "fixed" by linking the full stylesheet, so its rule has to be local.
    embed = DOCS / "embed.html"
    text = embed.read_text(encoding="utf-8")
    # Parsed link hrefs, not a substring scan: the first version of this
    # assertion searched the raw text and tripped over the code comment that
    # explains why style.css is absent.
    linked = {os.path.basename(h) for h in STYLESHEET.findall(text)}
    assert "style.css" not in linked, (
        "embed.html now links the site stylesheet; if that is intended, this "
        "test and the inline rule should be reconsidered together"
    )
    assert FOCUS_RULE.search(text)
