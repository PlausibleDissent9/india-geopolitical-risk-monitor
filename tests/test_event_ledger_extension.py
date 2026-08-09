from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from src import event_ledger_extension as ext
from src.knowledge_replay_fixture import (
    KnowledgeReplayFixture,
    build_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/event-ledger/0.1.0")
BASE_OGES_PROFILE_SHA256 = "640e4d5e7439ad884e75524dc6e517416031ab2266ab1b70733e4f8cd70e124d"

COVERED_CASES = {
    "evidence_verification_is_not_claim_truth",
    "claim_state_is_not_event_lifecycle",
    "ineligible_official_role",
    "official_claim_without_official_evidence",
    "same_independence_group_corroborators",
    "disputed_or_withdrawn_disruption_evidence",
    "model_high_confidence_cluster_promotion",
    "detector_episode_event_promotion",
    "unregistered_episode_formation",
    "model_claim_event_promotion",
    "unregistered_event_promotion",
    "wrong_predecessor_record_hash",
    "episode_correction_valid_time_mismatch",
    "correction_before_successor_known",
    "superseded_bytes_removed",
    "hidden_same_id_rewrite",
    "hidden_split",
    "hidden_merge",
    "blast_object_omitted",
    "blast_product_omitted",
    "blast_release_omitted",
    "correction_removed",
    "valid_time_collapsed_into_knowledge_time",
    "future_effective_revision_hides_predecessor",
    "future_event_lookahead",
    "future_evidence_lookahead",
    "future_rights_retroactive_authorization",
    "aggregate_rows_relabelled_unique_events",
    "synthetic_fixture_claims_production_trust",
    "base_oges_profile_substitution",
}


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _install_extension(root: Path) -> None:
    shutil.copytree(ROOT / EXTENSION, root / EXTENSION, dirs_exist_ok=True)
    (root / "standard/oges/0.1.0").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "standard/oges/0.1.0/profile.json",
        root / "standard/oges/0.1.0/profile.json",
    )
    shutil.copy2(
        ROOT / "governance/event_ledger_contract.json",
        root / "governance/event_ledger_contract.json",
    )
    shutil.copy2(
        ROOT / "src/event_ledger_extension.py",
        root / "src/event_ledger_extension.py",
    )


def _manifest_object(fixture: KnowledgeReplayFixture, sequence: int, object_id: str) -> dict[str, Any]:
    manifest = json.loads(fixture.release_manifests[sequence - 1].read_text(encoding="utf-8"))
    entry = next(row for row in manifest["objects"] if row["object_id"] == object_id)
    return json.loads((fixture.root / entry["path"]).read_text(encoding="utf-8"))


def _ref(object_type: str, object_id: str, record_sha256: str) -> dict[str, str]:
    return {
        "object_type": object_type,
        "object_id": object_id,
        "record_sha256": record_sha256,
    }


def _event_ref(event: dict[str, Any]) -> dict[str, str]:
    return {"event_id": event["event_id"], "record_sha256": event["record_sha256"]}


