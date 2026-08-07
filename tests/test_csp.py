"""The self-hosted-only guarantee, enforced rather than remembered.

The strict CSP is treated as a credential in this project: no external
script, stylesheet, font or image, ever. That promise is easy to keep
by intention and easy to break by one convenient CDN link added in a
hurry at 2am. So it is a test.

Measured when written: 23 pages, all with a CSP, zero external resource
references anywhere.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"

CSP_RE = re.compile(
    r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"')

# Pages allowed to open a connection off-origin, each with the reason
# and the host. connect-src only -- never script-src, never style-src.
ALLOWED_CONNECT: dict[str, dict[str, str]] = {
    "index.html": {
        "hosts": "https://buttondown.com https://formsubmit.co",
        "why": ("the subscribe form posts to the newsletter provider; "
                "the visitor initiates it and no third-party code runs"),
    },
    "portal.html": {
        "hosts": "https://api.github.com",
        "why": ("author-only writing tool: not in the nav, not in the "
                "sitemap, linked only from write.html, so no reader's "
                "browser reaches GitHub from this site"),
    },
}


def _pages() -> list[Path]:
    return sorted(DOCS.glob("*.html"))


def test_every_page_declares_a_csp():
    missing = [p.name for p in _pages()
               if not CSP_RE.search(p.read_text(encoding="utf-8"))]
    assert not missing, f"pages served with no CSP: {missing}"


def test_no_page_permits_an_external_script_or_style_source():
    """script-src and style-src must never name a remote host. This is
    the line that keeps a CDN out of the site forever."""
    bad = []
    for p in _pages():
        m = CSP_RE.search(p.read_text(encoding="utf-8"))
        if not m:
            continue
        for directive in ("script-src", "style-src", "font-src",
                          "default-src"):
            d = re.search(rf"{directive} ([^;]+)", m.group(1))
            if d and "http" in d.group(1):
                bad.append(f"{p.name}: {directive} {d.group(1).strip()}")
    assert not bad, f"CSP permits remote code or styling: {bad}"


def test_off_origin_connections_are_declared_with_a_reason():
    undeclared = []
    for p in _pages():
        m = CSP_RE.search(p.read_text(encoding="utf-8"))
        if not m:
            continue
        d = re.search(r"connect-src ([^;]+)", m.group(1))
        if not d or "http" not in d.group(1):
            continue
        if p.name not in ALLOWED_CONNECT:
            undeclared.append(f"{p.name}: {d.group(1).strip()}")
    assert not undeclared, (
        "pages connect off-origin without a declared reason: "
        f"{undeclared}. Add it to ALLOWED_CONNECT with the host and why, "
        "or remove the connection.")


def test_declared_connections_still_match_the_page():
    """A declaration must describe the page as it is now, not as it was
    when someone wrote the exemption."""
    for name, spec in ALLOWED_CONNECT.items():
        page = DOCS / name
        if not page.exists():
            continue
        m = CSP_RE.search(page.read_text(encoding="utf-8"))
        assert m, f"{name} lost its CSP"
        d = re.search(r"connect-src ([^;]+)", m.group(1))
        assert d, f"{name} no longer declares connect-src"
        for host in spec["hosts"].split():
            assert host in d.group(1), (
                f"{name} no longer connects to {host}; the exemption is "
                "stale and should be narrowed or removed")
        assert len(spec["why"]) > 30, f"{name} exemption has no real reason"


def test_no_html_references_an_external_resource():
    """The CSP is the policy; this is the practice. Both, because a
    stray CDN link would be blocked at runtime and still tells us the
    discipline slipped."""
    ext = []
    for p in _pages():
        html = p.read_text(encoding="utf-8")
        for m in re.finditer(r'<script[^>]+src="(https?://[^"]+)"', html):
            ext.append(f"{p.name}: script {m.group(1)}")
        for m in re.finditer(r'<link[^>]+href="(https?://[^"]+)"', html):
            rel = re.search(r'rel="([^"]+)"', m.group(0))
            if rel and rel.group(1) in ("stylesheet", "preconnect",
                                        "preload"):
                ext.append(f"{p.name}: {rel.group(1)} {m.group(1)}")
        for m in re.finditer(r'<img[^>]+src="(https?://[^"]+)"', html):
            ext.append(f"{p.name}: img {m.group(1)}")
    assert not ext, f"external resources referenced: {ext}"
