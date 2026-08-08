"""Build and score the preregistered external precision audit v3 cohorts.

The source-frame collector in :mod:`src.precision_frame_v3` runs during the
production scoring pass.  This module is deliberately downstream of that
collector: it refuses to draw anything until every calendar day in the named
cohort exists, every attestation still reproduces its source cache, and every
registered file still has its pre-label digest.

No production package exists while the source window is open.  The commands
are therefore safe to ship before any coder sees a row::

    python -m src.precision_audit_v3 --preflight v3a
    python -m src.precision_audit_v3 --build v3a \
        --output /absolute/path/outside/repository/precision-v3a-private \
        --freeze-receipt validation/precision_v3/freeze_v3a.json
    python -m src.precision_audit_v3 --score /private/path c1.csv c2.csv \
        --coder-attestation c1-attestation.json \
        --coder-attestation c2-attestation.json \
        --freeze-receipt validation/precision_v3/freeze_v3a.json \
        --anchor-commit <full-public-commit-sha> --output results.json

Coder packets contain titles and links for private audit use.  They are not a
public-data licence.  The public release is a separately rights-reviewed,
hash-linked result package.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src import precision_frame_v3

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "validation" / "precision_v3" / "registration.json"

SCHEMA_VERSION = "3.0.0"
CHANNELS = [
    "pakistan_west",
    "china_east",
    "gulf_energy",
    "us_trade",
    "shipping",
]
FIRM_LABELS = {"ON", "OFF"}
LABELS = FIRM_LABELS | {"ABSTAIN"}
CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
ACCESS = {"TITLE_ONLY", "LIVE", "PAYWALL", "DEAD", "OTHER_UNAVAILABLE"}

CODER_ATTESTATION_STATEMENTS = {
    "independent_from_igrm_design",
    "coded_without_collaboration",
    "no_llm_or_classifier_used_for_labels",
    "compensation_fixed_before_coding_and_outcome_independent",
    "pilot_completed_before_scored_sheet",
    "did_not_view_igrm_outputs_or_prior_labels_during_scoring",
}

LOCKED_FIELDS = [
    "audit_id",
    "channel",
    "article_date",
    "title",
    "domain",
    "url",
]
CODER_FIELDS = LOCKED_FIELDS + [
    "coder_label",
    "coder_confidence",
    "evidence_access_status",
    "evidence_accessed_at_utc",
    "coder_note",
]


class AuditV3Error(ValueError):
    """The preregistered v3 package or submitted labels are invalid."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _read_object(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuditV3Error(f"unreadable JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AuditV3Error(f"JSON root is not an object: {path}")
    return raw, payload


