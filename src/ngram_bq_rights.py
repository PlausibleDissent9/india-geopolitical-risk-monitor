"""Rights gate for the BigQuery backfill lane (profile 3.0).

Before any mirror query runs, this module requires, from committed bytes:
the founder-signed ``gdelt_bq_webngrams`` decision (exactly the two
aggregate uses, in review window, target within the signed age bound), the
target day's durable source-stage refusal ledger entry (the signed
statement scopes recovery to ledger-disclosed lost days), and an ``active``
profile 3.0 whose detached Ed25519 signature verifies over the exact
profile bytes. Signer trust is the same reviewed code pin the aggregate
lane uses — one enrolled human, one pin.
"""
from __future__ import annotations

import base64
import json
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import ngram_bq_attestation, ngram_rights, publication_guard

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "gdelt_bq_webngrams"
REQUIRED_USES = frozenset({"model_processing", "publish_derived_value"})
PROFILE_RELATIVE = ngram_bq_attestation.PROFILE_RELATIVE


class BqRightsError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise BqRightsError(code)


def _day(value: object, code: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        _fail(code)


def require_bq_backfill_rights(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Refuse-or-proof for one backfill target day."""

    checked_at = (
        ngram_rights._utc_now().astimezone(timezone.utc).replace(microsecond=0)
    )
    decision_day = checked_at.date()
    rights_path = root / "governance/source_rights_registry.json"
    signers_path = root / "governance/rights_signers.json"
    try:
        rights_raw, rights_document, _ = publication_guard._read_json(
            rights_path, "rights_registry_unreadable"
        )
        signers_raw, signers_document, _ = publication_guard._read_json(
            signers_path, "rights_signers_unreadable"
        )
        signers = publication_guard._validate_signers(signers_document)
        rights = publication_guard._validate_rights_registry(
            rights_document, root, signers
        )
    except publication_guard.PublicationGuardError as exc:
        _fail(exc.code)
    if (
        _day(rights_document.get("effective"), "rights_effective_date_invalid")
        > decision_day
        or _day(signers_document.get("effective"), "rights_effective_date_invalid")
        > decision_day
    ):
        _fail("rights_registry_future_dated")

    source = rights.get(SOURCE_ID)
    if source is None:
        _fail("bq_backfill_rights_decision_missing")
    if source.get("decision_state") != "approved":
        _fail(f"bq_backfill_rights_decision_{source.get('decision_state') or 'missing'}")
    reviewed = _day(source.get("reviewed_on"), "bq_backfill_rights_dates_invalid")
    due = _day(source.get("review_due"), "bq_backfill_rights_dates_invalid")
    if reviewed > decision_day:
        _fail("bq_backfill_rights_decision_future_dated")
    if due < decision_day:
        _fail("bq_backfill_rights_decision_expired")

    signer_id = source.get("signer_id")
    if not isinstance(signer_id, str) or signer_id not in signers:
        _fail("bq_backfill_rights_signer_missing")
    signer = signers[signer_id]
    try:
        ngram_rights._require_trusted_signer(
            root=root,
            signer_id=signer_id,
            signer=signer,
            signers_raw=signers_raw,
            test_authority=test_authority,
        )
    except ngram_rights.NgramRightsError as exc:
        _fail(exc.code)
    signer_effective = _day(signer.get("effective"), "bq_backfill_rights_signer_invalid")
    if signer_effective > decision_day:
        _fail("bq_backfill_rights_signer_future_dated")
    revoked_on = signer.get("revoked_on")
    signer_revoked = (
        _day(revoked_on, "bq_backfill_rights_signer_invalid")
        if revoked_on is not None
        else None
    )
    if signer_revoked is not None and decision_day >= signer_revoked:
        _fail("bq_backfill_rights_signer_revoked")

    uses = source.get("permitted_uses")
    if not isinstance(uses, list) or set(uses) != REQUIRED_USES:
        _fail("bq_backfill_rights_uses_not_exact")
    max_age = source.get("max_current_age_days")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0:
        _fail("bq_backfill_rights_max_age_invalid")
    evaluated_age = (decision_day - target).days
    if evaluated_age < 0:
        _fail("bq_backfill_rights_target_in_future")
    if evaluated_age > max_age:
        # The signed base artifact carries no recovery-target carve-out; a
        # target older than the signed bound needs a fresh human decision.
        _fail("bq_backfill_rights_target_too_old")
    verified_decision = source.get("_verified_decision")
    if not isinstance(verified_decision, dict):
        _fail("bq_backfill_signed_decision_missing")

    ledger_relative = (
        ngram_bq_attestation.REFUSAL_LEDGER_RELATIVE / f"{target.isoformat()}.json"
    )
    try:
        ledger = json.loads((root / ledger_relative).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _fail("bq_backfill_target_not_ledger_disclosed")
    if (
        not isinstance(ledger, dict)
        or ledger.get("target_date") != target.isoformat()
        or ledger.get("failure_stage") != "source"
        or ledger.get("reason_code") != "source_acquisition_failed"
    ):
        _fail("bq_backfill_target_not_ledger_disclosed")

    profile_path = root / PROFILE_RELATIVE
    try:
        profile_raw = profile_path.read_bytes()
        profile = json.loads(profile_raw)
    except (OSError, ValueError):
        _fail("bq_backfill_profile_unreadable")
    if (
        not isinstance(profile, dict)
        or profile.get("profile_id") != ngram_bq_attestation.PROFILE_ID
    ):
        _fail("bq_backfill_profile_unreadable")
    activation = profile.get("activation")
    if not isinstance(activation, dict) or activation.get("state") != "active":
        _fail("bq_backfill_profile_inactive")
    if activation.get("signer_id") != signer_id:
        _fail("bq_backfill_profile_signer_mismatch")
    profile_reviewed = _day(
        activation.get("reviewed_on"), "bq_backfill_profile_dates_invalid"
    )
    profile_due = _day(
        activation.get("review_due"), "bq_backfill_profile_dates_invalid"
    )
    if profile_reviewed > decision_day:
        _fail("bq_backfill_profile_future_dated")
    if profile_due < decision_day:
        _fail("bq_backfill_profile_expired")
    signature_relative = activation.get("signature_path")
    if not isinstance(signature_relative, str):
        _fail("bq_backfill_profile_signature_invalid")
    try:
        signature_raw = (root / signature_relative).read_bytes()
    except OSError:
        _fail("bq_backfill_profile_signature_invalid")
    if len(signature_raw) != 64:
        _fail("bq_backfill_profile_signature_invalid")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(
                str(signer.get("public_key_ed25519_base64")), validate=True
            )
        )
        public_key.verify(signature_raw, profile_raw)
    except (ValueError, InvalidSignature):
        _fail("bq_backfill_profile_signature_invalid")

    release_deadline_day = min(due, profile_due, target + timedelta(days=max_age))
    if signer_revoked is not None:
        release_deadline_day = min(
            release_deadline_day, signer_revoked - timedelta(days=1)
        )
    return {
        "source_id": SOURCE_ID,
        "profile_id": ngram_bq_attestation.PROFILE_ID,
        "decision_id": source["decision_id"],
        "signer_id": signer_id,
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "profile_reviewed_on": profile_reviewed.isoformat(),
        "profile_review_due": profile_due.isoformat(),
        "target_date": target.isoformat(),
        "evaluated_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rights_as_of": decision_day.isoformat(),
        "max_current_age_days": max_age,
        "evaluated_age_days": evaluated_age,
        "release_deadline_utc": f"{release_deadline_day.isoformat()}T23:59:59Z",
        "permitted_uses": sorted(REQUIRED_USES),
        "refusal_ledger_path": ledger_relative.as_posix(),
        "rights_registry_sha256": ngram_rights._sha256(rights_raw),
        "rights_signers_sha256": ngram_rights._sha256(signers_raw),
        "decision_artifact_path": source["decision_artifact_path"],
        "decision_artifact_sha256": verified_decision["artifact_sha256"],
        "decision_signature_path": source["decision_signature_path"],
        "decision_signature_sha256": verified_decision["signature_sha256"],
        "profile_sha256": ngram_rights._sha256(profile_raw),
        "profile_signature_path": signature_relative,
        "profile_signature_sha256": ngram_rights._sha256(signature_raw),
    }
