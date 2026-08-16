"""No page may load executable or tracking code from another origin.

The public plane's privacy promise is that visiting igrm.in tells nobody
else you visited. That holds today: across every page, the only external
references are plain anchors -- GitHub links and two academic citations
on vs-gpr.html -- and NOTHING is fetched from another origin. A single
CDN script, webfont, analytics beacon or tracking pixel would silently
end it, which is exactly the kind of change that arrives in an unrelated
commit.

This distinguishes LOADING from LINKING. An <a href> to another site is
a link the reader chooses to follow; a <script src> or <img src> is a
request their browser makes for them, before they choose anything.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGES = sorted(DOCS.glob("*.html"))

# Tags whose src/href causes the browser to FETCH, as opposed to <a>.
LOADING = re.compile(
    r"<(script|img|iframe|link|source|video|audio|embed|object|track)\b[^>]*"
    r'(?:src|href|data)="(https?://[^"]+)"',
    re.I,
)
OWN_ORIGIN = ("igrm.in",)


def _external_loads(text: str) -> list[tuple[str, str]]:
    out = []
    for tag, url in LOADING.findall(text):
        host = url.split("/")[2].lower()
        if not any(host == o or host.endswith("." + o) for o in OWN_ORIGIN):
            out.append((tag, url))
    return out


def test_there_are_pages_to_check() -> None:
    assert len(PAGES) >= 30


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_loads_nothing_from_another_origin(page: Path) -> None:
    offenders = _external_loads(page.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{page.name} fetches from another origin before the reader chooses "
        f"to go there: {offenders}"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_page_has_no_analytics_or_beacon_hooks(page: Path) -> None:
    text = page.read_text(encoding="utf-8").lower()
    banned = [
        "google-analytics", "googletagmanager", "gtag(", "dataLayer".lower(),
        "plausible.io", "matomo", "piwik", "segment.com", "mixpanel",
        "hotjar", "fullstory", "sentry.io", "navigator.sendbeacon",
    ]
    found = [b for b in banned if b in text]
    assert not found, f"{page.name} carries analytics/beacon hooks: {found}"


def test_the_detector_actually_fires() -> None:
    # A guard that cannot fail is decoration. Prove this one distinguishes a
    # fetched subresource from a plain link.
    assert _external_loads('<script src="https://cdn.example.com/x.js"></script>')
    assert _external_loads('<img src="https://tracker.example.com/p.gif">')
    assert not _external_loads('<a href="https://github.com/whatever">link</a>')
    assert not _external_loads('<script src="app.js"></script>')
