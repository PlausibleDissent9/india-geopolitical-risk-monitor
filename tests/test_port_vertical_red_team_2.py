"""Red-team, second pass: the same two cold refusals in the other compilers.

Instrumenting `_fail` across the whole port-trade vertical
(2026-08-10): `shipmin_port_trade_pdf` fires 9 of its 44 refusal codes
under test, `ogd_port_trade` 6 of 32. Credit where due -- shipmin's
`rights_decision_expired` and `rights_signer_inactive` DO fire, which the
marginals compiler had no equivalent for. But the same two policy-critical
codes are cold in BOTH modules, and they are the same two that were cold
in `port_commodity_marginals` before `test_port_marginals_red_team.py`:

    rights_use_not_approved    a validly signed decision granting a strict
                               subset of the pinned required uses
    json_duplicate_key         {"k": honest, "k": inflated} -- default
                               json.loads keeps the second silently

The subset attack matters concretely: the ministry decision packets in
`governance/decisions/` offer "APPROVE subset: ______" as a first-class
founder choice. If the founder ever exercises it, these three compilers'
subset checks are the only thing standing between a one-use grant and a
full-pipeline compile. As of tonight all three are tested.

Fixture technique as in the first pass: rebuild the module's own approved
fixture, downgrade the grant consistently in the rights entry AND the
decision artifact (so the structural artifact-mismatch check stays quiet),
install a fresh keypair in the fixture signers file, re-sign. Everything
is valid except the breadth of the grant.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import ogd_port_trade as ogd
from src import shipmin_port_trade_pdf as shipmin

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_shipmin_fx = _load("shipmin_fixtures", "test_shipmin_port_trade_pdf.py")
_ogd_fx = _load("ogd_fixtures", "test_ogd_port_trade.py")


def _downgrade_grant(root: Path, rights_path: Path, signers_path: Path) -> None:
    """Shrink the fixture's grant to cite_metadata only, keeping every
    signature and digest internally valid."""
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["public_key_ed25519_base64"] = (
        base64.b64encode(public).decode())
    signers_path.write_text(json.dumps(signers, indent=2) + "\n",
                            encoding="utf-8")

    rights_doc = json.loads(rights_path.read_text(encoding="utf-8"))
    source = rights_doc["sources"][0]
    source["permitted_uses"] = ["cite_metadata"]
    decision_path = root / source["decision_artifact_path"]
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["permitted_uses"] = ["cite_metadata"]
    decision_path.write_text(json.dumps(decision, indent=2) + "\n",
                             encoding="utf-8")
    source["decision_artifact_sha256"] = hashlib.sha256(
        decision_path.read_bytes()).hexdigest()
    (root / source["decision_signature_path"]).write_bytes(
        private.sign(decision_path.read_bytes()))
    rights_path.write_text(json.dumps(rights_doc, indent=2) + "\n",
                           encoding="utf-8")


def test_shipmin_refuses_a_signed_one_use_grant(tmp_path: Path) -> None:
    rights, signers, registry = _shipmin_fx._approved_rights_fixture(
        tmp_path, review_due="2027-08-09", revoked_on=None)
    _downgrade_grant(tmp_path, rights, signers)
    with pytest.raises(shipmin.ShipminPortTradeError,
                       match="rights_use_not_approved"):
        shipmin._approved_source(
            root=tmp_path, registry=registry, rights_path=rights,
            signers_path=signers, as_of=date.fromisoformat("2026-08-10"))


def test_ogd_refuses_a_signed_one_use_grant(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _ogd_fx._fixture(tmp_path)
    root = registry_path.parents[1]
    rights, signers = _ogd_fx._approved_rights(root)
    _downgrade_grant(root, rights, signers)
    with pytest.raises(ogd.OGDPortTradeError,
                       match="rights_use_not_approved"):
        # rights_path/signers_path explicitly: their defaults are the
        # repository's own governance files, where this source is
        # review_required -- omitting them makes the test "pass" against
        # the wrong registry with the coarser rights_not_approved, which
        # is exactly how the first draft of this test fooled itself.
        ogd.compile_baseline(unloaded, loaded, root=root,
                             registry_path=registry_path,
                             rights_path=rights, signers_path=signers)


def test_shipmin_refuses_duplicate_registry_keys(tmp_path: Path) -> None:
    hostile = tmp_path / "registry.json"
    hostile.write_text('{"artifact": 1, "artifact": 2}', encoding="utf-8")
    with pytest.raises(shipmin.ShipminPortTradeError,
                       match="json_duplicate_key"):
        shipmin.validate_only(tmp_path / "unused.pdf", registry_path=hostile)


def test_ogd_refuses_duplicate_registry_keys(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _ogd_fx._fixture(tmp_path)
    hostile = tmp_path / "registry.json"
    hostile.write_text('{"source": 1, "source": 2}', encoding="utf-8")
    with pytest.raises(ogd.OGDPortTradeError, match="json_duplicate_key"):
        ogd.validate_only(unloaded, loaded, registry_path=hostile)
