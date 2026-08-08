"""Lock the independent-coder sample before any external label exists."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from scripts import verify_blind_audit_v2
from src import blind_audit_500

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "validation" / "blind_audit_500"
REGISTRATION = PACKAGE / "registration.json"
ANCHORED_CHANNELS = {"pakistan_west", "china_east", "us_trade"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _registration() -> dict:
    return json.loads(REGISTRATION.read_text(encoding="utf-8"))


def _eligible_instances(
    source_files: dict[str, str],
) -> dict[str, set[tuple[str, str]]]:
    """Independent registered union-plus-anchor arithmetic.

    This deliberately imports no mutable production matcher. Receipt caches
    key their frozen subqueries as ``<channel>/qN``; anchored channels then
    intersect that union with the per-document India set.
    """
    eligible: dict[str, set[tuple[str, str]]] = {
        channel: set() for channel in blind_audit_500.CHANNELS
    }
    for relpath in source_files:
        payload = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
        india = set(payload.get("india") or [])
        for channel in blind_audit_500.CHANNELS:
            keys: set[str] = set()
            for group, members in payload["matched"].items():
                if group.startswith(f"{channel}/"):
                    keys.update(members)
            if channel in ANCHORED_CHANNELS:
                keys &= india
            eligible[channel].update((relpath, key) for key in keys)
    return eligible


def test_registered_builder_inputs_and_outputs_are_unchanged() -> None:
    report = verify_blind_audit_v2.verify()
    assert report["status"] == "REPRODUCIBLE_INVALID_STUDY"
    assert report["artifact_verification"] == "PASS"
    assert report["study_status"] == "INVALID_BEFORE_CODING"
    assert report["base_commit"] == _registration()["base_commit"]
    assert report["registration_sha256"] == _sha256(REGISTRATION)


def test_living_registered_inputs_resolve_at_base_not_mutable_head() -> None:
    registration = _registration()
    inputs = registration["inputs"]
    living = {
        inputs["rubric_path"],
        inputs["dictionaries_path"],
        *(item["path"] for item in inputs["production_matcher_files"]),
    }
    current_pins = {
        path
        for path, _ in verify_blind_audit_v2._current_evidence_paths(registration)
    }
    assert living.isdisjoint(current_pins)
    for path in living:
        expected = next(
            digest
            for registered_path, digest in verify_blind_audit_v2._registered_paths(
                registration
            )
            if registered_path == path
        )
        frozen = verify_blind_audit_v2._run_git(
            "show", f'{registration["base_commit"]}:{path}'
        )
        assert hashlib.sha256(frozen).hexdigest() == expected


def test_tampered_registration_bytes_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tampered = tmp_path / "registration.json"
    tampered.write_bytes(REGISTRATION.read_bytes() + b"\n")
    monkeypatch.setattr(verify_blind_audit_v2, "REGISTRATION", tampered)

    with pytest.raises(
        verify_blind_audit_v2.VerificationError,
        match="registration bytes changed",
    ):
        verify_blind_audit_v2._load_registration(tampered)


def test_tampered_registered_base_hash_fails_closed() -> None:
    registration = _registration()
    registration["inputs"]["production_matcher_files"][0]["sha256"] = "0" * 64

    with pytest.raises(
        verify_blind_audit_v2.VerificationError,
        match="registered base blob mismatch",
    ):
        verify_blind_audit_v2._verify_commit_inputs(registration)


def test_tampered_rebuilt_output_hash_fails_closed() -> None:
    registration = _registration()
    registration["sample"]["coder_sheet_sha256"] = "0" * 64

    with pytest.raises(
        verify_blind_audit_v2.VerificationError,
        match="frozen rebuild mismatch",
    ):
        verify_blind_audit_v2._rebuild(
            registration,
            registration["base_commit"],
            ROOT,
        )


def test_tampered_current_evidence_fails_closed(tmp_path: Path) -> None:
    registration = _registration()
    path = registration["inputs"]["builder_and_scorer"]
    candidate = tmp_path / path
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes((ROOT / path).read_bytes() + b"\n")

    with pytest.raises(
        verify_blind_audit_v2.VerificationError,
        match=f"frozen current evidence mismatch for {path}",
    ):
        verify_blind_audit_v2._verify_current_evidence(registration, tmp_path)


def test_missing_registered_base_commit_fails_closed() -> None:
    registration = _registration() | {"base_commit": "0" * 40}
    with pytest.raises(verify_blind_audit_v2.VerificationError):
        verify_blind_audit_v2._verify_commit_inputs(registration)


def test_v2_is_publicly_invalidated_before_coding() -> None:
    notice = (PACKAGE / "V2_INVALID.md").read_text(encoding="utf-8")
    normalized = " ".join(notice.split())
    assert verify_blind_audit_v2.INVALIDATION_MARKER in notice
    assert "5,386 documents" in normalized
    assert "Nine sampled article-instance rows" in normalized
    assert (PACKAGE / "registration.json.ots").is_file()
    assert (PACKAGE / "registration_v1_989c43f.json.ots").is_file()
    for path in [*blind_audit_500.CODER_SHEETS, blind_audit_500.PILOT]:
        assert all(not row["coder_label"] for row in _csv(path))
    assert "invalidated before any label" in (
        ROOT / "docs" / "validation.html"
    ).read_text(encoding="utf-8")
    assert "blind-audit v2 did not match" in (
        ROOT / "docs" / "corrections.md"
    ).read_text(encoding="utf-8")


def test_v2_invalidation_matches_frozen_source_and_sample_evidence() -> None:
    score = json.loads(
        (ROOT / "data/raw/ngram_days/2026-08-05.json").read_text(
            encoding="utf-8"
        )
    )
    receipt_path = "data/raw/receipt_days/2026-08-05.json"
    receipt = json.loads((ROOT / receipt_path).read_text(encoding="utf-8"))
    assert (score["n_samples"], score["n_docs_sampled"]) == (48, 33_961)
    assert (receipt["n_samples"], receipt["n_docs_sampled"]) == (39, 28_575)

    key_rows = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    deficient = [row for row in key_rows if row["source_path"] == receipt_path]
    assert len(deficient) == 49
    assert Counter(row["stratum"] for row in deficient) == Counter(
        {"article_instance": 40, "story_cluster": 9}
    )
    assert Counter(row["channel"] for row in deficient) == Counter(
        {
            "pakistan_west": 10,
            "china_east": 8,
            "gulf_energy": 17,
            "us_trade": 10,
            "shipping": 4,
        }
    )

    registration = _registration()
    totals = {}
    for channel in ("pakistan_west", "gulf_energy"):
        union: set[tuple[str, str]] = set()
        contributions = 0
        for source in registration["inputs"]["receipt_sources"]:
            payload = json.loads(
                (ROOT / source["path"]).read_text(encoding="utf-8")
            )
            india = set(payload.get("india") or [])
            for group, members in payload["matched"].items():
                if not group.startswith(f"{channel}/"):
                    continue
                keys = set(members)
                if channel in ANCHORED_CHANNELS:
                    keys &= india
                eligible = {
                    key
                    for key in keys
                    if str(payload["meta"].get(key, {}).get("url") or "").strip()
                    and str(
                        payload["meta"].get(key, {}).get("title") or ""
                    ).strip()
                    and len(
                        str(payload["meta"].get(key, {}).get("date") or "")
                        .replace("-", "")
                    )
                    >= 8
                }
                contributions += len(eligible)
                union.update((source["path"], key) for key in eligible)
        totals[channel] = (contributions, len(union))
    assert totals == {
        "pakistan_west": (287, 264),
        "gulf_energy": (8_178, 8_156),
    }


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
    report = verify_blind_audit_v2.verify()
    registration = _registration()
    for key, expected_path in registration["sample"].items():
        if not key.endswith("_path"):
            continue
        digest_key = key.removesuffix("_path") + "_sha256"
        assert report["output_sha256"][expected_path] == registration["sample"][
            digest_key
        ]


def test_every_sampled_instance_belongs_to_the_registered_union_frame() -> None:
    """Reproduce v2's union-plus-anchor frame without mutable matchers."""
    scored_eligible = _eligible_instances(blind_audit_500.SOURCE_FILES)
    key_rows = json.loads(blind_audit_500.KEY.read_text(encoding="utf-8"))["items"]
    assert all(
        (row["source_path"], row["source_document_key"])
        in scored_eligible[row["channel"]]
        for row in key_rows
    )
    pilot_eligible = _eligible_instances(blind_audit_500.PILOT_SOURCE_FILES)
    pilot_evidence: dict[str, set[tuple[str, str, str]]] = {
        channel: set() for channel in blind_audit_500.CHANNELS
    }
    for channel, instances in pilot_eligible.items():
        for relpath, key in instances:
            payload = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
            row = payload["meta"][key]
            raw_date = str(row["date"]).replace("-", "")[:8]
            pilot_evidence[channel].add(
                (
                    f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}",
                    str(row["title"]).strip(),
                    str(row["url"]).strip(),
                )
            )
    assert all(
        (row["article_date"], row["title"], row["url"])
        in pilot_evidence[row["channel"]]
        for row in _csv(blind_audit_500.PILOT)
    )


