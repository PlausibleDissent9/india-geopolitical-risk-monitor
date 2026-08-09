"""Closed OGES execution/proof profile for registered IGRM queries.

Version 0.1.0 proves exact registered execution only.  It does not compute a
geopolitical consequence or grant rights, truth, completeness, causal,
forecast, probability, score, recommendation or publication authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker

from src import event_ledger, knowledge_replay
from src import evidence_assistant as assistant

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "standard" / "oges" / "extensions" / "consequence-plan" / "0.1.0"
PROFILE_PATH = EXTENSION / "profile.json"
PLAN_SCHEMA_PATH = EXTENSION / "consequence-plan.schema.json"
EXECUTION_SCHEMA_PATH = EXTENSION / "consequence-execution.schema.json"
OPERATOR_REGISTRY_PATH = EXTENSION / "operator-registry.json"
OUTPUT_PROFILE_REGISTRY_PATH = EXTENSION / "output-profile-registry.json"
SOURCE_REGISTRY_PATH = EXTENSION / "source-registry.json"
FACT_CATALOG_PATH = EXTENSION / "fact-catalog.json"
TYPED_FIXTURE_PATH = ROOT / "validation" / "event_ledger_canonicalization.json"
BASE_PROFILE_PATH = ROOT / "standard" / "oges" / "0.1.0" / "profile.json"

SCHEMA_VERSION = "0.1.0"
TYPED_PROFILE = "igrm-typed-canonical-f64-v1"
METHOD_ID = "method:igrm.consequence_plan"
METHOD_VERSION = "0.1.0"
ZERO_SHA = "0" * 64

_FALSE_GUARDS = {
    "model_authored_fact": False,
    "literal_fact_value": False,
    "literal_citation": False,
    "free_text_renderer": False,
    "unregistered_operator": False,
    "general_cross_source_join": False,
    "causal_attribution": False,
    "forecast": False,
    "probability": False,
    "recommendation": False,
    "scalar_score": False,
}

_REFUSAL_GRAPH = (
    ("step:refuse", "op:igrm.emit_registered_refusal", ("request:refusal",), "step:refuse:output"),
)

_OPERATOR_CONTRACTS = {
    "op:igrm.select_registered_facts": {
        "input_kind_sequences": [
            ["registered_payload", "registered_fact_reference_set"],
            [
                "registered_payload",
                "registered_payload",
                "registered_fact_reference_set",
            ],
        ],
        "output_kinds": ["integrity_verified_payload_fact_set"],
        "required_rights_uses": [],
        "time_rule": "source_effective_date_from_opened_bytes",
        "max_cardinality": 32,
    },
    "op:igrm.assert_same_effective_date": {
        "input_kind_sequences": [["integrity_verified_payload_fact_set"]],
        "output_kinds": ["same_effective_date_fact_set", "registered_refusal"],
        "required_rights_uses": [],
        "time_rule": "exact_source_effective_date_equality_or_registered_refusal",
        "max_cardinality": 32,
    },
    "op:igrm.render_registered_template": {
        "input_kind_sequences": [
            ["same_effective_date_fact_set"],
            ["registered_refusal"],
        ],
        "output_kinds": ["descriptive_registered_answer", "registered_refusal"],
        "required_rights_uses": ["publish_derived_value", "cite_metadata"],
        "time_rule": "preserve_verified_source_effective_date_or_refusal",
        "max_cardinality": 1,
    },
    "op:igrm.select_signed_replay_state": {
        "input_kind_sequences": [
            ["verified_signed_replay_ledger", "registered_replay_request"]
        ],
        "output_kinds": ["bitemporal_state_selection"],
        "required_rights_uses": [],
        "time_rule": "knowledge_cutoff_and_valid_on_remain_distinct",
        "max_cardinality": 1000,
    },
    "op:igrm.render_structural_replay": {
        "input_kind_sequences": [["bitemporal_state_selection"]],
        "output_kinds": ["structural_replay_report"],
        "required_rights_uses": [],
        "time_rule": "preserve_replay_query_and_selected_receipt_time",
        "max_cardinality": 1,
    },
    "op:igrm.emit_registered_refusal": {
        "input_kind_sequences": [["registered_refusal_code"]],
        "output_kinds": ["registered_refusal"],
        "required_rights_uses": [],
        "time_rule": "not_applicable",
        "max_cardinality": 1,
    },
}


class ConsequencePlanError(ValueError):
    """Fail-closed refusal carrying a stable machine reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ConsequencePlanError(code, detail)


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("json_duplicate_key", key)
        value[key] = item
    return value


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_object,
            parse_constant=lambda value: _fail("json_non_finite", value),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConsequencePlanError(code, str(path)) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _sha(path: Path, code: str = "artifact_unreadable") -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ConsequencePlanError(code, str(path)) from exc


