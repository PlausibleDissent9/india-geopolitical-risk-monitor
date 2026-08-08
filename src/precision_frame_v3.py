"""Prospective production-frame evidence for the external precision audit v3.

This module does not draw a sample, accept labels, or estimate precision.  It
verifies and records one completed score day's exact group-contribution frame.
The source is the evidence-bearing cache written inside ``fetch_ngrams`` during
the production scoring pass, rather than a later reconstruction.

    python -m src.precision_frame_v3 --record-latest
    python -m src.precision_frame_v3 --check-day 2026-08-08
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.fetch_gdelt import build_queries

ROOT = Path(__file__).resolve().parents[1]
DAY_CACHES = ROOT / "data" / "raw" / "ngram_days"
ATTESTATIONS = ROOT / "data" / "raw" / "precision_v3_days"
LATEST = ROOT / "docs" / "data" / "latest.json"

WINDOW_START = date(2026, 8, 8)
WINDOW_END = date(2026, 11, 5)
EXPECTED_SAMPLES = 48
SCHEMA_VERSION = "1.0.0"


class FrameValidationError(ValueError):
    """The cached day cannot enter the prospective v3 precision frame."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrameValidationError(f"unreadable JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FrameValidationError(f"JSON root is not an object: {path}")
    return raw, payload


def _int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FrameValidationError(f"{label} must be a non-negative integer")
    return value


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise FrameValidationError(f"{label} must be a string list")
    if len(value) != len(set(value)):
        raise FrameValidationError(f"{label} contains duplicates")
    return value


