"""Every reader-facing page must be reachable by clicking.

test_site_links.py checks the outbound direction: no page links to
something that is not there. Nothing checked the inbound direction, and
that gap has now shipped twice. history.html -- the biggest substantive
artifact on the site -- went live linked from nothing at all, which
test_history_page.py records and pins for that one page. ask.html did
the same on 2026-08-08: in the sitemap, styled, working, and reachable
only by typing the URL.

A page in the sitemap is findable by a crawler. A page nobody links is
not findable by a reader, and the difference is the whole point of
publishing it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# Pages that are correctly unlinked, each with the reason. These are the
# same four the sitemap generator excludes: entered by the server, by an
# embed, or by a direct hand-off, never by a click from another page.
NOT_LINKED_BY_DESIGN = {
    # The sitemap generator's EXCLUDE set: entered by the server, by an
    # embed, or by a direct hand-off, never by a click.
    "404.html": "served by the host on a missing path, never linked",
    "embed.html": "loaded in an iframe by third-party embedders",
    "portal.html": "handed to specific reviewers by URL",
    "write.html": "internal drafting surface, deliberately unadvertised",
    # The forecast experiment's separation rule is REGISTERED and
    # load-bearing: tests/test_forecasts.py asserts "research/forecasts"
    # never appears in index.html, so the experiment cannot be mistaken
    # for the instrument. Unlinked here is the rule working, not a
    # defect -- and this guard would otherwise pressure someone to
    # "fix" it by breaking the separation.
    "predictions.html": "V11 experiment, separated from front surfaces by registration",
    "research/forecasts.html": "V11 experiment, same registered separation",
}

# Pages that SHOULD be linked and are not yet, with the date and the
# owner of the fix. This list must shrink; a stale entry fails below.
# The product directory now makes every intended public capability reachable.
ORPHANS_PENDING: dict[str, str] = {}

# Query strings and fragments are real links: episode.html?ep=... and
# viewer.html#ch are how two pages are entered. An earlier version of
# this pattern dropped them and reported both as orphans.
HREF = re.compile(r'href="([^"#?]*\.html|\./|/)(?:[?#][^"]*)?"')


def _pages() -> dict[str, Path]:
    return {p.relative_to(DOCS).as_posix(): p for p in DOCS.rglob("*.html")}


def _inbound() -> dict[str, set[str]]:
    """Who links to whom, resolved relative to the linking page."""
    pages = _pages()
    inbound: dict[str, set[str]] = {name: set() for name in pages}
    for name, path in pages.items():
        here = Path(name).parent
        for href in HREF.findall(path.read_text(encoding="utf-8")):
            if href.startswith(("http://", "https://", "//")):
                continue
            if href in ("./", "/"):
                target = "index.html"
            elif href.startswith("/"):
                target = href.lstrip("/")
            else:
                target = (here / href).as_posix()
            target = Path(target).as_posix().replace("../", "")
            if target in inbound and target != name:
                inbound[target].add(name)
    return inbound


def _exempt(name: str) -> bool:
    """Match on the full docs-relative path or the bare filename, so a
    page in a subdirectory (research/forecasts.html) can be named either
    way in the lists above."""
    return any(key in (name, Path(name).name)
               for key in (*NOT_LINKED_BY_DESIGN, *ORPHANS_PENDING))


def test_every_reader_facing_page_is_linked_from_somewhere():
    inbound = _inbound()
    assert len(inbound) >= 20, (
        f"only {len(inbound)} pages found; the page scan went blind and "
        "an empty set would pass this test vacuously")
    orphans = sorted(
        name for name, sources in inbound.items()
        if not sources and not _exempt(name))
    assert not orphans, (
        f"pages nobody links to: {orphans}. A page in the sitemap is "
        "findable by a crawler; a page nobody links is not findable by a "
        "reader. Add a link, or add the page to NOT_LINKED_BY_DESIGN "
        "with the reason it is entered another way.")


def test_a_pending_orphan_leaves_the_list_once_it_is_linked():
    """The failure mode of any exemption list: the thing gets fixed and
    the entry stays, quietly excusing the next page that ships unlinked."""
    inbound = _inbound()
    linked = sorted(
        name for name in ORPHANS_PENDING
        if any(name in (k, Path(k).name) and v for k, v in inbound.items()))
    assert not linked, (
        f"these pages are now linked and must leave ORPHANS_PENDING: "
        f"{linked}")


def test_the_sitemap_exclusions_are_all_accounted_for_here():
    """Every page the sitemap refuses to advertise must appear in the
    by-design set, so the two lists cannot drift apart silently. The
    reverse does not hold: the forecast pages ARE in the sitemap and are
    unlinked for a different, registered reason."""
    from src.sitemap import EXCLUDE
    missing = {e for e in EXCLUDE
               if (e if e.endswith(".html") else f"{e}.html")
               not in NOT_LINKED_BY_DESIGN}
    assert not missing, (
        f"src/sitemap.py excludes {sorted(missing)} but this guard does "
        "not explain why they are unlinked")
