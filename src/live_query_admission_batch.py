"""Materialize every admission in one registered synthetic question universe.

This layer calls only the public ``live_query_admission.admit`` API.  It does
not execute a source query or create a result.  Its purpose is to bind the full
ordered admission denominator—including refusals—into one internal record so a
later product cannot silently present a selected question as the whole set.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

from . import event_ledger, event_ledger_extension
from . import live_query_admission as admission

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "live_query_admission_batch_contract.json"
PROFILE_PATH = ROOT / "governance" / "live_query_admission_batch_profile.json"
VECTORS_PATH = ROOT / "governance" / "live_query_admission_batch_adversarial_vectors.json"
ADMISSION_CONTRACT_PATH = ROOT / "governance" / "live_query_admission_contract.json"
ADMISSION_PROFILE_PATH = ROOT / "governance" / "live_query_admission_profile.json"
ADMISSION_RUNTIME_PATH = ROOT / "src" / "live_query_admission.py"
BATCH_RUNTIME_PATH = ROOT / "src" / "live_query_admission_batch.py"

_VERSION = "0.1.0"
_PROFILE_SHA256 = "8bf870516c8f577e2385ddccbcda1e5cca56ce169c4b0e37591965d2b9cd43fe"
_NORMATIVE_PATHS = {
    "batch_contract": "governance/live_query_admission_batch_contract.json",
    "batch_vectors": "governance/live_query_admission_batch_adversarial_vectors.json",
    "admission_contract": "governance/live_query_admission_contract.json",
    "admission_profile": "governance/live_query_admission_profile.json",
    "admission_runtime": "src/live_query_admission.py",
}
_TRUST = {
    "signed": False,
    "authenticated": False,
    "synthetic": True,
    "contract_only": True,
    "source_execution_performed": False,
    "result_execution_performed": False,
    "production_authority": False,
    "public_authority": False,
    "requested_at_semantics": "caller_declared_unauthenticated",
    "record_sha256_is_authentication": False,
    "implementation_binding_authenticated": False,
}
_PROFILE_TRUST = {
    key: value for key, value in _TRUST.items() if key != "record_sha256_is_authentication"
}
_CROSS_RECEIPT_FIELDS = (
    "template_id",
    "template_record_sha256",
    "source_release_ref",
    "domain_versions",
    "requested_at",
    "binding_universe",
    "universe_size",
    "universe_digest_sha256",
    "universe_truncated",
    "rights_state_per_binding",
    "limitation_ids",
    "trust_boundary",
    "claim_boundary",
)
_RECEIPT_KEYS = (
    "object_type",
    "schema_version",
    "batch_id",
    "record_sha256",
    "implementation_binding",
    "template_id",
    "template_record_sha256",
    "source_release_ref",
    "domain_versions",
    "requested_at",
    "binding_universe",
    "binding_universe_digest_sha256",
    "universe_size",
    "universe_truncated",
    "admissions",
    "receipt_universe_root_sha256",
    "receipt_count",
    "admitted_count",
    "refused_rights_count",
    "indexes",
    "all_questions_materialized",
    "seed_member_choice_affects_batch",
    "limitation_ids",
    "trust_boundary",
    "claim_boundary",
)


class LiveQueryAdmissionBatchError(ValueError):
    """Stable fail-closed batch refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise LiveQueryAdmissionBatchError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("batch_json_duplicate_key", key)
        result[key] = value
    return result


