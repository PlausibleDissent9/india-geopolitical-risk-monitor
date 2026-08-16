#!/usr/bin/env python3
"""Enrol one canonical-release signer. Interactive, founder-only.

`governance/release_signers.json` ships with an EMPTY signer list under
`default_policy: deny`. That is the single reason the four proof products
exist only as a synthetic demonstration: `src/evidence_outputs.py` is a
real, template-driven compiler, but a canonical release must carry a
signature from an enrolled `canonical_release_signer`, and nobody is
enrolled. One ceremony unblocks the largest scoring domain in the plan.

WHY A SEPARATE KEY FROM THE RIGHTS REVIEWER
The rights key (`human:igrm-ngram-rights-reviewer`) answers "may this
source be used at all". A release key answers "are these exact bytes the
release I stand behind". Those are different authorities with different
blast radii, and sharing one key means a single compromise grants both.
This script therefore REFUSES a public key already enrolled as a rights
signer, rather than making key separation a matter of remembering.

WHAT THIS SCRIPT NEVER DOES
It never reads, requests, stores or transmits a private key. The operator
signs a challenge on their own machine with their own tooling; this
script sees a public key and a signature over bytes it prints, and it
verifies that the two match before writing anything. If verification
fails, nothing is written.

    python scripts/release_signer_enrol.py --prepare \\
        --signer-id human:igrm-release-signer \\
        --public-key-file ~/.igrm/release.pub \\
        --effective 2026-08-17

    # sign the printed challenge file with your own key, then:

    python scripts/release_signer_enrol.py --apply \\
        --signer-id human:igrm-release-signer \\
        --public-key-file ~/.igrm/release.pub \\
        --effective 2026-08-17 \\
        --proof-signature ~/.igrm/release-challenge.sig
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
SIGNERS_PATH = ROOT / "governance/release_signers.json"
RIGHTS_SIGNERS_PATH = ROOT / "governance/rights_signers.json"
REQUIRED_ROLE = "canonical_release_signer"
CHALLENGE_PATH = Path.home() / ".igrm" / "release-signer-challenge.txt"


def _fail(code: str) -> NoReturn:
    print(code, file=sys.stderr)
    raise SystemExit(1)


def _load(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _fail("signers_file_unreadable")


def _public_key_bytes(path: Path) -> bytes:
    """Accept a base64 Ed25519 public key. 32 raw bytes, nothing else."""
    if ROOT in path.resolve().parents:
        _fail("public_key_must_be_outside_repository")
    try:
        raw = base64.b64decode(path.read_text(encoding="utf-8").strip(), validate=True)
    except (OSError, binascii.Error):
        _fail("public_key_unreadable")
    if len(raw) != 32:
        _fail("public_key_not_ed25519")
    return raw


def _challenge_bytes(signer_id: str, public_key: bytes, effective: str) -> bytes:
    """Exact bytes the operator signs. Binds identity, key and date together.

    Signing a bare nonce would prove key possession but not agreement to
    THIS enrolment; an attacker who could get any signature could enrol a
    different id or an earlier effective date with it.
    """
    return (
        "IGRM CANONICAL RELEASE SIGNER ENROLMENT\n"
        f"signer_id: {signer_id}\n"
        f"public_key_ed25519_base64: {base64.b64encode(public_key).decode('ascii')}\n"
        f"role: {REQUIRED_ROLE}\n"
        f"effective: {effective}\n"
    ).encode()


def _checked_inputs(args: argparse.Namespace) -> tuple[str, bytes, str]:
    if not args.signer_id.startswith("human:"):
        _fail("release_signer_must_be_a_named_human")
    try:
        date.fromisoformat(args.effective)
    except ValueError:
        _fail("effective_date_invalid")
    public_key = _public_key_bytes(Path(args.public_key_file).expanduser())

    signers = _load(SIGNERS_PATH)
    if signers.get("default_policy") != "deny":
        _fail("release_signers_not_deny_by_default")
    for existing in signers.get("signers", []):
        if existing.get("signer_id") == args.signer_id:
            _fail("release_signer_already_enrolled")

    # Key separation, enforced rather than remembered.
    encoded = base64.b64encode(public_key).decode("ascii")
    for rights_signer in _load(RIGHTS_SIGNERS_PATH).get("signers", []):
        if rights_signer.get("public_key_ed25519_base64") == encoded:
            _fail("release_key_must_differ_from_rights_key")
    return args.signer_id, public_key, args.effective


def prepare(args: argparse.Namespace) -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        _fail("interactive_human_terminal_required")
    signer_id, public_key, effective = _checked_inputs(args)
    challenge = _challenge_bytes(signer_id, public_key, effective)
    CHALLENGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CHALLENGE_PATH.write_bytes(challenge)
    print(f"challenge written to {CHALLENGE_PATH}")
    print("sign these exact bytes with the release private key, then re-run --apply")
    print("nothing has been written to the repository")


def apply(args: argparse.Namespace) -> None:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        _fail("interactive_human_terminal_required")
    signer_id, public_key, effective = _checked_inputs(args)
    challenge = _challenge_bytes(signer_id, public_key, effective)

    signature_path = Path(args.proof_signature).expanduser()
    if ROOT in signature_path.resolve().parents:
        _fail("proof_signature_must_be_outside_repository")
    try:
        signature = signature_path.read_bytes()
    except OSError:
        _fail("proof_signature_unreadable")
    if len(signature) != 64:
        _fail("proof_signature_not_ed25519")
    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, challenge)
    except (InvalidSignature, ValueError):
        _fail("proof_signature_does_not_verify")

    print(f"Type exactly: ENROL {signer_id} {REQUIRED_ROLE}")
    if input("> ").strip() != f"ENROL {signer_id} {REQUIRED_ROLE}":
        _fail("enrolment_challenge_mismatch")

    signers = _load(SIGNERS_PATH)
    signers["signers"].append({
        "signer_id": signer_id,
        "name": args.name,
        "role": REQUIRED_ROLE,
        "public_key_ed25519_base64": base64.b64encode(public_key).decode("ascii"),
        "effective": effective,
        "revoked_on": None,
    })
    signers["signers"].sort(key=lambda s: s["signer_id"])
    SIGNERS_PATH.write_text(
        json.dumps(signers, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"enrolled {signer_id} as {REQUIRED_ROLE}")
    print("review the diff before committing; this grants release authority")


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--signer-id", required=True)
    parser.add_argument("--public-key-file", required=True)
    parser.add_argument("--effective", required=True)
    parser.add_argument("--name", default="IGRM release signer")
    parser.add_argument("--proof-signature")
    args = parser.parse_args()
    if args.apply and not args.proof_signature:
        _fail("proof_signature_required_for_apply")
    (prepare if args.prepare else apply)(args)


if __name__ == "__main__":
    main()
