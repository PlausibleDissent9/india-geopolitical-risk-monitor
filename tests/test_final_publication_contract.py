"""Focused fail-closed tests for the visitor-visible D-1 final contract."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import pytest
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import (
    fetch_gdelt,
    fetch_ngrams,
    final_publication,
    ngram_daily_attestation,
    ngram_rights,
    ngram_rights_contract,
    nowcast,
    run_daily,
    status_data,
)

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 8, 10)
TARGET = date(2026, 8, 9)
PREFIX_DAY = date(2026, 8, 8)


@pytest.fixture(autouse=True)
def _freeze_synthetic_rights_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the dated synthetic rights fixtures stable across real UTC days.

    Tests of expiry, revocation, max age, and midnight rollover replace this
    clock explicitly. Letting all other cases read the wall clock makes the
    fixed Aug-9/Aug-10 fixtures change meaning merely because CI ran later.
    """

    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_approved_ngram_rights(
    root: Path,
    *,
    reviewed_on: str = "2026-08-08",
    review_due: str = "2027-08-08",
    signer_effective: str = "2026-08-08",
    signer_revoked: str | None = None,
    registry_effective: str = "2026-08-08",
    permitted_uses: list[str] | None = None,
    max_current_age_days: int = 2,
    signer_role: str = "rights_reviewer",
    historical_recovery_targets: list[str] | None = None,
) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signer = {
        "signer_id": "test_ngram_rights_signer",
        "name": "Synthetic test signer",
        "role": signer_role,
        "public_key_ed25519_base64": base64.b64encode(public_key).decode(),
        "effective": signer_effective,
        "revoked_on": signer_revoked,
    }
    _write_json(
        root / "governance/rights_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": registry_effective,
            "default_policy": "deny",
            "signers": [signer],
        },
    )
    uses = permitted_uses or ["model_processing", "publish_derived_value"]
    aggregate_profile = set(uses) == set(ngram_rights.DAILY_AGGREGATE_USES)
    source = {
        "source_id": "gdelt_web_ngrams_v5",
        "name": "Synthetic GDELT NGrams fixture",
        "provider": "Synthetic test provider",
        "role": "news_attention_corpus",
        "authority_class": "aggregator",
        "independence_group": "synthetic_gdelt",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "test:ngrams-public-identity-retention",
        "decision_owner": "Synthetic test owner",
        "signer_id": signer["signer_id"],
        "decision_artifact_path": "governance/rights_decisions/ngrams.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/ngrams.sig",
        "reviewed_on": reviewed_on,
        "review_due": review_due,
        "access_url": "https://example.test/ngrams",
        "terms_url": (
            "https://www.gdeltproject.org/about.html"
            if aggregate_profile
            else "https://example.test/terms"
        ),
        "access_basis": "synthetic_test_fixture",
        "geographic_coverage": "Synthetic fixture",
        "historical_coverage": "Synthetic fixture day",
        "retrieval_target": "Synthetic identity commitments",
        "outage_fallback": "Fail closed",
        "cost_owner": "Synthetic test owner",
        "reproducibility_tier": "test_only",
        "max_current_age_days": max_current_age_days,
        "permitted_uses": uses,
        "notes": "Synthetic test-only authorization; not a real rights decision.",
    }
    decision = {
        "schema_version": "1.1.0" if aggregate_profile else "1.0.0",
        **{
            key: source[key]
            for key in (
                "source_id",
                "name",
                "provider",
                "role",
                "authority_class",
                "independence_group",
                "decision_id",
                "decision_owner",
                "signer_id",
                "reviewed_on",
                "review_due",
                "access_url",
                "terms_url",
                "access_basis",
                "lineage_policy",
                "max_current_age_days",
                "permitted_uses",
            )
        },
        "statement": "Synthetic authorization for exact test-only uses.",
    }
    if aggregate_profile:
        expected_recovery_targets = ngram_rights_contract.historical_recovery_targets(
            date.fromisoformat(reviewed_on)
        )
        recovery_targets = (
            expected_recovery_targets
            if historical_recovery_targets is None
            else historical_recovery_targets
        )
        decision.update(
            profile_id="igrm:gdelt-ngram-daily-aggregate:2.0.0",
            official_terms_citation={
                "url": "https://www.gdeltproject.org/about.html",
                "publisher": "The GDELT Project",
                "review_scope": "about page dataset-use and redistribution terms",
            },
            historical_recovery_targets=recovery_targets,
            historical_recovery_targets_sha256=(
                ngram_rights_contract.historical_recovery_targets_sha256(
                    recovery_targets
                )
            ),
        )
    decision_path = root / str(source["decision_artifact_path"])
    _write_json(decision_path, decision)
    (root / str(source["decision_signature_path"])).write_bytes(
        private_key.sign(decision_path.read_bytes())
    )
    source["decision_artifact_sha256"] = _sha(decision_path.read_bytes())
    _write_json(
        root / "governance/source_rights_registry.json",
        {
            "schema_version": "1.0.0",
            "effective": registry_effective,
            "default_policy": "deny",
            "sources": [source],
        },
    )


def _set_ngram_rights_pending(root: Path) -> None:
    path = root / "governance/source_rights_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    source = registry["sources"][0]
    source.update(
        decision_state="review_required",
        decision_id="pending:gdelt_web_ngrams_v5",
        signer_id=None,
        decision_artifact_path=None,
        decision_artifact_sha256=None,
        decision_signature_path=None,
        reviewed_on=None,
        review_due=None,
        max_current_age_days=None,
        permitted_uses=[],
    )
    _write_json(path, registry)


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


def _identity_result(root: Path) -> dict:
    stamps = [_stamp(index) for index in range(48)]
    raw_keys = [f"{stamps[0]}:A", f"{stamps[1]}:B"]
    raw_english = [*raw_keys]
    raw_english.extend(f"{stamps[index % len(stamps)]}:filler-{index}" for index in range(98))
    identities = {key: fetch_ngrams._document_identity(key) for key in raw_english}
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
                json.dumps(canonical_specs, sort_keys=True, separators=(",", ":")).encode()
            ),
            "dictionaries_sha256": _sha((root / "dictionaries.json").read_bytes()),
            "production_matcher_sha256": _sha((root / "src/fetch_ngrams.py").read_bytes()),
            "english_document_identities": english,
            "english_document_counts_by_stamp": {
                stamp: sum(key.startswith(f"{stamp}:") for key in english) for stamp in stamps
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


def _complete_result(root: Path) -> dict:
    stamps = [_stamp(index) for index in range(48)]
    canonical_specs = fetch_ngrams._canonical_specs(_specs())
    denominators = [3, 3, *([2] * 45), 4]
    windows = []
    for bucket, (stamp, denominator) in enumerate(zip(stamps, denominators)):
        toc_url, ngram_url = ngram_daily_attestation.source_urls(stamp)
        windows.append(
            {
                "bucket": bucket,
                "stamp": stamp,
                "source_objects": {
                    "toc": {
                        "url": toc_url,
                        "sha256": _sha(f"toc-{stamp}".encode()),
                        "bytes": len(f"toc-{stamp}"),
                    },
                    "ngrams": {
                        "url": ngram_url,
                        "sha256": _sha(f"ngrams-{stamp}".encode()),
                        "bytes": len(f"ngrams-{stamp}"),
                    },
                },
                "english_denominator": denominator,
                "group_numerators": {"pakistan_west/q1": 1 if bucket < 2 else 0},
            }
        )
    attestation = {
        "schema_version": ngram_daily_attestation.SCHEMA_VERSION,
        "profile_id": ngram_daily_attestation.PROFILE_ID,
        "day": TARGET.isoformat(),
        "expected_windows": 48,
        "located_windows": 48,
        "loaded_windows": 48,
        "method_bindings": {
            "profile_sha256": _sha((root / ngram_daily_attestation.PROFILE_RELATIVE).read_bytes()),
            "schema_sha256": _sha((root / ngram_daily_attestation.SCHEMA_RELATIVE).read_bytes()),
            "dictionaries_sha256": _sha((root / "dictionaries.json").read_bytes()),
            "production_matcher_sha256": _sha((root / "src/fetch_ngrams.py").read_bytes()),
            "validator_sha256": _sha((root / "src/ngram_daily_attestation.py").read_bytes()),
            "calibration_sha256": _sha((root / "data/raw/ngram_calibration.json").read_bytes()),
            "matcher_specs": canonical_specs,
            "matcher_specs_sha256": _sha(ngram_daily_attestation.canonical_bytes(canonical_specs)),
        },
        "windows": windows,
        "aggregate_reconstruction": {
            "window_order": list(range(48)),
            "english_denominator": 100,
            "group_numerators": {"pakistan_west/q1": 2},
            "shares": {"pakistan_west/q1": 2.0},
            "channel_sums": {"pakistan_west": 2.0},
        },
        "membership_reproducibility": ngram_daily_attestation.MEMBERSHIP_LIMIT,
    }
    return {
        "date": TARGET.isoformat(),
        "n_docs_sampled": 100,
        "n_samples": 48,
        "n_samples_loaded": 48,
        "partial": False,
        "shares": {"pakistan_west/q1": 2.0},
        "_aggregate_attestation": ngram_daily_attestation.seal(attestation),
    }


def _legacy_result(root: Path) -> dict:
    result = _identity_result(root)
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
    (root / "dictionaries.json").write_text(json.dumps(dictionary) + "\n", encoding="utf-8")
    (root / "src/fetch_ngrams.py").write_text("# exact matcher fixture\n", encoding="utf-8")
    shutil.copy2(
        ROOT / "src/ngram_daily_attestation.py",
        root / "src/ngram_daily_attestation.py",
    )
    for relative in (
        ngram_daily_attestation.PROFILE_RELATIVE,
        ngram_daily_attestation.SCHEMA_RELATIVE,
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
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
        json.dumps({"dates": [PREFIX_DAY.isoformat()], "composite": [49.0]}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/data/status.json").write_text(
        json.dumps({"_meta": {"generated": "2026-08-09T00:00:00Z"}}) + "\n",
        encoding="utf-8",
    )
    (root / "docs/index.html").write_text(
        "<!--final-publication-static:start-->old<!--final-publication-static:end-->",
        encoding="utf-8",
    )
    (root / "docs/status.html").write_text(
        "<!--final-publication-status-static:start-->old<!--final-publication-status-static:end-->",
        encoding="utf-8",
    )
    _write_approved_ngram_rights(root)
    return root


def _trust(root: Path) -> final_publication.NonGitTestTrustRoot:
    return final_publication.non_git_test_trust_root(root, "a" * 40)


def _rights(root: Path) -> ngram_rights.NonGitTestRightsAuthority:
    return ngram_rights.non_git_test_authority(root)


def _authorize_production_test_signer(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = json.loads((root / "governance/rights_signers.json").read_text(encoding="utf-8"))
    signer = registry["signers"][0]
    monkeypatch.setattr(
        ngram_rights,
        "PRODUCTION_TRUSTED_SIGNERS",
        {
            signer["signer_id"]: (
                signer["public_key_ed25519_base64"],
                signer["role"],
            )
        },
    )


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
    evidence = result["_aggregate_attestation"]
    for row, stamp in zip(evidence["windows"], stamps):
        row["stamp"] = stamp
        toc_url, ngram_url = ngram_daily_attestation.source_urls(stamp)
        row["source_objects"]["toc"]["url"] = toc_url
        row["source_objects"]["ngrams"]["url"] = ngram_url
    result["_aggregate_attestation"] = ngram_daily_attestation.seal(evidence)


def _reseal_receipt_marker(root: Path, receipt: dict) -> None:
    receipt_path = root / f"data/raw/final_publication_receipts/{TARGET}.json"
    receipt_path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    marker_path = root / final_publication.STATUS_RELATIVE
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["receipt"]["sha256"] = _sha(final_publication._json_bytes(receipt))
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
        non_git_test_rights=_rights(root),
    )


def _legacy_verification_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    root = _publication_root(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(_legacy_result(root)), encoding="utf-8")
    with (root / "data/raw/gdelt_volume.csv").open("a", encoding="utf-8") as handle:
        handle.write("2026-08-09,1.0\n")
    with (root / "data/raw/provenance.csv").open("a", encoding="utf-8") as handle:
        handle.write("2026-08-09,ngram_bridge,recorded\n")
    (root / "docs/data/latest.json").write_text(
        json.dumps({"date": TARGET.isoformat(), "composite": 54.5, "composite7": 54.5})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        final_publication,
        "is_exact_legacy_cache_exception",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    return root


def test_aug9_aggregate_upgrade_matches_without_rewriting_legacy_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_verification_root(tmp_path, monkeypatch)
    protected = (
        root / f"data/raw/ngram_days/{TARGET}.json",
        root / "data/raw/gdelt_volume.csv",
        root / "data/raw/provenance.csv",
        root / "docs/data/latest.json",
        root / "docs/data/history.json",
    )
    before = {path: path.read_bytes() for path in protected}
    receipt = final_publication.verify_legacy_under_aggregate_profile(
        root=root,
        compute_day=lambda *_args: _complete_result(root),
        non_git_test_rights=_rights(root),
    )
    assert receipt["status"] == "legacy_verified_under_aggregate_profile"
    assert receipt["public_score_claim_added"] is False
    assert {path: path.read_bytes() for path in protected} == before
    # An idempotent restart revalidates the receipt and exact old-byte hashes.
    assert final_publication.verify_legacy_under_aggregate_profile(
        root=root, non_git_test_rights=_rights(root)
    ) == receipt
    assert final_publication.required_next_target(
        root=root, today=date(2026, 8, 12)
    ) == date(2026, 8, 10)


def test_aug9_recovery_proof_revalidates_at_delayed_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_verification_root(tmp_path, monkeypatch)
    _write_approved_ngram_rights(
        root,
        reviewed_on="2026-08-13",
        review_due="2027-08-13",
        signer_effective="2026-08-13",
        registry_effective="2026-08-13",
        max_current_age_days=3,
    )
    _authorize_production_test_signer(root, monkeypatch)
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
    )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Recovery test"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "recovery.invalid"], cwd=root, check=True
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "legacy base"], cwd=root, check=True)
    base_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    receipt = final_publication.verify_legacy_under_aggregate_profile(
        root=root,
        compute_day=lambda *_args: _complete_result(root),
    )
    assert receipt["rights"]["recovery_exception_used"] is True
    assert receipt["rights"]["reviewed_on"] == "2026-08-13"
    assert receipt["rights"]["rights_as_of"] == "2026-08-14"
    receipt_path = root / "data/raw/legacy_aggregate_verification/2026-08-09.json"
    subprocess.run(["git", "add", str(receipt_path)], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "aggregate verification"], cwd=root, check=True)
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert final_publication.verify_legacy_under_aggregate_profile(root=root) == receipt
    release = final_publication.require_release_candidate(
        "verification",
        expected_candidate_sha=candidate,
        base_commit=base_commit,
        expected_target=TARGET,
        root=root,
    )
    assert release["status"] == "legacy_aggregate_verification_release_verified"
    assert release["value_fields_published"] is False


