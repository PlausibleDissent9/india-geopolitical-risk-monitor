"""Collate semantically distinct sensors around one canonical event.

The engine consumes one fully validated, signed canonical release.  It never
averages, rescales or converts observations across lanes.  Its output is a
structural evidence matrix: identifiers, hashes, timing, source roles, rights
decisions and explicit missing lanes.  It emits no source text, URLs, observed
values, event intensity, risk score, probability, causal claim or forecast.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]
FUSION_REGISTRY = ROOT / "governance" / "sensor_fusion_registry.json"

_METHOD_ID = "method:igrm.sensor_fusion"
_METHOD_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/sensor-fusion.schema.json"
_JOIN_POLICY = "collate_only_never_average_or_convert"
_SELECTION_RULE = "event_linked_release_evidence_observed_in_window_and_retrieved_by_cutoff"
_LANE_IDS = (
    "official",
    "news",
    "coded_event",
    "physical_transmission",
    "trade_transmission",
    "energy_transmission",
    "market_transmission",
    "public_attention",
)
_BASE_LIMITATIONS = (
    "absence_means_no_eligible_link_in_release_not_no_real_world_signal",
    "canonical_release_generation_is_not_external_availability_proof",
    "event_status_not_ground_truth",
    "lane_coverage_not_event_coverage",
    "no_cross_lane_numeric_fusion",
    "no_causal_attribution",
    "no_forecast_or_probability",
    "no_source_content_or_observed_values_rendered",
    "semantic_collation_not_sensor_agreement",
)


class SensorFusionError(ValueError):
    """A fail-closed sensor-fusion refusal with a stable reason."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class LaneDefinition:
    lane_id: str
    label: str
    semantic_definition: str
    source_roles: frozenset[str]
    permitted_evidence_types: frozenset[str]


@dataclass(frozen=True)
class FusionContract:
    row: Mapping[str, Any]
    fusion_registry_sha256: str
    lane_registry_sha256: str
    lanes: tuple[LaneDefinition, ...]
    role_to_lane: Mapping[str, LaneDefinition]
    validator: Draft202012Validator


