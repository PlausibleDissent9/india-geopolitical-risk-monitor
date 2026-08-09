"""Generate sitemap.xml from the pages that exist, not from memory.

The sitemap was hand-maintained and had drifted to 16 URLs against 26
pages. Ten were missing, including `start.html` -- the page the site
tells newcomers to read first -- and `history.html`, the forty-one-year
series, which is the largest substantive artifact here and was invisible
to search engines the day it shipped.

Every `lastmod` also read 2026-08-04 regardless of when the page last
changed, which is worse than omitting the field: it tells a crawler
nothing has moved on a site that republishes daily.

Same failure as everything else this week -- a second copy of a fact,
maintained by hand, drifting from the first. So the list is derived from
`docs/*.html` and the dates come from git.

EXCLUSIONS carry a reason, and the list is short by design.

  python -m src.sitemap            write docs/sitemap.xml
  python -m src.sitemap --check    exit 1 if it is out of date
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITEMAP = DOCS / "sitemap.xml"
BASE = "https://igrm.in/"

# Pages a crawler should not index, each with the reason.
EXCLUDE: dict[str, str] = {
    "404.html": "the not-found page; indexing it puts an error in results",
    "embed.html": (
        "an iframe widget meant to be embedded in someone else's page, not landed on directly"
    ),
    "portal.html": "a private operational portal marked noindex and blocked in robots.txt",
    "write.html": "an authenticated author console marked noindex",
}

# Rough priority: the instrument first, then the documents that explain
# it, then everything else. Crawlers treat this as a hint, not a ranking.
PRIORITY: dict[str, str] = {
    "index.html": "1.0",
    "start.html": "0.9",
    "atlas.html": "0.9",
    "ledger.html": "0.8",
    "methodology.html": "0.9",
    "codebook.html": "0.9",
    "history.html": "0.8",
    "validation.html": "0.8",
    "data.html": "0.8",
    # The vintages panel is the one asset a later entrant cannot rebuild
    # after the fact; its page ranks with the data surfaces it explains.
    "vintages.html": "0.8",
    # The ask surface is the front door for non-technical readers.
    "ask.html": "0.8",
}


def _last_commit_date(path: Path) -> str:
    """When the page actually changed, per git. Falls back to today in a
    shallow checkout, which is honest -- a wrong-but-recent date is
    better than every page claiming the same stale day."""
    out = subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return out or date.today().isoformat()


def pages() -> list[Path]:
    # rglob, not glob: docs/research/*.html shipped invisible to this
    # generator (and to stamp_assets, and to three tests) because every
    # one of them looked only at the top level. Indexable, canonical,
    # absent from the sitemap, and orphaned -- found by the site audit
    # on 2026-08-07. One directory of depth defeated five checks.
    return sorted(p for p in DOCS.rglob("*.html")
                  if str(p.relative_to(DOCS)) not in EXCLUDE)


def build() -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for p in pages():
        rel = str(p.relative_to(DOCS))
        loc = BASE if rel == "index.html" else BASE + rel
        lastmod = _last_commit_date(p)
        prio = PRIORITY.get(rel, "0.5")
        lines.append(
            f"  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod><priority>{prio}</priority></url>"
        )
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def main() -> None:
    want = build()
    check = "--check" in sys.argv
    have = SITEMAP.read_text(encoding="utf-8") if SITEMAP.exists() else ""

    if check:
        if want != have:
            raise SystemExit(
                "[sitemap] docs/sitemap.xml is out of date. Regenerate with: python -m src.sitemap"
            )
        print(f"[sitemap] current ({len(pages())} pages)")
        return

    SITEMAP.write_text(want, encoding="utf-8")
    print(
        f"[sitemap] wrote {len(pages())} urls "
        f"({len(EXCLUDE)} excluded: {', '.join(sorted(EXCLUDE))})"
    )


if __name__ == "__main__":
    main()
