"""Per-sector feeds: pure assembly from published payloads."""
from __future__ import annotations

from src import sector_feeds


def test_feed_carries_scores_bands_weights_and_disclaimer():
    sectors = {"sectors": {"s": {"label": "S",
                                 "channels": ["shipping", "us_trade"],
                                 "rationale": "why"}}}
    latest = {"date": "2026-08-05", "channels": {
        "shipping": {"label": "Shipping", "score": 83.2},
        "us_trade": {"label": "US & trade", "score": 35.6}}}
    unc = {"days": {"2026-08-05": {"shipping": [77.5, 88.4]}}}
    feed = sector_feeds.build_feed("s", sectors["sectors"]["s"], sectors,
                                   latest, unc, None)
    assert feed["channels"]["shipping"]["score"] == 83.2
    assert feed["channels"]["shipping"]["band95"] == [77.5, 88.4]
    assert feed["channels"]["us_trade"]["band95"] is None
    assert feed["channels"]["shipping"]["weight"] == 0.5
    assert "not a measure of risk" in feed["_meta"]["what"]
    assert "measured_sensitivity" not in feed  # no signed mapping given
