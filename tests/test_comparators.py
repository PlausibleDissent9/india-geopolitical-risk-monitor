"""Comparator acquisition persists completed countries before moving on."""
from __future__ import annotations

import pandas as pd
import pytest
from src import comparators


def test_update_banks_a_country_before_the_shared_deadline(tmp_path, monkeypatch):
    store = tmp_path / "comparators.csv"
    monkeypatch.setattr(comparators, "STORE", store)
    monkeypatch.setattr(comparators, "_load_store", lambda: None)
    monkeypatch.setattr(
        comparators,
        "_spec",
        lambda: {
            "shared_terms": ["risk"],
            "countries": {
                "a": {"anchor": "a"},
                "b": {"anchor": "b"},
                "c": {"anchor": "c"},
            },
        },
    )
    idx = pd.date_range("2026-08-01", periods=3, freq="D").date
    calls: list[float | None] = []

    def bounded_fetch(*args, deadline_monotonic=None, **kwargs):
        calls.append(deadline_monotonic)
        if len(calls) == 2:
            raise comparators.fetch_gdelt.AcquisitionDeadlineExceeded("spent")
        return pd.Series([1.0, 2.0, 3.0], index=idx)

    monkeypatch.setattr(comparators.fetch_gdelt, "fetch_channel", bounded_fetch)
    result = comparators.update(deadline_monotonic=123.0)

    assert list(result.columns) == ["a"]
    assert calls == [123.0, 123.0]
    written = pd.read_csv(store)
    assert list(written.columns) == ["date", "a"]


def test_update_fails_loudly_when_nothing_can_be_banked(tmp_path, monkeypatch):
    monkeypatch.setattr(comparators, "STORE", tmp_path / "comparators.csv")
    monkeypatch.setattr(comparators, "_load_store", lambda: None)
    monkeypatch.setattr(
        comparators,
        "_spec",
        lambda: {
            "shared_terms": ["risk"],
            "countries": {"a": {"anchor": "a"}},
        },
    )

    def refuse(*args, **kwargs):
        raise comparators.fetch_gdelt.AcquisitionDeadlineExceeded("spent")

    monkeypatch.setattr(comparators.fetch_gdelt, "fetch_channel", refuse)
    with pytest.raises(RuntimeError, match="no country series landed"):
        comparators.update(deadline_monotonic=123.0)
