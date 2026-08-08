"""Project bounded exposure paths from one signed canonical release.

The projection is deliberately not another truth store. It consumes the exact
records returned by :func:`src.canonical_objects.load_validated_release`, follows
only stored ``source_entity_id -> target_entity_id`` edge orientation, and emits
identifiers, hashes, statuses, dates, universe counts and evidence bindings. It
never emits source content, entity/event prose, exposure magnitudes, confidence
values, causal claims or realized-loss claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_REGISTRY = ROOT / "governance" / "exposure_projection_registry.json"

_METHOD_ID = "method:igrm.exposure_graph_projection"
_METHOD_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/exposure-traversal.schema.json"
_MAX_HOPS = 6
_MAX_PATHS = 100
_MAX_EXPANSIONS = 100_000
_SELECTION_RULE = "bounded_breadth_first_stored_direction_simple_paths"
_TEMPORAL_BASIS = "canonical_release_effective_date"
_EVENT_EDGE_RELATION = "event_entities_to_release_effective_graph"
_BASE_LIMITATIONS = (
    "active_release_records_only",
    "confidence_not_probability",
    "event_entry_not_exposure_cause",
    "event_status_not_ground_truth",
    "exposure_not_realized_loss",
    "magnitude_values_not_rendered",
    "path_search_bounded",
    "stored_edge_direction_only",
    "structural_connection_not_causation",
)


class ExposureGraphError(ValueError):
    """A fail-closed projection refusal with a stable, non-content code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ExposureGraphError(code, detail)


