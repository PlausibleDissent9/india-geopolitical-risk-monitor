"""UCDP filter/upsert: India-only scoping, id-keyed revision, stable order."""
from __future__ import annotations

from src.fetch_ucdp import FIELDS, filter_row, upsert


def test_filter_row_keeps_only_known_fields_and_truncates_dates():
    row = {
        "id": "244657", "year": "2017", "type_of_violence": "1",
        "conflict_name": "India: Kashmir insurgency", "dyad_name": "x",
        "side_a": "Government of India", "side_b": "Y", "country": "India",
        "region": "Asia", "date_start": "2017-07-31 00:00:00.000",
        "date_end": "2017-07-31 00:00:00.000", "deaths_a": "0",
        "deaths_b": "4", "deaths_civilians": "0", "deaths_unknown": "2",
        "best": "6", "high": "6", "low": "6",
        "where_coordinates": "Srinagar", "latitude": "34.0", "longitude": "74.8",
        "relid": "should not survive", "source_headline": "should not survive",
    }
    out = filter_row(row)
    assert set(out) == set(FIELDS)
    assert out["date_start"] == "2017-07-31"
    assert out["date_end"] == "2017-07-31"
    assert out["id"] == "244657"


def test_upsert_revises_by_id_and_sorts_by_date():
    existing = [
        {"id": "2", "date_start": "2020-02-01", "best": "5"},
        {"id": "1", "date_start": "2020-01-01", "best": "3"},
    ]
    new = [
        {"id": "2", "date_start": "2020-02-01", "best": "9"},  # revision
        {"id": "3", "date_start": "2020-01-15", "best": "1"},  # new event
    ]
    out = upsert(existing, new)
    assert [r["id"] for r in out] == ["1", "3", "2"]
    assert out[2]["best"] == "9"  # the revision won
