"""Hostile tests for the first canonical entity emitter.

An entity is an assertion about the world. The attacks worth writing are
the ones where the emitter asserts more than its evidence supports:
claiming an identity is settled, inferring a jurisdiction from a domain
suffix, or citing evidence that does not exist.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012
from src import entity_emitter, evidence_emitter

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def validator() -> jsonschema.Draft202012Validator:
    schemas = {
        p.name: json.loads(p.read_text(encoding="utf-8"))
        for p in (ROOT / "schemas").glob("*.schema.json")
    }
    registry = Registry().with_resources([
        (n, Resource.from_contents(d, default_specification=DRAFT202012))
        for n, d in schemas.items()
    ])
    return jsonschema.Draft202012Validator(
        schemas["entity.schema.json"], registry=registry
    )


@pytest.fixture(scope="module")
def records() -> list[dict[str, Any]]:
    return entity_emitter.build_records()


def test_every_entity_validates(records, validator) -> None:
    for record in records:
        validator.validate(record)


def test_entities_exist_at_all(records) -> None:
    assert records


def test_every_cited_evidence_id_actually_exists(records) -> None:
    # The failure that would matter most: an entity citing evidence that is
    # not in the store. The citation graph would look complete and be
    # hollow.
    real = {r["evidence_id"] for r in evidence_emitter.build_records()}
    for record in records:
        for identifier in record["identifiers"]:
            assert identifier["evidence_ids"], "an identifier with no evidence"
            assert set(identifier["evidence_ids"]) <= real
        assert set(record["provenance"]["evidence_ids"]) <= real


def test_no_entity_claims_a_settled_identity(records) -> None:
    # A domain observation supports "a publisher operates here" and nothing
    # stronger. authoritative or crosswalked would overclaim.
    for record in records:
        assert record["identity_status"] == "provisional"


def test_no_jurisdiction_is_inferred_from_a_domain(records) -> None:
    # A .in suffix is not evidence of Indian jurisdiction, and a .com is
    # not evidence of American. Guessing would be inference dressed as a
    # record.
    for record in records:
        assert record["jurisdiction_entity_ids"] == []
        assert record["parent_entity_ids"] == []


def test_absence_of_geometry_is_stated_not_implied(records) -> None:
    for record in records:
        geometry = record["geometry"]
        assert geometry["geometry_type"] == "none"
        assert geometry["precision"] == "not_applicable"
        assert geometry["artifact_path"] is None
        assert geometry["artifact_sha256"] is None


def test_india_is_not_emitted(records) -> None:
    # The entity everyone wants first, and the one nothing here evidences.
    # Nothing in the store records a country code; only news articles.
    names = {r["canonical_name"].lower() for r in records}
    assert "india" not in names
    assert not any(r["entity_type"] == "country" for r in records)


def test_effective_start_is_an_observation_not_a_founding_date(records) -> None:
    # The earliest day evidence saw the domain. A publisher founded in 1838
    # must not be recorded as starting in 2026, nor the reverse invented.
    evidence_days = {
        r["effective_start"][:10] for r in evidence_emitter.build_records()
    }
    for record in records:
        assert record["effective_start"] in evidence_days


def test_ids_are_stable_across_runs(records) -> None:
    assert [r["entity_id"] for r in records] == [
        r["entity_id"] for r in entity_emitter.build_records()
    ]


def test_a_domain_that_no_evidence_observed_cannot_appear(records) -> None:
    payload = json.loads(
        (ROOT / "docs/data/receipt_identity.json").read_text(encoding="utf-8")
    )
    observed = {
        article["domain"].lower()
        for block in payload["channels"].values()
        if block.get("state") == "available"
        for article in block.get("articles", [])
    }
    assert {r["canonical_name"] for r in records} == observed
