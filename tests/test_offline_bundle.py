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


def test_symlink_member_refuses_before_reading_its_target(tmp_path: Path) -> None:
    """Adversarial self-review (design attack A4): a symlink member would have
    read_bytes() follow the link and bundle out-of-tree content. git tracks a
    symlink as a symlink, so the tracked check would not catch it. Refuse."""
    import os
    secret = tmp_path / "out_of_tree_secret.txt"
    secret.write_text("SECRET")
    link = ROOT / "docs" / "data" / "_advtest_symlink.json"
    try:
        os.symlink(secret, link)
        digest = hashlib.sha256(link.read_bytes()).hexdigest()  # the target's bytes
        with pytest.raises(ob.OfflineBundleError) as err:
            ob.build_manifest([{"path": "docs/data/_advtest_symlink.json",
                                "declared_sha256": digest}])
        assert err.value.code == "bundle_member_unsafe_path"
    finally:
        link.unlink(missing_ok=True)


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


# --- deterministic zip packaging (T11 sub-slice) ----------------------------

def test_bundle_zip_is_byte_deterministic() -> None:
    import io
    import zipfile
    a = ob.build_bundle_bytes(_members())
    b = ob.build_bundle_bytes(_members())
    assert a == b, "the bundle zip is not byte-reproducible"
    # it is a real, readable zip containing the members + manifest.json
    with zipfile.ZipFile(io.BytesIO(a)) as zf:
        names = sorted(zf.namelist())
        assert names == sorted(PUBLIC + ["manifest.json"])
        # every member's stored bytes equal the committed file bytes
        for p in PUBLIC:
            assert zf.read(p) == (ROOT / p).read_bytes()


def test_bundle_zip_refuses_a_rights_restricted_member_before_writing() -> None:
    members = _members() + [{"path": "data/raw/gdelt_chunks/x.json",
                             "declared_sha256": "0" * 64}]
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.build_bundle_bytes(members)
    assert err.value.code == "bundle_member_rights_ineligible"


def test_bundle_zip_member_timestamp_is_pinned_not_now() -> None:
    import io
    import zipfile
    data = ob.build_bundle_bytes(_members())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0), (
                "a zip member carries a build-time timestamp; the bundle bytes "
                "would then depend on when it was built")


# --- T1 sufficiency: the bundle carries the reconstruction inputs -----------

def test_bundle_carries_the_public_reconstruction_inputs() -> None:
    """The bundle's central claim (design/offline_audit_bundle.md §2): a reader
    can recompute every published score cell from the bundle's public inputs.
    src.blind_replicator IS that recomputation, and it reads shares.csv and
    history.csv from its SITE_DATA. This proves the bundle can carry exactly
    those inputs, digest-matched, so the T1 claim is not hollow. Coupled to
    blind_replicator's real reads: if it starts reading a different file, this
    list is wrong and should be updated deliberately."""
    from src import blind_replicator as br

    site = br.SITE_DATA.relative_to(ROOT).as_posix()
    reconstruction_inputs = [f"{site}/shares.csv", f"{site}/history.csv"]
    # sanity: those are the files blind_replicator actually opens
    src_text = (ROOT / "src" / "blind_replicator.py").read_text(encoding="utf-8")
    for name in ("shares.csv", "history.csv"):
        assert f'"{name}"' in src_text, (
            f"blind_replicator no longer reads {name}; update this coupling")

    members = [_member(p) for p in reconstruction_inputs]
    bundle = ob.build_bundle_bytes(members)
    assert ob.verify_bundle_bytes(bundle)["verified"] is True
    manifest = ob.build_manifest(members)
    carried = {m["path"] for m in manifest["members"]}
    assert set(reconstruction_inputs) <= carried, (
        "the bundle does not carry blind_replicator's reconstruction inputs; "
        "the T1 'recompute from included public inputs' claim would be hollow")


# --- stdlib reader-side verifier (T12 sub-slice) ----------------------------

def test_verifier_accepts_a_faithful_bundle() -> None:
    data = ob.build_bundle_bytes(_members())
    result = ob.verify_bundle_bytes(data)
    assert result["verified"] is True
    assert result["member_count"] == len(PUBLIC)


def test_verifier_rejects_a_tampered_member() -> None:
    import io
    import zipfile
    data = ob.build_bundle_bytes(_members())
    # rebuild a zip with one member's bytes altered but the manifest unchanged
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        manifest_bytes = zf.read("manifest.json")
        contents = {n: zf.read(n) for n in zf.namelist()}
    contents[PUBLIC[0]] = contents[PUBLIC[0]] + b"tamper"
    contents["manifest.json"] = manifest_bytes  # unchanged: digests now stale
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in sorted(contents):
            zf.writestr(name, contents[name])
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.verify_bundle_bytes(out.getvalue())
    assert err.value.code == "bundle_member_digest_mismatch"


def test_verifier_rejects_a_zip_member_not_in_the_manifest() -> None:
    import io
    import zipfile
    data = ob.build_bundle_bytes(_members())
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        contents = {n: zf.read(n) for n in zf.namelist()}
    contents["docs/data/latest.json_stowaway"] = b"{}"  # not in the manifest
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        for name in sorted(contents):
            zf.writestr(name, contents[name])
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.verify_bundle_bytes(out.getvalue())
    assert err.value.code == "bundle_manifest_incomplete"


@pytest.mark.parametrize("manifest_obj", [
    {"members": [{"path": "docs/data/latest.json"}]},   # member missing sha256
    {"members": [{"sha256": "0" * 64}]},                 # member missing path
    {"members": "not-a-list"},                           # members not a list
    [1, 2, 3],                                            # manifest not an object
    {"members": [{"path": "a", "sha256": "0" * 64},
                 {"path": "a", "sha256": "1" * 64}]},     # duplicate member path
])
def test_verifier_refuses_a_hostile_manifest_cleanly(manifest_obj: object) -> None:
    """The verifier processes UNTRUSTED input. A bundle crafted with a malformed
    manifest.json must refuse cleanly (refusal-first), never crash the reader."""
    import io
    import json
    import zipfile
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest_obj))
    with pytest.raises(ob.OfflineBundleError) as err:
        ob.verify_bundle_bytes(out.getvalue())
    assert err.value.code == "bundle_manifest_incomplete"


def test_verifier_uses_only_the_standard_library() -> None:
    """The verifier's worth is that a reader need trust nothing but Python's
    stdlib. Assert the function body touches no IGRM runtime -- no
    event_ledger, no build_manifest, no typed-canonical."""
    import inspect
    body = inspect.getsource(ob.verify_bundle_bytes)
    for forbidden in ("event_ledger", "build_manifest", "typed_record_sha256",
                      "typed_canonical", "_typed_sha"):
        assert forbidden not in body, (
            f"verify_bundle_bytes references {forbidden!r}; the stdlib-only "
            "property (a reader trusts nothing but Python) is broken")


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
