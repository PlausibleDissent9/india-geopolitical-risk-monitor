"""Validate one release-bound OGES source-frame/entity-foundry package.

The foundry composes the existing DependencyObservation, SourceLabelFrame,
EntityCrosswalkRelease, UniverseRelease, rights and canonical-release
machinery. It does not create another data platform or project n-ary source
facts into binary edges. The real Ministry reference remains contract-only
until the exact registered uses have a valid signed rights decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src import canonical_objects, dependency_observation, publication_guard

ROOT = Path(__file__).resolve().parents[1]
PROFILE_RELATIVE = Path(
    "standard/oges/extensions/source-frame-entity-foundry/0.1.0/profile.json"
)
PROFILE_PATH = ROOT / PROFILE_RELATIVE
RIGHTS_PATH = ROOT / "governance/source_rights_registry.json"
RIGHTS_SIGNERS_PATH = ROOT / "governance/rights_signers.json"
SCHEMA_REGISTRY_PATH = ROOT / "governance/canonical_schema_registry.json"
METHOD_REGISTRY_PATH = ROOT / "governance/canonical_method_registry.json"
RELEASE_SIGNERS_PATH = ROOT / "governance/release_signers.json"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VALUE_STATUSES = (
    "observed_positive",
    "observed_zero",
    "source_blank",
    "source_missing",
    "suppressed",
    "not_applicable",
)
_BOUND_KINDS = {
    "specification",
    "reference_source_contract",
    "foundry_package_schema",
    "normalization_registry",
    "dependency_profile",
    "universe_release_schema",
    "canonical_release_schema",
    "adversarial_cases",
}
_ROW_TUPLE_FIELDS = {
    "row_tuple_id",
    "country_provider_value",
    "commodity_provider_value",
    "page",
    "row",
}


class SourceFrameEntityFoundryError(ValueError):
    """Stable fail-closed foundry refusal."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise SourceFrameEntityFoundryError(code)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key")
        result[key] = value
    return result


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceFrameEntityFoundryError(code) from exc
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


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
            _fail("symlink_forbidden")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
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


