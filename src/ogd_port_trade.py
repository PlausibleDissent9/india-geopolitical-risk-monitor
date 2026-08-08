"""Validate and compile the OGD India port-country-commodity baseline.

The Open Government Data Platform publishes two 2019-20 CSV extracts from the
Ministry of Ports, Shipping and Waterways.  Unlike the current monthly report,
these files contain joint country x commodity x port observations.  This module
preserves source zeros, source ``NA`` cells, rounding residuals, fiscal vintage
and the provider's ambiguous country heading in the loaded-cargo table.

Validation is usable before a rights decision.  Compilation is default-deny and
requires an approved, signed source decision through IGRM's rights registry.
Neither mode invents firm, route, shipment or current-period coverage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import unquote, urlsplit

from src import publication_guard

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "ogd_port_trade_baseline.json"
RIGHTS_PATH = ROOT / "governance" / "source_rights_registry.json"
SIGNERS_PATH = ROOT / "governance" / "rights_signers.json"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_EXPECTED_HEADER = [
    "Commodities",
    "Country of Origin",
    "SMP (KDS)",
    "SMP(HDC)",
    "PPT",
    "VPT",
    "KPL",
    "ChPT",
    "V.O.C",
    "CoPT",
    "NMPT",
    "MoPT",
    "JNPT",
    "MbPT",
    "DPT",
    "ALL PORTS",
]


class OGDPortTradeError(ValueError):
    """Stable fail-closed error raised by the baseline compiler."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise OGDPortTradeError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _read_object(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OGDPortTradeError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _digest(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        _fail(code)
    return value


def _day(value: object, code: str) -> str:
    text = _text(value, code)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise OGDPortTradeError(code) from exc
    return text


def _timestamp(value: object, code: str) -> str:
    text = _text(value, code)
    if not text.endswith("Z"):
        _fail(code)
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise OGDPortTradeError(code) from exc
    return text


def _safe_url(value: object, allowed_paths: list[str], code: str) -> str:
    url = _text(value, code)
    parsed = urlsplit(url)
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.data.gov.in"
        or not any(parsed.path.startswith(prefix) for prefix in allowed_paths)
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or unquote(decoded_path) != decoded_path
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _fail(code)
    return url


