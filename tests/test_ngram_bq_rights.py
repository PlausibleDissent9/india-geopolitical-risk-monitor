"""Hostile tests for the BigQuery backfill rights gate.

The gate must refuse unless ALL of: founder-signed two-use decision in its
review window, target inside the signed age bound, target ledger-disclosed
as a lost source, and an active profile 3.0 whose signature verifies over
the exact committed profile bytes.
"""
from __future__ import annotations

import base64
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import ngram_bq_attestation as bqa
from src import ngram_bq_rights as bqr
from src import ngram_rights

ROOT = Path(__file__).resolve().parents[1]
TARGET = date(2026, 8, 11)
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
SIGNER_ID = "human:igrm-ngram-rights-reviewer"
ACTIVATION_SIG = "governance/rights_decisions/ngram_bq_backfill-activation-3.0.sig"


@pytest.fixture
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ngram_rights, "_utc_now", lambda: NOW)


def _profile_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _synthetic_root(tmp_path: Path, *, activate: bool = True) -> Path:
    root = tmp_path / "root"
    key = Ed25519PrivateKey.generate()
    pub64 = base64.b64encode(
        key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode("ascii")

    registry_path = root / "governance/source_rights_registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "governance/source_rights_registry.json", registry_path)
    decisions = root / "governance/rights_decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for row in registry["sources"]:
        if row.get("decision_state") != "approved":
            continue
        artifact_bytes = (ROOT / row["decision_artifact_path"]).read_bytes()
        (root / row["decision_artifact_path"]).write_bytes(artifact_bytes)
        (root / row["decision_signature_path"]).write_bytes(key.sign(artifact_bytes))

    (root / "governance/rights_signers.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "effective": "2026-08-08",
                "default_policy": "deny",
                "signers": [
                    {
                        "signer_id": SIGNER_ID,
                        "name": "Synthetic reviewer",
                        "role": "rights_reviewer",
                        "public_key_ed25519_base64": pub64,
                        "effective": "2026-08-01",
                        "revoked_on": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    ledger = root / bqa.REFUSAL_LEDGER_RELATIVE / f"{TARGET.isoformat()}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "target_date": TARGET.isoformat(),
                "failure_stage": "source",
                "reason_code": "source_acquisition_failed",
                "status": "refused_value_free",
                "generated": "2026-08-12 06:20 IST",
            }
        ),
        encoding="utf-8",
    )

    profile = json.loads(
        (ROOT / bqa.PROFILE_RELATIVE).read_text(encoding="utf-8")
    )
    profile_path = root / bqa.PROFILE_RELATIVE
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    if activate:
        profile["activation"] = {
            "state": "active",
            "signer_id": SIGNER_ID,
            "reviewed_on": "2026-08-15",
            "review_due": "2026-11-13",
            "signature_path": ACTIVATION_SIG,
        }
        raw = _profile_bytes(profile)
        profile_path.write_bytes(raw)
        (root / ACTIVATION_SIG).write_bytes(key.sign(raw))
    else:
        profile_path.write_bytes(_profile_bytes(profile))
    return root


def _authority(root: Path) -> ngram_rights.NonGitTestRightsAuthority:
    return ngram_rights.non_git_test_authority(root)


def _refuses(root: Path, code: str, *, target: date = TARGET) -> None:
    with pytest.raises(bqr.BqRightsError) as excinfo:
        bqr.require_bq_backfill_rights(
            target=target, root=root, test_authority=_authority(root)
        )
    assert excinfo.value.code == code


def test_full_chain_authorizes_with_proof(
    tmp_path: Path, fixed_clock: None
) -> None:
    root = _synthetic_root(tmp_path)
    proof = bqr.require_bq_backfill_rights(
        target=TARGET, root=root, test_authority=_authority(root)
    )
    assert proof["source_id"] == "gdelt_bq_webngrams"
    assert proof["profile_id"] == bqa.PROFILE_ID
    assert proof["permitted_uses"] == ["model_processing", "publish_derived_value"]
    assert proof["evaluated_age_days"] == 5
    assert proof["refusal_ledger_path"].endswith("2026-08-11.json")
    assert proof["profile_signature_path"] == ACTIVATION_SIG


def test_pending_profile_refuses(tmp_path: Path, fixed_clock: None) -> None:
    root = _synthetic_root(tmp_path, activate=False)
    _refuses(root, "bq_backfill_profile_inactive")


def test_undisclosed_target_refuses(tmp_path: Path, fixed_clock: None) -> None:
    root = _synthetic_root(tmp_path)
    _refuses(root, "bq_backfill_target_not_ledger_disclosed", target=date(2026, 8, 10))


def test_target_older_than_signed_bound_refuses(
    tmp_path: Path, fixed_clock: None
) -> None:
    root = _synthetic_root(tmp_path)
    old = date(2026, 7, 1)
    ledger = root / bqa.REFUSAL_LEDGER_RELATIVE / f"{old.isoformat()}.json"
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "target_date": old.isoformat(),
                "failure_stage": "source",
                "reason_code": "source_acquisition_failed",
                "status": "refused_value_free",
                "generated": "2026-07-02 06:20 IST",
            }
        ),
        encoding="utf-8",
    )
    _refuses(root, "bq_backfill_rights_target_too_old", target=old)


def test_tampered_profile_bytes_refuse(tmp_path: Path, fixed_clock: None) -> None:
    root = _synthetic_root(tmp_path)
    profile_path = root / bqa.PROFILE_RELATIVE
    document = json.loads(profile_path.read_text(encoding="utf-8"))
    document["expected_utc_half_hour_windows"] = 24
    profile_path.write_bytes(_profile_bytes(document))
    _refuses(root, "bq_backfill_profile_signature_invalid")


def test_unapproved_row_refuses(tmp_path: Path, fixed_clock: None) -> None:
    root = _synthetic_root(tmp_path)
    registry_path = root / "governance/source_rights_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    for row in registry["sources"]:
        if row["source_id"] == "gdelt_bq_webngrams":
            row.update(
                decision_state="review_required",
                decision_id="pending:gdelt_bq_webngrams",
                decision_owner="unassigned",
                signer_id=None,
                decision_artifact_path=None,
                decision_artifact_sha256=None,
                decision_signature_path=None,
                reviewed_on=None,
                review_due=None,
                max_current_age_days=None,
                permitted_uses=[],
            )
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    _refuses(root, "bq_backfill_rights_decision_review_required")
