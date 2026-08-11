"""Byte-deterministic manifest for an offline audit bundle (first sub-slice).

A stranger who distrusts the site should be able to carry away one artifact and
verify it forever. The full design (design/offline_audit_bundle.md) ships zip
packaging, a founder signature, a timestamp proof and a stdlib verifier. THIS
sub-slice is only the manifest half, which everything else rests on: a member
list that is rights-eligible, tracked, safely named, digest-matched, and a
manifest whose self-digest reproduces byte-for-byte from committed bytes.

Deny-by-default. Rights-restricted members refuse rather than degrade; a member
whose declared digest does not match its bytes refuses; an unsafe path refuses.
The manifest never contains the raw store -- it proves without containing.

Refusal codes and the rights-restricted glob list are registered in
governance/offline_bundle_contract.json. Codes for the deferred sub-slices
(signature, timestamp, verifier) are reserved there and are NOT raised here;
`tests/test_offline_bundle.py` asserts that boundary so the contract never
claims more than this runtime proves.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from src import event_ledger_extension

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "offline_bundle_contract.json"

_MEMBER_FIELDS = frozenset({"path", "declared_sha256"})


class OfflineBundleError(ValueError):
    """Stable fail-closed refusal for the offline-bundle manifest builder."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise OfflineBundleError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail("bundle_member_unsafe_path", "json_duplicate_key")
        out[key] = value
    return out


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise OfflineBundleError("bundle_manifest_incomplete",
                                 "contract_unreadable") from exc
    if contract.get("default_policy") != "deny":
        _fail("bundle_manifest_incomplete", "contract_not_deny_by_default")
    return cast(dict[str, Any], contract)


def _tracked_paths(root: Path) -> set[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root,
                         capture_output=True, text=True, check=True).stdout
    return set(out.split())


def _safe_relative_path(raw: object) -> str:
    """Reject anything that is not a plain relative repo path: no absolute
    paths, no '..' traversal, no NUL, no backslashes. Returns the normalized
    posix path."""
    if not isinstance(raw, str) or not raw or "\x00" in raw or "\\" in raw:
        _fail("bundle_member_unsafe_path", repr(raw)[:60])
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        _fail("bundle_member_unsafe_path", raw)
    normalized = pure.as_posix()
    if normalized != raw:
        _fail("bundle_member_unsafe_path", raw)
    return normalized


def _rights_ineligible(path: str, contract: Mapping[str, Any]) -> bool:
    for prefix in contract["rights_restricted_globs"]:
        if path == prefix.rstrip("/") or path.startswith(prefix):
            return True
    return False


