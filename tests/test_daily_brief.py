"""Daily brief: the measurement-language lint, the registered prompt,
the factual-grounding withdrawal, and the frozen null tombstone."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src import daily_brief, status_data

ROOT = Path(__file__).resolve().parents[1]


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


def test_main_is_a_hard_withdrawal_with_no_model_or_write_branch(
        monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-used")
    data = tmp_path / "data"
    data.mkdir()
    sentinel = data / "daily_brief.json"
    sentinel.write_text("sentinel", encoding="utf-8")
    monkeypatch.setattr(daily_brief, "SITE_DATA", data)

    daily_brief.main()
    assert "withdrawn_factual_grounding_failure" in capsys.readouterr().out
    assert sentinel.read_text(encoding="utf-8") == "sentinel"
    source = Path(daily_brief.__file__).read_text(encoding="utf-8")
    assert "import anthropic" not in source
    assert "client.messages.create" not in source
    assert daily_brief.PUBLICATION_ENABLED is False


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


def test_context_refuses_to_join_receipts_from_another_day(
        monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "latest.json").write_text(
        '{"date":"2026-08-07","composite":55.9,"channels":{}}',
        encoding="utf-8")
    (data / "receipts.json").write_text(
        '{"date":"2026-08-06","channels":{"shipping":'
        '{"articles":[{"title":"stale headline"}]}}}',
        encoding="utf-8")
    monkeypatch.setattr(daily_brief, "SITE_DATA", data)
    context = daily_brief.build_context()
    assert context["receipts_aligned_to_scores"] is False
    assert context["receipts"] == {}


def test_public_endpoint_is_only_the_contract_safe_null_tombstone():
    payload = json.loads(
        (ROOT / "docs" / "data" / "daily_brief.json").read_text(
            encoding="utf-8"))
    meta = payload["_meta"]
    assert meta["status"] == "withdrawn_factual_grounding_failure"
    assert date.fromisoformat(payload["date"]).isoformat() == payload["date"]
    assert payload["date"] == meta["withdrawn"] == meta["deprecated"]
    assert (date.fromisoformat(meta["earliest_removal"])
            - date.fromisoformat(meta["deprecated"])).days >= 90
    assert payload["composite"] is None
    assert set(payload["channels"]) == set(daily_brief.CHANNELS)
    assert all(value is None for value in payload["channels"].values())


def test_daily_workflow_cannot_receive_the_model_key():
    workflow = (ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8")
    block = workflow.split("- name: Machine-brief safety withdrawal check", 1)[1]
    block = block.split("\n      - name:", 1)[0]
    assert "python -m src.daily_brief" in block
    assert "ANTHROPIC_API_KEY" not in block
    assert "continue-on-error" not in block


def test_public_status_names_the_lane_as_withdrawn():
    registered = next(lane for lane in status_data.LANES
                      if lane["key"] == "daily_brief")
    assert registered["name"] == "Machine brief (withdrawn)"
    assert registered["field"] == "_meta.withdrawn"
    published = json.loads(
        (ROOT / "docs" / "data" / "status.json").read_text(encoding="utf-8"))
    lane = next(row for row in published["lanes"]
                if row["key"] == "daily_brief")
    assert lane["name"] == registered["name"]
    assert lane["last"] == "2026-08-08"
