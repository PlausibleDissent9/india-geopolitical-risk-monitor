"""Fail-closed construction of one finalized D-1 publication candidate.

The daily score store is append-only at the publication boundary.  Acquisition
may inspect an untrusted target-day frame, but it may not write that frame, a
calibrated value, or provenance into the canonical stores until the existing
prospective production-frame validator accepts the exact bytes as 48/48.

This module deliberately publishes a separate, value-free operational state.
A source refusal can therefore be visible without turning a provisional
nowcast into a final score or banking an unvalidated target-day value.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn

from . import fetch_ngrams, precision_frame_v3, provenance, publication_guard

ROOT = Path(__file__).resolve().parents[1]
STATUS_RELATIVE = Path("data/raw/final_publication_status.json")
RECEIPTS_RELATIVE = Path("data/raw/final_publication_receipts")

_LEGACY_AUG9_DAY = date(2026, 8, 9)
_LEGACY_AUG9_INTRODUCTION = "9077ea4f27b4662ed6651828ee28183eed8fc727"
_LEGACY_AUG9_BLOBS = {
    "data/raw/ngram_days/2026-08-09.json": (
        "1d14bd7e4e2151b77709857fc184d65569b6703942c2763777aa89f816f4250b"
    ),
    "data/raw/gdelt_volume.csv": (
        "ad4766d872ca5ed95b8d1efe729480016e46040816be21ad32d02cc9984eb065"
    ),
    "data/raw/provenance.csv": (
        "940281c3e0c2f898dc246f41e2f0dbe42cb690ed1f2c2968fb0676cd5b0e9ad1"
    ),
    "data/raw/ngram_calibration.json": (
        "02efb5a493878701f1890802133ee395e6e1775028c33f8986b0043235e87c2e"
    ),
    "dictionaries.json": (
        "4f5d3333cad6d7b708c3b7d855f5fcc636b0ef2243f56f8e58def9f754d99b40"
    ),
    "src/fetch_ngrams.py": (
        "0cbf9e9837e5d6bb51ddb558a4cd3397953907e9a4ba44133292fd7441629e39"
    ),
    "docs/data/latest.json": (
        "2af2170bd58fbcf98d4285124f2fede5d6a5d01628cc8674eaf4055acb37e049"
    ),
    "docs/data/history.json": (
        "672d240e167ee95f3363395445cdf4ab98a0dcf5d89c5071f65d85d12329bdfe"
    ),
}
_LEGACY_AUG9_HISTORICAL_ONLY_PATHS = {"src/fetch_ngrams.py"}
_NGRAM_RIGHTS_SOURCE_ID = "gdelt_web_ngrams_v5"
_NGRAM_PUBLIC_IDENTITY_USES = {
    "model_processing",
    "publish_derived_value",
    "publish_extract",
    "redistribute_full_record",
}

_PUBLIC_STATES = {
    "already_finalized",
    "source_unavailable",
    "acquisition_failed",
    "pipeline_failed",
    "target_ready",
    "finalized",
    "legacy_proof_limited",
}


class FinalPublicationError(RuntimeError):
    """Stable typed refusal from the finalized-publication boundary."""

    def __init__(self, classification: str, detail: str = "") -> None:
        super().__init__(classification)
        self.classification = classification
        self.detail = detail


@dataclass(frozen=True)
class NonGitTestTrustRoot:
    """Explicit immutable parent bytes for a non-git unit-test fixture.

    Production callers cannot use this escape hatch: resolution rejects it
    whenever ``root`` has a Git HEAD or is the canonical repository.
    """

    commit: str
    store: bytes
    provenance: bytes
    calibration: bytes
    dictionaries: bytes
    matcher: bytes
    rights_registry: bytes
    rights_signers: bytes
    rights_decision_files: dict[str, bytes]


@dataclass(frozen=True)
class _ParentSnapshot:
    commit: str
    store: bytes
    provenance: bytes
    calibration: bytes
    dictionaries: bytes
    matcher: bytes
    rights_registry: bytes
    rights_signers: bytes
    rights_decision_files: dict[str, bytes]


def _fail(classification: str, detail: str = "") -> NoReturn:
    raise FinalPublicationError(classification, detail)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def required_target(today: date | None = None) -> date:
    return (today or utc_today()) - timedelta(days=1)


def require_exact_target(target: date, today: date | None = None) -> None:
    expected = required_target(today)
    if target != expected:
        _fail(
            "target_not_d_minus_one",
            f"target={target.isoformat()} expected={expected.isoformat()}",
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def _generated() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_head(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and len(value) == 40 else None


def _git_commit(root: Path, ref: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        _fail("promotion_trust_invalid", f"unresolvable_git_parent:{ref}")
    return value


def _git_blob(root: Path, commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=root,
        capture_output=True,
    )
    if result.returncode != 0:
        _fail("promotion_trust_invalid", f"parent_blob_missing:{relative}")
    return result.stdout


def _rights_decision_paths(registry_raw: bytes) -> list[str]:
    try:
        registry = json.loads(registry_raw)
        sources = registry.get("sources")
    except (UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(sources, list):
        return []
    for source in sources:
        if (
            isinstance(source, dict)
            and source.get("source_id") == _NGRAM_RIGHTS_SOURCE_ID
        ):
            paths = [
                source.get("decision_artifact_path"),
                source.get("decision_signature_path"),
            ]
            return [path for path in paths if isinstance(path, str)]
    return []


def non_git_test_trust_root(root: Path, commit: str) -> NonGitTestTrustRoot:
    """Capture explicit parent bytes only for a non-git test fixture."""

    if root.resolve() == ROOT.resolve() or _git_head(root) is not None:
        _fail("promotion_trust_invalid", "test_trust_forbidden_in_git_repository")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        _fail("promotion_trust_invalid", "test_trust_commit_invalid")
    rights_registry = (root / "governance/source_rights_registry.json").read_bytes()
    decision_files = {
        relative: (root / relative).read_bytes()
        for relative in _rights_decision_paths(rights_registry)
    }
    return NonGitTestTrustRoot(
        commit=commit,
        store=(root / "data/raw/gdelt_volume.csv").read_bytes(),
        provenance=(root / "data/raw/provenance.csv").read_bytes(),
        calibration=(root / "data/raw/ngram_calibration.json").read_bytes(),
        dictionaries=(root / "dictionaries.json").read_bytes(),
        matcher=(root / "src/fetch_ngrams.py").read_bytes(),
        rights_registry=rights_registry,
        rights_signers=(root / "governance/rights_signers.json").read_bytes(),
        rights_decision_files=decision_files,
    )


def _parent_snapshot(
    root: Path,
    trusted_parent: str | None,
    non_git_test_trust: NonGitTestTrustRoot | None,
) -> _ParentSnapshot:
    if non_git_test_trust is not None:
        if root.resolve() == ROOT.resolve() or _git_head(root) is not None:
            _fail("promotion_trust_invalid", "test_trust_forbidden_in_git_repository")
        if trusted_parent not in {None, non_git_test_trust.commit}:
            _fail("promotion_trust_invalid", "test_trust_parent_mismatch")
        return _ParentSnapshot(**vars(non_git_test_trust))

    commit = _git_commit(root, trusted_parent or "HEAD")
    rights_registry = _git_blob(
        root, commit, "governance/source_rights_registry.json"
    )
    return _ParentSnapshot(
        commit=commit,
        store=_git_blob(root, commit, "data/raw/gdelt_volume.csv"),
        provenance=_git_blob(root, commit, "data/raw/provenance.csv"),
        calibration=_git_blob(root, commit, "data/raw/ngram_calibration.json"),
        dictionaries=_git_blob(root, commit, "dictionaries.json"),
        matcher=_git_blob(root, commit, "src/fetch_ngrams.py"),
        rights_registry=rights_registry,
        rights_signers=_git_blob(root, commit, "governance/rights_signers.json"),
        rights_decision_files={
            relative: _git_blob(root, commit, relative)
            for relative in _rights_decision_paths(rights_registry)
        },
    )


def require_ngram_public_identity_rights(
    *,
    root: Path = ROOT,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Require an applicable signed decision before public identity retention."""

    decision_day = as_of or utc_today()
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
        _fail("rights_not_authorized", exc.code)
    try:
        registry_effective = date.fromisoformat(str(rights_document["effective"]))
        signers_effective = date.fromisoformat(str(signers_document["effective"]))
    except (KeyError, ValueError):
        _fail("rights_not_authorized", "rights_effective_date_invalid")
    if registry_effective > decision_day or signers_effective > decision_day:
        _fail("rights_not_authorized", "rights_registry_future_dated")
    source = rights.get(_NGRAM_RIGHTS_SOURCE_ID)
    if source is None:
        _fail("rights_not_authorized", "ngram_rights_decision_missing")
    if source.get("decision_state") != "approved":
        _fail(
            "rights_not_authorized",
            f"ngram_rights_decision_{source.get('decision_state') or 'missing'}",
        )
    try:
        reviewed = date.fromisoformat(str(source["reviewed_on"]))
        due = date.fromisoformat(str(source["review_due"]))
    except (KeyError, ValueError):
        _fail("rights_not_authorized", "ngram_rights_dates_invalid")
    if reviewed > decision_day:
        _fail("rights_not_authorized", "ngram_rights_decision_future_dated")
    if due < decision_day:
        _fail("rights_not_authorized", "ngram_rights_decision_expired")
    signer_id = source.get("signer_id")
    if not isinstance(signer_id, str):
        _fail("rights_not_authorized", "ngram_rights_signer_missing")
    signer = signers.get(signer_id)
    if signer is None:
        _fail("rights_not_authorized", "ngram_rights_signer_missing")
    signer_effective = date.fromisoformat(str(signer["effective"]))
    signer_revoked = signer.get("revoked_on")
    if signer_effective > decision_day:
        _fail("rights_not_authorized", "ngram_rights_signer_future_dated")
    if signer_revoked is not None and decision_day >= date.fromisoformat(
        str(signer_revoked)
    ):
        _fail("rights_not_authorized", "ngram_rights_signer_revoked")
    uses = source.get("permitted_uses")
    if not isinstance(uses, list) or not _NGRAM_PUBLIC_IDENTITY_USES <= set(uses):
        _fail("rights_not_authorized", "ngram_public_identity_use_not_permitted")
    artifact_path = source.get("decision_artifact_path")
    signature_path = source.get("decision_signature_path")
    if not isinstance(artifact_path, str) or not isinstance(signature_path, str):
        _fail("rights_not_authorized", "ngram_signed_decision_missing")
    return {
        "source_id": _NGRAM_RIGHTS_SOURCE_ID,
        "decision_id": source["decision_id"],
        "signer_id": source["signer_id"],
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "permitted_uses": sorted(_NGRAM_PUBLIC_IDENTITY_USES),
        "rights_registry_sha256": _sha256(rights_raw),
        "rights_signers_sha256": _sha256(signers_raw),
        "decision_artifact_path": artifact_path,
        "decision_artifact_sha256": source["decision_artifact_sha256"],
        "decision_signature_path": signature_path,
        "decision_signature_sha256": _sha256((root / signature_path).read_bytes()),
    }


