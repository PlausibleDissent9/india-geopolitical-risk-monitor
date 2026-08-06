"""Aptness pre-filter: founder-agreement arithmetic against a synthetic
queue (no network, no API key)."""
from __future__ import annotations

from src import aptness


def _write_queue(tmp_path, rows):
    path = tmp_path / "audit_queue.csv"
    header = "date,channel,url,title,domain,machine_label,rubric_version,human_label\n"
    body = "".join(
        f"2026-08-05,ch,{u},t,d,,1.0.0,{h}\n" for u, h in rows
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def test_agreement_counts_firm_overlap_only(tmp_path, monkeypatch):
    queue = _write_queue(tmp_path, [
        ("https://a.example/1", "ON"),
        ("https://a.example/2", "OFF"),
        ("https://a.example/3", "ABSTAIN"),  # abstention never audits
    ])
    monkeypatch.setattr(aptness, "QUEUE", queue)
    machine = {
        "https://a.example/1": "ON",       # agree
        "https://a.example/2": "ON",       # disagree
        "https://a.example/3": "OFF",      # founder abstained -> excluded
        "https://a.example/4": "OFF",      # no founder ruling -> excluded
    }
    out = aptness.founder_agreement(machine)
    assert out == {"n_overlap": 2, "rate": 0.5}


def test_agreement_empty_when_no_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(aptness, "QUEUE", tmp_path / "missing.csv")
    assert aptness.founder_agreement({"u": "ON"}) == {"n_overlap": 0, "rate": None}
