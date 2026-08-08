#!/usr/bin/env python3
"""Rebuild the frozen blind-audit v2 and report its invalid study status.

The v2 artifacts are historically reproducible but are not a valid
production-precision study.  Living production matchers, dictionaries and the
versioned rubric are therefore resolved from the immutable registered
``base_commit`` rather than pinned to HEAD.  Frozen source evidence, coder
instructions, sheets and the study-specific builder must remain byte-identical
in the current checkout.

    python scripts/verify_blind_audit_v2.py
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "validation" / "blind_audit_500"
REGISTRATION = PACKAGE / "registration.json"
INVALIDATION = PACKAGE / "V2_INVALID.md"
REGISTRATION_SHA256 = (
    "c313c7a557be3788aea2724796c23ce7fa36a59fd0f381a395bf4a5c924a9b87"
)
INVALIDATION_MARKER = (
    "INVALID FOR PRODUCTION PRECISION. DO NOT FIELD, LABEL OR SCORE."
)


class VerificationError(RuntimeError):
    """The registration, its Git evidence, or its rebuild failed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_git(*args: str, root: Path = ROOT) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return proc.stdout


def _registered_paths(registration: dict[str, Any]) -> list[tuple[str, str]]:
    """All bytes frozen at the registration's immutable base commit."""
    inputs = registration["inputs"]
    paths = [
        (inputs["builder_and_scorer"], inputs["builder_and_scorer_sha256"]),
        (inputs["rubric_path"], inputs["rubric_sha256"]),
        (inputs["dictionaries_path"], inputs["dictionaries_sha256"]),
        (
            inputs["coder_instructions_path"],
            inputs["coder_instructions_sha256"],
        ),
    ]
    for collection in (
        "receipt_sources",
        "pilot_sources",
        "production_matcher_files",
    ):
        paths.extend(
            (item["path"], item["sha256"])
            for item in inputs[collection]
        )
    return paths


def _registered_outputs(registration: dict[str, Any]) -> list[tuple[str, str]]:
    sample = registration["sample"]
    return [
        (sample["coder_sheet_path"], sample["coder_sheet_sha256"]),
        (sample["coder_1_sheet_path"], sample["coder_1_sheet_sha256"]),
        (sample["coder_2_sheet_path"], sample["coder_2_sheet_sha256"]),
        (sample["sample_key_path"], sample["sample_key_sha256"]),
        (sample["pilot_sheet_path"], sample["pilot_sheet_sha256"]),
    ]


def _current_evidence_paths(
    registration: dict[str, Any],
) -> list[tuple[str, str]]:
    """Frozen evidence that must remain available at HEAD.

    The rubric, dictionary and production matchers are intentionally absent:
    they are living, versioned instruments whose v2 bytes are verified at the
    base commit.  The study-specific builder, instructions, source caches and
    coder artifacts are immutable evidence and remain pinned in the checkout.
    """
    inputs = registration["inputs"]
    paths = [
        (inputs["builder_and_scorer"], inputs["builder_and_scorer_sha256"]),
        (
            inputs["coder_instructions_path"],
            inputs["coder_instructions_sha256"],
        ),
    ]
    for collection in ("receipt_sources", "pilot_sources"):
        paths.extend(
            (item["path"], item["sha256"])
            for item in inputs[collection]
        )
    return [*paths, *_registered_outputs(registration)]


def _load_registration(path: Path = REGISTRATION) -> dict[str, Any]:
    raw = path.read_bytes()
    if path.resolve() == REGISTRATION.resolve() and _sha256(raw) != REGISTRATION_SHA256:
        raise VerificationError("the frozen v2 registration bytes changed")
    try:
        registration: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise VerificationError(f"invalid registration JSON: {exc}") from exc
    return registration


def _verify_invalidation(path: Path = INVALIDATION) -> None:
    if not path.is_file():
        raise VerificationError("the v2 invalidation notice is missing")
    if INVALIDATION_MARKER not in path.read_text(encoding="utf-8"):
        raise VerificationError("the v2 invalidation notice lost its do-not-field status")


def _verify_commit_inputs(registration: dict[str, Any], root: Path = ROOT) -> str:
    base_commit = registration.get("base_commit")
    if not isinstance(base_commit, str) or len(base_commit) != 40:
        raise VerificationError("registration has no full 40-character base_commit")
    _run_git("cat-file", "-e", f"{base_commit}^{{commit}}", root=root)
    for path, expected in _registered_paths(registration):
        observed = _sha256(_run_git("show", f"{base_commit}:{path}", root=root))
        if observed != expected:
            raise VerificationError(
                f"registered base blob mismatch for {path}: "
                f"expected {expected}, got {observed}"
            )
    return base_commit


