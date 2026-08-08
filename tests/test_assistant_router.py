"""Adversarial tests for cost-bounded assistant model selection."""
from __future__ import annotations

import builtins
import json
import sys
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

import pytest
from src import assistant_router as router
from src import evidence_assistant as evidence

ROOT = Path(__file__).resolve().parents[1]


def _selection(intent: str, channels: list[str] | None = None) -> dict[str, object]:
    return {
        "schema_version": router.SELECTION_SCHEMA_VERSION,
        "intent": intent,
        "channels": channels or [],
    }


class FakePlanner:
    def __init__(
        self,
        selection: dict[str, object] | None = None,
        *,
        failure: Exception | None = None,
        model_alias: str = "configured-selector",
        input_tokens: int | None = 31,
        output_tokens: int | None = 12,
    ):
        self.selection = selection or _selection("refuse")
        self.failure = failure
        self.model_alias = model_alias
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.preflights: list[router.ModelTier] = []
        self.calls: list[tuple[str, router.ModelTier, int]] = []

    def preflight(self, tier: router.ModelTier) -> None:
        self.preflights.append(tier)

    def plan(
        self,
        question: str,
        tier: router.ModelTier,
        max_output_tokens: int,
    ) -> router.PlannerResult:
        self.calls.append((question, tier, max_output_tokens))
        if self.failure is not None:
            raise self.failure
        return router.PlannerResult(
            self.selection,
            model_alias=self.model_alias,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
        )


class FakeBudget:
    def __init__(self) -> None:
        self.reservations: list[router.ModelTier] = []

    def reserve(self, tier: router.ModelTier) -> None:
        self.reservations.append(tier)


@pytest.mark.parametrize(
    ("question", "refusal_code"),
    [
        ("What is the latest headline?", None),
        ("Tell me the shipping reading", None),
        ("Will shipping rise tomorrow?", "forecast_or_advice"),
        ("Should I hedge oil?", "forecast_or_advice"),
    ],
)
def test_registered_or_forbidden_questions_never_call_a_model(
    question: str,
    refusal_code: str | None,
) -> None:
    planner = FakePlanner(_selection("latest_headline"))
    budget = FakeBudget()
    routed = router.route_question(question, planner=planner, budget=budget)

    assert planner.calls == []
    assert planner.preflights == []
    assert budget.reservations == []
    assert routed.route.path == "deterministic"
    assert routed.route.model_calls == 0
    assert routed.answer.refusal_code == refusal_code


def test_models_are_disabled_by_default() -> None:
    routed = router.route_question("Give me the figure")

    assert routed.answer.status == "refused"
    assert routed.answer.refusal_code == "unsupported_question"
    assert routed.route.path == "refusal"
    assert routed.route.reason == "models_disabled"
    assert routed.route.model_calls == 0


def test_fast_selector_can_only_choose_a_registered_headline_plan() -> None:
    planner = FakePlanner(_selection("latest_headline"))
    budget = FakeBudget()
    routed = router.route_question("Give me the figure", planner=planner, budget=budget)

    assert budget.reservations == [router.ModelTier.FAST]
    assert planner.preflights == [router.ModelTier.FAST]
    assert planner.calls == [(
        "Give me the figure",
        router.ModelTier.FAST,
        router.MAX_OUTPUT_TOKENS[router.ModelTier.FAST],
    )]
    assert routed.answer.status == "answered"
    assert routed.answer.template_id == "latest_headline"
    assert routed.route.path == "model_selector"
    assert routed.route.reason == "selection_verified"
    assert routed.route.model_calls == 1
    assert routed.route.input_tokens == 31
    assert routed.route.output_tokens == 12


def test_balanced_selector_can_resolve_two_explicitly_named_channels() -> None:
    question = "Put Pakistan and shipping side by side"
    planner = FakePlanner(_selection("compare_channels", ["pakistan_west", "shipping"]))
    budget = FakeBudget()
    routed = router.route_question(question, planner=planner, budget=budget)
    payload = json.loads(
        (ROOT / "docs" / "data" / "latest.json").read_text(encoding="utf-8")
    )

    assert len(planner.calls) == 1
    assert budget.reservations == [router.ModelTier.BALANCED]
    assert planner.calls[0][1] is router.ModelTier.BALANCED
    assert routed.answer.status == "answered"
    assert routed.answer.template_id == "channel_comparison"
    assert payload["channels"]["pakistan_west"]["label"] in routed.answer.text
    assert payload["channels"]["shipping"]["label"] in routed.answer.text


