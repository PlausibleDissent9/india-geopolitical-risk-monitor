"""Validate the OGES lossless DependencyObservation extension.

The extension preserves n-ary source facts without pretending that a
country-commodity-port cell is a binary exposure edge.  Validation is offline,
rights-aware and frame-complete: every positive, zero, blank, missing,
suppressed and not-applicable cell in the declared joint frame must be present
before the bundle can pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from src import canonical_objects, publication_guard

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = (
    ROOT / "standard" / "oges" / "extensions" / "dependency-observation" / "0.1.0" / "profile.json"
)
RIGHTS_PATH = ROOT / "governance" / "source_rights_registry.json"
SIGNERS_PATH = ROOT / "governance" / "rights_signers.json"

_HEX = set("0123456789abcdef")
_STATUS = (
    "observed_positive",
    "observed_zero",
    "source_blank",
    "source_missing",
    "suppressed",
    "not_applicable",
)


class DependencyObservationError(ValueError):
    """Stable fail-closed extension refusal."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise DependencyObservationError(code)


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
        document = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: _fail("json_non_finite"),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DependencyObservationError(code) from exc
    if not isinstance(document, dict):
        _fail(code)
    return raw, cast(dict[str, Any], document), hashlib.sha256(raw).hexdigest()


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
            _fail("symlink_forbidden")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


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
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
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


def _canonical_sha(document: Mapping[str, object]) -> str:
    try:
        return canonical_objects.canonical_record_sha256(document)
    except canonical_objects.CanonicalObjectError as exc:
        raise DependencyObservationError("record_not_canonical_json") from exc


def seal_record(document: Mapping[str, object]) -> dict[str, object]:
    """Return a record carrying its canonical self-hash."""

    result = dict(document)
    result["record_sha256"] = _canonical_sha(result)
    return result


