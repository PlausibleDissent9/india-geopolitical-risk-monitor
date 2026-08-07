"""Regression locks for the independent splice-calibration audit."""
from pathlib import Path

from analysis.splice_overlap_audit import audit

ROOT = Path(__file__).resolve().parents[1]


def test_audit_uses_genuinely_additional_overlap_where_available():
    result = audit()
    assert result["pakistan_west"]["independent_n"] == 18
    assert result["china_east"]["independent_n"] == 18
    assert result["gulf_energy"]["independent_n"] == 18
    assert result["us_trade"]["additional_independent_days"] == 0
    assert result["shipping"]["additional_independent_days"] == 0


def test_recovered_independent_ratios_are_not_the_circular_n38_result():
    result = audit()
    assert result["pakistan_west"]["independent_ratio"] == 2.4634
    assert result["china_east"]["independent_ratio"] == 2.6998
    assert result["gulf_energy"]["independent_ratio"] == 1.8098
    assert result["pakistan_west"]["relative_change_pct"] == 26.0
    assert result["china_east"]["relative_change_pct"] == -19.7
    assert result["gulf_energy"]["relative_change_pct"] == 1.0


def test_n1_channels_are_not_presented_as_reestimates():
    result = audit()
    assert result["us_trade"]["relative_change_pct"] is None
    assert result["shipping"]["relative_change_pct"] is None


def test_public_methodology_discloses_the_failed_stability_claim():
    page = (ROOT / "methodology.md").read_text(encoding="utf-8")
    assert "proposed 38-day stability check was rejected" in page
    assert "2.4634 (18)" in page
    assert "not independently re-estimable (1)" in page
    assert "splice_sensitivity.json" in page
    assert "no ratio moved by more than 1.1%" not in page


def test_validation_page_separates_the_two_episode_tranches():
    page = (ROOT / "docs" / "validation.html").read_text(encoding="utf-8")
    assert "Original tranche: <b>" in page
    assert "Second dated tranche: <b>" in page