def _day(value: object, label: str) -> date:
    if not isinstance(value, str):
        raise AuditV3Error(f"{label} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AuditV3Error(f"{label} must be an ISO date") from exc


def _days(start: date, end: date) -> list[date]:
    if end < start:
        raise AuditV3Error("cohort window is reversed")
    return [date.fromordinal(value) for value in range(start.toordinal(), end.toordinal() + 1)]


def _safe_path(root: Path, relpath: object, label: str) -> Path:
    if not isinstance(relpath, str) or not relpath or Path(relpath).is_absolute():
        raise AuditV3Error(f"{label} has an invalid path")
    path = (root / relpath).resolve()
    resolved_root = root.resolve()
    if path != resolved_root and resolved_root not in path.parents:
        raise AuditV3Error(f"{label} escapes the repository")
    return path


def _git_blob(root: Path, commit: str, relpath: str) -> bytes:
    """Read a preregistered blob from its immutable Git commit."""
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{relpath}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise AuditV3Error(
            f"registered base blob is unavailable: {commit}:{relpath}"
        )
    return proc.stdout


def _registration(root: Path = ROOT) -> dict[str, Any]:
    path = root / "validation" / "precision_v3" / "registration.json"
    _, registration = _read_object(path)
    required = {
        "schema_version",
        "audit_id",
        "status",
        "registered_at",
        "base_commit",
        "base_commit_rule",
        "pre_source_amendment",
        "source_collection",
        "cohorts",
        "registered_files",
        "sampling",
        "coding",
        "estimands",
        "quality_gates",
        "rights_and_release",
        "attestation",
    }
    if set(registration) != required:
        raise AuditV3Error("registration fields differ from the frozen schema")
    if registration["schema_version"] != SCHEMA_VERSION:
        raise AuditV3Error("unsupported registration schema")
    if registration["status"] != "PREREGISTERED_NO_SAMPLE_NO_LABELS":
        raise AuditV3Error("registration is not in the pre-label state")

    try:
        registered_at = datetime.fromisoformat(
            str(registration["registered_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise AuditV3Error("registered_at is invalid") from exc
    if registered_at.tzinfo is None or registered_at.utcoffset() != timezone.utc.utcoffset(registered_at):
        raise AuditV3Error("registered_at must be UTC")

    base_commit = registration["base_commit"]
    if not isinstance(base_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise AuditV3Error("base_commit must be a full lowercase Git commit")
    if not isinstance(registration["base_commit_rule"], str) or len(
        registration["base_commit_rule"]
    ) < 80:
        raise AuditV3Error("base_commit_rule is missing or incomplete")
    amendment = registration["pre_source_amendment"]
    amendment_fields = {
        "amended_at",
        "prior_registration_commit",
        "source_day_available",
        "sample_drawn",
        "labels_seen",
        "changes",
    }
    if not isinstance(amendment, dict) or set(amendment) != amendment_fields:
        raise AuditV3Error("pre_source_amendment fields are invalid")
    if amendment["prior_registration_commit"] != base_commit:
        raise AuditV3Error("pre-source amendment is not bound to the initial registration")
    if any(
        amendment[field] is not False
        for field in ("source_day_available", "sample_drawn", "labels_seen")
    ):
        raise AuditV3Error("pre-source amendment occurred after study evidence existed")
    if not isinstance(amendment["changes"], list) or not amendment["changes"]:
        raise AuditV3Error("pre-source amendment has no change ledger")
    try:
        amended_at = datetime.fromisoformat(
            str(amendment["amended_at"]).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise AuditV3Error("pre-source amendment timestamp is invalid") from exc
    if (
        amended_at.tzinfo is None
        or amended_at.utcoffset() != timezone.utc.utcoffset(amended_at)
        or amended_at <= registered_at
    ):
        raise AuditV3Error("pre-source amendment timestamp is not later UTC")

    files = registration["registered_files"]
    if not isinstance(files, list) or not files:
        raise AuditV3Error("registered_files must be a non-empty list")
    seen_paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {
            "path", "sha256", "role", "resolution"
        }:
            raise AuditV3Error("registered file entry is invalid")
        relpath = item["path"]
        if relpath in seen_paths:
            raise AuditV3Error("registered file path is duplicated")
        seen_paths.add(relpath)
        file_path = _safe_path(root, relpath, "registered file")
        resolution = item["resolution"]
        if resolution == "base_commit":
            observed = _sha256(_git_blob(root, base_commit, relpath))
        elif resolution == "working_tree":
            try:
                observed = _sha256(file_path.read_bytes())
            except OSError as exc:
                raise AuditV3Error(f"registered file is missing: {relpath}") from exc
        else:
            raise AuditV3Error(f"registered file resolution is invalid: {relpath}")
        if observed != item["sha256"]:
            raise AuditV3Error(
                "registered file changed "
                f"({resolution.replace('_', '-')} resolution): {relpath}"
            )

    cohorts = registration["cohorts"]
    if not isinstance(cohorts, list) or len(cohorts) != 2:
        raise AuditV3Error("registration must contain the initial and holdout cohorts")
    cohort_ids: set[str] = set()
    prior_end: date | None = None
    for cohort in cohorts:
        expected = {
            "cohort_id",
            "role",
            "window_start",
            "window_end",
            "calendar_days",
            "sample_per_channel",
            "selection_seed",
            "labels_may_begin_after",
        }
        if not isinstance(cohort, dict) or set(cohort) != expected:
            raise AuditV3Error("cohort entry is invalid")
        cohort_id = cohort["cohort_id"]
        if not isinstance(cohort_id, str) or not re.fullmatch(r"v3[ab]", cohort_id):
            raise AuditV3Error("cohort id is invalid")
        if cohort_id in cohort_ids:
            raise AuditV3Error("cohort id is duplicated")
        cohort_ids.add(cohort_id)
        start = _day(cohort["window_start"], "window_start")
        end = _day(cohort["window_end"], "window_end")
        if cohort["calendar_days"] != len(_days(start, end)):
            raise AuditV3Error("cohort calendar-day count is wrong")
        if cohort["sample_per_channel"] != 500:
            raise AuditV3Error("cohort sample size differs from the preregistered design")
        if not isinstance(cohort["selection_seed"], str) or len(cohort["selection_seed"]) < 24:
            raise AuditV3Error("cohort selection seed is invalid")
        if _day(cohort["labels_may_begin_after"], "labels_may_begin_after") <= end:
            raise AuditV3Error("labels may not begin inside the source window")
        if prior_end is not None and start.toordinal() != prior_end.toordinal() + 1:
            raise AuditV3Error("cohort windows are not contiguous")
        prior_end = end
    if cohort_ids != {"v3a", "v3b"}:
        raise AuditV3Error("cohort ids are incomplete")
    return registration


def _cohort(registration: dict[str, Any], cohort_id: str) -> dict[str, Any]:
    for cohort in registration["cohorts"]:
        if cohort["cohort_id"] == cohort_id:
            return cohort
    raise AuditV3Error(f"unknown cohort: {cohort_id}")


def _article_date(value: object) -> str:
    compact = re.sub(r"[^0-9]", "", str(value or ""))[:8]
    if len(compact) != 8:
        raise AuditV3Error("article metadata has no valid date")
    try:
        parsed = date(int(compact[:4]), int(compact[4:6]), int(compact[6:8]))
    except ValueError as exc:
        raise AuditV3Error("article metadata has no valid date") from exc
    return parsed.isoformat()


def _domain(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AuditV3Error("article metadata has an invalid public URL")
    return parsed.netloc.lower().removeprefix("www.")


def _frame_digest(rows: Iterable[dict[str, Any]]) -> str:
    return _sha256(_canonical_bytes(list(rows)))


def build_frame(
    cohort_id: str,
    root: Path = ROOT,
    *,
    registration: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rebuild one cohort's exact group-contribution population."""
    registration = registration or _registration(root)
    cohort = _cohort(registration, cohort_id)
    start = _day(cohort["window_start"], "window_start")
    end = _day(cohort["window_end"], "window_end")
    expected_days = _days(start, end)
    attestation_dir = _safe_path(
        root,
        registration["source_collection"]["attestation_directory"],
        "attestation directory",
    )

    missing = [day.isoformat() for day in expected_days if not (attestation_dir / f"{day}.json").is_file()]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = "..." if len(missing) > 5 else ""
        raise AuditV3Error(
            f"{cohort_id} source window is incomplete: {len(missing)} missing day(s): {preview}{suffix}"
        )

    rows: list[dict[str, Any]] = []
    day_manifest: list[dict[str, Any]] = []
    regime: tuple[str, str, str] | None = None
    seen_frame_ids: set[str] = set()
    for day in expected_days:
        attestation_path = attestation_dir / f"{day}.json"
        attestation_raw, attestation = _read_object(attestation_path)
        if attestation.get("status") == "FRAME_FAILURE_NO_LABELS":
            reason = attestation.get("failure_reason")
            raise AuditV3Error(
                f"{cohort_id} contains a recorded frame failure on {day}: {reason}"
            )
        rebuilt = precision_frame_v3.build_day_attestation(
            day, root, require_live_hashes=False
        )
        if attestation != rebuilt:
            raise AuditV3Error(f"{day} attestation does not reproduce its source cache")
        if attestation.get("status") != "ELIGIBLE_SOURCE_DAY_NO_LABELS":
            raise AuditV3Error(f"{day} is not an eligible pre-label source day")
        if attestation.get("labels_seen") is not False or attestation.get("precision_estimated") is not False:
            raise AuditV3Error(f"{day} attestation is not label-free")

        current_regime = (
            str(attestation["matcher_specs_sha256"]),
            str(attestation["dictionaries_sha256"]),
            str(attestation["production_matcher_sha256"]),
        )
        if regime is None:
            regime = current_regime
        elif current_regime != regime:
            raise AuditV3Error("matcher or dictionary regime changed inside the cohort")

        source_path = _safe_path(root, attestation["source_cache"], "source cache")
        source_raw, source = _read_object(source_path)
        if _sha256(source_raw) != attestation["source_cache_sha256"]:
            raise AuditV3Error(f"{day} source cache hash changed")
        evidence = source.get("_matcher_evidence")
        if not isinstance(evidence, dict):
            raise AuditV3Error(f"{day} source cache lacks matcher evidence")
        specs = evidence.get("matcher_specs")
        matched = evidence.get("matched_document_keys")
        article_meta = evidence.get("article_meta")
        if not isinstance(specs, dict) or not isinstance(matched, dict) or not isinstance(article_meta, dict):
            raise AuditV3Error(f"{day} matcher evidence is malformed")
        india_keys = set(evidence.get("india_document_keys") or [])

        group_counts: dict[str, int] = {}
        channel_counts: dict[str, int] = defaultdict(int)
        for group in sorted(specs):
            spec = specs[group]
            if not isinstance(spec, dict) or not isinstance(spec.get("channel"), str):
                raise AuditV3Error(f"{day} has an invalid matcher group")
            channel = spec["channel"]
            if channel not in CHANNELS:
                raise AuditV3Error(f"{day} has an unknown channel")
            raw_keys = matched.get(group)
            if not isinstance(raw_keys, list) or not all(isinstance(key, str) for key in raw_keys):
                raise AuditV3Error(f"{day} has malformed matched keys")
            keys = set(raw_keys)
            eligible = keys & india_keys if spec.get("anchor") == "india" else keys
            group_counts[group] = len(eligible)
            channel_counts[channel] += len(eligible)
            for document_key in sorted(eligible):
                metadata = article_meta.get(document_key)
                if not isinstance(metadata, dict):
                    raise AuditV3Error(f"{day} contribution lacks article metadata")
                title = str(metadata.get("title") or "").strip()
                url = str(metadata.get("url") or "").strip()
                if not title:
                    raise AuditV3Error(f"{day} contribution has an empty title")
                frame_key = f"{day.isoformat()}|{channel}|{group}|{document_key}"
                frame_id = _sha256(frame_key.encode())
                if frame_id in seen_frame_ids:
                    raise AuditV3Error("frame contribution is duplicated")
                seen_frame_ids.add(frame_id)
                evidence_identity = _sha256(
                    _canonical_bytes(
                        {
                            "article_date": _article_date(metadata.get("date")),
                            "title": title,
                            "url": url,
                        }
                    )
                )
                rows.append(
                    {
                        "frame_id": frame_id,
                        "source_day": day.isoformat(),
                        "channel": channel,
                        "query_group": group,
                        "source_cache": attestation["source_cache"],
                        "source_cache_sha256": attestation["source_cache_sha256"],
                        "source_document_key": document_key,
                        "article_date": _article_date(metadata.get("date")),
                        "title": title,
                        "domain": _domain(url),
                        "url": url,
                        "evidence_identity_sha256": evidence_identity,
                    }
                )

        for group, observed in attestation["groups"].items():
            if group_counts.get(group) != observed["n_group_contributions"]:
                raise AuditV3Error(f"{day} group contribution count changed")
        for channel, observed in attestation["channels"].items():
            if channel_counts.get(channel, 0) != observed["n_group_contributions"]:
                raise AuditV3Error(f"{day} channel contribution count changed")
        day_manifest.append(
            {
                "day": day.isoformat(),
                "attestation_path": attestation_path.relative_to(root).as_posix(),
                "attestation_sha256": _sha256(attestation_raw),
                "source_cache": attestation["source_cache"],
                "source_cache_sha256": attestation["source_cache_sha256"],
                "n_english_documents": attestation["n_english_documents"],
                "n_group_contributions": sum(group_counts.values()),
            }
        )

    rows.sort(key=lambda row: row["frame_id"])
    frame_by_channel = {
        channel: sum(row["channel"] == channel for row in rows) for channel in CHANNELS
    }
    if any(count == 0 for count in frame_by_channel.values()):
        raise AuditV3Error("one or more channels have an empty source frame")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": registration["audit_id"],
        "cohort_id": cohort_id,
        "status": "COMPLETE_LABEL_FREE_SOURCE_FRAME",
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "calendar_days": len(expected_days),
        "source_days": day_manifest,
        "n_group_contributions": len(rows),
        "frame_by_channel": frame_by_channel,
        "unique_evidence_identities": len(
            {row["evidence_identity_sha256"] for row in rows}
        ),
        "frame_sha256": _frame_digest(rows),
        "labels_seen": False,
        "precision_estimated": False,
    }
    return rows, manifest


def _rank(seed: str, purpose: str, identifier: str) -> str:
    return _sha256(f"{seed}|{purpose}|{identifier}".encode())


def select_sample(
    rows: list[dict[str, Any]],
    cohort: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select the preregistered contribution SRS by language-neutral hash rank."""
    seed = cohort["selection_seed"]
    target = cohort["sample_per_channel"]
    selected: list[dict[str, Any]] = []
    selection_by_channel: dict[str, dict[str, Any]] = {}
    for channel in CHANNELS:
        pool = [row for row in rows if row["channel"] == channel]
        ranked = sorted(
            pool,
            key=lambda row: (_rank(seed, f"sample:{channel}", row["frame_id"]), row["frame_id"]),
        )
        n = min(target, len(ranked))
        if n == 0:
            raise AuditV3Error(f"{channel} has an empty sampling frame")
        channel_rows = []
        for index, source in enumerate(ranked[:n], start=1):
            item = dict(source)
            item["selection_rank"] = index
            item["inclusion_probability"] = n / len(ranked)
            item["audit_id"] = "V3" + _sha256(
                f"{seed}|audit|{source['frame_id']}".encode()
            )[:17].upper()
            channel_rows.append(item)
        selected.extend(channel_rows)
        selection_by_channel[channel] = {
            "frame_n": len(ranked),
            "sample_n": n,
            "inclusion_probability": n / len(ranked),
            "census": n == len(ranked),
        }
    if len({row["audit_id"] for row in selected}) != len(selected):
        raise AuditV3Error("audit-id collision")
    selected.sort(key=lambda row: row["audit_id"])
    sample_meta = {
        "algorithm": "sha256_rank_v1",
        "selection_seed": seed,
        "sampling_unit": "group-qualified production contribution instance",
        "selection_by_channel": selection_by_channel,
        "sample_rows": len(selected),
        "unique_evidence_identities": len(
            {row["evidence_identity_sha256"] for row in selected}
        ),
        "repeated_evidence_rows": len(selected)
        - len({row["evidence_identity_sha256"] for row in selected}),
        "sample_sha256": _frame_digest(selected),
    }
    return selected, sample_meta


def _coder_row(row: dict[str, Any]) -> dict[str, str]:
    return {
        "audit_id": row["audit_id"],
        "channel": row["channel"],
        "article_date": row["article_date"],
        "title": row["title"],
        "domain": row["domain"],
        "url": row["url"],
        "coder_label": "",
        "coder_confidence": "",
        "evidence_access_status": "",
        "evidence_accessed_at_utc": "",
        "coder_note": "",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CODER_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _pilot_rows(registration: dict[str, Any], root: Path) -> list[dict[str, str]]:
    pilot = registration["coding"]["pilot"]
    source_path = _safe_path(root, pilot["source_path"], "pilot source")
    raw, source = _read_object(source_path)
    if _sha256(raw) != pilot["source_sha256"]:
        raise AuditV3Error("pilot source changed")
    matched = source.get("matched")
    meta = source.get("meta")
    india = set(source.get("india") or [])
    if not isinstance(matched, dict) or not isinstance(meta, dict):
        raise AuditV3Error("pilot source is malformed")
    specs = precision_frame_v3._active_specs_from_dictionary(root)
    candidates: dict[str, dict[str, dict[str, str]]] = {channel: {} for channel in CHANNELS}
    for group, spec in specs.items():
        raw_keys = matched.get(group)
        if not isinstance(raw_keys, list):
            raise AuditV3Error("pilot matched-key frame is incomplete")
        keys = set(raw_keys)
        eligible = keys & india if spec.get("anchor") == "india" else keys
        channel = spec["channel"]
        for key in eligible:
            record = meta.get(key)
            if not isinstance(record, dict):
                continue
            title = str(record.get("title") or "").strip()
            url = str(record.get("url") or "").strip()
            if not title or not url:
                continue
            identity = _sha256(_canonical_bytes({"title": title, "url": url}))
            candidates[channel].setdefault(
                identity,
                {
                    "audit_id": "P3" + _sha256(
                        f"{pilot['selection_seed']}|{channel}|{identity}".encode()
                    )[:17].upper(),
                    "channel": channel,
                    "article_date": _article_date(record.get("date")),
                    "title": title,
                    "domain": _domain(url),
                    "url": url,
                    "coder_label": "",
                    "coder_confidence": "",
                    "evidence_access_status": "",
                    "evidence_accessed_at_utc": "",
                    "coder_note": "",
                },
            )
    rows: list[dict[str, str]] = []
    for channel in CHANNELS:
        ranked = sorted(
            candidates[channel].items(),
            key=lambda item: (
                _rank(pilot["selection_seed"], f"pilot:{channel}", item[0]),
                item[0],
            ),
        )
        if len(ranked) < pilot["per_channel"]:
            raise AuditV3Error(f"pilot source has too few {channel} items")
        rows.extend(item[1] for item in ranked[: pilot["per_channel"]])
    return sorted(
        rows,
        key=lambda row: _rank(pilot["selection_seed"], "pilot-order", row["audit_id"]),
    )


def write_package(cohort_id: str, output: Path, root: Path = ROOT) -> Path:
    """Build one private package atomically, always outside the repository."""
    root = root.resolve()
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise AuditV3Error(
            "private coder package destination must be outside the repository: "
            f"{output}"
        )

    registration = _registration(root)
    cohort = _cohort(registration, cohort_id)
    rows, frame_manifest = build_frame(
        cohort_id, root, registration=registration
    )
    selected, sample_meta = select_sample(rows, cohort)

    if output.exists():
        raise AuditV3Error(f"refusing to overwrite package path: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        registration_path = root / "validation" / "precision_v3" / "registration.json"
        shutil.copyfile(registration_path, temp / "registration.json")
        (temp / "frame_manifest.json").write_text(
            json.dumps(frame_manifest, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (temp / "sample_key.json").write_text(
            json.dumps(
                {
                    "_meta": {
                        "schema_version": SCHEMA_VERSION,
                        "audit_id": registration["audit_id"],
                        "cohort_id": cohort_id,
                        "status": "FROZEN_SAMPLE_NO_LABELS",
                        **sample_meta,
                    },
                    "items": selected,
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        base_rows = [_coder_row(row) for row in selected]
        for index in (1, 2):
            ordered = sorted(
                base_rows,
                key=lambda row: (
                    _rank(cohort["selection_seed"], f"coder-{index}-order", row["audit_id"]),
                    row["audit_id"],
                ),
            )
            _write_csv(temp / f"coder_sheet_c{index}.csv", ordered)
        _write_csv(temp / "pilot_sheet.csv", _pilot_rows(registration, root))

        package_files = sorted(
            path for path in temp.iterdir() if path.name != "package_manifest.json"
        )
        package_manifest = {
            "schema_version": SCHEMA_VERSION,
            "audit_id": registration["audit_id"],
            "cohort_id": cohort_id,
            "status": "FROZEN_PRIVATE_CODER_PACKAGE_NO_LABELS",
            "files": [
                {
                    "path": path.name,
                    "sha256": _sha256(path.read_bytes()),
                    "bytes": path.stat().st_size,
                }
                for path in package_files
            ],
            "rights_notice": (
                "Private external-audit use only. Third-party titles and links are not "
                "relicensed; public disclosure requires the registered rights review."
            ),
            "labels_seen": False,
            "precision_estimated": False,
        }
        (temp / "package_manifest.json").write_text(
            json.dumps(package_manifest, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return output


def verify_package(package: Path) -> dict[str, Any]:
    _, manifest = _read_object(package / "package_manifest.json")
    expected = {
        "schema_version",
        "audit_id",
        "cohort_id",
        "status",
        "files",
        "rights_notice",
        "labels_seen",
        "precision_estimated",
    }
    if set(manifest) != expected or manifest.get("schema_version") != SCHEMA_VERSION:
        raise AuditV3Error("package manifest is invalid")
    if manifest.get("status") != "FROZEN_PRIVATE_CODER_PACKAGE_NO_LABELS":
        raise AuditV3Error("package is not in the frozen pre-label state")
    listed: set[str] = set()
    for item in manifest["files"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise AuditV3Error("package file record is invalid")
        name = item["path"]
        if name in listed or Path(name).name != name:
            raise AuditV3Error("package file path is invalid")
        listed.add(name)
        path = package / name
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise AuditV3Error(f"package file is missing: {name}") from exc
        if len(raw) != item["bytes"] or _sha256(raw) != item["sha256"]:
            raise AuditV3Error(f"package file changed: {name}")
    actual = {path.name for path in package.iterdir() if path.is_file()} - {"package_manifest.json"}
    if actual != listed:
        raise AuditV3Error("package has an unregistered or missing file")
    return manifest


def write_freeze_receipt(package: Path, destination: Path) -> Path:
    """Write the rights-safe receipt that must be externally anchored pre-label."""
    manifest = verify_package(package)
    manifest_path = package / "package_manifest.json"
    file_records = manifest["files"]
    by_name = {item["path"]: item["sha256"] for item in file_records}
    required = {
        "registration.json",
        "frame_manifest.json",
        "sample_key.json",
        "coder_sheet_c1.csv",
        "coder_sheet_c2.csv",
        "pilot_sheet.csv",
    }
    if set(by_name) != required:
        raise AuditV3Error("package file set differs from the registered package shape")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "audit_id": manifest["audit_id"],
        "cohort_id": manifest["cohort_id"],
        "status": "PUBLIC_FREEZE_RECEIPT_NO_LABELS",
        "package_manifest_sha256": _sha256(manifest_path.read_bytes()),
        "package_file_set_root_sha256": _sha256(_canonical_bytes(file_records)),
        "registration_sha256": by_name["registration.json"],
        "frame_manifest_sha256": by_name["frame_manifest.json"],
        "sample_key_sha256": by_name["sample_key.json"],
        "coder_sheet_c1_sha256": by_name["coder_sheet_c1.csv"],
        "coder_sheet_c2_sha256": by_name["coder_sheet_c2.csv"],
        "pilot_sheet_sha256": by_name["pilot_sheet.csv"],
        "contains_third_party_titles_or_urls": False,
        "labels_seen": False,
        "precision_estimated": False,
        "external_anchor_required_before_coder_access": True,
        "anchor_rule": (
            "Commit this exact receipt to the public repository and obtain its immutable "
            "commit identifier before either coder receives any package file."
        ),
    }
    encoded = json.dumps(receipt, indent=1, sort_keys=True) + "\n"
    if destination.exists():
        if destination.read_text(encoding="utf-8") != encoded:
            raise AuditV3Error(f"refusing to overwrite freeze receipt: {destination}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(encoded, encoding="utf-8")
    return destination


def verify_freeze_receipt(package: Path, receipt_path: Path) -> dict[str, Any]:
    """Bind scoring to the exact public pre-label receipt for the package."""
    manifest = verify_package(package)
    _, receipt = _read_object(receipt_path)
    expected_fields = {
        "schema_version",
        "audit_id",
        "cohort_id",
        "status",
        "package_manifest_sha256",
        "package_file_set_root_sha256",
        "registration_sha256",
        "frame_manifest_sha256",
        "sample_key_sha256",
        "coder_sheet_c1_sha256",
        "coder_sheet_c2_sha256",
        "pilot_sheet_sha256",
        "contains_third_party_titles_or_urls",
        "labels_seen",
        "precision_estimated",
        "external_anchor_required_before_coder_access",
        "anchor_rule",
    }
    if set(receipt) != expected_fields:
        raise AuditV3Error("freeze receipt fields are invalid")
    if (
        receipt["schema_version"] != SCHEMA_VERSION
        or receipt["audit_id"] != manifest["audit_id"]
        or receipt["cohort_id"] != manifest["cohort_id"]
        or receipt["status"] != "PUBLIC_FREEZE_RECEIPT_NO_LABELS"
        or receipt["labels_seen"] is not False
        or receipt["precision_estimated"] is not False
        or receipt["contains_third_party_titles_or_urls"] is not False
        or receipt["external_anchor_required_before_coder_access"] is not True
    ):
        raise AuditV3Error("freeze receipt state is invalid")
    manifest_raw = (package / "package_manifest.json").read_bytes()
    if receipt["package_manifest_sha256"] != _sha256(manifest_raw):
        raise AuditV3Error("freeze receipt does not bind the package manifest")
    records = manifest["files"]
    if receipt["package_file_set_root_sha256"] != _sha256(_canonical_bytes(records)):
        raise AuditV3Error("freeze receipt does not bind the package file set")
    by_name = {item["path"]: item["sha256"] for item in records}
    receipt_fields = {
        "registration_sha256": "registration.json",
        "frame_manifest_sha256": "frame_manifest.json",
        "sample_key_sha256": "sample_key.json",
        "coder_sheet_c1_sha256": "coder_sheet_c1.csv",
        "coder_sheet_c2_sha256": "coder_sheet_c2.csv",
        "pilot_sheet_sha256": "pilot_sheet.csv",
    }
    if any(receipt[field] != by_name[name] for field, name in receipt_fields.items()):
        raise AuditV3Error("freeze receipt has a mismatched package-file digest")
    return receipt


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != CODER_FIELDS:
                raise AuditV3Error(f"{path} has changed columns")
            return list(reader)
    except OSError as exc:
        raise AuditV3Error(f"unreadable coder sheet: {path}") from exc


def _parse_utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuditV3Error(f"{label} is not a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise AuditV3Error(f"{label} is not a UTC timestamp")
    return parsed


def verify_git_anchor(
    receipt_path: Path,
    anchor_commit: str,
    root: Path = ROOT,
) -> dict[str, str]:
    """Prove that the exact receipt bytes exist in a reachable Git commit."""
    if not re.fullmatch(r"[0-9a-f]{40}", anchor_commit):
        raise AuditV3Error("freeze-receipt anchor must be a full lowercase commit id")
    receipt = receipt_path.resolve()
    resolved_root = root.resolve()
    if receipt == resolved_root or resolved_root not in receipt.parents:
        raise AuditV3Error("freeze receipt must be inside the repository")
    relpath = receipt.relative_to(resolved_root).as_posix()

    def git(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", "-C", str(resolved_root), *args],
            check=False,
            capture_output=True,
        )

    resolved = git("rev-parse", "--verify", f"{anchor_commit}^{{commit}}")
    if resolved.returncode != 0 or resolved.stdout.decode().strip() != anchor_commit:
        raise AuditV3Error("freeze-receipt anchor commit is unavailable")
    if git("merge-base", "--is-ancestor", anchor_commit, "HEAD").returncode != 0:
        raise AuditV3Error("freeze-receipt anchor is not reachable from this checkout")
    committed = git("show", f"{anchor_commit}:{relpath}")
    if committed.returncode != 0:
        raise AuditV3Error("freeze receipt is absent from the anchor commit")
    try:
        live = receipt.read_bytes()
    except OSError as exc:
        raise AuditV3Error("freeze receipt is unavailable") from exc
    if committed.stdout != live:
        raise AuditV3Error("freeze receipt differs from its committed anchor")
    committed_at = git("show", "-s", "--format=%cI", anchor_commit)
    if committed_at.returncode != 0:
        raise AuditV3Error("freeze-receipt anchor time is unavailable")
    try:
        committed_at_value = datetime.fromisoformat(
            committed_at.stdout.decode().strip()
        )
    except ValueError as exc:
        raise AuditV3Error("freeze-receipt anchor time is invalid") from exc
    if committed_at_value.tzinfo is None:
        raise AuditV3Error("freeze-receipt anchor time has no timezone")
    committed_at_utc = committed_at_value.astimezone(timezone.utc)
    return {
        "commit": anchor_commit,
        "receipt_path": relpath,
        "committed_at_utc": committed_at_utc.isoformat().replace("+00:00", "Z"),
    }


def _coder_attestation(
    path: Path,
    sheet: Path,
    assignment: str,
    package_manifest: dict[str, Any],
    freeze_receipt: Path,
    anchor: dict[str, str],
) -> dict[str, str]:
    """Validate one private coder's hash-bound independence declaration."""
    raw, attestation = _read_object(path)
    expected = {
        "schema_version",
        "audit_id",
        "cohort_id",
        "coder_id",
        "coder_assignment",
        "sheet_sha256",
        "freeze_receipt_sha256",
        "freeze_receipt_commit",
        "packet_received_at_utc",
        "pilot_completed_at_utc",
        "sheet_completed_at_utc",
        "attested_at_utc",
        "statements",
    }
    if set(attestation) != expected or attestation.get("schema_version") != SCHEMA_VERSION:
        raise AuditV3Error(f"coder attestation fields are invalid: {path}")
    coder_id = attestation.get("coder_id")
    if not isinstance(coder_id, str) or not re.fullmatch(r"C[A-Z0-9_-]{2,31}", coder_id):
        raise AuditV3Error(f"coder attestation has an invalid opaque coder id: {path}")
    if (
        attestation.get("audit_id") != package_manifest["audit_id"]
        or attestation.get("cohort_id") != package_manifest["cohort_id"]
        or attestation.get("coder_assignment") != assignment
        or attestation.get("sheet_sha256") != _sha256(sheet.read_bytes())
        or attestation.get("freeze_receipt_sha256")
        != _sha256(freeze_receipt.read_bytes())
        or attestation.get("freeze_receipt_commit") != anchor["commit"]
    ):
        raise AuditV3Error(f"coder attestation does not bind its assigned evidence: {path}")
    statements = attestation.get("statements")
    if (
        not isinstance(statements, dict)
        or set(statements) != CODER_ATTESTATION_STATEMENTS
        or any(value is not True for value in statements.values())
    ):
        raise AuditV3Error(f"coder independence statements are incomplete: {path}")
    packet_received = _parse_utc(
        str(attestation["packet_received_at_utc"]), "packet_received_at_utc"
    )
    pilot_completed = _parse_utc(
        str(attestation["pilot_completed_at_utc"]), "pilot_completed_at_utc"
    )
    sheet_completed = _parse_utc(
        str(attestation["sheet_completed_at_utc"]), "sheet_completed_at_utc"
    )
    attested_at = _parse_utc(
        str(attestation["attested_at_utc"]), "attested_at_utc"
    )
    anchor_time = _parse_utc(anchor["committed_at_utc"], "anchor commit time")
    if not anchor_time <= packet_received <= pilot_completed <= sheet_completed <= attested_at:
        raise AuditV3Error(f"coder attestation chronology is invalid: {path}")
    return {
        "coder_id": coder_id,
        "coder_assignment": assignment,
        "sheet_sha256": attestation["sheet_sha256"],
        "attestation_sha256": _sha256(raw),
        "packet_received_at_utc": attestation["packet_received_at_utc"],
        "pilot_completed_at_utc": attestation["pilot_completed_at_utc"],
        "sheet_completed_at_utc": attestation["sheet_completed_at_utc"],
        "attested_at_utc": attestation["attested_at_utc"],
    }


def _coder_labels(
    submitted: Path,
    canonical: Path,
) -> dict[str, dict[str, str]]:
    expected_rows = _read_csv(canonical)
    observed_rows = _read_csv(submitted)
    expected = {row["audit_id"]: row for row in expected_rows}
    if len(expected) != len(expected_rows) or len(observed_rows) != len(expected_rows):
        raise AuditV3Error(f"{submitted} has a missing or duplicate row")
    labels: dict[str, dict[str, str]] = {}
    for row in observed_rows:
        audit_id = row.get("audit_id", "")
        if audit_id in labels or audit_id not in expected:
            raise AuditV3Error(f"{submitted} has an unknown or duplicate audit id")
        for field in LOCKED_FIELDS:
            if row.get(field, "") != expected[audit_id][field]:
                raise AuditV3Error(f"{submitted} changed locked field {field}")
        label = row.get("coder_label", "").strip().upper()
        confidence = row.get("coder_confidence", "").strip().upper()
        access = row.get("evidence_access_status", "").strip().upper()
        accessed_at = row.get("evidence_accessed_at_utc", "").strip()
        note = row.get("coder_note", "").strip()
        if label not in LABELS:
            raise AuditV3Error(f"{submitted} has an invalid or unfilled label")
        if confidence not in CONFIDENCE:
            raise AuditV3Error(f"{submitted} has an invalid or unfilled confidence")
        if access not in ACCESS:
            raise AuditV3Error(f"{submitted} has an invalid evidence-access status")
        if access == "TITLE_ONLY" and accessed_at:
            raise AuditV3Error(f"{submitted} timestamps unopened evidence")
        if access != "TITLE_ONLY":
            _parse_utc(accessed_at, "evidence_accessed_at_utc")
        if (label == "ABSTAIN" or confidence == "LOW") and not note:
            raise AuditV3Error(f"{submitted} must explain abstentions and low confidence")
        labels[audit_id] = {
            "label": label,
            "confidence": confidence,
            "access": access,
            "accessed_at": accessed_at,
            "note": note,
        }
    return labels


def _wilson(successes: int, n: int, z: float = 1.959963984540054) -> list[float] | None:
    if n == 0:
        return None
    proportion = successes / n
    denominator = 1 + z * z / n
    centre = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(
        proportion * (1 - proportion) / n + z * z / (4 * n * n)
    ) / denominator
    return [round(centre - half, 4), round(centre + half, 4)]


def _finite_population_interval(
    population_n: int,
    sample_n: int,
    successes: int,
    alpha: float = 0.05,
) -> list[float]:
    """Equal-tail exact interval for a finite-population success share."""
    if not 0 <= successes <= sample_n <= population_n or population_n <= 0:
        raise AuditV3Error("finite-population interval inputs are invalid")
    possible_low = successes
    possible_high = population_n - (sample_n - successes)

    def log_choose(n: int, k: int) -> float:
        if k < 0 or k > n:
            return float("-inf")
        return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)

    def probability(candidate: int, observed: int) -> float:
        minimum = max(0, sample_n - (population_n - candidate))
        maximum = min(sample_n, candidate)
        if not minimum <= observed <= maximum:
            return 0.0
        value = (
            log_choose(candidate, observed)
            + log_choose(population_n - candidate, sample_n - observed)
            - log_choose(population_n, sample_n)
        )
        return math.exp(value)

    def lower_tail(candidate: int) -> float:
        minimum = max(0, sample_n - (population_n - candidate))
        maximum = min(successes, sample_n, candidate)
        return math.fsum(probability(candidate, observed) for observed in range(minimum, maximum + 1))

    def upper_tail(candidate: int) -> float:
        maximum = min(sample_n, candidate)
        minimum = max(successes, 0, sample_n - (population_n - candidate))
        return math.fsum(probability(candidate, observed) for observed in range(minimum, maximum + 1))

    # P(X >= successes | K) grows monotonically with the population success
    # count K.  P(X <= successes | K) falls monotonically.  Binary inversion
    # avoids a population-sized scan when the Gulf frame contains tens of
    # thousands of contribution instances.
    lo, hi = possible_low, possible_high
    while lo < hi:
        middle = (lo + hi) // 2
        if upper_tail(middle) > alpha / 2:
            hi = middle
        else:
            lo = middle + 1
    lower_k = lo

    lo, hi = possible_low, possible_high
    while lo < hi:
        middle = (lo + hi + 1) // 2
        if lower_tail(middle) > alpha / 2:
            lo = middle
        else:
            hi = middle - 1
    upper_k = lo
    return [round(lower_k / population_n, 4), round(upper_k / population_n, 4)]


def _gwet_ac1(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    pooled_on = (
        sum(left == "ON" for left, _ in pairs)
        + sum(right == "ON" for _, right in pairs)
    ) / (2 * len(pairs))
    chance = 2 * pooled_on * (1 - pooled_on)
    if chance >= 1:
        return None
    return round((observed - chance) / (1 - chance), 4)


def _repeat_conflicts(
    key_rows: list[dict[str, Any]], labels: dict[str, dict[str, str]]
) -> list[dict[str, Any]]:
    identities: dict[tuple[str, str], set[str]] = defaultdict(set)
    audit_ids: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in key_rows:
        label = labels[row["audit_id"]]["label"]
        if label not in FIRM_LABELS:
            continue
        key = (row["channel"], row["evidence_identity_sha256"])
        identities[key].add(label)
        audit_ids[key].append(row["audit_id"])
    return [
        {
            "channel": channel,
            "evidence_identity_sha256": identity,
            "labels": sorted(identities[(channel, identity)]),
            "audit_ids": sorted(audit_ids[(channel, identity)]),
        }
        for channel, identity in sorted(identities)
        if len(identities[(channel, identity)]) > 1
    ]


def _coder_summary(
    key_rows: list[dict[str, Any]],
    labels: dict[str, dict[str, str]],
    selection: dict[str, Any],
) -> dict[str, Any]:
    by_channel: dict[str, Any] = {}
    for channel in CHANNELS:
        rows = [row for row in key_rows if row["channel"] == channel]
        channel_labels = [labels[row["audit_id"]]["label"] for row in rows]
        on = channel_labels.count("ON")
        off = channel_labels.count("OFF")
        abstain = channel_labels.count("ABSTAIN")
        firm_n = on + off
        sample_n = len(rows)
        population_n = selection[channel]["frame_n"]
        firm_interval = _wilson(on, firm_n)
        worst_case_interval = _finite_population_interval(
            population_n, sample_n, on
        )
        passed = (
            firm_n >= 400
            and firm_interval is not None
            and firm_interval[0] >= 0.80
            and worst_case_interval[0] >= 0.80
        )
        by_channel[channel] = {
            "frame_n": population_n,
            "sample_n": sample_n,
            "on": on,
            "off": off,
            "abstain": abstain,
            "firm_n": firm_n,
            "firm_label_precision": round(on / firm_n, 4) if firm_n else None,
            "firm_label_wilson_95": firm_interval,
            "all_abstentions_off_precision": round(on / sample_n, 4),
            "finite_population_95_all_abstentions_off": worst_case_interval,
            "gate": "PASS" if passed else ("FAIL" if firm_n >= 400 else "INCONCLUSIVE_TOO_FEW_FIRM_LABELS"),
        }
    return {"channels": by_channel, "all_channels_pass": all(value["gate"] == "PASS" for value in by_channel.values())}


def _reliability(
    key_rows: list[dict[str, Any]],
    left: dict[str, dict[str, str]],
    right: dict[str, dict[str, str]],
) -> dict[str, Any]:
    conflicts = {
        "coder_1": _repeat_conflicts(key_rows, left),
        "coder_2": _repeat_conflicts(key_rows, right),
    }
    channels: dict[str, Any] = {}
    for channel in CHANNELS:
        by_identity: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in key_rows:
            if row["channel"] != channel:
                continue
            pair = (left[row["audit_id"]]["label"], right[row["audit_id"]]["label"])
            if pair[0] in FIRM_LABELS and pair[1] in FIRM_LABELS:
                by_identity[row["evidence_identity_sha256"]].append(pair)
        pairs: list[tuple[str, str]] = []
        for _identity, observed in by_identity.items():
            left_values = {pair[0] for pair in observed}
            right_values = {pair[1] for pair in observed}
            if len(left_values) == 1 and len(right_values) == 1:
                pairs.append((next(iter(left_values)), next(iter(right_values))))
        raw = round(sum(a == b for a, b in pairs) / len(pairs), 4) if pairs else None
        ac1 = _gwet_ac1(pairs)
        constant = len({label for pair in pairs for label in pair}) <= 1
        channel_conflicts = [
            item
            for coder_conflicts in conflicts.values()
            for item in coder_conflicts
            if item["channel"] == channel
        ]
        evaluable = len(pairs) >= 400 and not constant and not channel_conflicts
        passed = evaluable and raw is not None and raw >= 0.90 and ac1 is not None and ac1 >= 0.70
        channels[channel] = {
            "n_unique_firm_overlap": len(pairs),
            "raw_agreement": raw,
            "gwet_ac1": ac1,
            "constant_labels": constant,
            "repeat_conflicts": channel_conflicts,
            "gate": "PASS" if passed else ("FAIL" if evaluable else "INCONCLUSIVE"),
        }
    return {"channels": channels, "coder_repeat_conflicts": conflicts, "all_channels_pass": all(value["gate"] == "PASS" for value in channels.values())}


def score_package(
    package: Path,
    coder_paths: list[Path],
    freeze_receipt: Path,
    anchor_commit: str,
    attestation_paths: list[Path],
    root: Path = ROOT,
) -> dict[str, Any]:
    """Score one or two frozen coder sheets without adjudicating the primary."""
    if len(coder_paths) not in {1, 2}:
        raise AuditV3Error("score requires one or two coder sheets")
    if len(attestation_paths) != len(coder_paths):
        raise AuditV3Error("each coder sheet requires one coder attestation")
    package_manifest = verify_package(package)
    receipt = verify_freeze_receipt(package, freeze_receipt)
    anchor = verify_git_anchor(freeze_receipt, anchor_commit, root)
    _, registration = _read_object(package / "registration.json")
    if registration.get("audit_id") != package_manifest["audit_id"]:
        raise AuditV3Error("package registration does not match its manifest")
    _, key = _read_object(package / "sample_key.json")
    key_rows = key.get("items")
    if not isinstance(key_rows, list) or not all(isinstance(row, dict) for row in key_rows):
        raise AuditV3Error("sample key is invalid")
    selection = key.get("_meta", {}).get("selection_by_channel")
    if not isinstance(selection, dict):
        raise AuditV3Error("sample selection metadata is missing")
    labels = [
        _coder_labels(path, package / f"coder_sheet_c{index}.csv")
        for index, path in enumerate(coder_paths, start=1)
    ]
    submission_records = [
        _coder_attestation(
            attestation,
            sheet,
            f"coder_{index}",
            package_manifest,
            freeze_receipt,
            anchor,
        )
        for index, (sheet, attestation) in enumerate(
            zip(coder_paths, attestation_paths), start=1
        )
    ]
    if len({record["coder_id"] for record in submission_records}) != len(
        submission_records
    ):
        raise AuditV3Error("primary coder ids are not distinct")
    if len({record["sheet_sha256"] for record in submission_records}) != len(
        submission_records
    ):
        raise AuditV3Error("primary coder submissions are byte-identical")
    summaries = [
        {"coder": f"coder_{index}", **_coder_summary(key_rows, coder, selection)}
        for index, coder in enumerate(labels, start=1)
    ]
    reliability = _reliability(key_rows, labels[0], labels[1]) if len(labels) == 2 else None
    return {
        "_meta": {
            "schema_version": SCHEMA_VERSION,
            "audit_id": package_manifest["audit_id"],
            "cohort_id": package_manifest["cohort_id"],
            "primary_estimand": (
                "Coder-specific ON share among group-qualified production contribution "
                "instances in the fixed cohort."
            ),
            "missingness_rule": (
                "Firm-only precision is descriptive; the pass gate also treats every "
                "ABSTAIN as OFF and uses an exact finite-population interval."
            ),
            "adjudication": (
                "No adjudicated label replaces either coder's primary estimate. A masked "
                "third review may be published only as a secondary diagnostic."
            ),
            "comparison_claim_authorized": False,
            "freeze_receipt_sha256": _sha256(freeze_receipt.read_bytes()),
            "freeze_receipt_package_manifest_sha256": receipt[
                "package_manifest_sha256"
            ],
            "freeze_receipt_anchor": anchor,
        },
        "coder_submissions": submission_records,
        "coder_results": summaries,
        "inter_coder_reliability": reliability,
        "overall_gate": (
            "PASS"
            if all(summary["all_channels_pass"] for summary in summaries)
            and reliability is not None
            and reliability["all_channels_pass"]
            else "NOT_PASS"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preflight", choices=("v3a", "v3b"))
    actions.add_argument("--build", choices=("v3a", "v3b"))
    actions.add_argument("--score", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--freeze-receipt", type=Path)
    parser.add_argument("--anchor-commit")
    parser.add_argument(
        "--coder-attestation", action="append", default=[], type=Path
    )
    parser.add_argument("coder_sheets", nargs="*", type=Path)
    args = parser.parse_args()

    if args.preflight:
        rows, manifest = build_frame(args.preflight)
        print(
            json.dumps(
                {
                    **manifest,
                    "preflight_only": True,
                    "frame_rows_verified": len(rows),
                },
                indent=1,
                sort_keys=True,
            )
        )
        return
    if args.build:
        if args.output is None:
            parser.error("--build requires --output")
        if args.freeze_receipt is None:
            parser.error("--build requires --freeze-receipt")
        if args.anchor_commit is not None or args.coder_attestation:
            parser.error("coder attestations and anchor commit are not accepted with --build")
        if args.coder_sheets:
            parser.error("coder sheets are not accepted with --build")
        destination = write_package(args.build, args.output)
        receipt = write_freeze_receipt(destination, args.freeze_receipt)
        print(f"[precision-v3] wrote frozen private package: {destination}")
        print(f"[precision-v3] commit this receipt before coder access: {receipt}")
        return
    if args.score:
        if args.output is None:
            parser.error("--score requires --output")
        if args.freeze_receipt is None:
            parser.error("--score requires --freeze-receipt")
        if args.anchor_commit is None:
            parser.error("--score requires --anchor-commit")
        result = score_package(
            args.score,
            args.coder_sheets,
            args.freeze_receipt,
            args.anchor_commit,
            args.coder_attestation,
        )
        encoded = (json.dumps(result, indent=1, sort_keys=True) + "\n").encode()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise AuditV3Error(f"refusing to overwrite scored result: {args.output}") from exc
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        print(f"[precision-v3] wrote scored result: {args.output}")


if __name__ == "__main__":
    main()