def _read_latest_day(root: Path) -> date | None:
    path = root / "docs/data/latest.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8")).get("date")
        parsed = date.fromisoformat(value)
    except (OSError, AttributeError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if parsed.isoformat() == value else None


def _status_payload(
    target: date,
    state: str,
    reason: str,
    *,
    root: Path,
    base_commit: str | None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if state not in _PUBLIC_STATES:
        _fail("final_status_invalid", state)
    latest = _read_latest_day(root)
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "target_date": target.isoformat(),
        "status": state,
        "reason": reason,
        "latest_finalized_date": latest.isoformat() if latest else None,
        "generated": _generated(),
        "base_commit": base_commit,
        "value_fields_published": False,
        "provisional_substitution_allowed": False,
    }
    if receipt is not None:
        payload["receipt"] = receipt
    return payload


def _atomic_replace(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _atomic_write(path: Path, data: bytes) -> None:
    """Failpoint seam for one atomic replacement inside a candidate bundle."""

    _atomic_replace(path, data)


def _commit_candidate_bundle(writes: list[tuple[Path, bytes]]) -> None:
    """Replace a prepared bundle and roll every path back on an exception.

    A process kill cannot run Python rollback, so failed-workflow staging also
    validates or discards these exact paths. Together, the target_ready marker
    is the visibility boundary and a partial bundle has no commit path.
    """

    originals = {
        path: path.read_bytes() if path.exists() else None for path, _ in writes
    }
    try:
        for path, data in writes:
            _atomic_write(path, data)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for path, _ in reversed(writes):
            original = originals[path]
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_replace(path, original)
            except OSError:
                rollback_errors.append(path.as_posix())
        if rollback_errors:
            raise FinalPublicationError(
                "acquisition_failed",
                "candidate_bundle_rollback_failed:" + ",".join(rollback_errors),
            ) from exc
        raise FinalPublicationError(
            "acquisition_failed", "candidate_bundle_commit_interrupted"
        ) from exc


def record_status(
    target: date,
    state: str,
    reason: str,
    *,
    root: Path = ROOT,
    base_commit: str | None = None,
    receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _status_payload(
        target,
        state,
        reason,
        root=root,
        base_commit=base_commit or _git_head(root),
        receipt=receipt,
    )
    _atomic_write(root / STATUS_RELATIVE, _json_bytes(payload))
    return payload


def _validate_frame_candidate(
    target: date,
    result: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    """Run the existing registered 48/48 validator on isolated bytes."""

    with tempfile.TemporaryDirectory(prefix="igrm-final-frame-") as raw:
        candidate_root = Path(raw)
        cache = candidate_root / "data/raw/ngram_days" / f"{target}.json"
        cache.parent.mkdir(parents=True)
        cache.write_bytes(json.dumps(result).encode("utf-8"))
        (candidate_root / "src").mkdir()
        shutil.copyfile(root / "dictionaries.json", candidate_root / "dictionaries.json")
        shutil.copyfile(
            root / "src/fetch_ngrams.py", candidate_root / "src/fetch_ngrams.py"
        )
        return precision_frame_v3.build_day_attestation(
            target,
            candidate_root,
            require_live_hashes=True,
            require_strong_denominator=True,
        )


def _calibration(
    root: Path, channels: list[str]
) -> tuple[bytes, dict[str, dict[str, Any]]]:
    path = root / "data/raw/ngram_calibration.json"
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError("acquisition_failed", "calibration_unreadable") from exc
    if not isinstance(value, dict) or set(value) != set(channels):
        _fail("acquisition_failed", "calibration_channel_set_invalid")
    for channel in channels:
        row = value[channel]
        ratio = row.get("ratio") if isinstance(row, dict) else None
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(float(ratio))
            or float(ratio) <= 0
        ):
            _fail("acquisition_failed", f"calibration_ratio_invalid:{channel}")
    return raw, value


def _store_candidate(
    root: Path,
    target: date,
    calibrated: dict[str, float],
) -> tuple[bytes, bytes, str]:
    path = root / "data/raw/gdelt_volume.csv"
    raw = path.read_bytes()
    if not raw.endswith((b"\n", b"\r")):
        _fail("acquisition_failed", "store_prefix_has_no_line_ending")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    if not rows:
        _fail("acquisition_failed", "store_prefix_empty")
    fields = list(rows[0])
    if fields != ["date", *calibrated]:
        _fail("acquisition_failed", "store_channel_order_invalid")
    days = [date.fromisoformat(row["date"]) for row in rows]
    if days != sorted(days) or len(days) != len(set(days)):
        _fail("acquisition_failed", "store_prefix_order_invalid")
    if days[-1] != target - timedelta(days=1):
        _fail(
            "acquisition_failed",
            f"store_prefix_end={days[-1].isoformat()} target={target.isoformat()}",
        )
    if any(day >= target for day in days):
        _fail("acquisition_failed", "store_contains_target_or_d0")

    line_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(line_buffer, fieldnames=fields, lineterminator="\n")
    candidate_row: dict[str, object] = {"date": target.isoformat(), **calibrated}
    writer.writerow(candidate_row)
    appended = line_buffer.getvalue().encode("utf-8")
    candidate = raw + appended
    if not candidate.startswith(raw):
        _fail("acquisition_failed", "store_prefix_changed")
    return raw, candidate, _sha256(_canonical_bytes(candidate_row))


def _provenance_candidate(root: Path, target: date) -> tuple[bytes, bytes]:
    path = root / "data/raw/provenance.csv"
    raw = path.read_bytes()
    if not raw.endswith((b"\n", b"\r")):
        _fail("acquisition_failed", "provenance_prefix_has_no_line_ending")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    days = [date.fromisoformat(row["date"]) for row in rows]
    if not rows or days != sorted(days) or len(days) != len(set(days)):
        _fail("acquisition_failed", "provenance_prefix_invalid")
    if days[-1] != target - timedelta(days=1) or any(day >= target for day in days):
        _fail("acquisition_failed", "provenance_not_target_append_only")
    line_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        line_buffer, fieldnames=provenance.FIELDS, lineterminator="\n"
    )
    writer.writerow(
        {
            "date": target.isoformat(),
            "source": provenance.NGRAM_BRIDGE,
            "basis": "recorded",
        }
    )
    candidate = raw + line_buffer.getvalue().encode("utf-8")
    if not candidate.startswith(raw):
        _fail("acquisition_failed", "provenance_prefix_changed")
    return raw, candidate


def _transform_receipt(
    *,
    target: date,
    base_commit: str | None,
    result: dict[str, Any],
    attestation: dict[str, Any],
    calibration_raw: bytes,
    calibration: dict[str, dict[str, Any]],
    store_prefix: bytes,
    provenance_prefix: bytes,
    candidate_row_sha256: str,
    rights_proof: dict[str, Any],
) -> dict[str, Any]:
    evidence = result["_matcher_evidence"]
    return {
        "schema_version": "1.0.0",
        "receipt_id": f"igrm:final-publication:{target.isoformat()}",
        "target_date": target.isoformat(),
        "base_commit": base_commit,
        "status": "eligible_immutable_target_candidate",
        "source": provenance.NGRAM_BRIDGE,
        "frame": {
            "validator": "src.precision_frame_v3.build_day_attestation",
            "attestation_sha256": _sha256(_canonical_bytes(attestation)),
            "source_cache_sha256": attestation["source_cache_sha256"],
            "n_samples_located": attestation["n_samples_located"],
            "n_samples_loaded": attestation["n_samples_loaded"],
            "missing_stamps": attestation["missing_stamps"],
        },
        "bindings": {
            "calibration_sha256": _sha256(calibration_raw),
            "calibration_records_sha256": {
                channel: _sha256(_canonical_bytes(calibration[channel]))
                for channel in sorted(calibration)
            },
            "dictionary_sha256": evidence["dictionaries_sha256"],
            "matcher_sha256": evidence["production_matcher_sha256"],
            "matcher_specs_sha256": evidence["matcher_specs_sha256"],
            "candidate_row_sha256": candidate_row_sha256,
            "rights": rights_proof,
        },
        "append_contract": {
            "store_prefix_sha256": _sha256(store_prefix),
            "provenance_prefix_sha256": _sha256(provenance_prefix),
            "old_prefix_equal": True,
            "target_rows_appended": 1,
            "d0_excluded": True,
        },
        "value_fields_published": False,
        "provisional_substitution_allowed": False,
    }


def acquire_target(
    target: date,
    *,
    today: date | None = None,
    root: Path = ROOT,
    base_commit: str | None = None,
    compute_day: Callable[[date, dict[str, dict]], dict[str, Any] | None]
    | None = None,
) -> dict[str, Any]:
    """Acquire, validate and atomically bank exactly one D-1 frame.

    A refusal writes only the value-free status record.  The score store,
    production cache, provenance and transform receipt remain byte-identical.
    """

    require_exact_target(target, today)
    frozen_commit = base_commit or _git_head(root)
    latest = _read_latest_day(root)
    if latest == target:
        state = public_status(root=root, today=target + timedelta(days=1))
        if state["status"] == "legacy_proof_limited":
            return record_status(
                target,
                "legacy_proof_limited",
                state["reason"],
                root=root,
                base_commit=frozen_commit,
            )
        if state["status"] != "finalized":
            return record_status(
                target,
                "acquisition_failed",
                "published target lacks a valid finalized proof",
                root=root,
                base_commit=frozen_commit,
            )
        return record_status(
            target,
            "already_finalized",
            "the exact D-1 final is already published",
            root=root,
            base_commit=frozen_commit,
        )
    if latest != target - timedelta(days=1):
        return record_status(
            target,
            "acquisition_failed",
            "latest finalized day is not the target's immutable D-2 prefix",
            root=root,
            base_commit=frozen_commit,
        )

    # Schema 1.1 freezes document-membership commitments in the public raw
    # cache. That retention surface is disabled unless the exact current
    # operation is covered by an applicable signed decision. Refuse before
    # the first source request so a pending rights review cannot leave local
    # identity evidence behind even when later validation would fail.
    try:
        rights_proof = require_ngram_public_identity_rights(
            root=root, as_of=today or utc_today()
        )
    except FinalPublicationError as exc:
        return record_status(
            target,
            "acquisition_failed",
            f"registered ngram evidence retention refused: {exc.detail}",
            root=root,
            base_commit=frozen_commit,
        )

    specs = fetch_ngrams.group_specs()
    compute = compute_day or fetch_ngrams.compute_day
    try:
        result = compute(target, specs)
    except Exception as exc:  # noqa: BLE001 - classified, value-free refusal
        return record_status(
            target,
            "acquisition_failed",
            f"registered ngram acquisition raised {type(exc).__name__}",
            root=root,
            base_commit=frozen_commit,
        )
    if result is None:
        return record_status(
            target,
            "source_unavailable",
            "the registered ngram source returned no eligible target-day frame",
            root=root,
            base_commit=frozen_commit,
        )

    try:
        attestation = _validate_frame_candidate(target, result, root)
        channels = sorted({spec["channel"] for spec in specs.values()})
        calibration_raw, calibration = _calibration(root, channels)
        sums = fetch_ngrams._channel_sums(result, specs)
        if set(sums) != set(channels):
            _fail("acquisition_failed", "target_channel_set_invalid")
        calibrated = {
            channel: sums[channel] / float(calibration[channel]["ratio"])
            for channel in channels
        }
        # Preserve the canonical store's registered channel order.
        with (root / "data/raw/gdelt_volume.csv").open(encoding="utf-8") as handle:
            store_fields = list(csv.DictReader(handle).fieldnames or [])[1:]
        calibrated = {channel: calibrated[channel] for channel in store_fields}
        store_prefix, store_candidate, row_sha = _store_candidate(
            root, target, calibrated
        )
        provenance_prefix, provenance_candidate = _provenance_candidate(root, target)
        cache_bytes = json.dumps(result).encode("utf-8")
        receipt = _transform_receipt(
            target=target,
            base_commit=frozen_commit,
            result=result,
            attestation=attestation,
            calibration_raw=calibration_raw,
            calibration=calibration,
            store_prefix=store_prefix,
            provenance_prefix=provenance_prefix,
            candidate_row_sha256=row_sha,
            rights_proof=rights_proof,
        )
    except (FinalPublicationError, precision_frame_v3.FrameValidationError) as exc:
        detail = getattr(exc, "detail", "") or str(exc)
        return record_status(
            target,
            "acquisition_failed",
            f"target frame refused: {detail}",
            root=root,
            base_commit=frozen_commit,
        )
    except Exception as exc:  # noqa: BLE001 - typed, value-free refusal
        return record_status(
            target,
            "acquisition_failed",
            f"candidate preparation raised {type(exc).__name__}",
            root=root,
            base_commit=frozen_commit,
        )

    receipt_path = RECEIPTS_RELATIVE / f"{target.isoformat()}.json"
    status = _status_payload(
        target,
        "target_ready",
        "a complete registered source frame is banked; final publication is pending",
        root=root,
        base_commit=frozen_commit,
        receipt={
            "path": receipt_path.as_posix(),
            "sha256": _sha256(_canonical_bytes(receipt)),
        },
    )
    # No canonical source/provenance write occurs before every candidate byte
    # and the value-free state have been prepared successfully. If any
    # replacement raises, restore the whole pre-acquisition bundle before
    # recording a value-free refusal.
    try:
        _commit_candidate_bundle(
            [
                (root / "data/raw/ngram_days" / f"{target}.json", cache_bytes),
                (root / "data/raw/gdelt_volume.csv", store_candidate),
                (root / "data/raw/provenance.csv", provenance_candidate),
                (root / receipt_path, _json_bytes(receipt)),
                (root / STATUS_RELATIVE, _json_bytes(status)),
            ]
        )
    except FinalPublicationError as exc:
        return record_status(
            target,
            "acquisition_failed",
            exc.detail,
            root=root,
            base_commit=frozen_commit,
        )
    return status


def _strip_last_csv_row(raw: bytes, expected_day: date, label: str) -> bytes:
    """Return exact prefix bytes after proving the final row is the target."""

    lines = raw.splitlines(keepends=True)
    if len(lines) < 2 or not lines[-1].endswith((b"\n", b"\r")):
        _fail("promotion_receipt_invalid", f"{label}_candidate_shape_invalid")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except (UnicodeError, csv.Error) as exc:
        raise FinalPublicationError(
            "promotion_receipt_invalid", f"{label}_candidate_unreadable"
        ) from exc
    if not rows or rows[-1].get("date") != expected_day.isoformat():
        _fail("promotion_receipt_invalid", f"{label}_target_row_missing")
    if sum(row.get("date") == expected_day.isoformat() for row in rows) != 1:
        _fail("promotion_receipt_invalid", f"{label}_target_row_not_unique")
    return b"".join(lines[:-1])


def _require_parent_prefix(raw: bytes, target: date, label: str) -> None:
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
        days = [date.fromisoformat(row["date"]) for row in rows]
    except (UnicodeError, csv.Error, KeyError, ValueError) as exc:
        raise FinalPublicationError(
            "promotion_trust_invalid", f"parent_{label}_unreadable"
        ) from exc
    if (
        not rows
        or days != sorted(days)
        or len(days) != len(set(days))
        or days[-1] != target - timedelta(days=1)
    ):
        _fail("promotion_trust_invalid", f"parent_{label}_is_not_exact_d2_prefix")


def require_written_final_target(target: date, *, site_data: Path) -> None:
    """Reopen public bytes and require one finite exact-target final."""

    try:
        latest = json.loads((site_data / "latest.json").read_text(encoding="utf-8"))
        history = json.loads((site_data / "history.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError(
            "final_output_target_mismatch", "written_final_payloads_unreadable"
        ) from exc
    target_iso = target.isoformat()
    dates = history.get("dates")
    composites = history.get("composite")
    if (
        latest.get("date") != target_iso
        or not isinstance(dates, list)
        or not dates
        or max(dates) != target_iso
        or dates[-1] != target_iso
        or not isinstance(composites, list)
        or len(composites) != len(dates)
    ):
        _fail(
            "final_output_target_mismatch",
            "written_latest_history_do_not_end_at_target",
        )
    for label, value in (
        ("latest.composite", latest.get("composite")),
        ("latest.composite7", latest.get("composite7")),
        ("history.composite[target]", composites[-1]),
    ):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            _fail("final_output_target_mismatch", f"non_finite_target:{label}")


def require_promotion_receipt(
    target: date,
    *,
    root: Path = ROOT,
    require_bridge_receipt: bool = False,
    trusted_parent: str | None = None,
    non_git_test_trust: NonGitTestTrustRoot | None = None,
    required_marker_status: str = "target_ready",
    rights_as_of: date | None = None,
) -> dict[str, Any]:
    """Revalidate the exact bridge candidate before it may become final.

    Legacy healing can leave a source cache and calibrated store row without
    proving the frame was complete.  Presence of either bridge provenance or
    a target-day ngram cache therefore makes the transform receipt mandatory.
    No DOC-only target is silently exempt: that source needs a separately
    registered proof mode before it may become final.
    """

    parent = _parent_snapshot(root, trusted_parent, non_git_test_trust)
    cache_path = root / "data/raw/ngram_days" / f"{target}.json"
    provenance_path = root / "data/raw/provenance.csv"
    try:
        provenance_rows = list(
            csv.DictReader(io.StringIO(provenance_path.read_text(encoding="utf-8")))
        )
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FinalPublicationError(
            "promotion_receipt_invalid", "provenance_unreadable"
        ) from exc
    target_provenance = [
        row for row in provenance_rows if row.get("date") == target.isoformat()
    ]
    bridge_target = bool(
        cache_path.exists()
        or any(row.get("source") == provenance.NGRAM_BRIDGE for row in target_provenance)
    )
    if not bridge_target:
        classification = (
            "promotion_receipt_invalid"
            if require_bridge_receipt
            else "final_proof_mode_unregistered"
        )
        _fail(classification, "registered_ngram_bridge_proof_missing")

    receipt_path = root / RECEIPTS_RELATIVE / f"{target}.json"
    marker_path = root / STATUS_RELATIVE
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        store_raw = (root / "data/raw/gdelt_volume.csv").read_bytes()
        provenance_raw = provenance_path.read_bytes()
        calibration_raw = (root / "data/raw/ngram_calibration.json").read_bytes()
        calibration = json.loads(calibration_raw)
        cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError(
            "promotion_receipt_invalid", "receipt_or_bound_input_unreadable"
        ) from exc

    expected_identity = {
        "target_date": target.isoformat(),
        "status": "eligible_immutable_target_candidate",
        "source": provenance.NGRAM_BRIDGE,
    }
    if any(receipt.get(key) != value for key, value in expected_identity.items()):
        _fail("promotion_receipt_invalid", "receipt_identity_mismatch")
    if (
        receipt.get("base_commit") != parent.commit
        or marker.get("base_commit") != parent.commit
    ):
        _fail("promotion_receipt_invalid", "frozen_parent_binding_mismatch")
    if len(target_provenance) != 1 or target_provenance[0] != {
        "date": target.isoformat(),
        "source": provenance.NGRAM_BRIDGE,
        "basis": "recorded",
    }:
        _fail("promotion_receipt_invalid", "recorded_bridge_provenance_missing")

    receipt_ref = marker.get("receipt")
    expected_relative = (RECEIPTS_RELATIVE / f"{target}.json").as_posix()
    if (
        marker.get("target_date") != target.isoformat()
        or marker.get("status") != required_marker_status
        or not isinstance(receipt_ref, dict)
        or receipt_ref.get("path") != expected_relative
        or receipt_ref.get("sha256") != _sha256(_canonical_bytes(receipt))
    ):
        _fail("promotion_receipt_invalid", "target_ready_status_binding_invalid")

    try:
        attestation = precision_frame_v3.build_day_attestation(
            target,
            root,
            require_live_hashes=True,
            require_strong_denominator=True,
        )
    except precision_frame_v3.FrameValidationError as exc:
        raise FinalPublicationError(
            "promotion_receipt_invalid", f"frame_invalid:{exc}"
        ) from exc
    frame = receipt.get("frame")
    if not isinstance(frame, dict) or frame != {
        "validator": "src.precision_frame_v3.build_day_attestation",
        "attestation_sha256": _sha256(_canonical_bytes(attestation)),
        "source_cache_sha256": attestation["source_cache_sha256"],
        "n_samples_located": precision_frame_v3.EXPECTED_SAMPLES,
        "n_samples_loaded": precision_frame_v3.EXPECTED_SAMPLES,
        "missing_stamps": [],
    }:
        _fail("promotion_receipt_invalid", "frame_binding_invalid")

    bindings = receipt.get("bindings")
    if not isinstance(bindings, dict):
        _fail("promotion_receipt_invalid", "transform_bindings_missing")
    try:
        rights_proof = require_ngram_public_identity_rights(
            root=root, as_of=rights_as_of or utc_today()
        )
    except FinalPublicationError as exc:
        _fail("promotion_receipt_invalid", f"rights_not_authorized:{exc.detail}")
    rights_paths = {
        "governance/source_rights_registry.json": parent.rights_registry,
        "governance/rights_signers.json": parent.rights_signers,
        **parent.rights_decision_files,
    }
    for relative, frozen_bytes in rights_paths.items():
        try:
            current_bytes = (root / relative).read_bytes()
        except OSError:
            _fail("promotion_receipt_invalid", f"rights_input_missing:{relative}")
        if current_bytes != frozen_bytes:
            _fail(
                "promotion_receipt_invalid",
                f"rights_input_differs_from_frozen_parent:{relative}",
            )
    if bindings.get("rights") != rights_proof:
        _fail("promotion_receipt_invalid", "rights_binding_mismatch")
    if calibration_raw != parent.calibration:
        _fail("promotion_receipt_invalid", "calibration_differs_from_frozen_parent")
    if (root / "dictionaries.json").read_bytes() != parent.dictionaries:
        _fail("promotion_receipt_invalid", "dictionary_differs_from_frozen_parent")
    if (root / "src/fetch_ngrams.py").read_bytes() != parent.matcher:
        _fail("promotion_receipt_invalid", "matcher_differs_from_frozen_parent")
    if not isinstance(calibration, dict):
        _fail("promotion_receipt_invalid", "calibration_root_invalid")
    expected_calibration_records = {
        channel: _sha256(_canonical_bytes(calibration[channel]))
        for channel in sorted(calibration)
    }
    if bindings.get("calibration_sha256") != _sha256(calibration_raw):
        _fail("promotion_receipt_invalid", "calibration_hash_mismatch")
    if bindings.get("calibration_records_sha256") != expected_calibration_records:
        _fail("promotion_receipt_invalid", "calibration_records_mismatch")
    if bindings.get("dictionary_sha256") != _sha256(
        (root / "dictionaries.json").read_bytes()
    ):
        _fail("promotion_receipt_invalid", "dictionary_hash_mismatch")
    if bindings.get("matcher_sha256") != _sha256(
        (root / "src/fetch_ngrams.py").read_bytes()
    ):
        _fail("promotion_receipt_invalid", "matcher_hash_mismatch")
    if bindings.get("matcher_specs_sha256") != attestation["matcher_specs_sha256"]:
        _fail("promotion_receipt_invalid", "matcher_specs_hash_mismatch")

    store_prefix = _strip_last_csv_row(store_raw, target, "store")
    provenance_prefix = _strip_last_csv_row(
        provenance_raw, target, "provenance"
    )
    _require_parent_prefix(parent.store, target, "store")
    _require_parent_prefix(parent.provenance, target, "provenance")
    if store_prefix != parent.store:
        _fail("promotion_receipt_invalid", "store_prefix_differs_from_frozen_parent")
    if provenance_prefix != parent.provenance:
        _fail(
            "promotion_receipt_invalid",
            "provenance_prefix_differs_from_frozen_parent",
        )
    append_contract = receipt.get("append_contract")
    if not isinstance(append_contract, dict) or append_contract != {
        "store_prefix_sha256": _sha256(parent.store),
        "provenance_prefix_sha256": _sha256(parent.provenance),
        "old_prefix_equal": True,
        "target_rows_appended": 1,
        "d0_excluded": True,
    }:
        _fail("promotion_receipt_invalid", "append_contract_mismatch")

    store_reader = csv.DictReader(io.StringIO(store_raw.decode("utf-8")))
    store_rows = list(store_reader)
    store_fields = list(store_reader.fieldnames or [])[1:]
    evidence = cache_payload.get("_matcher_evidence")
    specs = evidence.get("matcher_specs") if isinstance(evidence, dict) else None
    if not isinstance(specs, dict):
        _fail("promotion_receipt_invalid", "matcher_specs_missing")
    sums = fetch_ngrams._channel_sums(cache_payload, specs)
    if set(store_fields) != set(sums) or set(store_fields) != set(calibration):
        _fail("promotion_receipt_invalid", "target_channel_set_invalid")
    expected_row: dict[str, object] = {"date": target.isoformat()}
    actual_row: dict[str, object] = {"date": target.isoformat()}
    for field in store_fields:
        row = calibration[field]
        ratio = row.get("ratio") if isinstance(row, dict) else None
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(float(ratio))
            or float(ratio) <= 0
        ):
            _fail("promotion_receipt_invalid", f"calibration_ratio_invalid:{field}")
        expected_row[field] = sums[field] / float(ratio)
        try:
            actual_row[field] = float(store_rows[-1][field])
        except (KeyError, TypeError, ValueError) as exc:
            raise FinalPublicationError(
                "promotion_receipt_invalid", "candidate_row_non_numeric"
            ) from exc
    if actual_row != expected_row:
        _fail("promotion_receipt_invalid", "target_row_does_not_recompute")
    if bindings.get("candidate_row_sha256") != _sha256(
        _canonical_bytes(expected_row)
    ):
        _fail("promotion_receipt_invalid", "candidate_row_hash_mismatch")
    return receipt


def mark_finalized(
    target: date,
    *,
    root: Path = ROOT,
    base_commit: str | None = None,
    non_git_test_trust: NonGitTestTrustRoot | None = None,
    rights_as_of: date | None = None,
) -> dict[str, Any]:
    prior: dict[str, Any] = {}
    try:
        prior = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    if (
        prior.get("target_date") != target.isoformat()
        or prior.get("status") != "target_ready"
        or not isinstance(prior.get("receipt"), dict)
    ):
        _fail("final_proof_missing", "target_ready_receipt_binding_required")
    receipt = require_promotion_receipt(
        target,
        root=root,
        require_bridge_receipt=True,
        trusted_parent=base_commit,
        non_git_test_trust=non_git_test_trust,
        required_marker_status="target_ready",
        rights_as_of=rights_as_of,
    )
    require_written_final_target(target, site_data=root / "docs/data")
    return record_status(
        target,
        "finalized",
        "the exact D-1 finalized score is published",
        root=root,
        base_commit=receipt["base_commit"],
        receipt=prior["receipt"],
    )


def record_pipeline_failed(
    target: date,
    *,
    root: Path = ROOT,
    base_commit: str | None = None,
    failure_stage: str = "pipeline",
) -> dict[str, Any]:
    """Record a value-free failure while preserving the last true final."""

    prior: dict[str, Any] = {}
    try:
        prior = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    prior_matches = prior.get("target_date") == target.isoformat()
    if prior_matches and prior.get("status") in {
        "source_unavailable",
        "acquisition_failed",
        "pipeline_failed",
        "legacy_proof_limited",
    }:
        return prior
    if failure_stage not in {"source", "pipeline", "audit", "derived"}:
        _fail("final_status_invalid", f"unknown_failure_stage:{failure_stage}")
    prior_latest = prior.get("latest_finalized_date")
    state = "acquisition_failed" if failure_stage == "source" else "pipeline_failed"
    reason = (
        "the registered source acquisition did not complete its bounded step"
        if failure_stage == "source"
        else "the exact D-1 candidate did not complete publication validation"
    )
    payload = record_status(
        target,
        state,
        reason,
        root=root,
        base_commit=base_commit or prior.get("base_commit"),
    )
    # run_daily may have written an uncommitted candidate latest.json before a
    # later gate failed. The target_ready marker captured the real published
    # prefix before that work began; retain it instead of laundering local
    # candidate bytes into the visitor status.
    # Preserve only the pre-promotion target_ready prefix. A local successful
    # run writes a finalized marker before its audit/gate; copying that marker
    # into a frozen-base refusal worktree must not claim the unpushed target as
    # the latest public final.
    if (
        prior_matches
        and prior.get("status") == "target_ready"
        and isinstance(prior_latest, str)
        and prior_latest != target.isoformat()
    ):
        payload["latest_finalized_date"] = prior_latest
        _atomic_write(root / STATUS_RELATIVE, _json_bytes(payload))
    return payload


def _committed_receipt_parent(root: Path, marker: dict[str, Any]) -> str | None:
    """Derive a committed receipt's trust root without trusting its own base."""

    head = _git_head(root)
    base = marker.get("base_commit")
    receipt_ref = marker.get("receipt")
    if head is None or not isinstance(base, str) or not isinstance(receipt_ref, dict):
        return None
    if base == head:
        # The candidate is prepared but not committed yet; HEAD is the frozen
        # parent supplied by the workflow, so this is still externally rooted.
        return head
    relative = receipt_ref.get("path")
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%H", "--", relative],
        cwd=root,
        capture_output=True,
        text=True,
    )
    introductions = result.stdout.splitlines() if result.returncode == 0 else []
    if len(introductions) != 1:
        return None
    introduction = introductions[0]
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", introduction, head], cwd=root
    )
    if ancestor.returncode != 0:
        return None
    try:
        parent = _git_commit(root, f"{introduction}^")
        introduced_bytes = _git_blob(root, introduction, relative)
        current_bytes = (root / relative).read_bytes()
    except (FinalPublicationError, OSError):
        return None
    return parent if parent == base and current_bytes == introduced_bytes else None


