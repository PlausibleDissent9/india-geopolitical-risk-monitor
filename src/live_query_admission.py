"""Closed, synthetic live-query admission with an explicit question denominator.

The caller binds registered parameter IDs to registered finite-domain member IDs.
It never supplies a selector, relation, projection, aggregation, bound, universe,
rights state, source release, or result field.  This v0.1 slice executes no source
query and publishes no route; its self-hashes provide integrity, not authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, NoReturn, cast

from . import event_ledger, event_ledger_extension

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "live_query_admission_contract.json"
PROFILE_PATH = ROOT / "governance" / "live_query_admission_profile.json"
DOMAIN_REGISTRY_PATH = ROOT / "governance" / "live_query_domain_registry.json"
TEMPLATE_REGISTRY_PATH = ROOT / "governance" / "live_query_template_registry.json"
VECTORS_PATH = ROOT / "governance" / "live_query_admission_adversarial_vectors.json"

_VERSION = "0.1.0"
_PROFILE_SHA256 = "eedc35b0b17bf63a6858706cd1904ec5b0b37e09490fd5ebc261941184f23a74"
_NORMATIVE_PATHS = {
    "contract": "governance/live_query_admission_contract.json",
    "domain_registry": "governance/live_query_domain_registry.json",
    "template_registry": "governance/live_query_template_registry.json",
    "adversarial_vectors": "governance/live_query_admission_adversarial_vectors.json",
}
_TRUST = {
    "signed": False,
    "authenticated": False,
    "synthetic": True,
    "contract_only": True,
    "source_execution_performed": False,
    "production_authority": False,
    "public_authority": False,
    "requested_at_semantics": "caller_declared_unauthenticated",
    "record_sha256_is_authentication": False,
}
_PROFILE_TRUST = {key: value for key, value in _TRUST.items() if key != "record_sha256_is_authentication"}
_SELECTOR_TOKENS = ("*", "?", "[", "]", "{", "}", "(", ")", "=", "<", ">", "|", "&", ";", "\\")
_CALLER_SEMANTIC_KEYS = {
    "aggregation",
    "bounds",
    "denominator",
    "domain_restriction",
    "filter",
    "limit",
    "max_hops",
    "max_paths",
    "max_rows",
    "ordering",
    "projection",
    "query",
    "relation",
    "rights_state",
    "selector",
    "source_release_ref",
    "sql",
    "universe",
}
_BINDING_KEYS = (
    "object_type",
    "schema_version",
    "template_id",
    "template_record_sha256",
    "arguments",
    "requested_at",
)
_ARGUMENT_KEYS = ("parameter_id", "domain_id", "domain_record_sha256", "member_id")
_DOMAIN_KEYS = ("domain_id", "record_sha256", "members")
_MEMBER_KEYS = ("member_id",)
_TEMPLATE_KEYS = (
    "template_id",
    "record_sha256",
    "relation",
    "denominator_rule",
    "projection",
    "aggregation",
    "parameters",
    "bounds",
    "rights_use_required",
    "source_release_ref",
    "limitation_ids",
)
_PARAMETER_KEYS = ("parameter_id", "domain_id", "required")
_BOUNDS_KEYS = ("max_hops", "max_rows", "max_universe_size")
_RELEASE_KEYS = ("release_id", "record_sha256")
_RECEIPT_KEYS = (
    "object_type",
    "schema_version",
    "admission_id",
    "record_sha256",
    "template_id",
    "template_record_sha256",
    "source_release_ref",
    "domain_versions",
    "requested_arguments",
    "requested_at",
    "binding_universe",
    "universe_size",
    "universe_digest_sha256",
    "universe_truncated",
    "requested_index",
    "rights_state_per_binding",
    "admitted",
    "refusal_code",
    "limitation_ids",
    "trust_boundary",
    "claim_boundary",
)


class LiveQueryAdmissionError(ValueError):
    """Stable fail-closed live-query admission refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise LiveQueryAdmissionError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("admission_json_duplicate_key", key)
        result[key] = value
    return result


def _parse_json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("admission_structure_invalid"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiveQueryAdmissionError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], code: str) -> None:
    if set(value) != set(expected):
        _fail(code, f"expected={sorted(expected)!r} observed={sorted(value)!r}")