def _verify_current_evidence(
    registration: dict[str, Any], root: Path = ROOT
) -> None:
    for path, expected in _current_evidence_paths(registration):
        candidate = root / path
        if not candidate.is_file():
            raise VerificationError(f"frozen current evidence is missing: {path}")
        observed = _sha256(candidate.read_bytes())
        if observed != expected:
            raise VerificationError(
                f"frozen current evidence mismatch for {path}: "
                f"expected {expected}, got {observed}"
            )


def _safe_extract(archive: bytes, target: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            parts = Path(member.name).parts
            if member.name.startswith("/") or ".." in parts:
                raise VerificationError(f"unsafe Git archive path: {member.name}")
            if member.issym() or member.islnk():
                raise VerificationError(
                    f"links are not allowed in the frozen Git archive: {member.name}"
                )
        bundle.extractall(target)


def _frame_report(checkout: Path) -> dict[str, dict[str, Any]]:
    probe = """
import hashlib, json
from src import blind_audit_500 as audit
out = {}
for channel, rows in audit._universe().items():
    ids = sorted(row["frame_id"] for row in rows)
    out[channel] = {
        "n": len(ids),
        "frame_ids_sha256": hashlib.sha256(
            ("\\n".join(ids) + "\\n").encode("utf-8")
        ).hexdigest(),
    }
print("FROZEN_FRAME_JSON=" + json.dumps(out, sort_keys=True))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(checkout)
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=checkout,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise VerificationError(f"frozen frame probe failed: {proc.stderr.strip()}")
    marker = "FROZEN_FRAME_JSON="
    line = next(
        (line for line in proc.stdout.splitlines() if line.startswith(marker)),
        None,
    )
    if line is None:
        raise VerificationError("frozen frame probe returned no structured report")
    return json.loads(line[len(marker) :])


def _rebuild(
    registration: dict[str, Any], base_commit: str, root: Path
) -> dict[str, Any]:
    archive = _run_git(
        "archive",
        "--format=tar",
        base_commit,
        "src",
        "auditor",
        "dictionaries.json",
        "source_tiers.json",
        "validation/blind_audit_500",
        "data/raw/receipt_days",
        root=root,
    )
    with tempfile.TemporaryDirectory(prefix="igrm-blind-v2-") as tmp:
        checkout = Path(tmp)
        _safe_extract(archive, checkout)
        # A no-op or partial builder must not inherit correct archived output.
        for path, _ in _registered_outputs(registration):
            candidate = checkout / path
            if candidate.exists():
                candidate.unlink()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(checkout)
        proc = subprocess.run(
            [sys.executable, "-m", "src.blind_audit_500", "--build"],
            cwd=checkout,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode:
            raise VerificationError(f"frozen rebuild failed: {proc.stderr.strip()}")
        rebuilt: dict[str, str] = {}
        for path, expected in _registered_outputs(registration):
            candidate = checkout / path
            if not candidate.is_file():
                raise VerificationError(f"frozen rebuild omitted {path}")
            observed = _sha256(candidate.read_bytes())
            rebuilt[path] = observed
            if observed != expected:
                raise VerificationError(
                    f"frozen rebuild mismatch for {path}: "
                    f"expected {expected}, got {observed}"
                )
        frame = _frame_report(checkout)
    expected_counts = registration["sample"][
        "matched_document_instance_frame_by_channel"
    ]
    observed_counts = {
        channel: values["n"] for channel, values in frame.items()
    }
    if observed_counts != expected_counts:
        raise VerificationError(
            f"frozen frame counts changed: expected {expected_counts}, "
            f"got {observed_counts}"
        )
    return {"output_sha256": rebuilt, "frame_by_channel": frame}


def verify() -> dict[str, Any]:
    registration = _load_registration()
    _verify_invalidation()
    base_commit = _verify_commit_inputs(registration)
    _verify_current_evidence(registration)
    rebuilt = _rebuild(registration, base_commit, ROOT)
    return {
        "status": "REPRODUCIBLE_INVALID_STUDY",
        "artifact_verification": "PASS",
        "study_status": "INVALID_BEFORE_CODING",
        "invalidation": str(INVALIDATION.relative_to(ROOT)),
        "registration_sha256": REGISTRATION_SHA256,
        "base_commit": base_commit,
        **rebuilt,
    }


def main() -> None:
    try:
        report = verify()
    except (OSError, KeyError, TypeError, VerificationError) as exc:
        print(f"[blind-audit-v2] FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
