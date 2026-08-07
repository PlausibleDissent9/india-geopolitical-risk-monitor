"""
Static-page rendering that must never generate prose:

  - docs/methodology.html  CONVERTED from methodology.md (markdown lib);
  - docs/data/notes.json   the notes/*.md archive, newest first;
  - docs/feed.xml          RSS for the notes archive.

The words in all three come from files the author wrote. This module
formats; it does not write.

Called from run_daily's publish step; standalone: python -m src.render_site
"""
from __future__ import annotations

import email.utils
import json
import time
from pathlib import Path
from xml.sax.saxutils import escape

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE_DATA = DOCS / "data"
NOTES_DIR = ROOT / "notes"

SITE_URL = "https://igrm.in"

PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — India Geopolitical Risk Monitor</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{site}/{slug}.html">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%2312233D'/%3E%3Ctext x='16' y='23' font-family='Georgia' font-size='19' font-weight='bold' fill='%23FAFAF7' text-anchor='middle'%3EIG%3C/text%3E%3C/svg%3E">
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'">
<script>document.documentElement.dataset.theme = localStorage.igrmTheme || "dark";</script>
<link rel="stylesheet" href="site.css">
</head>
<body>
<header>
  <h1><a href="./">India Geopolitical Risk Monitor</a></h1>
  <nav class="masthead">
    <a href="start.html">Start here</a>
    <a href="methodology.html"{cur_meth}>Methodology</a>
    <a href="validation.html">Validation</a>
    <a href="analysis.html">Analysis</a>
    <a href="history.html">1979&ndash;2019</a>
    <a href="maps.html">Maps</a>
    <a href="data.html"{cur_data}>Data</a>
    <a href="notes.html">Notes</a>
    <a href="divergence.html">Divergence</a>
  </nav>
</header>
<div class="prose">
{body}
</div>
<footer>
  <p><a href="./">&larr; back to the index</a> &middot; <a href="validation.html">validation results</a></p>
  <p>Association, not causation. Not investment advice.</p>
