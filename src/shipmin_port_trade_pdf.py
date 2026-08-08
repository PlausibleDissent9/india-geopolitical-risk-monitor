"""Extract the latest official India port-country-commodity annual baseline.

The Ministry of Ports, Shipping and Waterways publishes 2024-25 country by
principal-commodity by Major Port tables inside Basic Port Statistics of India.
This extractor is coordinate-aware, hash-pins the exact PDF, derives column
centres from every page header, preserves blanks and provider labels, and
refuses row or commodity-total drift beyond the table's rounding tolerance.

Validation emits structural metadata only.  Row publication requires a signed
source-rights decision; canonical dependency traversal remains blocked until
entity crosswalks and a lossless multi-role relation object are registered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, NoReturn, cast
from urllib.parse import unquote, urlsplit

from src import publication_guard

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "shipmin_port_trade_2024_25.json"
RIGHTS_PATH = ROOT / "governance" / "source_rights_registry.json"
SIGNERS_PATH = ROOT / "governance" / "rights_signers.json"

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_NUMBER = re.compile(r"^(?:[0-9]+(?:\.[0-9]+)?|[-…])$")
_PORT_COLUMNS = [
    "SMP(KDS)",
    "SMP(HDC)",
    "PPA",
    "VPA",
    "KPL",
    "ChPA",
    "V.O.C",
    "CoPA",
    "NMPA",
    "MoPA",
    "JNPA",
    "MbPA",
    "DPA",
    "ALL PORTS",
]

Word = dict[str, Any]
WordProvider = Callable[[int], list[Word]]


class ShipminPortTradeError(ValueError):
    """Stable fail-closed source extraction error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise ShipminPortTradeError(code)


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
        raise ShipminPortTradeError(code) from exc
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


def _https(value: object, hosts: set[str], prefix: str, code: str) -> str:
    url = _text(value, code)
    parsed = urlsplit(url)
    decoded = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in hosts
        or not parsed.path.startswith(prefix)
        or any(part in {".", ".."} for part in decoded.split("/"))
        or unquote(decoded) != decoded
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _fail(code)
    return url


