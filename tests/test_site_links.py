"""No page may link to something that is not there.

A dead internal link is a small, cheap, entirely avoidable credibility
hit, and it rots in exactly the way this project keeps finding: nothing
breaks, the page still renders, and a reader clicking Methodology from
the 404 page lands on another 404.

347 references across 23 pages when this was written, none broken. The
test exists so that stays true when a page is added.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

# Fragments the href regex catches out of inline JavaScript string
# concatenation (`"<a href='" + esc(a.url) + "'>"`), not real links.
JS_ARTIFACT = re.compile(r"['\"]\s*\+|\$\d|\{|\}")

# Payloads a page fetches defensively and guards for absence. Each entry
# is a promise that the page degrades rather than breaks without it.
ALLOWED_ABSENT_FETCHES = {
    "data/multilingual.json": (
        "V5 is still backfilling; validation.html guards on falsy and "
        "leaves its section hidden"),
}


def _internal_refs(html: str) -> list[str]:
    out = []
    for m in re.finditer(r'(?:href|src)="([^"]+)"', html):
        t = m.group(1)
        if t.startswith(("http://", "https://", "#", "data:", "mailto:",
                         "//")):
            continue
        if JS_ARTIFACT.search(t):
            continue
        # Root-absolute links resolve against the site root, which is
        # docs/. The 404 page must use them: it is served from arbitrary
        # paths, so relative links there would resolve wrongly.
        target = t.split("?")[0].split("#")[0].lstrip("/")
        if target:
            out.append(target)
    return out


def test_no_page_links_to_a_missing_file():
    broken = []
    for page in sorted(DOCS.glob("*.html")):
        for target in _internal_refs(page.read_text(encoding="utf-8")):
            if not (DOCS / target).exists():
                broken.append(f"{page.name} -> {target}")
    assert not broken, f"dead internal links: {broken}"


def test_pages_only_fetch_payloads_that_exist_or_are_declared_absent():
    """A page fetching a payload that never lands renders an empty
    section forever, and nobody notices because it looks intentional."""
    missing = []
    for page in sorted(DOCS.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        for m in re.finditer(r'j\("([^"]+)"\)|fetch\("([^"]+)"', html):
            t = (m.group(1) or m.group(2) or "").split("?")[0]
            if not t or t.startswith("http") or JS_ARTIFACT.search(t):
                continue
            if (DOCS / t).exists() or t in ALLOWED_ABSENT_FETCHES:
                continue
            missing.append(f"{page.name} -> {t}")
    assert not missing, (
        f"pages fetch payloads that do not exist: {missing}. Either the "
        "lane never ran, or the path is wrong, or it belongs in "
        "ALLOWED_ABSENT_FETCHES with the reason it degrades safely.")


def test_declared_absent_fetches_carry_a_reason():
    for path, reason in ALLOWED_ABSENT_FETCHES.items():
        assert isinstance(reason, str) and len(reason) > 20, (
            f"{path} is allowed absent without a stated reason")


def test_the_404_page_uses_root_absolute_links():
    """It is served from arbitrary paths, so relative links on it would
    resolve against whatever directory the reader mistyped."""
    html = (DOCS / "404.html").read_text(encoding="utf-8")
    nav = re.findall(r'href="(/[^"]+\.html)"', html)
    assert nav, "404.html has no root-absolute navigation links"