def _legacy_proof_limited(root: Path, target: date) -> bool:
    """Recognize only the exact Aug-9 historical publication object.

    Schema 1.0 is not an eligibility rule. The one bounded exception is byte
    identity with the upstream publication introduced by the immutable Git
    commit below. The historical matcher is checked at that commit rather than
    against the current 1.1 producer; every value-bearing working-tree path,
    dictionary and calibration must still equal its introduced blob exactly.
    """

    if target != _LEGACY_AUG9_DAY:
        return False
    head = _git_head(root)
    if head is None:
        return False
    try:
        introduction = _git_commit(root, _LEGACY_AUG9_INTRODUCTION)
    except FinalPublicationError:
        return False
    if introduction != _LEGACY_AUG9_INTRODUCTION:
        return False
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", introduction, head],
        cwd=root,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        return False
    historical: dict[str, bytes] = {}
    try:
        for relative, expected_sha in _LEGACY_AUG9_BLOBS.items():
            introduced = _git_blob(root, introduction, relative)
            if _sha256(introduced) != expected_sha:
                return False
            historical[relative] = introduced
            if (
                relative not in _LEGACY_AUG9_HISTORICAL_ONLY_PATHS
                and (root / relative).read_bytes() != introduced
            ):
                return False
        cache = json.loads(
            historical["data/raw/ngram_days/2026-08-09.json"]
        )
    except (FinalPublicationError, OSError, UnicodeError, json.JSONDecodeError):
        return False
    evidence = cache.get("_matcher_evidence")
    if not isinstance(evidence, dict):
        return False
    if evidence.get("dictionaries_sha256") != _sha256(
        historical["dictionaries.json"]
    ):
        return False
    if evidence.get("production_matcher_sha256") != _sha256(
        historical["src/fetch_ngrams.py"]
    ):
        return False
    try:
        if evidence.get("matcher_specs") != (
            precision_frame_v3._active_specs_from_dictionary(root)
        ):
            return False
    except precision_frame_v3.FrameValidationError:
        return False

    try:
        attestation = precision_frame_v3.build_day_attestation(
            target,
            root,
            require_live_hashes=False,
            require_strong_denominator=False,
        )
    except precision_frame_v3.FrameValidationError:
        return False
    return attestation.get("denominator_evidence") == (
        "source_reported_denominator_legacy_v1.0"
    )