@pytest.mark.parametrize(
    ("question", "selection", "reason"),
    [
        (
            "Give me the figure",
            _selection("channel_reading", ["china_east"]),
            "selection_channel_binding_invalid",
        ),
        (
            "Put Pakistan and shipping side by side",
            _selection("channel_reading", ["pakistan_west"]),
            "selection_channel_binding_invalid",
        ),
        (
            "Put Pakistan and shipping side by side",
            _selection("compare_channels", ["pakistan_west", "china_east"]),
            "selection_channel_binding_invalid",
        ),
        (
            "Give me the figure",
            {**_selection("latest_headline"), "answer": "99.9"},
            "selection_fields_invalid",
        ),
        (
            "Give me the figure",
            _selection("compare_channels", ["shipping"]),
            "selection_shape_invalid",
        ),
        (
            "Give me the figure",
            _selection("channel_reading", ["not_a_channel"]),
            "selection_channels_invalid",
        ),
        (
            "Put Pakistan and shipping side by side",
            _selection("compare_channels", ["shipping", "shipping"]),
            "selection_channels_invalid",
        ),
    ],
)
def test_model_cannot_add_drop_duplicate_or_write_facts(
    question: str,
    selection: dict[str, object],
    reason: str,
) -> None:
    planner = FakePlanner(selection)
    routed = router.route_question(question, planner=planner, budget=FakeBudget())

    assert len(planner.calls) == 1
    assert routed.answer.status == "refused"
    assert routed.answer.evidence == ()
    assert routed.route.path == "refusal"
    assert routed.route.reason == reason
    assert routed.route.model_calls == 1


def test_provider_failure_refuses_without_exposing_exception_or_question() -> None:
    marker = "SECRET-QUESTION-MARKER"
    planner = FakePlanner(failure=RuntimeError(f"provider exploded: {marker}"))
    routed = router.route_question(marker, planner=planner, budget=FakeBudget())
    serialized = json.dumps(routed.to_dict())

    assert len(planner.calls) == 1
    assert routed.answer.status == "refused"
    assert routed.route.reason == "model_provider_failure"
    assert marker not in serialized
    assert "provider exploded" not in serialized


@pytest.mark.parametrize(
    ("planner", "reason"),
    [
        (
            FakePlanner(_selection("latest_headline"), model_alias="bad alias\nsecret"),
            "model_alias_invalid",
        ),
        (
            FakePlanner(_selection("latest_headline"), input_tokens=-1),
            "model_usage_invalid",
        ),
        (
            FakePlanner(_selection("latest_headline"), output_tokens=129),
            "model_usage_invalid",
        ),
    ],
)
def test_invalid_provider_metadata_never_enters_route_trace(
    planner: FakePlanner,
    reason: str,
) -> None:
    routed = router.route_question(
        "Give me the figure",
        planner=planner,
        budget=FakeBudget(),
    )

    assert len(planner.calls) == 1
    assert routed.answer.status == "refused"
    assert routed.route.reason == reason
    assert routed.route.model_alias is None


def test_question_bounds_refuse_without_a_model_call() -> None:
    planner = FakePlanner(_selection("latest_headline"))
    budget = FakeBudget()

    empty = router.route_question("   ", planner=planner, budget=budget)
    oversized = router.route_question(
        "x" * (router.MAX_QUESTION_CHARS + 1),
        planner=planner,
        budget=budget,
    )

    assert planner.calls == []
    assert budget.reservations == []
    assert empty.route.reason == "question_bounds"
    assert oversized.route.reason == "question_bounds"


@pytest.mark.parametrize(
    ("question", "tier"),
    [
        ("Tell me something", router.ModelTier.FAST),
        ("Put Pakistan and shipping side by side", router.ModelTier.BALANCED),
        ("Explain whether this is causal evidence", router.ModelTier.DEEP),
        ("word " * 41, router.ModelTier.DEEP),
    ],
)
def test_tier_selection_changes_comprehension_effort_only(
    question: str,
    tier: router.ModelTier,
) -> None:
    assert router.choose_model_tier(question) is tier


@pytest.mark.parametrize(
    ("intent", "channels"),
    [
        ("latest_headline", []),
        ("instrument_scope", []),
        ("channel_reading", ["shipping"]),
        ("compare_channels", ["shipping", "gulf_energy"]),
        ("receipt_evidence", ["shipping"]),
        ("current_receipt_evidence", ["shipping"]),
        ("refuse", []),
    ],
)
def test_every_model_selection_compiles_to_an_exact_registered_plan(
    intent: str,
    channels: list[str],
) -> None:
    parsed = router.parse_selection(_selection(intent, channels))
    plan = router.compile_selection(parsed)

    evidence._validate_plan_shape(plan)


