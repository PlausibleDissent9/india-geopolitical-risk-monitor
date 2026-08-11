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

LIVE PINS vs FROZEN PINS
Not every mismatch is a defect, and treating them alike would make this
useless. A LIVE pin (a contract, profile or registry) must track the bytes it
names -- if it drifts, something is broken now. A FROZEN pin records what a
file contained at a moment that has passed: a registration pins the versions
AS OF registration, a replay fixture pins the world its replay assumes, a
completion record pins the artifact as delivered. "Updating" one of those does
not fix anything; it falsifies a record.

So the frozen owners are listed explicitly below, with a reason each, and only
they are allowed to carry a mismatch. That list is an inventory lock, not an
ignore list: a new frozen file must be added here deliberately, in the commit
that introduces it, and a frozen file whose pins all match will be reported so
the entry can be retired rather than left to rot.

A frozen pin whose target HAS drifted is still reported (as information, not
failure), because it is worth knowing that a file certified at some commit no
longer matches what is served today. That is a governance question -- is the
deliverable still complete? -- and burying it in an allowlist would be exactly
the kind of silent green this repo keeps finding and removing.

  python scripts/verify_digest_pins.py          # report; exit 1 if any LIVE pin is stale
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

# Files whose pins are historical records, with the reason each is frozen.
#
# THREE, not four. The consequence_plan replay fixture was listed here and has
# been REMOVED: it never drifted. It looked like it had, because _resolve
# compared its pins against the repo's schemas/ and governance/ instead of the
# fixture's own shadowing copies. Exempting it was the worse half of that bug
# -- a healthy file excused from checking, which would have hidden real drift
# in it forever. With resolution fixed it is fully consistent and is now
# actively verified, which is where it belongs.
#
# The lesson generalises: an exemption granted on the strength of a failure
# you have not explained is how a checker becomes decoration.
FROZEN_OWNERS: dict[str, str] = {
    "validation/blind_audit_500/registration.json":
        "a registration: pins the code versions AS OF registration, so that a "
        "later reader can tell what the blind audit actually ran against",
    "validation/precision_v3/registration.json":
        "a registration, same reason",
    "design/igrm_max_launch_contract.json":
        "completion records, each carrying the exact commit that delivered "
        "it; the pin describes the artifact as delivered, not as served today",
}


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


def _resolve(owner: Path, target: str) -> Path | None:
    """Find the file a pin names, NEAREST BASE FIRST: walk outward from the
    owner's directory to the repo root and take the first base that resolves.

    The ordering is the whole correctness argument. An earlier version tried
    the repo root FIRST, which is wrong whenever a self-contained fixture
    shadows a repo directory -- and the consequence_plan replay fixture ships
    its own schemas/ and governance/ trees. Its registry pins
    "schemas/common.schema.json" meaning ITS OWN copy; root-first compared the
    repo's copy instead. That silently verified 18 pins against the wrong
    files, and then reported the fixture as drifted when it was internally
    consistent all along.

    Nearest-first is correct for both shapes: a governance file pinning
    "src/event_ledger.py" finds nothing under governance/ and walks out to the
    repo root, while the fixture finds its own copy immediately. The repo root
    is simply the last ancestor tried, not a special case.
    """
    if ".." in Path(target).parts or Path(target).is_absolute():
        return None
    base = owner.parent
    while True:
        candidate = base / target
        if candidate.is_file():
            return candidate
        if base == ROOT or ROOT not in base.parents:
            return None
        base = base.parent


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def audit() -> dict[str, Any]:
    """Return the pin audit as data, so tests assert on it rather than on
    printed text."""
    checked = 0
    stale: list[tuple[str, str, str, str, str]] = []
    frozen_drift: list[tuple[str, str, str, str, str]] = []
    frozen_owners_seen: set[str] = set()
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
                # Most pins are repo-relative. Self-contained fixtures pin
                # their own members RELATIVE TO THE FIXTURE ROOT, which is
                # some ancestor of the owner rather than the repo root or the
                # owner's own directory -- resolving only against ROOT
                # reported 24 phantom misses. Walk outward from the owner to
                # the repo root and take the first base that resolves.
                pointee = _resolve(jf, target)
                if pointee is None:
                    missing.append((rel_owner, target))
                    continue
                actual = sha256_of(pointee)
                checked += 1
                if actual == declared:
                    continue
                row = (rel_owner, key, target, declared, actual or "")
                if rel_owner in FROZEN_OWNERS:
                    frozen_owners_seen.add(rel_owner)
                    frozen_drift.append(row)
                else:
                    stale.append(row)

    return {
        "checked": checked,
        "stale": stale,
        "frozen_drift": frozen_drift,
        "missing": missing,
        # A frozen entry whose pins ALL match no longer needs the exemption.
        # Reported so the list can be retired rather than left to rot.
        "frozen_owners_without_drift": sorted(
            set(FROZEN_OWNERS) - frozen_owners_seen),
    }


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    result = audit()
    stale = result["stale"]

    if not quiet:
        print(f"[pins] checked {result['checked']} digest pin(s)")
        for owner, target in result["missing"]:
            print(f"[pins] pin names a path that does not exist: {owner} -> {target}")
        if result["frozen_drift"]:
            print(f"[pins] {len(result['frozen_drift'])} frozen pin(s) have "
                  f"drifted -- expected, reported, NOT a failure:")
            for owner, _key, target, _d, _a in result["frozen_drift"]:
                print(f"       {owner} -> {target}")
                print(f"         frozen because: {FROZEN_OWNERS[owner]}")
        for owner in result["frozen_owners_without_drift"]:
            print(f"[pins] {owner} is listed as frozen but every pin in it "
                  f"matches; the exemption can be retired")

    if stale:
        print(f"\n[pins] {len(stale)} STALE LIVE pin(s) -- a contract, profile "
              f"or registry no longer matches the bytes it names:", file=sys.stderr)
        for owner, key, target, declared, actual in stale:
            print(f"  {owner}\n    {key} of {target}\n"
                  f"      declared {declared}\n      actual   {actual}",
                  file=sys.stderr)
        print("\n  Re-derive the cascade to a fixpoint (see "
              "operating notes), or investigate if no change should have "
              "moved these.", file=sys.stderr)
        return 1

    if not quiet:
        print("[pins] every live digest pin matches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
