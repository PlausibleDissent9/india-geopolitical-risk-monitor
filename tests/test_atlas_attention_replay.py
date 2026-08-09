"""Attention Replay executes one bounded, evidence-aware daily state machine."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HTML = (DOCS / "maps.html").read_text(encoding="utf-8")
JS = (DOCS / "maps.js").read_text(encoding="utf-8")
CORE = (DOCS / "maps_replay.js").read_text(encoding="utf-8")
CSS = (DOCS / "maps.css").read_text(encoding="utf-8")


def _run_node(source: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable locally; this browser-core test executes in CI")
    result = subprocess.run(
        [node, "-e", source],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_attention_replay_executes_the_public_validation_core_adversarially() -> None:
    result = _run_node(
        r"""
const fs = require("fs");
const vm = require("vm");
vm.runInThisContext(fs.readFileSync("docs/maps_replay.js", "utf8"));
const core = globalThis.IGRM_ATLAS_REPLAY;
const history = JSON.parse(fs.readFileSync("docs/data/history.json", "utf8"));
const episodes = JSON.parse(fs.readFileSync("docs/data/episodes.json", "utf8"));
const receipts = JSON.parse(fs.readFileSync("docs/data/receipts_archive.json", "utf8"));
const anchors = JSON.parse(fs.readFileSync("docs/geo/channel_anchors.json", "utf8"));
const world = JSON.parse(fs.readFileSync("docs/geo/world.json", "utf8"));

