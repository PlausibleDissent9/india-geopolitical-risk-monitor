"""A page that builds itself in the browser still owes a reader the data.

WHAT WAS WRONG
Measured across every route on 2026-08-09, five pages rendered
essentially nothing without JavaScript and offered no fallback at all:

    episode.html    23 characters
    notes.html      23
    receipts.html   24
    viewer.html     76
    ask.html       276

notes.html was worse than blank. Its static markup asserted "No notes
published yet." while two notes were published -- a page that lies
rather than one that is empty, linked from the site footer and pointed
at by the RSS feed's own <link>.

This is not a hypothetical reader. It is also every fetch that runs no
JavaScript, and every moment the payload request fails: the same markup
is what a reader sees when the network drops the JSON.

THE RULE
A route may build its view in the browser. It may not leave a reader
with nothing and no route to the same material. Each of the five now
carries a <noscript> naming the exact published payload behind the view,
because "enable JavaScript" is a demand, and a link is an answer.

WHAT THIS DOES NOT CLAIM
It measures characters, not usefulness -- it cannot tell a real fallback
from 400 characters of apology. It is a floor that catches the failure
that actually happened (a blank page shipping unnoticed), not a
substitute for looking at the page.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Entered by the server, by an embed, or by a direct hand-off -- never by
# a reader clicking a link. Same set the sitemap generator excludes.
NOT_READER_FACING = {"404.html", "embed.html", "portal.html", "write.html"}

# Below this, the content region is a spinner and a heading. Chosen from
# the measured distribution: the five failures sat at 23-276 characters
# and the next page up was 440, so the line is drawn where the data
# already separates rather than at a round number.
MIN_CHARS = 300


def _content_region(text: str) -> str:
    """Only the page's own content: the shared shell is on every route
    and would mask an empty page with a masthead and a footer."""
    text = re.sub(r"<script\b.*?</script>", "", text, flags=re.S | re.I)
    text = re.sub(r"<style\b.*?</style>", "", text, flags=re.S | re.I)
    text = re.sub(r".*<!--site-shell:content-start-->", "", text, flags=re.S)
    text = re.sub(r"<!--site-shell:content-end-->.*", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _routes() -> list[Path]:
    return [p for p in sorted(DOCS.glob("*.html"))
            if p.name not in NOT_READER_FACING]


def test_no_route_is_blank_without_javascript() -> None:
    blank = []
    for path in _routes():
        seen = _content_region(path.read_text(encoding="utf-8"))
        if len(seen) < MIN_CHARS:
            blank.append(f"{path.name}: {len(seen)} chars")
    assert not blank, (
        "these routes show a reader with no JavaScript almost nothing, and "
        "no <noscript> pointing at the published data:\n  "
        + "\n  ".join(blank))


def test_the_measure_ignores_the_shared_shell() -> None:
    """Guard the guard.

    If the content-region markers ever move, _content_region falls back
    to the whole document, every page clears MIN_CHARS on masthead and
    footer alone, and this file silently stops testing anything.
    """
    sample = (DOCS / "notes.html").read_text(encoding="utf-8")
    assert "<!--site-shell:content-start-->" in sample, (
        "the shell markers moved; _content_region now measures the whole "
        "page, including the masthead and footer every route shares, and "
        "would pass a completely empty content region")
    assert "India Geopolitical Risk Monitor" not in _content_region(sample), (
        "the footer brand leaked into the measured region")


def test_notes_does_not_claim_there_are_no_notes() -> None:
    """The specific lie, kept as its own assertion.

    A generic length check would have passed a page whose fallback text
    was the false sentence itself.
    """
    text = (DOCS / "notes.html").read_text(encoding="utf-8")
    assert "No notes published yet" not in text, (
        "notes.html states that no notes are published; without "
        "JavaScript that is what every reader is told, whatever "
        "data/notes.json actually contains")
