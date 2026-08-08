"""Pre-label tests for the production-linked external precision audit v3."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from copy import deepcopy
from datetime import date
from math import comb
from pathlib import Path

import pytest
from src import precision_audit_v3 as audit
from src import precision_frame_v3 as frame

ROOT = Path(__file__).resolve().parents[1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stamp(day: date, index: int) -> str:
    minute = index * 30
    return f"{day:%Y%m%d}{minute // 60:02d}{minute % 60:02d}00"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _dictionary() -> dict[str, object]:
    return {
        channel: {"terms": [f'"{channel.replace("_", " ")}"'], "anchor": None}
        for channel in audit.CHANNELS
    }


def _source_day(root: Path, day: date, per_channel: int = 12) -> None:
    dictionary_bytes = (root / "dictionaries.json").read_bytes()
    matcher_bytes = (root / "src" / "fetch_ngrams.py").read_bytes()
    stamps = [_stamp(day, index) for index in range(48)]
    specs = {
        f"{channel}/q1": {
            "channel": channel,
            "anchor": None,
            "phrases": [[channel.replace("_", " ")]],
        }
        for channel in audit.CHANNELS
    }
    matched: dict[str, list[str]] = {}
    metadata: dict[str, dict[str, str]] = {}
    shares: dict[str, float] = {}
    for channel_index, channel in enumerate(audit.CHANNELS):
        group = f"{channel}/q1"
        keys: list[str] = []
        for item in range(per_channel):
            key = f"{stamps[(channel_index * per_channel + item) % 48]}:{channel_index}-{item}"
            keys.append(key)
            metadata[key] = {
                "date": f"{day:%Y%m%d}",
                "title": f"{channel} prospective evidence {day} item {item}",
                "url": f"https://{channel}.example/{day}/{item}",
            }
        matched[group] = keys
        shares[group] = round(100 * per_channel / 1000, 6)
    encoded_specs = json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()
    payload = {
        "date": day.isoformat(),
        "n_docs_sampled": 1000,
        "n_samples": 48,
        "n_samples_loaded": 48,
        "partial": False,
        "shares": shares,
        "_matcher_evidence": {
            "schema_version": frame.SCHEMA_VERSION,
            "day": day.isoformat(),
            "located_stamps": stamps,
            "loaded_stamps": stamps,
            "missing_stamps": [],
            "matcher_specs": specs,
            "matcher_specs_sha256": _sha(encoded_specs),
            "dictionaries_sha256": _sha(dictionary_bytes),
            "production_matcher_sha256": _sha(matcher_bytes),
            "india_document_keys": [],
            "matched_document_keys": matched,
            "article_meta": metadata,
        },
    }
    source = root / "data" / "raw" / "ngram_days" / f"{day}.json"
    _write_json(source, payload)
    attestation = frame.build_day_attestation(day, root, require_live_hashes=False)
    _write_json(root / "data" / "raw" / "precision_v3_days" / f"{day}.json", attestation)


def _pilot_source(root: Path, per_channel: int = 6) -> Path:
    specs = frame._active_specs_from_dictionary(root)
    matched: dict[str, list[str]] = {}
    metadata: dict[str, dict[str, str]] = {}
    for channel_index, channel in enumerate(audit.CHANNELS):
        group = f"{channel}/q1"
        assert group in specs
        keys = []
        for item in range(per_channel):
            key = f"20260807000000:{channel_index}-{item}"
            keys.append(key)
            metadata[key] = {
                "date": "20260807",
                "title": f"{channel} pilot evidence {item}",
                "url": f"https://pilot-{channel}.example/{item}",
            }
        matched[group] = keys
    path = root / "data" / "raw" / "receipt_days" / "2026-08-07-extended.json"
    _write_json(
        path,
        {
            "n_docs_sampled": 100,
            "n_samples": 48,
            "extended": True,
            "scored_stamps": ["20260807000000"],
            "india": [],
            "matched": matched,
            "meta": metadata,
        },
    )
    return path


def _fixture_root(tmp_path: Path, *, complete: bool = True) -> Path:
    root = tmp_path / "repo"
    registered_paths = [
        "validation/precision_v3/PROTOCOL.md",
        "validation/precision_v3/CODING_MANUAL.md",
        "auditor/RUBRIC.md",
        "dictionaries.json",
        "src/fetch_ngrams.py",
        "src/precision_frame_v3.py",
        "src/precision_audit_v3.py",
    ]
    for relpath in registered_paths:
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        if relpath == "dictionaries.json":
            path.write_text(json.dumps(_dictionary()), encoding="utf-8")
        else:
            path.write_text(f"registered fixture: {relpath}\n", encoding="utf-8")

    pilot_path = _pilot_source(root)
    registration = deepcopy(json.loads((ROOT / "validation" / "precision_v3" / "registration.json").read_text()))
    registration["registered_files"] = [
        {
            "path": relpath,
            "sha256": _sha((root / relpath).read_bytes()),
            "role": f"fixture_{index}",
        }
        for index, relpath in enumerate(registered_paths)
    ]
    registration["coding"]["pilot"]["source_sha256"] = _sha(pilot_path.read_bytes())
    _write_json(root / "validation" / "precision_v3" / "registration.json", registration)

    cohort = registration["cohorts"][0]
    start = date.fromisoformat(cohort["window_start"])
    end = date.fromisoformat(cohort["window_end"])
    days = audit._days(start, end)
    if not complete:
        days = days[:-1]
    for day in days:
        _source_day(root, day)
    return root


def _filled_sheet(
    canonical: Path,
    destination: Path,
    *,
    abstain_last: int = 0,
) -> Path:
    with canonical.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_channel: dict[str, list[str]] = {channel: [] for channel in audit.CHANNELS}
    for row in rows:
        by_channel[row["channel"]].append(row["audit_id"])
    off = {
        audit_id
        for channel in audit.CHANNELS
        for audit_id in sorted(by_channel[channel])[:50]
    }
    abstain = {
        audit_id
        for channel in audit.CHANNELS
        for audit_id in sorted(by_channel[channel])[-abstain_last:]
    } if abstain_last else set()
    for row in rows:
        if row["audit_id"] in abstain:
            row["coder_label"] = "ABSTAIN"
            row["coder_note"] = "Frozen title and linked evidence are insufficient."
        else:
            row["coder_label"] = "OFF" if row["audit_id"] in off else "ON"
            row["coder_note"] = ""
        row["coder_confidence"] = "HIGH"
        row["evidence_access_status"] = "TITLE_ONLY"
        row["evidence_accessed_at_utc"] = ""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit.CODER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return destination


def _anchor_receipt(root: Path, package: Path) -> tuple[Path, str]:
    receipt = root / "validation" / "precision_v3" / "freeze_v3a.json"
    audit.write_freeze_receipt(package, receipt)
    commands = (
        ("init", "-q"),
        ("config", "user.name", "Precision V3 Test"),
        ("config", "user.email", "precision-v3-test@example.invalid"),
        ("add", "validation/precision_v3/freeze_v3a.json"),
        ("commit", "-q", "-m", "anchor precision v3 freeze receipt"),
    )
    for command in commands:
        subprocess.run(["git", "-C", str(root), *command], check=True)
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return receipt, commit


def _coder_attestation(
    package: Path,
    sheet: Path,
    receipt: Path,
    commit: str,
    destination: Path,
    index: int,
    *,
    coder_id: str | None = None,
) -> Path:
    manifest = json.loads((package / "package_manifest.json").read_text())
    payload = {
        "schema_version": audit.SCHEMA_VERSION,
        "audit_id": manifest["audit_id"],
        "cohort_id": manifest["cohort_id"],
        "coder_id": coder_id or f"C00{index}",
        "coder_assignment": f"coder_{index}",
        "sheet_sha256": _sha(sheet.read_bytes()),
        "freeze_receipt_sha256": _sha(receipt.read_bytes()),
        "freeze_receipt_commit": commit,
        "packet_received_at_utc": f"2099-01-0{index}T10:00:00Z",
        "pilot_completed_at_utc": f"2099-01-0{index}T11:00:00Z",
        "sheet_completed_at_utc": f"2099-01-0{index}T12:00:00Z",
        "attested_at_utc": f"2099-01-0{index}T12:05:00Z",
        "statements": {
            statement: True for statement in audit.CODER_ATTESTATION_STATEMENTS
        },
    }
    _write_json(destination, payload)
    return destination


def test_repository_registration_is_pre_label_and_preserves_a_holdout() -> None:
    registration = audit._registration(ROOT)
    assert registration["status"] == "PREREGISTERED_NO_SAMPLE_NO_LABELS"
    assert [cohort["calendar_days"] for cohort in registration["cohorts"]] == [42, 48]
    assert registration["cohorts"][0]["window_end"] == "2026-09-18"
    assert registration["cohorts"][1]["window_start"] == "2026-09-19"
    assert len({cohort["selection_seed"] for cohort in registration["cohorts"]}) == 2
    assert registration["attestation"]["v3_sample_drawn_when_registered"] is False
    assert registration["attestation"]["v3_label_seen_when_registered"] is False
    assert registration["attestation"]["comparison_claim_authorized"] is False


def test_complete_source_frame_reproduces_contributions_and_draws_exact_sample(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    rows, manifest = audit.build_frame("v3a", root)
    registration = audit._registration(root)
    selected, sample = audit.select_sample(rows, registration["cohorts"][0])

    assert len(rows) == 42 * 12 * 5
    assert manifest["calendar_days"] == 42
    assert manifest["frame_by_channel"] == {channel: 504 for channel in audit.CHANNELS}
    assert manifest["labels_seen"] is False
    assert len(selected) == 2500
    assert sample["selection_by_channel"] == {
        channel: {
            "frame_n": 504,
            "sample_n": 500,
            "inclusion_probability": 500 / 504,
            "census": False,
        }
        for channel in audit.CHANNELS
    }
    assert len({row["audit_id"] for row in selected}) == 2500


def test_source_frame_refuses_missing_days_and_changed_registered_code(tmp_path: Path) -> None:
    incomplete = _fixture_root(tmp_path / "missing", complete=False)
    with pytest.raises(audit.AuditV3Error, match="source window is incomplete"):
        audit.build_frame("v3a", incomplete)

    complete = _fixture_root(tmp_path / "changed")
    (complete / "src" / "precision_audit_v3.py").write_text("changed\n")
    with pytest.raises(audit.AuditV3Error, match="registered file changed"):
        audit.build_frame("v3a", complete)


def test_source_frame_names_a_recorded_failure_instead_of_sampling_around_it(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    failed_path = root / "data" / "raw" / "precision_v3_days" / "2026-08-20.json"
    failure = frame.build_failure_attestation(
        date(2026, 8, 20), frame.FrameValidationError("partial production day"), root
    )
    _write_json(failed_path, failure)

    with pytest.raises(
        audit.AuditV3Error,
        match="recorded frame failure on 2026-08-20: partial production day",
    ):
        audit.build_frame("v3a", root)


def test_hash_rank_selection_preserves_distinct_contributions_with_same_evidence() -> None:
    rows = []
    for index in range(2):
        rows.append(
            {
                "frame_id": str(index),
                "channel": "pakistan_west",
                "evidence_identity_sha256": "same",
            }
        )
    for channel in audit.CHANNELS[1:]:
        rows.append(
            {
                "frame_id": channel,
                "channel": channel,
                "evidence_identity_sha256": channel,
            }
        )
    cohort = {
        "selection_seed": "fixed-before-future-frame-1234567890",
        "sample_per_channel": 500,
    }
    first, first_meta = audit.select_sample(rows, cohort)
    second, second_meta = audit.select_sample(list(reversed(rows)), cohort)
    assert first == second
    assert first_meta == second_meta
    assert [row["evidence_identity_sha256"] for row in first].count("same") == 2


def test_private_package_is_deterministic_hash_locked_and_scored_coder_specific(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    first = audit.write_package("v3a", tmp_path / "package-one", root)
    second = audit.write_package("v3a", tmp_path / "package-two", root)
    manifest = audit.verify_package(first)
    second_receipt = audit.write_freeze_receipt(
        second, tmp_path / "second-freeze-receipt.json"
    )
    receipt, commit = _anchor_receipt(root, first)
    assert manifest["status"] == "FROZEN_PRIVATE_CODER_PACKAGE_NO_LABELS"
    assert manifest["labels_seen"] is False
    assert manifest["precision_estimated"] is False
    for name in {item["path"] for item in manifest["files"]}:
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert receipt.read_bytes() == second_receipt.read_bytes()
    assert b"https://" not in receipt.read_bytes()
    assert b"prospective evidence" not in receipt.read_bytes()
    audit.verify_freeze_receipt(first, receipt)
    assert audit.verify_git_anchor(receipt, commit, root)["commit"] == commit

    coder_one = _filled_sheet(first / "coder_sheet_c1.csv", tmp_path / "coder-one.csv")
    coder_two = _filled_sheet(first / "coder_sheet_c2.csv", tmp_path / "coder-two.csv")
    attestation_one = _coder_attestation(
        first, coder_one, receipt, commit, tmp_path / "coder-one-attestation.json", 1
    )
    attestation_two = _coder_attestation(
        first, coder_two, receipt, commit, tmp_path / "coder-two-attestation.json", 2
    )
    result = audit.score_package(
        first,
        [coder_one, coder_two],
        receipt,
        commit,
        [attestation_one, attestation_two],
        root,
    )
    assert result["overall_gate"] == "PASS"
    assert result["_meta"]["freeze_receipt_anchor"]["commit"] == commit
    assert len({row["sheet_sha256"] for row in result["coder_submissions"]}) == 2
    assert len(result["coder_results"]) == 2
    for coder in result["coder_results"]:
        assert coder["all_channels_pass"] is True
        for channel in audit.CHANNELS:
            block = coder["channels"][channel]
            assert block["sample_n"] == 500
            assert block["firm_n"] == 500
            assert block["on"] == 450
            assert block["gate"] == "PASS"
    assert result["inter_coder_reliability"]["all_channels_pass"] is True

    copied_attestation = _coder_attestation(
        first,
        coder_one,
        receipt,
        commit,
        tmp_path / "copied-coder-attestation.json",
        2,
    )
    with pytest.raises(audit.AuditV3Error, match="byte-identical"):
        audit.score_package(
            first,
            [coder_one, coder_one],
            receipt,
            commit,
            [attestation_one, copied_attestation],
            root,
        )
    with pytest.raises(audit.AuditV3Error, match="anchor commit is unavailable"):
        audit.score_package(
            first,
            [coder_one],
            receipt,
            "0" * 40,
            [attestation_one],
            root,
        )

    (first / "unexpected.txt").write_text("not registered\n")
    with pytest.raises(audit.AuditV3Error, match="unregistered or missing"):
        audit.verify_package(first)


def test_abstentions_cannot_inflate_the_registered_pass_gate(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    package = audit.write_package("v3a", tmp_path / "package", root)
    receipt, commit = _anchor_receipt(root, package)
    coder = _filled_sheet(
        package / "coder_sheet_c1.csv",
        tmp_path / "coder.csv",
        abstain_last=100,
    )
    attestation = _coder_attestation(
        package, coder, receipt, commit, tmp_path / "coder-attestation.json", 1
    )
    result = audit.score_package(
        package, [coder], receipt, commit, [attestation], root
    )
    assert result["overall_gate"] == "NOT_PASS"
    for channel in audit.CHANNELS:
        block = result["coder_results"][0]["channels"][channel]
        assert block["firm_label_precision"] == 0.875
        assert block["all_abstentions_off_precision"] == 0.7
        assert block["gate"] == "FAIL"


def test_coder_sheet_refuses_locked_field_and_access_provenance_tampering(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    package = audit.write_package("v3a", tmp_path / "package", root)
    receipt, commit = _anchor_receipt(root, package)
    coder = _filled_sheet(package / "coder_sheet_c1.csv", tmp_path / "coder.csv")
    rows = audit._read_csv(coder)
    rows[0]["title"] += " changed"
    with coder.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit.CODER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    attestation = _coder_attestation(
        package, coder, receipt, commit, tmp_path / "coder-attestation.json", 1
    )
    with pytest.raises(audit.AuditV3Error, match="changed locked field title"):
        audit.score_package(
            package, [coder], receipt, commit, [attestation], root
        )

    coder = _filled_sheet(package / "coder_sheet_c1.csv", tmp_path / "coder.csv")
    rows = audit._read_csv(coder)
    rows[0]["evidence_access_status"] = "LIVE"
    rows[0]["evidence_accessed_at_utc"] = "not-a-time"
    with coder.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=audit.CODER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    attestation = _coder_attestation(
        package, coder, receipt, commit, tmp_path / "coder-attestation-2.json", 1
    )
    with pytest.raises(audit.AuditV3Error, match="not a UTC timestamp"):
        audit.score_package(
            package, [coder], receipt, commit, [attestation], root
        )

    receipt_payload = json.loads(receipt.read_text())
    receipt_payload["sample_key_sha256"] = "0" * 64
    _write_json(receipt, receipt_payload)
    coder = _filled_sheet(package / "coder_sheet_c1.csv", tmp_path / "coder.csv")
    attestation = _coder_attestation(
        package, coder, receipt, commit, tmp_path / "coder-attestation-3.json", 1
    )
    with pytest.raises(audit.AuditV3Error, match="mismatched package-file digest"):
        audit.score_package(
            package, [coder], receipt, commit, [attestation], root
        )


def test_exact_finite_population_interval_is_conservative_on_small_populations() -> None:
    for population_n in range(2, 18):
        for sample_n in range(1, population_n + 1):
            denominator = comb(population_n, sample_n)
            for population_successes in range(population_n + 1):
                coverage = 0.0
                minimum = max(0, sample_n - (population_n - population_successes))
                maximum = min(sample_n, population_successes)
                for observed in range(minimum, maximum + 1):
                    interval = audit._finite_population_interval(
                        population_n, sample_n, observed
                    )
                    target = population_successes / population_n
                    if interval[0] - 0.000051 <= target <= interval[1] + 0.000051:
                        coverage += (
                            comb(population_successes, observed)
                            * comb(population_n - population_successes, sample_n - observed)
                            / denominator
                        )
                assert coverage >= 0.95 - 1e-12

    assert audit._finite_population_interval(500, 500, 418) == [0.836, 0.836]


def test_public_protocol_forbids_superiority_and_primary_adjudication() -> None:
    protocol = " ".join(
        (ROOT / "validation" / "precision_v3" / "PROTOCOL.md")
        .read_text()
        .lower()
        .split()
    )
    manual = " ".join(
        (ROOT / "validation" / "precision_v3" / "CODING_MANUAL.md")
        .read_text()
        .lower()
        .split()
    )
    assert "out-of-time holdout replication" in protocol
    assert "every abstain" in protocol
    assert "no v3 sample or label exists" in manual
    assert "no consensus/adjudicated label replaces a primary estimate" in manual
    assert "superiority over another index" in manual
