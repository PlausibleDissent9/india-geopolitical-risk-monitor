"""Static integration checks for the public World State Matrix surface."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = (DOCS / "world.html").read_text(encoding="utf-8")
JS = (DOCS / "world.js").read_text(encoding="utf-8")
CSS = (DOCS / "world.css").read_text(encoding="utf-8")


def test_world_page_has_the_institutional_shell_and_claim_boundary() -> None:
    assert '<meta http-equiv="Content-Security-Policy"' in HTML
    assert '<main id="main-content"' in HTML
    assert '<h1 id="page-title">World State Matrix</h1>' in HTML
    assert 'id="world-denominator-copy"' in HTML
    assert "Loading the validated geometry-layer denominator" in HTML
    assert "3,458 explicit geometry-layer cells" not in HTML
    assert "Search 247 members" not in HTML
    assert "not omniscience" in HTML
    assert 'href="data/world_state.json"' in HTML
    assert re.search(r'href="world\.css\?v=[0-9a-f]{8}"', HTML)
    assert re.search(r'src="world\.js\?v=[0-9a-f]{8}"', HTML)


def test_world_page_is_discoverable_without_replacing_an_atlas_route() -> None:
    catalog = json.loads(
        (ROOT / "design" / "public_product_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    routes = {row["path"] for row in catalog["routes"]}
    assert {"atlas.html", "maps.html", "world.html"} <= routes
    assert "world.html" in catalog["protected_routes"]
    assert 'href="world.html"' in (DOCS / "atlas.html").read_text(encoding="utf-8")
    assert 'href="world.html"' in (DOCS / "products.html").read_text(
        encoding="utf-8"
    )
    assert "https://igrm.in/world.html" in (DOCS / "sitemap.xml").read_text(
        encoding="utf-8"
    )


def test_runtime_validates_the_complete_denominator_before_rendering() -> None:
    for required in (
        "Matrix denominator does not reconcile",
        "Matrix identifiers are not unique",
        "Member cell partition is invalid",
        "Map geometry and matrix denominator differ",
        "Observation exists outside an observed matrix cell",
        "No partial view was rendered",
    ):
        assert required in JS
    assert 'fetch(DATA_URL, { cache: "no-store" })' in JS
    assert 'fetch(GEO_URL, { cache: "no-store" })' in JS
    assert "innerHTML" not in JS
    assert 'fetch("http' not in JS and "fetch('http" not in JS
    assert (
        'number(state.payload.denominator.cells) +\n      " explicit geometry-layer cells'
        in JS
    )
    assert (
        'number(state.payload.denominator.geometry_members) + " members"' in JS
    )


def test_world_page_supports_keyboard_search_and_reduced_motion() -> None:
    assert '<label for="world-search">' in HTML
    assert 'type="search"' in HTML
    assert 'role="listbox"' in HTML
    assert 'setAttribute("role", "option")' in JS
    assert 'button.type = "button"' in JS
    assert "prefers-reduced-motion: reduce" in CSS
    assert "overflow-x: auto" in CSS


def test_world_payload_is_stable_in_contract_and_openapi() -> None:
    contract = json.loads((DOCS / "data" / "api_contract.json").read_text())
    endpoint = next(
        row for row in contract["endpoints"] if row["path"] == "data/world_state.json"
    )
    assert endpoint["stability"] == "stable"
    assert set(endpoint["frozen_fields"]) == {
        "_meta",
        "denominator",
        "layers",
        "members",
        "observations",
        "non_country_layers",
    }
    openapi = json.loads((DOCS / "openapi.json").read_text())
    assert "/data/world_state.json" in openapi["paths"]