def test_aug9_aggregate_upgrade_refuses_value_mismatch_and_unavailable_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_verification_root(tmp_path, monkeypatch)
    mismatch = _complete_result(root)
    mismatch["shares"]["pakistan_west/q1"] = 3.0
    with pytest.raises(final_publication.FinalPublicationError, match="legacy_verification_refused"):
        final_publication.verify_legacy_under_aggregate_profile(
            root=root,
            compute_day=lambda *_args: mismatch,
            non_git_test_rights=_rights(root),
        )
    receipt = root / "data/raw/legacy_aggregate_verification/2026-08-09.json"
    assert not receipt.exists()
    with pytest.raises(final_publication.FinalPublicationError, match="legacy_verification_refused"):
        final_publication.verify_legacy_under_aggregate_profile(
            root=root,
            compute_day=lambda *_args: None,
            non_git_test_rights=_rights(root),
        )
    assert not receipt.exists()


@pytest.mark.parametrize("attack", ("empty_map", "partial_map", "extra_map", "extra_field", "row_reseal"))
def test_legacy_upgrade_receipt_is_closed_and_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    root = _legacy_verification_root(tmp_path, monkeypatch)
    final_publication.verify_legacy_under_aggregate_profile(
        root=root,
        compute_day=lambda *_args: _complete_result(root),
        non_git_test_rights=_rights(root),
    )
    path = root / "data/raw/legacy_aggregate_verification/2026-08-09.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if attack == "empty_map":
        receipt["legacy_bytes_sha256"] = {}
    elif attack == "partial_map":
        receipt["legacy_bytes_sha256"].pop("docs/data/history.json")
    elif attack == "extra_map":
        receipt["legacy_bytes_sha256"]["../outside"] = "0" * 64
    elif attack == "extra_field":
        receipt["legacy_identity_hashes"] = []
    else:
        receipt["transform"]["channel_values"]["pakistan_west"] = 999.0
    body = {key: value for key, value in receipt.items() if key != "record_sha256"}
    receipt["record_sha256"] = _sha(
        json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.verify_legacy_under_aggregate_profile(
            root=root, non_git_test_rights=_rights(root)
        )


def test_legacy_upgrade_refuses_symlinked_receipt_or_protected_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_verification_root(tmp_path, monkeypatch)
    final_publication.verify_legacy_under_aggregate_profile(
        root=root,
        compute_day=lambda *_args: _complete_result(root),
        non_git_test_rights=_rights(root),
    )
    receipt = root / "data/raw/legacy_aggregate_verification/2026-08-09.json"
    target = tmp_path / "receipt-target.json"
    receipt.replace(target)
    receipt.symlink_to(target)
    assert not final_publication._legacy_upgrade_receipt_is_bound(root)


@pytest.mark.parametrize(
    "rights_attack",
    ("missing", "pending", "revoked", "future_decision"),
)
def test_aggregate_acquisition_requires_current_signed_rights_before_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rights_attack: str,
) -> None:
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )
    root = _publication_root(tmp_path)
    if rights_attack == "missing":
        (root / "governance/rights_decisions/ngrams.sig").unlink()
    elif rights_attack == "pending":
        _set_ngram_rights_pending(root)
    elif rights_attack == "revoked":
        _write_approved_ngram_rights(root, signer_revoked=TODAY.isoformat())
    else:
        _write_approved_ngram_rights(
            root,
            reviewed_on="2026-08-11",
            review_due="2027-08-11",
        )
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    called = False

    def compute(*_args: object) -> dict:
        nonlocal called
        called = True
        return _complete_result(root)

    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        base_commit="a" * 40,
        compute_day=compute,
        non_git_test_rights=_rights(root),
    )

    assert status["status"] == "acquisition_failed"
    assert "aggregate processing refused" in status["reason"]
    assert called is False
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()


def test_cached_day_does_not_fetch_or_retain_strong_evidence_while_rights_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    _set_ngram_rights_pending(root)
    cache_dir = root / "data/raw/ngram_days"
    probes: list[str] = []

    def probe(*_args: object, **_kwargs: object) -> list[str]:
        probes.append("network-probe")
        return []

    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache_dir)
    monkeypatch.setattr(fetch_ngrams, "_day_minute_files", probe)
    with pytest.raises(ngram_rights.NgramRightsError):
        fetch_ngrams._cached_day(TARGET, _specs())

    assert probes == []
    assert not (cache_dir / f"{TARGET}.json").exists()


def _apply_ngram_rights_attack(root: Path, attack: str) -> None:
    if attack == "missing":
        (root / "governance/source_rights_registry.json").unlink()
    elif attack == "pending":
        _set_ngram_rights_pending(root)
    elif attack == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-09")
    elif attack == "revoked":
        _write_approved_ngram_rights(root, signer_revoked=TODAY.isoformat())
    elif attack == "future":
        _write_approved_ngram_rights(
            root,
            reviewed_on="2026-08-11",
            review_due="2027-08-11",
        )
    elif attack == "wrong_use":
        _write_approved_ngram_rights(root, permitted_uses=["model_processing"])
    elif attack == "extra_use":
        _write_approved_ngram_rights(
            root,
            permitted_uses=[
                "model_processing",
                "publish_derived_value",
                "publish_extract",
            ],
        )
    else:
        raise AssertionError(attack)


@pytest.mark.parametrize(
    "rights_attack",
    ("missing", "pending", "expired", "revoked", "future", "wrong_use", "extra_use"),
)
def test_compute_day_and_nowcast_refuse_before_any_source_or_identity_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rights_attack: str,
) -> None:
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )
    direct_root = _publication_root(tmp_path / "direct")
    _apply_ngram_rights_attack(direct_root, rights_attack)
    probes: list[str] = []

    def probe(*_args: object, **_kwargs: object) -> list[str]:
        probes.append("network-probe")
        return []

    monkeypatch.setattr(fetch_ngrams, "ROOT", direct_root)
    monkeypatch.setattr(fetch_ngrams, "_day_minute_files", probe)
    with pytest.raises(ngram_rights.NgramRightsError):
        fetch_ngrams.compute_day(TARGET, _specs(), rights_authority=_rights(direct_root))
    assert probes == []
    assert not (direct_root / "data/raw/ngram_days").exists()

    nowcast_root = _publication_root(tmp_path / "nowcast")
    _apply_ngram_rights_attack(nowcast_root, rights_attack)
    nowcast_out = nowcast_root / "docs/data/nowcast.json"

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(fetch_ngrams, "ROOT", nowcast_root)
    monkeypatch.setattr(nowcast, "ROOT", nowcast_root)
    monkeypatch.setattr(nowcast, "STORE", nowcast_root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", nowcast_root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", nowcast_out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)
    with pytest.raises(ngram_rights.NgramRightsError):
        nowcast.main(rights_authority=_rights(nowcast_root))
    assert probes == []
    assert not nowcast_out.exists()
    assert not (nowcast_root / "data/raw/ngram_days").exists()


def test_compute_day_reaches_probe_with_applicable_signed_rights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    probes: list[date] = []

    def probe(day: date, *_args: object, **_kwargs: object) -> list[str]:
        probes.append(day)
        return []

    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "_day_minute_files", probe)
    assert fetch_ngrams.compute_day(TARGET, _specs(), rights_authority=_rights(root)) is None
    assert probes == [TARGET]


def test_pending_rights_allow_only_exact_pinned_aug9_legacy_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _legacy_history_repo(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    legacy = json.loads(cache.read_text(encoding="utf-8"))
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache.parent)
    monkeypatch.setattr(
        fetch_ngrams,
        "compute_day",
        lambda *_args, **_kwargs: pytest.fail("legacy cache attempted recomputation"),
    )

    assert fetch_ngrams._cached_day(TARGET, _specs()) == legacy


def test_retained_cache_binds_authorized_day_to_path_payload_and_no_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    _write_approved_ngram_rights(
        root,
        permitted_uses=[
            "model_processing",
            "publish_derived_value",
            "publish_extract",
            "redistribute_full_record",
        ],
    )
    cache_dir = root / "data/raw/ngram_days"
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = _identity_result(root)
    payload["date"] = PREFIX_DAY.isoformat()
    cache = cache_dir / f"{TARGET}.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ngram_rights.NgramRightsError) as exc:
        fetch_ngrams.read_retained_identity_cache(
            TARGET,
            root=root,
            rights_authority=_rights(root),
        )
    assert exc.value.code == "ngram_cache_day_binding_invalid"

    other = cache_dir / f"{PREFIX_DAY}.json"
    other.write_text(json.dumps(payload), encoding="utf-8")
    cache.unlink()
    try:
        cache.symlink_to(other)
    except OSError:
        pytest.skip("symlinks unavailable on this filesystem")
    with pytest.raises(ngram_rights.NgramRightsError) as exc:
        fetch_ngrams.read_retained_identity_cache(
            TARGET,
            root=root,
            rights_authority=_rights(root),
        )
    assert exc.value.code == "ngram_cache_path_invalid"


