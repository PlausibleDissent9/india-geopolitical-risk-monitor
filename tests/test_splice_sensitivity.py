"""The frozen splice study stays separate and cannot outrun source rights."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from src import final_publication, ngram_rights
from src.splice_sensitivity import build

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs/data/splice_sensitivity.json"


def _frozen_payload() -> dict:
    raw = PAYLOAD.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == final_publication._LEGACY_AUG9_BLOBS[
        "docs/data/splice_sensitivity.json"
    ]
    return json.loads(raw)


def test_sensitivity_reports_material_score_impact_without_restatement():
    payload = _frozen_payload()
    meta = payload["_meta"]
    assert meta["status"] == "sensitivity analysis, not a replacement series"
    adjusted = meta["adjusted_store_dates"]
    assert adjusted == sorted(set(adjusted))
    assert meta["n_adjusted_store_days"] == len(adjusted)
    assert meta["generated"] == "2026-08-10"
    assert meta["affected_start"] == "2026-07-01"
    assert meta["affected_end"] == "2026-08-09"
    assert len(adjusted) == 40
    daily = payload["summary"]["daily"]
    weekly = payload["summary"]["trailing_7_day"]
    assert daily["pakistan_west"]["median_absolute_shift"] > 5
    assert daily["china_east"]["median_absolute_shift"] > 10
    assert weekly["china_east"]["median_absolute_shift"] > 20
    assert daily["composite"]["maximum_absolute_shift"] < 5


def test_one_day_channels_are_not_silently_reestimated():
    payload = _frozen_payload()
    audit = payload["calibration_audit"]
    assert audit["us_trade"]["additional_independent_days"] == 0
    assert audit["shipping"]["additional_independent_days"] == 0
    assert "us_trade" not in payload["daily"]["primary"]
    assert "shipping" not in payload["daily"]["primary"]


def test_recomputation_refuses_before_identity_cache_processing_without_rights():
    # The signed 2026-08-12 aggregate-2.0 decision approves the source for
    # aggregate uses only, so the identity-cache path now refuses one gate
    # later: not "review_required" but "use_not_permitted". Same boundary,
    # same refusal-before-processing; the identity path stays closed until a
    # separate identity-use decision exists.
    with pytest.raises(
        ngram_rights.NgramRightsError,
        match="^ngram_public_identity_use_not_permitted$",
    ):
        build()


def test_daily_lanes_do_not_recompute_the_rights_blocked_frozen_study():
    for relative in (".github/workflows/daily.yml", ".github/workflows/morning.yml"):
        assert "python -m src.splice_sensitivity" not in (ROOT / relative).read_text(
            encoding="utf-8"
        )
