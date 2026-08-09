"""Execute the closed OGES TRACE_NARY_ASSOCIATION contract.

The runtime is a deterministic sidecar over one exact, signed Source Frame /
Entity Foundry package. It preserves every source observation as one complete
n-ary historical association path. It does not emit edges, causal statements,
open-ended model text, real Ministry data, or a second rights/proof system.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src import (
    event_ledger,
    event_ledger_extension,
    publication_guard,
    source_frame_entity_foundry,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_RELATIVE = Path(
    "standard/oges/extensions/nary-association-trace/0.1.0/profile.json"
)
PROFILE_PATH = ROOT / PROFILE_RELATIVE
RIGHTS_RELATIVE = Path("governance/source_rights_registry.json")
RIGHTS_SIGNERS_RELATIVE = Path("governance/rights_signers.json")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAPPING_STATES = ("matched", "unmatched", "ambiguous", "withheld")
_VALUE_STATES = (
    "observed_positive",
    "observed_zero",
    "source_blank",
    "source_missing",
    "suppressed",
    "not_applicable",
)
_BOUND_KINDS = {
    "specification",
    "reference_contract",
    "request_schema",
    "output_schema",
    "projection_registry",
    "foundry_profile",
    "dependency_profile",
    "consequence_plan_profile",
    "event_ledger_profile",
    "claim_schema",
    "episode_schema",
    "correction_impact_schema",
    "canonicalization_implementation",
    "typed_record_implementation",
    "canonicalization_fixture",
    "adversarial_cases",
}

_CANONICALIZATION_PROFILE_ID = "igrm-typed-canonical-f64-v1"
_TUPLE_WRAPPER_TYPE = "trace_nary_tuple_canonical_value"


class NaryAssociationTraceError(ValueError):
    """Stable fail-closed refusal for the trace contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise NaryAssociationTraceError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _parse_json_bytes(raw: bytes, code: str) -> dict[str, Any]:
    try:
        document = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise NaryAssociationTraceError(code) from exc
    if not isinstance(document, dict):
        _fail(code)
    return cast(dict[str, Any], document)


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise NaryAssociationTraceError(code) from exc
    return raw, _parse_json_bytes(raw, code), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
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
    if not resolved.is_file() or resolved.is_symlink():
        _fail(code)
    return resolved


def _safe_dir(root: Path, relative: object, code: str) -> Path:
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
    if not resolved.is_dir() or resolved.is_symlink():
        _fail(code)
    return resolved


def _inside_root(root: Path, path: Path, code: str) -> Path:
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file() or resolved.is_symlink():
        _fail(code)
    return resolved


