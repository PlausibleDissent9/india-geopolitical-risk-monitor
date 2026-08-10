"""Prospective v3 source-frame tests; no labels or precision result exist."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from src import fetch_ngrams
from src import precision_frame_v3 as frame

ROOT = Path(__file__).resolve().parents[1]
DAY = date(2026, 8, 8)


@pytest.fixture(autouse=True)
def _synthetic_cache_rights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        frame.ngram_rights,
        "require_public_identity_rights",
        lambda **_kwargs: {"status": "synthetic_authorized_fixture"},
    )


def _stamp(index: int, day: date = DAY) -> str:
    minute = index * 30
    return f"{day:%Y%m%d}{minute // 60:02d}{minute % 60:02d}00"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_source_cache(
    root: Path,
    day: date = DAY,
    dictionary_bytes: bytes = b'{"version":"test"}\n',
    *,
    strong: bool | None = None,
    stamps: list[str] | None = None,
) -> Path:
    matcher_bytes = b"# frozen production matcher fixture\n"
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "dictionaries.json").write_bytes(dictionary_bytes)
    (root / "src" / "fetch_ngrams.py").write_bytes(matcher_bytes)

    if strong is None:
        strong = day > frame.LEGACY_EVIDENCE_LAST_DAY
    stamps = stamps or [_stamp(index, day) for index in range(48)]
    first = f"{stamps[0]}:A"
    second = f"{stamps[1]}:B"
    specs = {
        "pakistan_west/q1": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [["border"]],
        },
        "pakistan_west/q2": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [["ceasefire"]],
        },
    }
    specs_sha = _sha(
        json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()
    )
    evidence: dict[str, object] = {
        "schema_version": (
            frame.STRONG_MATCHER_EVIDENCE_VERSION
            if strong
            else frame.LEGACY_MATCHER_EVIDENCE_VERSION
        ),
        "day": day.isoformat(),
        "located_stamps": stamps,
        "loaded_stamps": stamps,
        "missing_stamps": [],
        "matcher_specs": specs,
        "matcher_specs_sha256": specs_sha,
        "dictionaries_sha256": _sha(dictionary_bytes),
        "production_matcher_sha256": _sha(matcher_bytes),
    }
    article_meta = {
            first: {
                "date": f"{day:%Y%m%d}",
                "title": "Border and ceasefire item",
                "url": "https://one.example/a",
            },
            second: {
                "date": f"{day:%Y%m%d}",
                "title": "Border item",
                "url": "https://two.example/b",
            },
    }
    if strong:
        raw_english = [first, second]
        raw_english.extend(
            f"{stamps[index % len(stamps)]}:filler-{index}" for index in range(98)
        )
        identities = {
            key: fetch_ngrams._document_identity(key) for key in raw_english
        }
        english = sorted(identities.values())
        evidence.update(
            {
                "english_document_identities": english,
                "english_document_counts_by_stamp": {
                    stamp: sum(key.startswith(f"{stamp}:") for key in english)
                    for stamp in stamps
                },
                "india_document_keys": [identities[first], identities[second]],
                "matched_document_keys": {
                    "pakistan_west/q1": [identities[first], identities[second]],
                    "pakistan_west/q2": [identities[first]],
                },
                "article_meta": {
                    identities[key]: value for key, value in article_meta.items()
                },
            }
        )
    else:
        evidence.update(
            {
                "india_document_keys": [first, second],
                "matched_document_keys": {
                    "pakistan_west/q1": [first, second],
                    "pakistan_west/q2": [first],
                },
                "article_meta": article_meta,
            }
        )
    payload = {
        "date": day.isoformat(),
        "n_docs_sampled": 100,
        "n_samples": 48,
        "n_samples_loaded": 48,
        "partial": False,
        "shares": {
            "pakistan_west/q1": 2.0,
            "pakistan_west/q2": 1.0,
        },
        "_matcher_evidence": evidence,
    }
    path = root / "data" / "raw" / "ngram_days" / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_production_scan_captures_exact_matcher_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetch_ngrams.ngram_rights,
        "require_public_identity_rights",
        lambda **_kwargs: {"status": "synthetic_authorized_fixture"},
    )
    stamp = _stamp(0)
    toc = gzip.compress(
        "\n".join(
            json.dumps(row)
            for row in (
                {
                    "ID": "A",
                    "lang": "en",
                    "date": "2026-08-08",
                    "title": "Border and ceasefire item",
                    "url": "https://one.example/a",
                },
                {
                    "ID": "B",
                    "lang": "en",
                    "date": "2026-08-08",
                    "title": "Border item",
                    "url": "https://two.example/b",
                },
            )
        ).encode()
    )
    ngrams = gzip.compress(
        b"A\tindia region\nA\tborder ceasefire\nB\tindia region\nB\tborder area\n"
    )
    specs = {
        "pakistan_west/q1": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [("border",)],
        },
        "pakistan_west/q2": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [("ceasefire",)],
        },
    }
    monkeypatch.setattr(fetch_ngrams, "_day_minute_files", lambda *_args: [stamp])
    monkeypatch.setattr(
        fetch_ngrams,
        "prefetch_pairs",
        lambda _stamps: iter([(stamp, toc, ngrams)]),
    )

    result = fetch_ngrams.compute_day(DAY, specs, min_docs=1)

    assert result is not None
    assert result["shares"] == {
        "pakistan_west/q1": 100.0,
        "pakistan_west/q2": 50.0,
    }
    assert result["n_samples_loaded"] == 1
    assert result["partial"] is False
    evidence = result["_matcher_evidence"]
    assert evidence["located_stamps"] == [stamp]
    assert evidence["loaded_stamps"] == [stamp]
    assert evidence["missing_stamps"] == []
    first = fetch_ngrams._document_identity(f"{stamp}:A")
    second = fetch_ngrams._document_identity(f"{stamp}:B")
    assert evidence["english_document_identities"] == sorted([first, second])
    assert evidence["english_document_counts_by_stamp"] == {stamp: 2}
    assert evidence["matched_document_keys"]["pakistan_west/q1"] == sorted(
        [first, second]
    )
    assert evidence["matched_document_keys"]["pakistan_west/q2"] == [
        first
    ]
    assert evidence["article_meta"][first]["url"] == "https://one.example/a"


def test_day_attestation_preserves_group_contribution_multiplicity(
    tmp_path: Path,
) -> None:
    _write_source_cache(tmp_path)

    result = frame.build_day_attestation(
        DAY, tmp_path, require_live_hashes=False
    )

    channel = result["channels"]["pakistan_west"]
    assert result["status"] == "ELIGIBLE_SOURCE_DAY_NO_LABELS"
    assert channel == {
        "n_group_contributions": 3,
        "n_distinct_document_keys": 2,
        "multi_group_contribution_excess": 1,
    }
    assert result["groups"]["pakistan_west/q1"]["reconstructed_share"] == 2.0
    assert result["groups"]["pakistan_west/q2"]["reconstructed_share"] == 1.0
    assert result["denominator_evidence"] == (
        "source_reported_denominator_legacy_v1.0"
    )
    assert result["labels_seen"] is False
    assert result["precision_estimated"] is False


def test_day_attestation_refuses_rights_before_source_cache_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write_source_cache(tmp_path)
    reads: list[Path] = []
    original = Path.read_bytes

    def refused(**_kwargs: object) -> dict[str, object]:
        raise frame.ngram_rights.NgramRightsError(
            "ngram_rights_decision_review_required"
        )

    def observed(path: Path) -> bytes:
        if path == source:
            reads.append(path)
        return original(path)

    monkeypatch.setattr(frame.ngram_rights, "require_public_identity_rights", refused)
    monkeypatch.setattr(Path, "read_bytes", observed)

    with pytest.raises(
        frame.ngram_rights.NgramRightsError,
        match="^ngram_rights_decision_review_required$",
    ):
        frame.build_day_attestation(
            DAY, tmp_path, require_live_hashes=False
        )

    assert reads == []


def _offset_stamps(day: date) -> list[str]:
    return [
        f"{day:%Y%m%d}{index // 2:02d}{(index % 2) * 30 + 1:02d}00"
        for index in range(48)
    ]


def _invalid_stamp_frames(day: date) -> dict[str, list[str]]:
    valid = _offset_stamps(day)
    return {
        "clustered_48": [f"{day:%Y%m%d}00{index:02d}00" for index in range(48)],
        "invalid_calendar": ["20260230000100", *valid[1:]],
        "invalid_hour": [f"{day:%Y%m%d}240100", *valid[1:]],
        "invalid_minute": [f"{day:%Y%m%d}006000", *valid[1:]],
        "nonzero_seconds": [f"{day:%Y%m%d}000101", *valid[1:]],
        "duplicate_bucket": [*valid[:-1], f"{day:%Y%m%d}230100"],
    }


def test_strong_frame_accepts_first_available_minute_in_every_bucket(
    tmp_path: Path,
) -> None:
    day = date(2026, 8, 10)
    _write_source_cache(tmp_path, day, strong=True, stamps=_offset_stamps(day))

    attestation = frame.build_day_attestation(
        day,
        tmp_path,
        require_live_hashes=False,
        require_strong_denominator=True,
    )

    assert attestation["n_samples_loaded"] == 48
    assert attestation["denominator_evidence"] == "hashed_identity_membership_v1.1"


@pytest.mark.parametrize("attack", sorted(_invalid_stamp_frames(date(2026, 8, 10))))
def test_strong_frame_refuses_invalid_or_duplicate_bucket_stamps(
    tmp_path: Path,
    attack: str,
) -> None:
    day = date(2026, 8, 10)
    _write_source_cache(
        tmp_path,
        day,
        strong=True,
        stamps=_invalid_stamp_frames(day)[attack],
    )

    with pytest.raises(frame.FrameValidationError):
        frame.build_day_attestation(
            day,
            tmp_path,
            require_live_hashes=False,
            require_strong_denominator=True,
        )


@pytest.mark.parametrize(
    "attack",
    (
        "denominator_reseal",
        "duplicate_english",
        "cross_stamp_english",
        "india_not_subset",
        "matched_not_subset",
        "per_stamp_count",
    ),
)
def test_strong_denominator_membership_attacks_fail_closed(
    tmp_path: Path,
    attack: str,
) -> None:
    path = _write_source_cache(tmp_path, strong=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    evidence = payload["_matcher_evidence"]
    english = evidence["english_document_identities"]
    outsider = f"{_stamp(0)}:{'f' * 64}"
    if attack == "denominator_reseal":
        payload["n_docs_sampled"] = 200
        payload["shares"] = {
            "pakistan_west/q1": 1.0,
            "pakistan_west/q2": 0.5,
        }
    elif attack == "duplicate_english":
        english.append(english[0])
        payload["n_docs_sampled"] += 1
    elif attack == "cross_stamp_english":
        english[0] = f"20260807000000:{english[0].split(':', 1)[1]}"
    elif attack == "india_not_subset":
        evidence["india_document_keys"].append(outsider)
    elif attack == "matched_not_subset":
        evidence["matched_document_keys"]["pakistan_west/q1"].append(outsider)
    else:
        evidence["english_document_counts_by_stamp"][_stamp(0)] += 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(frame.FrameValidationError):
        frame.build_day_attestation(
            DAY,
            tmp_path,
            require_live_hashes=False,
            require_strong_denominator=True,
        )


def test_new_publication_cannot_fall_back_to_legacy_denominator(
    tmp_path: Path,
) -> None:
    _write_source_cache(tmp_path, strong=False)

    with pytest.raises(frame.FrameValidationError, match="schema 1.1.0"):
        frame.build_day_attestation(
            DAY,
            tmp_path,
            require_live_hashes=False,
            require_strong_denominator=True,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("share", "does not reproduce"),
        ("partial", "partial production days"),
        ("missing_stamp", "not every located"),
        ("missing_meta", "lacks metadata"),
        ("spec_hash", "specification hash mismatch"),
        ("live_matcher_hash", "does not match the live scoring source"),
    ],
)
def test_ineligible_or_tampered_source_days_fail_closed(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    path = _write_source_cache(tmp_path)
    payload = json.loads(path.read_text())
    evidence = payload["_matcher_evidence"]
    if mutation == "share":
        payload["shares"]["pakistan_west/q1"] = 2.1
    elif mutation == "partial":
        payload["partial"] = True
    elif mutation == "missing_stamp":
        evidence["missing_stamps"] = [_stamp(0)]
    elif mutation == "missing_meta":
        evidence["article_meta"].pop(f"{_stamp(0)}:A")
    elif mutation == "spec_hash":
        evidence["matcher_specs_sha256"] = "0" * 64
    else:
        evidence["production_matcher_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(frame.FrameValidationError, match=message):
        frame.build_day_attestation(
            DAY,
            tmp_path,
            require_live_hashes=mutation == "live_matcher_hash",
        )


def test_day_attestations_are_append_only(tmp_path: Path) -> None:
    path = _write_source_cache(tmp_path)
    destination = frame.record_day(DAY, tmp_path, require_live_hashes=False)
    original = destination.read_bytes()

    payload = json.loads(path.read_text())
    stamp = _stamp(2)
    key = f"{stamp}:C"
    payload["_matcher_evidence"]["india_document_keys"].append(key)
    payload["_matcher_evidence"]["matched_document_keys"][
        "pakistan_west/q1"
    ].append(key)
    payload["_matcher_evidence"]["article_meta"][key] = {
        "date": "20260808",
        "title": "A third border item",
        "url": "https://three.example/c",
    }
    payload["shares"]["pakistan_west/q1"] = 3.0
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(frame.FrameValidationError, match="existing v3 day"):
        frame.record_day(DAY, tmp_path, require_live_hashes=False)
    assert destination.read_bytes() == original


def test_frame_failure_is_immutable_but_does_not_break_the_later_calendar(
    tmp_path: Path,
) -> None:
    failed_source = _write_source_cache(tmp_path)
    payload = json.loads(failed_source.read_text())
    payload["partial"] = True
    failed_source.write_text(json.dumps(payload), encoding="utf-8")

    failed_path = frame.record_day_outcome(
        DAY, tmp_path, require_live_hashes=False
    )
    failed = json.loads(failed_path.read_text())
    assert failed["status"] == "FRAME_FAILURE_NO_LABELS"
    assert failed["source_cache_sha256"] == _sha(failed_source.read_bytes())
    assert failed["observed"]["partial"] is True
    assert failed["labels_seen"] is False
    assert failed["precision_estimated"] is False

    next_day = date(2026, 8, 9)
    _write_source_cache(tmp_path, next_day)
    eligible_path = frame.record_day(
        next_day, tmp_path, require_live_hashes=False
    )
    eligible = json.loads(eligible_path.read_text())
    assert eligible["status"] == "ELIGIBLE_SOURCE_DAY_NO_LABELS"

    payload["partial"] = False
    failed_source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(frame.FrameValidationError, match="existing v3 day"):
        frame.record_day_outcome(DAY, tmp_path, require_live_hashes=False)


def test_source_window_refuses_gaps_and_regime_changes(tmp_path: Path) -> None:
    _write_source_cache(tmp_path)
    frame.record_day(DAY, tmp_path, require_live_hashes=False)

    day_ten = date(2026, 8, 10)
    _write_source_cache(tmp_path, day_ten)
    with pytest.raises(frame.FrameValidationError, match="missing, extra"):
        frame.record_day(day_ten, tmp_path, require_live_hashes=False)

    day_nine = date(2026, 8, 9)
    _write_source_cache(
        tmp_path,
        day_nine,
        dictionary_bytes=b'{"version":"changed"}\n',
    )
    with pytest.raises(frame.FrameValidationError, match="regime changed"):
        frame.record_day(day_nine, tmp_path, require_live_hashes=False)


def test_regime_change_records_failure_and_keeps_calendar_chain(
    tmp_path: Path,
) -> None:
    _write_source_cache(tmp_path)
    frame.record_day_outcome(DAY, tmp_path, require_live_hashes=False)

    changed = b'{"version":"changed"}\n'
    day_nine = date(2026, 8, 9)
    _write_source_cache(tmp_path, day_nine, dictionary_bytes=changed)
    failed_nine = frame.record_day_outcome(
        day_nine, tmp_path, require_live_hashes=False
    )
    payload_nine = json.loads(failed_nine.read_text())
    assert payload_nine["status"] == "FRAME_FAILURE_NO_LABELS"
    assert "regime changed" in payload_nine["failure_reason"]

    day_ten = date(2026, 8, 10)
    _write_source_cache(tmp_path, day_ten, dictionary_bytes=changed)
    failed_ten = frame.record_day_outcome(
        day_ten, tmp_path, require_live_hashes=False
    )
    payload_ten = json.loads(failed_ten.read_text())
    assert payload_ten["status"] == "FRAME_FAILURE_NO_LABELS"
    assert "regime changed" in payload_ten["failure_reason"]


def test_new_day_rechecks_every_prior_source_cache(tmp_path: Path) -> None:
    first_path = _write_source_cache(tmp_path)
    frame.record_day(DAY, tmp_path, require_live_hashes=False)
    _write_source_cache(tmp_path, date(2026, 8, 9))
    first_path.write_bytes(first_path.read_bytes() + b" ")

    with pytest.raises(frame.FrameValidationError, match="prior source cache changed"):
        frame.record_day(
            date(2026, 8, 9), tmp_path, require_live_hashes=False
        )


def test_independent_dictionary_parser_matches_the_production_specification() -> None:
    assert frame._active_specs_from_dictionary(ROOT) == fetch_ngrams._canonical_specs(
        fetch_ngrams.group_specs()
    )


def test_daily_workflow_does_not_read_precision_frames_without_rights() -> None:
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text()
    command = "python -m src.precision_frame_v3 --record-latest"
    assert command not in workflow
    assert "Precision-v3 frame recording remains dormant" in workflow


def test_public_surfaces_distinguish_frame_collection_from_a_result() -> None:
    paths = (
        ROOT / "README.md",
        ROOT / "docs" / "validation.html",
        ROOT / "docs" / "data.html",
        ROOT / "nef" / "REVIEWERS_GUIDE.md",
    )
    for path in paths:
        raw = path.read_text(encoding="utf-8").lower().replace(">", " ")
        text = " ".join(raw.split())
        assert "source-frame collection" in text, path
        assert "paused" in text, path
        assert "signed" in text and "rights" in text, path
        assert "not a precision result" in text or "no v3 sample" in text, path
        assert "42" in text and "v3a" in text, path
        assert "48" in text and "v3b" in text, path
        assert "no v3 exists yet" not in text, path
