"""V11: the registration's own enforcement -- mechanics, separation,
and the mandatory research-page header."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from src import forecasts

ROOT = Path(__file__).resolve().parents[1]

MANDATORY_HEADER = (
    "This is an experiment about the index, not advice, and until the "
    "registered criterion resolves it should be presumed to show that "
    "salience does not forecast."
)


def test_research_page_carries_the_mandatory_header_verbatim():
    page = (ROOT / "docs" / "research" / "forecasts.html").read_text(
        encoding="utf-8")
    assert MANDATORY_HEADER in " ".join(page.split())


def test_registration_is_signed_and_frozen_logit_registered():
    reg = json.loads((ROOT / "validation" / "forecast_registration.json")
                     .read_text(encoding="utf-8"))
    assert reg["founder_signature"]["signed"] == "2026-08-06"
    frozen = json.loads((ROOT / "validation" / "forecast_logit_frozen.json")
                        .read_text(encoding="utf-8"))
    assert len(frozen["coefficients"]) == 3
    assert frozen["n_obs"] > 500


def test_separation_no_forecast_payload_on_front_surfaces():
    """latest.json, the brief, and index.html must never reference the
    experiment -- the separation rule is load-bearing."""
    for name in ("latest.json", "daily_brief.json"):
        text = (ROOT / "docs" / "data" / name).read_text(encoding="utf-8")
        assert "forecast" not in text.lower(), f"{name} mentions the experiment"
    index = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "research/forecasts" not in index


def test_spike_days_matches_registered_episode_rule():
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    s = pd.Series(1.0, index=idx)
    s.iloc[150] = 10.0  # a clear spike over a flat baseline
    spikes = forecasts.spike_days(s)
    assert bool(spikes.iloc[150])
    assert not spikes.iloc[100:150].any()


def test_climatology_counts_trailing_window_frequency():
    idx = pd.date_range("2024-01-01", periods=800, freq="D")
    spikes = pd.Series(False, index=idx)
    spikes.iloc[::7] = True  # a spike every week -> frequency ~1
    from datetime import date
    p = forecasts.climatology_p(spikes, date(2026, 2, 2))
    assert p == 1.0