def _strict_string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _strict_int(value: object, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(code)
    return value


def _instant(value: object) -> str:
    if not isinstance(value, str):
        _fail("admission_time_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _fail("admission_time_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("admission_time_invalid")
    return value


def _typed_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise LiveQueryAdmissionError("admission_typed_canonical_invalid", exc.code) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], event_ledger_extension.seal_record(value))
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise LiveQueryAdmissionError("admission_receipt_digest_mismatch", exc.code) from exc


def _typed_record_sha(value: Mapping[str, Any]) -> str:
    try:
        return event_ledger_extension.typed_record_sha256(value)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise LiveQueryAdmissionError("admission_typed_canonical_invalid", exc.code) from exc


def _verify_digest(value: Mapping[str, Any]) -> None:
    try:
        observed = event_ledger_extension.typed_record_sha256(value)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise LiveQueryAdmissionError("admission_receipt_digest_mismatch", exc.code) from exc
    if observed != value.get("record_sha256"):
        _fail("admission_receipt_digest_mismatch")


def serialize_record(value: Mapping[str, Any]) -> bytes:
    """Return deterministic transport bytes for replay equality."""

    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


@dataclass(frozen=True)
class _FixedInputs:
    contract: dict[str, Any]
    profile: dict[str, Any]
    domain_registry: dict[str, Any]
    template_registry: dict[str, Any]
    vectors: dict[str, Any]
    raw_sha256: dict[str, str]


def _capture_fixed_inputs() -> _FixedInputs:
    paths = {
        "contract": CONTRACT_PATH,
        "profile": PROFILE_PATH,
        "domain_registry": DOMAIN_REGISTRY_PATH,
        "template_registry": TEMPLATE_REGISTRY_PATH,
        "adversarial_vectors": VECTORS_PATH,
    }
    try:
        raw = {kind: path.read_bytes() for kind, path in paths.items()}
    except OSError as exc:
        raise LiveQueryAdmissionError("admission_profile_drift") from exc
    digests = {kind: hashlib.sha256(value).hexdigest() for kind, value in raw.items()}
    if digests["profile"] != _PROFILE_SHA256:
        _fail("admission_profile_drift")
    captured = _FixedInputs(
        contract=_parse_json(raw["contract"], "admission_contract_drift"),
        profile=_parse_json(raw["profile"], "admission_profile_invalid"),
        domain_registry=_parse_json(raw["domain_registry"], "admission_domain_registry_invalid"),
        template_registry=_parse_json(raw["template_registry"], "admission_template_registry_invalid"),
        vectors=_parse_json(raw["adversarial_vectors"], "admission_vector_registry_invalid"),
        raw_sha256=digests,
    )
    _validate_fixed_inputs(captured)
    return captured


def _validate_contract(contract: Mapping[str, Any]) -> None:
    _exact_keys(
        contract,
        (
            "schema_version",
            "contract_id",
            "canonicalization_profile_id",
            "status",
            "default_policy",
            "public_routes",
            "input_rule",
            "universe_rule",
            "requested_index_base",
            "trust_boundary",
            "claim_boundary",
            "limitations",
            "active_refusal_codes",
            "future_execution_refusal_codes",
        ),
        "admission_contract_drift",
    )
    if (
        contract["schema_version"] != _VERSION
        or contract["contract_id"] != "igrm:live-query-admission:0.1.0"
        or contract["canonicalization_profile_id"] != "igrm-typed-canonical-f64-v1"
        or contract["status"] != "synthetic_contract_only"
        or contract["default_policy"] != "deny"
        or contract["public_routes"] != []
        or contract["requested_index_base"] != 0
        or contract["trust_boundary"] != _TRUST
    ):
        _fail("admission_contract_drift")
    for key in ("claim_boundary", "input_rule", "universe_rule"):
        _strict_string(contract[key], "admission_contract_drift")
    limitations = contract["limitations"]
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not isinstance(row, str) or not row for row in limitations)
        or len(limitations) != len(set(limitations))
    ):
        _fail("admission_contract_drift")
    for key in ("active_refusal_codes", "future_execution_refusal_codes"):
        rows = contract[key]
        if (
            not isinstance(rows, list)
            or not rows
            or any(not isinstance(row, str) or not row for row in rows)
            or rows != sorted(set(rows))
        ):
            _fail("admission_contract_drift")


