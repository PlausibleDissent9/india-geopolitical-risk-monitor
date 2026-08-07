"""Every download must explain itself, because the codebook says it does.

The codebook promised that every dict payload carries what/units/
licence/citation/codebook-link/generated "so a downloaded file explains
itself without this website". Measured, licence and citation were
present in 3 of 64. For a project whose entire pitch is citability, a
false claim about citability is the worst one to leave standing.
"""
from __future__ import annotations

import json

import pytest
from src import stamp_meta


def _write(tmp_path, name, payload):
    (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path / name


def test_absent_fields_are_filled(tmp_path):
    p = _write(tmp_path, "thing.json", {"_meta": {"what": "x"}, "a": 1})
    added = stamp_meta.stamp_file(p)
    assert set(added) == {"license", "citation", "codebook", "source"}
    meta = json.loads(p.read_text())["_meta"]
    assert meta["license"] == stamp_meta.LICENSE
    assert meta["source"].endswith("thing.json")
    assert meta["what"] == "x", "an existing field was disturbed"


def test_a_module_set_field_is_never_overwritten(tmp_path):
    """A lane that writes its own citation or a stricter licence knows
    more about its payload than a blanket stamp does."""
    p = _write(tmp_path, "thing.json", {"_meta": {
        "license": "ODbL 1.0", "citation": "Someone else (2020)"}})
    stamp_meta.stamp_file(p)
    meta = json.loads(p.read_text())["_meta"]
    assert meta["license"] == "ODbL 1.0"
    assert meta["citation"] == "Someone else (2020)"


def test_stamping_is_idempotent(tmp_path):
    p = _write(tmp_path, "thing.json", {"a": 1})
    assert stamp_meta.stamp_file(p)
    assert stamp_meta.stamp_file(p) == [], "a second pass rewrote the file"


def test_a_payload_without_meta_gets_one(tmp_path):
    p = _write(tmp_path, "thing.json", {"a": 1})
    stamp_meta.stamp_file(p)
    assert "_meta" in json.loads(p.read_text())


def test_arrays_are_left_alone(tmp_path):
    """episodes.json and notes.json are bare arrays with nowhere to put
    _meta; they must not be mangled into objects."""
    p = _write(tmp_path, "arr.json", [1, 2, 3])
    assert stamp_meta.stamp_file(p) == []
    assert json.loads(p.read_text()) == [1, 2, 3]


def test_the_frozen_contract_is_never_rewritten():
    """api_contract.json is a promise about field stability. Rewriting
    it as a side effect is precisely what it exists to prevent."""
    assert "api_contract.json" in stamp_meta.SKIP


@pytest.mark.live
def test_the_live_site_keeps_the_codebook_promise():
    """The claim, checked against what is actually served."""
    gaps = stamp_meta.audit()
    assert not gaps, (
        "payloads missing the universal _meta fields the codebook "
        f"promises every download carries: {gaps}")
