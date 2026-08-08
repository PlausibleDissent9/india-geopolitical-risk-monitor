"""Read-only, fail-closed NVIDIA model evaluation plane for IGRM.

This module is deliberately not an autonomous coding agent.  A registered
candidate model may review a bounded, secret-scanned text artifact and return
one strict JSON assessment.  It receives no tools, repository credentials,
write path, commit authority, publication authority or calibration labels.

The NVIDIA key is read from macOS Keychain only at the network boundary.  It is
never accepted as a CLI argument, environment variable, registry value or log
field.  Provider output remains untrusted until the local schema validator
accepts it.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "governance" / "nvidia_model_lab.json"

_ROOT_FIELDS = {
    "schema_version",
    "effective",
    "status",
    "default_policy",
    "provider",
    "credential",
    "limits",
    "models",
    "authority_boundary",
    "forbidden_inputs",
}
_PROVIDER_FIELDS = {"name", "base_url", "models_path", "chat_path", "official_reference"}
_LIMIT_FIELDS = {
    "input_bytes",
    "response_bytes",
    "timeout_seconds",
    "temperature",
    "max_findings",
}
_AUTHORITY_FIELDS = {
    "repository_write",
    "commit",
    "publish",
    "label_or_adjudicate",
    "final_claim_authority",
    "review_output_is_evidence",
}
_TASKS = {"code_review", "claim_review", "method_review", "multilingual_review"}
_PRIORITIES = {"P0", "P1", "P2", "P3"}
_VERDICTS = {"clear", "changes_required", "refuse"}
_CONFIDENCE = {"low", "medium", "high"}
_PROHIBITED_PATH_PARTS = {
    ".git",
    ".env",
    "data/raw",
    "rights_decisions",
    "private_keys",
    "coder_labels",
}
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bnvapi-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh(?:p|o|s|u)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
)


class ModelLabError(ValueError):
    """Stable, non-sensitive refusal raised by the local trust boundary."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Message,
        newurl: str,
    ) -> None:
        raise ModelLabError("provider_redirect_refused")


