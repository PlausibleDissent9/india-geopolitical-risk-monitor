"""Hostile tests for the canonical-release signer enrolment ceremony.

Enrolling a release signer grants the authority to say "these exact bytes
are a release I stand behind". The ceremony must refuse everything except
a human at a terminal who demonstrably holds the private key for the
public key being enrolled, and it must never touch a private key itself.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_signer_enrol.py"


def _keypair(tmp_path: Path, name: str = "release") -> tuple[Ed25519PrivateKey, Path]:
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    path = tmp_path / f"{name}.pub"
    path.write_text(base64.b64encode(pub).decode("ascii"), encoding="utf-8")
    return key, path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT, input="", capture_output=True, text=True,
    )


def test_the_repository_ships_with_no_release_signer(tmp_path: Path) -> None:
    # The premise of the ceremony. If this ever fails, someone enrolled a
    # signer outside it and that must be noticed.
    signers = json.loads(
        (ROOT / "governance/release_signers.json").read_text(encoding="utf-8")
    )
    assert signers["default_policy"] == "deny"
    assert signers["signers"] == []


def test_non_interactive_invocation_is_refused(tmp_path: Path) -> None:
    _, pub = _keypair(tmp_path)
    result = _run("--prepare", "--signer-id", "human:x",
                  "--public-key-file", str(pub), "--effective", "2026-08-17")
    assert result.returncode == 1
    assert "interactive_human_terminal_required" in result.stderr


def test_the_script_never_mentions_a_private_key_parameter() -> None:
    # A ceremony that can accept a private key will eventually be handed one.
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("--private-key", "private_key_file", "getpass", "load_pem_private"):
        assert forbidden not in source, f"{forbidden} would invite a private key"


def test_challenge_binds_identity_key_and_date_together() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import release_signer_enrol as rse

    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    base = rse._challenge_bytes("human:a", pub, "2026-08-17")
    # Changing ANY bound field must change the bytes that get signed,
    # otherwise a signature captured for one enrolment authorises another.
    assert base != rse._challenge_bytes("human:b", pub, "2026-08-17")
    assert base != rse._challenge_bytes("human:a", pub, "2026-01-01")
    other = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    assert base != rse._challenge_bytes("human:a", other, "2026-08-17")
    assert rse.REQUIRED_ROLE.encode() in base


def test_a_signature_over_different_bytes_does_not_verify() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import release_signer_enrol as rse
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    wrong = key.sign(rse._challenge_bytes("human:a", pub, "2026-01-01"))
    with pytest.raises(InvalidSignature):
        Ed25519PublicKey.from_public_bytes(pub).verify(
            wrong, rse._challenge_bytes("human:a", pub, "2026-08-17")
        )


def test_key_separation_from_the_rights_signer_is_enforced_not_remembered() -> None:
    # The rights key answers "may this source be used"; a release key
    # answers "are these the bytes I stand behind". One key for both means
    # one compromise grants both.
    source = SCRIPT.read_text(encoding="utf-8")
    assert "release_key_must_differ_from_rights_key" in source
    assert "rights_signers.json" in source


def test_enrolment_requires_the_declared_role() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'REQUIRED_ROLE = "canonical_release_signer"' in source
    # canonical_objects refuses any other role, so the ceremony must not be
    # able to write one.
    assert '"role": REQUIRED_ROLE' in source
