"""Red-team of the port-marginals compiler: the refusals nobody had fired.

CONTEXT (cross-review rule, 2026-08-10)
Instrumenting `_fail` during the existing suite shows 11 of the compiler's 42
refusal codes ever fire; 31 have never executed under test. Most of the cold
ones guard registry shape and would need a corrupted committed file. Three
guard live policy and deserved hostile fixtures:

1. `rights_use_not_approved` -- the PARTIAL-APPROVAL path. The suite tests an
   unapproved source (`rights_not_approved`) and a fully-approved one, but
   never a source whose signed decision grants a strict subset of the uses
   the pipeline requires. That scenario is not hypothetical: the ministry
   decision packets drafted today offer "APPROVE subset" explicitly, and the
   offline audit bundle will ADD a required use
   (redistribute_in_audit_bundle) to sources whose decisions were signed
   before it existed. This test stages exactly that future: requirements
   grow, an old signature does not.
   (The other direction -- registry claiming more uses than the signed
   decision -- is already closed structurally: publication_guard compares
   the decision artifact's permitted_uses to the registry entry and fails
   `rights_source_decision_artifact_mismatch` on divergence. Verified by
   reading, not asserted here.)

2. `source_knowledge_predates_registration` -- anti-backdating. A snapshot
   claiming knowledge of a vintage before IGRM registered that vintage is
   the "we always knew this" attack on the evidence clock.

3. `json_duplicate_key` -- hostile JSON. Python's default json.loads keeps
   the LAST duplicate key, so {"a":1,"a":2} silently becomes {"a":2}; two
   validators disagreeing on which copy wins is a classic smuggling channel.
   The compiler installs an object_pairs_hook against this; nothing had
   ever exercised it.

The existing suite's fixture builders are reused via importlib (tests/ is
not a package), so these attacks stay honest: everything except the attacked
field is a byte-for-byte valid, signed tree.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from src import port_commodity_marginals as marginal

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "tpcm_fixtures", ROOT / "tests" / "test_port_commodity_marginals.py")
_fx = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_fx)


def test_a_signed_subset_approval_does_not_cover_the_pinned_requirements(
        tmp_path: Path) -> None:
    """A validly signed decision granting ONE of the three required uses.

    First finding, recorded before the test would even run: the attack this
    was designed as -- grow required_permitted_uses past an old signature --
    is STRUCTURALLY IMPOSSIBLE. The compiler pins the required list to
    exactly its three members and fails `registry_uses_invalid` on any
    other value, so requirements can only move with the compiler source,
    whose digest the registry binds. Defence in depth, confirmed by a
    failed attack rather than assumed.

    So the reachable partial-approval path is the other direction: the
    rights side grants a strict subset. Everything here is internally
    valid -- fresh keypair installed in the fixture's signers file, the
    decision artifact and registry entry agree (so the structural
    mismatch check stays quiet), the signature verifies. Only the subset
    check stands between a one-use approval and a three-use compile."""
    import base64
    import hashlib

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    root, snapshot, artifact, rights, evidence = _fx._approved_tree(tmp_path)
    signers_path = root / "governance" / "rights_signers.json"

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["public_key_ed25519_base64"] = (
        base64.b64encode(public).decode())
    _fx._write(signers_path, signers)

    rights_doc = json.loads(rights.read_text(encoding="utf-8"))
    source = rights_doc["sources"][0]
    source["permitted_uses"] = ["cite_metadata"]  # a real but partial grant
    decision_path = root / source["decision_artifact_path"]
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["permitted_uses"] = ["cite_metadata"]
    _fx._write(decision_path, decision)
    source["decision_artifact_sha256"] = hashlib.sha256(
        decision_path.read_bytes()).hexdigest()
    (root / source["decision_signature_path"]).write_bytes(
        private.sign(decision_path.read_bytes()))
    _fx._write(rights, rights_doc)

    with pytest.raises(marginal.PortCommodityError) as err:
        marginal.compile_snapshot(
            snapshot, artifact, evidence, root=root,
            registry_path=root / "governance" / "port_commodity_marginals.json",
            rights_path=rights, signers_path=signers_path)
    assert err.value.code == "rights_use_not_approved", (
        f"expected the partial-approval refusal, got {err.value.code!r}: a "
        "signed grant of one use must not compile a three-use pipeline")


def test_knowledge_before_registration_is_refused(tmp_path: Path) -> None:
    """Backdate every snapshot clock to before the vintage's registered_on
    (2026-08-09 in the fixture registry), keeping the clocks internally
    consistent so no ordering check fires first. Only the anti-backdating
    refusal should remain."""
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _fx._snapshot(artifact)
    value["source_artifact"]["retrieved_at"] = "2026-08-01T00:00:00Z"
    value["extraction"]["verified_at"] = "2026-08-01T00:05:00Z"
    value["knowledge_time"] = "2026-08-01T00:10:00Z"
    registry_path = _fx._write_fixture_registry(tmp_path, artifact)

    with pytest.raises(marginal.PortCommodityError) as err:
        marginal.validate_snapshot(
            value, json.loads(registry_path.read_text(encoding="utf-8")))
    assert err.value.code == "source_knowledge_predates_registration", (
        f"got {err.value.code!r}; a snapshot may not claim to have known a "
        "vintage before IGRM registered it")


def test_duplicate_json_keys_are_refused_not_last_write_wins(
        tmp_path: Path) -> None:
    """Two total_cargo_tonnes keys: honest value first, inflated second.
    Default json.loads would keep the second silently; the compiler must
    refuse the document outright instead of picking a winner."""
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"candidate bytes")
    value = _fx._snapshot(artifact)
    registry_path = _fx._write_fixture_registry(tmp_path, artifact)
    text = json.dumps(value, indent=2)
    assert text.count('"total_cargo_tonnes": 1200') == 1
    text = text.replace('"total_cargo_tonnes": 1200',
                        '"total_cargo_tonnes": 1200, "total_cargo_tonnes": 999999',
                        1)
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(text + "\n", encoding="utf-8")

    with pytest.raises(marginal.PortCommodityError) as err:
        marginal.validate_only(
            snapshot_path, artifact, [], registry_path=registry_path)
    assert err.value.code == "json_duplicate_key", (
        f"got {err.value.code!r}; duplicate keys must refuse the document, "
        "not resolve to whichever copy the parser happens to keep")