def _json_object(path: Path, code: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ModelLabError(code) from exc
    if not isinstance(document, dict):
        raise ModelLabError(code)
    return document


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = _json_object(path, "registry_unreadable")
    if set(registry) != _ROOT_FIELDS:
        raise ModelLabError("registry_fields_invalid")
    if (
        registry.get("schema_version") != "1.0.0"
        or registry.get("default_policy") != "deny"
        or registry.get("status") != "candidate_review_fleet_only"
        or not isinstance(registry.get("effective"), str)
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", registry["effective"])
    ):
        raise ModelLabError("registry_policy_invalid")

    provider = registry.get("provider")
    credential = registry.get("credential")
    limits = registry.get("limits")
    models = registry.get("models")
    authority = registry.get("authority_boundary")
    if not isinstance(provider, dict):
        raise ModelLabError("registry_shape_invalid")
    if not isinstance(credential, dict):
        raise ModelLabError("registry_shape_invalid")
    if not isinstance(limits, dict):
        raise ModelLabError("registry_shape_invalid")
    if not isinstance(authority, dict):
        raise ModelLabError("registry_shape_invalid")
    if not isinstance(models, list) or not models:
        raise ModelLabError("registry_models_invalid")
    forbidden_inputs = registry.get("forbidden_inputs")
    if (
        not isinstance(forbidden_inputs, list)
        or not forbidden_inputs
        or len(forbidden_inputs) != len(set(forbidden_inputs))
        or any(not isinstance(item, str) or not item.strip() for item in forbidden_inputs)
    ):
        raise ModelLabError("registry_forbidden_inputs_invalid")

    if set(provider) != _PROVIDER_FIELDS:
        raise ModelLabError("registry_provider_invalid")

    base_url = provider.get("base_url")
    parsed = urllib.parse.urlsplit(base_url if isinstance(base_url, str) else "")
    if (
        parsed.scheme != "https"
        or parsed.hostname != "integrate.api.nvidia.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ModelLabError("registry_endpoint_invalid")
    if (
        provider.get("models_path") != "/v1/models"
        or provider.get("chat_path") != "/v1/chat/completions"
        or provider.get("official_reference")
        != "https://docs.api.nvidia.com/nim/reference/llm-apis"
    ):
        raise ModelLabError("registry_provider_invalid")
    if credential != {
        "storage": "macos_keychain",
        "service": "igrm-nvidia-api",
        "account_source": "local_os_user",
        "environment_fallback": False,
    }:
        raise ModelLabError("registry_credential_policy_invalid")
    if set(authority) != _AUTHORITY_FIELDS or any(
        authority.get(key) is not False for key in _AUTHORITY_FIELDS
    ):
        raise ModelLabError("registry_authority_invalid")
    if set(limits) != _LIMIT_FIELDS:
        raise ModelLabError("registry_limits_invalid")
    input_bytes = limits.get("input_bytes")
    response_bytes = limits.get("response_bytes")
    timeout_seconds = limits.get("timeout_seconds")
    temperature = limits.get("temperature")
    max_findings = limits.get("max_findings")
    if (
        isinstance(input_bytes, bool)
        or not isinstance(input_bytes, int)
        or not 1 <= input_bytes <= 250_000
        or isinstance(response_bytes, bool)
        or not isinstance(response_bytes, int)
        or not 1024 <= response_bytes <= 2_000_000
        or isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 120
        or temperature != 0
        or isinstance(max_findings, bool)
        or not isinstance(max_findings, int)
        or not 1 <= max_findings <= 40
    ):
        raise ModelLabError("registry_limits_invalid")

    seen: set[str] = set()
    for model in models:
        if not isinstance(model, dict) or set(model) != {
            "model_id",
            "status",
            "roles",
            "max_output_tokens",
        }:
            raise ModelLabError("registry_models_invalid")
        model_id = model.get("model_id")
        roles = model.get("roles")
        tokens = model.get("max_output_tokens")
        if (
            not isinstance(model_id, str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", model_id)
            or model_id in seen
            or model.get("status") != "candidate_unbenchmarked"
            or not isinstance(roles, list)
            or not roles
            or any(role not in _TASKS for role in roles)
            or len(roles) != len(set(roles))
            or isinstance(tokens, bool)
            or not isinstance(tokens, int)
            or not 256 <= tokens <= 2000
        ):
            raise ModelLabError("registry_models_invalid")
        seen.add(model_id)
    return registry


def _keychain_secret(
    service: str,
    *,
    account: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    args = [
        "security",
        "find-generic-password",
        "-a",
        account or getpass.getuser(),
        "-s",
        service,
        "-w",
    ]
    try:
        result = runner(args, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ModelLabError("keychain_unavailable") from exc
    if result.returncode != 0:
        raise ModelLabError("credential_missing")
    secret = result.stdout.strip()
    if not secret or "\n" in secret or "\r" in secret or len(secret) > 500:
        raise ModelLabError("credential_invalid")
    return secret


def _model_contract(registry: Mapping[str, Any], model_id: str, task: str) -> dict[str, Any]:
    if task not in _TASKS:
        raise ModelLabError("task_not_registered")
    for candidate in registry["models"]:
        if candidate["model_id"] == model_id:
            if task not in candidate["roles"]:
                raise ModelLabError("model_role_not_authorized")
            return candidate
    raise ModelLabError("model_not_registered")


def _safe_input(path: Path, registry: Mapping[str, Any]) -> tuple[str, str]:
    resolved = path.resolve()
    normalized = resolved.as_posix().lower()
    if any(part in normalized for part in _PROHIBITED_PATH_PARTS):
        raise ModelLabError("input_path_prohibited")
    if not resolved.is_file():
        raise ModelLabError("input_unreadable")
    limit = registry["limits"]["input_bytes"]
    try:
        raw = resolved.read_bytes()
    except OSError as exc:
        raise ModelLabError("input_unreadable") from exc
    if not raw or len(raw) > limit or b"\x00" in raw:
        raise ModelLabError("input_size_invalid")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ModelLabError("input_encoding_invalid") from exc
    if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
        raise ModelLabError("input_secret_detected")
    return text, hashlib.sha256(raw).hexdigest()


def _prompt(task: str, text: str) -> list[dict[str, str]]:
    system = (
        "You are one read-only adversarial reviewer inside the IGRM model lab. "
        "You have no tools and no authority to edit, commit, publish, label data, "
        "adjudicate evidence or approve a claim. Inspect only the supplied text. "
        "Return exactly one JSON object with keys verdict, confidence, findings, "
        "limitations. verdict is clear, changes_required, or refuse. confidence is "
        "low, medium, or high. findings is an array of at most 40 objects with exact "
        "keys priority, title, evidence, recommendation; priority is P0, P1, P2, or "
        "P3. limitations is an array of short strings. Do not wrap JSON in markdown."
    )
    user = f"Task: {task}\n\nArtifact begins:\n{text}\nArtifact ends."
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _request_json(
    registry: Mapping[str, Any],
    path: str,
    key: str,
    *,
    payload: Mapping[str, Any] | None = None,
    open_request: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    provider = registry["provider"]
    base_url = provider["base_url"].rstrip("/")
    url = f"{base_url}{path}"
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "integrate.api.nvidia.com":
        raise ModelLabError("provider_url_invalid")
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="GET" if payload is None else "POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": "IGRM-NVIDIA-Model-Lab/1.0",
        },
    )
    timeout = registry["limits"]["timeout_seconds"]
    response_limit = registry["limits"]["response_bytes"]
    if open_request is None:
        open_request = urllib.request.build_opener(_NoRedirect()).open
    try:
        with open_request(request, timeout=timeout) as response:
            status = response.getcode()
            content_type = response.headers.get("Content-Type", "")
            raw = response.read(response_limit + 1)
    except ModelLabError:
        raise
    except urllib.error.HTTPError as exc:
        status_code = exc.code if isinstance(exc.code, int) and 400 <= exc.code <= 599 else None
        code = f"provider_http_{status_code}" if status_code is not None else "provider_request_failed"
        raise ModelLabError(code) from exc
    except (OSError, urllib.error.URLError) as exc:
        raise ModelLabError("provider_request_failed") from exc
    if status != 200:
        raise ModelLabError("provider_status_invalid")
    if "application/json" not in content_type.lower():
        raise ModelLabError("provider_content_type_invalid")
    if len(raw) > response_limit:
        raise ModelLabError("provider_response_too_large")
    try:
        document = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ModelLabError("provider_json_invalid") from exc
    if not isinstance(document, dict):
        raise ModelLabError("provider_json_invalid")
    return document


def list_models(
    *,
    registry_path: Path = REGISTRY_PATH,
    key_loader: Callable[[str], str] | None = None,
    open_request: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    key = (key_loader or _keychain_secret)(registry["credential"]["service"])
    document = _request_json(
        registry,
        registry["provider"]["models_path"],
        key,
        open_request=open_request,
    )
    rows = document.get("data")
    if not isinstance(rows, list):
        raise ModelLabError("provider_model_catalog_invalid")
    available: set[str] = set()
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            available.add(row["id"])
        else:
            raise ModelLabError("provider_model_catalog_invalid")
    registered = [row["model_id"] for row in registry["models"]]
    return {
        "schema_version": "1.0.0",
        "status": "catalog_checked",
        "provider_model_count": len(available),
        "registered_candidates": [
            {"model_id": model_id, "available": model_id in available}
            for model_id in registered
        ],
        "authority": "discovery_only_no_write_commit_publish_or_claim_authority",
    }


def _validated_review(document: Mapping[str, Any], max_findings: int) -> dict[str, Any]:
    if set(document) != {"verdict", "confidence", "findings", "limitations"}:
        raise ModelLabError("review_fields_invalid")
    verdict = document.get("verdict")
    confidence = document.get("confidence")
    findings = document.get("findings")
    limitations = document.get("limitations")
    if verdict not in _VERDICTS or confidence not in _CONFIDENCE:
        raise ModelLabError("review_enum_invalid")
    if (
        not isinstance(findings, list)
        or len(findings) > max_findings
        or not isinstance(limitations, list)
        or len(limitations) > 20
        or any(not isinstance(item, str) or not 1 <= len(item) <= 500 for item in limitations)
    ):
        raise ModelLabError("review_shape_invalid")
    cleaned: list[dict[str, str]] = []
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {
            "priority",
            "title",
            "evidence",
            "recommendation",
        }:
            raise ModelLabError("review_finding_invalid")
        if finding.get("priority") not in _PRIORITIES:
            raise ModelLabError("review_finding_invalid")
        for field, ceiling in (("title", 240), ("evidence", 2000), ("recommendation", 2000)):
            value = finding.get(field)
            if not isinstance(value, str) or not 1 <= len(value) <= ceiling:
                raise ModelLabError("review_finding_invalid")
        cleaned.append({key: finding[key] for key in ("priority", "title", "evidence", "recommendation")})
    return {
        "verdict": verdict,
        "confidence": confidence,
        "findings": cleaned,
        "limitations": limitations,
    }


def review(
    input_path: Path,
    *,
    model_id: str,
    task: str,
    registry_path: Path = REGISTRY_PATH,
    key_loader: Callable[[str], str] | None = None,
    open_request: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    model = _model_contract(registry, model_id, task)
    text, input_sha = _safe_input(input_path, registry)
    key = (key_loader or _keychain_secret)(registry["credential"]["service"])
    request = {
        "model": model_id,
        "messages": _prompt(task, text),
        "temperature": registry["limits"]["temperature"],
        "max_tokens": model["max_output_tokens"],
        "stream": False,
    }
    response = _request_json(
        registry,
        registry["provider"]["chat_path"],
        key,
        payload=request,
        open_request=open_request,
    )
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ModelLabError("provider_completion_invalid")
    choice = choices[0]
    if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
        raise ModelLabError("provider_completion_invalid")
    content = choice["message"].get("content")
    if not isinstance(content, str):
        raise ModelLabError("provider_completion_invalid")
    try:
        candidate = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ModelLabError("review_json_invalid") from exc
    if not isinstance(candidate, dict):
        raise ModelLabError("review_json_invalid")
    validated = _validated_review(candidate, registry["limits"]["max_findings"])
    usage = response.get("usage")
    safe_usage: dict[str, int] | None = None
    if isinstance(usage, dict):
        selected = {}
        for key_name in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key_name)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                selected[key_name] = value
        safe_usage = selected or None
    return {
        "schema_version": "1.0.0",
        "status": "untrusted_review_validated",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "model_id": model_id,
        "task": task,
        "input_sha256": input_sha,
        "usage": safe_usage,
        **validated,
        "authority": "advisory_only_no_write_commit_publish_label_adjudication_or_claim_authority",
    }


def _emit(document: Mapping[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog", help="check which registered candidates are currently available")
    review_parser = sub.add_parser("review", help="run one bounded read-only review")
    review_parser.add_argument("--input", required=True, type=Path)
    review_parser.add_argument("--model", required=True)
    review_parser.add_argument("--task", required=True, choices=sorted(_TASKS))
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            _emit(list_models())
        else:
            _emit(review(args.input, model_id=args.model, task=args.task))
    except ModelLabError as exc:
        _emit({"schema_version": "1.0.0", "status": "refused", "code": exc.code}, stream=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
