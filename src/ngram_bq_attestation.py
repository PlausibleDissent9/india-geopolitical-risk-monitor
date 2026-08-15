"""Validate BigQuery backfill attestations (profile 3.0).

Profile 2.0 binds every half-hour window to exact source-object identity
(URL, sha256, byte length). BigQuery exposes no per-window object identity,
so a 3.0 attestation binds job-level provenance instead — exact query text
hash, job id and creation time, bytes processed, a table last-modified
witness — and is admissible only for a day whose durable refusal ledger
discloses a lost source, only alongside a sealed equivalence proof showing
the same frozen method reproduced a file-feed-published day exactly, and
only under the permanent ``bigquery_backfill`` acquisition-regime label.
"""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from .ngram_daily_attestation import (
    _MAX_COUNT,
    FORBIDDEN_KEYS,
    _keys,
    canonical_bytes,
    sha256,
)

PROFILE_ID = "igrm:gdelt-ngram-bq-backfill:3.0.0"
SCHEMA_VERSION = "3.0.0"
EXPECTED_WINDOWS = 48
ACQUISITION_REGIME = "bigquery_backfill"
BQ_TABLE = "gdelt-bq.gdeltv2.webngrams"
PROFILE_RELATIVE = Path("governance/ngram_bq_backfill_profile.json")
SCHEMA_RELATIVE = Path("governance/schemas/ngram-bq-backfill-attestation.schema.json")
REFUSAL_LEDGER_RELATIVE = Path("data/raw/final_publication_refusals")
EQUIVALENCE_RELATIVE = Path("data/raw/bq_equivalence")
MEMBERSHIP_LIMIT = (
    "Document membership is not retained and cannot be reconstructed from "
    "this attestation; the mirror table may be re-queried while the provider "
    "retains it, and only aggregate counts are persisted."
)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UTC_INSTANT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?Z$")
_ROOT_FIELDS = {
    "schema_version",
    "profile_id",
    "day",
    "acquisition_regime",
    "refusal_disclosure",
    "equivalence_binding",
    "expected_windows",
    "located_windows",
    "loaded_windows",
    "bq_provenance",
    "method_bindings",
    "windows",
    "aggregate_reconstruction",
    "membership_reproducibility",
    "record_sha256",
}
_BINDING_FIELDS = {
    "profile_sha256",
    "schema_sha256",
    "dictionaries_sha256",
    "production_matcher_sha256",
    "validator_sha256",
    "calibration_sha256",
    "matcher_specs",
    "matcher_specs_sha256",
}
_PROVENANCE_FIELDS = {
    "table",
    "query_text_sha256",
    "job_id",
    "job_created_utc",
    "total_bytes_processed",
    "table_last_modified_utc",
}
_WINDOW_FIELDS = {
    "bucket",
    "window_start_utc",
    "row_count",
    "english_denominator",
    "group_numerators",
}
_RECONSTRUCTION_FIELDS = {
    "window_order",
    "english_denominator",
    "group_numerators",
    "shares",
    "channel_sums",
}
_AGGREGATE_FIELDS = {
    "english_denominator",
    "group_numerators",
    "shares",
    "channel_sums",
}
_EQUIVALENCE_FIELDS = {
    "schema_version",
    "profile_id",
    "kind",
    "day",
    "published_reference",
    "bq_recomputation",
    "exact_match",
    "bq_provenance",
    "method_bindings",
    "record_sha256",
}


class BqAttestationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise BqAttestationError(code)


