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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, NoReturn, cast

from . import (
    fetch_ngrams,
    ngram_daily_attestation,
    ngram_rights,
    precision_frame_v3,
    provenance,
)

ROOT = Path(__file__).resolve().parents[1]
STATUS_RELATIVE = Path("data/raw/final_publication_status.json")
RECEIPTS_RELATIVE = Path("data/raw/final_publication_receipts")
LEGACY_AGGREGATE_RECEIPTS_RELATIVE = Path("data/raw/legacy_aggregate_verification")
_LEGACY_PROTECTED_PATHS = (
    "data/raw/ngram_days/2026-08-09.json",
    "data/raw/gdelt_volume.csv",
    "data/raw/provenance.csv",
    "docs/data/latest.json",
    "docs/data/history.json",
)
_LEGACY_RECEIPT_FIELDS = {
    "schema_version",
    "status",
    "target_date",
    "profile_id",
    "aggregate_attestation",
    "legacy_bytes_sha256",
    "transform",
    "rights",
    "original_bytes_rewritten",
    "public_score_claim_added",
    "membership_reproducibility",
    "record_sha256",
}

_LEGACY_AUG9_DAY = date(2026, 8, 9)
_LEGACY_AUG9_INTRODUCTION = "9077ea4f27b4662ed6651828ee28183eed8fc727"
_LEGACY_AUG9_BLOBS = {
    "data/raw/ngram_days/2026-08-09.json": (
        "1d14bd7e4e2151b77709857fc184d65569b6703942c2763777aa89f816f4250b"
    ),
    "data/raw/gdelt_volume.csv": (
        "ad4766d872ca5ed95b8d1efe729480016e46040816be21ad32d02cc9984eb065"
    ),
    "data/raw/provenance.csv": ("940281c3e0c2f898dc246f41e2f0dbe42cb690ed1f2c2968fb0676cd5b0e9ad1"),
    "data/raw/ngram_calibration.json": (
        "02efb5a493878701f1890802133ee395e6e1775028c33f8986b0043235e87c2e"
    ),
    "dictionaries.json": ("4f5d3333cad6d7b708c3b7d855f5fcc636b0ef2243f56f8e58def9f754d99b40"),
    "docs/data/latest.json": ("2af2170bd58fbcf98d4285124f2fede5d6a5d01628cc8674eaf4055acb37e049"),
    "docs/data/history.json": ("672d240e167ee95f3363395445cdf4ab98a0dcf5d89c5071f65d85d12329bdfe"),
    "docs/data/history.csv": ("b43ec447d9b009c18ffe9b20620a5bec9dfddb237bb33011e5fb2884bcc3ca9b"),
    "docs/data/shares.csv": ("c0bd5d30d81958c1d7e81cfc90fb98fed76d11cec31a24214a57d8685223317c"),
    "docs/data/shares.json": ("e34cec407d2ad9393eb03e723c2a42a70ce20ebdc43c27017757c4c91b606941"),
    "docs/data/assistant_answers.json": (
        "49b409a349d69e60a91688baabab066cdccb9f49069591bc7035799692624bb3"
    ),
    "docs/data/detection_baselines.json": (
        "f8c440223d8c37e63748a34280e75ac9e61d962dad39b1d25d7e4e70f775edc6"
    ),
    "docs/data/detector_blindness.json": (
        "b7ac0a46387acd2626e8d3f8a34c6cbc5c42aff364854cc9846f0205c11dcc6b"
    ),
    "docs/data/episode_actors.json": (
        "86f94c4a9977d79675ba09e5ef292f24150e3ff585a357dc8dec5ab916f64220"
    ),
    "docs/data/event_study.csv": (
        "1a6c492b33f14c6c8a42e6859091c1b05238b5aec878952a9bb912aebadacf5b"
    ),
    "docs/data/event_study.json": (
        "b99b1fbf04954121d4361b76d756ea5c30b6548f551fba9c1a9493901fa8bec7"
    ),
    "docs/data/exposure_sectors.json": (
        "6b6b6e2daf0d4a4216404c8ec64bb8d31e8c3c8f50426ae9e7c9705360388f9a"
    ),
    "docs/data/monthly.csv": ("3433e7ab806d2d12aa850d67fe0ac5fa084c81d943af2fc4f4921f522af27b2d"),
    "docs/data/monthly.json": ("1f59a74e46246d603b22917d2d85b48b3355c04167d59b20d643bab34081c9d5"),
    "docs/data/negative_results.json": (
        "1e8679d50f5175fa382c5d81542f32cc67eb3143750761de72d7e69c8c9954c8"
    ),
    "docs/data/outlet_drift.json": (
        "2069d8fd6dcd25c311aa1bd1e650c87fb047ba90910e703802a6affc8b525452"
    ),
    "docs/data/predictability.json": (
        "8d32459b5064b47787a38ed9c7059cc913411d53cfb4a6a9b0119392c79f56e9"
    ),
    "docs/data/splice_sensitivity.json": (
        "fe0cc510309b38fd21471c1e775c6f02624b69f11cc592f0395828c6e710c333"
    ),
    "docs/feed.xml": ("8a8d3af902870f11d3cb1860685ab72664d97772ba2802a79b764e7f4811cc3e"),
}
_LEGACY_AUG9_HISTORICAL_BLOBS = {
    # This pins the matcher that produced the cache at its introduction
    # commit. The live matcher legitimately evolved to schema 1.1 afterward,
    # so it is not part of the unchanged public value-surface history below.
    "src/fetch_ngrams.py": ("0cbf9e9837e5d6bb51ddb558a4cd3397953907e9a4ba44133292fd7441629e39"),
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
_VALUE_FREE_REFUSAL_PATHS = {
    "data/raw/final_publication_status.json",
    "docs/data/status.json",
    "docs/index.html",
    "docs/status.html",
}
# One durable value-free record per refused day. The single status marker is
# overwritten by every later run, so it cannot carry skip authority: the
# first Aug-12 attempt overwrote the Aug-11 disclosure that had authorized
# it, the selector snapped back, and the lane crashed on its own ordering
# check (run 31720836972). The ledger file survives marker turnover and is
# byte-pinned like every other receipt.
REFUSAL_LEDGER_RELATIVE = Path("data/raw/final_publication_refusals")


def value_free_refusal_paths(target: date) -> set[str]:
    """Every path a value-free refusal for ``target`` may write."""

    return set(_VALUE_FREE_REFUSAL_PATHS) | {
        (REFUSAL_LEDGER_RELATIVE / f"{target.isoformat()}.json").as_posix()
    }
_PUBLIC_API_BYTE_MANIFEST_PATH = "docs/data/public_api_byte_manifest.json"
_REFUSAL_REASONS = {
    "source_unavailable": (
        "source",
        "source_unavailable",
        "The registered source returned no eligible target-day frame.",
    ),
    "source_acquisition_failed": (
        "source",
        "acquisition_failed",
        "The registered source acquisition did not complete its bounded step.",
    ),
    "pipeline_validation_failed": (
        "pipeline",
        "pipeline_failed",
        "The exact D-1 candidate did not complete pipeline validation.",
    ),
    "audit_validation_failed": (
        "audit",
        "pipeline_failed",
        "The exact D-1 candidate did not complete audit validation.",
    ),
    "derived_validation_failed": (
        "derived",
        "pipeline_failed",
        "The exact D-1 candidate did not complete derived-output validation.",
    ),
}
_REFUSAL_DEFAULT_CODES = {
    "source": "source_acquisition_failed",
    "pipeline": "pipeline_validation_failed",
    "audit": "audit_validation_failed",
    "derived": "derived_validation_failed",
}


def _prefix_gap_is_disclosed(root: Path, last_day: date, target: date) -> bool:
    """True when every day in (last_day, target) is a disclosed lost day.

    Contiguity is enforced at three independent layers (the ordered-target
    prefix, the volume store, and the provenance ledger). All three accept
    the same and only exception: a gap day whose durable refusal ledger
    entry records a published SOURCE-stage refusal. Anything else keeps the
    strict append-only rule.
    """

    gap_day = last_day + timedelta(days=1)
    while gap_day < target:
        try:
            entry = json.loads(
                (
                    root
                    / REFUSAL_LEDGER_RELATIVE
                    / f"{gap_day.isoformat()}.json"
                ).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return False
        if not (
            entry.get("target_date") == gap_day.isoformat()
            and entry.get("failure_stage") == "source"
            and entry.get("reason_code") == "source_acquisition_failed"
        ):
            return False
        gap_day = gap_day + timedelta(days=1)
    return True


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
    aggregate_profile: bytes
    aggregate_schema: bytes
    aggregate_validator: bytes
    rights_registry: bytes
    rights_signers: bytes
    rights_decision_files: dict[str, bytes]
    rights_authority: ngram_rights.NonGitTestRightsAuthority


@dataclass(frozen=True)
class _ParentSnapshot:
    commit: str
    store: bytes
    provenance: bytes
    calibration: bytes
    dictionaries: bytes
    matcher: bytes
    aggregate_profile: bytes
    aggregate_schema: bytes
    aggregate_validator: bytes
    rights_registry: bytes
    rights_signers: bytes
    rights_decision_files: dict[str, bytes]
    rights_authority: ngram_rights.NonGitTestRightsAuthority | None


def _fail(classification: str, detail: str = "") -> NoReturn:
    raise FinalPublicationError(classification, detail)


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def required_target(today: date | None = None) -> date:
    return (today or utc_today()) - timedelta(days=1)


def required_next_target(*, root: Path = ROOT, today: date | None = None) -> date | None:
    """Return the sole ordered backlog day eligible for the next commit.

    This never skips an UNDISCLOSED day and never includes UTC D0. The caller
    must re-run it from the newly fetched remote tip after every publication.

    A day whose committed marker records a published SOURCE-stage refusal
    disclosure, and which has aged at least one full day past D-1 (so a
    transient provider outage had a full extra day of retries), advances the
    pointer by exactly one day. Without this, one permanently lost provider
    day livelocks every later publication: the 2026-08-11 Web NGrams files
    left the provider's temporary window and the lane republished the same
    honest refusal forever while 2026-08-12 could never be attempted. The
    skipped day is not silent -- its refusal disclosure is the published
    record -- and infrastructure failures (pipeline/derived/gate stages)
    never advance, because those are retryable defects, not lost sources.
    """

    latest = _read_latest_day(root)
    contract_today = today or utc_today()
    ceiling = required_target(today)
    if latest is None:
        _fail("final_target_invalid", "latest_finalized_day_unreadable")
    if latest == _LEGACY_AUG9_DAY and not _legacy_upgrade_receipt_is_bound(root):
        return _LEGACY_AUG9_DAY
    candidate = latest + timedelta(days=1)
    if candidate > ceiling:
        return None
    # Walk past EVERY consecutive disclosed lost-source day, not just one.
    # A single-step advance oscillated at the second of two consecutive
    # disclosed days (run 31757958830 re-refused Aug 12 while Aug 13 could
    # never be attempted), and the gap would then compound daily. Each
    # skipped day already carries its own published disclosure; the walk is
    # bounded by the ceiling and only crosses aged SOURCE-stage refusals.
    while candidate <= ceiling:
        ledger_path = (
            root / REFUSAL_LEDGER_RELATIVE / f"{candidate.isoformat()}.json"
        )
        try:
            entry = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            entry = {}
        disclosed_lost_source = (
            entry.get("target_date") == candidate.isoformat()
            and entry.get("failure_stage") == "source"
            and entry.get("reason_code") == "source_acquisition_failed"
            and candidate <= contract_today - timedelta(days=2)
        )
        if not disclosed_lost_source:
            return candidate
        candidate = candidate + timedelta(days=1)
    return None


def _legacy_upgrade_receipt_is_bound(root: Path) -> bool:
    try:
        _validated_legacy_receipt(root)
    except (
        FinalPublicationError,
        ngram_daily_attestation.AggregateAttestationError,
    ):
        return False
    return True


def _legacy_blob(root: Path, relative: str) -> bytes:
    commit = _git_head(root)
    if commit is not None:
        return _git_regular_blob(
            root,
            commit,
            relative,
            classification="legacy_verification_invalid",
            detail="legacy_blob_not_regular",
        )
    path = root / relative
    try:
        if path.is_symlink() or not path.is_file() or (path.stat().st_mode & 0o111):
            _fail("legacy_verification_invalid", f"legacy_blob_not_regular:{relative}")
        return path.read_bytes()
    except OSError as exc:
        raise FinalPublicationError(
            "legacy_verification_invalid", f"legacy_blob_missing:{relative}"
        ) from exc


def _validated_legacy_receipt(root: Path) -> dict[str, Any]:
    relative = (
        LEGACY_AGGREGATE_RECEIPTS_RELATIVE / f"{_LEGACY_AUG9_DAY}.json"
    ).as_posix()
    raw = _legacy_blob(root, relative)
    try:
        receipt = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError(
            "legacy_verification_invalid", "receipt_unreadable"
        ) from exc
    if not isinstance(receipt, dict) or set(receipt) != _LEGACY_RECEIPT_FIELDS:
        _fail("legacy_verification_invalid", "receipt_fields_invalid")
    body = {key: value for key, value in receipt.items() if key != "record_sha256"}
    if receipt["record_sha256"] != _sha256(_canonical_bytes(body)):
        _fail("legacy_verification_invalid", "receipt_seal_invalid")
    hashes = receipt["legacy_bytes_sha256"]
    transform = receipt["transform"]
    if (
        receipt["schema_version"] != "1.1.0"
        or receipt["status"] != "legacy_verified_under_aggregate_profile"
        or receipt["target_date"] != _LEGACY_AUG9_DAY.isoformat()
        or receipt["profile_id"] != ngram_daily_attestation.PROFILE_ID
        or receipt["original_bytes_rewritten"] is not False
        or receipt["public_score_claim_added"] is not False
        or receipt["membership_reproducibility"]
        != ngram_daily_attestation.MEMBERSHIP_LIMIT
        or not isinstance(hashes, dict)
        or set(hashes) != set(_LEGACY_PROTECTED_PATHS)
        or not isinstance(transform, dict)
        or set(transform)
        != {"calibration_sha256", "channel_values", "matched_existing_row"}
        or transform["matched_existing_row"] is not True
    ):
        _fail("legacy_verification_invalid", "receipt_identity_invalid")
    protected = {path: _legacy_blob(root, path) for path in _LEGACY_PROTECTED_PATHS}
    if any(
        not isinstance(hashes[path], str)
        or not re.fullmatch(r"[0-9a-f]{64}", hashes[path])
        or _sha256(protected[path]) != hashes[path]
        for path in _LEGACY_PROTECTED_PATHS
    ):
        _fail("legacy_verification_invalid", "legacy_bound_byte_mismatch")
    attestation = ngram_daily_attestation.validate(
        receipt["aggregate_attestation"],
        target=_LEGACY_AUG9_DAY,
        specs=fetch_ngrams._canonical_specs(fetch_ngrams.group_specs()),
        root=root,
        expected_calibration_sha256=transform["calibration_sha256"],
    )
    calibration_raw = _legacy_blob(root, "data/raw/ngram_calibration.json")
    if _sha256(calibration_raw) != transform["calibration_sha256"]:
        _fail("legacy_verification_invalid", "calibration_binding_mismatch")
    calibration = json.loads(calibration_raw)
    channel_sums = attestation["aggregate_reconstruction"]["channel_sums"]
    expected_values = {
        channel: channel_sums[channel] / float(calibration[channel]["ratio"])
        for channel in channel_sums
    }
    if transform["channel_values"] != expected_values:
        _fail("legacy_verification_invalid", "legacy_transform_value_mismatch")
    rows = list(
        csv.DictReader(io.StringIO(protected["data/raw/gdelt_volume.csv"].decode("utf-8")))
    )
    observed = [row for row in rows if row.get("date") == _LEGACY_AUG9_DAY.isoformat()]
    if len(observed) != 1 or any(
        float(observed[0][channel]) != value for channel, value in expected_values.items()
    ):
        _fail("legacy_verification_invalid", "legacy_target_row_mismatch")
    _validated_bound_aggregate_rights(receipt["rights"], _LEGACY_AUG9_DAY)
    return cast(dict[str, Any], receipt)


def require_ordered_target(target: date, *, root: Path = ROOT, today: date | None = None) -> None:
    expected = required_next_target(root=root, today=today)
    if expected is None or target != expected:
        _fail(
            "final_target_invalid",
            "target_is_not_exact_next_unpublished_day_before_utc_d0",
        )


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
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


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


def _git_regular_blob(
    root: Path,
    commit: str,
    relative: str,
    *,
    classification: str,
    detail: str,
) -> bytes:
    """Read one exact committed non-executable regular-file blob."""

    result = subprocess.run(
        ["git", "ls-tree", "-z", "--full-tree", commit, "--", relative],
        cwd=root,
        capture_output=True,
    )
    records = result.stdout.split(b"\0")
    if result.returncode != 0 or records[-1] or len(records) != 2:
        _fail(classification, f"{detail}:{relative}")
    try:
        metadata, encoded_path = records[0].split(b"\t", 1)
        mode, object_type, object_id = metadata.split(b" ")
        decoded_path = encoded_path.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise FinalPublicationError(classification, f"{detail}:{relative}") from exc
    if (
        mode != b"100644"
        or object_type != b"blob"
        or re.fullmatch(rb"[0-9a-f]{40,64}", object_id) is None
        or decoded_path != relative
    ):
        _fail(classification, f"{detail}:{relative}")
    return _git_blob(root, commit, relative)


def _git_blob_oid(root: Path, commit: str, relative: str) -> str | None:
    """Return a path's blob identity at one commit, including absence."""

    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commit}:{relative}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if result.returncode != 0:
        return None
    return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else None


def _first_parent_path_never_changed(
    root: Path,
    introduction: str,
    head: str,
    relative: str,
) -> bool:
    """Require byte identity at every first-parent transition after intro."""

    chain: list[tuple[str, str]] = []
    current = head
    while current != introduction:
        result = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", current],
            cwd=root,
            capture_output=True,
            text=True,
        )
        parts = result.stdout.split()
        if result.returncode != 0 or not parts or parts[0] != current or len(parts) < 2:
            return False
        first_parent = parts[1]
        chain.append((first_parent, current))
        current = first_parent
    for parent, child in reversed(chain):
        if _git_blob_oid(root, parent, relative) != _git_blob_oid(root, child, relative):
            return False
    return True