@pytest.mark.parametrize(
    "attack",
    ("downgraded_version", "missing_version", "mixed_fields", "fabricated_legacy"),
)
def test_cache_identity_classification_cannot_be_downgraded_by_schema_label(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    _set_ngram_rights_pending(root)
    day = TARGET if attack != "fabricated_legacy" else date(2026, 8, 7)
    payload = _identity_result(root)
    evidence = payload["_matcher_evidence"]
    if attack == "downgraded_version":
        evidence["schema_version"] = "1.0.0"
    elif attack == "missing_version":
        evidence.pop("schema_version")
    elif attack == "mixed_fields":
        payload = _legacy_result(root)
        payload["_matcher_evidence"]["english_document_identities"] = ["f" * 64]
    else:
        payload = _legacy_result(root)
    cache = root / f"data/raw/ngram_days/{day}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload), encoding="utf-8")
    returned: list[object] = []
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache.parent)
    monkeypatch.setattr(
        fetch_ngrams,
        "compute_day",
        lambda *_args, **_kwargs: pytest.fail("cached evidence was recomputed"),
    )

    with pytest.raises(ngram_rights.NgramRightsError):
        returned.append(fetch_ngrams._cached_day(day, _specs()))

    assert returned == []


@pytest.mark.parametrize("rights_attack", ("expired", "revoked"))
def test_identity_bearing_cached_day_rechecks_rights_before_processing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rights_attack: str,
) -> None:
    root = _publication_root(tmp_path)
    if rights_attack == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-09")
    else:
        _write_approved_ngram_rights(root, signer_revoked=TODAY.isoformat())
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_complete_result(root)), encoding="utf-8")
    probes: list[str] = []
    processed: list[str] = []
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache.parent)
    monkeypatch.setattr(
        fetch_ngrams,
        "_day_minute_files",
        lambda *_args, **_kwargs: probes.append("network") or [],
    )

    with pytest.raises(ngram_rights.NgramRightsError):
        value = fetch_ngrams._cached_day(
            TARGET,
            _specs(),
            rights_authority=_rights(root),
        )
        processed.append(str(value))

    assert probes == []
    assert processed == []


@pytest.mark.parametrize(
    ("day", "expected_reads"),
    ((date(2026, 8, 8), 0), (TARGET, 1)),
)
def test_pending_rights_refuse_before_cache_parse_or_unbounded_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    day: date,
    expected_reads: int,
) -> None:
    root = _publication_root(tmp_path)
    _set_ngram_rights_pending(root)
    cache = root / f"data/raw/ngram_days/{day}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_complete_result(root)), encoding="utf-8")
    cache_reads: list[str] = []
    parse_calls: list[str] = []
    original_read_bytes = Path.read_bytes

    def observed_read_bytes(path: Path) -> bytes:
        if path == cache:
            cache_reads.append(path.name)
        return original_read_bytes(path)

    def observed_parse(_raw: bytes) -> dict:
        parse_calls.append("parsed")
        return {}

    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache.parent)
    monkeypatch.setattr(Path, "read_bytes", observed_read_bytes)
    monkeypatch.setattr(fetch_ngrams, "_decode_cached_day", observed_parse)

    with pytest.raises(ngram_rights.NgramRightsError):
        fetch_ngrams._cached_day(day, _specs())

    assert len(cache_reads) == expected_reads
    assert parse_calls == []


@pytest.mark.parametrize("boundary", ("expired", "revoked", "max_age"))
def test_cached_day_rechecks_rights_after_fetch_before_cache_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    elif boundary == "revoked":
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    else:
        _write_approved_ngram_rights(
            root, max_current_age_days=1, historical_recovery_targets=[]
        )
    moments = iter(
        (
            datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: next(moments))
    cache_dir = root / "data/raw/ngram_days"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "DAY_CACHE", cache_dir)

    def compute(*_args: object, **_kwargs: object) -> dict[str, object]:
        ngram_rights.require_public_identity_rights(
            target=TARGET, root=root, test_authority=_rights(root)
        )
        return _complete_result(root)

    monkeypatch.setattr(fetch_ngrams, "compute_day", compute)
    with pytest.raises(ngram_rights.NgramRightsError):
        fetch_ngrams._cached_day(TARGET, _specs(), rights_authority=_rights(root))

    assert not (cache_dir / f"{TARGET}.json").exists()


@pytest.mark.parametrize("boundary", ("expired", "revoked", "max_age"))
def test_acquire_target_rechecks_rights_after_fetch_before_bundle_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    elif boundary == "revoked":
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    else:
            _write_approved_ngram_rights(
                root, max_current_age_days=1, historical_recovery_targets=[]
            )
    moments = iter(
        (
            datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: next(moments))
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()
    provenance_before = (root / "data/raw/provenance.csv").read_bytes()

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: _complete_result(root),
        non_git_test_rights=_rights(root),
    )

    assert status["status"] == "acquisition_failed"
    assert "post-fetch" in status["reason"]
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert (root / "data/raw/provenance.csv").read_bytes() == provenance_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
    assert not (root / f"data/raw/final_publication_receipts/{TARGET}.json").exists()


@pytest.mark.parametrize("boundary", ("expired", "revoked", "max_age"))
def test_acquire_target_rechecks_rights_at_atomic_bundle_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    elif boundary == "revoked":
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    else:
            _write_approved_ngram_rights(
                root, max_current_age_days=1, historical_recovery_targets=[]
            )
    moments = iter(
        (
            datetime(2026, 8, 10, 23, 59, 58, tzinfo=timezone.utc),
            datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: next(moments))
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    store_before = (root / "data/raw/gdelt_volume.csv").read_bytes()

    status = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        compute_day=lambda *_args: _complete_result(root),
        non_git_test_rights=_rights(root),
    )

    assert status["status"] == "acquisition_failed"
    assert "candidate-write" in status["reason"]
    assert (root / "data/raw/gdelt_volume.csv").read_bytes() == store_before
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()


@pytest.mark.parametrize("boundary", ("expired", "revoked", "max_age"))
def test_nowcast_rechecks_rights_after_fetch_before_public_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    elif boundary == "revoked":
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    else:
        _write_approved_ngram_rights(root, max_current_age_days=0)
    moments = iter(
        (
            datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: next(moments))

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc)

    def compute(*_args: object, **_kwargs: object) -> dict[str, object]:
        ngram_rights.require_public_identity_rights(
            target=date(2026, 8, 10), root=root, test_authority=_rights(root)
        )
        return _complete_result(root)

    out = root / "docs/data/nowcast.json"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "compute_day", compute)
    monkeypatch.setattr(nowcast, "ROOT", root)
    monkeypatch.setattr(nowcast, "STORE", root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)

    with pytest.raises(ngram_rights.NgramRightsError):
        nowcast.main(rights_authority=_rights(root))

    assert not out.exists()
    assert not (root / "data/raw/ngram_days").exists()


@pytest.mark.parametrize("boundary", ("expired", "revoked", "max_age"))
def test_nowcast_rechecks_rights_at_public_write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    elif boundary == "revoked":
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    else:
        _write_approved_ngram_rights(root, max_current_age_days=0)
    moments = iter(
        (
            datetime(2026, 8, 10, 23, 59, 58, tzinfo=timezone.utc),
            datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc),
            datetime(2026, 8, 11, 0, 0, 1, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: next(moments))

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return datetime(2026, 8, 10, 23, 59, 59, tzinfo=timezone.utc)

    def compute(*_args: object, **_kwargs: object) -> dict[str, object]:
        ngram_rights.require_public_identity_rights(
            target=date(2026, 8, 10), root=root, test_authority=_rights(root)
        )
        return _complete_result(root)

    out = root / "docs/data/nowcast.json"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(fetch_ngrams, "compute_day", compute)
    monkeypatch.setattr(nowcast, "ROOT", root)
    monkeypatch.setattr(nowcast, "STORE", root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)

    with pytest.raises(ngram_rights.NgramRightsError):
        nowcast.main(rights_authority=_rights(root))

    assert not out.exists()


def test_nowcast_binds_rights_receipts_and_rechecks_committed_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _publication_root(tmp_path)
    checked = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: checked)

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return checked

    out = root / "docs/data/nowcast.json"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(
        fetch_ngrams,
        "compute_day",
        lambda *_args, **_kwargs: _complete_result(root),
    )
    monkeypatch.setattr(nowcast, "ROOT", root)
    monkeypatch.setattr(nowcast, "STORE", root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)
    nowcast.main(rights_authority=_rights(root))

    payload = json.loads(out.read_text(encoding="utf-8"))
    receipt = payload["_meta"]["rights_receipt"]
    assert receipt["schema_version"] == "1.0.0"
    assert receipt["post_fetch"]["target_date"] == "2026-08-10"
    assert receipt["write_boundary"]["evaluated_at_utc"] == ("2026-08-10T12:00:00Z")

    for command in (
        ("init", "-q"),
        ("config", "user.name", "Nowcast rights test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "committed nowcast"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _authorize_production_test_signer(root, monkeypatch)
    monkeypatch.setattr(nowcast, "datetime", datetime)

    proof = nowcast.require_release_rights(candidate, root=root)

    assert proof["status"] == "nowcast_release_rights_verified"
    assert proof["candidate_sha"] == candidate


@pytest.mark.parametrize("attack", ("missing", "null", "future_post_fetch", "reversed"))
def test_nowcast_release_refuses_invalid_temporal_receipt_proofs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    checked = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: checked)

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return checked

    out = root / "docs/data/nowcast.json"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(
        fetch_ngrams,
        "compute_day",
        lambda *_args, **_kwargs: _complete_result(root),
    )
    monkeypatch.setattr(nowcast, "ROOT", root)
    monkeypatch.setattr(nowcast, "STORE", root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)
    nowcast.main(rights_authority=_rights(root))
    payload = json.loads(out.read_text(encoding="utf-8"))
    receipt = payload["_meta"]["rights_receipt"]
    if attack == "missing":
        for boundary in ("post_fetch", "write_boundary"):
            for field in (
                "evaluated_at_utc",
                "rights_as_of",
                "evaluated_age_days",
                "release_deadline_utc",
            ):
                receipt[boundary].pop(field)
    elif attack == "null":
        receipt["post_fetch"]["evaluated_at_utc"] = None
    elif attack == "future_post_fetch":
        receipt["post_fetch"]["evaluated_at_utc"] = "2026-08-10T13:00:00Z"
    else:
        receipt["write_boundary"]["evaluated_at_utc"] = "2026-08-10T11:59:59Z"
    out.write_text(json.dumps(payload), encoding="utf-8")

    for command in (
        ("init", "-q"),
        ("config", "user.name", "Nowcast receipt attack"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "committed attacked nowcast"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _authorize_production_test_signer(root, monkeypatch)
    monkeypatch.setattr(nowcast, "datetime", datetime)

    with pytest.raises(ngram_rights.NgramRightsError):
        nowcast.require_release_rights(candidate, root=root)


def test_nowcast_release_refuses_previous_utc_day_after_rollover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _publication_root(tmp_path)
    generated = datetime(2026, 8, 10, 23, 50, tzinfo=timezone.utc)
    release = datetime(2026, 8, 11, 0, 10, tzinfo=timezone.utc)
    current = [generated]
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: current[0])

    class FixedDateTime:
        @classmethod
        def now(cls, _tz: object = None) -> datetime:
            return generated

    out = root / "docs/data/nowcast.json"
    monkeypatch.setattr(fetch_ngrams, "ROOT", root)
    monkeypatch.setattr(
        fetch_ngrams,
        "compute_day",
        lambda *_args, **_kwargs: _complete_result(root),
    )
    monkeypatch.setattr(nowcast, "ROOT", root)
    monkeypatch.setattr(nowcast, "STORE", root / "data/raw/gdelt_volume.csv")
    monkeypatch.setattr(nowcast, "CALIB", root / "data/raw/ngram_calibration.json")
    monkeypatch.setattr(nowcast, "OUT", out)
    monkeypatch.setattr(nowcast, "datetime", FixedDateTime)
    nowcast.main(rights_authority=_rights(root))

    for command in (
        ("init", "-q"),
        ("config", "user.name", "Nowcast rollover attack"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "committed previous-day nowcast"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _authorize_production_test_signer(root, monkeypatch)
    current[0] = release
    monkeypatch.setattr(nowcast, "datetime", datetime)

    with pytest.raises(ngram_rights.NgramRightsError) as exc_info:
        nowcast.require_release_rights(candidate, root=root)
    assert exc_info.value.code == "nowcast_time_order_invalid"


def test_nowcast_publish_path_rechecks_rights_inside_push_boundary() -> None:
    workflow = (ROOT / ".github/workflows/nowcast.yml").read_text(encoding="utf-8")
    publisher = (ROOT / "scripts/publish_push.sh").read_text(encoding="utf-8")
    push = publisher.split("git_push() {", 1)[1].split("\n}", 1)[0]

    assert "IGRM_PUBLISH_CLASS: nowcast" in workflow
    assert '--check-release-rights "$candidate"' in push
    assert push.index('--check-release-rights "$candidate"') < push.index("git push")


@pytest.mark.parametrize(
    "attack",
    ("synthetic_copied_into_git", "arbitrary_agent_role", "coordinated_reseal"),
)
def test_production_rights_refuse_repository_added_signer_authority(
    tmp_path: Path,
    attack: str,
) -> None:
    root = _publication_root(tmp_path)
    if attack == "arbitrary_agent_role":
        _write_approved_ngram_rights(root, signer_role="autonomous_agent")
    elif attack == "coordinated_reseal":
        # Re-create the signer, signed decision, signature and both registries
        # together. Cryptographic self-consistency is not production trust.
        _write_approved_ngram_rights(root)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)

    with pytest.raises(
        ngram_rights.NgramRightsError,
        match="^ngram_production_signer_untrusted$",
    ):
        ngram_rights.require_public_identity_rights(target=TARGET, root=root)


def test_explicit_non_git_authority_is_the_only_synthetic_positive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
    )
    root = _publication_root(tmp_path)
    proof = ngram_rights.require_daily_aggregate_rights(
        target=TARGET,
        root=root,
        test_authority=_rights(root),
    )

    assert proof["target_date"] == TARGET.isoformat()
    assert proof["max_current_age_days"] == 2
    assert proof["evaluated_age_days"] == 1


def test_rights_are_rechecked_at_actual_promotion_day_after_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    _write_approved_ngram_rights(root, review_due="2026-08-10")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 23, 55, tzinfo=timezone.utc),
    )
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 0, 5, tzinfo=timezone.utc),
    )

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert exc.value.classification == "promotion_receipt_invalid"
    assert "ngram_rights_decision_expired" in exc.value.detail


