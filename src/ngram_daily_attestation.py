"""Validate the prospective value-free NGram daily aggregate profile.

The attestation retains exact source-object identity and aggregate counts, but
never document identity or source content. It licenses aggregate
reconstruction only; document membership requires re-fetching the exact source
objects while they remain available.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, NoReturn, cast

PROFILE_ID = "igrm:gdelt-ngram-daily-aggregate:2.0.0"
SCHEMA_VERSION = "2.0.0"
EXPECTED_WINDOWS = 48
PROFILE_RELATIVE = Path("governance/ngram_daily_aggregate_profile.json")
SCHEMA_RELATIVE = Path("governance/schemas/ngram-daily-aggregate-attestation.schema.json")
MEMBERSHIP_LIMIT = (
    "Document membership can be reconstructed only by re-fetching every exact "
    "hash-pinned source object while it remains available; membership is not "
    "independently retained."
)
FORBIDDEN_KEYS = frozenset(
    {
        "english_document_identities",
        "india_document_keys",
        "matched_document_keys",
        "article_meta",
        "document_ids",
        "document_hashes",
        "titles",
        "article_urls",
        "snippets",
        "source_records",
        "raw_source_bytes",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_ROOT_FIELDS = {
    "schema_version",
    "profile_id",
    "day",
    "expected_windows",
    "located_windows",
    "loaded_windows",
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
_WINDOW_FIELDS = {
    "bucket",
    "stamp",
    "source_objects",
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
_MAX_COUNT = 2**63 - 1


class AggregateAttestationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise AggregateAttestationError(code)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def seal(attestation: dict[str, Any]) -> dict[str, Any]:
    body = {key: value for key, value in attestation.items() if key != "record_sha256"}
    return {**body, "record_sha256": sha256(canonical_bytes(body))}


def source_urls(stamp: str) -> tuple[str, str]:
    base = "https://storage.googleapis.com/data.gdeltproject.org/gdeltv5/weblegacy/ngrams/"
    return (f"{base}{stamp}.toc.json.gz", f"{base}{stamp}.ngrams.txt.gz")


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


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key))
            found.update(_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_keys(item))
    return found


def validate(
    value: object,
    *,
    target: date,
    specs: dict[str, dict[str, Any]],
    root: Path,
    expected_calibration_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("aggregate_attestation_root_invalid")
    attestation = cast(dict[str, Any], value)
    if set(attestation) != _ROOT_FIELDS:
        _fail("aggregate_attestation_fields_invalid")
    if FORBIDDEN_KEYS & _keys(attestation):
        _fail("aggregate_attestation_identity_leak")
    if (
        attestation.get("schema_version") != SCHEMA_VERSION
        or attestation.get("profile_id") != PROFILE_ID
        or attestation.get("day") != target.isoformat()
        or attestation.get("membership_reproducibility") != MEMBERSHIP_LIMIT
    ):
        _fail("aggregate_attestation_profile_invalid")
    if seal(attestation) != attestation:
        _fail("aggregate_attestation_seal_invalid")
    for field in ("expected_windows", "located_windows", "loaded_windows"):
        if attestation.get(field) != EXPECTED_WINDOWS:
            _fail("aggregate_attestation_window_count_invalid")

    bindings = attestation.get("method_bindings")
    if not isinstance(bindings, dict) or set(bindings) != _BINDING_FIELDS:
        _fail("aggregate_attestation_bindings_invalid")
    expected_paths = {
        "profile_sha256": root / PROFILE_RELATIVE,
        "schema_sha256": root / SCHEMA_RELATIVE,
        "dictionaries_sha256": root / "dictionaries.json",
        "production_matcher_sha256": root / "src/fetch_ngrams.py",
        "validator_sha256": root / "src/ngram_daily_attestation.py",
    }
    for field, path in expected_paths.items():
        try:
            expected = sha256(path.read_bytes())
        except OSError:
            _fail("aggregate_attestation_bound_source_missing")
        if bindings.get(field) != expected:
            _fail("aggregate_attestation_bound_source_mismatch")
    if (
        expected_calibration_sha256 is not None
        and bindings.get("calibration_sha256") != expected_calibration_sha256
    ):
        _fail("aggregate_attestation_calibration_mismatch")
    canonical_specs = json.loads(canonical_bytes(specs))
    if bindings.get("matcher_specs") != canonical_specs or bindings.get(
        "matcher_specs_sha256"
    ) != sha256(canonical_bytes(canonical_specs)):
        _fail("aggregate_attestation_specs_mismatch")

    windows = attestation.get("windows")
    if not isinstance(windows, list) or len(windows) != EXPECTED_WINDOWS:
        _fail("aggregate_attestation_window_count_invalid")
    groups = sorted(specs)
    denominators: list[int] = []
    totals = {group: 0 for group in groups}
    seen_stamps: set[str] = set()
    for bucket, raw_row in enumerate(windows):
        if (
            not isinstance(raw_row, dict)
            or set(raw_row) != _WINDOW_FIELDS
            or raw_row.get("bucket") != bucket
        ):
            _fail("aggregate_attestation_window_order_invalid")
        stamp = raw_row.get("stamp")
        if not isinstance(stamp, str) or stamp in seen_stamps:
            _fail("aggregate_attestation_stamp_invalid")
        try:
            parsed = datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            _fail("aggregate_attestation_stamp_invalid")
        if (
            parsed.date() != target
            or parsed.second != 0
            or parsed.hour * 2 + parsed.minute // 30 != bucket
        ):
            _fail("aggregate_attestation_stamp_bucket_invalid")
        seen_stamps.add(stamp)
        toc_url, ngram_url = source_urls(stamp)
        objects = raw_row.get("source_objects")
        if not isinstance(objects, dict) or set(objects) != {"toc", "ngrams"}:
            _fail("aggregate_attestation_source_objects_invalid")
        for kind, expected_url in (("toc", toc_url), ("ngrams", ngram_url)):
            row = objects[kind]
            if (
                not isinstance(row, dict)
                or set(row) != {"url", "sha256", "bytes"}
                or row.get("url") != expected_url
                or not isinstance(row.get("sha256"), str)
                or _HEX64.fullmatch(str(row["sha256"])) is None
                or _nonnegative_int(row.get("bytes"), "aggregate_attestation_source_bytes_invalid")
                == 0
            ):
                _fail("aggregate_attestation_source_objects_invalid")
        denominator = _nonnegative_int(
            raw_row.get("english_denominator"),
            "aggregate_attestation_denominator_invalid",
        )
        if denominator == 0:
            _fail("aggregate_attestation_denominator_invalid")
        denominators.append(denominator)
        numerators = raw_row.get("group_numerators")
        if not isinstance(numerators, dict) or sorted(numerators) != groups:
            _fail("aggregate_attestation_group_set_invalid")
        for group in groups:
            numerator = _nonnegative_int(
                numerators[group], "aggregate_attestation_numerator_invalid"
            )
            if numerator > denominator:
                _fail("aggregate_attestation_numerator_invalid")
            totals[group] += numerator

    denominator_total = sum(denominators)
    reconstruction = attestation.get("aggregate_reconstruction")
    if (
        not isinstance(reconstruction, dict)
        or set(reconstruction) != _RECONSTRUCTION_FIELDS
    ):
        _fail("aggregate_attestation_reconstruction_invalid")
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
        _fail("aggregate_attestation_reconstruction_invalid")
    for share in cast(dict[str, object], reconstruction["shares"]).values():
        _finite_number(share, "aggregate_attestation_share_invalid")
    return dict(attestation)


def audit_source_objects(
    attestation: dict[str, Any],
    *,
    fetch: Callable[[str], bytes | None],
) -> dict[str, Any]:
    """Re-fetch exact objects and verify their retained byte commitments."""

    verified = 0
    for window in cast(list[dict[str, Any]], attestation["windows"]):
        for source in cast(dict[str, dict[str, Any]], window["source_objects"]).values():
            raw = fetch(str(source["url"]))
            if raw is None:
                _fail("aggregate_attestation_source_object_unavailable")
            if len(raw) != source["bytes"] or sha256(raw) != source["sha256"]:
                _fail("aggregate_attestation_source_object_mismatch")
            verified += 1
    return {
        "status": "exact_source_objects_match",
        "objects_verified": verified,
        "document_membership_retained": False,
    }
