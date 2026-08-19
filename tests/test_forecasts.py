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
    """The front surface has no forecast fields or generated brief prose."""
    latest = json.loads(
        (ROOT / "docs" / "data" / "latest.json").read_text(encoding="utf-8")
    )
    assert "forecast" not in latest
    assert "prediction" not in latest
    brief = json.loads(
        (ROOT / "docs" / "data" / "daily_brief.json").read_text(
            encoding="utf-8")
    )
    assert brief["_meta"]["status"] == "withdrawn_factual_grounding_failure"
    assert brief["composite"] is None
    assert all(value is None for value in brief["channels"].values())
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


def _synthetic_generate_inputs(drop_anchor: bool):
    """Scores/spikes where the registered 7-day-change anchor is present or a
    disclosed gap (the row absent), mirroring the 2026-08-11/12 tape."""
    import numpy as np

    idx = pd.date_range("2024-01-01", "2026-08-18", freq="D")
    rng = np.random.default_rng(11)
    scores = pd.DataFrame(
        rng.uniform(20, 80, size=(len(idx), len(forecasts.CHANNELS))),
        index=idx, columns=forecasts.CHANNELS,
    )
    if drop_anchor:
        scores = scores.drop(pd.Timestamp("2026-08-11"))
    spikes = {
        ch: pd.Series(False, index=idx).rename(ch) for ch in forecasts.CHANNELS
    }
    return scores, spikes


def test_a_disclosed_gap_anchor_refuses_the_window_instead_of_crashing(
        tmp_path, monkeypatch):
    """2026-08-19, measured: last_day Aug 18 put the registered 7-day-change
    anchor on the disclosed gap day Aug 11; .loc raised KeyError, the run
    died, and grading plus the payload write never happened."""
    from datetime import date
    monkeypatch.setattr(forecasts, "QUESTIONS", tmp_path / "questions.json")
    scores, spikes = _synthetic_generate_inputs(drop_anchor=True)
    fresh = forecasts.generate(date(2026, 8, 19), scores, spikes)
    assert fresh == []
    assert not (tmp_path / "questions.json").exists(), \
        "a refused window must commit nothing"


def test_a_present_anchor_still_generates_the_registered_questions(
        tmp_path, monkeypatch):
    from datetime import date
    monkeypatch.setattr(forecasts, "QUESTIONS", tmp_path / "questions.json")
    scores, spikes = _synthetic_generate_inputs(drop_anchor=False)
    fresh = forecasts.generate(date(2026, 8, 19), scores, spikes)
    assert len(fresh) == len(forecasts.CHANNELS)
    committed = json.loads((tmp_path / "questions.json").read_text(
        encoding="utf-8"))["questions"]
    assert len(committed) == len(forecasts.CHANNELS)
    for q in fresh:
        assert q["window_start"] == "2026-08-24"
        assert 0.0 <= q["p_salience"] <= 1.0
        assert q["features"]["as_of"] == "2026-08-18"
