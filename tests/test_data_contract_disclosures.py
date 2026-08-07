"""Secondary products must disclose their actual coverage.

These checks pin defects found by the 2026-08-07 institutional audit:
clean arithmetic in the core series is not enough if an adjacent payload
implies more dates, components or outcomes than it contains.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from src import event_study

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"


def _payload(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_monthly_json_uses_null_and_separate_composite_coverage():
    monthly = _payload("monthly.json")
    june = next(r for r in monthly["months"] if r["month"] == "2017-06")
    assert june["coverage"] == 1.0
    assert june["n_days_composite_present"] == 2
    assert june["composite_coverage"] < 0.08
    assert june["composite_mean_of_ranks"] is None
    assert june["composite_refused_reason"]


def test_receipts_archive_never_promises_missing_days():
    archive = _payload("receipts_archive.json")
    meta = archive["_meta"]
    assert meta["available_days"] == len(meta["days"])
    assert meta["complete_window"] == (
        meta["available_days"] >= meta["target_days"])
    if not meta["complete_window"]:
        assert "fewer than seven" in meta["what"]


def test_stress_gauge_discloses_renormalization_and_status():
    gauge = _payload("stress_gauge.json")
    meta = gauge["_meta"]
    registered = set(meta["registered_weights"])
    available = set(meta["latest_available_components"])
    missing = set(meta["latest_missing_components"])
    assert available.isdisjoint(missing)
    assert available | missing == registered
    assert set(gauge["components"]) == registered
    assert abs(sum(meta["latest_effective_weights"].values()) - 1) < 1e-5
    assert meta["headline_eligible"] is False
    assert meta["validation_status"] == "experimental_not_validated"


def test_event_study_lists_unavailable_outcomes_instead_of_null_grid():
    payload = _payload("event_study.json")
    configured = set(event_study.RELATIVE_OUTCOMES +
                     event_study.DESCRIPTIVE_OUTCOMES)
    available = set(payload["available_outcomes"])
    unavailable = set(payload["unavailable_outcomes"])
    assert available.isdisjoint(unavailable)
    assert available | unavailable == configured
    for channel in payload["channels"].values():
        assert set(channel["outcomes"]) == available


def test_detector_diagnostic_accounts_for_every_detected_episode():
    payload = _payload("detector_blindness.json")
    meta = payload["_meta"]
    with (DATA / "episodes.csv").open(encoding="utf-8") as fh:
        detected = sum(1 for _ in csv.DictReader(fh))
    assert meta["n_episodes_analysed"] == len(payload["episodes"])
    assert meta["n_episodes_excluded"] == len(meta["excluded_episodes"])
    assert meta["n_episodes_analysed"] + meta["n_episodes_excluded"] == detected
    assert all(e["reason"] for e in meta["excluded_episodes"])