def _parse_json(raw: bytes, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("batch_structure_invalid"),
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiveQueryAdmissionBatchError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return cast(dict[str, Any], value)


def _exact_keys(value: Mapping[str, Any], expected: Sequence[str], code: str) -> None:
    if set(value) != set(expected):
        _fail(code)


def _strict_string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _strict_int(value: object, code: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(code)
    return value


def _typed_sha(value: object) -> str:
    try:
        return event_ledger._typed_canonical_sha256(value)
    except event_ledger.EventLedgerError as exc:
        raise LiveQueryAdmissionBatchError("batch_typed_canonical_invalid", exc.code) from exc


def _seal(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], event_ledger_extension.seal_record(value))
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise LiveQueryAdmissionBatchError("batch_receipt_digest_mismatch", exc.code) from exc


def _record_sha(value: Mapping[str, Any]) -> str:
    try:
        return event_ledger_extension.typed_record_sha256(value)
    except event_ledger_extension.EventLedgerExtensionError as exc:
        raise LiveQueryAdmissionBatchError("batch_typed_canonical_invalid", exc.code) from exc


def _verify_record(value: Mapping[str, Any], code: str) -> None:
    if value.get("record_sha256") != _record_sha(value):
        _fail(code)


def serialize_record(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def _snapshot_seed(seed_binding: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(seed_binding, Mapping):
        _fail("batch_structure_invalid")
    try:
        raw = json.dumps(
            seed_binding,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as exc:
        raise LiveQueryAdmissionBatchError("batch_structure_invalid") from exc
    return _parse_json(raw, "batch_structure_invalid")


@dataclass(frozen=True)
class _FixedInputs:
    contract: dict[str, Any]
    profile: dict[str, Any]
    vectors: dict[str, Any]
    raw_sha256: dict[str, str]


def _capture_fixed_inputs() -> _FixedInputs:
    paths = {
        "batch_contract": CONTRACT_PATH,
        "profile": PROFILE_PATH,
        "batch_vectors": VECTORS_PATH,
        "admission_contract": ADMISSION_CONTRACT_PATH,
        "admission_profile": ADMISSION_PROFILE_PATH,
        "admission_runtime": ADMISSION_RUNTIME_PATH,
        "batch_runtime": BATCH_RUNTIME_PATH,
    }
    try:
        raw = {kind: path.read_bytes() for kind, path in paths.items()}
    except OSError as exc:
        raise LiveQueryAdmissionBatchError("batch_profile_drift") from exc
    digests = {kind: hashlib.sha256(value).hexdigest() for kind, value in raw.items()}
    if digests["profile"] != _PROFILE_SHA256:
        _fail("batch_profile_drift")
    fixed = _FixedInputs(
        contract=_parse_json(raw["batch_contract"], "batch_contract_drift"),
        profile=_parse_json(raw["profile"], "batch_profile_invalid"),
        vectors=_parse_json(raw["batch_vectors"], "batch_vector_registry_invalid"),
        raw_sha256=digests,
    )
    _validate_fixed_inputs(fixed)
    return fixed


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
            "batch_rule",
            "implementation_binding_rule",
            "future_product_rule",
            "trust_boundary",
            "claim_boundary",
            "active_refusal_codes",
        ),
        "batch_contract_drift",
    )
    if (
        contract["schema_version"] != _VERSION
        or contract["contract_id"] != "igrm:live-query-admission-batch:0.1.0"
        or contract["canonicalization_profile_id"] != "igrm-typed-canonical-f64-v1"
        or contract["status"] != "synthetic_contract_only"
        or contract["default_policy"] != "deny"
        or contract["public_routes"] != []
        or contract["trust_boundary"] != _TRUST
    ):
        _fail("batch_contract_drift")
    for key in (
        "input_rule",
        "batch_rule",
        "implementation_binding_rule",
        "future_product_rule",
        "claim_boundary",
    ):
        _strict_string(contract[key], "batch_contract_drift")
    codes = contract["active_refusal_codes"]
    if (
        not isinstance(codes, list)
        or not codes
        or codes != sorted(set(codes))
        or any(not isinstance(code, str) or not code for code in codes)
    ):
        _fail("batch_contract_drift")


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
            "upstream",
            "trust_boundary",
        ),
        "batch_profile_invalid",
    )
    if (
        profile["schema_version"] != _VERSION
        or profile["profile_id"] != "igrm:live-query-admission-batch-profile:0.1.0"
        or profile["effective"] != "2026-08-10"
        or profile["status"] != "synthetic_contract_only"
        or profile["default_policy"] != "deny"
        or profile["trust_boundary"] != _PROFILE_TRUST
        or profile["upstream"]
        != {
            "compiler": "src.live_query_admission.admit",
            "verifier": "src.live_query_admission.verify_admission",
            "caller_supplied_universe": False,
            "caller_supplied_order": False,
            "caller_supplied_admission": False,
        }
    ):
        _fail("batch_profile_invalid")
    rows = profile["normative_files"]
    if not isinstance(rows, list) or len(rows) != len(_NORMATIVE_PATHS):
        _fail("batch_profile_invalid")
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            _fail("batch_profile_invalid")
        _exact_keys(row, ("kind", "path", "sha256"), "batch_profile_invalid")
        kind = _strict_string(row["kind"], "batch_profile_invalid")
        if kind in seen or _NORMATIVE_PATHS.get(kind) != row["path"]:
            _fail("batch_profile_invalid")
        if fixed.raw_sha256.get(kind) != row["sha256"]:
            _fail("batch_profile_drift")
        seen.add(kind)
    if seen != set(_NORMATIVE_PATHS):
        _fail("batch_profile_invalid")


