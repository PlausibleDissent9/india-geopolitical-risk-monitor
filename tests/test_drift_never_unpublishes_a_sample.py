"""A drift rerun's rate-limit gaps must not delete published samples.

Which channel-years hit GDELT's artlist 429 varies run to run. Until
2026-08-10 the drift block wholesale-replaced per_channel_domains, so a
rerun whose gaps landed on years an earlier run had measured DELETED
those measurements from the published payload. A local rerun that day
would have removed four published channel-years its own 429s missed.

The rule is the ngram-heal rule: a rerun appends and refreshes, it never
un-publishes. A sample this run cannot refresh is carried forward
unchanged with its original sampled_on, and the payload note counts the
carries separately from true gaps (no published predecessor).
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
from src import fetch_gdelt, validate


def _norm_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2025-06-01", "2026-06-01"]).date
    return pd.DataFrame({"value": [1, 1], "norm": [1000, 1100]}, index=idx)


def test_a_429_year_keeps_its_published_sample(monkeypatch, tmp_path: Path):
    site = tmp_path / "data"
    site.mkdir()
    published = {
        "drift": {
            "per_channel_domains": {
                "pakistan_west": {
                    "2025": {"n_articles_sampled": 100,
                             "n_distinct_domains": 51,
                             "herfindahl_top10": 0.0197,
                             "sampled_on": "2026-07-13"},
                },
            },
        },
    }
    (site / "validation.json").write_text(json.dumps(published),
                                          encoding="utf-8")
    monkeypatch.setattr(validate, "SITE_DATA", site)
    monkeypatch.setattr(validate, "RAW_DIR", tmp_path / "no-raw")
    monkeypatch.setattr(fetch_gdelt, "fetch_corpus_norm",
                        lambda *a, **k: _norm_frame())

    def articles(query, start: date, end: date, maxrecords=100):
        if start.year == 2025 and "pakistan_west" not in getattr(
                articles, "seen", set()):
            # First channel's 2025 sample is throttled; everything else
            # resolves with a two-domain sample.
            articles.seen = {"pakistan_west"}
            raise RuntimeError("GDELT artlist failed after 6 attempts: "
                               "HTTP 429 rate limit")
        return [{"domain": "example.com"}, {"domain": "other.org"}]

    monkeypatch.setattr(fetch_gdelt, "fetch_articles", articles)
    validate.drift()

    result = json.loads((site / "validation.json").read_text(encoding="utf-8"))
    domains = result["drift"]["per_channel_domains"]
    kept = domains["pakistan_west"]["2025"]
    assert kept["n_distinct_domains"] == 51, (
        "the published 2025 sample was deleted by a rate-limited rerun")
    assert kept["sampled_on"] == "2026-07-13", (
        "a carried sample must keep its original date; re-dating it "
        "misrepresents when it was measured")
    assert "carried forward" in result["drift"]["note"]
    fresh = domains["pakistan_west"]["2026"]
    assert fresh["n_distinct_domains"] == 2
    assert fresh["sampled_on"] == date.today().isoformat()
