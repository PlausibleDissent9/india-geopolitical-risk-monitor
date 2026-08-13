"""Hostile vectors for the value-free daily aggregate profile."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import date
from pathlib import Path

import pytest
from src import final_publication, ngram_daily_attestation

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 8, 10)
SPECS = {"west/q1": {"channel": "west", "anchor": "india", "phrases": [["border"]]}}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, dict]:
    root = tmp_path
    paths = (
        ngram_daily_attestation.PROFILE_RELATIVE,
        ngram_daily_attestation.SCHEMA_RELATIVE,
        Path("dictionaries.json"),
        Path("src/fetch_ngrams.py"),
        Path("src/ngram_daily_attestation.py"),
    )
    for path in paths:
        full = root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(f"fixture:{path}".encode())
    bindings = {
        "profile_sha256": _sha((root / paths[0]).read_bytes()),
        "schema_sha256": _sha((root / paths[1]).read_bytes()),
        "dictionaries_sha256": _sha((root / paths[2]).read_bytes()),
        "production_matcher_sha256": _sha((root / paths[3]).read_bytes()),
        "validator_sha256": _sha((root / paths[4]).read_bytes()),
        "calibration_sha256": "a" * 64,
        "matcher_specs": SPECS,
        "matcher_specs_sha256": _sha(ngram_daily_attestation.canonical_bytes(SPECS)),
    }
    windows = []
    for bucket in range(48):
        stamp = f"{DAY:%Y%m%d}{bucket // 2:02d}{(bucket % 2) * 30:02d}00"
        toc, ngrams = ngram_daily_attestation.source_urls(stamp)
        windows.append(
            {
                "bucket": bucket,
                "stamp": stamp,
                "source_objects": {
                    "toc": {"url": toc, "sha256": _sha(stamp.encode()), "bytes": 10},
                    "ngrams": {"url": ngrams, "sha256": _sha((stamp + "n").encode()), "bytes": 20},
                },
                "english_denominator": 10,
                "group_numerators": {"west/q1": 1},
            }
        )
    value = {
        "schema_version": ngram_daily_attestation.SCHEMA_VERSION,
        "profile_id": ngram_daily_attestation.PROFILE_ID,
        "day": DAY.isoformat(),
        "expected_windows": 48,
        "located_windows": 48,
        "loaded_windows": 48,
        "method_bindings": bindings,
        "windows": windows,
        "aggregate_reconstruction": {
            "window_order": list(range(48)),
            "english_denominator": 480,
            "group_numerators": {"west/q1": 48},
            "shares": {"west/q1": 10.0},
            "channel_sums": {"west": 10.0},
        },
        "membership_reproducibility": ngram_daily_attestation.MEMBERSHIP_LIMIT,
    }
    return root, ngram_daily_attestation.seal(value)


@pytest.mark.parametrize(
    "attack",
    (
        "47_of_48",
        "duplicate_bucket",
        "source_hash",
        "source_bytes",
        "denominator",
        "numerator",
        "timestamp_splice",
        "aggregate_reseal",
        "old_profile",
        "identity",
        "title",
        "url_list",
        "domain_hash_list",
    ),
)
def test_attestation_hostile_vectors_refuse(tmp_path: Path, attack: str) -> None:
    root, value = _fixture(tmp_path)
    value = copy.deepcopy(value)
    if attack == "47_of_48":
        value["windows"].pop()
    elif attack == "duplicate_bucket":
        value["windows"][1]["bucket"] = 0
    elif attack == "source_hash":
        value["windows"][0]["source_objects"]["toc"]["sha256"] = "b" * 63
    elif attack == "source_bytes":
        value["windows"][0]["source_objects"]["toc"]["bytes"] = 0
    elif attack == "denominator":
        value["windows"][0]["english_denominator"] = 9
    elif attack == "numerator":
        value["windows"][0]["group_numerators"]["west/q1"] = 11
    elif attack == "timestamp_splice":
        value["windows"][0]["stamp"] = "20260811000000"
    elif attack == "aggregate_reseal":
        value["aggregate_reconstruction"]["shares"]["west/q1"] = 9.9
    elif attack == "old_profile":
        value["profile_id"] = "igrm:gdelt-ngram-identity:1.1.0"
    elif attack == "identity":
        value["document_ids"] = ["secret"]
    elif attack == "title":
        value["titles"] = ["secret"]
    elif attack == "url_list":
        value["article_urls"] = ["https://publisher.test/a"]
    else:
        value["document_hashes"] = ["c" * 64]
    value = ngram_daily_attestation.seal(value)
    with pytest.raises(ngram_daily_attestation.AggregateAttestationError):
        ngram_daily_attestation.validate(
            value,
            target=DAY,
            specs=SPECS,
            root=root,
            expected_calibration_sha256="a" * 64,
        )


def test_source_refetch_unavailable_and_mismatch_are_distinct(tmp_path: Path) -> None:
    _root, value = _fixture(tmp_path)
    with pytest.raises(ngram_daily_attestation.AggregateAttestationError, match="unavailable"):
        ngram_daily_attestation.audit_source_objects(value, fetch=lambda _url: None)
    with pytest.raises(ngram_daily_attestation.AggregateAttestationError, match="mismatch"):
        ngram_daily_attestation.audit_source_objects(value, fetch=lambda _url: b"wrong")


@pytest.mark.parametrize(
    "attack",
    ("root", "binding", "window", "source", "reconstruction", "unicode_alias"),
)
def test_attestation_recursively_refuses_unknown_fields(
    tmp_path: Path, attack: str
) -> None:
    root, attacked = _fixture(tmp_path)
    if attack == "root":
        attacked["membership"] = []
    elif attack == "binding":
        attacked["method_bindings"]["dictionary_alias"] = "0" * 64
    elif attack == "window":
        attacked["windows"][0]["document_count"] = 1
    elif attack == "source":
        attacked["windows"][0]["source_objects"]["toc"]["content_hash"] = "0" * 64
    elif attack == "reconstruction":
        attacked["aggregate_reconstruction"]["members"] = []
    else:
        attacked["windows"][0]["group_numerators"]["west／q1"] = 0
    attacked = ngram_daily_attestation.seal(attacked)
    with pytest.raises(ngram_daily_attestation.AggregateAttestationError):
        ngram_daily_attestation.validate(
            attacked,
            target=DAY,
            specs=SPECS,
            root=root,
            expected_calibration_sha256="a" * 64,
        )


def test_ordered_backlog_never_jumps_or_includes_d0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "docs/data").mkdir(parents=True)
    (tmp_path / "data/raw/legacy_aggregate_verification").mkdir(parents=True)
    (tmp_path / "docs/data/latest.json").write_text('{"date":"2026-08-09"}')
    assert final_publication.required_next_target(root=tmp_path, today=date(2026, 8, 12)) == date(
        2026, 8, 9
    )
    monkeypatch.setattr(
        final_publication, "_legacy_upgrade_receipt_is_bound", lambda _root: True
    )
    assert final_publication.required_next_target(root=tmp_path, today=date(2026, 8, 12)) == date(
        2026, 8, 10
    )
    (tmp_path / "docs/data/latest.json").write_text('{"date":"2026-08-11"}')
    assert final_publication.required_next_target(root=tmp_path, today=date(2026, 8, 12)) is None
    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_ordered_target(
            date(2026, 8, 11), root=tmp_path, today=date(2026, 8, 12)
        )


def _write_latest(root: Path, day: date) -> None:
    (root / "docs/data").mkdir(parents=True, exist_ok=True)
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": day.isoformat()})
    )


def test_two_and_three_day_catchup_replans_after_each_immutable_tip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        final_publication, "_legacy_upgrade_receipt_is_bound", lambda _root: True
    )
    _write_latest(tmp_path, date(2026, 8, 9))
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) == date(2026, 8, 10)
    # First candidate is now an immutable remote tip; the next run refetches.
    _write_latest(tmp_path, date(2026, 8, 10))
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) == date(2026, 8, 11)
    _write_latest(tmp_path, date(2026, 8, 11))
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) is None
    # A three-day backlog uses the same strict chain and still excludes D0.
    _write_latest(tmp_path, date(2026, 8, 9))
    assert [
        final_publication.required_next_target(
            root=tmp_path, today=date(2026, 8, 13)
        )
    ] == [date(2026, 8, 10)]


def _write_marker(root: Path, *, target: date, stage: str, code: str, status: str) -> None:
    # The durable per-day ledger entry, not the overwritten status marker:
    # marker-based skip authority self-erased the moment the next day was
    # attempted (run 31720836972).
    path = (
        root
        / final_publication.REFUSAL_LEDGER_RELATIVE
        / f"{target.isoformat()}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "target_date": target.isoformat(),
                "failure_stage": stage,
                "reason_code": code,
                "status": status,
            }
        )
    )


def test_disclosed_lost_source_day_advances_exactly_one_and_only_when_aged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 2026-08-11 livelock: a provider day that left the temporary window
    republished the same refusal forever while every later day starved. A
    committed SOURCE-stage refusal disclosure for exactly latest+1, aged at
    least one day past D-1, advances the pointer one day. Nothing else does.
    """
    monkeypatch.setattr(
        final_publication, "_legacy_upgrade_receipt_is_bound", lambda _root: True
    )
    _write_latest(tmp_path, date(2026, 8, 10))
    today = date(2026, 8, 13)

    # No marker: never skip.
    assert final_publication.required_next_target(
        root=tmp_path, today=today
    ) == date(2026, 8, 11)

    # Published source refusal for latest+1, aged (11 <= 13-2): advance one.
    _write_marker(
        tmp_path,
        target=date(2026, 8, 11),
        stage="source",
        code="source_acquisition_failed",
        status="acquisition_failed",
    )
    assert final_publication.required_next_target(
        root=tmp_path, today=today
    ) == date(2026, 8, 12)

    # A FRESH source outage (D-1 itself) must keep retrying, not skip.
    _write_latest(tmp_path, date(2026, 8, 11))
    _write_marker(
        tmp_path,
        target=date(2026, 8, 12),
        stage="source",
        code="source_acquisition_failed",
        status="acquisition_failed",
    )
    assert final_publication.required_next_target(
        root=tmp_path, today=today
    ) == date(2026, 8, 12)

    # Infrastructure failures are retryable defects and never advance.
    _write_latest(tmp_path, date(2026, 8, 10))
    for stage, code, status in (
        ("derived", "derived_validation_failed", "pipeline_failed"),
        ("pipeline", "pipeline_failed", "pipeline_failed"),
        ("gate", "gate_failed", "pipeline_failed"),
    ):
        _write_marker(
            tmp_path, target=date(2026, 8, 11), stage=stage, code=code, status=status
        )
        assert final_publication.required_next_target(
            root=tmp_path, today=today
        ) == date(2026, 8, 11)

    # A marker for a DIFFERENT day than latest+1 never advances.
    _write_marker(
        tmp_path,
        target=date(2026, 8, 12),
        stage="source",
        code="source_acquisition_failed",
        status="acquisition_failed",
    )
    assert final_publication.required_next_target(
        root=tmp_path, today=today
    ) == date(2026, 8, 11)

    # The advance is one day at a time and never crosses the D0 ceiling.
    _write_latest(tmp_path, date(2026, 8, 11))
    _write_marker(
        tmp_path,
        target=date(2026, 8, 12),
        stage="source",
        code="source_acquisition_failed",
        status="acquisition_failed",
    )
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 13)
    ) == date(2026, 8, 12)  # 12 > 13-2 fails the age rule: retry, no skip
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 14)
    ) == date(2026, 8, 13)  # aged now; one-day advance to the new D-1