def _sha(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _fail("projection_contract_file_missing", path.name)


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


def _safe_contract_file(relative: object) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        _fail("projection_contract_path_invalid")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        _fail("projection_contract_path_invalid")
    candidate = ROOT
    for part in path.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("projection_contract_symlink_forbidden", relative)
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        _fail("projection_contract_file_missing", relative)
    if not resolved.is_file():
        _fail("projection_contract_file_missing", relative)
    return resolved


def _read_contract_json(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        document = json.loads(
            raw,
            object_pairs_hook=canonical._unique_object,
            parse_constant=canonical._reject_constant,
        )
    except canonical.CanonicalObjectError as exc:
        _fail(code, exc.code)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(document, dict):
        _fail(code)
    return cast(dict[str, Any], document), hashlib.sha256(raw).hexdigest()


def _load_projection_contract(
    release_effective: date,
    registry_path: Path = PROJECTION_REGISTRY,
) -> tuple[dict[str, Any], str, Draft202012Validator]:
    try:
        relative_registry = registry_path.resolve().relative_to(ROOT.resolve())
    except (OSError, ValueError):
        _fail("projection_registry_outside_root")
    registry_file = _safe_contract_file(str(relative_registry))
    registry, registry_sha = _read_contract_json(
        registry_file, "projection_registry_invalid"
    )
    if set(registry) != {
        "schema_version",
        "effective",
        "default_policy",
        "projection",
    }:
        _fail("projection_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("projection_registry_policy_invalid")
    if _parse_day(registry["effective"], "projection_registry_effective_invalid") > release_effective:
        _fail("projection_registry_not_effective")

    row = registry["projection"]
    expected_fields = {
        "method_id",
        "version",
        "implementation_path",
        "implementation_sha256",
        "effective",
        "superseded_on",
        "output_schema_id",
        "output_schema_version",
        "output_schema_path",
        "output_schema_sha256",
        "common_schema_path",
        "common_schema_sha256",
    }
    if not isinstance(row, dict) or set(row) != expected_fields:
        _fail("projection_registry_entry_invalid")
    if row["method_id"] != _METHOD_ID or row["version"] != _METHOD_VERSION:
        _fail("projection_method_identity_invalid")
    if row["output_schema_id"] != _OUTPUT_SCHEMA_ID or row["output_schema_version"] != "1.0.0":
        _fail("projection_schema_identity_invalid")
    effective = _parse_day(row["effective"], "projection_method_effective_invalid")
    if release_effective < effective:
        _fail("projection_method_not_effective")
    superseded = row["superseded_on"]
    if superseded is not None and release_effective >= _parse_day(
        superseded, "projection_method_superseded_invalid"
    ):
        _fail("projection_method_superseded")

    implementation = _safe_contract_file(row["implementation_path"])
    if implementation != Path(__file__).resolve() or _sha(implementation) != row[
        "implementation_sha256"
    ]:
        _fail("projection_method_digest_mismatch")
    common_path = _safe_contract_file(row["common_schema_path"])
    output_path = _safe_contract_file(row["output_schema_path"])
    if _sha(common_path) != row["common_schema_sha256"]:
        _fail("projection_common_schema_digest_mismatch")
    if _sha(output_path) != row["output_schema_sha256"]:
        _fail("projection_output_schema_digest_mismatch")
    common, _ = _read_contract_json(common_path, "projection_common_schema_invalid")
    output, _ = _read_contract_json(output_path, "projection_output_schema_invalid")
    if output.get("$id") != row["output_schema_id"]:
        _fail("projection_output_schema_id_mismatch")
    try:
        Draft202012Validator.check_schema(common)
        Draft202012Validator.check_schema(output)
    except SchemaError:
        _fail("projection_schema_meta_validation_failed")
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
    return cast(dict[str, Any], row), registry_sha, validator


def _date_effective(
    document: Mapping[str, Any],
    on_day: date,
    *,
    start_field: str,
    end_field: str,
) -> bool:
    if document["lifecycle"]["state"] != "active":
        return False
    start = document[start_field]
    end = document[end_field]
    if start is not None and _parse_day(start, "projection_effective_date_invalid") > on_day:
        return False
    return end is None or _parse_day(end, "projection_effective_date_invalid") >= on_day


def _event_entries(
    event: Mapping[str, Any],
    entities: Mapping[str, Mapping[str, Any]],
    release_day: date,
) -> list[dict[str, Any]]:
    roles: dict[str, set[str]] = defaultdict(set)
    location_evidence: dict[str, set[str]] = defaultdict(set)
    for entity_id in event["actor_entity_ids"]:
        roles[entity_id].add("actor")
    for entity_id in event["target_entity_ids"]:
        roles[entity_id].add("target")
    for entity_id in event["affected_entity_ids"]:
        roles[entity_id].add("affected")
    for location in event["locations"]:
        entity_id = location["entity_id"]
        roles[entity_id].add(f"location_{location['role']}")
        location_evidence[entity_id].update(location["evidence_ids"])

    result = []
    for entity_id in sorted(roles):
        entity = entities[entity_id]
        result.append(
            {
                "entity_id": entity_id,
                "record_sha256": entity["record_sha256"],
                "entity_type": entity["entity_type"],
                "lifecycle_state": entity["lifecycle"]["state"],
                "effective_on_release": _date_effective(
                    entity,
                    release_day,
                    start_field="effective_start",
                    end_field="effective_end",
                ),
                "roles": sorted(roles[entity_id]),
                "location_evidence_ids": sorted(location_evidence[entity_id]),
            }
        )
    return result


def _projection_graph(
    objects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    release_day: date,
) -> tuple[dict[str, list[Mapping[str, Any]]], dict[str, int]]:
    entities = objects["entity"]
    universes = objects["universe_release"]
    edges = objects["exposure_edge"]
    effective_entities = {
        entity_id
        for entity_id, entity in entities.items()
        if _date_effective(
            entity,
            release_day,
            start_field="effective_start",
            end_field="effective_end",
        )
    }
    eligible_universes = {
        universe_id
        for universe_id, universe in universes.items()
        if universe["lifecycle"]["state"] == "active"
        and _parse_day(universe["reference_date"], "projection_universe_date_invalid")
        <= release_day
    }
    edge_counts: Counter[str] = Counter()
    adjacency: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for edge in edges.values():
        if edge["lifecycle"]["state"] != "active":
            edge_counts["edge_records_lifecycle_excluded"] += 1
            continue
        if not _date_effective(
            edge,
            release_day,
            start_field="effective_start",
            end_field="effective_end",
        ):
            edge_counts["edge_records_temporal_excluded"] += 1
            continue
        source_id = cast(str, edge["source_entity_id"])
        target_id = cast(str, edge["target_entity_id"])
        if source_id not in effective_entities or target_id not in effective_entities:
            _fail("active_edge_endpoint_not_effective", cast(str, edge["edge_id"]))
        universe_id = cast(str, edge["coverage_basis"]["universe_release_id"])
        if universe_id not in eligible_universes:
            _fail("active_edge_universe_not_effective", cast(str, edge["edge_id"]))
        adjacency[source_id].append(edge)
        edge_counts["edge_records_projected"] += 1
    for rows in adjacency.values():
        rows.sort(key=lambda row: cast(str, row["edge_id"]))
    counts = {
        "entity_records_total": len(entities),
        "entity_records_effective": len(effective_entities),
        "universe_records_total": len(universes),
        "universe_records_eligible": len(eligible_universes),
        "edge_records_total": len(edges),
        "edge_records_projected": edge_counts["edge_records_projected"],
        "edge_records_lifecycle_excluded": edge_counts[
            "edge_records_lifecycle_excluded"
        ],
        "edge_records_temporal_excluded": edge_counts[
            "edge_records_temporal_excluded"
        ],
    }
    return dict(adjacency), counts


def _bounded_paths(
    adjacency: Mapping[str, Sequence[Mapping[str, Any]]],
    entries: Sequence[Mapping[str, Any]],
    target_entity_id: str,
    *,
    max_hops: int,
    max_paths: int,
) -> tuple[list[tuple[str, tuple[str, ...], tuple[Mapping[str, Any], ...]]], bool]:
    roots = sorted(
        cast(str, entry["entity_id"])
        for entry in entries
        if entry["effective_on_release"]
    )
    queue: deque[
        tuple[str, tuple[str, ...], tuple[Mapping[str, Any], ...]]
    ] = deque((root, (root,), tuple()) for root in roots)
    found: list[tuple[str, tuple[str, ...], tuple[Mapping[str, Any], ...]]] = []
    expansions = 0
    while queue:
        root, entity_ids, path_edges = queue.popleft()
        expansions += 1
        if expansions > _MAX_EXPANSIONS:
            _fail("traversal_budget_exceeded")
        current = entity_ids[-1]
        if current == target_entity_id:
            if path_edges:
                found.append((root, entity_ids, path_edges))
                if len(found) > max_paths:
                    return found[:max_paths], True
            continue
        if len(path_edges) >= max_hops:
            continue
        for edge in adjacency.get(current, ()):  # stored direction only
            next_id = cast(str, edge["target_entity_id"])
            if next_id in entity_ids:
                continue
            if expansions + len(queue) >= _MAX_EXPANSIONS:
                _fail("traversal_budget_exceeded")
            queue.append((root, (*entity_ids, next_id), (*path_edges, edge)))
    return found, False


def _coverage_row(
    edge: Mapping[str, Any],
    universes: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    basis = edge["coverage_basis"]
    universe = universes[basis["universe_release_id"]]
    return {
        "universe_release_id": universe["universe_release_id"],
        "record_sha256": universe["record_sha256"],
        "entity_type": universe["entity_type"],
        "reference_date": universe["reference_date"],
        "covered_entity_id": basis["covered_entity_id"],
        "member_status": basis["member_status"],
        "counts": dict(universe["counts"]),
    }


def _path_rows(
    raw_paths: Sequence[tuple[str, tuple[str, ...], tuple[Mapping[str, Any], ...]]],
    entry_by_id: Mapping[str, Mapping[str, Any]],
    universes: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for root, entity_ids, edges in raw_paths:
        hops = []
        limitation_codes: set[str] = set()
        for edge in edges:
            limitation_codes.update(edge["limitation_codes"])
            hops.append(
                {
                    "edge_id": edge["edge_id"],
                    "record_sha256": edge["record_sha256"],
                    "source_entity_id": edge["source_entity_id"],
                    "target_entity_id": edge["target_entity_id"],
                    "edge_type": edge["edge_type"],
                    "exposure_direction": edge["exposure_direction"],
                    "quantification_status": edge["quantification_status"],
                    "effective_start": edge["effective_start"],
                    "effective_end": edge["effective_end"],
                    "observed_at": edge["observed_at"],
                    "coverage": _coverage_row(edge, universes),
                    "evidence_ids": sorted(edge["evidence_ids"]),
                    "limitation_codes": sorted(edge["limitation_codes"]),
                }
            )
        rows.append(
            {
                "entry_entity_id": root,
                "entry_roles": list(entry_by_id[root]["roles"]),
                "entity_ids": list(entity_ids),
                "edge_ids": [edge["edge_id"] for edge in edges],
                "hops": hops,
                "limitation_codes": sorted(limitation_codes),
            }
        )
    return rows


def _object_evidence(
    event: Mapping[str, Any],
    target: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
    paths: Sequence[Mapping[str, Any]],
    objects: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    selected: dict[str, str] = {
        cast(str, event["event_id"]): "event",
        cast(str, target["entity_id"]): "entity",
    }
    selected.update((cast(str, row["entity_id"]), "entity") for row in entries)
    for path in paths:
        selected.update((cast(str, entity_id), "entity") for entity_id in path["entity_ids"])
        for hop in path["hops"]:
            selected[cast(str, hop["edge_id"])] = "exposure_edge"
            selected[cast(str, hop["coverage"]["universe_release_id"])] = "universe_release"

    evidence_fields = {
        "event": lambda row: row["provenance"]["evidence_ids"],
        "entity": lambda row: row["provenance"]["evidence_ids"],
        "exposure_edge": lambda row: row["evidence_ids"],
        "universe_release": lambda row: row["source_evidence_ids"],
    }
    rows = []
    for object_id in sorted(selected):
        object_type = selected[object_id]
        document = objects[object_type][object_id]
        rows.append(
            {
                "object_type": object_type,
                "object_id": object_id,
                "record_sha256": document["record_sha256"],
                "evidence_ids": sorted(evidence_fields[object_type](document)),
            }
        )
    return rows


def _resolved_evidence(
    object_evidence: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    evidence_ids = sorted(
        {
            cast(str, evidence_id)
            for row in object_evidence
            for evidence_id in row["evidence_ids"]
        }
    )
    return [
        {
            "evidence_id": evidence_id,
            "record_sha256": evidence[evidence_id]["record_sha256"],
            "source_id": evidence[evidence_id]["source_id"],
            "rights_use": evidence[evidence_id]["rights_use"],
            "rights_decision_id": evidence[evidence_id]["rights_decision_id"],
            "content_sha256": evidence[evidence_id]["content_sha256"],
            "content_availability": evidence[evidence_id]["content_availability"],
            "privacy_class": evidence[evidence_id]["privacy_class"],
            "verification_status": evidence[evidence_id]["verification_status"],
        }
        for evidence_id in evidence_ids
    ]


def _rights_rows(
    evidence_rows: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    needed = {row["source_id"] for row in evidence_rows}
    snapshot = {row["source_id"]: row for row in manifest["rights_snapshot"]}
    if not needed <= set(snapshot):
        _fail("projection_rights_snapshot_missing")
    return [dict(snapshot[source_id]) for source_id in sorted(needed)]


def _coverage_rows(paths: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in paths:
        for hop in path["hops"]:
            coverage = dict(hop["coverage"])
            key = (
                cast(str, coverage["universe_release_id"]),
                cast(str, coverage["covered_entity_id"]),
            )
            rows[key] = coverage
    return [rows[key] for key in sorted(rows)]


def _validate_output(
    document: Mapping[str, Any], validator: Draft202012Validator
) -> None:
    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        _fail("projection_output_schema_invalid", f"{path or '/'}:{error.validator}")
    if canonical.canonical_record_sha256(document) != document["record_sha256"]:
        _fail("projection_output_digest_mismatch")
    paths = document["paths"]
    result = document["result"]
    if result["returned_paths"] != len(paths) or result["status"] != (
        "paths_found" if paths else "no_path"
    ):
        _fail("projection_output_result_mismatch")
    truncated_code = "bounded_paths_truncated" in document["limitations"]
    if result["truncated"] != truncated_code:
        _fail("projection_output_truncation_mismatch")
    for path in paths:
        entity_ids = path["entity_ids"]
        edge_ids = path["edge_ids"]
        hops = path["hops"]
        if (
            not hops
            or len(edge_ids) != len(hops)
            or len(entity_ids) != len(hops) + 1
            or path["entry_entity_id"] != entity_ids[0]
            or len(entity_ids) != len(set(entity_ids))
        ):
            _fail("projection_output_path_mismatch")
        for index, hop in enumerate(hops):
            if (
                hop["edge_id"] != edge_ids[index]
                or hop["source_entity_id"] != entity_ids[index]
                or hop["target_entity_id"] != entity_ids[index + 1]
            ):
                _fail("projection_output_hop_mismatch")
    object_evidence = document["object_evidence"]
    object_ids = [row["object_id"] for row in object_evidence]
    evidence_ids = [row["evidence_id"] for row in document["evidence"]]
    expected_evidence = {
        evidence_id
        for row in object_evidence
        for evidence_id in row["evidence_ids"]
    }
    if (
        len(object_ids) != len(set(object_ids))
        or len(evidence_ids) != len(set(evidence_ids))
        or set(evidence_ids) != expected_evidence
    ):
        _fail("projection_output_evidence_mismatch")
    source_ids = [row["source_id"] for row in document["rights"]]
    expected_sources = {row["source_id"] for row in document["evidence"]}
    if len(source_ids) != len(set(source_ids)) or set(source_ids) != expected_sources:
        _fail("projection_output_rights_mismatch")


def project_event_exposure(
    manifest_path: Path,
    event_id: str,
    target_entity_id: str,
    *,
    max_hops: int = 4,
    max_paths: int = 25,
    root: Path = canonical.ROOT,
    schema_registry_path: Path = canonical.SCHEMA_REGISTRY,
    rights_registry_path: Path = canonical.RIGHTS_REGISTRY,
    rights_signers_path: Path = canonical.RIGHTS_SIGNERS,
    method_registry_path: Path = canonical.METHOD_REGISTRY,
    release_signers_path: Path = canonical.RELEASE_SIGNERS,
    projection_registry_path: Path = PROJECTION_REGISTRY,
) -> dict[str, Any]:
    """Return one bounded structural traversal from a signed canonical release."""

    if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 1 <= max_hops <= _MAX_HOPS:
        _fail("max_hops_invalid")
    if isinstance(max_paths, bool) or not isinstance(max_paths, int) or not 1 <= max_paths <= _MAX_PATHS:
        _fail("max_paths_invalid")
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
    objects = validated.objects
    events = objects["event"]
    entities = objects["entity"]
    if event_id not in events:
        _fail("event_not_in_release")
    if target_entity_id not in entities:
        _fail("target_entity_not_in_release")
    event = events[event_id]
    target = entities[target_entity_id]
    if event["lifecycle"]["state"] != "active":
        _fail("event_not_active")
    release_day = _parse_day(manifest["effective_date"], "release_effective_date_invalid")
    if _parse_day(cast(str, event["starts_at"])[:10], "event_start_date_invalid") > release_day:
        _fail("event_after_release_effective")
    target_effective = _date_effective(
        target,
        release_day,
        start_field="effective_start",
        end_field="effective_end",
    )
    if not target_effective:
        _fail("target_entity_not_effective")
    contract, projection_registry_sha, validator = _load_projection_contract(
        release_day, projection_registry_path
    )
    entries = _event_entries(event, entities, release_day)
    adjacency, projection_counts = _projection_graph(objects, release_day)
    raw_paths, truncated = _bounded_paths(
        adjacency,
        entries,
        target_entity_id,
        max_hops=max_hops,
        max_paths=max_paths,
    )
    entry_by_id = {cast(str, entry["entity_id"]): entry for entry in entries}
    paths = _path_rows(raw_paths, entry_by_id, objects["universe_release"])
    object_evidence = _object_evidence(event, target, entries, paths, objects)
    evidence_rows = _resolved_evidence(object_evidence, objects["evidence_item"])
    limitations = list(_BASE_LIMITATIONS)
    if truncated:
        limitations.append("bounded_paths_truncated")
    result = canonical.seal_record(
        {
            "object_type": "exposure_traversal",
            "schema_version": "1.0.0",
            "record_sha256": "0" * 64,
            "release": {
                "release_id": manifest["release_id"],
                "record_sha256": manifest["record_sha256"],
                "effective_date": manifest["effective_date"],
                "release_signer_id": manifest["release_signer_id"],
                "schema_registry_sha256": manifest["schema_registry_sha256"],
                "method_registry_sha256": manifest["method_registry_sha256"],
                "rights_registry_sha256": manifest["rights_registry_sha256"],
                "rights_signers_sha256": manifest["rights_signers_sha256"],
                "release_signers_sha256": manifest["release_signers_sha256"],
            },
            "contract": {
                "schema_id": contract["output_schema_id"],
                "schema_version": contract["output_schema_version"],
                "schema_sha256": contract["output_schema_sha256"],
                "common_schema_sha256": contract["common_schema_sha256"],
                "projection_registry_sha256": projection_registry_sha,
            },
            "method": {
                "method_id": contract["method_id"],
                "version": contract["version"],
                "implementation_sha256": contract["implementation_sha256"],
            },
            "query": {
                "event_id": event_id,
                "target_entity_id": target_entity_id,
                "max_hops": max_hops,
                "max_paths": max_paths,
                "selection_rule": _SELECTION_RULE,
                "temporal_basis": _TEMPORAL_BASIS,
                "event_edge_temporal_relation": _EVENT_EDGE_RELATION,
            },
            "event": {
                "event_id": event_id,
                "record_sha256": event["record_sha256"],
                "lifecycle_state": event["lifecycle"]["state"],
                "record_status": event["record_status"],
                "publication_phase": event["publication_phase"],
                "starts_at": event["starts_at"],
                "ends_at": event["ends_at"],
                "first_known_at": event["first_known_at"],
                "last_verified_at": event["last_verified_at"],
                "evidence_links": [dict(link) for link in event["evidence_links"]],
                "entry_entities": entries,
            },
            "target": {
                "entity_id": target_entity_id,
                "record_sha256": target["record_sha256"],
                "entity_type": target["entity_type"],
                "lifecycle_state": target["lifecycle"]["state"],
                "effective_on_release": target_effective,
            },
            "projection_counts": projection_counts,
            "paths": paths,
            "coverage": _coverage_rows(paths),
            "object_evidence": object_evidence,
            "evidence": evidence_rows,
            "rights": _rights_rows(evidence_rows, manifest),
            "result": {
                "status": "paths_found" if paths else "no_path",
                "returned_paths": len(paths),
                "truncated": truncated,
            },
            "limitations": sorted(limitations),
        }
    )
    _validate_output(result, validator)
    return cast(dict[str, Any], result)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Project one evidence-bound exposure path from a canonical release"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("event_id")
    parser.add_argument("target_entity_id")
    parser.add_argument("--max-hops", type=int, default=4)
    parser.add_argument("--max-paths", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        result = project_event_exposure(
            args.manifest,
            args.event_id,
            args.target_entity_id,
            max_hops=args.max_hops,
            max_paths=args.max_paths,
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
    except ExposureGraphError as exc:
        print(
            json.dumps(
                {"status": "refused", "stage": "projection", "reason": exc.code},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
