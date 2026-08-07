"""Every registration-class artifact carries an OpenTimestamps proof that
stamps its current bytes.

A signature line in a chat log proves nothing to a referee -- it is a claim
inside the repo it vouches for. An .ots proof anchors the sha256 of the
registered bytes in public calendars and ultimately a Bitcoin block, so the
"frozen before results" claim is checkable without trusting this repo. But
the proof only means that while it stamps the bytes actually beside it: the
2026-08-08 registration audit (analysis/registration_audit_2026-08-08.md
section 8) caught a .ots still stamping a superseded v1 registration after
the file was rewritten -- a broken seal to anyone running `ots verify`.

These tests do digest comparison ONLY, fully offline: the stamped sha256 is
parsed from the proof header (via scripts/verify_stamps.py, pure Python, no
opentimestamps dependency) and compared with the subject's current bytes.
Verifying the Bitcoin attestation chain needs remote calendars and is
deliberately out of scope here -- attestations are legitimately pending for
hours after stamping and CI must not depend on third-party servers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "verify_stamps", ROOT / "scripts" / "verify_stamps.py"
)
assert _spec is not None and _spec.loader is not None
verify_stamps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_stamps)

# Every signed/registered artifact in the repo. Adding a registration means
# adding it here AND stamping it (`ots stamp <file>`); this list failing is
# the reminder.
REGISTRATION_ARTIFACTS = [
    "analysis/ai_gpr_benchmark_registration.json",
    "analysis/back_extension_memo.md",
    "countries/china.json",
    "design/alerts_webhook.md",
    "validation/blind_audit_500/CONFIRMATORY_PLAN.md",
    "validation/blind_audit_500/registration.json",
    "validation/forecast_logit_frozen.json",
    "validation/forecast_registration.json",
]

# Cardinality guard: the 8 artifacts above plus the retained v1 proof exist
# today. If enumeration ever returns fewer than 8, the glob broke or proofs
# were deleted -- either way the suite must not pass vacuously.
MIN_STAMPS = 8


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_every_registration_artifact_has_a_matching_stamp() -> None:
    for rel in REGISTRATION_ARTIFACTS:
        subject = ROOT / rel
        proof = ROOT / (rel + ".ots")
        assert subject.is_file(), f"{rel}: registered artifact is missing"
        assert proof.is_file(), (
            f"{rel}: no .ots beside it -- every registration gets a "
            "timestamp proof (`ots stamp <file>`)")
        assert verify_stamps.stamped_sha256(proof) == _sha256(subject), (
            f"{rel}: its .ots stamps different bytes than the file holds "
            "now. If the artifact legitimately changed (amendment, "
            "supersession), re-stamp the new bytes and keep the old proof "
            "under a name that says what it stamps, as with "
            "registration_v1_989c43f.json.ots")


def test_every_ots_in_the_repo_has_a_present_matching_subject() -> None:
    for proof in verify_stamps.find_ots_files():
        rel = proof.relative_to(ROOT).as_posix()
        if rel in verify_stamps.GIT_SUBJECTS:
            continue  # subject lives in git history; checked separately below
        subject = proof.with_suffix("")
        assert subject.is_file(), (
            f"{rel}: proof with no subject file beside it -- a stamp of "
            "nothing proves nothing")
        assert verify_stamps.stamped_sha256(proof) == _sha256(subject), (
            f"{rel}: stamped digest does not match the subject's current bytes")


def test_stamp_inventory_cannot_be_vacuous() -> None:
    n = len(verify_stamps.find_ots_files())
    assert n >= MIN_STAMPS, (
        f"only {n} .ots proofs enumerated, expected >= {MIN_STAMPS}: either "
        "proofs were deleted or find_ots_files() stopped finding them")


def test_v1_proof_stamps_the_superseded_registration_bytes() -> None:
    """The one proof whose subject is a git blob, not a living file.

    validation/blind_audit_500/registration_v1_989c43f.json.ots stamps
    registration.json AS OF commit 989c43f -- the invalidated v1, retained
    as timestamp evidence for the correction trail (V1_INVALID.md). Verified
    against the blob in history, with the same shallow-clone skip as
    tests/test_ai_gpr_registration.py: enforced wherever git history exists.
    """
    for rel, (commit, path) in verify_stamps.GIT_SUBJECTS.items():
        proof = ROOT / rel
        assert proof.is_file(), f"{rel}: retained v1 proof is missing"
        probe = subprocess.run(["git", "cat-file", "-t", commit],
                               cwd=ROOT, capture_output=True, text=True)
        if probe.stdout.strip() != "commit":
            pytest.skip(f"commit {commit} unreachable here (shallow clone or "
                        "no git history); enforced on any full clone")
        blob = subprocess.run(["git", "show", f"{commit}:{path}"],
                              cwd=ROOT, capture_output=True).stdout
        assert blob, f"{path} not retrievable at {commit}"
        assert verify_stamps.stamped_sha256(proof) == hashlib.sha256(blob).hexdigest(), (
            f"{rel}: does not stamp {path} as of {commit}; the retained v1 "
            "evidence no longer proves what the audit says it proves")
