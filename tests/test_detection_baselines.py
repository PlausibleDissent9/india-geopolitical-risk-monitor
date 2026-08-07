"""Base-rate context must remain executable, exact, and publicly wired."""
from __future__ import annotations

import json
from pathlib import Path

from src import detection_baselines

ROOT = Path(__file__).resolve().parents[1]


def test_duration_preserving_placebo_baseline_reproduces_public_context() -> None:
    result = detection_baselines.compute_placebo()
    validation = json.loads(
        (ROOT / "docs" / "data" / "validation.json").read_text(encoding="utf-8")
    )["placebo"]
    n = validation["n_placebo_episodes"]
    observed = validation["n_overlapping"] / n
    chance = result["random_placement_overlap_fraction"]
    assert result["n_placebo_episodes"] == n == len(validation["episodes"])
    assert result["observed_overlaps"] == validation["n_overlapping"]
    assert result["observed_overlap_fraction"] == round(observed, 4)
    assert 0 <= result["geopolitical_episode_day_fraction"] <= 1
    assert 0 <= chance <= 1
    assert abs(result["random_placement_expected_overlaps"] - n * chance) <= 0.1
    assert result["excess_over_random_fraction"] == round(observed - chance, 4)
    assert result["registered_null"] is False


def test_public_baseline_payload_contains_both_denominators() -> None:
    public = json.loads(
        (ROOT / "docs" / "data" / "detection_baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert public["hit_rate_context"] == detection_baselines.compute()
    assert public["placebo_context"] == detection_baselines.compute_placebo()


def test_validation_page_labels_placebo_as_descriptive_negative_diagnostic() -> None:
    page = (ROOT / "docs" / "validation.html").read_text(encoding="utf-8")
    assert "Negative diagnostic" in page
    assert 'baselines.placebo_context' in page
    assert "No pass/fail null was registered" in page


def test_composite7_battery_runs_the_registered_rule_not_a_lookalike() -> None:
    """Referee F16 asked for the 29-event battery on the 7-day headline.
    The battery only answers it if the detection rule is the SIGNED T2
    convention -- a battery on an invented rule would be a new
    registration wearing an old one's name."""
    from src.alerts import MIN_TRAILING_OBS, PCTL_THRESHOLD, PCTL_WINDOW_DAYS
    b = detection_baselines.composite7_battery()
    rule = b["rule"]
    for value in (f"{int(PCTL_THRESHOLD*100)}th", str(PCTL_WINDOW_DAYS),
                  str(MIN_TRAILING_OBS)):
        assert value in rule, (
            f"the battery's stated rule does not quote the registered "
            f"constant {value}; either the rule drifted from src.alerts "
            "or the payload stopped saying what it runs")


def test_composite7_battery_arithmetic_is_internally_consistent() -> None:
    b = detection_baselines.composite7_battery()
    assert b["n_days_evaluable"] >= 2000, (
        "the evaluable window collapsed; a battery over a handful of "
        "days would be vacuous while looking authoritative")
    assert 0.02 <= b["elevated_day_fraction"] <= 0.30, (
        f"elevated fraction {b['elevated_day_fraction']} is far from the "
        "90th-percentile rule's neighbourhood; the threshold arithmetic "
        "has probably drifted")
    assert b["hits"] + len(b["events_missed"]) == b["n_events_evaluable"]
    assert b["n_events_evaluable"] <= b["n_events"]
    assert 0 < b["chance_expected_hits"] <= b["n_events_evaluable"]


def test_the_battery_is_in_the_public_payload() -> None:
    public = json.loads(
        (ROOT / "docs" / "data" / "detection_baselines.json").read_text(
            encoding="utf-8"
        )
    )
    assert public["composite7_battery"] == detection_baselines.composite7_battery()