def test_rights_are_rechecked_at_actual_promotion_day_after_revocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 23, 55, tzinfo=timezone.utc),
    )
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 0, 5, tzinfo=timezone.utc),
    )

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert "ngram_rights_signer_revoked" in exc.value.detail


@pytest.mark.parametrize(
    ("checked_at", "max_age", "expected"),
    (
        (datetime(2026, 8, 10, 12, tzinfo=timezone.utc), 0, "refused"),
        (datetime(2026, 8, 10, 12, tzinfo=timezone.utc), 1, "target_ready"),
        (datetime(2026, 8, 8, 12, tzinfo=timezone.utc), 2, "refused"),
    ),
)
def test_signed_max_current_age_is_enforced_and_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checked_at: datetime,
    max_age: int,
    expected: str,
) -> None:
    root = _publication_root(tmp_path)
    _write_approved_ngram_rights(
        root,
        max_current_age_days=max_age,
        historical_recovery_targets=[],
    )
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: checked_at)

    status = _acquire(root, monkeypatch, _complete_result(root))

    if expected == "refused":
        assert status["status"] == "acquisition_failed"
        assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
        return
    assert status["status"] == expected
    receipt = json.loads((root / f"data/raw/final_publication_receipts/{TARGET}.json").read_text())
    rights = receipt["bindings"]["rights"]
    assert rights["max_current_age_days"] == 1
    assert rights["evaluated_age_days"] == 1
    assert rights["rights_as_of"] == "2026-08-10"


def test_signed_max_current_age_is_rechecked_at_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    _write_approved_ngram_rights(
        root, max_current_age_days=2, historical_recovery_targets=[]
    )
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
    )
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 12, 0, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert "ngram_rights_target_too_old" in exc.value.detail


def test_promotion_revalidates_signed_rights_against_frozen_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    trust = _trust(root)
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
    _set_ngram_rights_pending(root)

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_promotion_receipt(
            TARGET,
            root=root,
            require_bridge_receipt=True,
            non_git_test_trust=trust,
        )
    assert exc.value.classification == "promotion_receipt_invalid"
    assert "rights_not_authorized" in exc.value.detail


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
    assert provenance.decode().splitlines()[-1] == ("2026-08-09,ngram_bridge,recorded")
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
        "source_profile_sha256",
        "source_schema_sha256",
        "source_validator_sha256",
        "candidate_row_sha256",
        "rights",
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
    evidence = result["_aggregate_attestation"]
    if shape == "47_of_47":
        result["n_samples"] = 47
        result["n_samples_loaded"] = 47
        evidence["located_windows"] = 47
        evidence["loaded_windows"] = 47
        evidence["windows"] = evidence["windows"][:-1]
    elif shape == "48_of_47":
        result["n_samples_loaded"] = 47
        evidence["loaded_windows"] = 47
        evidence["windows"] = evidence["windows"][:-1]
    else:
        result["partial"] = True
    result["_aggregate_attestation"] = ngram_daily_attestation.seal(evidence)
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
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
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
    assert not (root / f"data/raw/final_publication_receipts/{TARGET}.json").exists()
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
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    store_before = store.read_bytes()
    provenance_before = provenance.read_bytes()
    store.write_bytes(store_before + b"2026-08-09,1.0\n")
    provenance.write_bytes(provenance_before + b"2026-08-09,ngram_bridge,recorded\n")
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    receipt = root / f"data/raw/final_publication_receipts/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    receipt.parent.mkdir(parents=True)
    cache.write_text(json.dumps({"date": TARGET.isoformat()}), encoding="utf-8")
    receipt.write_text(json.dumps({"target_date": TARGET.isoformat()}), encoding="utf-8")
    (root / final_publication.STATUS_RELATIVE).write_text(
        json.dumps({"target_date": PREFIX_DAY.isoformat(), "status": "target_ready"}),
        encoding="utf-8",
    )
    non_target_cache = root / f"data/raw/ngram_days/{PREFIX_DAY}.json"
    non_target_receipt = root / f"data/raw/final_publication_receipts/{PREFIX_DAY}.json"
    non_target_cache.write_text("{malformed", encoding="utf-8")
    non_target_receipt.write_text("{malformed", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    subprocess.run(
        [
            "bash",
            "scripts/stage_daily_outputs.sh",
            "failure",
            TARGET.isoformat(),
        ],
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
    assert not non_target_cache.exists()
    assert not non_target_receipt.exists()
    assert not (root / final_publication.STATUS_RELATIVE).exists()


def test_failed_staging_drops_valid_bundle_and_next_attempt_can_promote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _publication_root(tmp_path)
    (root / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/stage_daily_outputs.sh",
        root / "scripts/stage_daily_outputs.sh",
    )
    (root / "notes-inbox").mkdir()
    (root / "notes-inbox/.keep").write_text("\n", encoding="utf-8")
    (root / ".trigger").mkdir()
    (root / ".trigger/.keep").write_text("\n", encoding="utf-8")
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Daily staging test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    _authorize_production_test_signer(root, monkeypatch)

    first = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        base_commit=base,
        compute_day=lambda *_args: _complete_result(root),
    )
    assert first["status"] == "target_ready"
    (root / "docs/index.html").write_text("downstream candidate\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHON"] = sys.executable
    subprocess.run(
        [
            "bash",
            "scripts/stage_daily_outputs.sh",
            "failure",
            TARGET.isoformat(),
        ],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not (root / f"data/raw/ngram_days/{TARGET}.json").exists()
    assert not (root / f"data/raw/final_publication_receipts/{TARGET}.json").exists()
    assert not (root / final_publication.STATUS_RELATIVE).exists()
    assert subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root).returncode == 0

    second = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=root,
        base_commit=base,
        compute_day=lambda *_args: _complete_result(root),
    )
    assert second["status"] == "target_ready"
    _write_target_outputs(root)
    finalized = final_publication.mark_finalized(
        TARGET,
        root=root,
        base_commit=base,
    )
    assert finalized["status"] == "finalized"


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
    monkeypatch.setattr(fetch_ngrams, "ROOT", unavailable_root)
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
        non_git_test_rights=_rights(unavailable_root),
    )

    failed_root = _publication_root(tmp_path / "failed")
    monkeypatch.setattr(fetch_ngrams, "ROOT", failed_root)
    monkeypatch.setattr(
        fetch_ngrams.requests,
        "head",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("timed out")),
    )
    failed = final_publication.acquire_target(
        TARGET,
        today=TODAY,
        root=failed_root,
        compute_day=fetch_ngrams.compute_day,
        non_git_test_rights=_rights(failed_root),
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
        non_git_test_rights=_rights(root),
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


def _committed_new_contract_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str]:
    root = _publication_root(tmp_path)
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Final proof test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    parent = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    _authorize_production_test_signer(root, monkeypatch)
    assert (
        final_publication.acquire_target(
            TARGET,
            today=TODAY,
            root=root,
            base_commit=parent,
            compute_day=lambda *_args: _complete_result(root),
        )["status"]
        == "target_ready"
    )
    _write_target_outputs(root)
    final_publication.mark_finalized(
        TARGET,
        root=root,
        base_commit=parent,
    )
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "publish exact final"],
        cwd=root,
        check=True,
    )
    return root, parent


@pytest.mark.parametrize("boundary", ("expired", "revoked"))
def test_candidate_release_rechecks_rights_after_gate_crosses_midnight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    root = _publication_root(tmp_path)
    if boundary == "expired":
        _write_approved_ngram_rights(root, review_due="2026-08-10")
    else:
        _write_approved_ngram_rights(root, signer_revoked="2026-08-11")
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 23, 55, tzinfo=timezone.utc),
    )
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Release boundary test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    parent = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _authorize_production_test_signer(root, monkeypatch)
    monkeypatch.setattr(fetch_ngrams, "group_specs", _specs)
    assert (
        final_publication.acquire_target(
            TARGET,
            today=TODAY,
            root=root,
            base_commit=parent,
            compute_day=lambda *_args: _complete_result(root),
        )["status"]
        == "target_ready"
    )
    _write_target_outputs(root)
    final_publication.mark_finalized(TARGET, root=root, base_commit=parent)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "candidate before midnight"],
        cwd=root,
        check=True,
    )
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 11, 0, 5, tzinfo=timezone.utc),
    )

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_rights(root=root)
    assert exc.value.classification == "promotion_receipt_invalid"
    expected = (
        "ngram_rights_decision_expired" if boundary == "expired" else "ngram_rights_signer_revoked"
    )
    assert expected in exc.value.detail