def _first_parent_index_surface_never_changed(
    root: Path,
    introduction: str,
    head: str,
    expected: tuple[str, ...],
) -> bool:
    """Allow UX evolution while refusing any historical SSR value drift."""

    current = head
    while True:
        try:
            surface = _legacy_index_value_surface(_git_blob(root, current, "docs/index.html"))
        except FinalPublicationError:
            return False
        if surface != expected:
            return False
        if current == introduction:
            return True
        result = subprocess.run(
            ["git", "rev-list", "--parents", "-n", "1", current],
            cwd=root,
            capture_output=True,
            text=True,
        )
        parts = result.stdout.split()
        if result.returncode != 0 or not parts or parts[0] != current or len(parts) < 2:
            return False
        current = parts[1]


def _legacy_index_value_surface(raw: bytes) -> tuple[str, ...] | None:
    """Extract the closed SSR value surface and reject unregistered claims."""

    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return None
    scalar_patterns = (
        r'id="latest-date">([^<]+)</span>',
        r'id="composite-score"[^>]*>([^<]+)</p>',
        r'id="composite-delta">([^<]+)</p>',
    )
    scalars: list[str] = []
    for pattern in scalar_patterns:
        values = re.findall(pattern, text)
        if len(values) != 1:
            return None
        scalars.append(values[0])
    components = re.findall(
        r'<a class="component-row" href="receipts\.html\?channel=[^"]+">.*?</a>',
        text,
    )
    if len(components) != 5:
        return None
    scrubbed = text
    status_pattern = (
        r"<!--final-publication-static:start-->.*?"
        r"<!--final-publication-static:end-->"
    )
    status_regions = re.findall(status_pattern, scrubbed, flags=re.DOTALL)
    if len(status_regions) > 1:
        return None
    scrubbed = re.sub(status_pattern, "", scrubbed, flags=re.DOTALL)
    registered_patterns = (
        r'<p[^>]*id="composite-label"[^>]*>.*?</p>',
        r'<p[^>]*id="composite-score"[^>]*>.*?</p>',
        r'<p[^>]*id="composite-delta"[^>]*>.*?</p>',
        r"<!--ssr:components-->.*?<!--/ssr:components-->",
    )
    for pattern in registered_patterns:
        scrubbed, count = re.subn(pattern, "", scrubbed, count=1, flags=re.DOTALL)
        if count != 1:
            return None
    if _contains_unregistered_final_claim(scrubbed):
        return None
    return (*scalars, *components)


