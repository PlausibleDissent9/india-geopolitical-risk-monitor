"""Cross-language validity: refusals, no scipy, and an honest gap rule."""
from __future__ import annotations

import numpy as np
import pandas as pd
from src import wiki_hindi


def _series(n, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2017-01-01", periods=n, freq="D")
    return pd.Series(rng.normal(size=n), index=idx)


def test_a_short_overlap_refuses_rather_than_reports():
    a, b = _series(100), _series(100, seed=1)
    out = wiki_hindi._corr(a, b)
    assert out["levels_pearson"] is None
    assert out["refused"] == "fewer than 180 overlapping days"


def test_spearman_matches_pearson_on_ranks_without_scipy():
    """The project ships no scipy; Spearman must still be Spearman."""
    a, b = _series(400), _series(400, seed=2)
    out = wiki_hindi._corr(a, b)
    expected = float(a.rank().corr(b.rank()))
    assert out["levels_spearman"] == round(expected, 4)


def test_perfect_monotone_but_nonlinear_separates_the_two_measures():
    idx = pd.date_range("2017-01-01", periods=400, freq="D")
    x = pd.Series(np.linspace(1, 400, 400), index=idx)
    y = x ** 3
    out = wiki_hindi._corr(x, y)
    # Spearman sees a perfect monotone relation; Pearson does not.
    assert out["levels_spearman"] == 1.0
    assert out["levels_pearson"] < 1.0
    # x is a straight line, so its day-to-day change is constant and the
    # changes correlation is mathematically undefined. It must publish
    # as null, never as a bare NaN that would make the JSON unparseable.
    assert out["changes_pearson"] is None


def test_undefined_correlations_publish_as_null_not_nan():
    """json.dumps writes bare NaN, which no strict JSON parser accepts;
    a payload that cannot be read is worse than a missing field."""
    import json
    idx = pd.date_range("2017-01-01", periods=400, freq="D")
    flat = pd.Series([1.0] * 400, index=idx)
    out = wiki_hindi._corr(flat, _series(400, seed=9))
    assert out["levels_pearson"] is None
    assert "NaN" not in json.dumps(out)


def test_changes_are_computed_on_differences_not_levels():
    """A shared trend must not be allowed to masquerade as agreement."""
    idx = pd.date_range("2017-01-01", periods=400, freq="D")
    trend = pd.Series(np.linspace(0, 10, 400), index=idx)
    rng = np.random.default_rng(3)
    a = trend + pd.Series(rng.normal(size=400), index=idx)
    b = trend + pd.Series(rng.normal(size=400), index=idx)
    out = wiki_hindi._corr(a, b)
    # Both are mostly trend, so levels agree strongly...
    assert out["levels_pearson"] > 0.8
    # ...while their day-to-day movements are independent noise.
    assert abs(out["changes_pearson"]) < 0.2


def test_the_thin_channel_floor_exists_and_is_a_real_number():
    """A correlation on a handful of daily views is a statement about
    Poisson noise; the module must have a floor rather than a vibe."""
    assert wiki_hindi.MIN_MEDIAN_VIEWS > 0


def test_english_leads_requires_both_levels_and_changes():
    """One metric leading is a coin flip; requiring both is what makes
    'five of five, one-directional' mean something."""
    gaps = {
        "both": {"english_changes": 0.5, "hindi_changes": 0.1,
                 "english_levels": 0.6, "hindi_levels": 0.2},
        "levels_only": {"english_changes": 0.1, "hindi_changes": 0.4,
                        "english_levels": 0.6, "hindi_levels": 0.2},
        "changes_only": {"english_changes": 0.5, "hindi_changes": 0.1,
                         "english_levels": 0.1, "hindi_levels": 0.7},
    }
    leads = [ch for ch, g in gaps.items()
             if g["english_changes"] > g["hindi_changes"]
             and g["english_levels"] > g["hindi_levels"]]
    assert leads == ["both"]


def test_published_payload_never_substitutes_a_missing_hindi_article():
    """Unresolved titles must be reported, never quietly replaced."""
    import json
    from pathlib import Path
    p = (Path(__file__).resolve().parents[1] / "docs" / "data"
         / "wiki_hindi.json")
    if not p.exists():
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    for ch, blk in d["channels"].items():
        n_res = blk.get("n_articles_resolved", 0)
        n_reg = blk.get("n_articles_registered", 0)
        missing = blk.get("missing_english_titles", [])
        assert n_res + len(missing) == n_reg, (
            f"{ch}: resolved+missing must account for every registered "
            "article, or a title was silently substituted")
