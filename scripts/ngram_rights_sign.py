#!/usr/bin/env python3
"""Interactively create a closed GDELT aggregate-rights review bundle.

This tool never edits, commits or pushes the repository. It writes one atomic
off-repository bundle containing a signed decision and proposed registry/code
changes for separate human review. There is deliberately no ``--yes`` mode.
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
from src import ngram_rights_contract  # noqa: E402, I001

SOURCE_ID = ngram_rights_contract.SOURCE_ID
PROFILE_ID = ngram_rights_contract.PROFILE_ID
SIGNER_ID = "human:igrm-ngram-rights-reviewer"
SIGNER_ROLE = "rights_reviewer"
TERMS_URL = ngram_rights_contract.TERMS_URL
USES = ["model_processing", "publish_derived_value"]


class RightsSigningError(ValueError):
    """Safe refusal from the human-only signing path."""


def _fail(code: str) -> NoReturn:
    raise RightsSigningError(code)


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _outside_repository(path: Path, code: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return resolved
    _fail(code)


def _source_row(
    original: dict[str, Any], *, reviewed_on: str, review_due: str
) -> dict[str, Any]:
    return {
        **original,
        "decision_state": "approved",
        "decision_id": f"rights:{SOURCE_ID}:aggregate-2.0:{reviewed_on}",
        "decision_owner": "Human source-rights reviewer",
        "signer_id": SIGNER_ID,
        "decision_artifact_path": f"governance/rights_decisions/{SOURCE_ID}-aggregate-2.0.json",
        "decision_artifact_sha256": "PENDING_ARTIFACT_SHA256",
        "decision_signature_path": f"governance/rights_decisions/{SOURCE_ID}-aggregate-2.0.sig",
        "reviewed_on": reviewed_on,
        "review_due": review_due,
        "terms_url": TERMS_URL,
        "access_basis": "official_unlimited_unrestricted_use_terms_human_reviewed",
        "retrieval_target": "Prospective aggregate-only profile 2.0 source processing",
        "reproducibility_tier": "exact_source_object_hashes_and_aggregate_counts_no_membership_retention",
        "max_current_age_days": 3,
        "permitted_uses": USES,
        "notes": (
            "Human-reviewed official GDELT terms permit use and redistribution; "
            "this narrower decision licenses only model processing and publication "
            "of derived aggregate values under profile 2.0. Cite and link The GDELT "
            f"Project and {TERMS_URL}. No identity, extract or full-record retention "
            "is authorized by this row."
        ),
    }


def _decision(source: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "source_id",
        "name",
        "provider",
        "role",
        "authority_class",
        "independence_group",
        "decision_id",
        "decision_owner",
        "signer_id",
        "reviewed_on",
        "review_due",
        "access_url",
        "terms_url",
        "access_basis",
        "lineage_policy",
        "max_current_age_days",
        "permitted_uses",
    )
    reviewed_on = date.fromisoformat(str(source["reviewed_on"]))
    recovery_targets = ngram_rights_contract.historical_recovery_targets(reviewed_on)
    return {
        "schema_version": ngram_rights_contract.DECISION_SCHEMA_VERSION,
        **{field: source[field] for field in fields},
        "profile_id": PROFILE_ID,
        "official_terms_citation": dict(
            ngram_rights_contract.OFFICIAL_TERMS_CITATION
        ),
        "historical_recovery_targets": recovery_targets,
        "historical_recovery_targets_sha256": (
            ngram_rights_contract.historical_recovery_targets_sha256(
                recovery_targets
            )
        ),
        "statement": (
            "The human signer approves exactly model_processing and "
            "publish_derived_value for prospective aggregate profile 2.0. "
            "This is not approval for identity retention, extracts, full records, "
            "precision claims, forecasts, adoption claims or source-truth claims."
        ),
    }


def _signer(public: bytes, effective: str) -> dict[str, Any]:
    return {
        "signer_id": SIGNER_ID,
        "name": "Human GDELT source-rights reviewer",
        "role": SIGNER_ROLE,
        "public_key_ed25519_base64": base64.b64encode(public).decode("ascii"),
        "effective": effective,
        "revoked_on": None,
    }


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.chmod(path, 0o644)


def build_bundle(
    *, private_key_path: Path, output: Path, reviewed_on: str, review_due: str
) -> Path:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        _fail("interactive_human_terminal_required")
    key_path = _outside_repository(private_key_path, "private_key_must_be_outside_repository")
    destination = _outside_repository(output, "review_bundle_must_be_outside_repository")
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
    originals = [row for row in registry["sources"] if row.get("source_id") == SOURCE_ID]
    if len(originals) != 1:
        _fail("source_registry_row_not_unique")
    proposed_source = _source_row(originals[0], reviewed_on=reviewed_on, review_due=review_due)
    try:
        unsigned_decision = _decision(proposed_source)
    except ValueError:
        _fail("historical_recovery_review_outside_bounded_window")
    challenge_digest = hashlib.sha256(_canonical(unsigned_decision)).hexdigest()
    challenge = f"SIGN {SOURCE_ID} AGGREGATE-2.0 {challenge_digest[:16]}"
    print("This signs only the two-use prospective aggregate profile.")
    print("It does not pin trust, edit Git, approve identity retention, or publish a score.")
    print(f"Official terms bound for review: {TERMS_URL}")
    print(f"Type exactly: {challenge}")
    if input("> ").strip() != challenge:
        _fail("rights_signing_challenge_mismatch")

    key = founder_authorize._load_or_create_private_key(key_path)
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    artifact = _canonical(unsigned_decision)
    signature = key.sign(artifact)
    proposed_source["decision_artifact_sha256"] = hashlib.sha256(artifact).hexdigest()
    registry["sources"] = [
        proposed_source if row.get("source_id") == SOURCE_ID else row
        for row in registry["sources"]
    ]
    signers = json.loads(
        (ROOT / "governance/rights_signers.json").read_text(encoding="utf-8")
    )
    if any(row.get("signer_id") == SIGNER_ID for row in signers["signers"]):
        _fail("signer_id_already_registered_review_rotation")
    signers["effective"] = reviewed_on
    signers["signers"].append(_signer(public, reviewed_on))
    pin_line = (
        f'    "{SIGNER_ID}": ("{base64.b64encode(public).decode("ascii")}", '
        f'"{SIGNER_ROLE}"),\n'
    )
    pin_patch = (
        "REVIEW-ONLY TRUST-PIN PATCH (DO NOT APPLY WITHOUT CODE REVIEW)\n\n"
        "Insert into src/ngram_rights.py PRODUCTION_TRUSTED_SIGNERS:\n"
        + pin_line
    ).encode("utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "status": "closed_review_bundle_not_applied",
        "source_id": SOURCE_ID,
        "profile_id": PROFILE_ID,
        "official_terms_url": TERMS_URL,
        "required_human_followup": [
            "review_signed_decision_and_official_terms",
            "review_public_key_identity_out_of_band",
            "apply_registry_and_code_pin_in_one_reviewed_commit",
            "run_publication_guard_and_full_gate",
        ],
        "tool_applied_trust_pin": False,
        "tool_committed_or_pushed": False,
    }
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        _write(temporary / "decision.json", artifact)
        _write(temporary / "decision.sig", signature)
        _write(temporary / "proposed-rights-signers.json", _canonical(signers))
        _write(temporary / "proposed-source-rights-registry.json", _canonical(registry))
        _write(temporary / "proposed-production-trust-pin.txt", pin_patch)
        _write(temporary / "manifest.json", _canonical(manifest))
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
    except (RightsSigningError, founder_authorize.AuthorizationToolError) as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps({"status": "review_bundle_created", "path": str(result)}))


if __name__ == "__main__":
    main()
