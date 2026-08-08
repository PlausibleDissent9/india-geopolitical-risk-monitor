"""The sitemap must list the pages that exist.

It was hand-maintained and had drifted to 16 URLs against 26 pages. Ten
were missing, including `start.html` -- the page the site tells
newcomers to read first -- and `history.html`, the forty-one-year
series, which was invisible to search engines the day it shipped.

Every `lastmod` also read 2026-08-04 regardless of when the page changed,
which is worse than omitting the field: it tells a crawler nothing has
moved on a site that republishes daily.

`src/sitemap.py` derives the list from `docs/*.html` and the dates from
git. This checks the derivation is still current, so the file cannot
drift again between the day a page is added and the day someone notices.
"""

from __future__ import annotations

import re
from pathlib import Path

from src import sitemap

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITEMAP = DOCS / "sitemap.xml"


def _listed() -> set[str]:
    text = SITEMAP.read_text(encoding="utf-8")
    out = set()
    for loc in re.findall(r"<loc>([^<]+)</loc>", text):
        rel = loc.replace("https://igrm.in/", "").rstrip("/")
        out.add(rel if rel.endswith(".html") else "index.html")
    return out


def test_every_page_is_listed_or_excluded_with_a_reason():
    pages = {str(p.relative_to(DOCS)) for p in DOCS.rglob("*.html")}
    missing = pages - _listed() - set(sitemap.EXCLUDE)
    assert not missing, (
        f"pages absent from sitemap.xml and not excluded: {sorted(missing)}. "
        "A page no crawler is told about is a page nobody finds."
    )


def test_nothing_is_listed_that_does_not_exist():
    pages = {str(p.relative_to(DOCS)) for p in DOCS.rglob("*.html")}
    ghosts = _listed() - pages
    assert not ghosts, f"sitemap lists pages that do not exist: {sorted(ghosts)}"


def test_no_noindex_page_is_listed():
    noindex = {
        path.name
        for path in DOCS.glob("*.html")
        if 'name="robots" content="noindex"' in path.read_text(encoding="utf-8")
    }
    assert _listed().isdisjoint(noindex), (
        f"sitemap lists noindex pages: {sorted(_listed() & noindex)}"
    )


def test_every_listed_page_has_canonical_and_description():
    for name in _listed():
        text = (DOCS / name).read_text(encoding="utf-8")
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"\s*/?>', text)
        description = re.search(r'<meta name="description" content="([^"]+)"\s*/?>', text)
        expected = "https://igrm.in/" if name == "index.html" else f"https://igrm.in/{name}"
        assert canonical and canonical.group(1) == expected, (
            f"{name} has no exact self-canonical URL"
        )
        assert description and len(description.group(1)) >= 50, (
            f"{name} has no substantive search description"
        )


def test_exclusions_are_deliberate_and_few():
    """Same discipline as the freshness exemptions: a written reason, and
    a short list. 'It doesn't need listing' is a claim."""
    assert len(sitemap.EXCLUDE) <= 4, (
        f"{len(sitemap.EXCLUDE)} exclusions is too many to be deliberate"
    )
    for name, why in sitemap.EXCLUDE.items():
        assert len(why) > 20, f"{name} is excluded without a real reason"


def test_the_file_matches_what_the_generator_would_write():
    """The check that makes the rest meaningful: if the committed file
    and the generator disagree, someone edited the XML by hand and the
    derivation is decorative."""
    import re as _re

    def _shape(xml: str) -> list[tuple[str, str]]:
        # URLs and priorities, NOT lastmod. lastmod derives from git
        # commit dates, so byte-equality turned every commit touching a
        # page into a red CI until the file was regenerated. The daily
        # lane refreshes dates nightly; structure is the promise.
        return _re.findall(
            r"<loc>([^<]+)</loc>.*?<priority>([^<]+)</priority>", xml)

    assert _shape(SITEMAP.read_text(encoding="utf-8")) == _shape(sitemap.build()), (
        "docs/sitemap.xml's url set or priorities differ from the "
        "generator's output. Regenerate with: python -m src.sitemap"
    )


def test_lastmod_is_not_one_frozen_date_for_every_page():
    """The old file stamped every URL 2026-08-04. A crawler reading that
    concludes a daily-publishing site has stopped."""
    dates = set(re.findall(r"<lastmod>([\d-]+)</lastmod>", SITEMAP.read_text(encoding="utf-8")))
    assert dates, "no lastmod dates at all"
    # One date is legitimate only if every page really did change together.
    if len(dates) == 1:
        page_dates = {sitemap._last_commit_date(path) for path in sitemap.pages()}
        assert dates == page_dates, (
            f"every page claims lastmod {dates}, but the page histories are "
            f"{page_dates} -- the dates are frozen rather than derived"
        )
