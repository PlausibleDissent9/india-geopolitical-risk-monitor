"""Rounded-inputs tolerance locks for the dual-computation audit.

The published composite is rounded from the UNROUNDED channel mean while
the audit recomputes a mean of the already-rounded published scores, so
two honest computations may differ by up to ~0.10. A 0.051 bound refused
the green 2026-08-15 final at composite 47.8 vs recomputed mean 47.74
(run 31919051691) and cost the 06:00 IST contract -- the same defect the
gauge check fixed on 2026-08-03.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from src import audit


def _write_latest(data: Path, composite: float, channel_scores: list[float]) -> None:
    names = ["diplomatic", "military", "economic", "internal", "energy"]
    (data / "latest.json").write_text(
        json.dumps(
            {
                "composite": composite,
                "channels": {
                    n: {"score": s} for n, s in zip(names, channel_scores)
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def isolated_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "docs" / "data"
    data.mkdir(parents=True)
    monkeypatch.setattr(audit, "DATA", data)
    monkeypatch.setattr(audit, "RAW", tmp_path / "data" / "raw")
    return data


def test_composite_within_rounded_inputs_bound_passes(isolated_audit: Path) -> None:
    # The exact refused 2026-08-15 shape: published channel scores whose
    # mean is 47.74 under a composite of 47.8 (rounded from the unrounded
    # mean). Gap 0.06 is honest rounding, not a computation mismatch.
    _write_latest(isolated_audit, 47.8, [47.8, 47.7, 47.7, 47.7, 47.8])
    audit.main()


def test_composite_beyond_rounded_inputs_bound_refuses(isolated_audit: Path) -> None:
    # 0.16 above the published-channel mean cannot be rounding on either
    # side; the audit must still refuse a genuinely wrong composite.
    _write_latest(isolated_audit, 47.9, [47.8, 47.7, 47.7, 47.7, 47.8])
    with pytest.raises(SystemExit):
        audit.main()
