"""Compile rights-approved India major-port and commodity marginals.

The Ministry report exposes two separately reconciling tables.  This module
preserves that shape.  It cannot emit a port-by-commodity edge and refuses any
input that contains a purported joint cell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import unquote, urlsplit

from src import publication_guard

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "port_commodity_marginals.json"
RIGHTS_PATH = ROOT / "governance" / "source_rights_registry.json"
SIGNERS_PATH = ROOT / "governance" / "rights_signers.json"

_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MONTH = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})$")


class PortCommodityError(ValueError):
    """Stable fail-closed error for the marginal compiler."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise PortCommodityError(code)


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
        raise PortCommodityError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _list(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _identifier(value: object, code: str) -> str:
    text = _text(value, code)
    if not _ID.fullmatch(text):
        _fail(code)
    return text


def _integer(value: object, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
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
        raise PortCommodityError(code) from exc
    return text


def _timestamp(value: object, code: str) -> str:
    text = _text(value, code)
    if not text.endswith("Z"):
        _fail(code)
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PortCommodityError(code) from exc
    return text


def _month(value: object, code: str) -> str:
    text = _text(value, code)
    match = _MONTH.fullmatch(text)
    if not match or not 1 <= int(match.group("month")) <= 12:
        _fail(code)
    return text


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
            "port_frame",
            "commodity_frame",
            "joint_observation",
            "limitations",
        },
        "registry_fields_invalid",
    )
    if (
        registry["schema_version"] != "1.0.0"
        or registry["status"] != "rights_ready_no_public_observations"
    ):
        _fail("registry_identity_invalid")
    _day(registry["effective"], "registry_effective_invalid")
    source = _object(
        registry["source"],
        {
            "source_id",
            "allowed_origin",
            "allowed_path_prefix",
            "required_permitted_uses",
            "registered_vintages",
        },
        "registry_source_invalid",
    )
    _identifier(source["source_id"], "registry_source_id_invalid")
    parsed = urlsplit(_text(source["allowed_origin"], "registry_origin_invalid"))
    if parsed.scheme != "https" or parsed.netloc != "shipmin.gov.in" or parsed.path:
        _fail("registry_origin_invalid")
    if source["allowed_path_prefix"] != "/sites/default/files/":
        _fail("registry_path_prefix_invalid")
    required_uses = _list(source["required_permitted_uses"], "registry_uses_invalid")
    if required_uses != ["cite_metadata", "publish_derived_value", "publish_extract"]:
        _fail("registry_uses_invalid")
    vintages = _list(source["registered_vintages"], "registry_vintages_invalid")
    vintage_keys: set[tuple[str, str]] = set()
    if not vintages:
        _fail("registry_vintages_invalid")
    for raw in vintages:
        vintage = _object(
            raw,
            {
                "url",
                "sha256",
                "valid_period",
                "estimate_status",
                "published_on",
                "table_pages",
                "registered_on",
            },
            "registry_vintage_invalid",
        )
        url = _source_url(registry, vintage["url"])
        sha = _digest(vintage["sha256"], "registry_vintage_digest_invalid")
        _month(vintage["valid_period"], "registry_vintage_period_invalid")
        if vintage["estimate_status"] not in {
            "advance_estimate",
            "provisional",
            "final",
        }:
            _fail("registry_vintage_estimate_status_invalid")
        published = _day(vintage["published_on"], "registry_vintage_published_invalid")
        registered = _day(vintage["registered_on"], "registry_vintage_registered_invalid")
        if vintage["table_pages"] != [6, 7] or published > registered:
            _fail("registry_vintage_temporal_or_pages_invalid")
        if (url, sha) in vintage_keys:
            _fail("registry_vintage_duplicate")
        vintage_keys.add((url, sha))

    implementation = _object(
        registry["implementation"], {"path", "sha256"}, "registry_implementation_invalid"
    )
    if implementation["path"] != "src/port_commodity_marginals.py":
        _fail("registry_implementation_invalid")
    expected = _digest(
        implementation["sha256"], "registry_implementation_digest_invalid"
    )
    implementation_path = path.parents[1] / implementation["path"]
    try:
        actual = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PortCommodityError("implementation_unreadable") from exc
    if actual != expected:
        _fail("implementation_digest_mismatch")

    ports = _frame_registry(registry["port_frame"], "port")
    commodities = _frame_registry(registry["commodity_frame"], "commodity")
    if len(ports["member_ids"]) != 12 or len(commodities["member_ids"]) != 20:
        _fail("registry_frame_count_invalid")
    joint = _object(
        registry["joint_observation"],
        {"status", "inference_allowed", "required_cells", "reason"},
        "registry_joint_invalid",
    )
    if (
        joint["status"] != "not_observed"
        or joint["inference_allowed"] is not False
        or joint["required_cells"] != 0
    ):
        _fail("registry_joint_policy_invalid")
    _text(joint["reason"], "registry_joint_reason_invalid")
    limitations = _list(registry["limitations"], "registry_limitations_invalid")
    if len(limitations) < 4 or any(not isinstance(item, str) or not item for item in limitations):
        _fail("registry_limitations_invalid")
    return registry, digest


