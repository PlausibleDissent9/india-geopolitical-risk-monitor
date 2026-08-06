"""Exposure engine: the registered weighting rule, exactly and only."""
from __future__ import annotations

import pytest
from src import exposure

SPEC = {"sectors": {
    "a_two_channels": {"label": "A", "channels": ["shipping", "us_trade"]},
    "b_one_channel": {"label": "B", "channels": ["gulf_energy"]},
}}


def test_equal_split_across_a_sectors_channels():
    w = exposure.profile_weights({"a_two_channels": 1.0}, SPEC)
    assert w == {"shipping": 0.5, "us_trade": 0.5}


def test_shares_normalize_and_sum_across_sectors():
    w = exposure.profile_weights(
        {"a_two_channels": 60, "b_one_channel": 40}, SPEC)
    assert w == {"gulf_energy": 0.4, "shipping": 0.3, "us_trade": 0.3}
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_unknown_sector_refuses():
    with pytest.raises(ValueError, match="unknown sectors"):
        exposure.profile_weights({"nope": 1.0}, SPEC)


def test_zero_profile_refuses():
    with pytest.raises(ValueError):
        exposure.profile_weights({"a_two_channels": 0.0}, SPEC)


def test_registered_sectors_map_to_real_channels():
    """Every channel named in the registered sectors.json must exist in
    the instrument's dictionaries -- a dangling channel would render a
    reader's exposure from nothing."""
    import json

    from src.exposure import ROOT, load_sectors
    dictionaries = json.loads(
        (ROOT / "dictionaries.json").read_text(encoding="utf-8"))
    real = {k for k in dictionaries if k != "_meta"}
    for key, spec in load_sectors()["sectors"].items():
        assert spec["channels"], f"{key} has no channels"
        for ch in spec["channels"]:
            assert ch in real, f"{key} names unknown channel {ch}"
