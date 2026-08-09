"""Historical Intelligence v1 must not be able to overstate itself.

The archive is the oldest and least checkable thing the site publishes:
nobody reading a 1984 number can feel it is wrong the way they would feel
a wrong number for yesterday. So the guards here are about the failure
modes that would be invisible.

  denominator reconciliation  a mean must state what it averaged over,
                              and coverage must equal observed/calendar
  break stability             a candidate break that moves when the
                              settings move must SAY it moves
  analog determinism          the same query is the same answer, forever
  future leakage              nothing dated after the archive's registered
                              end may attach to a historical view
  null handling               a missing feature is excluded and named,
                              never imputed and never zero
  release identity            the payload pins the contract, the source
                              and the implementation it was built from
  public copy                 no forecast vocabulary, no causal claim

The construct warning matters most. The archive measures monthly
event-mention share under frozen filters -- press attention. Every one of
these tests exists so the page cannot quietly become a history of events.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from src import historical_intelligence as hi

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_PATH = ROOT / "docs" / "data" / "historical_intelligence.json"
CONTRACT_PATH = ROOT / "governance" / "historical_intelligence_contract.json"


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- denominators
def test_every_baseline_states_the_denominator_it_averaged_over(payload):
    for row in payload["regime_baselines"]["rows"]:
        assert row["n_months_in_period"] > 0, row
        assert row["n_observed"] is not None, row
        assert row["n_observed"] <= row["n_months_in_period"], row


def test_coverage_fraction_reconciles_with_its_own_counts(payload):
    """A coverage number that does not equal observed/calendar is the kind
    of thing that survives review for years."""
    for row in payload["regime_baselines"]["rows"]:
        expected = row["n_observed"] / row["n_months_in_period"]
        assert abs(row["coverage_fraction"] - expected) < 5e-5, row


def test_a_thin_period_refuses_instead_of_averaging_what_is_there(payload,
                                                                  contract):
    minimum = contract["regime_baselines"]["min_observed_months"]
    for row in payload["regime_baselines"]["rows"]:
        if row["n_observed"] < minimum:
            assert row["available"] is False, row
            assert row["unavailable_reason"], row
            for stat in ("mean", "median", "p90", "max", "min"):
                assert row[stat] is None, (
                    f"{row['channel']} {row['period_id']} published {stat} "
                    f"over {row['n_observed']} months")


def test_no_statistic_is_ever_zero_substituted(payload):
    """Unavailable must be null. A zero is a number, and a reader cannot
    tell a computed zero from a missing one."""
    for row in payload["regime_baselines"]["rows"]:
        if not row["available"]:
            assert all(row[s] is None for s in
                       ("mean", "median", "p90", "max", "min")), row


def test_baseline_periods_are_exactly_the_registered_ones(payload, contract):
    registered = {p["id"] for p in contract["regime_baselines"]["periods"]}
    published = {r["period_id"] for r in payload["regime_baselines"]["rows"]}
    assert published == registered


# ------------------------------------------------------------- break stability
def test_a_break_that_moves_with_the_settings_says_so(payload):
    """The sweep is the honesty. A single candidate reported alone would
    read as a finding; the same candidate reported beside the settings
    that move it reads as what it is."""
    for row in payload["structural_breaks"]["rows"]:
        distinct = row["distinct_candidates_across_settings"]
        assert row["stable_across_all_settings"] == (len(distinct) == 1), row
        assert len(row["sensitivity_sweep"]) >= 2, row


def test_every_break_carries_its_null_and_its_permutation_count(payload):
    for row in payload["structural_breaks"]["rows"]:
        for entry in row["sensitivity_sweep"]:
            if not entry["available"]:
                assert entry["p_value"] is None and entry["statistic"] is None
                assert entry["unavailable_reason"]
                continue
            assert 0.0 < entry["p_value"] <= 1.0, entry
            assert entry["n_permutations"] >= 1000, entry
            assert entry["statistic"] >= 0.0, entry


def test_break_language_never_claims_a_cause(payload):
    """Scan the RESULTS, not the rules.

    The first version of this scanned the whole structural_breaks block and
    failed on 'turning point' -- inside the language rule that forbids the
    phrase. A claim linter that cannot tell a disclaimer from a claim will
    either be switched off or answered by deleting the disclaimer, and both
    are worse than no linter.
    """
    results = json.dumps(payload["structural_breaks"]["rows"]).lower()
    for forbidden in ("caused", "because of", "triggered by", "led to",
                      "explains the"):
        assert forbidden not in results, forbidden
    for row in payload["structural_breaks"]["rows"]:
        assert "not a historical cause" in row["interpretation"].lower()
    rule = payload["structural_breaks"]["language_rule"].lower()
    for refused in ("historical cause", "turning point", "regime change"):
        assert refused in rule, (
            f"the language rule no longer refuses {refused!r}")


def test_the_break_scan_is_deterministic_for_a_fixed_series():
    """Same values, same settings, same answer -- the permutation null is
    seeded, so a p-value must not wander between runs."""
    values = [0.1] * 60 + [0.4] * 60
    first = hi._max_welch_t(values, 24)
    second = hi._max_welch_t(values, 24)
    assert first == second
    assert first[1] == 60, "the split between two flat halves is at 60"


# --------------------------------------------------------- analog determinism
def test_the_same_query_returns_the_same_ordered_analogs(payload):
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    source = json.loads((ROOT / "docs" / "data" / "back_extension.json")
                        .read_text(encoding="utf-8"))
    rebuilt, _ = hi.analog_index(contract, source["series"])
    for channel, entries in payload["analog_retrieval"]["by_channel"].items():
        for month, entry in entries.items():
            got = rebuilt[channel][month]
            assert [a["month"] for a in got["analogs"]] == \
                   [a["month"] for a in entry["analogs"]], (channel, month)


def test_analog_distances_are_sorted_and_non_negative(payload):
    for channel, entries in payload["analog_retrieval"]["by_channel"].items():
        for month, entry in entries.items():
            dists = [a["distance"] for a in entry["analogs"]]
            assert all(d >= 0 for d in dists), (channel, month)
            assert dists == sorted(dists), (channel, month)


def test_no_analog_is_inside_the_registered_exclusion_window(payload, contract):
    window = contract["analog_retrieval"]["exclusion_window_months"]
    for channel, entries in payload["analog_retrieval"]["by_channel"].items():
        for month, entry in entries.items():
            for a in entry["analogs"]:
                gap = abs(hi._month_index(a["month"]) - hi._month_index(month))
                assert gap > window, (channel, month, a["month"])


# --------------------------------------------------------------- null handling
def test_a_null_feature_is_excluded_and_named_never_imputed(payload, contract):
    ids = {f["id"] for f in contract["analog_retrieval"]["features"]}
    minimum = contract["analog_retrieval"]["min_features_for_match"]
    for channel, entries in payload["analog_retrieval"]["by_channel"].items():
        for month, entry in entries.items():
            for a in entry["analogs"]:
                used = set(a["features_used"])
                excluded = set(a["features_excluded_as_null"])
                assert used | excluded == ids, (channel, month, a)
                assert not (used & excluded), (channel, month, a)
                assert a["n_features_used"] == len(used)
                assert len(used) >= minimum, (channel, month, a)


def test_a_month_without_enough_features_refuses_with_a_reason(payload):
    refused = [
        (c, m) for c, entries in payload["analog_retrieval"]["by_channel"].items()
        for m, e in entries.items() if not e["available"]
    ]
    for channel, month in refused:
        entry = payload["analog_retrieval"]["by_channel"][channel][month]
        assert entry["analogs"] == []
        assert entry["unavailable_reason"]


def test_the_first_archive_months_are_the_refused_ones(payload):
    """The trailing-ten-year percentile is undefined early, so the early
    archive is exactly where features run out. If refusals ever appear
    somewhere else, something changed about the source."""
    for channel, entries in payload["analog_retrieval"]["by_channel"].items():
        refused = sorted(m for m, e in entries.items() if not e["available"])
        if refused:
            assert refused[0].startswith("1979"), (channel, refused[:3])


# ------------------------------------------------------------- future leakage
def test_nothing_dated_after_the_cutoff_is_published_as_available(payload):
    cutoff = payload["_meta"]["knowledge_cutoff"]["archive_end"]
    limit = hi._month_index(cutoff)
    for row in payload["event_archetypes"]["rows"]:
        if row["month"] and hi._month_index(row["month"]) > limit:
            assert row["available"] is False, row
            assert "cutoff" in row["unavailable_reason"].lower(), row


def test_a_post_cutoff_archetype_is_refused_rather_than_dropped(contract):
    """Dropping it would hide the leak. The refusal is the record."""
    source = {"anchor_grades": [
        {"month": "2024-05", "channel": "pakistan_west",
         "anchor": "an annotation from after the archive ended"},
    ]}
    rows = hi.archetypes(contract, source)
    assert len(rows) == 1, "the post-cutoff anchor was dropped, not refused"
    assert rows[0]["available"] is False
    assert "cutoff" in rows[0]["unavailable_reason"].lower()


def test_no_baseline_period_extends_past_the_archive(payload, contract):
    cutoff = hi._month_index(contract["knowledge_cutoff"]["archive_end"])
    for period in contract["regime_baselines"]["periods"]:
        assert hi._month_index(period["end"]) <= cutoff, period


# ----------------------------------------------------------- archetype policy
def test_no_archetype_is_machine_generated(payload):
    assert payload["event_archetypes"]["machine_generated_permitted"] is False
    for row in payload["event_archetypes"]["rows"]:
        assert row["authorship"] == "human_authored_at_registration", row


def test_archetypes_for_refused_channels_are_marked_unavailable(payload):
    eligible = set(payload["channel_eligibility"]["eligible"])
    for row in payload["event_archetypes"]["rows"]:
        if row["channel"] not in eligible:
            assert row["available"] is False, row
            assert row["unavailable_reason"], row


# ----------------------------------------------------------- release identity
def test_the_payload_pins_what_it_was_built_from(payload):
    meta = payload["_meta"]
    for field in ("contract_sha256", "source_sha256", "implementation_sha256"):
        assert re.fullmatch(r"[0-9a-f]{64}", meta[field]), field


def test_the_pinned_hashes_are_the_files_on_disk(payload):
    meta = payload["_meta"]
    assert meta["contract_sha256"] == hi._sha256(CONTRACT_PATH)
    assert meta["source_sha256"] == hi._sha256(hi.SOURCE_PATH)
    assert meta["implementation_sha256"] == hi._sha256(
        ROOT / "src" / "historical_intelligence.py")


def test_the_committed_payload_is_exactly_what_the_code_builds(payload):
    """The whole point of a citable payload: a reader can regenerate it."""
    rebuilt = hi.build()
    assert rebuilt["regime_baselines"]["rows"] == \
        payload["regime_baselines"]["rows"]
    assert rebuilt["structural_breaks"]["rows"] == \
        payload["structural_breaks"]["rows"]
    assert rebuilt["event_archetypes"]["rows"] == \
        payload["event_archetypes"]["rows"]


# --------------------------------------------------------------- public copy
FORECAST_WORDS = [
    "will repeat", "predicts", "prediction", "forecast", "we expect",
    "likely to recur", "history says", "history shows that", "bound to",
    "signals that india will",
]


def test_the_payload_contains_no_forecast_vocabulary(payload):
    text = json.dumps(payload).lower()
    for phrase in FORECAST_WORDS:
        assert phrase not in text, phrase


def test_the_payload_states_it_measures_attention_not_events(payload):
    text = json.dumps(payload).lower()
    assert "attention" in text
    assert any(p in text for p in ("not conflict", "not a historical cause",
                                   "different construct"))


def test_refused_channels_travel_with_the_output(payload):
    refused = payload["channel_eligibility"]["refused"]
    assert set(refused) >= {"us_trade", "gulf_energy", "shipping"}
    for channel, reason in refused.items():
        assert reason and len(reason) > 20, channel


def test_limitations_are_published_not_just_registered(payload):
    assert len(payload["limitations"]) >= 4
    text = " ".join(payload["limitations"]).lower()
    assert "attention" in text