def _registry(path: Path = REGISTRY_PATH) -> tuple[dict[str, Any], str]:
    value, registry_sha = _read_object(path, "registry_unreadable")
    registry = _object(
        value,
        {
            "schema_version",
            "effective",
            "status",
            "source",
            "implementation",
            "artifact",
            "period",
            "unit",
            "port_frame",
            "flows",
            "limits",
        },
        "registry_fields_invalid",
    )
    if (
        registry["schema_version"] != "1.0.0"
        or registry["effective"] != "2026-08-09"
        or registry["status"] != "acquired_rights_review_required"
    ):
        _fail("registry_identity_invalid")
    source = _object(
        registry["source"],
        {"source_id", "page_url", "terms_url", "required_permitted_uses"},
        "registry_source_invalid",
    )
    if not isinstance(source["source_id"], str) or not _ID.fullmatch(source["source_id"]):
        _fail("registry_source_id_invalid")
    _https(
        source["page_url"],
        {"shipmin.gov.in", "www.shipmin.gov.in"},
        "/en/content/",
        "registry_page_url_invalid",
    )
    _https(
        source["terms_url"],
        {"shipmin.gov.in", "www.shipmin.gov.in"},
        "/en/footer/",
        "registry_terms_url_invalid",
    )
    if source["required_permitted_uses"] != [
        "cite_metadata",
        "publish_derived_value",
        "publish_extract",
    ]:
        _fail("registry_required_uses_invalid")

    implementation = _object(
        registry["implementation"], {"path", "sha256"}, "registry_implementation_invalid"
    )
    if implementation["path"] != "src/shipmin_port_trade_pdf.py":
        _fail("registry_implementation_invalid")
    expected_implementation = _digest(
        implementation["sha256"], "registry_implementation_digest_invalid"
    )
    try:
        actual_implementation = hashlib.sha256(
            (path.parents[1] / implementation["path"]).read_bytes()
        ).hexdigest()
    except OSError as exc:
        raise ShipminPortTradeError("implementation_unreadable") from exc
    if actual_implementation != expected_implementation:
        _fail("implementation_digest_mismatch")

    artifact = _object(
        registry["artifact"],
        {
            "url",
            "sha256",
            "file_size_bytes",
            "page_count",
            "published_on",
            "retrieved_at",
            "table_ids",
        },
        "registry_artifact_invalid",
    )
    _https(
        artifact["url"],
        {"shipmin.gov.in", "www.shipmin.gov.in"},
        "/sites/default/files/",
        "registry_artifact_url_invalid",
    )
    _digest(artifact["sha256"], "registry_artifact_digest_invalid")
    if artifact["file_size_bytes"] != 2469332 or artifact["page_count"] != 243:
        _fail("registry_artifact_size_or_pages_invalid")
    if artifact["published_on"] != "2026-04-29" or artifact["table_ids"] != [
        "2.1.6",
        "2.1.7",
    ]:
        _fail("registry_artifact_identity_invalid")
    _text(artifact["retrieved_at"], "registry_artifact_retrieved_invalid")
    if registry["period"] != {
        "label": "2024-25",
        "start": "2024-04-01",
        "end": "2025-03-31",
        "status": "latest_released_fiscal_baseline_not_live",
    }:
        _fail("registry_period_invalid")
    if registry["unit"] != "thousand_metric_tonnes":
        _fail("registry_unit_invalid")
    port_frame = _object(
        registry["port_frame"],
        {"frame_id", "columns", "member_count", "scope", "excluded_scope"},
        "registry_port_frame_invalid",
    )
    if (
        port_frame["frame_id"] != "india_major_port_table_columns_2024_25"
        or port_frame["columns"] != _PORT_COLUMNS[:-1]
        or port_frame["member_count"] != 13
    ):
        _fail("registry_port_frame_invalid")

    flows = registry["flows"]
    if not isinstance(flows, list) or len(flows) != 2:
        _fail("registry_flows_invalid")
    seen: set[str] = set()
    for raw in flows:
        flow = _object(
            raw,
            {
                "flow",
                "pdf_pages",
                "country_semantics",
                "commodities",
                "expected_detail_rows",
                "expected_positive_joint_cells",
                "expected_rows_missing_all_ports_total",
                "expected_commodity_total_drifts",
            },
            "registry_flow_invalid",
        )
        flow_id = flow["flow"]
        if flow_id not in {"unloaded", "loaded"} or flow_id in seen:
            _fail("registry_flow_identity_invalid")
        seen.add(flow_id)
        pages = flow["pdf_pages"]
        commodities = flow["commodities"]
        if (
            not isinstance(pages, list)
            or not pages
            or any(not isinstance(item, int) for item in pages)
            or pages != list(range(pages[0], pages[-1] + 1))
            or not isinstance(commodities, list)
            or not commodities
            or any(not isinstance(item, str) or not item for item in commodities)
            or len(commodities) != len(set(commodities))
        ):
            _fail("registry_flow_frame_invalid")
        for field in (
            "expected_detail_rows",
            "expected_positive_joint_cells",
            "expected_rows_missing_all_ports_total",
        ):
            if isinstance(flow[field], bool) or not isinstance(flow[field], int) or flow[field] < 0:
                _fail("registry_flow_count_invalid")
        expected_drifts = flow["expected_commodity_total_drifts"]
        if (
            not isinstance(expected_drifts, dict)
            or list(expected_drifts) != commodities
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in expected_drifts.values()
            )
        ):
            _fail("registry_flow_commodity_drifts_invalid")
        expected_semantics = (
            "country_of_origin"
            if flow_id == "unloaded"
            else "provider_heading_says_country_of_origin_for_loaded_cargo_destination_not_asserted"
        )
        if flow["country_semantics"] != expected_semantics:
            _fail("registry_country_semantics_invalid")
    if seen != {"unloaded", "loaded"}:
        _fail("registry_flows_invalid")
    limits = registry["limits"]
    if (
        not isinstance(limits, list)
        or len(limits) < 7
        or any(not isinstance(item, str) or not item for item in limits)
    ):
        _fail("registry_limits_invalid")
    return registry, registry_sha