def _contains_unregistered_final_claim(text: str) -> bool:
    """Refuse score/date claims outside the registered SSR slots.

    Contexts cover reader prose, tables, metadata, ordinary DOM containers,
    and JSON-LD.  Registered headline/component/status regions are removed by
    the caller before this scan, so any remaining official/final/latest
    numeric claim is an unregistered public mirror.
    """

    parser = _LegacyClaimContextParser()
    try:
        parser.feed(text)
        parser.close()
    except (AssertionError, ValueError):
        return True
    contexts = parser.claim_contexts()
    number = r"(?:\b\d{4}-\d{2}-\d{2}\b|(?<![\w])[-+]?\d+(?:\.\d+)?%?)"
    official_claim = re.compile(
        r"(?is)(?=.*(?:official|final(?:ized)?|latest))"
        r"(?=.*(?:score|composite|measure|date|channel))"
        rf"(?=.*{number})"
    )
    direct_claim = re.compile(
        rf"(?is)(?:composite|(?:pakistan|china|gulf|energy|trade|shipping)"
        rf"(?:\s+channel)?(?:\s+score)?)\s*(?:is|=|:|·)\s*{number}"
    )
    return any(
        official_claim.search(context) or direct_claim.search(context) for context in contexts
    )


@dataclass
class _LegacyClaimNode:
    tag: str
    attrs: list[tuple[str, str | None]]
    text: list[str]
    children: list[_LegacyClaimNode]
    parent: _LegacyClaimNode | None


