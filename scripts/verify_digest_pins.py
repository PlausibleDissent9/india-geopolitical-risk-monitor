#!/usr/bin/env python3
"""Verify every {path, sha256} digest pin in the repository.

WHY THIS EXISTS
A hashed primitive's bytes are pinned in many places: extension profiles,
governance contracts, attestation registries, and hardcoded constants. When a
primitive changes, EVERY pin that references it -- transitively -- has to be
re-derived, because a pin whose target moved is exactly what the integrity
checks are built to refuse.

That cascade was previously done by hand, and a hand-done cascade is
incomplete in a way nothing detects until a specific test happens to exercise
the specific pin. On 2026-08-10 a perf change updated the CONTENTS of four
governance/profile files but not the pins OF those files, and the result was
85 failures spread across six suites, each reporting a refusal code rather
than the actual cause. This script names the cause directly.

It is a verifier, not a fixer: it never rewrites a pin. A pin that is wrong is
either a stale cascade (re-derive it) or a real tampering signal (investigate
it), and only a human should decide which.

  python scripts/verify_digest_pins.py          # report; exit 1 if any stale
  python scripts/verify_digest_pins.py --quiet  # only failures
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
# Keys that carry a digest of the file named by a sibling "path" key.
_DIGEST_KEYS = ("sha256", "file_sha256")
_PATH_KEY = "path"


def tracked_json() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "*.json"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / rel for rel in out.split() if (ROOT / rel).is_file()]


def walk(node: Any) -> Iterator[dict[str, Any]]:
    """Yield every dict in a JSON tree."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item)


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    checked = 0
    stale: list[tuple[str, str, str, str, str]] = []
    missing: list[tuple[str, str]] = []

    for jf in sorted(tracked_json()):
        try:
            doc = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        rel_owner = jf.relative_to(ROOT).as_posix()
        for obj in walk(doc):
            target = obj.get(_PATH_KEY)
            if not isinstance(target, str):
                continue
            for key in _DIGEST_KEYS:
                declared = obj.get(key)
                # A 64-hex string alongside a repo-relative path is a pin.
                if not isinstance(declared, str) or len(declared) != 64:
                    continue
                pointee = ROOT / target
                if not pointee.is_file():
                    missing.append((rel_owner, target))
                    continue
                actual = sha256_of(pointee)
                checked += 1
                if actual != declared:
                    stale.append((rel_owner, key, target, declared, actual or ""))

    if not quiet:
        print(f"[pins] checked {checked} digest pin(s) across "
              f"{len(tracked_json())} tracked JSON file(s)")
        if missing:
            print(f"[pins] {len(missing)} pin(s) name a path that does not exist:")
            for owner, target in missing:
                print(f"       {owner} -> {target}")

    if stale:
        print(f"\n[pins] {len(stale)} STALE pin(s):", file=sys.stderr)
        for owner, key, target, declared, actual in stale:
            print(f"  {owner}\n    {key} of {target}\n"
                  f"      declared {declared}\n      actual   {actual}",
                  file=sys.stderr)
        return 1

    if not quiet:
        print("[pins] all digest pins match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
