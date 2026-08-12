"""Signed authorization boundary for identity-bearing NGram processing."""

from __future__ import annotations

import base64
import hashlib
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from . import ngram_rights_contract, publication_guard

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = ngram_rights_contract.SOURCE_ID
PUBLIC_IDENTITY_USES = {
    "model_processing",
    "publish_derived_value",
    "publish_extract",
    "redistribute_full_record",
}
DAILY_AGGREGATE_USES = frozenset({"model_processing", "publish_derived_value"})
PUBLIC_IDENTITY_RIGHTS_PROOF_FIELDS = frozenset(
    {
        "source_id",
        "decision_id",
        "signer_id",
        "reviewed_on",
        "review_due",
        "target_date",
        "evaluated_at_utc",
        "rights_as_of",
        "max_current_age_days",
        "evaluated_age_days",
        "release_deadline_utc",
        "permitted_uses",
        "trusted_signer_public_key_sha256",
        "rights_registry_sha256",
        "rights_signers_sha256",
        "decision_artifact_path",
        "decision_artifact_sha256",
        "decision_signature_path",
        "decision_signature_sha256",
    }
)
DAILY_AGGREGATE_RIGHTS_PROOF_FIELDS = PUBLIC_IDENTITY_RIGHTS_PROOF_FIELDS | {
    "profile_id",
    "historical_recovery_targets",
    "historical_recovery_targets_sha256",
    "recovery_exception_used",
    "signer_revoked_on",
}
PRODUCTION_HUMAN_ROLES = frozenset({"principal_investigator", "rights_reviewer"})
# Production trust requires the exact human signer ID, Ed25519 public key and
# closed role here in a reviewed code transition as well as in the signed
# governance registries. Merely adding a self-generated key to mutable
# repository JSON is not trust. The entry below binds the founder-run
# 2026-08-12 aggregate-2.0 rights review; its signed decision artifact is
# governance/rights_decisions/gdelt_web_ngrams_v5-aggregate-2.0.json.
PRODUCTION_TRUSTED_SIGNERS: dict[str, tuple[str, str]] = {
    "human:igrm-ngram-rights-reviewer": (
        "qcS/4lMEpmUO0RhFRkVILagrVBIhMsSfVYksZmRvgFQ=",
        "rights_reviewer",
    ),
}


@dataclass(frozen=True)
class NonGitTestRightsAuthority:
    """Explicit signer trust for a single non-Git synthetic fixture."""

    root: Path
    signers_sha256: str
    trusted_signers: tuple[tuple[str, str, str], ...]