def _validate_profile(profile: Mapping[str, Any], fixed: _FixedInputs) -> None:
    _exact_keys(
        profile,
        (
            "schema_version",
            "profile_id",
            "effective",
            "status",
            "default_policy",
            "normative_files",
            "source_releases",
            "synthetic_rights_policy",
            "trust_boundary",
        ),
        "admission_profile_invalid",
    )
    if (
        profile["schema_version"] != _VERSION
        or profile["profile_id"] != "igrm:live-query-admission-profile:0.1.0"
        or profile["effective"] != "2026-08-10"
        or profile["status"] != "synthetic_contract_only"
        or profile["default_policy"] != "deny"
        or profile["trust_boundary"] != _PROFILE_TRUST
    ):
        _fail("admission_profile_invalid")
    normative = profile["normative_files"]
    if not isinstance(normative, list) or len(normative) != len(_NORMATIVE_PATHS):
        _fail("admission_profile_invalid")
    seen: set[str] = set()
    for row in normative:
        if not isinstance(row, dict):
            _fail("admission_profile_invalid")
        _exact_keys(row, ("kind", "path", "sha256"), "admission_profile_invalid")
        kind = _strict_string(row["kind"], "admission_profile_invalid")
        if kind in seen or _NORMATIVE_PATHS.get(kind) != row["path"]:
            _fail("admission_profile_invalid")
        if fixed.raw_sha256.get(kind) != row["sha256"]:
            _fail("admission_profile_drift")
        seen.add(kind)
    if seen != set(_NORMATIVE_PATHS):
        _fail("admission_profile_invalid")
    releases = profile["source_releases"]
    if not isinstance(releases, list) or len(releases) != 1:
        _fail("admission_profile_invalid")
    release = releases[0]
    if not isinstance(release, dict):
        _fail("admission_profile_invalid")
    _exact_keys(
        release,
        ("release_id", "record_sha256", "status", "source_execution_performed"),
        "admission_profile_invalid",
    )
    expected_release_record = {
        "release_id": release["release_id"],
        "status": release["status"],
        "source_execution_performed": release["source_execution_performed"],
    }
    if (
        release["release_id"] != "release:live-query.synthetic.v1"
        or release["record_sha256"] != _typed_sha(expected_release_record)
        or release["status"] != "registered_synthetic_identity_only"
        or release["source_execution_performed"] is not False
    ):
        _fail("admission_profile_invalid")
    policy = profile["synthetic_rights_policy"]
    if not isinstance(policy, dict):
        _fail("admission_profile_invalid")
    _exact_keys(policy, ("default_state", "overrides"), "admission_profile_invalid")
    if policy["default_state"] != "admitted" or not isinstance(policy["overrides"], list):
        _fail("admission_profile_invalid")
    seen_bindings: set[tuple[str, ...]] = set()
    for override in policy["overrides"]:
        if not isinstance(override, dict):
            _fail("admission_profile_invalid")
        _exact_keys(override, ("binding_member_ids", "state"), "admission_profile_invalid")
        member_ids = override["binding_member_ids"]
        if (
            not isinstance(member_ids, list)
            or any(not isinstance(member_id, str) or not member_id for member_id in member_ids)
            or override["state"] != "refused_rights"
            or tuple(member_ids) in seen_bindings
        ):
            _fail("admission_profile_invalid")
        seen_bindings.add(tuple(member_ids))


