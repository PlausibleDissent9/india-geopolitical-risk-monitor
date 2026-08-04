"""Regression locks for the 2026-08-04 frozen v1 API contract (V7)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"
CONTRACT_PATH = SITE_DATA / "api_contract.json"


def _contract():
    return json.loads(CONTRACT_PATH.read_text())


def test_contract_version_is_semver():
    version = _contract()["_meta"]["contract_version"]
    assert re.match(r"^\d+\.\d+\.\d+$", version), version


def test_every_served_payload_is_in_the_contract():
    contract = _contract()
    listed = {e["path"] for e in contract["endpoints"]}
    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in ("api_contract.json",):
            continue
        assert f"data/{path.name}" in listed, (
            f"{path.name} is served but missing from api_contract.json")
    for path in sorted(SITE_DATA.glob("*.csv")):
        assert f"data/{path.name}" in listed, (
            f"{path.name} is served but missing from api_contract.json")
    assert "feed.xml" in listed


def test_contract_lists_no_endpoint_that_no_longer_exists():
    contract = _contract()
    for e in contract["endpoints"]:
        if e["path"] == "feed.xml":
            assert (ROOT / "docs" / "feed.xml").exists()
            continue
        assert (ROOT / "docs" / e["path"]).exists(), (
            f"{e['path']} is in the contract but no longer served")


def test_frozen_fields_are_still_present_in_live_payloads():
    contract = _contract()
    for e in contract["endpoints"]:
        if e["format"] != "json" or not isinstance(e["frozen_fields"], list):
            continue
        live = json.loads((ROOT / "docs" / e["path"]).read_text())
        if isinstance(live, dict):
            live_keys = set(live.keys())
        elif isinstance(live, list) and live and isinstance(live[0], dict):
            live_keys = set(live[0].keys())
        else:
            continue
        missing = set(e["frozen_fields"]) - live_keys
        assert not missing, (
            f"{e['path']} dropped frozen field(s) {missing}; "
            "a frozen v1 field cannot be removed without a major version bump")