def _fixture(
    tmp_path: Path,
    *,
    first_claim_state: str = "official_confirmation",
    first_evidence_role: str = "official_confirmation",
) -> tuple[KnowledgeReplayFixture, Path, dict[str, Any]]:
    fixture = build_fixture(tmp_path / "repo")
    _install_extension(fixture.root)
    event_one = _manifest_object(fixture, 1, "evt:oges.fixture.policy.001")
    event_two = _manifest_object(fixture, 2, "evt:oges.fixture.policy.002")
    evidence_one = _manifest_object(fixture, 1, "evd:oges.fixture.official.001")
    evidence_two = _manifest_object(fixture, 2, "evd:oges.fixture.correction.002")

    claim_one = ext.seal_record(
        {
            "object_type": "claim",
            "schema_version": "0.1.0",
            "claim_id": "clm:oges.fixture.policy.001",
            "record_sha256": "0" * 64,
            "revision": 1,
            "supersedes_claim_id": None,
            "assertion_state": first_claim_state,
            "subject_event": _event_ref(event_one),
            "valid_from": "2026-08-08T09:00:00Z",
            "valid_to": None,
            "known_at": "2026-08-08T12:30:00Z",
            "created_by": {
                "kind": "human",
                "authority_id": "person:oges.fixture.coder",
            },
            "evidence_links": [
                {
                    "evidence_id": evidence_one["evidence_id"],
                    "evidence_record_sha256": evidence_one["record_sha256"],
                    "role": first_evidence_role,
                    "asserted_at": "2026-08-08T09:00:00Z",
                }
            ],
            "event_state_effect": {
                "kind": "none",
                "from_event": None,
                "to_event": None,
                "target_record_status": None,
                "authority_kind": None,
                "authority_id": None,
            },
        }
    )
    claim_two = ext.seal_record(
        {
            "object_type": "claim",
            "schema_version": "0.1.0",
            "claim_id": "clm:oges.fixture.policy.002",
            "record_sha256": "0" * 64,
            "revision": 2,
            "supersedes_claim_id": claim_one["claim_id"],
            "assertion_state": "disputed",
            "subject_event": _event_ref(event_two),
            "valid_from": "2026-08-08T09:00:00Z",
            "valid_to": None,
            "known_at": "2026-08-09T12:30:00Z",
            "created_by": {
                "kind": "human",
                "authority_id": "person:oges.fixture.coder",
            },
            "evidence_links": [
                {
                    "evidence_id": evidence_two["evidence_id"],
                    "evidence_record_sha256": evidence_two["record_sha256"],
                    "role": "correction",
                    "asserted_at": "2026-08-09T10:30:00Z",
                }
            ],
            "event_state_effect": {
                "kind": "promotion",
                "from_event": _event_ref(event_one),
                "to_event": _event_ref(event_two),
                "target_record_status": "disputed",
                "authority_kind": "named_human_authority",
                "authority_id": "person:oges.fixture.coder",
            },
        }
    )
    episode = ext.seal_record(
        {
            "object_type": "episode",
            "schema_version": "0.1.0",
            "episode_id": "epi:oges.fixture.salience.001",
            "record_sha256": "0" * 64,
            "revision": 1,
            "supersedes_episode_id": None,
            "episode_kind": "detector_salience_window",
            "episode_state": "clustering_proposal",
            "valid_from": "2026-08-08T00:00:00Z",
            "valid_to": "2026-08-10T23:59:59Z",
            "known_at": "2026-08-08T12:45:00Z",
            "formation": {
                "authority_kind": "model_clustering_proposal",
                "authority_id": "model:oges.fixture.cluster",
                "implementation_sha256": None,
                "proposal_confidence": 1.0,
            },
            "claim_members": [
                _ref("claim", claim_one["claim_id"], claim_one["record_sha256"])
            ],
            "event_links": [
                {
                    **_event_ref(event_one),
                    "role": "candidate_member",
                }
            ],
        }
    )
    affected = sorted(
        [
            _ref("event", event_one["event_id"], event_one["record_sha256"]),
            _ref("event", event_two["event_id"], event_two["record_sha256"]),
            _ref("claim", claim_one["claim_id"], claim_one["record_sha256"]),
            _ref("claim", claim_two["claim_id"], claim_two["record_sha256"]),
            _ref("episode", episode["episode_id"], episode["record_sha256"]),
        ],
        key=lambda row: (row["object_type"], row["object_id"], row["record_sha256"]),
    )
    correction = ext.seal_record(
        {
            "object_type": "correction_impact",
            "schema_version": "0.1.0",
            "correction_id": "cor:oges.fixture.policy.001",
            "record_sha256": "0" * 64,
            "known_at": "2026-08-09T13:00:00Z",
            "valid_from": "2026-08-08T09:00:00Z",
            "reason_code": "official_correction",
            "transitions": [
                {
                    "change_kind": "supersede",
                    "predecessor": _ref(
                        "event", event_one["event_id"], event_one["record_sha256"]
                    ),
                    "successor": _ref(
                        "event", event_two["event_id"], event_two["record_sha256"]
                    ),
                },
                {
                    "change_kind": "supersede",
                    "predecessor": _ref(
                        "claim", claim_one["claim_id"], claim_one["record_sha256"]
                    ),
                    "successor": _ref(
                        "claim", claim_two["claim_id"], claim_two["record_sha256"]
                    ),
                },
            ],
            "blast_radius": {
                "affected_objects": affected,
                "affected_product_ids": [
                    "product:global_event_episode_ledger",
                    "product:knowledge_replay",
                ],
                "affected_release_ids": [
                    "rel:oges.fixture.2026-08-08",
                    "rel:oges.fixture.2026-08-09",
                ],
                "counts": {"objects": 5, "products": 2, "releases": 2},
            },
        }
    )
    release_one = json.loads(fixture.release_manifests[0].read_text(encoding="utf-8"))
    release_two = json.loads(fixture.release_manifests[1].read_text(encoding="utf-8"))
    units = {
        "aggregate_source_rows": None,
        "deduplicated_source_events": None,
        "canonical_geopolitical_events": 1,
        "detected_salience_episodes": 1,
    }
    bundle = ext.seal_record(
        {
            "object_type": "event_ledger_extension_bundle",
            "schema_version": "0.1.0",
            "record_sha256": "0" * 64,
            "profile_sha256": _sha(fixture.root / EXTENSION / "profile.json"),
            "trust_class": "synthetic_nonproduction",
            "production_trust": False,
            "base_ledger": {
                "root_path": ".",
                "ledger_path": "knowledge/ledger.json",
                "ledger_file_sha256": _sha(fixture.ledger),
                "replay_registry_path": "governance/knowledge_replay_registry.json",
                "replay_registry_sha256": _sha(
                    fixture.root / "governance/knowledge_replay_registry.json"
                ),
                "knowledge_signers_path": "governance/knowledge_replay_signers.json",
            },
            "snapshots": [
                {
                    "sequence": 1,
                    "release_id": release_one["release_id"],
                    "release_manifest_record_sha256": release_one["record_sha256"],
                    "knowledge_available_at": "2026-08-08T14:00:00Z",
                    "claims": [claim_one],
                    "episodes": [episode],
                    "correction_impacts": [],
                    "counts": {"claims": 1, "episodes": 1, "correction_impacts": 0},
                    "count_units": units,
                },
                {
                    "sequence": 2,
                    "release_id": release_two["release_id"],
                    "release_manifest_record_sha256": release_two["record_sha256"],
                    "knowledge_available_at": "2026-08-09T14:00:00Z",
                    "claims": [claim_one, claim_two],
                    "episodes": [episode],
                    "correction_impacts": [correction],
                    "counts": {"claims": 2, "episodes": 1, "correction_impacts": 1},
                    "count_units": units,
                },
            ],
        }
    )
    bundle_path = fixture.root / "event-ledger-extension.json"
    _write_json(bundle_path, bundle)
    return fixture, bundle_path, bundle


