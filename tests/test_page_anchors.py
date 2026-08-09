"""A deep link must land on something.

WHAT WAS WRONG
`tests/test_page_reachability.py` checks that every page is reachable from
some other page, and deliberately strips the fragment when it does:

    HREF = re.compile(r'href="([^"#?]*\\.html|\\./|/)(?:[?#][^"]*)?"')

So `methodology.html#splice-audit` counted as a link to methodology.html
and nothing checked the anchor. On 2026-08-09 a scan of all 39 pages found
four dead ones, and they were not obscure:

  * index.html's calibration notice -- the homepage, in the paragraph
    telling a reader to check the audit before using bridge-period levels
    -- linked methodology.html#splice-audit, which resolved nowhere. It
    also called the target an "audit table"; the target is prose.
  * methodology.html linked #changelog twice, once from its own opening
    line ("changelog at the end"), and had no id="changelog".
  * codebook.html#historical-intelligence, linked from the new History
    Lab page.

The common cause: `src/render_site.py` converted markdown with only
`tables` and `fenced_code`, so the generated pages carried NO heading ids
at all. Every deep link into methodology, codebook or corrections was
dead by construction, and nothing said so. attr_list is now enabled and
the anchors are written explicitly.

WHY EXPLICIT IDS, NOT `toc`
The `toc` extension slugifies heading text automatically, which means
rewording a heading silently breaks every link into it -- the same defect
in a new costume. An explicit `{#anchor}` breaks loudly, here.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

HREF = re.compile(r'href="([^"]*)#([^"]+)"')
ID = re.compile(r'\bid="([^"]+)"')
NAME = re.compile(r'\bname="([^"]+)"')
# Script bodies build hrefs by concatenation -- receipts.html#" + esc(ch) +
# " is a template, not a link. Reading them as static links reports
# nonsense, so they are removed before scanning.
SCRIPT = re.compile(r"<script\b.*?</script>", re.S | re.I)

# Anchors created at RUNTIME, with the mechanism that creates them. An
# entry here is a claim that the anchor exists for a reader with
# JavaScript, and it has to name where. It is not a place to park a
# broken link.
RUNTIME_ANCHORS = {
    # notes.html renders the archive client-side from notes.json and sets
    # `sec.id = n.week` per note, so #2026-W32 resolves once the page
    # runs. The RSS feed's <link> uses the same form.
    "notes.html": re.compile(r"^\d{4}-W\d{2}$"),
}


def _pages() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(DOCS.glob("*.html"))}


def _anchors(text: str) -> set[str]:
    return set(ID.findall(text)) | set(NAME.findall(text))


def _broken() -> list[str]:
    pages = _pages()
    anchors = {name: _anchors(text) for name, text in pages.items()}
    bad: list[str] = []
    for name, text in pages.items():
        for target, frag in HREF.findall(SCRIPT.sub("", text)):
            if target.startswith(("http://", "https://", "mailto:", "data:")):
                continue
            page = name if target == "" else target.split("/")[-1]
            if not page.endswith(".html"):
                continue
            if page not in pages:
                bad.append(f"{name} -> {target}#{frag}: no such page")
                continue
            if frag in anchors[page]:
                continue
            runtime = RUNTIME_ANCHORS.get(page)
            if runtime is not None and runtime.match(frag):
                continue
            bad.append(f'{name} -> {target}#{frag}: no id="{frag}" in {page}')
    return bad


def test_every_internal_fragment_link_resolves() -> None:
    bad = _broken()
    assert not bad, "dead deep links:\n  " + "\n  ".join(bad)


def test_the_generated_pages_carry_heading_anchors() -> None:
    """The root cause, asserted directly.

    If attr_list is dropped from src/render_site.py the fragment scan
    above still passes for any page nobody deep-links yet, and the next
    anchor written into markdown silently renders as literal text.
    """
    meth = (DOCS / "methodology.html").read_text(encoding="utf-8")
    assert 'id="changelog"' in meth, (
        "methodology.html has no changelog anchor, so its own opening "
        "line links to nothing")
    assert "{#" not in meth, (
        "an attr_list anchor rendered as literal text, which means the "
        "extension is not enabled in src/render_site.py")


def test_runtime_anchor_allowances_are_still_needed() -> None:
    """An allowance that has become unnecessary must not linger.

    A stale entry here would hide a real dead link later, which is how
    the pending-orphan list in test_page_reachability.py is guarded too.
    """
    pages = _pages()
    for page in RUNTIME_ANCHORS:
        assert page in pages, f"{page} no longer exists; drop its allowance"
        assert "<script" in pages[page], (
            f"{page} no longer runs any script, so it cannot be creating "
            "anchors at runtime; drop its allowance and add real ids")
