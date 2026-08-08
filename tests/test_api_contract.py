"""Regression locks for the frozen v2 API contract."""
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


def test_contract_is_self_citing_and_freezes_outcome_availability_fields():
    from src import stamp_meta

    contract = _contract()
    meta = contract["_meta"]
    for key, value in stamp_meta.universal_fields("api_contract.json").items():
        assert meta[key] == value

    event_study = next(e for e in contract["endpoints"]
                       if e["path"] == "data/event_study.json")
    assert {"available_outcomes", "unavailable_outcomes"} <= set(
        event_study["frozen_fields"])


def test_every_served_payload_is_in_the_contract():
    contract = _contract()
    listed = {e["path"] for e in contract["endpoints"]}
    for path in sorted(SITE_DATA.glob("*.json")):
        if path.name in ("api_contract.json", "decisions.json"):
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
            "a frozen field cannot be removed without a major version bump")


def test_operational_author_queue_is_not_a_public_endpoint():
    contract = _contract()
    listed = {e["path"] for e in contract["endpoints"]}
    assert "data/decisions.json" not in listed
    assert not (ROOT / "docs" / "decisions.html").exists()
    assert not (SITE_DATA / "decisions.json").exists()


def test_the_contract_matches_its_generator():
    """committed == generated, the sitemap discipline applied to the API.

    Found drifted in BOTH directions on 2026-08-07: the generator would
    have rolled back hand-refined text for the frozen AI-GPR vintage
    (fixed with an explicit OVERRIDES table -- a frozen payload cannot
    carry new _meta text, so the override is the sanctioned place), and
    the committed file lacked additive fields monthly.json and
    receipts_archive.json had already grown. Either direction of drift
    now fails here instead of surfacing as a 34-line surprise diff.
    """
    import subprocess
    import sys
    before = (SITE_DATA / "api_contract.json").read_bytes()
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_api_contract.py")],
                       capture_output=True, text=True, cwd=ROOT)
    after = (SITE_DATA / "api_contract.json").read_bytes()
    if before != after:
        (SITE_DATA / "api_contract.json").write_bytes(before)  # restore
    assert r.returncode == 0, f"generator failed: {r.stderr[-300:]}"
    assert before == after, (
        "docs/data/api_contract.json differs from what its generator "
        "produces. Update the payload/_meta, the OVERRIDES table, or "
        "regenerate -- but do not let the served promise and its "
        "generator disagree.")
