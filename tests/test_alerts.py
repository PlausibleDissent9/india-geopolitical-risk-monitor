"""Alerts: each registered trigger fires exactly when its rule says,
and near-misses stay silent."""
from __future__ import annotations

from src import alerts

HISTORY = {
    "dates": ["2026-08-04", "2026-08-05"],
    "channels": {"china_east": [74.3, 4.5]},
    "composite": [65.0, 70.0],
}
LATEST = {"date": "2026-08-05",
          "channels": {"china_east": {"score": 4.5}}}


def test_t1_fires_on_non_overlapping_bands():
    unc = {"2026-08-04": {"china_east": [45.0, 90.5]},
           "2026-08-05": {"china_east": [0.4, 36.4]}}
    out = alerts.t1_band_separated(LATEST, unc, HISTORY)
    assert len(out) == 1
    a = out[0]
    assert a["type"] == "band_separated_move"
    assert a["direction"] == "down"
    assert a["prev_score"] == 74.3
    assert a["id"] == "2026-08-05-china_east-T1"


def test_t1_silent_when_bands_touch():
    unc = {"2026-08-04": {"china_east": [45.0, 90.5]},
           "2026-08-05": {"china_east": [45.0, 60.0]}}
    assert alerts.t1_band_separated(LATEST, unc, HISTORY) == []


def _t2_history(prev, today):
    # 400 trailing days at 50 make the 90th percentile land at 50.
    from datetime import date, timedelta
    start = date(2025, 6, 30)
    dates = [(start + timedelta(days=k)).isoformat() for k in range(400)]
    return {"dates": dates + ["2026-08-04", "2026-08-05"],
            "channels": {},
            "composite": [50.0] * 400 + [prev, today]}


def test_t2_fires_when_crossing_survives_band():
    hist = _t2_history(prev=40.0, today=80.0)
    unc = {"2026-08-05": {"composite": [70.0, 88.0]}}  # entirely above 50
    out = alerts.t2_composite_crossing(
        {"date": "2026-08-05", "channels": {}}, unc, hist)
    assert len(out) == 1
    assert out[0]["direction"] == "up"


def test_t2_silent_when_band_straddles_threshold():
    hist = _t2_history(prev=40.0, today=80.0)
    unc = {"2026-08-05": {"composite": [45.0, 88.0]}}  # dips below 50
    assert alerts.t2_composite_crossing(
        {"date": "2026-08-05", "channels": {}}, unc, hist) == []


def test_t3_reports_the_missed_morning_only():
    rel = {"days": [
        {"day": "2026-08-04", "contract": True, "on_time": False,
         "published_ist": "2026-08-05 10:27", "deadline_ist": "2026-08-05 06:00"},
        {"day": "2026-08-05", "contract": True, "on_time": True,
         "published_ist": "2026-08-06 05:50", "deadline_ist": "2026-08-06 06:00"},
    ]}
    assert alerts.t3_integrity(rel) == []  # latest scored day was on time
    rel["days"][1]["on_time"] = False
    out = alerts.t3_integrity(rel)
    assert len(out) == 1
    assert out[0]["event"] == "morning_contract_miss"
