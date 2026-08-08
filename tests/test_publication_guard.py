"""Adversarial tests for the IGRM Max public-claim trust boundary."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import publication_guard as guard

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resign(bundle: dict[str, Any]) -> None:
    bundle["bundle_sha256"] = guard._bundle_digest(bundle)


def _fixture(
    tmp_path: Path, *, lineage_policy: str = "primary"
) -> tuple[dict[str, Any], dict[str, Path]]:
    root = tmp_path / "root"
    evidence = root / "data" / "evidence.json"
    _write_json(
        evidence,
        {
            "date": "2026-08-08",
            "generated": "2026-08-08T10:00:00Z",
            "score": 61.5,
            "unit": "salience_percentile_points",
            "denominator": "registered_test_frame",
        },
    )

    transform = root / "src" / "publication_transforms.py"
    transform.parent.mkdir(parents=True)
    transform.write_bytes((ROOT / "src" / "publication_transforms.py").read_bytes())

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers = tmp_path / "rights_signers.json"
    _write_json(
        signers,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "test_signer",
                    "name": "Test signer",
                    "role": "test rights reviewer",
                    "public_key_ed25519_base64": base64.b64encode(public_key).decode(),
                    "effective": "2026-08-08",
                    "revoked_on": None,
                }
            ],
        },
    )

    rights = tmp_path / "source_rights.json"
    source = {
        "source_id": "test_source",
        "name": "Test source",
        "provider": "Test provider",
        "role": "first_party_test",
        "authority_class": "official_primary",
        "independence_group": "test_provider",
        "lineage_policy": lineage_policy,
        "decision_state": "approved",
        "decision_id": "test-decision-2026-08-08",
        "decision_owner": "Test owner",
        "signer_id": "test_signer",
        "decision_artifact_path": "governance/rights_decisions/test_source.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/test_source.sig",
        "reviewed_on": "2026-08-08",
        "review_due": "2027-08-08",
        "access_url": "https://example.test/data",
        "terms_url": "https://example.test/terms",
        "access_basis": "first_party_test",
        "geographic_coverage": "Test frame",
        "historical_coverage": "One test day",
        "retrieval_target": "One deterministic fixture",
        "outage_fallback": "Fail closed",
        "cost_owner": "Test owner",
        "reproducibility_tier": "open_fixture",
        "max_current_age_days": 3,
        "permitted_uses": [
            "cite_metadata",
            "publish_derived_value",
        ],
        "notes": "Synthetic test-only decision.",
    }
    decision = {
        "schema_version": "1.0.0",
        "source_id": source["source_id"],
        "name": source["name"],
        "provider": source["provider"],
        "role": source["role"],
        "authority_class": source["authority_class"],
        "independence_group": source["independence_group"],
        "decision_id": source["decision_id"],
        "decision_owner": source["decision_owner"],
        "signer_id": source["signer_id"],
        "reviewed_on": source["reviewed_on"],
        "review_due": source["review_due"],
        "access_url": source["access_url"],
        "terms_url": source["terms_url"],
        "access_basis": source["access_basis"],
        "lineage_policy": source["lineage_policy"],
        "max_current_age_days": source["max_current_age_days"],
        "permitted_uses": source["permitted_uses"],
        "statement": "Synthetic test authorization for the exact listed uses.",
    }
    decision_path = root / source["decision_artifact_path"]
    _write_json(decision_path, decision)
    signature_path = root / source["decision_signature_path"]
    signature_path.write_bytes(private_key.sign(decision_path.read_bytes()))
    source["decision_artifact_sha256"] = _sha(decision_path)
    _write_json(
        rights,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    contract = tmp_path / "claim_contract.json"
    _write_json(
        contract,
        {
            "schema_version": "2.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "allowed_claim_classes": [
                "descriptive_current",
                "descriptive_historical",
                "methodology",
            ],
            "forbidden_claim_classes": [
                "forecast",
                "causal",
                "superiority",
            ],
            "allowed_temporal_policies": ["same_effective_date"],
            "templates": [
                {
                    "template_id": "direct_fact_v1",
                    "claim_classes": [
                        "descriptive_current",
                        "descriptive_historical",
                        "methodology",
                    ],
                    "allowed_value_types": [
                        "boolean",
                        "integer",
                        "number",
                        "null",
                    ],
                    "allowed_units": ["salience_percentile_points"],
                    "allowed_denominators": ["registered_test_frame"],
                    "allowed_uncertainty_meaning_codes": [
                        "synthetic_test_uncertainty"
                    ],
                    "min_facts": 1,
                    "max_facts": 1,
                    "required_transformations": ["direct_registered_fact"],
                }
            ],
        },
    )
    transforms = tmp_path / "transforms.json"
    _write_json(
        transforms,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-08",
            "default_policy": "deny",
            "transformations": [
                {
                    "transformation_id": "direct_registered_fact",
                    "version": "1.0.0",
                    "implementation_path": "src/publication_transforms.py",
                    "implementation_sha256": _sha(transform),
                    "claim_classes": [
                        "descriptive_current",
                        "descriptive_historical",
                        "methodology",
                    ],
                    "effective": "2026-08-08",
                    "superseded_on": None,
                }
            ],
        },
    )
    paths = {
        "root": root,
        "evidence": evidence,
        "transform": transform,
        "rights": rights,
        "signers": signers,
        "contract": contract,
        "transforms": transforms,
    }
    bundle: dict[str, Any] = {
        "schema_version": "2.0.0",
        "claim_id": "test.claim.001",
        "claim_class": "descriptive_current",
        "template_id": "direct_fact_v1",
        "as_of": "2026-08-08",
        "generated_at": "2026-08-08T12:00:00Z",
        "temporal_policy": "same_effective_date",
        "policy": {
            "rights_registry_sha256": _sha(rights),
            "rights_signers_sha256": _sha(signers),
            "claim_contract_sha256": _sha(contract),
            "transformation_registry_sha256": _sha(transforms),
        },
        "facts": [
            {
                "fact_id": "test.fact.score",
                "source_id": "test_source",
                "upstream_source_ids": [],
                "lineage_manifest_path": None,
                "lineage_manifest_sha256": None,
                "source_path": "data/evidence.json",
                "source_sha256": _sha(evidence),
                "json_pointer": "/score",
                "value": 61.5,
                "value_type": "number",
                "effective_date": "2026-08-08",
                "effective_date_pointer": "/date",
                "observed_at": "2026-08-08T10:00:00Z",
                "observed_at_pointer": "/generated",
                "unit": "salience_percentile_points",
                "unit_pointer": "/unit",
                "denominator": "registered_test_frame",
                "denominator_pointer": "/denominator",
                "rights_use": "publish_derived_value",
                "uncertainty": {
                    "status": "not_estimated",
                    "meaning_code": "synthetic_test_uncertainty",
                    "lower": None,
                    "upper": None,
                },
            }
        ],
        "transformations": [
            {
                "transformation_id": "direct_registered_fact",
                "version": "1.0.0",
                "implementation_sha256": _sha(transform),
            }
        ],
        "bundle_sha256": "0" * 64,
    }
    _resign(bundle)
    return bundle, paths


def _validate(bundle: dict[str, Any], paths: dict[str, Path]) -> dict[str, object]:
    return guard.validate_claim_bundle(
        bundle,
        root=paths["root"],
        rights_path=paths["rights"],
        signer_registry_path=paths["signers"],
        claim_contract_path=paths["contract"],
        transform_registry_path=paths["transforms"],
    )


def _refuses(
    bundle: dict[str, Any], paths: dict[str, Path], reason: str
) -> None:
    with pytest.raises(guard.PublicationGuardError) as exc:
        _validate(bundle, paths)
    assert exc.value.code == reason


def test_complete_bundle_is_eligible_without_emitting_its_value(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    result = _validate(bundle, paths)

    assert result == {
        "status": "eligible",
        "claim_id": "test.claim.001",
        "bundle_sha256": bundle["bundle_sha256"],
        "fact_ids": ["test.fact.score"],
        "source_ids": ["test_source"],
    }
    assert "61.5" not in json.dumps(result)


def test_unwired_v1_contract_and_bundle_are_explicitly_refused(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["schema_version"] = "1.0.0"
    _resign(bundle)
    _refuses(bundle, paths, "bundle_schema_unsupported")

    bundle, paths = _fixture(tmp_path / "contract")
    contract = json.loads(paths["contract"].read_text())
    contract["schema_version"] = "1.0.0"
    _write_json(paths["contract"], contract)
    bundle["policy"]["claim_contract_sha256"] = _sha(paths["contract"])
    _resign(bundle)
    _refuses(bundle, paths, "claim_contract_schema_unsupported")


@pytest.mark.parametrize("field", ["prose", "citation", "model_output", "confidence"])
def test_bundle_has_no_field_for_model_written_claims(tmp_path: Path, field: str) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle[field] = "invented public statement"
    _refuses(bundle, paths, "bundle_fields_invalid")


def test_unknown_pending_expired_and_unauthorized_sources_fail_closed(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["source_id"] = "unknown_source"
    _resign(bundle)
    _refuses(bundle, paths, "fact_source_unregistered")

    bundle, paths = _fixture(tmp_path / "pending")
    rights = json.loads(paths["rights"].read_text())
    source = rights["sources"][0]
    source.update(
        decision_state="review_required",
        signer_id=None,
        decision_artifact_path=None,
        decision_artifact_sha256=None,
        decision_signature_path=None,
        reviewed_on=None,
        review_due=None,
        max_current_age_days=None,
        permitted_uses=[],
    )
    _write_json(paths["rights"], rights)
    bundle["policy"]["rights_registry_sha256"] = _sha(paths["rights"])
    _resign(bundle)
    _refuses(bundle, paths, "fact_source_not_approved")

    bundle, paths = _fixture(tmp_path / "expired")
    bundle["generated_at"] = "2027-08-09T12:00:00Z"
    _resign(bundle)
    _refuses(bundle, paths, "fact_source_rights_expired")

    bundle, paths = _fixture(tmp_path / "forbidden")
    bundle["facts"][0]["rights_use"] = "publish_extract"
    _resign(bundle)
    _refuses(bundle, paths, "fact_rights_use_forbidden")


def test_approved_rights_require_an_authentic_detached_signature(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    rights = json.loads(paths["rights"].read_text())
    rights["sources"][0]["signer_id"] = None
    rights["sources"][0]["decision_artifact_path"] = None
    rights["sources"][0]["decision_artifact_sha256"] = None
    rights["sources"][0]["decision_signature_path"] = None
    _write_json(paths["rights"], rights)
    bundle["policy"]["rights_registry_sha256"] = _sha(paths["rights"])
    _resign(bundle)
    _refuses(bundle, paths, "rights_source_signed_decision_required")

    bundle, paths = _fixture(tmp_path / "tampered")
    signature = paths["root"] / "governance" / "rights_decisions" / "test_source.sig"
    signature.write_bytes(b"0" * 64)
    _refuses(bundle, paths, "rights_source_decision_signature_invalid")

    bundle, paths = _fixture(tmp_path / "escalated")
    rights = json.loads(paths["rights"].read_text())
    rights["sources"][0]["permitted_uses"].append("publish_extract")
    _write_json(paths["rights"], rights)
    bundle["policy"]["rights_registry_sha256"] = _sha(paths["rights"])
    _resign(bundle)
    _refuses(bundle, paths, "rights_source_decision_artifact_mismatch")


def test_derived_source_cannot_launder_missing_or_unapproved_upstream_rights(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path, lineage_policy="bundle_declared")
    _refuses(bundle, paths, "fact_upstream_sources_required")

    rights = json.loads(paths["rights"].read_text())
    upstream = json.loads(json.dumps(rights["sources"][0]))
    upstream.update(
        source_id="pending_upstream",
        name="Pending upstream",
        lineage_policy="primary",
        decision_state="review_required",
        decision_id="pending:pending_upstream",
        decision_owner="unassigned",
        signer_id=None,
        decision_artifact_path=None,
        decision_artifact_sha256=None,
        decision_signature_path=None,
        reviewed_on=None,
        review_due=None,
        max_current_age_days=None,
        permitted_uses=[],
    )
    rights["sources"].append(upstream)
    _write_json(paths["rights"], rights)
    bundle["policy"]["rights_registry_sha256"] = _sha(paths["rights"])
    bundle["facts"][0]["upstream_source_ids"] = ["pending_upstream"]
    lineage = paths["root"] / "data" / "lineage.json"
    _write_json(
        lineage,
        {
            "schema_version": "1.0.0",
            "artifact_path": bundle["facts"][0]["source_path"],
            "artifact_sha256": bundle["facts"][0]["source_sha256"],
            "upstream_source_ids": ["pending_upstream"],
        },
    )
    bundle["facts"][0]["lineage_manifest_path"] = "data/lineage.json"
    bundle["facts"][0]["lineage_manifest_sha256"] = _sha(lineage)
    _resign(bundle)
    _refuses(bundle, paths, "fact_upstream_source_not_approved")


def test_evidence_bytes_pointer_type_and_value_are_reverified(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    paths["evidence"].write_text('{"date":"2026-08-08","score":99.9}\n')
    _refuses(bundle, paths, "fact_source_digest_mismatch")

    bundle, paths = _fixture(tmp_path / "pointer")
    bundle["facts"][0]["json_pointer"] = "/missing"
    _resign(bundle)
    _refuses(bundle, paths, "fact_pointer_missing")

    bundle, paths = _fixture(tmp_path / "type")
    bundle["facts"][0]["value_type"] = "integer"
    _resign(bundle)
    _refuses(bundle, paths, "fact_value_type_mismatch")

    bundle, paths = _fixture(tmp_path / "value")
    bundle["facts"][0]["value"] = 61.6
    _resign(bundle)
    _refuses(bundle, paths, "fact_value_source_mismatch")


def test_direct_fact_rejects_prose_even_when_exactly_bound_to_evidence(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    advisory = (
        "India's geopolitical risk is elevated and investors should reduce "
        "shipping exposure ahead of an expected escalation."
    )
    _write_json(
        paths["evidence"],
        {
            "date": "2026-08-08",
            "generated": "2026-08-08T10:00:00Z",
            "score": advisory,
            "unit": "salience_percentile_points",
            "denominator": "registered_test_frame",
        },
    )
    fact = bundle["facts"][0]
    fact["source_sha256"] = _sha(paths["evidence"])
    fact["value"] = advisory
    fact["value_type"] = "string"
    _resign(bundle)

    _refuses(bundle, paths, "fact_value_type_unlicensed")


def test_direct_fact_contract_cannot_register_an_unbounded_string_channel(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    contract = json.loads(paths["contract"].read_text())
    contract["templates"][0]["allowed_value_types"].append("string")
    _write_json(paths["contract"], contract)
    bundle["policy"]["claim_contract_sha256"] = _sha(paths["contract"])
    _resign(bundle)

    _refuses(bundle, paths, "claim_template_value_types_invalid")


def test_template_semantic_allowlists_accept_only_machine_codes(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    contract = json.loads(paths["contract"].read_text())
    contract["templates"][0]["allowed_units"].append(
        "India risk is elevated and investors should sell shipping exposure."
    )
    _write_json(paths["contract"], contract)
    bundle["policy"]["claim_contract_sha256"] = _sha(paths["contract"])
    _resign(bundle)

    _refuses(bundle, paths, "claim_template_semantic_codes_invalid")


def test_false_unit_and_denominator_labels_refuse_even_with_a_valid_value(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["unit"] = "percentage_of_articles"
    _resign(bundle)
    _refuses(bundle, paths, "fact_unit_source_mismatch")

    bundle, paths = _fixture(tmp_path / "denominator")
    bundle["facts"][0]["denominator"] = "daily_brief_score_pool"
    _resign(bundle)
    _refuses(bundle, paths, "fact_denominator_source_mismatch")


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("unit", "fact_unit_invalid"),
        ("denominator", "fact_denominator_invalid"),
    ],
)
def test_semantic_labels_cannot_carry_matching_whitespace_prose(
    tmp_path: Path, field: str, reason: str
) -> None:
    bundle, paths = _fixture(tmp_path)
    advisory = "India risk is elevated and investors should reduce shipping exposure."
    evidence = json.loads(paths["evidence"].read_text())
    evidence[field] = advisory
    _write_json(paths["evidence"], evidence)
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0][field] = advisory
    _resign(bundle)

    _refuses(bundle, paths, reason)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("unit", "fact_unit_unlicensed"),
        ("denominator", "fact_denominator_unlicensed"),
    ],
)
def test_identifier_shaped_semantic_labels_still_require_registration(
    tmp_path: Path, field: str, reason: str
) -> None:
    bundle, paths = _fixture(tmp_path)
    advisory_code = "india_risk_is_elevated_sell_shipping"
    evidence = json.loads(paths["evidence"].read_text())
    evidence[field] = advisory_code
    _write_json(paths["evidence"], evidence)
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0][field] = advisory_code
    _resign(bundle)

    _refuses(bundle, paths, reason)


@pytest.mark.parametrize(
    ("field", "pointer_field", "reason"),
    [
        ("unit", "unit_pointer", "fact_unit_pointer_missing"),
        ("denominator", "denominator_pointer", "fact_denominator_pointer_missing"),
    ],
)
def test_semantic_labels_must_exist_inside_the_hashed_evidence(
    tmp_path: Path, field: str, pointer_field: str, reason: str
) -> None:
    bundle, paths = _fixture(tmp_path)
    evidence = json.loads(paths["evidence"].read_text())
    del evidence[field]
    _write_json(paths["evidence"], evidence)
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0][pointer_field] = f"/{field}"
    _resign(bundle)

    _refuses(bundle, paths, reason)


@pytest.mark.parametrize(
    ("pointer_field", "source_field", "reason"),
    [
        ("json_pointer", "score", "fact_pointer_invalid"),
        ("unit_pointer", "unit", "fact_unit_pointer_invalid"),
        (
            "denominator_pointer",
            "denominator",
            "fact_denominator_pointer_invalid",
        ),
        (
            "effective_date_pointer",
            "date",
            "fact_effective_date_pointer_invalid",
        ),
        ("observed_at_pointer", "generated", "fact_observed_at_pointer_invalid"),
    ],
)
def test_structural_pointers_cannot_carry_whitespace_prose(
    tmp_path: Path, pointer_field: str, source_field: str, reason: str
) -> None:
    bundle, paths = _fixture(tmp_path)
    prose_key = "India risk is elevated and this pointer carries prose"
    evidence = json.loads(paths["evidence"].read_text())
    evidence[prose_key] = evidence[source_field]
    _write_json(paths["evidence"], evidence)
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0][pointer_field] = f"/{prose_key}"
    _resign(bundle)

    _refuses(bundle, paths, reason)


def test_source_path_cannot_carry_whitespace_prose(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    prose_path = paths["root"] / "data" / "India risk is elevated.json"
    prose_path.write_bytes(paths["evidence"].read_bytes())
    bundle["facts"][0]["source_path"] = "data/India risk is elevated.json"
    bundle["facts"][0]["source_sha256"] = _sha(prose_path)
    _resign(bundle)

    _refuses(bundle, paths, "fact_source_path_invalid")


def test_json_pointer_decoding_and_strict_json_are_enforced(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    _write_json(
        paths["evidence"],
        {
            "a~1": 61.5,
            "date": "2026-08-08",
            "generated": "2026-08-08T10:00:00Z",
            "unit": "salience_percentile_points",
            "denominator": "registered_test_frame",
        },
    )
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0]["json_pointer"] = "/a~01"
    _resign(bundle)
    assert _validate(bundle, paths)["status"] == "eligible"

    bundle, paths = _fixture(tmp_path / "duplicate")
    paths["evidence"].write_text('{"score":61.5,"score":61.5}\n')
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    _resign(bundle)
    _refuses(bundle, paths, "json_duplicate_key")

    bundle, paths = _fixture(tmp_path / "non_finite")
    paths["evidence"].write_text(
        '{"date":"2026-08-08","generated":"2026-08-08T10:00:00Z",'
        '"score":NaN}\n'
    )
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    _resign(bundle)
    _refuses(bundle, paths, "json_non_finite")


def test_evidence_path_cannot_escape_or_traverse_a_symlink(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["source_path"] = "../outside.json"
    _resign(bundle)
    _refuses(bundle, paths, "fact_source_path_invalid")

    bundle, paths = _fixture(tmp_path / "symlink")
    real = paths["root"] / "real"
    real.mkdir()
    (real / "evidence.json").write_bytes(paths["evidence"].read_bytes())
    link = paths["root"] / "linked"
    link.symlink_to(real, target_is_directory=True)
    bundle["facts"][0]["source_path"] = "linked/evidence.json"
    bundle["facts"][0]["source_sha256"] = _sha(real / "evidence.json")
    _resign(bundle)
    _refuses(bundle, paths, "fact_source_symlink_forbidden")


def test_temporal_join_freshness_and_future_observation_are_enforced(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    _write_json(
        paths["evidence"],
        {
            "date": "2026-08-07",
            "generated": "2026-08-08T10:00:00Z",
            "score": 61.5,
            "unit": "salience_percentile_points",
            "denominator": "registered_test_frame",
        },
    )
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0]["effective_date"] = "2026-08-07"
    _resign(bundle)
    _refuses(bundle, paths, "fact_temporal_join_invalid")

    bundle, paths = _fixture(tmp_path / "stale")
    bundle["generated_at"] = "2026-08-12T12:00:00Z"
    _resign(bundle)
    _refuses(bundle, paths, "fact_current_evidence_stale")

    bundle, paths = _fixture(tmp_path / "future")
    _write_json(
        paths["evidence"],
        {
            "date": "2026-08-08",
            "generated": "2026-08-08T13:00:00Z",
            "score": 61.5,
            "unit": "salience_percentile_points",
            "denominator": "registered_test_frame",
        },
    )
    bundle["facts"][0]["source_sha256"] = _sha(paths["evidence"])
    bundle["facts"][0]["observed_at"] = "2026-08-08T13:00:00Z"
    _resign(bundle)
    _refuses(bundle, paths, "fact_observed_after_generation")


def test_declared_dates_must_equal_dates_inside_evidence_bytes(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["effective_date"] = "2026-08-07"
    _resign(bundle)
    _refuses(bundle, paths, "fact_effective_date_source_mismatch")

    bundle, paths = _fixture(tmp_path / "observed")
    bundle["facts"][0]["observed_at"] = "2026-08-08T09:00:00Z"
    _resign(bundle)
    _refuses(bundle, paths, "fact_observed_at_source_mismatch")


def test_numeric_uncertainty_is_typed_and_bounded(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["uncertainty"] = {
        "status": "not_applicable",
        "meaning_code": "synthetic_test_uncertainty",
        "lower": None,
        "upper": None,
    }
    _resign(bundle)
    _refuses(bundle, paths, "fact_numeric_uncertainty_required")

    bundle, paths = _fixture(tmp_path / "interval")
    bundle["facts"][0]["uncertainty"] = {
        "status": "interval",
        "meaning_code": "synthetic_test_uncertainty",
        "lower": 70.0,
        "upper": 80.0,
    }
    _resign(bundle)
    _refuses(bundle, paths, "fact_uncertainty_interval_invalid")


def test_uncertainty_meaning_code_cannot_carry_advisory_prose(tmp_path: Path) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["uncertainty"]["meaning_code"] = (
        "India's geopolitical risk is elevated and investors should reduce exposure."
    )
    _resign(bundle)

    _refuses(bundle, paths, "fact_uncertainty_meaning_code_invalid")


def test_identifier_shaped_uncertainty_code_still_requires_registration(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["facts"][0]["uncertainty"]["meaning_code"] = (
        "india_risk_is_elevated_sell_shipping"
    )
    _resign(bundle)

    _refuses(bundle, paths, "fact_uncertainty_meaning_code_unlicensed")


def test_transform_registration_and_implementation_bytes_are_locked(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["transformations"][0]["transformation_id"] = "unknown_transform"
    _resign(bundle)
    _refuses(bundle, paths, "bundle_transformation_unregistered")

    bundle, paths = _fixture(tmp_path / "bundle_digest")
    bundle["transformations"][0]["implementation_sha256"] = "1" * 64
    _resign(bundle)
    _refuses(bundle, paths, "bundle_transformation_digest_mismatch")

    bundle, paths = _fixture(tmp_path / "code_drift")
    paths["transform"].write_text("def changed():\n    return 1\n")
    _refuses(bundle, paths, "transformation_implementation_drift")


def test_policy_and_bundle_hashes_cannot_be_self_attested_after_tampering(
    tmp_path: Path,
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["policy"]["rights_registry_sha256"] = "2" * 64
    _resign(bundle)
    _refuses(bundle, paths, "bundle_policy_digest_mismatch")

    bundle, paths = _fixture(tmp_path / "bundle")
    bundle["bundle_sha256"] = "3" * 64
    _refuses(bundle, paths, "bundle_digest_mismatch")


@pytest.mark.parametrize(
    "claim_class", ["forecast", "causal", "investment_advice", "superiority"]
)
def test_forbidden_claim_classes_have_no_template(
    tmp_path: Path, claim_class: str
) -> None:
    bundle, paths = _fixture(tmp_path)
    bundle["claim_class"] = claim_class
    _resign(bundle)
    _refuses(bundle, paths, "claim_class_unlicensed")


def test_committed_registry_is_deny_by_default_and_external_sources_are_pending() -> None:
    """Trip CI deliberately when the founder makes the first signed approval.

    That approval commit must update these initial-state assertions alongside
    its signed artifact; an unexpected green transition would hide a policy
    change at the trust boundary.
    """
    registry_path = ROOT / "governance" / "source_rights_registry.json"
    signers_path = ROOT / "governance" / "rights_signers.json"
    registry = json.loads(
        registry_path.read_text()
    )
    _, strict_signers, _ = guard._read_json(signers_path, "unreadable")
    signers = guard._validate_signers(strict_signers)
    _, strict_registry, _ = guard._read_json(registry_path, "unreadable")
    validated = guard._validate_rights_registry(strict_registry, ROOT, signers)
    assert registry["default_policy"] == "deny"
    assert signers == {}
    assert len(registry["sources"]) >= 10
    assert set(validated) == {source["source_id"] for source in registry["sources"]}

    approved = [
        source for source in registry["sources"] if source["decision_state"] == "approved"
    ]
    assert approved == []
    for source in registry["sources"]:
        assert source["decision_state"] == "review_required"
        expected_lineage = (
            "bundle_declared"
            if source["source_id"] == "igrm_public_payloads"
            else "primary"
        )
        assert source["lineage_policy"] == expected_lineage
        assert source["authority_class"] in guard._AUTHORITY_CLASSES
        assert isinstance(source["independence_group"], str)
        assert source["permitted_uses"] == []
        assert source["reviewed_on"] is None
        assert source["review_due"] is None
        assert source["signer_id"] is None


def test_committed_contract_forbids_high_risk_claims_and_transform_hash_is_exact() -> None:
    contract_path = ROOT / "governance" / "claim_eligibility_contract.json"
    contract = json.loads(contract_path.read_text())
    _, strict_contract, _ = guard._read_json(contract_path, "unreadable")
    guard._validate_claim_contract(strict_contract)
    assert contract["default_policy"] == "deny"
    assert contract["schema_version"] == "2.0.0"
    assert {
        "causal",
        "forecast",
        "investment_advice",
        "policy_directive",
        "security_assurance",
        "superiority",
    } <= set(contract["forbidden_claim_classes"])
    assert set(contract["allowed_claim_classes"]).isdisjoint(
        contract["forbidden_claim_classes"]
    )
    assert len(contract["templates"]) == 1
    assert contract["templates"][0]["template_id"] == "direct_fact_v1"
    assert contract["templates"][0]["allowed_value_types"] == [
        "boolean",
        "integer",
        "number",
        "null",
    ]
    assert contract["templates"][0]["allowed_units"] == []
    assert contract["templates"][0]["allowed_denominators"] == []
    assert contract["templates"][0]["allowed_uncertainty_meaning_codes"] == []

    registry_path = ROOT / "governance" / "transformation_registry.json"
    transforms = json.loads(registry_path.read_text())
    _, strict_transforms, _ = guard._read_json(registry_path, "unreadable")
    guard._validate_transform_registry(strict_transforms, ROOT)
    registered = transforms["transformations"][0]
    implementation = ROOT / registered["implementation_path"]
    assert _sha(implementation) == registered["implementation_sha256"]
