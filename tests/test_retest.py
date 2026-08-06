"""Test-retest: blindness, reproducible draws, honest kappa."""
from __future__ import annotations

import csv
from datetime import date

from src import retest


def _queue(tmp_path, rows):
    p = tmp_path / "audit_queue.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "channel", "url", "title",
                                          "domain", "human_label"])
        w.writeheader()
        w.writerows(rows)
    return p


def test_recent_labels_are_ineligible_recall_not_judgment(tmp_path, monkeypatch):
    monkeypatch.setattr(retest, "QUEUE", _queue(tmp_path, [
        {"date": "2026-01-01", "channel": "c", "url": "u1", "title": "t",
         "domain": "d", "human_label": "ON"},
        {"date": "2026-08-05", "channel": "c", "url": "u2", "title": "t",
         "domain": "d", "human_label": "ON"},
    ]))
    got = retest.eligible(retest._rows(), date(2026, 8, 6))
    assert [r["url"] for r in got] == ["u1"]


def test_sheet_never_carries_the_original_label(tmp_path, monkeypatch):
    monkeypatch.setattr(retest, "SHEET", tmp_path / "sheet.csv")
    retest.write_sheet([{"date": "2026-01-01", "channel": "c", "url": "u1",
                         "title": "t", "domain": "d", "human_label": "ON"}])
    text = (tmp_path / "sheet.csv").read_text(encoding="utf-8")
    assert "human_label" not in text
    assert text.rstrip().endswith(",")  # retest_label left empty


def test_draw_is_reproducible_for_a_given_date(tmp_path, monkeypatch):
    rows = [{"date": "2026-01-01", "channel": "c", "url": f"u{i}",
             "title": "t", "domain": "d", "human_label": "ON"}
            for i in range(50)]
    monkeypatch.setattr(retest, "QUEUE", _queue(tmp_path, rows))
    a = [r["url"] for r in retest.draw(date(2026, 9, 10))]
    b = [r["url"] for r in retest.draw(date(2026, 9, 10))]
    c = [r["url"] for r in retest.draw(date(2026, 9, 11))]
    assert a == b and a != c


def test_kappa_is_none_when_undefined_not_a_flattering_one():
    assert retest.cohens_kappa([("ON", "ON")] * 10) is None
    perfect_mixed = [("ON", "ON")] * 5 + [("OFF", "OFF")] * 5
    assert retest.cohens_kappa(perfect_mixed) == 1.0
    coin = [("ON", "OFF"), ("OFF", "ON"), ("ON", "ON"), ("OFF", "OFF")]
    k = retest.cohens_kappa(coin)
    assert k is not None and abs(k) < 0.01
