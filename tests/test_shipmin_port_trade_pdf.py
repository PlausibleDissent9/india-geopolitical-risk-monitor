from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from src import shipmin_port_trade_pdf as shipmin

ROOT = Path(__file__).resolve().parents[1]


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
    assert alpha["values"]["SMP(HDC)"] == 0
    assert alpha["values"]["PPA"] is None
    assert beta["values"]["ALL PORTS"] is None
    assert beta["reconciliation_drift"] is None


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
        shipmin.compile_baseline(tmp_path / "not-opened.pdf")


def test_registry_source_is_review_required_and_cannot_claim_publication() -> None:
    rights = json.loads((ROOT / "governance" / "source_rights_registry.json").read_text())
    source = next(
        row for row in rights["sources"] if row["source_id"] == "india_major_ports_bps_2024_25"
    )
    assert source["decision_state"] == "review_required"
    assert source["permitted_uses"] == []
    assert source["decision_signature_path"] is None