def canonical_joint_frame_sha256(observations: Sequence[Mapping[str, Any]]) -> str:
    """Hash the lossless joint-cell census without self-referential coverage fields."""

    census = []
    for row in observations:
        measure = row.get("measure")
        census.append(
            {
                "observation_id": row.get("observation_id"),
                "frame_member_id": (
                    row.get("coverage", {}).get("frame_member_id")
                    if isinstance(row.get("coverage"), dict)
                    else None
                ),
                "flow_semantics_id": row.get("flow_semantics_id"),
                "value_status": row.get("value_status"),
                "value": measure.get("value") if isinstance(measure, dict) else None,
                "roles": [
                    {
                        "slot": role.get("slot"),
                        "semantic_role_id": role.get("semantic_role_id"),
                        "provider_value": role.get("provider_value"),
                    }
                    for role in row.get("roles", [])
                    if isinstance(role, dict)
                ],
            }
        )
    try:
        encoded = json.dumps(
            sorted(census, key=lambda row: str(row["observation_id"])),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    except (TypeError, ValueError) as exc:
        raise DependencyObservationError("joint_frame_not_canonical_json") from exc
    return hashlib.sha256(encoded).hexdigest()


def _profile(
    root: Path = ROOT, profile_path: Path = PROFILE_PATH
) -> tuple[dict[str, Any], dict[str, Draft202012Validator], dict[str, Any]]:
    _, profile, _ = _read_json(profile_path, "profile_unreadable")
    if set(profile) != {
        "schema_version",
        "extension_id",
        "version",
        "effective",
        "status",
        "base_standard",
        "specification",
        "normative_files",
        "reference_implementation",
        "required_rights_uses",
        "claim_boundary",
    }:
        _fail("profile_fields_invalid")
    if (
        profile["schema_version"] != "0.1.0"
        or profile["extension_id"] != "oges:extension:dependency_observation"
        or profile["version"] != "0.1.0"
        or profile["status"] != "public_draft_no_adoption_claim"
    ):
        _fail("profile_identity_invalid")
    _day(profile["effective"], "profile_effective_invalid")
    base = profile["base_standard"]
    if not isinstance(base, dict) or set(base) != {"version", "profile_path", "profile_sha256"}:
        _fail("profile_base_standard_invalid")
    base_path = _safe_file(root, base["profile_path"], "profile_base_standard_missing")
    if hashlib.sha256(base_path.read_bytes()).hexdigest() != _sha(
        base["profile_sha256"], "profile_base_standard_digest_invalid"
    ):
        _fail("profile_base_standard_digest_mismatch")

    specification = profile["specification"]
    if not isinstance(specification, dict) or set(specification) != {"path", "sha256"}:
        _fail("profile_specification_invalid")
    specification_path = _safe_file(root, specification["path"], "profile_specification_missing")
    if hashlib.sha256(specification_path.read_bytes()).hexdigest() != _sha(
        specification["sha256"], "profile_specification_digest_invalid"
    ):
        _fail("profile_specification_digest_mismatch")

    files = profile["normative_files"]
    if not isinstance(files, list) or not files:
        _fail("profile_normative_files_invalid")
    loaded: dict[str, dict[str, Any]] = {}
    validators: dict[str, Draft202012Validator] = {}
    for row in files:
        if not isinstance(row, dict) or set(row) != {"kind", "path", "sha256"}:
            _fail("profile_normative_file_invalid")
        kind = row["kind"]
        if not isinstance(kind, str) or kind in loaded:
            _fail("profile_normative_file_duplicate")
        path = _safe_file(root, row["path"], "profile_normative_file_missing")
        raw, document, digest = _read_json(path, "profile_normative_file_invalid")
        if hashlib.sha256(raw).hexdigest() != digest or digest != _sha(
            row["sha256"], "profile_normative_digest_invalid"
        ):
            _fail("profile_normative_digest_mismatch")
        loaded[kind] = document
        if kind.endswith("_schema"):
            try:
                Draft202012Validator.check_schema(document)
            except SchemaError as exc:
                raise DependencyObservationError("profile_schema_invalid") from exc
            validators[kind] = Draft202012Validator(document, format_checker=FormatChecker())
    if set(validators) != {
        "dependency_observation_schema",
        "source_label_frame_schema",
        "entity_crosswalk_release_schema",
    } or set(loaded) != {
        *validators,
        "role_registry",
        "adversarial_cases",
    }:
        _fail("profile_normative_set_invalid")

    implementation = profile["reference_implementation"]
    if not isinstance(implementation, dict) or set(implementation) != {"path", "sha256"}:
        _fail("profile_implementation_invalid")
    implementation_path = _safe_file(root, implementation["path"], "profile_implementation_missing")
    if hashlib.sha256(implementation_path.read_bytes()).hexdigest() != _sha(
        implementation["sha256"], "profile_implementation_digest_invalid"
    ):
        _fail("profile_implementation_digest_mismatch")
    if profile["required_rights_uses"] != [
        "cite_metadata",
        "publish_derived_value",
        "publish_extract",
    ]:
        _fail("profile_rights_uses_invalid")
    if not isinstance(profile["claim_boundary"], list) or len(profile["claim_boundary"]) < 4:
        _fail("profile_claim_boundary_invalid")
    return profile, validators, loaded["role_registry"]


def _schema_validate(
    validator: Draft202012Validator, document: Mapping[str, Any], code: str
) -> None:
    if next(validator.iter_errors(document), None) is not None:
        _fail(code)


def _value_status_measure(document: Mapping[str, Any]) -> None:
    """Keep source missingness labels inseparable from their numeric payload."""

    status = document.get("value_status")
    measure = document.get("measure")
    if status in {"observed_positive", "observed_zero"}:
        if not isinstance(measure, Mapping):
            _fail("observation_value_measure_invalid")
        value = measure.get("value")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or (status == "observed_positive" and value <= 0)
            or (status == "observed_zero" and value != 0)
        ):
            _fail("observation_value_measure_invalid")
    elif status in set(_STATUS[2:]) and measure is not None:
        _fail("observation_value_measure_invalid")


def _record(document: Mapping[str, Any]) -> None:
    expected = _sha(document.get("record_sha256"), "record_digest_invalid")
    if _canonical_sha(document) != expected:
        _fail("record_digest_mismatch")


def _method(root: Path, method: Mapping[str, Any]) -> None:
    path = _safe_file(root, method.get("implementation_path"), "observation_method_missing")
    if hashlib.sha256(path.read_bytes()).hexdigest() != _sha(
        method.get("implementation_sha256"), "observation_method_digest_invalid"
    ):
        _fail("observation_method_digest_mismatch")


