"""Syndication multiplier: the bias guard, idempotence, and a refusal
to summarise a single observation."""
from __future__ import annotations

import csv

from src import syndication


def _day(date_str: str, docs: int, mult: float = 2.0) -> dict:
    return {
        "date": date_str, "n_docs_sampled": docs, "extended": True,
        "channels": {
            "pakistan_west": {"n_articles": 160, "n_stories": 46,
                              "n_domains": 144, "multiplier": mult},
            "china_east": {"n_articles": 17, "n_stories": 17,
                           "n_domains": 13, "multiplier": 1.0},
        },
    }


def test_shallow_scans_are_refused_because_the_estimator_understates(
        tmp_path, monkeypatch):
    """A duplicate is only visible when both copies land in the scan, so
    a thin day reads as less syndicated than it was. Recording it beside
    full-depth days would manufacture a downward trend out of sampling."""
    monkeypatch.setattr(syndication, "HISTORY", tmp_path / "s.csv")
    assert syndication.record(_day("2026-08-05", 28_575)) == 0
    assert not (tmp_path / "s.csv").exists()

    assert syndication.record(_day("2026-08-05", 119_349)) == 2
    assert (tmp_path / "s.csv").exists()


def test_recording_a_day_twice_adds_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(syndication, "HISTORY", tmp_path / "s.csv")
    assert syndication.record(_day("2026-08-05", 119_349)) == 2
    assert syndication.record(_day("2026-08-05", 119_349)) == 0
    with (tmp_path / "s.csv").open(encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 2


def test_sampled_depth_travels_with_every_row(tmp_path, monkeypatch):
    """Comparability has to be checkable by the reader, not asserted."""
    monkeypatch.setattr(syndication, "HISTORY", tmp_path / "s.csv")
    syndication.record(_day("2026-08-05", 119_349))
    with (tmp_path / "s.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert all(r["n_docs_sampled"] == "119349" for r in rows)


def test_one_day_gets_no_mean(tmp_path, monkeypatch):
    """A single observation summarised as a mean is how one day becomes
    a cited rate."""
    monkeypatch.setattr(syndication, "HISTORY", tmp_path / "s.csv")
    monkeypatch.setattr(syndication, "SITE_DATA", tmp_path)
    syndication.record(_day("2026-08-05", 119_349, mult=3.478))
    p = syndication.publish()
    pw = p["channels"]["pakistan_west"]
    assert pw["n_days"] == 1
    assert pw["mean"] is None and pw["min"] is None and pw["max"] is None
    assert pw["latest"]["multiplier"] == 3.478


def test_mean_appears_once_there_is_something_to_average(
        tmp_path, monkeypatch):
    monkeypatch.setattr(syndication, "HISTORY", tmp_path / "s.csv")
    monkeypatch.setattr(syndication, "SITE_DATA", tmp_path)
    for d, m in (("2026-08-03", 2.0), ("2026-08-04", 3.0),
                 ("2026-08-05", 4.0)):
        syndication.record(_day(d, 119_349, mult=m))
    pw = syndication.publish()["channels"]["pakistan_west"]
    assert pw["n_days"] == 3
    assert pw["mean"] == 3.0 and pw["min"] == 2.0 and pw["max"] == 4.0


def test_multiplier_is_articles_over_stories():
    """The definition, pinned: 1.0 means every article is its own story."""
    from src import receipts_ngrams as rn

    corpus = {
        "meta": {
            f"s:{i}": {"url": f"https://outlet{i}.example/a", "date": "20260805",
                       "title": "Same wire story" if i < 4 else f"Unique {i}"}
            for i in range(6)
        },
        "scored_stamps": set(),
    }
    spec = {"label": "t", "anchor": None, "terms": ["india"]}
    blk = rn.assemble_channel("t", spec, set(corpus["meta"]), corpus, {}, None)
    # six distinct URLs, four sharing one headline -> three stories
    assert blk["n_pool_urls"] == 6
    assert blk["n_pool_unique"] == 3
    assert blk["syndication_multiplier"] == 2.0
