"""Adversarial tests for the sealed NVIDIA review boundary."""
from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from src import nvidia_model_lab as lab

ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, document: object, *, status: int = 200, content_type: str = "application/json"):
        self.raw = json.dumps(document).encode()
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read(self, limit: int) -> bytes:
        return self.raw[:limit]


def _finding(priority: str = "P1") -> dict[str, str]:
    return {
        "priority": priority,
        "title": "Missing refusal test",
        "evidence": "The patch adds a network boundary without a timeout test.",
        "recommendation": "Add a deterministic timeout refusal test.",
    }


def _review_document() -> dict[str, object]:
    return {
        "verdict": "changes_required",
        "confidence": "high",
        "findings": [_finding()],
        "limitations": ["Static review only."],
    }


def _completion(content: object | None = None) -> dict[str, object]:
    return {
        "id": "chatcmpl-safe-id",
        "choices": [{"message": {"role": "assistant", "content": json.dumps(content or _review_document())}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32},
    }


def test_registry_is_deny_by_default_and_contains_no_secret() -> None:
    registry = lab.load_registry()
    raw = lab.REGISTRY_PATH.read_text(encoding="utf-8")

    assert registry["default_policy"] == "deny"
    assert all(model["status"] == "candidate_unbenchmarked" for model in registry["models"])
    assert "nvapi-" not in raw
    assert registry["authority_boundary"] and not any(registry["authority_boundary"].values())


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (("provider", "base_url", "https://attacker.example"), "registry_endpoint_invalid"),
        (("provider", "chat_path", "/v1/completions"), "registry_provider_invalid"),
        (("limits", "temperature", 0.7), "registry_limits_invalid"),
        (("limits", "max_findings", 400), "registry_limits_invalid"),
        (("authority_boundary", "publish", True), "registry_authority_invalid"),
    ],
)
def test_registry_mutation_fails_closed(
    tmp_path: Path, mutation: tuple[str, str, object], code: str
) -> None:
    registry = json.loads(lab.REGISTRY_PATH.read_text(encoding="utf-8"))
    section, field, value = mutation
    registry[section][field] = value
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    with pytest.raises(lab.ModelLabError, match=code):
        lab.load_registry(path)


def test_keychain_loader_uses_argument_vector_and_never_environment_or_shell() -> None:
    seen: dict[str, Any] = {}

    def runner(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="sealed-secret\n", stderr="")

    assert lab._keychain_secret("igrm-nvidia-api", account="ishan", runner=runner) == "sealed-secret"
    assert seen["args"] == [
        "security",
        "find-generic-password",
        "-a",
        "ishan",
        "-s",
        "igrm-nvidia-api",
        "-w",
    ]
    assert seen["kwargs"] == {"capture_output": True, "text": True, "check": False}


@pytest.mark.parametrize(
    ("result", "code"),
    [
        (subprocess.CompletedProcess([], 44, stdout="", stderr="secret details"), "credential_missing"),
        (subprocess.CompletedProcess([], 0, stdout="\n", stderr=""), "credential_invalid"),
        (subprocess.CompletedProcess([], 0, stdout="one\ntwo", stderr=""), "credential_invalid"),
    ],
)
def test_keychain_failures_collapse_to_non_sensitive_codes(
    result: subprocess.CompletedProcess[str], code: str
) -> None:
    with pytest.raises(lab.ModelLabError, match=code) as exc:
        lab._keychain_secret("igrm-nvidia-api", runner=lambda *args, **kwargs: result)
    assert "secret details" not in str(exc.value)


def test_input_secret_and_prohibited_paths_refuse_before_key_access(tmp_path: Path) -> None:
    secret_file = tmp_path / "candidate.diff"
    secret_file.write_text("+ NVIDIA_API_KEY=nvapi-abcdefghijklmnop\n", encoding="utf-8")
    calls = 0

    def key_loader(service: str) -> str:
        nonlocal calls
        calls += 1
        return "never"

    with pytest.raises(lab.ModelLabError, match="input_secret_detected"):
        lab.review(
            secret_file,
            model_id="poolside/laguna-xs-2.1",
            task="code_review",
            key_loader=key_loader,
        )
    prohibited = tmp_path / ".env"
    prohibited.write_text("ordinary text", encoding="utf-8")
    with pytest.raises(lab.ModelLabError, match="input_path_prohibited"):
        lab.review(
            prohibited,
            model_id="poolside/laguna-xs-2.1",
            task="code_review",
            key_loader=key_loader,
        )
    assert calls == 0


