"""Fail-closed eligibility checks for future public analytical claims.

This is the common trust boundary specified by IGRM_MAX_SPEC.md. It does not
make an existing page compliant by existing; a publishing lane must explicitly
construct and validate a bundle before it may rely on this guard.

The guard is deliberately offline. It uses ``cryptography`` only for detached
Ed25519 signature verification and otherwise relies on the standard library.
It verifies the exact policy bytes, source-rights decision, local evidence
bytes, JSON pointer, scalar type and value, unit, denominator, uncertainty,
temporal join, freshness, registered transformation and final bundle hash. No
prose field is accepted in the bundle schema.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, Union, cast
from urllib.parse import urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
RIGHTS = ROOT / "governance" / "source_rights_registry.json"
CLAIMS = ROOT / "governance" / "claim_eligibility_contract.json"
TRANSFORMS = ROOT / "governance" / "transformation_registry.json"
SIGNERS = ROOT / "governance" / "rights_signers.json"

JsonScalar = Union[str, int, float, bool, None]

_ID = re.compile(r"^[a-z][a-z0-9_.:-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RIGHTS_USES = {
    "cite_metadata",
    "model_processing",
    "publish_derived_value",
    "publish_extract",
    "redistribute_full_record",
}
_SOURCE_STATES = {"approved", "denied", "expired", "review_required"}
_AUTHORITY_CLASSES = {
    "aggregator",
    "first_party_derived",
    "independent_reporting",
    "intergovernmental_dataset",
    "market_data",
    "official_primary",
    "provider_coded_dataset",
    "public_platform",
    "reference_data",
    "research_dataset",
}
_UNCERTAINTY = {"categorical", "interval", "not_applicable", "not_estimated"}


class PublicationGuardError(ValueError):
    """A stable fail-closed publication refusal."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise PublicationGuardError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    _fail("json_non_finite")


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(parsed, dict):
        _fail(code)
    return raw, cast(dict[str, Any], parsed), hashlib.sha256(raw).hexdigest()


def _object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _list(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail(code)
    return value


def _identifier(value: object, code: str) -> str:
    text = _text(value, code)
    if not _ID.fullmatch(text):
        _fail(code)
    return text


def _digest(value: object, code: str) -> str:
    text = _text(value, code)
    if not _SHA256.fullmatch(text):
        _fail(code)
    return text


def _day(value: object, code: str) -> date:
    text = _text(value, code)
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != text:
        _fail(code)
    return parsed


def _utc(value: object, code: str) -> datetime:
    text = _text(value, code)
    if not text.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(code)
    return parsed


def _https_or_none(value: object, code: str) -> None:
    if value is None:
        return
    text = _text(value, code)
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(ch.isspace() for ch in text)
    ):
        _fail(code)


def _scalar_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("fact_value_non_finite")
        return "number"
    if isinstance(value, str):
        return "string"
    _fail("fact_value_not_scalar")


def _same_scalar(left: object, right: object) -> bool:
    return _scalar_kind(left) == _scalar_kind(right) and left == right


def _pointer(document: object, pointer: str) -> object:
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        _fail("fact_pointer_invalid")
    current = document
    for encoded in pointer[1:].split("/"):
        if re.search(r"~(?![01])", encoded):
            _fail("fact_pointer_invalid")
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                _fail("fact_pointer_missing")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                _fail("fact_pointer_invalid")
            index = int(token)
            if index >= len(current):
                _fail("fact_pointer_missing")
            current = current[index]
        else:
            _fail("fact_pointer_missing")
    return current


def _safe_evidence_file(root: Path, relative: object) -> Path:
    text = _text(relative, "fact_source_path_invalid")
    candidate_rel = Path(text)
    if candidate_rel.is_absolute() or ".." in candidate_rel.parts or "\\" in text:
        _fail("fact_source_path_invalid")

    root_resolved = root.resolve()
    candidate = root_resolved
    for part in candidate_rel.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("fact_source_symlink_forbidden")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        _fail("fact_source_path_invalid")
    if not resolved.is_file():
        _fail("fact_source_path_invalid")
    return resolved