def _rewrite_bundle(path: Path, bundle: dict[str, Any]) -> None:
    _write_json(path, ext.seal_record(bundle))


def _refuses(
    fixture: KnowledgeReplayFixture,
    bundle_path: Path,
    bundle: dict[str, Any],
    reason: str,
) -> None:
    _rewrite_bundle(bundle_path, bundle)
    with pytest.raises(ext.EventLedgerExtensionError) as exc:
        ext.validate_bundle(
            bundle_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert exc.value.code == reason


def test_valid_extension_is_a_nonproduction_sidecar_over_signed_replay(tmp_path: Path) -> None:
    fixture, bundle_path, _ = _fixture(tmp_path)
    validated = ext.validate_bundle(
        bundle_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    report = ext.summary(validated)
    assert validated.bundle_sha256 == hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    replay_from_loaded = ext.replay_validated(
        validated, "2026-08-08T14:30:00Z", "2026-08-08"
    )
    replay_from_path = ext.replay(
        bundle_path,
        "2026-08-08T14:30:00Z",
        "2026-08-08",
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    assert replay_from_loaded == replay_from_path
    assert report["status"] == "conformant_synthetic_event_ledger_extension"
    assert report["base_ledger_id"] == "kld:oges.fixture.2026-08-09"
    assert report["production_trust"] is False
    assert report["source_rights_authority"] is False


def test_normative_schema_hash_and_parse_use_one_captured_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    bundle["injected"] = True
    _rewrite_bundle(bundle_path, bundle)
    target = fixture.root / EXTENSION / "event-ledger-extension.schema.json"
    version_a = target.read_bytes()
    weakened = json.loads(version_a)
    weakened["additionalProperties"] = True
    version_b = (
        json.dumps(weakened, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    original_read = Path.read_bytes
    original_parse = ext._parse_json_bytes
    state = {"swapped": False}

    def read_then_swap(path: Path) -> bytes:
        payload = original_read(path)
        if path.resolve() == target.resolve() and not state["swapped"]:
            target.write_bytes(version_b)
            state["swapped"] = True
        return payload

    def parse_then_restore(raw: bytes, code: str) -> dict[str, Any]:
        parsed = original_parse(raw, code)
        if state["swapped"] and raw == version_a:
            target.write_bytes(version_a)
        return parsed

    monkeypatch.setattr(Path, "read_bytes", read_then_swap)
    monkeypatch.setattr(ext, "_parse_json_bytes", parse_then_restore)
    with pytest.raises(ext.EventLedgerExtensionError) as exc:
        ext.validate_bundle(
            bundle_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert state["swapped"] is True
    assert exc.value.code == "object_schema_invalid"


def test_evidence_verification_never_promotes_claim_truth(tmp_path: Path) -> None:
    fixture, bundle_path, _ = _fixture(
        tmp_path,
        first_claim_state="allegation",
        first_evidence_role="allegation",
    )
    replay = ext.replay(
        bundle_path,
        "2026-08-08T14:30:00Z",
        "2026-08-08",
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    assert replay["claims"][0]["assertion_state"] == "allegation"
    assert replay["events"][0]["record_status"] == "confirmed"


def test_claim_event_and_episode_states_remain_separate_axes(tmp_path: Path) -> None:
    fixture, bundle_path, _ = _fixture(tmp_path)
    replay = ext.replay(
        bundle_path,
        "2026-08-08T14:30:00Z",
        "2026-08-08",
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    assert replay["claims"][0]["assertion_state"] == "official_confirmation"
    assert replay["events"][0]["lifecycle_state"] == "active"
    assert replay["events"][0]["record_status"] == "confirmed"
    assert replay["episodes"][0]["episode_state"] == "clustering_proposal"
    assert replay["episodes"][0]["event_effect"] == "relationship_only_never_promotion"


def test_official_links_are_role_eligible_and_corroborators_are_independent(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    validated = ext.validate_bundle(
        bundle_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    claim = copy.deepcopy(bundle["snapshots"][0]["claims"][0])
    base_objects, _ = ext._base_catalogs(validated.ledger, validated.ledger_root)
    rights = ext._rights_for_release(validated.ledger_root, validated.ledger.releases[0])
    official_key = next(key for key in base_objects if key[0] == "evidence_item")
    ineligible = dict(base_objects[official_key])
    ineligible["evidence_type"] = "news_article"
    with pytest.raises(ext.EventLedgerExtensionError) as official:
        ext._validate_evidence_roles(claim, {official_key: ineligible}, rights)
    assert official.value.code == "claim_official_confirmation_ineligible"

    mirror_one_key = ("evidence_item", "evd:oges.fixture.mirror.002", "e" * 64)
    mirror_two_key = ("evidence_item", "evd:oges.fixture.mirror.003", "f" * 64)
    mirror_one = dict(base_objects[official_key])
    mirror_one["evidence_id"] = mirror_one_key[1]
    mirror_one["record_sha256"] = mirror_one_key[2]
    mirror_one["source_id"] = "oges_fixture_mirror_one"
    mirror_two = dict(base_objects[official_key])
    mirror_two["evidence_id"] = mirror_two_key[1]
    mirror_two["record_sha256"] = mirror_two_key[2]
    mirror_two["source_id"] = "oges_fixture_mirror_two"
    claim["evidence_links"] = [
        {
            "evidence_id": mirror_one_key[1],
            "evidence_record_sha256": mirror_one_key[2],
            "role": "corroborates",
            "asserted_at": "2026-08-08T09:00:00Z",
        },
        {
            "evidence_id": mirror_two_key[1],
            "evidence_record_sha256": mirror_two_key[2],
            "role": "corroborates",
            "asserted_at": "2026-08-08T09:00:00Z",
        },
    ]
    rights = copy.deepcopy(rights)
    rights["oges_fixture_mirror_one"] = dict(rights["oges_fixture_source"])
    rights["oges_fixture_mirror_two"] = dict(rights["oges_fixture_source"])
    evidence = {
        official_key: base_objects[official_key],
        mirror_one_key: mirror_one,
        mirror_two_key: mirror_two,
    }
    with pytest.raises(ext.EventLedgerExtensionError) as same_group:
        ext._validate_evidence_roles(claim, evidence, rights)
    assert same_group.value.code == "claim_corroborator_independence_duplicate"
    rights["oges_fixture_mirror_two"]["independence_group"] = (
        "independent_fixture_group"
    )
    with pytest.raises(ext.EventLedgerExtensionError) as no_official:
        ext._validate_evidence_roles(claim, evidence, rights)
    assert no_official.value.code == "claim_official_confirmation_insufficient"
    claim["evidence_links"].append(
        {
            "evidence_id": official_key[1],
            "evidence_record_sha256": official_key[2],
            "role": "official_confirmation",
            "asserted_at": "2026-08-08T09:00:00Z",
        }
    )
    ext._validate_evidence_roles(claim, evidence, rights)


@pytest.mark.parametrize("status", ["disputed", "withdrawn"])
def test_observed_disruption_requires_positive_evidence_and_source_role(
    tmp_path: Path, status: str
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    validated = ext.validate_bundle(
        bundle_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    base_objects, _ = ext._base_catalogs(validated.ledger, validated.ledger_root)
    rights = ext._rights_for_release(validated.ledger_root, validated.ledger.releases[0])
    evidence_key = next(key for key in base_objects if key[0] == "evidence_item")
    claim = copy.deepcopy(bundle["snapshots"][0]["claims"][0])
    claim["assertion_state"] = "observed_disruption"
    claim["evidence_links"][0]["role"] = "observed_disruption"
    evidence = dict(base_objects[evidence_key])
    evidence["verification_status"] = status
    with pytest.raises(ext.EventLedgerExtensionError) as nonpositive:
        ext._validate_evidence_roles(claim, {evidence_key: evidence}, rights)
    assert nonpositive.value.code == "claim_observed_disruption_ineligible"

    evidence["verification_status"] = "official_record"
    ineligible_rights = copy.deepcopy(rights)
    ineligible_rights["oges_fixture_source"]["role"] = "news_attention_corpus"
    ineligible_rights["oges_fixture_source"]["authority_class"] = "aggregator"
    with pytest.raises(ext.EventLedgerExtensionError) as source_role:
        ext._validate_evidence_roles(
            claim, {evidence_key: evidence}, ineligible_rights
        )
    assert source_role.value.code == "claim_observed_disruption_ineligible"
    ext._validate_evidence_roles(claim, {evidence_key: evidence}, rights)


def test_model_clustering_is_proposal_only_even_at_full_confidence(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    assert bundle["snapshots"][0]["episodes"][0]["formation"]["proposal_confidence"] == 1.0
    ext.validate_bundle(
        bundle_path,
        root=fixture.root,
        profile_path=fixture.root / EXTENSION / "profile.json",
    )
    for snapshot in bundle["snapshots"]:
        episode = snapshot["episodes"][0]
        episode["episode_state"] = "detector_window_closed"
        snapshot["episodes"][0] = ext.seal_record(episode)
    _refuses(fixture, bundle_path, bundle, "episode_model_proposal_only")


def test_episode_schema_has_no_event_promotion_surface(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    episode = bundle["snapshots"][0]["episodes"][0]
    episode["event_state_effect"] = "confirmed"
    sealed = ext.seal_record(episode)
    bundle["snapshots"][0]["episodes"][0] = sealed
    bundle["snapshots"][1]["episodes"][0] = copy.deepcopy(sealed)
    _refuses(fixture, bundle_path, bundle, "object_schema_invalid")


@pytest.mark.parametrize(
    ("authority_kind", "implementation_sha256"),
    [
        ("registered_deterministic_method", "f" * 64),
        ("named_human_authority", None),
    ],
)
def test_nonmodel_episode_formation_fails_closed_without_pinned_registry(
    tmp_path: Path, authority_kind: str, implementation_sha256: str | None
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    episode = bundle["snapshots"][0]["episodes"][0]
    episode["formation"] = {
        "authority_kind": authority_kind,
        "authority_id": "authority:unregistered.but.plausible",
        "implementation_sha256": implementation_sha256,
        "proposal_confidence": None,
    }
    sealed = ext.seal_record(episode)
    bundle["snapshots"][0]["episodes"][0] = sealed
    bundle["snapshots"][1]["episodes"][0] = copy.deepcopy(sealed)
    _refuses(
        fixture,
        bundle_path,
        bundle,
        "episode_formation_authority_unregistered",
    )


def test_models_and_unregistered_authorities_cannot_promote_event_state(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path / "model")
    claim = bundle["snapshots"][1]["claims"][1]
    claim["created_by"]["kind"] = "model"
    claim["assertion_state"] = "coded_inference"
    claim["evidence_links"][0]["role"] = "supports_inference"
    bundle["snapshots"][1]["claims"][1] = ext.seal_record(claim)
    _refuses(fixture, bundle_path, bundle, "claim_model_promotion_forbidden")

    fixture, bundle_path, bundle = _fixture(tmp_path / "authority")
    claim = bundle["snapshots"][1]["claims"][1]
    claim["event_state_effect"]["authority_kind"] = "registered_evidence_rule"
    claim["event_state_effect"]["authority_id"] = "rule:unregistered.plausible"
    bundle["snapshots"][1]["claims"][1] = ext.seal_record(claim)
    _refuses(fixture, bundle_path, bundle, "claim_promotion_authority_invalid")


def test_snapshot_cannot_reference_future_base_event_or_evidence(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path / "event")
    future_event = bundle["snapshots"][1]["correction_impacts"][0]["transitions"][0][
        "successor"
    ]
    claim = copy.deepcopy(bundle["snapshots"][0]["claims"][0])
    claim["subject_event"] = {
        "event_id": future_event["object_id"],
        "record_sha256": future_event["record_sha256"],
    }
    sealed = ext.seal_record(claim)
    bundle["snapshots"][0]["claims"][0] = sealed
    bundle["snapshots"][1]["claims"][0] = copy.deepcopy(sealed)
    _refuses(fixture, bundle_path, bundle, "claim_subject_event_record_missing")

    fixture, bundle_path, bundle = _fixture(tmp_path / "evidence")
    future_link = copy.deepcopy(bundle["snapshots"][1]["claims"][1]["evidence_links"][0])
    future_link["role"] = "official_confirmation"
    claim = copy.deepcopy(bundle["snapshots"][0]["claims"][0])
    claim["evidence_links"] = [future_link]
    sealed = ext.seal_record(claim)
    bundle["snapshots"][0]["claims"][0] = sealed
    bundle["snapshots"][1]["claims"][0] = copy.deepcopy(sealed)
    _refuses(fixture, bundle_path, bundle, "claim_evidence_record_missing")


def test_future_rights_change_cannot_authorize_earlier_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture, bundle_path, _ = _fixture(tmp_path)
    original = ext._rights_for_release

    def rights_by_release(
        root: Path, loaded: Any
    ) -> dict[str, dict[str, Any]]:
        rights = copy.deepcopy(original(root, loaded))
        source = rights["oges_fixture_source"]
        if loaded.entry["sequence"] == 1:
            source["authority_class"] = "aggregator"
        return rights

    monkeypatch.setattr(ext, "_rights_for_release", rights_by_release)
    with pytest.raises(ext.EventLedgerExtensionError) as retroactive:
        ext.validate_bundle(
            bundle_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert retroactive.value.code == "claim_official_confirmation_ineligible"


def test_correction_binds_exact_predecessor_hash_and_preserves_old_bytes(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path / "hash")
    correction = bundle["snapshots"][1]["correction_impacts"][0]
    correction["transitions"][0]["predecessor"]["record_sha256"] = "f" * 64
    bundle["snapshots"][1]["correction_impacts"][0] = ext.seal_record(correction)
    _refuses(fixture, bundle_path, bundle, "correction_transition_record_missing")

    fixture, bundle_path, bundle = _fixture(tmp_path / "removed")
    bundle["snapshots"][1]["claims"] = [bundle["snapshots"][1]["claims"][1]]
    _refuses(fixture, bundle_path, bundle, "extension_archive_object_removed")


def test_episode_correction_uses_same_valid_time_as_successor(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    snapshot = bundle["snapshots"][1]
    predecessor = snapshot["episodes"][0]
    successor = copy.deepcopy(predecessor)
    successor["episode_id"] = "epi:oges.fixture.salience.002"
    successor["revision"] = 2
    successor["supersedes_episode_id"] = predecessor["episode_id"]
    successor["valid_from"] = "2026-08-08T01:00:00Z"
    successor["known_at"] = "2026-08-09T12:45:00Z"
    sealed_successor = ext.seal_record(successor)
    snapshot["episodes"].append(sealed_successor)
    snapshot["counts"]["episodes"] = 2
    correction = snapshot["correction_impacts"][0]
    correction["transitions"].append(
        {
            "change_kind": "supersede",
            "predecessor": _ref(
                "episode", predecessor["episode_id"], predecessor["record_sha256"]
            ),
            "successor": _ref(
                "episode",
                sealed_successor["episode_id"],
                sealed_successor["record_sha256"],
            ),
        }
    )
    snapshot["correction_impacts"][0] = ext.seal_record(correction)
    _refuses(fixture, bundle_path, bundle, "correction_valid_time_mismatch")


def test_correction_cannot_precede_successor_knowledge_time(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    correction = bundle["snapshots"][1]["correction_impacts"][0]
    correction["known_at"] = "2026-08-09T12:00:00Z"
    bundle["snapshots"][1]["correction_impacts"][0] = ext.seal_record(correction)
    _refuses(fixture, bundle_path, bundle, "correction_before_successor_known")


def test_same_id_rewrite_split_merge_and_correction_removal_are_refused(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path / "rewrite")
    old_claim = bundle["snapshots"][1]["claims"][0]
    old_claim["assertion_state"] = "coded_inference"
    bundle["snapshots"][1]["claims"][0] = ext.seal_record(old_claim)
    _refuses(fixture, bundle_path, bundle, "extension_object_id_rewritten")

    fixture, bundle_path, bundle = _fixture(tmp_path / "split")
    split = copy.deepcopy(bundle["snapshots"][1]["claims"][1])
    split["claim_id"] = "clm:oges.fixture.policy.003"
    split["event_state_effect"] = {
        "kind": "none",
        "from_event": None,
        "to_event": None,
        "target_record_status": None,
        "authority_kind": None,
        "authority_id": None,
    }
    bundle["snapshots"][1]["claims"].append(ext.seal_record(split))
    _refuses(fixture, bundle_path, bundle, "extension_revision_lineage_fork")

    fixture, bundle_path, bundle = _fixture(tmp_path / "merge")
    merged = bundle["snapshots"][1]["claims"][1]
    merged["supersedes_claim_id"] = [
        "clm:oges.fixture.policy.001",
        "clm:oges.fixture.other.001",
    ]
    bundle["snapshots"][1]["claims"][1] = ext.seal_record(merged)
    _refuses(fixture, bundle_path, bundle, "object_schema_invalid")

    _, _, valid_bundle = _fixture(tmp_path / "correction")
    correction = valid_bundle["snapshots"][1]["correction_impacts"][0]
    snapshots = [
        {"claims": [], "episodes": [], "correction_impacts": [correction]},
        {"claims": [], "episodes": [], "correction_impacts": []},
    ]
    with pytest.raises(ext.EventLedgerExtensionError) as removed:
        ext._validate_cumulative_history(snapshots)
    assert removed.value.code == "extension_archive_correction_removed"


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("affected_objects", lambda rows: rows.pop()),
        ("affected_product_ids", lambda rows: rows.pop()),
        ("affected_release_ids", lambda rows: rows.pop()),
    ],
)
def test_correction_blast_radius_is_recomputed_not_trusted(
    tmp_path: Path, field: str, mutate: Any
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    correction = bundle["snapshots"][1]["correction_impacts"][0]
    mutate(correction["blast_radius"][field])
    count_field = {
        "affected_objects": "objects",
        "affected_product_ids": "products",
        "affected_release_ids": "releases",
    }[field]
    correction["blast_radius"]["counts"][count_field] -= 1
    bundle["snapshots"][1]["correction_impacts"][0] = ext.seal_record(correction)
    _refuses(fixture, bundle_path, bundle, "correction_blast_radius_mismatch")


def test_replay_returns_old_then_corrected_state_for_the_same_valid_date(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, _ = _fixture(tmp_path)
    kwargs = {
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    before = ext.replay(
        bundle_path, "2026-08-08T14:30:00Z", "2026-08-08", **kwargs
    )
    after = ext.replay(
        bundle_path, "2026-08-09T14:30:00Z", "2026-08-08", **kwargs
    )
    assert before["query"]["valid_on"] == after["query"]["valid_on"] == "2026-08-08"
    assert before["claims"][0]["assertion_state"] == "official_confirmation"
    assert after["claims"][0]["assertion_state"] == "disputed"
    assert before["events"][0]["record_status"] == "confirmed"
    assert after["events"][0]["record_status"] == "disputed"
    assert before["correction_impacts"] == []
    assert [row["correction_id"] for row in after["correction_impacts"]] == [
        "cor:oges.fixture.policy.001"
    ]


def test_future_effective_known_revision_does_not_hide_applicable_predecessor(
    tmp_path: Path,
) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    claim = bundle["snapshots"][1]["claims"][1]
    claim["valid_from"] = "2026-08-10T09:00:00Z"
    sealed_claim = ext.seal_record(claim)
    bundle["snapshots"][1]["claims"][1] = sealed_claim

    correction = bundle["snapshots"][1]["correction_impacts"][0]
    correction["valid_from"] = "2026-08-10T09:00:00Z"
    claim_transition = next(
        transition
        for transition in correction["transitions"]
        if transition["successor"]["object_type"] == "claim"
    )
    old_hash = claim_transition["successor"]["record_sha256"]
    claim_transition["successor"]["record_sha256"] = sealed_claim["record_sha256"]
    affected_claim = next(
        reference
        for reference in correction["blast_radius"]["affected_objects"]
        if reference["object_type"] == "claim"
        and reference["record_sha256"] == old_hash
    )
    affected_claim["record_sha256"] = sealed_claim["record_sha256"]
    correction["blast_radius"]["affected_objects"] = sorted(
        correction["blast_radius"]["affected_objects"],
        key=lambda row: (row["object_type"], row["object_id"], row["record_sha256"]),
    )
    bundle["snapshots"][1]["correction_impacts"][0] = ext.seal_record(correction)
    _rewrite_bundle(bundle_path, bundle)

    kwargs = {
        "root": fixture.root,
        "profile_path": fixture.root / EXTENSION / "profile.json",
    }
    before_effective = ext.replay(
        bundle_path, "2026-08-09T14:30:00Z", "2026-08-08", **kwargs
    )
    after_effective = ext.replay(
        bundle_path, "2026-08-09T14:30:00Z", "2026-08-10", **kwargs
    )
    assert [row["assertion_state"] for row in before_effective["claims"]] == [
        "official_confirmation"
    ]
    assert [row["subject_event_id"] for row in before_effective["claims"]] == [
        "evt:oges.fixture.policy.001"
    ]
    assert [row["event_id"] for row in before_effective["events"]] == [
        "evt:oges.fixture.policy.001"
    ]
    assert before_effective["events"][0]["record_status"] == "confirmed"
    assert [row["assertion_state"] for row in after_effective["claims"]] == [
        "disputed"
    ]
    assert [row["subject_event_id"] for row in after_effective["claims"]] == [
        "evt:oges.fixture.policy.002"
    ]
    assert [row["event_id"] for row in after_effective["events"]] == [
        "evt:oges.fixture.policy.002"
    ]


def test_count_units_cannot_relabel_aggregate_rows_as_events(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    for snapshot in bundle["snapshots"]:
        units = snapshot["count_units"]
        assert units["aggregate_source_rows"] is None
        assert units["deduplicated_source_events"] is None
        assert units["canonical_geopolitical_events"] == 1
        assert units["detected_salience_episodes"] == 1
    bundle["snapshots"][0]["count_units"]["aggregate_source_rows"] = 1
    _refuses(fixture, bundle_path, bundle, "count_unit_boundary_invalid")


def test_synthetic_fixture_cannot_claim_production_trust(tmp_path: Path) -> None:
    fixture, bundle_path, bundle = _fixture(tmp_path)
    bundle["production_trust"] = True
    _refuses(fixture, bundle_path, bundle, "object_schema_invalid")


def test_extension_does_not_mutate_base_oges_or_its_trust_boundary(tmp_path: Path) -> None:
    assert _sha(ROOT / "standard/oges/0.1.0/profile.json") == BASE_OGES_PROFILE_SHA256
    fixture, bundle_path, _ = _fixture(tmp_path)
    profile = json.loads((fixture.root / EXTENSION / "profile.json").read_text())
    assert profile["base_oges"]["profile_sha256"] == BASE_OGES_PROFILE_SHA256
    assert profile["trust_boundary"] == {
        "accepted_bundle_class": "synthetic_nonproduction",
        "production_trust": False,
        "source_rights_authority": False,
        "fixture_keys_production_forbidden": True,
    }
    (fixture.root / "standard/oges/0.1.0/profile.json").write_text("{}\n")
    with pytest.raises(ext.EventLedgerExtensionError) as substituted:
        ext.validate_bundle(
            bundle_path,
            root=fixture.root,
            profile_path=fixture.root / EXTENSION / "profile.json",
        )
    assert substituted.value.code == "profile_base_oges_digest_mismatch"


def test_adversarial_matrix_and_normative_surfaces_are_committed_together() -> None:
    cases = json.loads((ROOT / EXTENSION / "adversarial-cases.json").read_text())
    assert {row["id"] for row in cases["cases"]} == COVERED_CASES
    surfaces = [
        "src/event_ledger_extension.py",
        "tests/test_event_ledger_extension.py",
        *(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / EXTENSION).iterdir())),
    ]
    subprocess.run(
        ["git", "ls-files", "--error-unmatch", *surfaces],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
