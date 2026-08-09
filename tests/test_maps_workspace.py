"""The Atlas map is an evidence workspace, not a decorative choropleth.

These checks lock the product and truth boundaries that are easiest to
erase during a redesign: self-hosted inputs, accessible non-map controls,
deep-linkable state, refusal of partial payloads, and explicit non-claims.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = (DOCS / "maps.html").read_text(encoding="utf-8")
JS = (DOCS / "maps.js").read_text(encoding="utf-8")
REPLAY_JS = (DOCS / "maps_replay.js").read_text(encoding="utf-8")
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
    assert re.search(r'src="maps_replay\.js\?v=[0-9a-f]{8}"', HTML)
    assert "https://" not in CSS
    assert "http://" not in CSS
    assert "https://" not in JS
    assert JS.count("http://") == 1
    assert '"http://www.w3.org/2000/svg"' in JS
    assert "https://" not in REPLAY_JS
    assert "http://" not in REPLAY_JS


def test_maps_load_only_the_twelve_registered_public_inputs() -> None:
    expected = {
        "geo/world.json",
        "data/map_relations.json",
        "geo/india.json",
        "data/map_states.json",
        "data/latest.json",
        "data/episodes.json",
        "data/status.json",
        "data/chokepoints.json",
        "geo/chokepoints.json",
        "data/history.json",
        "data/receipts_archive.json",
        "geo/channel_anchors.json",
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
    assert "Published maritime anchor geometry or projection contract is invalid" in JS
    assert "Published maritime observation manifest is partial, unaligned, or missing provenance" in JS
    assert "Maritime evidence unavailable · manifest refused" in JS
    assert "The rest of Atlas remains available" in JS


def test_observation_room_adds_workspaces_command_search_and_truth_panels() -> None:
    for capability in (
        'data-map-mission="partner"',
        'data-map-mission="border"',
        'data-map-mission="states"',
        'data-map-mission="audit"',
        'data-map-mission="maritime"',
        'data-map-mission="replay"',
        'id="map-command-dialog"',
        'data-inspector-tab="selection"',
        'data-inspector-tab="maritime"',
        'data-inspector-tab="replay"',
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
        "validMaritimeGeometry",
        "validMaritimeObservations",
        "hasJointObservation",
        "initializeMaritime",
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


def test_maritime_monitor_is_replayable_but_never_a_disruption_claim() -> None:
    for capability in (
        'id="map-chokepoint-layer"',
        'id="map-chokepoint-time"',
        'id="map-chokepoint-play"',
        'id="map-maritime-source-salience"',
        'id="map-maritime-source-transits"',
        'id="map-maritime-rights"',
        "Monday-labelled published observations",
        "missing weeks remain gaps",
    ):
        assert capability in HTML
    page = HTML.lower()
    assert "not a measured supply disruption" in page
    assert "not a disruption or causal estimate" in JS.lower()
    assert "no joint observation" in JS.lower()
    assert "does not interpolate or carry values forward" in JS


def test_maritime_anchor_registry_matches_the_active_world_projection() -> None:
    anchors = json.loads((DOCS / "geo/chokepoints.json").read_text(encoding="utf-8"))
    world = json.loads((DOCS / "geo/world.json").read_text(encoding="utf-8"))
    assert anchors["_meta"]["partial"] is False
    assert set(anchors["chokepoints"]) == {"hormuz", "bab_el_mandeb", "suez", "malacca"}
    assert anchors["_meta"]["projection_id"] == world["_meta"]["projection_id"]
    assert anchors["_meta"]["world_view_box"] == world["viewBox"]
    assert anchors["_meta"]["longitude_domain"] == world["_meta"]["longitude_domain"]
    assert anchors["_meta"]["latitude_domain"] == world["_meta"]["latitude_domain"]
    for point in anchors["chokepoints"].values():
        assert anchors["_meta"]["longitude_domain"][0] <= point["longitude"] <= anchors["_meta"]["longitude_domain"][1]
        assert anchors["_meta"]["latitude_domain"][0] <= point["latitude"] <= anchors["_meta"]["latitude_domain"][1]
    assert "not boundaries, route geometries, or exposure estimates" in anchors["_meta"]["what"]
    assert "1000" not in re.sub(r'payload\._meta\.world_view_box !== worldGeometry\.viewBox', "", JS)


def test_maritime_manifest_freezes_sources_rights_cadence_and_joint_denominators() -> None:
    payload = json.loads((DOCS / "data/chokepoints.json").read_text(encoding="utf-8"))
    meta = payload["_meta"]
    assert meta["partial"] is False
    assert meta["knowledge_cutoff"] <= meta["generated"]
    assert "Monday-labelled" in meta["week_rule"]
    assert "never interpolated" in meta["week_rule"]
    assert re.fullmatch(r"[0-9a-f]{64}", meta["transform"]["implementation_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", meta["transform"]["dictionary_sha256"])
    assert re.fullmatch(r"[0-9a-f]{64}", meta["rights_registry_sha256"])
    for source in meta["source_vintages"].values():
        assert re.fullmatch(r"[0-9a-f]{64}", source["input_sha256"])
        assert source["rights"]["decision_state"] in {"review_required", "approved"}
        assert source["rights"]["decision_id"]
    assert set(payload["chokepoints"]) == {"hormuz", "bab_el_mandeb", "suez", "malacca"}
    for row in payload["chokepoints"].values():
        assert row["n_weeks"] == row["n_joint_weeks"] == len(row["weeks"])
        assert len(row["weeks"]) == len(row["salience_pct"]) == len(row["transits_pct"])
        assert row["weeks"][-1] == meta["knowledge_cutoff"]
        missing = 0
        for previous, current in zip(row["weeks"], row["weeks"][1:]):
            prior_day = date.fromisoformat(previous)
            current_day = date.fromisoformat(current)
            assert prior_day.weekday() == current_day.weekday() == 0
            delta = (current_day - prior_day).days
            assert delta > 0 and delta % 7 == 0
            missing += delta // 7 - 1
        assert missing == row["missing_joint_weeks"]
        assert all(0 <= float(value) <= 100 for value in row["salience_pct"] + row["transits_pct"])
        assert abs(row["latest_gap"] - (row["salience_pct"][-1] - row["transits_pct"][-1])) < 0.051
