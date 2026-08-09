from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src import shipmin_port_trade_pdf as shipmin

ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _word(text: str, x: float, top: float, width: float = 4) -> dict[str, object]:
    return {
        "text": text,
        "x0": x - width / 2,
        "x1": x + width / 2,
        "top": top,
        "bottom": top + 4,
    }


def _header() -> list[dict[str, object]]:
    words = [_word("Origin/Commodities", 25, 10, 46)]
    words.extend(
        _word(name, 100 + index * 25, 10, 12)
        for index, name in enumerate(shipmin._PORT_COLUMNS[:-1])
    )
    words.extend([_word("ALL", 423, 10, 6), _word("PORTS", 437, 10, 10)])
    return words


def _row(
    label: str,
    top: float,
    values: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    words = [_word(label, 25, top, 30)]
    for column, value in (values or {}).items():
        index = shipmin._PORT_COLUMNS.index(column)
        centre = 430 if column == "ALL PORTS" else 100 + index * 25
        words.append(_word(value, centre, top))
    return words


def _fixture_words() -> list[dict[str, object]]:
    summary = {name: "0" for name in shipmin._PORT_COLUMNS}
    summary.update({"SMP(KDS)": "5", "SMP(HDC)": "2", "ALL PORTS": "7"})
    return [
        *_header(),
        *_row("TEST-COMMODITY", 30),
        *_row("Alpha", 40, {"SMP(KDS)": "4", "SMP(HDC)": "0", "ALL PORTS": "4"}),
        *_row("Beta", 50, {"SMP(KDS)": "1", "SMP(HDC)": "2"}),
        *_row("Total", 60, summary),
    ]


def _config() -> dict[str, object]:
    return {
        "flow": "unloaded",
        "table_id": "2.1.6",
        "pdf_pages": [1],
        "country_semantics": "country_of_origin",
        "commodities": ["TEST-COMMODITY"],
        "expected_detail_rows": 2,
        "expected_positive_joint_cells": 3,
        "expected_rows_missing_all_ports_total": 1,
        "expected_commodity_total_drifts": {"TEST-COMMODITY": 0},
    }


def _provider(words: list[dict[str, object]]):
    def provide(page: int) -> list[dict[str, object]]:
        assert page == 1
        return words

    return provide


def _approved_rights_fixture(
    root: Path, *, review_due: str, revoked_on: str | None
) -> tuple[Path, Path, dict[str, object]]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    signers_path = root / "governance/rights_signers.json"
    signers = {
        "schema_version": "1.0.0",
        "effective": "2026-08-09",
        "default_policy": "deny",
        "signers": [
            {
                "signer_id": "signer:fixture.shipmin",
                "name": "Fixture Shipmin rights signer",
                "role": "test-only rights reviewer",
                "public_key_ed25519_base64": base64.b64encode(public).decode(),
                "effective": "2026-08-09",
                "revoked_on": revoked_on,
            }
        ],
    }
    _write_json(signers_path, signers)
    source = {
        "source_id": "fixture_shipmin_source",
        "name": "Fixture Shipmin source",
        "provider": "Fixture provider",
        "role": "official_synthetic_joint_cargo_frame",
        "authority_class": "official_primary",
        "independence_group": "fixture_shipmin_provider",
        "lineage_policy": "primary",
        "decision_state": "approved",
        "decision_id": "fixture-shipmin-rights-2026-08-09",
        "decision_owner": "Fixture rights owner",
        "signer_id": "signer:fixture.shipmin",
        "decision_artifact_path": "governance/rights_decisions/fixture_shipmin.json",
        "decision_artifact_sha256": "0" * 64,
        "decision_signature_path": "governance/rights_decisions/fixture_shipmin.sig",
        "reviewed_on": "2026-08-09",
        "review_due": review_due,
        "access_url": "https://example.test/fixture",
        "terms_url": "https://example.test/terms",
        "access_basis": "synthetic_fixture",
        "geographic_coverage": "Synthetic fixture",
        "historical_coverage": "One synthetic period",
        "retrieval_target": "Synthetic rights boundary",
        "outage_fallback": "Fail closed",
        "cost_owner": "Fixture owner",
        "reproducibility_tier": "open_synthetic_fixture",
        "max_current_age_days": 3650,
        "permitted_uses": [
            "cite_metadata",
            "publish_derived_value",
            "publish_extract",
        ],
        "notes": "Synthetic test-only decision; not legal advice.",
    }
    decision = {
        key: source[key]
        for key in (
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
        statement="Synthetic test authorization for the exact listed uses.",
    )
    decision_path = root / str(source["decision_artifact_path"])
    _write_json(decision_path, decision)
    signature_path = root / str(source["decision_signature_path"])
    signature_path.write_bytes(private.sign(decision_path.read_bytes()))
    source["decision_artifact_sha256"] = hashlib.sha256(
        decision_path.read_bytes()
    ).hexdigest()
    rights_path = root / "governance/source_rights_registry.json"
    _write_json(
        rights_path,
        {
            "schema_version": "1.0.0",
            "effective": "2026-08-09",
            "default_policy": "deny",
            "sources": [source],
        },
    )
    registry = {
        "source": {
            "source_id": source["source_id"],
            "required_permitted_uses": [
                "cite_metadata",
                "publish_derived_value",
                "publish_extract",
            ],
        }
    }
    return rights_path, signers_path, registry


def test_committed_registry_binds_latest_official_pdf_and_implementation() -> None:
    registry, _ = shipmin._registry()
    assert registry["artifact"] == {
        "url": "https://shipmin.gov.in/sites/default/files/BPS%202024-25_compressed.pdf",
        "sha256": "c443531e8b7acd3d6912b25b99c97b2b2388fcba9d18d60123e2513fcd76e478",
        "file_size_bytes": 2469332,
        "page_count": 243,
        "published_on": "2026-04-29",
        "retrieved_at": "2026-08-08T20:04:00Z",
        "table_ids": ["2.1.6", "2.1.7"],
    }
    implementation = ROOT / registry["implementation"]["path"]
    assert (
        hashlib.sha256(implementation.read_bytes()).hexdigest()
        == registry["implementation"]["sha256"]
    )
    assert sum(row["expected_positive_joint_cells"] for row in registry["flows"]) == 1264


def test_parser_preserves_blank_zero_and_missing_printed_total() -> None:
    profile = shipmin._parse_flow(_config(), _provider(_fixture_words()))
    assert profile["coverage"] == {
        "detail_rows": 2,
        "summary_rows": 1,
        "port_columns": 13,
        "expected_joint_cells": 26,
        "positive_joint_cells": 3,
        "explicit_zero_cells": 1,
        "source_blank_cells": 22,
        "explicit_missing_cells": 0,
        "rows_missing_all_ports_total": 1,
    }
    alpha, beta = profile["rows"]
    assert alpha["page"] == 1
    assert [alpha["source_row"], beta["source_row"]] == [1, 2]
    assert alpha["values"]["SMP(HDC)"] == 0
    assert alpha["values"]["PPA"] is None
    assert beta["values"]["ALL PORTS"] is None
    assert beta["reconciliation_drift"] is None

    observations = shipmin._observations([profile], source_artifact_sha256="a" * 64)
    assert len(observations) == 26
    assert {row["source_row"] for row in observations} == {1, 2}
    assert {
        status: sum(row["value_status"] == status for row in observations)
        for status in ("observed_positive", "observed_zero", "source_blank")
    } == {
        "observed_positive": 3,
        "observed_zero": 1,
        "source_blank": 22,
    }
    assert all(
        row["quantity"] is None for row in observations if row["value_status"] == "source_blank"
    )


def test_commodity_sequence_and_numeric_column_geometry_fail_closed() -> None:
    words = _fixture_words()
    next(word for word in words if word["text"] == "TEST-COMMODITY")["text"] = "OTHER"
    with pytest.raises(shipmin.ShipminPortTradeError, match="pdf_commodity_sequence_invalid"):
        shipmin._parse_flow(_config(), _provider(words))

    words = _fixture_words()
    alpha = next(word for word in words if word["text"] == "4")
    alpha["x0"] = 470
    alpha["x1"] = 474
    with pytest.raises(shipmin.ShipminPortTradeError, match="pdf_value_outside_columns"):
        shipmin._parse_flow(_config(), _provider(words))


def test_row_and_registered_commodity_reconciliation_fail_closed() -> None:
    words = _fixture_words()
    next(word for word in words if word["text"] == "4")["text"] = "9"
    with pytest.raises(shipmin.ShipminPortTradeError, match="pdf_row_reconciliation_invalid"):
        shipmin._parse_flow(_config(), _provider(words))

    config = _config()
    config["expected_commodity_total_drifts"] = {"TEST-COMMODITY": 1}
    with pytest.raises(
        shipmin.ShipminPortTradeError,
        match="pdf_commodity_total_reconciliation_invalid",
    ):
        shipmin._parse_flow(config, _provider(_fixture_words()))


def test_artifact_size_and_digest_changes_refuse(tmp_path: Path) -> None:
    artifact = tmp_path / "source.pdf"
    artifact.write_bytes(b"official fixture")
    registry = {
        "artifact": {
            "file_size_bytes": len(artifact.read_bytes()),
            "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }
    }
    shipmin._verify_artifact(artifact, registry)
    artifact.write_bytes(artifact.read_bytes() + b"!")
    with pytest.raises(shipmin.ShipminPortTradeError, match="pdf_size_mismatch"):
        shipmin._verify_artifact(artifact, registry)

    artifact.write_bytes(b"different bytes")
    registry["artifact"]["file_size_bytes"] = len(artifact.read_bytes())
    with pytest.raises(shipmin.ShipminPortTradeError, match="pdf_digest_mismatch"):
        shipmin._verify_artifact(artifact, registry)


def test_compile_refuses_until_source_specific_rights_are_signed(tmp_path: Path) -> None:
    with pytest.raises(shipmin.ShipminPortTradeError, match="rights_not_approved"):
        shipmin.compile_baseline(
            tmp_path / "not-opened.pdf", as_of=date.fromisoformat("2026-08-09")
        )


def test_publication_refuses_expired_rights_at_explicit_as_of(tmp_path: Path) -> None:
    rights, signers, registry = _approved_rights_fixture(
        tmp_path, review_due="2026-08-09", revoked_on=None
    )
    with pytest.raises(shipmin.ShipminPortTradeError, match="rights_decision_expired"):
        shipmin._approved_source(
            root=tmp_path,
            registry=registry,
            rights_path=rights,
            signers_path=signers,
            as_of=date.fromisoformat("2026-08-10"),
        )


def test_publication_refuses_revoked_signer_at_explicit_as_of(tmp_path: Path) -> None:
    rights, signers, registry = _approved_rights_fixture(
        tmp_path, review_due="2027-08-09", revoked_on="2026-08-10"
    )
    with pytest.raises(shipmin.ShipminPortTradeError, match="rights_signer_inactive"):
        shipmin._approved_source(
            root=tmp_path,
            registry=registry,
            rights_path=rights,
            signers_path=signers,
            as_of=date.fromisoformat("2026-08-10"),
        )


def test_registry_source_is_review_required_and_cannot_claim_publication() -> None:
    rights = json.loads((ROOT / "governance" / "source_rights_registry.json").read_text())
    source = next(
        row for row in rights["sources"] if row["source_id"] == "india_major_ports_bps_2024_25"
    )
    assert source["decision_state"] == "review_required"
    assert source["permitted_uses"] == []
    assert source["decision_signature_path"] is None
