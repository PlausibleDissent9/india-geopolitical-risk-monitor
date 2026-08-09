"""The public site is one system across every committed route."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from src import render_site, site_shell, stamp_assets

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

EXPECTED_LAYOUTS = {
    "article": {
        "break.html",
        "codebook.html",
        "corrections.html",
        "dna.html",
        "history.html",
        "methodology.html",
        "notes.html",
        "research/forecasts.html",
        "replay.html",
        "research/history.html",
        "sensors.html",
        "shock.html",
        "standard.html",
        "vintages.html",
        "vs-gpr.html",
    },
    "dashboard": {
        "analysis.html",
        "atlas.html",
        "explorer.html",
        "maps.html",
        "validation.html",
        "workbench.html",
        "products.html",
        "world.html",
    },
    "evidence": {
        "divergence.html",
        "episode.html",
        "exposure.html",
        "predictions.html",
        "receipts.html",
    },
    "onboarding": {"ask.html", "portal.html", "start.html", "write.html"},
    "system": {"404.html", "api.html", "data.html", "status.html", "viewer.html"},
}


class StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def count(self, tag: str | None = None, *, id_: str | None = None) -> int:
        return sum(
            1
            for found_tag, attrs in self.tags
            if (tag is None or found_tag == tag) and (id_ is None or attrs.get("id") == id_)
        )

    def has_class(self, class_name: str) -> bool:
        return any(class_name in (attrs.get("class") or "").split() for _, attrs in self.tags)


def _parse(relative: str) -> tuple[str, StructureParser]:
    text = (DOCS / relative).read_text(encoding="utf-8")
    parser = StructureParser()
    parser.feed(text)
    return text, parser


def test_all_public_routes_have_an_owned_layout() -> None:
    routes = {str(path.relative_to(DOCS)) for path in DOCS.rglob("*.html")}
    assert len(routes) == 39
    expected_shell = set().union(*EXPECTED_LAYOUTS.values())
    assert set(site_shell.PAGES) == expected_shell
    assert routes == expected_shell | {"index.html", "embed.html"}
    for layout, members in EXPECTED_LAYOUTS.items():
        assert {
            relative for relative, page in site_shell.PAGES.items() if page.layout == layout
        } == members


def test_every_shell_route_has_one_semantic_shell() -> None:
    for relative, page in site_shell.PAGES.items():
        text, parser = _parse(relative)
        assert parser.has_class("site-page"), relative
        assert parser.has_class(f"layout-{page.layout}"), relative
        assert parser.has_class("site-masthead"), relative
        assert parser.has_class("skip-link"), relative
        assert parser.has_class("site-footer"), relative
        assert parser.count("h1") == 1, relative
        assert parser.count("main") == 1, relative
        assert parser.count(id_="theme-toggle") == 1, relative
        assert 'id="main-content"' in text, relative
        assert "data-latest-date" in text, relative
        assert re.search(
            r'<script src="(?:\.\./|/)?site\.js\?v=[0-9a-f]{8}"></script>',
            text,
        ), relative
        assert "<style>" not in text, relative
        if page.layout == "article":
            assert "data-page-toc" in text, relative


def test_shell_preserves_page_header_runtime_targets() -> None:
    viewer, parser = _parse("viewer.html")
    assert parser.count(id_="filedesc") == 1
    assert 'document.getElementById("filedesc")' in viewer


def test_theme_boot_precedes_shared_interaction_on_every_route() -> None:
    boot = 'document.documentElement.dataset.theme = localStorage.igrmTheme || "dark"'
    for relative in site_shell.PAGES:
        text = (DOCS / relative).read_text(encoding="utf-8")
        assert text.count(boot) == 1, relative
        assert text.index(boot) < text.index("site.js?v="), relative


def test_shell_render_is_idempotent_after_asset_stamping() -> None:
    for relative in site_shell.PAGES:
        current = (DOCS / relative).read_text(encoding="utf-8")
        assert site_shell.render_text(relative, current) == current, relative


def test_every_removed_inline_selector_exists_in_shared_css() -> None:
    assert set(site_shell.MIGRATED_INLINE_STYLE_HASHES) == set(site_shell.MIGRATED_INLINE_SELECTORS)
    assert site_shell.migrated_selector_gaps() == {}


def test_home_owns_the_north_star_shell_and_embed_owns_the_exception() -> None:
    home, home_parser = _parse("index.html")
    assert home_parser.has_class("masthead")
    assert home_parser.has_class("brand")
    assert home_parser.count("h1") == 1
    assert home_parser.count("main") == 1
    assert home_parser.count(id_="theme-toggle") == 1
    assert "site.js" not in home

    embed, embed_parser = _parse("embed.html")
    assert not embed_parser.has_class("site-masthead")
    assert embed_parser.count("main") == 0
    assert "tokens.css?v=" in embed and "fonts.css?v=" in embed
    assert 'id="t" role="status" aria-live="polite"' in embed


def test_embed_describes_each_construct_in_its_own_units() -> None:
    embed = (DOCS / "embed.html").read_text(encoding="utf-8")
    assert 'what === "gauge"' in embed
    assert "validation_status" in embed
    assert "headline_eligible" in embed
    assert "daily 0–100 weighted salience-and-stress gauge" in embed
    assert "daily tape; ${units}; salience, not risk" in embed
    assert "payload._meta" in embed
    assert "percentile of trailing 2y; salience, not risk" not in embed


def test_generator_runs_shell_after_content_and_before_asset_stamping() -> None:
    source = Path(render_site.__file__).read_text(encoding="utf-8")
    assert source.index("render_home()") < source.index("render_all()")
    assert "site.js" in stamp_assets.ASSETS


def test_shared_system_covers_deep_links_states_and_print() -> None:
    css = (DOCS / "site.css").read_text(encoding="utf-8")
    js = (DOCS / "site.js").read_text(encoding="utf-8")
    for contract in (
        ":target",
        ".skip-link",
        '[aria-busy="true"]',
        '[role="alert"]',
        "@media print",
        "CanvasText",
        "@media (max-width: 640px)",
    ):
        assert contract in css
    assert "heading.id = candidate" in js
    assert "time.dateTime = latest.date" in js
    assert 'cache: "no-store"' in js
    assert "-webkit-line-clamp" not in css
