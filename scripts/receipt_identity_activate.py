#!/usr/bin/env python3
"""Interactively sign the receipt-identity profile activation.

The gdelt_doc_api source-rights decision is founder-signed; the lane's second
and final gate is the profile signature this ceremony produces. It signs the
EXACT bytes of the proposed profile file (activation block filled), because
`receipt_identity_rights` verifies the detached signature over the committed
profile bytes.

This tool never edits, commits or pushes the repository. It writes one atomic
off-repository bundle: the proposed profile, the detached Ed25519 signature,
and a manifest. There is deliberately no ``--yes`` mode: only a human at an
interactive terminal can type the challenge and unlock the private key.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, NoReturn

from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import founder_authorize  # noqa: E402, I001
from src import receipt_identity_rights as rights  # noqa: E402, I001

SIGNER_ID = "human:igrm-ngram-rights-reviewer"
TAG = "ACTIVATION-1.0"
PROFILE_RELATIVE = "governance/gdelt_receipt_identity_profile.json"
SIGNATURE_RELATIVE = (
    "governance/rights_decisions/gdelt_doc_receipt_identity_v1-activation-1.0.sig"
)
PENDING_ACTIVATION = {
    "state": "inactive_pending_human_signature",
    "signer_id": None,
    "reviewed_on": None,
    "review_due": None,
    "signature_path": None,
}


class ActivationSigningError(ValueError):
    """Safe refusal from the human-only signing path."""


def _fail(code: str) -> NoReturn:
    raise ActivationSigningError(code)


def _outside_repository(path: Path, code: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    _fail(code)


def _profile_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.chmod(path, 0o644)


def build_bundle(
    *, private_key_path: Path, output: Path, reviewed_on: str, review_due: str
) -> Path:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        _fail("interactive_human_terminal_required")
    key_path = _outside_repository(
        private_key_path, "private_key_must_be_outside_repository"
    )
    destination = _outside_repository(
        output, "review_bundle_must_be_outside_repository"
    )
    if destination.exists():
        _fail("review_bundle_already_exists")
    try:
        reviewed = date.fromisoformat(reviewed_on)
        due = date.fromisoformat(review_due)
    except ValueError:
        _fail("review_dates_invalid")
    if due < reviewed:
        _fail("review_due_precedes_reviewed_on")

    registry = json.loads(
        (ROOT / "governance/source_rights_registry.json").read_text(encoding="utf-8")
    )
    rows = [
        row
        for row in registry["sources"]
        if row.get("source_id") == rights.SOURCE_ID
    ]
    if len(rows) != 1:
        _fail("source_registry_row_not_unique")
    row = rows[0]
    if row.get("decision_state") != "approved" or row.get("permitted_uses") != list(
        rights.CANONICAL_REQUIRED_USES
    ):
        _fail("activation_requires_approved_three_use_source_decision")
    if row.get("signer_id") != SIGNER_ID:
        _fail("source_decision_signer_unexpected")

    signers = json.loads(
        (ROOT / "governance/rights_signers.json").read_text(encoding="utf-8")
    )
    enrolled_rows = [
        signer
        for signer in signers["signers"]
        if signer.get("signer_id") == SIGNER_ID
    ]
    if len(enrolled_rows) != 1:
        _fail("signer_not_enrolled")
    enrolled = enrolled_rows[0]

    profile_path = ROOT / PROFILE_RELATIVE
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if profile.get("profile_id") != rights.PROFILE_ID:
        _fail("profile_id_unexpected")
    if profile.get("activation") != PENDING_ACTIVATION:
        _fail("profile_not_pending_activation")
    if _profile_bytes(profile) != profile_path.read_bytes():
        _fail("profile_serialization_drifted")
    schema_binding = profile["profile_schema"]
    schema_raw = (ROOT / schema_binding["path"]).read_bytes()
    if hashlib.sha256(schema_raw).hexdigest() != schema_binding["sha256"]:
        _fail("profile_schema_binding_stale")

    print("This signs the receipt-identity PROFILE ACTIVATION — the lane's")
    print("second and final gate now that the source decision is signed.")
    print("It binds the exact committed profile: acquisition caps, the")
    print("title/url/domain retention boundary, and the forbidden-field list.")
    print("It does not edit Git, publish receipts, or touch the daily score.")
    print(f"reviewed_on={reviewed_on}  review_due={review_due}  signer={SIGNER_ID}")

    key = founder_authorize._load_or_create_private_key(key_path)
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if base64.b64encode(public).decode("ascii") != enrolled.get(
        "public_key_ed25519_base64"
    ):
        _fail("private_key_does_not_match_enrolled_signer")

    proposed = json.loads(json.dumps(profile))
    proposed["activation"] = {
        "state": "active",
        "signer_id": SIGNER_ID,
        "reviewed_on": reviewed_on,
        "review_due": review_due,
        "signature_path": SIGNATURE_RELATIVE,
    }
    proposed_bytes = _profile_bytes(proposed)
    digest = hashlib.sha256(proposed_bytes).hexdigest()
    challenge = f"SIGN {rights.PROFILE_ID} {TAG} {digest[:16]}"
    print()
    print(f"Type exactly: {challenge}")
    if input("> ").strip() != challenge:
        _fail("activation_signing_challenge_mismatch")
    signature = key.sign(proposed_bytes)

    manifest = {
        "schema_version": "1.0.0",
        "status": "closed_review_bundle_not_applied",
        "profile_id": rights.PROFILE_ID,
        "signer_id": SIGNER_ID,
        "signature_relative_path": SIGNATURE_RELATIVE,
        "proposed_profile_sha256": digest,
        "required_human_followup": [
            "review_signed_profile_and_official_terms",
            "apply_profile_and_signature_in_one_reviewed_commit",
            "run_receipt_identity_tests_and_full_gate",
        ],
        "tool_committed_or_pushed": False,
    }

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        _write(
            temporary / "proposed-gdelt_receipt_identity_profile.json",
            proposed_bytes,
        )
        _write(temporary / Path(SIGNATURE_RELATIVE).name, signature)
        _write(
            temporary / "manifest.json",
            (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reviewed-on", required=True)
    parser.add_argument("--review-due", required=True)
    args = parser.parse_args()
    try:
        result = build_bundle(
            private_key_path=args.private_key,
            output=args.output,
            reviewed_on=args.reviewed_on,
            review_due=args.review_due,
        )
    except (
        ActivationSigningError,
        founder_authorize.AuthorizationToolError,
    ) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps({"status": "review_bundle_created", "path": str(result)}))


if __name__ == "__main__":
    main()
