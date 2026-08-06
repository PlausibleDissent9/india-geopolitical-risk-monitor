"""Spike breadth: channel aggregation uses the receipts arithmetic."""
from __future__ import annotations

from src import receipts_ngrams, spike_breadth


def test_breadth_counts_domains_with_anchor_arithmetic(monkeypatch):
    monkeypatch.setattr(receipts_ngrams, "CHANNELS", ["ch"])
    monkeypatch.setattr(
        receipts_ngrams, "group_specs",
        lambda: {"ch/q1": {"channel": "ch", "anchor": "india",
                           "phrases": []}})
    cache = {
        "matched": {"ch/q1": ["t:1", "t:2", "t:3"]},
        "india": ["t:1", "t:2"],  # t:3 fails the anchor and must drop
        "meta": {
            "t:1": {"url": "https://www.alpha.example/a"},
            "t:2": {"url": "https://alpha.example/b"},  # same domain
            "t:3": {"url": "https://beta.example/c"},
        },
    }
    out = spike_breadth.day_breadth(cache)
    assert out == {"ch": {"n_matched": 2, "n_domains": 1,
                          "top_domain": "alpha.example",
                          "top_domain_share": 1.0}}
