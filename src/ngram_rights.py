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

from . import publication_guard

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "gdelt_web_ngrams_v5"
PUBLIC_IDENTITY_USES = {
    "model_processing",
    "publish_derived_value",
    "publish_extract",
    "redistribute_full_record",
}
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
PRODUCTION_HUMAN_ROLES = frozenset(
    {"principal_investigator", "rights_reviewer"}
)
# Production is intentionally empty-by-default. An actual authorization must
# add the exact human signer ID, Ed25519 public key and closed role here in a
# reviewed code transition as well as in the signed governance registries.
# Merely adding a self-generated key to mutable repository JSON is not trust.
PRODUCTION_TRUSTED_SIGNERS: dict[str, tuple[str, str]] = {}


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


def validate_public_identity_rights_proof(
    value: object, *, target: date
) -> dict[str, Any]:
    """Validate the complete closed proof emitted by the rights authority."""

    if not isinstance(value, dict) or set(value) != (
        PUBLIC_IDENTITY_RIGHTS_PROOF_FIELDS
    ):
        _fail("ngram_rights_proof_fields_invalid")
    if (
        value.get("source_id") != SOURCE_ID
        or value.get("target_date") != target.isoformat()
        or value.get("permitted_uses") != sorted(PUBLIC_IDENTITY_USES)
    ):
        _fail("ngram_rights_proof_binding_invalid")
    try:
        reviewed = date.fromisoformat(str(value["reviewed_on"]))
        due = date.fromisoformat(str(value["review_due"]))
        as_of = date.fromisoformat(str(value["rights_as_of"]))
    except ValueError:
        _fail("ngram_rights_proof_date_invalid")
    evaluated_at = _parse_utc_second(value["evaluated_at_utc"])
    deadline = _parse_utc_second(value["release_deadline_utc"])
    max_age = value.get("max_current_age_days")
    age = value.get("evaluated_age_days")
    expected_age = (as_of - target).days
    if (
        evaluated_at.date() != as_of
        or isinstance(max_age, bool)
        or not isinstance(max_age, int)
        or max_age < 0
        or isinstance(age, bool)
        or not isinstance(age, int)
        or age != expected_age
        or age < 0
        or age > max_age
        or reviewed > as_of
        or due < as_of
        or deadline.time() != datetime.max.time().replace(microsecond=0)
        or deadline.date() < target
        or deadline.date() > due
        or deadline.date() > target + timedelta(days=max_age)
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
        if not isinstance(digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", digest
        ):
            _fail("ngram_rights_proof_binding_invalid")
    return dict(value)


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
        raw, document, _ = publication_guard._read_json(
            signers_path, "rights_signers_unreadable"
        )
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


def require_public_identity_rights(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
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
        rights = publication_guard._validate_rights_registry(
            rights_document, root, signers
        )
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
    if signer_revoked is not None and decision_day >= date.fromisoformat(
        str(signer_revoked)
    ):
        _fail("ngram_rights_signer_revoked")
    uses = source.get("permitted_uses")
    if not isinstance(uses, list) or not PUBLIC_IDENTITY_USES <= set(uses):
        _fail("ngram_public_identity_use_not_permitted")
    max_age = source.get("max_current_age_days")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0:
        _fail("ngram_rights_max_age_invalid")
    evaluated_age = (decision_day - target).days
    if evaluated_age < 0:
        _fail("ngram_rights_target_in_future")
    if evaluated_age > max_age:
        _fail("ngram_rights_target_too_old")
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
    return {
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
        "release_deadline_utc": (
            f"{release_deadline_day.isoformat()}T23:59:59Z"
        ),
        "permitted_uses": sorted(PUBLIC_IDENTITY_USES),
        "trusted_signer_public_key_sha256": _sha256(
            base64.b64decode(
                str(signer["public_key_ed25519_base64"]), validate=True
            )
        ),
        "rights_registry_sha256": _sha256(rights_raw),
        "rights_signers_sha256": _sha256(signers_raw),
        "decision_artifact_path": artifact_path,
        "decision_artifact_sha256": source["decision_artifact_sha256"],
        "decision_signature_path": signature_path,
        "decision_signature_sha256": _sha256((root / signature_path).read_bytes()),
    }
