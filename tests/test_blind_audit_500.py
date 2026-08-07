"""Lock the independent-coder sample before any external label exists."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from src import blind_audit_500
from src.fetch_ngrams import group_specs
from src.receipts_ngrams import channel_doc_keys

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
    assert _sha256(ROOT / inputs["dictionaries_path"]) == inputs["dictionaries_sha256"]
    assert _sha256(ROOT / inputs["coder_instructions_path"]) == inputs["coder_instructions_sha256"]
    for source in inputs["receipt_sources"]:
        assert _sha256(ROOT / source["path"]) == source["sha256"]
    for source in inputs["pilot_sources"]:
        assert _sha256(ROOT / source["path"]) == source["sha256"]
    for source in inputs["production_matcher_files"]:
        assert _sha256(ROOT / source["path"]) == source["sha256"]
    assert _sha256(ROOT / sample["coder_sheet_path"]) == sample["coder_sheet_sha256"]
    assert _sha256(ROOT / sample["coder_1_sheet_path"]) == sample["coder_1_sheet_sha256"]
    assert _sha256(ROOT / sample["coder_2_sheet_path"]) == sample["coder_2_sheet_sha256"]
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


def test_two_coder_copies_have_same_rows_in_different_registered_orders() -> None:
    canonical = _csv(blind_audit_500.SHEET)
    coder_1, coder_2 = (_csv(path) for path in blind_audit_500.CODER_SHEETS)
    canonical_ids = {row["audit_id"] for row in canonical}
    assert {row["audit_id"] for row in coder_1} == canonical_ids
    assert {row["audit_id"] for row in coder_2} == canonical_ids
    assert [row["audit_id"] for row in coder_1] != [row["audit_id"] for row in coder_2]
    assert all(not row["coder_label"] for row in coder_1 + coder_2)


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
    assert counts == published_key["_meta"]["matched_document_instance_frame_by_channel"]
    assert pilot_rows == _csv(blind_audit_500.PILOT)


def test_every_sampled_instance_belongs_to_the_production_channel_numerator() -> None:
    """Prevent auditing raw phrase matches or URL-deduped proxy units."""
    specs = group_specs()

    def eligible_instances(
        source_files: dict[str, str],
    ) -> dict[str, set[tuple[str, str]]]:
        eligible: dict[str, set[tuple[str, str]]] = {
            channel: set() for channel in blind_audit_500.CHANNELS
        }
        for relpath in source_files:
            payload = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
            corpus = {
                **payload,
                "india": set(payload.get("india") or []),
                "matched": {
                    group: set(keys) for group, keys in payload["matched"].items()
                },
            }
            for channel in blind_audit_500.CHANNELS:
                keys = channel_doc_keys(channel, specs, corpus)
                eligible[channel].update((relpath, key) for key in keys)
        return eligible

    scored_eligible = eligible_instances(blind_audit_500.SOURCE_FILES)
    key_rows = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    assert all(
        (row["source_path"], row["source_document_key"])
        in scored_eligible[row["channel"]]
        for row in key_rows
    )
    pilot_universe = blind_audit_500._universe(blind_audit_500.PILOT_SOURCE_FILES)
    pilot_evidence = {
        channel: {
            (row["article_date"], row["title"], row["url"])
            for row in rows
        }
        for channel, rows in pilot_universe.items()
    }
    assert all(
        (row["article_date"], row["title"], row["url"])
        in pilot_evidence[row["channel"]]
        for row in _csv(blind_audit_500.PILOT)
    )


def test_audit_universe_equals_independent_production_document_frame() -> None:
    """Parity must cover the whole frame, not just the eventual draw."""
    specs = group_specs()
    expected: dict[str, set[tuple[str, str]]] = {
        channel: set() for channel in blind_audit_500.CHANNELS
    }
    for relpath in blind_audit_500.SOURCE_FILES:
        payload = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
        india = set(payload.get("india") or [])
        matched = {group: set(keys) for group, keys in payload["matched"].items()}
        for channel in blind_audit_500.CHANNELS:
            channel_specs = [spec for spec in specs.values() if spec["channel"] == channel]
            keys: set[str] = set()
            for group, spec in specs.items():
                if spec["channel"] == channel:
                    keys |= matched[group]
            if any(spec["anchor"] == "india" for spec in channel_specs):
                keys &= india
            expected[channel].update(
                (relpath, key)
                for key in keys
                if str(payload["meta"].get(key, {}).get("url") or "").strip()
                and str(payload["meta"].get(key, {}).get("title") or "").strip()
                and len(
                    str(payload["meta"].get(key, {}).get("date") or "")
                    .replace("-", "")
                )
                >= 8
            )

    observed = blind_audit_500._universe()
    assert {
        channel: {(row["source_path"], row["source_document_key"]) for row in rows}
        for channel, rows in observed.items()
    } == expected


def test_registration_forbids_recall_and_one_coder_reliability_claims() -> None:
    registration = _registration()
    assert registration["status"] == (
        "FROZEN V2 CURRENT-REGIME PILOT BEFORE FIRST EXTERNAL LABEL"
    )
    assert registration["attestation"]["external_labels_seen_before_freeze"] is False
    assert registration["estimands"]["recall"].startswith("Not estimated.")
    assert registration["attestation"]["comparison_claim_authorized"] is False
    assert registration["study_role"].startswith("Retrospective current-regime pilot")
    assert "no inter-coder" in registration["quality_gates"]["one_coder_rule"].lower()


def test_two_coder_scorer_reports_reliability_without_adjudication(tmp_path: Path) -> None:
    source_rows = _csv(blind_audit_500.SHEET)
    key_rows = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    evidence_by_id = {
        row["audit_id"]: row["evidence_identity_sha256"] for row in key_rows
    }
    coder_paths = [tmp_path / "coder_1.csv", tmp_path / "coder_2.csv"]
    for path in coder_paths:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=blind_audit_500.SHEET_FIELDS)
            writer.writeheader()
            for row in source_rows:
                writer.writerow(
                    row
                    | {
                        "coder_label": (
                            "ON"
                            if int(evidence_by_id[row["audit_id"]][0], 16) % 2
                            else "OFF"
                        ),
                        "coder_confidence": "HIGH",
                    }
                )

    payload = blind_audit_500.score(coder_paths)

    assert payload["_meta"]["coders"] == 2
    assert payload["_meta"]["recall_estimated"] is False
    assert payload["inter_coder"]["n_firm_overlap"] == len(
        set(evidence_by_id.values())
    )
    assert payload["inter_coder"]["n_within_coder_repeat_conflicts"] == 0
    assert payload["inter_coder"]["raw_agreement"] == 1.0
    assert payload["inter_coder"]["gwet_ac1"] == 1.0
    assert payload["inter_coder"]["cohens_kappa_descriptive"] == 1.0
    assert payload["inter_coder"]["reliability_evaluable"] is True
    assert payload["inter_coder"]["reliability_gate"] == "PASS"
    assert payload["inter_coder"]["disagreements_are_not_adjudicated_in_primary"] is True


def test_repeat_conflict_cannot_pass_inter_coder_reliability(tmp_path: Path) -> None:
    source_rows = _csv(blind_audit_500.SHEET)
    key_rows = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    by_evidence: dict[str, list[str]] = {}
    for row in key_rows:
        by_evidence.setdefault(row["evidence_identity_sha256"], []).append(row["audit_id"])
    repeated = next(ids for ids in by_evidence.values() if len(ids) > 1)
    coder_paths = [tmp_path / "coder_1.csv", tmp_path / "coder_2.csv"]
    for coder_index, path in enumerate(coder_paths):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=blind_audit_500.SHEET_FIELDS)
            writer.writeheader()
            for row in source_rows:
                label = "ON" if int(row["audit_id"][-1], 16) % 2 else "OFF"
                if coder_index == 0 and row["audit_id"] == repeated[0]:
                    label = "ON"
                elif coder_index == 0 and row["audit_id"] == repeated[1]:
                    label = "OFF"
                writer.writerow(
                    row | {"coder_label": label, "coder_confidence": "HIGH"}
                )

    payload = blind_audit_500.score(coder_paths)

    assert payload["inter_coder"]["n_within_coder_repeat_conflicts"] >= 1
    assert payload["inter_coder"]["reliability_gate"] == "INCONCLUSIVE_REPEAT_CONFLICT"


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


def test_reliability_boundary_is_exactly_400_firm_pairs() -> None:
    below = [("ON", "ON")] * 398 + [("OFF", "OFF")]
    at_gate = below + [("OFF", "OFF")]

    assert blind_audit_500._inter_coder_summary(below)["reliability_gate"] == "INCONCLUSIVE"
    summary = blind_audit_500._inter_coder_summary(at_gate)
    assert summary["n_firm_overlap"] == 400
    assert summary["reliability_evaluable"] is True
    assert summary["reliability_gate"] == "PASS"


def test_gwet_ac1_matches_hand_computed_balanced_fixture() -> None:
    pairs = (
        [("ON", "ON")] * 40
        + [("OFF", "OFF")] * 40
        + [("ON", "OFF")] * 10
        + [("OFF", "ON")] * 10
    )
    # Observed agreement=.8; pooled ON prevalence=.5; chance=.5;
    # AC1=(.8-.5)/(1-.5)=.6.
    assert blind_audit_500._gwet_ac1(pairs) == 0.6


def test_primary_output_never_contains_a_consensus_or_adjudicated_result(
    tmp_path: Path,
) -> None:
    source_rows = _csv(blind_audit_500.SHEET)
    coder = tmp_path / "coder.csv"
    with coder.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=blind_audit_500.SHEET_FIELDS)
        writer.writeheader()
        for row in source_rows:
            writer.writerow(row | {"coder_label": "ON", "coder_confidence": "HIGH"})

    payload = blind_audit_500.score([coder])
    serialized = json.dumps(payload).lower()
    assert "inter_coder" not in payload
    assert "consensus" not in serialized
    assert "adjudicated" not in serialized
