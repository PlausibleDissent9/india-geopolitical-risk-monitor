"""The events reducer counts what it should and nothing else."""
from __future__ import annotations

import io
import zipfile
from datetime import date

from src import fetch_events


def _row(a1: str = "", a2: str = "", geo: str = "", quad: str = "1",
         root: str = "01", goldstein: str = "0.0", mentions: str = "1") -> str:
    cols = [""] * 58
    cols[fetch_events.COL_A1_COUNTRY] = a1
    cols[fetch_events.COL_A2_COUNTRY] = a2
    cols[fetch_events.COL_ACTIONGEO_COUNTRY] = geo
    cols[fetch_events.COL_QUADCLASS] = quad
    cols[fetch_events.COL_ROOTCODE] = root
    cols[fetch_events.COL_GOLDSTEIN] = goldstein
    cols[fetch_events.COL_MENTIONS] = mentions
    return "\t".join(cols)


def _zip_of(rows: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("20260101.export.CSV", "\n".join(rows) + "\n")
    return buf.getvalue()


def test_compute_day_counts(monkeypatch):
    rows = [
        _row(a1="IND", quad="4", root="19", goldstein="-10", mentions="5"),
        _row(a1="USA", geo="IN", quad="3", root="14", goldstein="-6.5", mentions="3"),
        _row(a1="USA", geo="US", quad="4", root="19", goldstein="-9", mentions="7"),
        _row(a2="IND", quad="1", root="04", goldstein="2", mentions="2"),
    ]
    monkeypatch.setattr(fetch_events, "_download", lambda day: _zip_of(rows))
    out = fetch_events.compute_day(date(2026, 1, 1))
    assert out is not None
    assert out["n_global"] == 4
    assert out["n_india"] == 3
    assert out["n_material_conflict"] == 1
    assert out["n_verbal_conflict"] == 1
    assert out["n_protest"] == 1
    assert out["mentions_sum"] == 10
    assert out["goldstein_mean"] == round((-10 - 6.5 + 2) / 3, 3)


def test_unpublished_day_returns_none(monkeypatch):
    monkeypatch.setattr(fetch_events, "_download", lambda day: None)
    assert fetch_events.compute_day(date(2026, 1, 1)) is None