def _bundle_digest(bundle: Mapping[str, object]) -> str:
    unsigned = dict(bundle)
    unsigned.pop("bundle_sha256", None)
    try:
        encoded = json.dumps(
            unsigned,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("bundle_not_canonical_json")
    return hashlib.sha256(encoded).hexdigest()


def _validate_signers(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    registry = _object(
        document,
        {"schema_version", "effective", "default_policy", "signers"},
        "signer_registry_fields_invalid",
    )
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("signer_registry_policy_invalid")
    _day(registry["effective"], "signer_registry_effective_invalid")
    expected = {
        "signer_id",
        "name",
        "role",
        "public_key_ed25519_base64",
        "effective",
        "revoked_on",
    }
    result: dict[str, dict[str, Any]] = {}
    for raw in _list(registry["signers"], "signers_invalid"):
        signer = _object(raw, expected, "signer_fields_invalid")
        signer_id = _identifier(signer["signer_id"], "signer_id_invalid")
        if signer_id in result:
            _fail("signer_duplicate")
        _text(signer["name"], "signer_name_invalid")
        _text(signer["role"], "signer_role_invalid")
        public_key_text = _text(
            signer["public_key_ed25519_base64"], "signer_public_key_invalid"
        )
        try:
            public_key = base64.b64decode(public_key_text, validate=True)
            Ed25519PublicKey.from_public_bytes(public_key)
        except (binascii.Error, ValueError):
            _fail("signer_public_key_invalid")
        if len(public_key) != 32:
            _fail("signer_public_key_invalid")
        effective = _day(signer["effective"], "signer_effective_invalid")
        revoked = signer["revoked_on"]
        if revoked is not None and _day(revoked, "signer_revoked_invalid") <= effective:
            _fail("signer_revoked_invalid")
        result[signer_id] = signer
    return result


def _validate_rights_registry(
    document: dict[str, Any], root: Path, signers: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    registry = _object(
        document,
        {"schema_version", "effective", "default_policy", "sources"},
        "rights_registry_fields_invalid",
    )
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("rights_registry_policy_invalid")
    _day(registry["effective"], "rights_registry_effective_invalid")

    expected = {
        "source_id",
        "name",
        "provider",
        "role",
        "authority_class",
        "independence_group",
        "lineage_policy",
        "decision_state",
        "decision_id",
        "decision_owner",
        "signer_id",
        "decision_artifact_path",
        "decision_artifact_sha256",
        "decision_signature_path",
        "reviewed_on",
        "review_due",
        "access_url",
        "terms_url",
        "access_basis",
        "geographic_coverage",
        "historical_coverage",
        "retrieval_target",
        "outage_fallback",
        "cost_owner",
        "reproducibility_tier",
        "max_current_age_days",
        "permitted_uses",
        "notes",
    }
    result: dict[str, dict[str, Any]] = {}
    for raw in _list(registry["sources"], "rights_sources_invalid"):
        source = _object(raw, expected, "rights_source_fields_invalid")
        source_id = _identifier(source["source_id"], "rights_source_id_invalid")
        if source_id in result:
            _fail("rights_source_duplicate")
        for field in (
            "name",
            "provider",
            "role",
            "decision_id",
            "decision_owner",
            "access_basis",
            "geographic_coverage",
            "historical_coverage",
            "retrieval_target",
            "outage_fallback",
            "cost_owner",
            "reproducibility_tier",
            "notes",
        ):
            _text(source[field], f"rights_source_{field}_invalid")
        if source["authority_class"] not in _AUTHORITY_CLASSES:
            _fail("rights_source_authority_class_invalid")
        _identifier(
            source["independence_group"], "rights_source_independence_group_invalid"
        )
        state = source["decision_state"]
        if not isinstance(state, str):
            _fail("rights_source_state_invalid")
        if state not in _SOURCE_STATES:
            _fail("rights_source_state_invalid")
        if not isinstance(source["lineage_policy"], str) or source[
            "lineage_policy"
        ] not in {"bundle_declared", "primary"}:
            _fail("rights_source_lineage_policy_invalid")
        _https_or_none(source["access_url"], "rights_source_access_url_invalid")
        _https_or_none(source["terms_url"], "rights_source_terms_url_invalid")
        uses = _list(source["permitted_uses"], "rights_source_uses_invalid")
        if (
            any(not isinstance(use, str) for use in uses)
            or len(uses) != len(set(uses))
            or any(use not in _RIGHTS_USES for use in uses)
        ):
            _fail("rights_source_uses_invalid")

        reviewed = source["reviewed_on"]
        due = source["review_due"]
        age = source["max_current_age_days"]
        if state == "approved":
            reviewed_day = _day(reviewed, "rights_source_reviewed_invalid")
            due_day = _day(due, "rights_source_due_invalid")
            if due_day < reviewed_day or not uses:
                _fail("rights_source_approval_invalid")
            if isinstance(age, bool) or not isinstance(age, int) or age < 0:
                _fail("rights_source_age_invalid")
            if any(
                source[field] is None
                for field in (
                    "signer_id",
                    "decision_artifact_path",
                    "decision_artifact_sha256",
                    "decision_signature_path",
                )
            ):
                _fail("rights_source_signed_decision_required")
            signer_id = _identifier(source["signer_id"], "rights_source_signer_invalid")
            signer = signers.get(signer_id)
            if signer is None:
                _fail("rights_source_signer_unregistered")
            signer_effective = _day(signer["effective"], "signer_effective_invalid")
            signer_revoked = signer["revoked_on"]
            if signer_effective > reviewed_day or (
                signer_revoked is not None
                and reviewed_day >= _day(signer_revoked, "signer_revoked_invalid")
            ):
                _fail("rights_source_signer_inactive")
            artifact_path = _safe_evidence_file(root, source["decision_artifact_path"])
            expected_artifact_sha = _digest(
                source["decision_artifact_sha256"],
                "rights_source_decision_artifact_digest_invalid",
            )
            artifact_bytes, artifact, actual_artifact_sha = _read_json(
                artifact_path, "rights_source_decision_artifact_invalid"
            )
            if actual_artifact_sha != expected_artifact_sha:
                _fail("rights_source_decision_artifact_digest_mismatch")
            signature_path = _safe_evidence_file(root, source["decision_signature_path"])
            signature = signature_path.read_bytes()
            if len(signature) != 64:
                _fail("rights_source_decision_signature_invalid")
            try:
                public_key = base64.b64decode(
                    signer["public_key_ed25519_base64"], validate=True
                )
                Ed25519PublicKey.from_public_bytes(public_key).verify(
                    signature, artifact_bytes
                )
            except (binascii.Error, InvalidSignature, ValueError):
                _fail("rights_source_decision_signature_invalid")
            artifact = _object(
                artifact,
                {
                    "schema_version",
                    "source_id",
                    "name",
                    "provider",
                    "role",
                    "authority_class",
                    "independence_group",
                    "decision_id",
                    "decision_owner",
                    "signer_id",
                    "reviewed_on",
                    "review_due",
                    "access_url",
                    "terms_url",
                    "access_basis",
                    "lineage_policy",
                    "max_current_age_days",
                    "permitted_uses",
                    "statement",
                },
                "rights_source_decision_artifact_fields_invalid",
            )
            _text(artifact["statement"], "rights_source_decision_statement_invalid")
            matching_fields = {
                "source_id",
                "name",
                "provider",
                "role",
                "authority_class",
                "independence_group",
                "decision_id",
                "decision_owner",
                "signer_id",
                "reviewed_on",
                "review_due",
                "access_url",
                "terms_url",
                "access_basis",
                "lineage_policy",
                "max_current_age_days",
                "permitted_uses",
            }
            if artifact["schema_version"] != "1.0.0" or any(
                artifact[field] != source[field] for field in matching_fields
            ):
                _fail("rights_source_decision_artifact_mismatch")
        else:
            if (
                reviewed is not None
                or due is not None
                or age is not None
                or uses
                or source["signer_id"] is not None
                or source["decision_artifact_path"] is not None
                or source["decision_artifact_sha256"] is not None
                or source["decision_signature_path"] is not None
            ):
                _fail("rights_source_unapproved_permissions")
        result[source_id] = source
    if not result:
        _fail("rights_sources_empty")
    return result


def _validate_claim_contract(document: dict[str, Any]) -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
    contract = _object(
        document,
        {
            "schema_version",
            "effective",
            "default_policy",
            "allowed_claim_classes",
            "forbidden_claim_classes",
            "allowed_temporal_policies",
            "templates",
        },
        "claim_contract_fields_invalid",
    )
    if contract["schema_version"] != "1.0.0" or contract["default_policy"] != "deny":
        _fail("claim_contract_policy_invalid")
    _day(contract["effective"], "claim_contract_effective_invalid")
    allowed_raw = _list(contract["allowed_claim_classes"], "claim_classes_invalid")
    forbidden_raw = _list(contract["forbidden_claim_classes"], "claim_classes_invalid")
    policies_raw = _list(contract["allowed_temporal_policies"], "claim_temporal_invalid")
    if any(
        not isinstance(item, str)
        for item in allowed_raw + forbidden_raw + policies_raw
    ):
        _fail("claim_classes_invalid")
    allowed = set(allowed_raw)
    forbidden = set(forbidden_raw)
    policies = set(policies_raw)
    if not allowed or allowed & forbidden or policies != {"same_effective_date"}:
        _fail("claim_contract_policy_invalid")
    expected = {
        "template_id",
        "claim_classes",
        "min_facts",
        "max_facts",
        "required_transformations",
    }
    templates: dict[str, dict[str, Any]] = {}
    for raw in _list(contract["templates"], "claim_templates_invalid"):
        template = _object(raw, expected, "claim_template_fields_invalid")
        template_id = _identifier(template["template_id"], "claim_template_id_invalid")
        if template_id in templates:
            _fail("claim_template_duplicate")
        classes = _list(template["claim_classes"], "claim_template_classes_invalid")
        transforms = _list(
            template["required_transformations"], "claim_template_transforms_invalid"
        )
        minimum = template["min_facts"]
        maximum = template["max_facts"]
        if (
            not classes
            or any(not isinstance(item, str) for item in classes)
            or any(item not in allowed for item in classes)
            or not transforms
            or any(not isinstance(item, str) for item in transforms)
            or len(transforms) != len(set(transforms))
            or isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 1
            or maximum < minimum
        ):
            _fail("claim_template_policy_invalid")
        templates[template_id] = template
    if not templates:
        _fail("claim_templates_empty")
    return allowed, policies, templates


def _validate_transform_registry(
    document: dict[str, Any], root: Path
) -> dict[tuple[str, str], dict[str, Any]]:
    registry = _object(
        document,
        {"schema_version", "effective", "default_policy", "transformations"},
        "transform_registry_fields_invalid",
    )
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("transform_registry_policy_invalid")
    _day(registry["effective"], "transform_registry_effective_invalid")
    expected = {
        "transformation_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "claim_classes",
        "effective",
        "superseded_on",
    }
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in _list(registry["transformations"], "transformations_invalid"):
        transform = _object(raw, expected, "transformation_fields_invalid")
        transform_id = _identifier(
            transform["transformation_id"], "transformation_id_invalid"
        )
        version = _text(transform["version"], "transformation_version_invalid")
        key = (transform_id, version)
        if key in result:
            _fail("transformation_duplicate")
        path = _safe_evidence_file(root, transform["implementation_path"])
        expected_sha = _digest(
            transform["implementation_sha256"], "transformation_digest_invalid"
        )
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            _fail("transformation_implementation_drift")
        classes = _list(transform["claim_classes"], "transformation_classes_invalid")
        if not classes or any(not isinstance(item, str) for item in classes):
            _fail("transformation_classes_invalid")
        _day(transform["effective"], "transformation_effective_invalid")
        if transform["superseded_on"] is not None:
            _day(transform["superseded_on"], "transformation_superseded_invalid")
        result[key] = transform
    if not result:
        _fail("transformations_empty")
    return result


def _validate_uncertainty(raw: object, value: JsonScalar, value_kind: str) -> None:
    uncertainty = _object(
        raw,
        {"status", "meaning", "lower", "upper"},
        "fact_uncertainty_fields_invalid",
    )
    status = uncertainty["status"]
    if status not in _UNCERTAINTY:
        _fail("fact_uncertainty_status_invalid")
    _text(uncertainty["meaning"], "fact_uncertainty_meaning_invalid")
    lower = uncertainty["lower"]
    upper = uncertainty["upper"]
    if status == "interval":
        if value_kind not in {"integer", "number"}:
            _fail("fact_uncertainty_interval_type_invalid")
        if (
            isinstance(lower, bool)
            or isinstance(upper, bool)
            or not isinstance(lower, (int, float))
            or not isinstance(upper, (int, float))
            or not math.isfinite(float(lower))
            or not math.isfinite(float(upper))
            or float(lower) > float(value)  # type: ignore[arg-type]
            or float(value) > float(upper)  # type: ignore[arg-type]
        ):
            _fail("fact_uncertainty_interval_invalid")
    elif lower is not None or upper is not None:
        _fail("fact_uncertainty_bounds_forbidden")
    if value_kind in {"integer", "number"} and status == "not_applicable":
        _fail("fact_numeric_uncertainty_required")


def validate_claim_bundle(
    bundle: Mapping[str, object],
    *,
    root: Path = ROOT,
    rights_path: Path = RIGHTS,
    signer_registry_path: Path = SIGNERS,
    claim_contract_path: Path = CLAIMS,
    transform_registry_path: Path = TRANSFORMS,
) -> dict[str, object]:
    """Validate one complete claim bundle or raise a stable refusal."""

    _, signers_doc, signers_sha = _read_json(
        signer_registry_path, "signer_registry_unreadable"
    )
    _, rights_doc, rights_sha = _read_json(rights_path, "rights_registry_unreadable")
    _, claims_doc, claims_sha = _read_json(
        claim_contract_path, "claim_contract_unreadable"
    )
    _, transforms_doc, transforms_sha = _read_json(
        transform_registry_path, "transform_registry_unreadable"
    )
    signers = _validate_signers(signers_doc)
    rights = _validate_rights_registry(rights_doc, root, signers)
    allowed_classes, temporal_policies, templates = _validate_claim_contract(claims_doc)
    registered_transforms = _validate_transform_registry(transforms_doc, root)

    document = _object(
        dict(bundle),
        {
            "schema_version",
            "claim_id",
            "claim_class",
            "template_id",
            "as_of",
            "generated_at",
            "temporal_policy",
            "policy",
            "facts",
            "transformations",
            "bundle_sha256",
        },
        "bundle_fields_invalid",
    )
    if document["schema_version"] != "1.0.0":
        _fail("bundle_schema_unsupported")
    claim_id = _identifier(document["claim_id"], "claim_id_invalid")
    claim_class = _text(document["claim_class"], "claim_class_invalid")
    if claim_class not in allowed_classes:
        _fail("claim_class_unlicensed")
    template_id = _identifier(document["template_id"], "claim_template_id_invalid")
    if template_id not in templates:
        _fail("claim_template_unregistered")
    template = templates[template_id]
    if claim_class not in template["claim_classes"]:
        _fail("claim_template_class_mismatch")
    as_of = _day(document["as_of"], "claim_as_of_invalid")
    generated_at = _utc(document["generated_at"], "claim_generated_at_invalid")
    if generated_at.date() < as_of:
        _fail("claim_generated_before_as_of")
    temporal_policy = _text(document["temporal_policy"], "claim_temporal_policy_invalid")
    if temporal_policy not in temporal_policies:
        _fail("claim_temporal_policy_unlicensed")

    policy = _object(
        document["policy"],
        {
            "rights_registry_sha256",
            "rights_signers_sha256",
            "claim_contract_sha256",
            "transformation_registry_sha256",
        },
        "bundle_policy_fields_invalid",
    )
    expected_policy = {
        "rights_registry_sha256": rights_sha,
        "rights_signers_sha256": signers_sha,
        "claim_contract_sha256": claims_sha,
        "transformation_registry_sha256": transforms_sha,
    }
    for field, expected in expected_policy.items():
        if _digest(policy[field], "bundle_policy_digest_invalid") != expected:
            _fail("bundle_policy_digest_mismatch")

    transforms = _list(document["transformations"], "bundle_transformations_invalid")
    transform_fields = {"transformation_id", "version", "implementation_sha256"}
    seen_transforms: set[str] = set()
    for raw in transforms:
        item = _object(raw, transform_fields, "bundle_transformation_fields_invalid")
        transform_id = _identifier(
            item["transformation_id"], "bundle_transformation_id_invalid"
        )
        version = _text(item["version"], "bundle_transformation_version_invalid")
        if transform_id in seen_transforms:
            _fail("bundle_transformation_duplicate")
        seen_transforms.add(transform_id)
        registered = registered_transforms.get((transform_id, version))
        if registered is None:
            _fail("bundle_transformation_unregistered")
        if claim_class not in registered["claim_classes"]:
            _fail("bundle_transformation_class_mismatch")
        if (
            _digest(item["implementation_sha256"], "bundle_transformation_digest_invalid")
            != registered["implementation_sha256"]
        ):
            _fail("bundle_transformation_digest_mismatch")
        superseded = registered["superseded_on"]
        if superseded is not None and as_of >= _day(
            superseded, "transformation_superseded_invalid"
        ):
            _fail("bundle_transformation_superseded")
    required = set(template["required_transformations"])
    if seen_transforms != required:
        _fail("bundle_transformations_template_mismatch")

    facts = _list(document["facts"], "bundle_facts_invalid")
    if not template["min_facts"] <= len(facts) <= template["max_facts"]:
        _fail("bundle_fact_count_invalid")
    fact_fields = {
        "fact_id",
        "source_id",
        "upstream_source_ids",
        "lineage_manifest_path",
        "lineage_manifest_sha256",
        "source_path",
        "source_sha256",
        "json_pointer",
        "value",
        "value_type",
        "effective_date",
        "effective_date_pointer",
        "observed_at",
        "observed_at_pointer",
        "unit",
        "denominator",
        "rights_use",
        "uncertainty",
    }
    fact_ids: set[str] = set()
    source_ids: set[str] = set()
    for raw in facts:
        fact = _object(raw, fact_fields, "fact_fields_invalid")
        fact_id = _identifier(fact["fact_id"], "fact_id_invalid")
        if fact_id in fact_ids:
            _fail("fact_id_duplicate")
        fact_ids.add(fact_id)
        source_id = _identifier(fact["source_id"], "fact_source_id_invalid")
        source_ids.add(source_id)
        source = rights.get(source_id)
        if source is None:
            _fail("fact_source_unregistered")
        if source["decision_state"] != "approved":
            _fail("fact_source_not_approved")
        if generated_at.date() > _day(source["review_due"], "rights_source_due_invalid"):
            _fail("fact_source_rights_expired")
        rights_use = fact["rights_use"]
        if rights_use not in source["permitted_uses"]:
            _fail("fact_rights_use_forbidden")
        upstream_ids = _list(fact["upstream_source_ids"], "fact_upstream_sources_invalid")
        if (
            any(not isinstance(item, str) for item in upstream_ids)
            or len(upstream_ids) != len(set(upstream_ids))
            or source_id in upstream_ids
        ):
            _fail("fact_upstream_sources_invalid")
        if source["lineage_policy"] == "bundle_declared" and not upstream_ids:
            _fail("fact_upstream_sources_required")
        if source["lineage_policy"] == "primary" and upstream_ids:
            _fail("fact_upstream_sources_forbidden")
        manifest_path_raw = fact["lineage_manifest_path"]
        manifest_sha_raw = fact["lineage_manifest_sha256"]
        if source["lineage_policy"] == "bundle_declared":
            if manifest_path_raw is None or manifest_sha_raw is None:
                _fail("fact_lineage_manifest_required")
            manifest_path = _safe_evidence_file(root, manifest_path_raw)
            expected_manifest_sha = _digest(
                manifest_sha_raw, "fact_lineage_manifest_digest_invalid"
            )
            _, manifest, actual_manifest_sha = _read_json(
                manifest_path, "fact_lineage_manifest_invalid"
            )
            if actual_manifest_sha != expected_manifest_sha:
                _fail("fact_lineage_manifest_digest_mismatch")
            manifest = _object(
                manifest,
                {
                    "schema_version",
                    "artifact_path",
                    "artifact_sha256",
                    "upstream_source_ids",
                },
                "fact_lineage_manifest_fields_invalid",
            )
            manifest_upstream = _list(
                manifest["upstream_source_ids"], "fact_lineage_manifest_sources_invalid"
            )
            if (
                manifest["schema_version"] != "1.0.0"
                or manifest["artifact_path"] != fact["source_path"]
                or manifest["artifact_sha256"] != fact["source_sha256"]
                or manifest_upstream != upstream_ids
            ):
                _fail("fact_lineage_manifest_mismatch")
        elif manifest_path_raw is not None or manifest_sha_raw is not None:
            _fail("fact_lineage_manifest_forbidden")
        for upstream_id in upstream_ids:
            upstream = rights.get(upstream_id)
            if upstream is None:
                _fail("fact_upstream_source_unregistered")
            if upstream["decision_state"] != "approved":
                _fail("fact_upstream_source_not_approved")
            if rights_use not in upstream["permitted_uses"]:
                _fail("fact_upstream_rights_use_forbidden")
            if generated_at.date() > _day(
                upstream["review_due"], "rights_source_due_invalid"
            ):
                _fail("fact_upstream_source_rights_expired")
            source_ids.add(upstream_id)

        evidence_path = _safe_evidence_file(root, fact["source_path"])
        expected_sha = _digest(fact["source_sha256"], "fact_source_digest_invalid")
        raw_bytes, evidence, actual_sha = _read_json(
            evidence_path, "fact_source_json_invalid"
        )
        if hashlib.sha256(raw_bytes).hexdigest() != actual_sha or actual_sha != expected_sha:
            _fail("fact_source_digest_mismatch")
        pointer = _text(fact["json_pointer"], "fact_pointer_invalid")
        source_value = _pointer(evidence, pointer)
        value = cast(JsonScalar, fact["value"])
        value_kind = _scalar_kind(value)
        if fact["value_type"] != value_kind:
            _fail("fact_value_type_mismatch")
        if not _same_scalar(value, source_value):
            _fail("fact_value_source_mismatch")

        effective_pointer = _text(
            fact["effective_date_pointer"], "fact_effective_date_pointer_invalid"
        )
        source_effective = _pointer(evidence, effective_pointer)
        if not isinstance(source_effective, str) or source_effective != fact["effective_date"]:
            _fail("fact_effective_date_source_mismatch")
        effective = _day(source_effective, "fact_effective_date_invalid")
        if temporal_policy == "same_effective_date" and effective != as_of:
            _fail("fact_temporal_join_invalid")
        observed_pointer = _text(
            fact["observed_at_pointer"], "fact_observed_at_pointer_invalid"
        )
        source_observed = _pointer(evidence, observed_pointer)
        if not isinstance(source_observed, str) or source_observed != fact["observed_at"]:
            _fail("fact_observed_at_source_mismatch")
        observed = _utc(source_observed, "fact_observed_at_invalid")
        if observed > generated_at:
            _fail("fact_observed_after_generation")
        if claim_class == "descriptive_current":
            age_days = (generated_at.date() - observed.date()).days
            if age_days < 0 or age_days > source["max_current_age_days"]:
                _fail("fact_current_evidence_stale")

        _text(fact["unit"], "fact_unit_invalid")
        _text(fact["denominator"], "fact_denominator_invalid")
        _validate_uncertainty(fact["uncertainty"], value, value_kind)

    expected_bundle_sha = _digest(document["bundle_sha256"], "bundle_digest_invalid")
    actual_bundle_sha = _bundle_digest(document)
    if expected_bundle_sha != actual_bundle_sha:
        _fail("bundle_digest_mismatch")
    return {
        "status": "eligible",
        "claim_id": claim_id,
        "bundle_sha256": actual_bundle_sha,
        "fact_ids": sorted(fact_ids),
        "source_ids": sorted(source_ids),
    }


def validate_claim_file(
    path: Path,
    *,
    root: Path = ROOT,
    rights_path: Path = RIGHTS,
    signer_registry_path: Path = SIGNERS,
    claim_contract_path: Path = CLAIMS,
    transform_registry_path: Path = TRANSFORMS,
) -> dict[str, object]:
    _, bundle, _ = _read_json(path, "bundle_unreadable")
    return validate_claim_bundle(
        bundle,
        root=root,
        rights_path=rights_path,
        signer_registry_path=signer_registry_path,
        claim_contract_path=claim_contract_path,
        transform_registry_path=transform_registry_path,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate an IGRM public claim bundle")
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        result = validate_claim_file(args.bundle)
    except PublicationGuardError as exc:
        print(json.dumps({"status": "refused", "reason": exc.code}), file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