def _sha(value: object, code: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(code)
    return value


def _day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.tzinfo != timezone.utc or parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


def _temporal_triples(
    observed_times: Sequence[datetime],
    retrieval_times: Sequence[datetime],
    system_times: Sequence[datetime],
) -> zip:
    """Pair temporal vectors without relying on Python 3.10 ``zip(strict=)``."""
    if not (
        len(observed_times) == len(retrieval_times) == len(system_times)
    ):
        _fail("trace_time_order_invalid")
    return zip(observed_times, retrieval_times, system_times)


def _typed_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise NaryAssociationTraceError("trace_typed_canonical_invalid") from exc


def seal_record(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deterministic trace record carrying its self-digest."""

    result = copy.deepcopy(dict(document))
    try:
        return cast(dict[str, Any], event_ledger_extension.seal_record(result))
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise NaryAssociationTraceError("trace_typed_record_invalid") from exc


def _record(document: Mapping[str, Any]) -> None:
    expected = _sha(document.get("record_sha256"), "trace_output_record_digest_invalid")
    try:
        actual = event_ledger_extension.typed_record_sha256(document)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise NaryAssociationTraceError("trace_typed_record_invalid") from exc
    if actual != expected:
        _fail("trace_output_record_digest_mismatch")


def _object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _schema_validate(
    validator: Draft202012Validator, document: Mapping[str, Any], code: str
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        _fail(code)


def _canonicalization_fixture(document: dict[str, Any]) -> None:
    fixture = _object(
        document,
        {"profile", "fixtures"},
        "canonicalization_fixture_invalid",
    )
    if fixture["profile"] != _CANONICALIZATION_PROFILE_ID:
        _fail("canonicalization_fixture_invalid")
    cases = fixture["fixtures"]
    if not isinstance(cases, list) or len(cases) < 12:
        _fail("canonicalization_fixture_invalid")
    required = {
        "one_integer",
        "one_decimal",
        "negative_zero",
        "small_exponent_boundary",
        "max_safe_integer",
        "unicode_string",
        "utf8_key_order",
        "release_projection",
    }
    observed: set[str] = set()
    for raw in cases:
        row = _object(
            raw,
            {"id", "value", "typed_projection", "sha256"},
            "canonicalization_fixture_invalid",
        )
        case_id = row["id"]
        if not isinstance(case_id, str) or not case_id or case_id in observed:
            _fail("canonicalization_fixture_invalid")
        try:
            projection = event_ledger._typed_canonical_bytes(row["value"])
            projection_text = projection.decode("ascii")
        except (event_ledger.EventLedgerError, UnicodeDecodeError):
            _fail("canonicalization_fixture_invalid")
        if (
            projection_text != row["typed_projection"]
            or hashlib.sha256(projection).hexdigest()
            != _sha(row["sha256"], "canonicalization_fixture_invalid")
        ):
            _fail("canonicalization_fixture_digest_mismatch")
        observed.add(case_id)
    if not required <= observed:
        _fail("canonicalization_fixture_invalid")


def _profile(
    root: Path, profile_path: Path
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, Path],
    dict[str, str],
    dict[str, Draft202012Validator],
]:
    canonical_profile = _safe_file(root, PROFILE_RELATIVE.as_posix(), "profile_trust_root_invalid")
    try:
        if profile_path.resolve(strict=True) != canonical_profile:
            _fail("profile_trust_root_invalid")
    except OSError:
        _fail("profile_trust_root_invalid")
    _, profile, profile_transport_sha = _read_json(
        canonical_profile, "profile_unreadable"
    )
    if set(profile) != {
        "schema_version",
        "extension_id",
        "version",
        "effective",
        "status",
        "bound_files",
        "reference_implementation",
        "conformance_test",
        "required_rights_uses",
        "claim_boundary",
    }:
        _fail("profile_fields_invalid")
    if (
        profile["schema_version"] != "0.1.0"
        or profile["extension_id"] != "oges:extension:trace_nary_association"
        or profile["version"] != "0.1.0"
        or profile["status"] != "public_draft_contract_only_real_source_refused"
    ):
        _fail("profile_identity_invalid")
    _day(profile["effective"], "profile_effective_invalid")
    documents: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {}
    rows = profile["bound_files"]
    if not isinstance(rows, list):
        _fail("profile_bound_files_invalid")
    for raw in rows:
        row = _object(raw, {"kind", "path", "sha256"}, "profile_bound_file_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in paths:
            _fail("profile_bound_file_duplicate")
        path = _safe_file(root, row["path"], "profile_bound_file_missing")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise NaryAssociationTraceError("profile_bound_file_missing") from exc
        digest = hashlib.sha256(payload).hexdigest()
        if digest != _sha(row["sha256"], "profile_bound_file_digest_invalid"):
            _fail("profile_bound_file_digest_mismatch")
        document: dict[str, Any] = {}
        if kind not in {
            "specification",
            "canonicalization_implementation",
            "typed_record_implementation",
        }:
            document = _parse_json_bytes(payload, "profile_bound_file_invalid")
        documents[kind] = document
        paths[kind] = path
        digests[kind] = digest
    if set(paths) != _BOUND_KINDS:
        _fail("profile_bound_file_set_invalid")
    digests["trace_profile"] = profile_transport_sha
    _canonicalization_fixture(documents["canonicalization_fixture"])
    validators: dict[str, Draft202012Validator] = {}
    for kind in ("request_schema", "output_schema"):
        schema = documents[kind]
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise NaryAssociationTraceError(f"{kind}_invalid") from exc
        validators[kind] = Draft202012Validator(schema, format_checker=FormatChecker())
    for field in ("reference_implementation", "conformance_test"):
        binding = _object(profile[field], {"path", "sha256"}, f"profile_{field}_invalid")
        path = _safe_file(root, binding["path"], f"profile_{field}_missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != _sha(
            binding["sha256"], f"profile_{field}_digest_invalid"
        ):
            _fail("profile_bound_file_digest_mismatch")
    if profile["required_rights_uses"] != [
        "cite_metadata",
        "publish_derived_value",
        "publish_extract",
    ]:
        _fail("profile_rights_uses_invalid")
    if not isinstance(profile["claim_boundary"], list) or len(profile["claim_boundary"]) < 6:
        _fail("profile_claim_boundary_invalid")
    return profile, documents, paths, digests, validators


def _contract(
    root: Path,
    document: dict[str, Any],
    foundry_profile_document: Mapping[str, Any],
    paths: Mapping[str, Path],
    digests: Mapping[str, str],
) -> dict[str, Any]:
    contract = _object(
        document,
        {
            "schema_version",
            "contract_id",
            "effective",
            "status",
            "capability_state",
            "canonicalization",
            "runtime",
            "foundry",
            "rights",
            "temporal_policy",
            "projection_policy",
            "event_context",
            "public_surface",
            "forbidden_claims",
        },
        "trace_contract_fields_invalid",
    )
    if (
        contract["schema_version"] != "0.1.0"
        or contract["capability_state"] != "contract_only"
        or not isinstance(contract["contract_id"], str)
        or not contract["contract_id"].startswith("contract:trace_nary_association.")
    ):
        _fail("trace_contract_identity_invalid")
    _day(contract["effective"], "trace_contract_effective_invalid")
    canonicalization = _object(
        contract["canonicalization"],
        {
            "profile_id",
            "primitive",
            "tuple_wrapper_type",
            "implementation_path",
            "implementation_sha256",
            "record_implementation_path",
            "record_implementation_sha256",
            "fixture_path",
            "fixture_sha256",
        },
        "trace_contract_canonicalization_invalid",
    )
    canonical_implementation_path = _safe_file(
        root,
        canonicalization["implementation_path"],
        "trace_contract_canonicalization_invalid",
    )
    canonical_fixture_path = _safe_file(
        root,
        canonicalization["fixture_path"],
        "trace_contract_canonicalization_invalid",
    )
    record_implementation_path = _safe_file(
        root,
        canonicalization["record_implementation_path"],
        "trace_contract_canonicalization_invalid",
    )
    if (
        canonicalization["profile_id"] != _CANONICALIZATION_PROFILE_ID
        or canonicalization["primitive"]
        != "src.event_ledger._typed_canonical_sha256"
        or canonicalization["tuple_wrapper_type"] != _TUPLE_WRAPPER_TYPE
        or canonical_implementation_path != paths["canonicalization_implementation"]
        or record_implementation_path != paths["typed_record_implementation"]
        or canonical_fixture_path != paths["canonicalization_fixture"]
        or canonicalization["implementation_sha256"]
        != digests["canonicalization_implementation"]
        or canonicalization["record_implementation_sha256"]
        != digests["typed_record_implementation"]
        or canonicalization["fixture_sha256"] != digests["canonicalization_fixture"]
    ):
        _fail("trace_contract_canonicalization_invalid")
    runtime = _object(
        contract["runtime"],
        {"execution_allowed", "trust_class", "operator_id", "output_profile_id"},
        "trace_contract_runtime_invalid",
    )
    if (
        not isinstance(runtime["execution_allowed"], bool)
        or runtime["operator_id"] != "operator:trace.complete_registered_nary_frame"
        or runtime["output_profile_id"] != "output:trace.nary_association_paths"
    ):
        _fail("trace_contract_runtime_invalid")
    foundry = _object(
        contract["foundry"],
        {
            "source_id",
            "profile_path",
            "profile_sha256",
            "source_contract_path",
            "source_contract_sha256",
            "manifest_path",
            "manifest_sha256",
            "package_path",
            "package_sha256",
        },
        "trace_contract_foundry_invalid",
    )
    foundry_profile = _safe_file(root, foundry["profile_path"], "trace_foundry_profile_missing")
    foundry_contract = _safe_file(
        root, foundry["source_contract_path"], "trace_foundry_source_contract_missing"
    )
    foundry_profile_contract = next(
        (
            row
            for row in foundry_profile_document.get("bound_files", [])
            if isinstance(row, dict) and row.get("kind") == "reference_source_contract"
        ),
        None,
    )
    if (
        foundry_profile != paths["foundry_profile"]
        or foundry["profile_sha256"]
        != _sha(digests["foundry_profile"], "trace_foundry_profile_digest_invalid")
        or not isinstance(foundry_profile_contract, dict)
        or foundry_contract
        != _safe_file(
            root,
            foundry_profile_contract.get("path"),
            "trace_foundry_source_contract_missing",
        )
        or foundry["source_contract_sha256"]
        != _sha(
            foundry_profile_contract.get("sha256"),
            "trace_foundry_contract_digest_invalid",
        )
    ):
        _fail("trace_foundry_binding_mismatch")
    rights = _object(
        contract["rights"],
        {"required_uses", "allowed_signer_roles", "human_signature_is_legal_determination"},
        "trace_contract_rights_invalid",
    )
    if (
        rights["required_uses"]
        != ["cite_metadata", "publish_derived_value", "publish_extract"]
        or rights["human_signature_is_legal_determination"] is not False
        or not isinstance(rights["allowed_signer_roles"], list)
        or len(rights["allowed_signer_roles"]) != len(set(rights["allowed_signer_roles"]))
        or any(not isinstance(role, str) or not role for role in rights["allowed_signer_roles"])
    ):
        _fail("trace_contract_rights_invalid")
    temporal = _object(
        contract["temporal_policy"],
        {
            "selection_rule",
            "require_distinct_source_valid_retrieval_system_time",
            "implicit_wall_clock_forbidden",
        },
        "trace_contract_time_invalid",
    )
    if temporal != {
        "selection_rule": "complete_frame_period_end_at_explicit_knowledge_cutoff",
        "require_distinct_source_valid_retrieval_system_time": True,
        "implicit_wall_clock_forbidden": True,
    }:
        _fail("trace_contract_time_invalid")
    projection = _object(
        contract["projection_policy"],
        {
            "allowed_projection_ids",
            "binary_projection_allowed",
            "cross_product_allowed",
            "independent_projection_value_allowed",
        },
        "trace_contract_projection_invalid",
    )
    if projection != {
        "allowed_projection_ids": ["projection:trace.nary_identity_index"],
        "binary_projection_allowed": False,
        "cross_product_allowed": False,
        "independent_projection_value_allowed": False,
    }:
        _fail("trace_contract_projection_invalid")
    event_context = _object(
        contract["event_context"],
        {
            "status",
            "root_path",
            "bundle_path",
            "bundle_sha256",
            "profile_path",
            "profile_sha256",
        },
        "trace_contract_event_context_invalid",
    )
    if (
        event_context["profile_path"]
        != "standard/oges/extensions/event-ledger/0.1.0/profile.json"
        or event_context["profile_sha256"] != digests["event_ledger_profile"]
    ):
        _fail("trace_contract_event_context_invalid")
    public = _object(
        contract["public_surface"],
        {
            "real_labels_emitted",
            "real_tuples_emitted",
            "real_values_emitted",
            "real_trace_emitted",
            "page_emitted",
            "api_emitted",
        },
        "trace_contract_public_surface_invalid",
    )
    if any(public.values()):
        _fail("trace_contract_public_surface_invalid")
    forbidden = contract["forbidden_claims"]
    if (
        not isinstance(forbidden, list)
        or len(forbidden) != len(set(forbidden))
        or not {
            "causality",
            "dependency",
            "route",
            "firm",
            "vessel",
            "capacity",
            "buffer",
            "substitution",
            "disruption",
            "forecast",
            "probability",
            "advice",
            "live_state",
            "current_state",
            "all_india_coverage",
            "l1_maturity",
            "l2_maturity",
            "legal_clearance",
            "production_readiness",
            "benchmark_superiority",
        }
        <= set(forbidden)
    ):
        _fail("trace_contract_claim_boundary_invalid")
    if runtime["execution_allowed"]:
        for field in ("manifest_path", "manifest_sha256", "package_path", "package_sha256"):
            if foundry[field] is None:
                _fail("trace_contract_foundry_invalid")
        if runtime["trust_class"] != "test_generated_synthetic":
            _fail("trace_contract_runtime_invalid")
        if not rights["allowed_signer_roles"]:
            _fail("trace_contract_rights_invalid")
    else:
        if any(
            foundry[field] is not None
            for field in ("manifest_path", "manifest_sha256", "package_path", "package_sha256")
        ):
            _fail("trace_contract_foundry_invalid")
        if contract["status"] != "rights_blocked_contract_only":
            _fail("trace_contract_identity_invalid")
    return contract


def _projection_registry(
    document: dict[str, Any], implementation_sha: str
) -> dict[str, Any]:
    registry = _object(
        document,
        {"schema_version", "registry_id", "effective", "default_policy", "projections"},
        "projection_registry_invalid",
    )
    if (
        registry["schema_version"] != "0.1.0"
        or registry["registry_id"] != "oges:trace_nary_association_projection_registry"
        or registry["default_policy"] != "deny"
    ):
        _fail("projection_registry_invalid")
    _day(registry["effective"], "projection_registry_invalid")
    rows = registry["projections"]
    if not isinstance(rows, list) or len(rows) != 1:
        _fail("projection_registry_invalid")
    row = _object(
        rows[0],
        {
            "projection_id",
            "version",
            "method_id",
            "implementation_path",
            "implementation_sha256",
            "row_rule",
            "value_rule",
            "origin_rule",
            "source_fact_status",
        },
        "projection_registry_invalid",
    )
    if row != {
        "projection_id": "projection:trace.nary_identity_index",
        "version": "0.1.0",
        "method_id": "method:trace_nary_association",
        "implementation_path": "src/nary_association_trace.py",
        "implementation_sha256": implementation_sha,
        "row_rule": "one_projection_row_per_source_path_with_full_tuple_digest",
        "value_rule": "no_independent_projection_value",
        "origin_rule": "unique_exact_observation_and_trace_origin",
        "source_fact_status": "projection_not_source_fact",
    }:
        _fail("projection_registry_invalid")
    return row


def _same_file(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=True) == right.resolve(strict=True)
    except OSError:
        return False


def _trace_rights(
    *, root: Path, source_id: str, required_uses: Sequence[str], allowed_roles: set[str], as_of: datetime
) -> dict[str, Any]:
    rights_path = _safe_file(root, RIGHTS_RELATIVE.as_posix(), "trace_rights_registry_missing")
    signers_path = _safe_file(
        root, RIGHTS_SIGNERS_RELATIVE.as_posix(), "trace_rights_signers_missing"
    )
    try:
        _, signer_document, signer_sha = publication_guard._read_json(
            signers_path, "rights_signers_unreadable"
        )
        signers = publication_guard._validate_signers(signer_document)
        _, rights_document, rights_sha = publication_guard._read_json(
            rights_path, "rights_registry_unreadable"
        )
        rights = publication_guard._validate_rights_registry(rights_document, root, signers)
    except publication_guard.PublicationGuardError as exc:
        raise NaryAssociationTraceError("trace_rights_registry_invalid") from exc
    as_of_day = as_of.date()
    if _day(
        rights_document["effective"], "trace_rights_registry_effective_invalid"
    ) > as_of_day:
        _fail("trace_rights_registry_not_yet_effective")
    if _day(
        signer_document["effective"], "trace_rights_signers_effective_invalid"
    ) > as_of_day:
        _fail("trace_rights_signers_not_yet_effective")
    source = rights.get(source_id)
    if source is None or source["decision_state"] != "approved":
        _fail("trace_rights_missing")
    required = set(required_uses)
    permitted = set(source["permitted_uses"])
    if not required <= permitted:
        _fail("trace_rights_use_forbidden")
    reviewed_on = _day(source["reviewed_on"], "trace_rights_reviewed_on_invalid")
    if reviewed_on > as_of_day:
        _fail("trace_rights_decision_not_yet_effective")
    review_due = _day(source["review_due"], "trace_rights_review_due_invalid")
    if as_of_day > review_due:
        _fail("trace_rights_expired")
    signer = signers.get(source["signer_id"])
    if signer is None:
        _fail("trace_rights_signer_inactive")
    signer_effective = _day(signer["effective"], "trace_rights_signer_effective_invalid")
    signer_revoked = signer["revoked_on"]
    if signer_effective > as_of_day or (
        signer_revoked is not None
        and as_of_day >= _day(signer_revoked, "trace_rights_signer_revoked_invalid")
    ):
        _fail("trace_rights_signer_inactive")
    if signer["role"] not in allowed_roles:
        _fail("trace_rights_signer_role_forbidden")
    return {
        "source_id": source_id,
        "decision_id": source["decision_id"],
        "decision_artifact_sha256": source["decision_artifact_sha256"],
        "rights_registry_sha256": rights_sha,
        "rights_signers_sha256": signer_sha,
        "required_uses": list(required_uses),
        "permitted_use_intersection": [use for use in required_uses if use in permitted],
        "signer_id": signer["signer_id"],
        "signer_role": signer["role"],
        "execution_as_of": as_of.isoformat().replace("+00:00", "Z"),
        "human_signature_is_legal_determination": False,
    }


def _json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    number = float(value)
    if not math.isfinite(number):
        _fail("trace_mass_non_finite")
    return number


def _decimal(value: object, code: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(code)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        _fail(code)
    if not number.is_finite() or number < 0:
        _fail(code)
    return number


def _tuple_sha(roles: Sequence[Mapping[str, Any]]) -> str:
    return _typed_sha(
        {
            "object_type": _TUPLE_WRAPPER_TYPE,
            "canonicalization_profile_id": _CANONICALIZATION_PROFILE_ID,
            "roles": [
            {
                "slot": role["slot"],
                "semantic_role_id": role["semantic_role_id"],
                "provider_value": role["provider_value"],
                "crosswalk_entry_id": role["crosswalk_entry_id"],
                "resolution_status": role["resolution_status"],
                "canonical_entity_id": role["canonical_entity_id"],
                "interpretation_status": role["interpretation_status"],
            }
            for role in roles
            ],
        }
    )


def _path(observation: Mapping[str, Any]) -> dict[str, Any]:
    roles = [
        {
            "slot": role["slot"],
            "semantic_role_id": role["semantic_role_id"],
            "provider_value": role["provider_value"],
            "crosswalk_entry_id": role["crosswalk_entry_id"],
            "link_status": role["resolution_status"],
            "canonical_entity_id": role["canonical_entity_id"],
            "interpretation_status": role["interpretation_status"],
        }
        for role in observation["roles"]
    ]
    missing = [
        {
            "slot": role["slot"],
            "link_status": role["resolution_status"],
            "reason_code": f"source_label_{role['resolution_status']}",
        }
        for role in observation["roles"]
        if role["resolution_status"] != "matched"
    ]
    trace_suffix = hashlib.sha256(
        f"{observation['observation_id']}|{observation['record_sha256']}".encode()
    ).hexdigest()[:24]
    return {
        "trace_id": f"path:trace.{trace_suffix}",
        "origin": {
            "observation_id": observation["observation_id"],
            "record_sha256": observation["record_sha256"],
            "frame_member_id": observation["coverage"]["frame_member_id"],
        },
        "association_kind": "historical_nary_source_association",
        "roles": roles,
        "tuple_sha256": _tuple_sha(observation["roles"]),
        "value_status": observation["value_status"],
        "measure": copy.deepcopy(observation["measure"]),
        "period": copy.deepcopy(observation["period"]),
        "time": {
            "source_observed_at": observation["observed_at"],
            "valid_period": copy.deepcopy(observation["period"]),
            "retrieval_available_at": observation["knowledge_available_at"],
            "system_compiled_at": observation["compiled_at"],
        },
        "source": copy.deepcopy(observation["source"]),
        "method": copy.deepcopy(observation["method"]),
        "typed_missing_links": missing,
        "claim_status": "source_association_only_not_dependency_or_causality",
    }


def _denominators(package: Mapping[str, Any], paths: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    bundle = package["dependency_bundle"]
    observations = bundle["observations"]
    crosswalks = bundle["crosswalks"]
    member_partition = Counter(
        entry["resolution_status"]
        for crosswalk in crosswalks
        for entry in crosswalk["entries"]
    )
    value_partition = Counter(row["value_status"] for row in observations)
    measures = [row["measure"] for row in observations if row["measure"] is not None]
    if not measures:
        _fail("trace_measure_spec_missing")
    measure_specs = {
        (row["unit"], str(row["scale_factor"]), row["denominator"])
        for row in measures
    }
    if len(measure_specs) != 1:
        _fail("trace_measure_spec_mismatch")
    unit, scale_text, denominator = next(iter(measure_specs))
    scale = _decimal(measures[0]["scale_factor"], "trace_measure_spec_mismatch")
    total_mass = sum(
        (_decimal(row["value"], "trace_measure_value_invalid") for row in measures),
        Decimal(0),
    )
    crosswalk_by_slot = {row["slot"]: row for row in crosswalks}
    occurrence_counts: dict[str, Counter[str]] = defaultdict(Counter)
    mass_counts: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {state: Decimal(0) for state in _MAPPING_STATES}
    )
    for observation in observations:
        measure = observation["measure"]
        value = (
            _decimal(measure["value"], "trace_measure_value_invalid")
            if measure is not None
            else Decimal(0)
        )
        for role in observation["roles"]:
            slot = role["slot"]
            state = role["resolution_status"]
            occurrence_counts[slot][state] += 1
            mass_counts[slot][state] += value
    by_slot = []
    for slot in sorted(crosswalk_by_slot):
        crosswalk = crosswalk_by_slot[slot]
        observed_mass = {state: _json_number(mass_counts[slot][state]) for state in _MAPPING_STATES}
        observed_total = sum(mass_counts[slot].values(), Decimal(0))
        if observed_total != total_mass:
            _fail("trace_mass_partition_invalid")
        by_slot.append(
            {
                "slot": slot,
                "source_label_members": {
                    state: crosswalk["resolution_counts"][state] for state in _MAPPING_STATES
                },
                "cell_role_occurrences": {
                    state: occurrence_counts[slot][state] for state in _MAPPING_STATES
                },
                "observed_mass_by_mapping": observed_mass,
                "observed_mass_total": _json_number(observed_total),
            }
        )
    total_members = sum(member_partition.values())
    if total_members != sum(row["entry_count"] for row in crosswalks):
        _fail("trace_mapping_denominator_invalid")
    return {
        "source_label_members": {
            "total": total_members,
            "partition": {state: member_partition[state] for state in _MAPPING_STATES},
        },
        "joint_cells": {
            "total": len(observations),
            "value_partition": {state: value_partition[state] for state in _VALUE_STATES},
        },
        "mass": {
            "measure_status": "single_measure_spec",
            "unit": unit,
            "scale_factor": _json_number(scale),
            "denominator": denominator,
            "total_value": _json_number(total_mass),
            "value_cell_count": len(measures),
            "nonvalue_cell_count": len(observations) - len(measures),
            "by_slot": by_slot,
        },
        "paths": {"expected": len(observations), "emitted": len(paths), "omitted": 0},
    }


def _projection(
    projection_id: object, paths: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if projection_id is None:
        return {
            "status": "not_requested",
            "projection_id": None,
            "source_fact_status": "projection_not_source_fact",
            "source_path_count": len(paths),
            "projection_row_count": 0,
            "unique_origin_count": 0,
            "rows": [],
        }
    if projection_id != "projection:trace.nary_identity_index":
        _fail("trace_projection_unregistered")
    rows = [
        {
            "projection_row_id": "prjrow:"
            + hashlib.sha256(path["trace_id"].encode()).hexdigest()[:24],
            "origin_trace_id": path["trace_id"],
            "origin_observation_id": path["origin"]["observation_id"],
            "origin_record_sha256": path["origin"]["record_sha256"],
            "full_tuple_sha256": path["tuple_sha256"],
            "value_carried": False,
        }
        for path in paths
    ]
    origin_keys = {
        (row["origin_trace_id"], row["origin_observation_id"], row["origin_record_sha256"])
        for row in rows
    }
    if len(rows) != len(paths) or len(origin_keys) != len(paths):
        _fail("trace_projection_denominator_invalid")
    return {
        "status": "emitted",
        "projection_id": projection_id,
        "source_fact_status": "projection_not_source_fact",
        "source_path_count": len(paths),
        "projection_row_count": len(rows),
        "unique_origin_count": len(origin_keys),
        "rows": rows,
    }


def _context_key(reference: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        cast(str, reference["object_type"]),
        cast(str, reference["object_id"]),
        cast(str, reference["record_sha256"]),
    )


def _proof_context(
    *,
    root: Path,
    contract: Mapping[str, Any],
    request: Mapping[str, Any],
    paths: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requested = request["proof_context"]
    if requested["status"] == "not_requested":
        return [], []
    event_contract = contract["event_context"]
    if event_contract["status"] != "registered_synthetic_event_extension":
        _fail("trace_event_context_unregistered")
    event_root = _safe_dir(root, event_contract["root_path"], "trace_event_context_root_invalid")
    bundle_path = _safe_file(
        event_root, event_contract["bundle_path"], "trace_event_context_bundle_invalid"
    )
    profile_path = _safe_file(
        event_root, event_contract["profile_path"], "trace_event_context_profile_invalid"
    )
    _, captured_bundle, bundle_sha = _read_json(
        bundle_path, "trace_event_context_bundle_invalid"
    )
    if (
        bundle_sha != _sha(event_contract["bundle_sha256"], "trace_event_context_digest_invalid")
        or requested["event_bundle_sha256"] != bundle_sha
        or hashlib.sha256(profile_path.read_bytes()).hexdigest()
        != event_contract["profile_sha256"]
    ):
        _fail("trace_event_context_digest_mismatch")
    try:
        validated = event_ledger_extension.validate_bundle(
            bundle_path, root=event_root, profile_path=profile_path
        )
        if (
            validated.bundle_sha256 != bundle_sha
            or validated.document != captured_bundle
            or validated.profile.sha256 != event_contract["profile_sha256"]
        ):
            _fail("trace_event_context_validated_bytes_mismatch")
        replay = event_ledger_extension.replay_validated(
            validated,
            request["query"]["knowledge_cutoff"],
            requested["valid_on"],
        )
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise NaryAssociationTraceError("trace_event_context_invalid") from exc
    selected_release_id = replay["selected_release"]["release_id"]
    snapshot = next(
        (
            row
            for row in validated.document["snapshots"]
            if row["release_id"] == selected_release_id
        ),
        None,
    )
    if snapshot is None:
        _fail("trace_event_context_invalid")
    context_rows = [*snapshot["claims"], *snapshot["episodes"]]
    context_objects = {
        (
            row["object_type"],
            row["claim_id"] if row["object_type"] == "claim" else row["episode_id"],
            row["record_sha256"],
        ): row
        for row in context_rows
    }
    active_context_keys = {
        ("claim", row["claim_id"], row["record_sha256"])
        for row in replay["claims"]
    } | {
        ("episode", row["episode_id"], row["record_sha256"])
        for row in replay["episodes"]
    }
    context_valid_on = _day(requested["valid_on"], "trace_event_context_valid_on_invalid")
    corrections = snapshot["correction_impacts"]
    effective_predecessors: dict[str, set[tuple[str, str, str]]] = {}
    for correction in corrections:
        effective = (
            _utc(correction["valid_from"], "trace_event_context_valid_from_invalid").date()
            <= context_valid_on
        )
        effective_predecessors[correction["correction_id"]] = (
            {
                _context_key(transition["predecessor"])
                for transition in correction["transitions"]
                if transition["predecessor"]["object_type"] in {"claim", "episode"}
            }
            if effective
            else set()
        )
    eligible_predecessors = set().union(*effective_predecessors.values())
    path_by_observation = {
        path["origin"]["observation_id"]: path for path in paths
    }
    bindings = requested["bindings"]
    proof_ids = [row["proof_id"] for row in bindings]
    if len(proof_ids) != len(set(proof_ids)):
        _fail("trace_proof_binding_duplicate")
    for binding in bindings:
        if (
            binding["origin_observation_id"] not in path_by_observation
            or _context_key(binding["context_object"]) not in context_objects
        ):
            _fail("trace_proof_binding_invalid")
        context_key = _context_key(binding["context_object"])
        if context_key not in active_context_keys and context_key not in eligible_predecessors:
            _fail("trace_proof_context_not_effective")
    affected_by_proof: dict[str, list[str]] = defaultdict(list)
    correction_reports: list[dict[str, Any]] = []
    for correction in corrections:
        predecessors = effective_predecessors[correction["correction_id"]]
        effective = bool(predecessors) or (
            _utc(correction["valid_from"], "trace_event_context_valid_from_invalid").date()
            <= context_valid_on
        )
        affected_proof_ids = sorted(
            binding["proof_id"]
            for binding in bindings
            if _context_key(binding["context_object"]) in predecessors
        )
        for proof_id in affected_proof_ids:
            affected_by_proof[proof_id].append(correction["correction_id"])
        correction_reports.append(
            {
                "correction_id": correction["correction_id"],
                "correction_record_sha256": correction["record_sha256"],
                "known_at": correction["known_at"],
                "valid_from": correction["valid_from"],
                "context_valid_on": requested["valid_on"],
                "temporal_status": (
                    "effective_on_context_valid_date"
                    if effective
                    else "known_future_effective_not_applied"
                ),
                "affected_proof_ids": affected_proof_ids,
                "affected_trace_ids": [],
                "unaffected_trace_count": len(paths),
                "output_effect": (
                    "proof_invalidation_only_source_paths_immutable"
                    if effective
                    else "known_not_effective_no_output_change"
                ),
            }
        )
    proof_outputs = []
    for binding in bindings:
        correction_ids = sorted(affected_by_proof[binding["proof_id"]])
        invalidated = bool(correction_ids)
        proof_outputs.append(
            {
                "proof_id": binding["proof_id"],
                "origin_trace_id": path_by_observation[binding["origin_observation_id"]][
                    "trace_id"
                ],
                "context_object": copy.deepcopy(binding["context_object"]),
                "context_temporal_status": (
                    "superseded_predecessor_invalidated_by_effective_correction"
                    if invalidated
                    else "active_on_valid_date"
                ),
                "link_status": (
                    "invalidated_by_correction" if invalidated else "no_registered_association"
                ),
                "reason_code": (
                    "context_record_corrected" if invalidated else "no_registered_source_relation"
                ),
                "source_fact_claimed": False,
                "assumption_promoted": False,
                "affected_by_correction_ids": correction_ids,
            }
        )
    return sorted(proof_outputs, key=lambda row: row["proof_id"]), sorted(
        correction_reports, key=lambda row: row["correction_id"]
    )


def reference_status(
    *, root: Path = ROOT, profile_path: Path = PROFILE_PATH, as_of: date | None = None
) -> dict[str, Any]:
    """Return a non-value-bearing refusal for the real Ministry contract."""

    profile, documents, paths, digests, _ = _profile(root, profile_path)
    contract = _contract(
        root,
        documents["reference_contract"],
        documents["foundry_profile"],
        paths,
        digests,
    )
    effective_as_of = as_of or _day(profile["effective"], "profile_effective_invalid")
    try:
        foundry_status = source_frame_entity_foundry.reference_status(
            root=root,
            profile_path=paths["foundry_profile"],
            as_of=effective_as_of,
        )
    except source_frame_entity_foundry.SourceFrameEntityFoundryError as exc:
        raise NaryAssociationTraceError("trace_foundry_status_invalid") from exc
    if contract["runtime"]["execution_allowed"]:
        reason = "synthetic_execution_contract_installed"
    else:
        reason = "real_source_foundry_not_buildable"
    return {
        "status": "refused_contract_only",
        "reason": reason,
        "extension_id": profile["extension_id"],
        "version": profile["version"],
        "as_of": effective_as_of.isoformat(),
        "source_id": contract["foundry"]["source_id"],
        "trace_contract_sha256": digests["reference_contract"],
        "foundry_status": foundry_status["status"],
        "foundry_reason": foundry_status["reason"],
        "rights_authorized": foundry_status["rights_authorized"],
        "frame_contract_buildable": foundry_status["frame_contract_buildable"],
        "trace_execution_allowed": False,
        "real_labels_emitted": 0,
        "real_tuples_emitted": 0,
        "real_values_emitted": 0,
        "real_traces_emitted": 0,
        "pages_emitted": 0,
        "apis_emitted": 0,
        "capability_state": "contract_only",
        "authenticated_synthetic_verification_claimed": False,
        "production_trust": False,
        "legal_clearance_claimed": False,
    }


def execute_trace(
    *,
    manifest_path: Path,
    package_path: Path,
    request_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    """Execute the complete-frame trace over exact signed synthetic inputs."""

    profile, documents, paths, digests, validators = _profile(root, profile_path)
    contract = _contract(
        root,
        documents["reference_contract"],
        documents["foundry_profile"],
        paths,
        digests,
    )
    if not contract["runtime"]["execution_allowed"]:
        _fail("trace_real_source_forbidden")
    request_file = _inside_root(root, request_path, "trace_request_path_invalid")
    _, request, request_sha = _read_json(request_file, "trace_request_invalid")
    _schema_validate(validators["request_schema"], request, "trace_request_schema_invalid")
    if request["trust_class"] != contract["runtime"]["trust_class"]:
        _fail("trace_request_trust_class_invalid")
    foundry_contract = contract["foundry"]
    expected_manifest = _safe_file(
        root, foundry_contract["manifest_path"], "trace_foundry_manifest_missing"
    )
    expected_package = _safe_file(
        root, foundry_contract["package_path"], "trace_foundry_package_missing"
    )
    if not _same_file(manifest_path, expected_manifest) or not _same_file(
        package_path, expected_package
    ):
        _fail("trace_foundry_binding_mismatch")
    _, manifest, manifest_sha = _read_json(
        expected_manifest, "trace_foundry_manifest_invalid"
    )
    _, package, package_sha = _read_json(
        expected_package, "trace_foundry_package_invalid"
    )
    source_binding = request["source_binding"]
    expected_request_binding = {
        "source_id": foundry_contract["source_id"],
        "foundry_profile_sha256": foundry_contract["profile_sha256"],
        "foundry_source_contract_sha256": foundry_contract["source_contract_sha256"],
        "release_manifest_sha256": foundry_contract["manifest_sha256"],
        "foundry_package_sha256": foundry_contract["package_sha256"],
    }
    if (
        source_binding != expected_request_binding
        or manifest_sha != foundry_contract["manifest_sha256"]
        or package_sha != foundry_contract["package_sha256"]
    ):
        _fail("trace_foundry_binding_mismatch")
    implementation_sha = hashlib.sha256(
        _safe_file(root, profile["reference_implementation"]["path"], "trace_method_missing").read_bytes()
    ).hexdigest()
    _projection_registry(documents["projection_registry"], implementation_sha)
    request_semantic_sha = _typed_sha(
        {
            "object_type": "trace_nary_association_request_semantics",
            "canonicalization_profile_id": _CANONICALIZATION_PROFILE_ID,
            "request": request,
        }
    )
    execution_contract = {
        "request_transport_sha256": request_sha,
        "request_semantic_sha256": request_semantic_sha,
        "trace_profile_sha256": digests["trace_profile"],
        "trace_reference_contract_sha256": digests["reference_contract"],
        "trace_request_schema_sha256": digests["request_schema"],
        "trace_output_schema_sha256": digests["output_schema"],
        "projection_registry_sha256": digests["projection_registry"],
        "canonicalization_profile_id": _CANONICALIZATION_PROFILE_ID,
        "canonicalization_implementation_sha256": digests[
            "canonicalization_implementation"
        ],
        "typed_record_implementation_sha256": digests[
            "typed_record_implementation"
        ],
        "canonicalization_fixture_sha256": digests["canonicalization_fixture"],
        "trace_implementation_sha256": implementation_sha,
        "foundry_profile_sha256": digests["foundry_profile"],
        "dependency_profile_sha256": digests["dependency_profile"],
        "consequence_plan_profile_sha256": digests["consequence_plan_profile"],
        "event_ledger_profile_sha256": digests["event_ledger_profile"],
    }
    try:
        foundry_result = source_frame_entity_foundry.validate_foundry_release(
            manifest_path=expected_manifest,
            package_path=expected_package,
            root=root,
            profile_path=paths["foundry_profile"],
        )
    except source_frame_entity_foundry.SourceFrameEntityFoundryError as exc:
        raise NaryAssociationTraceError(exc.code) from exc
    if (
        foundry_result.get("manifest_sha256") != manifest_sha
        or foundry_result.get("package_sha256") != package_sha
        or foundry_result.get("profile_sha256") != digests["foundry_profile"]
        or foundry_result.get("source_contract_sha256")
        != foundry_contract["source_contract_sha256"]
        or foundry_result.get("release_id") != manifest.get("release_id")
        or foundry_result.get("package_id") != package.get("package_id")
    ):
        _fail("trace_foundry_validated_bytes_mismatch")
    observations = package["dependency_bundle"]["observations"]
    if not isinstance(observations, list) or not observations:
        _fail("trace_observation_frame_empty")
    if {row["source"]["source_id"] for row in observations} != {
        foundry_contract["source_id"]
    }:
        _fail("trace_source_retargeted")
    query = request["query"]
    valid_on = _day(query["valid_on"], "trace_valid_on_invalid")
    knowledge_cutoff = _utc(query["knowledge_cutoff"], "trace_time_order_invalid")
    execution_as_of = _utc(query["execution_as_of"], "trace_time_order_invalid")
    release_generated_at = _utc(
        manifest["generated_at"], "trace_time_order_invalid"
    )
    periods = {
        json.dumps(row["period"], sort_keys=True, separators=(",", ":"))
        for row in observations
    }
    if len(periods) != 1:
        _fail("trace_period_mismatch")
    period = observations[0]["period"]
    if valid_on != _day(period["end"], "trace_period_invalid"):
        _fail("trace_time_order_invalid")
    observed_times = [
        _utc(row["observed_at"], "trace_time_order_invalid")
        for row in observations
    ]
    retrieval_times = [
        _utc(row["knowledge_available_at"], "trace_time_order_invalid")
        for row in observations
    ]
    system_times = [
        _utc(row["compiled_at"], "trace_time_order_invalid") for row in observations
    ]
    if (
        any(
            not observed < retrieval < compiled
            for observed, retrieval, compiled in _temporal_triples(
                observed_times, retrieval_times, system_times
            )
        )
        or max(retrieval_times) > knowledge_cutoff
        or knowledge_cutoff > execution_as_of
        or max(system_times) > execution_as_of
        or release_generated_at > execution_as_of
        or valid_on > knowledge_cutoff.date()
    ):
        _fail("trace_time_order_invalid")
    rights = _trace_rights(
        root=root,
        source_id=foundry_contract["source_id"],
        required_uses=profile["required_rights_uses"],
        allowed_roles=set(contract["rights"]["allowed_signer_roles"]),
        as_of=execution_as_of,
    )
    governed_rights_snapshot = {
        "source_id": rights["source_id"],
        "rights_decision_id": rights["decision_id"],
        "rights_decision_artifact_sha256": rights["decision_artifact_sha256"],
        "rights_registry_sha256": rights["rights_registry_sha256"],
        "rights_signers_sha256": rights["rights_signers_sha256"],
    }
    if any(
        {
            "source_id": observation["source"]["source_id"],
            "rights_decision_id": observation["source"]["rights_decision_id"],
            "rights_decision_artifact_sha256": observation["source"][
                "rights_decision_artifact_sha256"
            ],
            "rights_registry_sha256": observation["source"]["rights_registry_sha256"],
            "rights_signers_sha256": observation["source"]["rights_signers_sha256"],
        }
        != governed_rights_snapshot
        for observation in observations
    ):
        _fail("trace_rights_snapshot_mismatch")
    trace_paths = [_path(row) for row in observations]
    if len(trace_paths) != foundry_result["joint_cell_count"]:
        _fail("trace_path_denominator_invalid")
    denominators = _denominators(package, trace_paths)
    projection = _projection(query["projection_id"], trace_paths)
    proof_outputs, correction_reports = _proof_context(
        root=root,
        contract=contract,
        request=request,
        paths=trace_paths,
    )
    execution_identity = {
        "object_type": "trace_nary_association_execution_identity",
        "canonicalization_profile_id": _CANONICALIZATION_PROFILE_ID,
        "request_semantic_sha256": request_semantic_sha,
        "release_manifest_sha256": manifest_sha,
        "foundry_package_sha256": package_sha,
        "trace_profile_sha256": digests["trace_profile"],
        "trace_implementation_sha256": implementation_sha,
        "rights_decision_id": rights["decision_id"],
        "rights_decision_artifact_sha256": rights["decision_artifact_sha256"],
        "rights_registry_sha256": rights["rights_registry_sha256"],
        "rights_signers_sha256": rights["rights_signers_sha256"],
    }
    execution_id = "trc:" + _typed_sha(execution_identity)[:32]
    run_id = "run:trace." + _typed_sha(
        {**execution_identity, "object_type": "trace_nary_association_method_run_identity"}
    )[:24]
    result = seal_record(
        {
            "object_type": "trace_nary_association_execution",
            "schema_version": "0.1.0",
            "execution_id": execution_id,
            "trust_class": "test_generated_synthetic",
            "production_trust": False,
            "capability_state": "contract_only",
            "authenticated_synthetic_verification_claimed": False,
            "query": {"request_id": request["request_id"], **copy.deepcopy(query)},
            "execution_contract": execution_contract,
            "source_binding": {
                "source_id": foundry_contract["source_id"],
                "source_artifact_sha256": observations[0]["source"]["artifact_sha256"],
                "release_id": manifest["release_id"],
                "release_manifest_sha256": manifest_sha,
                "foundry_package_id": package["package_id"],
                "foundry_package_sha256": package_sha,
                "foundry_profile_sha256": foundry_contract["profile_sha256"],
                "foundry_source_contract_sha256": foundry_contract[
                    "source_contract_sha256"
                ],
                "row_tuple_frame_sha256": package["row_tuple_frame_sha256"],
                "joint_frame_id": observations[0]["coverage"]["joint_frame_id"],
                "joint_frame_sha256": observations[0]["coverage"]["joint_frame_sha256"],
            },
            "rights": rights,
            "method": {
                "method_id": "method:trace_nary_association",
                "version": "0.1.0",
                "implementation_path": "src/nary_association_trace.py",
                "implementation_sha256": implementation_sha,
                "projection_registry_sha256": digests["projection_registry"],
                "run_id": run_id,
            },
            "denominators": denominators,
            "paths": trace_paths,
            "projection": projection,
            "proof_outputs": proof_outputs,
            "correction_reports": correction_reports,
            "guarantees": {
                "source_tuple_decomposed": False,
                "cross_product_invented": False,
                "binary_edge_emitted": False,
                "causal_claim_emitted": False,
                "dependency_claim_emitted": False,
                "impact_claim_emitted": False,
                "forecast_emitted": False,
                "advice_emitted": False,
                "live_state_claimed": False,
                "all_india_coverage_claimed": False,
                "model_literal_accepted": False,
            },
            "limitation_codes": sorted(
                [
                    "association_not_dependency",
                    "capability_contract_only",
                    "correction_changes_proof_status_not_source_path",
                    "historical_not_live",
                    "no_all_india_coverage",
                    "no_causal_or_impact_claim",
                    "no_forecast_probability_or_advice",
                    "projection_not_source_fact",
                    "synthetic_test_fixture_only",
                    "test_keys_not_production_trust",
                ]
            ),
        }
    )
    _schema_validate(validators["output_schema"], result, "trace_output_schema_invalid")
    _record(result)
    return result


def validate_trace_output(
    *,
    manifest_path: Path,
    package_path: Path,
    request_path: Path,
    output_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    """Recompute and compare a stored trace output byte-semantically."""

    _, _, _, _, validators = _profile(root, profile_path)
    output_file = _inside_root(root, output_path, "trace_output_path_invalid")
    _, observed, observed_sha = _read_json(output_file, "trace_output_invalid")
    _schema_validate(validators["output_schema"], observed, "trace_output_schema_invalid")
    _record(observed)
    expected = execute_trace(
        manifest_path=manifest_path,
        package_path=package_path,
        request_path=request_path,
        root=root,
        profile_path=profile_path,
    )
    if observed != expected:
        _fail("trace_output_result_mismatch")
    return {
        "status": "conformant_test_generated_synthetic_trace",
        "execution_id": expected["execution_id"],
        "record_sha256": expected["record_sha256"],
        "output_file_sha256": observed_sha,
        "source_path_count": len(expected["paths"]),
        "projection_row_count": expected["projection"]["projection_row_count"],
        "proof_output_count": len(expected["proof_outputs"]),
        "correction_report_count": len(expected["correction_reports"]),
        "capability_state": "contract_only",
        "production_trust": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--validate-output", type=Path)
    args = parser.parse_args()
    profile_path = args.root / PROFILE_RELATIVE
    try:
        if args.status:
            result = reference_status(
                root=args.root, profile_path=profile_path, as_of=args.as_of
            )
        else:
            if args.manifest is None or args.package is None or args.request is None:
                parser.error("--manifest, --package and --request are required for execution")
            if args.validate_output is None:
                result = execute_trace(
                    manifest_path=args.manifest,
                    package_path=args.package,
                    request_path=args.request,
                    root=args.root,
                    profile_path=profile_path,
                )
            else:
                result = validate_trace_output(
                    manifest_path=args.manifest,
                    package_path=args.package,
                    request_path=args.request,
                    output_path=args.validate_output,
                    root=args.root,
                    profile_path=profile_path,
                )
    except NaryAssociationTraceError as exc:
        raise SystemExit(
            json.dumps({"status": "refused", "reason": exc.code}, sort_keys=True)
        ) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
