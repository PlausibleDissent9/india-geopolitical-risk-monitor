from __future__ import annotations

import base64
import copy
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import canonical_objects as canonical
from src import event_ledger_extension as base
from src import event_semantic_lineage as sem

from test_event_ledger_extension import (
    _fixture as build_base_fixture,
)
from test_event_ledger_extension import (
    _manifest_object,
    _sha,
    _write_json,
)

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/event-semantic-lineage/0.1.0")
BASE_EXTENSION = Path("standard/oges/extensions/event-ledger/0.1.0")

PRODUCT_UNAVAILABLE = {
    "status": "unavailable",
    "reason_code": "product_compiler_contract_not_bound",
    "product_compilation_ref": None,
    "affected_manifest_ids": [],
}

COVERED_CASES = {
    "publisher_relabelled_as_speaker",
    "fake_attribution_entity",
    "missing_attribution_evidence",
    "future_attribution",
    "later_rights_back_authorization",
    "historical_semantic_injection",
    "model_proposition_truth_promotion",
    "model_proposition_event_promotion",
    "distinct_positions_collapsed",
    "nonexclusive_divergence_called_opposition",
    "episode_count_substituted_for_events",
    "aggregate_count_substituted_for_events",
    "unsigned_lineage_authority",
    "agent_lineage_authority",
    "future_lineage_authority",
    "expired_lineage_authority",
    "unrelated_lineage_authority",
    "malformed_lineage_topology",
    "many_to_many_lineage",
    "lineage_cycle",
    "double_consumed_predecessor",
    "future_successor",
    "lineage_operation_removed",
    "lineage_operation_rewritten",
    "lineage_visible_before_knowledge",
    "lineage_consumer_producer_unavailable",
    "wrong_unit_count_delta",
    "resealed_competition_output",
    "resealed_replay_active_set",
    "product_dependency_graph_injected",
    "production_trust_promotion",
}


def _install_semantic(root: Path) -> None:
    shutil.copytree(ROOT / EXTENSION, root / EXTENSION, dirs_exist_ok=True)
    shutil.copy2(ROOT / "src/event_semantic_lineage.py", root / "src/event_semantic_lineage.py")
    destination = root / "tests/test_event_semantic_lineage.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "tests/test_event_semantic_lineage.py", destination)


def _ref(object_type: str, document: dict[str, Any]) -> dict[str, str]:
    field = {
        "claim": "claim_id",
        "event": "event_id",
        "entity": "entity_id",
        "evidence_item": "evidence_id",
    }[object_type]
    return {
        "object_type": object_type,
        "object_id": document[field],
        "record_sha256": document["record_sha256"],
    }


