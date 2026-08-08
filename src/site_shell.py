"""Apply the shared institutional shell to every public HTML route.

The repository deliberately keeps hand-authored static pages. This module
does not generate their prose or analytical content; it wraps that content in
one navigational, accessibility, freshness, and footer system. It runs after
the markdown pages are converted, so the three regenerated pages cannot drift
back to the legacy text-link header overnight.

Standalone: python -m src.site_shell
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

CONTENT_START = "<!--site-shell:content-start-->"
CONTENT_END = "<!--site-shell:content-end-->"
FOOTER_START = "<!--site-shell:footer-start-->"
FOOTER_END = "<!--site-shell:footer-end-->"


@dataclass(frozen=True)
class Page:
    title: str
    section: str
    layout: str
    active: str = ""
    drop_duplicate_heading: bool = False


# Every shell-bearing public route appears exactly once. index.html owns the
# north-star homepage shell; embed.html is an iframe surface and adopts the
# tokens without importing the full navigation chrome.
PAGES: dict[str, Page] = {
    "404.html": Page("Page not found", "System", "system"),
    "analysis.html": Page("Analysis", "Research", "dashboard", "analysis"),
    "api.html": Page("API contract", "Data infrastructure", "system", "data"),
    "ask.html": Page("Ask IGRM", "Evidence access", "onboarding", "start"),
    "break.html": Page("Break this index", "Accountability", "article", "methodology", True),
    "codebook.html": Page("Codebook", "Reference", "article", "data", True),
    "corrections.html": Page("Corrections", "Accountability", "article", "methodology", True),
    "data.html": Page("Data", "Open infrastructure", "system", "data"),
    "divergence.html": Page("Divergence register", "Evidence", "evidence", "analysis"),
    "episode.html": Page("Episode detail", "Evidence", "evidence", "analysis"),
    "explorer.html": Page("Outcomes explorer", "Research", "dashboard", "analysis"),
    "exposure.html": Page("Your exposure", "Evidence utility", "evidence", "start", True),
    "history.html": Page("1979–2019 historical proxy", "Research", "article", "analysis"),
    "maps.html": Page("Maps", "Research", "dashboard", "analysis"),
    "methodology.html": Page("Methodology", "Method", "article", "methodology", True),
    "notes.html": Page("Weekly notes", "Research notes", "article", "notes"),
    "portal.html": Page("Author portal", "Operations", "onboarding"),
    "predictions.html": Page("Prediction archive", "Evidence", "evidence", "analysis"),
    "receipts.html": Page("Receipts", "Evidence", "evidence"),
    "research/forecasts.html": Page("Forecast experiment (V11)", "Research", "article", "analysis", True),
    "research/history.html": Page("Historical attention proxy, 1979–2019", "Research", "article", "analysis", True),
    "start.html": Page("Start here", "Orientation", "onboarding", "start"),
    "standard.html": Page("Open evidence standard", "Interoperability", "article", "methodology"),
    "status.html": Page("System status", "Operations", "system", "data", True),
    "validation.html": Page("Validation", "Evidence", "dashboard", "validation"),
    "viewer.html": Page("Data viewer", "Data infrastructure", "system", "data"),
    "vintages.html": Page("Point-in-time vintages", "Research record", "article", "analysis"),
    "vs-gpr.html": Page("IGRM and the GPR indices", "Research", "article", "analysis"),
    "workbench.html": Page("Research workbench", "Research infrastructure", "dashboard", "analysis"),
    "write.html": Page("Author console", "Operations", "onboarding"),
}


# Inline style blocks were ten independent mini-systems. Each one was moved
# into site.css before removal. Hashes make that migration fail closed: if a
# page-local rule changes later, this renderer refuses to delete the new CSS
# until the shared sheet and the selector inventory are updated together.
MIGRATED_INLINE_STYLE_HASHES: dict[str, str] = {
    "404.html": "6971ad3bdc90b8289dfae06773bf53ec6a9a3c13ea176f9ab2e6f2925ac9bfcb",
    "ask.html": "9d2e15c62123f2157ec46bc0e4ec78a8212921adeceae212af5118844f41cdff",
    "break.html": "c47661d6f23c9b80d07a73046863515290ae6c2f2bfbed8cb3bfa60859a122d1",
    "exposure.html": "2772ace6696e79c9fcd75c0c4c6d9798a3837d27e8053011d9780d2f32318cc3",
    "portal.html": "56f6e34a4a02faefe42e9c4737aff8435e865b948e258e5484a2a769b17e1612",
    "research/forecasts.html": "ab71d2d8f006fe595c31dd643510d464d944530e656922865ce288a4e2c26f9e",
    "research/history.html": "aa6e81bbc6cbd01cb25edeca19683b6a2e286089d0ec92365855f1276be24b41",
    "start.html": "f0a6c9c74849270881e140a240f9d45b62e53afb7a5b0cd2feba7f1b354624ac",
    "status.html": "8122ce2801de98bd2c78bc8b9314cfa57e7b740506d2d7ee3ca98cbc8db0e0cf",
    "viewer.html": "e30b7074800295b2edcb075009cf0c83d887024d86884bde6a3395064a32bb93",
}

MIGRATED_INLINE_SELECTORS: dict[str, tuple[str, ...]] = {
    "404.html": (".nf", ".nf .code", ".nf ul", ".nf li"),
    "ask.html": (
        "#chat-log", ".msg", ".msg.you", ".msg.igrm", ".msg.igrm.refused",
        ".msg details", "#ask-row", "#ask-input", ".chip",
    ),
    "break.html": (".falsify", ".falsify h3", ".falsify p", ".falsify .how"),
    "exposure.html": (
        ".hardline", ".sector-grid", ".sector-chip", ".sector-chip.on",
        ".sector-chip b", ".sector-chip .why", ".reading-card",
        ".reading-card h4", ".reading-card .score", ".reading-card .band",
        ".reading-card .wt", ".compute", ".compute td", ".compute th",
        ".tblwrap", "#profile-empty",
    ),
    "portal.html": (
        ".tabs", ".tab", ".tab.on", ".panel", ".row",
        'input[type="password"]', 'input[type="text"]', "textarea",
        "textarea:focus", "input:focus", ".btn.primary", ".status",
        ".scorecards", ".sc", ".sc .v", ".sc a", ".labelcard",
        ".labelcard .t", ".labelbtns", ".labelbtns .btn", ".on-b",
        ".off-b", ".health-grid", ".prose-mini h1", ".prose-mini h2",
        ".prose-mini", ".pill", ".pill.ok", ".pill.bad",
    ),
    "research/forecasts.html": (
        ".mandate", ".q-table", ".q-table th", ".q-table td", ".tblwrap",
        ".brier-strip", ".brier-strip b", ".brier-strip .kv",
    ),
    "research/history.html": (
        ".mandate", ".h-table", ".h-table th", ".h-table td", ".hit",
        ".miss", ".tblwrap", ".chart-wrap",
    ),
    "start.html": (
        ".start-hero", ".start-hero h2", ".start-hero .lede", ".start-live",
        ".start-live b", ".paths", ".path", ".path h3", ".path p",
        ".ninety li", ".instrument li", ".path:hover",
    ),
    "status.html": (
        ".status-table", ".status-table th", ".status-table td",
        ".status-table td.num", ".ok-yes", ".ok-no", ".tblwrap",
        ".contract-strip", ".contract-strip b", ".contract-strip .kv",
        ".role-note",
    ),
    "viewer.html": (
        ".meta-box", ".meta-box b", ".kvt td:first-child", ".section-block",
        ".truncated",
    ),
}


BODY_RE = re.compile(r"<body(?:\s[^>]*)?>(.*?)</body>", re.S)
HEADER_RE = re.compile(r"^\s*<header(?:\s[^>]*)?>(.*?)</header>\s*", re.S)
FOOTER_RE = re.compile(r"\s*<footer(?:\s[^>]*)?>(.*?)</footer>\s*", re.S)
DEFINITION_RE = re.compile(
    r'<p(?P<attrs>[^>]*\bclass="(?:definition|page-deck)"[^>]*)>'
    r'(?P<content>.*?)</p>',
    re.S,
)
STYLE_RE = re.compile(r"\s*<style>.*?</style>\s*", re.S)
SITE_JS_RE = re.compile(
    r'\s*<script src="(?P<src>(?:\.\./|/)?site\.js(?:\?v=[0-9a-f]{8})?)"></script>\s*'
)


def css_selectors(css: str) -> set[str]:
    """Return normalized selectors from the simple route-local CSS subset."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    selectors: set[str] = set()
    for raw in re.findall(r"([^{}]+)\{", css):
        raw = raw.strip()
        if raw.startswith("@"):
            continue
        for selector in raw.split(","):
            normalized = " ".join(selector.split())
            if normalized:
                selectors.add(normalized)
    return selectors


