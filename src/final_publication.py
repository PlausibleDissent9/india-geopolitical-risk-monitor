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
import shutil
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn

from . import fetch_ngrams, precision_frame_v3, provenance

ROOT = Path(__file__).resolve().parents[1]
STATUS_RELATIVE = Path("data/raw/final_publication_status.json")
RECEIPTS_RELATIVE = Path("data/raw/final_publication_receipts")

_PUBLIC_STATES = {
    "already_finalized",
    "source_unavailable",
    "acquisition_failed",
    "pipeline_failed",
    "target_ready",
    "finalized",
}


class FinalPublicationError(RuntimeError):
    """Stable typed refusal from the finalized-publication boundary."""

    def __init__(self, classification: str, detail: str = "") -> None:
        super().__init__(classification)
        self.classification = classification
        self.detail = detail


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


def _atomic_write(path: Path, data: bytes) -> None:
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
    # and the value-free state have been prepared successfully.
    _atomic_write(root / "data/raw/ngram_days" / f"{target}.json", cache_bytes)
    _atomic_write(root / "data/raw/gdelt_volume.csv", store_candidate)
    _atomic_write(root / "data/raw/provenance.csv", provenance_candidate)
    _atomic_write(root / receipt_path, _json_bytes(receipt))
    _atomic_write(root / STATUS_RELATIVE, _json_bytes(status))
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
    return b"".join(lines[:-1])


def require_promotion_receipt(
    target: date,
    *,
    root: Path = ROOT,
    require_bridge_receipt: bool = False,
) -> dict[str, Any] | None:
    """Revalidate the exact bridge candidate before it may become final.

    Legacy healing can leave a source cache and calibrated store row without
    proving the frame was complete.  Presence of either bridge provenance or
    a target-day ngram cache therefore makes the transform receipt mandatory.
    A DOC-only target is outside this bridge promotion boundary.
    """

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
    if not bridge_target and not require_bridge_receipt:
        return None

    receipt_path = root / RECEIPTS_RELATIVE / f"{target}.json"
    marker_path = root / STATUS_RELATIVE
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        store_raw = (root / "data/raw/gdelt_volume.csv").read_bytes()
        provenance_raw = provenance_path.read_bytes()
        calibration_raw = (root / "data/raw/ngram_calibration.json").read_bytes()
        calibration = json.loads(calibration_raw)
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
        or marker.get("status") != "target_ready"
        or not isinstance(receipt_ref, dict)
        or receipt_ref.get("path") != expected_relative
        or receipt_ref.get("sha256") != _sha256(_canonical_bytes(receipt))
    ):
        _fail("promotion_receipt_invalid", "target_ready_status_binding_invalid")

    attestation = precision_frame_v3.build_day_attestation(
        target, root, require_live_hashes=True
    )
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
    append_contract = receipt.get("append_contract")
    if not isinstance(append_contract, dict) or append_contract != {
        "store_prefix_sha256": _sha256(store_prefix),
        "provenance_prefix_sha256": _sha256(provenance_prefix),
        "old_prefix_equal": True,
        "target_rows_appended": 1,
        "d0_excluded": True,
    }:
        _fail("promotion_receipt_invalid", "append_contract_mismatch")

    store_rows = list(csv.DictReader(io.StringIO(store_raw.decode("utf-8"))))
    candidate_row: dict[str, object] = {"date": target.isoformat()}
    for field, value in store_rows[-1].items():
        if field != "date":
            try:
                candidate_row[field] = float(value)
            except (TypeError, ValueError) as exc:
                raise FinalPublicationError(
                    "promotion_receipt_invalid", "candidate_row_non_numeric"
                ) from exc
    if bindings.get("candidate_row_sha256") != _sha256(
        _canonical_bytes(candidate_row)
    ):
        _fail("promotion_receipt_invalid", "candidate_row_hash_mismatch")
    return receipt


def mark_finalized(
    target: date,
    *,
    root: Path = ROOT,
    base_commit: str | None = None,
) -> dict[str, Any]:
    latest = _read_latest_day(root)
    if latest != target:
        _fail(
            "final_output_target_mismatch",
            f"latest={latest} target={target.isoformat()}",
        )
    prior: dict[str, Any] = {}
    try:
        prior = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    receipt = prior.get("receipt") if prior.get("target_date") == target.isoformat() else None
    return record_status(
        target,
        "finalized",
        "the exact D-1 finalized score is published",
        root=root,
        base_commit=base_commit or prior.get("base_commit"),
        receipt=receipt,
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


def public_status(
    *, root: Path = ROOT, today: date | None = None
) -> dict[str, Any]:
    target = required_target(today)
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
    if marker_failure and isinstance(marker.get("latest_finalized_date"), str):
        try:
            latest = date.fromisoformat(marker["latest_finalized_date"])
        except ValueError:
            latest = None

    if latest == target and not marker_failure:
        status = "finalized"
        reason = "The exact D-1 finalized score is published."
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
        "latest_finalized_date": latest.isoformat() if latest else None,
        "status": status,
        "reason": reason,
        "finalized": status == "finalized",
        "provisional_substitution_allowed": False,
        "value_fields_published": False,
        "source_receipt": (
            marker.get("receipt")
            if marker.get("target_date") == target.isoformat()
            else None
        ),
    }


def write_public_status(
    *, root: Path = ROOT, today: date | None = None
) -> dict[str, Any]:
    """Update only the value-free final state in existing public status bytes."""

    state = public_status(root=root, today=today)
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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire-target", type=date.fromisoformat)
    parser.add_argument("--record-pipeline-failed", type=date.fromisoformat)
    parser.add_argument(
        "--failure-stage",
        choices=("source", "pipeline", "audit", "derived"),
        default="pipeline",
    )
    parser.add_argument("--write-public-status", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat)
    parser.add_argument("--base-commit")
    args = parser.parse_args()
    selected = sum(
        (
            args.acquire_target is not None,
            args.record_pipeline_failed is not None,
            args.write_public_status,
        )
    )
    if selected != 1:
        parser.error("select exactly one publication-status operation")
    if args.record_pipeline_failed is not None:
        status = record_pipeline_failed(
            args.record_pipeline_failed,
            base_commit=args.base_commit,
            failure_stage=args.failure_stage,
        )
        print(json.dumps(status, indent=1))
        return
    if args.write_public_status:
        print(json.dumps(write_public_status(today=args.today), indent=1))
        return
    assert args.acquire_target is not None
    status = acquire_target(
        args.acquire_target,
        today=args.today,
        base_commit=args.base_commit,
    )
    print(json.dumps(status, indent=1))
    if status["status"] not in {"target_ready", "already_finalized"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
