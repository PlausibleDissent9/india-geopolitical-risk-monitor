#!/usr/bin/env python3
"""Report every pinned digest that no longer matches the bytes it pins.

Written after the H0 composition shipped a stale PINNED_RIGHTS_SHA256 for
days. Nothing said "stale digest". The authority plane simply could not
validate its own input and answered `source_authority_invalid` for 23 of
28 endpoints -- a confident, plausible, wrong reason. A stale pin does not
fail loudly as a stale pin; it fails as a believable wrong answer, which
is why it survived a freeze, a ledger entry claiming verification, and an
adversarial review aimed at a different change.

The pins are deliberately spread across many anchors so that no single
automated actor can widen what the publisher trusts. That defence works,
but it also means a human changing one primitive must find every anchor
by hand, and a missed anchor is invisible. This reports all of them at
once.

It REPORTS and never fixes. A stale pin is sometimes correct on purpose:
registrations and replay fixtures pin versions AS OF registration, and
"fixing" one falsifies a historical record. Deciding which is which is a
human's job; finding them is not.

    python scripts/audit_pins.py            # exit 1 if anything is stale
    python scripts/audit_pins.py --json     # machine-readable
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BLOB_ROW_RE = re.compile(r"100644 blob ([0-9a-f]{40})\t([A-Za-z0-9_./-]+)")
# Paths whose pins are frozen by intent, not by neglect.
HISTORICAL = ("replay_fixture", "rights_decisions", "trust_anchors")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _blob_oid(path: Path) -> str:
    out = subprocess.run(
        ["git", "hash-object", str(path)], cwd=ROOT, capture_output=True, text=True
    )
    return out.stdout.strip()


def _historical(path: str, anchor: str = "") -> bool:
    """Frozen by intent rather than by neglect.

    The ANCHOR decides this, not the pinned path. A trust-anchor git-proof
    records what a set of files WERE at one commit; every entry in it is
    expected to diverge from current bytes, and "repairing" one would
    falsify the anchor it exists to prove. The first version of this
    checked the pinned path instead and reported six such entries as
    ordinary staleness, which would have led someone to overwrite a
    historical record to make a report go quiet.
    """
    return any(marker in anchor or marker in path for marker in HISTORICAL)


def audit_governance_json() -> list[dict[str, Any]]:
    """Every {"path": ..., "sha256": ...} pair in governance/."""
    findings = []
    for doc_path in sorted((ROOT / "governance").rglob("*.json")):
        try:
            document = json.loads(doc_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        def walk(node: Any, anchor: str = str(doc_path.relative_to(ROOT))) -> None:
            # anchor is bound as a default rather than closed over: a closure
            # over the loop variable reports whichever document the loop
            # happened to end on, so every finding would name the last file.
            if isinstance(node, dict):
                path, digest = node.get("path"), node.get("sha256")
                if isinstance(path, str) and isinstance(digest, str):
                    target = ROOT / path
                    if target.is_file():
                        actual = _sha256(target)
                        if actual != digest:
                            findings.append({
                                "anchor": anchor,
                                "kind": "governance_json_sha256",
                                "path": path,
                                "pinned": digest,
                                "actual": actual,
                                "historical_by_convention": _historical(path, anchor),
                            })
                for value in node.values():
                    walk(value, anchor)
            elif isinstance(node, list):
                for value in node:
                    walk(value, anchor)

        walk(document)
    return findings


def audit_shell_blob_rows() -> list[dict[str, Any]]:
    """Literal `100644 blob <oid>\\t<path>` rows embedded in publisher scripts."""
    findings = []
    for script in sorted((ROOT / "scripts").glob("*.sh")):
        text = script.read_text(encoding="utf-8")
        for oid, path in BLOB_ROW_RE.findall(text):
            target = ROOT / path
            if not target.is_file():
                continue
            actual = _blob_oid(target)
            if actual != oid:
                findings.append({
                    "anchor": str(script.relative_to(ROOT)),
                    "kind": "shell_blob_oid",
                    "path": path,
                    "pinned": oid,
                    "actual": actual,
                    "historical_by_convention": _historical(
                        path, str(script.relative_to(ROOT))
                    ),
                })
    return findings


def audit_module_constants() -> list[dict[str, Any]]:
    """`X_PATH = "..."` / `X_SHA256 = "..."` constant pairs in src/."""
    findings = []
    pair_re = re.compile(
        r'(?P<name>[A-Z][A-Z0-9_]*)_PATH\s*=\s*"(?P<path>[^"]+)"'
        r'(?P<gap>.{0,400}?)'
        r'(?P=name)_SHA256\s*=\s*\(?\s*"(?P<digest>[0-9a-f]{64})"',
        re.S,
    )
    for module in sorted((ROOT / "src").glob("*.py")):
        text = module.read_text(encoding="utf-8")
        for match in pair_re.finditer(text):
            path = match.group("path")
            target = ROOT / path
            if not target.is_file():
                continue
            actual = _sha256(target)
            if actual != match.group("digest"):
                findings.append({
                    "anchor": str(module.relative_to(ROOT)),
                    "kind": "module_constant_sha256",
                    "path": path,
                    "pinned": match.group("digest"),
                    "actual": actual,
                    "historical_by_convention": _historical(
                        path, str(module.relative_to(ROOT))
                    ),
                })
    return findings


def audit() -> list[dict[str, Any]]:
    return audit_governance_json() + audit_shell_blob_rows() + audit_module_constants()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps({"stale": findings}, indent=1, sort_keys=True))
    else:
        if not findings:
            print("[pins] every pinned digest matches the bytes it pins")
        for item in findings:
            note = "  (historical by convention -- may be frozen on purpose)" if (
                item["historical_by_convention"]
            ) else ""
            print(
                f"[pins] STALE {item['kind']}\n"
                f"       anchor {item['anchor']}\n"
                f"       path   {item['path']}\n"
                f"       pinned {item['pinned'][:16]}  actual {item['actual'][:16]}{note}"
            )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