def _flow_config(registry: dict[str, Any], flow: str) -> dict[str, Any]:
    try:
        return next(row for row in registry["flows"] if row["flow"] == flow)
    except StopIteration as exc:
        raise ShipminPortTradeError("flow_unregistered") from exc


def _number(text: str) -> Decimal | None:
    if text in {"-", "…"}:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ShipminPortTradeError("pdf_number_invalid") from exc
    if not value.is_finite() or value < 0:
        _fail("pdf_number_invalid")
    return value


def _label(words: list[Word]) -> str:
    text = " ".join(str(word["text"]) for word in sorted(words, key=lambda row: row["x0"]))
    if (
        not text
        or len(text) > 200
        or text[0] in {"=", "+", "-", "@"}
        or any(ord(character) < 32 for character in text)
    ):
        _fail("pdf_label_invalid")
    return text


def _groups(words: list[Word], tolerance: float = 1.2) -> list[list[Word]]:
    result: list[list[Word]] = []
    for word in sorted(words, key=lambda row: (row["top"], row["x0"])):
        if not result:
            result.append([word])
            continue
        mean_top = sum(float(item["top"]) for item in result[-1]) / len(result[-1])
        if abs(float(word["top"]) - mean_top) > tolerance:
            result.append([word])
        else:
            result[-1].append(word)
    return result


def _header(words: list[Word]) -> tuple[list[float], float, float]:
    centres: dict[str, float] = {}
    for name in _PORT_COLUMNS[:-1]:
        candidates = [word for word in words if word.get("text") == name]
        if len(candidates) != 1:
            _fail("pdf_header_invalid")
        word = candidates[0]
        centres[name] = (float(word["x0"]) + float(word["x1"])) / 2
    all_words = [word for word in words if word.get("text") in {"ALL", "PORTS"}]
    pairs = [
        (first, second)
        for first in all_words
        for second in all_words
        if first.get("text") == "ALL"
        and second.get("text") == "PORTS"
        and abs(float(first["top"]) - float(second["top"])) < 1
    ]
    if not pairs:
        _fail("pdf_header_invalid")
    first, second = max(pairs, key=lambda pair: float(pair[0]["x0"]))
    centres["ALL PORTS"] = (
        (float(first["x0"]) + float(first["x1"])) / 2
        + (float(second["x0"]) + float(second["x1"])) / 2
    ) / 2
    origins = [word for word in words if word.get("text") == "Origin/Commodities"]
    if len(origins) != 1:
        _fail("pdf_header_invalid")
    origin = origins[0]
    ordered = [centres[name] for name in _PORT_COLUMNS]
    if ordered != sorted(ordered):
        _fail("pdf_header_order_invalid")
    boundary = (float(origin["x1"]) + ordered[0]) / 2
    header_tokens = set(_PORT_COLUMNS[:-1]) | {"ALL", "PORTS", "Origin/Commodities"}
    header_bottom = max(
        float(word["bottom"]) for word in words if word.get("text") in header_tokens
    )
    return ordered, boundary, header_bottom


def _column_index(centre: float, centres: list[float]) -> int:
    boundaries = [(centres[index] + centres[index + 1]) / 2 for index in range(len(centres) - 1)]
    left = centres[0] - (boundaries[0] - centres[0])
    right = centres[-1] + (centres[-1] - boundaries[-1])
    if centre < left or centre > right:
        _fail("pdf_value_outside_columns")
    return sum(centre > boundary for boundary in boundaries)