class _LegacyClaimContextParser(HTMLParser):
    """Collect structurally local text so sibling-node claims cannot fragment.

    The registered value slots are removed before parsing.  Every remaining
    claim label is joined to its own subtree, its ancestors through the first
    semantic boundary, and any explicit ``aria-labelledby`` target.  That
    catches wrapped siblings without joining an unrelated year/licence fact
    from a distant outer section to the label "Latest final measure".
    """

    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _CLAIM_LABEL = re.compile(
        r"(?is)(?=.*(?:official|final(?:ized)?|latest))"
        r"(?=.*(?:score|composite|measure|date|channel))"
    )
    _SEMANTIC_BOUNDARY_TAGS = {
        "article",
        "aside",
        "dl",
        "main",
        "nav",
        "section",
        "table",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._root = _LegacyClaimNode("#document", [], [], [], None)
        self._stack = [self._root]
        self._malformed = False

    @staticmethod
    def _attribute_text(attrs: list[tuple[str, str | None]]) -> str:
        return " ".join(f"{key} {value or ''}" for key, value in attrs)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        parent = self._stack[-1]
        node = _LegacyClaimNode(lowered, attrs, [], [], parent)
        parent.children.append(node)
        if lowered not in self._VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if normalized:
            self._stack[-1].text.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self._VOID_TAGS:
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag != lowered:
                continue
            if index != len(self._stack) - 1:
                self._malformed = True
            del self._stack[index:]
            return
        self._malformed = True

    def claim_contexts(self) -> list[str]:
        if self._malformed or len(self._stack) != 1:
            raise ValueError("malformed HTML claim surface")
        contexts: list[str] = []
        nodes: list[_LegacyClaimNode] = []
        ids: dict[str, _LegacyClaimNode] = {}
        subtree_cache: dict[int, str] = {}

        def walk(node: _LegacyClaimNode) -> None:
            for child in node.children:
                nodes.append(child)
                for key, value in child.attrs:
                    if key.lower() == "id" and value:
                        if value in ids:
                            raise ValueError("duplicate HTML id in claim surface")
                        ids[value] = child
                walk(child)

        def direct(node: _LegacyClaimNode) -> str:
            return " ".join(part for part in (self._attribute_text(node.attrs), *node.text) if part)

        def subtree(node: _LegacyClaimNode) -> str:
            cache_key = id(node)
            if cache_key not in subtree_cache:
                subtree_cache[cache_key] = " ".join(
                    part
                    for part in (
                        direct(node),
                        *(subtree(child) for child in node.children),
                    )
                    if part
                )
            return subtree_cache[cache_key]

        walk(self._root)
        for node in nodes:
            own = direct(node)
            if own:
                contexts.append(own)
            if self._CLAIM_LABEL.search(own):
                contexts.append(subtree(node))
                ancestor = node.parent
                while ancestor is not None:
                    contexts.append(subtree(ancestor))
                    if ancestor.tag in self._SEMANTIC_BOUNDARY_TAGS:
                        break
                    ancestor = ancestor.parent
            labelled_by = next(
                (value for key, value in node.attrs if key.lower() == "aria-labelledby" and value),
                None,
            )
            if labelled_by is not None:
                labels = [ids.get(identifier) for identifier in labelled_by.split()]
                # Registered value nodes are intentionally removed before
                # this scan, so references to one of those removed IDs are
                # expected to be unresolved.  Only a surviving label can
                # license a structural join in the residual surface.
                if any(label is None for label in labels):
                    continue
                label_context = " ".join(subtree(label) for label in labels if label is not None)
                if self._CLAIM_LABEL.search(label_context):
                    contexts.append(f"{label_context} {subtree(node)}")
        return contexts


def _rights_decision_paths(registry_raw: bytes) -> list[str]:
    try:
        registry = json.loads(registry_raw)
        sources = registry.get("sources")
    except (UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(sources, list):
        return []
    for source in sources:
        if isinstance(source, dict) and source.get("source_id") == ngram_rights.SOURCE_ID:
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
        aggregate_profile=(root / ngram_daily_attestation.PROFILE_RELATIVE).read_bytes(),
        aggregate_schema=(root / ngram_daily_attestation.SCHEMA_RELATIVE).read_bytes(),
        aggregate_validator=(root / "src/ngram_daily_attestation.py").read_bytes(),
        rights_registry=rights_registry,
        rights_signers=(root / "governance/rights_signers.json").read_bytes(),
        rights_decision_files=decision_files,
        rights_authority=ngram_rights.non_git_test_authority(root),
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
    rights_registry = _git_blob(root, commit, "governance/source_rights_registry.json")
    return _ParentSnapshot(
        commit=commit,
        store=_git_blob(root, commit, "data/raw/gdelt_volume.csv"),
        provenance=_git_blob(root, commit, "data/raw/provenance.csv"),
        calibration=_git_blob(root, commit, "data/raw/ngram_calibration.json"),
        dictionaries=_git_blob(root, commit, "dictionaries.json"),
        matcher=_git_blob(root, commit, "src/fetch_ngrams.py"),
        aggregate_profile=_git_blob(
            root, commit, ngram_daily_attestation.PROFILE_RELATIVE.as_posix()
        ),
        aggregate_schema=_git_blob(
            root, commit, ngram_daily_attestation.SCHEMA_RELATIVE.as_posix()
        ),
        aggregate_validator=_git_blob(root, commit, "src/ngram_daily_attestation.py"),
        rights_registry=rights_registry,
        rights_signers=_git_blob(root, commit, "governance/rights_signers.json"),
        rights_decision_files={
            relative: _git_blob(root, commit, relative)
            for relative in _rights_decision_paths(rights_registry)
        },
        rights_authority=None,
    )


def require_ngram_public_identity_rights(
    *,
    target: date,
    root: Path = ROOT,
    non_git_test_rights: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Translate the shared processing refusal into publication terminology."""

    try:
        return ngram_rights.require_public_identity_rights(
            target=target,
            root=root,
            test_authority=non_git_test_rights,
        )
    except ngram_rights.NgramRightsError as exc:
        _fail("rights_not_authorized", exc.code)


def require_ngram_daily_aggregate_rights(
    *,
    target: date,
    root: Path = ROOT,
    non_git_test_rights: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Translate the narrow aggregate-processing refusal."""

    try:
        return ngram_rights.require_daily_aggregate_rights(
            target=target,
            root=root,
            test_authority=non_git_test_rights,
        )
    except ngram_rights.NgramRightsError as exc:
        _fail("rights_not_authorized", exc.code)


_RIGHTS_EVALUATION_FIELDS = {
    "evaluated_at_utc",
    "rights_as_of",
    "evaluated_age_days",
}


def _validated_bound_rights(value: object, target: date) -> dict[str, Any]:
    try:
        return ngram_rights.validate_public_identity_rights_proof(value, target=target)
    except ngram_rights.NgramRightsError as exc:
        _fail("promotion_receipt_invalid", exc.code)


def _validated_bound_aggregate_rights(value: object, target: date) -> dict[str, Any]:
    try:
        return ngram_rights.validate_daily_aggregate_rights_proof(value, target=target)
    except ngram_rights.NgramRightsError as exc:
        _fail("promotion_receipt_invalid", exc.code)


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

    originals = {path: path.read_bytes() if path.exists() else None for path, _ in writes}
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
    """Validate the prospective 48/48 aggregate-only source profile."""

    specs = fetch_ngrams._canonical_specs(fetch_ngrams.group_specs())
    calibration_sha = _sha256((root / "data/raw/ngram_calibration.json").read_bytes())
    attestation = ngram_daily_attestation.validate(
        result.get("_aggregate_attestation"),
        target=target,
        specs=specs,
        root=root,
        expected_calibration_sha256=calibration_sha,
    )
    reconstruction = attestation["aggregate_reconstruction"]
    if (
        result.get("date") != target.isoformat()
        or result.get("n_samples") != ngram_daily_attestation.EXPECTED_WINDOWS
        or result.get("n_samples_loaded") != ngram_daily_attestation.EXPECTED_WINDOWS
        or result.get("partial") is not False
        or result.get("n_docs_sampled") != reconstruction["english_denominator"]
        or result.get("shares") != reconstruction["shares"]
    ):
        _fail("acquisition_failed", "aggregate_result_binding_invalid")
    return attestation


def _calibration(root: Path, channels: list[str]) -> tuple[bytes, dict[str, dict[str, Any]]]:
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
    # The store prefix must reach target-1 either by finalized rows or by
    # disclosed lost days: every missing day between the last stored row and
    # the target must carry its own published SOURCE-stage refusal ledger
    # entry. Without this third-layer relaxation the store stalled at the
    # last finalized day exactly like the selector and the D-2 prefix did
    # (local replay of 2026-08-13 over the 08-11/12 disclosed gaps).
    if not _prefix_gap_is_disclosed(root, days[-1], target):
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
    if any(day >= target for day in days) or not _prefix_gap_is_disclosed(
        root, days[-1], target
    ):
        _fail("acquisition_failed", "provenance_not_target_append_only")
    line_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(line_buffer, fieldnames=provenance.FIELDS, lineterminator="\n")
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
    source_cache_sha256: str,
) -> dict[str, Any]:
    evidence = result["_aggregate_attestation"]
    return {
        "schema_version": "1.0.0",
        "receipt_id": f"igrm:final-publication:{target.isoformat()}",
        "target_date": target.isoformat(),
        "base_commit": base_commit,
        "status": "eligible_immutable_target_candidate",
        "source": provenance.NGRAM_BRIDGE,
        "frame": {
            "validator": "src.ngram_daily_attestation.validate",
            "attestation_sha256": _sha256(_canonical_bytes(attestation)),
            "source_cache_sha256": source_cache_sha256,
            "n_samples_located": attestation["located_windows"],
            "n_samples_loaded": attestation["loaded_windows"],
            "missing_stamps": [],
            "profile_id": ngram_daily_attestation.PROFILE_ID,
            "document_membership_retained": False,
        },
        "bindings": {
            "calibration_sha256": _sha256(calibration_raw),
            "calibration_records_sha256": {
                channel: _sha256(_canonical_bytes(calibration[channel]))
                for channel in sorted(calibration)
            },
            "source_profile_sha256": evidence["method_bindings"]["profile_sha256"],
            "source_schema_sha256": evidence["method_bindings"]["schema_sha256"],
            "source_validator_sha256": evidence["method_bindings"]["validator_sha256"],
            "dictionary_sha256": evidence["method_bindings"]["dictionaries_sha256"],
            "matcher_sha256": evidence["method_bindings"]["production_matcher_sha256"],
            "matcher_specs_sha256": evidence["method_bindings"]["matcher_specs_sha256"],
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
        "document_membership_retained": False,
        "membership_reproducibility": ngram_daily_attestation.MEMBERSHIP_LIMIT,
    }


def verify_legacy_under_aggregate_profile(
    *,
    root: Path = ROOT,
    compute_day: Callable[
        [date, dict[str, dict[str, Any]]], dict[str, Any] | None
    ]
    | None = None,
    non_git_test_rights: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Re-acquire Aug-9 under profile 2.0 without rewriting legacy bytes."""

    target = _LEGACY_AUG9_DAY
    receipt_path = root / LEGACY_AGGREGATE_RECEIPTS_RELATIVE / f"{target}.json"
    if receipt_path.exists():
        existing = _validated_legacy_receipt(root)
        require_ngram_daily_aggregate_rights(
            target=target, root=root, non_git_test_rights=non_git_test_rights
        )
        return existing
    legacy_paths = tuple(Path(path) for path in _LEGACY_PROTECTED_PATHS)
    before = {path.as_posix(): (root / path).read_bytes() for path in legacy_paths}
    if not is_exact_legacy_cache_exception(
        root, target, cache_bytes=before[legacy_paths[0].as_posix()]
    ):
        _fail("legacy_verification_invalid", "registered_legacy_bytes_not_exact")
    require_ngram_daily_aggregate_rights(
        target=target, root=root, non_git_test_rights=non_git_test_rights
    )
    specs = fetch_ngrams.group_specs()
    producer = compute_day or fetch_ngrams.compute_day
    result = (
        fetch_ngrams.compute_day(target, specs, rights_authority=non_git_test_rights)
        if producer is fetch_ngrams.compute_day
        else producer(target, specs)
    )
    if result is None:
        _fail("legacy_verification_refused", "source_object_unavailable")
    require_ngram_daily_aggregate_rights(
        target=target, root=root, non_git_test_rights=non_git_test_rights
    )
    try:
        attestation = _validate_frame_candidate(target, result, root)
    except (FinalPublicationError, ngram_daily_attestation.AggregateAttestationError) as exc:
        _fail("legacy_verification_refused", f"aggregate_candidate_mismatch:{exc}")
    calibration_raw, calibration = _calibration(
        root, sorted({spec["channel"] for spec in specs.values()})
    )
    sums = fetch_ngrams._channel_sums(result, specs)
    with (root / "data/raw/gdelt_volume.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    observed = [row for row in rows if row.get("date") == target.isoformat()]
    if len(observed) != 1:
        _fail("legacy_verification_refused", "legacy_target_row_not_unique")
    expected = {channel: sums[channel] / float(calibration[channel]["ratio"]) for channel in sums}
    if any(float(observed[0][channel]) != value for channel, value in expected.items()):
        _fail("legacy_verification_refused", "legacy_transform_value_mismatch")
    write_rights = require_ngram_daily_aggregate_rights(
        target=target, root=root, non_git_test_rights=non_git_test_rights
    )
    receipt_body = {
        "schema_version": "1.1.0",
        "status": "legacy_verified_under_aggregate_profile",
        "target_date": target.isoformat(),
        "profile_id": ngram_daily_attestation.PROFILE_ID,
        "aggregate_attestation": attestation,
        "legacy_bytes_sha256": {path: _sha256(raw) for path, raw in sorted(before.items())},
        "transform": {
            "calibration_sha256": _sha256(calibration_raw),
            "channel_values": expected,
            "matched_existing_row": True,
        },
        "rights": write_rights,
        "original_bytes_rewritten": False,
        "public_score_claim_added": False,
        "membership_reproducibility": ngram_daily_attestation.MEMBERSHIP_LIMIT,
    }
    receipt = {
        **receipt_body,
        "record_sha256": _sha256(_canonical_bytes(receipt_body)),
    }
    _atomic_write(receipt_path, _json_bytes(receipt))
    after = {path: (root / path).read_bytes() for path in before}
    if after != before:
        _fail("legacy_verification_invalid", "legacy_bytes_changed")
    return receipt


def acquire_target(
    target: date,
    *,
    today: date | None = None,
    root: Path = ROOT,
    base_commit: str | None = None,
    compute_day: Callable[
        [date, dict[str, dict[str, Any]]], dict[str, Any] | None
    ]
    | None = None,
    non_git_test_rights: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, Any]:
    """Acquire, validate and atomically bank one exact ordered daily frame.

    A refusal writes only the value-free status record.  The score store,
    production cache, provenance and transform receipt remain byte-identical.
    """

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
    require_ordered_target(target, root=root, today=today)
    # The immutable prefix rule, completed for disclosed lost days: every
    # day between the latest finalized day and the target must either BE
    # the finalized prefix or carry its own aged, published SOURCE-stage
    # refusal disclosure in the durable ledger. The selector already walks
    # such days (required_next_target); refusing them again here stalled
    # the chain at the last finalized day forever while holes accumulated
    # ahead of it (run 31759753420: target 2026-08-13 refused instantly
    # because 2026-08-11/12 are disclosed gaps, so latest stays 2026-08-10).
    if latest is None or not _prefix_gap_is_disclosed(root, latest, target):
        return record_status(
            target,
            "acquisition_failed",
            "latest finalized day is not the target's immutable D-2 prefix",
            root=root,
            base_commit=frozen_commit,
        )

    # Profile 2.0 retains aggregate counts and exact source-object commitments,
    # never document identities or source content. Refuse before the first
    # source request unless the exact narrow aggregate operation is covered by
    # an applicable signed human decision.
    try:
        rights_proof = require_ngram_daily_aggregate_rights(
            target=target,
            root=root,
            non_git_test_rights=non_git_test_rights,
        )
    except FinalPublicationError as exc:
        return record_status(
            target,
            "acquisition_failed",
            f"registered ngram aggregate processing refused: {exc.detail}",
            root=root,
            base_commit=frozen_commit,
        )

    specs = fetch_ngrams.group_specs()
    try:
        if compute_day is None or compute_day is fetch_ngrams.compute_day:
            result = fetch_ngrams.compute_day(target, specs, rights_authority=non_git_test_rights)
        else:
            result = compute_day(target, specs)
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
        rights_proof = require_ngram_daily_aggregate_rights(
            target=target,
            root=root,
            non_git_test_rights=non_git_test_rights,
        )
    except FinalPublicationError as exc:
        return record_status(
            target,
            "acquisition_failed",
            f"post-fetch ngram aggregate processing refused: {exc.detail}",
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
            channel: sums[channel] / float(calibration[channel]["ratio"]) for channel in channels
        }
        # Preserve the canonical store's registered channel order.
        with (root / "data/raw/gdelt_volume.csv").open(encoding="utf-8") as handle:
            store_fields = list(csv.DictReader(handle).fieldnames or [])[1:]
        calibrated = {channel: calibrated[channel] for channel in store_fields}
        store_prefix, store_candidate, row_sha = _store_candidate(root, target, calibrated)
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
            source_cache_sha256=_sha256(cache_bytes),
        )
    except (
        FinalPublicationError,
        ngram_daily_attestation.AggregateAttestationError,
    ) as exc:
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

    # Candidate preparation may itself span a policy boundary. Re-evaluate
    # immediately before the atomic bundle write and bind that latest proof.
    try:
        write_rights_proof = require_ngram_daily_aggregate_rights(
            target=target,
            root=root,
            non_git_test_rights=non_git_test_rights,
        )
    except FinalPublicationError as exc:
        return record_status(
            target,
            "acquisition_failed",
            f"candidate-write ngram aggregate processing refused: {exc.detail}",
            root=root,
            base_commit=frozen_commit,
        )
    receipt["bindings"]["rights"] = write_rights_proof
    receipt_path = RECEIPTS_RELATIVE / f"{target.isoformat()}.json"
    status = _status_payload(
        target,
        "target_ready",
        "a complete registered source frame is banked; final publication is pending",
        root=root,
        base_commit=frozen_commit,
        receipt={
            "path": receipt_path.as_posix(),
            # Pin the EXACT bytes the bundle writes (_json_bytes), not a
            # re-canonicalization: a pin a reader cannot verify with
            # sha256sum against the named file is not a byte pin, and the
            # repo-wide pin verifier refused the first value-advance
            # candidate on exactly this mismatch (run 31687324343).
            "sha256": _sha256(_json_bytes(receipt)),
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


def _require_parent_prefix(
    raw: bytes, target: date, label: str, *, root: Path = ROOT
) -> None:
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
        # The parent prefix may end earlier than target-1 ONLY across days
        # whose durable ledger discloses a published SOURCE-stage refusal:
        # the same single exception the selector, the D-2 check, the store
        # and the provenance layers accept (_prefix_gap_is_disclosed).
        or not _prefix_gap_is_disclosed(root, days[-1], target)
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
        raise FinalPublicationError("promotion_receipt_invalid", "provenance_unreadable") from exc
    target_provenance = [row for row in provenance_rows if row.get("date") == target.isoformat()]
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
        cache_raw = fetch_ngrams.read_daily_aggregate_cache(
            target,
            root=root,
            rights_authority=parent.rights_authority,
        )
        cache_payload = json.loads(cache_raw)
    except ngram_rights.NgramRightsError as exc:
        raise FinalPublicationError(
            "promotion_receipt_invalid", f"rights_not_authorized:{exc.code}"
        ) from exc
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
    if receipt.get("base_commit") != parent.commit or marker.get("base_commit") != parent.commit:
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
        or receipt_ref.get("sha256")
        != _sha256((root / RECEIPTS_RELATIVE / f"{target}.json").read_bytes())
    ):
        _fail("promotion_receipt_invalid", "target_ready_status_binding_invalid")

    try:
        specs = fetch_ngrams._canonical_specs(fetch_ngrams.group_specs())
        attestation = ngram_daily_attestation.validate(
            cache_payload.get("_aggregate_attestation"),
            target=target,
            specs=specs,
            root=root,
            expected_calibration_sha256=_sha256(calibration_raw),
        )
    except ngram_daily_attestation.AggregateAttestationError as exc:
        raise FinalPublicationError("promotion_receipt_invalid", f"frame_invalid:{exc}") from exc
    frame = receipt.get("frame")
    if not isinstance(frame, dict) or frame != {
        "validator": "src.ngram_daily_attestation.validate",
        "attestation_sha256": _sha256(_canonical_bytes(attestation)),
        "source_cache_sha256": _sha256(cache_raw),
        "n_samples_located": ngram_daily_attestation.EXPECTED_WINDOWS,
        "n_samples_loaded": ngram_daily_attestation.EXPECTED_WINDOWS,
        "missing_stamps": [],
        "profile_id": ngram_daily_attestation.PROFILE_ID,
        "document_membership_retained": False,
    }:
        _fail("promotion_receipt_invalid", "frame_binding_invalid")

    bindings = receipt.get("bindings")
    if not isinstance(bindings, dict):
        _fail("promotion_receipt_invalid", "transform_bindings_missing")
    bound_rights = _validated_bound_aggregate_rights(bindings.get("rights"), target)
    try:
        rights_proof = require_ngram_daily_aggregate_rights(
            target=target,
            root=root,
            non_git_test_rights=parent.rights_authority,
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
    bound_static = {
        key: value for key, value in bound_rights.items() if key not in _RIGHTS_EVALUATION_FIELDS
    }
    current_static = {
        key: value for key, value in rights_proof.items() if key not in _RIGHTS_EVALUATION_FIELDS
    }
    if bound_static != current_static:
        _fail("promotion_receipt_invalid", "rights_binding_mismatch")
    if calibration_raw != parent.calibration:
        _fail("promotion_receipt_invalid", "calibration_differs_from_frozen_parent")
    if (root / "dictionaries.json").read_bytes() != parent.dictionaries:
        _fail("promotion_receipt_invalid", "dictionary_differs_from_frozen_parent")
    if (root / "src/fetch_ngrams.py").read_bytes() != parent.matcher:
        _fail("promotion_receipt_invalid", "matcher_differs_from_frozen_parent")
    if (root / ngram_daily_attestation.PROFILE_RELATIVE).read_bytes() != parent.aggregate_profile:
        _fail("promotion_receipt_invalid", "aggregate_profile_differs_from_frozen_parent")
    if (root / ngram_daily_attestation.SCHEMA_RELATIVE).read_bytes() != parent.aggregate_schema:
        _fail("promotion_receipt_invalid", "aggregate_schema_differs_from_frozen_parent")
    if (root / "src/ngram_daily_attestation.py").read_bytes() != parent.aggregate_validator:
        _fail("promotion_receipt_invalid", "aggregate_validator_differs_from_frozen_parent")
    if not isinstance(calibration, dict):
        _fail("promotion_receipt_invalid", "calibration_root_invalid")
    expected_calibration_records = {
        channel: _sha256(_canonical_bytes(calibration[channel])) for channel in sorted(calibration)
    }
    if bindings.get("calibration_sha256") != _sha256(calibration_raw):
        _fail("promotion_receipt_invalid", "calibration_hash_mismatch")
    if bindings.get("calibration_records_sha256") != expected_calibration_records:
        _fail("promotion_receipt_invalid", "calibration_records_mismatch")
    if bindings.get("dictionary_sha256") != _sha256((root / "dictionaries.json").read_bytes()):
        _fail("promotion_receipt_invalid", "dictionary_hash_mismatch")
    if bindings.get("matcher_sha256") != _sha256((root / "src/fetch_ngrams.py").read_bytes()):
        _fail("promotion_receipt_invalid", "matcher_hash_mismatch")
    method_bindings = attestation["method_bindings"]
    if bindings.get("source_profile_sha256") != method_bindings["profile_sha256"]:
        _fail("promotion_receipt_invalid", "aggregate_profile_hash_mismatch")
    if bindings.get("source_schema_sha256") != method_bindings["schema_sha256"]:
        _fail("promotion_receipt_invalid", "aggregate_schema_hash_mismatch")
    if bindings.get("source_validator_sha256") != method_bindings["validator_sha256"]:
        _fail("promotion_receipt_invalid", "aggregate_validator_hash_mismatch")
    if bindings.get("matcher_specs_sha256") != method_bindings["matcher_specs_sha256"]:
        _fail("promotion_receipt_invalid", "matcher_specs_hash_mismatch")

    store_prefix = _strip_last_csv_row(store_raw, target, "store")
    provenance_prefix = _strip_last_csv_row(provenance_raw, target, "provenance")
    _require_parent_prefix(parent.store, target, "store", root=root)
    _require_parent_prefix(parent.provenance, target, "provenance", root=root)
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
    evidence = cache_payload.get("_aggregate_attestation")
    method = evidence.get("method_bindings") if isinstance(evidence, dict) else None
    attested_specs = method.get("matcher_specs") if isinstance(method, dict) else None
    if not isinstance(attested_specs, dict):
        _fail("promotion_receipt_invalid", "matcher_specs_missing")
    sums = fetch_ngrams._channel_sums(cache_payload, attested_specs)
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
    if bindings.get("candidate_row_sha256") != _sha256(_canonical_bytes(expected_row)):
        _fail("promotion_receipt_invalid", "candidate_row_hash_mismatch")
    validated_receipt = dict(receipt)
    validated_receipt["release_rights_evaluation"] = rights_proof
    return validated_receipt


def mark_finalized(
    target: date,
    *,
    root: Path = ROOT,
    base_commit: str | None = None,
    non_git_test_trust: NonGitTestTrustRoot | None = None,
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
    contract_today: date | None = None,
) -> dict[str, Any]:
    """Record a value-free failure while preserving the last true final."""

    frozen_today = contract_today or (target + timedelta(days=1))
    require_ordered_target(target, root=root, today=frozen_today)

    prior: dict[str, Any] = {}
    try:
        prior = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    prior_matches = prior.get("target_date") == target.isoformat()
    if failure_stage not in _REFUSAL_DEFAULT_CODES:
        _fail("final_status_invalid", f"unknown_failure_stage:{failure_stage}")
    prior_latest = prior.get("latest_finalized_date")
    reason_code = (
        "source_unavailable"
        if failure_stage == "source"
        and prior_matches
        and prior.get("status") == "source_unavailable"
        else _REFUSAL_DEFAULT_CODES[failure_stage]
    )
    _stage, state, reason = _REFUSAL_REASONS[reason_code]
    payload = record_status(
        target,
        state,
        reason,
        root=root,
        base_commit=base_commit or prior.get("base_commit"),
    )
    payload["contract_today"] = frozen_today.isoformat()
    payload["failure_stage"] = failure_stage
    payload["reason_code"] = reason_code
    _atomic_write(root / STATUS_RELATIVE, _json_bytes(payload))
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
    # The durable per-day record: the marker above is overwritten by every
    # later run, so this file is the disclosure that survives -- and for a
    # SOURCE-stage refusal it is what later authorizes the ordered backlog
    # to advance past a permanently lost provider day.
    ledger_entry = {
        "schema_version": "1.0.0",
        "target_date": target.isoformat(),
        "failure_stage": failure_stage,
        "reason_code": reason_code,
        "status": state,
        "generated": payload.get("generated"),
    }
    ledger_path = root / REFUSAL_LEDGER_RELATIVE / f"{target.isoformat()}.json"
    try:
        prior_entry = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        prior_entry = None
    # The FIRST disclosure's timestamp is the day's record; a repeated
    # identical refusal must leave the ledger byte-identical or the
    # unchanged-disclosure idempotence of repeated refusal shots breaks.
    if not (
        isinstance(prior_entry, dict)
        and prior_entry.get("target_date") == ledger_entry["target_date"]
        and prior_entry.get("failure_stage") == ledger_entry["failure_stage"]
        and prior_entry.get("reason_code") == ledger_entry["reason_code"]
    ):
        _atomic_write(ledger_path, _json_bytes(ledger_entry))
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
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", introduction, head], cwd=root)
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
            if (root / relative).read_bytes() != introduced:
                return False
            if not _first_parent_path_never_changed(root, introduction, head, relative):
                return False
        for relative, expected_sha in _LEGACY_AUG9_HISTORICAL_BLOBS.items():
            introduced = _git_blob(root, introduction, relative)
            if _sha256(introduced) != expected_sha:
                return False
            historical[relative] = introduced
        introduced_index = _git_blob(root, introduction, "docs/index.html")
        current_index = (root / "docs/index.html").read_bytes()
        introduced_surface = _legacy_index_value_surface(introduced_index)
        if (
            introduced_surface is None
            or _legacy_index_value_surface(current_index) != introduced_surface
            or not _first_parent_index_surface_never_changed(
                root, introduction, head, introduced_surface
            )
        ):
            return False
        cache = json.loads(historical["data/raw/ngram_days/2026-08-09.json"])
    except (FinalPublicationError, OSError, UnicodeError, json.JSONDecodeError):
        return False
    evidence = cache.get("_matcher_evidence")
    if not isinstance(evidence, dict):
        return False
    if evidence.get("dictionaries_sha256") != _sha256(historical["dictionaries.json"]):
        return False
    if evidence.get("production_matcher_sha256") != _sha256(historical["src/fetch_ngrams.py"]):
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
    return bool(
        attestation.get("denominator_evidence")
        == "source_reported_denominator_legacy_v1.0"
    )


def is_exact_legacy_cache_exception(root: Path, target: date, *, cache_bytes: bytes) -> bool:
    """Permit rights-free cache parsing only for the pinned Aug-9 object.

    The caller has already performed the one bounded byte read needed to
    identify the legacy object.  Authentication below uses committed Git
    blobs and the append-only first-parent history; it never reopens or parses
    the working-tree cache before exact identity is established.
    """

    relative = f"data/raw/ngram_days/{target.isoformat()}.json"
    expected = _LEGACY_AUG9_BLOBS.get(relative)
    if target != _LEGACY_AUG9_DAY or expected is None:
        return False
    try:
        head = _git_head(root)
        introduction = _git_commit(root, _LEGACY_AUG9_INTRODUCTION)
        introduced = _git_blob(root, introduction, relative)
        committed = _git_blob(root, head, relative) if head is not None else b""
    except FinalPublicationError:
        return False
    return (
        introduction == _LEGACY_AUG9_INTRODUCTION
        and introduced == committed == cache_bytes
        and _sha256(introduced) == expected
        and head is not None
        and _first_parent_path_never_changed(root, introduction, head, relative)
    )


def is_registered_legacy_cache_target(target: date) -> bool:
    """Identify the sole day allowed one pre-rights identity byte probe."""

    return target == _LEGACY_AUG9_DAY


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
    marker_stage = marker.get("failure_stage")
    marker_code = marker.get("reason_code")
    marker_refusal = _REFUSAL_REASONS.get(marker_code) if isinstance(marker_code, str) else None
    if marker_refusal is None and marker_matches and marker.get("status") == "source_unavailable":
        marker_refusal = _REFUSAL_REASONS["source_unavailable"]
    marker_failure = (
        marker_matches
        and marker_refusal is not None
        and marker.get("status") == marker_refusal[1]
        and (
            marker_code is None
            or (marker_stage == marker_refusal[0] and marker.get("reason") == marker_refusal[2])
        )
    )
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
                )
                require_written_final_target(target, site_data=root / "docs/data")
                proven_final = True
            except FinalPublicationError:
                proven_final = False

    legacy_limited = latest == target and not proven_final and _legacy_proof_limited(root, target)
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
        assert marker_refusal is not None
        reason = marker_refusal[2]
    else:
        status = "delayed_final"
        reason = (
            "The D-1 final has not completed publication; the latest older "
            "final remains the number of record."
        )
    result = {
        "target_date": target.isoformat(),
        "latest_finalized_date": (reported_latest.isoformat() if reported_latest else None),
        "status": status,
        "reason": reason,
        "finalized": status == "finalized",
        "provisional_substitution_allowed": False,
        "value_fields_published": False,
        "source_receipt": marker.get("receipt") if proven_final else None,
    }
    if marker_failure:
        assert marker_refusal is not None
        result["failure_stage"] = marker_refusal[0]
        result["reason_code"] = (
            marker_code if isinstance(marker_code, str) else "source_unavailable"
        )
    return result


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
        raise FinalPublicationError("public_status_unreadable", "docs/data/status.json") from exc
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


def _require_clean_release_tree(root: Path, classification: str) -> str:
    head = _git_head(root)
    status = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if head is None or status.returncode != 0 or status.stdout:
        _fail(classification, "candidate_worktree_not_clean")
    return head


@contextmanager
def _committed_candidate_snapshot(root: Path, candidate_sha: str) -> Iterator[Path]:
    container = Path(tempfile.mkdtemp(prefix="igrm-release-candidate-"))
    snapshot = container / "tree"
    added = subprocess.run(
        ["git", "worktree", "add", "--quiet", "--detach", str(snapshot), candidate_sha],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if added.returncode != 0:
        shutil.rmtree(container, ignore_errors=True)
        _fail("release_candidate_unproven", "candidate_snapshot_unavailable")
    try:
        yield snapshot
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(snapshot)],
            cwd=root,
            capture_output=True,
        )
        shutil.rmtree(container, ignore_errors=True)


def _require_release_rights_from_snapshot(
    *, root: Path = ROOT, expected_candidate_sha: str | None = None
) -> dict[str, Any]:
    """Recheck actual-time rights at the end of the candidate gate."""

    candidate_sha = _git_head(root)
    if candidate_sha is None or (
        expected_candidate_sha is not None and candidate_sha != expected_candidate_sha
    ):
        _fail("release_rights_unproven", "frozen_candidate_sha_mismatch")
    latest = _read_latest_day(root)
    try:
        marker = json.loads((root / STATUS_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalPublicationError(
            "release_rights_unproven", "finalized_marker_unreadable"
        ) from exc
    target_text = marker.get("target_date")
    try:
        target = date.fromisoformat(target_text)
    except (TypeError, ValueError) as exc:
        raise FinalPublicationError("release_rights_unproven", "finalized_target_invalid") from exc
    if (
        marker.get("status") != "finalized"
        or latest != target
        or not isinstance(marker.get("receipt"), dict)
    ):
        _fail("release_rights_unproven", "exact_finalized_marker_required")
    parent = _committed_receipt_parent(root, marker)
    if parent is None:
        _fail("release_rights_unproven", "receipt_introduction_parent_unproven")
    receipt = require_promotion_receipt(
        target,
        root=root,
        require_bridge_receipt=True,
        trusted_parent=parent,
        required_marker_status="finalized",
    )
    return {
        "status": "release_rights_verified",
        "target_date": target.isoformat(),
        "candidate_sha": candidate_sha,
        "release_rights_evaluation": receipt["release_rights_evaluation"],
    }


def require_release_rights(
    *, root: Path = ROOT, expected_candidate_sha: str | None = None
) -> dict[str, Any]:
    """Verify release rights only from one clean committed candidate tree."""

    candidate_sha = _require_clean_release_tree(root, "release_rights_unproven")
    if expected_candidate_sha is not None and candidate_sha != expected_candidate_sha:
        _fail("release_rights_unproven", "frozen_candidate_sha_mismatch")
    with _committed_candidate_snapshot(root, candidate_sha) as snapshot:
        return _require_release_rights_from_snapshot(
            root=snapshot,
            expected_candidate_sha=candidate_sha,
        )


def _tree_has_path(root: Path, treeish: str, relative: str) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{treeish}:{relative}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def _require_candidate_api_manifest(
    *, root: Path, candidate_sha: str, base_commit: str
) -> bool:
    """Recompute the manifest when this contract exists in the lineage.

    Old synthetic publication fixtures predate the manifest and remain valid
    tests of the earlier rights/finality boundary. Once either the parent or
    candidate contains the manifest, removing or failing to recompute it is a
    hard refusal. The manifest is derived metadata only: caller code still
    proves the final/refusal class and legal changed-path set independently.
    """

    parent_has = _tree_has_path(
        root, base_commit, _PUBLIC_API_BYTE_MANIFEST_PATH
    )
    candidate_has = _tree_has_path(
        root, candidate_sha, _PUBLIC_API_BYTE_MANIFEST_PATH
    )
    if not parent_has and not candidate_has:
        return False
    if not candidate_has:
        _fail("release_candidate_unproven", "api_manifest_missing")
    try:
        from . import public_api_byte_manifest

        public_api_byte_manifest.verify_tree(candidate_sha, root=root)
    except public_api_byte_manifest.PublicAPIByteManifestError as exc:
        _fail("release_candidate_unproven", f"api_manifest_invalid:{exc.code}")
    return True


def _require_release_candidate_from_snapshot(
    candidate_class: str,
    *,
    expected_candidate_sha: str,
    base_commit: str,
    expected_target: date,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Authorize one frozen final, verification, or value-free refusal."""

    candidate_sha = _git_head(root)
    if (
        candidate_class not in {"final", "verification", "refusal"}
        or not re.fullmatch(r"[0-9a-f]{40}", expected_candidate_sha)
        or not re.fullmatch(r"[0-9a-f]{40}", base_commit)
        or candidate_sha != expected_candidate_sha
    ):
        _fail("release_candidate_unproven", "candidate_identity_invalid")
    lineage = subprocess.run(
        ["git", "rev-list", "--parents", "-n", "1", candidate_sha],
        cwd=root,
        capture_output=True,
        text=True,
    ).stdout.split()
    if len(lineage) != 2 or lineage[1] != base_commit:
        _fail("release_candidate_unproven", "candidate_parent_invalid")
    manifest_required = _require_candidate_api_manifest(
        root=root,
        candidate_sha=candidate_sha,
        base_commit=base_commit,
    )
    if candidate_class == "final":
        proof = _require_release_rights_from_snapshot(
            root=root, expected_candidate_sha=expected_candidate_sha
        )
        if proof.get("status") != "release_rights_verified":
            _fail("release_candidate_unproven", "final_release_rights_required")
        if proof.get("target_date") != expected_target.isoformat():
            _fail("release_candidate_unproven", "final_target_mismatch")
        return {
            **proof,
            "candidate_class": "final",
            "base_commit": base_commit,
            "value_fields_published": True,
        }

    if candidate_class == "verification":
        if expected_target != _LEGACY_AUG9_DAY:
            _fail("release_candidate_unproven", "verification_target_invalid")
        diff = subprocess.run(
            ["git", "diff", "--name-status", "--no-renames", base_commit, candidate_sha],
            cwd=root,
            capture_output=True,
            text=True,
        )
        expected_path = (
            LEGACY_AGGREGATE_RECEIPTS_RELATIVE / f"{_LEGACY_AUG9_DAY}.json"
        ).as_posix()
        if diff.returncode != 0 or diff.stdout.splitlines() != [f"A\t{expected_path}"]:
            _fail("release_candidate_unproven", "verification_diff_not_disjoint")
        receipt = verify_legacy_under_aggregate_profile(root=root)
        return {
            "status": "legacy_aggregate_verification_release_verified",
            "candidate_class": "verification",
            "candidate_sha": candidate_sha,
            "base_commit": base_commit,
            "target_date": _LEGACY_AUG9_DAY.isoformat(),
            "receipt_sha256": _sha256(_json_bytes(receipt)),
            "value_fields_published": False,
        }

    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-status",
            "--no-renames",
            base_commit,
            candidate_sha,
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _fail("release_candidate_unproven", "refusal_diff_unreadable")
    changed: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or fields[0] not in {"A", "M"}:
            _fail("release_candidate_unproven", "refusal_diff_status_invalid")
        changed.add(fields[1])
    allowed_refusal_paths = set(_VALUE_FREE_REFUSAL_PATHS)
    if manifest_required:
        allowed_refusal_paths.add(_PUBLIC_API_BYTE_MANIFEST_PATH)
    allowed_refusal_paths.add(
        (REFUSAL_LEDGER_RELATIVE / f"{expected_target.isoformat()}.json").as_posix()
    )
    if (
        STATUS_RELATIVE.as_posix() not in changed
        or not changed.issubset(allowed_refusal_paths)
    ):
        _fail("release_candidate_unproven", "refusal_diff_not_value_free")
    candidate_bytes = {
        relative: _git_regular_blob(
            root,
            candidate_sha,
            relative,
            classification="release_candidate_unproven",
            detail="refusal_output_mode_invalid",
        )
        for relative in sorted(_VALUE_FREE_REFUSAL_PATHS)
    }
    try:
        marker_raw = candidate_bytes[STATUS_RELATIVE.as_posix()]
        marker = json.loads(marker_raw)
        parent_latest = json.loads(_git_blob(root, base_commit, "docs/data/latest.json"))["date"]
        target = date.fromisoformat(str(marker["target_date"]))
        contract_today = date.fromisoformat(str(marker["contract_today"]))
        latest = date.fromisoformat(str(marker["latest_finalized_date"]))
        generated_text = str(marker["generated"])
        generated = datetime.fromisoformat(generated_text[:-1] + "+00:00")
    except (
        FinalPublicationError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise FinalPublicationError("release_candidate_unproven", "refusal_marker_invalid") from exc
    expected_marker_fields = {
        "schema_version",
        "target_date",
        "contract_today",
        "status",
        "failure_stage",
        "reason_code",
        "reason",
        "latest_finalized_date",
        "generated",
        "base_commit",
        "value_fields_published",
        "provisional_substitution_allowed",
    }
    marker_reason_code = marker.get("reason_code")
    expected_refusal = (
        _REFUSAL_REASONS.get(marker_reason_code) if isinstance(marker_reason_code, str) else None
    )
    if (
        not isinstance(marker, dict)
        or set(marker) != expected_marker_fields
        or marker.get("schema_version") != "1.0.0"
        or expected_refusal is None
        or marker.get("failure_stage") != expected_refusal[0]
        or marker.get("status") != expected_refusal[1]
        or marker.get("reason_code") != marker_reason_code
        or marker.get("reason") != expected_refusal[2]
        or marker.get("base_commit") != base_commit
        or marker.get("value_fields_published") is not False
        or marker.get("provisional_substitution_allowed") is not False
        or marker_raw != _json_bytes(marker)
        or not generated_text.endswith("Z")
        or generated.tzinfo is None
        or generated.utcoffset() != timedelta(0)
        or target != expected_target
        or target != required_target(contract_today)
        or latest >= target
        or latest.isoformat() != parent_latest
    ):
        _fail("release_candidate_unproven", "refusal_marker_not_value_free")
    state = {
        "target_date": target.isoformat(),
        "latest_finalized_date": latest.isoformat(),
        "status": expected_refusal[1],
        "reason": expected_refusal[2],
        "finalized": False,
        "provisional_substitution_allowed": False,
        "value_fields_published": False,
        "source_receipt": None,
        "failure_stage": marker["failure_stage"],
        "reason_code": marker_reason_code,
    }
    try:
        parent_status = json.loads(_git_blob(root, base_commit, "docs/data/status.json"))
        if not isinstance(parent_status, dict):
            raise ValueError("parent status root invalid")
        parent_status["final_publication"] = state
        expected_bytes = {
            "data/raw/final_publication_status.json": marker_raw,
            # write_public_status preserves json.dumps' default ASCII escaping.
            # Rebuild those exact bytes here as well: current public metadata
            # contains Unicode punctuation, so _json_bytes(ensure_ascii=False)
            # would reject the publisher's own deterministic refusal output.
            "docs/data/status.json": (json.dumps(parent_status, indent=1) + "\n").encode("utf-8"),
        }
        from . import status_data

        for relative in ("docs/index.html", "docs/status.html"):
            expected_bytes[relative] = status_data.static_final_disclosure_bytes(
                state,
                relative,
                _git_blob(root, base_commit, relative),
            )
    except (FinalPublicationError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise FinalPublicationError("release_candidate_unproven", "refusal_rebuild_failed") from exc
    for relative, expected in expected_bytes.items():
        actual = candidate_bytes[relative]
        if actual != expected:
            _fail(
                "release_candidate_unproven",
                f"refusal_output_mismatch:{relative}",
            )
    return {
        "status": "value_free_refusal_verified",
        "candidate_class": "refusal",
        "candidate_sha": candidate_sha,
        "base_commit": base_commit,
        "changed_paths": sorted(changed),
        "value_fields_published": False,
        "release_rights_evaluation": None,
    }


def require_release_candidate(
    candidate_class: str,
    *,
    expected_candidate_sha: str,
    base_commit: str,
    expected_target: date,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Verify a release only from one clean snapshot of its committed SHA."""

    candidate_sha = _require_clean_release_tree(root, "release_candidate_unproven")
    if candidate_sha != expected_candidate_sha:
        _fail("release_candidate_unproven", "candidate_identity_invalid")
    with _committed_candidate_snapshot(root, candidate_sha) as snapshot:
        return _require_release_candidate_from_snapshot(
            candidate_class,
            expected_candidate_sha=expected_candidate_sha,
            base_commit=base_commit,
            expected_target=expected_target,
            root=snapshot,
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire-target", type=date.fromisoformat)
    parser.add_argument("--next-target", action="store_true")
    parser.add_argument("--verify-legacy-aggregate", action="store_true")
    parser.add_argument("--record-pipeline-failed", type=date.fromisoformat)
    parser.add_argument("--check-promotion-receipt", type=date.fromisoformat)
    parser.add_argument("--check-published-target", type=date.fromisoformat)
    parser.add_argument("--check-release-rights", metavar="EXPECTED_CANDIDATE_SHA")
    parser.add_argument(
        "--check-release-candidate", choices=("final", "verification", "refusal")
    )
    parser.add_argument("--expected-candidate-sha")
    parser.add_argument("--expected-target", type=date.fromisoformat)
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
            args.next_target,
            args.verify_legacy_aggregate,
            args.record_pipeline_failed is not None,
            args.check_promotion_receipt is not None,
            args.check_published_target is not None,
            args.check_release_rights is not None,
            args.check_release_candidate is not None,
            args.write_public_status,
        )
    )
    if selected != 1:
        parser.error("select exactly one publication-status operation")
    if args.next_target:
        target = required_next_target(root=args.root, today=args.today)
        print(target.isoformat() if target is not None else "none")
        return
    if args.verify_legacy_aggregate:
        print(json.dumps(verify_legacy_under_aggregate_profile(root=args.root), indent=1))
        return
    if args.record_pipeline_failed is not None:
        status = record_pipeline_failed(
            args.record_pipeline_failed,
            root=args.root,
            base_commit=args.base_commit,
            failure_stage=args.failure_stage,
            contract_today=args.today,
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
    if args.check_release_rights:
        try:
            release = require_release_rights(
                root=args.root,
                expected_candidate_sha=args.check_release_rights,
            )
        except FinalPublicationError as exc:
            print(
                json.dumps(
                    {"status": exc.classification, "reason": exc.detail},
                    indent=1,
                )
            )
            raise SystemExit(2) from exc
        print(json.dumps(release, indent=1))
        return
    if args.check_release_candidate is not None:
        if (
            args.expected_candidate_sha is None
            or args.base_commit is None
            or args.expected_target is None
        ):
            parser.error(
                "--check-release-candidate requires --expected-candidate-sha "
                "--base-commit, and --expected-target"
            )
        try:
            release = require_release_candidate(
                args.check_release_candidate,
                expected_candidate_sha=args.expected_candidate_sha,
                base_commit=args.base_commit,
                expected_target=args.expected_target,
                root=args.root,
            )
        except FinalPublicationError as exc:
            print(
                json.dumps(
                    {"status": exc.classification, "reason": exc.detail},
                    indent=1,
                )
            )
            raise SystemExit(2) from exc
        print(json.dumps(release, indent=1))
        return
    if args.write_public_status:
        print(json.dumps(write_public_status(root=args.root, today=args.today), indent=1))
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