def test_unregistered_model_or_role_refuses_before_key_access(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.diff"
    candidate.write_text("+ safe change\n", encoding="utf-8")
    calls = 0

    def key_loader(service: str) -> str:
        nonlocal calls
        calls += 1
        return "never"

    with pytest.raises(lab.ModelLabError, match="model_not_registered"):
        lab.review(candidate, model_id="vendor/unknown", task="code_review", key_loader=key_loader)
    with pytest.raises(lab.ModelLabError, match="model_role_not_authorized"):
        lab.review(
            candidate,
            model_id="nvidia/riva-translate-4b-instruct-v2",
            task="code_review",
            key_loader=key_loader,
        )
    assert calls == 0


def test_catalog_reports_only_ids_and_candidate_availability() -> None:
    captured: dict[str, object] = {}

    def open_request(request: urllib.request.Request, **kwargs: object) -> FakeResponse:
        captured["request"] = request
        captured["kwargs"] = kwargs
        return FakeResponse(
            {
                "object": "list",
                "data": [
                    {"id": "poolside/laguna-xs-2.1"},
                    {"id": "provider/unregistered-model"},
                ],
            }
        )

    result = lab.list_models(key_loader=lambda service: "sealed-secret", open_request=open_request)
    request = captured["request"]
    assert isinstance(request, urllib.request.Request)
    assert request.full_url == "https://integrate.api.nvidia.com/v1/models"
    assert request.get_header("Authorization") == "Bearer sealed-secret"
    assert result["provider_model_count"] == 2
    assert result["authority"].startswith("discovery_only")
    assert "sealed-secret" not in json.dumps(result)


def test_valid_review_is_schema_checked_and_carries_no_provider_prose_or_key(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.diff"
    candidate.write_text("+ safe change\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def open_request(request: urllib.request.Request, **kwargs: object) -> FakeResponse:
        captured["body"] = json.loads(request.data or b"{}")
        captured["authorization"] = request.get_header("Authorization")
        return FakeResponse(_completion())

    result = lab.review(
        candidate,
        model_id="poolside/laguna-xs-2.1",
        task="code_review",
        key_loader=lambda service: "sealed-secret",
        open_request=open_request,
    )

    assert result["status"] == "untrusted_review_validated"
    assert result["verdict"] == "changes_required"
    assert result["blocking_findings"] is True
    assert result["usage"] == {"prompt_tokens": 12, "completion_tokens": 20, "total_tokens": 32}
    assert result["authority"].startswith("advisory_only")
    assert "sealed-secret" not in json.dumps(result)
    assert captured["authorization"] == "Bearer sealed-secret"
    assert captured["body"]["stream"] is False
    assert captured["body"]["temperature"] == 0


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        ({**_review_document(), "answer": "ship it"}, "review_fields_invalid"),
        ({**_review_document(), "verdict": "perfect"}, "review_enum_invalid"),
        ({**_review_document(), "findings": [{"priority": "P0"}]}, "review_finding_invalid"),
    ],
)
def test_model_cannot_expand_the_review_channel(
    tmp_path: Path, candidate: dict[str, object], code: str
) -> None:
    input_file = tmp_path / "candidate.diff"
    input_file.write_text("+ safe change\n", encoding="utf-8")

    with pytest.raises(lab.ModelLabError, match=code):
        lab.review(
            input_file,
            model_id="poolside/laguna-xs-2.1",
            task="code_review",
            key_loader=lambda service: "sealed-secret",
            open_request=lambda *args, **kwargs: FakeResponse(_completion(candidate)),
        )


@pytest.mark.parametrize(
    "candidate",
    [
        {**_review_document(), "verdict": "clear"},
        {
            **_review_document(),
            "verdict": "clear",
            "findings": [_finding("P2")],
        },
        {
            **_review_document(),
            "verdict": "clear",
            "findings": [_finding("P3")],
        },
        {**_review_document(), "findings": []},
        {**_review_document(), "verdict": "refuse"},
        {
            **_review_document(),
            "verdict": "refuse",
            "findings": [],
            "limitations": [],
        },
    ],
)
def test_review_verdict_cannot_contradict_its_findings(
    tmp_path: Path, candidate: dict[str, object]
) -> None:
    input_file = tmp_path / "candidate.diff"
    input_file.write_text("+ safe change\n", encoding="utf-8")

    with pytest.raises(
        lab.ModelLabError, match="review_verdict_findings_inconsistent"
    ):
        lab.review(
            input_file,
            model_id="poolside/laguna-xs-2.1",
            task="code_review",
            key_loader=lambda service: "sealed-secret",
            open_request=lambda *args, **kwargs: FakeResponse(_completion(candidate)),
        )


def test_nonblocking_findings_are_reported_without_a_blocking_headline(
    tmp_path: Path,
) -> None:
    input_file = tmp_path / "candidate.diff"
    input_file.write_text("+ safe change\n", encoding="utf-8")
    candidate = _review_document()
    candidate["findings"] = [_finding("P2")]

    result = lab.review(
        input_file,
        model_id="poolside/laguna-xs-2.1",
        task="code_review",
        key_loader=lambda service: "sealed-secret",
        open_request=lambda *args, **kwargs: FakeResponse(_completion(candidate)),
    )
    assert result["verdict"] == "changes_required"
    assert result["blocking_findings"] is False


def test_clear_and_refused_reviews_have_no_findings(tmp_path: Path) -> None:
    input_file = tmp_path / "candidate.diff"
    input_file.write_text("+ safe change\n", encoding="utf-8")
    candidates = [
        {**_review_document(), "verdict": "clear", "findings": []},
        {
            **_review_document(),
            "verdict": "refuse",
            "findings": [],
            "limitations": ["Input was insufficient to complete the review."],
        },
    ]
    results = [
        lab.review(
            input_file,
            model_id="poolside/laguna-xs-2.1",
            task="code_review",
            key_loader=lambda service: "sealed-secret",
            open_request=lambda *args, value=value, **kwargs: FakeResponse(
                _completion(value)
            ),
        )
        for value in candidates
    ]
    assert [result["verdict"] for result in results] == ["clear", "refuse"]
    assert all(result["blocking_findings"] is False for result in results)


def test_redirects_are_refused_before_authorization_can_move_hosts() -> None:
    handler = lab._NoRedirect()
    request = urllib.request.Request("https://integrate.api.nvidia.com/v1/models")
    with pytest.raises(lab.ModelLabError, match="provider_redirect_refused"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://attacker.example/steal",
        )


def test_provider_http_error_exposes_status_but_not_body_or_key() -> None:
    registry = lab.load_registry()
    error = urllib.error.HTTPError(
        "https://integrate.api.nvidia.com/v1/models",
        403,
        "Forbidden sealed-secret",
        {},
        BytesIO(b"provider body contains sealed-secret"),
    )

    with pytest.raises(lab.ModelLabError, match="provider_http_403") as exc:
        lab._request_json(
            registry,
            registry["provider"]["models_path"],
            "sealed-secret",
            open_request=lambda *args, **kwargs: (_ for _ in ()).throw(error),
        )
    assert "sealed-secret" not in str(exc.value)
    assert "Forbidden" not in str(exc.value)


def test_public_assistant_and_publishers_do_not_invoke_the_model_lab() -> None:
    forbidden = "nvidia_model_lab"
    assert forbidden not in (ROOT / "src" / "assistant_router.py").read_text(encoding="utf-8")
    assert all(
        forbidden not in path.read_text(encoding="utf-8")
        for path in (ROOT / ".github" / "workflows").glob("*.yml")
    )
