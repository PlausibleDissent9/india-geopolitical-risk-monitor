"""BigQuery matcher for the backfill lane (profile 3.0).

Token semantics are not reimplemented: matching reuses ``fetch_ngrams``'s own
``_norm_tokens``/``_subseq`` over context rows pulled from the provider's
documented mirror, so the only seam between the file feed and this lane is
the row source itself — exactly the seam the equivalence day measures.

This module is deliberately network-free. It generates the SQL and does the
counting; the CI lane executes queries under ``maximum_bytes_billed`` caps
and passes rows back in. Only counts are persisted.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, NoReturn

from . import ngram_bq_attestation
from .fetch_ngrams import _norm_tokens, _subseq

ROOT = Path(__file__).resolve().parents[1]
BQ_TABLE = ngram_bq_attestation.BQ_TABLE
SAMPLES_PER_DAY = 48
# The mirror's lang column literal for English rows; the equivalence day is
# the check that this (and every other translation choice here) reproduces
# the file feed exactly.
ENGLISH_LANG_LITERAL = "en"
_STAMP = re.compile(r"^\d{14}$")

RunQuery = Callable[[str], list[dict[str, Any]]]


class BqAcquisitionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise BqAcquisitionError(code)


def _day_bounds(day: date) -> tuple[str, str]:
    return (f"{day.isoformat()} 00:00:00", f"{(day + timedelta(days=1)).isoformat()} 00:00:00")


def _stamp_timestamp(stamp: str) -> str:
    if _STAMP.fullmatch(stamp) is None:
        _fail("bq_backfill_stamp_invalid")
    return (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]} "
        f"{stamp[8:10]}:{stamp[10:12]}:{stamp[12:14]}"
    )


def _timestamp_list(stamps: list[str]) -> str:
    return ", ".join(f"TIMESTAMP '{_stamp_timestamp(stamp)}'" for stamp in stamps)


def trigger_fragments(specs: Mapping[str, dict[str, Any]]) -> list[str]:
    """The same pre-filter fragments the file-feed matcher compiles."""

    fragments = sorted({p[0] for s in specs.values() for p in s["phrases"]})
    return fragments + ["india"]


def _context_expression() -> str:
    return "LOWER(CONCAT(IFNULL(pre, ''), ' ', ngram, ' ', IFNULL(post, '')))"


def minute_discovery_query(day: date) -> str:
    start, end = _day_bounds(day)
    return (
        "SELECT FORMAT_TIMESTAMP('%Y%m%d%H%M%S', date) AS stamp, "
        "COUNT(*) AS row_count "
        f"FROM `{BQ_TABLE}` "
        f"WHERE date >= TIMESTAMP '{start}' AND date < TIMESTAMP '{end}' "
        "GROUP BY stamp ORDER BY stamp"
    )


def denominator_query(day: date, stamps: list[str]) -> str:
    start, end = _day_bounds(day)
    return (
        "SELECT FORMAT_TIMESTAMP('%Y%m%d%H%M%S', date) AS stamp, "
        "COUNT(DISTINCT url) AS english_documents "
        f"FROM `{BQ_TABLE}` "
        f"WHERE date >= TIMESTAMP '{start}' AND date < TIMESTAMP '{end}' "
        f"AND date IN ({_timestamp_list(stamps)}) "
        f"AND lang = '{ENGLISH_LANG_LITERAL}' "
        "GROUP BY stamp ORDER BY stamp"
    )


def context_rows_query(
    day: date, stamps: list[str], specs: Mapping[str, dict[str, Any]]
) -> str:
    start, end = _day_bounds(day)
    pattern = "|".join(re.escape(fragment) for fragment in trigger_fragments(specs))
    return (
        "SELECT FORMAT_TIMESTAMP('%Y%m%d%H%M%S', date) AS stamp, url, "
        f"{_context_expression()} AS context "
        f"FROM `{BQ_TABLE}` "
        f"WHERE date >= TIMESTAMP '{start}' AND date < TIMESTAMP '{end}' "
        f"AND date IN ({_timestamp_list(stamps)}) "
        f"AND lang = '{ENGLISH_LANG_LITERAL}' "
        f"AND REGEXP_CONTAINS({_context_expression()}, r'''{pattern}''')"
    )


def select_window_stamps(discovered: Mapping[str, int], day: date) -> list[str]:
    """First existing minute per half-hour window — the probe rule."""

    day_key = f"{day:%Y%m%d}"
    per_window: dict[int, str] = {}
    for stamp in sorted(discovered):
        if _STAMP.fullmatch(stamp) is None or not stamp.startswith(day_key):
            _fail("bq_backfill_stamp_invalid")
        minute = int(stamp[8:10]) * 60 + int(stamp[10:12])
        bucket = minute // 30
        if bucket not in per_window:
            per_window[bucket] = stamp
    missing = [w for w in range(SAMPLES_PER_DAY) if w not in per_window]
    if missing:
        _fail(f"bq_backfill_windows_missing:{len(missing)}")
    return [per_window[w] for w in range(SAMPLES_PER_DAY)]


def recompute_day(
    day: date,
    specs: Mapping[str, dict[str, Any]],
    run_query: RunQuery,
) -> dict[str, Any]:
    """Windows and totals for one day, matched with the file feed's tokens."""

    discovered: dict[str, int] = {}
    for row in run_query(minute_discovery_query(day)):
        discovered[str(row["stamp"])] = int(row["row_count"])
    if not discovered:
        _fail("bq_backfill_day_absent")
    stamps = select_window_stamps(discovered, day)

    denominators: dict[str, int] = {}
    for row in run_query(denominator_query(day, stamps)):
        denominators[str(row["stamp"])] = int(row["english_documents"])
    for stamp in stamps:
        if denominators.get(stamp, 0) <= 0:
            _fail("bq_backfill_denominator_empty")

    groups = sorted(specs)
    india_docs: set[str] = set()
    matched: dict[str, set[str]] = {group: set() for group in groups}
    for row in run_query(context_rows_query(day, stamps, specs)):
        stamp = str(row["stamp"])
        if stamp not in denominators:
            _fail("bq_backfill_unexpected_stamp")
        key = f"{stamp}:{row['url']}"
        tokens = _norm_tokens(str(row["context"]))
        if "india" in tokens:
            india_docs.add(key)
        for group in groups:
            if key in matched[group]:
                continue
            for phrase in specs[group]["phrases"]:
                if len(phrase) <= len(tokens) and _subseq(tuple(phrase), tokens):
                    matched[group].add(key)
                    break

    windows: list[dict[str, Any]] = []
    for bucket, stamp in enumerate(stamps):
        prefix = f"{stamp}:"
        local_numerators: dict[str, int] = {}
        for group in groups:
            eligible = matched[group]
            if specs[group].get("anchor") == "india":
                eligible = eligible & india_docs
            count = sum(1 for key in eligible if key.startswith(prefix))
            if count > denominators[stamp]:
                # Matched documents the denominator query never saw mean the
                # two queries disagree about the window; never clamp that.
                _fail("bq_backfill_numerator_exceeds_denominator")
            local_numerators[group] = count
        windows.append(
            {
                "bucket": bucket,
                "window_start_utc": (
                    f"{day.isoformat()}T{bucket // 2:02d}:{(bucket % 2) * 30:02d}:00Z"
                ),
                "row_count": discovered[stamp],
                "english_denominator": denominators[stamp],
                "group_numerators": dict(sorted(local_numerators.items())),
            }
        )
    return {"stamps": stamps, "windows": windows}