def _frame_registry(value: object, kind: str) -> dict[str, Any]:
    common = {"frame_id", "member_ids", "member_labels"}
    fields = (
        common | {"scope", "subcomponent_policy", "excluded_scope"}
        if kind == "port"
        else common | {"classification", "separate_metric"}
    )
    frame = _object(value, fields, f"registry_{kind}_frame_invalid")
    _identifier(frame["frame_id"], f"registry_{kind}_frame_id_invalid")
    ids = _list(frame["member_ids"], f"registry_{kind}_ids_invalid")
    if (
        not ids
        or any(not isinstance(item, str) or not _ID.fullmatch(item) for item in ids)
        or len(ids) != len(set(ids))
    ):
        _fail(f"registry_{kind}_ids_invalid")
    labels = frame["member_labels"]
    if not isinstance(labels, dict) or set(labels) != set(ids):
        _fail(f"registry_{kind}_labels_invalid")
    if any(not isinstance(label, str) or not label.strip() for label in labels.values()):
        _fail(f"registry_{kind}_labels_invalid")
    if kind == "port":
        for field in ("scope", "subcomponent_policy", "excluded_scope"):
            _text(frame[field], f"registry_{kind}_{field}_invalid")
    else:
        _text(frame["classification"], "registry_commodity_classification_invalid")
        separate = _object(
            frame["separate_metric"],
            {"metric_id", "unit", "denominator_status"},
            "registry_separate_metric_invalid",
        )
        if separate != {
            "metric_id": "container_teu",
            "unit": "teu",
            "denominator_status": "excluded_from_tonne_reconciliation",
        }:
            _fail("registry_separate_metric_invalid")
    return frame


