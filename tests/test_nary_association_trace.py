"""Hostile conformance tests for OGES TRACE_NARY_ASSOCIATION."""

# ruff: noqa: E402, I001

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pytest
from src import capability_attestation
from src import event_ledger_extension as event_ext
from src import nary_association_trace as trace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from test_event_ledger_extension import _fixture as build_event_fixture  # noqa: E402
from test_source_frame_entity_foundry import (  # noqa: E402
    Fixture as FoundryFixture,
    _build_fixture as build_foundry_fixture,
    _reframe,
    _reseal as reseal_dependency_record,
    _resign_release,
    _sha,
    _universe_record_digest_substitution,
    _write_json,
    _write_package,
    _write_rights,
)

TRACE_EXTENSION = Path("standard/oges/extensions/nary-association-trace/0.1.0")
EVENT_EXTENSION = Path("standard/oges/extensions/event-ledger/0.1.0")
CONSEQUENCE_PROFILE = Path("standard/oges/extensions/consequence-plan/0.1.0/profile.json")

COVERED_CASES = {
    "valid_test_generated_signed_synthetic_trace",
    "tuple_decomposition",
    "cross_product_invention",
    "denominator_shrink",
    "mapping_state_omission",
    "blank_zero_missing_coercion",
    "unit_mismatch",
    "period_mismatch",
    "stale_or_wrong_universe",
    "crosswalk_hash_drift",
    "source_hash_drift",
    "rights_missing",
    "rights_expired",
    "rights_revoked",
    "rights_future_decision",
    "rights_future_registry",
    "rights_wrong_use",
    "rights_signer_role",
    "invalid_temporal_ordering",
    "projection_nonreconstructable",
    "projection_double_counted",
    "assumption_promoted_to_fact",
    "causal_dependency_impact_language",
    "model_authored_literal",
    "correction_over_blast",
    "correction_under_blast",
    "output_mutation_resealed",
    "path_traversal",
    "source_retargeting",
    "capability_overpromotion",
    "normative_surface_not_committed_together",
    "canonicalization_fixture_parity",
    "foundry_validated_bytes_swap",
    "foundry_profile_validated_swap",
    "event_context_validated_bytes_swap",
    "rights_snapshot_swap",
    "bound_contract_hash_parse_swap",
    "semantic_execution_identity_alias",
    "execution_contract_binding_mutation",
    "future_effective_correction",
    "non_effective_context_ref",
}


@dataclass
class TraceFixture:
    foundry: FoundryFixture
    root: Path
    profile: Path
    contract: Path
    request: Path
    output: Path


def _install_trace(root: Path) -> tuple[Path, Path]:
    shutil.copytree(ROOT / TRACE_EXTENSION, root / TRACE_EXTENSION, dirs_exist_ok=True)
    (root / CONSEQUENCE_PROFILE.parent).mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / CONSEQUENCE_PROFILE, root / CONSEQUENCE_PROFILE)
    shutil.copytree(ROOT / EVENT_EXTENSION, root / EVENT_EXTENSION, dirs_exist_ok=True)
    for relative in (
        "src/nary_association_trace.py",
        "src/event_ledger.py",
        "src/event_ledger_extension.py",
        "tests/test_nary_association_trace.py",
        "governance/nary_association_trace.json",
        "validation/event_ledger_canonicalization.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return (
        root / TRACE_EXTENSION / "profile.json",
        root / "governance/nary_association_trace.json",
    )


def _base_request(fixture: TraceFixture) -> dict[str, Any]:
    contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
    return {
        "object_type": "trace_nary_association_request",
        "schema_version": "0.1.0",
        "request_id": "trq:fixture.complete.frame.001",
        "trust_class": "test_generated_synthetic",
        "authority": {
            "kind": "registered_deterministic_method",
            "authority_id": "method:trace_nary_association",
        },
        "source_binding": {
            "source_id": contract["foundry"]["source_id"],
            "foundry_profile_sha256": contract["foundry"]["profile_sha256"],
            "foundry_source_contract_sha256": contract["foundry"][
                "source_contract_sha256"
            ],
            "release_manifest_sha256": contract["foundry"]["manifest_sha256"],
            "foundry_package_sha256": contract["foundry"]["package_sha256"],
        },
        "query": {
            "operator_id": "operator:trace.complete_registered_nary_frame",
            "output_profile_id": "output:trace.nary_association_paths",
            "selection": "complete_registered_joint_frame",
            "projection_id": "projection:trace.nary_identity_index",
            "valid_on": "2025-03-31",
            "knowledge_cutoff": "2026-08-09T11:00:00Z",
            "execution_as_of": "2026-08-09T12:00:00Z",
        },
        "proof_context": {
            "status": "not_requested",
            "event_bundle_sha256": None,
            "valid_on": None,
            "bindings": [],
        },
    }


