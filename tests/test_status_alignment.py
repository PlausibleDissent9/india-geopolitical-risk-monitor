"""Write time and measurement time are different operational facts."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src import status_data

ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, relative: str, payload: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_lagging_receipts_are_reported_without_hiding_label_alignment(
        tmp_path: Path) -> None:
    _write(tmp_path, "docs/data/latest.json", {"date": "2026-08-07"})
    _write(tmp_path, "docs/data/receipts.json", {"date": "2026-08-06"})
    _write(tmp_path, "docs/data/aptness.json", {
        "_meta": {"date": "2026-08-06"}})

    rows = {row["key"]: row
            for row in status_data.check_alignments(tmp_path)}
    receipts = rows["receipts_to_final_scores"]
    assert receipts["status"] == "lagging"
    assert receipts["aligned"] is False
    assert receipts["day_difference"] == 1
    assert receipts["publish_blocking"] is False
    assert "assistant answers refuse" in receipts["effect"]

    labels = rows["aptness_to_receipts"]
    assert labels["status"] == "aligned"
    assert labels["aligned"] is True
    assert labels["day_difference"] == 0


def test_missing_and_invalid_alignment_evidence_fail_visible(
        tmp_path: Path) -> None:
    _write(tmp_path, "docs/data/latest.json", {"date": "not-a-day"})
    _write(tmp_path, "docs/data/receipts.json", {"date": "2026-08-06"})

    rows = {row["key"]: row
            for row in status_data.check_alignments(tmp_path)}
    assert rows["receipts_to_final_scores"]["status"] == "invalid"
    assert rows["receipts_to_final_scores"]["aligned"] is None
    assert rows["aptness_to_receipts"]["status"] == "unavailable"
    assert "missing" in rows["aptness_to_receipts"]["reason"]


def test_alignment_dates_must_be_exact_and_not_future(tmp_path: Path) -> None:
    _write(tmp_path, "docs/data/latest.json", {
        "date": "2026-08-07T00:00:00Z"})
    _write(tmp_path, "docs/data/receipts.json", {"date": "2026-08-06"})
    _write(tmp_path, "docs/data/aptness.json", {
        "_meta": {"date": "2026-08-08"}})
    rows = {row["key"]: row for row in status_data.check_alignments(
        tmp_path, today=date(2026, 8, 7))}
    assert rows["receipts_to_final_scores"]["status"] == "invalid"
    assert "exact ISO-8601" in rows["receipts_to_final_scores"]["reason"]
    assert rows["aptness_to_receipts"]["status"] == "invalid"
    assert "future" in rows["aptness_to_receipts"]["reason"]


def test_published_alignment_payload_is_recomputed_from_committed_bytes() -> None:
    published = json.loads(
        (ROOT / "docs" / "data" / "status.json").read_text(encoding="utf-8"))
    assert published["alignments"] == status_data.check_alignments()
    assert "mismatch is published" in published["_meta"]["alignment_policy"]


def test_market_output_build_date_is_not_called_input_freshness(
        tmp_path: Path) -> None:
    _write(tmp_path, "docs/data/event_study.json", {
        "_meta": {"generated": "2026-08-07"}})
    market = next(row for row in status_data.check_sources(
        date(2026, 8, 8), root=tmp_path) if row["key"] == "markets")
    assert market["latest_data"] is None
    assert market["output_generated"] == "2026-08-07"
    assert market["ok"] is False
    assert "not an input-freshness claim" in market["note"]


def test_status_page_and_codebook_expose_both_clocks_and_join_effects() -> None:
    page = (ROOT / "docs" / "status.html").read_text(encoding="utf-8")
    codebook = (ROOT / "docs" / "codebook.md").read_text(encoding="utf-8")
    assert "Cross-payload coherence" in page
    assert 'id="alignment-body"' in page
    assert 'class="status-table alignment-table"' in page
    assert 'data-label="State and effect"' in page
    assert "Last written" in page and "Measured day" in page
    assert "output built" in page
    assert "status.json.alignments[]" in codebook
    assert "written_date" in codebook and "measured_date" in codebook
    assert "output_generated" in codebook
