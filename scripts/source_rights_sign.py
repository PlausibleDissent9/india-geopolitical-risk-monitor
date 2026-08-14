#!/usr/bin/env python3
"""Interactively sign the two pending source-rights decisions in one sitting.

Covers exactly two reviewed packets, both drafted with measured evidence:
  - gdelt_bq_webngrams  (governance/decisions/DRAFT_gdelt_bq_webngrams.md)
  - gdelt_doc_api       (governance/decisions/DRAFT_gdelt_doc_api_headline_lane.md)

This tool never edits, commits or pushes the repository. It writes one atomic
off-repository bundle containing each signed base-schema (1.0.0) decision
artifact, its detached Ed25519 signature, the proposed registry with both rows
approved, and a review-only trust-pin snippet for the receipt-identity module.
There is deliberately no ``--yes`` mode: only a human at an interactive
terminal can type each per-decision challenge and unlock the private key.
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

SIGNER_ID = "human:igrm-ngram-rights-reviewer"
DECISIONS: dict[str, dict[str, Any]] = {
    "gdelt_bq_webngrams": {
        "tag": "BACKFILL-1.0",
        "decision_id_prefix": "rights:gdelt_bq_webngrams:backfill-1.0",
        "artifact_stem": "gdelt_bq_webngrams-backfill-1.0",
        "permitted_uses": ["model_processing", "publish_derived_value"],
        "max_current_age_days": 30,
        "access_basis": "provider_bigquery_public_dataset_human_reviewed_terms",
        "statement": (
            "The human signer approves exactly model_processing and "
            "publish_derived_value against the provider-documented BigQuery "
            "mirror, solely to recover days whose durable refusal ledger "
            "discloses a lost source, under a future BigQuery-native "
            "attestation profile that must first reproduce a day already "
            "published from the file feed exactly. No identity retention, "
            "extract publication or redistribution is approved."
        ),
    },
    "gdelt_doc_api": {
        "tag": "RECEIPT-IDENTITY-1.0",
        "decision_id_prefix": "rights:gdelt_doc_api:receipt-identity-1.0",
        "artifact_stem": "gdelt_doc_api-receipt-identity-1.0",
        "permitted_uses": ["cite_metadata", "model_processing", "publish_extract"],
        "max_current_age_days": 30,
        "access_basis": "provider_api_public_access_human_reviewed_terms",
        "terms_url": "https://www.gdeltproject.org/about.html",
        "statement": (
            "The human signer approves exactly cite_metadata, "
            "model_processing and publish_extract for the bounded "
            "receipt-identity lane: public per-channel headline receipts of "
            "title, URL, source domain and seendate with attribution to The "
            "GDELT Project. No article body text, no images, no model "
            "training on article content, no full-record redistribution, and "
            "no substitution for the score's aggregate denominator is "
            "approved. The lane stays inactive until its own profile "
            "signature verifies."
        ),
    },
}
ARTIFACT_FIELDS = (
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


def _proposed_row(
    original: dict[str, Any], spec: dict[str, Any], *, reviewed_on: str, review_due: str
) -> dict[str, Any]:
    row = {
        **original,
        "decision_state": "approved",
        "decision_id": f"{spec['decision_id_prefix']}:{reviewed_on}",
        "decision_owner": "Human source-rights reviewer",
        "signer_id": SIGNER_ID,
        "decision_artifact_path": (
            f"governance/rights_decisions/{spec['artifact_stem']}.json"
        ),
        "decision_artifact_sha256": "PENDING_ARTIFACT_SHA256",
        "decision_signature_path": (
            f"governance/rights_decisions/{spec['artifact_stem']}.sig"
        ),
        "reviewed_on": reviewed_on,
        "review_due": review_due,
        "access_basis": spec["access_basis"],
        "max_current_age_days": spec["max_current_age_days"],
        "permitted_uses": list(spec["permitted_uses"]),
    }
    if "terms_url" in spec:
        row["terms_url"] = spec["terms_url"]
    return row


def _artifact(row: dict[str, Any], statement: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        **{field: row[field] for field in ARTIFACT_FIELDS},
        "statement": statement,
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
    signers = json.loads(
        (ROOT / "governance/rights_signers.json").read_text(encoding="utf-8")
    )
    if not any(row.get("signer_id") == SIGNER_ID for row in signers["signers"]):
        _fail("signer_not_enrolled_run_the_aggregate_ceremony_first")

    print("This signs the TWO pending source-rights decisions, one challenge each:")
    print("  1. gdelt_bq_webngrams  -- lost-day backfill, aggregate uses only")
    print("  2. gdelt_doc_api       -- headline receipts lane, three bounded uses")
    print("It does not activate any lane, edit Git, or publish anything.")
    print(f"reviewed_on={reviewed_on}  review_due={review_due}  signer={SIGNER_ID}")

    key = founder_authorize._load_or_create_private_key(key_path)
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    enrolled = next(
        row
        for row in signers["signers"]
        if row.get("signer_id") == SIGNER_ID
    )
    if base64.b64encode(public).decode("ascii") != enrolled.get(
        "public_key_ed25519_base64"
    ):
        _fail("private_key_does_not_match_enrolled_signer")

    artifacts: dict[str, tuple[bytes, bytes, dict[str, Any]]] = {}
    for source_id, spec in DECISIONS.items():
        originals = [
            row for row in registry["sources"] if row.get("source_id") == source_id
        ]
        if len(originals) != 1:
            _fail(f"source_registry_row_not_unique:{source_id}")
        if originals[0].get("decision_state") != "review_required":
            _fail(f"source_not_pending:{source_id}")
        proposed = _proposed_row(
            originals[0], spec, reviewed_on=reviewed_on, review_due=review_due
        )
        unsigned = _artifact(proposed, spec["statement"])
        digest = hashlib.sha256(_canonical(unsigned)).hexdigest()
        challenge = f"SIGN {source_id} {spec['tag']} {digest[:16]}"
        print()
        print(f"Decision {spec['tag']}: uses {proposed['permitted_uses']}")
        print(f"Type exactly: {challenge}")
        if input("> ").strip() != challenge:
            _fail(f"rights_signing_challenge_mismatch:{source_id}")
        artifact_bytes = _canonical(unsigned)
        signature = key.sign(artifact_bytes)
        proposed["decision_artifact_sha256"] = hashlib.sha256(
            artifact_bytes
        ).hexdigest()
        registry["sources"] = [
            proposed if row.get("source_id") == source_id else row
            for row in registry["sources"]
        ]
        artifacts[source_id] = (artifact_bytes, signature, proposed)

    pin_line = (
        f'    "{SIGNER_ID}": ("{base64.b64encode(public).decode("ascii")}", '
        f'"rights_reviewer"),\n'
    )
    pin_patch = (
        "REVIEW-ONLY TRUST-PIN PATCH (DO NOT APPLY WITHOUT CODE REVIEW)\n\n"
        "Insert into src/receipt_identity_rights.py PRODUCTION_TRUSTED_SIGNERS:\n"
        + pin_line
    ).encode("utf-8")
    manifest = {
        "schema_version": "1.0.0",
        "status": "closed_review_bundle_not_applied",
        "decisions": sorted(DECISIONS),
        "signer_id": SIGNER_ID,
        "required_human_followup": [
            "review_signed_decisions_and_official_terms",
            "apply_registry_artifacts_and_code_pin_in_one_reviewed_commit",
            "run_publication_guard_and_full_gate",
        ],
        "tool_applied_trust_pin": False,
        "tool_committed_or_pushed": False,
    }

    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        for source_id, (artifact_bytes, signature, _row) in artifacts.items():
            stem = DECISIONS[source_id]["artifact_stem"]
            _write(temporary / f"{stem}.json", artifact_bytes)
            _write(temporary / f"{stem}.sig", signature)
        _write(
            temporary / "proposed-source-rights-registry.json", _canonical(registry)
        )
        _write(temporary / "proposed-receipt-identity-trust-pin.txt", pin_patch)
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
