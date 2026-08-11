"""The Max redesign cannot silently delete or hide an existing capability."""

from __future__ import annotations

import copy
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from src import product_catalog
from src.product_catalog import ProductCatalogError

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


def _catalog() -> dict:
    return json.loads((ROOT / "design" / "public_product_catalog.json").read_text(encoding="utf-8"))


def _payload() -> dict:
    return json.loads((DOCS / "data" / "product_catalog.json").read_text(encoding="utf-8"))


def test_catalog_accounts_for_every_served_page_and_protects_every_product() -> None:
    result = product_catalog.check_public_surface()
    assert {key: value for key, value in result.items() if key != "route_floor_status"} == {
        "status": "pass",
        "catalog_version": "1.2.0",
        "pillar_count": 8,
        "protected_route_count": 39,
        "excluded_route_count": 5,
    }
    assert result["route_floor_status"] in {
        "bootstrap_no_prior_catalog",
        "checked_against_HEAD",
        "checked_against_HEAD^",
    }
    catalog = _catalog()
    served = {path.relative_to(DOCS).as_posix() for path in DOCS.rglob("*.html")}
    listed = {row["path"] for row in catalog["routes"]}
    excluded = {row["path"] for row in catalog["excluded_routes"]}
    assert served == listed | excluded
    protected_exclusions = {row["path"] for row in catalog["excluded_routes"] if row["protected"]}
    assert listed | protected_exclusions == set(catalog["protected_routes"])
    assert listed.isdisjoint(excluded)


def test_catalog_uses_the_exact_eight_locked_launch_pillars() -> None:
    catalog = _catalog()
    launch = json.loads(
        (ROOT / "design" / "igrm_max_launch_contract.json").read_text(encoding="utf-8")
    )
    assert [(row["id"], row["name"]) for row in catalog["pillars"]] == [
        (row["id"], row["name"]) for row in launch["pillars"]
    ]
    assigned = {row["pillar_id"] for row in catalog["routes"]}
    assert assigned == {row["id"] for row in catalog["pillars"]}


def test_public_catalog_is_an_exact_generated_payload() -> None:
    assert _payload() == product_catalog.build_public_payload()
    contract = json.loads((DOCS / "data" / "api_contract.json").read_text(encoding="utf-8"))
    endpoint = next(
        row for row in contract["endpoints"] if row["path"] == "data/product_catalog.json"
    )
    assert endpoint["stability"] == "stable"
    assert endpoint["frozen_fields"] == [
        "_meta",
        "primary_navigation",
        "pillars",
        "routes",
        "protected_routes",
        "excluded_routes",
        "removal_ledger",
    ]


def test_directory_links_every_product_and_never_promotes_author_operations() -> None:
    page = (DOCS / "products.html").read_text(encoding="utf-8")
    catalog = _catalog()
    for row in catalog["routes"]:
        href = "./" if row["path"] == "index.html" else row["path"]
        assert f'href="{href}"' in page, row["path"]
        assert row["label"] in page
    for row in catalog["excluded_routes"]:
        assert f'href="{row["path"]}"' not in page
    assert "Forecasting separation" in page
    for required in ("Start here", "Maps", "Methodology", "Explore every product"):
        assert required in (page + (DOCS / "index.html").read_text(encoding="utf-8"))


def test_explore_and_atlas_are_in_global_navigation_on_every_shell_route() -> None:
    from src.site_shell import PAGES

    for relative in PAGES:
        page = (DOCS / relative).read_text(encoding="utf-8")
        prefix = "/" if relative == "404.html" else ("../" if "/" in relative else "")
        assert f'href="{prefix}products.html"' in page, relative
        assert f'href="{prefix}atlas.html"' in page, relative
        assert f'href="{prefix}maps.html"' in page, relative
    homepage = (DOCS / "index.html").read_text(encoding="utf-8")
    assert 'href="products.html">Explore</a>' in homepage
    assert 'href="atlas.html">Atlas</a>' in homepage
    assert 'href="atlas.html"><span>02</span><strong>Atlas</strong>' in homepage


def test_atlas_hub_preserves_every_child_surface_and_its_maturity_boundary() -> None:
    page = (DOCS / "atlas.html").read_text(encoding="utf-8")
    for path in ("maps.html", "episode.html", "exposure.html", "dna.html", "shock.html"):
        assert f'href="{path}"' in page
    for boundary in (
        "Published observation",
        "Published utility",
        "Synthetic foundation",
        "0</dt><dd>production dependency-graph releases",
        "does not yet publish a comprehensive real firm–port–commodity–state dependency graph",
    ):
        assert boundary in page

    from src.site_shell import PAGES

    assert PAGES["atlas.html"].active == "atlas"
    for path in ("maps.html", "episode.html", "exposure.html", "dna.html", "shock.html"):
        assert PAGES[path].active == "atlas"