def _refresh_trace(fixture: TraceFixture) -> None:
    implementation = fixture.root / "src/nary_association_trace.py"
    projection_path = fixture.root / TRACE_EXTENSION / "projection-registry.json"
    projection = json.loads(projection_path.read_text(encoding="utf-8"))
    projection["projections"][0]["implementation_sha256"] = _sha(implementation)
    _write_json(projection_path, projection)

    contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
    contract["foundry"].update(
        source_id="fixture_foundry_source",
        profile_path=str(fixture.foundry.profile.relative_to(fixture.root)),
        profile_sha256=_sha(fixture.foundry.profile),
        source_contract_path=str(fixture.foundry.contract.relative_to(fixture.root)),
        source_contract_sha256=_sha(fixture.foundry.contract),
        manifest_path=str(fixture.foundry.manifest.relative_to(fixture.root)),
        manifest_sha256=_sha(fixture.foundry.manifest),
        package_path=str(fixture.foundry.package.relative_to(fixture.root)),
        package_sha256=_sha(fixture.foundry.package),
    )
    contract["status"] = "enumerated_test_generated_synthetic"
    contract["runtime"].update(
        execution_allowed=True,
        trust_class="test_generated_synthetic",
    )
    contract["rights"]["allowed_signer_roles"] = ["test-only rights reviewer"]
    _write_json(fixture.contract, contract)

    request = (
        json.loads(fixture.request.read_text(encoding="utf-8"))
        if fixture.request.exists()
        else _base_request(fixture)
    )
    request["source_binding"] = {
        "source_id": contract["foundry"]["source_id"],
        "foundry_profile_sha256": contract["foundry"]["profile_sha256"],
        "foundry_source_contract_sha256": contract["foundry"][
            "source_contract_sha256"
        ],
        "release_manifest_sha256": contract["foundry"]["manifest_sha256"],
        "foundry_package_sha256": contract["foundry"]["package_sha256"],
    }
    _write_json(fixture.request, request)

    profile = json.loads(fixture.profile.read_text(encoding="utf-8"))
    for row in profile["bound_files"]:
        target = fixture.root / row["path"]
        row["sha256"] = _sha(target)
    profile["reference_implementation"] = {
        "path": "src/nary_association_trace.py",
        "sha256": _sha(implementation),
    }
    profile["conformance_test"] = {
        "path": "tests/test_nary_association_trace.py",
        "sha256": _sha(fixture.root / "tests/test_nary_association_trace.py"),
    }
    _write_json(fixture.profile, profile)


def _build_trace_fixture(tmp_path: Path) -> TraceFixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    foundry = build_foundry_fixture(tmp_path)
    profile, contract = _install_trace(foundry.root)
    fixture = TraceFixture(
        foundry=foundry,
        root=foundry.root,
        profile=profile,
        contract=contract,
        request=foundry.root / "trace/request.json",
        output=foundry.root / "trace/output.json",
    )
    _refresh_trace(fixture)
    return fixture


def _execute(fixture: TraceFixture) -> dict[str, Any]:
    return trace.execute_trace(
        manifest_path=fixture.foundry.manifest,
        package_path=fixture.foundry.package,
        request_path=fixture.request,
        root=fixture.root,
        profile_path=fixture.profile,
    )


def _write_output(fixture: TraceFixture, output: dict[str, Any]) -> None:
    _write_json(fixture.output, output)


def _validate_output(fixture: TraceFixture) -> dict[str, Any]:
    return trace.validate_trace_output(
        manifest_path=fixture.foundry.manifest,
        package_path=fixture.foundry.package,
        request_path=fixture.request,
        output_path=fixture.output,
        root=fixture.root,
        profile_path=fixture.profile,
    )


def _refuses_execute(fixture: TraceFixture, reason: str) -> None:
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        _execute(fixture)
    assert exc.value.code == reason


def _refuses_output(fixture: TraceFixture, output: dict[str, Any], reason: str) -> None:
    _write_output(fixture, trace.seal_record(output))
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        _validate_output(fixture)
    assert exc.value.code == reason


def test_real_ministry_reference_is_non_value_contract_refusal() -> None:
    result = trace.reference_status()
    assert result["status"] == "refused_contract_only"
    assert result["reason"] == "real_source_foundry_not_buildable"
    assert result["source_id"] == "india_major_ports_bps_2024_25"
    assert result["rights_authorized"] is False
    assert result["frame_contract_buildable"] is False
    assert result["trace_execution_allowed"] is False
    assert result["real_labels_emitted"] == 0
    assert result["real_tuples_emitted"] == 0
    assert result["real_values_emitted"] == 0
    assert result["real_traces_emitted"] == 0
    assert result["pages_emitted"] == 0
    assert result["apis_emitted"] == 0
    assert result["capability_state"] == "contract_only"
    assert result["authenticated_synthetic_verification_claimed"] is False
    assert result["production_trust"] is False
    assert result["legal_clearance_claimed"] is False


def test_canonicalization_fixture_matches_shared_typed_primitive() -> None:
    fixture = json.loads(
        (ROOT / "validation/event_ledger_canonicalization.json").read_text(
            encoding="utf-8"
        )
    )
    trace._canonicalization_fixture(fixture)
    rows = {row["id"]: row for row in fixture["fixtures"]}
    assert rows["one_integer"]["sha256"] == rows["one_decimal"]["sha256"]
    assert trace._typed_sha(-0.0) != trace._typed_sha(0.0)
    assert trace._typed_sha(1e-7) == rows["small_exponent_boundary"]["sha256"]
    assert trace._typed_sha("भारत · é · 𐀀") == rows["unicode_string"]["sha256"]
    assert trace._typed_sha({"𐀀": 2, "": 1}) == rows["utf8_key_order"][
        "sha256"
    ]
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        trace._typed_sha(9007199254740992)
    assert exc.value.code == "trace_typed_canonical_invalid"
    representative = {
        "object_type": "trace_typed_record_fixture",
        "record_sha256": "f" * 64,
        "value": {"one": 1.0, "change": -0.0, "label": "भारत"},
    }
    sealed = trace.seal_record(representative)
    assert sealed == event_ext.seal_record(representative)