</footer>
</body>
</html>
"""


def _render_md_page(src, slug: str, title: str, description: str) -> None:
    # fenced_code matters more than it looks. Without it the converter
    # emitted the ``` markers as literal paragraphs AND parsed the "#"
    # comment lines inside a fence as H1 headings -- which is exactly
    # what the codebook's Researcher quick-start had been rendering as:
    # stray backticks around five giant headings, on the one section a
    # new user reads first. Found 2026-08-07.
    body = markdown.markdown(src.read_text(encoding="utf-8"),
                             extensions=["tables", "fenced_code"])
    (DOCS / f"{slug}.html").write_text(
        PAGE_SHELL.format(
            site=SITE_URL, body=body, slug=slug, title=title,
            description=description,
            cur_meth=' class="current"' if slug == "methodology" else "",
            cur_data=' class="current"' if slug == "codebook" else "",
        ),
        encoding="utf-8",
    )
    print(f"[render] wrote docs/{slug}.html (converted, not generated)")


def render_methodology() -> None:
    _render_md_page(
        ROOT / "methodology.md", "methodology", "Methodology",
        "Full methodology for the IGRM salience index: construct "
        "definition, term selection, normalization, episode detection, "
        "event-study design, limitations, and validation.",
    )
    _render_md_page(
        DOCS / "codebook.md", "codebook", "Codebook",
        "Column-by-column definitions, units, and construction for every "
        "IGRM data file.",
    )
    _render_md_page(
        DOCS / "corrections.md", "corrections", "Corrections",
        "Every error this project caught, dated, with the fix that keeps "
        "the class from recurring. Append-only.",
    )


def _notes() -> list[dict]:
    out = []
    for p in sorted(NOTES_DIR.glob("*.md"), reverse=True):
        if p.name.endswith(".example"):
            continue
        out.append({"week": p.stem, "markdown": p.read_text(encoding="utf-8")})
    return out


def render_notes() -> None:
    notes = _notes()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "notes.json").write_text(
        json.dumps(notes, separators=(",", ":")), encoding="utf-8"
    )

    now = email.utils.formatdate(time.time())
    items = []
    for n in notes:
        first_line = n["markdown"].strip().splitlines()[0].lstrip("# ").strip() \
            if n["markdown"].strip() else n["week"]
        items.append(
            "<item>"
            f"<title>{escape(n['week'] + ' — ' + first_line)}</title>"
            f"<link>{SITE_URL}/notes.html#{escape(n['week'])}</link>"
            f"<guid isPermaLink=\"false\">igrm-note-{escape(n['week'])}</guid>"
            f"<description>{escape(n['markdown'][:400])}</description>"
            "</item>"
        )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>IGRM weekly notes</title>"
        f"<link>{SITE_URL}/notes.html</link>"
        "<description>Weekly analytical notes on the India Geopolitical "
        "Risk Monitor</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + "".join(items) +
        "</channel></rss>"
    )
    (DOCS / "feed.xml").write_text(feed, encoding="utf-8")
    print(f"[render] wrote notes.json ({len(notes)} notes) and feed.xml")


def render_home() -> None:
    """Bake today's numbers into index.html at publish time, so crawlers,
    link previews, and no-JS readers see real data, not placeholders.
    The page's JavaScript re-renders the same values on load; this is the
    static floor beneath it."""
    import re

    latest_path = SITE_DATA / "latest.json"
    if not latest_path.exists():
        return
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    if latest.get("composite") is None:
        return
    hist = json.loads((SITE_DATA / "history.json").read_text(encoding="utf-8"))

    def delta(series):
        vals = [v for v in series if v is not None]
        return round(vals[-1] - vals[-2], 1) if len(vals) >= 2 else None

    def arrow(d):
        if d is None:
            return ""
        glyph = "▲" if d > 0.05 else ("▼" if d < -0.05 else "·")
        return f"{glyph} {d:+.1f}"

    idx_path = DOCS / "index.html"
    s = idx_path.read_text(encoding="utf-8")
    s = re.sub(r'(<span id="latest-date">)[^<]*(</span>)',
               rf"\g<1>{latest['date']}\g<2>", s, count=1)
    s = re.sub(r'(<p class="big-number" id="composite-score"[^>]*>)[^<]*(</p>)',
               rf"\g<1>{(latest.get('composite7') if latest.get('composite7') is not None else latest['composite']):.1f}\g<2>", s, count=1)
    s = re.sub(r'(<p class="delta" id="composite-delta">).*?(</p>)',
               rf"\g<1>{arrow(delta(hist.get('composite7') or hist['composite']))} vs yesterday\g<2>",
               s, count=1)
    s = re.sub(r'(<p class="asof" id="asof">)[^<]*(</p>)',
               rf"\g<1>Showing {latest['date']}, the most recent completed news day. "
               rf"Today's number publishes after the day ends; pipeline last ran "
               rf"{latest['_meta']['generated']}.\g<2>",
               s, count=1)
    row_parts = []
    for k, c in latest.get("channels", {}).items():
        score = "" if c["score"] is None else f"{c['score']:.1f}"
        d = arrow(delta(hist["channels"].get(k, [])))
        row_parts.append(
            f'\n      <a class="component-row" href="receipts.html?channel={k}">'
            f'<span class="component-name">{escape(c["label"])}</span>'
            f'<span class="component-score">{score}</span>'
            f'<span class="component-delta">{d}</span></a>'
        )
    rows = "".join(row_parts)
    s = re.sub(r"<!--ssr:components-->.*?<!--/ssr:components-->",
               f"<!--ssr:components-->{rows}\n    <!--/ssr:components-->",
               s, flags=re.S, count=1)
    idx_path.write_text(s, encoding="utf-8")
    print("[render] baked today's numbers into index.html (static floor)")


def main() -> None:
    render_methodology()
    render_notes()
    render_home()


if __name__ == "__main__":
    main()
