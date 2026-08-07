"""Enforce the AI-GPR analysis freeze without running the benchmark."""

from __future__ import annotations

import hashlib
import json
import subprocess
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

    # Verified against the registration's OWN base_commit, not the working
    # tree.
    #
    # These two lines used to hash docs/data/history.csv on disk. That file
    # gains a row every morning, so the assertion would have failed on the
    # next daily publish and left CI red permanently -- confirmed by
    # simulating one nightly append. The check was right in spirit and
    # aimed at the wrong object: a registration RECORDS what was used, an
    # immutable historical fact, while the working tree is mutable by
    # design and the daily lane's whole job is to change it.
    #
    # Pinning to base_commit keeps the meaningful guarantee -- the
    # registered hashes really are the bytes that were analysed -- and it
    # stays true forever. Run-time protection is unchanged and lives where
    # it belongs: ai_gpr_benchmark._verify_local_inputs() refuses to run on
    # drifted inputs, which is what actually defends the registration.
    base = registration["base_commit"]
    for path_key, sha_key in (("history_path", "history_sha256"),
                              ("episodes_path", "episodes_sha256")):
        blob = subprocess.run(
            ["git", "show", f"{base}:{inputs[path_key]}"],
            cwd=ROOT, capture_output=True).stdout
        assert blob, (
            f"{inputs[path_key]} is not retrievable at base_commit {base[:12]}; "
            "the registration cannot be independently verified")
        assert hashlib.sha256(blob).hexdigest() == inputs[sha_key], (
            f"{inputs[path_key]} at base_commit {base[:12]} does not hash to "
            "the registered value; the registration misrecords what was analysed")


def test_the_script_still_refuses_to_run_on_drifted_inputs():
    """The protection the test above deliberately stopped duplicating.

    Moving the on-disk check out of CI is only safe because the analysis
    script enforces it at run time. If that enforcement is ever removed,
    the registration becomes decorative -- the benchmark would happily
    recompute against whatever history.csv happens to say today and still
    call itself preregistered.
    """
    src = (ROOT / "src" / "ai_gpr_benchmark.py").read_text(encoding="utf-8")
    assert "_verify_local_inputs" in src, "input verification is gone"
    assert "_verify_registration" in src, "the code-freeze check is gone"
    body = src.split("def _verify_local_inputs", 1)[1].split("\ndef ", 1)[0]
    assert "SystemExit" in body, (
        "_verify_local_inputs no longer refuses on a hash mismatch; the "
        "registration would not survive a changed input")


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
