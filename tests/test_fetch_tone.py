"""Tone lane: cache adapter and store arithmetic, no network."""
from __future__ import annotations

import json

from src import fetch_tone


def test_day_urls_reads_extended_cache_first(tmp_path, monkeypatch):
    from src import receipts_ngrams
    monkeypatch.setattr(fetch_tone, "DAYS", tmp_path)
    monkeypatch.setattr(receipts_ngrams, "CHANNELS", ["ch"])
    monkeypatch.setattr(receipts_ngrams, "group_specs",
                        lambda: {"ch/q1": {"channel": "ch", "anchor": None,
                                           "phrases": []}})
    (tmp_path / "2026-08-05.json").write_text(json.dumps({
        "matched": {"ch/q1": ["t1:1"]}, "india": [],
        "meta": {"t1:1": {"url": "https://plain.example/a"}},
    }), encoding="utf-8")
    (tmp_path / "2026-08-05-extended.json").write_text(json.dumps({
        "matched": {"ch/q1": ["t1:1", "t2:9"]}, "india": [],
        "meta": {"t1:1": {"url": "https://ext.example/a"},
                 "t2:9": {"url": "https://ext.example/b"}},
    }), encoding="utf-8")
    urls = fetch_tone._day_urls("2026-08-05")
    assert sorted(urls["ch"]) == ["https://ext.example/a",
                                  "https://ext.example/b"]


def test_upsert_store_replaces_same_day_and_keeps_others(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_tone, "STORE", tmp_path / "tone_daily.csv")
    fetch_tone._upsert_store([
        {"date": "2026-08-04", "channel": "g", "n_matched": 5,
         "n_tone_found": 4, "mean_tone": -2.1},
    ])
    allrows = fetch_tone._upsert_store([
        {"date": "2026-08-05", "channel": "g", "n_matched": 9,
         "n_tone_found": 7, "mean_tone": -1.0},
        {"date": "2026-08-04", "channel": "g", "n_matched": 5,
         "n_tone_found": 5, "mean_tone": -2.4},  # revision wins
    ])
    by_day = {(r["date"], r["channel"]): r for r in allrows}
    assert by_day[("2026-08-04", "g")]["mean_tone"] == "-2.4"
    assert by_day[("2026-08-05", "g")]["n_tone_found"] == "7"
    assert len(allrows) == 2