def _canonical_specs_sha256(specs: object) -> str:
    if not isinstance(specs, dict):
        raise FrameValidationError("matcher_specs must be an object")
    encoded = json.dumps(specs, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(encoded)


def _active_specs_from_dictionary(root: Path) -> dict[str, dict[str, Any]]:
    """Independently reconstruct the production group specification."""
    _, dictionaries = _read_object(root / "dictionaries.json")
    specs: dict[str, dict[str, Any]] = {}
    for channel, raw_spec in dictionaries.items():
        if channel.startswith("_"):
            continue
        if not isinstance(raw_spec, dict):
            raise FrameValidationError(f"dictionary channel is invalid: {channel}")
        terms = raw_spec.get("terms")
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            raise FrameValidationError(f"dictionary terms are invalid: {channel}")
        anchor_value = raw_spec.get("anchor")
        anchor = str(anchor_value).lower() if anchor_value else None
        remaining = [term.strip('"') for term in terms]
        for index, query in enumerate(build_queries(terms, anchor_value), start=1):
            n_terms = query.count('"') // 2
            selected = remaining[:n_terms]
            remaining = remaining[n_terms:]
            specs[f"{channel}/q{index}"] = {
                "channel": channel,
                "anchor": anchor,
                "phrases": [
                    re.sub(r"[^a-z0-9 ]+", " ", term.lower().replace("-", " ")).split()
                    for term in selected
                ],
            }
        if remaining:
            raise FrameValidationError(f"dictionary partition is incomplete: {channel}")
    return {group: specs[group] for group in sorted(specs)}


def _source_record_sha256(record: dict[str, str]) -> str:
    encoded = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    return _sha256(encoded)


def _validate_live_hashes(evidence: dict[str, Any], root: Path) -> None:
    expected = {
        "dictionaries_sha256": root / "dictionaries.json",
        "production_matcher_sha256": root / "src" / "fetch_ngrams.py",
    }
    for field, path in expected.items():
        try:
            observed = _sha256(path.read_bytes())
        except OSError as exc:
            raise FrameValidationError(f"live source missing: {path}") from exc
        if evidence.get(field) != observed:
            raise FrameValidationError(f"{field} does not match the live scoring source")
    if evidence.get("matcher_specs") != _active_specs_from_dictionary(root):
        raise FrameValidationError(
            "embedded matcher specification does not match the live dictionary"
        )


def build_day_attestation(
    day: date,
    root: Path = ROOT,
    *,
    require_live_hashes: bool = True,
) -> dict[str, Any]:
    """Verify one score cache and return its compact, label-free attestation."""
    if not WINDOW_START <= day <= WINDOW_END:
        raise FrameValidationError(
            f"{day} is outside the prospective window "
            f"{WINDOW_START}..{WINDOW_END}"
        )
    source_path = root / "data" / "raw" / "ngram_days" / f"{day}.json"
    raw, payload = _read_object(source_path)
    if payload.get("date") != day.isoformat():
        raise FrameValidationError("cache date does not match requested day")

    denominator = _int(payload.get("n_docs_sampled"), "n_docs_sampled")
    located_n = _int(payload.get("n_samples"), "n_samples")
    loaded_n = _int(payload.get("n_samples_loaded"), "n_samples_loaded")
    if payload.get("partial") is not False:
        raise FrameValidationError("partial production days are ineligible")
    if (located_n, loaded_n) != (EXPECTED_SAMPLES, EXPECTED_SAMPLES):
        raise FrameValidationError(
            f"expected {EXPECTED_SAMPLES} located and loaded samples, got "
            f"{located_n} and {loaded_n}"
        )
    if denominator == 0:
        raise FrameValidationError("empty production denominator")

    evidence = payload.get("_matcher_evidence")
    if not isinstance(evidence, dict) or evidence.get("schema_version") != SCHEMA_VERSION:
        raise FrameValidationError("production matcher evidence is missing or unsupported")
    if evidence.get("day") != day.isoformat():
        raise FrameValidationError("matcher-evidence day mismatch")
    specs = evidence.get("matcher_specs")
    specs_hash = _canonical_specs_sha256(specs)
    if evidence.get("matcher_specs_sha256") != specs_hash:
        raise FrameValidationError("matcher specification hash mismatch")
    if require_live_hashes:
        _validate_live_hashes(evidence, root)

    located = _string_list(evidence.get("located_stamps"), "located_stamps")
    loaded = _string_list(evidence.get("loaded_stamps"), "loaded_stamps")
    missing = _string_list(evidence.get("missing_stamps"), "missing_stamps")
    if len(located) != located_n or len(loaded) != loaded_n:
        raise FrameValidationError("sample-depth fields disagree with stamp evidence")
    if located != loaded or missing:
        raise FrameValidationError("not every located production sample was loaded")
    prefix = day.strftime("%Y%m%d")
    if any(len(stamp) != 14 or not stamp.isdigit() or not stamp.startswith(prefix) for stamp in loaded):
        raise FrameValidationError("loaded stamp has an invalid day or shape")

    if not isinstance(specs, dict) or not specs:
        raise FrameValidationError("matcher specification is empty")
    shares = payload.get("shares")
    matched = evidence.get("matched_document_keys")
    article_meta = evidence.get("article_meta")
    if not isinstance(shares, dict) or set(shares) != set(specs):
        raise FrameValidationError("share groups do not match the frozen matcher")
    if not isinstance(matched, dict) or set(matched) != set(specs):
        raise FrameValidationError("matched groups do not match the frozen matcher")
    if not isinstance(article_meta, dict):
        raise FrameValidationError("article metadata is missing")

    india_keys = set(
        _string_list(evidence.get("india_document_keys"), "india_document_keys")
    )
    loaded_set = set(loaded)
    for key in india_keys:
        if key.split(":", 1)[0] not in loaded_set:
            raise FrameValidationError("India evidence points outside loaded stamps")

    source_sha = _sha256(raw)
    groups: dict[str, dict[str, Any]] = {}
    channel_units: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for group in sorted(specs):
        spec = specs[group]
        if not isinstance(spec, dict) or not isinstance(spec.get("channel"), str):
            raise FrameValidationError(f"invalid matcher specification for {group}")
        anchor = spec.get("anchor")
        if anchor not in {None, "india"}:
            raise FrameValidationError(f"unsupported production anchor for {group}")
        keys = set(_string_list(matched[group], f"matched_document_keys.{group}"))
        if any(key.split(":", 1)[0] not in loaded_set for key in keys):
            raise FrameValidationError(f"{group} points outside loaded stamps")
        eligible = keys & india_keys if anchor == "india" else keys
        for key in eligible:
            record = article_meta.get(key)
            if not isinstance(record, dict):
                raise FrameValidationError(f"eligible contribution lacks metadata: {group}|{key}")
            normalized = {
                field: str(record.get(field) or "") for field in ("date", "title", "url")
            }
            channel_units[spec["channel"]].append((group, key))
            if not normalized["date"]:
                raise FrameValidationError(f"eligible contribution lacks a date: {group}|{key}")

        reconstructed = round(100.0 * len(eligible) / denominator, 6)
        observed = shares[group]
        if (
            isinstance(observed, bool)
            or not isinstance(observed, (int, float))
            or not math.isfinite(float(observed))
            or reconstructed != float(observed)
        ):
            raise FrameValidationError(
                f"{group} contribution count does not reproduce its published share"
            )
        groups[group] = {
            "channel": spec["channel"],
            "anchor": anchor,
            "n_group_contributions": len(eligible),
            "reconstructed_share": reconstructed,
        }

    channels: dict[str, dict[str, int]] = {}
    for channel, units in sorted(channel_units.items()):
        distinct_documents = {key for _, key in units}
        channels[channel] = {
            "n_group_contributions": len(units),
            "n_distinct_document_keys": len(distinct_documents),
            "multi_group_contribution_excess": len(units) - len(distinct_documents),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "study": "igrm-external-precision-v3-prospective-frame",
        "status": "ELIGIBLE_SOURCE_DAY_NO_LABELS",
        "day": day.isoformat(),
        "prospective_window": {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
        },
        "source_cache": source_path.relative_to(root).as_posix(),
        "source_cache_sha256": source_sha,
        "n_samples_located": located_n,
        "n_samples_loaded": loaded_n,
        "missing_stamps": missing,
        "n_english_documents": denominator,
        "matcher_specs_sha256": specs_hash,
        "dictionaries_sha256": evidence["dictionaries_sha256"],
        "production_matcher_sha256": evidence["production_matcher_sha256"],
        "groups": groups,
        "channels": channels,
        "labels_seen": False,
        "precision_estimated": False,
        "claim_limit": (
            "Source-frame eligibility only; this attestation is not a sample, "
            "precision estimate, validation result, or superiority claim."
        ),
    }


def record_day(
    day: date,
    root: Path = ROOT,
    *,
    require_live_hashes: bool = True,
) -> Path:
    """Write one append-only attestation; refuse to revise an existing day."""
    payload = build_day_attestation(
        day, root, require_live_hashes=require_live_hashes
    )
    encoded = (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode()
    destination = root / "data" / "raw" / "precision_v3_days" / f"{day}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() != encoded:
            raise FrameValidationError(
                f"existing v3 day attestation differs: {destination}"
            )
        return destination
    prior_paths = sorted(destination.parent.glob("*.json"))
    expected_prior: list[str] = []
    cursor = WINDOW_START
    while cursor < day:
        expected_prior.append(cursor.isoformat())
        cursor += timedelta(days=1)
    observed_prior = [path.stem for path in prior_paths]
    if observed_prior != expected_prior:
        raise FrameValidationError(
            "prospective source window has a missing, extra, or out-of-order day"
        )
    regime_fields = (
        "matcher_specs_sha256",
        "dictionaries_sha256",
        "production_matcher_sha256",
    )
    for prior_path in prior_paths:
        _, prior = _read_object(prior_path)
        if prior.get("day") != prior_path.stem:
            raise FrameValidationError(f"prior attestation day mismatch: {prior_path}")
        if prior.get("status") != "ELIGIBLE_SOURCE_DAY_NO_LABELS":
            raise FrameValidationError(f"prior attestation is ineligible: {prior_path}")
        if any(prior.get(field) != payload.get(field) for field in regime_fields):
            raise FrameValidationError(
                "production matcher or dictionary regime changed inside v3"
            )
        source_relpath = prior.get("source_cache")
        if not isinstance(source_relpath, str):
            raise FrameValidationError(f"prior source path is invalid: {prior_path}")
        source_path = (root / source_relpath).resolve()
        resolved_root = root.resolve()
        if resolved_root not in source_path.parents:
            raise FrameValidationError(f"prior source path escapes root: {prior_path}")
        try:
            source_sha = _sha256(source_path.read_bytes())
        except OSError as exc:
            raise FrameValidationError(f"prior source cache is missing: {source_path}") from exc
        if source_sha != prior.get("source_cache_sha256"):
            raise FrameValidationError(f"prior source cache changed: {source_path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{day}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_name, destination)
        except FileExistsError:
            if destination.read_bytes() != encoded:
                raise FrameValidationError(
                    f"concurrent v3 day attestation differs: {destination}"
                ) from None
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return destination


def _latest_day(root: Path) -> date:
    _, payload = _read_object(root / "docs" / "data" / "latest.json")
    value = payload.get("date")
    if not isinstance(value, str):
        raise FrameValidationError("latest.json has no completed news day")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FrameValidationError("latest.json date is invalid") from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record-latest", action="store_true")
    group.add_argument("--record-day", type=date.fromisoformat)
    group.add_argument("--check-day", type=date.fromisoformat)
    args = parser.parse_args()

    day = _latest_day(ROOT) if args.record_latest else args.record_day or args.check_day
    if args.record_latest and not WINDOW_START <= day <= WINDOW_END:
        print(f"[precision-v3] {day} is outside the prospective window; no action")
        return
    if args.record_latest:
        expected = datetime.now(timezone.utc).date() - timedelta(days=1)
        if day != expected:
            raise FrameValidationError(
                f"latest completed score day is {day}; expected {expected}"
            )
    if args.check_day:
        print(json.dumps(build_day_attestation(day), indent=1, sort_keys=True))
        return
    destination = record_day(day)
    print(f"[precision-v3] recorded eligible source day {day}: {destination}")


if __name__ == "__main__":
    main()
