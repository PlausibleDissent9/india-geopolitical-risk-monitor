"""The public language comparison must disclose its partial denominator."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs" / "data" / "multilingual.json"
PAGE = ROOT / "docs" / "validation.html"


def _payload() -> dict:
    return json.loads(PAYLOAD.read_text(encoding="utf-8"))


def test_coverage_accounts_for_every_registered_channel_language_pair():
    data = _payload()
    meta = data["_meta"]
    expected = {
        f"{channel}_{language}"
        for channel in meta["registered_channels"]
        for language in meta["languages"]
    }
    published = {
        f"{channel}_{language}"
        for channel, block in data["channels"].items()
        for language in block["languages_compared"]
    }
    coverage = meta["coverage"]
    assert coverage["n_expected_series"] == len(expected)
    assert coverage["n_published_series"] == len(published)
    assert coverage["n_expected_channels"] == len(meta["registered_channels"])
    assert coverage["n_published_channels"] == len(data["channels"])
    assert coverage["complete"] == (published == expected)
    assert coverage["missing_series"] == sorted(expected - published)


def test_each_row_is_aligned_and_its_latest_divergence_recomputes():
    data = _payload()
    for channel, block in data["channels"].items():
        n = len(block["weeks"])
        languages = block["languages_compared"]
        assert languages == list(block["lang_pct"])
        assert set(languages).isdisjoint(block["languages_pending"])
        assert set(languages) | set(block["languages_pending"]) == set(
            data["_meta"]["languages"])
        assert len(block["english_pct"]) == len(block["divergence"]) == n
        assert n >= 26, f"{channel} publishes a 26-week statistic on {n} weeks"
        assert all(len(block["lang_pct"][language]) == n
                   for language in languages)
        non_english = sum(block["lang_pct"][language][-1]
                          for language in languages) / len(languages)
        expected = round(block["english_pct"][-1] - non_english, 1)
        assert block["latest_divergence"] == pytest.approx(expected, abs=0.05)


def test_validation_surface_never_hides_partial_or_failed_coverage():
    page = PAGE.read_text(encoding="utf-8")
    section = page.split('<section id="ml-section"', 1)[1].split(
        "</section>", 1)[0]
    normalized = " ".join(section.split())
    assert not section.lstrip().startswith(" hidden")
    assert "does not establish which language is correct" in section
    assert "represent the full Indian news ecosystem" in normalized
    assert 'href="data/multilingual.json"' in section
    assert "ml._meta" in page and "meta.coverage" in page
    assert "d.languages_compared" in page
    assert "Coverage is partial" in page
    assert "failed to load; no result is displayed" in page
    assert page.index("renderMultilingual();") < page.index("const v = await j(")