const missingDay = core.resolveDeepLink(history, "2020-02-30", "shipping");
const invalidChannel = core.resolveDeepLink(history, history.dates[10], "made_up");
const withNull = JSON.parse(JSON.stringify(history));
withNull.channels.shipping[10] = null;
const nullObservation = core.observation(withNull, withNull.dates[10], "shipping");
const partial = JSON.parse(JSON.stringify(history));
partial._meta.partial = true;
const futureEpisode = JSON.parse(JSON.stringify(episodes));
futureEpisode[0].start = "2099-01-01";
futureEpisode[0].peak_date = "2099-01-01";
futureEpisode[0].end = "2099-01-01";
const boundary = [{channel: "shipping", label: "Synthetic boundary", start: "2020-01-02", end: "2020-01-04", peak_date: "2020-01-03", n_spike_days: 1}];
const oldEvidence = core.receiptEvidence(receipts, "shipping", history.dates[10]);
const idlePresentation = core.presentation("2026-08-06", false);
const playingPresentation = core.presentation("2026-08-06", true);
const unavailablePresentation = core.presentation(null, false);
const unavailableWorkspace = core.workspaceVisibility(true, false);
const rangeState = core.rangeState(history, history.dates[10]);
process.stdout.write(JSON.stringify({
  current: core.validHistory(history) && core.validEpisodes(episodes, history) &&
    core.validReceiptsArchive(receipts) && core.validAnchors(anchors, world, history),
  missingDay,
  invalidChannel,
  nullHistoryValid: core.validHistory(withNull),
  nullObservation,
  partialRefused: !core.validHistory(partial),
  mismatchRefused: !core.validEpisodes(futureEpisode, history),
  inclusiveStart: core.activeEpisodes(boundary, "2020-01-02").length,
  inclusiveEnd: core.activeEpisodes(boundary, "2020-01-04").length,
  outside: core.activeEpisodes(boundary, "2020-01-05").length,
  oldEvidence,
  idlePresentation,
  playingPresentation,
  unavailablePresentation,
  unavailableWorkspace,
  rangeState,
}));
"""
    )
    assert result["current"] is True
    assert result["missingDay"]["ok"] is False  # type: ignore[index]
    assert "date_outside_published_history" in result["missingDay"]["errors"]  # type: ignore[index]
    assert result["invalidChannel"]["ok"] is False  # type: ignore[index]
    assert "channel_not_registered" in result["invalidChannel"]["errors"]  # type: ignore[index]
    assert result["nullHistoryValid"] is True
    assert result["nullObservation"]["isGap"] is True  # type: ignore[index]
    assert result["nullObservation"]["value"] is None  # type: ignore[index]
    assert result["partialRefused"] is True
    assert result["mismatchRefused"] is True
    assert result["inclusiveStart"] == result["inclusiveEnd"] == 1
    assert result["outside"] == 0
    assert result["oldEvidence"] == {"available": False}
    assert result["idlePresentation"]["hideCurrentContext"] is True  # type: ignore[index]
    assert result["idlePresentation"]["provenanceMode"] == "daily_history"  # type: ignore[index]
    assert "interface anchors" in result["idlePresentation"]["canvasDescription"]  # type: ignore[index]
    assert "event locations" in result["idlePresentation"]["canvasDescription"]  # type: ignore[index]
    assert result["idlePresentation"]["statusText"] == "Replay 2026-08-06 · published daily index"  # type: ignore[index]
    assert result["playingPresentation"]["statusText"] is None  # type: ignore[index]
    assert result["unavailablePresentation"] == {
        "available": False,
        "canvasDescription": "Attention Replay unavailable. No dated replay state is rendered; current analytical layers remain withheld.",
        "statusText": "Attention Replay unavailable · source bundle refused",
        "hideCurrentContext": True,
        "provenanceMode": "unavailable",
    }
    assert result["unavailableWorkspace"] == {
        "hideCurrentContext": True,
        "showReplaySurface": False,
    }
    live_history = json.loads((DOCS / "data/history.json").read_text(encoding="utf-8"))
    assert result["rangeState"]["min"] == 0  # type: ignore[index]
    assert result["rangeState"]["max"] == len(live_history["dates"]) - 1  # type: ignore[index]
    assert result["rangeState"]["value"] == 10  # type: ignore[index]
    assert result["rangeState"]["valueText"] == live_history["dates"][10]  # type: ignore[index]


def test_attention_replay_surface_preserves_the_truth_and_interaction_boundaries() -> None:
    for capability in (
        'data-map-mission="replay"',
        'id="map-replay-layer"',
        'id="map-replay-time"',
        'id="map-replay-play"',
        'aria-valuetext="Loading published date domain"',
        'data-inspector-tab="replay"',
        'id="map-replay-channel-list"',
        'id="map-replay-episodes"',
        'id="map-replay-evidence"',
        'id="map-replay-isolation"',
        'id="map-replay-provenance"',
        "data-current-context",
        'src="maps_replay.js',
    ):
        assert capability in HTML
    for behavior in (
        "resolveDeepLink",
        "renderReplayMarkers",
        "stopReplayPlayback",
        "latest completed news day",
        "IGRM does not substitute or deep-link the latest day",
        "The rest of Atlas remains available",
        "current 7-day pulse, current partner colors, map controls and current ranking are withheld",
        'classList.toggle("is-replay-base", replayVisibility.hideCurrentContext)',
        "renderReplayFrame({ playbackTick: true })",
        "prefers-reduced-motion: reduce",
    ):
        assert behavior in HTML + JS + CSS
    page = (HTML + JS).lower()
    assert "interface anchors only" in page
    assert "not event locations" in page
    assert "no causal attribution" in page
    assert "no interpolation" in page
    assert "date.now" not in CORE.lower() + JS.lower()


def test_attention_replay_anchor_registry_is_projection_bound_and_non_geographic() -> None:
    anchors = json.loads((DOCS / "geo/channel_anchors.json").read_text(encoding="utf-8"))
    world = json.loads((DOCS / "geo/world.json").read_text(encoding="utf-8"))
    history = json.loads((DOCS / "data/history.json").read_text(encoding="utf-8"))
    assert anchors["_meta"]["partial"] is False
    assert anchors["_meta"]["projection_id"] == world["_meta"]["projection_id"]
    assert anchors["_meta"]["world_view_box"] == world["viewBox"]
    assert anchors["_meta"]["longitude_domain"] == world["_meta"]["longitude_domain"]
    assert anchors["_meta"]["latitude_domain"] == world["_meta"]["latitude_domain"]
    assert set(anchors["channels"]) == set(history["channels"])
    assert "not event locations" in anchors["_meta"]["what"]
    assert "exposure paths" in anchors["_meta"]["what"]
    for key, point in anchors["channels"].items():
        assert point["label"] == history["labels"][key]


def test_attention_replay_has_no_external_egress_and_mobile_is_bounded() -> None:
    assert "https://" not in CORE
    assert "http://" not in CORE
    assert "XMLHttpRequest" not in CORE + JS
    assert "sendBeacon" not in CORE + JS
    assert "WebSocket" not in CORE + JS
    assert ".map-inspector-tabs { display: flex; max-width: 100%; }" in CSS
    assert ".map-replay-channel-list button { max-width: 100%; }" in CSS