def test_candidate_release_emits_sha_time_and_bound_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ngram_rights,
        "_utc_now",
        lambda: datetime(2026, 8, 10, 23, 59, 58, tzinfo=timezone.utc),
    )
    root, _parent = _committed_new_contract_final(tmp_path, monkeypatch)

    release = final_publication.require_release_rights(root=root)

    assert release["status"] == "release_rights_verified"
    assert (
        release["candidate_sha"]
        == subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    evaluation = release["release_rights_evaluation"]
    assert evaluation["evaluated_at_utc"] == "2026-08-10T23:59:58Z"
    assert evaluation["release_deadline_utc"] == "2026-08-11T23:59:59Z"


def test_exact_aug9_legacy_visibility_never_authorizes_final_release(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy-release"
    subprocess.run(["git", "clone", "-q", "--shared", str(ROOT), str(root)], check=True)
    legacy_candidate = "f200dbaf93812e295eb0bcc26b92b30d6796efb7"
    legacy_parent = "1ba3618b832a5ee64ea86b3f97e26145ee72c178"
    subprocess.run(
        ["git", "checkout", "-q", "--detach", legacy_candidate],
        cwd=root,
        check=True,
    )

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_release_candidate(
            "final",
            expected_candidate_sha=legacy_candidate,
            base_commit=legacy_parent,
            expected_target=TARGET,
            root=root,
        )

    subprocess.run(
        ["git", "config", "user.name", "Legacy release attack"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "arbitrary descendant"],
        cwd=root,
        check=True,
    )
    descendant = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_release_candidate(
            "final",
            expected_candidate_sha=descendant,
            base_commit=legacy_candidate,
            expected_target=TARGET,
            root=root,
        )


def test_final_release_never_reads_dirty_value_overlay_instead_of_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, parent = _committed_new_contract_final(tmp_path / "source", monkeypatch)
    protected = (
        f"data/raw/final_publication_receipts/{TARGET}.json",
        f"data/raw/ngram_days/{TARGET}.json",
        "data/raw/gdelt_volume.csv",
        "data/raw/provenance.csv",
        "data/raw/final_publication_status.json",
        "docs/data/latest.json",
        "docs/data/history.json",
    )
    for overlay in ("valid_over_invalid", "invalid_over_valid"):
        for index, relative in enumerate(protected):
            root = tmp_path / f"{overlay}-{index}"
            subprocess.run(
                ["git", "clone", "-q", "--shared", str(source), str(root)],
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Final overlay attack"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "actions@github.com"],
                cwd=root,
                check=True,
            )
            path = root / relative
            valid = path.read_bytes()
            malicious = valid + b"\nMALICIOUS FINAL VALUE 99.9\n"
            candidate = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if overlay == "valid_over_invalid":
                path.write_bytes(malicious)
                subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
                subprocess.run(
                    ["git", "commit", "-q", "--amend", "--no-edit"],
                    cwd=root,
                    check=True,
                )
                candidate = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                path.write_bytes(valid)
            else:
                path.write_bytes(malicious)

            with pytest.raises(final_publication.FinalPublicationError) as exc:
                final_publication.require_release_candidate(
                    "final",
                    expected_candidate_sha=candidate,
                    base_commit=parent,
                    expected_target=TARGET,
                    root=root,
                )
            assert exc.value.detail == "candidate_worktree_not_clean"


def _committed_value_free_refusal(tmp_path: Path) -> tuple[Path, str, str]:
    root = _publication_root(tmp_path)
    (root / "docs/index.html").write_bytes((ROOT / "docs/index.html").read_bytes())
    (root / "docs/status.html").write_bytes((ROOT / "docs/status.html").read_bytes())
    status_path = root / "docs/data/status.json"
    parent_status = json.loads(status_path.read_text(encoding="utf-8"))
    parent_status.setdefault("_meta", {})["what"] = (
        "Unicode punctuation – must retain deterministic JSON byte semantics"
    )
    status_path.write_text(json.dumps(parent_status, indent=1) + "\n", encoding="utf-8")
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Refusal proof test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    final_publication.record_pipeline_failed(
        TARGET,
        root=root,
        base_commit=base,
        failure_stage="source",
        contract_today=TODAY,
    )
    final_publication.write_public_status(root=root, today=TODAY)
    paths = sorted(final_publication.value_free_refusal_paths(TARGET))
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "value-free refusal"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return root, base, candidate


def _amend_refusal(root: Path, relative: str) -> str:
    subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--amend", "--no-edit"],
        cwd=root,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_value_free_refusal_release_rebuilds_exact_parent_patch(
    tmp_path: Path,
) -> None:
    root, base, candidate = _committed_value_free_refusal(tmp_path)

    proof = final_publication.require_release_candidate(
        "refusal",
        expected_candidate_sha=candidate,
        base_commit=base,
        expected_target=TARGET,
        root=root,
    )

    assert proof["candidate_class"] == "refusal"
    assert proof["candidate_sha"] == candidate
    assert proof["changed_paths"] == sorted(final_publication.value_free_refusal_paths(TARGET))
    assert proof["value_fields_published"] is False


def test_repeated_value_free_refusal_accepts_unchanged_public_disclosures(
    tmp_path: Path,
) -> None:
    root, _original_base, first_candidate = _committed_value_free_refusal(tmp_path)

    final_publication.record_pipeline_failed(
        TARGET,
        root=root,
        base_commit=first_candidate,
        failure_stage="source",
        contract_today=TODAY,
    )
    final_publication.write_public_status(root=root, today=TODAY)
    paths = sorted(final_publication.value_free_refusal_paths(TARGET))
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "repeat value-free refusal"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    changed = subprocess.run(
        ["git", "diff", "--name-only", first_candidate, candidate],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

    assert changed == [final_publication.STATUS_RELATIVE.as_posix()]
    proof = final_publication.require_release_candidate(
        "refusal",
        expected_candidate_sha=candidate,
        base_commit=first_candidate,
        expected_target=TARGET,
        root=root,
    )

    assert proof["candidate_class"] == "refusal"
    assert proof["changed_paths"] == changed
    assert proof["value_fields_published"] is False


def test_value_free_refusal_subset_still_requires_fresh_marker(
    tmp_path: Path,
) -> None:
    root, _original_base, first_candidate = _committed_value_free_refusal(tmp_path)
    path = root / "docs/status.html"
    path.write_bytes(path.read_bytes() + b"\n<!-- unrelated repeat -->\n")
    subprocess.run(["git", "add", "--", "docs/status.html"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "public-only repeat"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=first_candidate,
            expected_target=TARGET,
            root=root,
        )

    assert exc.value.detail == "refusal_diff_not_value_free"


def test_value_free_refusal_reads_committed_blob_not_symlink_target(
    tmp_path: Path,
) -> None:
    root = _publication_root(tmp_path)
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Refusal proof test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "frozen parent"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    final_publication.record_pipeline_failed(
        TARGET,
        root=root,
        base_commit=base,
        failure_stage="source",
        contract_today=TODAY,
    )
    final_publication.write_public_status(root=root, today=TODAY)
    marker_path = root / final_publication.STATUS_RELATIVE
    external_marker = tmp_path / "external-marker.json"
    external_marker.write_bytes(marker_path.read_bytes())
    marker_path.unlink()
    marker_path.symlink_to(external_marker)
    paths = sorted(final_publication.value_free_refusal_paths(TARGET))
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "symlink refusal"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )

    assert exc.value.detail == (
        "refusal_output_mode_invalid:data/raw/final_publication_status.json"
    )


@pytest.mark.parametrize(
    ("pattern", "new"),
    (
        # Literal page bytes (58.8, 2026-08-09, 65.2) pinned the Aug-9 page
        # and went stale in the first candidate that advanced the day (run
        # 31682875024). The attack's meaning is "mutate whichever value the
        # page CURRENTLY shows", so extract it from the page under test.
        (r">\d+\.\d+</p>", ">99.9</p>"),
        (r'id="latest-date">\d{4}-\d{2}-\d{2}</span>', 'id="latest-date">2030-01-01</span>'),
        (r'class="component-score">\d+\.\d+</span>', 'class="component-score">99.9</span>'),
    ),
)
def test_value_free_refusal_refuses_reader_value_mutation_inside_allowed_index(
    tmp_path: Path, pattern: str, new: str
) -> None:
    root, base, _candidate = _committed_value_free_refusal(tmp_path)
    path = root / "docs/index.html"
    text = path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    assert match is not None, pattern
    old = match.group(0)
    assert old != new
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    candidate = _amend_refusal(root, "docs/index.html")

    with pytest.raises(
        final_publication.FinalPublicationError,
        match="^release_candidate_unproven$",
    ):
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )


def test_value_free_refusal_refuses_unrelated_public_status_mutation(
    tmp_path: Path,
) -> None:
    root, base, _candidate = _committed_value_free_refusal(tmp_path)
    path = root / "docs/data/status.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unrelated_reader_score"] = 99.9
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    candidate = _amend_refusal(root, "docs/data/status.json")

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )


def test_value_free_refusal_refuses_value_in_operational_marker(
    tmp_path: Path,
) -> None:
    root, base, _candidate = _committed_value_free_refusal(tmp_path)
    path = root / final_publication.STATUS_RELATIVE
    marker = json.loads(path.read_text(encoding="utf-8"))
    marker["composite"] = 99.9
    path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
    candidate = _amend_refusal(root, final_publication.STATUS_RELATIVE.as_posix())

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )


@pytest.mark.parametrize(
    "injected_reason",
    (
        "Official finalized composite score = 99.9.",
        "Official final energy channel = 100.",
        "Official final date is 2030-01-01.",
        "Official final citation https://example.invalid/score says 99.9.",
    ),
)
def test_value_free_refusal_refuses_reason_claim_laundering_after_rebuild(
    tmp_path: Path, injected_reason: str
) -> None:
    root, base, _candidate = _committed_value_free_refusal(tmp_path)
    marker_path = root / final_publication.STATUS_RELATIVE
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["reason_code"] == "source_acquisition_failed"
    assert marker["failure_stage"] == "source"
    marker["reason"] = injected_reason
    marker_path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
    # Rebuild every disclosure byte from the now-hostile marker, reproducing
    # the old laundering path rather than relying on an output mismatch.
    final_publication.write_public_status(root=root, today=TODAY)
    paths = sorted(final_publication.value_free_refusal_paths(TARGET))
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "--amend", "--no-edit"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )
    assert exc.value.detail == "refusal_marker_not_value_free"


@pytest.mark.parametrize("relative", sorted(final_publication._VALUE_FREE_REFUSAL_PATHS))
@pytest.mark.parametrize("overlay", ("valid_over_invalid", "invalid_over_valid"))
def test_refusal_release_never_reads_dirty_overlay_instead_of_candidate(
    tmp_path: Path, relative: str, overlay: str
) -> None:
    root, base, candidate = _committed_value_free_refusal(tmp_path)
    path = root / relative
    valid = path.read_bytes()
    malicious = valid + b"\nMALICIOUS OFFICIAL FINAL SCORE 99.9\n"
    if overlay == "valid_over_invalid":
        path.write_bytes(malicious)
        subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--amend", "--no-edit"],
            cwd=root,
            check=True,
        )
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        path.write_bytes(valid)
    else:
        path.write_bytes(malicious)

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )
    assert exc.value.detail == "candidate_worktree_not_clean"


