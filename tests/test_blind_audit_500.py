"""Lock the independent-coder sample before any external label exists."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from src import blind_audit_500

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "validation" / "blind_audit_500"
REGISTRATION = PACKAGE / "registration.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _registration() -> dict:
    return json.loads(REGISTRATION.read_text(encoding="utf-8"))


def test_registered_builder_inputs_and_outputs_are_unchanged() -> None:
    registration = _registration()
    inputs = registration["inputs"]
    sample = registration["sample"]

    assert _sha256(ROOT / inputs["builder_and_scorer"]) == inputs["builder_and_scorer_sha256"]
    assert _sha256(ROOT / inputs["rubric_path"]) == inputs["rubric_sha256"]
    assert _sha256(ROOT / inputs["coder_instructions_path"]) == inputs["coder_instructions_sha256"]
    for source in inputs["receipt_sources"]:
        assert _sha256(ROOT / source["path"]) == source["sha256"]
    assert _sha256(ROOT / sample["coder_sheet_path"]) == sample["coder_sheet_sha256"]
    assert _sha256(ROOT / sample["sample_key_path"]) == sample["sample_key_sha256"]
    assert _sha256(ROOT / sample["pilot_sheet_path"]) == sample["pilot_sheet_sha256"]


def test_scored_sheet_is_exactly_500_balanced_and_blind() -> None:
    rows = _csv(blind_audit_500.SHEET)
    hidden = {
        "stratum",
        "query_group",
        "matched_phrase",
        "machine_label",
        "source_tier",
        "igrm_score",
        "human_label",
    }

    assert len(rows) == 500
    assert len({row["audit_id"] for row in rows}) == 500
    assert Counter(row["channel"] for row in rows) == Counter(
        {channel: 100 for channel in blind_audit_500.CHANNELS}
    )
    assert set(rows[0]).isdisjoint(hidden)
    assert all(not row["coder_label"] for row in rows)
    assert all(not row["coder_confidence"] for row in rows)
    assert all(not row["coder_note"] for row in rows)


def test_sample_key_has_registered_strata_and_no_labels() -> None:
    key = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    counts = Counter((row["channel"], row["stratum"]) for row in key)
    assert counts == Counter(
        {(channel, "article_instance"): 75 for channel in blind_audit_500.CHANNELS}
        | {(channel, "story_cluster"): 25 for channel in blind_audit_500.CHANNELS}
    )
    assert all("label" not in key_name for row in key for key_name in row)


def test_pilot_is_unscored_and_disjoint_from_scored_sheet() -> None:
    pilot = _csv(blind_audit_500.PILOT)
    scored = _csv(blind_audit_500.SHEET)
    assert len(pilot) == 20
    assert Counter(row["channel"] for row in pilot) == Counter(
        {channel: 4 for channel in blind_audit_500.CHANNELS}
    )
    assert {row["url"] for row in pilot}.isdisjoint(row["url"] for row in scored)
    assert {blind_audit_500._title_key(row["title"]) for row in pilot}.isdisjoint(
        blind_audit_500._title_key(row["title"]) for row in scored
    )
    assert all(not row["coder_label"] for row in pilot)


def test_committed_sample_rebuilds_byte_for_byte_at_row_level() -> None:
    sheet_rows, key_rows, counts, pilot_rows = blind_audit_500.build()
    published_key = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))

    assert sheet_rows == _csv(blind_audit_500.SHEET)
    assert key_rows == published_key["items"]
    assert counts == published_key["_meta"]["matched_url_universe_by_channel"]
    assert pilot_rows == _csv(blind_audit_500.PILOT)


def test_registration_forbids_recall_and_one_coder_reliability_claims() -> None:
    registration = _registration()
    assert registration["status"] == "FROZEN BEFORE FIRST EXTERNAL LABEL"
    assert registration["attestation"]["external_labels_seen_before_freeze"] is False
    assert registration["estimands"]["recall"] == "Not estimated."
    assert "no inter-coder" in registration["quality_gates"]["one_coder_rule"].lower()


def test_two_coder_scorer_reports_reliability_without_adjudication(tmp_path: Path) -> None:
    source_rows = _csv(blind_audit_500.SHEET)
    coder_paths = [tmp_path / "coder_1.csv", tmp_path / "coder_2.csv"]
    for path in coder_paths:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=blind_audit_500.SHEET_FIELDS)
            writer.writeheader()
            for index, row in enumerate(source_rows):
                writer.writerow(
                    row
                    | {
                        "coder_label": "ON" if index % 2 else "OFF",
                        "coder_confidence": "HIGH",
                    }
                )

    payload = blind_audit_500.score(coder_paths)

    assert payload["_meta"]["coders"] == 2
    assert payload["_meta"]["recall_estimated"] is False
    assert payload["inter_coder"]["raw_agreement"] == 1.0
    assert payload["inter_coder"]["gwet_ac1"] == 1.0
    assert payload["inter_coder"]["cohens_kappa_descriptive"] == 1.0
    assert payload["inter_coder"]["reliability_evaluable"] is True
    assert payload["inter_coder"]["reliability_gate"] == "PASS"
    assert payload["inter_coder"]["disagreements_are_not_adjudicated_in_primary"] is True


def test_constant_all_on_overlap_is_reliability_inconclusive(tmp_path: Path) -> None:
    source_rows = _csv(blind_audit_500.SHEET)
    coder_paths = [tmp_path / "coder_1.csv", tmp_path / "coder_2.csv"]
    for path in coder_paths:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=blind_audit_500.SHEET_FIELDS)
            writer.writeheader()
            for row in source_rows:
                writer.writerow(row | {"coder_label": "ON", "coder_confidence": "HIGH"})

    payload = blind_audit_500.score(coder_paths)

    assert payload["inter_coder"]["raw_agreement"] == 1.0
    assert payload["inter_coder"]["gwet_ac1"] == 1.0
    assert payload["inter_coder"]["cohens_kappa_descriptive"] is None
    assert payload["inter_coder"]["reliability_evaluable"] is False
    assert payload["inter_coder"]["reliability_gate"] == "NOT_IDENTIFIABLE_CONSTANT_LABELS"
