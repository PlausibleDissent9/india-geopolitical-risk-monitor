"""Provenance: a recorded fact must never be overwritten by a guess."""
from __future__ import annotations

import csv
import json

from src import provenance


def _setup(tmp_path, monkeypatch, store_days, cached, calib=None):
    store = tmp_path / "gdelt_volume.csv"
    with store.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "pakistan_west"])
        for d in store_days:
            w.writerow([d, "0.1"])
    ngram_dir = tmp_path / "ngram_days"
    ngram_dir.mkdir()
    for d in cached:
        (ngram_dir / f"{d}.json").write_text("{}", encoding="utf-8")
    calib_path = tmp_path / "calib.json"
    calib_path.write_text(json.dumps(calib or {}), encoding="utf-8")

    monkeypatch.setattr(provenance, "STORE", store)
    monkeypatch.setattr(provenance, "NGRAM_DAYS", ngram_dir)
    monkeypatch.setattr(provenance, "CALIB", calib_path)
    monkeypatch.setattr(provenance, "RECORD", tmp_path / "provenance.csv")


def test_cached_days_reconstruct_as_bridged(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           ["2026-06-28", "2026-06-29", "2026-06-30"], ["2026-06-30"])
    rows = provenance.build()
    assert rows["2026-06-28"]["source"] == provenance.DOC_API
    assert rows["2026-06-30"]["source"] == provenance.NGRAM_BRIDGE
    assert all(r["basis"] == "reconstructed" for r in rows.values())


def test_a_recorded_row_survives_a_rebuild(tmp_path, monkeypatch):
    """The whole point of recording at splice time is that the later
    guess cannot silently overrule it."""
    _setup(tmp_path, monkeypatch, ["2026-07-01"], [])
    provenance.record_bridged("2026-07-01")
    rows = provenance.build()
    assert rows["2026-07-01"]["source"] == provenance.NGRAM_BRIDGE
    assert rows["2026-07-01"]["basis"] == "recorded"


def test_impurity_bound_is_read_from_calibration_not_assumed(
        tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, ["2026-07-01"], ["2026-07-01"],
           calib={"pakistan_west": {"ratio": 1.95, "n_days": 5},
                  "us_trade": {"ratio": 2.56, "n_days": 1}})
    assert provenance.calibration_overlap_n() == 5
    assert provenance.summary()["reconstruction_impurity_bound"] == 5


def test_summary_counts_the_mixture(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch,
           ["2026-06-29", "2026-06-30", "2026-07-01"],
           ["2026-06-30", "2026-07-01"])
    provenance.build()
    s = provenance.summary()
    assert s["n_days"] == 3
    assert s["n_doc_api"] == 1
    assert s["n_ngram_bridge"] == 2
    assert s["bridge_first_day"] == "2026-06-30"
    assert s["bridge_last_day"] == "2026-07-01"


def test_every_published_share_row_carries_a_source():
    """The label has to reach the CSV, not stop at the record."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "docs" / "data" / "shares.csv"
    if not p.exists():
        return
    with p.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "shares.csv is empty"
    assert all(r.get("source") for r in rows), (
        "a published day has no instrument label")
    assert {r["source"] for r in rows} <= {provenance.DOC_API,
                                           provenance.NGRAM_BRIDGE}
