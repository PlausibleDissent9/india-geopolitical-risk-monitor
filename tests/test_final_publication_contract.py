"""Focused fail-closed tests for the visitor-visible D-1 final contract."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest
import requests
from src import (
    fetch_gdelt,
    fetch_ngrams,
    final_publication,
    run_daily,
)

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 8, 10)
TARGET = date(2026, 8, 9)
PREFIX_DAY = date(2026, 8, 8)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stamp(index: int) -> str:
    minute = index * 30
    return f"{TARGET:%Y%m%d}{minute // 60:02d}{minute % 60:02d}00"


def _specs() -> dict[str, dict]:
    return {
        "pakistan_west/q1": {
            "channel": "pakistan_west",
            "anchor": "india",
            "phrases": [("border",)],
        }
    }


def _complete_result(root: Path) -> dict:
    stamps = [_stamp(index) for index in range(48)]
    raw_keys = [f"{stamps[0]}:A", f"{stamps[1]}:B"]
    raw_english = [*raw_keys]
    raw_english.extend(
        f"{stamps[index % len(stamps)]}:filler-{index}" for index in range(98)
    )
    identities = {
        key: fetch_ngrams._document_identity(key) for key in raw_english
    }
    english = sorted(identities.values())
    keys = [identities[key] for key in raw_keys]
    canonical_specs = fetch_ngrams._canonical_specs(_specs())
    return {
        "date": TARGET.isoformat(),
        "n_docs_sampled": 100,
        "n_samples": 48,
        "n_samples_loaded": 48,
        "partial": False,
        "shares": {"pakistan_west/q1": 2.0},
        "_matcher_evidence": {
            "schema_version": fetch_ngrams.MATCHER_EVIDENCE_VERSION,
            "day": TARGET.isoformat(),
            "located_stamps": stamps,
            "loaded_stamps": stamps,
            "missing_stamps": [],
            "matcher_specs": canonical_specs,
            "matcher_specs_sha256": _sha(
                json.dumps(
                    canonical_specs, sort_keys=True, separators=(",", ":")
                ).encode()
            ),
            "dictionaries_sha256": _sha((root / "dictionaries.json").read_bytes()),
            "production_matcher_sha256": _sha(
                (root / "src/fetch_ngrams.py").read_bytes()
            ),
            "english_document_identities": english,
            "english_document_counts_by_stamp": {
                stamp: sum(key.startswith(f"{stamp}:") for key in english)
                for stamp in stamps
            },
            "india_document_keys": keys,
            "matched_document_keys": {"pakistan_west/q1": keys},
            "article_meta": {
                key: {
                    "date": f"{TARGET:%Y%m%d}",
                    "title": f"Eligible article {index}",
                    "url": f"https://example.test/{index}",
                }
                for index, key in enumerate(keys)
            },
        },
    }


def _legacy_result(root: Path) -> dict:
    result = _complete_result(root)
    stamps = [_stamp(index) for index in range(48)]
    raw = [f"{stamps[0]}:A", f"{stamps[1]}:B"]
    evidence = result["_matcher_evidence"]
    evidence["schema_version"] = "1.0.0"
    evidence.pop("english_document_identities")
    evidence.pop("english_document_counts_by_stamp")
    evidence["india_document_keys"] = raw
    evidence["matched_document_keys"] = {"pakistan_west/q1": raw}
    evidence["article_meta"] = {
        key: {
            "date": f"{TARGET:%Y%m%d}",
            "title": f"Legacy eligible article {index}",
            "url": f"https://legacy.example.test/{index}",
        }
        for index, key in enumerate(raw)
    }
    return result


def _publication_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "docs/data").mkdir(parents=True)
    dictionary = {
        "pakistan_west": {
            "label": "Pakistan / western border",
            "terms": ['"border"'],
            "anchor": "india",
        }
    }
    (root / "dictionaries.json").write_text(
        json.dumps(dictionary) + "\n", encoding="utf-8"
    )
    (root / "src/fetch_ngrams.py").write_text(
        "# exact matcher fixture\n", encoding="utf-8"
    )
    (root / "data/raw/gdelt_volume.csv").write_text(
        "date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8"
    )
    (root / "data/raw/provenance.csv").write_text(
        "date,source,basis\n2026-08-08,ngram_bridge,recorded\n",
        encoding="utf-8",
    )
    (root / "data/raw/ngram_calibration.json").write_text(
        json.dumps({"pakistan_west": {"ratio": 2.0, "n_days": 5}}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/latest.json").write_text(
        json.dumps(
            {
                "date": PREFIX_DAY.isoformat(),
                "composite": 49.0,
                "composite7": 49.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/history.json").write_text(
        json.dumps({"dates": [PREFIX_DAY.isoformat()], "composite": [49.0]})
        + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/status.json").write_text(
        json.dumps({"_meta": {"generated": "2026-08-09T00:00:00Z"}}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/index.html").write_text(
        "<!--final-publication-static:start-->old"
        "<!--final-publication-static:end-->",
        encoding="utf-8",
    )
    (root / "docs/status.html").write_text(
        "<!--final-publication-status-static:start-->old"
        "<!--final-publication-status-static:end-->",
        encoding="utf-8",
    )
    return root


def _trust(root: Path) -> final_publication.NonGitTestTrustRoot:
    return final_publication.non_git_test_trust_root(root, "a" * 40)


def _write_target_outputs(root: Path) -> None:
    (root / "docs/data/latest.json").write_text(
        json.dumps(
            {
                "date": TARGET.isoformat(),
                "composite": 50.0,
                "composite7": 50.0,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/history.json").write_text(
        json.dumps(
            {
                "dates": [PREFIX_DAY.isoformat(), TARGET.isoformat()],
                "composite": [49.0, 50.0],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _stamp_attacks() -> dict[str, list[str]]:
    valid = [_stamp(index) for index in range(48)]
    return {
        "clustered_48": [f"{TARGET:%Y%m%d}00{index:02d}00" for index in range(48)],
        "invalid_calendar": ["20260230000100", *valid[1:]],
        "invalid_hour": [f"{TARGET:%Y%m%d}240100", *valid[1:]],
        "invalid_minute": [f"{TARGET:%Y%m%d}006000", *valid[1:]],
        "nonzero_seconds": [f"{TARGET:%Y%m%d}000001", *valid[1:]],
        "duplicate_bucket": [*valid[:-1], f"{TARGET:%Y%m%d}230100"],
    }


def _rewrite_stamps(result: dict, stamps: list[str]) -> None:
    evidence = result["_matcher_evidence"]
    evidence["located_stamps"] = stamps
    evidence["loaded_stamps"] = stamps


def _reseal_receipt_marker(root: Path, receipt: dict) -> None:
    receipt_path = root / f"data/raw/final_publication_receipts/{TARGET}.json"
    receipt_path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    marker_path = root / final_publication.STATUS_RELATIVE
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["receipt"]["sha256"] = _sha(final_publication._canonical_bytes(receipt))
    marker_path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")


def _acquire(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    result: dict | None,
) -> dict:
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    return final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        base_commit="a" * 40,
        compute_day=lambda _day, _specs_arg: result,
    )


def test_exact_d_minus_one_complete_frame_promotes_target_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    store_prefix = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_prefix = (root / "data/raw/provenance.csv").read_bytes()

    status = _acquire(root, monkeypatch, _complete_result(root))

    assert status["status"] == "target_ready"
    store = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance = (root / "data/raw/provenance.csv").read_bytes()
    assert store.startswith(store_prefix)
    assert provenance.startswith(provenance_prefix)
    assert store.decode().splitlines()[-1] == "2026-08-09,1.0"
    assert provenance.decode().splitlines()[-1] == (
        "2026-08-09,ngram_bridge,recorded"
    )
    assert "2026-08-10" not in store.decode()
    receipt = final_publication.require_promotion_receipt(
        TARGET,
        root=root,
        require_bridge_receipt=True,
        non_git_test_trust=trust,
    )
    assert receipt is not None
    assert receipt["frame"]["n_samples_located"] == 48
    assert receipt["frame"]["n_samples_loaded"] == 48
    assert receipt["append_contract"]["old_prefix_equal"] is True
    assert receipt["append_contract"]["d0_excluded"] is True
    assert set(receipt["bindings"]) == {
        "calibration_sha256",
        "calibration_records_sha256",
        "dictionary_sha256",
        "matcher_sha256",
        "matcher_specs_sha256",
        "candidate_row_sha256",
    }


@pytest.mark.parametrize(
    ("result_factory", "expected_state"),
    [
        (lambda _root: None, "source_unavailable"),
        (
            lambda root: {
                **_complete_result(root),
                "n_samples": 1,
                "n_samples_loaded": 1,
                "_matcher_evidence": {
                    **_complete_result(root)["_matcher_evidence"],
                    "located_stamps": [_stamp(0)],
                    "loaded_stamps": [_stamp(0)],
                },
            },
            "acquisition_failed",
        ),
    ],
)
def test_refusal_discloses_typed_state_without_banking_candidate_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    result_factory: Callable[[Path], dict | None],
    expected_state: str,
) -> None:
    root = _publication_root(tmp_path)
    value_paths = [
        root / "data/raw/gdelt_volume.csv",
        root / "data/raw/provenance.csv",
    ]
    before = {path: path.read_bytes() for path in value_paths}

    result = result_factory(root)
    status = _acquire(root, monkeypatch, result)

    assert status["status"] == expected_state
    assert status["value_fields_published"] is False
    assert status["provisional_substitution_allowed"] is False
    assert {path: path.read_bytes() for path in value_paths} == before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
    assert not (root / f"data/raw/final_publication_receipts/{TARGET}.json").exists()


@pytest.mark.parametrize("shape", ["47_of_47", "48_of_47", "partial_true"])
def test_every_incomplete_frame_shape_refuses_without_canonical_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
) -> None:
    root = _publication_root(tmp_path)
    result = _complete_result(root)
    evidence = result["_matcher_evidence"]
    if shape == "47_of_47":
        result["n_samples"] = 47
        result["n_samples_loaded"] = 47
        evidence["located_stamps"] = evidence["located_stamps"][:-1]
        evidence["loaded_stamps"] = evidence["loaded_stamps"][:-1]
    elif shape == "48_of_47":
        result["n_samples_loaded"] = 47
        evidence["loaded_stamps"] = evidence["loaded_stamps"][:-1]
        evidence["missing_stamps"] = [evidence["located_stamps"][-1]]
    else:
        result["partial"] = True
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_before = (root / "data/raw/provenance.csv").read_bytes()

    status = _acquire(root, monkeypatch, result)

    assert status["status"] == "acquisition_failed"
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert (root / "data/raw/provenance.csv").read_bytes() == provenance_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()


@pytest.mark.parametrize("attack", sorted(_stamp_attacks()))
def test_fresh_acquisition_refuses_invalid_or_duplicate_bucket_stamps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    result = _complete_result(root)
    _rewrite_stamps(result, _stamp_attacks()[attack])
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()

    status = _acquire(root, monkeypatch, result)

    assert status["status"] == "acquisition_failed"
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()


@pytest.mark.parametrize("attack", sorted(_stamp_attacks()))
def test_promotion_revalidates_real_half_hour_bucket_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == (
        "target_ready"
    )
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    payload = json.loads(cache.read_text(encoding="utf-8"))
    _rewrite_stamps(payload, _stamp_attacks()[attack])
    cache.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        final_publication.FinalPublicationError,
        match="^promotion_receipt_invalid$",
    ) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert "frame_invalid" in exc.value.detail


@pytest.mark.parametrize("fail_after", range(1, 6))
def test_candidate_bundle_failpoint_restores_every_canonical_value_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_after: int,
) -> None:
    root = _publication_root(tmp_path)
    store = root / "data/raw/gdelt_volume.csv"
    provenance = root / "data/raw/provenance.csv"
    before = {store: store.read_bytes(), provenance: provenance.read_bytes()}
    original = final_publication._atomic_write
    calls = 0

    def interrupted(path: Path, data: bytes) -> None:
        nonlocal calls
        calls += 1
        original(path, data)
        if calls == fail_after:
            raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(final_publication, "_atomic_write", interrupted)
    status = _acquire(root, monkeypatch, _complete_result(root))

    assert status["status"] == "acquisition_failed"
    assert {store: store.read_bytes(), provenance: provenance.read_bytes()} == before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
    assert not (
        root / f"data/raw/final_publication_receipts/{TARGET}.json"
    ).exists()
    marker = json.loads((root / final_publication.STATUS_RELATIVE).read_text())
    assert marker["status"] == "acquisition_failed"


def test_failed_daily_staging_drops_an_interrupted_unverified_bundle(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    shutil.copytree(ROOT / "src", root / "src")
    (root / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/stage_daily_outputs.sh",
        root / "scripts/stage_daily_outputs.sh",
    )
    shutil.copy2(ROOT / "dictionaries.json", root / "dictionaries.json")
    (root / "data/raw").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "notes-inbox").mkdir()
    (root / "docs/index.html").write_text("frozen docs\n", encoding="utf-8")
    (root / "notes-inbox/.keep").write_text("\n", encoding="utf-8")
    (root / ".trigger").write_text("frozen\n", encoding="utf-8")
    store = root / "data/raw/gdelt_volume.csv"
    provenance = root / "data/raw/provenance.csv"
    store.write_text("date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8")
    provenance.write_text(
        "date,source,basis\n2026-08-08,ngram_bridge,recorded\n",
        encoding="utf-8",
    )
    (root / "data/raw/ngram_calibration.json").write_text(
        json.dumps({"pakistan_west": {"ratio": 2.0}}) + "\n",
        encoding="utf-8",
    )
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Daily staging test"),
        ("config", "user.email", "daily-staging@example.invalid"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    store_before = store.read_bytes()
    provenance_before = provenance.read_bytes()
    store.write_bytes(store_before + b"2026-08-09,1.0\n")
    provenance.write_bytes(
        provenance_before + b"2026-08-09,ngram_bridge,recorded\n"
    )
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    receipt = root / f"data/raw/final_publication_receipts/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    receipt.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"date": TARGET.isoformat()}), encoding="utf-8")
    receipt.write_text(json.dumps({"target_date": TARGET.isoformat()}), encoding="utf-8")
    (root / final_publication.STATUS_RELATIVE).write_text(
        json.dumps({"target_date": TARGET.isoformat(), "status": "target_ready"}),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHON"] = str(ROOT / ".venv/bin/python")
    subprocess.run(
        ["bash", "scripts/stage_daily_outputs.sh", "failure"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert staged == []
    assert store.read_bytes() == store_before
    assert provenance.read_bytes() == provenance_before
    assert not cache.exists()
    assert not receipt.exists()
    assert not (root / final_publication.STATUS_RELATIVE).exists()


def test_typed_network_classification_distinguishes_404_from_transport_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        def __init__(self, status: int) -> None:
            self.status_code = status

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(str(self.status_code))

    unavailable_root = _publication_root(tmp_path / "unavailable")
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: Response(404),
    )
    monkeypatch.setattr(
        fetch_ngrams,
        "_day_minute_files",
        lambda *_args, **_kwargs: (
            []
            if fetch_ngrams._probe_window(TARGET, 0, 2) is None
            else pytest.fail("404 source unexpectedly located")
        ),
    )

    unavailable = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=unavailable_root,
        compute_day=fetch_ngrams.compute_day,
    )

    failed_root = _publication_root(tmp_path / "failed")
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            requests.Timeout("timed out")
        ),
    )
    failed = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=failed_root,
        compute_day=fetch_ngrams.compute_day,
    )

    assert unavailable["status"] == "source_unavailable"
    assert failed["status"] == "acquisition_failed"
    assert "NgramAcquisitionError" in failed["reason"]


def test_typed_network_classification_treats_5xx_as_acquisition_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Response:
        status_code = 503

        @staticmethod
        def raise_for_status() -> None:
            raise requests.HTTPError("503")

    root = _publication_root(tmp_path)
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: Response(),
    )

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: (
            None
            if fetch_ngrams._probe_window(TARGET, 0, 2) is None
            else pytest.fail("5xx source unexpectedly located")
        ),
    )

    assert status["status"] == "acquisition_failed"


def test_forged_latest_date_is_not_treated_as_already_finalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat()}), encoding="utf-8"
    )
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: pytest.fail("already-finalized target reacquired"),
    )

    assert status["status"] == "acquisition_failed"
    assert "lacks a valid finalized proof" in status["reason"]
    public = final_publication.public_status(root=root, today=TODAY)
    assert public["finalized"] is False
    assert public["latest_finalized_date"] is None
    assert public["source_receipt"] is None


def test_frozen_legacy_target_remains_visible_only_as_proof_limited(
    tmp_path: Path,
) -> None:
    root = _publication_root(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_legacy_result(root)), encoding="utf-8")
    _write_target_outputs(root)

    public = final_publication.public_status(root=root, today=TODAY)

    assert public["status"] == "legacy_proof_limited"
    assert public["latest_finalized_date"] == TARGET.isoformat()
    assert public["finalized"] is False
    assert public["source_receipt"] is None
    assert "48 half-hour windows are verified" in public["reason"]
    assert "cannot be independently reconstructed" in public["reason"]


def test_receipt_revalidation_refuses_bound_input_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == "target_ready"
    calibration = root / "data/raw/ngram_calibration.json"
    calibration.write_text(
        json.dumps({"pakistan_west": {"ratio": 3.0, "n_days": 5}}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        final_publication.FinalPublicationError,
        match="^promotion_receipt_invalid$",
    ):
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )


@pytest.mark.parametrize(
    ("attack", "detail"),
    (
        ("store_prefix", "store_prefix_differs_from_frozen_parent"),
        ("provenance_prefix", "provenance_prefix_differs_from_frozen_parent"),
        ("target_row", "target_row_does_not_recompute"),
        ("base_splice", "frozen_parent_binding_mismatch"),
    ),
)
def test_coordinated_receipt_and_marker_reseals_cannot_self_attest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
    detail: str,
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == (
        "target_ready"
    )
    receipt_path = root / f"data/raw/final_publication_receipts/{TARGET}.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if attack == "store_prefix":
        store = root / "data/raw/gdelt_volume.csv"
        store.write_text(
            store.read_text(encoding="utf-8").replace("2026-08-08,0.25", "2026-08-08,99"),
            encoding="utf-8",
        )
        prefix = store.read_bytes().splitlines(keepends=True)[:-1]
        receipt["append_contract"]["store_prefix_sha256"] = _sha(b"".join(prefix))
    elif attack == "provenance_prefix":
        provenance = root / "data/raw/provenance.csv"
        provenance.write_text(
            provenance.read_text(encoding="utf-8").replace(
                "2026-08-08,ngram_bridge,recorded",
                "2026-08-08,gdelt_doc_api,recorded",
            ),
            encoding="utf-8",
        )
        prefix = provenance.read_bytes().splitlines(keepends=True)[:-1]
        receipt["append_contract"]["provenance_prefix_sha256"] = _sha(
            b"".join(prefix)
        )
    elif attack == "target_row":
        store = root / "data/raw/gdelt_volume.csv"
        store.write_text(
            store.read_text(encoding="utf-8").replace("2026-08-09,1.0", "2026-08-09,0.5"),
            encoding="utf-8",
        )
        receipt["bindings"]["candidate_row_sha256"] = _sha(
            final_publication._canonical_bytes(
                {"date": TARGET.isoformat(), "pakistan_west": 0.5}
            )
        )
    else:
        receipt["base_commit"] = "b" * 40
        marker_path = root / final_publication.STATUS_RELATIVE
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        marker["base_commit"] = "b" * 40
        marker_path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
    _reseal_receipt_marker(root, receipt)

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert exc.value.detail == detail


@pytest.mark.parametrize("attack", ("no_receipt", "wrong_status", "receipt_drift"))
def test_mark_finalized_requires_live_target_ready_proof_and_written_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    _write_target_outputs(root)
    if attack == "no_receipt":
        pass
    else:
        # Acquisition sees the D-2 public prefix, then the pipeline writes D-1.
        (root / "docs/data/latest.json").write_text(
            json.dumps(
                {
                    "date": PREFIX_DAY.isoformat(),
                    "composite": 49.0,
                    "composite7": 49.0,
                }
            ),
            encoding="utf-8",
        )
        assert _acquire(root, monkeypatch, _complete_result(root))["status"] == (
            "target_ready"
        )
        _write_target_outputs(root)
        if attack == "wrong_status":
            marker_path = root / final_publication.STATUS_RELATIVE
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["status"] = "pipeline_failed"
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
        else:
            receipt_path = root / f"data/raw/final_publication_receipts/{TARGET}.json"
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["bindings"]["candidate_row_sha256"] = "0" * 64
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.mark_finalized(
            TARGET,
            root=root,
            non_git_test_trust=trust,
        )

    public = final_publication.public_status(
        root=root,
        today=TODAY,
        non_git_test_trust=trust,
    )
    assert public["status"] != "finalized"
    assert public["finalized"] is False
    assert public["source_receipt"] is None


def test_cached_ineligible_day_cannot_stick_or_override_fresh_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    ineligible = _complete_result(root)
    ineligible["partial"] = True
    cache.write_text(json.dumps(ineligible), encoding="utf-8")

    status = _acquire(root, monkeypatch, _complete_result(root))

    assert status["status"] == "target_ready"
    banked = json.loads(cache.read_text(encoding="utf-8"))
    assert banked["partial"] is False
    assert banked["n_samples"] == 48


def test_daily_guard_requires_exact_d_minus_one_and_excludes_d0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    days = pd.date_range("2025-01-01", TARGET)
    complete = pd.DataFrame({"pakistan_west": 1.0}, index=days)
    monkeypatch.setattr(run_daily, "SITE_DATA", Path("/path/that/does/not/exist"))

    accepted = run_daily._fail_loudly_on_partial_data(complete, TARGET)
    assert accepted.index.max().date() == TARGET

    with pytest.raises(SystemExit, match="exact D-1 target"):
        run_daily._fail_loudly_on_partial_data(complete.iloc[:-1], TARGET)

    with_d0 = pd.concat(
        [
            complete,
            pd.DataFrame(
                {"pakistan_west": [999.0]}, index=[pd.Timestamp(TODAY)]
            ),
        ]
    )
    with pytest.raises(SystemExit, match="rows after exact final target"):
        run_daily._fail_loudly_on_partial_data(with_d0, TARGET)


def test_target_nulls_and_null_composites_refuse_before_site_write() -> None:
    index = pd.to_datetime([TARGET])
    daily = pd.DataFrame(
        {"pakistan_west": [1.0], "composite": [1.0]}, index=index
    )
    headline = daily.copy()
    headline.loc[index[0], "composite"] = float("nan")
    with pytest.raises(SystemExit, match="headline target"):
        run_daily._require_exact_target_scores(daily, headline, TARGET)

    daily.loc[index[0], "pakistan_west"] = float("nan")
    with pytest.raises(SystemExit, match="daily target score row contains nulls"):
        run_daily._require_exact_target_scores(daily, daily.fillna(1.0), TARGET)


def test_written_latest_and_history_must_end_at_finite_target(tmp_path: Path) -> None:
    site = tmp_path / "docs/data"
    site.mkdir(parents=True)
    latest = {
        "date": TARGET.isoformat(),
        "composite": 50.0,
        "composite7": 51.0,
    }
    history = {"dates": [PREFIX_DAY.isoformat(), TARGET.isoformat()], "composite": [49.0, 50.0]}
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    (site / "history.json").write_text(json.dumps(history), encoding="utf-8")

    run_daily._require_written_target(TARGET, site_data=site)

    latest["composite"] = None
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    with pytest.raises(SystemExit, match="non_finite_target"):
        run_daily._require_written_target(TARGET, site_data=site)

    latest["composite"] = 50.0
    history["dates"][-1] = TODAY.isoformat()
    (site / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    (site / "history.json").write_text(json.dumps(history), encoding="utf-8")
    with pytest.raises(SystemExit, match="written_latest_history_do_not_end"):
        run_daily._require_written_target(TARGET, site_data=site)


def test_provisional_payload_never_launders_a_missing_final(tmp_path: Path) -> None:
    root = _publication_root(tmp_path)
    (root / "docs/data/nowcast.json").write_text(
        json.dumps(
            {"date": TODAY.isoformat(), "provisional": True, "composite": 99.9}
        ),
        encoding="utf-8",
    )

    status = final_publication.public_status(root=root, today=TODAY)

    assert status["status"] == "delayed_final"
    assert status["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert status["finalized"] is False
    assert status["provisional_substitution_allowed"] is False
    assert "composite" not in status


def test_public_refusal_status_is_value_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    marker = _acquire(root, monkeypatch, None)
    public = final_publication.public_status(root=root, today=TODAY)

    value_keys = {"composite", "composite7", "score", "score7", "channels", "shares"}

    def keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | {key for nested in value.values() for key in keys(nested)}
        if isinstance(value, list):
            return {key for nested in value for key in keys(nested)}
        return set()

    assert value_keys.isdisjoint(keys(marker))
    assert value_keys.isdisjoint(keys(public))
    assert marker["value_fields_published"] is False
    assert public["value_fields_published"] is False


def test_failed_pipeline_disclosure_uses_published_prefix_not_dirty_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == "target_ready"
    # Simulate run_daily having written an uncommitted candidate latest.json
    # before a later audit/gate refused publication.
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat(), "composite": 99.9}),
        encoding="utf-8",
    )
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_before = (root / "data/raw/provenance.csv").read_bytes()

    marker = final_publication.record_pipeline_failed(
        TARGET, root=root, base_commit="a" * 40
    )
    public = final_publication.write_public_status(root=root, today=TODAY)

    assert marker["status"] == "pipeline_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert public["status"] == "pipeline_failed"
    assert public["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert public["finalized"] is False
    assert "composite" not in public
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert (root / "data/raw/provenance.csv").read_bytes() == provenance_before
    for path in (root / "docs/index.html", root / "docs/status.html"):
        text = path.read_text(encoding="utf-8")
        assert "publication validation failed" in text
        assert TARGET.isoformat() in text
        assert PREFIX_DAY.isoformat() in text


def test_refusal_ignores_unpushed_finalized_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = _publication_root(tmp_path / "candidate")
    trust = _trust(candidate)
    assert _acquire(candidate, monkeypatch, _complete_result(candidate))["status"] == "target_ready"
    _write_target_outputs(candidate)
    finalized = final_publication.mark_finalized(
        TARGET,
        root=candidate,
        non_git_test_trust=trust,
    )
    assert finalized["latest_finalized_date"] == TARGET.isoformat()

    # The workflow constructs disclosure from the frozen parent and copies
    # only the operational marker. The unpushed candidate date must not cross
    # that boundary when a later audit/derived step fails.
    refusal = _publication_root(tmp_path / "refusal")
    (refusal / final_publication.STATUS_RELATIVE).write_text(
        (candidate / final_publication.STATUS_RELATIVE).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    marker = final_publication.record_pipeline_failed(
        TARGET, root=refusal, base_commit="a" * 40, failure_stage="audit"
    )

    assert marker["status"] == "pipeline_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()


def test_hard_source_step_failure_is_typed_acquisition_failed(tmp_path: Path) -> None:
    root = _publication_root(tmp_path)

    marker = final_publication.record_pipeline_failed(
        TARGET, root=root, base_commit="a" * 40, failure_stage="source"
    )

    assert marker["status"] == "acquisition_failed"
    assert marker["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert marker["value_fields_published"] is False


def test_gdelt_target_vintage_preserves_old_prefix_and_excludes_d0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    store = raw / "gdelt_volume.csv"
    store.write_text(
        "date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8"
    )
    monkeypatch.setattr(fetch_gdelt, "RAW_DIR", raw)
    observed: list[tuple[date, date]] = []

    def fetch(_dictionary: dict, start: date, end: date) -> pd.DataFrame:
        observed.append((start, end))
        return pd.DataFrame(
            {"pakistan_west": [1.0]}, index=pd.Index([TARGET], name="date")
        )

    monkeypatch.setattr(fetch_gdelt, "fetch_all", fetch)
    result = fetch_gdelt.load_or_update(
        {"pakistan_west": {}},
        end_date=TARGET,
        immutable_through=PREFIX_DAY,
    )

    assert observed == [(TARGET, TARGET)]
    assert result.loc[PREFIX_DAY, "pakistan_west"] == 0.25
    assert result.loc[TARGET, "pakistan_west"] == 1.0
    assert TODAY not in result.index

    store.write_text(
        "date,pakistan_west\n2026-08-08,0.25\n2026-08-10,9.0\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="D0/future"):
        fetch_gdelt.load_or_update(
            {"pakistan_west": {}},
            end_date=TARGET,
            immutable_through=PREFIX_DAY,
        )


def test_morning_gate_is_bounded_once_per_candidate_and_cas_only() -> None:
    workflow = (ROOT / ".github/workflows/morning.yml").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts/publish_final_cas.sh").read_text(encoding="utf-8")
    assert (
        "python -m pytest -q tests/test_dictionaries.py "
        "tests/test_registration_freezes.py"
    ) in workflow
    assert "python -m pytest -q\n" not in workflow
    assert "bash scripts/publish_push.sh" not in workflow
    assert workflow.count("bash scripts/publish_final_cas.sh") == 1
    assert workflow.count("git push origin HEAD:main") == 0
    assert publisher.count("bash scripts/gate.sh --committed") == 1
    assert publisher.count("git push origin HEAD:main") == 1
    assert 'REMOTE_COMMIT=$(git rev-parse origin/main)' in publisher
    assert "/usr/bin/time -v" in publisher
    assert "git worktree add --detach" in publisher
    publish_lane = workflow.split(
        "- name: Gate and CAS-publish final or value-free refusal", 1
    )[1]
    assert "id: publish" in publish_lane
    refusal_function = publisher.split("publish_refusal()", 1)[1]
    assert "git add data/raw/final_publication_status.json docs/data/status.json" in refusal_function
    assert "failure disclosure attempted to stage candidate value bytes" in refusal_function
    assert '--failure-stage "$failure_stage"' in refusal_function
    assert "failure_stage=source" in refusal_function
    assert "steps.pipeline.outcome == 'success'" in workflow
    assert "steps.audit.outcome == 'success'" in workflow
    assert '"${{ steps.derived.outcome }}"' in workflow
    assert '[ "$DERIVED_OUTCOME" = "success" ]' in publisher
    success_dispatch = publisher.rsplit(
        'if [ "$SOURCE_OUTCOME" = "success" ]', 1
    )[1]
    assert "publish_final" in success_dispatch
    assert "publish_refusal" not in success_dispatch.split("else", 1)[0]
    for command in (
        "timeout --signal=TERM 14m python -m src.final_publication",
        "timeout --signal=TERM 7m python -m src.run_daily --final-only",
        "timeout --signal=TERM 2m python -m src.audit",
        "timeout --signal=TERM 5m bash -c",
    ):
        assert command in workflow
    assert "timeout --signal=TERM 27m" not in workflow
    assert "36m42s" in workflow and "24m55s" in workflow
    assert "0.687s locally" in workflow and "run #43" in workflow
    assert "job cap remains the only" in workflow


def test_rescue_predicates_and_public_pages_use_final_date_contract() -> None:
    for relative in (
        ".github/workflows/nowcast.yml",
        ".github/workflows/watchdog.yml",
    ):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert "['date']" in workflow
        assert "['_meta']['generated']" not in workflow
        assert 'date -u -d "yesterday" +%F' in workflow

    homepage = (ROOT / "docs/index.html").read_text(encoding="utf-8")
    app = (ROOT / "docs/app.js").read_text(encoding="utf-8")
    status_page = (ROOT / "docs/status.html").read_text(encoding="utf-8")
    status = json.loads((ROOT / "docs/data/status.json").read_text(encoding="utf-8"))
    final_state = status["final_publication"]
    assert 'id="final-publication-status"' in homepage
    assert 'id="final-publication-status" hidden' not in homepage
    for text in (homepage, status_page):
        assert "Legacy final with proof limitation" in text
        assert "target <b>2026-08-09</b> remains published" in text
        assert "48 half-hour windows are verified" in text
        assert "cannot be independently reconstructed" in text
        assert "No new-contract source receipt is claimed" in text
        assert "provisional nowcast remains separate and non-final" in text
    assert "provisional nowcast remains separate and non-final" in app
    assert final_state["status"] == "legacy_proof_limited"
    assert final_state["latest_finalized_date"] == TARGET.isoformat()
    assert final_state["finalized"] is False
    assert final_state["source_receipt"] is None
