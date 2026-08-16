"""Locks for the unsigned canonical release manifest.

The manifest is everything a release is except the signature. These tests
pin that boundary in both directions: it must be complete enough that
only the signature is missing, and it must never fill the signature in
itself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from src import evidence_emitter, release_assembler

ROOT = Path(__file__).resolve().parents[1]
SIGNATURE_FIELDS = {"release_signer_id", "release_signature_path"}


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return release_assembler.build_manifest()


@pytest.fixture(scope="module")
def errors(manifest) -> list[Any]:
    schemas = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry = Registry().with_resources([
        (n, Resource.from_contents(d, default_specification=DRAFT202012))
        for n, d in schemas.items()
    ])
    validator = jsonschema.Draft202012Validator(
        schemas["canonical-release.schema.json"], registry=registry
    )
    return list(validator.iter_errors(manifest))


def test_only_the_signature_is_missing(errors) -> None:
    # The load-bearing assertion. If anything OTHER than the two signature
    # fields is invalid, the manifest is not ready for a ceremony and
    # handing it to one would waste the founder's signature.
    offending = {tuple(e.absolute_path)[0] for e in errors if e.absolute_path}
    assert offending == SIGNATURE_FIELDS, (
        f"expected only the signature fields to be missing, got {offending}"
    )


def test_the_assembler_never_signs(manifest) -> None:
    # A manifest that filled these in would assert an authority this
    # process does not hold.
    assert manifest["release_signer_id"] is None
    assert manifest["release_signature_path"] is None


def test_counts_match_the_objects_present(manifest) -> None:
    actual: dict[str, int] = {}
    for obj in manifest["objects"]:
        actual[obj["object_type"]] = actual.get(obj["object_type"], 0) + 1
    for object_type, count in manifest["counts"].items():
        assert count == actual.get(object_type, 0)


def test_zero_events_is_recorded_not_hidden(manifest) -> None:
    # A release with no events is honest, not broken. It must SAY zero
    # rather than omit the key, so a reader sees the graph's real shape.
    assert manifest["counts"]["event"] == 0
    assert manifest["counts"]["exposure_edge"] == 0
    assert manifest["counts"]["evidence_item"] > 0
    assert manifest["counts"]["entity"] > 0


def test_rights_snapshot_carries_the_real_decision(manifest) -> None:
    registry = json.loads(
        (ROOT / "governance/source_rights_registry.json").read_text(encoding="utf-8")
    )
    rows = {r["source_id"]: r for r in registry["sources"]}
    assert manifest["rights_snapshot"]
    for entry in manifest["rights_snapshot"]:
        row = rows[entry["source_id"]]
        assert row["decision_state"] == "approved"
        assert entry["decision_id"] == row["decision_id"]
        assert entry["decision_artifact_sha256"] == row["decision_artifact_sha256"]
        assert entry["signer_id"] == row["signer_id"]


def test_registry_digests_are_of_the_actual_files(manifest) -> None:
    import hashlib

    for key, relative in release_assembler.REGISTRIES.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        assert manifest[key] == actual


def test_object_record_digests_match_the_emitted_records(manifest) -> None:
    sealed = {r["evidence_id"]: r["record_sha256"]
              for r in evidence_emitter.build_records()}
    for obj in manifest["objects"]:
        if obj["object_type"] == "evidence_item":
            assert obj["record_sha256"] == sealed[obj["object_id"]]


def test_release_id_is_stable_for_the_same_graph(manifest) -> None:
    assert release_assembler.build_manifest()["release_id"] == manifest["release_id"]


def test_an_unapproved_source_refuses(monkeypatch) -> None:
    monkeypatch.setattr(release_assembler, "REGISTRIES", {
        **release_assembler.REGISTRIES,
        "rights_registry_sha256": "governance/rights_signers.json",  # no sources
    })
    with pytest.raises(release_assembler.ReleaseAssemblerError) as excinfo:
        release_assembler.build_manifest()
    assert excinfo.value.code == "release_source_not_approved"


def test_the_release_carries_its_own_universe(manifest) -> None:
    # A release that does not say what was in scope leaves a reader to
    # infer the universe from whatever happens to be present, which is how
    # a partial sample gets read as a complete one.
    assert manifest["counts"]["universe_release"] == 1
    universes = [o for o in manifest["objects"]
                 if o["object_type"] == "universe_release"]
    assert len(universes) == 1


def test_the_universe_states_the_channels_it_could_not_see(manifest) -> None:
    from src import universe_emitter

    record = universe_emitter.build_record()
    payload = json.loads(
        (ROOT / "docs/data/receipt_identity.json").read_text(encoding="utf-8")
    )
    unavailable = [n for n, b in payload["channels"].items()
                   if b.get("state") != "available"]
    for name in unavailable:
        assert name in record["denominator_definition"], (
            f"{name} was unavailable and the denominator must say so; a "
            "partial view that reads as complete is the failure this "
            "object exists to prevent"
        )
    for forbidden in ("share of Indian press", "share of coverage"):
        assert forbidden in record["denominator_definition"]