def _test_private_key(label: str = "semantic-lineage-coder") -> Ed25519PrivateKey:
    seed = hashlib.sha256(f"IGRM-SEMANTIC-LINEAGE-TEST-ONLY:{label}".encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _semantic_receipt(
    snapshot: dict[str, Any],
    *,
    sequence: int,
    available_at: str,
    previous: dict[str, Any] | None,
    profile: sem.SemanticProfile,
    base_binding: dict[str, str],
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "object_type": "semantic_availability_receipt",
        "schema_version": "0.1.0",
        "receipt_id": f"sar:oges.fixture.{sequence:04d}",
        "record_sha256": "0" * 64,
        "sequence": sequence,
        "previous_receipt_record_sha256": (
            previous["record_sha256"] if previous is not None else None
        ),
        "snapshot_sha256": sem.semantic_snapshot_sha256(snapshot),
        "semantic_available_at": available_at,
        "profile_sha256": profile.sha256,
        "base_bundle_file_sha256": base_binding["bundle_file_sha256"],
        "base_bundle_record_sha256": base_binding["bundle_record_sha256"],
        "base_release_id": snapshot["release_id"],
        "base_release_manifest_record_sha256": snapshot["release_manifest_record_sha256"],
        "signer_registry_sha256": profile.normative_sha256["semantic_release_signer_registry"],
        "signer_id": "signer:oges.fixture.semantic_release",
        "trust_class": "synthetic_nonproduction_public_test_vector",
        "statement_sha256": "0" * 64,
        "signature_ed25519_base64": base64.b64encode(b"0" * 64).decode("ascii"),
    }
    receipt["statement_sha256"] = sem.typed_sha256(sem.semantic_receipt_statement(receipt))
    receipt["signature_ed25519_base64"] = base64.b64encode(
        _test_private_key("semantic-release-signer").sign(
            sem.semantic_receipt_signing_bytes(receipt)
        )
    ).decode("ascii")
    return dict(sem.seal_record(receipt))


def _seal_operation(operation: dict[str, Any]) -> dict[str, Any]:
    authorization = operation["authorization"]
    authorization["payload_sha256"] = sem.typed_sha256(sem.lineage_authorization_payload(operation))
    authorization["statement_sha256"] = sem.typed_sha256(
        sem.lineage_authorization_statement(operation)
    )
    key_label = (
        "semantic-lineage-adjudicator"
        if authorization["authority_role"] == "lineage_adjudicator"
        else "semantic-lineage-coder"
    )
    authorization["signature_ed25519_base64"] = base64.b64encode(
        _test_private_key(key_label).sign(sem.lineage_authorization_signing_bytes(operation))
    ).decode("ascii")
    return dict(sem.seal_record(operation))


def _proposition(
    *,
    proposition_id: str,
    claim: dict[str, Any],
    event: dict[str, Any],
    evidence: dict[str, Any],
    actor: dict[str, Any],
    action: str,
    stance: str,
    known_at: str,
    asserted_at: str,
    profile: sem.SemanticProfile,
) -> dict[str, Any]:
    arguments = [
        {
            "position": 0,
            "name_id": "argument:actor",
            "argument_type": "entity_ref",
            "value": _ref("entity", actor),
        },
        {
            "position": 1,
            "name_id": "argument:action",
            "argument_type": "registered_term",
            "value": action,
        },
        {
            "position": 2,
            "name_id": "argument:object",
            "argument_type": "entity_ref",
            "value": _ref(
                "entity",
                _manifest_object_from_ref(profile, "ent:commodity.synthetic_crude"),
            ),
        },
    ]
    predicate = profile.predicates["predicate:actor_action_object_v1"]
    position_sha, competition_sha = sem.proposition_hashes(
        "predicate:actor_action_object_v1",
        arguments,
        stance,
        predicate,
        _ref("event", event),
    )
    evidence_ref = _ref("evidence_item", evidence)
    content_span_sha = hashlib.sha256(
        f"{proposition_id}:synthetic-unverified-span".encode()
    ).hexdigest()
    locator = {
        "locator_id": "locator:content.unverified_utf8_byte_span_v1",
        "start": 0,
        "end": 17,
        "unit": "utf8_byte",
        "locator_sha256": "0" * 64,
    }
    locator["locator_sha256"] = sem.locator_sha256(
        evidence_ref,
        content_span_sha,
        "hash_bound_locator_unverified_span",
        locator,
    )
    return dict(
        sem.seal_record(
            {
                "object_type": "claim_proposition",
                "schema_version": "0.1.0",
                "proposition_id": proposition_id,
                "record_sha256": "0" * 64,
                "claim_ref": _ref("claim", claim),
                "event_ref": _ref("event", event),
                "predicate_id": "predicate:actor_action_object_v1",
                "ordered_arguments": arguments,
                "stance": stance,
                "position_sha256": position_sha,
                "competition_sha256": competition_sha,
                "known_at": known_at,
                "attributions": [
                    {
                        "actor_kind": "named_entity",
                        "actor_entity_ref": _ref("entity", actor),
                        "evidence_ref": evidence_ref,
                        "asserted_at": asserted_at,
                        "content_span_sha256": content_span_sha,
                        "locator_evidence_class": "hash_bound_locator_unverified_span",
                        "locator": locator,
                        "extraction_authority": {
                            "authority_kind": "human",
                            "authority_id": "person:oges.fixture.coder",
                        },
                    }
                ],
                "truth_selected": False,
                "event_state_effect": "none",
            }
        )
    )


_PROFILE_FIXTURE_OBJECTS: dict[str, dict[str, Any]] = {}


def _manifest_object_from_ref(profile: sem.SemanticProfile, object_id: str) -> dict[str, Any]:
    # The helper's profile parameter prevents accidental use before the fixture
    # has loaded and verified the profile. The object itself is fixture-local.
    assert profile.sha256
    return _PROFILE_FIXTURE_OBJECTS[object_id]


def _fixture(tmp_path: Path) -> tuple[Any, Path, Path, dict[str, Any]]:
    fixture, base_bundle_path, base_bundle = build_base_fixture(tmp_path)
    _install_semantic(fixture.root)
    profile_path = fixture.root / EXTENSION / "profile.json"
    profile = sem._load_profile(fixture.root, profile_path)
    event_one = _manifest_object(fixture, 1, "evt:oges.fixture.policy.001")
    event_two = _manifest_object(fixture, 2, "evt:oges.fixture.policy.002")
    evidence_one = _manifest_object(fixture, 1, "evd:oges.fixture.official.001")
    evidence_two = _manifest_object(fixture, 2, "evd:oges.fixture.correction.002")
    actor = _manifest_object(fixture, 1, "ent:country.synthetic_origin")
    commodity = _manifest_object(fixture, 1, "ent:commodity.synthetic_crude")
    _PROFILE_FIXTURE_OBJECTS.clear()
    _PROFILE_FIXTURE_OBJECTS[commodity["entity_id"]] = commodity
    claim_one = base_bundle["snapshots"][0]["claims"][0]
    claim_two = base_bundle["snapshots"][1]["claims"][1]
    proposition_one = _proposition(
        proposition_id="prp:oges.fixture.restriction.affirms",
        claim=claim_one,
        event=event_one,
        evidence=evidence_one,
        actor=actor,
        action="action:restricts",
        stance="affirms",
        known_at="2026-08-08T12:30:00Z",
        asserted_at="2026-08-08T09:00:00Z",
        profile=profile,
    )
    proposition_two = _proposition(
        proposition_id="prp:oges.fixture.restriction.denies",
        claim=claim_two,
        event=event_two,
        evidence=evidence_two,
        actor=actor,
        action="action:restricts",
        stance="denies",
        known_at="2026-08-09T12:45:00Z",
        asserted_at="2026-08-09T10:30:00Z",
        profile=profile,
    )
    proposition_three = _proposition(
        proposition_id="prp:oges.fixture.review.affirms",
        claim=claim_two,
        event=event_two,
        evidence=evidence_two,
        actor=actor,
        action="action:reviews_restriction",
        stance="affirms",
        known_at="2026-08-09T12:45:00Z",
        asserted_at="2026-08-09T10:30:00Z",
        profile=profile,
    )
    operation = {
        "object_type": "lineage_operation",
        "schema_version": "0.1.0",
        "operation_id": "lin:oges.fixture.event.supersede.001",
        "record_sha256": "0" * 64,
        "topology": "supersede",
        "predecessors": [_ref("event", event_one)],
        "successors": [_ref("event", event_two)],
        "known_at": "2026-08-09T13:00:00Z",
        "valid_from": "2026-08-08T09:00:00Z",
        "reason_code": "reason:official_correction",
        "basis_evidence_refs": [_ref("evidence_item", evidence_two)],
        "authorization": {
            "authority_kind": "human",
            "authority_id": "person:oges.fixture.coder",
            "authority_role": "lineage_coder",
            "authority_registry_sha256": profile.normative_sha256["semantic_authority_registry"],
            "signer_id": "signer:oges.fixture.semantic_lineage_coder",
            "statement_id": "statement:lineage_operation_authorization_v1",
            "payload_sha256": "0" * 64,
            "statement_sha256": "0" * 64,
            "trust_class": "synthetic_nonproduction_public_test_vector",
            "signature_ed25519_base64": base64.b64encode(b"0" * 64).decode("ascii"),
        },
        "unit_count_delta": {"event": 0, "episode": 0, "claim": 0},
        "product_closure": PRODUCT_UNAVAILABLE,
    }
    operation = _seal_operation(operation)
    release_one = json.loads(fixture.release_manifests[0].read_text())
    release_two = json.loads(fixture.release_manifests[1].read_text())
    first_propositions = [proposition_one]
    second_propositions = [proposition_one, proposition_two, proposition_three]
    base_binding = {
        "bundle_file_sha256": _sha(base_bundle_path),
        "bundle_record_sha256": base_bundle["record_sha256"],
        "profile_sha256": _sha(fixture.root / BASE_EXTENSION / "profile.json"),
    }
    snapshots = [
        {
            "sequence": 1,
            "release_id": release_one["release_id"],
            "release_manifest_record_sha256": release_one["record_sha256"],
            "knowledge_available_at": "2026-08-08T14:00:00Z",
            "claim_propositions": first_propositions,
            "competition_sets": sem.compile_competition_sets(first_propositions, profile),
            "lineage_operations": [],
            "archive_counts": {
                "claim_propositions": 1,
                "competition_sets": 1,
                "lineage_operations": 0,
            },
            "source_count_units": base_bundle["snapshots"][0]["count_units"],
        },
        {
            "sequence": 2,
            "release_id": release_two["release_id"],
            "release_manifest_record_sha256": release_two["record_sha256"],
            "knowledge_available_at": "2026-08-09T14:00:00Z",
            "claim_propositions": second_propositions,
            "competition_sets": sem.compile_competition_sets(
                second_propositions, profile, [operation]
            ),
            "lineage_operations": [operation],
            "archive_counts": {
                "claim_propositions": 3,
                "competition_sets": 1,
                "lineage_operations": 1,
            },
            "source_count_units": base_bundle["snapshots"][1]["count_units"],
        },
    ]
    first_receipt = _semantic_receipt(
        snapshots[0],
        sequence=1,
        available_at="2026-08-10T01:00:00Z",
        previous=None,
        profile=profile,
        base_binding=base_binding,
    )
    snapshots[0]["semantic_receipt"] = first_receipt
    snapshots[1]["semantic_receipt"] = _semantic_receipt(
        snapshots[1],
        sequence=2,
        available_at="2026-08-10T02:00:00Z",
        previous=first_receipt,
        profile=profile,
        base_binding=base_binding,
    )
    semantic_bundle = dict(
        sem.seal_record(
            {
                "object_type": "event_semantic_lineage_bundle",
                "schema_version": "0.1.0",
                "record_sha256": "0" * 64,
                "profile_sha256": profile.sha256,
                "trust_class": "synthetic_nonproduction",
                "production_trust": False,
                "base_event_ledger": base_binding,
                "product_compiler_boundary": PRODUCT_UNAVAILABLE,
                "snapshots": snapshots,
            }
        )
    )
    path = fixture.root / "event-semantic-lineage.json"
    _write_json(path, semantic_bundle)
    return fixture, base_bundle_path, path, semantic_bundle


def _append_authenticated_events(
    fixture: Any,
    base_bundle_path: Path,
    suffixes: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Add adjudicated root Events to release two and re-sign its chain."""

    source = _manifest_object(fixture, 1, "evt:oges.fixture.policy.001")
    events: list[dict[str, Any]] = []
    for suffix in suffixes:
        event = copy.deepcopy(source)
        event["event_id"] = f"evt:oges.fixture.split.{suffix}"
        event["first_known_at"] = "2026-08-09T11:00:00Z"
        event["last_verified_at"] = "2026-08-09T12:00:00Z"
        event["coding"].update(
            status="adjudicated",
            coder_ids=[
                "person:oges.fixture.coder",
                "person:oges.fixture.second_coder",
            ],
            adjudicator_ids=["person:oges.fixture.adjudicator"],
        )
        event["provenance"].update(
            created_at="2026-08-09T11:30:00Z",
            reviewed_by=[
                "person:oges.fixture.adjudicator",
                "person:oges.fixture.coder",
                "person:oges.fixture.second_coder",
            ],
            adjudication_status="adjudicated",
        )
        event["lifecycle"] = {
            "revision": 1,
            "state": "active",
            "supersedes_id": None,
            "superseded_by": None,
            "correction_id": None,
        }
        event = dict(canonical.seal_record(event))
        event_path = fixture.root / "canonical/objects" / f"{event['record_sha256']}.json"
        _write_json(event_path, event)
        events.append(event)

    manifest_path = fixture.release_manifests[1]
    manifest = json.loads(manifest_path.read_text())
    for event in events:
        event_path = fixture.root / "canonical/objects" / f"{event['record_sha256']}.json"
        manifest["objects"].append(
            {
                "object_type": "event",
                "object_id": event["event_id"],
                "path": event_path.relative_to(fixture.root).as_posix(),
                "file_sha256": _sha(event_path),
                "record_sha256": event["record_sha256"],
            }
        )
    manifest["objects"] = sorted(
        manifest["objects"], key=lambda row: (row["object_type"], row["object_id"])
    )
    manifest["counts"]["event"] += len(events)
    manifest = dict(canonical.seal_record(manifest))
    _write_json(manifest_path, manifest)
    (fixture.root / manifest["release_signature_path"]).write_bytes(
        fixture.release_private_key.sign(manifest_path.read_bytes())
    )

    receipt_path = fixture.receipts[1]
    receipt = json.loads(receipt_path.read_text())
    receipt["release_manifest_file_sha256"] = _sha(manifest_path)
    receipt["release_record_sha256"] = manifest["record_sha256"]
    receipt = dict(canonical.seal_record(receipt))
    _write_json(receipt_path, receipt)
    (fixture.root / receipt["signature_path"]).write_bytes(
        fixture.availability_private_key.sign(receipt_path.read_bytes())
    )

    ledger = json.loads(fixture.ledger.read_text())
    entry = ledger["entries"][1]
    entry["manifest_file_sha256"] = _sha(manifest_path)
    entry["manifest_record_sha256"] = manifest["record_sha256"]
    entry["receipt_file_sha256"] = _sha(receipt_path)
    ledger = dict(canonical.seal_record(ledger))
    _write_json(fixture.ledger, ledger)
    fixture.ledger_signature.write_bytes(
        fixture.ledger_private_key.sign(fixture.ledger.read_bytes())
    )

    base_bundle = json.loads(base_bundle_path.read_text())
    base_bundle["base_ledger"]["ledger_file_sha256"] = _sha(fixture.ledger)
    base_bundle["snapshots"][1]["release_manifest_record_sha256"] = manifest["record_sha256"]
    base_bundle["snapshots"][1]["count_units"]["canonical_geopolitical_events"] += len(events)
    base_bundle = dict(base.seal_record(base_bundle))
    _write_json(base_bundle_path, base_bundle)
    return events, manifest, base_bundle


def _rewrite(path: Path, bundle: dict[str, Any]) -> None:
    _write_json(path, sem.seal_record(bundle))


def _resign_semantic_receipts(fixture: Any, bundle: dict[str, Any]) -> None:
    """Authenticate a deliberately malformed inner snapshot for attack tests."""

    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    previous: dict[str, Any] | None = None
    for sequence, snapshot in enumerate(bundle["snapshots"], 1):
        available_at = snapshot["semantic_receipt"]["semantic_available_at"]
        snapshot["semantic_receipt"] = _semantic_receipt(
            snapshot,
            sequence=sequence,
            available_at=available_at,
            previous=previous,
            profile=profile,
            base_binding=bundle["base_event_ledger"],
        )
        previous = snapshot["semantic_receipt"]


def _refuses(
    fixture: Any,
    base_bundle_path: Path,
    semantic_path: Path,
    bundle: dict[str, Any],
    reason: str,
    *,
    resign_receipts: bool = True,
) -> None:
    if resign_receipts:
        _resign_semantic_receipts(fixture, bundle)
    _rewrite(semantic_path, bundle)
    with pytest.raises(sem.SemanticLineageError) as exc:
        sem.validate_bundle(
            semantic_path,
            base_bundle_path=base_bundle_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert exc.value.code == reason


def test_valid_sidecar_preserves_every_position_and_selects_no_truth(tmp_path: Path) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    validated = sem.validate_bundle(
        path,
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    competition = validated.document["snapshots"][1]["competition_sets"][0]
    assert competition["proposition_denominator"] == 3
    assert len(competition["positions"]) == 3
    assert [row["relation"] for row in competition["relations"]].count("registered_opposition") == 1
    assert [row["relation"] for row in competition["relations"]].count("divergence") == 2
    assert competition["truth_selected"] is False
    assert sem.summary(validated)["product_compiler_boundary"] == PRODUCT_UNAVAILABLE


def test_replay_keeps_knowledge_and_valid_time_and_object_counts_separate(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    kwargs = {
        "base_bundle_path": base_path,
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    before = sem.replay(path, "2026-08-10T01:30:00Z", "2026-08-08", **kwargs)
    after = sem.replay(path, "2026-08-10T02:30:00Z", "2026-08-08", **kwargs)
    assert [row["object_id"] for row in before["active_sets"]["event"]] == [
        "evt:oges.fixture.policy.001"
    ]
    assert [row["object_id"] for row in after["active_sets"]["event"]] == [
        "evt:oges.fixture.policy.002"
    ]
    assert before["active_counts"] == {"event": 1, "episode": 1, "claim": 1}
    assert after["active_counts"] == {"event": 1, "episode": 1, "claim": 1}
    assert before["source_count_units"] == after["source_count_units"]
    assert after["truth_selected"] is False
    assert after["proof"]["verification_method"] == "full_offline_recomputation_v1"


def test_semantic_receipt_cutoff_boundaries_select_exact_bound_base_release(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    kwargs = {
        "base_bundle_path": base_path,
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    with pytest.raises(sem.SemanticLineageError) as before:
        sem.replay(path, "2026-08-10T00:59:59Z", "2026-08-08", **kwargs)
    assert before.value.code == "semantic_knowledge_cutoff_before_first_receipt"
    at_first = sem.replay(path, "2026-08-10T01:00:00Z", "2026-08-08", **kwargs)
    between = sem.replay(path, "2026-08-10T01:59:59Z", "2026-08-08", **kwargs)
    at_second = sem.replay(path, "2026-08-10T02:00:00Z", "2026-08-08", **kwargs)
    after = sem.replay(path, "2026-08-11T00:00:00Z", "2026-08-08", **kwargs)
    assert at_first["selected_release"]["sequence"] == 1
    assert between["selected_release"]["sequence"] == 1
    assert at_second["selected_release"]["sequence"] == 2
    assert after["selected_release"]["sequence"] == 2
    assert at_first["selected_release"]["release_id"] == "rel:oges.fixture.2026-08-08"
    assert at_second["selected_release"]["release_id"] == "rel:oges.fixture.2026-08-09"


def test_event_active_sets_exclude_before_start_and_after_end(tmp_path: Path) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    kwargs = {
        "base_bundle_path": base_path,
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    before_start = sem.replay(path, "2026-08-10T01:30:00Z", "2026-08-07", **kwargs)
    assert before_start["active_sets"]["event"] == []
    assert before_start["active_counts"]["event"] == 0

    event = _manifest_object(fixture, 1, "evt:oges.fixture.policy.001")
    ended = copy.deepcopy(event)
    ended["ends_at"] = "2026-08-08T23:59:59Z"
    assert sem._effective(ended, sem._day("2026-08-09", "bad"), "event") is False


def test_split_successor_outside_event_window_is_not_active() -> None:
    predecessor = {
        "object_type": "event",
        "event_id": "evt:test.predecessor",
        "record_sha256": "a" * 64,
        "starts_at": "2026-08-08T00:00:00Z",
        "ends_at": None,
    }
    outside = {
        "object_type": "event",
        "event_id": "evt:test.outside",
        "record_sha256": "b" * 64,
        "starts_at": "2026-08-10T00:00:00Z",
        "ends_at": None,
    }
    inside = {
        "object_type": "event",
        "event_id": "evt:test.inside",
        "record_sha256": "c" * 64,
        "starts_at": "2026-08-09T00:00:00Z",
        "ends_at": None,
    }
    assert sem._effective(predecessor, sem._day("2026-08-09", "bad"), "event") is True
    assert sem._effective(outside, sem._day("2026-08-09", "bad"), "event") is False
    predecessor_ref = _ref("event", predecessor)
    inside_ref = _ref("event", inside)
    outside_ref = _ref("event", outside)
    active = {
        "event": {sem._object_key(predecessor_ref)},
        "episode": set(),
        "claim": set(),
    }
    sem._apply_operations(
        active,
        {
            sem._object_key(predecessor_ref): predecessor,
            sem._object_key(inside_ref): inside,
            sem._object_key(outside_ref): outside,
        },
        [
            {
                "operation_id": "lin:test.split.valid_window",
                "record_sha256": "d" * 64,
                "known_at": "2026-08-09T12:00:00Z",
                "valid_from": "2026-08-09T00:00:00Z",
                "predecessors": [predecessor_ref],
                "successors": [inside_ref, outside_ref],
            }
        ],
        sem._utc("2026-08-09T12:00:00Z", "bad"),
        sem._day("2026-08-09", "bad"),
    )
    assert active["event"] == {sem._object_key(inside_ref)}


def test_base_paths_are_not_document_authority_and_exact_bytes_are_bound(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    assert set(bundle["base_event_ledger"]) == {
        "bundle_file_sha256",
        "bundle_record_sha256",
        "profile_sha256",
    }
    bundle["base_event_ledger"]["bundle_file_sha256"] = "f" * 64
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "base_event_ledger_bundle_digest_mismatch",
    )


def test_historical_semantic_injection_breaks_signed_snapshot_receipt(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    injected = copy.deepcopy(bundle["snapshots"][0]["claim_propositions"][0])
    injected["proposition_id"] = "prp:oges.fixture.injected"
    injected["stance"] = "questions"
    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    predicate = profile.predicates[injected["predicate_id"]]
    position, competition = sem.proposition_hashes(
        injected["predicate_id"],
        injected["ordered_arguments"],
        injected["stance"],
        predicate,
        injected["event_ref"],
    )
    injected["position_sha256"] = position
    injected["competition_sha256"] = competition
    injected = dict(sem.seal_record(injected))
    snapshot = bundle["snapshots"][0]
    snapshot["claim_propositions"].append(injected)
    snapshot["competition_sets"] = sem.compile_competition_sets(
        snapshot["claim_propositions"], profile
    )
    snapshot["archive_counts"] = {
        "claim_propositions": 2,
        "competition_sets": 1,
        "lineage_operations": 0,
    }
    later = bundle["snapshots"][1]
    later["claim_propositions"].append(copy.deepcopy(injected))
    later["competition_sets"] = sem.compile_competition_sets(
        later["claim_propositions"], profile, later["lineage_operations"]
    )
    later["archive_counts"] = {
        "claim_propositions": 4,
        "competition_sets": 1,
        "lineage_operations": 1,
    }
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "semantic_receipt_snapshot_digest_mismatch",
        resign_receipts=False,
    )


def test_event_components_separate_unrelated_events_until_authorized_lineage(
    tmp_path: Path,
) -> None:
    _, _, _, bundle = _fixture(tmp_path)
    propositions = bundle["snapshots"][1]["claim_propositions"][:2]
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    fixture_root = Path(tmp_path) / "repo"
    profile = sem._load_profile(fixture_root, fixture_root / EXTENSION / "profile.json")
    immutable_hashes = [row["record_sha256"] for row in propositions]
    without_known_lineage = sem.compile_competition_sets(propositions, profile)
    with_known_lineage = sem.compile_competition_sets(propositions, profile, [operation])
    assert len(without_known_lineage) == 2
    assert all(not row["relations"] for row in without_known_lineage)
    assert len(with_known_lineage) == 1
    assert with_known_lineage[0]["relations"][0]["relation"] == "registered_opposition"
    assert with_known_lineage[0]["subject_event_component_status"] == "normalized_lineage_identity"
    assert [row["record_sha256"] for row in propositions] == immutable_hashes


def test_signed_split_keeps_siblings_and_ambiguous_predecessor_separate(
    tmp_path: Path,
) -> None:
    fixture, _, _, bundle = _fixture(tmp_path)
    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    predicate = profile.predicates["predicate:actor_action_object_v1"]
    prototype = bundle["snapshots"][0]["claim_propositions"][0]
    event_refs = [
        {
            "object_type": "event",
            "object_id": event_id,
            "record_sha256": character * 64,
        }
        for event_id, character in (
            ("evt:test.split.predecessor", "a"),
            ("evt:test.split.branch_one", "b"),
            ("evt:test.split.branch_two", "c"),
        )
    ]

    def proposition(index: int, stance: str) -> dict[str, Any]:
        row = copy.deepcopy(prototype)
        row["proposition_id"] = f"prp:test.split.{index}"
        row["event_ref"] = event_refs[index]
        row["stance"] = stance
        position, competition = sem.proposition_hashes(
            row["predicate_id"],
            row["ordered_arguments"],
            stance,
            predicate,
            row["event_ref"],
        )
        row["position_sha256"] = position
        row["competition_sha256"] = competition
        return dict(sem.seal_record(row))

    propositions = [
        proposition(0, "questions"),
        proposition(1, "affirms"),
        proposition(2, "denies"),
    ]
    operation = copy.deepcopy(bundle["snapshots"][1]["lineage_operations"][0])
    operation.update(
        operation_id="lin:test.split.signed",
        topology="split",
        predecessors=[event_refs[0]],
        successors=event_refs[1:],
        unit_count_delta={"event": 1, "episode": 0, "claim": 0},
    )
    operation["authorization"]["authority_role"] = "lineage_adjudicator"
    operation["authorization"]["authority_id"] = "person:oges.fixture.adjudicator"
    operation["authorization"]["signer_id"] = "signer:oges.fixture.semantic_lineage_adjudicator"
    operation = _seal_operation(operation)
    sem._validate_schema(
        operation,
        profile.validators["lineage_operation_schema"],
        "object_schema_invalid",
    )
    sem._validate_lineage_authorization(operation, profile, sem._utc(operation["known_at"], "bad"))

    competitions = sem.compile_competition_sets(propositions, profile, [operation])
    assert len(competitions) == 3
    assert not any(row["relations"] for row in competitions)
    assert {row["subject_event_component_status"] for row in competitions} == {
        "ambiguous_split_ancestor",
        "distinct_split_branch",
    }
    assert sorted(len(row["subject_event_refs"]) for row in competitions) == [1, 1, 1]


def test_signed_release_split_is_separate_end_to_end(tmp_path: Path) -> None:
    fixture, base_path, semantic_path, bundle = _fixture(tmp_path)
    branches, manifest, base_bundle = _append_authenticated_events(
        fixture, base_path, ("branch_one", "branch_two")
    )
    claim_prototype = base_bundle["snapshots"][1]["claims"][0]
    branch_claims: list[dict[str, Any]] = []
    for index, event in enumerate(branches, 1):
        claim = copy.deepcopy(claim_prototype)
        claim.update(
            claim_id=f"clm:oges.fixture.split.branch_{index}",
            revision=1,
            supersedes_claim_id=None,
            subject_event={
                "event_id": event["event_id"],
                "record_sha256": event["record_sha256"],
            },
            known_at="2026-08-09T12:30:00Z",
        )
        branch_claims.append(dict(base.seal_record(claim)))
    base_bundle["snapshots"][1]["claims"].extend(branch_claims)
    base_bundle["snapshots"][1]["counts"]["claims"] += len(branch_claims)
    base_bundle = dict(base.seal_record(base_bundle))
    _write_json(base_path, base_bundle)
    base.validate_bundle(
        base_path,
        root=fixture.root,
        profile_path=fixture.root / BASE_EXTENSION / "profile.json",
    )

    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    predicate = profile.predicates["predicate:actor_action_object_v1"]
    proposition_prototype = bundle["snapshots"][0]["claim_propositions"][0]
    branch_propositions: list[dict[str, Any]] = []
    for index, (event, claim, stance) in enumerate(
        zip(branches, branch_claims, ("affirms", "denies")), 1
    ):
        proposition = copy.deepcopy(proposition_prototype)
        proposition.update(
            proposition_id=f"prp:oges.fixture.split.branch_{index}",
            claim_ref=_ref("claim", claim),
            event_ref=_ref("event", event),
            stance=stance,
            known_at="2026-08-09T12:45:00Z",
        )
        position, competition = sem.proposition_hashes(
            proposition["predicate_id"],
            proposition["ordered_arguments"],
            proposition["stance"],
            predicate,
            proposition["event_ref"],
        )
        proposition["position_sha256"] = position
        proposition["competition_sha256"] = competition
        branch_propositions.append(dict(sem.seal_record(proposition)))

    event_two = _manifest_object(fixture, 2, "evt:oges.fixture.policy.002")
    split = copy.deepcopy(bundle["snapshots"][1]["lineage_operations"][0])
    split.update(
        operation_id="lin:oges.fixture.event.split.002",
        topology="split",
        predecessors=[_ref("event", event_two)],
        successors=[_ref("event", event) for event in branches],
        unit_count_delta={"event": 1, "episode": 0, "claim": 0},
    )
    split["authorization"].update(
        authority_id="person:oges.fixture.adjudicator",
        authority_role="lineage_adjudicator",
        signer_id="signer:oges.fixture.semantic_lineage_adjudicator",
    )
    split = _seal_operation(split)

    snapshot = bundle["snapshots"][1]
    immutable_pre_split_records = [
        row["record_sha256"]
        for row in snapshot["claim_propositions"]
        if row["event_ref"]["object_id"] == event_two["event_id"]
    ]
    snapshot["claim_propositions"].extend(branch_propositions)
    snapshot["lineage_operations"].append(split)
    snapshot["competition_sets"] = sem.compile_competition_sets(
        snapshot["claim_propositions"], profile, snapshot["lineage_operations"]
    )
    snapshot["archive_counts"] = {
        "claim_propositions": len(snapshot["claim_propositions"]),
        "competition_sets": len(snapshot["competition_sets"]),
        "lineage_operations": len(snapshot["lineage_operations"]),
    }
    snapshot["release_manifest_record_sha256"] = manifest["record_sha256"]
    snapshot["source_count_units"] = base_bundle["snapshots"][1]["count_units"]
    bundle["base_event_ledger"] = {
        "bundle_file_sha256": _sha(base_path),
        "bundle_record_sha256": base_bundle["record_sha256"],
        "profile_sha256": _sha(fixture.root / BASE_EXTENSION / "profile.json"),
    }
    _resign_semantic_receipts(fixture, bundle)
    _rewrite(semantic_path, bundle)

    validated = sem.validate_bundle(
        semantic_path,
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    competitions = validated.document["snapshots"][1]["competition_sets"]
    assert len(competitions) == 3
    branches_only = [
        row
        for row in competitions
        if row["subject_event_component_status"] == "distinct_split_branch"
    ]
    assert len(branches_only) == 2
    assert not any(row["relations"] for row in branches_only)
    ambiguous = next(
        row
        for row in competitions
        if row["subject_event_component_status"] == "ambiguous_split_ancestor"
    )
    assert event_two["event_id"] in {row["object_id"] for row in ambiguous["subject_event_refs"]}
    assert immutable_pre_split_records == [
        row["record_sha256"]
        for row in snapshot["claim_propositions"]
        if row["event_ref"]["object_id"] == event_two["event_id"]
    ]

    replay = sem.replay(
        semantic_path,
        "2026-08-10T02:30:00Z",
        "2026-08-08",
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    assert {row["object_id"] for row in replay["active_sets"]["event"]} == {
        event["event_id"] for event in branches
    }
    assert replay["active_counts"]["event"] == 2


def test_signed_release_merge_normalizes_predecessors_end_to_end(
    tmp_path: Path,
) -> None:
    fixture, base_path, semantic_path, bundle = _fixture(tmp_path)
    events, manifest, base_bundle = _append_authenticated_events(
        fixture,
        base_path,
        ("merge_left", "merge_right", "merge_successor"),
    )
    claim_prototype = base_bundle["snapshots"][1]["claims"][0]
    claims: list[dict[str, Any]] = []
    for index, event in enumerate(events, 1):
        claim = copy.deepcopy(claim_prototype)
        claim.update(
            claim_id=f"clm:oges.fixture.merge.{index}",
            revision=1,
            supersedes_claim_id=None,
            subject_event={
                "event_id": event["event_id"],
                "record_sha256": event["record_sha256"],
            },
            known_at="2026-08-09T12:30:00Z",
        )
        claims.append(dict(base.seal_record(claim)))
    base_bundle["snapshots"][1]["claims"].extend(claims)
    base_bundle["snapshots"][1]["counts"]["claims"] += len(claims)
    base_bundle = dict(base.seal_record(base_bundle))
    _write_json(base_path, base_bundle)
    base.validate_bundle(
        base_path,
        root=fixture.root,
        profile_path=fixture.root / BASE_EXTENSION / "profile.json",
    )

    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    predicate = profile.predicates["predicate:actor_action_object_v1"]
    prototype = bundle["snapshots"][0]["claim_propositions"][0]
    propositions: list[dict[str, Any]] = []
    for index, (event, claim, stance) in enumerate(
        zip(events, claims, ("affirms", "denies", "questions")), 1
    ):
        proposition = copy.deepcopy(prototype)
        proposition.update(
            proposition_id=f"prp:oges.fixture.merge.{index}",
            claim_ref=_ref("claim", claim),
            event_ref=_ref("event", event),
            stance=stance,
            known_at="2026-08-09T12:45:00Z",
        )
        position, competition = sem.proposition_hashes(
            proposition["predicate_id"],
            proposition["ordered_arguments"],
            proposition["stance"],
            predicate,
            proposition["event_ref"],
        )
        proposition["position_sha256"] = position
        proposition["competition_sha256"] = competition
        propositions.append(dict(sem.seal_record(proposition)))

    merge = copy.deepcopy(bundle["snapshots"][1]["lineage_operations"][0])
    merge.update(
        operation_id="lin:oges.fixture.event.merge.002",
        topology="merge",
        predecessors=[_ref("event", event) for event in events[:2]],
        successors=[_ref("event", events[2])],
        unit_count_delta={"event": -1, "episode": 0, "claim": 0},
    )
    merge["authorization"].update(
        authority_id="person:oges.fixture.adjudicator",
        authority_role="lineage_adjudicator",
        signer_id="signer:oges.fixture.semantic_lineage_adjudicator",
    )
    merge = _seal_operation(merge)

    snapshot = bundle["snapshots"][1]
    snapshot["claim_propositions"].extend(propositions)
    snapshot["lineage_operations"].append(merge)
    snapshot["competition_sets"] = sem.compile_competition_sets(
        snapshot["claim_propositions"], profile, snapshot["lineage_operations"]
    )
    snapshot["archive_counts"] = {
        "claim_propositions": len(snapshot["claim_propositions"]),
        "competition_sets": len(snapshot["competition_sets"]),
        "lineage_operations": len(snapshot["lineage_operations"]),
    }
    snapshot["release_manifest_record_sha256"] = manifest["record_sha256"]
    snapshot["source_count_units"] = base_bundle["snapshots"][1]["count_units"]
    bundle["base_event_ledger"] = {
        "bundle_file_sha256": _sha(base_path),
        "bundle_record_sha256": base_bundle["record_sha256"],
        "profile_sha256": _sha(fixture.root / BASE_EXTENSION / "profile.json"),
    }
    _resign_semantic_receipts(fixture, bundle)
    _rewrite(semantic_path, bundle)

    validated = sem.validate_bundle(
        semantic_path,
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    event_ids = {event["event_id"] for event in events}
    competition = next(
        row
        for row in validated.document["snapshots"][1]["competition_sets"]
        if {ref["object_id"] for ref in row["subject_event_refs"]} == event_ids
    )
    assert competition["subject_event_component_status"] == "normalized_lineage_identity"
    assert competition["proposition_denominator"] == 3
    assert [row["relation"] for row in competition["relations"]].count("registered_opposition") == 1
    assert [row["relation"] for row in competition["relations"]].count("divergence") == 2

    replay = sem.replay(
        semantic_path,
        "2026-08-10T02:30:00Z",
        "2026-08-08",
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    active_ids = {row["object_id"] for row in replay["active_sets"]["event"]}
    assert events[2]["event_id"] in active_ids
    assert not {event["event_id"] for event in events[:2]} & active_ids


def test_dependency_topological_replay_order_beats_reverse_lexical_ids() -> None:
    references = [
        {
            "object_type": "claim",
            "object_id": f"clm:test.chain.{name}",
            "record_sha256": character * 64,
        }
        for name, character in (("a", "a"), ("b", "b"), ("c", "c"))
    ]
    objects = {
        sem._object_key(reference): {
            "valid_from": "2026-08-08T00:00:00Z",
            "valid_to": None,
        }
        for reference in references
    }

    def operation(
        operation_id: str,
        predecessor: dict[str, str],
        successor: dict[str, str],
        known_at: str = "2026-08-09T12:00:00Z",
    ) -> dict[str, Any]:
        return {
            "operation_id": operation_id,
            "record_sha256": hashlib.sha256(operation_id.encode()).hexdigest(),
            "known_at": known_at,
            "valid_from": "2026-08-08T00:00:00Z",
            "predecessors": [predecessor],
            "successors": [successor],
        }

    operations = [
        operation("lin:test.z_producer", references[0], references[1]),
        operation("lin:test.a_consumer", references[1], references[2]),
    ]
    active = {"event": set(), "episode": set(), "claim": {sem._object_key(references[0])}}
    applied, pending = sem._apply_operations(
        active,
        objects,
        operations,
        sem._utc("2026-08-09T12:00:00Z", "bad"),
        sem._day("2026-08-08", "bad"),
    )
    assert [row["operation_id"] for row in applied] == [
        "lin:test.z_producer",
        "lin:test.a_consumer",
    ]
    assert pending == []
    assert active["claim"] == {sem._object_key(references[2])}

    unavailable = [
        operation(
            "lin:test.z_producer",
            references[0],
            references[1],
            "2026-08-10T12:00:00Z",
        ),
        operation("lin:test.a_consumer", references[1], references[2]),
    ]
    with pytest.raises(sem.SemanticLineageError) as exc:
        sem._apply_operations(
            {"event": set(), "episode": set(), "claim": {sem._object_key(references[0])}},
            objects,
            unavailable,
            sem._utc("2026-08-09T12:00:00Z", "bad"),
            sem._day("2026-08-08", "bad"),
        )
    assert exc.value.code == "lineage_consumer_producer_unavailable"


def test_signed_reverse_lexical_chain_replays_terminal_only_end_to_end(
    tmp_path: Path,
) -> None:
    fixture, base_path, semantic_path, bundle = _fixture(tmp_path)
    base_bundle = json.loads(base_path.read_text())
    base_snapshot = base_bundle["snapshots"][1]
    claim_one, claim_two = base_snapshot["claims"]
    claim_three = copy.deepcopy(claim_two)
    claim_three.update(
        claim_id="clm:oges.fixture.policy.003",
        revision=3,
        supersedes_claim_id=claim_two["claim_id"],
    )
    claim_three = dict(base.seal_record(claim_three))
    base_snapshot["claims"].append(claim_three)
    base_snapshot["counts"]["claims"] += 1
    correction = base_snapshot["correction_impacts"][0]
    correction["blast_radius"]["affected_objects"].append(_ref("claim", claim_three))
    correction["blast_radius"]["affected_objects"] = sorted(
        correction["blast_radius"]["affected_objects"],
        key=lambda row: (row["object_type"], row["object_id"], row["record_sha256"]),
    )
    correction["blast_radius"]["counts"]["objects"] += 1
    base_snapshot["correction_impacts"][0] = base.seal_record(correction)
    base_bundle = dict(base.seal_record(base_bundle))
    _write_json(base_path, base_bundle)
    base.validate_bundle(
        base_path,
        root=fixture.root,
        profile_path=fixture.root / BASE_EXTENSION / "profile.json",
    )

    prototype = bundle["snapshots"][1]["lineage_operations"][0]

    def claim_operation(
        operation_id: str,
        predecessor: dict[str, Any],
        successor: dict[str, Any],
    ) -> dict[str, Any]:
        operation = copy.deepcopy(prototype)
        operation.update(
            operation_id=operation_id,
            predecessors=[_ref("claim", predecessor)],
            successors=[_ref("claim", successor)],
            unit_count_delta={"event": 0, "episode": 0, "claim": 0},
        )
        return _seal_operation(operation)

    producer = claim_operation("lin:oges.fixture.z_producer", claim_one, claim_two)
    consumer = claim_operation("lin:oges.fixture.a_consumer", claim_two, claim_three)
    semantic_snapshot = bundle["snapshots"][1]
    semantic_snapshot["lineage_operations"].extend([producer, consumer])
    semantic_snapshot["archive_counts"]["lineage_operations"] = len(
        semantic_snapshot["lineage_operations"]
    )
    bundle["base_event_ledger"] = {
        "bundle_file_sha256": _sha(base_path),
        "bundle_record_sha256": base_bundle["record_sha256"],
        "profile_sha256": _sha(fixture.root / BASE_EXTENSION / "profile.json"),
    }
    _resign_semantic_receipts(fixture, bundle)
    _rewrite(semantic_path, bundle)

    replay = sem.replay(
        semantic_path,
        "2026-08-10T02:30:00Z",
        "2026-08-08",
        base_bundle_path=base_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    assert [row["object_id"] for row in replay["active_sets"]["claim"]] == [claim_three["claim_id"]]
    applied_ids = [row["operation_id"] for row in replay["applied_lineage_operation_refs"]]
    assert applied_ids.index(producer["operation_id"]) < applied_ids.index(consumer["operation_id"])


def test_full_recomputation_verifier_refuses_resealed_active_set(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    kwargs = {
        "base_bundle_path": base_path,
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    replay = sem.replay(path, "2026-08-10T02:30:00Z", "2026-08-08", **kwargs)
    verified = sem.verify_replay(replay, path, **kwargs)
    assert verified["status"] == "verified_full_semantic_replay_recomputation"
    replay["active_sets"]["event"] = []
    replay["active_counts"]["event"] = 0
    resealed = sem.seal_record(replay)
    with pytest.raises(sem.SemanticLineageError) as forged:
        sem.verify_replay(resealed, path, **kwargs)
    assert forged.value.code == "semantic_replay_recomputation_mismatch"


def test_publisher_metadata_cannot_be_relabelled_as_speaker(tmp_path: Path) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    proposition = bundle["snapshots"][0]["claim_propositions"][0]
    attribution = proposition["attributions"][0]
    attribution["locator"]["locator_id"] = "locator:evidence.publisher_entity_id_v1"
    attribution["locator"]["unit"] = "metadata_field"
    attribution["locator"]["start"] = None
    attribution["locator"]["end"] = None
    attribution["locator_evidence_class"] = "verified_evidence_metadata"
    attribution["locator"]["locator_sha256"] = sem.locator_sha256(
        attribution["evidence_ref"],
        attribution["content_span_sha256"],
        attribution["locator_evidence_class"],
        attribution["locator"],
    )
    sealed = dict(sem.seal_record(proposition))
    bundle["snapshots"][0]["claim_propositions"][0] = sealed
    bundle["snapshots"][1]["claim_propositions"][0] = copy.deepcopy(sealed)
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "attribution_locator_actor_kind_invalid",
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("fake_entity", "attribution_entity_record_missing"),
        ("missing_evidence", "attribution_evidence_record_missing"),
        ("future", "attribution_time_invalid"),
    ],
)
def test_fake_missing_and_future_attribution_refuse(
    tmp_path: Path, mutation: str, reason: str
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    proposition = bundle["snapshots"][0]["claim_propositions"][0]
    attribution = proposition["attributions"][0]
    if mutation == "fake_entity":
        attribution["actor_entity_ref"]["object_id"] = "ent:country.fake"
    elif mutation == "missing_evidence":
        attribution["evidence_ref"]["record_sha256"] = "f" * 64
    else:
        attribution["asserted_at"] = "2026-08-08T13:00:00Z"
    proposition["attributions"][0] = attribution
    sealed = dict(sem.seal_record(proposition))
    bundle["snapshots"][0]["claim_propositions"][0] = sealed
    bundle["snapshots"][1]["claim_propositions"][0] = copy.deepcopy(sealed)
    _refuses(fixture, base_path, path, bundle, reason)


def test_rights_are_evaluated_at_proposition_knowledge_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, base_path, path, _ = _fixture(tmp_path)
    original = base._rights_for_release

    def rights_by_release(root: Path, loaded: Any) -> dict[str, dict[str, Any]]:
        rights = copy.deepcopy(original(root, loaded))
        if loaded.entry["sequence"] == 1:
            rights["oges_fixture_source"]["reviewed_on"] = "2026-08-09"
        return rights

    monkeypatch.setattr(base, "_rights_for_release", rights_by_release)
    with pytest.raises(sem.SemanticLineageError) as exc:
        sem.validate_bundle(
            path,
            base_bundle_path=base_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert exc.value.code == "attribution_rights_ineligible"


@pytest.mark.parametrize(
    ("field", "value"),
    [("truth_selected", True), ("event_state_effect", "promotion")],
)
def test_model_proposition_cannot_promote_truth_or_event(
    tmp_path: Path, field: str, value: object
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    proposition = bundle["snapshots"][1]["claim_propositions"][1]
    proposition["attributions"][0]["extraction_authority"] = {
        "authority_kind": "model",
        "authority_id": "model:fake",
    }
    proposition[field] = value
    bundle["snapshots"][1]["claim_propositions"][1] = sem.seal_record(proposition)
    _refuses(fixture, base_path, path, bundle, "object_schema_invalid")


@pytest.mark.parametrize("mutation", ["collapse", "false_opposition", "reseal"])
def test_competition_sets_are_exact_recomputations(tmp_path: Path, mutation: str) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    competition = bundle["snapshots"][1]["competition_sets"][0]
    if mutation == "collapse":
        competition["positions"].pop()
        competition["proposition_denominator"] = 2
    elif mutation == "false_opposition":
        divergent = next(row for row in competition["relations"] if row["relation"] == "divergence")
        divergent["relation"] = "registered_opposition"
        divergent["opposition_rule_id"] = "opposition:affirm_deny_identical_arguments_v1"
    else:
        competition["truth_selected"] = False
        competition["positions"][0]["proposition_refs"][0]["record_sha256"] = "f" * 64
    bundle["snapshots"][1]["competition_sets"][0] = sem.seal_record(competition)
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "competition_sets_recomputation_mismatch",
    )


@pytest.mark.parametrize("field", ["aggregate_source_rows", "detected_salience_episodes"])
def test_non_event_count_units_cannot_substitute_for_events(tmp_path: Path, field: str) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    units = bundle["snapshots"][0]["source_count_units"]
    units[field] = 7
    units["canonical_geopolitical_events"] = units[field]
    _refuses(fixture, base_path, path, bundle, "source_count_units_mismatch")


def test_unsigned_agent_future_expired_and_unrelated_authorities_refuse(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path / "unsigned")
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    operation["authorization"]["signature_ed25519_base64"] = base64.b64encode(b"x" * 64).decode(
        "ascii"
    )
    bundle["snapshots"][1]["lineage_operations"][0] = sem.seal_record(operation)
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "lineage_authorization_signature_invalid",
    )

    fixture, base_path, path, bundle = _fixture(tmp_path / "agent")
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    operation["authorization"]["authority_kind"] = "agent"
    bundle["snapshots"][1]["lineage_operations"][0] = sem.seal_record(operation)
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "lineage_model_or_agent_authority_forbidden",
    )

    profile = sem._load_profile(fixture.root, fixture.root / EXTENSION / "profile.json")
    with pytest.raises(sem.SemanticLineageError) as future:
        sem._authority_at(
            profile,
            "human",
            "person:oges.fixture.coder",
            sem._utc("2026-08-07T23:59:59Z", "bad"),
            "lineage_coder",
            forbidden_code="forbidden",
            missing_code="missing",
            role_code="role",
            time_code="lineage_authority_time_invalid",
        )
    assert future.value.code == "lineage_authority_time_invalid"
    with pytest.raises(sem.SemanticLineageError) as expired:
        sem._authority_at(
            profile,
            "human",
            "person:oges.fixture.viewer",
            sem._utc("2026-08-09T00:00:00Z", "bad"),
            "evidence_viewer",
            forbidden_code="forbidden",
            missing_code="missing",
            role_code="role",
            time_code="lineage_authority_time_invalid",
        )
    assert expired.value.code == "lineage_authority_time_invalid"
    with pytest.raises(sem.SemanticLineageError) as unrelated:
        sem._authority_at(
            profile,
            "human",
            "person:oges.fixture.viewer",
            sem._utc("2026-08-08T12:00:00Z", "bad"),
            "lineage_coder",
            forbidden_code="forbidden",
            missing_code="missing",
            role_code="lineage_authority_role_invalid",
            time_code="time",
        )
    assert unrelated.value.code == "lineage_authority_role_invalid"


@pytest.mark.parametrize("topology", ["malformed", "many_to_many"])
def test_malformed_and_many_to_many_topologies_refuse(tmp_path: Path, topology: str) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    if topology == "malformed":
        operation["topology"] = "merge"
    else:
        operation["topology"] = "merge"
        operation["predecessors"].append(copy.deepcopy(operation["successors"][0]))
        operation["successors"].append(copy.deepcopy(operation["predecessors"][0]))
    bundle["snapshots"][1]["lineage_operations"][0] = sem.seal_record(operation)
    _refuses(fixture, base_path, path, bundle, "lineage_topology_invalid")


def test_cycles_and_double_consumption_refuse_without_caller_graphs() -> None:
    def operation(operation_id: str, predecessor: str, successor: str) -> dict[str, Any]:
        return {
            "operation_id": operation_id,
            "known_at": "2026-08-09T12:00:00Z",
            "valid_from": "2026-08-09T12:00:00Z",
            "predecessors": [
                {"object_type": "claim", "object_id": predecessor, "record_sha256": "a" * 64}
            ],
            "successors": [
                {"object_type": "claim", "object_id": successor, "record_sha256": "a" * 64}
            ],
        }

    with pytest.raises(sem.SemanticLineageError) as cycle:
        sem._validate_lineage_graph(
            [
                operation("lin:test.one", "clm:test.a", "clm:test.b"),
                operation("lin:test.two", "clm:test.b", "clm:test.a"),
            ]
        )
    assert cycle.value.code == "lineage_cycle"
    with pytest.raises(sem.SemanticLineageError) as consumed:
        sem._validate_lineage_graph(
            [
                operation("lin:test.one", "clm:test.a", "clm:test.b"),
                operation("lin:test.two", "clm:test.a", "clm:test.c"),
            ]
        )
    assert consumed.value.code == "lineage_predecessor_double_consumed"


def test_future_successor_and_wrong_unit_delta_refuse(tmp_path: Path) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path / "future")
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    operation["known_at"] = "2026-08-09T10:00:00Z"
    operation = _seal_operation(operation)
    bundle["snapshots"][1]["lineage_operations"][0] = operation
    _refuses(fixture, base_path, path, bundle, "lineage_successor_future")

    fixture, base_path, path, bundle = _fixture(tmp_path / "delta")
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    operation["unit_count_delta"] = {"event": 0, "episode": 1, "claim": 0}
    operation = _seal_operation(operation)
    bundle["snapshots"][1]["lineage_operations"][0] = operation
    _refuses(fixture, base_path, path, bundle, "lineage_unit_count_delta_mismatch")


def test_operation_history_is_append_only_and_not_visible_before_knowledge() -> None:
    operation = {"operation_id": "lin:test.one", "record_sha256": "a" * 64}
    with pytest.raises(sem.SemanticLineageError) as removed:
        sem._validate_cumulative_history(
            [
                {"claim_propositions": [], "lineage_operations": [operation]},
                {"claim_propositions": [], "lineage_operations": []},
            ]
        )
    assert removed.value.code == "lineage_archive_operation_removed"
    with pytest.raises(sem.SemanticLineageError) as rewritten:
        sem._validate_cumulative_history(
            [
                {"claim_propositions": [], "lineage_operations": [operation]},
                {
                    "claim_propositions": [],
                    "lineage_operations": [
                        {"operation_id": "lin:test.one", "record_sha256": "b" * 64}
                    ],
                },
            ]
        )
    assert rewritten.value.code == "lineage_archive_operation_rewritten"


def test_operation_cannot_be_visible_before_its_knowledge_time(tmp_path: Path) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    operation = bundle["snapshots"][1]["lineage_operations"][0]
    operation["known_at"] = "2026-08-09T14:00:01Z"
    bundle["snapshots"][1]["lineage_operations"][0] = _seal_operation(operation)
    _refuses(
        fixture,
        base_path,
        path,
        bundle,
        "lineage_snapshot_time_invalid",
    )


def test_product_compiler_boundary_has_no_dependency_graph_surface(
    tmp_path: Path,
) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    bundle["product_compiler_boundary"]["dependency_graph"] = []
    _refuses(fixture, base_path, path, bundle, "object_schema_invalid")


def test_synthetic_contract_cannot_claim_production_trust(tmp_path: Path) -> None:
    fixture, base_path, path, bundle = _fixture(tmp_path)
    bundle["production_trust"] = True
    _refuses(fixture, base_path, path, bundle, "object_schema_invalid")


def test_adversarial_matrix_and_normative_surfaces_ship_together() -> None:
    cases = json.loads((ROOT / EXTENSION / "adversarial-cases.json").read_text())
    assert {row["id"] for row in cases["cases"]} == COVERED_CASES
    assert not any(
        field in (ROOT / EXTENSION / "event-semantic-lineage-bundle.schema.json").read_text()
        for field in ("AnalyticalClause", "ProductManifest", "dependency_graph")
    )