def aggregate_sides(
    windows: list[dict[str, Any]], specs: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    groups = sorted(specs)
    totals = {
        group: sum(int(row["group_numerators"][group]) for row in windows)
        for group in groups
    }
    denominator = sum(int(row["english_denominator"]) for row in windows)
    shares = {
        group: round(100.0 * totals[group] / denominator, 6) for group in groups
    }
    channel_sums: dict[str, float] = {}
    for group in groups:
        channel = str(specs[group]["channel"])
        channel_sums[channel] = channel_sums.get(channel, 0.0) + shares[group]
    return {
        "english_denominator": denominator,
        "group_numerators": totals,
        "shares": shares,
        "channel_sums": channel_sums,
    }


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def method_bindings(
    specs: Mapping[str, dict[str, Any]], *, root: Path = ROOT
) -> dict[str, Any]:
    canonical_specs = json.loads(ngram_bq_attestation.canonical_bytes(specs))
    return {
        "profile_sha256": _sha256_path(root / ngram_bq_attestation.PROFILE_RELATIVE),
        "schema_sha256": _sha256_path(root / ngram_bq_attestation.SCHEMA_RELATIVE),
        "dictionaries_sha256": _sha256_path(root / "dictionaries.json"),
        "production_matcher_sha256": _sha256_path(root / "src/fetch_ngrams_bq.py"),
        "validator_sha256": _sha256_path(root / "src/ngram_bq_attestation.py"),
        "calibration_sha256": _sha256_path(root / "data/raw/ngram_calibration.json"),
        "matcher_specs": canonical_specs,
        "matcher_specs_sha256": ngram_bq_attestation.sha256(
            ngram_bq_attestation.canonical_bytes(canonical_specs)
        ),
    }


def build_equivalence_proof(
    *,
    day: date,
    specs: Mapping[str, dict[str, Any]],
    windows: list[dict[str, Any]],
    published_reference: dict[str, Any],
    provenance: dict[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    recomputation = aggregate_sides(windows, specs)
    # A sealed mismatch record is still a product — the lane commits it for
    # the public record — but the validator refuses it as authorization.
    return ngram_bq_attestation.seal(
        {
            "schema_version": ngram_bq_attestation.SCHEMA_VERSION,
            "profile_id": ngram_bq_attestation.PROFILE_ID,
            "kind": "bq_equivalence_proof",
            "day": day.isoformat(),
            "published_reference": published_reference,
            "bq_recomputation": recomputation,
            "exact_match": published_reference == recomputation,
            "bq_provenance": provenance,
            "method_bindings": method_bindings(specs, root=root),
        }
    )


def build_backfill_attestation(
    *,
    day: date,
    specs: Mapping[str, dict[str, Any]],
    windows: list[dict[str, Any]],
    equivalence_day: date,
    equivalence_record_sha256: str,
    provenance: dict[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    sides = aggregate_sides(windows, specs)
    attestation = ngram_bq_attestation.seal(
        {
            "schema_version": ngram_bq_attestation.SCHEMA_VERSION,
            "profile_id": ngram_bq_attestation.PROFILE_ID,
            "day": day.isoformat(),
            "acquisition_regime": ngram_bq_attestation.ACQUISITION_REGIME,
            "refusal_disclosure": {
                "ledger_path": (
                    ngram_bq_attestation.REFUSAL_LEDGER_RELATIVE
                    / f"{day.isoformat()}.json"
                ).as_posix(),
                "reason_code": "source_acquisition_failed",
            },
            "equivalence_binding": {
                "day": equivalence_day.isoformat(),
                "proof_path": (
                    ngram_bq_attestation.EQUIVALENCE_RELATIVE
                    / f"{equivalence_day.isoformat()}.json"
                ).as_posix(),
                "proof_record_sha256": equivalence_record_sha256,
            },
            "expected_windows": SAMPLES_PER_DAY,
            "located_windows": len(windows),
            "loaded_windows": len(windows),
            "bq_provenance": provenance,
            "method_bindings": method_bindings(specs, root=root),
            "windows": windows,
            "aggregate_reconstruction": {
                "window_order": list(range(SAMPLES_PER_DAY)),
                **sides,
            },
            "membership_reproducibility": ngram_bq_attestation.MEMBERSHIP_LIMIT,
        }
    )
    return attestation
