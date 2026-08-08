"""The IGRM Max benchmark contract stays ambitious without claiming results."""

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "design" / "igrm_max_benchmark_contract.json"


def _load() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_benchmark_contract_is_target_only_and_fail_closed() -> None:
    contract = _load()
    policy = contract["claim_policy"]

    assert contract["status"] == "target_only"
    assert policy["default"] == "unlicensed"
    assert policy["overall_superiority_claim_allowed"] is False
    assert len(policy["required_comparison_properties"]) >= 10


def test_benchmark_roster_and_gates_are_complete() -> None:
    contract = _load()
    benchmarks = contract["benchmarks"]
    ids = [row["id"] for row in benchmarks]

    assert len(benchmarks) == 12
    assert len(ids) == len(set(ids))
    assert {
        "gpr",
        "acled_conflict_index",
        "icrg",
        "epu",
        "wui",
        "global_peace_index",
        "fragile_states_index",
        "inform_risk",
        "gscpi",
        "baltic_dry_index",
        "worldwide_governance_indicators",
        "blackrock_geopolitical_risk_dashboard",
    } == set(ids)

    required = {
        "id",
        "name",
        "canonical_source",
        "strength",
        "igrm_target",
        "claim_status",
        "claim_allowed",
        "gates",
    }
    for row in benchmarks:
        assert set(row) == required
        assert row["claim_status"] == "unlicensed"
        assert row["claim_allowed"] is False
        assert len(row["gates"]) >= 3
        assert all(isinstance(gate, str) and gate.endswith(".") for gate in row["gates"])

        parsed = urlparse(row["canonical_source"])
        assert parsed.scheme == "https"
        assert parsed.netloc


def test_spec_and_machine_contract_name_the_same_benchmarks() -> None:
    spec = (ROOT / "IGRM_MAX_SPEC.md").read_text(encoding="utf-8")
    for row in _load()["benchmarks"]:
        assert row["name"] in spec