def test_model_selection_schema_has_no_prose_fact_or_confidence_channel() -> None:
    assert {field.name for field in fields(router.ModelSelection)} == {
        "schema_version",
        "intent",
        "channels",
    }


def test_budget_reserves_worst_case_and_rejects_before_the_next_call(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "private" / "budget.json"
    budget = router.DailyBudget(
        ledger,
        call_cap=1,
        output_token_cap=router.MAX_OUTPUT_TOKENS[router.ModelTier.FAST],
    )
    budget.reserve(router.ModelTier.FAST)

    state = json.loads(ledger.read_text(encoding="utf-8"))
    assert state["model_calls"] == 1
    assert state["reserved_output_tokens"] == router.MAX_OUTPUT_TOKENS[router.ModelTier.FAST]
    assert state["by_tier"] == {"fast": 1, "balanced": 0, "deep": 0}
    assert set(state) == {
        "date_utc",
        "model_calls",
        "reserved_output_tokens",
        "by_tier",
    }
    with pytest.raises(router.RouterError, match="daily_model_budget_exhausted"):
        budget.reserve(router.ModelTier.FAST)


def test_budget_exhaustion_occurs_before_provider_call(tmp_path: Path) -> None:
    planner = FakePlanner(_selection("latest_headline"))
    budget = router.DailyBudget(tmp_path / "budget.json", call_cap=0)
    routed = router.route_question("Give me the figure", planner=planner, budget=budget)

    assert planner.calls == []
    assert routed.route.reason == "daily_model_budget_exhausted"
    assert routed.route.model_calls == 0


def test_model_planner_without_budget_is_rejected_before_call() -> None:
    planner = FakePlanner(_selection("latest_headline"))
    routed = router.route_question("Give me the figure", planner=planner)

    assert planner.calls == []
    assert routed.answer.status == "refused"
    assert routed.route.reason == "model_budget_missing"
    assert routed.route.model_calls == 0


@pytest.mark.parametrize(
    "bad_state",
    [
        "not-json",
        json.dumps({"date_utc": "2000-01-01"}),
        json.dumps({
            "date_utc": "2999-01-01",
            "model_calls": 0,
            "reserved_output_tokens": 0,
            "by_tier": {"fast": 0, "balanced": 0, "deep": 0},
        }),
        json.dumps({
            "date_utc": "2026-08-08",
            "model_calls": 3,
            "reserved_output_tokens": 0,
            "by_tier": {"fast": 0, "balanced": 0, "deep": 0},
        }),
        json.dumps({
            "date_utc": "2026-08-08",
            "model_calls": -1,
            "reserved_output_tokens": -128,
            "by_tier": {"fast": -1, "balanced": 0, "deep": 0},
        }),
    ],
)
def test_budget_ledger_corruption_fails_closed(tmp_path: Path, bad_state: str) -> None:
    ledger = tmp_path / "budget.json"
    ledger.write_text(bad_state, encoding="utf-8")

    with pytest.raises(router.RouterError, match="budget_ledger_invalid"):
        router.DailyBudget(ledger).reserve(router.ModelTier.FAST)


def test_valid_prior_day_ledger_resets_without_carrying_question_data(
    tmp_path: Path,
) -> None:
    ledger = tmp_path / "budget.json"
    ledger.write_text(
        json.dumps({
            "date_utc": "2000-01-01",
            "model_calls": 1,
            "reserved_output_tokens": router.MAX_OUTPUT_TOKENS[router.ModelTier.DEEP],
            "by_tier": {"fast": 0, "balanced": 0, "deep": 1},
        }),
        encoding="utf-8",
    )

    router.DailyBudget(ledger).reserve(router.ModelTier.BALANCED)
    state = json.loads(ledger.read_text(encoding="utf-8"))

    assert state["model_calls"] == 1
    assert state["reserved_output_tokens"] == router.MAX_OUTPUT_TOKENS[router.ModelTier.BALANCED]
    assert state["by_tier"] == {"fast": 0, "balanced": 1, "deep": 0}
    assert "question" not in json.dumps(state).lower()


def test_anthropic_adapter_kill_switch_closes_before_provider_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(router.MODELS_ENABLED_ENV, raising=False)
    real_import = builtins.__import__

    def guarded_import(name: str, *args, **kwargs):
        if name == "anthropic":
            raise AssertionError("closed model route imported the provider")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    with pytest.raises(router.RouterError, match="model_kill_switch_closed"):
        router.AnthropicPlanner().preflight(router.ModelTier.FAST)


def test_closed_anthropic_route_does_not_reserve_or_report_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(router.MODELS_ENABLED_ENV, raising=False)
    budget = FakeBudget()
    routed = router.route_question(
        "Give me the figure",
        planner=router.AnthropicPlanner(),
        budget=budget,
    )

    assert budget.reservations == []
    assert routed.route.reason == "model_kill_switch_closed"
    assert routed.route.model_calls == 0


def test_invalid_configured_model_id_fails_before_budget_or_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(router.MODELS_ENABLED_ENV, "1")
    monkeypatch.setenv(router.MODEL_ENV[router.ModelTier.FAST.value], "bad id\nsecret")
    budget = FakeBudget()
    routed = router.route_question(
        "Give me the figure",
        planner=router.AnthropicPlanner(),
        budget=budget,
    )

    assert budget.reservations == []
    assert routed.route.reason == "model_alias_invalid"
    assert routed.route.model_calls == 0


def test_anthropic_adapter_sends_only_question_and_selector_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    response = SimpleNamespace(
        content=[SimpleNamespace(
            type="text",
            text=json.dumps(_selection("compare_channels", ["pakistan_west", "shipping"])),
        )],
        usage=SimpleNamespace(input_tokens=44, output_tokens=17),
    )

    class FakeMessages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return response

    class FakeAnthropic:
        def __init__(self) -> None:
            self.messages = FakeMessages()

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=FakeAnthropic),
    )
    monkeypatch.setenv(router.MODELS_ENABLED_ENV, "1")
    monkeypatch.setenv(router.MODEL_ENV[router.ModelTier.BALANCED.value], "claude-test")
    question = "Put Pakistan and shipping side by side"

    result = router.AnthropicPlanner().plan(
        question,
        router.ModelTier.BALANCED,
        router.MAX_OUTPUT_TOKENS[router.ModelTier.BALANCED],
    )

    assert result.selection == _selection(
        "compare_channels", ["pakistan_west", "shipping"]
    )
    assert result.model_alias == "claude-test"
    assert result.input_tokens == 44
    assert result.output_tokens == 17
    assert calls == [{
        "model": "claude-test",
        "max_tokens": router.MAX_OUTPUT_TOKENS[router.ModelTier.BALANCED],
        "temperature": 0,
        "system": router.AnthropicPlanner.SYSTEM,
        "messages": [{"role": "user", "content": question}],
    }]
    serialized_request = json.dumps(calls)
    assert "docs/data" not in serialized_request
    assert "source_sha256" not in serialized_request
    assert "composite7" not in serialized_request


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ([], "model_selection_not_single_text"),
        (
            [
                SimpleNamespace(type="text", text="{}"),
                SimpleNamespace(type="text", text="{}"),
            ],
            "model_selection_not_single_text",
        ),
        ([SimpleNamespace(type="text", text="not-json")], "model_selection_not_json"),
        ([SimpleNamespace(type="text", text="[]")], "model_selection_not_object"),
    ],
)
def test_anthropic_adapter_rejects_non_single_object_channels(
    monkeypatch: pytest.MonkeyPatch,
    content: list[SimpleNamespace],
    reason: str,
) -> None:
    response = SimpleNamespace(content=content, usage=None)

    class FakeMessages:
        def create(self, **_kwargs):
            return response

    class FakeAnthropic:
        def __init__(self) -> None:
            self.messages = FakeMessages()

    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=FakeAnthropic),
    )
    monkeypatch.setenv(router.MODELS_ENABLED_ENV, "1")
    monkeypatch.setenv(router.MODEL_ENV[router.ModelTier.FAST.value], "claude-test")

    with pytest.raises(router.RouterError, match=reason):
        router.AnthropicPlanner().plan("question", router.ModelTier.FAST, 128)


def test_answer_plan_refactor_preserves_public_answer() -> None:
    question = "Compare China versus shipping"
    plan = evidence.plan_question(question)

    assert evidence.answer_plan(plan) == evidence.answer_question(question)


def test_private_budget_path_and_router_remain_unpublished() -> None:
    assert "data/private/" in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    public_wiring = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "docs" / "app.js", ROOT / "docs" / "index.html"]
    )
    assert "assistant_router" not in public_wiring
