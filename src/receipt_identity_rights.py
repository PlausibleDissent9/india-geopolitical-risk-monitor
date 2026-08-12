"""Separate signed authority for the bounded GDELT receipt-identity lane.

The legacy score, NGram cache and receipts have deliberately different rights
needs.  This module therefore accepts only the exact title/link profile and the
exact three-use source decision.  Every evaluation reads each authority object
once, verifies signatures over those captured bytes, and returns their digests.
Production signer trust is empty until a reviewed human transition pins a key.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, Protocol, cast

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
PROFILE_RELATIVE = PurePosixPath("governance/gdelt_receipt_identity_profile.json")
RIGHTS_RELATIVE = PurePosixPath("governance/source_rights_registry.json")
SIGNERS_RELATIVE = PurePosixPath("governance/rights_signers.json")
SOURCE_ID = "gdelt_doc_api"
PROFILE_ID = "gdelt_doc_receipt_identity_v1"
CANONICAL_REQUIRED_USES = (
    "cite_metadata",
    "model_processing",
    "publish_extract",
)
PRODUCTION_HUMAN_ROLES = frozenset({"principal_investigator", "rights_reviewer"})
PRODUCTION_TRUSTED_SIGNERS: dict[str, tuple[str, str]] = {}
DECISION_STATES = frozenset({"approved", "denied", "expired", "review_required"})
PROFILE_STATES = frozenset({"inactive_pending_human_signature", "active"})
AUTHORIZATION_STATUSES = frozenset(
    {
        "authorized",
        "receipt_identity_profile_inactive",
        "receipt_identity_profile_signature_invalid",
        "receipt_identity_profile_signer_missing",
        "receipt_identity_profile_signer_untrusted",
        "receipt_identity_profile_dates_invalid",
        "receipt_identity_source_decision_denied",
        "receipt_identity_source_decision_expired",
        "receipt_identity_source_decision_review_required",
        "receipt_identity_source_decision_missing",
        "receipt_identity_source_decision_future_dated",
        "receipt_identity_source_dates_invalid",
        "receipt_identity_source_use_not_permitted",
        "receipt_identity_source_signer_missing",
        "receipt_identity_source_signer_untrusted",
        "receipt_identity_source_signer_revoked",
        "receipt_identity_source_decision_expired_now",
        "receipt_identity_source_max_age_invalid",
        "receipt_identity_source_terms_mismatch",
        "receipt_identity_source_decision_artifact_invalid",
        "receipt_identity_source_decision_artifact_digest_mismatch",
        "receipt_identity_source_decision_artifact_mismatch",
        "receipt_identity_source_decision_signature_invalid",
        "receipt_identity_rights_registry_future_dated",
        "receipt_identity_target_not_completed_d_minus_1",
        "receipt_identity_target_too_old",
    }
)
SNAPSHOT_FIELDS = frozenset(
    {
        "source_id",
        "profile_id",
        "target_date",
        "evaluated_at_utc",
        "source_decision_state",
        "source_decision_id",
        "profile_activation_state",
        "authorization_status",
        "rights_registry_sha256",
        "rights_signers_sha256",
        "profile_sha256",
    }
)
PROOF_FIELDS = frozenset(
    {
        "source_id",
        "profile_id",
        "decision_id",
        "source_signer_id",
        "source_signer_revoked_on",
        "profile_signer_id",
        "profile_signer_revoked_on",
        "reviewed_on",
        "review_due",
        "profile_reviewed_on",
        "profile_review_due",
        "target_date",
        "evaluated_at_utc",
        "rights_as_of",
        "max_current_age_days",
        "evaluated_age_days",
        "release_deadline_utc",
        "permitted_uses",
        "rights_registry_sha256",
        "rights_signers_sha256",
        "decision_artifact_path",
        "decision_artifact_sha256",
        "decision_signature_path",
        "decision_signature_sha256",
        "profile_sha256",
        "profile_signature_path",
        "profile_signature_sha256",
        "profile_schema_sha256",
        "dictionary_sha256",
        "output_schema_sha256",
        "source_signer_public_key_sha256",
        "profile_signer_public_key_sha256",
    }
)
_STABLE_PROOF_FIELDS = PROOF_FIELDS - {
    "evaluated_at_utc",
    "rights_as_of",
    "evaluated_age_days",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")


@dataclass(frozen=True)
class NonGitTestRightsAuthority:
    """Explicit signer trust frozen from one non-Git synthetic fixture."""

    root: Path
    signers_sha256: str
    trusted_signers: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True)
class ProfileIdentity:
    """Non-authorizing profile identity safe for an inactive status payload."""

    profile_id: str
    profile_sha256: str
    activation_state: str
    output_path: str
    schema_path: str
    schema_sha256: str
    dictionary_path: str
    dictionary_sha256: str


class ReceiptIdentityRightsError(RuntimeError):
    """Stable refusal before any GDELT request or public value release."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ReceiptIdentityRightsError(code)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("receipt_identity_json_duplicate_key")
        result[key] = value
    return result