def test_catchup_stops_and_restarts_at_first_unavailable_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        final_publication, "_legacy_upgrade_receipt_is_bound", lambda _root: True
    )
    _write_latest(tmp_path, date(2026, 8, 9))
    first = final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    )
    assert first == date(2026, 8, 10)
    # An unavailable first day changes no final bytes; restart selects it again.
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) == first
    _write_latest(tmp_path, first)
    second = final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    )
    assert second == date(2026, 8, 11)
    # A second-day refusal cannot relabel it or progress beyond it.
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) == second


def test_remote_movement_is_recomputed_and_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        final_publication, "_legacy_upgrade_receipt_is_bound", lambda _root: True
    )
    _write_latest(tmp_path, date(2026, 8, 9))
    frozen_attempt = final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    )
    assert frozen_attempt == date(2026, 8, 10)
    # Another publisher moves the remote. A newly dispatched run reads that
    # tip and advances from it rather than replaying the stale frozen attempt.
    _write_latest(tmp_path, date(2026, 8, 10))
    assert final_publication.required_next_target(
        root=tmp_path, today=date(2026, 8, 12)
    ) == date(2026, 8, 11)


def test_workflow_dispatches_exactly_one_successor_after_legacy_receipt() -> None:
    workflow = (ROOT / ".github/workflows/morning.yml").read_text(encoding="utf-8")
    successor = workflow.split(
        "- name: Continue ordered backlog from the new immutable remote tip", 1
    )[1]
    assert successor.count("gh workflow run morning.yml") == 1
    assert "steps.publish.outcome == 'success'" in successor
    assert "dispatch_morning_successor.py" in successor
    assert "git fetch --quiet origin main" in successor
    assert '"dispatch_authorized": true' in successor
    guard = workflow.split("- name: Cheap disjoint preflight", 1)[0]
    assert 'if [ "$TARGET" = "$CEILING" ] && python -m src.final_publication' in guard


