"""Adversarial tests for hindsight-free signed world-state replay."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import canonical_objects as canonical
from src import knowledge_replay
from src.knowledge_replay_fixture import (
    KnowledgeReplayFixture,
    build_demo_payload,
    build_fixture,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_key_text(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _kwargs(fixture: KnowledgeReplayFixture) -> dict[str, Path]:
    return {
        "root": fixture.root,
        "replay_registry_path": fixture.root
        / "governance"
        / "knowledge_replay_registry.json",
        "knowledge_signers_path": fixture.root
        / "governance"
        / "knowledge_replay_signers.json",
    }


def _replay(
    fixture: KnowledgeReplayFixture,
    cutoff: str,
    *,
    valid_on: str = "2026-08-08",
    object_type: str | None = "event",
    object_id: str | None = None,
) -> dict[str, Any]:
    return knowledge_replay.replay(
        fixture.ledger,
        cutoff,
        valid_on,
        object_type=object_type,
        object_id=object_id,
        **_kwargs(fixture),
    )


def _resign_ledger(fixture: KnowledgeReplayFixture) -> None:
    ledger = json.loads(fixture.ledger.read_text(encoding="utf-8"))
    for index, (manifest_path, receipt_path) in enumerate(
        zip(fixture.release_manifests, fixture.receipts), start=1
    ):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        entry = ledger["entries"][index - 1]
        entry.update(
            release_id=manifest["release_id"],
            manifest_file_sha256=_sha(manifest_path),
            manifest_record_sha256=manifest["record_sha256"],
            generated_at=manifest["generated_at"],
            effective_date=manifest["effective_date"],
            available_at=receipt["available_at"],
            receipt_file_sha256=_sha(receipt_path),
        )
    _write_json(fixture.ledger, canonical.seal_record(ledger))
    fixture.ledger_signature.write_bytes(
        fixture.ledger_private_key.sign(fixture.ledger.read_bytes())
    )


def _rewrite_receipt(
    fixture: KnowledgeReplayFixture,
    index: int,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    path = fixture.receipts[index]
    receipt = json.loads(path.read_text(encoding="utf-8"))
    manifest_path = fixture.release_manifests[index]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt.update(
        release_id=manifest["release_id"],
        release_manifest_file_sha256=_sha(manifest_path),
        release_record_sha256=manifest["record_sha256"],
        release_generated_at=manifest["generated_at"],
    )
    if index > 0:
        receipt["previous_receipt_file_sha256"] = _sha(fixture.receipts[index - 1])
    if mutate is not None:
        mutate(receipt)
    _write_json(path, canonical.seal_record(receipt))
    signature = fixture.root / receipt["signature_path"]
    signature.write_bytes(fixture.availability_private_key.sign(path.read_bytes()))
    if index == 0:
        _rewrite_receipt(fixture, 1)
    _resign_ledger(fixture)


def _rewrite_release(
    fixture: KnowledgeReplayFixture,
    index: int,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    path = fixture.release_manifests[index]
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    _write_json(path, canonical.seal_record(manifest))
    signature = fixture.root / manifest["release_signature_path"]
    signature.write_bytes(fixture.release_private_key.sign(path.read_bytes()))
    _rewrite_receipt(fixture, index)


def _replace_knowledge_signer_key(
    fixture: KnowledgeReplayFixture,
    signer_id: str,
    private_key: Ed25519PrivateKey,
) -> None:
    signers_path = fixture.root / "governance" / "knowledge_replay_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    row = next(row for row in signers["signers"] if row["signer_id"] == signer_id)
    row["public_key_ed25519_base64"] = _public_key_text(private_key)
    _write_json(signers_path, signers)

    if "knowledge_availability_signer" in row["roles"]:
        for path in fixture.receipts:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            (fixture.root / receipt["signature_path"]).write_bytes(
                private_key.sign(path.read_bytes())
            )

    ledger = json.loads(fixture.ledger.read_text(encoding="utf-8"))
    ledger["availability_signers_sha256"] = _sha(signers_path)
    _write_json(fixture.ledger, canonical.seal_record(ledger))
    ledger_key = (
        private_key
        if ledger["ledger_signer_id"] == signer_id
        else fixture.ledger_private_key
    )
    fixture.ledger_signature.write_bytes(ledger_key.sign(fixture.ledger.read_bytes()))


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for nested in value.values() for key in _all_keys(nested)
        }
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def test_replay_selects_only_the_release_receipted_by_each_cutoff(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    before = _replay(fixture, "2026-08-08T14:30:00Z")
    after = _replay(fixture, "2026-08-09T14:30:00Z")

    assert before["selected_release"]["release_id"] == "rel:oges.fixture.2026-08-08"
    assert before["records"] == [
        {
            "object_type": "event",
            "object_id": "evt:oges.fixture.policy.001",
            "record_sha256": before["records"][0]["record_sha256"],
            "lifecycle_revision": 1,
            "lifecycle_state": "active",
            "record_status": "confirmed",
            "publication_phase": "final",
            "verification_status": None,
            "effective_on_valid_date": True,
            "selection_status": "included",
            "selection_reason": "active_and_effective",
        }
    ]
    assert after["selected_release"]["release_id"] == "rel:oges.fixture.2026-08-09"
    assert after["records"][0]["object_id"] == "evt:oges.fixture.policy.002"
    assert after["records"][0]["record_status"] == "disputed"
    assert after["changes"] == {
        "basis_release_id": "rel:oges.fixture.2026-08-08",
        "added_ids": ["evt:oges.fixture.policy.002"],
        "removed_ids": ["evt:oges.fixture.policy.001"],
        "same_id_changed_ids": [],
    }
    assert before["query"]["valid_on"] == after["query"]["valid_on"]
    assert before["record_sha256"] != after["record_sha256"]


def test_replay_is_deterministic_and_emits_no_labels_values_urls_or_evidence_text(
    tmp_path: Path,
) -> None:
    first = build_fixture(tmp_path / "first")
    second = build_fixture(tmp_path / "second")
    one = _replay(first, "2026-08-09T14:30:00Z", object_type=None)
    two = _replay(second, "2026-08-09T14:30:00Z", object_type=None)
    assert one == two
    forbidden = {
        "canonical_label",
        "canonical_name",
        "title",
        "public_url",
        "artifact_path",
        "magnitude",
        "value",
        "confidence",
        "evidence_links",
    }
    assert forbidden.isdisjoint(_all_keys(one))
    encoded = json.dumps(one, sort_keys=True)
    assert "Synthetic" not in encoded
    assert "example.test" not in encoded
    assert "12.5" not in encoded


def test_cutoff_refuses_before_first_receipt_and_after_signed_ledger_close(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as early:
        _replay(fixture, "2026-08-08T13:59:59Z")
    assert early.value.code == "knowledge_cutoff_before_first_receipt"
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as late:
        _replay(fixture, "2026-08-09T15:00:01Z")
    assert late.value.code == "knowledge_cutoff_after_ledger_close"


def test_object_absence_is_explicit_and_never_substitutes_a_later_revision(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    result = _replay(
        fixture,
        "2026-08-08T14:30:00Z",
        object_id="evt:oges.fixture.policy.002",
    )
    assert result["records"] == []
    assert result["result"] == {
        "status": "object_absent",
        "requested_object_present": False,
        "records_considered": 0,
        "included": 0,
        "excluded": 0,
    }


def test_receipt_signature_chain_and_release_bytes_are_reverified(
    tmp_path: Path,
) -> None:
    signature_fixture = build_fixture(tmp_path / "signature")
    second_receipt = json.loads(
        signature_fixture.receipts[1].read_text(encoding="utf-8")
    )
    (signature_fixture.root / second_receipt["signature_path"]).write_bytes(b"0" * 64)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as signature:
        _replay(signature_fixture, "2026-08-09T14:30:00Z")
    assert signature.value.code == "knowledge_signature_invalid"

    release_fixture = build_fixture(tmp_path / "release")
    release_fixture.release_manifests[0].write_text(
        release_fixture.release_manifests[0].read_text() + "\n", encoding="utf-8"
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as release:
        _replay(release_fixture, "2026-08-09T14:30:00Z")
    assert release.value.code == "knowledge_release_manifest_digest_mismatch"


def test_availability_and_ledger_roles_cannot_alias_one_public_key(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    _replace_knowledge_signer_key(
        fixture,
        "signer:knowledge.ledger.fixture",
        fixture.availability_private_key,
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_signer_key_duplicate"


def test_one_signer_identity_cannot_hold_both_knowledge_roles(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    signers_path = fixture.root / "governance" / "knowledge_replay_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["roles"] = [
        "knowledge_availability_signer",
        "knowledge_ledger_signer",
    ]
    _write_json(signers_path, signers)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_signer_entry_invalid"


def test_knowledge_signer_revocation_must_follow_its_effective_date(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    signers_path = fixture.root / "governance" / "knowledge_replay_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    signers["signers"][0]["revoked_on"] = signers["signers"][0]["effective"]
    _write_json(signers_path, signers)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_signer_revoked_invalid"


def test_availability_key_cannot_alias_the_canonical_release_key(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    _replace_knowledge_signer_key(
        fixture,
        "signer:knowledge.availability.fixture",
        fixture.release_private_key,
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_receipt_not_separate_from_release_signer"


def test_ledger_key_cannot_alias_the_canonical_release_key(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    _replace_knowledge_signer_key(
        fixture,
        "signer:knowledge.ledger.fixture",
        fixture.release_private_key,
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_ledger_not_separate_from_release_signer"


def test_receipt_time_not_release_generated_time_controls_selection(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-08T13:30:00Z")
    assert exc.value.code == "knowledge_cutoff_before_first_receipt"


def test_later_receipt_cannot_roll_back_to_a_nonnewer_release_generation(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    _rewrite_release(
        fixture,
        0,
        lambda manifest: manifest.update(generated_at="2026-08-09T13:00:00Z"),
    )
    _rewrite_receipt(
        fixture,
        0,
        lambda receipt: receipt.update(available_at="2026-08-09T13:30:00Z"),
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_release_generated_at_not_increasing"


def test_same_id_cannot_be_silently_rewritten_between_complete_releases(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")

    def mutate(manifest: dict[str, Any]) -> None:
        entry = next(
            row
            for row in manifest["objects"]
            if row["object_id"] == "ent:country.synthetic_india"
        )
        original = json.loads(
            (fixture.root / entry["path"]).read_text(encoding="utf-8")
        )
        original["aliases"] = ["changed-same-id"]
        changed = canonical.seal_record(original)
        path = fixture.root / "canonical" / "objects" / f"{changed['record_sha256']}.json"
        _write_json(path, changed)
        entry.update(
            path=path.relative_to(fixture.root).as_posix(),
            file_sha256=_sha(path),
            record_sha256=changed["record_sha256"],
        )

    _rewrite_release(fixture, 1, mutate)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "object_id_reused_with_different_record"


def test_complete_snapshot_cannot_drop_an_active_object_without_a_successor(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")

    def remove_event(manifest: dict[str, Any]) -> None:
        manifest["objects"] = [
            row for row in manifest["objects"] if row["object_type"] != "event"
        ]
        manifest["counts"]["event"] = 0

    _rewrite_release(fixture, 1, remove_event)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "complete_snapshot_object_removed_without_successor"


def test_complete_snapshot_cannot_keep_parent_and_active_revision_together(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    release_one = json.loads(
        fixture.release_manifests[0].read_text(encoding="utf-8")
    )
    parent = next(
        copy.deepcopy(row)
        for row in release_one["objects"]
        if row["object_id"] == "evt:oges.fixture.policy.001"
    )

    def retain_parent(manifest: dict[str, Any]) -> None:
        manifest["objects"].append(parent)
        manifest["objects"] = sorted(
            manifest["objects"], key=lambda row: (row["object_type"], row["object_id"])
        )
        manifest["counts"]["event"] = 2

    _rewrite_release(fixture, 1, retain_parent)
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "object_revision_parent_retained_in_complete_snapshot"


def test_sequence_gap_refuses_even_when_the_ledger_is_resigned(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    ledger = json.loads(fixture.ledger.read_text(encoding="utf-8"))
    ledger["entries"][1]["sequence"] = 3
    _write_json(fixture.ledger, canonical.seal_record(ledger))
    fixture.ledger_signature.write_bytes(
        fixture.ledger_private_key.sign(fixture.ledger.read_bytes())
    )
    with pytest.raises(knowledge_replay.KnowledgeReplayError) as exc:
        _replay(fixture, "2026-08-09T14:30:00Z")
    assert exc.value.code == "knowledge_receipt_sequence_gap"


def test_default_repository_has_no_production_knowledge_signer() -> None:
    signers = json.loads(
        (ROOT / "governance" / "knowledge_replay_signers.json").read_text()
    )
    assert signers == {
        "schema_version": "1.0.0",
        "effective": "2026-08-08",
        "default_policy": "deny",
        "signers": [],
    }


def test_public_demo_and_schemas_are_exact_generated_contracts() -> None:
    public_demo = json.loads(
        (ROOT / "docs" / "data" / "knowledge_replay_demo.json").read_text()
    )
    assert public_demo == build_demo_payload()
    assert public_demo["demo_class"] == "synthetic_test_vector_only"
    assert public_demo["assertions"]["production_release"] is False
    for name in (
        "knowledge-availability-receipt.schema.json",
        "knowledge-replay-ledger.schema.json",
        "knowledge-replay.schema.json",
    ):
        assert (ROOT / "docs" / "schemas" / name).read_bytes() == (
            ROOT / "schemas" / name
        ).read_bytes()


def test_public_surface_states_the_production_boundary_and_is_catalogued() -> None:
    page = (ROOT / "docs" / "replay.html").read_text(encoding="utf-8")
    assert "No production canonical world-state ledger exists yet" in page
    assert "distinct identities and public keys" in page
    assert "does not establish\n  institutional independence" in page
    assert "synthetic" in page.lower()
    assert "replay.js" in page
    assert "knowledge_replay_demo.json" in page
    catalog = json.loads(
        (ROOT / "design" / "public_product_catalog.json").read_text()
    )
    row = next(row for row in catalog["routes"] if row["path"] == "replay.html")
    assert row["status"] == "public_draft"
    assert "replay.html" in catalog["protected_routes"]


def test_public_replay_script_parses_when_node_is_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available in this environment")
    result = subprocess.run(
        [node, "--check", str(ROOT / "docs" / "replay.js")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_emits_structural_json_and_stable_refusal(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    base = [
        sys.executable,
        "-m",
        "src.knowledge_replay",
        str(fixture.ledger),
        "--root",
        str(fixture.root),
        "--valid-on",
        "2026-08-08",
        "--object-type",
        "event",
    ]
    success = subprocess.run(
        [*base, "--knowledge-cutoff", "2026-08-09T14:30:00Z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert success.returncode == 0, success.stderr
    assert json.loads(success.stdout)["result"]["status"] == "state_found"

    refusal = subprocess.run(
        [*base, "--knowledge-cutoff", "2026-08-09T15:00:01Z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert refusal.returncode == 2
    assert json.loads(refusal.stderr) == {
        "status": "refused",
        "stage": "knowledge_replay",
        "reason": "knowledge_cutoff_after_ledger_close",
    }