def _registry(path: Path = REGISTRY_PATH) -> tuple[dict[str, Any], str]:
    value, digest = _read_object(path, "registry_unreadable")
    registry = _object(
        value,
        {
            "schema_version",
            "effective",
            "status",
            "source",
            "implementation",
            "period",
            "unit_evidence",
            "port_frame",
            "artifacts",
            "limits",
        },
        "registry_fields_invalid",
    )
    if registry["schema_version"] != "1.0.0" or registry["status"] != (
        "acquired_rights_review_required"
    ):
        _fail("registry_identity_invalid")
    _day(registry["effective"], "registry_effective_invalid")

    source = _object(
        registry["source"],
        {
            "source_id",
            "catalog_url",
            "license_url",
            "allowed_file_path_prefixes",
            "required_permitted_uses",
        },
        "registry_source_invalid",
    )
    if not isinstance(source["source_id"], str) or not _ID.fullmatch(source["source_id"]):
        _fail("registry_source_id_invalid")
    allowed_paths = source["allowed_file_path_prefixes"]
    if allowed_paths != [
        "/files/ogdpv2dms/s3fs-public/datafile/",
        "/sites/default/files/datafile/",
    ]:
        _fail("registry_allowed_paths_invalid")
    _safe_url(source["catalog_url"], ["/catalog/"], "registry_catalog_url_invalid")
    _safe_url(source["license_url"], ["/sites/default/files/"], "registry_license_url_invalid")
    if source["required_permitted_uses"] != [
        "cite_metadata",
        "publish_derived_value",
        "publish_extract",
    ]:
        _fail("registry_required_uses_invalid")

    implementation = _object(
        registry["implementation"], {"path", "sha256"}, "registry_implementation_invalid"
    )
    if implementation["path"] != "src/ogd_port_trade.py":
        _fail("registry_implementation_invalid")
    expected_implementation = _digest(
        implementation["sha256"], "registry_implementation_digest_invalid"
    )
    implementation_path = path.parents[1] / implementation["path"]
    try:
        actual_implementation = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OGDPortTradeError("implementation_unreadable") from exc
    if actual_implementation != expected_implementation:
        _fail("implementation_digest_mismatch")

    period = _object(
        registry["period"], {"label", "start", "end", "status"}, "registry_period_invalid"
    )
    if period != {
        "label": "2019-20",
        "start": "2019-04-01",
        "end": "2020-03-31",
        "status": "historical_baseline_not_current",
    }:
        _fail("registry_period_invalid")

    unit = _object(
        registry["unit_evidence"],
        {"unit", "source_url", "source_sha256", "table_ids", "pdf_pages"},
        "registry_unit_evidence_invalid",
    )
    if (
        unit["unit"] != "thousand_metric_tonnes"
        or unit["table_ids"] != ["2.1.6", "2.1.7"]
        or unit["pdf_pages"] != [105, 118]
    ):
        _fail("registry_unit_evidence_invalid")
    _digest(unit["source_sha256"], "registry_unit_digest_invalid")
    parsed_pdf = urlsplit(_text(unit["source_url"], "registry_unit_url_invalid"))
    if parsed_pdf.scheme != "https" or parsed_pdf.netloc not in {
        "shipmin.gov.in",
        "www.shipmin.gov.in",
    }:
        _fail("registry_unit_url_invalid")

    ports = _object(
        registry["port_frame"],
        {"frame_id", "columns", "member_count", "scope", "excluded_scope"},
        "registry_port_frame_invalid",
    )
    if (
        ports["frame_id"] != "india_major_port_table_columns_2019_20"
        or ports["columns"] != _EXPECTED_HEADER[2:-1]
        or ports["member_count"] != 13
    ):
        _fail("registry_port_frame_invalid")
    _text(ports["scope"], "registry_port_scope_invalid")
    _text(ports["excluded_scope"], "registry_port_excluded_invalid")

    artifacts = registry["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != 2:
        _fail("registry_artifacts_invalid")
    seen_flows: set[str] = set()
    for raw in artifacts:
        artifact = _object(
            raw,
            {
                "flow",
                "resource_uuid",
                "resource_url",
                "declared_file_url",
                "retrieval_url",
                "sha256",
                "file_size_bytes",
                "published_on",
                "updated_on",
                "retrieved_at",
                "expected_rows",
                "expected_summary_rows",
                "expected_detail_rows",
                "country_semantics",
            },
            "registry_artifact_invalid",
        )
        flow = artifact["flow"]
        if flow not in {"unloaded", "loaded"} or flow in seen_flows:
            _fail("registry_artifact_flow_invalid")
        seen_flows.add(flow)
        _safe_url(artifact["resource_url"], ["/resource/"], "registry_resource_url_invalid")
        _safe_url(artifact["declared_file_url"], allowed_paths, "registry_file_url_invalid")
        _safe_url(artifact["retrieval_url"], allowed_paths, "registry_file_url_invalid")
        _digest(artifact["sha256"], "registry_artifact_digest_invalid")
        for field in (
            "file_size_bytes",
            "expected_rows",
            "expected_summary_rows",
            "expected_detail_rows",
        ):
            if (
                isinstance(artifact[field], bool)
                or not isinstance(artifact[field], int)
                or artifact[field] <= 0
            ):
                _fail("registry_artifact_count_invalid")
        _day(artifact["published_on"], "registry_artifact_published_invalid")
        _day(artifact["updated_on"], "registry_artifact_updated_invalid")
        _timestamp(artifact["retrieved_at"], "registry_artifact_retrieved_invalid")
        if (
            artifact["expected_rows"]
            != artifact["expected_summary_rows"] + artifact["expected_detail_rows"]
        ):
            _fail("registry_artifact_count_invalid")
        expected_semantics = (
            "country_of_origin"
            if flow == "unloaded"
            else "provider_heading_says_country_of_origin_for_loaded_cargo_destination_not_asserted"
        )
        if artifact["country_semantics"] != expected_semantics:
            _fail("registry_country_semantics_invalid")
    if seen_flows != {"unloaded", "loaded"}:
        _fail("registry_artifacts_invalid")

    limits = registry["limits"]
    if (
        not isinstance(limits, list)
        or len(limits) < 6
        or any(not isinstance(item, str) or not item for item in limits)
    ):
        _fail("registry_limits_invalid")
    return registry, digest


def _quantity(token: str) -> int | None:
    text = token.strip().replace(",", "")
    if text in {"NA", "-"}:
        return None
    if not re.fullmatch(r"0|[1-9][0-9]*", text):
        _fail("csv_quantity_invalid")
    return int(text)


def _label(token: str) -> str:
    text = token.strip()
    if (
        not text
        or len(text) > 200
        or text[0] in {"=", "+", "-", "@"}
        or any(ord(character) < 32 for character in text)
    ):
        _fail("csv_identity_invalid")
    return text


def _artifact_for_flow(registry: dict[str, Any], flow: str) -> dict[str, Any]:
    return next(row for row in registry["artifacts"] if row["flow"] == flow)


def profile_artifact(path: Path, *, flow: str, registry: dict[str, Any]) -> dict[str, Any]:
    artifact = _artifact_for_flow(registry, flow)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise OGDPortTradeError("csv_unreadable") from exc
    if len(raw) != artifact["file_size_bytes"]:
        _fail("csv_size_mismatch")
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        _fail("csv_digest_mismatch")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise OGDPortTradeError("csv_parse_invalid") from exc
    if not rows or rows[0] != _EXPECTED_HEADER:
        _fail("csv_header_invalid")
    data_rows = rows[1:]
    if len(data_rows) != artifact["expected_rows"] or any(
        len(row) != len(_EXPECTED_HEADER) for row in data_rows
    ):
        _fail("csv_row_count_or_width_invalid")

    port_columns = _EXPECTED_HEADER[2:-1]
    seen: set[tuple[str, str]] = set()
    commodities: list[str] = []
    detail_rows: list[dict[str, Any]] = []
    summary_rows: dict[str, dict[str, Any]] = {}
    missing_cells = 0
    observed_zero_cells = 0
    nonzero_cells = 0
    row_drift_histogram: dict[str, int] = defaultdict(int)
    unidentified_quantity = 0

    for line_number, row in enumerate(data_rows, 2):
        commodity = _label(row[0])
        country = _label(row[1])
        key = (commodity, country)
        if key in seen:
            _fail("csv_identity_duplicate")
        seen.add(key)
        if commodity not in commodities:
            commodities.append(commodity)
        cells = {port: _quantity(row[index + 2]) for index, port in enumerate(port_columns)}
        total = _quantity(row[-1])
        if total is None:
            _fail("csv_all_ports_total_missing")
        present_total = sum(value for value in cells.values() if value is not None)
        drift = present_total - total
        if drift < -2 and all(value is not None for value in cells.values()):
            _fail("csv_row_reconciliation_invalid")
        if drift > 2:
            _fail("csv_row_reconciliation_invalid")
        row_drift_histogram[str(drift)] += 1
        if country.casefold() == "total":
            if commodity in summary_rows:
                _fail("csv_summary_duplicate")
            summary_rows[commodity] = {
                "commodity": commodity,
                "ports": cells,
                "all_ports": total,
                "line_number": line_number,
                "reconciliation_drift": drift,
            }
            continue
        unidentified_quantity += max(total - present_total, 0)
        for value in cells.values():
            if value is None:
                missing_cells += 1
            elif value == 0:
                observed_zero_cells += 1
            else:
                nonzero_cells += 1
        detail_rows.append(
            {
                "commodity": commodity,
                "reported_country": country,
                "ports": cells,
                "all_ports": total,
                "line_number": line_number,
                "reconciliation_drift": drift,
            }
        )

    if (
        len(detail_rows) != artifact["expected_detail_rows"]
        or len(summary_rows) != artifact["expected_summary_rows"]
        or set(summary_rows) != set(commodities)
    ):
        _fail("csv_summary_or_detail_coverage_invalid")
    for commodity in commodities:
        detail_total = sum(row["all_ports"] for row in detail_rows if row["commodity"] == commodity)
        summary_total = summary_rows[commodity]["all_ports"]
        if abs(detail_total - summary_total) > 2:
            _fail("csv_commodity_total_reconciliation_invalid")

    expected_cells = len(detail_rows) * len(port_columns)
    if missing_cells + observed_zero_cells + nonzero_cells != expected_cells:
        _fail("csv_cell_partition_invalid")
    return {
        "flow": flow,
        "artifact_sha256": artifact["sha256"],
        "country_semantics": artifact["country_semantics"],
        "unit": registry["unit_evidence"]["unit"],
        "commodities": commodities,
        "port_columns": port_columns,
        "detail_rows": detail_rows,
        "summary_rows": [summary_rows[item] for item in commodities],
        "coverage": {
            "detail_rows": len(detail_rows),
            "summary_rows": len(summary_rows),
            "port_columns": len(port_columns),
            "expected_joint_cells": expected_cells,
            "observed_nonzero_cells": nonzero_cells,
            "observed_zero_cells": observed_zero_cells,
            "source_missing_cells": missing_cells,
            "observed_cell_rate": round((expected_cells - missing_cells) / expected_cells, 8),
        },
        "reconciliation": {
            "row_drift_histogram_thousand_tonnes": dict(sorted(row_drift_histogram.items())),
            "maximum_allowed_absolute_rounding_drift": 2,
            "unidentified_quantity_lower_bound_thousand_tonnes": unidentified_quantity,
        },
    }


def _approved_source(
    *, root: Path, registry: dict[str, Any], rights_path: Path, signers_path: Path
) -> dict[str, Any]:
    try:
        _, signer_document, _ = publication_guard._read_json(
            signers_path, "rights_signers_unreadable"
        )
        signers = publication_guard._validate_signers(signer_document)
        _, rights_document, _ = publication_guard._read_json(
            rights_path, "rights_registry_unreadable"
        )
        rights = publication_guard._validate_rights_registry(rights_document, root, signers)
    except publication_guard.PublicationGuardError as exc:
        raise OGDPortTradeError(f"rights_{exc.code}") from exc
    source = rights.get(registry["source"]["source_id"])
    if source is None or source["decision_state"] != "approved":
        _fail("rights_not_approved")
    if not set(registry["source"]["required_permitted_uses"]).issubset(source["permitted_uses"]):
        _fail("rights_use_not_approved")
    return source


def _candidate_cells(profile: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in profile["detail_rows"]:
        for port, value in row["ports"].items():
            if value is None or value == 0:
                continue
            material = "|".join((profile["flow"], row["commodity"], row["reported_country"], port))
            result.append(
                {
                    "observation_id": "ogdpt:" + hashlib.sha256(material.encode()).hexdigest()[:24],
                    "flow": profile["flow"],
                    "commodity": row["commodity"],
                    "reported_country": row["reported_country"],
                    "country_semantics": profile["country_semantics"],
                    "port_column": port,
                    "quantity": value,
                    "unit": profile["unit"],
                    "source_line": row["line_number"],
                    "row_all_ports_quantity": row["all_ports"],
                    "row_reconciliation_drift": row["reconciliation_drift"],
                }
            )
    return result


def validate_only(
    unloaded_path: Path,
    loaded_path: Path,
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    registry, registry_sha = _registry(registry_path)
    profiles = [
        profile_artifact(unloaded_path, flow="unloaded", registry=registry),
        profile_artifact(loaded_path, flow="loaded", registry=registry),
    ]
    return {
        "status": "valid_internal_historical_candidate",
        "publication_allowed": False,
        "source_id": registry["source"]["source_id"],
        "registry_sha256": registry_sha,
        "period": registry["period"],
        "unit": registry["unit_evidence"]["unit"],
        "flows": [
            {
                "flow": profile["flow"],
                "artifact_sha256": profile["artifact_sha256"],
                "country_semantics": profile["country_semantics"],
                "commodity_count": len(profile["commodities"]),
                "coverage": profile["coverage"],
                "reconciliation": profile["reconciliation"],
            }
            for profile in profiles
        ],
        "candidate_joint_observation_count": sum(
            profile["coverage"]["observed_nonzero_cells"] for profile in profiles
        ),
        "dependency_edges_emitted": 0,
        "dependency_edge_blockers": [
            "signed_source_rights_decision_absent",
            "country_entity_crosswalk_not_registered",
            "loaded_country_heading_semantically_ambiguous",
            "historical_baseline_not_current",
        ],
        "limitations": registry["limits"],
    }


def compile_baseline(
    unloaded_path: Path,
    loaded_path: Path,
    *,
    root: Path = ROOT,
    registry_path: Path = REGISTRY_PATH,
    rights_path: Path = RIGHTS_PATH,
    signers_path: Path = SIGNERS_PATH,
) -> dict[str, Any]:
    registry, registry_sha = _registry(registry_path)
    rights = _approved_source(
        root=root,
        registry=registry,
        rights_path=rights_path,
        signers_path=signers_path,
    )
    profiles = [
        profile_artifact(unloaded_path, flow="unloaded", registry=registry),
        profile_artifact(loaded_path, flow="loaded", registry=registry),
    ]
    observations = [cell for profile in profiles for cell in _candidate_cells(profile)]
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "status": "rights_approved_historical_joint_observations",
            "publication_allowed": True,
            "source_id": registry["source"]["source_id"],
            "rights_decision_id": rights["decision_id"],
            "registry_sha256": registry_sha,
            "period": registry["period"],
            "unit_evidence": registry["unit_evidence"],
            "not_current": True,
        },
        "coverage": {
            "port_frame": registry["port_frame"],
            "flows": [{"flow": profile["flow"], **profile["coverage"]} for profile in profiles],
            "national_port_coverage": None,
            "national_port_coverage_reason": registry["port_frame"]["excluded_scope"],
        },
        "joint_observations": observations,
        "dependency_edges": [],
        "dependency_edge_status": (
            "not_emitted_until_country_crosswalk_and_loaded_country_semantics_are_registered"
        ),
        "limitations": registry["limits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unloaded", type=Path, required=True)
    parser.add_argument("--loaded", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            validate_only(args.unloaded, args.loaded)
            if args.validate_only
            else compile_baseline(args.unloaded, args.loaded)
        )
    except OGDPortTradeError as exc:
        raise SystemExit(f"ogd_port_trade: refused: {exc.code}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