def _parse_object(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: _fail("receipt_identity_json_non_finite"),
        )
    except ReceiptIdentityRightsError:
        raise
    except (UnicodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


class AuthorityReader(Protocol):
    """Read one repository-relative authority object into immutable bytes."""

    def read(self, value: object, code: str) -> tuple[str, bytes]: ...


def _path_text(value: object, code: str) -> tuple[str, PurePosixPath]:
    text = _text(value, code)
    posix = PurePosixPath(text)
    if (
        posix.is_absolute()
        or ".." in posix.parts
        or "." in posix.parts
        or "\\" in text
        or str(posix) != text
    ):
        _fail(code)
    return text, posix


class WorktreeAuthorityReader:
    """Capture each regular worktree file once and never reopen it."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.cache: dict[str, bytes] = {}

    def read(self, value: object, code: str) -> tuple[str, bytes]:
        text, posix = _path_text(value, code)
        if text in self.cache:
            return text, self.cache[text]
        current = self.root
        for part in posix.parts:
            current = current / part
            if current.is_symlink():
                _fail(code)
        try:
            resolved = current.resolve(strict=True)
            resolved.relative_to(self.root)
            if not resolved.is_file():
                _fail(code)
            raw = resolved.read_bytes()
        except (OSError, ValueError):
            _fail(code)
        self.cache[text] = raw
        return text, raw


class CandidateAuthorityReader:
    """Capture exact 100644 blobs from one immutable Git candidate tree."""

    def __init__(self, root: Path, candidate_sha: str) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", candidate_sha) is None:
            _fail("receipt_identity_release_candidate_invalid")
        self.root = root
        self.candidate_sha = candidate_sha
        self.cache: dict[str, bytes] = {}

    def read(self, value: object, code: str) -> tuple[str, bytes]:
        text, _ = _path_text(value, code)
        if text in self.cache:
            return text, self.cache[text]
        tree = subprocess.run(
            ["git", "ls-tree", "-z", self.candidate_sha, "--", text],
            cwd=self.root,
            capture_output=True,
        )
        match = re.fullmatch(
            rb"100644 blob ([0-9a-f]{40})\t" + re.escape(text.encode()) + rb"\x00",
            tree.stdout,
        )
        if tree.returncode != 0 or match is None:
            _fail(code)
        expected_blob = match.group(1).decode("ascii")
        blob = subprocess.run(
            ["git", "cat-file", "blob", f"{self.candidate_sha}:{text}"],
            cwd=self.root,
            capture_output=True,
        )
        if blob.returncode != 0:
            _fail(code)
        raw = blob.stdout
        actual_blob = hashlib.sha1(  # noqa: S324 - Git SHA-1 object identity
            b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw,
            usedforsecurity=False,
        ).hexdigest()
        if actual_blob != expected_blob:
            _fail(code)
        self.cache[text] = raw
        return text, raw


def _strict_object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail(code)
    return value


def _day(value: object, code: str) -> date:
    text = _text(value, code)
    try:
        result = date.fromisoformat(text)
    except ValueError:
        _fail(code)
    if result.isoformat() != text:
        _fail(code)
    return result


def _utc_second(value: object, code: str) -> datetime:
    text = _text(value, code)
    if not text.endswith("Z"):
        _fail(code)
    try:
        result = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if (
        result.utcoffset() != timedelta(0)
        or result.microsecond != 0
        or result.strftime("%Y-%m-%dT%H:%M:%SZ") != text
    ):
        _fail(code)
    return result


def _digest(value: object, code: str) -> str:
    text = _text(value, code)
    if _SHA256.fullmatch(text) is None:
        _fail(code)
    return text


def _is_git_repository(root: Path) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )


def non_git_test_authority(root: Path) -> NonGitTestRightsAuthority:
    resolved = root.resolve()
    if resolved == ROOT.resolve() or _is_git_repository(resolved):
        _fail("receipt_identity_test_authority_forbidden")
    reader = WorktreeAuthorityReader(resolved)
    _, raw = reader.read(
        SIGNERS_RELATIVE.as_posix(), "receipt_identity_signers_unreadable"
    )
    document = _parse_object(raw, "receipt_identity_signers_unreadable")
    signers = _validate_signers(document)
    trusted = tuple(
        sorted(
            (
                signer_id,
                cast(str, signer["public_key_ed25519_base64"]),
                cast(str, signer["role"]),
            )
            for signer_id, signer in signers.items()
        )
    )
    return NonGitTestRightsAuthority(resolved, _sha256(raw), trusted)


def _validate_signers(document: object) -> dict[str, dict[str, Any]]:
    top = _strict_object(
        document,
        {"schema_version", "effective", "default_policy", "signers"},
        "receipt_identity_signers_invalid",
    )
    if top["schema_version"] != "1.0.0" or top["default_policy"] != "deny":
        _fail("receipt_identity_signers_invalid")
    _day(top["effective"], "receipt_identity_signers_invalid")
    if not isinstance(top["signers"], list):
        _fail("receipt_identity_signers_invalid")
    expected = {
        "signer_id",
        "name",
        "role",
        "public_key_ed25519_base64",
        "effective",
        "revoked_on",
    }
    result: dict[str, dict[str, Any]] = {}
    for raw in top["signers"]:
        signer = _strict_object(raw, expected, "receipt_identity_signer_invalid")
        signer_id = _text(signer["signer_id"], "receipt_identity_signer_invalid")
        if _ID.fullmatch(signer_id) is None or signer_id in result:
            _fail("receipt_identity_signer_invalid")
        _text(signer["name"], "receipt_identity_signer_invalid")
        _text(signer["role"], "receipt_identity_signer_invalid")
        try:
            key = base64.b64decode(
                _text(
                    signer["public_key_ed25519_base64"],
                    "receipt_identity_signer_invalid",
                ),
                validate=True,
            )
            Ed25519PublicKey.from_public_bytes(key)
        except (binascii.Error, ValueError):
            _fail("receipt_identity_signer_invalid")
        effective = _day(signer["effective"], "receipt_identity_signer_invalid")
        revoked_raw = signer["revoked_on"]
        if revoked_raw is not None:
            revoked = _day(revoked_raw, "receipt_identity_signer_invalid")
            if revoked <= effective:
                _fail("receipt_identity_signer_invalid")
        result[signer_id] = signer
    return result


def _require_trusted_signer(
    *,
    root: Path,
    signer_id: str,
    signer: dict[str, Any],
    signers_raw: bytes,
    test_authority: NonGitTestRightsAuthority | None,
    code: str,
) -> None:
    key = cast(str, signer["public_key_ed25519_base64"])
    role = cast(str, signer["role"])
    if role not in PRODUCTION_HUMAN_ROLES:
        _fail(code)
    if test_authority is not None:
        if (
            root.resolve() == ROOT.resolve()
            or _is_git_repository(root.resolve())
            or test_authority.root != root.resolve()
            or test_authority.signers_sha256 != _sha256(signers_raw)
            or (signer_id, key, role) not in test_authority.trusted_signers
        ):
            _fail("receipt_identity_test_authority_invalid")
        return
    if PRODUCTION_TRUSTED_SIGNERS.get(signer_id) != (key, role):
        _fail(code)


def _verify_signature(raw: bytes, signature: bytes, signer: dict[str, Any], code: str) -> None:
    if len(signature) != 64:
        _fail(code)
    try:
        public_key = base64.b64decode(
            cast(str, signer["public_key_ed25519_base64"]), validate=True
        )
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, raw)
    except (binascii.Error, InvalidSignature, ValueError):
        _fail(code)


def _load_profile(
    reader: AuthorityReader,
) -> tuple[bytes, dict[str, Any], ProfileIdentity]:
    _, raw = reader.read(PROFILE_RELATIVE.as_posix(), "receipt_identity_profile_unreadable")
    document = _parse_object(raw, "receipt_identity_profile_unreadable")
    schema_binding = document.get("profile_schema")
    if not isinstance(schema_binding, dict):
        _fail("receipt_identity_profile_schema_invalid")
    schema_path, schema_raw = reader.read(
        schema_binding.get("path"),
        "receipt_identity_profile_schema_invalid",
    )
    schema = _parse_object(schema_raw, "receipt_identity_profile_schema_invalid")
    if _sha256(schema_raw) != schema_binding.get("sha256"):
        _fail("receipt_identity_profile_schema_digest_mismatch")
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    except Exception as exc:  # jsonschema exposes several validation subclasses
        raise ReceiptIdentityRightsError("receipt_identity_profile_invalid") from exc
    if document.get("profile_id") != PROFILE_ID:
        _fail("receipt_identity_profile_invalid")
    channels = cast(dict[str, Any], document["channels"])
    dictionary = cast(dict[str, Any], channels["dictionary"])
    dictionary_path, dictionary_raw = reader.read(
        dictionary["path"], "receipt_identity_dictionary_invalid"
    )
    if _sha256(dictionary_raw) != dictionary["sha256"]:
        _fail("receipt_identity_dictionary_digest_mismatch")
    output = cast(dict[str, Any], document["output"])
    output_schema = cast(dict[str, Any], output["schema"])
    output_schema_path, output_schema_raw = reader.read(
        output_schema["path"], "receipt_identity_output_schema_invalid"
    )
    if _sha256(output_schema_raw) != output_schema["sha256"]:
        _fail("receipt_identity_output_schema_digest_mismatch")
    activation = cast(dict[str, Any], document["activation"])
    identity = ProfileIdentity(
        profile_id=PROFILE_ID,
        profile_sha256=_sha256(raw),
        activation_state=cast(str, activation["state"]),
        output_path=cast(str, output["path"]),
        schema_path=cast(str, output_schema["path"]),
        schema_sha256=cast(str, output_schema["sha256"]),
        dictionary_path=cast(str, dictionary["path"]),
        dictionary_sha256=cast(str, dictionary["sha256"]),
    )
    return raw, document, identity


def load_profile_identity(root: Path = ROOT) -> ProfileIdentity:
    """Validate the closed profile and return its non-authorizing identity."""

    return _load_profile(WorktreeAuthorityReader(root))[2]


def load_profile_configuration(
    root: Path = ROOT,
) -> tuple[ProfileIdentity, dict[str, Any]]:
    """Return one captured, validated worktree profile configuration."""

    _, document, identity = _load_profile(WorktreeAuthorityReader(root))
    return identity, document


def load_candidate_profile_configuration(
    *, root: Path, candidate_sha: str
) -> tuple[ProfileIdentity, dict[str, Any], CandidateAuthorityReader]:
    """Return the profile and reader bound to exact candidate 100644 blobs."""

    reader = CandidateAuthorityReader(root, candidate_sha)
    _, document, identity = _load_profile(reader)
    return identity, document, reader


def _source_row(document: object) -> tuple[dict[str, Any], str]:
    top = _strict_object(
        document,
        {"schema_version", "effective", "default_policy", "sources"},
        "receipt_identity_rights_registry_invalid",
    )
    if top["schema_version"] != "1.0.0" or top["default_policy"] != "deny":
        _fail("receipt_identity_rights_registry_invalid")
    effective = _day(top["effective"], "receipt_identity_rights_registry_invalid")
    if not isinstance(top["sources"], list):
        _fail("receipt_identity_rights_registry_invalid")
    matches = [
        row
        for row in top["sources"]
        if isinstance(row, dict) and row.get("source_id") == SOURCE_ID
    ]
    if len(matches) != 1:
        _fail("receipt_identity_source_decision_missing")
    return cast(dict[str, Any], matches[0]), effective.isoformat()


def _revocation_day(signer: dict[str, Any]) -> date | None:
    raw = signer.get("revoked_on")
    return None if raw is None else _day(raw, "receipt_identity_signer_invalid")


def _evaluate_loaded(
    *,
    target: date,
    checked_at: datetime,
    root: Path,
    profile_raw: bytes,
    profile: dict[str, Any],
    profile_identity: ProfileIdentity,
    rights_raw: bytes,
    rights_document: dict[str, Any],
    signers_raw: bytes,
    signers_document: dict[str, Any],
    reader: AuthorityReader,
    test_authority: NonGitTestRightsAuthority | None,
) -> dict[str, Any]:
    decision_day = checked_at.date()
    if target >= decision_day:
        _fail("receipt_identity_target_not_completed_d_minus_1")
    signers = _validate_signers(signers_document)
    source, registry_effective = _source_row(rights_document)
    if _day(registry_effective, "receipt_identity_rights_registry_invalid") > decision_day:
        _fail("receipt_identity_rights_registry_future_dated")
    if _day(signers_document["effective"], "receipt_identity_signers_invalid") > decision_day:
        _fail("receipt_identity_rights_registry_future_dated")
    state = source.get("decision_state")
    if state != "approved":
        _fail(f"receipt_identity_source_decision_{state or 'missing'}")
    uses = source.get("permitted_uses")
    if uses != list(CANONICAL_REQUIRED_USES):
        _fail("receipt_identity_source_use_not_permitted")
    reviewed = _day(source.get("reviewed_on"), "receipt_identity_source_dates_invalid")
    due = _day(source.get("review_due"), "receipt_identity_source_dates_invalid")
    if reviewed > decision_day:
        _fail("receipt_identity_source_decision_future_dated")
    if due < decision_day:
        _fail("receipt_identity_source_decision_expired_now")
    max_age = source.get("max_current_age_days")
    age = (decision_day - target).days
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 0:
        _fail("receipt_identity_source_max_age_invalid")
    if age < 1 or age > max_age:
        _fail("receipt_identity_target_too_old")
    if source.get("terms_url") != "https://www.gdeltproject.org/about.html":
        _fail("receipt_identity_source_terms_mismatch")

    source_signer_id = source.get("signer_id")
    if not isinstance(source_signer_id, str) or source_signer_id not in signers:
        _fail("receipt_identity_source_signer_missing")
    source_signer = signers[source_signer_id]
    _require_trusted_signer(
        root=root,
        signer_id=source_signer_id,
        signer=source_signer,
        signers_raw=signers_raw,
        test_authority=test_authority,
        code="receipt_identity_source_signer_untrusted",
    )
    source_revoked = _revocation_day(source_signer)
    if _day(source_signer["effective"], "receipt_identity_signer_invalid") > reviewed:
        _fail("receipt_identity_source_signer_untrusted")
    if source_revoked is not None and decision_day >= source_revoked:
        _fail("receipt_identity_source_signer_revoked")
    artifact_path, artifact_raw = reader.read(
        source.get("decision_artifact_path"),
        "receipt_identity_source_decision_artifact_invalid",
    )
    artifact = _parse_object(
        artifact_raw, "receipt_identity_source_decision_artifact_invalid"
    )
    artifact_sha = _sha256(artifact_raw)
    if artifact_sha != source.get("decision_artifact_sha256"):
        _fail("receipt_identity_source_decision_artifact_digest_mismatch")
    signature_path, signature_raw = reader.read(
        source.get("decision_signature_path"),
        "receipt_identity_source_decision_signature_invalid",
    )
    _verify_signature(
        artifact_raw,
        signature_raw,
        source_signer,
        "receipt_identity_source_decision_signature_invalid",
    )
    matching = {
        "source_id",
        "name",
        "provider",
        "role",
        "authority_class",
        "decision_state",
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
    }
    if artifact.get("schema_version") != "1.0.0" or any(
        artifact.get(field) != source.get(field) for field in matching
    ):
        _fail("receipt_identity_source_decision_artifact_mismatch")

    activation = cast(dict[str, Any], profile["activation"])
    if activation.get("state") != "active":
        _fail("receipt_identity_profile_inactive")
    profile_signer_id = activation.get("signer_id")
    if not isinstance(profile_signer_id, str) or profile_signer_id not in signers:
        _fail("receipt_identity_profile_signer_missing")
    profile_signer = signers[profile_signer_id]
    _require_trusted_signer(
        root=root,
        signer_id=profile_signer_id,
        signer=profile_signer,
        signers_raw=signers_raw,
        test_authority=test_authority,
        code="receipt_identity_profile_signer_untrusted",
    )
    profile_revoked = _revocation_day(profile_signer)
    profile_reviewed = _day(
        activation.get("reviewed_on"), "receipt_identity_profile_dates_invalid"
    )
    profile_due = _day(
        activation.get("review_due"), "receipt_identity_profile_dates_invalid"
    )
    if (
        profile_reviewed > decision_day
        or profile_due < decision_day
        or _day(profile_signer["effective"], "receipt_identity_signer_invalid")
        > profile_reviewed
        or (profile_revoked is not None and decision_day >= profile_revoked)
    ):
        _fail("receipt_identity_profile_signer_untrusted")
    profile_signature_path, profile_signature_raw = reader.read(
        activation.get("signature_path"),
        "receipt_identity_profile_signature_invalid",
    )
    _verify_signature(
        profile_raw,
        profile_signature_raw,
        profile_signer,
        "receipt_identity_profile_signature_invalid",
    )

    deadline = min(due, profile_due, target + timedelta(days=max_age))
    for revoked in (source_revoked, profile_revoked):
        if revoked is not None:
            deadline = min(deadline, revoked - timedelta(days=1))
    schema = cast(dict[str, Any], profile["profile_schema"])
    channels = cast(dict[str, Any], profile["channels"])
    dictionary = cast(dict[str, Any], channels["dictionary"])
    output = cast(dict[str, Any], profile["output"])
    output_schema = cast(dict[str, Any], output["schema"])
    return {
        "source_id": SOURCE_ID,
        "profile_id": PROFILE_ID,
        "decision_id": source["decision_id"],
        "source_signer_id": source_signer_id,
        "source_signer_revoked_on": (
            source_revoked.isoformat() if source_revoked is not None else None
        ),
        "profile_signer_id": profile_signer_id,
        "profile_signer_revoked_on": (
            profile_revoked.isoformat() if profile_revoked is not None else None
        ),
        "reviewed_on": reviewed.isoformat(),
        "review_due": due.isoformat(),
        "profile_reviewed_on": profile_reviewed.isoformat(),
        "profile_review_due": profile_due.isoformat(),
        "target_date": target.isoformat(),
        "evaluated_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rights_as_of": decision_day.isoformat(),
        "max_current_age_days": max_age,
        "evaluated_age_days": age,
        "release_deadline_utc": f"{deadline.isoformat()}T23:59:59Z",
        "permitted_uses": list(CANONICAL_REQUIRED_USES),
        "rights_registry_sha256": _sha256(rights_raw),
        "rights_signers_sha256": _sha256(signers_raw),
        "decision_artifact_path": source["decision_artifact_path"],
        "decision_artifact_sha256": artifact_sha,
        "decision_signature_path": source["decision_signature_path"],
        "decision_signature_sha256": _sha256(signature_raw),
        "profile_sha256": profile_identity.profile_sha256,
        "profile_signature_path": activation["signature_path"],
        "profile_signature_sha256": _sha256(profile_signature_raw),
        "profile_schema_sha256": schema["sha256"],
        "dictionary_sha256": dictionary["sha256"],
        "output_schema_sha256": output_schema["sha256"],
        "source_signer_public_key_sha256": _sha256(
            base64.b64decode(
                cast(str, source_signer["public_key_ed25519_base64"]), validate=True
            )
        ),
        "profile_signer_public_key_sha256": _sha256(
            base64.b64decode(
                cast(str, profile_signer["public_key_ed25519_base64"]), validate=True
            )
        ),
    }


def evaluate_authority(
    *,
    target: date,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return a value-free snapshot plus an exact proof when authorized."""

    reader = WorktreeAuthorityReader(root)
    return _evaluate_with_reader(
        target=target,
        root=root,
        reader=reader,
        test_authority=test_authority,
    )


def evaluate_candidate_authority(
    *,
    target: date,
    candidate_sha: str,
    root: Path = ROOT,
    test_authority: NonGitTestRightsAuthority | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Evaluate only exact regular blobs from an immutable candidate tree."""

    return _evaluate_with_reader(
        target=target,
        root=root,
        reader=CandidateAuthorityReader(root, candidate_sha),
        test_authority=test_authority,
    )


def _evaluate_with_reader(
    *,
    target: date,
    root: Path,
    reader: AuthorityReader,
    test_authority: NonGitTestRightsAuthority | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    checked_at = _utc_now().astimezone(timezone.utc).replace(microsecond=0)
    profile_raw, profile, identity = _load_profile(reader)
    _, rights_raw = reader.read(
        RIGHTS_RELATIVE.as_posix(), "receipt_identity_rights_registry_unreadable"
    )
    rights_document = _parse_object(
        rights_raw, "receipt_identity_rights_registry_unreadable"
    )
    _, signers_raw = reader.read(
        SIGNERS_RELATIVE.as_posix(), "receipt_identity_signers_unreadable"
    )
    signers_document = _parse_object(signers_raw, "receipt_identity_signers_unreadable")
    source, _ = _source_row(rights_document)
    try:
        proof = _evaluate_loaded(
            target=target,
            checked_at=checked_at,
            root=root,
            profile_raw=profile_raw,
            profile=profile,
            profile_identity=identity,
            rights_raw=rights_raw,
            rights_document=rights_document,
            signers_raw=signers_raw,
            signers_document=signers_document,
            reader=reader,
            test_authority=test_authority,
        )
        status = "authorized"
    except ReceiptIdentityRightsError as exc:
        proof = None
        status = exc.code
    snapshot = {
        "source_id": SOURCE_ID,
        "profile_id": PROFILE_ID,
        "target_date": target.isoformat(),
        "evaluated_at_utc": checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_decision_state": source.get("decision_state"),
        "source_decision_id": source.get("decision_id"),
        "profile_activation_state": identity.activation_state,
        "authorization_status": status,
        "rights_registry_sha256": _sha256(rights_raw),
        "rights_signers_sha256": _sha256(signers_raw),
        "profile_sha256": identity.profile_sha256,
    }
    validate_snapshot(snapshot, target=target)
    return snapshot, proof


def validate_snapshot(value: object, *, target: date) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SNAPSHOT_FIELDS:
        _fail("receipt_identity_rights_snapshot_fields_invalid")
    if (
        value.get("source_id") != SOURCE_ID
        or value.get("profile_id") != PROFILE_ID
        or value.get("target_date") != target.isoformat()
        or value.get("source_decision_state") not in DECISION_STATES
        or value.get("profile_activation_state") not in PROFILE_STATES
        or value.get("authorization_status") not in AUTHORIZATION_STATUSES
    ):
        _fail("receipt_identity_rights_snapshot_binding_invalid")
    _utc_second(value.get("evaluated_at_utc"), "receipt_identity_rights_snapshot_invalid")
    _text(value.get("source_decision_id"), "receipt_identity_rights_snapshot_invalid")
    for field in ("rights_registry_sha256", "rights_signers_sha256", "profile_sha256"):
        _digest(value.get(field), "receipt_identity_rights_snapshot_invalid")
    return dict(value)


def validate_proof(value: object, *, target: date) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROOF_FIELDS:
        _fail("receipt_identity_rights_proof_fields_invalid")
    if (
        value.get("source_id") != SOURCE_ID
        or value.get("profile_id") != PROFILE_ID
        or value.get("target_date") != target.isoformat()
        or value.get("permitted_uses") != list(CANONICAL_REQUIRED_USES)
    ):
        _fail("receipt_identity_rights_proof_binding_invalid")
    reviewed = _day(value.get("reviewed_on"), "receipt_identity_rights_proof_invalid")
    due = _day(value.get("review_due"), "receipt_identity_rights_proof_invalid")
    profile_reviewed = _day(
        value.get("profile_reviewed_on"), "receipt_identity_rights_proof_invalid"
    )
    profile_due = _day(
        value.get("profile_review_due"), "receipt_identity_rights_proof_invalid"
    )
    as_of = _day(value.get("rights_as_of"), "receipt_identity_rights_proof_invalid")
    evaluated = _utc_second(
        value.get("evaluated_at_utc"), "receipt_identity_rights_proof_invalid"
    )
    deadline = _utc_second(
        value.get("release_deadline_utc"), "receipt_identity_rights_proof_invalid"
    )
    max_age = value.get("max_current_age_days")
    age = value.get("evaluated_age_days")
    source_revoked = value.get("source_signer_revoked_on")
    profile_revoked = value.get("profile_signer_revoked_on")
    revocations = [
        _day(item, "receipt_identity_rights_proof_invalid")
        for item in (source_revoked, profile_revoked)
        if item is not None
    ]
    expected_deadline = min(
        due,
        profile_due,
        target + timedelta(days=max_age),
        *[revoked - timedelta(days=1) for revoked in revocations],
    ) if isinstance(max_age, int) and not isinstance(max_age, bool) else date.min
    if (
        evaluated.date() != as_of
        or target >= as_of
        or isinstance(max_age, bool)
        or not isinstance(max_age, int)
        or max_age < 0
        or isinstance(age, bool)
        or not isinstance(age, int)
        or age != (as_of - target).days
        or age < 1
        or age > max_age
        or reviewed > as_of
        or profile_reviewed > as_of
        or due < as_of
        or profile_due < as_of
        or any(as_of >= revoked for revoked in revocations)
        or deadline.time() != datetime.max.time().replace(microsecond=0)
        or deadline.date() != expected_deadline
        or evaluated > deadline
    ):
        _fail("receipt_identity_rights_proof_temporal_invalid")
    for field in (
        "decision_id",
        "source_signer_id",
        "profile_signer_id",
        "decision_artifact_path",
        "decision_signature_path",
        "profile_signature_path",
    ):
        _text(value.get(field), "receipt_identity_rights_proof_binding_invalid")
    for field in (
        "rights_registry_sha256",
        "rights_signers_sha256",
        "decision_artifact_sha256",
        "decision_signature_sha256",
        "profile_sha256",
        "profile_signature_sha256",
        "profile_schema_sha256",
        "dictionary_sha256",
        "output_schema_sha256",
        "source_signer_public_key_sha256",
        "profile_signer_public_key_sha256",
    ):
        _digest(value.get(field), "receipt_identity_rights_proof_binding_invalid")
    return dict(value)


def require_compatible_evaluations(
    proofs: list[dict[str, Any]], *, target: date
) -> list[dict[str, Any]]:
    if not proofs:
        _fail("receipt_identity_rights_evaluations_empty")
    checked = [validate_proof(proof, target=target) for proof in proofs]
    baseline = {field: checked[0][field] for field in _STABLE_PROOF_FIELDS}
    previous = _utc_second(
        checked[0]["evaluated_at_utc"], "receipt_identity_rights_proof_invalid"
    )
    for proof in checked[1:]:
        current = _utc_second(
            proof["evaluated_at_utc"], "receipt_identity_rights_proof_invalid"
        )
        if current < previous:
            _fail("receipt_identity_rights_evaluation_order_invalid")
        if any(proof[field] != baseline[field] for field in _STABLE_PROOF_FIELDS):
            _fail("receipt_identity_rights_authority_drift")
        previous = current
    return checked