def _parse_flow(config: dict[str, Any], word_provider: WordProvider) -> dict[str, Any]:
    expected_commodities = config["commodities"]
    commodity_index = 0
    current_commodity: str | None = None
    expect_commodity = True
    complete = False
    rows: list[dict[str, Any]] = []
    header_centres: list[list[float]] = []

    for page_number in config["pdf_pages"]:
        words = word_provider(page_number)
        if not isinstance(words, list) or not words:
            _fail("pdf_page_words_missing")
        centres, boundary, header_bottom = _header(words)
        header_centres.append(centres)
        body = [
            word
            for word in words
            if float(word["top"]) >= header_bottom + 2 and float(word["top"]) <= 550
        ]
        for group in _groups(body):
            if complete:
                continue
            label_words = [word for word in group if float(word["x1"]) < boundary]
            value_words = [
                word
                for word in group
                if float(word["x0"]) >= boundary and _NUMBER.fullmatch(str(word["text"]))
            ]
            if not label_words:
                continue
            right_words = [word for word in group if float(word["x0"]) >= boundary]
            if len(right_words) != len(value_words):
                _fail("pdf_cell_token_invalid")
            label = _label(label_words)
            if expect_commodity:
                if value_words or commodity_index >= len(expected_commodities):
                    _fail("pdf_commodity_sequence_invalid")
                if label != expected_commodities[commodity_index]:
                    _fail("pdf_commodity_sequence_invalid")
                current_commodity = label
                commodity_index += 1
                expect_commodity = False
                continue
            if current_commodity is None:
                _fail("pdf_commodity_missing")
            values: dict[str, Decimal | None] = {name: None for name in _PORT_COLUMNS}
            explicit_missing: set[str] = set()
            for word in value_words:
                centre = (float(word["x0"]) + float(word["x1"])) / 2
                column = _PORT_COLUMNS[_column_index(centre, centres)]
                if values[column] is not None or column in explicit_missing:
                    _fail("pdf_column_duplicate")
                value = _number(str(word["text"]))
                if value is None:
                    explicit_missing.add(column)
                else:
                    values[column] = value
            port_values = [values[name] for name in _PORT_COLUMNS[:-1]]
            all_ports = values["ALL PORTS"]
            if all_ports is None:
                drift: Decimal | None = None
            else:
                drift = sum((value or Decimal(0)) for value in port_values) - all_ports
                if abs(drift) > Decimal(2):
                    _fail("pdf_row_reconciliation_invalid")
            row = {
                "page": page_number,
                "commodity": current_commodity,
                "reported_country": label,
                "values": values,
                "explicit_missing_columns": sorted(explicit_missing),
                "reconciliation_drift": drift,
            }
            rows.append(row)
            if label.casefold() == "total":
                if any(values[name] is None for name in _PORT_COLUMNS):
                    _fail("pdf_summary_incomplete")
                expect_commodity = True
                if commodity_index == len(expected_commodities):
                    complete = True

    if not complete or commodity_index != len(expected_commodities):
        _fail("pdf_flow_incomplete")
    summaries = [row for row in rows if row["reported_country"].casefold() == "total"]
    details = [row for row in rows if row["reported_country"].casefold() != "total"]
    if len(summaries) != len(expected_commodities):
        _fail("pdf_summary_coverage_invalid")
    summary_by_commodity = {row["commodity"]: row for row in summaries}
    commodity_drifts: dict[str, Decimal] = {}
    for commodity in expected_commodities:
        detail_total = sum(
            (
                row["values"]["ALL PORTS"]
                if row["values"]["ALL PORTS"] is not None
                else sum((row["values"][name] or Decimal(0)) for name in _PORT_COLUMNS[:-1])
            )
            for row in details
            if row["commodity"] == commodity
        )
        summary_total = summary_by_commodity[commodity]["values"]["ALL PORTS"]
        if summary_total is None:
            _fail("pdf_commodity_total_reconciliation_invalid")
        commodity_drift = detail_total - summary_total
        commodity_drifts[commodity] = commodity_drift
        if commodity_drift != Decimal(config["expected_commodity_total_drifts"][commodity]):
            _fail("pdf_commodity_total_reconciliation_invalid")

    positive_cells = sum(
        value is not None and value > 0
        for row in details
        for name, value in row["values"].items()
        if name != "ALL PORTS"
    )
    rows_missing_total = sum(row["values"]["ALL PORTS"] is None for row in details)
    if (
        len(details) != config["expected_detail_rows"]
        or positive_cells != config["expected_positive_joint_cells"]
        or rows_missing_total != config["expected_rows_missing_all_ports_total"]
    ):
        _fail("pdf_registered_counts_mismatch")
    blank_cells = sum(
        value is None and name not in row["explicit_missing_columns"]
        for row in details
        for name, value in row["values"].items()
        if name != "ALL PORTS"
    )
    explicit_zero_cells = sum(
        value == 0
        for row in details
        for name, value in row["values"].items()
        if name != "ALL PORTS"
    )
    explicit_missing_cells = sum(
        len([name for name in row["explicit_missing_columns"] if name != "ALL PORTS"])
        for row in details
    )
    drift_histogram = Counter(
        str(row["reconciliation_drift"])
        for row in details
        if row["reconciliation_drift"] is not None
    )
    return {
        "flow": config["flow"],
        "country_semantics": config["country_semantics"],
        "commodities": expected_commodities,
        "rows": details,
        "summaries": summaries,
        "header_centres": header_centres,
        "coverage": {
            "detail_rows": len(details),
            "summary_rows": len(summaries),
            "port_columns": len(_PORT_COLUMNS) - 1,
            "expected_joint_cells": len(details) * (len(_PORT_COLUMNS) - 1),
            "positive_joint_cells": positive_cells,
            "explicit_zero_cells": explicit_zero_cells,
            "source_blank_cells": blank_cells,
            "explicit_missing_cells": explicit_missing_cells,
            "rows_missing_all_ports_total": rows_missing_total,
        },
        "reconciliation": {
            "maximum_absolute_rounding_drift_thousand_tonnes": 2,
            "detail_row_drift_histogram_thousand_tonnes": dict(sorted(drift_histogram.items())),
            "commodity_total_drift_thousand_tonnes": {
                commodity: int(drift) for commodity, drift in commodity_drifts.items()
            },
        },
    }


