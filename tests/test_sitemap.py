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
        name = loc.rstrip("/").rsplit("/", 1)[-1]
        out.add(name if name.endswith(".html") else "index.html")
    return out


def test_every_page_is_listed_or_excluded_with_a_reason():
    pages = {p.name for p in DOCS.glob("*.html")}
    missing = pages - _listed() - set(sitemap.EXCLUDE)
    assert not missing, (
        f"pages absent from sitemap.xml and not excluded: {sorted(missing)}. "
        "A page no crawler is told about is a page nobody finds."
    )


def test_nothing_is_listed_that_does_not_exist():
    pages = {p.name for p in DOCS.glob("*.html")}
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
    assert SITEMAP.read_text(encoding="utf-8") == sitemap.build(), (
        "docs/sitemap.xml differs from what src/sitemap.py generates. "
        "Regenerate with: python -m src.sitemap"
    )


def test_lastmod_is_not_one_frozen_date_for_every_page():
    """The old file stamped every URL 2026-08-04. A crawler reading that
    concludes a daily-publishing site has stopped."""
    dates = set(re.findall(r"<lastmod>([\d-]+)</lastmod>", SITEMAP.read_text(encoding="utf-8")))
    assert dates, "no lastmod dates at all"
    # One date is legitimate only if every page really did change together.
    if len(dates) == 1:
        import subprocess

        changed = subprocess.run(
            ["git", "log", "-1", "--format=%ad", "--date=short"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert dates == {changed}, (
            f"every page claims lastmod {dates}, which matches no recent "
            "commit -- the dates are frozen rather than derived"
        )