def migrated_selector_gaps() -> dict[str, list[str]]:
    shared = css_selectors((DOCS / "site.css").read_text(encoding="utf-8"))
    return {
        relative: sorted(set(selectors) - shared)
        for relative, selectors in MIGRATED_INLINE_SELECTORS.items()
        if set(selectors) - shared
    }


def _remove_migrated_styles(relative: str, text: str) -> str:
    blocks = re.findall(r"<style>(.*?)</style>", text, flags=re.S)
    if not blocks:
        return text
    expected_hash = MIGRATED_INLINE_STYLE_HASHES.get(relative)
    if expected_hash is None or len(blocks) != 1:
        raise ValueError(
            f"docs/{relative} has an inline style block that is not in the "
            "shared-CSS migration register"
        )
    digest = hashlib.sha256(blocks[0].encode()).hexdigest()
    if digest != expected_hash:
        raise ValueError(
            f"docs/{relative} inline CSS changed after migration inventory; "
            "update site.css, its selector coverage, and the hash together"
        )
    found = css_selectors(blocks[0])
    expected = set(MIGRATED_INLINE_SELECTORS[relative])
    if found != expected:
        raise ValueError(
            f"docs/{relative} selector inventory is incomplete: "
            f"missing={sorted(found - expected)}, stale={sorted(expected - found)}"
        )
    gaps = set(expected) - css_selectors(
        (DOCS / "site.css").read_text(encoding="utf-8")
    )
    if gaps:
        raise ValueError(
            f"docs/{relative} selectors were not migrated to site.css: "
            f"{sorted(gaps)}"
        )
    return STYLE_RE.sub("\n", text)