def _validate_domain_registry(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    _exact_keys(
        registry,
        ("schema_version", "registry_id", "status", "default_policy", "domains"),
        "admission_domain_registry_invalid",
    )
    if (
        registry["schema_version"] != _VERSION
        or registry["registry_id"] != "igrm:live-query-domains:0.1.0"
        or registry["status"] != "synthetic_contract_only"
        or registry["default_policy"] != "deny"
        or not isinstance(registry["domains"], list)
        or not registry["domains"]
    ):
        _fail("admission_domain_registry_invalid")
    result: dict[str, dict[str, Any]] = {}
    for domain in registry["domains"]:
        if not isinstance(domain, dict):
            _fail("admission_domain_registry_invalid")
        _exact_keys(domain, _DOMAIN_KEYS, "admission_domain_registry_invalid")
        domain_id = _strict_string(domain["domain_id"], "admission_domain_registry_invalid")
        if domain_id in result or domain["record_sha256"] != _typed_record_sha(domain):
            _fail("admission_domain_registry_invalid")
        members = domain["members"]
        if not isinstance(members, list) or not members:
            _fail("admission_universe_not_recomputable")
        member_ids: set[str] = set()
        for member in members:
            if not isinstance(member, dict):
                _fail("admission_domain_registry_invalid")
            _exact_keys(member, _MEMBER_KEYS, "admission_domain_registry_invalid")
            member_id = _strict_string(member["member_id"], "admission_domain_registry_invalid")
            if member_id in member_ids:
                _fail("admission_domain_registry_invalid")
            member_ids.add(member_id)
        result[domain_id] = cast(dict[str, Any], domain)
    return result


def _validate_template_registry(
    registry: Mapping[str, Any], domains: Mapping[str, Mapping[str, Any]], profile: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    _exact_keys(
        registry,
        (
            "schema_version",
            "registry_id",
            "status",
            "default_policy",
            "registered_aggregations",
            "registered_relations",
            "registered_denominator_rules",
            "templates",
        ),
        "admission_template_registry_invalid",
    )
    if (
        registry["schema_version"] != _VERSION
        or registry["registry_id"] != "igrm:live-query-templates:0.1.0"
        or registry["status"] != "synthetic_contract_only"
        or registry["default_policy"] != "deny"
    ):
        _fail("admission_template_registry_invalid")
    for name in ("registered_aggregations", "registered_relations", "registered_denominator_rules"):
        rows = registry[name]
        if not isinstance(rows, list) or not rows or rows != list(dict.fromkeys(rows)):
            _fail("admission_template_registry_invalid")
    if registry["registered_aggregations"] != ["aggregation:none"]:
        _fail("admission_aggregation_unregistered")
    templates = registry["templates"]
    if not isinstance(templates, list) or not templates:
        _fail("admission_template_registry_invalid")
    releases = {row["release_id"]: row for row in profile["source_releases"]}
    result: dict[str, dict[str, Any]] = {}
    for template in templates:
        if not isinstance(template, dict):
            _fail("admission_template_registry_invalid")
        _exact_keys(template, _TEMPLATE_KEYS, "admission_template_registry_invalid")
        template_id = _strict_string(template["template_id"], "admission_template_registry_invalid")
        if template_id in result:
            _fail("admission_template_registry_invalid")
        if template["aggregation"] not in registry["registered_aggregations"]:
            _fail("admission_aggregation_unregistered")
        if (
            template["relation"] not in registry["registered_relations"]
            or template["denominator_rule"] not in registry["registered_denominator_rules"]
            or template["projection"] != []
            or template["rights_use_required"] != "synthetic_none"
        ):
            _fail("admission_template_registry_invalid")
        parameters = template["parameters"]
        if not isinstance(parameters, list) or not parameters:
            _fail("admission_template_registry_invalid")
        seen_parameters: set[str] = set()
        for parameter in parameters:
            if not isinstance(parameter, dict):
                _fail("admission_template_registry_invalid")
            _exact_keys(parameter, _PARAMETER_KEYS, "admission_template_registry_invalid")
            parameter_id = _strict_string(parameter["parameter_id"], "admission_template_registry_invalid")
            if (
                parameter_id in seen_parameters
                or parameter["domain_id"] not in domains
                or parameter["required"] is not True
            ):
                _fail("admission_template_registry_invalid")
            seen_parameters.add(parameter_id)
        bounds = template["bounds"]
        if not isinstance(bounds, dict):
            _fail("admission_template_registry_invalid")
        _exact_keys(bounds, _BOUNDS_KEYS, "admission_template_registry_invalid")
        if (
            _strict_int(bounds["max_hops"], "admission_template_registry_invalid") != 0
            or _strict_int(bounds["max_rows"], "admission_template_registry_invalid") != 0
            or _strict_int(bounds["max_universe_size"], "admission_template_registry_invalid", minimum=1) < 1
        ):
            _fail("admission_template_registry_invalid")
        release_ref = template["source_release_ref"]
        if not isinstance(release_ref, dict):
            _fail("admission_template_registry_invalid")
        _exact_keys(release_ref, _RELEASE_KEYS, "admission_template_registry_invalid")
        release_id = _strict_string(release_ref["release_id"], "admission_source_release_unregistered")
        if release_id not in releases:
            _fail("admission_source_release_unregistered")
        release = releases[release_id]
        if release["status"] != "registered_synthetic_identity_only":
            _fail("admission_source_release_refused")
        if release_ref["record_sha256"] != release["record_sha256"]:
            _fail("admission_source_release_refused")
        limitations = template["limitation_ids"]
        if (
            not isinstance(limitations, list)
            or not limitations
            or limitations != sorted(set(limitations))
            or any(not isinstance(item, str) or not item.startswith("limitation:") for item in limitations)
        ):
            _fail("admission_template_registry_invalid")
        if template["record_sha256"] != _typed_record_sha(template):
            _fail("admission_template_registry_invalid")
        result[template_id] = cast(dict[str, Any], template)
    return result


def _validate_vectors(vectors: Mapping[str, Any]) -> None:
    _exact_keys(
        vectors,
        ("schema_version", "registry_id", "default_policy", "cases"),
        "admission_vector_registry_invalid",
    )
    cases = vectors["cases"]
    if (
        vectors["schema_version"] != _VERSION
        or vectors["registry_id"] != "igrm:live-query-admission-adversarial:0.1.0"
        or vectors["default_policy"] != "deny"
        or not isinstance(cases, list)
        or not cases
    ):
        _fail("admission_vector_registry_invalid")
    case_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or set(case) not in (
            {"case_id", "expected_status"},
            {"case_id", "expected_status", "expected_reason"},
        ):
            _fail("admission_vector_registry_invalid")
        case_id = _strict_string(case["case_id"], "admission_vector_registry_invalid")
        if case_id in case_ids or case["expected_status"] not in ("valid", "refused"):
            _fail("admission_vector_registry_invalid")
        if case["expected_status"] == "refused" and not isinstance(case.get("expected_reason"), str):
            _fail("admission_vector_registry_invalid")
        case_ids.add(case_id)


def _validate_fixed_inputs(fixed: _FixedInputs) -> None:
    _validate_contract(fixed.contract)
    _validate_profile(fixed.profile, fixed)
    domains = _validate_domain_registry(fixed.domain_registry)
    templates = _validate_template_registry(fixed.template_registry, domains, fixed.profile)
    for template in templates.values():
        universe = _enumerate_universe(template, domains)
        valid_member_tuples = {
            tuple(argument["member_id"] for argument in row["arguments"]) for row in universe
        }
        for override in fixed.profile["synthetic_rights_policy"]["overrides"]:
            if tuple(override["binding_member_ids"]) not in valid_member_tuples:
                _fail("admission_profile_invalid")
    _validate_vectors(fixed.vectors)


def _looks_like_selector(value: str) -> bool:
    lowered = value.lower()
    return any(token in value for token in _SELECTOR_TOKENS) or any(
        marker in lowered for marker in ("select ", "filter:", "where ", "regex:", "sql:")
    )


def _reject_caller_semantics(binding: Mapping[str, Any]) -> None:
    forbidden = sorted(set(binding) & _CALLER_SEMANTIC_KEYS)
    arguments = binding.get("arguments")
    if isinstance(arguments, list):
        for argument in arguments:
            if isinstance(argument, Mapping):
                forbidden.extend(sorted(set(argument) & _CALLER_SEMANTIC_KEYS))
    if forbidden:
        _fail("admission_selector_text_supplied", ",".join(forbidden))


def _normalize_binding(
    binding: Mapping[str, Any],
    template: Mapping[str, Any],
    domains: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, str]]:
    _reject_caller_semantics(binding)
    _exact_keys(binding, _BINDING_KEYS, "admission_structure_invalid")
    if binding["object_type"] != "argument_binding" or binding["schema_version"] != _VERSION:
        _fail("admission_structure_invalid")
    _instant(binding["requested_at"])
    arguments = binding["arguments"]
    if not isinstance(arguments, list):
        _fail("admission_structure_invalid")
    parameters = template["parameters"]
    parameter_by_id = {row["parameter_id"]: row for row in parameters}
    supplied: dict[str, dict[str, str]] = {}
    for argument in arguments:
        if not isinstance(argument, dict):
            _fail("admission_structure_invalid")
        _exact_keys(argument, _ARGUMENT_KEYS, "admission_structure_invalid")
        parameter_id = _strict_string(argument["parameter_id"], "admission_parameter_unregistered")
        if parameter_id not in parameter_by_id:
            _fail("admission_parameter_unregistered", parameter_id)
        if parameter_id in supplied:
            _fail("admission_extra_parameter_supplied", parameter_id)
        domain_id = _strict_string(argument["domain_id"], "admission_domain_unregistered")
        if domain_id not in domains or domain_id != parameter_by_id[parameter_id]["domain_id"]:
            _fail("admission_domain_unregistered", domain_id)
        domain = domains[domain_id]
        if argument["domain_record_sha256"] != domain["record_sha256"]:
            _fail("admission_domain_digest_mismatch", domain_id)
        member_id = _strict_string(argument["member_id"], "admission_member_not_in_domain")
        member_ids = [row["member_id"] for row in domain["members"]]
        if member_id not in member_ids:
            if _looks_like_selector(member_id):
                _fail("admission_selector_text_supplied", member_id)
            _fail("admission_member_not_in_domain", member_id)
        supplied[parameter_id] = {
            "parameter_id": parameter_id,
            "domain_id": domain_id,
            "domain_record_sha256": cast(str, domain["record_sha256"]),
            "member_id": member_id,
        }
    if len(arguments) > len(parameters):
        _fail("admission_extra_parameter_supplied")
    missing = [row["parameter_id"] for row in parameters if row["required"] and row["parameter_id"] not in supplied]
    if missing:
        _fail("admission_required_parameter_missing", ",".join(missing))
    return [supplied[row["parameter_id"]] for row in parameters]


def _enumerate_universe(
    template: Mapping[str, Any], domains: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    parameters = template["parameters"]
    member_lists = [domains[row["domain_id"]]["members"] for row in parameters]
    size = 1
    for members in member_lists:
        if not members:
            _fail("admission_universe_not_recomputable")
        size *= len(members)
    bound = template["bounds"]["max_universe_size"]
    if size > bound:
        _fail("admission_universe_exceeds_bound", f"size={size} bound={bound}")
    universe: list[dict[str, Any]] = []
    for members in product(*member_lists):
        arguments = []
        for parameter, member in zip(parameters, members, strict=True):
            domain = domains[parameter["domain_id"]]
            arguments.append(
                {
                    "parameter_id": parameter["parameter_id"],
                    "domain_id": parameter["domain_id"],
                    "domain_record_sha256": domain["record_sha256"],
                    "member_id": member["member_id"],
                }
            )
        universe.append({"arguments": arguments, "binding_digest_sha256": _typed_sha(arguments)})
    if len(universe) != size:
        _fail("admission_universe_not_recomputable")
    return universe


def _rights_states(universe: list[dict[str, Any]], profile: Mapping[str, Any]) -> list[dict[str, str]]:
    policy = profile["synthetic_rights_policy"]
    overrides = {
        tuple(row["binding_member_ids"]): row["state"] for row in policy["overrides"]
    }
    states: list[dict[str, str]] = []
    for row in universe:
        member_ids = tuple(argument["member_id"] for argument in row["arguments"])
        state = overrides.get(member_ids, policy["default_state"])
        states.append({"binding_digest_sha256": row["binding_digest_sha256"], "state": state})
    return states


def _admit_captured(binding: Mapping[str, Any], fixed: _FixedInputs) -> dict[str, Any]:
    domains = _validate_domain_registry(fixed.domain_registry)
    templates = _validate_template_registry(fixed.template_registry, domains, fixed.profile)
    _reject_caller_semantics(binding)
    _exact_keys(binding, _BINDING_KEYS, "admission_structure_invalid")
    template_id = _strict_string(binding["template_id"], "admission_template_unregistered")
    if template_id not in templates:
        _fail("admission_template_unregistered", template_id)
    template = templates[template_id]
    if binding["template_record_sha256"] != template["record_sha256"]:
        _fail("admission_template_digest_mismatch", template_id)
    normalized = _normalize_binding(binding, template, domains)
    universe = _enumerate_universe(template, domains)
    requested_digest = _typed_sha(normalized)
    requested_matches = [
        index
        for index, row in enumerate(universe)
        if row["arguments"] == normalized and row["binding_digest_sha256"] == requested_digest
    ]
    if len(requested_matches) != 1:
        _fail("admission_universe_not_recomputable")
    requested_index = requested_matches[0]
    states = _rights_states(universe, fixed.profile)
    requested_state = states[requested_index]["state"]
    admitted = requested_state == "admitted"
    domain_versions = [
        {
            "domain_id": parameter["domain_id"],
            "record_sha256": domains[parameter["domain_id"]]["record_sha256"],
        }
        for parameter in template["parameters"]
    ]
    universe_digest = _typed_sha(universe)
    semantic_identity = {
        "template_record_sha256": template["record_sha256"],
        "source_release_ref": template["source_release_ref"],
        "domain_versions": domain_versions,
        "requested_arguments": normalized,
        "requested_at": _instant(binding["requested_at"]),
        "universe_digest_sha256": universe_digest,
    }
    admission_id = f"admission:live-query.{_typed_sha(semantic_identity)[:32]}"
    receipt = {
        "object_type": "live_query_admission",
        "schema_version": _VERSION,
        "admission_id": admission_id,
        "record_sha256": "",
        "template_id": template_id,
        "template_record_sha256": template["record_sha256"],
        "source_release_ref": template["source_release_ref"],
        "domain_versions": domain_versions,
        "requested_arguments": normalized,
        "requested_at": _instant(binding["requested_at"]),
        "binding_universe": universe,
        "universe_size": len(universe),
        "universe_digest_sha256": universe_digest,
        "universe_truncated": False,
        "requested_index": requested_index,
        "rights_state_per_binding": states,
        "admitted": admitted,
        "refusal_code": None if admitted else "admission_binding_rights_ineligible",
        "limitation_ids": template["limitation_ids"],
        "trust_boundary": fixed.contract["trust_boundary"],
        "claim_boundary": fixed.contract["claim_boundary"],
    }
    sealed = _seal(receipt)
    _exact_keys(sealed, _RECEIPT_KEYS, "admission_structure_invalid")
    return sealed


def admit(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Admit one closed synthetic binding and materialize its full universe."""

    if not isinstance(binding, Mapping):
        _fail("admission_structure_invalid")
    fixed = _capture_fixed_inputs()
    return _admit_captured(binding, fixed)


def verify_admission(binding: Mapping[str, Any], receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Recompile an admission from fixed governance bytes and require byte equality."""

    if not isinstance(receipt, Mapping):
        _fail("admission_structure_invalid")
    _exact_keys(receipt, _RECEIPT_KEYS, "admission_structure_invalid")
    _verify_digest(receipt)
    expected = admit(binding)
    if serialize_record(expected) != serialize_record(receipt):
        _fail("admission_receipt_recompile_mismatch")
    return {"status": "valid", "admission_id": expected["admission_id"]}


def make_binding(
    *,
    country: str = "member:country.alpha",
    commodity: str = "member:commodity.grain",
    period: str = "member:period.one",
    requested_at: str = "2026-08-10T00:00:00Z",
) -> dict[str, Any]:
    """Construct the one registered synthetic binding for tests and conformance."""

    fixed = _capture_fixed_inputs()
    domains = _validate_domain_registry(fixed.domain_registry)
    template = fixed.template_registry["templates"][0]
    values = (country, commodity, period)
    arguments = []
    for parameter, member_id in zip(template["parameters"], values, strict=True):
        domain = domains[parameter["domain_id"]]
        arguments.append(
            {
                "parameter_id": parameter["parameter_id"],
                "domain_id": parameter["domain_id"],
                "domain_record_sha256": domain["record_sha256"],
                "member_id": member_id,
            }
        )
    return {
        "object_type": "argument_binding",
        "schema_version": _VERSION,
        "template_id": template["template_id"],
        "template_record_sha256": template["record_sha256"],
        "arguments": arguments,
        "requested_at": requested_at,
    }
