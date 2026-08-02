"""Receipts drill-down: tier-first sort, dedup, and the spike-quality
share, all against a monkeypatched fetch_gdelt (no network)."""
from __future__ import annotations

from datetime import date

from src import fetch_gdelt, receipts


def test_tier_sort_orders_registered_tiers_before_unranked():
    articles = [
        {"domain": "unknown-blog.example", "url": "u1", "tier": None},
        {"domain": "reuters.com", "url": "u2", "tier": 1},
        {"domain": "syndication-mill.example", "url": "u3", "tier": 4},
        {"domain": "thehindu.com", "url": "u4", "tier": 2},
    ]
    articles.sort(key=receipts._tier_sort_key)
    assert [a["domain"] for a in articles] == [
        "reuters.com", "thehindu.com", "syndication-mill.example",
        "unknown-blog.example",
    ]


def test_channel_receipts_dedupes_by_url_and_scores_tier12_share(monkeypatch):
    def fake_fetch_articles(query, start, end, maxrecords=20, sort="hybridrel"):
        # Two sub-queries return an overlapping URL; only one copy should
        # survive, keyed by URL as make_datapack's dossier already does.
        if "term-a" in query:
            return [
                {"title": "A", "domain": "reuters.com", "date": "20260801",
                 "url": "https://reuters.com/a"},
                {"title": "B", "domain": "syndication-mill.example",
                 "date": "20260801", "url": "https://mill.example/b"},
            ]
        return [
            {"title": "A dup", "domain": "reuters.com", "date": "20260801",
             "url": "https://reuters.com/a"},
        ]

    monkeypatch.setattr(fetch_gdelt, "fetch_articles", fake_fetch_articles)
    monkeypatch.setattr(
        fetch_gdelt, "build_queries",
        lambda terms, anchor=None: ["anchor (term-a)", "anchor (term-b)"],
    )
    spec = {"label": "Test channel", "anchor": "India", "terms": ["term-a", "term-b"]}
    tiers = {"reuters.com": 1, "syndication-mill.example": 4}

    out = receipts.channel_receipts("test", spec, date(2026, 8, 1), tiers)

    assert out["n_retrieved"] == 2  # deduped by URL, not 3
    assert [a["domain"] for a in out["articles"]] == [
        "reuters.com", "syndication-mill.example",
    ]
    assert out["spike_quality_tier12_share"] == 0.5  # 1 of 2 tier1-2


def test_channel_receipts_caps_at_max_published(monkeypatch):
    many = [
        {"title": f"t{i}", "domain": f"site{i}.example", "date": "20260801",
         "url": f"https://site{i}.example/{i}"}
        for i in range(receipts.MAX_ARTICLES_PUBLISHED + 10)
    ]
    monkeypatch.setattr(
        fetch_gdelt, "fetch_articles",
        lambda query, start, end, maxrecords=20, sort="hybridrel": many,
    )
    monkeypatch.setattr(fetch_gdelt, "build_queries", lambda terms, anchor=None: ["q"])
    spec = {"label": "Test channel", "anchor": None, "terms": ["term-a"]}

    out = receipts.channel_receipts("test", spec, date(2026, 8, 1), {})

    assert out["n_retrieved"] == receipts.MAX_ARTICLES_PUBLISHED
    assert all(a["tier"] is None for a in out["articles"])
