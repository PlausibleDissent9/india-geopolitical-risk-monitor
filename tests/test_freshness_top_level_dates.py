"""Locks for dating a payload by its top-level timestamp.

freshness._generated used to read TIMESTAMP_KEYS only inside _meta. That
called receipt_identity.json "undatable" while the payload was in fact
dated: it seals its write instant as a TOP-LEVEL generated_at, covered by
payload_seal_sha256 and typed date-time by its schema, and carries only
constant strings in _meta. "Undatable" was a false statement about it,
and a payload nobody can date is one nobody can trust.

The danger in widening a freshness lookup is that it becomes a way to
make things look fresh. It must not be. These tests pin the boundary:
the change widens where a date may be FOUND and never what counts as
fresh, so an old payload still reads STALE from either position, and a
payload with no timestamp anywhere is still undatable.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from src import freshness

RECENT = date.today().isoformat() + "T00:00:00Z"
ANCIENT = "2020-01-01T00:00:00Z"


def _payload(tmp_path, name: str, body: dict) -> None:
    (tmp_path / name).write_text(json.dumps(body), encoding="utf-8")


def _status(tmp_path, monkeypatch, name: str) -> str:
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    rows = {r["payload"]: r["status"] for r in freshness.audit()}
    return rows[name]


def test_top_level_generated_at_makes_a_payload_datable(tmp_path, monkeypatch):
    # The receipt_identity.json shape: real timestamp at the top level,
    # _meta present but carrying only constants.
    _payload(tmp_path, "thing.json", {
        "generated_at": RECENT,
        "_meta": {"what": "constant strings only"},
    })
    assert _status(tmp_path, monkeypatch, "thing.json") == "fresh"


def test_an_old_top_level_timestamp_is_still_stale(tmp_path, monkeypatch):
    # The property that matters: this cannot be used to look fresh.
    _payload(tmp_path, "thing.json", {
        "generated_at": ANCIENT,
        "_meta": {"what": "constant strings only"},
    })
    assert _status(tmp_path, monkeypatch, "thing.json") == "STALE"


def test_meta_still_wins_when_both_positions_carry_a_date(tmp_path, monkeypatch):
    # _meta is checked first and must keep precedence, so a stale _meta date
    # cannot be masked by a fresher top-level one.
    _payload(tmp_path, "thing.json", {
        "generated_at": RECENT,
        "_meta": {"generated": ANCIENT},
    })
    assert _status(tmp_path, monkeypatch, "thing.json") == "STALE"


def test_a_payload_with_no_timestamp_anywhere_is_still_undatable(
    tmp_path, monkeypatch
):
    _payload(tmp_path, "thing.json", {"_meta": {"what": "no date at all"}})
    assert _status(tmp_path, monkeypatch, "thing.json") == "undatable"


@pytest.mark.parametrize("key", freshness.TIMESTAMP_KEYS)
def test_every_registered_timestamp_key_works_from_the_top_level(
    tmp_path, monkeypatch, key: str
):
    # The registered key set is the contract; the lookup position is not
    # allowed to silently support only some of it.
    _payload(tmp_path, "thing.json", {key: RECENT})
    assert _status(tmp_path, monkeypatch, "thing.json") == "fresh"


def test_a_non_string_top_level_value_does_not_date_a_payload(
    tmp_path, monkeypatch
):
    _payload(tmp_path, "thing.json", {"generated_at": 20260816})
    assert _status(tmp_path, monkeypatch, "thing.json") == "undatable"


def test_the_real_receipt_identity_payload_is_now_datable() -> None:
    # The payload this change exists for, read from the committed tree.
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "docs/data/receipt_identity.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert "generated_at" in document, "top-level seal disappeared"
    assert not any(k in (document.get("_meta") or {}) for k in freshness.TIMESTAMP_KEYS)
    assert freshness._generated(path) == document["generated_at"][:10]


def test_widening_did_not_move_any_other_payload(tmp_path, monkeypatch):
    # A directory of one stale and one fresh payload keeps both verdicts;
    # the widened lookup adds a position, not leniency.
    old = (date.today() - timedelta(days=400)).isoformat() + "T00:00:00Z"
    _payload(tmp_path, "old.json", {"generated_at": old})
    _payload(tmp_path, "new.json", {"_meta": {"generated": RECENT}})
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    rows = {r["payload"]: r["status"] for r in freshness.audit()}
    assert rows["old.json"] == "STALE"
    assert rows["new.json"] == "fresh"