def seal(record: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    return {**body, "record_sha256": sha256(canonical_bytes(body))}


def _nonnegative_int(value: object, code: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _MAX_COUNT
    ):
        _fail(code)
    return value


def _finite_number(value: object, code: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
    ):
        _fail(code)
    return float(value)


def _utc_instant(value: object, code: str) -> str:
    if not isinstance(value, str) or _UTC_INSTANT.fullmatch(value) is None:
        _fail(code)
    return value


def _hex64(value: object, code: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        _fail(code)
    return value


def _validate_provenance(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PROVENANCE_FIELDS:
        _fail("bq_attestation_provenance_invalid")
    provenance = cast(dict[str, Any], value)
    if provenance.get("table") != BQ_TABLE:
        _fail("bq_attestation_provenance_invalid")
    _hex64(provenance.get("query_text_sha256"), "bq_attestation_provenance_invalid")
    job_id = provenance.get("job_id")
    if not isinstance(job_id, str) or not 1 <= len(job_id) <= 512:
        _fail("bq_attestation_provenance_invalid")
    _utc_instant(provenance.get("job_created_utc"), "bq_attestation_provenance_invalid")
    _utc_instant(
        provenance.get("table_last_modified_utc"),
        "bq_attestation_provenance_invalid",
    )
    _nonnegative_int(
        provenance.get("total_bytes_processed"), "bq_attestation_provenance_invalid"
    )
    return provenance


def _validate_bindings(
    bindings: object, *, root: Path, expected_calibration_sha256: str | None
) -> None:
    if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
        _fail("bq_attestation_bindings_invalid")
    expected_paths = {
        "profile_sha256": root / PROFILE_RELATIVE,
        "schema_sha256": root / SCHEMA_RELATIVE,
        "dictionaries_sha256": root / "dictionaries.json",
        "production_matcher_sha256": root / "src/fetch_ngrams_bq.py",
        "validator_sha256": root / "src/ngram_bq_attestation.py",
    }
    for field, path in expected_paths.items():
        try:
            expected = sha256(path.read_bytes())
        except OSError:
            _fail("bq_attestation_bound_source_missing")
        if bindings.get(field) != expected:
            _fail("bq_attestation_bound_source_mismatch")
    if (
        expected_calibration_sha256 is not None
        and bindings.get("calibration_sha256") != expected_calibration_sha256
    ):
        _fail("bq_attestation_calibration_mismatch")


def _validate_specs_binding(
    bindings: dict[str, Any], specs: dict[str, dict[str, Any]]
) -> None:
    canonical_specs = json.loads(canonical_bytes(specs))
    if bindings.get("matcher_specs") != canonical_specs or bindings.get(
        "matcher_specs_sha256"
    ) != sha256(canonical_bytes(canonical_specs)):
        _fail("bq_attestation_specs_mismatch")


def validate_equivalence_proof(
    value: object, *, root: Path, specs: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Validate the sealed proof that BigQuery reproduced a published day."""

    if not isinstance(value, dict):
        _fail("bq_equivalence_proof_invalid")
    proof = cast(dict[str, Any], value)
    if set(proof) != _EQUIVALENCE_FIELDS:
        _fail("bq_equivalence_proof_fields_invalid")
    if FORBIDDEN_KEYS & _keys(proof):
        _fail("bq_equivalence_proof_identity_leak")
    if (
        proof.get("schema_version") != SCHEMA_VERSION
        or proof.get("profile_id") != PROFILE_ID
        or proof.get("kind") != "bq_equivalence_proof"
    ):
        _fail("bq_equivalence_proof_invalid")
    try:
        date.fromisoformat(str(proof.get("day")))
    except ValueError:
        _fail("bq_equivalence_proof_invalid")
    if seal(proof) != proof:
        _fail("bq_equivalence_proof_seal_invalid")
    _validate_bindings(
        proof.get("method_bindings"), root=root, expected_calibration_sha256=None
    )
    _validate_specs_binding(cast(dict[str, Any], proof["method_bindings"]), specs)
    _validate_provenance(proof.get("bq_provenance"))
    reference = proof.get("published_reference")
    recomputed = proof.get("bq_recomputation")
    for side in (reference, recomputed):
        if not isinstance(side, dict) or set(side) != _AGGREGATE_FIELDS:
            _fail("bq_equivalence_proof_sides_invalid")
    if proof.get("exact_match") is not True or reference != recomputed:
        _fail("bq_equivalence_proof_not_exact")
    for share in cast(dict[str, object], cast(dict[str, Any], reference)["shares"]).values():
        _finite_number(share, "bq_equivalence_proof_share_invalid")
    return dict(proof)


def validate(
    value: object,
    *,
    target: date,
    specs: dict[str, dict[str, Any]],
    root: Path,
    expected_calibration_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("bq_attestation_root_invalid")
    attestation = cast(dict[str, Any], value)
    if set(attestation) != _ROOT_FIELDS:
        _fail("bq_attestation_fields_invalid")
    if FORBIDDEN_KEYS & _keys(attestation):
        _fail("bq_attestation_identity_leak")
    if (
        attestation.get("schema_version") != SCHEMA_VERSION
        or attestation.get("profile_id") != PROFILE_ID
        or attestation.get("day") != target.isoformat()
        or attestation.get("acquisition_regime") != ACQUISITION_REGIME
        or attestation.get("membership_reproducibility") != MEMBERSHIP_LIMIT
    ):
        _fail("bq_attestation_profile_invalid")
    if seal(attestation) != attestation:
        _fail("bq_attestation_seal_invalid")
    for field in ("expected_windows", "located_windows", "loaded_windows"):
        if attestation.get(field) != EXPECTED_WINDOWS:
            _fail("bq_attestation_window_count_invalid")

    disclosure = attestation.get("refusal_disclosure")
    expected_ledger = (REFUSAL_LEDGER_RELATIVE / f"{target.isoformat()}.json").as_posix()
    if (
        not isinstance(disclosure, dict)
        or set(disclosure) != {"ledger_path", "reason_code"}
        or disclosure.get("ledger_path") != expected_ledger
        or disclosure.get("reason_code") != "source_acquisition_failed"
    ):
        _fail("bq_attestation_refusal_disclosure_invalid")
    try:
        ledger = json.loads((root / expected_ledger).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _fail("bq_attestation_refusal_ledger_missing")
    if (
        not isinstance(ledger, dict)
        or ledger.get("target_date") != target.isoformat()
        or ledger.get("failure_stage") != "source"
        or ledger.get("reason_code") != "source_acquisition_failed"
    ):
        _fail("bq_attestation_refusal_ledger_mismatch")

    binding = attestation.get("equivalence_binding")
    if (
        not isinstance(binding, dict)
        or set(binding) != {"day", "proof_path", "proof_record_sha256"}
    ):
        _fail("bq_attestation_equivalence_binding_invalid")
    try:
        proof_day = date.fromisoformat(str(binding.get("day")))
    except ValueError:
        _fail("bq_attestation_equivalence_binding_invalid")
    if proof_day == target:
        _fail("bq_attestation_equivalence_binding_invalid")
    expected_proof_path = (EQUIVALENCE_RELATIVE / f"{proof_day.isoformat()}.json").as_posix()
    if binding.get("proof_path") != expected_proof_path:
        _fail("bq_attestation_equivalence_binding_invalid")
    _hex64(
        binding.get("proof_record_sha256"),
        "bq_attestation_equivalence_binding_invalid",
    )
    try:
        proof_value = json.loads((root / expected_proof_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _fail("bq_attestation_equivalence_proof_missing")
    proof = validate_equivalence_proof(proof_value, root=root, specs=specs)
    if (
        proof["day"] != proof_day.isoformat()
        or proof["record_sha256"] != binding["proof_record_sha256"]
    ):
        _fail("bq_attestation_equivalence_proof_mismatch")

    _validate_provenance(attestation.get("bq_provenance"))
    bindings = attestation.get("method_bindings")
    _validate_bindings(
        bindings, root=root, expected_calibration_sha256=expected_calibration_sha256
    )
    _validate_specs_binding(cast(dict[str, Any], bindings), specs)

    windows = attestation.get("windows")
    if not isinstance(windows, list) or len(windows) != EXPECTED_WINDOWS:
        _fail("bq_attestation_window_count_invalid")
    groups = sorted(specs)
    denominators: list[int] = []
    totals = {group: 0 for group in groups}
    for bucket, raw_row in enumerate(windows):
        if (
            not isinstance(raw_row, dict)
            or set(raw_row) != _WINDOW_FIELDS
            or raw_row.get("bucket") != bucket
        ):
            _fail("bq_attestation_window_order_invalid")
        start = _utc_instant(
            raw_row.get("window_start_utc"), "bq_attestation_window_start_invalid"
        )
        try:
            # Fractional-second instants pass the regex but are not window starts.
            parsed = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            _fail("bq_attestation_window_start_invalid")
        if (
            parsed.date() != target
            or parsed.second != 0
            or parsed.minute % 30 != 0
            or parsed.hour * 2 + parsed.minute // 30 != bucket
        ):
            _fail("bq_attestation_window_start_invalid")
        row_count = _nonnegative_int(
            raw_row.get("row_count"), "bq_attestation_row_count_invalid"
        )
        if row_count == 0:
            _fail("bq_attestation_row_count_invalid")
        denominator = _nonnegative_int(
            raw_row.get("english_denominator"),
            "bq_attestation_denominator_invalid",
        )
        if denominator == 0:
            _fail("bq_attestation_denominator_invalid")
        denominators.append(denominator)
        numerators = raw_row.get("group_numerators")
        if not isinstance(numerators, dict) or sorted(numerators) != groups:
            _fail("bq_attestation_group_set_invalid")
        for group in groups:
            numerator = _nonnegative_int(
                numerators[group], "bq_attestation_numerator_invalid"
            )
            if numerator > denominator:
                _fail("bq_attestation_numerator_invalid")
            totals[group] += numerator

    denominator_total = sum(denominators)
    reconstruction = attestation.get("aggregate_reconstruction")
    if (
        not isinstance(reconstruction, dict)
        or set(reconstruction) != _RECONSTRUCTION_FIELDS
    ):
        _fail("bq_attestation_reconstruction_invalid")
    expected_shares = {
        group: round(100.0 * totals[group] / denominator_total, 6) for group in groups
    }
    channel_sums: dict[str, float] = {}
    for group in groups:
        channel = str(specs[group]["channel"])
        channel_sums[channel] = channel_sums.get(channel, 0.0) + expected_shares[group]
    if (
        reconstruction.get("window_order") != list(range(EXPECTED_WINDOWS))
        or reconstruction.get("english_denominator") != denominator_total
        or reconstruction.get("group_numerators") != totals
        or reconstruction.get("shares") != expected_shares
        or reconstruction.get("channel_sums") != channel_sums
    ):
        _fail("bq_attestation_reconstruction_invalid")
    for share in cast(dict[str, object], reconstruction["shares"]).values():
        _finite_number(share, "bq_attestation_share_invalid")
    return dict(attestation)