def _root_prefix(relative: str) -> str:
    if relative == "404.html":
        return "/"
    return "../" if "/" in relative else ""


def _href(prefix: str, target: str) -> str:
    if target == "index.html":
        return prefix or "./"
    return prefix + target


def _current(active: str, key: str) -> str:
    return ' class="current"' if active == key else ""


def _masthead(page: Page, prefix: str) -> str:
    home = _href(prefix, "index.html")
    return f"""<header class="masthead site-masthead">
  <div class="site-shell nav-shell">
    <a class="brand" href="{home}" aria-label="IGRM home">
      <span class="brand-mark" aria-hidden="true">IG</span>
      <span class="brand-copy"><strong>IGRM</strong><small>Public research instrument</small></span>
    </a>
    <nav class="mast-links" aria-label="Primary navigation">
      <a href="{_href(prefix, 'start.html')}"{_current(page.active, 'start')}>Start here</a>
      <a href="{_href(prefix, 'methodology.html')}"{_current(page.active, 'methodology')}>Methodology</a>
      <a href="{_href(prefix, 'validation.html')}"{_current(page.active, 'validation')}>Validation</a>
      <a href="{_href(prefix, 'analysis.html')}"{_current(page.active, 'analysis')}>Research</a>
      <a href="{_href(prefix, 'notes.html')}"{_current(page.active, 'notes')}>Notes</a>
    </nav>
    <div class="nav-actions">
      <a class="data-cta{(' current' if page.active == 'data' else '')}" href="{_href(prefix, 'data.html')}">Open data <span aria-hidden="true">↗</span></a>
      <button id="theme-toggle" class="theme-btn" type="button" aria-label="Switch to light theme">Light</button>
    </div>
  </div>
</header>"""


