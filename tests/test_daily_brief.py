"""Daily brief: the measurement-language lint, the registered prompt,
and the fail-closed no-key path. No network anywhere."""
from __future__ import annotations

from src import daily_brief


def test_lint_drops_predictive_language_and_keeps_measurement():
    assert daily_brief.lint(
        "Attention will rise as the standoff continues."
    ) is None
    assert daily_brief.lint("The model forecasts escalation.") is None
    assert daily_brief.lint("Coverage is likely to intensify.") is None
    kept = ("Pakistan coverage scored 91.2, up 15.7 versus yesterday, "
            "driven by Indus Waters Treaty statements.")
    assert daily_brief.lint(kept) == kept
    assert daily_brief.lint(None) is None


def test_registered_prompt_loads_with_version():
    system_prompt, version = daily_brief.load_prompt()
    assert version == "1.0.0"
    assert "Measurement language only" in system_prompt
    # Registration metadata must not leak into what the model is told.
    assert "append-only" not in system_prompt


def test_no_api_key_is_a_clean_skip(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    daily_brief.main()
    assert "fail-closed" in capsys.readouterr().out


def test_schema_requires_every_channel():
    props = daily_brief.SCHEMA["properties"]["channels"]
    assert set(props["required"]) == set(daily_brief.CHANNELS)
    assert props["additionalProperties"] is False


def test_experimental_gauge_is_not_a_brief_ingredient(monkeypatch, tmp_path):
    """A 2/29 experimental secondary gauge must not be elevated by the
    daily language model into the day's headline narrative."""
    data = tmp_path / "data"
    data.mkdir()
    (data / "latest.json").write_text(
        '{"date":"2026-08-06","composite":50,"channels":{}}',
        encoding="utf-8")
    (data / "receipts.json").write_text(
        '{"date":"2026-08-06","channels":{}}', encoding="utf-8")
    (data / "stress_gauge.json").write_text(
        '{"gauge":99,"_meta":{"headline_eligible":false}}',
        encoding="utf-8")
    monkeypatch.setattr(daily_brief, "SITE_DATA", data)
    assert "stress_gauge" not in daily_brief.build_context()
