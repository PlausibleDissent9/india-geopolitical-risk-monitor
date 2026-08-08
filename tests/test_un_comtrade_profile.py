from __future__ import annotations

import json
from pathlib import Path

import pytest
from src import publication_guard
from src import un_comtrade_profile as profile

ROOT = Path(__file__).resolve().parents[1]


def _policy() -> dict[str, object]:
    return profile._load_policy(ROOT / "governance" / "un_comtrade_acquisition.json")


def _row(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "period": "202401",
        "reporterCode": 699,
        "flowCode": "X",
        "partnerCode": 0,
        "partner2Code": 0,
        "cmdCode": "27",
        "customsCode": "C00",
        "motCode": 0,
        "isReported": False,
    }
    value.update(updates)
    return value


def _query() -> dict[str, object]:
    return {
        "period": "202401",
        "cmd_code": "27",
        "commodity": "mineral_fuels",
        "flow_code": "X",
    }


def test_policy_is_bounded_and_purchase_defaults_to_defer() -> None:
    policy = _policy()
    assert policy["decision"] == "evaluate_free_before_purchase"
    assert policy["rights_state"] == "review_required"
    assert policy["purchase_gate"]["direct_purchase_allowed"] is False
    assert policy["public_preview"]["origin"] == "https://comtradeapi.un.org"
    assert policy["public_preview"]["maximum_probe_calls"] == 24
    assert policy["public_preview"]["minimum_seconds_between_calls"] >= 1
    assert profile._url(policy, _query()).startswith(
        "https://comtradeapi.un.org/public/v1/preview/C/M/HS?"
    )
    assert "subscription-key" not in profile._url(policy, _query())


def test_query_matrix_is_small_deterministic_and_month_bounded() -> None:
    policy = _policy()
    queries = profile._queries(policy, ["202401", "202401", "202402"])
    assert len(queries) == 20
    assert queries[0] == {
        "period": "202401",
        "cmd_code": "10",
        "commodity": "cereals",
        "flow_code": "M",
    }
    with pytest.raises(profile.ProfileError, match="probe_call_budget_exceeded"):
        profile._queries(policy, ["202401", "202402", "202403"])
    for bad in ("2024", "202413", "not-a-month"):
        with pytest.raises(profile.ProfileError, match="period_invalid"):
            profile._queries(policy, [bad])


def test_profile_reduces_rows_to_structure_without_trade_values() -> None:
    policy = _policy()
    payload = {
        "count": 2,
        "error": "",
        "data": [
            _row(partnerCode=156),
            _row(
                partnerCode=784,
                partner2Code=156,
                motCode=7,
                customsCode="C01",
                isReported=True,
                primaryValue=999999999,
            ),
        ],
    }
    result = profile.profile_payload(policy, _query(), payload)
    assert result["distinct_partner_codes"] == 2
    assert result["rows_with_nonzero_mode_of_transport"] == 1
    assert result["rows_with_nondefault_customs_code"] == 1
    assert result["rows_with_second_partner"] == 1
    assert result["rows_marked_reported"] == 1
    encoded = json.dumps(result)
    assert "primaryValue" not in encoded
    assert "999999999" not in encoded


def test_missing_port_fields_and_transport_mode_never_establish_atlas_graph() -> None:
    policy = _policy()
    one = profile.profile_payload(
        policy,
        _query(),
        {"count": 1, "error": "", "data": [_row(motCode=7)]},
    )
    result = profile.summarize(policy, [one])
    assert result["rows_with_nonzero_mode_of_transport"] == 1
    assert result["port_fields_present"] == []
    assert result["atlas_joint_port_commodity_capability_established"] is False
    assert "trade_route" in result["premium_does_not_establish"]
    assert result["publication_allowed"] is False


def test_censored_preview_recommends_trial_not_purchase() -> None:
    policy = _policy()
    rows = [_row(partnerCode=index) for index in range(500)]
    one = profile.profile_payload(
        policy,
        _query(),
        {"count": 500, "error": "", "data": rows},
    )
    result = profile.summarize(policy, [one])
    assert result["premium_trial_recommended"] is True
    assert result["purchase_recommendation"] == "request_trial_before_purchase"


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({"count": 1, "error": "", "data": []}, "provider_payload_invalid"),
        ({"count": 1, "error": "boom", "data": [_row()]}, "provider_payload_invalid"),
        ({"count": 1, "error": "", "data": [{}]}, "provider_row_invalid"),
        (
            {"count": 1, "error": "", "data": [_row(reporterCode=156)]},
            "provider_row_scope_mismatch",
        ),
    ],
)
def test_provider_schema_and_scope_fail_closed(
    payload: dict[str, object], error: str
) -> None:
    with pytest.raises(profile.ProfileError, match=error):
        profile.profile_payload(_policy(), _query(), payload)


def test_live_probe_requires_explicit_internal_only_acknowledgement() -> None:
    with pytest.raises(
        profile.ProfileError,
        match="internal_evaluation_acknowledgement_required",
    ):
        profile.run_probe(["202401"], acknowledged=False)


def test_source_registry_remains_unsigned_and_deny_by_default() -> None:
    registry = json.loads(
        (ROOT / "governance" / "source_rights_registry.json").read_text()
    )
    source = next(item for item in registry["sources"] if item["source_id"] == "un_comtrade")
    assert source["decision_state"] == "review_required"
    assert source["permitted_uses"] == []
    assert source["signer_id"] is None
    assert source["decision_artifact_path"] is None
    _, strict_signers, _ = publication_guard._read_json(
        ROOT / "governance" / "rights_signers.json", "unreadable"
    )
    signers = publication_guard._validate_signers(strict_signers)
    _, strict_registry, _ = publication_guard._read_json(
        ROOT / "governance" / "source_rights_registry.json", "unreadable"
    )
    validated = publication_guard._validate_rights_registry(strict_registry, ROOT, signers)
    assert validated["un_comtrade"]["decision_state"] == "review_required"