def _page_heading(
    page: Page, prefix: str, definition: str, definition_id: str
) -> str:
    id_attr = f' id="{escape(definition_id)}"' if definition_id else ""
    deck = (
        f'\n      <p class="page-deck"{id_attr}>{definition.strip()}</p>'
        if definition.strip() or definition_id
        else ""
    )
    return f"""<section class="page-heading" aria-labelledby="page-title">
    <div class="page-heading-copy">
      <p class="page-kicker">{escape(page.section)}</p>
      <h1 id="page-title">{escape(page.title)}</h1>{deck}
    </div>
    <dl class="page-meta" aria-label="Publication context">
      <div><dt>Data day</dt><dd data-latest-date>See latest published payload</dd></div>
      <div><dt>Freshness</dt><dd><a href="{_href(prefix, 'status.html')}">Source-by-source status</a></dd></div>
    </dl>
  </section>"""


def _footer(prefix: str, original: str) -> str:
    context = original.strip() or "<p>Association, not causation. Not investment advice.</p>"
    return f"""<footer class="site-footer">
    <div class="footer-context">
      {FOOTER_START}
      {context}
      {FOOTER_END}
    </div>
    <div class="footer-grid">
      <div>
        <a class="footer-brand" href="{_href(prefix, 'index.html')}">India Geopolitical Risk Monitor</a>
        <p>Public research instrument · India-specific press salience</p>
      </div>
      <nav aria-label="Footer navigation">
        <a href="{_href(prefix, 'methodology.html')}">Methodology</a>
        <a href="{_href(prefix, 'validation.html')}">Validation</a>
        <a href="{_href(prefix, 'history.html')}">1979&ndash;2019 history</a>
        <a href="{_href(prefix, 'data.html')}">Data</a>
        <a href="{_href(prefix, 'corrections.html')}">Corrections</a>
      </nav>
    </div>
  </footer>"""


def _definition_parts(match: re.Match[str] | None) -> tuple[str, str]:
    if not match:
        return "", ""
    id_match = re.search(r'\bid="([^"]+)"', match.group("attrs"))
    return match.group("content"), id_match.group(1) if id_match else ""


def _extract_existing(body: str) -> tuple[str, str, str, str]:
    """Return content, footer HTML, page definition, and definition id."""
    if CONTENT_START in body and CONTENT_END in body:
        content = body.split(CONTENT_START, 1)[1].split(CONTENT_END, 1)[0].strip()
        footer = ""
        if FOOTER_START in body and FOOTER_END in body:
            footer = body.split(FOOTER_START, 1)[1].split(FOOTER_END, 1)[0].strip()
        definition, definition_id = _definition_parts(DEFINITION_RE.search(body))
        return content, footer, definition, definition_id

    header_match = HEADER_RE.match(body)
    definition = ""
    definition_id = ""
    if header_match:
        definition, definition_id = _definition_parts(
            DEFINITION_RE.search(header_match.group(1))
        )
        body = body[header_match.end():]

    footer_match = FOOTER_RE.search(body)
    footer = footer_match.group(1) if footer_match else ""
    if footer_match:
        body = body[:footer_match.start()] + body[footer_match.end():]

    # ask.html and divergence.html already had a main landmark. The new
    # shell owns the single landmark, so unwrap only a leading legacy one.
    if re.match(r"^\s*<main(?:\s[^>]*)?>", body):
        body = re.sub(r"^\s*<main(?:\s[^>]*)?>", "", body, count=1)
        body = body.replace("</main>", "", 1)
    return body.strip(), footer.strip(), definition, definition_id