def _fail(code: str, detail: str = "") -> NoReturn:
    raise SensorFusionError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    _fail("json_non_finite")


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        parsed = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(parsed, dict):
        _fail(code)
    return raw, cast(dict[str, Any], parsed), hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        _fail(code)
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        _fail(code)
    resolved_root = root.resolve()
    candidate = resolved_root
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("sensor_contract_symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        _fail(code)
    if not resolved.is_file():
        _fail(code)
    return resolved


def _inside_root(root: Path, path: Path, code: str) -> Path:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        _fail(code)
    return _safe_file(root, relative, code)


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("sensor_contract_file_missing")


def _parse_day(value: object, code: str) -> date:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(code)
    if parsed.isoformat() != value:
        _fail(code)
    return parsed


def _parse_time(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code)
    if parsed.isoformat().replace("+00:00", "Z") != value:
        _fail(code)
    return parsed


def _strings(value: object, code: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        _fail(code)
    return cast(list[str], value)


def _load_lane_registry(
    path: Path, expected_sha: object
) -> tuple[tuple[LaneDefinition, ...], dict[str, LaneDefinition], str]:
    _, document, digest = _read_json(path, "sensor_lane_registry_invalid")
    if digest != expected_sha:
        _fail("sensor_lane_registry_digest_mismatch")
    if set(document) != {
        "schema_version",
        "effective",
        "default_policy",
        "join_policy",
        "lanes",
    }:
        _fail("sensor_lane_registry_fields_invalid")
    if (
        document["schema_version"] != "1.0.0"
        or document["default_policy"] != "deny"
        or document["join_policy"] != _JOIN_POLICY
    ):
        _fail("sensor_lane_registry_policy_invalid")
    _parse_day(document["effective"], "sensor_lane_registry_effective_invalid")
    rows = document["lanes"]
    if not isinstance(rows, list) or len(rows) != len(_LANE_IDS):
        _fail("sensor_lane_denominator_invalid")
    lanes: list[LaneDefinition] = []
    role_to_lane: dict[str, LaneDefinition] = {}
    for raw in rows:
        if not isinstance(raw, dict) or set(raw) != {
            "lane_id",
            "label",
            "semantic_definition",
            "source_roles",
            "permitted_evidence_types",
        }:
            _fail("sensor_lane_entry_invalid")
        lane_id = raw["lane_id"]
        label = raw["label"]
        definition = raw["semantic_definition"]
        if (
            not isinstance(lane_id, str)
            or not isinstance(label, str)
            or not label.strip()
            or not isinstance(definition, str)
            or len(definition) < 40
        ):
            _fail("sensor_lane_entry_invalid")
        lane = LaneDefinition(
            lane_id=lane_id,
            label=label,
            semantic_definition=definition,
            source_roles=frozenset(_strings(raw["source_roles"], "sensor_lane_roles_invalid")),
            permitted_evidence_types=frozenset(
                _strings(
                    raw["permitted_evidence_types"],
                    "sensor_lane_evidence_types_invalid",
                )
            ),
        )
        lanes.append(lane)
        for role in lane.source_roles:
            if role in role_to_lane:
                _fail("sensor_source_role_ambiguous", role)
            role_to_lane[role] = lane
    if tuple(lane.lane_id for lane in lanes) != _LANE_IDS:
        _fail("sensor_lane_order_invalid")
    return tuple(lanes), role_to_lane, digest


def _load_contract(root: Path, registry_path: Path) -> FusionContract:
    registry_file = _inside_root(root, registry_path, "sensor_fusion_registry_missing")
    _, registry, registry_sha = _read_json(registry_file, "sensor_fusion_registry_invalid")
    if set(registry) != {
        "schema_version",
        "effective",
        "default_policy",
        "fusion",
    }:
        _fail("sensor_fusion_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("sensor_fusion_registry_policy_invalid")
    _parse_day(registry["effective"], "sensor_fusion_registry_effective_invalid")
    row = registry["fusion"]
    expected = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "effective",
        "superseded_on",
        "lane_registry_path",
        "lane_registry_sha256",
        "output_schema_id",
        "output_schema_version",
        "output_schema_path",
        "output_schema_sha256",
        "common_schema_path",
        "common_schema_sha256",
        "max_event_evidence_links",
    }
    if not isinstance(row, dict) or set(row) != expected:
        _fail("sensor_fusion_registry_entry_invalid")
    if (
        row["method_id"] != _METHOD_ID
        or row["version"] != _METHOD_VERSION
        or row["output_schema_id"] != _OUTPUT_SCHEMA_ID
        or row["output_schema_version"] != "1.0.0"
    ):
        _fail("sensor_fusion_method_identity_invalid")
    _parse_day(row["effective"], "sensor_fusion_method_effective_invalid")
    if row["superseded_on"] is not None:
        _parse_day(row["superseded_on"], "sensor_fusion_method_superseded_invalid")
    maximum = row["max_event_evidence_links"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 100_000:
        _fail("sensor_fusion_bound_invalid")

    implementation = _safe_file(
        root, row["implementation_path"], "sensor_fusion_implementation_missing"
    )
    running_sha = _sha(Path(__file__).resolve())
    if (
        _sha(implementation) != row["implementation_sha256"]
        or running_sha != row["implementation_sha256"]
    ):
        _fail("sensor_fusion_implementation_digest_mismatch")

    lane_path = _safe_file(root, row["lane_registry_path"], "sensor_lane_registry_missing")
    lanes, role_to_lane, lane_sha = _load_lane_registry(lane_path, row["lane_registry_sha256"])
    common_path = _safe_file(root, row["common_schema_path"], "sensor_common_schema_missing")
    output_path = _safe_file(root, row["output_schema_path"], "sensor_output_schema_missing")
    if _sha(common_path) != row["common_schema_sha256"]:
        _fail("sensor_common_schema_digest_mismatch")
    if _sha(output_path) != row["output_schema_sha256"]:
        _fail("sensor_output_schema_digest_mismatch")
    _, common, _ = _read_json(common_path, "sensor_common_schema_invalid")
    _, output, _ = _read_json(output_path, "sensor_output_schema_invalid")
    if output.get("$id") != _OUTPUT_SCHEMA_ID:
        _fail("sensor_output_schema_id_mismatch")
    try:
        Draft202012Validator.check_schema(common)
        Draft202012Validator.check_schema(output)
    except SchemaError:
        _fail("sensor_schema_meta_invalid")
    resources = Registry().with_resources(
        [
            (cast(str, common["$id"]), Resource.from_contents(common)),
            (cast(str, output["$id"]), Resource.from_contents(output)),
        ]
    )
    validator = Draft202012Validator(
        output,
        registry=resources,
        format_checker=FormatChecker(),
    )
    return FusionContract(
        row=row,
        fusion_registry_sha256=registry_sha,
        lane_registry_sha256=lane_sha,
        lanes=lanes,
        role_to_lane=role_to_lane,
        validator=validator,
    )


def _source_roles(root: Path, rights_path: Path, expected_sha: object) -> dict[str, str]:
    safe = _inside_root(root, rights_path, "sensor_rights_registry_missing")
    _, document, digest = _read_json(safe, "sensor_rights_registry_invalid")
    if digest != expected_sha:
        _fail("sensor_rights_registry_digest_mismatch")
    rows = document.get("sources")
    if not isinstance(rows, list):
        _fail("sensor_rights_registry_invalid")
    roles: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            _fail("sensor_rights_registry_invalid")
        source_id = row.get("source_id")
        role = row.get("role")
        if not isinstance(source_id, str) or not isinstance(role, str) or source_id in roles:
            _fail("sensor_rights_registry_invalid")
        roles[source_id] = role
    return roles


def _link_roles(event: Mapping[str, Any]) -> dict[str, list[str]]:
    roles: dict[str, set[str]] = defaultdict(set)
    pairs: set[tuple[str, str]] = set()
    for link in event["evidence_links"]:
        evidence_id = cast(str, link["evidence_id"])
        role = cast(str, link["role"])
        pair = (evidence_id, role)
        if pair in pairs:
            _fail("sensor_event_evidence_role_duplicate", evidence_id)
        pairs.add(pair)
        roles[evidence_id].add(role)
    return {evidence_id: sorted(values) for evidence_id, values in roles.items()}


def _observation(
    evidence: Mapping[str, Any],
    source_role: str,
    event_link_roles: Sequence[str],
) -> dict[str, Any]:
    return {
        "evidence_id": evidence["evidence_id"],
        "record_sha256": evidence["record_sha256"],
        "source_id": evidence["source_id"],
        "source_role": source_role,
        "evidence_type": evidence["evidence_type"],
        "event_link_roles": list(event_link_roles),
        "verification_status": evidence["verification_status"],
        "observed_at": evidence["observed_at"],
        "effective_start": evidence["effective_start"],
        "effective_end": evidence["effective_end"],
        "retrieved_at": evidence["retrieved_at"],
        "content_sha256": evidence["content_sha256"],
        "rights_decision_id": evidence["rights_decision_id"],
        "rights_use": evidence["rights_use"],
        "privacy_class": evidence["privacy_class"],
    }


def _validate_output(document: Mapping[str, Any], contract: FusionContract) -> None:
    errors = sorted(
        contract.validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("sensor_output_schema_invalid", f"{path or '/'}:{error.validator}")
    if canonical.canonical_record_sha256(document) != document["record_sha256"]:
        _fail("sensor_output_digest_mismatch")

    lanes = document["lanes"]
    if [row["lane_id"] for row in lanes] != list(_LANE_IDS):
        _fail("sensor_output_lane_partition_invalid")
    observed_ids: set[str] = set()
    present: list[str] = []
    for lane, row in zip(contract.lanes, lanes):
        observations = row["observations"]
        evidence_ids = [item["evidence_id"] for item in observations]
        source_ids = sorted({item["source_id"] for item in observations})
        ordered = sorted(
            observations,
            key=lambda item: (item["observed_at"], item["evidence_id"]),
        )
        if (
            row["lane_id"] != lane.lane_id
            or row["label"] != lane.label
            or row["semantic_definition"] != lane.semantic_definition
            or len(evidence_ids) != len(set(evidence_ids))
            or observed_ids.intersection(evidence_ids)
            or row["observation_count"] != len(observations)
            or row["source_ids"] != source_ids
            or row["state"] != ("present" if observations else "absent")
            or observations != ordered
            or any(
                item["source_role"] not in lane.source_roles
                or item["evidence_type"] not in lane.permitted_evidence_types
                for item in observations
            )
        ):
            _fail("sensor_output_lane_semantics_invalid")
        observed_ids.update(evidence_ids)
        if observations:
            present.append(cast(str, row["lane_id"]))
    excluded = document["excluded_evidence"]
    excluded_ids = [row["evidence_id"] for row in excluded]
    expected_excluded = sorted(excluded, key=lambda row: (row["lane_id"], row["evidence_id"]))
    if (
        len(excluded_ids) != len(set(excluded_ids))
        or observed_ids.intersection(excluded_ids)
        or excluded != expected_excluded
    ):
        _fail("sensor_output_evidence_partition_invalid")
    counts = document["counts"]
    expected_total = len(observed_ids) + len(excluded_ids)
    if (
        counts["registered_lanes"] != len(_LANE_IDS)
        or counts["present_lanes"] != len(present)
        or counts["absent_lanes"] != len(_LANE_IDS) - len(present)
        or counts["eligible_observations"] != len(observed_ids)
        or counts["excluded_observations"] != len(excluded_ids)
        or counts["event_evidence_links"] != expected_total
    ):
        _fail("sensor_output_counts_invalid")
    missing = [lane_id for lane_id in _LANE_IDS if lane_id not in present]
    coverage = document["coverage"]
    if (
        coverage["observed_lane_ids"] != present
        or coverage["missing_lane_ids"] != missing
        or abs(coverage["fraction"] - len(present) / len(_LANE_IDS)) > 1e-12
    ):
        _fail("sensor_output_coverage_invalid")
    expected_status = "matrix_complete" if not missing else "matrix_partial"
    if document["result"]["status"] != expected_status:
        _fail("sensor_output_result_invalid")


def fuse_event_sensors(
    manifest_path: Path,
    event_id: str,
    window_start: str,
    window_end: str,
    knowledge_cutoff: str,
    *,
    root: Path = canonical.ROOT,
    schema_registry_path: Path = canonical.SCHEMA_REGISTRY,
    rights_registry_path: Path = canonical.RIGHTS_REGISTRY,
    rights_signers_path: Path = canonical.RIGHTS_SIGNERS,
    method_registry_path: Path = canonical.METHOD_REGISTRY,
    release_signers_path: Path = canonical.RELEASE_SIGNERS,
    fusion_registry_path: Path = FUSION_REGISTRY,
) -> dict[str, Any]:
    """Return a non-numeric eight-lane matrix for one signed event."""

    start = _parse_time(window_start, "sensor_window_start_invalid")
    end = _parse_time(window_end, "sensor_window_end_invalid")
    cutoff = _parse_time(knowledge_cutoff, "sensor_knowledge_cutoff_invalid")
    if start > end or end > cutoff:
        _fail("sensor_time_window_invalid")

    validated = canonical.load_validated_release(
        manifest_path,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
    )
    manifest = validated.manifest
    release_generated = _parse_time(manifest["generated_at"], "sensor_release_generated_at_invalid")
    if cutoff != release_generated:
        _fail("sensor_cutoff_must_equal_release_generation")
    release_effective = _parse_day(
        manifest["effective_date"], "sensor_release_effective_date_invalid"
    )
    contract = _load_contract(root, fusion_registry_path)
    method_effective = _parse_day(
        contract.row["effective"], "sensor_fusion_method_effective_invalid"
    )
    if release_effective < method_effective:
        _fail("sensor_fusion_method_not_effective")
    superseded = contract.row["superseded_on"]
    if superseded is not None and release_effective >= _parse_day(
        superseded, "sensor_fusion_method_superseded_invalid"
    ):
        _fail("sensor_fusion_method_superseded")

    events = validated.objects["event"]
    evidence_by_id = validated.objects["evidence_item"]
    if event_id not in events:
        _fail("sensor_event_not_in_release")
    event = events[event_id]
    if event["lifecycle"]["state"] != "active":
        _fail("sensor_event_not_active")
    if _parse_time(event["first_known_at"], "sensor_event_first_known_invalid") > cutoff:
        _fail("sensor_event_not_known_by_cutoff")
    links = event["evidence_links"]
    if len(links) > contract.row["max_event_evidence_links"]:
        _fail("sensor_event_evidence_bound_exceeded")
    link_roles = _link_roles(event)
    source_roles = _source_roles(root, rights_registry_path, manifest["rights_registry_sha256"])

    grouped: dict[str, list[dict[str, Any]]] = {lane_id: [] for lane_id in _LANE_IDS}
    excluded: list[dict[str, Any]] = []
    for evidence_id in sorted(link_roles):
        evidence = evidence_by_id[evidence_id]
        source_id = cast(str, evidence["source_id"])
        source_role = source_roles.get(source_id)
        if source_role is None:
            _fail("sensor_source_missing_from_rights_registry", source_id)
        lane = contract.role_to_lane.get(source_role)
        if lane is None:
            _fail("sensor_source_role_unregistered", source_role)
        if evidence["evidence_type"] not in lane.permitted_evidence_types:
            _fail("sensor_evidence_type_incompatible_with_lane", evidence_id)

        reason: str | None = None
        if evidence["lifecycle"]["state"] != "active":
            reason = "inactive_evidence"
        elif _parse_time(evidence["retrieved_at"], "sensor_evidence_retrieved_at_invalid") > cutoff:
            reason = "retrieved_after_knowledge_cutoff"
        else:
            observed = _parse_time(evidence["observed_at"], "sensor_evidence_observed_at_invalid")
            if observed < start or observed > end:
                reason = "outside_observation_window"
        if reason is not None:
            excluded.append(
                {
                    "evidence_id": evidence_id,
                    "record_sha256": evidence["record_sha256"],
                    "source_id": source_id,
                    "lane_id": lane.lane_id,
                    "reason": reason,
                }
            )
            continue
        grouped[lane.lane_id].append(_observation(evidence, source_role, link_roles[evidence_id]))

    lane_rows: list[dict[str, Any]] = []
    for lane in contract.lanes:
        observations = sorted(
            grouped[lane.lane_id],
            key=lambda row: (row["observed_at"], row["evidence_id"]),
        )
        lane_rows.append(
            {
                "lane_id": lane.lane_id,
                "label": lane.label,
                "semantic_definition": lane.semantic_definition,
                "state": "present" if observations else "absent",
                "observation_count": len(observations),
                "source_ids": sorted({row["source_id"] for row in observations}),
                "observations": observations,
            }
        )
    present = [row["lane_id"] for row in lane_rows if row["observations"]]
    missing = [lane_id for lane_id in _LANE_IDS if lane_id not in present]
    eligible = sum(len(row["observations"]) for row in lane_rows)
    document = canonical.seal_record(
        {
            "object_type": "sensor_fusion",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "release": {
                "release_id": manifest["release_id"],
                "record_sha256": manifest["record_sha256"],
                "generated_at": manifest["generated_at"],
                "effective_date": manifest["effective_date"],
                "release_signer_id": manifest["release_signer_id"],
                "schema_registry_sha256": manifest["schema_registry_sha256"],
                "method_registry_sha256": manifest["method_registry_sha256"],
                "rights_registry_sha256": manifest["rights_registry_sha256"],
                "rights_signers_sha256": manifest["rights_signers_sha256"],
                "release_signers_sha256": manifest["release_signers_sha256"],
            },
            "contract": {
                "schema_id": contract.row["output_schema_id"],
                "schema_version": contract.row["output_schema_version"],
                "schema_sha256": contract.row["output_schema_sha256"],
                "common_schema_sha256": contract.row["common_schema_sha256"],
                "fusion_registry_sha256": contract.fusion_registry_sha256,
                "lane_registry_sha256": contract.lane_registry_sha256,
            },
            "method": {
                "method_id": contract.row["method_id"],
                "version": contract.row["version"],
                "implementation_sha256": contract.row["implementation_sha256"],
            },
            "query": {
                "event_id": event_id,
                "window_start": window_start,
                "window_end": window_end,
                "knowledge_cutoff": knowledge_cutoff,
                "selection_rule": _SELECTION_RULE,
                "join_policy": _JOIN_POLICY,
            },
            "event": {
                "event_id": event_id,
                "record_sha256": event["record_sha256"],
                "lifecycle_state": event["lifecycle"]["state"],
                "record_status": event["record_status"],
                "publication_phase": event["publication_phase"],
                "starts_at": event["starts_at"],
                "first_known_at": event["first_known_at"],
                "last_verified_at": event["last_verified_at"],
            },
            "lanes": lane_rows,
            "excluded_evidence": sorted(
                excluded, key=lambda row: (row["lane_id"], row["evidence_id"])
            ),
            "counts": {
                "registered_lanes": len(_LANE_IDS),
                "present_lanes": len(present),
                "absent_lanes": len(missing),
                "event_evidence_links": len(links),
                "eligible_observations": eligible,
                "excluded_observations": len(excluded),
            },
            "coverage": {
                "denominator": "eight_registered_semantic_lanes",
                "observed_lane_ids": present,
                "missing_lane_ids": missing,
                "fraction": len(present) / len(_LANE_IDS),
            },
            "result": {
                "status": "matrix_complete" if not missing else "matrix_partial",
                "semantic_join": "collation_only",
                "numeric_fusion_performed": False,
            },
            "limitations": sorted(_BASE_LIMITATIONS),
        }
    )
    _validate_output(document, contract)
    return cast(dict[str, Any], document)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Collate one canonical event into separate sensor lanes"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("event_id")
    parser.add_argument("--window-start", required=True)
    parser.add_argument("--window-end", required=True)
    parser.add_argument("--knowledge-cutoff", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = fuse_event_sensors(
            args.manifest,
            args.event_id,
            args.window_start,
            args.window_end,
            args.knowledge_cutoff,
            root=args.root,
            schema_registry_path=args.root / "governance" / "canonical_schema_registry.json",
            rights_registry_path=args.root / "governance" / "source_rights_registry.json",
            rights_signers_path=args.root / "governance" / "rights_signers.json",
            method_registry_path=args.root / "governance" / "canonical_method_registry.json",
            release_signers_path=args.root / "governance" / "release_signers.json",
            fusion_registry_path=args.root / "governance" / "sensor_fusion_registry.json",
        )
    except canonical.CanonicalObjectError as exc:
        print(
            json.dumps(
                {
                    "status": "refused",
                    "stage": "canonical_release",
                    "reason": exc.code,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except SensorFusionError as exc:
        print(
            json.dumps(
                {"status": "refused", "stage": "sensor_fusion", "reason": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
