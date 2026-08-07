"""The public disagreement record must stay aligned with its frozen sources."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER_PATH = ROOT / "docs" / "data" / "divergence_register.json"
BENCHMARK_PATH = ROOT / "docs" / "data" / "ai_gpr_benchmark.json"
PAGE_PATH = ROOT / "docs" / "divergence.html"
RUN_LOG_PATH = ROOT / "analysis" / "ai_gpr_benchmark_run_log.md"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_register_ids_are_unique_and_rows_have_receipts_and_limits() -> None:
    rows = _load(REGISTER_PATH)["entries"]
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert len(rows) == 7
    for row in rows:
        assert row["evidence_url"].startswith("https://igrm.in/")
        assert row["source_payload"].startswith("data/")
        assert row["claim_limit"]
        assert 0 <= row["igrm_rank"] <= 100
        assert 0 <= row["comparator_rank"] <= 100
        assert 0 <= row["absolute_gap"] <= 100


def test_ai_gpr_rows_are_verbatim_ranks_from_frozen_result() -> None:
    benchmark = _load(BENCHMARK_PATH)
    registered = _load(REGISTER_PATH)["entries"]
    ai_rows = {
        row["period"]: row for row in registered if row["family"] == "igrm_vs_ai_gpr_india_all"
    }

    assert len(ai_rows) == 5
    for source in benchmark["largest_rank_divergences"]:
        period = source["month"][:7]
        row = ai_rows[period]
        assert row["igrm_rank"] == source["igrm_composite_rank"]
        assert row["comparator_rank"] == source["ai_gpr_india_all_rank"]
        assert row["absolute_gap"] == source["absolute_gap"]
        assert row["evidence_url"] == source["igrm_evidence_url"]


def test_static_page_contains_every_machine_readable_row() -> None:
    page = PAGE_PATH.read_text(encoding="utf-8")
    for row in _load(REGISTER_PATH)["entries"]:
        assert f'id="{row["id"]}"' in page
        assert f'>{row["absolute_gap"]:.1f}<' in page


def test_run_log_names_the_verbatim_result_hash_and_operational_failure() -> None:
    result_hash = hashlib.sha256(BENCHMARK_PATH.read_bytes()).hexdigest()
    log = RUN_LOG_PATH.read_text(encoding="utf-8")
    assert result_hash in log
    assert "No statistic was returned" in log
    assert "no analytical deviations" in log.lower()
