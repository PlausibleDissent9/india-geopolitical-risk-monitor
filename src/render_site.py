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

SITE_URL = "https://igrm.indiconomics.com"

PAGE_SHELL = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Methodology — India Geopolitical Risk Monitor</title>
<meta name="description" content="Full methodology for the IGRM salience index: construct definition, term selection, normalization, episode detection, event-study design, limitations, and validation.">
<link rel="canonical" href="{site}/methodology.html">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%238a3324'/%3E%3Ctext x='16' y='23' font-family='Georgia' font-size='19' font-weight='bold' fill='white' text-anchor='middle'%3EIG%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="site.css">
</head>
<body>
<header>
  <h1><a href="./">India Geopolitical Risk Monitor</a></h1>
  <nav class="masthead">
    <a href="methodology.html" class="current">Methodology</a>
    <a href="validation.html">Validation</a>
    <a href="data.html">Data</a>
    <a href="notes.html">Notes</a>
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


def render_methodology() -> None:
    md_text = (ROOT / "methodology.md").read_text(encoding="utf-8")
    body = markdown.markdown(md_text, extensions=["tables"])
    (DOCS / "methodology.html").write_text(
        PAGE_SHELL.format(site=SITE_URL, body=body), encoding="utf-8"
    )
    print("[render] wrote docs/methodology.html (converted, not generated)")


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


def main() -> None:
    render_methodology()
    render_notes()


if __name__ == "__main__":
    main()
