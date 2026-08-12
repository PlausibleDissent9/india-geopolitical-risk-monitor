"""The public OGES draft must be executable, adversarial and byte-identical."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from src import canonical_objects as canonical
from src import oges_conformance as conformance
from src.oges_fixture import apply_operation, build_fixture

ROOT = Path(__file__).resolve().parents[1]


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_profile_is_exact_public_draft_not_an_adoption_claim() -> None:
    result = conformance.profile_summary()
    assert result == {
        "status": "registered_public_draft",
        "standard_id": "oges",
        "standard_version": "0.1.0",
        "profile_sha256": conformance.PROFILE_SHA256,
        "validator_sha256": "3d07e0e8e14537e61b3a5559fba1f56c114ec32151c09066abba64f184d2e934",
        "schema_registry_sha256": "582f0d859edb29fbc5a303e57a34c1bff789360078593dafb78a36f7edc9cc66",
        "required_object_types": [
            "evidence_item",
            "entity",
            "event",
            "universe_release",
            "exposure_edge",
        ],
        "adversarial_case_count": 11,
        "production_adoption_claim": False,
    }
    assert hashlib.sha256(conformance.PROFILE_PATH.read_bytes()).hexdigest() == (
        conformance.PROFILE_SHA256
    )


def test_synthetic_fixture_is_deterministic_and_contains_no_private_key_file(
    tmp_path: Path,
) -> None:
    first = build_fixture(tmp_path / "first")
    second = build_fixture(tmp_path / "second")
    assert _tree_hashes(first.root) == _tree_hashes(second.root)
    assert not any("private" in path.name.lower() for path in first.root.rglob("*"))
    assert not any(path.suffix in {".key", ".pem"} for path in first.root.rglob("*"))


def test_valid_bundle_report_is_bounded_and_value_free(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    result = conformance.validate_bundle(fixture.root)
    assert result["status"] == "conformant"
    assert result["release_id"] == "rel:oges.fixture.2026-08-08"
    assert result["object_count"] == 7
    assert result["object_counts"] == {
        "entity": 3,
        "event": 1,
        "evidence_item": 1,
        "exposure_edge": 1,
        "universe_release": 1,
    }
    serialized = json.dumps(result)
    for forbidden in ("12.5", "Synthetic official action", "private_key"):
        assert forbidden not in serialized


def test_all_registered_vectors_return_the_exact_reason() -> None:
    result = conformance.self_test()
    assert result["status"] == "pass"
    assert result["cases_passed"] == 11
    assert result["cases_total"] == 11
    assert [row["id"] for row in result["cases"]] == list(
        conformance.EXPECTED_CASES
    )
    assert all(row["passed"] is True for row in result["cases"])


@pytest.mark.parametrize(
    ("operation", "reason"),
    [
        ("tamper_release_signature", "release_signature_invalid"),
        ("spoof_official_confirmation", "event_official_confirmation_ineligible"),
        ("omit_universe_member", "universe_frame_membership_mismatch"),
        ("invent_exposure_method", "method_unregistered"),
        ("qualitative_edge_with_number", "object_schema_invalid"),
        ("future_measurement_period", "edge_magnitude_after_observation"),
        ("tamper_rights_registry", "release_rights_registry_digest_mismatch"),
        ("duplicate_json_key", "json_duplicate_key"),
        ("false_release_count", "release_counts_mismatch"),
        ("expose_restricted_evidence", "restricted_evidence_bytes_forbidden"),
    ],
)
def test_each_adversarial_bundle_fails_closed(
    tmp_path: Path, operation: str, reason: str
) -> None:
    fixture = build_fixture(tmp_path / operation)
    apply_operation(fixture, operation)
    with pytest.raises(canonical.CanonicalObjectError) as exc:
        conformance.validate_bundle(fixture.root)
    assert exc.value.code == reason


def test_bundle_cannot_supply_a_self_consistent_alternative_schema_profile(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    registry = fixture.root / "governance" / "canonical_schema_registry.json"
    registry.write_text(registry.read_text() + "\n")
    with pytest.raises(
        conformance.OgesConformanceError,
        match="bundle_schema_registry_profile_mismatch",
    ):
        conformance.validate_bundle(fixture.root)


def test_materialization_refuses_to_overwrite_a_nonempty_directory(
    tmp_path: Path,
) -> None:
    target = tmp_path / "vectors"
    target.mkdir()
    (target / "founder-file.txt").write_text("preserve me", encoding="utf-8")
    with pytest.raises(
        conformance.OgesConformanceError, match="materialize_path_not_empty"
    ):
        conformance.self_test(target)
    assert (target / "founder-file.txt").read_text(encoding="utf-8") == "preserve me"


def test_cli_refusal_is_machine_readable_and_does_not_echo_evidence(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "bundle")
    apply_operation(fixture, "tamper_release_signature")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.oges_conformance",
            "validate",
            "--bundle",
            str(fixture.root),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    payload = json.loads(completed.stderr)
    assert payload["status"] == "refused"
    assert payload["reason"] == "release_signature_invalid"
    assert "Synthetic official action" not in completed.stderr
    assert "12.5" not in completed.stderr


def test_public_standard_page_and_downloads_match_normative_bytes() -> None:
    page = (ROOT / "docs" / "standard.html").read_text(encoding="utf-8")
    assert "public draft 0.1.0" in page
    assert "not yet issued a\n  production canonical-object release" in page
    assert "eleven-case conformance suite" in page
    assert "government or industry-adopted standard" in page
    assert "python -m src.oges_conformance self-test" in page
    assert 'href="oges/0.1.0/profile.json"' in page
    assert 'href="schemas/event.schema.json"' in page
    for relative in ("profile.json", "adversarial-cases.json", "SPEC.md"):
        assert (ROOT / "standard" / "oges" / "0.1.0" / relative).read_bytes() == (
            ROOT / "docs" / "oges" / "0.1.0" / relative
        ).read_bytes()
    for schema in (ROOT / "schemas").glob("*.schema.json"):
        assert schema.read_bytes() == (ROOT / "docs" / "schemas" / schema.name).read_bytes()
    for referrer in ("analysis.html", "data.html"):
        assert 'href="standard.html"' in (ROOT / "docs" / referrer).read_text(
            encoding="utf-8"
        )


def test_every_public_oges_json_download_is_in_the_frozen_api_contract() -> None:
    contract = json.loads(
        (ROOT / "docs" / "data" / "api_contract.json").read_text(encoding="utf-8")
    )
    endpoints = {row["path"]: row for row in contract["endpoints"]}
    expected = {
        "oges/0.1.0/profile.json",
        "oges/0.1.0/adversarial-cases.json",
        *{
            f"schemas/{path.name}"
            for path in (ROOT / "docs" / "schemas").glob("*.schema.json")
        },
    }
    assert expected <= endpoints.keys()
    for path in expected:
        if path == "schemas/receipt-identity.schema.json":
            expected_stability = "static versioned release profile 1.0.0"
        elif path in {
                "schemas/sensor-fusion.schema.json",
                "schemas/exposure-dna.schema.json",
                "schemas/shock-scenario.schema.json",
                "schemas/shock-compilation.schema.json",
                "schemas/evidence-output-set.schema.json",
                "schemas/max-state-join.schema.json",
        }:
            expected_stability = "static synthetic foundation 1.0.0"
        else:
            expected_stability = "static versioned public draft 0.1.0"
        assert endpoints[path]["stability"] == expected_stability
