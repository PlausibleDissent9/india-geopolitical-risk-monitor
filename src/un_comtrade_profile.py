"""Bounded, non-publishing UN Comtrade acquisition profiler.

The profiler answers a purchase question; it is not a production data lane.
It uses the unauthenticated preview endpoint, retains no provider rows, and
emits only structural coverage counts.  A separate signed source-rights
decision is required before any UN Comtrade-derived public product exists.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "un_comtrade_acquisition.json"

_REQUIRED_ROW_FIELDS = {
    "period",
    "reporterCode",
    "flowCode",
    "partnerCode",
    "partner2Code",
    "cmdCode",
    "customsCode",
    "motCode",
    "isReported",
}
_PORT_FIELD_NAMES = {
    "portCode",
    "portDesc",
    "portOfEntry",
    "portOfExit",
    "originPort",
    "destinationPort",
}


class ProfileError(RuntimeError):
    """Stable refusal raised by the acquisition profiler."""


def _load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError("policy_unreadable") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "effective",
        "source_id",
        "decision",
        "rights_state",
        "public_preview",
        "sample_plan",
        "documented_plan_limits",
        "provider_documented_absences",
        "provider_documentation",
        "purchase_gate",
    }:
        raise ProfileError("policy_schema_invalid")
    if (
        value["schema_version"] != "1.0.0"
        or value["source_id"] != "un_comtrade"
        or value["decision"] != "evaluate_free_before_purchase"
        or value["rights_state"] != "review_required"
    ):
        raise ProfileError("policy_boundary_invalid")
    preview = value["public_preview"]
    if not isinstance(preview, dict) or set(preview) != {
        "origin",
        "path",
        "reporter_code",
        "reporter_name",
        "max_records",
        "timeout_seconds",
        "minimum_seconds_between_calls",
        "maximum_probe_calls",
    }:
        raise ProfileError("preview_policy_invalid")
    parsed = urlparse(preview["origin"])
    if parsed.scheme != "https" or parsed.netloc != "comtradeapi.un.org":
        raise ProfileError("preview_origin_invalid")
    if preview["path"] != "/public/v1/preview/C/M/HS":
        raise ProfileError("preview_path_invalid")
    if preview["reporter_code"] != 699 or preview["max_records"] != 500:
        raise ProfileError("preview_bounds_invalid")
    interval = preview["minimum_seconds_between_calls"]
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 1:
        raise ProfileError("preview_rate_limit_invalid")
    return value


def _period(value: str) -> str:
    if len(value) != 6 or not value.isdigit():
        raise ProfileError("period_invalid")
    year = int(value[:4])
    month = int(value[4:])
    if year < 1988 or year > 2100 or month < 1 or month > 12:
        raise ProfileError("period_invalid")
    return value


def _queries(policy: dict[str, Any], periods: list[str]) -> list[dict[str, Any]]:
    periods = list(dict.fromkeys(_period(value) for value in periods))
    if not periods:
        raise ProfileError("period_required")
    plan = policy["sample_plan"]
    flows = plan.get("flow_codes")
    commodities = plan.get("commodities")
    if flows != ["M", "X"] or not isinstance(commodities, list):
        raise ProfileError("sample_plan_invalid")
    result: list[dict[str, Any]] = []
    for period in periods:
        for commodity in commodities:
            if not isinstance(commodity, dict) or set(commodity) != {"cmd_code", "label"}:
                raise ProfileError("sample_plan_invalid")
            code = commodity["cmd_code"]
            if not isinstance(code, str) or not code.isdigit() or len(code) != 2:
                raise ProfileError("sample_plan_invalid")
            for flow in flows:
                result.append(
                    {
                        "period": period,
                        "cmd_code": code,
                        "commodity": commodity["label"],
                        "flow_code": flow,
                    }
                )
    if len(result) > policy["public_preview"]["maximum_probe_calls"]:
        raise ProfileError("probe_call_budget_exceeded")
    return result


def _url(policy: dict[str, Any], query: dict[str, Any]) -> str:
    preview = policy["public_preview"]
    params = {
        "period": query["period"],
        "reporterCode": preview["reporter_code"],
        "cmdCode": query["cmd_code"],
        "flowCode": query["flow_code"],
        "maxRecords": preview["max_records"],
    }
    url = f"{preview['origin']}{preview['path']}?{urlencode(params)}"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "comtradeapi.un.org":
        raise ProfileError("request_target_invalid")
    return url


def _fetch(policy: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
    try:
        response = requests.get(
            _url(policy, query),
            timeout=policy["public_preview"]["timeout_seconds"],
            allow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "IGRM-acquisition-profiler/1.0"},
        )
    except requests.RequestException as exc:
        raise ProfileError("provider_unreachable") from exc
    if 300 <= response.status_code < 400:
        raise ProfileError("provider_redirect_refused")
    if response.status_code != 200:
        raise ProfileError(f"provider_http_{response.status_code}")
    try:
        value = response.json()
    except requests.JSONDecodeError as exc:
        raise ProfileError("provider_json_invalid") from exc
    if not isinstance(value, dict):
        raise ProfileError("provider_payload_invalid")
    return value


def profile_payload(
    policy: dict[str, Any], query: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """Reduce one provider response to non-row structural coverage."""

    if set(query) != {"period", "cmd_code", "commodity", "flow_code"}:
        raise ProfileError("query_schema_invalid")
    data = payload.get("data")
    count = payload.get("count")
    error = payload.get("error")
    if not isinstance(data, list) or isinstance(count, bool) or not isinstance(count, int):
        raise ProfileError("provider_payload_invalid")
    if error not in ("", None) or count != len(data):
        raise ProfileError("provider_payload_invalid")
    mot_nonzero = 0
    customs_nondefault = 0
    partner2_nonzero = 0
    reported = 0
    port_fields: set[str] = set()
    partners: set[int] = set()
    for row in data:
        if not isinstance(row, dict) or not _REQUIRED_ROW_FIELDS.issubset(row):
            raise ProfileError("provider_row_invalid")
        if (
            str(row["period"]) != query["period"]
            or row["reporterCode"] != policy["public_preview"]["reporter_code"]
            or str(row["cmdCode"]) != query["cmd_code"]
            or row["flowCode"] != query["flow_code"]
        ):
            raise ProfileError("provider_row_scope_mismatch")
        if any(isinstance(row[field], bool) or not isinstance(row[field], int) for field in ("partnerCode", "partner2Code", "motCode")):
            raise ProfileError("provider_row_type_invalid")
        if not isinstance(row["customsCode"], str) or not isinstance(row["isReported"], bool):
            raise ProfileError("provider_row_type_invalid")
        partners.add(row["partnerCode"])
        mot_nonzero += int(row["motCode"] != 0)
        customs_nondefault += int(row["customsCode"] not in {"", "C00"})
        partner2_nonzero += int(row["partner2Code"] != 0)
        reported += int(row["isReported"])
        port_fields.update(_PORT_FIELD_NAMES.intersection(row))
    max_records = policy["public_preview"]["max_records"]
    return {
        "period": query["period"],
        "cmd_code": query["cmd_code"],
        "commodity": query["commodity"],
        "flow_code": query["flow_code"],
        "rows_returned": count,
        "preview_censored": count >= max_records,
        "distinct_partner_codes": len(partners),
        "rows_with_nonzero_mode_of_transport": mot_nonzero,
        "rows_with_nondefault_customs_code": customs_nondefault,
        "rows_with_second_partner": partner2_nonzero,
        "rows_marked_reported": reported,
        "port_fields_present": sorted(port_fields),
    }


def summarize(policy: dict[str, Any], profiles: list[dict[str, Any]]) -> dict[str, Any]:
    if not profiles:
        raise ProfileError("profiles_required")
    censored = sum(int(item["preview_censored"]) for item in profiles)
    mot_rows = sum(item["rows_with_nonzero_mode_of_transport"] for item in profiles)
    port_fields = sorted({field for item in profiles for field in item["port_fields_present"]})
    trial_needed = censored > 0
    return {
        "schema_version": "1.0.0",
        "status": "internal_acquisition_evaluation_only",
        "source_id": policy["source_id"],
        "rights_state": policy["rights_state"],
        "queries_attempted": len(profiles),
        "queries_censored_at_preview_limit": censored,
        "rows_with_nonzero_mode_of_transport": mot_rows,
        "port_fields_present": port_fields,
        "atlas_joint_port_commodity_capability_established": False,
        "premium_trial_recommended": trial_needed,
        "purchase_recommendation": (
            "request_trial_before_purchase" if trial_needed else "defer_premium_use_basic"
        ),
        "reason": (
            "At least one preview query hit the 500-row ceiling; measure the free key and "
            "premium trial before purchase."
            if trial_needed
            else "The bounded profile did not hit the public-preview ceiling; test the free "
            "Basic API before paying for throughput."
        ),
        "premium_does_not_establish": policy["purchase_gate"]["premium_never_establishes"],
        "publication_allowed": False,
    }


def run_probe(periods: list[str], *, acknowledged: bool) -> dict[str, Any]:
    if not acknowledged:
        raise ProfileError("internal_evaluation_acknowledgement_required")
    policy = _load_policy()
    profiles: list[dict[str, Any]] = []
    last_started: float | None = None
    interval = policy["public_preview"]["minimum_seconds_between_calls"]
    for query in _queries(policy, periods):
        now = time.monotonic()
        if last_started is not None:
            time.sleep(max(0.0, interval - (now - last_started)))
        last_started = time.monotonic()
        profiles.append(profile_payload(policy, query, _fetch(policy, query)))
    return summarize(policy, profiles)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("period", nargs="+", help="One or two YYYYMM India periods")
    parser.add_argument(
        "--acknowledge-internal-evaluation",
        action="store_true",
        help="Confirm that this is a non-publishing acquisition probe",
    )
    args = parser.parse_args()
    try:
        result = run_probe(
            args.period,
            acknowledged=args.acknowledge_internal_evaluation,
        )
    except ProfileError as exc:
        raise SystemExit(f"un_comtrade_profile: refused: {exc}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