def test_value_free_refusal_refuses_value_path_even_with_exact_disclosure(
    tmp_path: Path,
) -> None:
    root, base, _candidate = _committed_value_free_refusal(tmp_path)
    path = root / "data/raw/gdelt_volume.csv"
    path.write_text(
        path.read_text(encoding="utf-8") + "2026-08-09,99.9\n",
        encoding="utf-8",
    )
    candidate = _amend_refusal(root, "data/raw/gdelt_volume.csv")

    with pytest.raises(final_publication.FinalPublicationError):
        final_publication.require_release_candidate(
            "refusal",
            expected_candidate_sha=candidate,
            base_commit=base,
            expected_target=TARGET,
            root=root,
        )


def test_unresolved_first_refusal_blocks_all_later_target_progression(
    tmp_path: Path,
) -> None:
    root = _publication_root(tmp_path)
    for command in (
        ("init", "-q"),
        ("config", "user.name", "Consecutive refusal test"),
        ("config", "user.email", "actions@github.com"),
        ("add", "."),
        ("commit", "-q", "-m", "last finalized Aug-8"),
    ):
        subprocess.run(["git", *command], cwd=root, check=True)
    value_paths = (
        "data/raw/gdelt_volume.csv",
        "data/raw/provenance.csv",
        "docs/data/latest.json",
        "docs/data/history.json",
    )
    frozen_values = {relative: (root / relative).read_bytes() for relative in value_paths}

    target = date(2026, 8, 9)
    contract_today = date(2026, 8, 10)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    final_publication.record_pipeline_failed(
        target,
        root=root,
        base_commit=base,
        failure_stage="source",
        contract_today=contract_today,
    )
    state = final_publication.write_public_status(root=root, today=contract_today)
    paths = sorted(final_publication.value_free_refusal_paths(TARGET))
    subprocess.run(["git", "add", "--", *paths], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"refuse {target}"],
        cwd=root,
        check=True,
    )
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    proof = final_publication.require_release_candidate(
        "refusal",
        expected_candidate_sha=candidate,
        base_commit=base,
        expected_target=target,
        root=root,
    )

    assert proof["changed_paths"] == paths
    assert state["target_date"] == target.isoformat()
    assert state["latest_finalized_date"] == PREFIX_DAY.isoformat()
    assert all(
        (root / relative).read_bytes() == frozen_values[relative] for relative in value_paths
    )

    frozen_tree = {
        relative: (root / relative).read_bytes()
        for relative in (*value_paths, *final_publication._VALUE_FREE_REFUSAL_PATHS)
    }
    # This test originally asserted that the first refusal blocks ALL later
    # progression forever. That exact property livelocked production: the
    # 2026-08-11 provider files left the temporary window and every later
    # day starved behind an unrecoverable refusal. The property that
    # survives is ORDER: progression moves exactly one disclosed day at a
    # time. Jumping over the next eligible day still refuses; the next
    # eligible day itself (behind an AGED published source disclosure) is
    # now legitimately recordable.
    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.record_pipeline_failed(
            date(2026, 8, 11),
            root=root,
            base_commit=candidate,
            failure_stage="source",
            contract_today=date(2026, 8, 12),
        )
    assert exc.value.classification == "final_target_invalid"
    assert exc.value.detail == "target_is_not_exact_next_unpublished_day_before_utc_d0"
    assert {
        relative: (root / relative).read_bytes() for relative in frozen_tree
    } == frozen_tree
    # The aged Aug-9 disclosure admits exactly Aug 10 next, and recording its
    # failure still never touches a frozen value byte.
    final_publication.record_pipeline_failed(
        date(2026, 8, 10),
        root=root,
        base_commit=candidate,
        failure_stage="source",
        contract_today=date(2026, 8, 12),
    )
    assert all(
        (root / relative).read_bytes() == frozen_values[relative]
        for relative in value_paths
    )


def test_release_rights_check_is_inside_the_final_cas_barrier() -> None:
    publisher = (ROOT / "scripts/publish_final_cas.sh").read_text(encoding="utf-8")
    push = publisher.split("push_frozen_parent() {", 1)[1].split("\n}", 1)[0]
    remote = push.index('[ "$remote_commit" != "$BASE_COMMIT" ]')
    rights = push.index('--check-release-candidate "$CANDIDATE_CLASS"')
    target = push.index('--expected-target "$TARGET"')
    candidate = push.index('[ "$release_candidate" != "$FROZEN_CANDIDATE_SHA" ]')
    direct_push = push.index('git push origin "$FROZEN_CANDIDATE_SHA:main"')

    assert remote < rights < target < candidate < direct_push


def test_remote_idempotence_verifier_skips_only_valid_receipt_or_pinned_aug9(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _parent = _committed_new_contract_final(tmp_path, monkeypatch)

    assert (
        final_publication.require_published_target(TARGET, root=root, today=TODAY)["status"]
        == "finalized"
    )
    # The legacy-limited contrast belongs to the pinned aug9 vintage, not the
    # live head, which legitimately outgrew this posture at the first value
    # advance (run 31682875024).
    assert (
        final_publication.require_published_target(
            TARGET, root=_legacy_history_repo(tmp_path), today=TODAY
        )["status"]
        == "legacy_proof_limited"
    )


@pytest.mark.parametrize(
    "attack",
    ("latest_status_only", "invalid_receipt", "wrong_introduction_parent", "generic_legacy"),
)
def test_remote_idempotence_verifier_never_skips_unproven_public_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack: str,
) -> None:
    if attack in {"invalid_receipt", "wrong_introduction_parent"}:
        root, _parent = _committed_new_contract_final(tmp_path, monkeypatch)
        receipt_path = root / f"data/raw/final_publication_receipts/{TARGET}.json"
        marker_path = root / final_publication.STATUS_RELATIVE
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if attack == "invalid_receipt":
            receipt["bindings"]["candidate_row_sha256"] = "0" * 64
        else:
            receipt["base_commit"] = "b" * 40
            marker["base_commit"] = "b" * 40
        receipt_path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8")
        marker["receipt"]["sha256"] = _sha(final_publication._json_bytes(receipt))
        marker_path.write_text(json.dumps(marker, indent=1) + "\n", encoding="utf-8")
    else:
        root = _publication_root(tmp_path)
        if attack == "generic_legacy":
            cache = root / f"data/raw/ngram_days/{TARGET}.json"
            cache.parent.mkdir(parents=True)
            cache.write_text(json.dumps(_legacy_result(root)), encoding="utf-8")
        _write_target_outputs(root)
        status_path = root / "docs/data/status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["final_publication"] = {
            "target_date": TARGET.isoformat(),
            "status": ("legacy_proof_limited" if attack == "generic_legacy" else "finalized"),
            "finalized": attack != "generic_legacy",
        }
        status_path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(final_publication.FinalPublicationError) as exc:
        final_publication.require_published_target(TARGET, root=root, today=TODAY)
    assert exc.value.classification == "published_target_unproven"


def test_fabricated_schema_1_legacy_target_is_not_a_historical_exception(
    tmp_path: Path,
) -> None:
    root = _publication_root(tmp_path)
    cache = root / f"data/raw/ngram_days/{TARGET}.json"
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps(_legacy_result(root)), encoding="utf-8")
    _write_target_outputs(root)

    public = final_publication.public_status(root=root, today=TODAY)

    assert public["status"] == "delayed_final"
    assert public["latest_finalized_date"] is None
    assert public["finalized"] is False
    assert public["source_receipt"] is None


def test_exact_upstream_aug9_object_alone_retains_bounded_legacy_label(
    tmp_path: Path,
) -> None:
    # Asserted against live ROOT until the first value advance made the live
    # posture legitimately newer than this frozen-era description (run
    # 31682875024). The property belongs to the pinned aug9 vintage.
    public = final_publication.public_status(
        root=_legacy_history_repo(tmp_path), today=TODAY
    )

    assert public["status"] == "legacy_proof_limited"
    assert public["latest_finalized_date"] == TARGET.isoformat()
    assert public["finalized"] is False
    assert public["source_receipt"] is None
    for missing_link in (
        "source acquisition receipt",
        "reconstructable English denominator",
        "cache-to-store calibration/transform receipt",
        "store-to-public score derivation receipt",
        "source-retention and redistribution rights review",
    ):
        assert missing_link in public["reason"]


@pytest.mark.parametrize(
    "attack",
    (
        "cache",
        "latest",
        "history",
        "history_csv",
        "shares_csv",
        "shares_json",
        "store",
        "provenance",
        "dictionary",
        "coordinated_later_commit",
    ),
)
def test_aug9_legacy_label_refuses_any_value_or_regime_drift(tmp_path: Path, attack: str) -> None:
    root = tmp_path / "legacy-repo"
    subprocess.run(["git", "clone", "-q", "--shared", str(ROOT), str(root)], check=True)
    # Pin the 2026-08-09 vintage these attacks describe; a live-head clone
    # made every expectation stale in the first candidate that advanced the
    # day (run 31682875024), deadlocking value publishes structurally.
    subprocess.run(
        ["git", "checkout", "-q", "9077ea4f27b4662ed6651828ee28183eed8fc727"],
        cwd=root,
        check=True,
    )
    paths = {
        "cache": root / f"data/raw/ngram_days/{TARGET}.json",
        "latest": root / "docs/data/latest.json",
        "history": root / "docs/data/history.json",
        "history_csv": root / "docs/data/history.csv",
        "shares_csv": root / "docs/data/shares.csv",
        "shares_json": root / "docs/data/shares.json",
        "store": root / "data/raw/gdelt_volume.csv",
        "provenance": root / "data/raw/provenance.csv",
        "dictionary": root / "dictionaries.json",
    }
    if attack == "coordinated_later_commit":
        for key in ("cache", "latest", "history", "store", "provenance"):
            paths[key].write_bytes(paths[key].read_bytes() + b"\n")
        subprocess.run(["git", "config", "user.name", "Legacy attack"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "actions@github.com"],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "add", *[str(paths[key]) for key in paths if key != "dictionary"]],
            cwd=root,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-q", "-m", "coordinated reseal"],
            cwd=root,
            check=True,
        )
    else:
        paths[attack].write_bytes(paths[attack].read_bytes() + b"\n")

    public = final_publication.public_status(root=root, today=TODAY)
    assert public["status"] == "delayed_final"
    assert public["latest_finalized_date"] is None
    assert public["source_receipt"] is None


