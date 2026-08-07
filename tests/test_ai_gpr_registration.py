"""Enforce the AI-GPR analysis freeze without running the benchmark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from src import ai_gpr_benchmark

ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "analysis" / "ai_gpr_benchmark_registration.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_registered_analysis_script_is_unchanged() -> None:
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    script = ROOT / registration["analysis_script"]
    assert _sha256(script) == registration["analysis_script_sha256"]


def test_registered_inputs_match_code_and_repository() -> None:
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    source = registration["source"]
    inputs = registration["igrm_inputs"]

    assert source["sha256"] == ai_gpr_benchmark.AI_GPR_SHA256
    assert source["data_through"] == ai_gpr_benchmark.AI_GPR_DATA_THROUGH
    assert inputs["history_sha256"] == ai_gpr_benchmark.IGRM_HISTORY_SHA256
    assert inputs["episodes_sha256"] == ai_gpr_benchmark.EPISODES_SHA256
    assert _sha256(ROOT / inputs["history_path"]) == inputs["history_sha256"]
    assert _sha256(ROOT / inputs["episodes_path"]) == inputs["episodes_sha256"]


def test_registration_closes_analyst_degrees_of_freedom() -> None:
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))

    assert registration["status"] == "REGISTERED BEFORE FIRST COMPARISON STATISTIC"
    assert registration["attestation"]["ai_gpr_file_was_already_in_hand"] is True
    assert registration["attestation"]["comparison_statistic_computed_before_freeze"] is False
    assert registration["sample"]["changes_bridge_excluded_months"] is False
    assert registration["inference"]["bootstrap_draws"] == 10_000
    assert registration["inference"]["primary_block_length_months"] == 6
    assert registration["inference"]["robustness_block_length_months"] == 12
    assert registration["publication"]["raw_ai_gpr_values_redistributed"] is False


def _ar1(seed: int, periods: int, phi: float = 0.65) -> np.ndarray:
    rng = np.random.default_rng(seed)
    shocks = rng.normal(size=periods)
    values = np.zeros(periods)
    for index in range(1, periods):
        values[index] = phi * values[index - 1] + shocks[index]
    return values


def test_registered_bootstrap_resamples_pairs_jointly_and_is_deterministic() -> None:
    index = pd.date_range("2000-01-01", periods=96, freq="MS")
    values = _ar1(11, len(index))
    pair = pd.DataFrame({"igrm": values, "ai_gpr": values * 3}, index=index)

    first = ai_gpr_benchmark._moving_block_ci(pair, 6, draws=400, seed=17)
    second = ai_gpr_benchmark._moving_block_ci(pair, 6, draws=400, seed=17)

    assert first == [1.0, 1.0]
    assert second == first


def test_registered_bootstrap_retains_short_segments_without_crossing_breaks() -> None:
    index = pd.DatetimeIndex(
        list(pd.date_range("2020-01-01", periods=4, freq="MS"))
        + list(pd.date_range("2020-09-01", periods=4, freq="MS"))
    )
    pair = pd.DataFrame(
        {"igrm": np.arange(8), "ai_gpr": np.array([1, 0, 3, 2, 5, 4, 7, 6])},
        index=index,
    )

    assert ai_gpr_benchmark._candidate_blocks(index, 6) == [list(range(4)), list(range(4, 8))]
    low, high = ai_gpr_benchmark._moving_block_ci(pair, 6, draws=200, seed=17)
    assert -1 <= low <= high <= 1


def test_registered_bootstrap_null_example_contains_zero() -> None:
    index = pd.date_range("2000-01-01", periods=240, freq="MS")
    pair = pd.DataFrame(
        {"igrm": _ar1(21, len(index)), "ai_gpr": _ar1(84, len(index))},
        index=index,
    )

    low, high = ai_gpr_benchmark._moving_block_ci(pair, 6, draws=1_000, seed=17)
    assert low < 0 < high