def public_status(
    *,
    root: Path = ROOT,
    today: date | None = None,
    trusted_parent: str | None = None,
    non_git_test_trust: NonGitTestTrustRoot | None = None,
) -> dict[str, Any]:
    contract_today = today or utc_today()
    target = required_target(contract_today)
    latest = _read_latest_day(root)
    marker: dict[str, Any] = {}
    try:
        marker = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    marker_matches = marker.get("target_date") == target.isoformat()
    marker_failure = marker_matches and marker.get("status") in {
        "source_unavailable",
        "acquisition_failed",
        "pipeline_failed",
    }
    proven_final = False
    if latest == target and marker_matches and marker.get("status") == "finalized":
        proof_parent = trusted_parent
        if proof_parent is None and non_git_test_trust is None:
            proof_parent = _committed_receipt_parent(root, marker)
        if proof_parent is not None or non_git_test_trust is not None:
            try:
                require_promotion_receipt(
                    target,
                    root=root,
                    require_bridge_receipt=True,
                    trusted_parent=proof_parent,
                    non_git_test_trust=non_git_test_trust,
                    required_marker_status="finalized",
                    rights_as_of=contract_today,
                )
                require_written_final_target(target, site_data=root / "docs/data")
                proven_final = True
            except FinalPublicationError:
                proven_final = False

    legacy_limited = (
        latest == target and not proven_final and _legacy_proof_limited(root, target)
    )
    reported_latest = latest
    if marker_failure and isinstance(marker.get("latest_finalized_date"), str):
        try:
            reported_latest = date.fromisoformat(marker["latest_finalized_date"])
        except ValueError:
            reported_latest = None
        if reported_latest == target:
            # A value-free failure marker may have been written while dirty
            # candidate site bytes already named the target. Never repeat that
            # unproven date as the finalized number of record.
            reported_latest = None
    elif latest == target and not proven_final and not legacy_limited:
        prior = marker.get("latest_finalized_date")
        try:
            parsed_prior = date.fromisoformat(prior) if isinstance(prior, str) else None
        except ValueError:
            parsed_prior = None
        reported_latest = parsed_prior if parsed_prior != target else None

    if proven_final:
        status = "finalized"
        reason = "The exact D-1 finalized score is published."
    elif legacy_limited:
        status = "legacy_proof_limited"
        reason = (
            "The Aug-9 number remains visible as the exact historical blobs "
            "introduced by commit 9077ea4; its cache structurally covers all "
            "48 half-hour windows. This byte identity does not supply a source "
            "acquisition receipt, reconstructable English denominator, "
            "cache-to-store calibration/transform receipt, or store-to-public "
            "score derivation receipt; source-retention and redistribution "
            "rights review also remains pending. It is not new-contract final "
            "proof."
        )
    elif marker_failure:
        status = marker["status"]
        reason = marker.get("reason") or "The D-1 final is unavailable."
    else:
        status = "delayed_final"
        reason = (
            "The D-1 final has not completed publication; the latest older "
            "final remains the number of record."
        )
    return {
        "target_date": target.isoformat(),
        "latest_finalized_date": (
            reported_latest.isoformat() if reported_latest else None
        ),
        "status": status,
        "reason": reason,
        "finalized": status == "finalized",
        "provisional_substitution_allowed": False,
        "value_fields_published": False,
        "source_receipt": marker.get("receipt") if proven_final else None,
    }