def _drop_duplicate_heading(content: str, title: str) -> str:
    """Let the shell own h1 without breaking a pre-existing deep link."""
    title_text = re.sub(r"\s+", " ", title).strip()
    pattern = re.compile(
        r"(?P<prefix>^\s*(?:<div class=\"prose\">\s*)?)"
        r"<(?P<tag>h[12])(?P<attrs>\s[^>]*)?>(?P<title>.*?)</(?P=tag)>",
        re.S,
    )
    match = pattern.search(content)
    if not match:
        return content
    candidate = re.sub(r"<[^>]+>", "", match.group("title"))
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if match.group("tag") != "h1" and candidate.casefold() != title_text.casefold():
        return content
    anchor = ""
    id_match = re.search(r'\bid="([^"]+)"', match.group("attrs") or "")
    if id_match:
        anchor = (
            f'<span id="{escape(id_match.group(1))}" class="anchor-target" '
            'aria-hidden="true"></span>'
        )
    return (
        content[:match.start()]
        + match.group("prefix")
        + anchor
        + content[match.end():]
    )


class _ShellAuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1_count = 0
        self.main_count = 0
        self.theme_toggle_count = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag == "h1":
            self.h1_count += 1
        elif tag == "main":
            self.main_count += 1
        if dict(attrs).get("id") == "theme-toggle":
            self.theme_toggle_count += 1


def _audit_shell(relative: str, body: str) -> None:
    parser = _ShellAuditParser()
    parser.feed(body)
    if parser.h1_count != 1:
        raise ValueError(
            f"docs/{relative} shell must contain exactly one parsed h1; "
            f"found {parser.h1_count}"
        )
    if parser.main_count != 1:
        raise ValueError(
            f"docs/{relative} shell must contain exactly one main landmark; "
            f"found {parser.main_count}"
        )
    if parser.theme_toggle_count != 1:
        raise ValueError(
            f"docs/{relative} shell must contain exactly one theme-toggle id; "
            f"found {parser.theme_toggle_count}"
        )


def render_text(relative: str, text: str) -> str:
    page = PAGES[relative]
    prefix = _root_prefix(relative)
    script_match = SITE_JS_RE.search(text)
    script_src = script_match.group("src") if script_match else _href(prefix, "site.js")
    text = SITE_JS_RE.sub("\n", text)
    text = _remove_migrated_styles(relative, text)

    body_match = BODY_RE.search(text)
    if not body_match:
        raise ValueError(f"docs/{relative} has no body")
    content, original_footer, definition, definition_id = _extract_existing(
        body_match.group(1)
    )
    if page.drop_duplicate_heading:
        content = _drop_duplicate_heading(content, page.title)

    if page.layout == "article":
        content_frame = f"""<div class="article-grid">
    <aside class="reading-rail" aria-label="On this page">
      <p class="rail-label">On this page</p>
      <nav data-page-toc><a href="#main-content">Overview</a></nav>
    </aside>
    <main id="main-content" class="page-content" tabindex="-1">
      {CONTENT_START}
      {content}
      {CONTENT_END}
    </main>
  </div>"""
    else:
        content_frame = f"""<main id="main-content" class="page-content" tabindex="-1">
    {CONTENT_START}
    {content}
    {CONTENT_END}
  </main>"""

    body = f"""<body class="site-page layout-{page.layout}" data-page="{escape(relative)}" data-root="{escape(prefix or '.')}">
<a class="skip-link" href="#main-content">Skip to content</a>
{_masthead(page, prefix)}
<div class="site-shell page-frame">
  {_page_heading(page, prefix, definition, definition_id)}
  {content_frame}
  {_footer(prefix, original_footer)}
</div>
<script src="{script_src}"></script>
</body>"""
    _audit_shell(relative, body)
    return text[:body_match.start()] + body + text[body_match.end():]


def render_all() -> list[str]:
    changed: list[str] = []
    for relative in PAGES:
        path = DOCS / relative
        current = path.read_text(encoding="utf-8")
        rendered = render_text(relative, current)
        if rendered != current:
            path.write_text(rendered, encoding="utf-8")
            changed.append(relative)
    return changed


def main() -> None:
    changed = render_all()
    print(f"[site_shell] applied shared shell to {len(PAGES)} routes; "
          f"{len(changed)} files changed")


if __name__ == "__main__":
    main()