class NgramRightsError(RuntimeError):
    """Stable refusal before any identity-bearing source processing."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise NgramRightsError(code)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc_second(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("ngram_rights_proof_time_invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail("ngram_rights_proof_time_invalid")
    if (
        parsed.utcoffset() != timedelta(0)
        or parsed.microsecond != 0
        or parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value
    ):
        _fail("ngram_rights_proof_time_invalid")
    return parsed


@dataclass(frozen=True)
class _ValidatedProof:
    value: dict[str, Any]
    reviewed: date
    due: date
    as_of: date
    evaluated_at: datetime
    deadline: datetime
    max_age: int
    age: int


def _parse_proof_day(value: object) -> date:
    if not isinstance(value, str):
        _fail("ngram_rights_proof_date_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail("ngram_rights_proof_date_invalid")
    if parsed.isoformat() != value:
        _fail("ngram_rights_proof_date_invalid")
    return parsed


def _validate_common_rights_proof(
    value: object,
    *,
    target: date,
    expected_fields: frozenset[str],
    expected_uses: frozenset[str],
) -> _ValidatedProof:
    """Validate shared proof bytes without inventing alternate time values."""

    if not isinstance(value, dict) or set(value) != expected_fields:
        _fail("ngram_rights_proof_fields_invalid")
    if (
        value.get("source_id") != SOURCE_ID
        or value.get("target_date") != target.isoformat()
        or value.get("permitted_uses") != sorted(expected_uses)
    ):
        _fail("ngram_rights_proof_binding_invalid")
    reviewed = _parse_proof_day(value.get("reviewed_on"))
    due = _parse_proof_day(value.get("review_due"))
    as_of = _parse_proof_day(value.get("rights_as_of"))
    evaluated_at = _parse_utc_second(value.get("evaluated_at_utc"))
    deadline = _parse_utc_second(value.get("release_deadline_utc"))
    max_age = value.get("max_current_age_days")
    age = value.get("evaluated_age_days")
    if (
        isinstance(max_age, bool)
        or not isinstance(max_age, int)
        or max_age < 0
        or isinstance(age, bool)
        or not isinstance(age, int)
        or age < 0
        or age != (as_of - target).days
        or evaluated_at.date() != as_of
        or reviewed > as_of
        or due < as_of
        or deadline.time() != datetime.max.time().replace(microsecond=0)
        or deadline.date() < target
        or as_of > deadline.date()
        or evaluated_at > deadline
    ):
        _fail("ngram_rights_proof_temporal_invalid")
    for key in (
        "decision_id",
        "signer_id",
        "decision_artifact_path",
        "decision_signature_path",
    ):
        if not isinstance(value.get(key), str) or not value[key]:
            _fail("ngram_rights_proof_binding_invalid")
    for key in (
        "trusted_signer_public_key_sha256",
        "rights_registry_sha256",
        "rights_signers_sha256",
        "decision_artifact_sha256",
        "decision_signature_sha256",
    ):
        digest = value.get(key)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            _fail("ngram_rights_proof_binding_invalid")
    return _ValidatedProof(
        value=dict(value),
        reviewed=reviewed,
        due=due,
        as_of=as_of,
        evaluated_at=evaluated_at,
        deadline=deadline,
        max_age=max_age,
        age=age,
    )


def validate_public_identity_rights_proof(value: object, *, target: date) -> dict[str, Any]:
    """Validate the complete closed proof emitted by the rights authority."""

    proof = _validate_common_rights_proof(
        value,
        target=target,
        expected_fields=PUBLIC_IDENTITY_RIGHTS_PROOF_FIELDS,
        expected_uses=frozenset(PUBLIC_IDENTITY_USES),
    )
    try:
        ordinary_deadline = target + timedelta(days=proof.max_age)
    except OverflowError:
        _fail("ngram_rights_proof_temporal_invalid")
    if (
        proof.age > proof.max_age
        or proof.deadline.date() > proof.due
        or proof.deadline.date() > ordinary_deadline
    ):
        _fail("ngram_rights_proof_temporal_invalid")
    return proof.value


def validate_daily_aggregate_rights_proof(value: object, *, target: date) -> dict[str, Any]:
    """Validate the closed proof for the non-identity daily profile."""

    proof = _validate_common_rights_proof(
        value,
        target=target,
        expected_fields=frozenset(DAILY_AGGREGATE_RIGHTS_PROOF_FIELDS),
        expected_uses=DAILY_AGGREGATE_USES,
    )
    document = proof.value
    if document.get("profile_id") != ngram_rights_contract.PROFILE_ID:
        _fail("ngram_rights_proof_binding_invalid")
    recovery_targets = document.get("historical_recovery_targets")
    try:
        expected_recovery_targets = ngram_rights_contract.historical_recovery_targets(
            proof.reviewed
        )
    except ValueError:
        _fail("ngram_rights_recovery_binding_invalid")
    if (
        recovery_targets != expected_recovery_targets
        or document.get("historical_recovery_targets_sha256")
        != ngram_rights_contract.historical_recovery_targets_sha256(
            expected_recovery_targets
        )
    ):
        _fail("ngram_rights_recovery_binding_invalid")
    recovery_used = document.get("recovery_exception_used")
    if not isinstance(recovery_used, bool) or recovery_used != (
        target.isoformat() in expected_recovery_targets and proof.age > proof.max_age
    ):
        _fail("ngram_rights_recovery_binding_invalid")
    revoked_raw = document.get("signer_revoked_on")
    revoked = None if revoked_raw is None else _parse_proof_day(revoked_raw)
    try:
        ordinary_deadline_day = target + timedelta(days=proof.max_age)
    except OverflowError:
        _fail("ngram_rights_proof_temporal_invalid")
    expected_deadline = (
        proof.due if revoked is None else min(proof.due, revoked - timedelta(days=1))
    )
    if recovery_used:
        if proof.deadline.date() != expected_deadline:
            _fail("ngram_rights_proof_temporal_invalid")
    elif proof.age > proof.max_age or proof.deadline.date() != min(
        expected_deadline, ordinary_deadline_day
    ):
        _fail("ngram_rights_proof_temporal_invalid")
    return document


def _is_git_repository(root: Path) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def non_git_test_authority(root: Path) -> NonGitTestRightsAuthority:
    """Freeze synthetic signer identities for one explicit non-Git test root."""

    resolved = root.resolve()
    if resolved == ROOT.resolve() or _is_git_repository(resolved):
        _fail("ngram_test_rights_authority_forbidden")
    signers_path = resolved / "governance/rights_signers.json"
    try:
        raw, document, _ = publication_guard._read_json(signers_path, "rights_signers_unreadable")
        signers = publication_guard._validate_signers(document)
    except publication_guard.PublicationGuardError as exc:
        _fail(exc.code)
    trusted = tuple(
        sorted(
            (
                signer_id,
                str(signer["public_key_ed25519_base64"]),
                str(signer["role"]),
            )
            for signer_id, signer in signers.items()
        )
    )
    return NonGitTestRightsAuthority(
        root=resolved,
        signers_sha256=_sha256(raw),
        trusted_signers=trusted,
    )


def _require_trusted_signer(
    *,
    root: Path,
    signer_id: str,
    signer: dict[str, Any],
    signers_raw: bytes,
    test_authority: NonGitTestRightsAuthority | None,
) -> None:
    key = str(signer.get("public_key_ed25519_base64"))
    role = str(signer.get("role"))
    if test_authority is not None:
        resolved = root.resolve()
        if (
            resolved == ROOT.resolve()
            or _is_git_repository(resolved)
            or test_authority.root != resolved
            or test_authority.signers_sha256 != _sha256(signers_raw)
            or (signer_id, key, role) not in test_authority.trusted_signers
        ):
            _fail("ngram_test_rights_authority_invalid")
        return
    pinned = PRODUCTION_TRUSTED_SIGNERS.get(signer_id)
    if pinned is None or pinned != (key, role):
        _fail("ngram_production_signer_untrusted")
    if role not in PRODUCTION_HUMAN_ROLES:
        _fail("ngram_production_signer_role_invalid")


def _require_rights(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
    required_uses: frozenset[str],
    exact_uses: bool,
    use_error: str,
    required_profile_id: str | None = None,
) -> dict[str, Any]:
    """Require an applicable signed decision before probing or processing."""

    checked_at = _utc_now().astimezone(timezone.utc).replace(microsecond=0)
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
        rights = publication_guard._validate_rights_registry(rights_document, root, signers)
    except publication_guard.PublicationGuardError as exc:
        _fail(exc.code)
    try:
        registry_effective = date.fromisoformat(str(rights_document["effective"]))
        signers_effective = date.fromisoformat(str(signers_document["effective"]))
    except (KeyError, ValueError):
        _fail("rights_effective_date_invalid")
    if registry_effective > decision_day or signers_effective > decision_day:
        _fail("rights_registry_future_dated")
    source = rights.get(SOURCE_ID)
    if source is None:
        _fail("ngram_rights_decision_missing")
    if source.get("decision_state") != "approved":
        _fail(f"ngram_rights_decision_{source.get('decision_state') or 'missing'}")
    try:
        reviewed = date.fromisoformat(str(source["reviewed_on"]))
        due = date.fromisoformat(str(source["review_due"]))
    except (KeyError, ValueError):
        _fail("ngram_rights_dates_invalid")
    if reviewed > decision_day:
        _fail("ngram_rights_decision_future_dated")
    if due < decision_day:
        _fail("ngram_rights_decision_expired")
    signer_id = source.get("signer_id")
    if not isinstance(signer_id, str):
        _fail("ngram_rights_signer_missing")
    signer = signers.get(signer_id)
    if signer is None:
        _fail("ngram_rights_signer_missing")
    _require_trusted_signer(
        root=root,
        signer_id=signer_id,
        signer=signer,
        signers_raw=signers_raw,
        test_authority=test_authority,
    )
    signer_effective = date.fromisoformat(str(signer["effective"]))
    signer_revoked = signer.get("revoked_on")
    if signer_effective > decision_day:
        _fail("ngram_rights_signer_future_dated")
    if signer_revoked is not None and decision_day >= date.fromisoformat(str(signer_revoked)):
        _fail("ngram_rights_signer_revoked")
    uses = source.get("permitted_uses")
    observed_uses = set(uses) if isinstance(uses, list) else set()
    if (
        not isinstance(uses, list)
        or (exact_uses and observed_uses != required_uses)
        or (not exact_uses and not required_uses <= observed_uses)
    ):
        _fail(use_error)
    max_age = source.get("max_current_age_days")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0:
        _fail("ngram_rights_max_age_invalid")
    evaluated_age = (decision_day - target).days
    if evaluated_age < 0:
        _fail("ngram_rights_target_in_future")
    release_deadline_day = min(due, target + timedelta(days=max_age))
    if signer_revoked is not None:
        release_deadline_day = min(
            release_deadline_day,
            date.fromisoformat(str(signer_revoked)) - timedelta(days=1),
        )
    artifact_path = source.get("decision_artifact_path")
    signature_path = source.get("decision_signature_path")
    if not isinstance(artifact_path, str) or not isinstance(signature_path, str):
        _fail("ngram_signed_decision_missing")
    verified_decision = source.get("_verified_decision")
    if not isinstance(verified_decision, dict):
        _fail("ngram_signed_decision_missing")
    if required_profile_id is not None:
        if (
            verified_decision.get("schema_version")
            != ngram_rights_contract.DECISION_SCHEMA_VERSION
            or verified_decision.get("profile_id") != required_profile_id
            or verified_decision.get("official_terms_citation")
            != ngram_rights_contract.OFFICIAL_TERMS_CITATION
        ):
            _fail("ngram_rights_profile_binding_invalid")
    recovery_targets = verified_decision.get("historical_recovery_targets")
    recovery_targets_sha256 = verified_decision.get(
        "historical_recovery_targets_sha256"
    )
    recovery_authorized = (
        required_profile_id is not None
        and isinstance(recovery_targets, list)
        and target.isoformat() in recovery_targets
    )
    if evaluated_age > max_age and not recovery_authorized:
        _fail("ngram_rights_target_too_old")
    if recovery_authorized and evaluated_age > max_age:
        release_deadline_day = due
        if signer_revoked is not None:
            release_deadline_day = min(
                release_deadline_day,
                date.fromisoformat(str(signer_revoked)) - timedelta(days=1),
            )
    proof = {
        "source_id": SOURCE_ID,
        "decision_id": source["decision_id"],
        "signer_id": signer_id,
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "target_date": target.isoformat(),
        "evaluated_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rights_as_of": decision_day.isoformat(),
        "max_current_age_days": max_age,
        "evaluated_age_days": evaluated_age,
        "release_deadline_utc": (f"{release_deadline_day.isoformat()}T23:59:59Z"),
        "permitted_uses": sorted(required_uses),
        "trusted_signer_public_key_sha256": _sha256(
            base64.b64decode(str(signer["public_key_ed25519_base64"]), validate=True)
        ),
        "rights_registry_sha256": _sha256(rights_raw),
        "rights_signers_sha256": _sha256(signers_raw),
        "decision_artifact_path": artifact_path,
        "decision_artifact_sha256": verified_decision["artifact_sha256"],
        "decision_signature_path": signature_path,
        "decision_signature_sha256": verified_decision["signature_sha256"],
    }
    if required_profile_id is not None:
        if (
            not isinstance(recovery_targets, list)
            or not isinstance(recovery_targets_sha256, str)
        ):
            _fail("ngram_rights_recovery_binding_invalid")
        proof.update(
            profile_id=required_profile_id,
            historical_recovery_targets=recovery_targets,
            historical_recovery_targets_sha256=recovery_targets_sha256,
            recovery_exception_used=(evaluated_age > max_age),
            signer_revoked_on=signer_revoked,
        )
    return proof


def require_public_identity_rights(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Require the incumbent four-use identity-retention authorization."""

    return _require_rights(
        target=target,
        root=root,
        test_authority=test_authority,
        required_uses=frozenset(PUBLIC_IDENTITY_USES),
        exact_uses=False,
        use_error="ngram_public_identity_use_not_permitted",
    )


def require_daily_aggregate_rights(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Require exactly the two uses licensed by aggregate profile 2.0.

    Extra permissions are not silently interpreted as approval for this new
    profile: the signed decision must name its deliberately narrow use set.
    Production signer trust remains code-pinned and empty by default.
    """

    return _require_rights(
        target=target,
        root=root,
        test_authority=test_authority,
        required_uses=DAILY_AGGREGATE_USES,
        exact_uses=True,
        use_error="ngram_daily_aggregate_use_not_permitted",
        required_profile_id=ngram_rights_contract.PROFILE_ID,
    )
