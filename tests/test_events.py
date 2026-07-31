"""The events reducer counts what it should, in all three layers."""
from __future__ import annotations

import io
import zipfile
from datetime import date

from src import fetch_events


def _row(a1: str = "", a2: str = "", geo: str = "", adm1: str = "",
         quad: str = "1", root: str = "01", goldstein: str = "0.0",
         mentions: str = "1") -> str:
    cols = [""] * 58
    cols[fetch_events.COL_A1_COUNTRY] = a1
    cols[fetch_events.COL_A2_COUNTRY] = a2
    cols[fetch_events.COL_ACTIONGEO_COUNTRY] = geo
    cols[fetch_events.COL_ACTIONGEO_ADM1] = adm1
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


def test_compute_day_three_layers(monkeypatch):
    rows = [
        # India-Pakistan material conflict, in Punjab (IN23)
        _row(a1="IND", a2="PAK", geo="IN", adm1="IN23", quad="4", root="19",
             goldstein="-10", mentions="5"),
        # US actor protesting in India (no dyad: single India actor absent)
        _row(a1="USA", geo="IN", adm1="IN16", quad="3", root="14",
             goldstein="-6.5", mentions="3"),
        # US domestic event: not India at all
        _row(a1="USA", geo="US", quad="4", root="19", goldstein="-9",
             mentions="7"),
        # China-India cooperation abroad (no Indian geography)
        _row(a1="CHN", a2="IND", geo="CH", quad="1", root="04",
             goldstein="2", mentions="2"),
    ]
    monkeypatch.setattr(fetch_events, "_download", lambda day: _zip_of(rows))
    out = fetch_events.compute_day(date(2026, 1, 1))
    assert out is not None
    nat, dyads, states = out

    assert nat["n_global"] == 4
    assert nat["n_india"] == 3
    assert nat["n_material_conflict"] == 1
    assert nat["n_verbal_conflict"] == 1
    assert nat["n_protest"] == 1
    assert nat["mentions_sum"] == 10
    assert nat["goldstein_mean"] == round((-10 - 6.5 + 2) / 3, 3)

    by_partner = {d["partner"]: d for d in dyads}
    assert set(by_partner) == {"PAK", "CHN"}
    assert by_partner["PAK"]["n_conflict"] == 1
    assert by_partner["PAK"]["goldstein_mean"] == -10.0
    assert by_partner["CHN"]["n_coop"] == 1

    by_state = {s["adm1"]: s for s in states}
    assert set(by_state) == {"IN23", "IN16"}
    assert by_state["IN23"]["n_conflict"] == 1
    assert by_state["IN16"]["n_protest"] == 1


def test_unpublished_day_returns_none(monkeypatch):
    monkeypatch.setattr(fetch_events, "_download", lambda day: None)
    assert fetch_events.compute_day(date(2026, 1, 1)) is None
