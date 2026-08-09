"""Validate the OGES Claim/Episode/CorrectionImpact Event Ledger extension.

This module is deliberately a sidecar over the existing Event Ledger and
``knowledge_replay`` release chain. It owns no ingestion path and never writes
canonical Events. Extension snapshots are selected by the already authenticated
knowledge receipt time, while valid time remains an independent replay input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import event_ledger, knowledge_replay, publication_guard

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = Path("standard/oges/extensions/event-ledger/0.1.0")
PROFILE_PATH = ROOT / EXTENSION / "profile.json"

_PROFILE_ID = "oges:extension:event_ledger"
_VERSION = "0.1.0"
_REGISTERED_PROMOTION_RULE = "rule:oges.event_promotion.evidence_roles_v1"
_SELECTION_RULE = "latest_separately_receipted_complete_release_at_or_before_cutoff"
_EXTENSION_TYPES = ("claim", "episode", "correction_impact")
_UNIT_IDS = event_ledger.UNIT_IDS
_HEX = set("0123456789abcdef")
_POSITIVE_EVIDENCE_STATUSES = frozenset(
    {"single_source", "independently_corroborated", "official_record"}
)
_DISRUPTION_SOURCE_ROLES = frozenset(
    {
        "official_operational_record",
        "official_statistics",
        "official_test_evidence",
        "physical_transmission",
    }
)


class EventLedgerExtensionError(ValueError):
    """Stable, fail-closed S1 refusal."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class ExtensionProfile:
    document: Mapping[str, Any]
    sha256: str
    validators: Mapping[str, Draft202012Validator]
    products_by_type: Mapping[str, frozenset[str]]


@dataclass(frozen=True)
class ValidatedExtension:
    document: Mapping[str, Any]
    profile: ExtensionProfile
    ledger: knowledge_replay.LoadedLedger
    ledger_root: Path


