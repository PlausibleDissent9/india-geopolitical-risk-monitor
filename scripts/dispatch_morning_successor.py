#!/usr/bin/env python3
"""Prove immutable remote backlog progress before one serialized successor run."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path
from typing import NoReturn


class SuccessorDispatchError(RuntimeError):
    pass


def _fail(code: str) -> NoReturn:
    raise SuccessorDispatchError(code)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode()


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, cwd=root, capture_output=True)


def _regular_blob(root: Path, commit: str, relative: str) -> bytes:
    tree = _run(root, "git", "ls-tree", "-z", "--full-tree", commit, "--", relative)
    records = tree.stdout.split(b"\0")
    if tree.returncode or records[-1] or len(records) != 2:
        _fail("successor_progress_blob_missing")
    metadata, encoded_path = records[0].split(b"\t", 1)
    mode, kind, object_id = metadata.split(b" ")
    if (
        mode != b"100644"
        or kind != b"blob"
        or encoded_path.decode() != relative
        or re.fullmatch(rb"[0-9a-f]{40,64}", object_id) is None
    ):
        _fail("successor_progress_blob_not_regular")
    shown = _run(root, "git", "show", f"{commit}:{relative}")
    if shown.returncode:
        _fail("successor_progress_blob_unreadable")
    return shown.stdout


def authorize(
    *, root: Path, base: str, result: str, target: date, source_run: str, authority_epoch: int
) -> dict[str, object]:
    if not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(
        r"[0-9a-f]{40}", result
    ):
        _fail("successor_commit_invalid")
    remote = _run(root, "git", "rev-parse", "origin/main").stdout.decode().strip()
    if remote != result or result == base:
        _fail("successor_remote_did_not_advance")
    if target == date(2026, 8, 9):
        receipt = json.loads(
            _regular_blob(
                root,
                result,
                "data/raw/legacy_aggregate_verification/2026-08-09.json",
            )
        )
        if (
            receipt.get("target_date") != target.isoformat()
            or receipt.get("status") != "legacy_verified_under_aggregate_profile"
            or receipt.get("original_bytes_rewritten") is not False
        ):
            _fail("successor_legacy_progress_invalid")
    else:
        latest = json.loads(_regular_blob(root, result, "docs/data/latest.json"))
        if latest.get("date") != target.isoformat():
            _fail("successor_measured_progress_invalid")
    if authority_epoch < 1 or authority_epoch > 3:
        _fail("successor_authority_epoch_exhausted")
    receipt = {
        "schema_version": "1.0.0",
        "source_run": source_run,
        "base_commit": base,
        "result_commit": result,
        "target_date": target.isoformat(),
        "authority_epoch": authority_epoch,
        "dispatch_authorized": True,
        "dedupe_boundary": "serialized_workflow_plus_exact_remote_progress",
    }
    receipt["record_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--target", type=date.fromisoformat, required=True)
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--authority-epoch", type=int, required=True)
    args = parser.parse_args()
    try:
        value = authorize(
            root=Path.cwd(),
            base=args.base,
            result=args.result,
            target=args.target,
            source_run=args.source_run,
            authority_epoch=args.authority_epoch,
        )
    except SuccessorDispatchError as exc:
        print(json.dumps({"dispatch_authorized": False, "reason": str(exc)}))
        return
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
