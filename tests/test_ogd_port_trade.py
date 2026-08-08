from __future__ import annotations

import base64
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import ogd_port_trade as ogd

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _row(commodity: str, country: str, values: list[str], total: str) -> str:
    assert len(values) == 13
    return ",".join([commodity, country, *values, total])


def _csv(flow: str) -> bytes:
    header = ",".join(ogd._EXPECTED_HEADER)
    if flow == "unloaded":
        rows = [
            _row("POL-CRUDE", "Iraq", ["4", "0", "NA", *(["0"] * 10)], "4"),
            _row("POL-CRUDE", "Other Countries", ["0", "2", *(["0"] * 11)], "2"),
            _row("POL-CRUDE", "Total", ["4", "2", "NA", *(["0"] * 10)], "6"),
        ]
    else:
        rows = [
            _row("IRON ORE", "China", ["0", "5", *(["0"] * 11)], "5"),
            _row("IRON ORE", "Total", ["0", "5", *(["0"] * 11)], "5"),
        ]
    return ("\n".join([header, *rows]) + "\n").encode()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    implementation = tmp_path / "src" / "ogd_port_trade.py"
    implementation.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "src" / "ogd_port_trade.py", implementation)
    unloaded = tmp_path / "unloaded.csv"
    loaded = tmp_path / "loaded.csv"
    unloaded.write_bytes(_csv("unloaded"))
    loaded.write_bytes(_csv("loaded"))

    registry = json.loads((ROOT / "governance" / "ogd_port_trade_baseline.json").read_text())
    registry["implementation"]["sha256"] = hashlib.sha256(implementation.read_bytes()).hexdigest()
    for artifact, path, counts in zip(
        registry["artifacts"],
        (unloaded, loaded),
        ((3, 1, 2), (2, 1, 1)),
    ):
        artifact["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact["file_size_bytes"] = len(path.read_bytes())
        artifact["expected_rows"] = counts[0]
        artifact["expected_summary_rows"] = counts[1]
        artifact["expected_detail_rows"] = counts[2]
    registry_path = tmp_path / "governance" / "ogd_port_trade_baseline.json"
    _write_json(registry_path, registry)
    return registry_path, unloaded, loaded


def _approved_rights(tmp_path: Path) -> tuple[Path, Path]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers = tmp_path / "governance" / "rights_signers.json"
    _write_json(
        signers,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "signers": [
                {
                    "signer_id": "fixture_rights_reviewer",
                    "name": "Fixture reviewer",
                    "role": "test-only rights reviewer",
                    "public_key_ed25519_base64": base64.b64encode(public).decode(),
                    "effective": "2026-08-09",
                    "revoked_on": None,
                }
            ],
        },
    )
    source = {
        "source_id": "india_ogd_port_trade_2019_20",
        "name": "Fixture OGD source",
        "provider": "Fixture ministry",
        "role": "official_historical_port_country_commodity_observations",
        "authority_class": "official_primary",
        "independence_group": "fixture_ministry",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "fixture-ogd-rights-2026-08-09",
        "decision_owner": "Fixture owner",
        "signer_id": "fixture_rights_reviewer",
        "decision_artifact_path": "governance/rights_decisions/fixture_ogd.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/fixture_ogd.sig",
        "reviewed_on": "2026-08-09",
        "review_due": "2027-08-09",
        "access_url": "https://www.data.gov.in/catalog/test",
        "terms_url": "https://www.data.gov.in/sites/default/files/test-license.pdf",
        "access_basis": "fixture_open_data_license",
        "geographic_coverage": "Fixture frame",
        "historical_coverage": "One fixture year",
        "retrieval_target": "Fixture observations",
        "outage_fallback": "Fail closed",
        "cost_owner": "Fixture owner",
        "reproducibility_tier": "open_fixture",
        "max_current_age_days": 3650,
        "permitted_uses": [
            "cite_metadata",
            "publish_derived_value",
            "publish_extract",
        ],
        "notes": "Synthetic test-only authorization.",
    }
    decision = {
        field: source[field]
        for field in (
            "source_id",
            "name",
            "provider",
            "role",
            "authority_class",
            "independence_group",
            "decision_id",
            "decision_owner",
            "signer_id",
            "reviewed_on",
            "review_due",
            "access_url",
            "terms_url",
            "access_basis",
            "lineage_policy",
            "max_current_age_days",
            "permitted_uses",
        )
    }
    decision.update(
        schema_version="1.0.0",
        statement="Synthetic fixture authorization for the exact three listed uses.",
    )
    decision_path = tmp_path / source["decision_artifact_path"]
    _write_json(decision_path, decision)
    source["decision_artifact_sha256"] = hashlib.sha256(decision_path.read_bytes()).hexdigest()
    signature_path = tmp_path / source["decision_signature_path"]
    signature_path.write_bytes(private.sign(decision_path.read_bytes()))
    rights = tmp_path / "governance" / "source_rights_registry.json"
    _write_json(
        rights,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    return rights, signers


def test_committed_registry_binds_official_vintages_unit_and_implementation() -> None:
    registry, _ = ogd._registry()
    assert registry["unit_evidence"] == {
        "unit": "thousand_metric_tonnes",
        "source_url": "https://www.shipmin.gov.in/sites/default/files/BPS2020.pdf",
        "source_sha256": "ad1af140a52c4280bcc33ebac439339485fe2ed2dfe25a1fada0ab74f2d053a8",
        "table_ids": ["2.1.6", "2.1.7"],
        "pdf_pages": [105, 118],
    }
    assert {row["sha256"] for row in registry["artifacts"]} == {
        "4f8df1d300a3f0a580812b2ff014a56554190073c5c798476ed45e1d691e628e",
        "e8506e26095d2e72f1ae0825893115eda74919bc7f273bc07e7f593cb0d74270",
    }


def test_profile_preserves_na_separately_from_observed_zero(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    report = ogd.validate_only(unloaded, loaded, registry_path=registry_path)
    inbound = report["flows"][0]
    assert inbound["coverage"] == {
        "detail_rows": 2,
        "summary_rows": 1,
        "port_columns": 13,
        "expected_joint_cells": 26,
        "observed_nonzero_cells": 2,
        "observed_zero_cells": 23,
        "source_missing_cells": 1,
        "observed_cell_rate": 0.96153846,
    }
    assert report["publication_allowed"] is False
    assert report["dependency_edges_emitted"] == 0


def test_source_byte_change_and_implementation_drift_refuse(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    unloaded.write_bytes(unloaded.read_bytes() + b" ")
    with pytest.raises(ogd.OGDPortTradeError, match="csv_size_mismatch"):
        ogd.validate_only(unloaded, loaded, registry_path=registry_path)

    registry_path, unloaded, loaded = _fixture(tmp_path / "implementation")
    (registry_path.parents[1] / "src" / "ogd_port_trade.py").write_text("# drift\n")
    with pytest.raises(ogd.OGDPortTradeError, match="implementation_digest_mismatch"):
        ogd.validate_only(unloaded, loaded, registry_path=registry_path)


def test_rounding_over_tolerance_and_missing_summary_refuse(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    raw = unloaded.read_text()
    unloaded.write_text(raw.replace("POL-CRUDE,Iraq,4", "POL-CRUDE,Iraq,9", 1))
    registry = json.loads(registry_path.read_text())
    registry["artifacts"][0]["sha256"] = hashlib.sha256(unloaded.read_bytes()).hexdigest()
    registry["artifacts"][0]["file_size_bytes"] = len(unloaded.read_bytes())
    _write_json(registry_path, registry)
    with pytest.raises(ogd.OGDPortTradeError, match="csv_row_reconciliation_invalid"):
        ogd.validate_only(unloaded, loaded, registry_path=registry_path)

    registry_path, unloaded, loaded = _fixture(tmp_path / "summary")
    rows = unloaded.read_text().splitlines()
    unloaded.write_text("\n".join(rows[:-1]) + "\n")
    registry = json.loads(registry_path.read_text())
    registry["artifacts"][0]["sha256"] = hashlib.sha256(unloaded.read_bytes()).hexdigest()
    registry["artifacts"][0]["file_size_bytes"] = len(unloaded.read_bytes())
    registry["artifacts"][0]["expected_rows"] = 2
    registry["artifacts"][0]["expected_summary_rows"] = 1
    registry["artifacts"][0]["expected_detail_rows"] = 1
    _write_json(registry_path, registry)
    with pytest.raises(ogd.OGDPortTradeError, match="csv_summary_or_detail_coverage_invalid"):
        ogd.validate_only(unloaded, loaded, registry_path=registry_path)


def test_csv_formula_identity_is_refused_before_output(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    unloaded.write_text(unloaded.read_text().replace("Iraq", "=CMD()"))
    registry = json.loads(registry_path.read_text())
    registry["artifacts"][0]["sha256"] = hashlib.sha256(unloaded.read_bytes()).hexdigest()
    registry["artifacts"][0]["file_size_bytes"] = len(unloaded.read_bytes())
    _write_json(registry_path, registry)
    with pytest.raises(ogd.OGDPortTradeError, match="csv_identity_invalid"):
        ogd.validate_only(unloaded, loaded, registry_path=registry_path)


def test_loaded_country_heading_is_not_silently_relabelled_destination(
    tmp_path: Path,
) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    report = ogd.validate_only(unloaded, loaded, registry_path=registry_path)
    assert report["flows"][1]["country_semantics"] == (
        "provider_heading_says_country_of_origin_for_loaded_cargo_destination_not_asserted"
    )


def test_compile_requires_signed_approved_rights_and_keeps_edges_empty(
    tmp_path: Path,
) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    with pytest.raises(ogd.OGDPortTradeError, match="rights_not_approved"):
        ogd.compile_baseline(
            unloaded,
            loaded,
            root=ROOT,
            registry_path=registry_path,
        )

    registry_path, unloaded, loaded = _fixture(tmp_path / "approved")
    root = registry_path.parents[1]
    rights, signers = _approved_rights(root)
    result = ogd.compile_baseline(
        unloaded,
        loaded,
        root=root,
        registry_path=registry_path,
        rights_path=rights,
        signers_path=signers,
    )
    assert result["_meta"]["publication_allowed"] is True
    assert len(result["joint_observations"]) == 39
    assert result["coverage"]["joint_observation_frame_count"] == 39
    assert len(result["coverage"]["joint_observation_frame_sha256"]) == 64
    assert {
        status: sum(row["value_status"] == status for row in result["joint_observations"])
        for status in ("observed_positive", "observed_zero", "source_missing")
    } == {
        "observed_positive": 3,
        "observed_zero": 35,
        "source_missing": 1,
    }
    missing = next(
        row for row in result["joint_observations"] if row["value_status"] == "source_missing"
    )
    assert missing["quantity"] is None
    assert result["dependency_edges"] == []
    assert "country_crosswalk" in result["dependency_edge_status"]


def test_tampered_rights_signature_refuses(tmp_path: Path) -> None:
    registry_path, unloaded, loaded = _fixture(tmp_path)
    root = registry_path.parents[1]
    rights, signers = _approved_rights(root)
    (root / "governance" / "rights_decisions" / "fixture_ogd.sig").write_bytes(b"0" * 64)
    with pytest.raises(
        ogd.OGDPortTradeError, match="rights_rights_source_decision_signature_invalid"
    ):
        ogd.compile_baseline(
            unloaded,
            loaded,
            root=root,
            registry_path=registry_path,
            rights_path=rights,
            signers_path=signers,
        )