def _validate_vectors(vectors: Mapping[str, Any]) -> None:
    _exact_keys(
        vectors,
        ("schema_version", "registry_id", "default_policy", "cases"),
        "batch_vector_registry_invalid",
    )
    cases = vectors["cases"]
    if (
        vectors["schema_version"] != _VERSION
        or vectors["registry_id"] != "igrm:live-query-admission-batch-adversarial:0.1.0"
        or vectors["default_policy"] != "deny"
        or not isinstance(cases, list)
        or not cases
    ):
        _fail("batch_vector_registry_invalid")
    seen: set[str] = set()
    for row in cases:
        if not isinstance(row, dict) or set(row) not in (
            {"case_id", "expected_status"},
            {"case_id", "expected_status", "expected_reason"},
        ):
            _fail("batch_vector_registry_invalid")
        case_id = _strict_string(row["case_id"], "batch_vector_registry_invalid")
        if case_id in seen or row["expected_status"] not in ("valid", "refused"):
            _fail("batch_vector_registry_invalid")
        if row["expected_status"] == "refused" and not isinstance(row.get("expected_reason"), str):
            _fail("batch_vector_registry_invalid")
        seen.add(case_id)


def _validate_fixed_inputs(fixed: _FixedInputs) -> None:
    _validate_contract(fixed.contract)
    _validate_profile(fixed.profile, fixed)
    _validate_vectors(fixed.vectors)


def _admission_refs(receipts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "requested_index": receipt["requested_index"],
            "admission_id": receipt["admission_id"],
            "record_sha256": receipt["record_sha256"],
            "admitted": receipt["admitted"],
            "refusal_code": receipt["refusal_code"],
        }
        for receipt in receipts
    ]


def _implementation_binding(fixed: _FixedInputs) -> dict[str, str]:
    """Return exact observed bytes; these digests are provenance, not authority."""

    return {
        "batch_contract_sha256": fixed.raw_sha256["batch_contract"],
        "batch_profile_sha256": fixed.raw_sha256["profile"],
        "batch_vectors_sha256": fixed.raw_sha256["batch_vectors"],
        "batch_runtime_sha256": fixed.raw_sha256["batch_runtime"],
        "admission_contract_sha256": fixed.raw_sha256["admission_contract"],
        "admission_profile_sha256": fixed.raw_sha256["admission_profile"],
        "admission_runtime_sha256": fixed.raw_sha256["admission_runtime"],
    }