def write_public_status(
    *,
    root: Path = ROOT,
    today: date | None = None,
    trusted_parent: str | None = None,
    non_git_test_trust: NonGitTestTrustRoot | None = None,
) -> dict[str, Any]:
    """Update only the value-free final state in existing public status bytes."""

    state = public_status(
        root=root,
        today=today,
        trusted_parent=trusted_parent,
        non_git_test_trust=non_git_test_trust,
    )
    path = root / "docs/data/status.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError(
            "public_status_unreadable", "docs/data/status.json"
        ) from exc
    if not isinstance(payload, dict):
        _fail("public_status_unreadable", "status_root_not_object")
    payload["final_publication"] = state
    # status.json predates the operational marker and uses json.dumps'
    # default ASCII escaping. Preserve every unrelated byte convention while
    # adding the one value-free field.
    _atomic_write(path, (json.dumps(payload, indent=1) + "\n").encode("utf-8"))
    from . import status_data

    status_data.write_static_final_disclosure(state, root=root)
    return state


def require_published_target(
    target: date,
    *,
    root: Path = ROOT,
    today: date | None = None,
) -> dict[str, Any]:
    """Read-only idempotence proof for an exact fetched publication tree.

    Public JSON fields are claims, not authority. Only the live promotion
    receipt verifier or the one byte-pinned Aug-9 historical exception can
    suppress recovery.
    """

    contract_today = today or utc_today()
    require_exact_target(target, contract_today)
    state = public_status(root=root, today=contract_today)
    if state["status"] not in {"finalized", "legacy_proof_limited"}:
        _fail(
            "published_target_unproven",
            f"target={target.isoformat()} status={state['status']}",
        )
    return state


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire-target", type=date.fromisoformat)
    parser.add_argument("--record-pipeline-failed", type=date.fromisoformat)
    parser.add_argument("--check-promotion-receipt", type=date.fromisoformat)
    parser.add_argument("--check-published-target", type=date.fromisoformat)
    parser.add_argument(
        "--failure-stage",
        choices=("source", "pipeline", "audit", "derived"),
        default="pipeline",
    )
    parser.add_argument("--write-public-status", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--base-commit")
    parser.add_argument("--trusted-parent")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    selected = sum(
        (
            args.acquire_target is not None,
            args.record_pipeline_failed is not None,
            args.check_promotion_receipt is not None,
            args.check_published_target is not None,
            args.write_public_status,
        )
    )
    if selected != 1:
        parser.error("select exactly one publication-status operation")
    if args.record_pipeline_failed is not None:
        status = record_pipeline_failed(
            args.record_pipeline_failed,
            root=args.root,
            base_commit=args.base_commit,
            failure_stage=args.failure_stage,
        )
        print(json.dumps(status, indent=1))
        return
    if args.check_promotion_receipt is not None:
        receipt = require_promotion_receipt(
            args.check_promotion_receipt,
            root=args.root,
            require_bridge_receipt=True,
            trusted_parent=args.trusted_parent,
        )
        print(json.dumps(receipt, indent=1))
        return
    if args.check_published_target is not None:
        try:
            state = require_published_target(
                args.check_published_target,
                root=args.root,
                today=args.today,
            )
        except FinalPublicationError as exc:
            print(
                json.dumps(
                    {"status": exc.classification, "reason": exc.detail},
                    indent=1,
                )
            )
            raise SystemExit(2) from exc
        print(json.dumps(state, indent=1))
        return
    if args.write_public_status:
        print(
            json.dumps(
                write_public_status(root=args.root, today=args.today), indent=1
            )
        )
        return
    assert args.acquire_target is not None
    status = acquire_target(
        args.acquire_target,
        today=args.today,
        root=args.root,
        base_commit=args.base_commit,
    )
    print(json.dumps(status, indent=1))
    if status["status"] not in {"target_ready", "already_finalized"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
