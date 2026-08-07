#!/usr/bin/env python3
"""Verify every OpenTimestamps proof in the repo stamps the bytes beside it.

WHY THIS EXISTS
A signature line in a chat log proves nothing to a referee: it is a claim
made inside the same repository it vouches for. An OpenTimestamps proof is
different in kind -- the sha256 of the registered bytes is committed to
public calendar servers and ultimately anchored in a Bitcoin block, so a
third party can verify the bytes existed before the results did without
trusting this repo, its git history, or its author.

That guarantee holds only while each .ots actually stamps the bytes sitting
beside it. The 2026-08-08 registration audit
(analysis/registration_audit_2026-08-08.md section 8) found exactly one way
this rots: the blind-audit .ots kept stamping the superseded v1 registration
after the file was rewritten for v2 -- an honest proof for the wrong bytes,
which reads as a broken seal to anyone running `ots verify`. This script
makes that class of drift visible in one command.

WHAT IT CHECKS (offline; no calendar-server calls)
For every *.ots in the tree, extract the sha256 digest recorded in the proof
header and compare it with the sha256 of the subject's current bytes. It
does NOT verify the Bitcoin attestation chain -- pending attestations are
normal for hours after stamping, and remote verification is what
`ots verify` is for. Digest agreement is the property the repo can and
should enforce continuously.

Exit status: 0 when every proof matches its subject; 1 on any mismatch,
any proof whose subject is missing, or an empty inventory.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Proofs whose subject is NOT the living neighbor file, mapped to
# (commit, path-at-that-commit). The blind-audit v1 proof stamps
# validation/blind_audit_500/registration.json AS OF commit 989c43f -- the
# superseded v1 bytes, kept deliberately as evidence for the correction
# trail (V1_INVALID.md; audit section 8). Its subject lives in git history,
# not the working tree.
GIT_SUBJECTS: dict[str, tuple[str, str]] = {
    "validation/blind_audit_500/registration_v1_989c43f.json.ots": (
        "989c43f",
        "validation/blind_audit_500/registration.json",
    ),
}

# Directories that can contain third-party or generated .ots-suffixed files
# that are not this repo's proofs.
SKIP_DIRS = {".git", ".venv", "node_modules"}

# Detached-proof header, per the OpenTimestamps serialization format:
# magic bytes, varint version, one-byte file-hash-op tag, then the digest.
MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
OP_SHA256 = 0x08
SHA256_LEN = 32


def find_ots_files(root: Path = ROOT) -> list[Path]:
    """Every .ots proof in the tree, excluding SKIP_DIRS, sorted."""
    return sorted(
        p
        for p in root.rglob("*.ots")
        if not set(p.relative_to(root).parts[:-1]) & SKIP_DIRS
    )


def stamped_sha256(ots_path: Path) -> str:
    """The sha256 digest a detached .ots proof commits to, from its header.

    Pure-Python and offline on purpose: tests must not depend on the
    opentimestamps package (absent from CI's requirements) or on network
    calendars. The header layout is fixed by the OTS spec: magic, varint
    version, hash-op tag (0x08 = sha256), 32-byte digest.
    """
    data = ots_path.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError(f"{ots_path}: missing OpenTimestamps magic bytes")
    i = len(MAGIC)
    while i < len(data) and data[i] & 0x80:  # varint version, continuation bit
        i += 1
    i += 1  # final varint byte
    if i >= len(data):
        raise ValueError(f"{ots_path}: truncated before the hash-op tag")
    tag = data[i]
    i += 1
    if tag != OP_SHA256:
        raise ValueError(
            f"{ots_path}: file hash op 0x{tag:02x} is not sha256 (0x{OP_SHA256:02x})"
        )
    if len(data) < i + SHA256_LEN:
        raise ValueError(f"{ots_path}: truncated before the {SHA256_LEN}-byte digest")
    return data[i : i + SHA256_LEN].hex()


def subject_sha256(ots_path: Path, root: Path = ROOT) -> tuple[str, str | None]:
    """(subject description, sha256 of the subject's current bytes or None).

    None means the subject is unavailable: neighbor file missing, or a
    git-history subject whose commit is unreachable (shallow clone).
    """
    rel = ots_path.relative_to(root).as_posix()
    if rel in GIT_SUBJECTS:
        commit, path = GIT_SUBJECTS[rel]
        desc = f"git {commit}:{path}"
        probe = subprocess.run(
            ["git", "cat-file", "-t", commit],
            cwd=root, capture_output=True, text=True,
        )
        if probe.stdout.strip() != "commit":
            return desc, None
        blob = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=root, capture_output=True,
        ).stdout
        if not blob:
            return desc, None
        return desc, hashlib.sha256(blob).hexdigest()
    neighbor = ots_path.with_suffix("")
    desc = neighbor.relative_to(root).as_posix()
    if not neighbor.is_file():
        return desc, None
    return desc, hashlib.sha256(neighbor.read_bytes()).hexdigest()


def main() -> int:
    proofs = find_ots_files()
    if not proofs:
        print("verify_stamps: 0 .ots files found -- refusing to call an "
              "empty inventory a pass")
        return 1

    failures = 0
    rows: list[tuple[str, str, str, str]] = []
    for proof in proofs:
        rel = proof.relative_to(ROOT).as_posix()
        try:
            stamped = stamped_sha256(proof)
        except ValueError as exc:
            rows.append((rel, "-", "-", f"FAIL unparseable: {exc}"))
            failures += 1
            continue
        subject, current = subject_sha256(proof)
        if current is None:
            rows.append((rel, stamped[:16], "-", f"FAIL subject unavailable: {subject}"))
            failures += 1
        elif current == stamped:
            rows.append((rel, stamped[:16], current[:16], "ok"))
        else:
            rows.append((rel, stamped[:16], current[:16], f"MISMATCH vs {subject}"))
            print(f"MISMATCH {rel}\n  stamped {stamped}\n  current {current}")
            failures += 1

    width = max(len(r[0]) for r in rows)
    print(f"{'proof':<{width}}  {'stamped[:16]':<16}  {'current[:16]':<16}  status")
    for rel, stamped16, current16, status in rows:
        print(f"{rel:<{width}}  {stamped16:<16}  {current16:<16}  {status}")
    print(f"\n{len(rows)} proofs, {len(rows) - failures} match, {failures} fail")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
