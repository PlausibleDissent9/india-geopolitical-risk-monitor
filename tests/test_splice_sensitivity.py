"""The public splice sensitivity must remain separate from the primary."""
from src.splice_sensitivity import build


def test_sensitivity_reports_material_score_impact_without_restatement():
    payload = build()
    meta = payload["_meta"]
    assert meta["status"] == "sensitivity analysis, not a replacement series"
    assert meta["n_adjusted_store_days"] == 37
    daily = payload["summary"]["daily"]
    weekly = payload["summary"]["trailing_7_day"]
    assert daily["pakistan_west"]["median_absolute_shift"] > 5
    assert daily["china_east"]["median_absolute_shift"] > 10
    assert weekly["china_east"]["latest_shift"] > 20
    assert daily["composite"]["maximum_absolute_shift"] < 5


def test_one_day_channels_are_not_silently_reestimated():
    payload = build()
    audit = payload["calibration_audit"]
    assert audit["us_trade"]["additional_independent_days"] == 0
    assert audit["shipping"]["additional_independent_days"] == 0
    assert "us_trade" not in payload["daily"]["primary"]
    assert "shipping" not in payload["daily"]["primary"]
