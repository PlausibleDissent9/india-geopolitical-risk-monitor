"""Hostile tests for the first canonical evidence emitter.

These records are the root of the canonical graph: entities cite them,
events link them, exposure edges depend on them. An emitter that can
invent one, or claim a right it does not hold, or claim to hold content
it does not have, corrupts everything downstream. So the attacks are the
ones that would produce a plausible record rather than a broken one.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from src import evidence_emitter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry = Registry().with_resources([
        (name, Resource.from_contents(doc, default_specification=DRAFT202012))
        for name, doc in schemas.items()
    ])
    return jsonschema.Draft202012Validator(
        schemas["evidence-item.schema.json"], registry=registry
    )


@pytest.fixture(scope="module")
def records() -> list[dict[str, Any]]:
    return evidence_emitter.build_records()


def test_every_record_validates(records, validator) -> None:
    for record in records:
        validator.validate(record)


def test_records_exist_at_all(records) -> None:
    # A silently empty emitter would pass every other test here.
    assert records, "no evidence emitted; the receipt payload may have no channels"


def test_content_availability_never_claims_bytes_we_lack(records) -> None:
    # The lane holds title, url and domain -- no article body. Claiming
    # full_bytes or public_extract would assert we hold the content, and the
    # schema would then demand an artifact digest we cannot produce.
    for record in records:
        assert record["content_availability"] == "hash_metadata_only"
        assert record["artifact_path"] is None
        assert record["artifact_sha256"] is None


def test_every_record_carries_the_signed_decision_that_permits_it(records) -> None:
    for record in records:
        assert record["rights_use"] == evidence_emitter.REQUIRED_USE
        assert record["rights_decision_id"], "a record with no decision id is unrooted"
        assert record["source_id"] == evidence_emitter.SOURCE_ID


def test_emission_refuses_when_the_use_is_not_permitted(monkeypatch) -> None:
    # The decisive rights attack: the row exists and is approved, but the
    # use this emitter stamps on every record is not among its permitted
    # uses. Emitting anyway would forge a right.
    original = evidence_emitter._approved_row

    def narrowed() -> dict[str, Any]:
        row = dict(original())
        row["permitted_uses"] = ["cite_metadata"]
        return row

    monkeypatch.setattr(evidence_emitter, "_approved_row", narrowed)
    # _approved_row itself does the check, so exercise the real one instead.
    monkeypatch.undo()
    monkeypatch.setattr(evidence_emitter, "REQUIRED_USE", "redistribute_full_record")
    with pytest.raises(evidence_emitter.EvidenceEmitterError) as excinfo:
        evidence_emitter._approved_row()
    assert excinfo.value.code == "evidence_use_not_permitted"


def test_an_unavailable_channel_produces_no_evidence(records) -> None:
    # A refused channel must stay refused. Manufacturing an evidence item
    # for a channel the lane could not fetch would be inventing evidence.
    payload = json.loads(
        (ROOT / "docs/data/receipt_identity.json").read_text(encoding="utf-8")
    )
    available_urls = {
        article["url"]
        for block in payload["channels"].values()
        if block.get("state") == "available"
        for article in block.get("articles", [])
    }
    assert {r["source_record_id"] for r in records} == available_urls


def test_the_seal_moves_when_any_field_moves(records) -> None:
    from src import canonical_objects

    record = dict(records[0])
    sealed = record["record_sha256"]
    tampered = {k: v for k, v in record.items() if k != "record_sha256"}
    tampered["title"] = tampered["title"] + "."
    assert canonical_objects.seal_record(tampered)["record_sha256"] != sealed


def test_records_are_bound_to_the_exact_emitter_that_made_them(records) -> None:
    import hashlib

    actual = hashlib.sha256(
        (ROOT / "src/evidence_emitter.py").read_bytes()
    ).hexdigest()
    for record in records:
        method = record["provenance"]["method"]
        assert method["implementation_sha256"] == actual, (
            "a record must name the code that produced it, so two records "
            "can be told apart by their emitter rather than by a version "
            "string somebody remembered to bump"
        )


def test_evidence_ids_are_stable_and_unique(records) -> None:
    ids = [r["evidence_id"] for r in records]
    assert len(ids) == len(set(ids))
    # Re-running must reproduce the same identities, or every run would
    # create duplicate evidence for the same article.
    assert ids == [r["evidence_id"] for r in evidence_emitter.build_records()]