def _role_registry(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if (
        set(document)
        != {
            "schema_version",
            "extension_id",
            "default_policy",
            "roles",
            "flows",
            "projection_rule",
            "limits",
        }
        or document["default_policy"] != "deny"
    ):
        _fail("role_registry_invalid")
    roles: dict[str, Any] = {}
    for row in document["roles"]:
        if not isinstance(row, dict) or set(row) != {
            "semantic_role_id",
            "slot",
            "entity_type",
            "meaning",
            "interpretation_status",
        }:
            _fail("role_registry_invalid")
        if row["semantic_role_id"] in roles:
            _fail("role_registry_duplicate")
        roles[row["semantic_role_id"]] = row
    flows: dict[str, Any] = {}
    for row in document["flows"]:
        if not isinstance(row, dict) or set(row) != {
            "flow_semantics_id",
            "provider_flow",
            "direction",
            "required_roles",
            "semantic_ambiguity",
        }:
            _fail("flow_registry_invalid")
        if row["flow_semantics_id"] in flows:
            _fail("flow_registry_duplicate")
        flows[row["flow_semantics_id"]] = row
    return roles, flows


def _rights(
    *,
    root: Path,
    source: Mapping[str, Any],
    required_uses: Sequence[str],
    rights_path: Path,
    signers_path: Path,
    as_of: datetime,
) -> None:
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
        raise DependencyObservationError("observation_rights_invalid") from exc
    source_id = source.get("source_id")
    if not isinstance(source_id, str):
        _fail("observation_rights_invalid")
    row = rights.get(source_id)
    signer = signers.get(row["signer_id"]) if row is not None else None
    if (
        row is None
        or row["decision_state"] != "approved"
        or not set(required_uses).issubset(row["permitted_uses"])
        or source.get("rights_decision_id") != row["decision_id"]
        or source.get("rights_decision_artifact_sha256") != row["decision_artifact_sha256"]
        or source.get("rights_registry_sha256") != rights_sha
        or source.get("rights_signers_sha256") != signer_sha
        or as_of.date() > _day(row["review_due"], "observation_rights_invalid")
        or signer is None
        or (
            signer["revoked_on"] is not None
            and as_of.date() >= _day(signer["revoked_on"], "observation_rights_invalid")
        )
    ):
        _fail("observation_rights_invalid")


def _crosswalks(
    *,
    frames: Sequence[Mapping[str, Any]],
    crosswalks: Sequence[Mapping[str, Any]],
    known_entity_ids: set[str],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    frame_by_slot: dict[str, Mapping[str, Any]] = {}
    for frame in frames:
        slot = frame["slot"]
        if slot in frame_by_slot:
            _fail("source_label_frame_slot_duplicate")
        if frame["member_count"] != len(frame["provider_values"]):
            _fail("source_label_frame_count_invalid")
        frame_by_slot[slot] = frame

    entry_by_id: dict[str, Mapping[str, Any]] = {}
    crosswalk_by_slot: dict[str, Mapping[str, Any]] = {}
    for crosswalk in crosswalks:
        slot = crosswalk["slot"]
        if slot in crosswalk_by_slot:
            _fail("crosswalk_slot_duplicate")
        bound_frame = frame_by_slot.get(slot)
        if (
            bound_frame is None
            or crosswalk["frame_id"] != bound_frame["frame_id"]
            or crosswalk["frame_record_sha256"] != bound_frame["record_sha256"]
            or crosswalk["source_id"] != bound_frame["source_id"]
            or crosswalk["semantic_role_id"] != bound_frame["semantic_role_id"]
        ):
            _fail("crosswalk_frame_binding_invalid")
        entries = crosswalk["entries"]
        provider_values = [row["provider_value"] for row in entries]
        if (
            len(provider_values) != len(set(provider_values))
            or set(provider_values) != set(bound_frame["provider_values"])
            or crosswalk["entry_count"] != len(entries)
        ):
            _fail("crosswalk_frame_partition_invalid")
        counts = Counter(row["resolution_status"] for row in entries)
        if crosswalk["resolution_counts"] != {
            status: counts[status]
            for status in counts.keys() | {"matched", "unmatched", "ambiguous", "withheld"}
        }:
            _fail("crosswalk_resolution_counts_invalid")
        for entry in entries:
            entry_id = entry["entry_id"]
            if entry_id in entry_by_id:
                _fail("crosswalk_entry_duplicate")
            matched = entry["resolution_status"] == "matched"
            if matched != (entry["canonical_entity_id"] is not None):
                _fail("crosswalk_resolution_invalid")
            if matched and (
                entry["canonical_entity_id"] not in known_entity_ids
                or not entry["reviewed_by"]
                or not entry["evidence_ids"]
            ):
                _fail("crosswalk_resolution_invalid")
            entry_by_id[entry_id] = {**entry, "slot": slot}
        crosswalk_by_slot[slot] = crosswalk
    if set(frame_by_slot) != set(crosswalk_by_slot):
        _fail("crosswalk_frame_set_invalid")
    return frame_by_slot, entry_by_id


def validate_bundle(
    *,
    observations: Sequence[Mapping[str, Any]],
    frames: Sequence[Mapping[str, Any]],
    crosswalks: Sequence[Mapping[str, Any]],
    known_entity_ids: set[str],
    root: Path = ROOT,
    profile_path: Path = PROFILE_PATH,
    rights_path: Path = RIGHTS_PATH,
    signers_path: Path = SIGNERS_PATH,
) -> dict[str, Any]:
    """Validate one complete lossless joint-observation frame."""

    profile, validators, role_document = _profile(root, profile_path)
    if not observations:
        _fail("observation_bundle_empty")
    for observation in observations:
        _value_status_measure(observation)
        _schema_validate(
            validators["dependency_observation_schema"],
            observation,
            "observation_schema_invalid",
        )
        _record(observation)
    for frame in frames:
        _schema_validate(
            validators["source_label_frame_schema"], frame, "source_label_frame_schema_invalid"
        )
        _record(frame)
        _method(root, frame["extraction_method"])
    for crosswalk in crosswalks:
        _schema_validate(
            validators["entity_crosswalk_release_schema"],
            crosswalk,
            "crosswalk_schema_invalid",
        )
        _record(crosswalk)

    registered_roles, registered_flows = _role_registry(role_document)
    frame_by_slot, entry_by_id = _crosswalks(
        frames=frames, crosswalks=crosswalks, known_entity_ids=known_entity_ids
    )

    first = observations[0]
    first_coverage = first["coverage"]
    joint_frame_id = first_coverage["joint_frame_id"]
    joint_frame_count = first_coverage["joint_frame_count"]
    joint_frame_sha = first_coverage["joint_frame_sha256"]
    partition = first_coverage["value_partition"]
    if (
        joint_frame_count != len(observations)
        or sum(partition.values()) != len(observations)
        or {
            status: sum(row["value_status"] == status for row in observations) for status in _STATUS
        }
        != partition
        or canonical_joint_frame_sha256(observations) != joint_frame_sha
    ):
        _fail("observation_value_partition_invalid")
    ids: set[str] = set()
    members: set[str] = set()
    source_snapshots: dict[tuple[str, str, str, str, str], datetime] = {}
    for observation in observations:
        coverage = observation["coverage"]
        if (
            coverage["joint_frame_id"] != joint_frame_id
            or coverage["joint_frame_count"] != joint_frame_count
            or coverage["joint_frame_sha256"] != joint_frame_sha
            or coverage["value_partition"] != partition
        ):
            _fail("observation_joint_frame_binding_invalid")
        if observation["observation_id"] in ids:
            _fail("observation_id_duplicate")
        ids.add(observation["observation_id"])
        if coverage["frame_member_id"] in members:
            _fail("observation_frame_member_duplicate")
        members.add(coverage["frame_member_id"])

        flow = registered_flows.get(observation["flow_semantics_id"])
        if flow is None:
            _fail("observation_flow_unregistered")
        roles = observation["roles"]
        slots = [role["slot"] for role in roles]
        if len(slots) != len(set(slots)):
            _fail("observation_role_slot_duplicate")
        expected = {row["slot"]: row["semantic_role_id"] for row in flow["required_roles"]}
        if set(slots) != set(expected):
            _fail("observation_role_set_invalid")
        unresolved = False
        for role in roles:
            registered = registered_roles.get(role["semantic_role_id"])
            if (
                registered is None
                or expected.get(role["slot"]) != role["semantic_role_id"]
                or registered["slot"] != role["slot"]
                or registered["interpretation_status"] != role["interpretation_status"]
            ):
                _fail("observation_role_semantics_invalid")
            role_frame = frame_by_slot.get(role["slot"])
            entry = entry_by_id.get(role["crosswalk_entry_id"])
            if (
                role_frame is None
                or role_frame["source_id"] != observation["source"]["source_id"]
                or role_frame["source_artifact_sha256"] != observation["source"]["artifact_sha256"]
                or role_frame["semantic_role_id"] != role["semantic_role_id"]
                or entry is None
                or entry["slot"] != role["slot"]
                or entry["provider_value"] != role["provider_value"]
                or entry["resolution_status"] != role["resolution_status"]
                or entry["canonical_entity_id"] != role["canonical_entity_id"]
            ):
                _fail("observation_crosswalk_mismatch")
            unresolved = unresolved or role["resolution_status"] != "matched"

        period = observation["period"]
        observed = _utc(observation["observed_at"], "observation_time_invalid")
        knowledge = _utc(observation["knowledge_available_at"], "observation_time_invalid")
        compiled = _utc(observation["compiled_at"], "observation_time_invalid")
        if (
            _day(period["start"], "observation_period_invalid")
            > _day(period["end"], "observation_period_invalid")
            or observed.date() < _day(period["end"], "observation_period_invalid")
            or not observed <= knowledge <= compiled
        ):
            _fail("observation_time_order_invalid")

        _method(root, observation["method"])
        source = observation["source"]
        snapshot = (
            source["source_id"],
            source["rights_registry_sha256"],
            source["rights_signers_sha256"],
            source["rights_decision_id"],
            source["rights_decision_artifact_sha256"],
        )
        source_snapshots[snapshot] = max(compiled, source_snapshots.get(snapshot, compiled))
        expected_status = (
            "blocked_semantic_ambiguity"
            if flow["semantic_ambiguity"]
            else "blocked_unresolved_roles"
            if unresolved
            else "blocked_nonpositive_or_missing"
            if observation["value_status"] != "observed_positive"
            else "eligible_for_separate_registered_projection"
        )
        if observation["relation_compilation_status"] != expected_status:
            _fail("observation_projection_status_invalid")

    for snapshot, as_of in source_snapshots.items():
        source_id, rights_sha, signers_sha, decision_id, decision_sha = snapshot
        matching = next(
            row
            for row in observations
            if row["source"]["source_id"] == source_id
            and row["source"]["rights_registry_sha256"] == rights_sha
            and row["source"]["rights_signers_sha256"] == signers_sha
            and row["source"]["rights_decision_id"] == decision_id
            and row["source"]["rights_decision_artifact_sha256"] == decision_sha
        )
        _rights(
            root=root,
            source=matching["source"],
            required_uses=profile["required_rights_uses"],
            rights_path=rights_path,
            signers_path=signers_path,
            as_of=as_of,
        )
    return {
        "status": "conformant_dependency_observation_frame",
        "extension_id": profile["extension_id"],
        "version": profile["version"],
        "joint_frame_id": joint_frame_id,
        "joint_frame_sha256": joint_frame_sha,
        "observation_count": len(observations),
        "value_partition": partition,
        "source_count": len({row["source"]["source_id"] for row in observations}),
        "crosswalk_count": len(crosswalks),
        "canonical_entity_count": len(known_entity_ids),
        "claim_boundary": "structural_source_observations_not_dependency_edges",
    }


def _bundle(path: Path) -> dict[str, Any]:
    _, document, _ = _read_json(path, "bundle_unreadable")
    if set(document) != {"observations", "frames", "crosswalks", "known_entity_ids"}:
        _fail("bundle_fields_invalid")
    if not all(isinstance(document[field], list) for field in document):
        _fail("bundle_fields_invalid")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--rights-registry", type=Path, default=RIGHTS_PATH)
    parser.add_argument("--rights-signers", type=Path, default=SIGNERS_PATH)
    args = parser.parse_args()
    profile_path = (
        args.root
        / "standard"
        / "oges"
        / "extensions"
        / "dependency-observation"
        / "0.1.0"
        / "profile.json"
    )
    try:
        bundle = _bundle(args.bundle)
        result = validate_bundle(
            observations=bundle["observations"],
            frames=bundle["frames"],
            crosswalks=bundle["crosswalks"],
            known_entity_ids=set(bundle["known_entity_ids"]),
            root=args.root,
            profile_path=profile_path,
            rights_path=args.rights_registry,
            signers_path=args.rights_signers,
        )
    except DependencyObservationError as exc:
        raise SystemExit(
            json.dumps({"status": "refused", "reason": exc.code}, sort_keys=True)
        ) from exc
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
