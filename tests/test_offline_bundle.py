"""Offline audit bundle — the byte-deterministic manifest sub-slice.

Design: design/offline_audit_bundle.md. This proves the manifest half:
member admission (rights-eligible, tracked, safe path, digest-matched) and a
manifest whose self-digest reproduces from committed bytes. Deferred sub-slices
(zip, signature, timestamp, verifier) are NOT tested here and their codes must
NOT be reachable yet.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from src import offline_bundle as ob

ROOT = Path(__file__).resolve().parents[1]

# Small tracked public inputs that exist today.
PUBLIC = ["docs/data/latest.json", "docs/data/shares.csv"]


def _member(path: str) -> dict:
    return {"path": path,
            "declared_sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}


def _members() -> list[dict]:
    return [_member(p) for p in PUBLIC]


def test_contract_loads_deny_by_default() -> None:
    contract = ob.load_contract()
    assert contract["default_policy"] == "deny"
    assert "data/raw/" in contract["rights_restricted_globs"]


def test_a_real_manifest_builds_and_is_byte_deterministic() -> None:
    a = ob.build_manifest(_members())
    b = ob.build_manifest(_members())
    assert a["manifest_digest"] == b["manifest_digest"], "manifest is non-deterministic"
    assert a["member_count"] == len(PUBLIC)
    # members are lexicographically ordered
    assert [m["path"] for m in a["members"]] == sorted(PUBLIC)
    assert ob.verify_rebuild(a, _members())["verified"] is True


def test_rights_restricted_member_refuses() -> None:
    members = _members() + [{"path": "data/raw/gdelt_chunks/x.json",
                             "declared_sha256": "0" * 64}]
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest(members)
    assert err.value.code == "bundle_member_rights_ineligible"


def test_untracked_member_refuses(tmp_path: Path) -> None:
    # a path that is safe and not rights-restricted but not tracked in git
    members = [{"path": "docs/data/this_file_is_not_tracked_zzz.json",
                "declared_sha256": "0" * 64}]
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest(members)
    assert err.value.code == "bundle_member_untracked"


def test_declared_digest_mismatch_refuses() -> None:
    members = _members()
    members[0]["declared_sha256"] = "0" * 64  # wrong digest for a real file
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest(members)
    assert err.value.code == "bundle_member_digest_mismatch"


@pytest.mark.parametrize("bad_path", [
    "/etc/passwd",                       # absolute
    "../secret.txt",                     # traversal
    "docs/../../escape.txt",             # traversal via ..
    "docs\\data\\latest.json",           # backslash
    "docs/data/./latest.json",           # non-normalized
])
def test_unsafe_member_path_refuses(bad_path: str) -> None:
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest([{"path": bad_path, "declared_sha256": "0" * 64}])
    assert err.value.code == "bundle_member_unsafe_path"


def test_duplicate_member_path_refuses() -> None:
    m = _member(PUBLIC[0])
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest([m, dict(m)])
    assert err.value.code == "bundle_member_duplicate_path"


def test_a_flipped_member_byte_breaks_the_rebuild() -> None:
    """The determinism claim, from the reader's side: if a member's bytes
    change after the manifest was built, verify_rebuild refuses. Simulated by
    presenting a manifest whose member digest no longer matches the file."""
    manifest = ob.build_manifest(_members())
    tampered = dict(manifest)
    tampered_members = [dict(r) for r in manifest["members"]]
    tampered_members[0] = {**tampered_members[0], "sha256": "f" * 64}
    tampered["members"] = tampered_members
    # rebuild from the true members; the presented (tampered) manifest differs
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.verify_rebuild(tampered, _members())
    assert err.value.code == "bundle_nondeterminism_detected"


def test_malformed_member_shape_refuses() -> None:
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_manifest([{"path": PUBLIC[0]}])  # missing declared_sha256
    assert err.value.code == "bundle_manifest_incomplete"


def test_reserved_codes_are_not_reachable_by_this_runtime() -> None:
    """No over-claim: the contract lists reserved codes for later sub-slices;
    this runtime must raise exactly refusal_codes and none of the reserved
    set. Asserted by scraping _fail( sites out of the module source."""
    import re
    src = (ROOT / "src" / "offline_bundle.py").read_text(encoding="utf-8")
    raised = set(re.findall(r'_fail\("([a-z_]+)"', src))
    # ProductManifestError-style: also catch codes passed to the constructor
    raised |= set(re.findall(r'OfflineBundleError\("([a-z_]+)"', src))
    contract = ob.load_contract()
    registered = set(contract["refusal_codes"])
    reserved = set(contract["reserved_refusal_codes_later_slices"])
    assert raised <= registered, {"raised_not_registered": raised - registered}
    assert not (raised & reserved), {"raised_a_reserved_code": raised & reserved}
    assert registered.isdisjoint(reserved), "a code is both registered and reserved"