def canonical_row_tuple_frame_sha256(frame: Mapping[str, Any]) -> str:
    """Hash the ordered source row-tuple frame without its self-digest."""

    projection = {
        key: frame.get(key)
        for key in ("frame_id", "status", "tuple_count", "tuples")
    }
    return hashlib.sha256(
        json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


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


def _object(value: object, fields: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _profile(
    root: Path, profile_path: Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Path], dict[str, str]]:
    canonical_profile = _safe_file(
        root, PROFILE_RELATIVE.as_posix(), "profile_trust_root_invalid"
    )
    try:
        if profile_path.resolve(strict=True) != canonical_profile:
            _fail("profile_trust_root_invalid")
    except OSError:
        _fail("profile_trust_root_invalid")
    _, profile, profile_sha = _read_json(profile_path, "profile_unreadable")
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
        or profile["extension_id"] != "oges:extension:source_frame_entity_foundry"
        or profile["version"] != "0.1.0"
        or profile["status"] != "public_draft_contract_only_real_source_rights_blocked"
    ):
        _fail("profile_identity_invalid")
    _day(profile["effective"], "profile_effective_invalid")
    rows = profile["bound_files"]
    if not isinstance(rows, list):
        _fail("profile_bound_files_invalid")
    documents: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    digests: dict[str, str] = {"profile": profile_sha}
    for raw in rows:
        row = _object(raw, {"kind", "path", "sha256"}, "profile_bound_file_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in paths:
            _fail("profile_bound_file_duplicate")
        path = _safe_file(root, row["path"], "profile_bound_file_missing")
        if kind == "specification":
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                raise SourceFrameEntityFoundryError("profile_bound_file_invalid") from exc
            document: dict[str, Any] = {}
        else:
            _, document, digest = _read_json(path, "profile_bound_file_invalid")
        if digest != _sha(row["sha256"], "profile_bound_file_digest_invalid"):
            _fail("profile_bound_file_digest_mismatch")
        documents[kind] = document
        paths[kind] = path
        digests[kind] = digest
    if set(paths) != _BOUND_KINDS:
        _fail("profile_bound_file_set_invalid")
    package_schema = documents["foundry_package_schema"]
    try:
        Draft202012Validator.check_schema(package_schema)
    except SchemaError as exc:
        raise SourceFrameEntityFoundryError("foundry_package_schema_invalid") from exc
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
    if not isinstance(profile["claim_boundary"], list) or len(profile["claim_boundary"]) < 5:
        _fail("profile_claim_boundary_invalid")
    return profile, documents, paths, digests


def _source_contract(
    root: Path,
    contract: dict[str, Any],
    contract_path: Path,
) -> dict[str, Any]:
    if set(contract) != {
        "schema_version",
        "contract_id",
        "effective",
        "status",
        "evidence_class",
        "source",
        "source_registry",
        "parser",
        "scope",
        "rights",
        "forbidden_semantics",
        "limits",
    }:
        _fail("source_contract_fields_invalid")
    if contract["schema_version"] != "0.1.0":
        _fail("source_contract_identity_invalid")
    _day(contract["effective"], "source_contract_effective_invalid")
    source = _object(
        contract["source"],
        {"source_id", "document_id", "artifact_sha256"},
        "source_contract_source_invalid",
    )
    _sha(source["artifact_sha256"], "source_contract_artifact_digest_invalid")
    registry = _object(
        contract["source_registry"], {"path", "sha256"}, "source_contract_registry_invalid"
    )
    registry_path = _safe_file(root, registry["path"], "source_registry_missing")
    _, registry_document, registry_sha = _read_json(registry_path, "source_registry_invalid")
    if registry_sha != _sha(registry["sha256"], "source_registry_digest_invalid"):
        _fail("source_registry_digest_mismatch")
    parser = _object(
        contract["parser"],
        {"method_id", "version", "path", "sha256"},
        "source_contract_parser_invalid",
    )
    parser_path = _safe_file(root, parser["path"], "source_parser_missing")
    if hashlib.sha256(parser_path.read_bytes()).hexdigest() != _sha(
        parser["sha256"], "source_parser_digest_invalid"
    ):
        _fail("source_parser_digest_mismatch")
    scope = _object(
        contract["scope"],
        {
            "flow_semantics_id",
            "provider_flow",
            "table_id",
            "pdf_pages",
            "dock_columns",
            "expected_detail_rows",
            "expected_joint_cells",
            "source_labels_status",
            "slots",
            "row_tuple_frame",
        },
        "source_contract_scope_invalid",
    )
    if (
        scope["provider_flow"] != "unloaded"
        or scope["flow_semantics_id"]
        != "flow:overseas_cargo_unloaded_at_india_major_port"
        or not isinstance(scope["pdf_pages"], list)
        or not scope["pdf_pages"]
        or any(not isinstance(item, int) or item < 1 for item in scope["pdf_pages"])
        or len(scope["pdf_pages"]) != len(set(scope["pdf_pages"]))
        or not isinstance(scope["dock_columns"], list)
        or not scope["dock_columns"]
        or len(scope["dock_columns"]) != len(set(scope["dock_columns"]))
    ):
        _fail("source_contract_scope_invalid")
    slots = scope["slots"]
    if not isinstance(slots, list) or len(slots) != 3:
        _fail("source_contract_slots_invalid")
    slot_rows: dict[str, dict[str, Any]] = {}
    for raw in slots:
        row = _object(
            raw,
            {
                "slot",
                "semantic_role_id",
                "entity_type",
                "normalization_rule_id",
                "provider_values",
            },
            "source_contract_slot_invalid",
        )
        slot = row["slot"]
        if not isinstance(slot, str) or slot in slot_rows:
            _fail("source_contract_slot_invalid")
        values = row["provider_values"]
        if values is not None and (
            not isinstance(values, list)
            or not values
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            _fail("source_contract_slot_invalid")
        slot_rows[slot] = row
    if set(slot_rows) != {"country", "commodity", "port"}:
        _fail("source_contract_slots_invalid")
    if slot_rows["port"]["provider_values"] is not None and slot_rows["port"][
        "provider_values"
    ] != scope["dock_columns"]:
        _fail("source_contract_port_frame_invalid")
    counts = (scope["expected_detail_rows"], scope["expected_joint_cells"])
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in counts):
        _fail("source_contract_denominator_invalid")
    if scope["expected_joint_cells"] != scope["expected_detail_rows"] * len(
        scope["dock_columns"]
    ):
        _fail("source_contract_denominator_invalid")
    row_frame = _object(
        scope["row_tuple_frame"],
        {"frame_id", "status", "tuple_count", "record_sha256", "tuples"},
        "source_row_tuple_frame_invalid",
    )
    if (
        not isinstance(row_frame["frame_id"], str)
        or not row_frame["frame_id"].startswith("rowframe:")
        or row_frame["tuple_count"] != scope["expected_detail_rows"]
    ):
        _fail("source_row_tuple_frame_invalid")
    tuples = row_frame["tuples"]
    if tuples is None:
        if (
            row_frame["status"] != "withheld_rights_blocked"
            or row_frame["record_sha256"] is not None
            or contract["status"] != "rights_blocked_contract_only"
        ):
            _fail("source_row_tuple_frame_invalid")
    else:
        if (
            row_frame["status"] != "enumerated"
            or not isinstance(tuples, list)
            or len(tuples) != row_frame["tuple_count"]
            or any(row["provider_values"] is None for row in slot_rows.values())
            or row_frame["record_sha256"]
            != canonical_row_tuple_frame_sha256(row_frame)
        ):
            _fail("source_row_tuple_frame_invalid")
        tuple_ids: set[str] = set()
        source_locations: set[tuple[int, int]] = set()
        tuple_countries: set[str] = set()
        tuple_commodities: set[str] = set()
        for raw in tuples:
            row = _object(raw, _ROW_TUPLE_FIELDS, "source_row_tuple_invalid")
            tuple_id = row["row_tuple_id"]
            location = (row["page"], row["row"])
            if (
                not isinstance(tuple_id, str)
                or not tuple_id.startswith("rowtuple:")
                or tuple_id in tuple_ids
                or isinstance(row["page"], bool)
                or not isinstance(row["page"], int)
                or row["page"] not in scope["pdf_pages"]
                or isinstance(row["row"], bool)
                or not isinstance(row["row"], int)
                or row["row"] < 1
                or location in source_locations
                or not isinstance(row["country_provider_value"], str)
                or not isinstance(row["commodity_provider_value"], str)
            ):
                _fail("source_row_tuple_invalid")
            tuple_ids.add(tuple_id)
            source_locations.add(location)
            tuple_countries.add(row["country_provider_value"])
            tuple_commodities.add(row["commodity_provider_value"])
        if (
            tuple_countries != set(slot_rows["country"]["provider_values"])
            or tuple_commodities != set(slot_rows["commodity"]["provider_values"])
            or slot_rows["port"]["provider_values"] != scope["dock_columns"]
        ):
            _fail("source_row_tuple_label_frame_mismatch")
    if (
        tuples is None
        or any(row["provider_values"] is None for row in slot_rows.values())
    ) and contract["status"] != "rights_blocked_contract_only":
        _fail("source_contract_frame_not_enumerated")
    rights = _object(
        contract["rights"],
        {"required_uses", "human_signature_is_legal_determination"},
        "source_contract_rights_invalid",
    )
    if (
        rights["required_uses"]
        != ["cite_metadata", "publish_derived_value", "publish_extract"]
        or rights["human_signature_is_legal_determination"] is not False
    ):
        _fail("source_contract_rights_invalid")
    if not isinstance(contract["forbidden_semantics"], list) or not isinstance(
        contract["limits"], list
    ):
        _fail("source_contract_limits_invalid")

    # The reference Ministry registry is itself hash-bound and must agree with
    # every locator and denominator asserted by this contract.
    if contract_path == ROOT / "governance/source_frame_entity_foundry.json" or source[
        "source_id"
    ] == "india_major_ports_bps_2024_25":
        try:
            implementation = registry_document["implementation"]
            artifact = registry_document["artifact"]
            port_frame = registry_document["port_frame"]
            flow = next(
                row for row in registry_document["flows"] if row["flow"] == "unloaded"
            )
        except (KeyError, StopIteration, TypeError) as exc:
            raise SourceFrameEntityFoundryError("source_registry_contract_mismatch") from exc
        if (
            registry_document["source"]["source_id"] != source["source_id"]
            or artifact["sha256"] != source["artifact_sha256"]
            or implementation["path"] != parser["path"]
            or implementation["sha256"] != parser["sha256"]
            or flow["table_id"] != scope["table_id"]
            or flow["pdf_pages"] != scope["pdf_pages"]
            or flow["expected_detail_rows"] != scope["expected_detail_rows"]
            or port_frame["columns"] != scope["dock_columns"]
            or flow["expected_detail_rows"] * port_frame["member_count"]
            != scope["expected_joint_cells"]
        ):
            _fail("source_registry_contract_mismatch")
    return contract


def _normalization_rules(document: dict[str, Any]) -> dict[str, str]:
    if set(document) != {"schema_version", "registry_id", "default_policy", "rules"} or (
        document["schema_version"] != "0.1.0" or document["default_policy"] != "deny"
    ):
        _fail("normalization_registry_invalid")
    rules: dict[str, str] = {}
    for raw in document["rules"]:
        row = _object(raw, {"rule_id", "operation", "meaning"}, "normalization_rule_invalid")
        if row["rule_id"] in rules or row["operation"] not in {
            "exact_identity",
            "unicode_nfkc_casefold_space",
        }:
            _fail("normalization_rule_invalid")
        rules[row["rule_id"]] = row["operation"]
    return rules


def _normalize(value: str, operation: str) -> str:
    if operation == "exact_identity":
        return value
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def reference_status(
    *, root: Path = ROOT, profile_path: Path = PROFILE_PATH, as_of: date | None = None
) -> dict[str, Any]:
    """Return a non-value-bearing readiness/refusal state for the real source."""

    profile, documents, paths, digests = _profile(root, profile_path)
    contract = _source_contract(
        root,
        documents["reference_source_contract"],
        paths["reference_source_contract"],
    )
    try:
        _, signer_document, signers_sha = publication_guard._read_json(
            root / RIGHTS_SIGNERS_PATH.relative_to(ROOT), "rights_signers_unreadable"
        )
        signers = publication_guard._validate_signers(signer_document)
        _, rights_document, rights_sha = publication_guard._read_json(
            root / RIGHTS_PATH.relative_to(ROOT), "rights_registry_unreadable"
        )
        rights = publication_guard._validate_rights_registry(rights_document, root, signers)
    except publication_guard.PublicationGuardError as exc:
        raise SourceFrameEntityFoundryError("rights_registry_invalid") from exc
    source = rights.get(contract["source"]["source_id"])
    effective_as_of = as_of or _day(profile["effective"], "profile_effective_invalid")
    required = set(profile["required_rights_uses"])
    registries_current = bool(
        _day(rights_document["effective"], "rights_registry_effective_invalid")
        <= effective_as_of
        and _day(signer_document["effective"], "rights_signers_effective_invalid")
        <= effective_as_of
    )
    approved = source is not None and source["decision_state"] == "approved"
    uses_approved = bool(
        source is not None
        and approved
        and required <= set(source["permitted_uses"])
    )
    decision_started = bool(
        source is not None
        and uses_approved
        and _day(source["reviewed_on"], "rights_reviewed_on_invalid")
        <= effective_as_of
    )
    decision_current = bool(
        source is not None
        and registries_current
        and uses_approved
        and decision_started
        and effective_as_of <= _day(source["review_due"], "rights_review_due_invalid")
    )
    signer = signers.get(source["signer_id"]) if source is not None and approved else None
    signer_current = bool(
        decision_current
        and signer is not None
        and _day(signer["effective"], "rights_signer_effective_invalid") <= effective_as_of
        and (
            signer["revoked_on"] is None
            or effective_as_of
            < _day(signer["revoked_on"], "rights_signer_revoked_invalid")
        )
    )
    rights_authorized = bool(decision_current and signer_current)
    frame_contract_buildable = bool(
        contract["status"] != "rights_blocked_contract_only"
        and all(row["provider_values"] is not None for row in contract["scope"]["slots"])
        and contract["scope"]["row_tuple_frame"]["status"] == "enumerated"
        and contract["scope"]["row_tuple_frame"]["tuples"] is not None
    )
    if not approved or not uses_approved:
        reason = "exact_signed_rights_decision_absent"
    elif not registries_current:
        reason = "rights_registry_not_yet_effective"
    elif not decision_started:
        reason = "rights_decision_not_yet_effective"
    elif not decision_current:
        reason = "rights_decision_expired"
    elif not signer_current:
        reason = "rights_signer_revoked_or_inactive"
    elif not frame_contract_buildable:
        reason = "source_frame_contract_not_buildable"
    else:
        reason = "signed_publication_release_absent"
    return {
        "status": "refused_contract_only",
        "reason": reason,
        "extension_id": profile["extension_id"],
        "version": profile["version"],
        "as_of": effective_as_of.isoformat(),
        "source_id": contract["source"]["source_id"],
        "source_artifact_sha256": contract["source"]["artifact_sha256"],
        "source_contract_sha256": digests["reference_source_contract"],
        "rights_registry_sha256": rights_sha,
        "rights_signers_sha256": signers_sha,
        "rights_authorized": rights_authorized,
        "frame_contract_buildable": frame_contract_buildable,
        "publication_release_eligible": False,
        "public_value_artifact_allowed": False,
        "source_label_frames_emitted": 0,
        "crosswalks_emitted": 0,
        "universe_releases_emitted": 0,
        "dependency_observations_emitted": 0,
        "binary_edges_emitted": 0,
        "capability_ceiling": "contract_only_l0",
        "legal_correctness_claimed": False,
    }


def _validate_normalizations(
    package: dict[str, Any],
    frames: Sequence[Mapping[str, Any]],
    slot_contracts: Mapping[str, Mapping[str, Any]],
    rules: Mapping[str, str],
) -> None:
    frame_by_slot = {cast(str, frame["slot"]): frame for frame in frames}
    rows = package["normalizations"]
    if len(rows) != len({row["slot"] for row in rows}) or set(frame_by_slot) != {
        row["slot"] for row in rows
    }:
        _fail("normalization_frame_set_invalid")
    for row in rows:
        slot = row["slot"]
        frame = frame_by_slot[slot]
        if row["frame_id"] != frame["frame_id"]:
            _fail("normalization_frame_binding_invalid")
        entries = row["entries"]
        by_raw = {entry["provider_value"]: entry for entry in entries}
        if len(by_raw) != len(entries) or set(by_raw) != set(frame["provider_values"]):
            _fail("normalization_frame_partition_invalid")
        expected_rule = slot_contracts[slot]["normalization_rule_id"]
        declared_normalized = [entry["normalized_value"] for entry in entries]
        if len(declared_normalized) != len(set(declared_normalized)):
            _fail("normalization_collision")
        normalized_values: list[str] = []
        for raw_label in frame["provider_values"]:
            entry = by_raw[raw_label]
            operation = rules.get(entry["rule_id"])
            if entry["rule_id"] != expected_rule or operation is None:
                _fail("normalization_rule_unregistered")
            normalized = _normalize(raw_label, operation)
            if entry["normalized_value"] != normalized:
                _fail("normalization_value_mismatch")
            normalized_values.append(normalized)
        if len(normalized_values) != len(set(normalized_values)):
            _fail("normalization_collision")


def _validate_convergences(
    package: dict[str, Any],
    crosswalks: Sequence[Mapping[str, Any]],
    evidence_ids: set[str],
) -> None:
    required: dict[tuple[str, str], set[str]] = {}
    for crosswalk in crosswalks:
        by_entity: dict[str, set[str]] = defaultdict(set)
        for entry in crosswalk["entries"]:
            if entry["resolution_status"] == "matched":
                by_entity[entry["canonical_entity_id"]].add(entry["provider_value"])
        for entity_id, provider_values in by_entity.items():
            if len(provider_values) > 1:
                required[(crosswalk["slot"], entity_id)] = provider_values
    observed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in package["canonical_convergences"]:
        key = (row["slot"], row["canonical_entity_id"])
        if key in observed:
            _fail("canonical_convergence_duplicate")
        if not set(row["evidence_ids"]) <= evidence_ids:
            _fail("canonical_convergence_evidence_missing")
        observed[key] = row
    if set(observed) != set(required):
        _fail("canonical_convergence_unregistered")
    for key, provider_values in required.items():
        row = observed[key]
        if set(row["provider_values"]) != provider_values:
            _fail("canonical_convergence_membership_invalid")


def validate_foundry_release(
    *,
    manifest_path: Path,
    package_path: Path,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
    rights_path: Path | None = None,
    rights_signers_path: Path | None = None,
    schema_registry_path: Path | None = None,
    method_registry_path: Path | None = None,
    release_signers_path: Path | None = None,
) -> dict[str, Any]:
    """Validate one signed release and its exact foundry package."""

    profile, documents, paths, digests = _profile(root, profile_path)
    contract = _source_contract(
        root,
        documents["reference_source_contract"],
        paths["reference_source_contract"],
    )
    scope = contract["scope"]
    slot_contracts = {row["slot"]: row for row in scope["slots"]}
    row_tuple_frame = scope["row_tuple_frame"]
    if (
        contract["status"] == "rights_blocked_contract_only"
        or any(row["provider_values"] is None for row in slot_contracts.values())
        or row_tuple_frame["status"] != "enumerated"
        or row_tuple_frame["tuples"] is None
    ):
        _fail("source_frame_contract_not_buildable")
    manifest_file = _inside_root(root, manifest_path, "release_manifest_missing")
    _, captured_manifest, manifest_sha = _read_json(
        manifest_file, "release_manifest_invalid"
    )
    package_file = _inside_root(root, package_path, "foundry_package_missing")
    _, package, package_sha = _read_json(package_file, "foundry_package_invalid")
    validator = Draft202012Validator(
        documents["foundry_package_schema"], format_checker=FormatChecker()
    )
    if next(validator.iter_errors(package), None) is not None:
        _fail("foundry_package_schema_invalid")
    if package["source_contract_sha256"] != digests["reference_source_contract"]:
        _fail("source_contract_digest_mismatch")
    if package["normalization_registry_sha256"] != digests["normalization_registry"]:
        _fail("normalization_registry_digest_mismatch")
    if package["row_tuple_frame_sha256"] != row_tuple_frame["record_sha256"]:
        _fail("source_row_tuple_frame_digest_mismatch")
    if any(
        row.get("flow_semantics_id") != scope["flow_semantics_id"]
        for row in package["dependency_bundle"]["observations"]
    ):
        _fail("loaded_cargo_forbidden")
    try:
        release = canonical_objects.load_validated_release(
            manifest_file,
            root=root,
            schema_registry_path=schema_registry_path
            or root / SCHEMA_REGISTRY_PATH.relative_to(ROOT),
            rights_registry_path=rights_path or root / RIGHTS_PATH.relative_to(ROOT),
            rights_signers_path=rights_signers_path
            or root / RIGHTS_SIGNERS_PATH.relative_to(ROOT),
            method_registry_path=method_registry_path
            or root / METHOD_REGISTRY_PATH.relative_to(ROOT),
            release_signers_path=release_signers_path
            or root / RELEASE_SIGNERS_PATH.relative_to(ROOT),
        )
    except canonical_objects.CanonicalObjectError as exc:
        raise SourceFrameEntityFoundryError("canonical_release_invalid") from exc
    if release.manifest != captured_manifest:
        _fail("release_manifest_validated_content_mismatch")
    objects = release.objects
    evidence = objects["evidence_item"]
    entities = objects["entity"]
    universes = objects["universe_release"]
    if objects["exposure_edge"]:
        _fail("binary_edge_release_forbidden")
    package_evidence = evidence.get(package["package_evidence_id"])
    try:
        package_relative = package_file.relative_to(root.resolve()).as_posix()
    except ValueError:
        _fail("foundry_package_missing")
    if (
        package_evidence is None
        or package_evidence["artifact_path"] != package_relative
        or package_evidence["artifact_sha256"] != package_sha
        or package_evidence["content_sha256"] != package_sha
        or package_evidence["content_availability"] != "public_extract"
        or package_evidence["rights_use"] != "publish_extract"
    ):
        _fail("foundry_package_release_binding_invalid")
    source_evidence = evidence.get(package["source_evidence_id"])
    if (
        source_evidence is None
        or source_evidence["source_id"] != contract["source"]["source_id"]
        or source_evidence["content_sha256"] != contract["source"]["artifact_sha256"]
    ):
        _fail("source_evidence_digest_mismatch")
    bundle = package["dependency_bundle"]
    known_ids = set(entities)
    if set(bundle["known_entity_ids"]) != known_ids:
        _fail("canonical_entity_release_mismatch")
    try:
        dependency_result = dependency_observation.validate_bundle(
            observations=bundle["observations"],
            frames=bundle["frames"],
            crosswalks=bundle["crosswalks"],
            known_entity_ids=known_ids,
            root=root,
            profile_path=paths["dependency_profile"],
            rights_path=rights_path or root / RIGHTS_PATH.relative_to(ROOT),
            signers_path=rights_signers_path or root / RIGHTS_SIGNERS_PATH.relative_to(ROOT),
        )
    except dependency_observation.DependencyObservationError as exc:
        raise SourceFrameEntityFoundryError(exc.code) from exc

    frames = bundle["frames"]
    crosswalks = bundle["crosswalks"]
    frame_by_slot = {frame["slot"]: frame for frame in frames}
    crosswalk_by_slot = {row["slot"]: row for row in crosswalks}
    if set(frame_by_slot) != set(slot_contracts):
        _fail("source_label_frame_set_invalid")
    parser = contract["parser"]
    for slot, slot_contract in slot_contracts.items():
        frame = frame_by_slot[slot]
        if (
            frame["source_id"] != contract["source"]["source_id"]
            or frame["source_artifact_sha256"] != contract["source"]["artifact_sha256"]
            or frame["semantic_role_id"] != slot_contract["semantic_role_id"]
            or frame["provider_values"] != slot_contract["provider_values"]
        ):
            _fail("source_label_frame_contract_mismatch")
        method = frame["extraction_method"]
        if (
            method["method_id"] != parser["method_id"]
            or method["version"] != parser["version"]
            or method["implementation_path"] != parser["path"]
            or method["implementation_sha256"] != parser["sha256"]
        ):
            _fail("source_parser_binding_invalid")

    rules = _normalization_rules(documents["normalization_registry"])
    _validate_normalizations(package, frames, slot_contracts, rules)
    _validate_convergences(package, crosswalks, set(evidence))

    bindings = package["universe_bindings"]
    if len(bindings) != len({row["slot"] for row in bindings}) or {
        row["slot"] for row in bindings
    } != set(slot_contracts):
        _fail("universe_binding_set_invalid")
    bound_universe_ids: set[str] = set()
    mapped_canonical_ids: set[str] = set()
    for binding in bindings:
        slot = binding["slot"]
        crosswalk = crosswalk_by_slot[slot]
        universe = universes.get(binding["universe_release_id"])
        if universe is None or universe["entity_type"] != slot_contracts[slot]["entity_type"]:
            _fail("universe_release_binding_invalid")
        matched_ids = {
            entry["canonical_entity_id"]
            for entry in crosswalk["entries"]
            if entry["resolution_status"] == "matched"
        }
        universe_ids = {member["entity_id"] for member in universe["members"]}
        bound_universe_ids.update(universe_ids)
        mapped_canonical_ids.update(matched_ids)
        counts = crosswalk["resolution_counts"]
        if (
            universe_ids != matched_ids
            or binding["universe_record_sha256"] != universe["record_sha256"]
            or universe["counts"]["total_eligible"] != len(matched_ids)
            or binding
            != {
                "slot": slot,
                "universe_release_id": universe["universe_release_id"],
                "universe_record_sha256": universe["record_sha256"],
                "source_label_count": frame_by_slot[slot]["member_count"],
                "matched": counts["matched"],
                "unmatched": counts["unmatched"],
                "ambiguous": counts["ambiguous"],
                "withheld": counts["withheld"],
                "canonical_member_count": len(matched_ids),
            }
        ):
            _fail("universe_denominator_mismatch")
    if known_ids != bound_universe_ids or known_ids != mapped_canonical_ids:
        _fail("unbound_release_entity")

    observations = bundle["observations"]
    expected_cells = {
        (
            row["country_provider_value"],
            row["commodity_provider_value"],
            row["page"],
            row["row"],
            port,
        )
        for row in row_tuple_frame["tuples"]
        for port in scope["dock_columns"]
    }
    observed_cells: list[tuple[str, str, int, int, str]] = []
    actual_partition = Counter(row["value_status"] for row in observations)
    for observation in observations:
        if observation["flow_semantics_id"] != scope["flow_semantics_id"]:
            _fail("loaded_cargo_forbidden")
        roles = {role["slot"]: role for role in observation["roles"]}
        locator = observation["source"]["locator"]
        observed_cells.append(
            cast(
                tuple[str, str, int, int, str],
                (
                    roles["country"]["provider_value"],
                    roles["commodity"]["provider_value"],
                    locator["page"],
                    locator["row"],
                    roles["port"]["provider_value"],
                ),
            )
        )
        if locator["document_id"] != contract["source"]["document_id"]:
            _fail("source_locator_document_invalid")
        if locator["table_id"] != scope["table_id"]:
            _fail("source_locator_table_invalid")
        if locator["page"] not in scope["pdf_pages"]:
            _fail("source_locator_page_invalid")
        if locator["column"] != roles["port"]["provider_value"] or locator[
            "column"
        ] not in scope["dock_columns"]:
            _fail("source_locator_column_invalid")
        method = observation["method"]
        if (
            method["method_id"] != parser["method_id"]
            or method["version"] != parser["version"]
            or method["implementation_path"] != parser["path"]
            or method["implementation_sha256"] != parser["sha256"]
        ):
            _fail("source_parser_binding_invalid")
    if len(observations) != scope["expected_joint_cells"]:
        _fail("joint_frame_count_mismatch")
    if len(observed_cells) != len(set(observed_cells)) or set(observed_cells) != expected_cells:
        _fail("joint_frame_membership_mismatch")
    expected_partition = {status: actual_partition[status] for status in _VALUE_STATUSES}
    coverage = package["coverage"]
    if coverage["value_partition"] != expected_partition:
        _fail("joint_frame_value_partition_mismatch")
    if coverage != {
        "row_tuple_count": scope["expected_detail_rows"],
        "dock_column_count": len(scope["dock_columns"]),
        "joint_cell_count": scope["expected_joint_cells"],
        "value_partition": expected_partition,
    }:
        _fail("joint_frame_coverage_mismatch")
    return {
        "status": "conformant_source_frame_entity_foundry_package",
        "extension_id": profile["extension_id"],
        "version": profile["version"],
        "profile_sha256": digests["profile"],
        "release_id": release.manifest["release_id"],
        "manifest_sha256": manifest_sha,
        "package_id": package["package_id"],
        "package_sha256": package_sha,
        "source_id": contract["source"]["source_id"],
        "source_contract_sha256": digests["reference_source_contract"],
        "row_tuple_frame_sha256": row_tuple_frame["record_sha256"],
        "row_tuple_count": row_tuple_frame["tuple_count"],
        "joint_cell_count": len(observations),
        "source_label_count": sum(frame["member_count"] for frame in frames),
        "unresolved_label_count": sum(
            row[status]
            for row in (crosswalk["resolution_counts"] for crosswalk in crosswalks)
            for status in ("unmatched", "ambiguous", "withheld")
        ),
        "canonical_entity_count": len(known_ids),
        "universe_release_count": len(bindings),
        "value_partition": dependency_result["value_partition"],
        "binary_edges_emitted": 0,
        "claim_boundary": "signed_synthetic_structural_conformance_not_real_dependency",
        "legal_correctness_claimed": False,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--package", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args(argv)
    profile_path = args.profile or args.root / PROFILE_RELATIVE
    try:
        if args.status:
            result = reference_status(
                root=args.root, profile_path=profile_path, as_of=args.as_of
            )
        elif args.manifest is not None and args.package is not None:
            result = validate_foundry_release(
                manifest_path=args.manifest,
                package_path=args.package,
                root=args.root,
                profile_path=profile_path,
            )
        else:
            parser.error("choose --status or provide both --manifest and --package")
    except SourceFrameEntityFoundryError as exc:
        raise SystemExit(json.dumps({"status": "refused", "reason": exc.code})) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