def _successor_repo(tmp_path: Path, *, target: date, progressed: bool) -> tuple[Path, str, str]:
    root = tmp_path / "successor"
    (root / "docs/data").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test.invalid"], cwd=root, check=True)
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": "2026-08-09"}) + "\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    if progressed:
        (root / "docs/data/latest.json").write_text(
            json.dumps({"date": target.isoformat()}) + "\n", encoding="utf-8"
        )
    else:
        (root / "refusal.json").write_text("{}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "result"], cwd=root, check=True)
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", result], cwd=root, check=True
    )
    return root, base, result


def test_successor_dispatch_requires_progress_and_bounded_authority_epoch(
    tmp_path: Path,
) -> None:
    from scripts import dispatch_morning_successor as dispatch

    root, base, result = _successor_repo(
        tmp_path, target=date(2026, 8, 10), progressed=True
    )
    first = dispatch.authorize(
        root=root,
        base=base,
        result=result,
        target=date(2026, 8, 10),
        source_run="123",
        authority_epoch=1,
    )
    assert first["dispatch_authorized"] is True
    assert first["dedupe_boundary"] == "serialized_workflow_plus_exact_remote_progress"
    # The workflow-level concurrency group serializes attempts. A retry is
    # bounded to three authority epochs and must prove the same immutable tip.
    second = dispatch.authorize(
        root=root,
        base=base,
        result=result,
        target=date(2026, 8, 10),
        source_run="123",
        authority_epoch=2,
    )
    assert second["record_sha256"] != first["record_sha256"]
    with pytest.raises(dispatch.SuccessorDispatchError, match="authority_epoch_exhausted"):
        dispatch.authorize(
            root=root,
            base=base,
            result=result,
            target=date(2026, 8, 10),
            source_run="123",
            authority_epoch=4,
        )


def test_successor_dispatch_refuses_value_free_no_progress(tmp_path: Path) -> None:
    from scripts import dispatch_morning_successor as dispatch

    root, base, result = _successor_repo(
        tmp_path, target=date(2026, 8, 10), progressed=False
    )
    with pytest.raises(dispatch.SuccessorDispatchError, match="measured_progress_invalid"):
        dispatch.authorize(
            root=root,
            base=base,
            result=result,
            target=date(2026, 8, 10),
            source_run="124",
            authority_epoch=1,
        )