def test_route_omission_and_self_served_ghost_both_refuse() -> None:
    catalog = _catalog()
    missing = copy.deepcopy(catalog)
    missing["routes"] = [row for row in missing["routes"] if row["path"] != "maps.html"]
    with pytest.raises(ProductCatalogError, match="catalog_protected_routes_mismatch"):
        product_catalog.validate_catalog(missing)

    ghost = copy.deepcopy(catalog)
    ghost["routes"].append(
        {
            "path": "imaginary.html",
            "label": "Imaginary",
            "pillar_id": "atlas",
            "status": "live",
            "purpose": "This route does not exist.",
        }
    )
    ghost["protected_routes"].append("imaginary.html")
    with pytest.raises(ProductCatalogError, match="catalog_served_route_mismatch"):
        product_catalog.validate_catalog(ghost)


def test_route_floor_refuses_a_removal_without_an_earlier_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _catalog()
    current = copy.deepcopy(prior)
    current["routes"] = [row for row in current["routes"] if row["path"] != "maps.html"]
    current["protected_routes"].remove("maps.html")
    monkeypatch.setattr(product_catalog, "_catalog_at_revision", lambda revision: prior)
    with pytest.raises(ProductCatalogError, match="catalog_route_removed_without_prior_notice"):
        product_catalog.validate_route_continuity(current)


def test_protected_route_floor_is_append_only_across_commits() -> None:
    """A route needs a notice in an earlier commit and a full 90 days.

    The bootstrap commit has no parent catalog and therefore establishes the
    floor. Every later committed change is compared with its first parent.
    """

    previous = subprocess.run(
        ["git", "show", "HEAD^:design/public_product_catalog.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if previous.returncode != 0:
        return
    prior = json.loads(previous.stdout)
    current = _catalog()
    removed = set(prior["protected_routes"]) - set(current["protected_routes"])
    prior_notices = {row["path"]: row for row in prior["removal_ledger"]}
    effective = dt.date.fromisoformat(current["effective"])
    violations: list[str] = []
    for path in sorted(removed):
        notice = prior_notices.get(path)
        if notice is None:
            violations.append(f"{path}: no notice in the prior committed catalog")
            continue
        deprecated = dt.date.fromisoformat(notice["deprecated_on"])
        earliest = dt.date.fromisoformat(notice["earliest_removal"])
        if earliest < deprecated + dt.timedelta(days=90):
            violations.append(f"{path}: deprecation window is shorter than 90 days")
        if effective < earliest:
            violations.append(f"{path}: removed before {earliest.isoformat()}")
    assert not violations, "\n".join(violations)


def test_the_floor_compares_against_the_parent_when_the_catalog_is_committed() -> None:
    """The revision compared against must follow committed-ness, not layout.

    Every other test of the floor supplies the prior catalog itself, by
    monkeypatching `_catalog_at_revision`, so none of them exercises the
    line that decides WHICH revision to ask for. That line re-serialized
    the committed JSON and compared bytes; this catalog is hand-formatted
    one route per line, so the comparison was false even for an untouched
    checkout -- which is precisely what CI checks out. The floor compared
    HEAD with HEAD, a removal was absent from both sides, and a commit
    deleting maps.html against an empty removal_ledger returned
    {"status": "pass"} with exit 0. Reproduced before this test existed.
    """

    def at(revision: str) -> dict | None:
        shown = subprocess.run(
            ["git", "show", f"{revision}:design/public_product_catalog.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return json.loads(shown.stdout) if shown.returncode == 0 else None

    head = at("HEAD")
    if head is None:
        pytest.skip("no catalog committed at HEAD to compare against")
    status = product_catalog.check_public_surface()["route_floor_status"]
    if head != _catalog():
        # An uncommitted edit: HEAD is genuinely the state before it.
        assert status == "checked_against_HEAD"
    elif at("HEAD^") is None:
        # The commit that introduced the catalog establishes the floor.
        assert status == "bootstrap_no_prior_catalog"
    else:
        assert status == "checked_against_HEAD^", (
            "the catalog on disk is the one committed at HEAD, so the state "
            "before this change is HEAD^; comparing HEAD with HEAD lets a "
            "committed removal check against a copy of itself and pass"
        )


def test_check_cli_is_machine_readable_and_green() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src.product_catalog", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "pass"
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run: python -m src.product_catalog --check" in workflow
