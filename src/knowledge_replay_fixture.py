"""Deterministic two-release fixture for the IGRM knowledge time machine.

Every private key is a public test vector derived from a fixed label.  The
fixture contains no real source, event, rights or exposure assertion and must
never be installed as a production trust root.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from src import canonical_objects as canonical
from src import knowledge_replay
from src.oges_fixture import Fixture as OgesFixture
from src.oges_fixture import build_fixture as build_oges_fixture

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class KnowledgeReplayFixture:
    root: Path
    ledger: Path
    ledger_signature: Path
    release_manifests: tuple[Path, Path]
    receipts: tuple[Path, Path]
    availability_private_key: Ed25519PrivateKey
    ledger_private_key: Ed25519PrivateKey
    release_private_key: Ed25519PrivateKey


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _private_key(label: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(f"IGRM-KNOWLEDGE-REPLAY-TEST-ONLY:{label}".encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _public_key(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")


def _install_replay_contract(
    root: Path,
    availability_private_key: Ed25519PrivateKey,
    ledger_private_key: Ed25519PrivateKey,
) -> None:
    shutil.copy2(
        ROOT / "governance" / "knowledge_replay_registry.json",
        root / "governance" / "knowledge_replay_registry.json",
    )
    source = root / "src" / "knowledge_replay.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src" / "knowledge_replay.py", source)
    _write_json(
        root / "governance" / "knowledge_replay_signers.json",
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "signer:knowledge.availability.fixture",
                    "name": "Knowledge availability public test-vector signer",
                    "roles": ["knowledge_availability_signer"],
                    "public_key_ed25519_base64": _public_key(
                        availability_private_key
                    ),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                },
                {
                    "signer_id": "signer:knowledge.ledger.fixture",
                    "name": "Knowledge ledger public test-vector signer",
                    "roles": ["knowledge_ledger_signer"],
                    "public_key_ed25519_base64": _public_key(ledger_private_key),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                }
            ],
        },
    )


def _freeze_release(
    fixture: OgesFixture,
    manifest: dict[str, Any],
    *,
    sequence: int,
) -> Path:
    root = fixture.root
    entries: list[dict[str, Any]] = []
    for entry in manifest["objects"]:
        original = root / entry["path"]
        frozen = root / "canonical" / "objects" / f"{entry['file_sha256']}.json"
        frozen.parent.mkdir(parents=True, exist_ok=True)
        if not frozen.exists():
            shutil.copy2(original, frozen)
        updated = dict(entry)
        updated["path"] = frozen.relative_to(root).as_posix()
        entries.append(updated)
    manifest["objects"] = entries
    signature = root / "canonical" / "releases" / f"{sequence:04d}.sig"
    manifest["release_signature_path"] = signature.relative_to(root).as_posix()
    sealed = canonical.seal_record(manifest)
    path = root / "canonical" / "releases" / f"{sequence:04d}.json"
    _write_json(path, sealed)
    signature.write_bytes(fixture.release_private_key.sign(path.read_bytes()))
    return path


def _new_correction_evidence(
    root: Path, release_one: MappingLike
) -> tuple[dict[str, Any], Path]:
    old_entry = next(
        row
        for row in release_one["objects"]
        if row["object_id"] == "evd:oges.fixture.official.001"
    )
    old = json.loads((root / old_entry["path"]).read_text(encoding="utf-8"))
    document = copy.deepcopy(old)
    document.update(
        evidence_id="evd:oges.fixture.correction.002",
        source_record_id="official-002",
        retrieval_id="ret:oges.fixture.002",
        title="Synthetic correction notice",
        published_at="2026-08-09T09:00:00Z",
        observed_at="2026-08-09T09:00:00Z",
        effective_start="2026-08-09T09:00:00Z",
        retrieved_at="2026-08-09T10:00:00Z",
        public_url="https://example.test/oges-fixture/official-002",
        content_sha256=hashlib.sha256(b"OGES synthetic correction bytes").hexdigest(),
    )
    document["lifecycle"] = {
        "revision": 1,
        "state": "active",
        "supersedes_id": None,
        "superseded_by": None,
        "correction_id": None,
    }
    document["provenance"] = copy.deepcopy(old["provenance"])
    document["provenance"]["created_at"] = "2026-08-09T10:15:00Z"
    sealed = canonical.seal_record(document)
    path = root / "canonical" / "objects" / f"{sealed['record_sha256']}.json"
    _write_json(path, sealed)
    return sealed, path


MappingLike = dict[str, Any]


def _new_event_revision(
    root: Path,
    release_one: MappingLike,
) -> tuple[dict[str, Any], Path]:
    old_entry = next(
        row
        for row in release_one["objects"]
        if row["object_id"] == "evt:oges.fixture.policy.001"
    )
    old = json.loads((root / old_entry["path"]).read_text(encoding="utf-8"))
    document = copy.deepcopy(old)
    document.update(
        event_id="evt:oges.fixture.policy.002",
        record_status="disputed",
        direction="mixed",
        last_verified_at="2026-08-09T11:00:00Z",
    )
    document["lifecycle"] = {
        "revision": 2,
        "state": "active",
        "supersedes_id": "evt:oges.fixture.policy.001",
        "superseded_by": None,
        "correction_id": "cor:oges.fixture.policy.001",
    }
    document["evidence_links"].append(
        {
            "evidence_id": "evd:oges.fixture.correction.002",
            "role": "correction",
            "asserted_at": "2026-08-09T10:30:00Z",
        }
    )
    document["provenance"] = copy.deepcopy(old["provenance"])
    document["provenance"]["created_at"] = "2026-08-09T11:30:00Z"
    document["provenance"]["evidence_ids"] = [
        "evd:oges.fixture.official.001",
        "evd:oges.fixture.correction.002",
    ]
    sealed = canonical.seal_record(document)
    path = root / "canonical" / "objects" / f"{sealed['record_sha256']}.json"
    _write_json(path, sealed)
    return sealed, path


def _release_two(fixture: OgesFixture, release_one_path: Path) -> Path:
    root = fixture.root
    release_one = json.loads(release_one_path.read_text(encoding="utf-8"))
    manifest = copy.deepcopy(release_one)
    manifest.update(
        release_id="rel:oges.fixture.2026-08-09",
        generated_at="2026-08-09T13:00:00Z",
        effective_date="2026-08-09",
    )
    evidence, evidence_path = _new_correction_evidence(root, release_one)
    event, event_path = _new_event_revision(root, release_one)
    manifest["objects"] = [
        row
        for row in manifest["objects"]
        if row["object_id"] != "evt:oges.fixture.policy.001"
    ]
    manifest["objects"].extend(
        [
            {
                "object_type": "evidence_item",
                "object_id": evidence["evidence_id"],
                "path": evidence_path.relative_to(root).as_posix(),
                "file_sha256": _sha(evidence_path),
                "record_sha256": evidence["record_sha256"],
            },
            {
                "object_type": "event",
                "object_id": event["event_id"],
                "path": event_path.relative_to(root).as_posix(),
                "file_sha256": _sha(event_path),
                "record_sha256": event["record_sha256"],
            },
        ]
    )
    manifest["objects"] = sorted(
        manifest["objects"], key=lambda row: (row["object_type"], row["object_id"])
    )
    manifest["counts"] = dict(manifest["counts"])
    manifest["counts"]["evidence_item"] += 1
    return _freeze_release(fixture, manifest, sequence=2)


def _governance_snapshot(root: Path) -> dict[str, dict[str, str]]:
    names = {
        "canonical_schema_registry": "governance/canonical_schema_registry.json",
        "canonical_method_registry": "governance/canonical_method_registry.json",
        "source_rights_registry": "governance/source_rights_registry.json",
        "rights_signers": "governance/rights_signers.json",
        "release_signers": "governance/release_signers.json",
    }
    return {
        name: {"path": relative, "sha256": _sha(root / relative)}
        for name, relative in names.items()
    }


def _receipt(
    root: Path,
    private_key: Ed25519PrivateKey,
    release_path: Path,
    *,
    sequence: int,
    available_at: str,
    previous_sha: str | None,
) -> Path:
    manifest = json.loads(release_path.read_text(encoding="utf-8"))
    signature_path = root / "knowledge" / "receipt-signatures" / f"{sequence:04d}.sig"
    document = canonical.seal_record(
        {
            "object_type": "knowledge_availability_receipt",
            "schema_version": "1.0.0",
            "receipt_id": f"krc:oges.fixture.{sequence:04d}",
            "record_sha256": "0" * 64,
            "sequence": sequence,
            "previous_receipt_file_sha256": previous_sha,
            "release_id": manifest["release_id"],
            "release_manifest_file_sha256": _sha(release_path),
            "release_record_sha256": manifest["record_sha256"],
            "release_generated_at": manifest["generated_at"],
            "available_at": available_at,
            "signer_id": "signer:knowledge.availability.fixture",
            "signature_path": signature_path.relative_to(root).as_posix(),
        }
    )
    path = root / "knowledge" / "receipts" / f"{sequence:04d}.json"
    _write_json(path, document)
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_bytes(private_key.sign(path.read_bytes()))
    return path


def build_fixture(destination: Path) -> KnowledgeReplayFixture:
    """Build a deterministic signed two-release replay ledger."""

    fixture = build_oges_fixture(destination)
    root = fixture.root
    availability_private_key = _private_key("availability")
    ledger_private_key = _private_key("ledger")
    _install_replay_contract(root, availability_private_key, ledger_private_key)

    release_one_source = json.loads(fixture.manifest.read_text(encoding="utf-8"))
    release_one = _freeze_release(fixture, release_one_source, sequence=1)
    release_two = _release_two(fixture, release_one)
    receipt_one = _receipt(
        root,
        availability_private_key,
        release_one,
        sequence=1,
        available_at="2026-08-08T14:00:00Z",
        previous_sha=None,
    )
    receipt_two = _receipt(
        root,
        availability_private_key,
        release_two,
        sequence=2,
        available_at="2026-08-09T14:00:00Z",
        previous_sha=_sha(receipt_one),
    )
    governance = _governance_snapshot(root)
    entries = []
    for sequence, (release_path, receipt_path) in enumerate(
        ((release_one, receipt_one), (release_two, receipt_two)), start=1
    ):
        manifest = json.loads(release_path.read_text(encoding="utf-8"))
        receipt_document = json.loads(receipt_path.read_text(encoding="utf-8"))
        entries.append(
            {
                "sequence": sequence,
                "snapshot_kind": "complete",
                "release_id": manifest["release_id"],
                "manifest_path": release_path.relative_to(root).as_posix(),
                "manifest_file_sha256": _sha(release_path),
                "manifest_record_sha256": manifest["record_sha256"],
                "generated_at": manifest["generated_at"],
                "effective_date": manifest["effective_date"],
                "available_at": receipt_document["available_at"],
                "receipt_path": receipt_path.relative_to(root).as_posix(),
                "receipt_file_sha256": _sha(receipt_path),
                "governance": governance,
            }
        )
    ledger_signature = root / "knowledge" / "ledger.sig"
    ledger = canonical.seal_record(
        {
            "object_type": "knowledge_replay_ledger",
            "schema_version": "1.0.0",
            "ledger_id": "kld:oges.fixture.2026-08-09",
            "record_sha256": "0" * 64,
            "created_at": "2026-08-09T15:00:00Z",
            "replay_registry_sha256": _sha(
                root / "governance" / "knowledge_replay_registry.json"
            ),
            "availability_signers_sha256": _sha(
                root / "governance" / "knowledge_replay_signers.json"
            ),
            "ledger_signer_id": "signer:knowledge.ledger.fixture",
            "ledger_signature_path": ledger_signature.relative_to(root).as_posix(),
            "entries": entries,
            "counts": {"releases": len(entries)},
        }
    )
    ledger_path = root / "knowledge" / "ledger.json"
    _write_json(ledger_path, ledger)
    ledger_signature.write_bytes(ledger_private_key.sign(ledger_path.read_bytes()))
    return KnowledgeReplayFixture(
        root=root,
        ledger=ledger_path,
        ledger_signature=ledger_signature,
        release_manifests=(release_one, release_two),
        receipts=(receipt_one, receipt_two),
        availability_private_key=availability_private_key,
        ledger_private_key=ledger_private_key,
        release_private_key=fixture.release_private_key,
    )


def build_demo_payload() -> dict[str, Any]:
    """Return the byte-deterministic public synthetic replay demonstration."""

    with tempfile.TemporaryDirectory(prefix="igrm-knowledge-replay-") as temporary:
        fixture = build_fixture(Path(temporary))
        replay_registry = (
            fixture.root / "governance" / "knowledge_replay_registry.json"
        )
        replay_signers = (
            fixture.root / "governance" / "knowledge_replay_signers.json"
        )
        before = knowledge_replay.replay(
            fixture.ledger,
            "2026-08-08T14:30:00Z",
            "2026-08-08",
            root=fixture.root,
            replay_registry_path=replay_registry,
            knowledge_signers_path=replay_signers,
            object_type="event",
        )
        after = knowledge_replay.replay(
            fixture.ledger,
            "2026-08-09T14:30:00Z",
            "2026-08-08",
            root=fixture.root,
            replay_registry_path=replay_registry,
            knowledge_signers_path=replay_signers,
            object_type="event",
        )
    return {
        "_meta": {
            "schema": "igrm-knowledge-replay-demo-v1",
            "generated": "2026-08-08T00:00:00Z",
            "date": "2026-08-08",
            "what": "Deterministic synthetic demonstration of two-time signed-release replay; it contains no real geopolitical observation.",
            "license": "CC-BY-4.0",
            "citation": "India Geopolitical Risk Monitor (2026), Knowledge replay synthetic conformance demonstration.",
            "source": "https://igrm.in/data/knowledge_replay_demo.json",
            "codebook": "https://igrm.in/standard.html",
        },
        "schema_version": "1.0.0",
        "demo_class": "synthetic_test_vector_only",
        "before_correction_receipt": before,
        "after_correction_receipt": after,
        "assertions": {
            "same_valid_date": True,
            "different_knowledge_cutoffs": True,
            "later_revision_never_leaks_into_earlier_cutoff": True,
            "production_release": False,
        },
    }


def write_demo(path: Path) -> None:
    _write_json(path, build_demo_payload())


if __name__ == "__main__":
    write_demo(ROOT / "docs" / "data" / "knowledge_replay_demo.json")
