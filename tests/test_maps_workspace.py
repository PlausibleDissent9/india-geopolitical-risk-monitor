"""The Atlas map is an evidence workspace, not a decorative choropleth.

These checks lock the product and truth boundaries that are easiest to
erase during a redesign: self-hosted inputs, accessible non-map controls,
deep-linkable state, refusal of partial payloads, and explicit non-claims.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = (DOCS / "maps.html").read_text(encoding="utf-8")
JS = (DOCS / "maps.js").read_text(encoding="utf-8")
CSS = (DOCS / "maps.css").read_text(encoding="utf-8")


def test_maps_workspace_is_the_primary_interactive_surface() -> None:
    assert 'id="map-studio"' in HTML
    assert 'id="atlas-map"' in HTML
    assert 'id="map-inspector-title"' in HTML
    assert 'id="map-ranking-body"' in HTML
    assert 'id="map-layer-title"' in HTML
    assert '<template id="legacy-map-reference">' in HTML
    assert 'id="legacy-maps"' not in HTML


def test_maps_assets_are_external_and_content_versioned() -> None:
    assert re.search(r'href="maps\.css\?v=[0-9a-f]{8}"', HTML)
    assert re.search(r'src="maps\.js\?v=[0-9a-f]{8}"', HTML)
    assert "https://" not in CSS
    assert "http://" not in CSS
    assert "https://" not in JS
    assert JS.count("http://") == 1
    assert '"http://www.w3.org/2000/svg"' in JS


def test_maps_load_only_the_seven_registered_public_inputs() -> None:
    expected = {
        "geo/world.json",
        "data/map_relations.json",
        "geo/india.json",
        "data/map_states.json",
        "data/latest.json",
        "data/episodes.json",
        "data/status.json",
    }
    declared = set(re.findall(r'"((?:geo|data)/[^"]+\.json)"', JS))
    assert declared == expected
    for relative in expected:
        assert (DOCS / relative).is_file(), relative


def test_maps_refuse_partial_or_structurally_invalid_payloads() -> None:
    assert "Published map payload shape is invalid" in JS
    assert "meta.partial !== false" in JS
    assert "map metadata is missing or invalid" in JS
    assert "map row has invalid values" in JS
    assert "map row has no registered geometry" in JS
    assert "Map unavailable · payload refused" in JS
    assert "No map ranking is rendered when a required payload fails" in JS
    assert "Published operational payload shape is invalid" in JS
    assert "Operational context unavailable · payload refused" in JS


def test_observation_room_adds_workspaces_command_search_and_truth_panels() -> None:
    for capability in (
        'data-map-mission="partner"',
        'data-map-mission="border"',
        'data-map-mission="states"',
        'data-map-mission="audit"',
        'id="map-command-dialog"',
        'data-inspector-tab="selection"',
        'data-inspector-tab="episodes"',
        'data-inspector-tab="evidence"',
        'id="map-pulse-channels"',
        'id="map-lane-health"',
        'id="map-alignment-note"',
    ):
        assert capability in HTML
    for behavior in (
        "applyMission",
        "showInspectorTab",
        "commandCatalog",
        "showModal",
        'event.key.toLowerCase() === "k"',
        "validLatest",
        "validEpisodes",
        "validStatus",
    ):
        assert behavior in JS


def test_observation_room_never_labels_published_context_as_live_intelligence() -> None:
    page = HTML.lower()
    assert "observation room" in page
    assert "published observation mode" in page
    assert "not risk" in page
    assert "live intelligence" not in page
    assert "real-time intelligence" not in page
    assert "ai confidence" not in page


def test_recent_rankings_apply_the_same_sparse_data_floor_as_the_map() -> None:
    assert 'state.window !== "recent" || eventValue(entry[1]) >= 50' in JS


def test_maps_support_investigation_without_pointer_only_access() -> None:
    for capability in (
        'role="tablist"',
        'type="search"',
        'data-map-metric="conflict"',
        'data-map-window="recent"',
        'data-map-zoom="in"',
        "URLSearchParams",
        "history.replaceState",
        'event.key === "ArrowRight"',
        'event.key === "Enter"',
    ):
        assert capability in HTML + JS
    assert "Use search or the ranked table as accessible alternatives" in HTML


def test_maps_publish_observations_without_inventing_exposure_or_causation() -> None:
    page = HTML.lower()
    assert "counts and shares, never causes" in page
    assert "not a risk league table" in page
    assert "no port×commodity cells or paths exist" in page
    assert "no production source currently authorizes" in page
    assert "rights pending" in page
    assert "atlas · live observations" not in page
    assert ">live<" not in page
    assert "real-time" not in page


def test_phone_layout_is_edge_to_edge_without_forcing_page_overflow() -> None:
    assert "@media (max-width: 760px)" in CSS
    assert ".map-studio { width: 100vw; border-inline: 0; border-radius: 0; }" in CSS
    assert "max-width: 100%; overflow-x: auto" in CSS
    assert "touch-action: none" in CSS
    assert "prefers-reduced-motion: reduce" in CSS