def _validate_admission_set(
    reference: Mapping[str, Any],
    universe: Sequence[Mapping[str, Any]],
    receipts: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(universe, list) or not universe:
        _fail("batch_universe_invalid")
    if reference.get("universe_digest_sha256") != _typed_sha(universe):
        _fail("batch_universe_invalid")
    if len(receipts) != len(universe) or reference.get("universe_size") != len(universe):
        _fail("batch_denominator_invalid")
    admission_ids: set[str] = set()
    record_hashes: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            _fail("batch_upstream_receipt_invalid")
        _verify_record(receipt, "batch_upstream_receipt_invalid")
        admission_id = _strict_string(receipt.get("admission_id"), "batch_upstream_receipt_invalid")
        record_hash = _strict_string(receipt.get("record_sha256"), "batch_upstream_receipt_invalid")
        if admission_id in admission_ids or record_hash in record_hashes:
            _fail("batch_duplicate_admission")
        admission_ids.add(admission_id)
        record_hashes.add(record_hash)
    for index, receipt in enumerate(receipts):
        if receipt.get("requested_index") != index:
            _fail("batch_index_invalid")
        if receipt.get("requested_arguments") != universe[index].get("arguments"):
            _fail("batch_index_invalid")
        if any(receipt.get(field) != reference.get(field) for field in _CROSS_RECEIPT_FIELDS):
            _fail("batch_snapshot_drift", f"index={index}")


def _synthesized_binding(reference: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "object_type": "argument_binding",
        "schema_version": _VERSION,
        "template_id": reference["template_id"],
        "template_record_sha256": reference["template_record_sha256"],
        "arguments": deepcopy(row["arguments"]),
        "requested_at": reference["requested_at"],
    }


def _compile_captured(seed: Mapping[str, Any], fixed: _FixedInputs) -> dict[str, Any]:
    seed_receipt = admission.admit(seed)
    universe = deepcopy(seed_receipt["binding_universe"])
    seed_index = _strict_int(seed_receipt["requested_index"], "batch_index_invalid")
    receipts: list[dict[str, Any]] = []
    for index, row in enumerate(universe):
        if index == seed_index:
            receipt = deepcopy(seed_receipt)
        else:
            receipt = admission.admit(_synthesized_binding(seed_receipt, row))
        receipts.append(receipt)
    _validate_admission_set(seed_receipt, universe, receipts)
    refs = _admission_refs(receipts)
    receipt_root = _typed_sha(refs)
    implementation_binding = _implementation_binding(fixed)
    batch_identity = {
        "template_record_sha256": seed_receipt["template_record_sha256"],
        "source_release_ref": seed_receipt["source_release_ref"],
        "domain_versions": seed_receipt["domain_versions"],
        "requested_at": seed_receipt["requested_at"],
        "binding_universe_digest_sha256": seed_receipt["universe_digest_sha256"],
        "receipt_universe_root_sha256": receipt_root,
        "implementation_binding": implementation_binding,
    }
    batch = {
        "object_type": "live_query_admission_batch",
        "schema_version": _VERSION,
        "batch_id": f"batch:live-query.{_typed_sha(batch_identity)[:32]}",
        "record_sha256": "",
        "implementation_binding": implementation_binding,
        "template_id": seed_receipt["template_id"],
        "template_record_sha256": seed_receipt["template_record_sha256"],
        "source_release_ref": seed_receipt["source_release_ref"],
        "domain_versions": seed_receipt["domain_versions"],
        "requested_at": seed_receipt["requested_at"],
        "binding_universe": universe,
        "binding_universe_digest_sha256": seed_receipt["universe_digest_sha256"],
        "universe_size": seed_receipt["universe_size"],
        "universe_truncated": seed_receipt["universe_truncated"],
        "admissions": receipts,
        "receipt_universe_root_sha256": receipt_root,
        "receipt_count": len(receipts),
        "admitted_count": sum(receipt["admitted"] is True for receipt in receipts),
        "refused_rights_count": sum(
            receipt["refusal_code"] == "admission_binding_rights_ineligible" for receipt in receipts
        ),
        "indexes": list(range(len(receipts))),
        "all_questions_materialized": True,
        "seed_member_choice_affects_batch": False,
        "limitation_ids": seed_receipt["limitation_ids"],
        "trust_boundary": fixed.contract["trust_boundary"],
        "claim_boundary": fixed.contract["claim_boundary"],
    }
    sealed = _seal(batch)
    _validate_batch_record(sealed, fixed)
    return sealed


def _validate_batch_record(batch: Mapping[str, Any], fixed: _FixedInputs) -> None:
    _exact_keys(batch, _RECEIPT_KEYS, "batch_structure_invalid")
    _verify_record(batch, "batch_receipt_digest_mismatch")
    if (
        batch["object_type"] != "live_query_admission_batch"
        or batch["schema_version"] != _VERSION
        or batch["implementation_binding"] != _implementation_binding(fixed)
        or batch["trust_boundary"] != fixed.contract["trust_boundary"]
        or batch["claim_boundary"] != fixed.contract["claim_boundary"]
        or batch["all_questions_materialized"] is not True
        or batch["seed_member_choice_affects_batch"] is not False
        or batch["universe_truncated"] is not False
    ):
        if batch.get("implementation_binding") != _implementation_binding(fixed):
            _fail("batch_implementation_binding_invalid")
        _fail("batch_structure_invalid")
    universe = batch["binding_universe"]
    receipts = batch["admissions"]
    if not isinstance(universe, list) or not isinstance(receipts, list) or not receipts:
        _fail("batch_structure_invalid")
    if batch["binding_universe_digest_sha256"] != _typed_sha(universe):
        _fail("batch_universe_invalid")
    reference = receipts[0]
    _validate_admission_set(reference, universe, receipts)
    if (
        batch["template_id"] != reference["template_id"]
        or batch["template_record_sha256"] != reference["template_record_sha256"]
        or batch["source_release_ref"] != reference["source_release_ref"]
        or batch["domain_versions"] != reference["domain_versions"]
        or batch["requested_at"] != reference["requested_at"]
        or batch["universe_size"] != len(universe)
        or batch["receipt_count"] != len(receipts)
        or batch["indexes"] != list(range(len(receipts)))
        or batch["limitation_ids"] != reference["limitation_ids"]
    ):
        _fail("batch_denominator_invalid")
    if batch["receipt_universe_root_sha256"] != _typed_sha(_admission_refs(receipts)):
        _fail("batch_receipt_root_invalid")
    admitted_count = sum(receipt["admitted"] is True for receipt in receipts)
    refused_count = sum(
        receipt["refusal_code"] == "admission_binding_rights_ineligible" for receipt in receipts
    )
    if batch["admitted_count"] != admitted_count or batch["refused_rights_count"] != refused_count:
        _fail("batch_denominator_invalid")


def compile_batch(seed_binding: Mapping[str, Any]) -> dict[str, Any]:
    """Compile all admissions in the seed's fixed registered universe."""

    seed = _snapshot_seed(seed_binding)
    fixed = _capture_fixed_inputs()
    result = _compile_captured(seed, fixed)
    after = _capture_fixed_inputs()
    if fixed.raw_sha256 != after.raw_sha256:
        _fail("batch_profile_drift")
    return result


def verify_batch(seed_binding: Mapping[str, Any], batch: Mapping[str, Any]) -> dict[str, Any]:
    """Validate internal roots, recompile from the seed and require byte equality."""

    if not isinstance(batch, Mapping):
        _fail("batch_structure_invalid")
    fixed = _capture_fixed_inputs()
    _validate_batch_record(batch, fixed)
    expected = compile_batch(seed_binding)
    if serialize_record(expected) != serialize_record(batch):
        _fail("batch_receipt_recompile_mismatch")
    return {"status": "valid", "batch_id": expected["batch_id"]}