ObjectKey = tuple[str, str, str]


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EventLedgerExtensionError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key", key)
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventLedgerExtensionError(code, str(path)) from exc
    if not isinstance(value, dict):
        _fail(code, str(path))
    return raw, cast(dict[str, Any], value), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail(code)
    candidate = root.resolve()
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _safe_dir(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail(code)
    candidate = root.resolve()
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_dir():
        _fail(code)
    return resolved


def _inside_root(root: Path, path: Path, code: str) -> Path:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        _fail(code)
    return _safe_file(root, relative, code)


def _sha(value: object, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return value


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


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


def typed_record_sha256(document: Mapping[str, object]) -> str:
    """Hash an extension record with the Event Ledger typed projection."""

    projected = dict(document)
    projected.pop("record_sha256", None)
    try:
        return event_ledger._typed_canonical_sha256(projected)
    except event_ledger.EventLedgerError as exc:
        raise EventLedgerExtensionError("typed_record_not_canonical", exc.code) from exc


def seal_record(document: Mapping[str, object]) -> dict[str, object]:
    """Return an extension record carrying its typed, cross-runtime hash."""

    result = dict(document)
    result["record_sha256"] = typed_record_sha256(result)
    return result


def _schema_error(error: Any) -> str:
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    return f"{path or '/'}:{error.validator}"


def _validate_schema(
    document: Mapping[str, Any], validator: Draft202012Validator, code: str
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        _fail(code, _schema_error(errors[0]))
    if typed_record_sha256(document) != document.get("record_sha256"):
        _fail("typed_record_digest_mismatch", str(document.get("object_type")))


def _load_profile(root: Path, profile_path: Path) -> ExtensionProfile:
    profile_file = _inside_root(root, profile_path, "profile_missing")
    _, profile, profile_sha = _read_json(profile_file, "profile_invalid")
    expected = {
        "schema_version",
        "extension_id",
        "version",
        "effective",
        "status",
        "base_oges",
        "event_ledger",
        "knowledge_replay",
        "normative_files",
        "reference_implementation",
        "trust_boundary",
        "meaning_boundary",
    }
    if set(profile) != expected:
        _fail("profile_fields_invalid")
    if (
        profile["schema_version"] != _VERSION
        or profile["extension_id"] != _PROFILE_ID
        or profile["version"] != _VERSION
        or profile["status"] != "synthetic_nonproduction_public_draft"
    ):
        _fail("profile_identity_invalid")
    _day(profile["effective"], "profile_effective_invalid")

    bindings = (
        ("base_oges", "profile_path", "profile_sha256", "profile_base_oges_digest_mismatch"),
        ("event_ledger", "contract_path", "contract_sha256", "profile_event_ledger_digest_mismatch"),
        (
            "knowledge_replay",
            "registry_path",
            "registry_sha256",
            "profile_knowledge_replay_digest_mismatch",
        ),
    )
    for section_name, path_key, sha_key, refusal in bindings:
        section = profile.get(section_name)
        if not isinstance(section, dict):
            _fail(f"profile_{section_name}_invalid")
        path = _safe_file(root, section.get(path_key), f"profile_{section_name}_missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != _sha(
            section.get(sha_key), f"profile_{section_name}_digest_invalid"
        ):
            _fail(refusal)

    rows = profile.get("normative_files")
    if not isinstance(rows, list) or not rows:
        _fail("profile_normative_files_invalid")
    schemas: dict[str, dict[str, Any]] = {}
    paths_by_kind: dict[str, Path] = {}
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != {"kind", "path", "sha256"}:
            _fail("profile_normative_file_invalid")
        kind = raw["kind"]
        if not isinstance(kind, str) or kind in paths_by_kind:
            _fail("profile_normative_file_duplicate")
        path = _safe_file(root, raw["path"], "profile_normative_file_missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != _sha(
            raw["sha256"], "profile_normative_file_digest_invalid"
        ):
            _fail("profile_normative_file_digest_mismatch", kind)
        paths_by_kind[kind] = path
        if kind.endswith("_schema"):
            _, schema, _ = _read_json(path, "profile_schema_invalid")
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError:
                _fail("profile_schema_meta_invalid", kind)
            schemas[kind] = schema

    required_kinds = {
        "common_schema",
        "claim_schema",
        "episode_schema",
        "correction_impact_schema",
        "bundle_schema",
        "replay_schema",
        "product_dependency_registry",
        "specification",
        "adversarial_cases",
    }
    if set(paths_by_kind) != required_kinds:
        _fail("profile_normative_files_incomplete")
    resources = Registry().with_resources(
        [
            (cast(str, schema["$id"]), Resource.from_contents(schema))
            for schema in schemas.values()
        ]
    )
    validators = {
        kind: Draft202012Validator(
            schema, registry=resources, format_checker=FormatChecker()
        )
        for kind, schema in schemas.items()
        if kind != "common_schema"
    }

    implementation = profile.get("reference_implementation")
    if not isinstance(implementation, dict) or set(implementation) != {"path", "sha256"}:
        _fail("profile_implementation_invalid")
    implementation_path = _safe_file(
        root, implementation["path"], "profile_implementation_missing"
    )
    implementation_sha = hashlib.sha256(implementation_path.read_bytes()).hexdigest()
    if implementation_sha != _sha(
        implementation["sha256"], "profile_implementation_digest_invalid"
    ) or implementation_sha != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        _fail("profile_implementation_digest_mismatch")

    _, dependency_registry, _ = _read_json(
        paths_by_kind["product_dependency_registry"],
        "product_dependency_registry_invalid",
    )
    products_by_type = _validate_product_registry(dependency_registry)
    if profile.get("trust_boundary") != {
        "accepted_bundle_class": "synthetic_nonproduction",
        "production_trust": False,
        "source_rights_authority": False,
        "fixture_keys_production_forbidden": True,
    }:
        _fail("profile_trust_boundary_invalid")
    meaning = profile.get("meaning_boundary")
    if not isinstance(meaning, dict) or set(meaning) != {"pass_means", "pass_does_not_mean"}:
        _fail("profile_meaning_boundary_invalid")
    return ExtensionProfile(
        document=profile,
        sha256=profile_sha,
        validators=validators,
        products_by_type=products_by_type,
    )


def _validate_product_registry(
    document: Mapping[str, Any],
) -> dict[str, frozenset[str]]:
    if set(document) != {"schema_version", "registry_id", "default_policy", "products"}:
        _fail("product_dependency_registry_fields_invalid")
    if (
        document["schema_version"] != _VERSION
        or document["registry_id"] != "oges:event-ledger:product-dependencies"
        or document["default_policy"] != "deny"
    ):
        _fail("product_dependency_registry_identity_invalid")
    products = document["products"]
    if not isinstance(products, list) or not products:
        _fail("product_dependency_registry_entries_invalid")
    product_ids: set[str] = set()
    by_type: dict[str, set[str]] = defaultdict(set)
    for raw in products:
        if not isinstance(raw, dict) or set(raw) != {"product_id", "dependent_object_types"}:
            _fail("product_dependency_registry_entry_invalid")
        product_id = raw["product_id"]
        types = raw["dependent_object_types"]
        if (
            not isinstance(product_id, str)
            or product_id in product_ids
            or not isinstance(types, list)
            or not types
            or len(types) != len(set(types))
            or not set(types) <= {"event", "claim", "episode"}
        ):
            _fail("product_dependency_registry_entry_invalid")
        product_ids.add(product_id)
        for object_type in types:
            by_type[cast(str, object_type)].add(product_id)
    if set(by_type) != {"event", "claim", "episode"}:
        _fail("product_dependency_registry_incomplete")
    return {key: frozenset(value) for key, value in by_type.items()}


def _object_key(reference: Mapping[str, Any]) -> ObjectKey:
    return (
        cast(str, reference["object_type"]),
        cast(str, reference["object_id"]),
        cast(str, reference["record_sha256"]),
    )


def _event_key(reference: Mapping[str, Any]) -> ObjectKey:
    return (
        "event",
        cast(str, reference["event_id"]),
        cast(str, reference["record_sha256"]),
    )


def _record_reference(object_type: str, document: Mapping[str, Any]) -> dict[str, str]:
    identifier = {
        "event": "event_id",
        "claim": "claim_id",
        "episode": "episode_id",
    }[object_type]
    return {
        "object_type": object_type,
        "object_id": cast(str, document[identifier]),
        "record_sha256": cast(str, document["record_sha256"]),
    }


def _rights_for_release(
    root: Path, loaded: knowledge_replay.LoadedRelease
) -> dict[str, dict[str, Any]]:
    governance = loaded.entry["governance"]
    signers_path = _safe_file(
        root,
        governance["rights_signers"]["path"],
        "extension_rights_signers_missing",
    )
    rights_path = _safe_file(
        root,
        governance["source_rights_registry"]["path"],
        "extension_rights_registry_missing",
    )
    try:
        _, signers_document, _ = publication_guard._read_json(
            signers_path, "signer_registry_unreadable"
        )
        signers = publication_guard._validate_signers(signers_document)
        _, rights_document, _ = publication_guard._read_json(
            rights_path, "rights_registry_unreadable"
        )
        return publication_guard._validate_rights_registry(rights_document, root, signers)
    except publication_guard.PublicationGuardError as exc:
        raise EventLedgerExtensionError("extension_rights_registry_invalid", exc.code) from exc


def _base_catalogs(
    ledger: knowledge_replay.LoadedLedger, root: Path
) -> tuple[
    dict[ObjectKey, Mapping[str, Any]],
    dict[ObjectKey, set[str]],
]:
    objects: dict[ObjectKey, Mapping[str, Any]] = {}
    releases: dict[ObjectKey, set[str]] = defaultdict(set)
    for loaded in ledger.releases:
        release_id = cast(str, loaded.entry["release_id"])
        for object_type in ("event", "evidence_item"):
            for object_id, document in loaded.validated.objects[object_type].items():
                key = (object_type, object_id, cast(str, document["record_sha256"]))
                existing = objects.get(key)
                if existing is not None and existing != document:
                    _fail("base_object_record_collision", object_id)
                objects[key] = document
                releases[key].add(release_id)
    return objects, releases


def _extension_catalogs(
    snapshots: Sequence[Mapping[str, Any]],
) -> tuple[
    dict[ObjectKey, Mapping[str, Any]],
    dict[ObjectKey, set[str]],
]:
    objects: dict[ObjectKey, Mapping[str, Any]] = {}
    releases: dict[ObjectKey, set[str]] = defaultdict(set)
    for snapshot in snapshots:
        release_id = cast(str, snapshot["release_id"])
        for object_type, collection in (("claim", "claims"), ("episode", "episodes")):
            for document in snapshot[collection]:
                reference = _record_reference(object_type, document)
                key = _object_key(reference)
                objects[key] = document
                releases[key].add(release_id)
    return objects, releases


def _validate_evidence_roles(
    claim: Mapping[str, Any],
    evidence: Mapping[ObjectKey, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
) -> None:
    claim_id = cast(str, claim["claim_id"])
    links = claim["evidence_links"]
    keys = [
        ("evidence_item", link["evidence_id"], link["evidence_record_sha256"])
        for link in links
    ]
    if len(keys) != len(set(keys)):
        _fail("claim_evidence_duplicate", claim_id)
    documents: dict[ObjectKey, Mapping[str, Any]] = {}
    for key in keys:
        document = evidence.get(cast(ObjectKey, key))
        if document is None:
            _fail("claim_evidence_record_missing", claim_id)
        documents[cast(ObjectKey, key)] = document
    known_at = _utc(claim["known_at"], "claim_known_at_invalid")
    for link, key in zip(links, keys):
        observed_at = _utc(
            documents[cast(ObjectKey, key)]["observed_at"],
            "claim_evidence_observed_at_invalid",
        )
        asserted_at = _utc(link["asserted_at"], "claim_evidence_asserted_at_invalid")
        if not observed_at <= asserted_at <= known_at:
            _fail("claim_evidence_time_invalid", claim_id)

    official_links = [link for link in links if link["role"] == "official_confirmation"]
    eligible_official: list[Mapping[str, Any]] = []
    for link in official_links:
        key = ("evidence_item", link["evidence_id"], link["evidence_record_sha256"])
        document = documents[cast(ObjectKey, key)]
        source = rights.get(cast(str, document["source_id"]))
        eligible = (
            document["evidence_type"] in {"official_document", "official_statement"}
            and document["verification_status"] == "official_record"
            and source is not None
            and source["authority_class"] == "official_primary"
            and source["decision_state"] == "approved"
            and "cite_metadata" in source["permitted_uses"]
        )
        if not eligible:
            _fail("claim_official_confirmation_ineligible", claim_id)
        eligible_official.append(link)

    corroborators = [link for link in links if link["role"] == "corroborates"]
    independence_groups: list[str] = []
    for link in corroborators:
        key = ("evidence_item", link["evidence_id"], link["evidence_record_sha256"])
        document = documents[cast(ObjectKey, key)]
        source = rights.get(cast(str, document["source_id"]))
        if (
            document["verification_status"] not in _POSITIVE_EVIDENCE_STATUSES
            or document["evidence_type"]
            not in {
                "dataset_observation",
                "news_article",
                "official_document",
                "official_statement",
                "research_paper",
                "web_page",
            }
            or source is None
            or source["decision_state"] != "approved"
            or "cite_metadata" not in source["permitted_uses"]
        ):
            _fail("claim_corroboration_evidence_ineligible", claim_id)
        independence_groups.append(cast(str, source["independence_group"]))
    if len(independence_groups) != len(set(independence_groups)):
        _fail("claim_corroborator_independence_duplicate", claim_id)

    roles = {cast(str, link["role"]) for link in links}
    assertion_state = claim["assertion_state"]
    if assertion_state == "allegation" and "allegation" not in roles:
        _fail("claim_allegation_evidence_missing", claim_id)
    if assertion_state == "coded_inference" and "supports_inference" not in roles:
        _fail("claim_inference_evidence_missing", claim_id)
    # Independent corroboration can support an Event confirmation under the
    # base OGES contract, but it cannot be relabelled as an *official* Claim.
    if assertion_state == "official_confirmation" and not eligible_official:
        _fail("claim_official_confirmation_insufficient", claim_id)
    if assertion_state == "observed_disruption":
        disruption_links = [link for link in links if link["role"] == "observed_disruption"]
        eligible_disruption: list[Mapping[str, Any]] = []
        for link in disruption_links:
            key = (
                "evidence_item",
                link["evidence_id"],
                link["evidence_record_sha256"],
            )
            document = documents[cast(ObjectKey, key)]
            source = rights.get(cast(str, document["source_id"]))
            source_role_eligible = source is not None and (
                source["role"] in _DISRUPTION_SOURCE_ROLES
                or (
                    document["evidence_type"]
                    in {"official_document", "official_statement"}
                    and source["authority_class"] == "official_primary"
                )
            )
            if (
                document["evidence_type"]
                in {"dataset_observation", "official_document", "official_statement"}
                and document["verification_status"] in _POSITIVE_EVIDENCE_STATUSES
                and source_role_eligible
                and source is not None
                and source["decision_state"] == "approved"
                and "cite_metadata" in source["permitted_uses"]
            ):
                eligible_disruption.append(link)
        if len(eligible_disruption) != len(disruption_links) or not eligible_disruption:
            _fail("claim_observed_disruption_ineligible", claim_id)
    if assertion_state == "disputed" and not roles & {"contradicts", "correction"}:
        _fail("claim_dispute_evidence_missing", claim_id)
    if assertion_state == "superseded" and claim["supersedes_claim_id"] is None:
        _fail("claim_superseded_parent_missing", claim_id)


def _validate_claim_effect(
    claim: Mapping[str, Any], events: Mapping[ObjectKey, Mapping[str, Any]]
) -> None:
    claim_id = cast(str, claim["claim_id"])
    effect = claim["event_state_effect"]
    if effect["kind"] == "none":
        if any(
            effect[field] is not None
            for field in (
                "from_event",
                "to_event",
                "target_record_status",
                "authority_kind",
                "authority_id",
            )
        ):
            _fail("claim_none_effect_fields_present", claim_id)
        return
    if claim["created_by"]["kind"] == "model":
        _fail("claim_model_promotion_forbidden", claim_id)
    if any(
        effect[field] is None
        for field in (
            "from_event",
            "to_event",
            "target_record_status",
            "authority_kind",
            "authority_id",
        )
    ):
        _fail("claim_promotion_fields_missing", claim_id)
    before_ref = cast(Mapping[str, Any], effect["from_event"])
    after_ref = cast(Mapping[str, Any], effect["to_event"])
    before_key = _event_key(before_ref)
    after_key = _event_key(after_ref)
    before = events.get(before_key)
    after = events.get(after_key)
    if before is None or after is None:
        _fail("claim_promotion_event_record_missing", claim_id)
    if (
        after["lifecycle"]["supersedes_id"] != before["event_id"]
        or after["lifecycle"]["revision"] != before["lifecycle"]["revision"] + 1
        or effect["target_record_status"] != after["record_status"]
        or _event_key(claim["subject_event"]) != after_key
    ):
        _fail("claim_promotion_transition_invalid", claim_id)

    authority_kind = effect["authority_kind"]
    authority_id = effect["authority_id"]
    if authority_kind == "registered_evidence_rule":
        if authority_id != _REGISTERED_PROMOTION_RULE:
            _fail("claim_promotion_authority_invalid", claim_id)
        state = claim["assertion_state"]
        target = effect["target_record_status"]
        if not (
            (target == "confirmed" and state in {"official_confirmation", "observed_disruption"})
            or (target == "disputed" and state == "disputed")
            or (target == "withdrawn" and state == "superseded")
        ):
            _fail("claim_registered_promotion_state_invalid", claim_id)
    elif authority_kind == "named_human_authority":
        coding = after["coding"]
        named = set(coding["coder_ids"]) | set(coding["adjudicator_ids"])
        if (
            coding["status"] == "machine_candidate"
            or authority_id not in named
            or authority_id not in after["provenance"]["reviewed_by"]
        ):
            _fail("claim_named_human_authority_invalid", claim_id)
    else:
        _fail("claim_promotion_authority_invalid", claim_id)


def _validate_claim(
    claim: Mapping[str, Any],
    snapshot_available: datetime,
    events: Mapping[ObjectKey, Mapping[str, Any]],
    evidence: Mapping[ObjectKey, Mapping[str, Any]],
    rights: Mapping[str, Mapping[str, Any]],
) -> None:
    claim_id = cast(str, claim["claim_id"])
    if claim["revision"] == 1 and claim["supersedes_claim_id"] is not None:
        _fail("claim_first_revision_supersedes", claim_id)
    if claim["revision"] > 1 and claim["supersedes_claim_id"] is None:
        _fail("claim_revision_parent_missing", claim_id)
    valid_from = _utc(claim["valid_from"], "claim_valid_from_invalid")
    valid_to = (
        _utc(claim["valid_to"], "claim_valid_to_invalid")
        if claim["valid_to"] is not None
        else None
    )
    known_at = _utc(claim["known_at"], "claim_known_at_invalid")
    if (valid_to is not None and valid_to < valid_from) or known_at > snapshot_available:
        _fail("claim_bitemporal_order_invalid", claim_id)
    if _event_key(claim["subject_event"]) not in events:
        _fail("claim_subject_event_record_missing", claim_id)
    if claim["created_by"]["kind"] == "model" and claim["assertion_state"] not in {
        "allegation",
        "coded_inference",
    }:
        _fail("claim_model_truth_state_forbidden", claim_id)
    _validate_evidence_roles(claim, evidence, rights)
    _validate_claim_effect(claim, events)


def _validate_episode(
    episode: Mapping[str, Any],
    snapshot_available: datetime,
    events: Mapping[ObjectKey, Mapping[str, Any]],
    claims: Mapping[ObjectKey, Mapping[str, Any]],
) -> None:
    episode_id = cast(str, episode["episode_id"])
    if episode["revision"] == 1 and episode["supersedes_episode_id"] is not None:
        _fail("episode_first_revision_supersedes", episode_id)
    if episode["revision"] > 1 and episode["supersedes_episode_id"] is None:
        _fail("episode_revision_parent_missing", episode_id)
    valid_from = _utc(episode["valid_from"], "episode_valid_from_invalid")
    valid_to = (
        _utc(episode["valid_to"], "episode_valid_to_invalid")
        if episode["valid_to"] is not None
        else None
    )
    known_at = _utc(episode["known_at"], "episode_known_at_invalid")
    if (valid_to is not None and valid_to < valid_from) or known_at > snapshot_available:
        _fail("episode_bitemporal_order_invalid", episode_id)
    formation = episode["formation"]
    if formation["authority_kind"] == "model_clustering_proposal":
        if (
            episode["episode_state"] != "clustering_proposal"
            or any(link["role"] != "candidate_member" for link in episode["event_links"])
        ):
            _fail("episode_model_proposal_only", episode_id)
    if formation["authority_kind"] != "model_clustering_proposal":
        # The synthetic 0.1.0 profile binds neither an Episode method registry
        # nor a human-authority registry. Shape alone (an ID or digest) is not
        # authority, so these reserved formation kinds fail closed.
        _fail("episode_formation_authority_unregistered", episode_id)
    if formation["authority_kind"] != "model_clustering_proposal" and formation[
        "proposal_confidence"
    ] is not None:
        _fail("episode_nonmodel_confidence_forbidden", episode_id)
    for member in episode["claim_members"]:
        if _object_key(member) not in claims:
            _fail("episode_claim_record_missing", episode_id)
    for link in episode["event_links"]:
        if _event_key(link) not in events:
            _fail("episode_event_record_missing", episode_id)


def _validate_archive_transition(
    previous: Mapping[str, Mapping[str, Any]],
    current: Mapping[str, Mapping[str, Any]],
    *,
    object_type: str,
) -> None:
    id_field = {"claim": "claim_id", "episode": "episode_id"}[object_type]
    parent_field = {
        "claim": "supersedes_claim_id",
        "episode": "supersedes_episode_id",
    }[object_type]
    missing = set(previous) - set(current)
    if missing:
        _fail("extension_archive_object_removed", sorted(missing)[0])
    for object_id in set(previous) & set(current):
        if previous[object_id]["record_sha256"] != current[object_id]["record_sha256"]:
            _fail("extension_object_id_rewritten", object_id)
    children: dict[str, str] = {}
    for object_id, document in current.items():
        parent_id = document[parent_field]
        if parent_id is None:
            continue
        parent = current.get(parent_id)
        if parent is None:
            _fail("extension_revision_parent_missing", object_id)
        if document["revision"] != parent["revision"] + 1:
            _fail("extension_revision_not_contiguous", object_id)
        existing = children.get(parent_id)
        if existing is not None and existing != object_id:
            _fail("extension_revision_lineage_fork", parent_id)
        children[parent_id] = object_id
        if document[id_field] == parent_id:
            _fail("extension_revision_self_reference", object_id)


def _validate_cumulative_history(snapshots: Sequence[Mapping[str, Any]]) -> None:
    previous_claims: dict[str, Mapping[str, Any]] = {}
    previous_episodes: dict[str, Mapping[str, Any]] = {}
    previous_corrections: dict[str, Mapping[str, Any]] = {}
    for snapshot in snapshots:
        current_claims = {cast(str, row["claim_id"]): row for row in snapshot["claims"]}
        current_episodes = {
            cast(str, row["episode_id"]): row for row in snapshot["episodes"]
        }
        current_corrections = {
            cast(str, row["correction_id"]): row for row in snapshot["correction_impacts"]
        }
        if len(current_claims) != len(snapshot["claims"]):
            _fail("extension_claim_id_duplicate")
        if len(current_episodes) != len(snapshot["episodes"]):
            _fail("extension_episode_id_duplicate")
        if len(current_corrections) != len(snapshot["correction_impacts"]):
            _fail("extension_correction_id_duplicate")
        _validate_archive_transition(previous_claims, current_claims, object_type="claim")
        _validate_archive_transition(previous_episodes, current_episodes, object_type="episode")
        missing_corrections = set(previous_corrections) - set(current_corrections)
        if missing_corrections:
            _fail("extension_archive_correction_removed", sorted(missing_corrections)[0])
        for correction_id in set(previous_corrections) & set(current_corrections):
            if (
                previous_corrections[correction_id]["record_sha256"]
                != current_corrections[correction_id]["record_sha256"]
            ):
                _fail("extension_correction_id_rewritten", correction_id)
        previous_claims = current_claims
        previous_episodes = current_episodes
        previous_corrections = current_corrections


def _successor_matches(
    object_type: str,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    correction_id: str,
) -> bool:
    if object_type == "event":
        return bool(
            successor["lifecycle"]["supersedes_id"] == predecessor["event_id"]
            and successor["lifecycle"]["revision"]
            == predecessor["lifecycle"]["revision"] + 1
            and successor["lifecycle"]["correction_id"] == correction_id
        )
    parent_field = {
        "claim": "supersedes_claim_id",
        "episode": "supersedes_episode_id",
    }[object_type]
    return bool(
        successor[parent_field]
        == predecessor[{"claim": "claim_id", "episode": "episode_id"}[object_type]]
        and successor["revision"] == predecessor["revision"] + 1
    )


def _dependency_adjacency(
    snapshot: Mapping[str, Any],
    objects: Mapping[ObjectKey, Mapping[str, Any]],
) -> dict[ObjectKey, set[ObjectKey]]:
    adjacency: dict[ObjectKey, set[ObjectKey]] = defaultdict(set)
    claims_by_id = {cast(str, row["claim_id"]): row for row in snapshot["claims"]}
    episodes_by_id = {cast(str, row["episode_id"]): row for row in snapshot["episodes"]}
    for claim in snapshot["claims"]:
        claim_key = _object_key(_record_reference("claim", claim))
        adjacency[_event_key(claim["subject_event"])].add(claim_key)
        parent_id = claim["supersedes_claim_id"]
        if parent_id is not None:
            parent = claims_by_id[cast(str, parent_id)]
            adjacency[_object_key(_record_reference("claim", parent))].add(claim_key)
    for episode in snapshot["episodes"]:
        episode_key = _object_key(_record_reference("episode", episode))
        for member in episode["claim_members"]:
            adjacency[_object_key(member)].add(episode_key)
        for link in episode["event_links"]:
            adjacency[_event_key(link)].add(episode_key)
        parent_id = episode["supersedes_episode_id"]
        if parent_id is not None:
            parent = episodes_by_id[cast(str, parent_id)]
            adjacency[_object_key(_record_reference("episode", parent))].add(episode_key)
    referenced = set(adjacency) | {
        item for dependencies in adjacency.values() for item in dependencies
    }
    if not referenced <= set(objects):
        _fail("correction_dependency_record_missing")
    return adjacency


def _expected_blast_radius(
    correction: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    releases: Mapping[ObjectKey, set[str]],
    products_by_type: Mapping[str, frozenset[str]],
) -> dict[str, Any]:
    seeds: set[ObjectKey] = set()
    for transition in correction["transitions"]:
        seeds.add(_object_key(transition["predecessor"]))
        seeds.add(_object_key(transition["successor"]))
    adjacency = _dependency_adjacency(snapshot, objects)
    affected = set(seeds)
    pending = deque(sorted(seeds))
    while pending:
        current = pending.popleft()
        for dependent in sorted(adjacency.get(current, set())):
            if dependent not in affected:
                affected.add(dependent)
                pending.append(dependent)
    affected_objects = [
        {
            "object_type": key[0],
            "object_id": key[1],
            "record_sha256": key[2],
        }
        for key in sorted(affected)
    ]
    product_ids = sorted(
        {
            product_id
            for key in affected
            for product_id in products_by_type.get(key[0], frozenset())
        }
    )
    release_ids = sorted(
        {release_id for key in affected for release_id in releases.get(key, set())}
    )
    return {
        "affected_objects": affected_objects,
        "affected_product_ids": product_ids,
        "affected_release_ids": release_ids,
        "counts": {
            "objects": len(affected_objects),
            "products": len(product_ids),
            "releases": len(release_ids),
        },
    }


def _validate_correction(
    correction: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    snapshot_available: datetime,
    objects: Mapping[ObjectKey, Mapping[str, Any]],
    releases: Mapping[ObjectKey, set[str]],
    products_by_type: Mapping[str, frozenset[str]],
) -> None:
    correction_id = cast(str, correction["correction_id"])
    known_at = _utc(correction["known_at"], "correction_known_at_invalid")
    valid_from = _utc(correction["valid_from"], "correction_valid_from_invalid")
    if known_at > snapshot_available:
        _fail("correction_after_snapshot", correction_id)
    if len(correction["transitions"]) != len(
        {
            (
                transition["predecessor"]["object_type"],
                transition["predecessor"]["object_id"],
            )
            for transition in correction["transitions"]
        }
    ):
        _fail("correction_predecessor_duplicate", correction_id)
    for transition in correction["transitions"]:
        predecessor_key = _object_key(transition["predecessor"])
        successor_key = _object_key(transition["successor"])
        predecessor = objects.get(predecessor_key)
        successor = objects.get(successor_key)
        if predecessor is None or successor is None:
            _fail("correction_transition_record_missing", correction_id)
        if predecessor_key[0] != successor_key[0] or not _successor_matches(
            predecessor_key[0], predecessor, successor, correction_id
        ):
            _fail("correction_transition_lineage_invalid", correction_id)
        if successor_key[0] in {"claim", "episode"}:
            successor_valid_from = _utc(
                successor["valid_from"], "correction_successor_valid_from_invalid"
            )
            successor_known_at = _utc(
                successor["known_at"], "correction_successor_known_at_invalid"
            )
            if successor_valid_from != valid_from:
                _fail("correction_valid_time_mismatch", correction_id)
            if successor_known_at > known_at:
                _fail("correction_before_successor_known", correction_id)
    expected = _expected_blast_radius(
        correction, snapshot, objects, releases, products_by_type
    )
    if correction["blast_radius"] != expected:
        _fail("correction_blast_radius_mismatch", correction_id)


def _validate_count_units(
    snapshot: Mapping[str, Any], loaded: knowledge_replay.LoadedRelease
) -> None:
    units = snapshot["count_units"]
    if tuple(units) != _UNIT_IDS:
        _fail("count_unit_boundary_invalid")
    if units["aggregate_source_rows"] is not None or units[
        "deduplicated_source_events"
    ] is not None:
        _fail("count_unit_boundary_invalid")
    canonical_count = len(loaded.validated.objects["event"])
    episodes = {cast(str, row["episode_id"]): row for row in snapshot["episodes"]}
    superseded = {
        cast(str, row["supersedes_episode_id"])
        for row in episodes.values()
        if row["supersedes_episode_id"] is not None
    }
    detector_count = sum(
        row["episode_kind"] == "detector_salience_window" and episode_id not in superseded
        for episode_id, row in episodes.items()
    )
    if units["canonical_geopolitical_events"] != canonical_count or units[
        "detected_salience_episodes"
    ] != detector_count:
        _fail("count_unit_boundary_invalid")


def _validate_snapshot_identity(
    snapshot: Mapping[str, Any], loaded: knowledge_replay.LoadedRelease, sequence: int
) -> None:
    if snapshot["sequence"] != sequence:
        _fail("extension_snapshot_sequence_invalid")
    if (
        snapshot["release_id"] != loaded.entry["release_id"]
        or snapshot["release_manifest_record_sha256"]
        != loaded.entry["manifest_record_sha256"]
        or snapshot["knowledge_available_at"] != loaded.entry["available_at"]
    ):
        _fail("extension_snapshot_release_identity_mismatch")
    if snapshot["counts"] != {
        "claims": len(snapshot["claims"]),
        "episodes": len(snapshot["episodes"]),
        "correction_impacts": len(snapshot["correction_impacts"]),
    }:
        _fail("extension_snapshot_counts_mismatch")


def validate_bundle(
    bundle_path: Path,
    *,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> ValidatedExtension:
    """Validate one complete synthetic S1 sidecar against signed base releases."""

    profile = _load_profile(root, profile_path)
    bundle_file = _inside_root(root, bundle_path, "extension_bundle_missing")
    _, bundle, _ = _read_json(bundle_file, "extension_bundle_invalid")
    bundle_validator = profile.validators.get("bundle_schema")
    if bundle_validator is None:
        _fail("profile_bundle_schema_missing")
    _validate_schema(bundle, bundle_validator, "object_schema_invalid")
    if bundle["profile_sha256"] != profile.sha256:
        _fail("extension_profile_digest_mismatch")
    if bundle["trust_class"] != "synthetic_nonproduction" or bundle["production_trust"]:
        _fail("extension_production_trust_forbidden")

    base = bundle["base_ledger"]
    ledger_root = _safe_dir(root, base["root_path"], "extension_base_root_missing")
    ledger_path = _safe_file(ledger_root, base["ledger_path"], "extension_base_ledger_missing")
    replay_registry_path = _safe_file(
        ledger_root,
        base["replay_registry_path"],
        "extension_replay_registry_missing",
    )
    knowledge_signers_path = _safe_file(
        ledger_root,
        base["knowledge_signers_path"],
        "extension_knowledge_signers_missing",
    )
    if hashlib.sha256(ledger_path.read_bytes()).hexdigest() != base["ledger_file_sha256"]:
        _fail("extension_base_ledger_digest_mismatch")
    expected_replay_sha = profile.document["knowledge_replay"]["registry_sha256"]
    if (
        hashlib.sha256(replay_registry_path.read_bytes()).hexdigest()
        != base["replay_registry_sha256"]
        or base["replay_registry_sha256"] != expected_replay_sha
    ):
        _fail("extension_replay_registry_digest_mismatch")
    try:
        ledger = knowledge_replay.load_ledger(
            ledger_path,
            root=ledger_root,
            replay_registry_path=replay_registry_path,
            knowledge_signers_path=knowledge_signers_path,
        )
    except knowledge_replay.KnowledgeReplayError as exc:
        raise EventLedgerExtensionError("extension_base_ledger_invalid", exc.code) from exc

    snapshots = cast(list[Mapping[str, Any]], bundle["snapshots"])
    if len(snapshots) != len(ledger.releases):
        _fail("extension_snapshot_release_denominator_mismatch")
    _validate_cumulative_history(snapshots)
    base_objects, base_releases = _base_catalogs(ledger, ledger_root)
    extension_objects, extension_releases = _extension_catalogs(snapshots)
    all_objects = {**base_objects, **extension_objects}
    all_releases: dict[ObjectKey, set[str]] = defaultdict(set)
    for key, release_ids in (*base_releases.items(), *extension_releases.items()):
        all_releases[key].update(release_ids)

    claim_validator = profile.validators["claim_schema"]
    episode_validator = profile.validators["episode_schema"]
    correction_validator = profile.validators["correction_impact_schema"]
    for index, (snapshot, loaded) in enumerate(zip(snapshots, ledger.releases), start=1):
        _validate_snapshot_identity(snapshot, loaded, index)
        available = _utc(snapshot["knowledge_available_at"], "snapshot_available_at_invalid")
        prefix_release_ids = {
            cast(str, release.entry["release_id"]) for release in ledger.releases[:index]
        }
        prefix_objects = {
            key: value
            for key, value in all_objects.items()
            if all_releases.get(key, set()) & prefix_release_ids
        }
        prefix_releases = {
            key: release_ids & prefix_release_ids
            for key, release_ids in all_releases.items()
            if release_ids & prefix_release_ids
        }
        prefix_base_objects = {
            key: value
            for key, value in base_objects.items()
            if base_releases.get(key, set()) & prefix_release_ids
        }
        # Role eligibility is evaluated against the exact signed rights
        # registry bound to this release. A later release may not retroactively
        # authorize an earlier Claim, even when its source ID is unchanged.
        rights = _rights_for_release(ledger_root, loaded)
        claims = {
            _object_key(_record_reference("claim", row)): row for row in snapshot["claims"]
        }
        for claim in snapshot["claims"]:
            _validate_schema(claim, claim_validator, "object_schema_invalid")
            _validate_claim(
                claim,
                available,
                prefix_base_objects,
                prefix_base_objects,
                rights,
            )
        for episode in snapshot["episodes"]:
            _validate_schema(episode, episode_validator, "object_schema_invalid")
            _validate_episode(episode, available, prefix_base_objects, claims)
        for correction in snapshot["correction_impacts"]:
            _validate_schema(correction, correction_validator, "object_schema_invalid")
            _validate_correction(
                correction,
                snapshot,
                available,
                prefix_objects,
                prefix_releases,
                profile.products_by_type,
            )
        _validate_count_units(snapshot, loaded)
    return ValidatedExtension(
        document=bundle,
        profile=profile,
        ledger=ledger,
        ledger_root=ledger_root,
    )


def _effective(valid_on: date, start: object, end: object) -> bool:
    start_day = _utc(start, "extension_valid_start_invalid").date()
    end_day = _utc(end, "extension_valid_end_invalid").date() if end is not None else None
    return valid_on >= start_day and (end_day is None or valid_on <= end_day)


def _active_on(
    rows: Sequence[Mapping[str, Any]],
    valid_on: date,
    *,
    id_field: str,
    parent_field: str,
) -> list[Mapping[str, Any]]:
    applicable = [
        row for row in rows if _effective(valid_on, row["valid_from"], row["valid_to"])
    ]
    # Only an applicable successor suppresses its predecessor. A revision
    # already known at the cutoff but effective in the future must not erase
    # the predecessor that still governs the requested valid date. A
    # retroactive correction is itself applicable and therefore wins.
    superseded = {
        cast(str, row[parent_field])
        for row in applicable
        if row[parent_field] is not None
    }
    return [row for row in applicable if row[id_field] not in superseded]


def _events_on(
    validated: ValidatedExtension,
    selected_index: int,
    snapshot: Mapping[str, Any],
    valid_on: date,
) -> list[Mapping[str, Any]]:
    archive: dict[ObjectKey, Mapping[str, Any]] = {}
    for loaded in validated.ledger.releases[: selected_index + 1]:
        for event in loaded.validated.objects["event"].values():
            archive[_event_key(event)] = event

    selected = validated.ledger.releases[selected_index]
    candidates = {_event_key(event) for event in selected.validated.objects["event"].values()}
    excluded: set[ObjectKey] = set()
    for correction in snapshot["correction_impacts"]:
        correction_applies = valid_on >= _utc(
            correction["valid_from"], "extension_correction_valid_from_invalid"
        ).date()
        for transition in correction["transitions"]:
            if transition["predecessor"]["object_type"] != "event":
                continue
            predecessor = _object_key(transition["predecessor"])
            successor = _object_key(transition["successor"])
            candidates.update({predecessor, successor})
            excluded.add(predecessor if correction_applies else successor)
    missing = candidates - set(archive)
    if missing:
        _fail("extension_replay_event_archive_missing", sorted(missing)[0][1])
    return [archive[key] for key in sorted(candidates - excluded)]


def replay(
    bundle_path: Path,
    knowledge_cutoff: str,
    valid_on: str,
    *,
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
) -> dict[str, Any]:
    """Replay extension state using signed receipt time and separate valid time."""

    cutoff = _utc(knowledge_cutoff, "extension_knowledge_cutoff_invalid")
    valid_day = _day(valid_on, "extension_valid_on_invalid")
    validated = validate_bundle(bundle_path, root=root, profile_path=profile_path)
    ledger_created = _utc(
        validated.ledger.document["created_at"], "extension_ledger_created_at_invalid"
    )
    if cutoff > ledger_created:
        _fail("extension_knowledge_cutoff_after_ledger_close")
    eligible = [
        (index, loaded)
        for index, loaded in enumerate(validated.ledger.releases)
        if _utc(loaded.receipt["available_at"], "extension_receipt_available_at_invalid")
        <= cutoff
    ]
    if not eligible:
        _fail("extension_knowledge_cutoff_before_first_receipt")
    selected_index, selected = eligible[-1]
    snapshot = validated.document["snapshots"][selected_index]
    if snapshot["release_id"] != selected.entry["release_id"]:
        _fail("extension_replay_snapshot_identity_mismatch")

    events = []
    for event in _events_on(validated, selected_index, snapshot, valid_day):
        starts = _utc(event["starts_at"], "extension_event_start_invalid").date()
        ends = (
            _utc(event["ends_at"], "extension_event_end_invalid").date()
            if event["ends_at"] is not None
            else None
        )
        events.append(
            {
                "event_id": event["event_id"],
                "record_sha256": event["record_sha256"],
                "lifecycle_state": event["lifecycle"]["state"],
                "record_status": event["record_status"],
                "effective_on_valid_date": valid_day >= starts
                and (ends is None or valid_day <= ends),
            }
        )
    claims = [
        {
            "claim_id": claim["claim_id"],
            "record_sha256": claim["record_sha256"],
            "assertion_state": claim["assertion_state"],
            "subject_event_id": claim["subject_event"]["event_id"],
            "effective_on_valid_date": _effective(
                valid_day, claim["valid_from"], claim["valid_to"]
            ),
        }
        for claim in _active_on(
            snapshot["claims"],
            valid_day,
            id_field="claim_id",
            parent_field="supersedes_claim_id",
        )
    ]
    episodes = [
        {
            "episode_id": episode["episode_id"],
            "record_sha256": episode["record_sha256"],
            "episode_kind": episode["episode_kind"],
            "episode_state": episode["episode_state"],
            "effective_on_valid_date": _effective(
                valid_day, episode["valid_from"], episode["valid_to"]
            ),
            "event_effect": "relationship_only_never_promotion",
        }
        for episode in _active_on(
            snapshot["episodes"],
            valid_day,
            id_field="episode_id",
            parent_field="supersedes_episode_id",
        )
    ]
    corrections = [
        {
            "correction_id": correction["correction_id"],
            "record_sha256": correction["record_sha256"],
            "known_at": correction["known_at"],
            "valid_from": correction["valid_from"],
        }
        for correction in snapshot["correction_impacts"]
    ]
    document: dict[str, Any] = {
        "object_type": "event_ledger_extension_replay",
        "schema_version": _VERSION,
        "record_sha256": "0" * 64,
        "trust_class": "synthetic_nonproduction",
        "production_trust": False,
        "query": {
            "knowledge_cutoff": knowledge_cutoff,
            "valid_on": valid_on,
            "selection_rule": _SELECTION_RULE,
        },
        "selected_release": {
            "sequence": selected.entry["sequence"],
            "release_id": selected.entry["release_id"],
            "manifest_record_sha256": selected.entry["manifest_record_sha256"],
            "available_at": selected.entry["available_at"],
        },
        "events": events,
        "claims": sorted(claims, key=lambda row: cast(str, row["claim_id"])),
        "episodes": sorted(episodes, key=lambda row: cast(str, row["episode_id"])),
        "correction_impacts": sorted(
            corrections, key=lambda row: cast(str, row["correction_id"])
        ),
        "count_units": snapshot["count_units"],
        "limitations": sorted(
            [
                "aggregate_gdelt_rows_are_not_unique_events",
                "claim_assertion_state_is_not_event_lifecycle",
                "detector_episode_state_never_promotes_event",
                "evidence_verification_is_not_claim_truth",
                "model_clustering_is_proposal_only",
                "signed_synthetic_fixture_is_not_production_trust",
                "valid_time_separate_from_knowledge_time",
            ]
        ),
    }
    sealed = cast(dict[str, Any], seal_record(document))
    replay_validator = validated.profile.validators.get("replay_schema")
    if replay_validator is None:
        _fail("profile_replay_schema_missing")
    _validate_schema(sealed, replay_validator, "extension_replay_schema_invalid")
    return sealed


def summary(validated: ValidatedExtension) -> dict[str, Any]:
    """Return structural conformance metadata without source or claim content."""

    snapshots = validated.document["snapshots"]
    latest = snapshots[-1]
    return {
        "status": "conformant_synthetic_event_ledger_extension",
        "extension_id": _PROFILE_ID,
        "version": _VERSION,
        "profile_sha256": validated.profile.sha256,
        "base_ledger_id": validated.ledger.document["ledger_id"],
        "snapshots": len(snapshots),
        "latest_counts": latest["counts"],
        "production_trust": False,
        "source_rights_authority": False,
    }


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate or replay the OGES Event Ledger S1 extension")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--knowledge-cutoff")
    parser.add_argument("--valid-on")
    args = parser.parse_args(argv)
    try:
        if (args.knowledge_cutoff is None) != (args.valid_on is None):
            _fail("extension_replay_query_incomplete")
        if args.knowledge_cutoff is not None:
            result = replay(
                args.bundle,
                args.knowledge_cutoff,
                args.valid_on,
                root=args.root,
                profile_path=args.root / EXTENSION / "profile.json",
            )
        else:
            result = summary(
                validate_bundle(
                    args.bundle,
                    root=args.root,
                    profile_path=args.root / EXTENSION / "profile.json",
                )
            )
    except EventLedgerExtensionError as exc:
        print(
            json.dumps(
                {"status": "refused", "reason": exc.code, "detail": exc.detail},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
