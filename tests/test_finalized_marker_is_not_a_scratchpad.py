"""A finalized marker with its receipt is a proof pointer, not a scratchpad.

WHAT HAPPENED (2026-08-19)

daily-update 32280274391's acquire step found target 2026-08-18 already
finalized and recorded that verdict -- by rewriting
data/raw/final_publication_status.json, which replaced status
"finalized" with "already_finalized" and DELETED the receipt block
pinning data/raw/final_publication_receipts/2026-08-18.json by sha256.
The run's own commit shipped the damage. The next run (32299777258)
read the marker, found "published target lacks a valid finalized
proof", and refused the entire pipeline at step 16. The receipt file
itself was intact the whole time; only the pointer to it had been
overwritten by an acknowledgment that the world was already good.

record_status now refuses to overwrite a marker that is a finalized
proof for the SAME target. Verdicts still return their record; markers
for a different target still move the lifecycle forward.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src import final_publication


def _write_marker(root: Path, payload: dict) -> Path:
    path = root / final_publication.STATUS_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return path


FINALIZED = {
    "schema_version": "1.0.0",
    "target_date": "2026-08-18",
    "status": "finalized",
    "reason": "the exact D-1 finalized score is published",
    "latest_finalized_date": "2026-08-18",
    "generated": "2026-08-19T01:21:35Z",
    "base_commit": "4924071c9ee806a5c561794d089b850e39f17af9",
    "value_fields_published": False,
    "provisional_substitution_allowed": False,
    "receipt": {
        "path": "data/raw/final_publication_receipts/2026-08-18.json",
        "sha256": "5d" + "0" * 62,
    },
}


def test_a_verdict_about_a_finalized_day_cannot_replace_its_proof(tmp_path):
    path = _write_marker(tmp_path, FINALIZED)
    before = path.read_bytes()
    record = final_publication.record_status(
        date(2026, 8, 18),
        "already_finalized",
        "the exact D-1 final is already published",
        root=tmp_path,
        base_commit="0" * 40,
    )
    assert record["status"] == "already_finalized"  # the caller still gets its record
    assert path.read_bytes() == before, (
        "an already-finalized acknowledgment overwrote the finalized "
        "proof pointer -- the 2026-08-19 damage, recurring")


def test_a_refusal_about_a_finalized_day_cannot_replace_its_proof_either(tmp_path):
    path = _write_marker(tmp_path, FINALIZED)
    before = path.read_bytes()
    final_publication.record_status(
        date(2026, 8, 18),
        "acquisition_failed",
        "published target lacks a valid finalized proof",
        root=tmp_path,
        base_commit="0" * 40,
    )
    assert path.read_bytes() == before


def test_a_new_target_still_moves_the_marker_forward(tmp_path):
    path = _write_marker(tmp_path, FINALIZED)
    final_publication.record_status(
        date(2026, 8, 19),
        "acquisition_failed",
        "source unavailable",
        root=tmp_path,
        base_commit="0" * 40,
    )
    marker = json.loads(path.read_text(encoding="utf-8"))
    assert marker["target_date"] == "2026-08-19"
    assert marker["status"] == "acquisition_failed"


def test_a_non_finalized_marker_is_still_overwritten_in_place(tmp_path):
    weak = dict(FINALIZED, status="already_finalized")
    weak.pop("receipt")
    path = _write_marker(tmp_path, weak)
    final_publication.record_status(
        date(2026, 8, 18),
        "acquisition_failed",
        "published target lacks a valid finalized proof",
        root=tmp_path,
        base_commit="0" * 40,
    )
    marker = json.loads(path.read_text(encoding="utf-8"))
    assert marker["status"] == "acquisition_failed"