def _legacy_history_repo(tmp_path: Path) -> Path:
    root = tmp_path / "legacy-history"
    subprocess.run(["git", "clone", "-q", "--shared", str(ROOT), str(root)], check=True)
    subprocess.run(
        ["git", "config", "user.name", "Legacy history attack"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        cwd=root,
        check=True,
    )
    # These aug9-legacy attacks describe the frozen 2026-08-09 vintage. A
    # clone of the LIVE head inherited whatever day the candidate had
    # advanced to, so the first candidate that actually published a newer
    # day made every SSR-claim expectation stale mid-gate -- a structural
    # deadlock on the first value advance. Pin the world the tests name.
    subprocess.run(
        ["git", "checkout", "-q", "9077ea4f27b4662ed6651828ee28183eed8fc727"],
        cwd=root,
        check=True,
    )
    return root


def _commit_legacy_path(root: Path, relative: str, message: str) -> None:
    subprocess.run(["git", "add", "--", relative], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


def _restore_aug9_blob(root: Path, relative: str) -> None:
    blob = subprocess.run(
        [
            "git",
            "show",
            f"9077ea4f27b4662ed6651828ee28183eed8fc727:{relative}",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    (root / relative).write_bytes(blob)


def test_aug9_legacy_history_allows_only_unchanged_first_parent_descendants(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "unchanged descendant one"],
        cwd=root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "unchanged descendant two"],
        cwd=root,
        check=True,
    )

    state = final_publication.public_status(root=root, today=TODAY)
    assert state["status"] == "legacy_proof_limited"


def test_aug9_legacy_history_refuses_mutation_followed_by_exact_revert(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    latest = root / "docs/data/latest.json"
    latest.write_bytes(latest.read_bytes() + b"\n")
    _commit_legacy_path(root, "docs/data/latest.json", "mutate pinned latest")
    _restore_aug9_blob(root, "docs/data/latest.json")
    _commit_legacy_path(root, "docs/data/latest.json", "restore exact pinned latest")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


def test_aug9_legacy_history_refuses_remove_then_exact_readd(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    subprocess.run(["git", "rm", "-q", "docs/data/latest.json"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "remove pinned latest"],
        cwd=root,
        check=True,
    )
    _restore_aug9_blob(root, "docs/data/latest.json")
    _commit_legacy_path(root, "docs/data/latest.json", "readd exact pinned latest")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


def test_aug9_legacy_history_refuses_merge_path_change_followed_by_revert(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    # The committed publication gate extracts an exact detached HEAD. Do not
    # make this Git-history attack depend on the caller having checked out a
    # named branch, or `git switch -` will try (and refuse) a commit SHA.
    subprocess.run(["git", "switch", "-q", "-c", "legacy-base"], cwd=root, check=True)
    subprocess.run(["git", "switch", "-q", "-c", "legacy-side"], cwd=root, check=True)
    latest = root / "docs/data/latest.json"
    latest.write_bytes(latest.read_bytes() + b"\n")
    _commit_legacy_path(root, "docs/data/latest.json", "side mutates pinned latest")
    subprocess.run(["git", "switch", "-q", "legacy-base"], cwd=root, check=True)
    subprocess.run(
        ["git", "merge", "-q", "--no-ff", "legacy-side", "-m", "merge path mutation"],
        cwd=root,
        check=True,
    )
    _restore_aug9_blob(root, "docs/data/latest.json")
    _commit_legacy_path(root, "docs/data/latest.json", "revert merge path mutation")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


def test_aug9_legacy_history_refuses_ssr_score_mutation_then_exact_revert(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    index = root / "docs/index.html"
    text = index.read_text(encoding="utf-8")
    assert 'id="composite-score" aria-live="polite">58.8</p>' in text
    index.write_text(
        text.replace(
            'id="composite-score" aria-live="polite">58.8</p>',
            'id="composite-score" aria-live="polite">99.9</p>',
            1,
        ),
        encoding="utf-8",
    )
    _commit_legacy_path(root, "docs/index.html", "contradict pinned SSR score")
    _restore_aug9_blob(root, "docs/index.html")
    _commit_legacy_path(root, "docs/index.html", "restore pinned SSR score")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


@pytest.mark.parametrize(
    "injected",
    (
        '<section id="official-final-score"><strong>99.9</strong></section>',
        ("<section><h2>Official finalized composite score</h2><p>99.9</p></section>"),
        (
            '<article><header id="claim-label">Official final measure</header>'
            '<div aria-labelledby="claim-label"><span>99.9</span></div>'
            "</article>"
        ),
        (
            "<div><h3>Latest channel score</h3>"
            "<table><tr><td><strong>99.9</strong></td></tr></table></div>"
        ),
        ("<section><p>99.9</p><h2>Official finalized composite score</h2></section>"),
        (
            "<section><h2>Official finalized composite score</h2>"
            f"<div>{'filler ' * 80}<strong>99.9</strong></div></section>"
        ),
        (
            "<section><div><h2>Official finalized composite score</h2></div>"
            "<div><p>99.9</p></div></section>"
        ),
        (
            "<section><div><p>99.9</p></div>"
            "<div><h2>Official finalized composite score</h2></div></section>"
        ),
        (
            "<article><div><div><h2>Official final score</h2></div></div>"
            f"<div>{'<span>filler</span>' * 80}<strong>99.9</strong></div>"
            "</article>"
        ),
        "<p>Official finalized composite score: 99.9</p>",
        "<table><tr><th>Official final score</th><td>99.9</td></tr></table>",
        '<meta name="official-final-score" content="99.9">',
        '<script type="application/ld+json">{"finalScore":99.9}</script>',
    ),
)
def test_aug9_legacy_refuses_any_unregistered_ssr_final_claim(
    tmp_path: Path, injected: str
) -> None:
    root = _legacy_history_repo(tmp_path)
    index = root / "docs/index.html"
    text = index.read_text(encoding="utf-8")
    index.write_text(text.replace("</body>", f"{injected}</body>"), encoding="utf-8")
    _commit_legacy_path(root, "docs/index.html", "add unregistered SSR claim")

    state = final_publication.public_status(root=root, today=TODAY)
    assert state["status"] == "delayed_final"
    assert state["latest_finalized_date"] is None


def test_aug9_legacy_ssr_claim_history_refuses_mutation_then_exact_revert(
    tmp_path: Path,
) -> None:
    root = _legacy_history_repo(tmp_path)
    index = root / "docs/index.html"
    original = index.read_bytes()
    text = original.decode("utf-8")
    index.write_text(
        text.replace(
            "</body>",
            '<script type="application/ld+json">{"finalScore":99.9}</script></body>',
        ),
        encoding="utf-8",
    )
    _commit_legacy_path(root, "docs/index.html", "add hidden SSR claim mirror")
    index.write_bytes(original)
    _commit_legacy_path(root, "docs/index.html", "restore exact SSR surface")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    (
        (
            "docs/data/history.csv",
            "2026-08-09,65.2,5.5,78.5,39.3,83.9,54.5",
            "2026-08-09,65.2,5.5,78.5,39.3,83.9,99.9",
        ),
        (
            "docs/data/shares.csv",
            "2026-08-09,0.023916201974727578",
            "2026-08-09,99.0",
        ),
        ("docs/data/shares.json", '"ratio": 1.9547', '"ratio": 99.0'),
    ),
)
def test_aug9_legacy_refuses_contradictory_public_mirror_values(
    tmp_path: Path, relative: str, old: str, new: str
) -> None:
    root = _legacy_history_repo(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


@pytest.mark.parametrize(
    "relative",
    ("docs/data/history.csv", "docs/data/shares.csv", "docs/data/shares.json"),
)
def test_aug9_legacy_mirrors_refuse_mutation_followed_by_exact_revert(
    tmp_path: Path, relative: str
) -> None:
    root = _legacy_history_repo(tmp_path)
    path = root / relative
    path.write_bytes(path.read_bytes() + b"\n")
    _commit_legacy_path(root, relative, f"mutate {relative}")
    _restore_aug9_blob(root, relative)
    _commit_legacy_path(root, relative, f"restore {relative}")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


@pytest.mark.parametrize(
    "relative",
    ("docs/data/history.csv", "docs/data/shares.csv", "docs/data/shares.json"),
)
def test_aug9_legacy_mirrors_refuse_remove_then_exact_readd(tmp_path: Path, relative: str) -> None:
    root = _legacy_history_repo(tmp_path)
    subprocess.run(["git", "rm", "-q", "--", relative], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"remove {relative}"],
        cwd=root,
        check=True,
    )
    _restore_aug9_blob(root, relative)
    _commit_legacy_path(root, relative, f"readd {relative}")

    assert final_publication.public_status(root=root, today=TODAY)["status"] == ("delayed_final")


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
    assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
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
        receipt["append_contract"]["provenance_prefix_sha256"] = _sha(b"".join(prefix))
    elif attack == "target_row":
        store = root / "data/raw/gdelt_volume.csv"
        store.write_text(
            store.read_text(encoding="utf-8").replace("2026-08-09,1.0", "2026-08-09,0.5"),
            encoding="utf-8",
        )
        receipt["bindings"]["candidate_row_sha256"] = _sha(
            final_publication._canonical_bytes({"date": TARGET.isoformat(), "pakistan_west": 0.5})
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
        assert _acquire(root, monkeypatch, _complete_result(root))["status"] == ("target_ready")
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
            pd.DataFrame({"pakistan_west": [999.0]}, index=[pd.Timestamp(TODAY)]),
        ]
    )
    with pytest.raises(SystemExit, match="rows after exact final target"):
        run_daily._fail_loudly_on_partial_data(with_d0, TARGET)


def test_target_nulls_and_null_composites_refuse_before_site_write() -> None:
    index = pd.to_datetime([TARGET])
    daily = pd.DataFrame({"pakistan_west": [1.0], "composite": [1.0]}, index=index)
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
        json.dumps({"date": TODAY.isoformat(), "provisional": True, "composite": 99.9}),
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

    marker = final_publication.record_pipeline_failed(TARGET, root=root, base_commit="a" * 40)
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
    store.write_text("date,pakistan_west\n2026-08-08,0.25\n", encoding="utf-8")
    monkeypatch.setattr(fetch_gdelt, "RAW_DIR", raw)
    observed: list[tuple[date, date]] = []

    def fetch(_dictionary: dict, start: date, end: date) -> pd.DataFrame:
        observed.append((start, end))
        return pd.DataFrame({"pakistan_west": [1.0]}, index=pd.Index([TARGET], name="date"))

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
        'python -m pytest -q -m "not live" tests/test_dictionaries.py '
        "tests/test_registration_freezes.py"
    ) in workflow
    assert "python -m pytest -q\n" not in workflow
    assert "bash scripts/publish_push.sh" not in workflow
    assert workflow.count("bash scripts/publish_final_cas.sh") == 1
    assert workflow.count("git push origin HEAD:main") == 0
    assert publisher.count("bash scripts/gate.sh --publish") == 1
    assert "bash scripts/gate.sh --committed" not in publisher
    assert publisher.count('git push origin "$FROZEN_CANDIDATE_SHA:main"') == 1
    assert "remote_commit=$(git rev-parse origin/main)" in publisher
    assert "candidate_head=$(git rev-parse HEAD)" in publisher
    assert 'candidate_parent=$(git rev-parse "$FROZEN_CANDIDATE_SHA^")' in publisher
    assert "current_head=$(git rev-parse HEAD)" in publisher
    assert "/usr/bin/time -v" in publisher
    assert "git worktree add --detach" in publisher
    publish_lane = workflow.split("- name: Gate and CAS-publish final or value-free refusal", 1)[1]
    assert "id: publish" in publish_lane
    refusal_function = publisher.split("publish_refusal()", 1)[1]
    assert (
        "git add data/raw/final_publication_status.json docs/data/status.json" in refusal_function
    )
    assert "failure disclosure attempted to stage candidate value bytes" in refusal_function
    assert '--failure-stage "$failure_stage"' in refusal_function
    assert "failure_stage=source" in refusal_function
    assert "steps.pipeline.outcome == 'success'" in workflow
    assert "steps.audit.outcome == 'success'" in workflow
    assert '"${{ steps.derived.outcome }}"' in workflow
    assert '[ "$DERIVED_OUTCOME" = "success" ]' in publisher
    success_dispatch = publisher.rsplit('if [ "$SOURCE_OUTCOME" = "success" ]', 1)[1]
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
    assert "CONTRACT_TODAY=$(date -u +%F)" in workflow
    assert '--check-published-target "$TARGET"' in workflow
    assert '--root "$REMOTE_ROOT"' in workflow
    assert "git worktree add --quiet --detach" in workflow
    assert "REMOTE_PROOF_STATUS" not in workflow
    assert '--today "${{ steps.guard.outputs.contract_today }}"' in workflow
    assert '--contract-today "${{ steps.guard.outputs.contract_today }}"' in workflow

    daily = (ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
    staging = (ROOT / "scripts/stage_daily_outputs.sh").read_text(encoding="utf-8")
    assert "id: final_contract" in daily
    assert '--acquire-target "${{ steps.final_contract.outputs.target }}"' in daily
    assert '--contract-today "${{ steps.final_contract.outputs.today }}"' in daily
    assert '"${{ job.status }}" "${{ steps.final_contract.outputs.target }}"' in daily
    assert "datetime.now" not in staging
    assert "date -u" not in staging
    assert 'TARGET="${2:?missing frozen final-publication target}"' in staging


def _publisher_e2e_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    remote = tmp_path / "remote.git"
    root = tmp_path / "publisher"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Publisher E2E"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "actions@github.com"],
        cwd=root,
        check=True,
    )
    (root / "scripts").mkdir()
    shutil.copy2(
        ROOT / "scripts/publish_final_cas.sh",
        root / "scripts/publish_final_cas.sh",
    )
    (root / "scripts/gate.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8"
    )
    (root / "bin").mkdir()
    rights_python = root / "bin/python"
    rights_python.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [ \"${1:-}\" = '-m' ] && "
        "[ \"${2:-}\" = 'scripts.generate_public_api_byte_manifest' ]; then\n"
        "  if [ \"${3:-}\" != '--check-index' ]; then\n"
        "    mkdir -p docs/data\n"
        "    printf '{\"object_type\":\"igrm.public_api_byte_manifest\","
        "\"test_fixture_only\":true}\n' > "
        "docs/data/public_api_byte_manifest.json\n"
        "  fi\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${3:-}\" = '--record-pipeline-failed' ]; then\n"
        "  mkdir -p data/raw\n"
        '  printf \'{"status":"acquisition_failed"}\\n\' > '
        "data/raw/final_publication_status.json\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${3:-}\" = '--write-public-status' ]; then\n"
        "  mkdir -p docs/data\n"
        '  printf \'{"final_publication":{"status":'
        '"acquisition_failed"}}\\n\' > docs/data/status.json\n'
        "  printf '<p>value-free refusal</p>\\n' > docs/index.html\n"
        "  printf '<p>value-free refusal</p>\\n' > docs/status.html\n"
        "  exit 0\n"
        "fi\n"
        "if [ \"${1:-}\" != '-m' ] || "
        "[ \"${2:-}\" != 'src.final_publication' ] || "
        "[ \"${3:-}\" != '--check-release-candidate' ]; then\n"
        "  echo 'unexpected test python invocation' >&2\n"
        "  exit 90\n"
        "fi\n"
        "candidate_class=${4:-}\n"
        'if [ "$candidate_class" = final ] && '
        "[ -f .rights-expired-after-gate ]; then\n"
        '  echo \'{"status":"promotion_receipt_invalid",'
        '"evaluated_at_utc":"2026-08-11T00:00:01Z"}\'\n'
        "  exit 2\n"
        "fi\n"
        "candidate=${RELEASE_CANDIDATE_OVERRIDE:-$(git rev-parse HEAD)}\n"
        'printf \'{"status":"release_rights_verified",'
        '"candidate_class": "%s",'
        '"candidate_sha": "%s"}\\n\' '
        '"$candidate_class" "$candidate"\n',
        encoding="utf-8",
    )
    rights_python.chmod(0o755)
    (root / "docs/data").mkdir(parents=True)
    (root / "data/raw").mkdir(parents=True)
    (root / "docs/data/base.json").write_text("{}\n", encoding="utf-8")
    (root / "data/raw/base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=root, check=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    subprocess.run(["git", "push", "-q", "-u", "origin", "main"], cwd=root, check=True)
    return root, remote, base


def _run_publisher(
    root: Path,
    base: str,
    env: dict[str, str],
    outcomes: tuple[str, str, str, str] = ("success",) * 4,
) -> subprocess.CompletedProcess[str]:
    run_env = {
        **env,
        "PATH": f"{root / 'bin'}:{env.get('PATH', os.environ.get('PATH', ''))}",
    }
    return subprocess.run(
        [
            "bash",
            "scripts/publish_final_cas.sh",
            TARGET.isoformat(),
            base,
            *outcomes,
        ],
        cwd=root,
        env=run_env,
        capture_output=True,
        text=True,
    )


def _remote_main(remote: Path) -> str:
    return subprocess.run(
        ["git", f"--git-dir={remote}", "rev-parse", "refs/heads/main"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_final_cas_refuses_extra_local_ancestor_before_candidate_generation(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    (root / "docs/local.txt").write_text("unpublished ancestor\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/local.txt"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "extra local ancestor"],
        cwd=root,
        check=True,
    )
    (root / "docs/data/candidate.json").write_text("{}\n", encoding="utf-8")
    env = {**os.environ, "IGRM_PUBLISH_TOKEN": "test-token"}

    result = _run_publisher(root, base, env)

    assert result.returncode != 0
    assert "local HEAD" in result.stdout
    assert _remote_main(remote) == base


def test_final_cas_gates_and_pushes_exact_single_parent_candidate(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    publisher = root / "scripts/publish_final_cas.sh"
    publisher.write_text(
        publisher.read_text(encoding="utf-8").replace("/usr/bin/time -v ", ""),
        encoding="utf-8",
    )
    (root / "docs/data/candidate.json").write_text("{}\n", encoding="utf-8")
    env = {**os.environ, "IGRM_PUBLISH_TOKEN": "test-token"}

    result = _run_publisher(root, base, env)

    assert result.returncode == 0, result.stderr
    candidate = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert _remote_main(remote) == candidate
    assert (
        subprocess.run(
            ["git", "rev-parse", f"{candidate}^"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == base
    )


def test_final_cas_midnight_rights_barrier_refuses_before_push(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    publisher = root / "scripts/publish_final_cas.sh"
    publisher.write_text(
        publisher.read_text(encoding="utf-8").replace("/usr/bin/time -v ", ""),
        encoding="utf-8",
    )
    (root / "scripts/gate.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '2026-08-11T00:00:01Z\\n' > .rights-expired-after-gate\n",
        encoding="utf-8",
    )
    (root / "docs/data/candidate.json").write_text("{}\n", encoding="utf-8")
    env = {**os.environ, "IGRM_PUBLISH_TOKEN": "test-token"}

    result = _run_publisher(root, base, env)

    assert result.returncode != 0
    assert "candidate-class release proof is not valid" in result.stdout
    assert _remote_main(remote) == base


def test_final_cas_release_proof_must_name_frozen_candidate(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    publisher = root / "scripts/publish_final_cas.sh"
    publisher.write_text(
        publisher.read_text(encoding="utf-8").replace("/usr/bin/time -v ", ""),
        encoding="utf-8",
    )
    (root / "docs/data/candidate.json").write_text("{}\n", encoding="utf-8")
    env = {
        **os.environ,
        "IGRM_PUBLISH_TOKEN": "test-token",
        "RELEASE_CANDIDATE_OVERRIDE": "f" * 40,
    }

    result = _run_publisher(root, base, env)

    assert result.returncode != 0
    assert "is not frozen candidate" in result.stdout
    assert _remote_main(remote) == base


def test_final_cas_expired_rights_still_publish_value_free_refusal(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    publisher = root / "scripts/publish_final_cas.sh"
    publisher.write_text(
        publisher.read_text(encoding="utf-8").replace("/usr/bin/time -v ", ""),
        encoding="utf-8",
    )
    (root / "scripts/gate.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '2026-08-11T00:00:01Z\\n' > .rights-expired-after-gate\n",
        encoding="utf-8",
    )
    env = {**os.environ, "IGRM_PUBLISH_TOKEN": "test-token"}

    result = _run_publisher(
        root,
        base,
        env,
        outcomes=("failure", "skipped", "skipped", "skipped"),
    )

    assert result.returncode == 0, result.stderr
    candidate = _remote_main(remote)
    changed = subprocess.run(
        [
            "git",
            f"--git-dir={remote}",
            "diff-tree",
            "--no-commit-id",
            "--name-only",
            "-r",
            candidate,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert set(changed) == {
        "data/raw/final_publication_status.json",
        "docs/data/status.json",
        "docs/data/public_api_byte_manifest.json",
        "docs/index.html",
        "docs/status.html",
    }
    assert not any(
        path.startswith("data/raw/ngram_days/")
        or path.startswith("data/raw/final_publication_receipts/")
        or path in {"data/raw/gdelt_volume.csv", "data/raw/provenance.csv"}
        for path in changed
    )


def test_final_cas_refuses_merge_parent_candidate_before_gate_or_push(
    tmp_path: Path,
) -> None:
    root, remote, base = _publisher_e2e_repo(tmp_path)
    real_git = shutil.which("git")
    assert real_git is not None
    side = subprocess.run(
        [real_git, "commit-tree", f"{base}^{{tree}}", "-p", base],
        cwd=root,
        input="side parent\n",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    wrapper_dir = tmp_path / "bin"
    wrapper_dir.mkdir()
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'if [ "${1:-}" = "commit" ]; then\n'
        '  tree=$("$REAL_GIT" write-tree)\n'
        '  head=$("$REAL_GIT" rev-parse HEAD)\n'
        '  candidate=$(printf \'forced merge candidate\\n\' | "$REAL_GIT" commit-tree "$tree" -p "$head" -p "$EXTRA_PARENT")\n'
        '  "$REAL_GIT" reset --hard "$candidate" >/dev/null\n'
        "  exit 0\n"
        "fi\n"
        'exec "$REAL_GIT" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    (root / "docs/data/candidate.json").write_text("{}\n", encoding="utf-8")
    env = {
        **os.environ,
        "IGRM_PUBLISH_TOKEN": "test-token",
        "PATH": f"{wrapper_dir}:{os.environ['PATH']}",
        "REAL_GIT": real_git,
        "EXTRA_PARENT": side,
    }

    result = _run_publisher(root, base, env)

    assert result.returncode != 0
    assert "exactly one parent" in result.stdout
    assert _remote_main(remote) == base


def test_rescue_predicates_and_public_pages_use_final_date_contract() -> None:
    for relative in (
        ".github/workflows/nowcast.yml",
        ".github/workflows/watchdog.yml",
    ):
        workflow = (ROOT / relative).read_text(encoding="utf-8")
        assert "['date']" in workflow
        assert "['_meta']['generated']" not in workflow
        assert 'date -u -d "yesterday" +%F' in workflow

    homepage_path = ROOT / "docs/index.html"
    status_page_path = ROOT / "docs/status.html"
    homepage_bytes = homepage_path.read_bytes()
    status_page_bytes = status_page_path.read_bytes()
    homepage = homepage_bytes.decode("utf-8")
    app = (ROOT / "docs/app.js").read_text(encoding="utf-8")
    status = json.loads((ROOT / "docs/data/status.json").read_text(encoding="utf-8"))
    final_state = status["final_publication"]
    assert 'id="final-publication-status"' in homepage
    assert 'id="final-publication-status" hidden' not in homepage
    for relative, current_bytes in (
        ("docs/index.html", homepage_bytes),
        ("docs/status.html", status_page_bytes),
    ):
        assert (
            status_data.static_final_disclosure_bytes(final_state, relative, current_bytes)
            == current_bytes
        )
    assert "nowcast remains separate and non-final" in app
    # Pinned `finalized is False` throughout the outage era, which became
    # untrue the moment a candidate carried a proven final again. The
    # durable property is the pairing: a finalized state must carry its
    # source receipt, and an unfinalized one must not claim one.
    assert final_state["finalized"] in (True, False)
    assert (final_state["source_receipt"] is not None) == (
        final_state["finalized"] is True
    )


def test_static_final_disclosure_keeps_the_bounded_legacy_boundary() -> None:
    message = status_data._static_final_message(
        {
            "target_date": TARGET.isoformat(),
            "latest_finalized_date": TARGET.isoformat(),
            "status": "legacy_proof_limited",
            "finalized": False,
        }
    )

    for expected in (
        "Bounded historical publication",
        "target <b>2026-08-09</b> remains visible",
        "exactly match commit 9077ea4",
        "source acquisition receipt",
        "reconstructable English denominator",
        "cache-to-store calibration/transform receipt",
        "store-to-public score derivation receipt",
        "source-retention and redistribution rights review",
        "provisional nowcast remains separate and non-final",
    ):
        assert expected in message
