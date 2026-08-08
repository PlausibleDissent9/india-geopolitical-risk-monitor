"""Every number on vintages.html must arrive from the payload, never the HTML.

analysis/prose_number_audit_2026-08-08.md is the record of what happens to
pages that bake their figures into prose: across the site's committed
surface it counted eight claims that were true when typed and drifted, ten
that were never true, and three that cannot be checked at all. The vintages
page is the one place that discipline matters most -- it describes the
payload whose entire warrant is exactness -- so it is built to make the
stale-prose failure impossible rather than unlikely: the prose carries NO
digits at rest, every count and date is a placeholder the page's own script
fills from data/vintages_panel.json, and these tests hold the page to that
construction.

The audit's headline example is the pair "10 of 12". Neither figure can go
stale here because neither appears in the source; the day a thirteenth
vintage publishes, the page is already correct.
"""
from __future__ import annotations

import html as html_mod
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGE = DOCS / "vintages.html"

CSP_RE = re.compile(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"')


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _prose_text() -> str:
    """The reader-facing text: the header definition plus the prose block,
    scripts excluded, tags stripped, entities normalised. The audit found
    a guard that matched plain spaces and could not see "24&nbsp;of&nbsp;29",
    so entities are decoded BEFORE any matching here."""
    page = _page()
    definition = re.search(r'<p class="definition">.*?</p>', page, re.S)
    assert definition, "the page lost its masthead definition paragraph"
    start = page.index('<div class="prose">')
    prose = page[start:page.index("<script", start)]
    text = definition.group(0) + prose
    text = re.sub(r"<[^>]+>", " ", text)
    return html_mod.unescape(text)


def test_the_page_exists_with_the_committed_shell():
    page = _page()
    canonical = re.search(r'<link rel="canonical" href="([^"]+)"\s*/?>', page)
    assert canonical and canonical.group(1) == "https://igrm.in/vintages.html", (
        "vintages.html has no exact self-canonical URL")
    description = re.search(r'<meta name="description" content="([^"]+)"\s*/?>', page)
    assert description and len(description.group(1)) >= 50, (
        "no substantive search description")
    assert '<nav class="masthead">' in page, "the shared nav shell is missing"


def test_the_csp_is_byte_identical_to_the_rest_of_the_site():
    """The self-hosted-only guarantee is a site credential, and a page
    with its own slightly different policy is a page where the guarantee
    is being renegotiated. history.html is the committed shell this page
    was built from; the two policies must be the same string."""
    ours = CSP_RE.search(_page())
    theirs = CSP_RE.search((DOCS / "history.html").read_text(encoding="utf-8"))
    assert ours and theirs, "a page lost its CSP meta"
    assert ours.group(1) == theirs.group(1), (
        "vintages.html carries a different CSP from the committed shell: "
        f"{ours.group(1)!r} vs {theirs.group(1)!r}")


def test_no_external_origin_appears_anywhere_on_the_page():
    refs = re.findall(r'(?:href|src)="(https?://[^"]+)"', _page())
    assert refs == ["https://igrm.in/vintages.html"], (
        f"vintages.html references origins beyond its own canonical: {refs}")


def test_the_page_reads_the_panel_rather_than_describing_it_from_memory():
    page = _page()
    assert re.search(r'fetch\("data/vintages_panel\.json"\)', page), (
        "the page does not fetch vintages_panel.json; whatever its prose "
        "says about the panel is a recollection, not a reading")
    assert re.search(r'fetch\("data/history\.csv"\)', page), (
        "the worked example must run the recipe against the real current "
        "file, not a paraphrase of it")


def test_the_prose_carries_no_digits_at_rest():
    """The structural immunity: not one digit in the reader-facing text
    before the script runs. Stronger than banning the audit's "12"/"10"
    by name -- a count that is not in the source cannot go stale in the
    source. The nav's "1979-2019" label sits in the header nav, outside
    prose scope, which is the only digit-bearing text the shell needs."""
    text = _prose_text()
    digits = sorted(set(re.findall(r"\d[\d.,:-]*", text)))
    assert not digits, (
        f"vintages.html hardcodes numbers in its prose: {digits}. Every "
        "figure belongs in data/vintages_panel.json, read by the page's "
        "script at render time; prose numbers are how the audit's eight "
        "stale and ten wrong claims happened.")


def test_the_audited_counts_are_not_baked_into_body_markup_or_script():
    """"10 of 12" must not hide outside the prose either -- in the inline
    script as a constant, in a table cell, in an attribute. Asset-stamp
    query strings are content hashes and may legitimately contain any
    substring, so they are stripped first."""
    page = _page()
    body = re.sub(r"\?v=[0-9a-f]{8}", "", page[page.index("<body>"):])
    for banned in ("10", "12"):
        assert banned not in body, (
            f'the vintage count "{banned}" is baked into the page body; '
            "it must be derived from the payload in JS")


def test_number_bearing_content_is_js_filled_placeholders():
    """Every placeholder is inert at rest and the script fills them all
    through one mechanism, so a typo'd key shows an em-dash rather than
    a silently wrong number."""
    page = _page()
    holders = re.findall(r'<(\w+)[^>]*data-fill="([\w-]+)"[^>]*>([^<]*)<', page)
    assert len(holders) >= 15, (
        f"only {len(holders)} data-fill placeholders found; the page has "
        "stopped sourcing its numbers from the payload")
    for _tag, key, content in holders:
        assert not re.search(r"\d", content), (
            f"placeholder {key} ships with digits in its static content "
            f"({content!r}); the payload is the only permitted source")
    script = page[page.index("<script", page.index("<body>")):]
    assert "data-fill" in script and "querySelectorAll" in script, (
        "the inline script no longer fills the data-fill placeholders")


def test_the_recipe_is_quoted_from_the_payload_not_restated():
    """The three-step recipe is displayed verbatim from _meta.reconstruction.
    A hand-typed copy would be the exact second-copy failure the audit
    catalogued, on the sentence least able to afford it."""
    page = _page()
    assert re.search(r'data-fill="recipe"', page), (
        "the recipe placeholder is gone")
    assert "_meta.reconstruction" in page, (
        "the script no longer quotes the payload's own reconstruction rule")
    assert "last_observation and d not in absent_days" not in page, (
        "the reconstruction rule is baked into the page; it must be read "
        "from the payload so the quote cannot drift from the source")


def test_the_vintage_table_is_empty_at_rest():
    assert re.search(r'<table id="vintages">.*?<tbody>\s*</tbody>', _page(), re.S), (
        "the vintages table ships with static rows; rows must be rendered "
        "from the payload at load time")


def test_the_page_is_listed_in_the_sitemap():
    text = (DOCS / "sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://igrm.in/vintages.html</loc>" in text, (
        "vintages.html is not in sitemap.xml; regenerate with: "
        "python -m src.sitemap")


def test_the_page_has_contextual_inbound_links():
    """A sitemap entry is crawlability, not human discoverability."""
    linkers = []
    for path in sorted(DOCS.glob("*.html")):
        if path == PAGE:
            continue
        if re.search(r'href="vintages\.html"',
                     path.read_text(encoding="utf-8")):
            linkers.append(path.name)
    assert {"data.html", "start.html"} <= set(linkers), (
        "the point-in-time panel must be reachable from both the data "
        f"catalogue and researcher onboarding; current linkers: {linkers}")


def test_no_forecast_language():
    """Same rule as history.html, with its lesson kept: only phrases that
    cannot appear in honest prose are banned, because a disclaimer about
    forecasting would trip anything broader."""
    page = _page().lower()
    for banned in ("we forecast", "predicts that"):
        assert banned not in page, f"forecast language on vintages.html: {banned}"
