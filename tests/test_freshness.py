"""The freshness audit must be able to fail, and must not excuse itself.

Written after two lanes (China, V5 multilingual) failed silently for
days. A stale payload does not break: it keeps serving its last value,
and gets quoted exactly as confidently as a fresh one.
"""
from __future__ import annotations

import json
from datetime import date

import pytest
from src import freshness


def _write(tmp_path, name, meta=None, body=None):
    payload = dict(body or {})
    if meta is not None:
        payload["_meta"] = meta
    (tmp_path / name).write_text(json.dumps(payload), encoding="utf-8")


def test_a_stale_payload_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json", {"generated": "2026-08-01T00:00:00Z"})
    rows = freshness.audit(today=date(2026, 8, 7))
    assert rows[0]["status"] == "STALE"
    assert rows[0]["age_days"] == 6


def test_a_fresh_payload_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json", {"generated": "2026-08-06T00:00:00Z"})
    assert freshness.audit(today=date(2026, 8, 7))[0]["status"] == "fresh"


def test_write_day_and_measurement_day_are_never_conflated(
        tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json",
           {"generated": "2026-08-07T00:00:00Z"},
           {"date": "2026-08-05", "value": 1})
    row = freshness.audit(today=date(2026, 8, 7))[0]
    assert row["status"] == "fresh"
    assert row["written_date"] == "2026-08-07"
    assert row["write_age_days"] == 0
    assert row["measured_date"] == "2026-08-05"
    assert row["measured_age_days"] == 2
    assert row["measurement_status"] == "declared"


def test_an_invalid_declared_measurement_day_is_not_called_fresh(
        tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json",
           {"generated": "2026-08-07T00:00:00Z"},
           {"date": "not-a-day"})
    row = freshness.audit(today=date(2026, 8, 7))[0]
    assert row["status"] == "undatable"
    assert row["measurement_status"] == "invalid"
    assert "declared measurement date" in row["reason"]


def test_measurement_days_must_be_exact_and_not_future(
        tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "timestamp.json",
           {"generated": "2026-08-07T00:00:00Z"},
           {"date": "2026-08-06T12:00:00Z"})
    _write(tmp_path, "future.json",
           {"generated": "2026-08-07T00:00:00Z"},
           {"date": "2026-08-08"})
    rows = {row["payload"]: row
            for row in freshness.audit(today=date(2026, 8, 7))}
    assert rows["timestamp.json"]["measurement_status"] == "invalid"
    assert rows["timestamp.json"]["status"] == "undatable"
    assert rows["future.json"]["measurement_status"] == "future"
    assert rows["future.json"]["status"] == "undatable"


def test_an_undatable_payload_is_a_failure_not_a_pass(tmp_path, monkeypatch):
    """The trap this whole module exists to avoid: an auditor that
    skips what it cannot read reports green forever. Three real
    payloads had no timestamp when this was written."""
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json", meta=None, body={"data": [1, 2]})
    row = freshness.audit(today=date(2026, 8, 7))[0]
    assert row["status"] == "undatable"
    assert row["status"] != "fresh"


def test_an_unparseable_timestamp_is_also_a_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    _write(tmp_path, "thing.json", {"generated": "not-a-date"})
    assert freshness.audit(today=date(2026, 8, 7))[0]["status"] == "undatable"


def test_slower_lanes_get_their_own_limit(tmp_path, monkeypatch):
    """A weekly lane must not be reported stale every Tuesday."""
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    monkeypatch.setitem(freshness.MAX_AGE_DAYS, "slow.json", 30)
    _write(tmp_path, "slow.json", {"generated": "2026-07-20T00:00:00Z"})
    _write(tmp_path, "fast.json", {"generated": "2026-07-20T00:00:00Z"})
    rows = {r["payload"]: r for r in freshness.audit(today=date(2026, 8, 7))}
    assert rows["slow.json"]["status"] == "fresh"
    assert rows["fast.json"]["status"] == "STALE"


def test_every_exemption_carries_a_reason():
    """An exemption without a stated reason is how a check gets hollowed
    out one entry at a time."""
    for name, reason in freshness.EXEMPT.items():
        assert isinstance(reason, str) and len(reason) > 20, (
            f"{name} is exempt without a real reason")


def test_withdrawn_brief_tombstone_is_intentionally_static():
    reason = freshness.EXEMPT["daily_brief.json"]
    assert "withdrawn 2026-08-08" in reason
    assert "2026-11-06" in reason
    assert "must not be refreshed" in reason


def test_evolution_contract_is_static_but_live_health_is_not_hidden() -> None:
    reason = freshness.EXEMPT["evolution.json"]
    assert "deterministic capability" in reason
    assert "hourly evolution audit reads current freshness separately" in reason


@pytest.mark.live
def test_the_real_site_has_no_stale_or_undatable_payloads():
    """Belt and braces against the live tree, so this cannot pass in
    isolation while the actual site serves a frozen payload."""
    rows = freshness.audit()
    bad = [r["payload"] for r in rows
           if r["status"] in ("STALE", "undatable")]
    assert not bad, f"stale or undatable payloads being served: {bad}"


def test_the_audit_fails_loudly_when_something_is_stale(tmp_path,
                                                       monkeypatch):
    """The whole point: it has to be able to stop a run."""
    monkeypatch.setattr(freshness, "SITE_DATA", tmp_path)
    monkeypatch.setattr(freshness.sys, "argv", ["freshness"])
    _write(tmp_path, "thing.json", {"generated": "2026-01-01T00:00:00Z"})
    with pytest.raises(SystemExit):
        freshness.main()
