"""Daily publication must transform the accepted store without refetching it.

Both production workflows run the exact-target final-publication acquisition
before run_daily. An online run_daily then opens a second GDELT DOC acquisition
over a 14-day tail, mixing source regimes and consuming the lane's complete
timeout. The post-acquisition transformation therefore runs with IGRM_OFFLINE;
explicit backfills remain online and separately bounded.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from src import fetch_gdelt

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def test_both_post_heal_pipelines_are_offline() -> None:
    morning = (WORKFLOWS / "morning.yml").read_text(encoding="utf-8")
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")

    acquisition = "--acquire-target"
    morning_pipeline = (
        "IGRM_OFFLINE=1 /usr/bin/time -v timeout --signal=TERM 7m "
        "python -m src.run_daily --final-only"
    )
    daily_pipeline = "IGRM_OFFLINE=1 timeout 30m python -m src.run_daily"
    assert morning.index(acquisition) < morning.index(
        morning_pipeline
    )
    assert daily.index(acquisition) < daily.index(
        daily_pipeline
    )
    assert "python -m src.fetch_ngrams --heal" not in morning
    assert "python -m src.fetch_ngrams --heal" not in daily
    assert "IGRM_OFFLINE=1 python -m src.run_daily --backfill" not in daily


def test_offline_incremental_load_preserves_the_healed_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    store = raw / "gdelt_volume.csv"
    original = pd.DataFrame(
        {
            "date": ["2026-08-09", "2026-08-10"],
            "test_channel": [0.25, 0.5],
        }
    )
    original.to_csv(store, index=False)

    monkeypatch.setenv("IGRM_OFFLINE", "1")
    monkeypatch.setattr(fetch_gdelt, "RAW_DIR", raw)
    monkeypatch.setattr(fetch_gdelt, "CHUNK_CACHE_DIR", raw / "chunks")

    def network_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("offline post-heal pipeline attempted network access")

    monkeypatch.setattr(fetch_gdelt, "_fetch_chunk_network", network_forbidden)
    observed = fetch_gdelt.load_or_update(
        {"test_channel": {"terms": ["test phrase"]}}
    )

    expected = original.copy()
    expected["date"] = pd.to_datetime(expected["date"]).dt.date
    expected = expected.set_index("date")
    pd.testing.assert_frame_equal(observed, expected, check_freq=False)
    persisted = pd.read_csv(store)
    pd.testing.assert_frame_equal(persisted, original)