def test_audit_universe_equals_independent_production_document_frame() -> None:
    """Parity must cover the whole frame, not just the eventual draw."""
    expected: dict[str, set[tuple[str, str]]] = {
        channel: set() for channel in blind_audit_500.CHANNELS
    }
    for relpath in blind_audit_500.SOURCE_FILES:
        payload = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
        eligible = _eligible_instances({relpath: blind_audit_500.SOURCE_FILES[relpath]})
        for channel in blind_audit_500.CHANNELS:
            expected[channel].update(
                (relpath, key)
                for _, key in eligible[channel]
                if str(payload["meta"].get(key, {}).get("url") or "").strip()
                and str(payload["meta"].get(key, {}).get("title") or "").strip()
                and len(
                    str(payload["meta"].get(key, {}).get("date") or "")
                    .replace("-", "")
                )
                >= 8
            )

    report = verify_blind_audit_v2.verify()["frame_by_channel"]
    expected_report = {}
    for channel, members in expected.items():
        frame_ids = sorted(f"{path}|{key}" for path, key in members)
        expected_report[channel] = {
            "n": len(frame_ids),
            "frame_ids_sha256": hashlib.sha256(
                ("\n".join(frame_ids) + "\n").encode("utf-8")
            ).hexdigest(),
        }
    assert report == expected_report


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