def _word_provider(path: Path, expected_pages: int) -> tuple[WordProvider, Callable[[], None]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ShipminPortTradeError("pdfplumber_unavailable") from exc
    try:
        document = pdfplumber.open(path)
    except Exception as exc:
        raise ShipminPortTradeError("pdf_unreadable") from exc
    if len(document.pages) != expected_pages:
        document.close()
        _fail("pdf_page_count_mismatch")

    def provide(page_number: int) -> list[Word]:
        if not 1 <= page_number <= len(document.pages):
            _fail("pdf_page_out_of_range")
        try:
            words = document.pages[page_number - 1].extract_words(
                x_tolerance=1,
                y_tolerance=2,
                extra_attrs=["fontname", "size"],
            )
        except Exception as exc:
            raise ShipminPortTradeError("pdf_word_extraction_failed") from exc
        return words

    return provide, document.close


def _verify_artifact(path: Path, registry: dict[str, Any]) -> None:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ShipminPortTradeError("pdf_unreadable") from exc
    artifact = registry["artifact"]
    if len(raw) != artifact["file_size_bytes"]:
        _fail("pdf_size_mismatch")
    if hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        _fail("pdf_digest_mismatch")


def extract_profiles(path: Path, registry: dict[str, Any]) -> list[dict[str, Any]]:
    _verify_artifact(path, registry)
    provider, close = _word_provider(path, registry["artifact"]["page_count"])
    try:
        return [_parse_flow(config, provider) for config in registry["flows"]]
    finally:
        close()


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
        raise ShipminPortTradeError(f"rights_{exc.code}") from exc
    source = rights.get(registry["source"]["source_id"])
    if source is None or source["decision_state"] != "approved":
        _fail("rights_not_approved")
    if not set(registry["source"]["required_permitted_uses"]).issubset(source["permitted_uses"]):
        _fail("rights_use_not_approved")
    return source


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _observations(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for profile in profiles:
        for row in profile["rows"]:
            for port, value in row["values"].items():
                if port == "ALL PORTS" or value is None or value <= 0:
                    continue
                material = "|".join(
                    (
                        profile["flow"],
                        row["commodity"],
                        row["reported_country"],
                        port,
                    )
                )
                result.append(
                    {
                        "observation_id": "smpt:"
                        + hashlib.sha256(material.encode()).hexdigest()[:24],
                        "flow": profile["flow"],
                        "commodity": row["commodity"],
                        "reported_country": row["reported_country"],
                        "country_semantics": profile["country_semantics"],
                        "port_column": port,
                        "quantity": _json_number(value),
                        "unit": "thousand_metric_tonnes",
                        "pdf_page": row["page"],
                        "row_all_ports_quantity": (
                            _json_number(row["values"]["ALL PORTS"])
                            if row["values"]["ALL PORTS"] is not None
                            else None
                        ),
                        "row_reconciliation_drift": (
                            _json_number(row["reconciliation_drift"])
                            if row["reconciliation_drift"] is not None
                            else None
                        ),
                    }
                )
    return result


def validate_only(pdf_path: Path, *, registry_path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry, registry_sha = _registry(registry_path)
    profiles = extract_profiles(pdf_path, registry)
    return {
        "status": "valid_internal_latest_fiscal_candidate",
        "publication_allowed": False,
        "source_id": registry["source"]["source_id"],
        "source_artifact_sha256": registry["artifact"]["sha256"],
        "registry_sha256": registry_sha,
        "period": registry["period"],
        "unit": registry["unit"],
        "flows": [
            {
                "flow": profile["flow"],
                "country_semantics": profile["country_semantics"],
                "commodity_count": len(profile["commodities"]),
                "coverage": profile["coverage"],
                "reconciliation": profile["reconciliation"],
            }
            for profile in profiles
        ],
        "candidate_joint_observation_count": sum(
            profile["coverage"]["positive_joint_cells"] for profile in profiles
        ),
        "dependency_relations_emitted": 0,
        "dependency_relation_blockers": [
            "signed_source_rights_decision_absent",
            "country_and_port_entity_crosswalks_not_registered",
            "loaded_country_heading_semantically_ambiguous",
            "lossless_multi_role_dependency_object_not_yet_in_canonical_release",
        ],
        "limitations": registry["limits"],
    }


def compile_baseline(
    pdf_path: Path,
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
    profiles = extract_profiles(pdf_path, registry)
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "status": "rights_approved_latest_fiscal_joint_observations",
            "publication_allowed": True,
            "source_id": registry["source"]["source_id"],
            "rights_decision_id": rights["decision_id"],
            "source_artifact": registry["artifact"],
            "registry_sha256": registry_sha,
            "period": registry["period"],
            "unit": registry["unit"],
            "not_live": True,
        },
        "coverage": {
            "port_frame": registry["port_frame"],
            "flows": [{"flow": profile["flow"], **profile["coverage"]} for profile in profiles],
            "national_port_coverage": None,
            "national_port_coverage_reason": registry["port_frame"]["excluded_scope"],
        },
        "joint_observations": _observations(profiles),
        "dependency_relations": [],
        "dependency_relation_status": (
            "not_emitted_until_entity_crosswalks_and_lossless_multi_role_schema_are_registered"
        ),
        "limitations": registry["limits"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        result = validate_only(args.pdf) if args.validate_only else compile_baseline(args.pdf)
    except ShipminPortTradeError as exc:
        raise SystemExit(f"shipmin_port_trade_pdf: refused: {exc.code}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