def test_trace_tuple_wrapper_matches_browser_typed_canonical_if_available() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available in this environment")
    value = {
        "object_type": "trace_nary_tuple_canonical_value",
        "canonicalization_profile_id": "igrm-typed-canonical-f64-v1",
        "roles": [
            {"slot": "country", "provider_value": "भारत", "rank": 1.0},
            {"slot": "commodity", "provider_value": "X", "change": -0.0},
            {"slot": "port", "provider_value": "P1", "epsilon": 1e-7},
        ],
    }
    script = r"""
const crypto = require("crypto");
const typed = require(process.argv[1]);
const value = JSON.parse(process.argv[2]);
process.stdout.write(crypto.createHash("sha256").update(typed.encode(value), "utf8").digest("hex"));
"""
    result = subprocess.run(
        [
            node,
            "-e",
            script,
            str(ROOT / "docs/typed-canonical.js"),
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == trace._typed_sha(value)


def test_valid_trace_preserves_complete_tuple_denominators_and_time(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    output = _execute(fixture)
    _write_output(fixture, output)
    report = _validate_output(fixture)
    assert report["status"] == "conformant_test_generated_synthetic_trace"
    assert report["source_path_count"] == 6
    assert report["projection_row_count"] == 6
    assert report["capability_state"] == "contract_only"
    assert report["production_trust"] is False
    assert output["denominators"]["source_label_members"] == {
        "total": 7,
        "partition": {"matched": 6, "unmatched": 1, "ambiguous": 0, "withheld": 0},
    }
    assert output["denominators"]["joint_cells"]["value_partition"] == {
        "observed_positive": 1,
        "observed_zero": 1,
        "source_blank": 1,
        "source_missing": 1,
        "suppressed": 1,
        "not_applicable": 1,
    }
    assert output["denominators"]["mass"]["total_value"] == 5
    assert output["denominators"]["mass"]["unit"] == "thousand_metric_tonnes"
    assert output["denominators"]["paths"] == {
        "expected": 6,
        "emitted": 6,
        "omitted": 0,
    }
    assert all(len(path["roles"]) == 3 for path in output["paths"])
    assert {path["value_status"] for path in output["paths"]} == {
        "observed_positive",
        "observed_zero",
        "source_blank",
        "source_missing",
        "suppressed",
        "not_applicable",
    }
    assert output["paths"][0]["time"] == {
        "source_observed_at": "2025-04-01T00:00:00Z",
        "valid_period": {
            "label": "2024-25",
            "start": "2024-04-01",
            "end": "2025-03-31",
            "time_basis": "fiscal_year",
        },
        "retrieval_available_at": "2026-08-09T09:00:00Z",
        "system_compiled_at": "2026-08-09T11:00:00Z",
    }
    assert output["projection"]["source_fact_status"] == "projection_not_source_fact"
    assert output["projection"]["unique_origin_count"] == 6
    assert output["guarantees"] == {
        "source_tuple_decomposed": False,
        "cross_product_invented": False,
        "binary_edge_emitted": False,
        "causal_claim_emitted": False,
        "dependency_claim_emitted": False,
        "impact_claim_emitted": False,
        "forecast_emitted": False,
        "advice_emitted": False,
        "live_state_claimed": False,
        "all_india_coverage_claimed": False,
        "model_literal_accepted": False,
    }


def test_semantic_execution_identity_changes_with_projection(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    projected = _execute(fixture)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["query"]["projection_id"] = None
    _write_json(fixture.request, request)
    unprojected = _execute(fixture)
    assert projected["query"]["request_id"] == unprojected["query"]["request_id"]
    assert projected["query"]["execution_as_of"] == unprojected["query"][
        "execution_as_of"
    ]
    assert projected["execution_id"] != unprojected["execution_id"]
    assert projected["method"]["run_id"] != unprojected["method"]["run_id"]
    assert projected["execution_contract"]["request_semantic_sha256"] != (
        unprojected["execution_contract"]["request_semantic_sha256"]
    )
    assert projected["execution_contract"]["request_transport_sha256"] != (
        unprojected["execution_contract"]["request_transport_sha256"]
    )


def test_semantic_execution_identity_changes_with_proof_context(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["query"]["knowledge_cutoff"] = "2026-08-09T14:30:00Z"
    request["query"]["execution_as_of"] = "2026-08-09T15:00:00Z"
    _write_json(fixture.request, request)
    without_context = _execute(fixture)
    _install_correction_context(fixture)
    with_context = _execute(fixture)
    assert without_context["query"] == with_context["query"]
    assert without_context["execution_id"] != with_context["execution_id"]
    assert without_context["method"]["run_id"] != with_context["method"]["run_id"]


def test_resealed_execution_contract_binding_mutation_refuses(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    output = _execute(fixture)
    output["execution_contract"]["trace_request_schema_sha256"] = "f" * 64
    _refuses_output(fixture, output, "trace_output_result_mismatch")


OutputMutation = Callable[[dict[str, Any]], None]


def _tuple_decomposition(output: dict[str, Any]) -> None:
    output["paths"][0]["roles"][2] = copy.deepcopy(output["paths"][0]["roles"][1])
    output["paths"][0]["tuple_sha256"] = "a" * 64


def _cross_product(output: dict[str, Any]) -> None:
    output["paths"][0]["roles"][1]["provider_value"] = "Y"
    output["paths"][0]["tuple_sha256"] = "b" * 64


def _denominator_shrink(output: dict[str, Any]) -> None:
    output["denominators"]["paths"]["expected"] = 5


def _mapping_omission(output: dict[str, Any]) -> None:
    output["denominators"]["source_label_members"]["partition"]["unmatched"] = 0
    output["denominators"]["source_label_members"]["total"] = 6


def _blank_zero(output: dict[str, Any]) -> None:
    row = next(path for path in output["paths"] if path["value_status"] == "source_blank")
    row["value_status"] = "observed_zero"
    row["measure"] = {
        "value": 0,
        "unit": "thousand_metric_tonnes",
        "scale_factor": 1000,
        "denominator": "exact synthetic joint source cell",
    }


def _unit_mismatch(output: dict[str, Any]) -> None:
    output["paths"][0]["measure"]["unit"] = "tonnes"


def _period_mismatch(output: dict[str, Any]) -> None:
    output["paths"][0]["period"]["end"] = "2025-04-01"
    output["paths"][0]["time"]["valid_period"]["end"] = "2025-04-01"


def _projection_nonreconstructable(output: dict[str, Any]) -> None:
    output["projection"]["rows"][0]["origin_observation_id"] = "depobs:invented.origin"


def _projection_double(output: dict[str, Any]) -> None:
    row = copy.deepcopy(output["projection"]["rows"][0])
    row["projection_row_id"] = "prjrow:double.count"
    output["projection"]["rows"].append(row)
    output["projection"]["projection_row_count"] = 7


def _output_reseal(output: dict[str, Any]) -> None:
    output["limitation_codes"][0] = "association_boundary_mutated"


@pytest.mark.parametrize(
    ("case_id", "mutation"),
    [
        ("tuple_decomposition", _tuple_decomposition),
        ("cross_product_invention", _cross_product),
        ("denominator_shrink", _denominator_shrink),
        ("mapping_state_omission", _mapping_omission),
        ("blank_zero_missing_coercion", _blank_zero),
        ("unit_mismatch", _unit_mismatch),
        ("period_mismatch", _period_mismatch),
        ("projection_nonreconstructable", _projection_nonreconstructable),
        ("projection_double_counted", _projection_double),
        ("output_mutation_resealed", _output_reseal),
    ],
)
def test_resealed_output_mutations_cannot_change_deterministic_result(
    tmp_path: Path, case_id: str, mutation: OutputMutation
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    output = _execute(fixture)
    mutation(output)
    _refuses_output(fixture, output, "trace_output_result_mismatch")


@pytest.mark.parametrize(
    ("value_status", "measure_value"),
    [
        ("source_blank", 2),
        ("source_missing", 2),
        ("suppressed", 2),
        ("not_applicable", 2),
        ("observed_zero", 2),
        ("observed_positive", 0),
    ],
)
def test_output_schema_preserves_typed_value_boundary(
    tmp_path: Path, value_status: str, measure_value: int
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    output = _execute(fixture)
    row = next(path for path in output["paths"] if path["value_status"] == value_status)
    row["measure"] = {
        "value": measure_value,
        "unit": "thousand_metric_tonnes",
        "scale_factor": 1000,
        "denominator": "exact synthetic joint source cell",
    }
    _refuses_output(fixture, output, "trace_output_schema_invalid")


@pytest.mark.parametrize(
    ("case_id", "field", "value"),
    [
        ("assumption_promoted_to_fact", "assumption_promoted_to_fact", True),
        (
            "causal_dependency_impact_language",
            "claim_literal",
            "causal dependency impact",
        ),
    ],
)
def test_closed_output_schema_refuses_fact_or_claim_language(
    tmp_path: Path, case_id: str, field: str, value: object
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    output = _execute(fixture)
    output[field] = value
    _refuses_output(fixture, output, "trace_output_schema_invalid")


def test_model_authored_literal_is_not_a_plan_surface(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["authority"] = {
        "kind": "model",
        "authority_id": "model:invented",
        "literal": "trace a dependency",
    }
    _write_json(fixture.request, request)
    _refuses_execute(fixture, "trace_request_schema_invalid")


def test_foundry_universe_crosswalk_and_source_drift_refuse_before_trace(
    tmp_path: Path,
) -> None:
    universe_fixture = _build_trace_fixture(tmp_path / "universe")
    _universe_record_digest_substitution(universe_fixture.foundry)
    _refresh_trace(universe_fixture)
    _refuses_execute(universe_fixture, "universe_denominator_mismatch")

    crosswalk_fixture = _build_trace_fixture(tmp_path / "crosswalk")
    package = json.loads(crosswalk_fixture.foundry.package.read_text(encoding="utf-8"))
    crosswalk = package["dependency_bundle"]["crosswalks"][0]
    crosswalk["frame_record_sha256"] = "b" * 64
    reseal_dependency_record(crosswalk)
    _write_package(crosswalk_fixture.foundry, package)
    _refresh_trace(crosswalk_fixture)
    _refuses_execute(crosswalk_fixture, "crosswalk_frame_binding_invalid")

    source_fixture = _build_trace_fixture(tmp_path / "source")
    package = json.loads(source_fixture.foundry.package.read_text(encoding="utf-8"))
    package["source_contract_sha256"] = "c" * 64
    _write_package(source_fixture.foundry, package)
    _refresh_trace(source_fixture)
    _refuses_execute(source_fixture, "source_contract_digest_mismatch")


def test_foundry_validated_bytes_must_equal_captured_trace_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    assert len(_execute(fixture)["paths"]) == 6
    release_signature = fixture.root / "canonical/release.sig"
    package_evidence = fixture.foundry.objects["evd:fixture.foundry.package"]
    watched = [
        fixture.foundry.package,
        package_evidence,
        fixture.foundry.manifest,
        release_signature,
    ]
    version_a = {path: path.read_bytes() for path in watched}
    package = json.loads(fixture.foundry.package.read_text(encoding="utf-8"))
    package["package_id"] = "foundry:fixture.unloaded.002"
    _write_package(fixture.foundry, package)
    version_b = {path: path.read_bytes() for path in watched}
    for path, payload in version_a.items():
        path.write_bytes(payload)

    original = trace.source_frame_entity_foundry.validate_foundry_release

    def validate_version_b(**kwargs: Any) -> dict[str, Any]:
        for path, payload in version_b.items():
            path.write_bytes(payload)
        try:
            return original(**kwargs)
        finally:
            for path, payload in version_a.items():
                path.write_bytes(payload)

    monkeypatch.setattr(
        trace.source_frame_entity_foundry,
        "validate_foundry_release",
        validate_version_b,
    )
    _refuses_execute(fixture, "trace_foundry_validated_bytes_mismatch")


def test_foundry_validated_profile_must_equal_captured_trace_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    assert len(_execute(fixture)["paths"]) == 6
    profile_path = fixture.foundry.profile
    version_a = profile_path.read_bytes()
    version_b = json.dumps(
        json.loads(version_a),
        ensure_ascii=False,
        indent=1,
    ).encode("utf-8")
    assert hashlib.sha256(version_a).digest() != hashlib.sha256(version_b).digest()
    original = trace.source_frame_entity_foundry.validate_foundry_release

    def validate_version_b(**kwargs: Any) -> dict[str, Any]:
        profile_path.write_bytes(version_b)
        try:
            return original(**kwargs)
        finally:
            profile_path.write_bytes(version_a)

    monkeypatch.setattr(
        trace.source_frame_entity_foundry,
        "validate_foundry_release",
        validate_version_b,
    )
    _refuses_execute(fixture, "trace_foundry_validated_bytes_mismatch")


def test_bound_contract_hash_and_parse_use_one_captured_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    target = fixture.contract
    version_a = target.read_bytes()
    weakened = json.loads(version_a)
    weakened["projection_policy"]["binary_projection_allowed"] = True
    version_b = (
        json.dumps(weakened, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    original_read = Path.read_bytes
    original_parse = trace._parse_json_bytes
    state = {"swapped": False}

    def read_then_swap(path: Path) -> bytes:
        payload = original_read(path)
        if path.resolve() == target.resolve() and not state["swapped"]:
            target.write_bytes(version_b)
            state["swapped"] = True
        return payload

    def parse_then_restore(raw: bytes, code: str) -> dict[str, Any]:
        parsed = original_parse(raw, code)
        if state["swapped"] and raw == version_a:
            target.write_bytes(version_a)
        return parsed

    monkeypatch.setattr(Path, "read_bytes", read_then_swap)
    monkeypatch.setattr(trace, "_parse_json_bytes", parse_then_restore)
    assert len(_execute(fixture)["paths"]) == 6
    assert state["swapped"] is True


def _update_signer_snapshot(
    fixture: TraceFixture, *, revoked_on: str | None = None, role: str | None = None
) -> None:
    signers_path = fixture.root / "governance/rights_signers.json"
    signers = json.loads(signers_path.read_text(encoding="utf-8"))
    if revoked_on is not None:
        signers["signers"][0]["revoked_on"] = revoked_on
    if role is not None:
        signers["signers"][0]["role"] = role
    _write_json(signers_path, signers)
    package = json.loads(fixture.foundry.package.read_text(encoding="utf-8"))
    for observation in package["dependency_bundle"]["observations"]:
        observation["source"]["rights_signers_sha256"] = _sha(signers_path)
    _reframe(package["dependency_bundle"])
    _write_package(fixture.foundry, package)
    _refresh_trace(fixture)


def test_rights_missing_expired_revoked_wrong_use_and_role_fail_closed(
    tmp_path: Path,
) -> None:
    missing = _build_trace_fixture(tmp_path / "missing")
    rights_path = missing.root / "governance/source_rights_registry.json"
    registry = json.loads(rights_path.read_text(encoding="utf-8"))
    registry["sources"] = []
    _write_json(rights_path, registry)
    _refuses_execute(missing, "canonical_release_invalid")

    expired = _build_trace_fixture(tmp_path / "expired")
    request = json.loads(expired.request.read_text(encoding="utf-8"))
    request["query"]["knowledge_cutoff"] = "2027-08-10T11:00:00Z"
    request["query"]["execution_as_of"] = "2027-08-10T12:00:00Z"
    _write_json(expired.request, request)
    _refuses_execute(expired, "trace_rights_expired")

    revoked = _build_trace_fixture(tmp_path / "revoked")
    _update_signer_snapshot(revoked, revoked_on="2026-08-10")
    request = json.loads(revoked.request.read_text(encoding="utf-8"))
    request["query"]["knowledge_cutoff"] = "2026-08-10T11:00:00Z"
    request["query"]["execution_as_of"] = "2026-08-10T12:00:00Z"
    _write_json(revoked.request, request)
    _refuses_execute(revoked, "trace_rights_signer_inactive")

    wrong_use = _build_trace_fixture(tmp_path / "wrong-use")
    rights_path = wrong_use.root / "governance/source_rights_registry.json"
    source = json.loads(rights_path.read_text(encoding="utf-8"))["sources"][0]
    source["permitted_uses"] = ["cite_metadata", "publish_derived_value"]
    _write_rights(wrong_use.foundry, wrong_use.root, source)
    _resign_release(wrong_use.foundry, rebind_package=False)
    _refresh_trace(wrong_use)
    _refuses_execute(wrong_use, "canonical_release_invalid")

    wrong_role = _build_trace_fixture(tmp_path / "wrong-role")
    _update_signer_snapshot(wrong_role, role="unregistered trace signer")
    _refuses_execute(wrong_role, "trace_rights_signer_role_forbidden")


def test_future_rights_state_cannot_authorize_earlier_trace_execution(
    tmp_path: Path,
) -> None:
    fixture = _build_trace_fixture(tmp_path / "decision")
    rights_path = fixture.root / "governance/source_rights_registry.json"
    source = json.loads(rights_path.read_text(encoding="utf-8"))["sources"][0]
    source["reviewed_on"] = "2026-12-01"
    source["review_due"] = "2027-12-01"
    _write_rights(fixture.foundry, fixture.root, source)
    package = json.loads(fixture.foundry.package.read_text(encoding="utf-8"))
    rights_sha = _sha(rights_path)
    signers_sha = _sha(fixture.root / "governance/rights_signers.json")
    for observation in package["dependency_bundle"]["observations"]:
        observation["source"]["rights_decision_artifact_sha256"] = source[
            "decision_artifact_sha256"
        ]
        observation["source"]["rights_registry_sha256"] = rights_sha
        observation["source"]["rights_signers_sha256"] = signers_sha
    _reframe(package["dependency_bundle"])
    _write_package(fixture.foundry, package)
    _refresh_trace(fixture)
    _refuses_execute(fixture, "canonical_release_invalid")

    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        trace._trace_rights(
            root=fixture.root,
            source_id=source["source_id"],
            required_uses=(
                "cite_metadata",
                "publish_derived_value",
                "publish_extract",
            ),
            allowed_roles={"test-only rights reviewer"},
            as_of=trace._utc("2026-08-09T12:00:00Z", "test_time_invalid"),
        )
    assert exc.value.code == "trace_rights_decision_not_yet_effective"

    fixture = _build_trace_fixture(tmp_path / "registry")
    rights_path = fixture.root / "governance/source_rights_registry.json"
    registry = json.loads(rights_path.read_text(encoding="utf-8"))
    registry["effective"] = "2026-12-01"
    _write_json(rights_path, registry)
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        trace._trace_rights(
            root=fixture.root,
            source_id=registry["sources"][0]["source_id"],
            required_uses=(
                "cite_metadata",
                "publish_derived_value",
                "publish_extract",
            ),
            allowed_roles={"test-only rights reviewer"},
            as_of=trace._utc("2026-08-09T12:00:00Z", "test_time_invalid"),
        )
    assert exc.value.code == "trace_rights_registry_not_yet_effective"


def test_foundry_and_execution_rights_snapshots_cannot_be_composed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    original = trace.source_frame_entity_foundry.validate_foundry_release

    def validate_then_expand_rights(**kwargs: Any) -> dict[str, Any]:
        result = original(**kwargs)
        rights_path = fixture.root / "governance/source_rights_registry.json"
        source = json.loads(rights_path.read_text(encoding="utf-8"))["sources"][0]
        source["decision_id"] = "fixture-foundry-rights-expanded-2026-08-09"
        source["permitted_uses"].append("model_processing")
        _write_rights(fixture.foundry, fixture.root, source)
        return result

    monkeypatch.setattr(
        trace.source_frame_entity_foundry,
        "validate_foundry_release",
        validate_then_expand_rights,
    )
    _refuses_execute(fixture, "trace_rights_snapshot_mismatch")


def test_invalid_time_order_source_retarget_and_path_traversal_refuse(
    tmp_path: Path,
) -> None:
    temporal = _build_trace_fixture(tmp_path / "time")
    request = json.loads(temporal.request.read_text(encoding="utf-8"))
    request["query"]["knowledge_cutoff"] = "2026-08-09T08:59:59Z"
    _write_json(temporal.request, request)
    _refuses_execute(temporal, "trace_time_order_invalid")

    retarget = _build_trace_fixture(tmp_path / "retarget")
    request = json.loads(retarget.request.read_text(encoding="utf-8"))
    request["source_binding"]["source_id"] = "fixture_retargeted_source"
    _write_json(retarget.request, request)
    _refuses_execute(retarget, "trace_foundry_binding_mismatch")

    traversal = _build_trace_fixture(tmp_path / "traversal")
    outside = tmp_path / "outside-request.json"
    _write_json(outside, json.loads(traversal.request.read_text(encoding="utf-8")))
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        trace.execute_trace(
            manifest_path=traversal.foundry.manifest,
            package_path=traversal.foundry.package,
            request_path=outside,
            root=traversal.root,
            profile_path=traversal.profile,
        )
    assert exc.value.code == "trace_request_path_invalid"

    alternate_profile = traversal.root / "trace/alternate-profile.json"
    shutil.copy2(traversal.profile, alternate_profile)
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        trace.execute_trace(
            manifest_path=traversal.foundry.manifest,
            package_path=traversal.foundry.package,
            request_path=traversal.request,
            root=traversal.root,
            profile_path=alternate_profile,
        )
    assert exc.value.code == "profile_trust_root_invalid"


def test_source_retrieval_system_time_collapse_refuses_signed_input(
    tmp_path: Path,
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    package = json.loads(fixture.foundry.package.read_text(encoding="utf-8"))
    for observation in package["dependency_bundle"]["observations"]:
        observation["knowledge_available_at"] = observation["observed_at"]
    _reframe(package["dependency_bundle"])
    _write_package(fixture.foundry, package)
    _refresh_trace(fixture)
    _refuses_execute(fixture, "trace_time_order_invalid")


def test_temporal_pairing_is_python39_compatible_and_length_strict() -> None:
    observed = trace._utc("2025-04-01T00:00:00Z", "unexpected")
    retrieval = trace._utc("2026-08-09T09:00:00Z", "unexpected")
    compiled = trace._utc("2026-08-09T11:00:00Z", "unexpected")
    assert list(trace._temporal_triples([observed], [retrieval], [compiled])) == [
        (observed, retrieval, compiled)
    ]
    with pytest.raises(trace.NaryAssociationTraceError) as exc:
        list(trace._temporal_triples([observed], [], [compiled]))
    assert exc.value.code == "trace_time_order_invalid"


def _install_correction_context(
    fixture: TraceFixture,
) -> tuple[dict[str, Any], dict[str, Any]]:
    event_fixture, bundle_path, bundle = build_event_fixture(
        fixture.root / "event-context"
    )
    unaffected_episode = event_ext.seal_record(
        {
            "object_type": "episode",
            "schema_version": "0.1.0",
            "episode_id": "epi:oges.fixture.unaffected.001",
            "record_sha256": "0" * 64,
            "revision": 1,
            "supersedes_episode_id": None,
            "episode_kind": "cross_source_cluster",
            "episode_state": "clustering_proposal",
            "valid_from": "2026-08-08T00:00:00Z",
            "valid_to": "2026-08-10T23:59:59Z",
            "known_at": "2026-08-08T13:00:00Z",
            "formation": {
                "authority_kind": "model_clustering_proposal",
                "authority_id": "model:oges.fixture.unaffected",
                "implementation_sha256": None,
                "proposal_confidence": 0.1,
            },
            "claim_members": [],
            "event_links": [],
        }
    )
    for snapshot in bundle["snapshots"]:
        snapshot["episodes"].append(copy.deepcopy(unaffected_episode))
        snapshot["counts"]["episodes"] += 1
    bundle = event_ext.seal_record(bundle)
    _write_json(bundle_path, bundle)
    validated = event_ext.validate_bundle(
        bundle_path,
        root=event_fixture.root,
        profile_path=event_fixture.root / EVENT_EXTENSION / "profile.json",
    )
    assert event_ext.summary(validated)["production_trust"] is False

    contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
    contract["event_context"] = {
        "status": "registered_synthetic_event_extension",
        "root_path": str(event_fixture.root.relative_to(fixture.root)),
        "bundle_path": str(bundle_path.relative_to(event_fixture.root)),
        "bundle_sha256": _sha(bundle_path),
        "profile_path": str(
            (event_fixture.root / EVENT_EXTENSION / "profile.json").relative_to(
                event_fixture.root
            )
        ),
        "profile_sha256": _sha(event_fixture.root / EVENT_EXTENSION / "profile.json"),
    }
    _write_json(fixture.contract, contract)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["query"]["knowledge_cutoff"] = "2026-08-09T14:30:00Z"
    request["query"]["execution_as_of"] = "2026-08-09T15:00:00Z"
    claim = bundle["snapshots"][1]["claims"][0]
    request["proof_context"] = {
        "status": "registered_event_extension",
        "event_bundle_sha256": _sha(bundle_path),
        "valid_on": "2026-08-08",
        "bindings": [
            {
                "proof_id": "prf:trace.corrected.claim",
                "origin_observation_id": "depobs:fixture.foundry.1",
                "context_object": {
                    "object_type": "claim",
                    "object_id": claim["claim_id"],
                    "record_sha256": claim["record_sha256"],
                },
            },
            {
                "proof_id": "prf:trace.unaffected.episode",
                "origin_observation_id": "depobs:fixture.foundry.2",
                "context_object": {
                    "object_type": "episode",
                    "object_id": unaffected_episode["episode_id"],
                    "record_sha256": unaffected_episode["record_sha256"],
                },
            },
        ],
    }
    _write_json(fixture.request, request)
    _refresh_trace(fixture)
    return claim, unaffected_episode


def _move_correction_to_future(
    fixture: TraceFixture,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
    event_contract = contract["event_context"]
    bundle_path = (
        fixture.root / event_contract["root_path"] / event_contract["bundle_path"]
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    predecessor = bundle["snapshots"][1]["claims"][0]
    successor = bundle["snapshots"][1]["claims"][1]
    successor["valid_from"] = "2026-08-10T09:00:00Z"
    sealed_successor = event_ext.seal_record(successor)
    bundle["snapshots"][1]["claims"][1] = sealed_successor
    correction = bundle["snapshots"][1]["correction_impacts"][0]
    correction["valid_from"] = "2026-08-10T09:00:00Z"
    transition = next(
        row
        for row in correction["transitions"]
        if row["successor"]["object_type"] == "claim"
    )
    old_hash = transition["successor"]["record_sha256"]
    transition["successor"]["record_sha256"] = sealed_successor["record_sha256"]
    affected = next(
        row
        for row in correction["blast_radius"]["affected_objects"]
        if row["object_type"] == "claim" and row["record_sha256"] == old_hash
    )
    affected["record_sha256"] = sealed_successor["record_sha256"]
    correction["blast_radius"]["affected_objects"] = sorted(
        correction["blast_radius"]["affected_objects"],
        key=lambda row: (row["object_type"], row["object_id"], row["record_sha256"]),
    )
    bundle["snapshots"][1]["correction_impacts"][0] = event_ext.seal_record(correction)
    _write_json(bundle_path, event_ext.seal_record(bundle))
    contract["event_context"]["bundle_sha256"] = _sha(bundle_path)
    _write_json(fixture.contract, contract)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["proof_context"]["event_bundle_sha256"] = _sha(bundle_path)
    _write_json(fixture.request, request)
    _refresh_trace(fixture)
    return predecessor, sealed_successor


def test_correction_impact_invalidates_exact_proof_not_source_paths(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    baseline_paths = _execute(fixture)["paths"]
    _install_correction_context(fixture)
    output = _execute(fixture)
    assert output["paths"] == baseline_paths
    proofs = {row["proof_id"]: row for row in output["proof_outputs"]}
    assert proofs["prf:trace.corrected.claim"]["link_status"] == (
        "invalidated_by_correction"
    )
    assert proofs["prf:trace.corrected.claim"]["source_fact_claimed"] is False
    assert proofs["prf:trace.unaffected.episode"]["link_status"] == (
        "no_registered_association"
    )
    assert proofs["prf:trace.unaffected.episode"]["affected_by_correction_ids"] == []
    correction = output["correction_reports"][0]
    assert correction["affected_proof_ids"] == ["prf:trace.corrected.claim"]
    assert correction["affected_trace_ids"] == []
    assert correction["unaffected_trace_count"] == 6
    assert correction["output_effect"] == (
        "proof_invalidation_only_source_paths_immutable"
    )


def test_known_future_correction_does_not_invalidate_active_predecessor(
    tmp_path: Path,
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    _install_correction_context(fixture)
    _move_correction_to_future(fixture)
    output = _execute(fixture)
    proof = next(
        row
        for row in output["proof_outputs"]
        if row["proof_id"] == "prf:trace.corrected.claim"
    )
    assert proof["link_status"] == "no_registered_association"
    assert proof["context_temporal_status"] == "active_on_valid_date"
    assert proof["affected_by_correction_ids"] == []
    correction = output["correction_reports"][0]
    assert correction["temporal_status"] == "known_future_effective_not_applied"
    assert correction["affected_proof_ids"] == []
    assert correction["output_effect"] == "known_not_effective_no_output_change"


def test_active_successor_is_accepted_after_correction_valid_date(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    _install_correction_context(fixture)
    _, successor = _move_correction_to_future(fixture)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["proof_context"]["valid_on"] = "2026-08-10"
    request["proof_context"]["bindings"][0]["context_object"] = {
        "object_type": "claim",
        "object_id": successor["claim_id"],
        "record_sha256": successor["record_sha256"],
    }
    _write_json(fixture.request, request)
    output = _execute(fixture)
    proof = next(
        row
        for row in output["proof_outputs"]
        if row["proof_id"] == "prf:trace.corrected.claim"
    )
    assert proof["link_status"] == "no_registered_association"
    assert proof["context_temporal_status"] == "active_on_valid_date"
    assert proof["affected_by_correction_ids"] == []


def test_future_successor_ref_is_refused_before_valid_date(tmp_path: Path) -> None:
    fixture = _build_trace_fixture(tmp_path)
    _install_correction_context(fixture)
    _, successor = _move_correction_to_future(fixture)
    request = json.loads(fixture.request.read_text(encoding="utf-8"))
    request["proof_context"]["bindings"][0]["context_object"] = {
        "object_type": "claim",
        "object_id": successor["claim_id"],
        "record_sha256": successor["record_sha256"],
    }
    _write_json(fixture.request, request)
    _refuses_execute(fixture, "trace_proof_context_not_effective")


def test_event_context_validated_bytes_must_equal_captured_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    _install_correction_context(fixture)
    assert len(_execute(fixture)["proof_outputs"]) == 2
    contract = json.loads(fixture.contract.read_text(encoding="utf-8"))
    event_contract = contract["event_context"]
    bundle_path = (
        fixture.root / event_contract["root_path"] / event_contract["bundle_path"]
    )
    version_a = bundle_path.read_bytes()
    document = json.loads(version_a)
    version_b = json.dumps(
        document,
        ensure_ascii=False,
        indent=1,
    ).encode("utf-8")
    assert hashlib.sha256(version_a).digest() != hashlib.sha256(version_b).digest()
    original = trace.event_ledger_extension.validate_bundle

    def validate_version_b(*args: Any, **kwargs: Any) -> event_ext.ValidatedExtension:
        bundle_path.write_bytes(version_b)
        try:
            return original(*args, **kwargs)
        finally:
            bundle_path.write_bytes(version_a)

    monkeypatch.setattr(
        trace.event_ledger_extension, "validate_bundle", validate_version_b
    )
    _refuses_execute(fixture, "trace_event_context_validated_bytes_mismatch")


@pytest.mark.parametrize("case_id", ["correction_over_blast", "correction_under_blast"])
def test_correction_blast_radius_is_recomputed_not_caller_supplied(
    tmp_path: Path, case_id: str
) -> None:
    fixture = _build_trace_fixture(tmp_path)
    _install_correction_context(fixture)
    output = _execute(fixture)
    report = output["correction_reports"][0]
    if case_id == "correction_over_blast":
        report["affected_proof_ids"].append("prf:trace.unaffected.episode")
    else:
        report["affected_proof_ids"] = []
    _refuses_output(fixture, output, "trace_output_result_mismatch")


@pytest.mark.parametrize(
    "relative",
    [
        "tests/test_nary_association_trace.py",
        "src/nary_association_trace.py",
        (
            "standard/oges/extensions/nary-association-trace/0.1.0/"
            "trace-output.schema.json"
        ),
        (
            "standard/oges/extensions/nary-association-trace/0.1.0/"
            "adversarial-cases.json"
        ),
    ],
)
def test_normative_surface_drift_fails_closed(
    tmp_path: Path, relative: str
) -> None:
    fixture = _build_trace_fixture(tmp_path / "profile")
    target = fixture.root / relative
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    _refuses_execute(fixture, "profile_bound_file_digest_mismatch")


def test_capability_overpromotion_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "capability"
    shutil.copytree(ROOT / "governance", root / "governance")
    shutil.copytree(ROOT / "standard", root / "standard")
    shutil.copytree(ROOT / "design", root / "design")
    shutil.copytree(ROOT / "schemas", root / "schemas")
    (root / "src").mkdir()
    shutil.copy2(ROOT / "src/nary_association_trace.py", root / "src/nary_association_trace.py")
    registry_path = root / "governance/capability_attestation_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    rule = next(
        row
        for row in registry["capability_rules"]
        if row["capability_id"] == "dependency_flow_reconciliation"
    )
    rule["levels"]["synthetic_verified"] = [
        "dependency_profile",
        "foundry_profile",
        "trace_profile",
    ]
    _write_json(registry_path, registry)
    monkeypatch.setattr(
        capability_attestation,
        "EXPECTED_REGISTRY_SHA256",
        hashlib.sha256(registry_path.read_bytes()).hexdigest(),
    )
    with pytest.raises(capability_attestation.CapabilityAttestationError) as exc:
        capability_attestation.build_report(root)
    assert exc.value.code == "unsigned_synthetic_evidence_forbidden"


def test_adversarial_registry_and_normative_hash_surface_are_complete() -> None:
    extension = ROOT / TRACE_EXTENSION
    registry = json.loads((extension / "adversarial-cases.json").read_text())
    assert {row["case_id"] for row in registry["cases"]} == COVERED_CASES
    profile = json.loads((extension / "profile.json").read_text())
    paths = {row["kind"]: ROOT / row["path"] for row in profile["bound_files"]}
    assert set(paths) == trace._BOUND_KINDS
    for row in profile["bound_files"]:
        assert _sha(ROOT / row["path"]) == row["sha256"]
    assert _sha(ROOT / profile["reference_implementation"]["path"]) == profile[
        "reference_implementation"
    ]["sha256"]
    assert _sha(ROOT / profile["conformance_test"]["path"]) == profile[
        "conformance_test"
    ]["sha256"]
