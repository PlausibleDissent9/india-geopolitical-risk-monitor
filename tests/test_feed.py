"""The feed is a published surface and its shape is load-bearing.

Three defects shipped together in one eight-line function and none of
them had a test: a note without a heading put its entire opening
paragraph in the title (702 characters, live in every reader), items
carried no pubDate, and descriptions sliced raw Markdown mid-word.
"""
from __future__ import annotations

import re
from pathlib import Path

from src import render_site

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "docs" / "feed.xml"

HEADLESS = {"week": "2026-W31", "markdown":
            "The largest movement in this week's data was also the "
            "easiest to misread. " + "Filler prose. " * 60}
HEADED = {"week": "2026-W32", "markdown":
          "# IGRM Weekly Assessment: Week ending 6 August 2026\n\n"
          "## Executive assessment\n\nAggregate salience eased."}


def test_a_note_without_a_heading_does_not_become_the_title():
    title = render_site._feed_title(HEADLESS)
    assert title == "2026-W31", (
        f"a headingless note produced the title {title!r} "
        f"({len(title)} chars); only a heading may become a title")


def test_a_heading_becomes_the_title_and_stays_short():
    title = render_site._feed_title(HEADED)
    assert title.startswith("2026-W32 — IGRM Weekly Assessment")
    assert len(title) <= render_site.FEED_TITLE_MAX


def test_every_item_carries_a_pubdate_dated_to_its_week():
    assert render_site._feed_pubdate("2026-W32").startswith(
        "Fri, 07 Aug 2026"), "the ISO week's Friday is the note's date"
    feed = FEED.read_text(encoding="utf-8")
    assert feed.count("<pubDate>") == feed.count("<item>"), (
        "an item without a pubDate dates itself to whenever the reader "
        "first polled")


def test_descriptions_are_prose_and_end_on_a_word():
    summary = render_site._feed_summary(HEADED["markdown"])
    assert "#" not in summary, "raw Markdown renders literally in readers"
    long = render_site._feed_summary(HEADLESS["markdown"])
    assert len(long) <= render_site.FEED_SUMMARY_MAX
    assert long.endswith("\u2026") and not long[-2].isspace()
    for desc in re.findall(r"<description>(.*?)</description>",
                           FEED.read_text(encoding="utf-8"))[1:]:
        assert "#" not in desc, "a published description carries Markdown"
