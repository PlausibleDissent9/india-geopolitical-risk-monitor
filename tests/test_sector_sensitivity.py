"""Sector sensitivity: signed-only gating and cell arithmetic."""
from __future__ import annotations

import json

import pandas as pd
from src import sector_sensitivity


def test_only_signed_mappings_run(tmp_path, monkeypatch):
    root = tmp_path
    (root / "sectors.json").write_text(json.dumps({"sectors": {
        "mapped": {"label": "M", "channels": ["shipping"],
                   "nse_index": "^X"},
        "unmapped": {"label": "U", "channels": ["shipping"],
                     "nse_index": None},
    }}), encoding="utf-8")
    monkeypatch.setattr(sector_sensitivity, "ROOT", root)
    m = sector_sensitivity.signed_mappings()
    assert list(m) == ["mapped"]


def test_cells_carry_n_ci_and_bh_flag():
    idx = pd.date_range("2020-01-01", periods=400, freq="D")
    rel = pd.DataFrame({"^X": [0.5] * 400}, index=idx)
    episodes = [{"channel": "shipping", "start": "2020-03-01"},
                {"channel": "shipping", "start": "2020-06-01"},
                {"channel": "shipping", "start": "2020-09-01"}]
    mappings = {"s": {"label": "S", "channels": ["shipping"],
                      "nse_index": "^X"}}
    out = sector_sensitivity.sensitivity_cells(mappings, episodes, rel)
    cell = out["s"]["channels"]["shipping"]["5"]
    assert cell["n"] == 3
    assert cell["mean"] == 2.5  # five 0.5% days
    assert "bh_significant_10pct" in cell
    assert cell["ci95"][0] <= cell["mean"] <= cell["ci95"][1]
