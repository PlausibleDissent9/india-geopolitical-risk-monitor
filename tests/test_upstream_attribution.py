"""A page that uses GDELT must credit GDELT, with the link its terms name.

WHAT HAPPENED (found 2026-08-17, by an adversarial rights review)

The GDELT Project places exactly one condition on its data, and it is not
onerous:

    any use or redistribution of the data must include a citation to the
    GDELT Project and a link to this website (https://www.gdeltproject.org/)

IGRM is a public index built primarily on GDELT. Measured at the time
this file was written:

    docs/codebook.html      named GDELT 27 times, linked it 0 times
    docs/codebook.md        27 / 0
    docs/methodology.html   14 / 0
    published payloads      17 derived from GDELT, 2 carried the link

So the single obligation attached to the project's main data source was
unmet on the pages a reviewer opens first. Nothing failed, because
nothing checked. It is the same shape as everything else found this week:
a promise made in one place and never verified anywhere.

The condition says "any USE", not "any redistribution", so naming GDELT
as a source is itself the trigger. That is the rule enforced here: a
public page that names GDELT must also carry the link.

NOT enforced here, deliberately: per-payload attribution in every
`_meta` block. That is a stricter posture and a defensible one, but it
would rewrite the bytes of every published payload and cascade into the
byte manifest, so it belongs in its own change with its own review rather
than being smuggled in behind a documentation fix.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

REQUIRED_LINK = "gdeltproject.org"

# Pages that are generated snapshots of machine output rather than prose
# a reader is meant to consult for provenance. They name GDELT because
# they report on it, and each already carries its own _meta attribution
# path; requiring the marketing-style credit inside them would be noise.
NOT_PROSE = {"404.html", "sitemap.xml"}


def _prose_pages() -> list[Path]:
    out = []
    for path in sorted(DOCS.glob("*.html")) + sorted(DOCS.glob("*.md")):
        if path.name in NOT_PROSE:
            continue
        out.append(path)
    return out


def _names_gdelt(text: str) -> bool:
    return re.search(r"\bGDELT\b", text) is not None


def test_some_public_page_actually_uses_gdelt():
    """Guard the guard.

    If the corpus stops naming GDELT entirely -- a rename, a rewrite --
    every assertion below would pass by matching nothing, and the
    obligation would quietly stop being checked.
    """
    naming = [p.name for p in _prose_pages() if _names_gdelt(p.read_text(encoding="utf-8"))]
    assert naming, (
        "no public page names GDELT any more; either the corpus moved or "
        "this check has gone vacuous")


def _actually_links_gdelt(page: str, text: str) -> bool:
    """A LINK, not a string that contains the domain.

    The first version asserted `"gdeltproject.org" in text`, and that was
    too weak in the way that matters. docs/codebook.html is GENERATED
    from codebook.md, whose source carried the URL as bare prose; the
    renderer emitted it as plain text, and the substring check passed on
    a page where the required link did not exist. The terms say "a link
    to this website". Plain text is not a link.
    """
    if page.endswith(".md"):
        return f"]({URL})" in text or f"]({URL[:-1]})" in text
    return f'<a href="{URL}"' in text or f"<a href='{URL}'" in text


URL = "https://www.gdeltproject.org/"


@pytest.mark.parametrize("page", [p.name for p in _prose_pages()])
def test_a_page_that_names_gdelt_also_links_it(page):
    text = (DOCS / page).read_text(encoding="utf-8")
    if not _names_gdelt(text):
        return
    assert REQUIRED_LINK in text, (
        f"docs/{page} names GDELT but does not link {REQUIRED_LINK}. The "
        "GDELT terms require a citation AND a link to that site for any "
        "USE of the data, not merely for redistribution, so naming it as "
        "a source is what triggers the obligation. Add the attribution "
        "rather than removing the mention.")
    assert _actually_links_gdelt(page, text), (
        f"docs/{page} mentions {REQUIRED_LINK} but never as a LINK -- no "
        f"anchor to {URL} in HTML, no markdown link in .md. The terms ask "
        "for a link, and a bare URL in prose is not one. If this page is "
        "generated, fix the SOURCE it renders from: a hand-added anchor "
        "in generated HTML is deleted by the next regeneration, which is "
        "exactly how this check came to be written.")


def test_the_codebook_carries_the_condition_verbatim():
    """The codebook is the canonical data document, so the obligation is
    quoted there rather than paraphrased -- a paraphrase drifts, and a
    reader inheriting the data needs the actual wording to know that it
    binds them too."""
    text = (DOCS / "codebook.html").read_text(encoding="utf-8")
    assert "citation to the" in text and "GDELT Project" in text, (
        "the codebook no longer quotes GDELT's attribution condition")
    assert "https://www.gdeltproject.org/" in text, (
        "the codebook no longer carries the exact link the terms name")