def _source_url(registry: dict[str, Any], value: object) -> str:
    url = _text(value, "source_url_invalid")
    parsed = urlsplit(url)
    source = registry["source"]
    origin = f"{parsed.scheme}://{parsed.netloc}"
    decoded_path = unquote(parsed.path)
    if (
        origin != source["allowed_origin"]
        or not parsed.path.startswith(source["allowed_path_prefix"])
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or unquote(decoded_path) != decoded_path
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        _fail("source_url_invalid")
    return url


def _members(
    value: object, frame: dict[str, Any], kind: str
) -> tuple[list[dict[str, Any]], int]:
    rows = _list(value, f"{kind}_members_invalid")
    expected_ids = frame["member_ids"]
    labels = frame["member_labels"]
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    total = 0
    for raw in rows:
        row = _object(raw, {f"{kind}_id", "label", "cargo_tonnes"}, f"{kind}_row_invalid")
        member_id = _identifier(row[f"{kind}_id"], f"{kind}_id_invalid")
        if member_id in seen or member_id not in labels or row["label"] != labels[member_id]:
            _fail(f"{kind}_membership_invalid")
        cargo = _integer(row["cargo_tonnes"], f"{kind}_cargo_invalid")
        seen.add(member_id)
        total += cargo
        result.append(
            {f"{kind}_id": member_id, "label": row["label"], "cargo_tonnes": cargo}
        )
    if [row[f"{kind}_id"] for row in result] != expected_ids:
        _fail(f"{kind}_frame_order_or_coverage_invalid")
    return result, total


def _share_basis_points(value: int, total: int) -> int:
    if total <= 0:
        _fail("total_cargo_invalid")
    return int(
        (Decimal(value) * Decimal(10000) / Decimal(total)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _observation_digest(material: dict[str, Any]) -> str:
    encoded = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_snapshot(
    value: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    snapshot = _object(
        value,
        {
            "schema_version",
            "snapshot_id",
            "source_id",
            "rights_decision_id",
            "source_artifact",
            "valid_period",
            "knowledge_time",
            "estimate_status",
            "unit",
            "total_cargo_tonnes",
            "port_frame",
            "commodity_frame",
            "separate_metrics",
            "joint_port_commodity",
            "extraction",
        },
        "snapshot_fields_invalid",
    )
    if snapshot["schema_version"] != "1.0.0":
        _fail("snapshot_schema_invalid")
    _identifier(snapshot["snapshot_id"], "snapshot_id_invalid")
    if snapshot["source_id"] != registry["source"]["source_id"]:
        _fail("snapshot_source_invalid")
    _identifier(snapshot["rights_decision_id"], "snapshot_rights_decision_invalid")
    valid_period = _month(snapshot["valid_period"], "snapshot_period_invalid")
    knowledge_time = _timestamp(snapshot["knowledge_time"], "snapshot_knowledge_time_invalid")
    if snapshot["estimate_status"] not in {"advance_estimate", "provisional", "final"}:
        _fail("snapshot_estimate_status_invalid")
    if snapshot["unit"] != "tonnes":
        _fail("snapshot_unit_invalid")
    total = _integer(snapshot["total_cargo_tonnes"], "total_cargo_invalid", minimum=1)

    artifact = _object(
        snapshot["source_artifact"],
        {"url", "sha256", "published_on", "retrieved_at", "table_pages"},
        "source_artifact_invalid",
    )
    source_url = _source_url(registry, artifact["url"])
    source_sha = _digest(artifact["sha256"], "source_artifact_digest_invalid")
    published_on = _day(artifact["published_on"], "source_published_on_invalid")
    retrieved_at = _timestamp(artifact["retrieved_at"], "source_retrieved_at_invalid")
    pages = _list(artifact["table_pages"], "source_table_pages_invalid")
    if pages != [6, 7]:
        _fail("source_table_pages_invalid")
    if published_on > retrieved_at[:10] or retrieved_at > knowledge_time:
        _fail("source_temporal_order_invalid")
    registered_vintage = next(
        (
            vintage
            for vintage in registry["source"]["registered_vintages"]
            if vintage["url"] == source_url
            and vintage["sha256"] == source_sha
            and vintage["valid_period"] == valid_period
            and vintage["estimate_status"] == snapshot["estimate_status"]
            and vintage["published_on"] == published_on
            and vintage["table_pages"] == pages
        ),
        None,
    )
    if registered_vintage is None:
        _fail("source_vintage_unregistered")
    if knowledge_time[:10] < registered_vintage["registered_on"]:
        _fail("source_knowledge_predates_registration")

    port_block = _object(
        snapshot["port_frame"],
        {"frame_id", "frame_count", "covered_count", "members"},
        "port_frame_invalid",
    )
    port_registry = registry["port_frame"]
    if (
        port_block["frame_id"] != port_registry["frame_id"]
        or port_block["frame_count"] != len(port_registry["member_ids"])
        or port_block["covered_count"] != len(port_registry["member_ids"])
    ):
        _fail("port_frame_denominator_invalid")
    ports, port_total = _members(port_block["members"], port_registry, "port")

    commodity_block = _object(
        snapshot["commodity_frame"],
        {"frame_id", "frame_count", "covered_count", "members"},
        "commodity_frame_invalid",
    )
    commodity_registry = registry["commodity_frame"]
    if (
        commodity_block["frame_id"] != commodity_registry["frame_id"]
        or commodity_block["frame_count"] != len(commodity_registry["member_ids"])
        or commodity_block["covered_count"] != len(commodity_registry["member_ids"])
    ):
        _fail("commodity_frame_denominator_invalid")
    commodities, commodity_total = _members(
        commodity_block["members"], commodity_registry, "commodity"
    )
    if port_total != total or commodity_total != total:
        _fail("marginal_total_mismatch")

    separate = _list(snapshot["separate_metrics"], "separate_metrics_invalid")
    if len(separate) != 1:
        _fail("separate_metrics_invalid")
    separate_row = _object(
        separate[0], {"metric_id", "unit", "value"}, "separate_metric_invalid"
    )
    expected_separate = commodity_registry["separate_metric"]
    if (
        separate_row["metric_id"] != expected_separate["metric_id"]
        or separate_row["unit"] != expected_separate["unit"]
    ):
        _fail("separate_metric_identity_invalid")
    separate_value = _integer(separate_row["value"], "separate_metric_value_invalid")

    joint = _object(
        snapshot["joint_port_commodity"],
        {"status", "cells"},
        "joint_snapshot_invalid",
    )
    if joint["status"] != "not_observed" or joint["cells"] != []:
        _fail("joint_observation_or_inference_refused")

    extraction = _object(
        snapshot["extraction"],
        {"method", "checks", "verified_at"},
        "extraction_invalid",
    )
    if extraction["method"] != "dual_method_reconciliation":
        _fail("extraction_method_invalid")
    checks_raw = _list(extraction["checks"], "extraction_checks_invalid")
    checks: list[dict[str, str]] = []
    for raw in checks_raw:
        check = _object(
            raw,
            {"check_id", "method", "artifact_sha256"},
            "extraction_check_invalid",
        )
        checks.append(
            {
                "check_id": _identifier(check["check_id"], "extraction_check_id_invalid"),
                "method": _text(check["method"], "extraction_check_method_invalid"),
                "artifact_sha256": _digest(
                    check["artifact_sha256"], "extraction_check_digest_invalid"
                ),
            }
        )
    if (
        len(checks) != 2
        or {check["method"] for check in checks}
        != {"pdf_text_extraction", "visual_table_review"}
        or len({check["check_id"] for check in checks}) != 2
        or len({check["artifact_sha256"] for check in checks}) != 2
    ):
        _fail("extraction_checks_not_independent")
    verified_at = _timestamp(extraction["verified_at"], "extraction_verified_at_invalid")
    if verified_at < retrieved_at or knowledge_time < verified_at:
        _fail("extraction_temporal_order_invalid")

    material = {
        "valid_period": valid_period,
        "estimate_status": snapshot["estimate_status"],
        "total_cargo_tonnes": total,
        "ports": ports,
        "commodities": commodities,
        "container_teu": separate_value,
        "joint_status": "not_observed",
        "joint_cells": [],
    }
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "source_id": snapshot["source_id"],
        "rights_decision_id": snapshot["rights_decision_id"],
        "source_artifact": {
            "url": source_url,
            "sha256": source_sha,
            "published_on": published_on,
            "retrieved_at": retrieved_at,
            "table_pages": pages,
        },
        "valid_period": valid_period,
        "knowledge_time": knowledge_time,
        "estimate_status": snapshot["estimate_status"],
        "total_cargo_tonnes": total,
        "ports": ports,
        "commodities": commodities,
        "container_teu": separate_value,
        "observation_sha256": _observation_digest(material),
        "extraction": {
            "method": extraction["method"],
            "checks": checks,
            "verified_at": verified_at,
        },
    }


def verify_source_artifact(validated: dict[str, Any], path: Path) -> None:
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise PortCommodityError("source_artifact_unreadable") from exc
    if actual != validated["source_artifact"]["sha256"]:
        _fail("source_artifact_digest_mismatch")


def verify_extraction_evidence(
    validated: dict[str, Any], evidence_paths: list[Path]
) -> None:
    checks = validated["extraction"]["checks"]
    if len(evidence_paths) != len(checks):
        _fail("extraction_evidence_count_invalid")
    expected = {check["artifact_sha256"]: check for check in checks}
    seen: set[str] = set()
    for path in evidence_paths:
        evidence, actual_sha = _read_object(path, "extraction_evidence_unreadable")
        check = expected.get(actual_sha)
        if check is None or actual_sha in seen:
            _fail("extraction_evidence_digest_mismatch")
        row = _object(
            evidence,
            {
                "schema_version",
                "check_id",
                "method",
                "source_artifact_sha256",
                "observation_sha256",
                "result",
            },
            "extraction_evidence_fields_invalid",
        )
        if (
            row["schema_version"] != "1.0.0"
            or row["check_id"] != check["check_id"]
            or row["method"] != check["method"]
            or row["source_artifact_sha256"] != validated["source_artifact"]["sha256"]
            or row["observation_sha256"] != validated["observation_sha256"]
            or row["result"] != "exact_match"
        ):
            _fail("extraction_evidence_mismatch")
        seen.add(actual_sha)
    if seen != set(expected):
        _fail("extraction_evidence_incomplete")


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
        rights = publication_guard._validate_rights_registry(
            rights_document, root, signers
        )
    except publication_guard.PublicationGuardError as exc:
        raise PortCommodityError(f"rights_{exc.code}") from exc
    source_id = registry["source"]["source_id"]
    source = rights.get(source_id)
    if source is None or source["decision_state"] != "approved":
        _fail("rights_not_approved")
    required = set(registry["source"]["required_permitted_uses"])
    if not required.issubset(source["permitted_uses"]):
        _fail("rights_use_not_approved")
    return source


def compile_snapshot(
    snapshot_path: Path,
    source_artifact_path: Path,
    extraction_evidence_paths: list[Path],
    *,
    root: Path = ROOT,
    registry_path: Path = REGISTRY_PATH,
    rights_path: Path = RIGHTS_PATH,
    signers_path: Path = SIGNERS_PATH,
) -> dict[str, Any]:
    registry, registry_sha = _registry(registry_path)
    snapshot, snapshot_sha = _read_object(snapshot_path, "snapshot_unreadable")
    validated = validate_snapshot(snapshot, registry)
    verify_source_artifact(validated, source_artifact_path)
    verify_extraction_evidence(validated, extraction_evidence_paths)
    source = _approved_source(
        root=root,
        registry=registry,
        rights_path=rights_path,
        signers_path=signers_path,
    )
    if validated["rights_decision_id"] != source["decision_id"]:
        _fail("snapshot_rights_decision_mismatch")
    total = validated["total_cargo_tonnes"]
    ports = [
        {**row, "share_basis_points": _share_basis_points(row["cargo_tonnes"], total)}
        for row in validated["ports"]
    ]
    commodities = [
        {**row, "share_basis_points": _share_basis_points(row["cargo_tonnes"], total)}
        for row in validated["commodities"]
    ]
    return {
        "_meta": {
            "schema_version": "1.0.0",
            "status": "rights_approved_marginals_only",
            "source_id": validated["source_id"],
            "source_artifact": validated["source_artifact"],
            "source_snapshot_sha256": snapshot_sha,
            "registry_sha256": registry_sha,
            "rights_decision_id": source["decision_id"],
            "valid_period": validated["valid_period"],
            "knowledge_time": validated["knowledge_time"],
            "estimate_status": validated["estimate_status"],
            "unit": "tonnes",
            "observation_sha256": validated["observation_sha256"],
            "extraction_checks": validated["extraction"]["checks"],
        },
        "coverage": {
            "port_frame_id": registry["port_frame"]["frame_id"],
            "ports_covered": len(ports),
            "ports_in_frame": len(registry["port_frame"]["member_ids"]),
            "national_port_coverage": None,
            "national_port_coverage_reason": registry["port_frame"]["excluded_scope"],
            "commodity_frame_id": registry["commodity_frame"]["frame_id"],
            "commodities_covered": len(commodities),
            "commodities_in_frame": len(registry["commodity_frame"]["member_ids"]),
        },
        "total_cargo_tonnes": total,
        "port_marginals": ports,
        "commodity_marginals": commodities,
        "separate_metrics": [
            {"metric_id": "container_teu", "unit": "teu", "value": validated["container_teu"]}
        ],
        "joint_port_commodity": {
            "status": "not_observed",
            "cells": [],
            "dependency_edges": [],
            "inference_allowed": False,
            "reason": registry["joint_observation"]["reason"],
        },
        "limitations": registry["limitations"],
    }


def validate_only(
    snapshot_path: Path,
    source_artifact_path: Path,
    extraction_evidence_paths: list[Path],
    *,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    registry, _ = _registry(registry_path)
    snapshot, snapshot_sha = _read_object(snapshot_path, "snapshot_unreadable")
    validated = validate_snapshot(snapshot, registry)
    verify_source_artifact(validated, source_artifact_path)
    verify_extraction_evidence(validated, extraction_evidence_paths)
    return {
        "status": "valid_internal_candidate",
        "snapshot_id": validated["snapshot_id"],
        "snapshot_sha256": snapshot_sha,
        "source_artifact_sha256": validated["source_artifact"]["sha256"],
        "observation_sha256": validated["observation_sha256"],
        "port_rows": len(validated["ports"]),
        "commodity_rows": len(validated["commodities"]),
        "marginals_reconcile": True,
        "joint_cells": 0,
        "publication_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument(
        "--extraction-evidence",
        type=Path,
        action="append",
        required=True,
        help="Repeat exactly twice: text-extraction and visual-review evidence JSON",
    )
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        result = (
            validate_only(
                args.snapshot,
                args.source_artifact,
                args.extraction_evidence,
            )
            if args.validate_only
            else compile_snapshot(
                args.snapshot,
                args.source_artifact,
                args.extraction_evidence,
            )
        )
    except PortCommodityError as exc:
        raise SystemExit(f"port_commodity_marginals: refused: {exc.code}") from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
