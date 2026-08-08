#!/usr/bin/env python3
"""Create the founder's local key and detached IGRM Max authorization.

This script is intentionally interactive and has no ``--yes`` mode.  An agent
may prepare and review the machinery, but only the founder may type the exact
authorization challenge and unlock the private key.  The encrypted private key
must live outside the repository; only its public half, the signed statement and
the detached signature are written to Git-visible paths.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.max_launch_contract import (
    AUTHORIZATION_SIGNATURE,
    AUTHORIZATION_STATEMENT,
    CONTRACT,
    FOUNDER_SIGNERS,
    REQUIRED_AUTHORIZATION_POLICY,
    build_authorization_statement,
    canonical_json_bytes,
    load_contract,
    scope_sha256,
    validate_contract,
    validate_scope,
)

ROOT = Path(__file__).resolve().parents[1]

class AuthorizationToolError(ValueError):
    """A safe, user-facing refusal from the signing tool."""


def _outside_repository(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError:
        return candidate
    raise AuthorizationToolError("private_key_must_be_outside_repository")


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _passphrase(*, confirm: bool) -> bytes:
    first = getpass.getpass("Private-key passphrase (12+ characters): ").encode("utf-8")
    if len(first) < 12:
        raise AuthorizationToolError("private_key_passphrase_too_short")
    if confirm:
        second = getpass.getpass("Repeat private-key passphrase: ").encode("utf-8")
        if first != second:
            raise AuthorizationToolError("private_key_passphrases_do_not_match")
    return first


def _load_or_create_private_key(path: Path) -> Ed25519PrivateKey:
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise AuthorizationToolError("private_key_path_invalid")
        if path.stat().st_mode & 0o077:
            raise AuthorizationToolError("private_key_permissions_must_be_0600")
        password = _passphrase(confirm=False)
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=password)
        except (OSError, TypeError, ValueError) as exc:
            raise AuthorizationToolError("private_key_unlock_failed") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise AuthorizationToolError("private_key_is_not_ed25519")
        return key

    password = _passphrase(confirm=True)
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(pem)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if path.exists():
            path.unlink()
        raise
    return key


def _registry(private_key: Ed25519PrivateKey, effective: str) -> dict[str, object]:
    public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "schema_version": "1.0.0",
        "effective": effective,
        "default_policy": "deny",
        "signers": [
            {
                "signer_id": REQUIRED_AUTHORIZATION_POLICY["required_signer_id"],
                "name": "Ishan Krishna",
                "role": REQUIRED_AUTHORIZATION_POLICY["required_role"],
                "public_key_ed25519_base64": base64.b64encode(public).decode("ascii"),
                "public_key_sha256": hashlib.sha256(public).hexdigest(),
                "effective": effective,
                "revoked_on": None,
            }
        ],
    }


def authorize(private_key_path: Path, authorized_on: str) -> dict[str, object]:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise AuthorizationToolError("interactive_founder_terminal_required")
    if AUTHORIZATION_STATEMENT.exists() or AUTHORIZATION_SIGNATURE.exists():
        raise AuthorizationToolError("authorization_already_exists_review_before_replacing")

    document = load_contract(CONTRACT)
    validate_scope(document)
    digest = scope_sha256(document)
    challenge = f"AUTHORIZE {document['program_id']} {digest[:12]}"
    print("\nThis authorizes the exact registered scope, launch date and budget ceiling.")
    print("It approves no purchase and proves no validation, adoption or endorsement.")
    print(f"Type exactly: {challenge}")
    if input("> ").strip() != challenge:
        raise AuthorizationToolError("founder_authorization_challenge_mismatch")

    key_path = _outside_repository(private_key_path)
    private_key = _load_or_create_private_key(key_path)
    registry_bytes = canonical_json_bytes(_registry(private_key, authorized_on))
    statement = build_authorization_statement(
        document,
        signer_registry_bytes=registry_bytes,
        authorized_on=authorized_on,
    )
    statement_bytes = canonical_json_bytes(statement)
    signature = private_key.sign(statement_bytes)

    _atomic_write(FOUNDER_SIGNERS, registry_bytes, 0o644)
    _atomic_write(AUTHORIZATION_STATEMENT, statement_bytes, 0o644)
    _atomic_write(AUTHORIZATION_SIGNATURE, signature, 0o644)
    return validate_contract(document)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-key",
        type=Path,
        required=True,
        help="encrypted Ed25519 private key outside this repository",
    )
    parser.add_argument(
        "--authorized-on",
        default=date.today().isoformat(),
        help="ISO authorization date; defaults to today",
    )
    arguments = parser.parse_args()
    try:
        result = authorize(arguments.private_key, arguments.authorized_on)
    except AuthorizationToolError as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Encrypted private key (never commit): {arguments.private_key.expanduser()}")
    print(f"Public signer registry: {FOUNDER_SIGNERS.relative_to(ROOT)}")
    print(f"Authorization statement: {AUTHORIZATION_STATEMENT.relative_to(ROOT)}")
    print(f"Detached signature: {AUTHORIZATION_SIGNATURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
