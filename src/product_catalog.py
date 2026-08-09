"""Validate and publish the no-capability-loss public product catalog.

The catalog is not a marketing inventory.  It reconciles every served HTML
route against one of the eight locked IGRM Max pillars or an explicit
non-product exclusion.  A route cannot disappear from the discoverable set by
accident: the protected-route floor is append-only and CI compares it with the
previous committed catalog.

Standalone::

    python -m src.product_catalog --check
    python -m src.product_catalog --write
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from src import stamp_meta

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "design" / "public_product_catalog.json"
LAUNCH_CONTRACT_PATH = ROOT / "design" / "igrm_max_launch_contract.json"
PUBLIC_PAYLOAD_PATH = ROOT / "docs" / "data" / "product_catalog.json"
DIRECTORY_PATH = ROOT / "docs" / "products.html"

EXPECTED_PILLARS = (
    "core",
    "atlas",
    "evidence_engine",
    "research_copilot",
    "observatory",
    "benchmark_lab",
    "institution",
    "distribution",
)
ALLOWED_ROUTE_STATUS = {"live", "public_draft", "experimental"}


class ProductCatalogError(ValueError):
    """Fail-closed catalog error with a stable machine reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ProductCatalogError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("catalog_json_duplicate_key", key)
        result[key] = value
    return result


