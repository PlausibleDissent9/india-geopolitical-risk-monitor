"""Tests for the BigQuery backfill matcher (profile 3.0).

The golden loop is the point: rows in via a fake query runner, windows
counted with the file feed's own token functions, an attestation assembled,
and the hostile 3.0 validator must accept it end to end.
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from src import fetch_ngrams_bq as bqf
from src import ngram_bq_attestation as bqa

ROOT = Path(__file__).resolve().parents[1]
TARGET = date(2026, 8, 11)
PROOF_DAY = date(2026, 8, 9)


def _specs() -> dict[str, dict[str, Any]]:
    return {
        "g_alpha": {
            "channel": "pakistan_west",
            "phrases": [("border", "clash")],
            "anchor": "india",
        },
        "g_beta": {"channel": "shipping", "phrases": [("red", "sea")], "anchor": None},
    }


def _provenance() -> dict[str, Any]:
    return {
        "table": "gdelt-bq.gdeltv2.webngrams",
        "query_text_sha256": "ab" * 32,
        "job_id": "igrm_backfill_20260811_0001",
        "job_created_utc": "2026-08-15T21:00:00Z",
        "total_bytes_processed": 123456789,
        "table_last_modified_utc": "2026-08-15T20:59:00Z",
    }


def _stamp(day: date, bucket: int, offset_minutes: int = 1) -> str:
    minute = bucket * 30 + offset_minutes
    return f"{day:%Y%m%d}{minute // 60:02d}{minute % 60:02d}00"


class FakeRunner:
    """Serves canned rows keyed by which builder produced the query."""

    def __init__(self, day: date, specs: dict[str, dict[str, Any]]) -> None:
        self.day = day
        self.specs = specs
        self.queries: list[str] = []
        self.stamps = [_stamp(day, bucket) for bucket in range(48)]

    def __call__(self, query: str) -> list[dict[str, Any]]:
        self.queries.append(query)
        if query == bqf.minute_discovery_query(self.day):
            return [
                {"stamp": stamp, "row_count": 200_000 + index}
                for index, stamp in enumerate(self.stamps)
            ]
        if query == bqf.denominator_query(self.day, self.stamps):
            return [
                {"stamp": stamp, "english_documents": 1000} for stamp in self.stamps
            ]
        if query == bqf.context_rows_query(self.day, self.stamps, self.specs):
            rows = []
            for stamp in self.stamps:
                # One document matching g_alpha with the india anchor, one
                # matching g_beta, one trigger hit that matches nothing.
                rows.append(
                    {
                        "stamp": stamp,
                        "url": f"https://example.com/{stamp}/a",
                        "context": "india border clash reported near the line",
                    }
                )
                rows.append(
                    {
                        "stamp": stamp,
                        "url": f"https://example.com/{stamp}/b",
                        "context": "red sea transits slowed again",
                    }
                )
                rows.append(
                    {
                        "stamp": stamp,
                        "url": f"https://example.com/{stamp}/c",
                        "context": "borderline commentary about nothing",
                    }
                )
            return rows
        raise AssertionError(f"unexpected query: {query[:120]}")


def _synthetic_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    for relative in (bqa.PROFILE_RELATIVE, bqa.SCHEMA_RELATIVE):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    for module_relative in ("src/fetch_ngrams_bq.py", "src/ngram_bq_attestation.py"):
        destination = root / module_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / module_relative, destination)
    (root / "dictionaries.json").write_text('{"synthetic": true}', encoding="utf-8")
    calibration = root / "data/raw/ngram_calibration.json"
    calibration.parent.mkdir(parents=True, exist_ok=True)
    calibration.write_text('{"synthetic_calibration": true}', encoding="utf-8")
    ledger = root / bqa.REFUSAL_LEDGER_RELATIVE / f"{TARGET.isoformat()}.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "target_date": TARGET.isoformat(),
                "failure_stage": "source",
                "reason_code": "source_acquisition_failed",
                "status": "refused_value_free",
                "generated": "2026-08-12 06:20 IST",
            }
        ),
        encoding="utf-8",
    )
    return root


def test_recompute_day_counts_with_file_feed_semantics() -> None:
    specs = _specs()
    runner = FakeRunner(TARGET, specs)
    computed = bqf.recompute_day(TARGET, specs, runner)
    assert len(computed["windows"]) == 48
    first = computed["windows"][0]
    assert first["window_start_utc"] == "2026-08-11T00:00:00Z"
    assert first["english_denominator"] == 1000
    # g_alpha needs both the phrase and the india anchor; g_beta only the
    # phrase; the near-miss document matches neither.
    assert first["group_numerators"] == {"g_alpha": 1, "g_beta": 1}
    assert len(runner.queries) == 3


def test_missing_window_refuses() -> None:
    specs = _specs()
    runner = FakeRunner(TARGET, specs)
    full_discovery = bqf.minute_discovery_query(TARGET)

    def gapped(query: str) -> list[dict[str, Any]]:
        rows = runner(query)
        if query == full_discovery:
            return [row for row in rows if not str(row["stamp"]).startswith(f"{TARGET:%Y%m%d}00")]
        return rows

    with pytest.raises(bqf.BqAcquisitionError) as excinfo:
        bqf.recompute_day(TARGET, specs, gapped)
    assert excinfo.value.code.startswith("bq_backfill_windows_missing")


def test_numerator_exceeding_denominator_refuses() -> None:
    specs = _specs()
    runner = FakeRunner(TARGET, specs)

    def inconsistent(query: str) -> list[dict[str, Any]]:
        rows = runner(query)
        if query == bqf.denominator_query(TARGET, runner.stamps):
            return [{"stamp": row["stamp"], "english_documents": 0} for row in rows]
        return rows

    with pytest.raises(bqf.BqAcquisitionError) as excinfo:
        bqf.recompute_day(TARGET, specs, inconsistent)
    assert excinfo.value.code == "bq_backfill_denominator_empty"


def test_golden_loop_attestation_validates(tmp_path: Path) -> None:
    specs = _specs()
    root = _synthetic_root(tmp_path)
    runner = FakeRunner(TARGET, specs)
    computed = bqf.recompute_day(TARGET, specs, runner)

    proof_runner = FakeRunner(PROOF_DAY, specs)
    proof_computed = bqf.recompute_day(PROOF_DAY, specs, proof_runner)
    reference = bqf.aggregate_sides(proof_computed["windows"], specs)
    proof = bqf.build_equivalence_proof(
        day=PROOF_DAY,
        specs=specs,
        windows=proof_computed["windows"],
        published_reference=reference,
        provenance=_provenance(),
        root=root,
    )
    assert proof["exact_match"] is True
    proof_path = root / bqa.EQUIVALENCE_RELATIVE / f"{PROOF_DAY.isoformat()}.json"
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    attestation = bqf.build_backfill_attestation(
        day=TARGET,
        specs=specs,
        windows=computed["windows"],
        equivalence_day=PROOF_DAY,
        equivalence_record_sha256=proof["record_sha256"],
        provenance=_provenance(),
        root=root,
    )
    validated = bqa.validate(attestation, target=TARGET, specs=specs, root=root)
    assert validated["aggregate_reconstruction"]["group_numerators"] == {
        "g_alpha": 48,
        "g_beta": 48,
    }


def test_non_exact_equivalence_is_sealed_but_refused(tmp_path: Path) -> None:
    specs = _specs()
    root = _synthetic_root(tmp_path)
    runner = FakeRunner(PROOF_DAY, specs)
    computed = bqf.recompute_day(PROOF_DAY, specs, runner)
    reference = bqf.aggregate_sides(computed["windows"], specs)
    drifted_reference = json.loads(json.dumps(reference))
    drifted_reference["english_denominator"] += 1
    proof = bqf.build_equivalence_proof(
        day=PROOF_DAY,
        specs=specs,
        windows=computed["windows"],
        published_reference=drifted_reference,
        provenance=_provenance(),
        root=root,
    )
    assert proof["exact_match"] is False
    with pytest.raises(bqa.BqAttestationError) as excinfo:
        bqa.validate_equivalence_proof(proof, root=root, specs=specs)
    assert excinfo.value.code == "bq_equivalence_proof_not_exact"


def test_query_text_is_deterministic() -> None:
    specs = _specs()
    stamps = [_stamp(TARGET, bucket) for bucket in range(48)]
    assert bqf.minute_discovery_query(TARGET) == bqf.minute_discovery_query(TARGET)
    assert bqf.denominator_query(TARGET, stamps) == bqf.denominator_query(
        TARGET, stamps
    )
    first = bqf.context_rows_query(TARGET, stamps, specs)
    second = bqf.context_rows_query(TARGET, stamps, specs)
    assert first == second
    assert "lang = 'en'" in first
    assert "red\\ sea|india" not in first  # fragments are first tokens only