def _relative_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail(code)
    candidate = root.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _relative_directory(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or value.as_posix() != relative:
        _fail(code)
    candidate = root.resolve()
    for part in value.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail(code)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_dir():
        _fail(code)
    return resolved


def _typed_digest(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise ConsequencePlanError("typed_canonical_invalid", exc.code) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(value))
    clone["integrity"]["value_sha256"] = ZERO_SHA
    digest = _typed_digest(clone)
    clone["integrity"]["value_sha256"] = digest
    return cast(dict[str, Any], clone)


def _verify_integrity(value: Mapping[str, Any], code: str) -> None:
    integrity = value.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("profile_id") != TYPED_PROFILE:
        _fail(code)
    observed = integrity.get("value_sha256")
    clone = json.loads(json.dumps(value))
    clone["integrity"]["value_sha256"] = ZERO_SHA
    if observed != _typed_digest(clone):
        _fail(code)


def serialize_plan(plan: Mapping[str, Any]) -> bytes:
    """Canonical transport bytes used by ``plan_file_sha256``."""
    return (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def load_plan(path: Path) -> dict[str, Any]:
    """Load only the canonical transport form and reject duplicate JSON keys."""
    raw, plan, _ = _read_json(path, "plan_file_invalid")
    if raw != serialize_plan(plan):
        _fail("plan_transport_noncanonical")
    validate_plan(plan)
    return plan


def _schema(path: Path, code: str) -> Draft202012Validator:
    _, value, _ = _read_json(path, code)
    try:
        Draft202012Validator.check_schema(value)
    except Exception as exc:  # jsonschema exposes several schema error subclasses
        raise ConsequencePlanError(code) from exc
    return Draft202012Validator(value, format_checker=FormatChecker())


def _schema_check(value: Mapping[str, Any], validator: Draft202012Validator, code: str) -> None:
    errors = sorted(validator.iter_errors(value), key=lambda error: list(error.absolute_path))
    if errors:
        path = "/" + "/".join(str(part) for part in errors[0].absolute_path)
        _fail(code, path)


def _contract_hashes() -> dict[str, str]:
    return {
        "base_oges_profile_sha256": _sha(BASE_PROFILE_PATH),
        "extension_profile_sha256": _sha(PROFILE_PATH),
        "plan_schema_sha256": _sha(PLAN_SCHEMA_PATH),
        "execution_schema_sha256": _sha(EXECUTION_SCHEMA_PATH),
        "operator_registry_sha256": _sha(OPERATOR_REGISTRY_PATH),
        "output_profile_registry_sha256": _sha(OUTPUT_PROFILE_REGISTRY_PATH),
        "source_registry_sha256": _sha(SOURCE_REGISTRY_PATH),
        "fact_catalog_sha256": _sha(FACT_CATALOG_PATH),
        "typed_canonical_fixture_sha256": _sha(TYPED_FIXTURE_PATH),
    }


def _validate_profile() -> None:
    _, profile, _ = _read_json(PROFILE_PATH, "extension_profile_invalid")
    if (
        profile.get("schema_version") != SCHEMA_VERSION
        or profile.get("extension_id") != "oges:extension:consequence_plan"
        or profile.get("version") != SCHEMA_VERSION
        or profile.get("status")
        != "public_draft_synthetic_reference_no_adoption_claim"
        or profile.get("production_endpoint") is not False
    ):
        _fail("extension_profile_identity_invalid")
    base = profile.get("base_standard")
    implementation = profile.get("reference_implementation")
    if (
        not isinstance(base, dict)
        or base.get("profile_sha256") != _sha(BASE_PROFILE_PATH)
        or not isinstance(implementation, dict)
        or implementation.get("path") != "src/consequence_plan.py"
        or implementation.get("sha256") != _sha(ROOT / "src/consequence_plan.py")
    ):
        _fail("extension_profile_binding_invalid")
    specification = profile.get("specification")
    if not isinstance(specification, dict):
        _fail("extension_profile_binding_invalid")
    bindings = [specification, *(profile.get("normative_files") or [])]
    if not all(isinstance(row, dict) for row in bindings):
        _fail("extension_profile_binding_invalid")
    for row in bindings:
        path = _relative_file(ROOT, row.get("path"), "extension_profile_path_invalid")
        if _sha(path) != row.get("sha256"):
            _fail("extension_profile_artifact_drift")
    pinned_source = next(
        row
        for row in cast(list[dict[str, Any]], profile["normative_files"])
        if row.get("kind") == "source_registry"
    )
    if SOURCE_REGISTRY_PATH.resolve() != _relative_file(
        ROOT, pinned_source["path"], "extension_profile_path_invalid"
    ):
        _fail("active_source_registry_unpinned")


def _fact_catalog_projection() -> dict[str, dict[str, str]]:
    return {
        fact_id: {
            "source_path": spec.source_path,
            "pointer": spec.pointer,
            "value_kind": spec.value_kind,
            "unit": spec.unit,
            "denominator": spec.denominator,
            "citation": spec.citation,
        }
        for fact_id, spec in sorted(assistant.FACT_SPECS.items())
    }


def _validate_fact_catalog() -> None:
    _, catalog, _ = _read_json(FACT_CATALOG_PATH, "fact_catalog_invalid")
    if (
        catalog.get("schema_version") != SCHEMA_VERSION
        or catalog.get("implementation_path") != "src/evidence_assistant.py"
        or catalog.get("implementation_sha256") != _sha(ROOT / "src/evidence_assistant.py")
        or catalog.get("fact_count") != len(assistant.FACT_SPECS)
        or catalog.get("canonical_fact_specs_sha256") != _typed_digest(_fact_catalog_projection())
    ):
        _fail("fact_catalog_drift")


def _registry_rows(path: Path, field: str, key: str, code: str) -> dict[str, dict[str, Any]]:
    _, document, _ = _read_json(path, code)
    rows = document.get(field)
    if (
        document.get("schema_version") != SCHEMA_VERSION
        or document.get("default_policy") != "deny"
        or not isinstance(rows, list)
    ):
        _fail(code)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or row[key] in result:
            _fail(code)
        result[row[key]] = row
    return result


def _source_rows() -> dict[str, dict[str, Any]]:
    rows = _registry_rows(
        SOURCE_REGISTRY_PATH,
        "sources",
        "source_registry_id",
        "source_registry_invalid",
    )
    for row in rows.values():
        if (
            row.get("binding_kind") not in {"registered_payload", "signed_replay_ledger"}
            or row.get("rights_state") not in {"review_required", "synthetic_fixture"}
            or row.get("permitted_uses") != []
        ):
            _fail("source_registry_v01_boundary_invalid")
    return rows


def _operator_rows() -> dict[str, dict[str, Any]]:
    _, document, _ = _read_json(OPERATOR_REGISTRY_PATH, "operator_registry_invalid")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        _fail("operator_dependency_registry_invalid")
    for row in dependencies:
        if not isinstance(row, dict):
            _fail("operator_dependency_registry_invalid")
        path = _relative_file(ROOT, row.get("path"), "operator_dependency_path_invalid")
        if _sha(path) != row.get("sha256"):
            _fail("operator_dependency_drift")
    rows = _registry_rows(
        OPERATOR_REGISTRY_PATH,
        "operators",
        "operator_id",
        "operator_registry_invalid",
    )
    if set(rows) != set(_OPERATOR_CONTRACTS):
        _fail("operator_registry_contract_invalid")
    for operator_id, expected in _OPERATOR_CONTRACTS.items():
        row = rows[operator_id]
        observed = {
            key: row.get(key)
            for key in (
                "input_kind_sequences",
                "output_kinds",
                "required_rights_uses",
                "time_rule",
                "max_cardinality",
            )
        }
        if observed != expected:
            _fail("operator_registry_contract_invalid", operator_id)
    return rows


def _output_rows() -> dict[str, dict[str, Any]]:
    rows = _registry_rows(
        OUTPUT_PROFILE_REGISTRY_PATH,
        "profiles",
        "output_profile_id",
        "output_registry_invalid",
    )
    expected_kinds = {
        "legacy_registered_answer": {
            "descriptive_registered_answer",
            "registered_refusal",
        },
        "structural_replay_report": {"structural_replay_report"},
        "registered_refusal": {"registered_refusal"},
    }
    if set(rows) != set(expected_kinds):
        _fail("output_registry_contract_invalid")
    for profile_id, kinds in expected_kinds.items():
        value = rows[profile_id].get("output_kinds")
        if not isinstance(value, list) or set(value) != kinds or len(value) != len(kinds):
            _fail("output_registry_contract_invalid", profile_id)
    return rows


def _source_for_path(source_path: str) -> dict[str, Any]:
    matches = [row for row in _source_rows().values() if row.get("path") == source_path]
    if len(matches) != 1:
        _fail("source_not_registered", source_path)
    return matches[0]


def _steps(graph: Sequence[tuple[str, str, tuple[str, ...], str]]) -> list[dict[str, Any]]:
    return [
        {
            "step_id": step_id,
            "operator_id": operator_id,
            "operator_version": "1.0.0",
            "input_refs": list(inputs),
            "output_ref": output,
        }
        for step_id, operator_id, inputs, output in graph
    ]


def _assistant_graph(bindings: Sequence[Mapping[str, Any]]) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    source_refs = tuple(cast(str, row["binding_id"]) for row in bindings)
    return (
        ("step:select", "op:igrm.select_registered_facts", (*source_refs, "request:facts"), "step:select:output"),
        ("step:time", "op:igrm.assert_same_effective_date", ("step:select:output",), "step:time:output"),
        ("step:render", "op:igrm.render_registered_template", ("step:time:output",), "step:render:output"),
    )


def _replay_graph(binding: Mapping[str, Any]) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    return (
        ("step:replay", "op:igrm.select_signed_replay_state", (cast(str, binding["binding_id"]), "request:replay"), "step:replay:output"),
        ("step:render", "op:igrm.render_structural_replay", ("step:replay:output",), "step:render:output"),
    )


def _binding(row: Mapping[str, Any], root: Path) -> dict[str, Any]:
    path = _relative_file(root, row.get("path"), "source_path_invalid")
    observed_sha = _sha(path, "source_unreadable")
    registered_sha = row.get("registered_file_sha256")
    if registered_sha is not None and registered_sha != observed_sha:
        _fail("registered_source_file_drift")
    return {
        "binding_id": f"binding:{str(row['artifact_id']).split(':', 1)[1]}",
        "binding_kind": row["binding_kind"],
        "source_registry_id": row["source_registry_id"],
        "source_registry_sha256": _sha(SOURCE_REGISTRY_PATH),
        "artifact_id": row["artifact_id"],
        "expected_file_sha256": observed_sha,
    }


def _base_plan(
    *,
    profile_id: str,
    intent_id: str,
    fact_ids: Sequence[str],
    knowledge_cutoff: str | None,
    valid_on: str | None,
    object_type: str | None,
    object_id: str | None,
    refusal_code: str | None,
    bindings: list[dict[str, Any]],
    graph: Sequence[tuple[str, str, tuple[str, ...], str]],
    output_profile_id: str,
    planner_sha: str,
    compiled_at: str,
) -> dict[str, Any]:
    identity_seed = {
        "profile_id": profile_id,
        "intent_id": intent_id,
        "fact_ids": list(fact_ids),
        "knowledge_cutoff": knowledge_cutoff,
        "valid_on": valid_on,
        "object_type": object_type,
        "object_id": object_id,
        "refusal_code": refusal_code,
        "bindings": bindings,
    }
    plan = {
        "object_type": "oges_consequence_plan",
        "schema_version": SCHEMA_VERSION,
        "plan_id": f"plan:{profile_id}:{_typed_digest(identity_seed)[:24]}",
        "integrity": {"profile_id": TYPED_PROFILE, "value_sha256": ZERO_SHA},
        "compiled_at": compiled_at,
        "profile_id": profile_id,
        "planner": {
            "kind": "compatibility_adapter",
            "planner_id": "planner:igrm.compatibility_adapter",
            "version": "0.1.0",
            "implementation_sha256": planner_sha,
            "candidate_only": False,
        },
        "request": {
            "intent_id": intent_id,
            "fact_ids": list(fact_ids),
            "knowledge_cutoff": knowledge_cutoff,
            "valid_on": valid_on,
            "object_type": object_type,
            "object_id": object_id,
            "refusal_code": refusal_code,
        },
        "source_bindings": bindings,
        "steps": _steps(graph),
        "output_profile_id": output_profile_id,
        "contract": _contract_hashes(),
        "guardrails": dict(_FALSE_GUARDS),
    }
    sealed = _seal(plan)
    validate_plan(sealed)
    return sealed


def _expected_plan_id(plan: Mapping[str, Any]) -> str:
    request = plan.get("request")
    bindings = plan.get("source_bindings")
    profile_id = plan.get("profile_id")
    if not isinstance(request, dict) or not isinstance(bindings, list):
        _fail("plan_identity_invalid")
    identity_seed = {
        "profile_id": profile_id,
        "intent_id": request.get("intent_id"),
        "fact_ids": request.get("fact_ids"),
        "knowledge_cutoff": request.get("knowledge_cutoff"),
        "valid_on": request.get("valid_on"),
        "object_type": request.get("object_type"),
        "object_id": request.get("object_id"),
        "refusal_code": request.get("refusal_code"),
        "bindings": bindings,
    }
    return f"plan:{profile_id}:{_typed_digest(identity_seed)[:24]}"


def from_legacy_assistant_plan(
    plan: assistant.Plan,
    root: Path = ROOT,
    *,
    compiled_at: str | None = None,
) -> dict[str, Any]:
    """Compile one exact existing assistant plan without a literal channel."""
    assistant._validate_plan_shape(plan)
    _validate_fact_catalog()
    timestamp = compiled_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if plan.template_id.startswith("refusal_"):
        refusals = {
            "refusal_forbidden": "forecast_or_advice",
            "refusal_unsupported": "unsupported_question",
        }
        refusal = refusals.get(plan.template_id)
        if refusal is None:
            _fail("legacy_refusal_not_plannable")
        return _base_plan(
            profile_id="registered_refusal", intent_id=plan.template_id,
            fact_ids=(), knowledge_cutoff=None, valid_on=None, object_type=None,
            object_id=None, refusal_code=refusal, bindings=[], graph=_REFUSAL_GRAPH,
            output_profile_id="registered_refusal", planner_sha=_sha(ROOT / "src/evidence_assistant.py"),
            compiled_at=timestamp,
        )
    source_paths = sorted({assistant.FACT_SPECS[fact_id].source_path for fact_id in plan.fact_ids})
    bindings = [_binding(_source_for_path(path), root) for path in source_paths]
    return _base_plan(
        profile_id="legacy_assistant_answer", intent_id=plan.template_id,
        fact_ids=plan.fact_ids, knowledge_cutoff=None, valid_on=None, object_type=None,
        object_id=None, refusal_code=None, bindings=bindings, graph=_assistant_graph(bindings),
        output_profile_id="legacy_registered_answer", planner_sha=_sha(ROOT / "src/evidence_assistant.py"),
        compiled_at=timestamp,
    )


def from_knowledge_replay(
    source_registry_id: str,
    knowledge_cutoff: str,
    valid_on: str,
    *,
    object_type: str | None = None,
    object_id: str | None = None,
    root: Path = ROOT,
    compiled_at: str | None = None,
) -> dict[str, Any]:
    """Bind an exact registered signed-replay ledger without reading values."""
    row = _source_rows().get(source_registry_id)
    if row is None or row.get("binding_kind") != "signed_replay_ledger":
        _fail("replay_source_not_registered")
    timestamp = compiled_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    binding = _binding(row, root)
    return _base_plan(
        profile_id="knowledge_replay_query", intent_id="knowledge_replay_query",
        fact_ids=(), knowledge_cutoff=knowledge_cutoff, valid_on=valid_on,
        object_type=object_type, object_id=object_id, refusal_code=None,
        bindings=[binding], graph=_replay_graph(binding),
        output_profile_id="structural_replay_report", planner_sha=_sha(ROOT / "src/knowledge_replay.py"),
        compiled_at=timestamp,
    )


def _expected_graph(
    profile_id: str, bindings: Sequence[Mapping[str, Any]]
) -> tuple[tuple[str, str, tuple[str, ...], str], ...]:
    if profile_id == "legacy_assistant_answer":
        return _assistant_graph(bindings)
    if profile_id == "knowledge_replay_query" and len(bindings) == 1:
        return _replay_graph(bindings[0])
    return _REFUSAL_GRAPH


def validate_plan(plan: Mapping[str, Any]) -> None:
    """Validate schema, contract, self-integrity and the exact closed graph."""
    _schema_check(plan, _schema(PLAN_SCHEMA_PATH, "plan_schema_invalid"), "plan_schema_refused")
    _verify_integrity(plan, "plan_integrity_mismatch")
    _validate_profile()
    if plan.get("contract") != _contract_hashes() or plan.get("guardrails") != _FALSE_GUARDS:
        _fail("plan_contract_drift")
    _validate_fact_catalog()
    profile_id = cast(str, plan["profile_id"])
    bindings = cast(list[dict[str, Any]], plan["source_bindings"])
    expected = _steps(_expected_graph(profile_id, bindings))
    if plan.get("steps") != expected:
        _fail("plan_graph_invalid")
    outputs = _output_rows()
    if plan.get("output_profile_id") not in outputs:
        _fail("output_profile_unregistered")
    operators = _operator_rows()
    for step in cast(list[dict[str, Any]], plan["steps"]):
        row = operators.get(step["operator_id"])
        if row is None or row.get("version") != step["operator_version"]:
            _fail("operator_unregistered")
        implementation = _relative_file(ROOT, row.get("implementation_path"), "operator_path_invalid")
        if _sha(implementation) != row.get("implementation_sha256"):
            _fail("operator_implementation_drift")
    planner = cast(dict[str, Any], plan["planner"])
    request = cast(dict[str, Any], plan["request"])
    if plan["plan_id"] != _expected_plan_id(plan):
        _fail("plan_identity_mismatch")
    binding_ids = [row["binding_id"] for row in bindings]
    source_ids = [row["source_registry_id"] for row in bindings]
    if len(binding_ids) != len(set(binding_ids)) or len(source_ids) != len(set(source_ids)):
        _fail("source_binding_duplicate")
    source_rows = _source_rows()
    for binding in bindings:
        row = source_rows.get(binding["source_registry_id"])
        if (
            row is None
            or binding["source_registry_sha256"] != _sha(SOURCE_REGISTRY_PATH)
            or binding["artifact_id"] != row.get("artifact_id")
            or binding["binding_kind"] != row.get("binding_kind")
        ):
            _fail("source_binding_unregistered")
        registered_sha = row.get("registered_file_sha256")
        if (
            registered_sha is not None
            and binding["expected_file_sha256"] != registered_sha
        ):
            _fail("registered_source_file_drift")
    if profile_id == "legacy_assistant_answer":
        expected_planner_sha = _sha(ROOT / "src/evidence_assistant.py")
        legacy = assistant.Plan(
            assistant.PLAN_SCHEMA_VERSION,
            request["intent_id"] if request["intent_id"] != "channel_comparison" else "compare_channels",
            request["intent_id"],
            tuple(request["fact_ids"]),
        )
        assistant._validate_plan_shape(legacy)
        if not 1 <= len(bindings) <= 2:
            _fail("assistant_binding_count_invalid")
        expected_sources = {
            _source_for_path(assistant.FACT_SPECS[fact_id].source_path)[
                "source_registry_id"
            ]
            for fact_id in request["fact_ids"]
        }
        if set(source_ids) != expected_sources:
            _fail("assistant_source_binding_mismatch")
        if any(
            request[field] is not None
            for field in (
                "knowledge_cutoff",
                "valid_on",
                "object_type",
                "object_id",
                "refusal_code",
            )
        ):
            _fail("assistant_request_fields_invalid")
    elif profile_id == "registered_refusal":
        expected_planner_sha = _sha(ROOT / "src/evidence_assistant.py")
        if bindings or request["fact_ids"] or request["refusal_code"] is None:
            _fail("registered_refusal_shape_invalid")
        expected_refusal = {
            "refusal_forbidden": "forecast_or_advice",
            "refusal_unsupported": "unsupported_question",
        }.get(request["intent_id"])
        if request["refusal_code"] != expected_refusal:
            _fail("registered_refusal_code_mismatch")
        if any(
            request[field] is not None
            for field in ("knowledge_cutoff", "valid_on", "object_type", "object_id")
        ):
            _fail("registered_refusal_request_fields_invalid")
    elif len(bindings) != 1 or bindings[0]["binding_kind"] != "signed_replay_ledger":
        _fail("replay_binding_count_invalid")
    elif _source_rows()[source_ids[0]].get("rights_state") != "synthetic_fixture":
        _fail("replay_v01_requires_synthetic_source")
    else:
        expected_planner_sha = _sha(ROOT / "src/knowledge_replay.py")
        if (
            request["intent_id"] != "knowledge_replay_query"
            or request["fact_ids"]
            or request["refusal_code"] is not None
            or request["knowledge_cutoff"] is None
            or request["valid_on"] is None
        ):
            _fail("replay_request_fields_invalid")
    expected_output = {
        "legacy_assistant_answer": "legacy_registered_answer",
        "knowledge_replay_query": "structural_replay_report",
        "registered_refusal": "registered_refusal",
    }[profile_id]
    if plan["output_profile_id"] != expected_output:
        _fail("output_profile_mismatch")
    if planner != {
        "kind": "compatibility_adapter",
        "planner_id": "planner:igrm.compatibility_adapter",
        "version": "0.1.0",
        "implementation_sha256": expected_planner_sha,
        "candidate_only": False,
    }:
        _fail("planner_unregistered")


def _load_bound_inputs(plan: Mapping[str, Any], root: Path) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    rows = _source_rows()
    inputs: list[dict[str, Any]] = []
    captured: dict[str, bytes] = {}
    observed_as_of: set[str] = set()
    for binding in cast(list[dict[str, Any]], plan["source_bindings"]):
        if binding["source_registry_sha256"] != _sha(SOURCE_REGISTRY_PATH):
            _fail("source_registry_drift")
        row = rows.get(binding["source_registry_id"])
        if row is None or row.get("artifact_id") != binding["artifact_id"] or row.get("binding_kind") != binding["binding_kind"]:
            _fail("source_binding_unregistered")
        path = _relative_file(root, row.get("path"), "source_path_invalid")
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise ConsequencePlanError("source_unreadable", str(path)) from exc
        digest = hashlib.sha256(raw).hexdigest()
        registered_sha = row.get("registered_file_sha256")
        if (
            registered_sha is not None
            and (
                binding["expected_file_sha256"] != registered_sha
                or digest != registered_sha
            )
        ):
            _fail("registered_source_file_drift")
        if digest != binding["expected_file_sha256"]:
            _fail("source_bytes_drift")
        source_as_of: str | None = None
        if binding["binding_kind"] == "registered_payload":
            try:
                payload = json.loads(raw, object_pairs_hook=_object)
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ConsequencePlanError("source_payload_invalid") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("date"), str):
                _fail("source_effective_date_missing")
            source_as_of = payload["date"]
            observed_as_of.add(source_as_of)
        captured[cast(str, row["path"])] = raw
        inputs.append({
            "binding_id": binding["binding_id"], "binding_kind": binding["binding_kind"],
            "file_sha256": digest, "source_registry_id": binding["source_registry_id"],
            "artifact_id": binding["artifact_id"], "source_as_of": source_as_of,
            "rights_state": row["rights_state"],
            "computed_evidence_class": "legacy_unverified_payload" if binding["binding_kind"] == "registered_payload" else "verified_signed_replay_ledger",
        })
    return inputs, captured


def _assistant_plan(plan: Mapping[str, Any]) -> assistant.Plan:
    request = cast(dict[str, Any], plan["request"])
    template_id = cast(str, request["intent_id"])
    intent = "compare_channels" if template_id == "channel_comparison" else template_id
    if template_id.startswith("refusal_"):
        intent = "refuse"
    return assistant.Plan(assistant.PLAN_SCHEMA_VERSION, intent, template_id, tuple(request["fact_ids"]))


def _step_proofs(
    plan: Mapping[str, Any],
    inputs: Sequence[Mapping[str, Any]],
    output: object,
    final_output_kind: str,
) -> list[dict[str, Any]]:
    operators = _operator_rows()
    request = cast(dict[str, Any], plan["request"])
    reference_digests = {
        cast(str, row["binding_id"]): _typed_digest(row) for row in inputs
    }
    reference_kinds = {
        cast(str, row["binding_id"]): (
            "registered_payload"
            if row["binding_kind"] == "registered_payload"
            else "verified_signed_replay_ledger"
        )
        for row in inputs
    }
    reference_digests.update(
        {
            "request:facts": _typed_digest(request["fact_ids"]),
            "request:replay": _typed_digest(
                {
                    key: request[key]
                    for key in (
                        "knowledge_cutoff",
                        "valid_on",
                        "object_type",
                        "object_id",
                    )
                }
            ),
            "request:refusal": _typed_digest(request["refusal_code"]),
        }
    )
    reference_kinds.update(
        {
            "request:facts": "registered_fact_reference_set",
            "request:replay": "registered_replay_request",
            "request:refusal": "registered_refusal_code",
        }
    )
    proofs: list[dict[str, Any]] = []
    source_days = sorted(
        cast(str, row["source_as_of"])
        for row in inputs
        if row["source_as_of"] is not None
    )
    for step in cast(list[dict[str, Any]], plan["steps"]):
        try:
            input_digests = [reference_digests[ref] for ref in step["input_refs"]]
            input_kinds = [reference_kinds[ref] for ref in step["input_refs"]]
        except KeyError as exc:  # pragma: no cover - graph validation prevents it
            raise ConsequencePlanError("step_input_unresolved", str(exc)) from exc
        operator_id = cast(str, step["operator_id"])
        row = operators[operator_id]
        if input_kinds not in row["input_kind_sequences"]:
            _fail("operator_input_kind_invalid", operator_id)
        step_output: object
        if operator_id == "op:igrm.select_registered_facts":
            output_kind = "integrity_verified_payload_fact_set"
            cardinality = len(request["fact_ids"])
            step_output = {
                "epistemic_kind": output_kind,
                "fact_ids": request["fact_ids"],
                "source_file_sha256": sorted(row["file_sha256"] for row in inputs),
            }
        elif operator_id == "op:igrm.assert_same_effective_date":
            output_kind = (
                "same_effective_date_fact_set"
                if len(set(source_days)) <= 1
                else "registered_refusal"
            )
            cardinality = len(request["fact_ids"])
            step_output = {
                "epistemic_kind": output_kind,
                "source_as_of": source_days,
                "status": "verified" if len(set(source_days)) <= 1 else "refused",
            }
        elif operator_id == "op:igrm.select_signed_replay_state":
            output_kind = "bitemporal_state_selection"
            records = output.get("records") if isinstance(output, dict) else None
            cardinality = len(records) if isinstance(records, list) else 0
            step_output = {
                "epistemic_kind": output_kind,
                "replay_output_sha256": _typed_digest(output),
            }
        else:
            output_kind = final_output_kind
            cardinality = 1
            step_output = output
        if output_kind not in row["output_kinds"]:
            _fail("operator_output_kind_invalid", operator_id)
        maximum = row["max_cardinality"]
        if (
            isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or cardinality > maximum
        ):
            _fail("operator_cardinality_exceeded", operator_id)
        output_digest = _typed_digest(step_output)
        proofs.append({
            "step_id": step["step_id"], "operator_id": step["operator_id"],
            "operator_version": step["operator_version"],
            "implementation_sha256": row["implementation_sha256"],
            "input_digests": input_digests, "input_kinds": input_kinds,
            "output_digest": output_digest, "output_kind": output_kind,
            "status": "verified",
        })
        reference_digests[step["output_ref"]] = output_digest
        reference_kinds[step["output_ref"]] = output_kind
    return proofs


def validate_execution(
    execution: Mapping[str, Any],
    plan: Mapping[str, Any],
    root: Path = ROOT,
) -> None:
    """Re-execute and refuse a mutated or source-drifted proof envelope."""
    _schema_check(
        execution,
        _schema(EXECUTION_SCHEMA_PATH, "execution_schema_invalid"),
        "execution_schema_refused",
    )
    _verify_integrity(execution, "execution_integrity_mismatch")
    engine = execution.get("engine")
    if not isinstance(engine, dict) or not isinstance(engine.get("executed_at"), str):
        _fail("execution_engine_invalid")
    if execution.get("execution_status") == "refused":
        expected = execute_or_refuse(plan, root, executed_at=engine["executed_at"])
    else:
        expected = execute_plan(plan, root, executed_at=engine["executed_at"])
    if execution != expected:
        _fail("execution_recompile_mismatch")


def execute_plan(plan: Mapping[str, Any], root: Path = ROOT, *, executed_at: str | None = None) -> dict[str, Any]:
    """Execute a valid closed plan and emit a self-hashed proof envelope."""
    validate_plan(plan)
    inputs, captured = _load_bound_inputs(plan, root)
    profile_id = cast(str, plan["profile_id"])
    request = cast(dict[str, Any], plan["request"])
    if profile_id in {"legacy_assistant_answer", "registered_refusal"}:
        legacy = _assistant_plan(plan)
        if profile_id == "registered_refusal":
            output = assistant.answer_plan(legacy, root).to_dict()
        else:
            with tempfile.TemporaryDirectory(prefix="igrm-consequence-") as temporary:
                captured_root = Path(temporary)
                for relative, raw in captured.items():
                    path = captured_root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                output = assistant.answer_plan(legacy, captured_root).to_dict()
        output_kind = (
            "registered_refusal"
            if profile_id == "registered_refusal" or output["status"] == "refused"
            else "descriptive_registered_answer"
        )
        trust = "legacy_unverified"
        source_days = {row["source_as_of"] for row in inputs if row["source_as_of"]}
        source_as_of = next(iter(source_days)) if len(source_days) == 1 else None
        time_policy = "not_applicable_registered_refusal" if profile_id == "registered_refusal" else "source_effective_date_equality"
        universe_status = "not_applicable_registered_denominator_text_only"
    else:
        binding = cast(dict[str, Any], plan["source_bindings"][0])
        row = _source_rows()[binding["source_registry_id"]]
        fixture_root = _relative_directory(
            root, row["fixture_root"], "replay_fixture_root_invalid"
        )
        captured_ledger = captured[cast(str, row["path"])]
        with tempfile.TemporaryDirectory(
            prefix=".consequence-ledger-", dir=fixture_root
        ) as temporary:
            captured_path = Path(temporary) / "ledger.json"
            captured_path.write_bytes(captured_ledger)
            output = knowledge_replay.replay(
                captured_path,
                request["knowledge_cutoff"],
                request["valid_on"],
                object_type=request["object_type"],
                object_id=request["object_id"],
                root=fixture_root,
                replay_registry_path=_relative_file(
                    fixture_root,
                    row["replay_registry_path"],
                    "replay_registry_path_invalid",
                ),
                knowledge_signers_path=_relative_file(
                    fixture_root,
                    row["knowledge_signers_path"],
                    "replay_signers_path_invalid",
                ),
            )
        output_kind = "structural_replay_report"
        trust = "synthetic_nonproduction"
        source_as_of = None
        time_policy = "separate_knowledge_and_valid_time"
        universe_status = "not_applicable_structural_replay"
    output_profile = _output_rows()[cast(str, plan["output_profile_id"])]
    if output_kind not in output_profile["output_kinds"]:
        _fail("output_profile_kind_invalid")
    timestamp = executed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    envelope = {
        "object_type": "oges_consequence_execution", "schema_version": SCHEMA_VERSION,
        "integrity": {"profile_id": TYPED_PROFILE, "value_sha256": ZERO_SHA},
        "plan_binding": {"plan_id": plan["plan_id"], "plan_integrity_sha256": plan["integrity"]["value_sha256"], "plan_file_sha256": hashlib.sha256(serialize_plan(plan)).hexdigest()},
        "contract": dict(plan["contract"]),
        "engine": {"method_id": METHOD_ID, "version": METHOD_VERSION, "implementation_sha256": _sha(ROOT / "src/consequence_plan.py"), "executed_at": timestamp},
        "inputs": inputs,
        "step_proofs": _step_proofs(plan, inputs, output, output_kind),
        "temporal": {"knowledge_cutoff": request["knowledge_cutoff"], "valid_on": request["valid_on"], "actual_source_as_of": source_as_of, "time_policy": time_policy},
        "universe": {"status": universe_status, "universe_release_id": None, "record_sha256": None, "member_count": None},
        "trust_class": trust, "publication_eligible": False,
        "execution_status": "succeeded",
        "result": {"output_kind": output_kind, "output_profile_id": plan["output_profile_id"], "output": output},
        "refusal": None,
        "limitations": sorted(["execution_proof_not_authenticated_truth", "no_consequence_causal_forecast_or_recommendation_claim", "no_universe_completeness_claim", "plans_grant_no_rights"]),
    }
    sealed = _seal(envelope)
    _schema_check(sealed, _schema(EXECUTION_SCHEMA_PATH, "execution_schema_invalid"), "execution_schema_refused")
    _verify_integrity(sealed, "execution_integrity_mismatch")
    return sealed


def _refusal_stage(code: str) -> str:
    if code.startswith(("source_", "artifact_")):
        return "source"
    if code.startswith(("operator_", "knowledge_", "replay_")):
        return "operator"
    if code.startswith(("output_", "execution_")):
        return "proof"
    if code.startswith(("extension_", "fact_catalog_")) or "contract" in code:
        return "contract"
    return "plan"


def execute_or_refuse(
    plan: Mapping[str, Any],
    root: Path = ROOT,
    *,
    executed_at: str | None = None,
) -> dict[str, Any]:
    """Execute or return a value-free, machine-readable refusal envelope."""
    timestamp = executed_at or datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        return execute_plan(plan, root, executed_at=timestamp)
    except (
        ConsequencePlanError,
        assistant.EvidenceError,
        knowledge_replay.KnowledgeReplayError,
    ) as exc:
        code = exc.code
    try:
        plan_bytes = serialize_plan(plan)
    except (TypeError, ValueError, UnicodeError):
        plan_bytes = type(plan).__name__.encode("ascii", "strict")
    plan_digest = hashlib.sha256(plan_bytes).hexdigest()
    plan_id = plan.get("plan_id")
    if not isinstance(plan_id, str) or re.fullmatch(
        r"plan:[a-z0-9][a-z0-9_.:-]{2,127}", plan_id
    ) is None:
        plan_id = f"plan:invalid:{plan_digest[:24]}"
    integrity = plan.get("integrity")
    plan_integrity = integrity.get("value_sha256") if isinstance(integrity, dict) else None
    if (
        not isinstance(plan_integrity, str)
        or len(plan_integrity) != 64
        or any(character not in "0123456789abcdef" for character in plan_integrity)
    ):
        plan_integrity = ZERO_SHA
    envelope = {
        "object_type": "oges_consequence_execution",
        "schema_version": SCHEMA_VERSION,
        "integrity": {"profile_id": TYPED_PROFILE, "value_sha256": ZERO_SHA},
        "plan_binding": {
            "plan_id": plan_id,
            "plan_integrity_sha256": plan_integrity,
            "plan_file_sha256": plan_digest,
        },
        "contract": _contract_hashes(),
        "engine": {
            "method_id": METHOD_ID,
            "version": METHOD_VERSION,
            "implementation_sha256": _sha(ROOT / "src/consequence_plan.py"),
            "executed_at": timestamp,
        },
        "inputs": [],
        "step_proofs": [],
        "temporal": {
            "knowledge_cutoff": None,
            "valid_on": None,
            "actual_source_as_of": None,
            "time_policy": "not_applicable_registered_refusal",
        },
        "universe": {
            "status": "not_applicable_structural_replay",
            "universe_release_id": None,
            "record_sha256": None,
            "member_count": None,
        },
        "trust_class": "legacy_unverified",
        "publication_eligible": False,
        "execution_status": "refused",
        "result": None,
        "refusal": {"stage": _refusal_stage(code), "code": code},
        "limitations": sorted(
            [
                "execution_proof_not_authenticated_truth",
                "no_partial_value_or_evidence_on_engine_refusal",
                "plans_grant_no_rights",
            ]
        ),
    }
    sealed = _seal(envelope)
    _schema_check(
        sealed,
        _schema(EXECUTION_SCHEMA_PATH, "execution_schema_invalid"),
        "execution_schema_refused",
    )
    _verify_integrity(sealed, "execution_integrity_mismatch")
    return sealed


def main(argv: Sequence[str] | None = None) -> None:
    del argv
    plan = from_legacy_assistant_plan(
        assistant.plan_question("What is the latest headline?"),
        compiled_at="2026-08-09T00:00:00Z",
    )
    print(json.dumps(execute_plan(plan, executed_at="2026-08-09T00:00:01Z"), indent=2))


if __name__ == "__main__":
    main()