def _read_object(path: Path, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProductCatalogError(code, str(path)) from exc
    if not isinstance(value, dict):
        _fail(code, str(path))
    return cast(dict[str, Any], value)


def _route(value: object, code: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        _fail(code)
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or ".." in parsed.parts
        or str(parsed) != value
        or parsed.suffix != ".html"
    ):
        _fail(code, value)
    return value


def _served_html() -> set[str]:
    return {
        path.relative_to(ROOT / "docs").as_posix()
        for path in (ROOT / "docs").rglob("*.html")
    }


def validate_catalog(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the canonical catalog or refuse any route/pillar drift."""

    value = catalog or _read_object(CATALOG_PATH, "catalog_unreadable")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("catalog_version") != "1.1.0"
        or value.get("effective") != "2026-08-09"
        or value.get("status") != "public_route_contract"
    ):
        _fail("catalog_identity_invalid")
    if not isinstance(value.get("scope_boundary"), str) or not value["scope_boundary"]:
        _fail("catalog_scope_boundary_missing")

    launch = _read_object(LAUNCH_CONTRACT_PATH, "launch_contract_unreadable")
    launch_pillars = launch.get("pillars")
    catalog_pillars = value.get("pillars")
    if not isinstance(launch_pillars, list) or not isinstance(catalog_pillars, list):
        _fail("catalog_pillars_invalid")
    launch_names = {
        row.get("id"): row.get("name")
        for row in launch_pillars
        if isinstance(row, dict)
    }
    observed_ids: list[str] = []
    for row in catalog_pillars:
        if not isinstance(row, dict):
            _fail("catalog_pillar_invalid")
        pillar_id = row.get("id")
        if not isinstance(pillar_id, str) or pillar_id in observed_ids:
            _fail("catalog_pillar_invalid")
        if row.get("name") != launch_names.get(pillar_id):
            _fail("catalog_pillar_launch_mismatch", pillar_id)
        if not isinstance(row.get("current_state"), str) or not isinstance(
            row.get("current_boundary"), str
        ):
            _fail("catalog_pillar_boundary_missing", pillar_id)
        observed_ids.append(pillar_id)
    if tuple(observed_ids) != EXPECTED_PILLARS:
        _fail("catalog_pillar_order_mismatch")

    raw_rows = value.get("routes")
    raw_exclusions = value.get("excluded_routes")
    raw_protected = value.get("protected_routes")
    raw_navigation = value.get("primary_navigation")
    raw_ledger = value.get("removal_ledger")
    if not all(
        isinstance(item, list)
        for item in (
            raw_rows,
            raw_exclusions,
            raw_protected,
            raw_navigation,
            raw_ledger,
        )
    ):
        _fail("catalog_route_collections_invalid")
    rows = cast(list[Any], raw_rows)
    exclusions = cast(list[Any], raw_exclusions)
    protected = cast(list[Any], raw_protected)
    navigation = cast(list[Any], raw_navigation)
    ledger = cast(list[Any], raw_ledger)

    route_rows: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            _fail("catalog_route_invalid")
        path = _route(row.get("path"), "catalog_route_path_invalid")
        if path in route_rows:
            _fail("catalog_route_duplicate", path)
        if row.get("pillar_id") not in EXPECTED_PILLARS:
            _fail("catalog_route_pillar_invalid", path)
        if row.get("status") not in ALLOWED_ROUTE_STATUS:
            _fail("catalog_route_status_invalid", path)
        for field in ("label", "purpose"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                _fail("catalog_route_text_missing", f"{path}:{field}")
        route_rows[path] = row

    exclusion_rows: dict[str, str] = {}
    protected_exclusions: set[str] = set()
    for row in exclusions:
        if not isinstance(row, dict):
            _fail("catalog_exclusion_invalid")
        path = _route(row.get("path"), "catalog_exclusion_path_invalid")
        reason = row.get("reason")
        if (
            path in exclusion_rows
            or not isinstance(reason, str)
            or not reason.strip()
            or not isinstance(row.get("protected"), bool)
        ):
            _fail("catalog_exclusion_invalid", path)
        exclusion_rows[path] = reason
        if row["protected"]:
            protected_exclusions.add(path)

    protected_routes = [_route(path, "catalog_protected_path_invalid") for path in protected]
    if len(protected_routes) != len(set(protected_routes)):
        _fail("catalog_protected_route_duplicate")
    if set(protected_routes) != set(route_rows) | protected_exclusions:
        _fail("catalog_protected_routes_mismatch")
    if set(route_rows) & set(exclusion_rows):
        _fail("catalog_route_exclusion_overlap")

    served = _served_html()
    accounted = set(route_rows) | set(exclusion_rows)
    if served != accounted:
        missing = sorted(served - accounted)
        ghost = sorted(accounted - served)
        _fail("catalog_served_route_mismatch", f"unaccounted={missing}; missing={ghost}")

    navigation_routes = [_route(path, "catalog_navigation_path_invalid") for path in navigation]
    if len(navigation_routes) != len(set(navigation_routes)):
        _fail("catalog_navigation_duplicate")
    if not set(navigation_routes) <= set(route_rows):
        _fail("catalog_navigation_route_missing")
    if set(navigation_routes) != {
        "start.html",
        "products.html",
        "atlas.html",
        "methodology.html",
        "validation.html",
        "analysis.html",
        "notes.html",
        "data.html",
    }:
        _fail("catalog_navigation_contract_mismatch")

    for item in ledger:
        if not isinstance(item, dict) or not {
            "path",
            "deprecated_on",
            "earliest_removal",
            "reason",
            "replacement",
        } <= set(item):
            _fail("catalog_removal_ledger_invalid")
    return value


def build_public_payload(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    value = validate_catalog(catalog)
    return {
        "_meta": {
            "what": (
                "The no-capability-loss public product catalog: every user-facing "
                "HTML route, its locked IGRM Max pillar, present maturity and "
                "claim boundary, plus explicit non-product exclusions."
            ),
            "definition": value["scope_boundary"],
            "catalog_version": value["catalog_version"],
            "effective": value["effective"],
            **stamp_meta.universal_fields("product_catalog.json"),
        },
        "primary_navigation": value["primary_navigation"],
        "pillars": value["pillars"],
        "routes": value["routes"],
        "protected_routes": value["protected_routes"],
        "excluded_routes": value["excluded_routes"],
        "removal_ledger": value["removal_ledger"],
    }


def _catalog_at_revision(revision: str) -> dict[str, Any] | None:
    relative = CATALOG_PATH.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout, object_pairs_hook=_unique_object)
    except (ProductCatalogError, json.JSONDecodeError) as exc:
        raise ProductCatalogError("catalog_prior_revision_invalid", revision) from exc
    if not isinstance(value, dict):
        _fail("catalog_prior_revision_invalid", revision)
    return cast(dict[str, Any], value)


def validate_route_continuity(current: dict[str, Any]) -> str:
    """Require a notice in an earlier commit and a full 90-day window."""

    committed = _catalog_at_revision("HEAD")
    if committed is None:
        return "bootstrap_no_prior_catalog"
    # Which revision holds the state BEFORE this change? If the catalog on
    # disk is the one already committed at HEAD, then HEAD *is* the change
    # under review and the state before it is HEAD^. The first form of this
    # test re-serialized the committed document with indent=2 and compared
    # bytes -- but this catalog is hand-formatted one route per line, so
    # the comparison was false even for an untouched checkout, which is
    # exactly what CI checks out. The floor therefore compared HEAD with
    # HEAD, where a removal is already absent on both sides: deleting
    # maps.html with an empty removal_ledger returned status "pass" and
    # exit 0. Comparing the parsed documents asks the question that was
    # meant, and no choice of layout can answer it wrongly.
    comparison_revision = "HEAD^" if committed == current else "HEAD"
    previous = _catalog_at_revision(comparison_revision)
    if previous is None:
        return "bootstrap_no_prior_catalog"
    prior_routes = previous.get("protected_routes")
    current_routes = current.get("protected_routes")
    prior_ledger = previous.get("removal_ledger")
    if not all(
        isinstance(item, list)
        for item in (prior_routes, current_routes, prior_ledger)
    ):
        _fail("catalog_prior_revision_invalid", comparison_revision)
    removed = set(cast(list[str], prior_routes)) - set(
        cast(list[str], current_routes)
    )
    notices = {
        row.get("path"): row
        for row in cast(list[Any], prior_ledger)
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    effective = dt.date.fromisoformat(cast(str, current["effective"]))
    for path in sorted(removed):
        notice = notices.get(path)
        if notice is None:
            _fail("catalog_route_removed_without_prior_notice", path)
        try:
            deprecated = dt.date.fromisoformat(cast(str, notice["deprecated_on"]))
            earliest = dt.date.fromisoformat(cast(str, notice["earliest_removal"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProductCatalogError("catalog_prior_notice_invalid", path) from exc
        if earliest < deprecated + dt.timedelta(days=90):
            _fail("catalog_prior_notice_too_short", path)
        if effective < earliest:
            _fail("catalog_route_removed_too_early", path)
    return f"checked_against_{comparison_revision}"


def check_public_surface() -> dict[str, object]:
    value = validate_catalog()
    continuity = validate_route_continuity(value)
    expected = build_public_payload(value)
    actual = _read_object(PUBLIC_PAYLOAD_PATH, "catalog_public_payload_missing")
    if actual != expected:
        _fail("catalog_public_payload_drift")
    try:
        page = DIRECTORY_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ProductCatalogError("catalog_directory_missing") from exc
    for row in value["routes"]:
        path = cast(dict[str, Any], row)["path"]
        href = "./" if path == "index.html" else path
        if f'href="{href}"' not in page:
            _fail("catalog_directory_link_missing", path)
    for path in value["primary_navigation"]:
        href = "./" if path == "index.html" else path
        if f'href="{href}"' not in page:
            _fail("catalog_primary_link_missing", path)
    return {
        "status": "pass",
        "catalog_version": value["catalog_version"],
        "pillar_count": len(value["pillars"]),
        "protected_route_count": len(value["protected_routes"]),
        "excluded_route_count": len(value["excluded_routes"]),
        "route_floor_status": continuity,
    }


def write_public_payload() -> None:
    payload = build_public_payload()
    PUBLIC_PAYLOAD_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the IGRM public product catalog")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        if args.write:
            write_public_payload()
        result = check_public_surface()
    except ProductCatalogError as exc:
        print(json.dumps({"status": "refused", "reason": exc.code, "detail": exc.detail}))
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
