"""Monthly aggregation: the three traps, each pinned by a test."""
from __future__ import annotations

import csv
from datetime import date

import pytest
from src import monthly


def _shares(tmp_path, days):
    p = tmp_path / "shares.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + monthly.CHANNELS + ["source"])
        for d, src in days:
            w.writerow([d] + ["1.0"] * len(monthly.CHANNELS) + [src])
    return p


def _setup(tmp_path, monkeypatch, days, sources=None):
    monkeypatch.setattr(monthly, "SHARES", _shares(tmp_path, days))
    monkeypatch.setattr(monthly, "HISTORY", tmp_path / "history.csv")
    monkeypatch.setattr(monthly, "provenance", type("P", (), {
        "by_day": staticmethod(lambda: sources or {d: s for d, s in days}),
        "DOC_API": "doc_api",
        "NGRAM_BRIDGE": "ngram_bridge",
    }))


def test_a_short_month_publishes_its_row_but_not_a_mean(
        tmp_path, monkeypatch):
    """The 2025-06 case: 14 of 30 days present. A mean over the
    survivors describes those days, not that month -- but the month must
    still appear, because a silently absent row is worse than a null."""
    days = [(f"2025-06-{d:02d}", "doc_api") for d in range(1, 15)]
    _setup(tmp_path, monkeypatch, days)
    rows = monthly.build()
    row = next(r for r in rows if r["month"] == "2025-06")
    assert row["n_days_present"] == 14
    assert row["n_days_expected"] == 30
    assert row["share_pakistan_west"] == ""
    assert "below the 80% floor" in row["refused_reason"]


def test_a_full_month_gets_its_mean(tmp_path, monkeypatch):
    days = [(f"2025-04-{d:02d}", "doc_api") for d in range(1, 31)]
    _setup(tmp_path, monkeypatch, days)
    rows = monthly.build()
    row = next(r for r in rows if r["month"] == "2025-04")
    assert row["coverage"] == 1.0
    assert row["share_pakistan_west"] == 1.0
    assert row["refused_reason"] == ""


def test_share_coverage_does_not_masquerade_as_composite_coverage(
        tmp_path, monkeypatch):
    days = [(f"2017-06-{d:02d}", "doc_api") for d in range(1, 31)]
    _setup(tmp_path, monkeypatch, days)
    # Only two ranked observations exist even though all thirty share
    # observations are present.
    monthly.HISTORY.write_text(
        "date,composite\n2017-06-29,60\n2017-06-30,64\n",
        encoding="utf-8")
    row = next(r for r in monthly.build() if r["month"] == "2017-06")
    assert row["coverage"] == 1.0
    assert row["n_days_composite_present"] == 2
    assert row["composite_coverage"] == 0.0667
    assert row["composite_mean_of_ranks"] == ""
    assert "below the 80% floor" in row["composite_refused_reason"]


def test_months_spanning_the_instrument_boundary_are_flagged(
        tmp_path, monkeypatch):
    """A user must be able to drop mixed months rather than discover
    them after the regression."""
    days = ([(f"2026-06-{d:02d}", "doc_api") for d in range(1, 30)]
            + [("2026-06-30", "ngram_bridge")])
    _setup(tmp_path, monkeypatch, days)
    row = next(r for r in monthly.build() if r["month"] == "2026-06")
    assert row["mixed_instruments"] is True
    assert row["n_days_doc_api"] == 29
    assert row["n_days_ngram_bridge"] == 1


def test_a_single_instrument_month_is_not_flagged(tmp_path, monkeypatch):
    days = [(f"2026-07-{d:02d}", "ngram_bridge") for d in range(1, 32)]
    _setup(tmp_path, monkeypatch, days)
    row = next(r for r in monthly.build() if r["month"] == "2026-07")
    assert row["mixed_instruments"] is False
    assert row["n_days_ngram_bridge"] == 31


def test_the_current_month_is_judged_against_days_elapsed(
        tmp_path, monkeypatch):
    """Otherwise every month in progress refuses itself for the whole
    month, and the series is permanently one month stale."""
    days = [(f"2026-08-{d:02d}", "ngram_bridge") for d in range(1, 8)]
    _setup(tmp_path, monkeypatch, days)

    class _D(date):
        @classmethod
        def today(cls):
            return date(2026, 8, 7)
    monkeypatch.setattr(monthly, "date", _D)

    row = next(r for r in monthly.build() if r["month"] == "2026-08")
    assert row["n_days_expected"] == 7
    assert row["coverage"] == 1.0
    assert row["refused_reason"] == ""


@pytest.mark.live
def test_published_monthly_csv_never_carries_a_mean_it_refused():
    """Belt and braces on the real artifact: no row may have both a
    refusal and a value."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "docs" / "data" / "monthly.csv"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["refused_reason"]:
                assert all(r[f"share_{c}"] == "" for c in monthly.CHANNELS), (
                    f"{r['month']} was refused but still published a mean")