def build_manifest(
    members: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Admit each member and emit a byte-deterministic bundle manifest.

    A member is {path, declared_sha256}. It must be a safe relative path, not
    rights-restricted, tracked in git, and its bytes must hash to the declared
    digest. Members are ordered lexicographically; the manifest self-digest is
    the typed-canonical digest of the manifest with manifest_digest excluded.
    """
    contract = contract or load_contract()
    tracked = _tracked_paths(root)

    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for member in members:
        if not isinstance(member, dict) or frozenset(member) != _MEMBER_FIELDS:
            _fail("bundle_manifest_incomplete", "member_shape")
        path = _safe_relative_path(member["path"])
        if path in seen:
            _fail("bundle_member_duplicate_path", path)
        seen.add(path)
        # A safe path STRING is not a safe FILE: a symlink member (or a member
        # reached through a symlinked parent) would have read_bytes() follow the
        # link and bundle out-of-tree content -- design attack A4. git tracks a
        # symlink as a symlink, so the tracked check below would not catch it.
        # Refuse any member that is a symlink or whose real path escapes root,
        # before rights/tracked/read.
        full = root / path
        if full.is_symlink() or not full.resolve().is_relative_to(root.resolve()):
            _fail("bundle_member_unsafe_path", f"symlink_or_escapes_root:{path}")
        if _rights_ineligible(path, contract):
            _fail("bundle_member_rights_ineligible", path)
        if path not in tracked:
            _fail("bundle_member_untracked", path)
        actual = hashlib.sha256(full.read_bytes()).hexdigest()
        declared = member["declared_sha256"]
        if not isinstance(declared, str) or declared != actual:
            _fail("bundle_member_digest_mismatch", path)
        rows.append({"path": path, "sha256": actual})

    rows.sort(key=lambda r: r["path"])
    manifest = {
        "schema_version": "0.1.0",
        "bundle_manifest_id": "offline-bundle-manifest",
        "members": rows,
        "member_count": len(rows),
    }
    manifest["manifest_digest"] = event_ledger_extension.typed_record_sha256(
        cast(Mapping[str, Any], manifest))
    return manifest


def verify_rebuild(
    manifest: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Rebuild the manifest from the same members and refuse on any drift.

    An offline bundle's whole worth is that its digest reproduces. A rebuilt
    manifest that differs by one byte from the presented one is
    bundle_nondeterminism_detected.
    """
    rebuilt = build_manifest(members, root=root, contract=contract)
    if rebuilt["manifest_digest"] != manifest.get("manifest_digest"):
        _fail("bundle_nondeterminism_detected", rebuilt["manifest_digest"])
    if rebuilt["members"] != list(manifest.get("members", [])):
        _fail("bundle_nondeterminism_detected", "members")
    return {"verified": True, "manifest_digest": rebuilt["manifest_digest"]}


# A single fixed timestamp for every zip member. A bundle's bytes must not
# depend on when it was built, so mtime is pinned rather than "now". 1980-01-01
# is the zip epoch (the earliest a DOS timestamp can express).
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def build_bundle_bytes(
    members: Sequence[Mapping[str, Any]],
    *,
    root: Path = ROOT,
    contract: Mapping[str, Any] | None = None,
) -> bytes:
    """Package the manifest and its members into a BYTE-DETERMINISTIC zip.

    Two builds over the same members and committed bytes are byte-identical.
    Determinism is not free in zip: it requires a fixed member order, a fixed
    per-member timestamp, a single compression method, and no host-specific
    external attributes. The manifest is admitted first (so a rights-restricted
    or tampered member refuses before any bytes are written), then members and
    manifest.json are added in one lexicographic order.
    """
    contract = contract or load_contract()
    manifest = build_manifest(members, root=root, contract=contract)

    entries: list[tuple[str, bytes]] = [
        (row["path"], (root / row["path"]).read_bytes())
        for row in manifest["members"]
    ]
    entries.append((
        "manifest.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8"),
    ))
    entries.sort(key=lambda e: e[0])

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo(filename=name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16  # fixed mode, no host bits
            info.create_system = 3  # fixed to unix, not the building host
            zf.writestr(info, data)
    return buffer.getvalue()


def verify_bundle_bytes(bundle_bytes: bytes) -> dict[str, Any]:
    """Reader-side verification of a bundle, using ONLY the standard library.

    A reader who distrusts the site opens the zip, reads its manifest.json, and
    re-hashes every member against the digest the manifest declares. This uses
    zipfile + hashlib + json alone -- no IGRM code, no typed-canonical runtime,
    nothing the reader would have to trust. It is the "convenience, never an
    authority" verifier of design/offline_audit_bundle.md: it checks that the
    zip's member bytes match the manifest's member digests and that no zip
    member escaped the manifest. It deliberately does NOT re-check the manifest
    self-digest (that needs the typed-canonical runtime) nor a signature nor a
    timestamp -- those are separate, and two of them are out of a reader's hands.
    """
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as zf:
        bad = zf.testzip()
        if bad is not None:
            _fail("bundle_member_digest_mismatch", f"corrupt_zip_entry:{bad}")
        try:
            manifest = json.loads(zf.read("manifest.json"), object_pairs_hook=_unique_object)
        except (KeyError, json.JSONDecodeError) as exc:
            raise OfflineBundleError("bundle_manifest_incomplete",
                                     "manifest.json_missing_or_unreadable") from exc
        # The bundle is UNTRUSTED here (a reader verifying a possibly hostile
        # bundle), so every shape is checked before use: a malformed manifest
        # must refuse cleanly, never crash. Refusal-first on the reader path.
        if not isinstance(manifest, dict):
            _fail("bundle_manifest_incomplete", "manifest_not_object")
        raw_members = manifest.get("members")
        if not isinstance(raw_members, list):
            _fail("bundle_manifest_incomplete", "members_not_list")
        declared: dict[str, str] = {}
        for m in raw_members:
            if (not isinstance(m, dict) or not isinstance(m.get("path"), str)
                    or not isinstance(m.get("sha256"), str)):
                _fail("bundle_manifest_incomplete", "malformed_manifest_member")
            if m["path"] in declared:
                _fail("bundle_manifest_incomplete", "duplicate_manifest_member")
            declared[m["path"]] = m["sha256"]
        present = {n for n in zf.namelist() if n != "manifest.json"}
        if present != set(declared):
            _fail("bundle_manifest_incomplete",
                  "zip_members_and_manifest_members_differ")
        for path, want in declared.items():
            got = hashlib.sha256(zf.read(path)).hexdigest()
            if got != want:
                _fail("bundle_member_digest_mismatch", path)
    return {"verified": True, "member_count": len(declared)}


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(
        description="Validate the offline-bundle contract loads deny-by-default.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        contract = load_contract()
        print(f"[offline-bundle] contract {contract['contract_id']} ok; "
              f"{len(contract['rights_restricted_globs'])} restricted globs, "
              f"{len(contract['refusal_codes'])} codes")
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
