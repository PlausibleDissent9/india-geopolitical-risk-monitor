"""Compile four deterministic products from one signed evidence release.

The engine consumes the exact records returned by the canonical-release
validator and the registered exposure traversal.  It produces a research
package, a board-brief draft, a newsroom claim card and a deterministic
offline audit ZIP from the same evidence graph.  All prose comes from fixed
templates over registered fields; no model writes facts, numbers, dates,
citations, confidence, causation, forecasts or recommendations.

The offline bundle contains source metadata and release dependencies, never
source content that the canonical record does not already license for public
use.  Evidence with non-public privacy state refuses the entire public output
set.  This first version therefore favours an explicit refusal over a useful-
looking partial disclosure whose rights boundary cannot be checked.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical
from src import exposure_graph

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_REGISTRY = ROOT / "governance" / "evidence_output_registry.json"

_METHOD_ID = "method:igrm.evidence_outputs"
_METHOD_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/evidence-output-set.schema.json"
_REQUIRED_OUTPUT_IDS = (
    "output:research_package",
    "output:board_brief",
    "output:newsroom_claim_card",
    "output:offline_audit_bundle",
)
_RENDERING_RULE = "registered_deterministic_templates_no_model_generation"
_PUBLIC_PRIVACY_CLASSES = ("public", "public_with_redactions")
_PUBLIC_RIGHTS_USES = (
    "cite_metadata",
    "publish_derived_value",
    "publish_extract",
    "redistribute_full_record",
)
_MAX_OBJECTS = 10_000
_MAX_ARCHIVE_BYTES = 50_000_000
_LIMITATIONS = (
    "bounded_traversal_not_complete_exposure",
    "event_status_not_ground_truth",
    "no_forecast_probability_or_advice",
    "no_source_content_or_extracts",
    "source_metadata_not_source_content",
    "structural_path_not_causation",
)
_RESEARCH_LIMITATIONS = (
    "citation_identifies_release_and_compilation_not_source_truth",
    "object_index_is_query_bounded",
    "structural_paths_do_not_measure_realized_effect",
)
_BRIEF_LIMITATIONS = (
    "draft_requires_human_review",
    "not_a_probability_severity_loss_or_recommendation",
    "structural_path_not_causation",
)
_CLAIM_LIMITATIONS = (
    "claims_are_about_registered_release_records",
    "not_independent_truth_or_completeness_claims",
    "structural_path_not_causation",
)
_AUDIT_LIMITATIONS = (
    "authenticate_external_verifier_before_execution",
    "bundle_excludes_unlicensed_source_content",
    "conformance_does_not_establish_substantive_truth",
)


class EvidenceOutputError(ValueError):
    """A stable fail-closed refusal with no source-content detail."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise EvidenceOutputError(code, detail)


def _json_bytes(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError):
        _fail("output_not_canonical_json")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json(path: Path, code: str) -> tuple[bytes, dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(
            raw,
            object_pairs_hook=canonical._unique_object,
            parse_constant=canonical._reject_constant,
        )
    except canonical.CanonicalObjectError as exc:
        _fail(code, exc.code)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail(code)
    if not isinstance(value, dict):
        _fail(code)
    return raw, cast(dict[str, Any], value), _sha_bytes(raw)


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
            _fail("output_contract_symlink_forbidden", relative)
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


def _relative(root: Path, path: Path, code: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        _fail(code)


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


def _schema_validator(
    common: Mapping[str, Any], schema: Mapping[str, Any]
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(common)
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        _fail("output_schema_meta_invalid")
    registry = Registry().with_resources(
        [
            (cast(str, common["$id"]), Resource.from_contents(common)),
            (cast(str, schema["$id"]), Resource.from_contents(schema)),
        ]
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _schema_check(
    document: Mapping[str, Any], validator: Draft202012Validator
) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("output_schema_invalid", f"{path or '/'}:{first.validator}")


def _load_contract(
    root: Path,
    registry_path: Path,
    release_day: date,
) -> tuple[dict[str, Any], str, Draft202012Validator]:
    registry_file = _inside_root(root, registry_path, "output_registry_missing")
    _, registry, registry_sha = _read_json(registry_file, "output_registry_invalid")
    if set(registry) != {"schema_version", "effective", "default_policy", "engine"}:
        _fail("output_registry_fields_invalid")
    if registry["schema_version"] != "1.0.0" or registry["default_policy"] != "deny":
        _fail("output_registry_policy_invalid")
    if _parse_day(registry["effective"], "output_registry_effective_invalid") > release_day:
        _fail("output_registry_not_effective")
    row = registry["engine"]
    expected = {
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
        "exposure_graph_implementation_path",
        "exposure_graph_implementation_sha256",
        "exposure_projection_registry_path",
        "exposure_projection_registry_sha256",
        "required_output_ids",
        "rendering_rule",
        "public_privacy_classes",
        "public_rights_uses",
        "max_objects",
        "max_archive_bytes",
    }
    if not isinstance(row, dict) or set(row) != expected:
        _fail("output_registry_engine_invalid")
    if (
        row["method_id"] != _METHOD_ID
        or row["version"] != _METHOD_VERSION
        or row["output_schema_id"] != _OUTPUT_SCHEMA_ID
        or row["output_schema_version"] != "1.0.0"
        or tuple(row["required_output_ids"]) != _REQUIRED_OUTPUT_IDS
        or row["rendering_rule"] != _RENDERING_RULE
        or tuple(row["public_privacy_classes"]) != _PUBLIC_PRIVACY_CLASSES
        or tuple(row["public_rights_uses"]) != _PUBLIC_RIGHTS_USES
        or row["max_objects"] != _MAX_OBJECTS
        or row["max_archive_bytes"] != _MAX_ARCHIVE_BYTES
    ):
        _fail("output_engine_identity_invalid")
    effective = _parse_day(row["effective"], "output_engine_effective_invalid")
    if release_day < effective:
        _fail("output_engine_not_effective")
    if row["superseded_on"] is not None and release_day >= _parse_day(
        row["superseded_on"], "output_engine_superseded_invalid"
    ):
        _fail("output_engine_superseded")

    implementation = _safe_file(root, row["implementation_path"], "output_implementation_missing")
    if (
        _sha_bytes(implementation.read_bytes()) != row["implementation_sha256"]
        or _sha_bytes(Path(__file__).read_bytes()) != row["implementation_sha256"]
    ):
        _fail("output_implementation_digest_mismatch")
    graph = _safe_file(
        root,
        row["exposure_graph_implementation_path"],
        "output_exposure_graph_missing",
    )
    if (
        _sha_bytes(graph.read_bytes()) != row["exposure_graph_implementation_sha256"]
        or _sha_bytes(Path(exposure_graph.__file__).read_bytes())
        != row["exposure_graph_implementation_sha256"]
    ):
        _fail("output_exposure_graph_digest_mismatch")
    projection_registry = _safe_file(
        root,
        row["exposure_projection_registry_path"],
        "output_projection_registry_missing",
    )
    if _sha_bytes(projection_registry.read_bytes()) != row[
        "exposure_projection_registry_sha256"
    ]:
        _fail("output_projection_registry_digest_mismatch")

    common_path = _safe_file(root, row["common_schema_path"], "output_common_schema_missing")
    schema_path = _safe_file(root, row["output_schema_path"], "output_schema_missing")
    if _sha_bytes(common_path.read_bytes()) != row["common_schema_sha256"]:
        _fail("output_common_schema_digest_mismatch")
    if _sha_bytes(schema_path.read_bytes()) != row["output_schema_sha256"]:
        _fail("output_schema_digest_mismatch")
    _, common, _ = _read_json(common_path, "output_common_schema_invalid")
    _, schema, _ = _read_json(schema_path, "output_schema_invalid")
    if schema.get("$id") != _OUTPUT_SCHEMA_ID:
        _fail("output_schema_id_mismatch")
    return cast(dict[str, Any], row), registry_sha, _schema_validator(common, schema)


def _release_identity(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: manifest[key]
        for key in (
            "release_id",
            "record_sha256",
            "generated_at",
            "effective_date",
            "release_signer_id",
            "schema_registry_sha256",
            "method_registry_sha256",
            "rights_registry_sha256",
            "rights_signers_sha256",
            "release_signers_sha256",
        )
    }


def _object_ref(object_type: str, document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "object_type": object_type,
        "object_id": document[canonical._ID_FIELD[object_type]],
        "record_sha256": document["record_sha256"],
    }


def _evidence_citations(
    evidence_ids: Sequence[str], evidence: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for evidence_id in sorted(set(evidence_ids)):
        row = evidence[evidence_id]
        rows.append(
            {
                "evidence_id": evidence_id,
                "record_sha256": row["record_sha256"],
                "source_id": row["source_id"],
                "title": row["title"],
                "public_url": row["public_url"],
                "published_at": row["published_at"],
                "observed_at": row["observed_at"],
                "verification_status": row["verification_status"],
                "content_availability": row["content_availability"],
                "rights_use": row["rights_use"],
            }
        )
    return rows


def _enforce_public_rights(
    evidence_ids: Sequence[str], evidence: Mapping[str, Mapping[str, Any]]
) -> None:
    for evidence_id in sorted(set(evidence_ids)):
        row = evidence[evidence_id]
        if row["privacy_class"] not in _PUBLIC_PRIVACY_CLASSES:
            _fail("output_evidence_privacy_not_public", evidence_id)
        if row["rights_use"] not in _PUBLIC_RIGHTS_USES:
            _fail("output_evidence_rights_not_public", evidence_id)


def _artifact(filename: str, media_type: str, body: bytes) -> dict[str, Any]:
    return {
        "filename": filename,
        "media_type": media_type,
        "sha256": _sha_bytes(body),
        "bytes": len(body),
    }


def _output_body(document: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "artifact"}


def _attach_artifact(
    body: Mapping[str, Any], filename: str, media_type: str = "application/json"
) -> tuple[dict[str, Any], bytes]:
    raw = _json_bytes(body)
    document = dict(body)
    document["artifact"] = _artifact(filename, media_type, raw)
    return document, raw


def _citation(
    manifest: Mapping[str, Any], event_id: str, target_entity_id: str
) -> str:
    return (
        "Krishna, Ishan (2026). IGRM evidence-bound research package for "
        f"{event_id} to {target_entity_id}. Canonical release "
        f"{manifest['release_id']} (record SHA-256 {manifest['record_sha256']}), "
        f"generated {manifest['generated_at']}. India Geopolitical Risk Monitor. "
        "https://igrm.in/standard.html"
    )


def _sections(
    event: Mapping[str, Any],
    target: Mapping[str, Any],
    traversal: Mapping[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    event_id = cast(str, event["event_id"])
    target_id = cast(str, target["entity_id"])
    paths = cast(int, traversal["result"]["returned_paths"])
    event_text = (
        f"The signed release records {event['canonical_label']} as a "
        f"{event['record_status']} {event['event_class']} beginning "
        f"{event['starts_at']}; it was last verified at {event['last_verified_at']}."
    )
    if paths:
        connection_text = (
            f"The registered bounded traversal returned {paths} structural "
            f"path(s) from stored event-entry entities to {target['canonical_name']} "
            f"within {traversal['query']['max_hops']} hop(s). A structural path is "
            "not evidence of causation, realized disruption or economic loss."
        )
    else:
        connection_text = (
            f"The registered bounded traversal returned no structural path to "
            f"{target['canonical_name']} within {traversal['query']['max_hops']} "
            "hop(s). This bounded non-result is not evidence that exposure is absent."
        )
    return [
        {
            "section_id": "section:board.event_record",
            "heading": "Registered event record",
            "text": event_text,
            "object_ids": [event_id],
            "evidence_ids": evidence_ids,
        },
        {
            "section_id": "section:board.india_linkage",
            "heading": "Stored India linkage",
            "text": connection_text,
            "object_ids": [event_id, target_id],
            "evidence_ids": evidence_ids,
        },
        {
            "section_id": "section:board.decision_boundary",
            "heading": "Decision boundary",
            "text": (
                "This deterministic draft supplies traceable release facts and "
                "structural paths only. It does not estimate probability, severity, "
                "loss, causation, future outcomes or a recommended action; a human "
                "reviewer must inspect the evidence and declared gaps before use."
            ),
            "object_ids": [event_id, target_id],
            "evidence_ids": evidence_ids,
        },
    ]


def _claims(
    event: Mapping[str, Any],
    target: Mapping[str, Any],
    traversal: Mapping[str, Any],
    evidence_ids: list[str],
) -> list[dict[str, Any]]:
    event_id = cast(str, event["event_id"])
    target_id = cast(str, target["entity_id"])
    first = {
        "claim_id": "claim:card.event_record",
        "statement": (
            f"In the signed release, {event['canonical_label']} is recorded as a "
            f"{event['record_status']} {event['event_class']} beginning "
            f"{event['starts_at']}."
        ),
        "scope": "release_record",
        "object_ids": [event_id],
        "evidence_ids": evidence_ids,
        "status": "compiled_from_registered_fields",
        "limitations": ["event_status_not_ground_truth"],
    }
    paths = cast(int, traversal["result"]["returned_paths"])
    second = {
        "claim_id": "claim:card.release_structure",
        "statement": (
            f"The registered traversal returned {paths} structural path(s) from the "
            f"event's stored entity entries to {target['canonical_name']} under its "
            "declared hop and path limits."
        ),
        "scope": "release_structure",
        "object_ids": [event_id, target_id],
        "evidence_ids": evidence_ids,
        "status": "compiled_from_registered_fields",
        "limitations": [
            "bounded_traversal_not_complete_exposure",
            "structural_path_not_causation",
        ],
    }
    return [first, second]


def _file_row(path: str, raw: bytes, role: str) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": _sha_bytes(raw),
        "bytes": len(raw),
        "role": role,
    }


def _add_file(
    files: dict[str, bytes], root: Path, path: Path, role: str, rows: list[dict[str, Any]]
) -> None:
    relative = _relative(root, path, "audit_dependency_outside_root")
    if relative in files:
        return
    raw = path.read_bytes()
    files[relative] = raw
    rows.append(_file_row(relative, raw, role))


def _audit_dependencies(
    *,
    root: Path,
    manifest_path: Path,
    manifest: Mapping[str, Any],
    objects: Mapping[str, Mapping[str, Mapping[str, Any]]],
    schema_registry_path: Path,
    rights_registry_path: Path,
    rights_signers_path: Path,
    method_registry_path: Path,
    release_signers_path: Path,
    output_registry_path: Path,
) -> tuple[dict[str, bytes], list[dict[str, Any]], list[str]]:
    files: dict[str, bytes] = {}
    rows: list[dict[str, Any]] = []
    excluded_content: list[str] = []

    _add_file(files, root, manifest_path, "canonical_release_manifest", rows)
    release_signature = _safe_file(
        root, manifest["release_signature_path"], "audit_release_signature_missing"
    )
    _add_file(files, root, release_signature, "canonical_release_signature", rows)
    for entry in manifest["objects"]:
        path = _safe_file(root, entry["path"], "audit_object_missing")
        _add_file(files, root, path, f"canonical_object:{entry['object_type']}", rows)

    registries = (
        (schema_registry_path, "schema_registry"),
        (rights_registry_path, "rights_registry"),
        (rights_signers_path, "rights_signer_registry"),
        (method_registry_path, "method_registry"),
        (release_signers_path, "release_signer_registry"),
        (output_registry_path, "output_registry"),
        (root / "governance" / "exposure_projection_registry.json", "projection_registry"),
    )
    for path, role in registries:
        _add_file(files, root, _inside_root(root, path, f"audit_{role}_missing"), role, rows)

    _, schema_registry, _ = _read_json(
        _inside_root(root, schema_registry_path, "audit_schema_registry_missing"),
        "audit_schema_registry_invalid",
    )
    for entry in schema_registry["schemas"]:
        _add_file(
            files,
            root,
            _safe_file(root, entry["path"], "audit_schema_missing"),
            f"schema:{entry['object_type']}",
            rows,
        )
    _, methods, _ = _read_json(
        _inside_root(root, method_registry_path, "audit_method_registry_missing"),
        "audit_method_registry_invalid",
    )
    for entry in methods["methods"]:
        _add_file(
            files,
            root,
            _safe_file(root, entry["implementation_path"], "audit_method_missing"),
            f"method:{entry['method_id']}",
            rows,
        )
    _, rights, _ = _read_json(
        _inside_root(root, rights_registry_path, "audit_rights_registry_missing"),
        "audit_rights_registry_invalid",
    )
    used_sources = {row["source_id"] for row in manifest["rights_snapshot"]}
    for source in rights["sources"]:
        if source["source_id"] not in used_sources:
            continue
        for field, role in (
            ("decision_artifact_path", "rights_decision"),
            ("decision_signature_path", "rights_decision_signature"),
        ):
            _add_file(
                files,
                root,
                _safe_file(root, source[field], f"audit_{role}_missing"),
                f"{role}:{source['source_id']}",
                rows,
            )

    for universe in objects["universe_release"].values():
        for path, role in (
            (universe["frame_artifact"]["path"], "universe_frame"),
            (universe["inclusion_rule"]["implementation_path"], "universe_rule"),
            (universe["inclusion_rule"]["documentation_path"], "universe_rule_documentation"),
        ):
            _add_file(
                files,
                root,
                _safe_file(root, path, f"audit_{role}_missing"),
                f"{role}:{universe['universe_release_id']}",
                rows,
            )
    for evidence in objects["evidence_item"].values():
        artifact_path = evidence["artifact_path"]
        if artifact_path is None:
            if evidence["content_availability"] != "full_bytes":
                excluded_content.append(cast(str, evidence["evidence_id"]))
            continue
        if evidence["rights_use"] not in {"publish_extract", "redistribute_full_record"}:
            _fail("audit_artifact_redistribution_not_allowed", evidence["evidence_id"])
        _add_file(
            files,
            root,
            _safe_file(root, artifact_path, "audit_evidence_artifact_missing"),
            f"evidence_artifact:{evidence['evidence_id']}",
            rows,
        )
    for entity in objects["entity"].values():
        path = entity["geometry"]["artifact_path"]
        if path is not None:
            _add_file(
                files,
                root,
                _safe_file(root, path, "audit_geometry_missing"),
                f"entity_geometry:{entity['entity_id']}",
                rows,
            )
    for path, role in (
        (root / "src" / "evidence_outputs.py", "output_implementation"),
        (root / "src" / "exposure_graph.py", "projection_implementation"),
        (root / "schemas" / "evidence-output-set.schema.json", "output_schema"),
    ):
        _add_file(files, root, _inside_root(root, path, f"audit_{role}_missing"), role, rows)

    rows.sort(key=lambda row: cast(str, row["path"]))
    return files, rows, sorted(excluded_content)


def _audit_readme(manifest: Mapping[str, Any]) -> bytes:
    text = f"""IGRM OFFLINE AUDIT BUNDLE\n\nCanonical release: {manifest['release_id']}\nRelease record SHA-256: {manifest['record_sha256']}\n\nThis deterministic bundle contains the exact signed release, registered schemas,\nmethod bytes, rights decisions, object records and four compiled output artifacts.\nIt deliberately excludes source content not licensed for redistribution.\n\nDo not execute code from an unauthenticated archive. First authenticate this ZIP\nagainst a digest obtained outside the ZIP, extract it without following symlinks,\nand use a separately trusted OGES/IGRM verifier whose digest matches the public\nprofile. Conformance establishes structural and cryptographic integrity, not the\ntruth of source statements, causal attribution, forecast skill or legal advice.\n"""
    return text.encode("utf-8")


def _zip_bytes(files: Mapping[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(files):
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                _fail("audit_archive_path_invalid", name)
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name])
    raw = stream.getvalue()
    if len(raw) > _MAX_ARCHIVE_BYTES:
        _fail("audit_archive_too_large")
    return raw


def _compile(
    manifest_path: Path,
    event_id: str,
    target_entity_id: str,
    *,
    max_hops: int,
    max_paths: int,
    root: Path,
    schema_registry_path: Path,
    rights_registry_path: Path,
    rights_signers_path: Path,
    method_registry_path: Path,
    release_signers_path: Path,
    output_registry_path: Path,
) -> tuple[dict[str, Any], bytes]:
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
    if sum(len(rows) for rows in validated.objects.values()) > _MAX_OBJECTS:
        _fail("output_release_object_limit_exceeded")
    events = validated.objects["event"]
    entities = validated.objects["entity"]
    if event_id not in events:
        _fail("output_event_not_in_release")
    if target_entity_id not in entities:
        _fail("output_target_not_in_release")
    event = events[event_id]
    target = entities[target_entity_id]
    release_day = _parse_day(manifest["effective_date"], "output_release_date_invalid")
    contract, registry_sha, validator = _load_contract(
        root, output_registry_path, release_day
    )
    traversal = exposure_graph.project_event_exposure(
        manifest_path,
        event_id,
        target_entity_id,
        max_hops=max_hops,
        max_paths=max_paths,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
    )
    evidence_ids = sorted(
        {
            evidence_id
            for row in traversal["object_evidence"]
            for evidence_id in row["evidence_ids"]
        }
    )
    _enforce_public_rights(evidence_ids, validated.objects["evidence_item"])
    citations = _evidence_citations(evidence_ids, validated.objects["evidence_item"])
    object_index = [
        {
            "object_type": row["object_type"],
            "object_id": row["object_id"],
            "record_sha256": row["record_sha256"],
        }
        for row in traversal["object_evidence"]
    ]
    object_index.extend(
        _object_ref("evidence_item", validated.objects["evidence_item"][item])
        for item in evidence_ids
    )
    object_index = sorted(object_index, key=lambda row: cast(str, row["object_id"]))

    stem = hashlib.sha256(
        f"{manifest['record_sha256']}:{event_id}:{target_entity_id}:{max_hops}:{max_paths}".encode()
    ).hexdigest()[:12]
    research_body = {
        "output_id": "output:research_package",
        "title": f"Evidence-bound research package — {event['canonical_label']}",
        "as_of": manifest["generated_at"],
        "object_index": object_index,
        "evidence": citations,
        "coverage": {
            "traversal_status": traversal["result"]["status"],
            "returned_paths": traversal["result"]["returned_paths"],
            "truncated": traversal["result"]["truncated"],
            "declared_universes": traversal["coverage"],
        },
        "citation": _citation(manifest, event_id, target_entity_id),
        "limitations": sorted(_RESEARCH_LIMITATIONS),
    }
    board_body = {
        "output_id": "output:board_brief",
        "title": f"Evidence-bound board brief — {event['canonical_label']}",
        "as_of": manifest["generated_at"],
        "review_status": "draft_requires_human_review",
        "sections": _sections(event, target, traversal, evidence_ids),
        "limitations": sorted(_BRIEF_LIMITATIONS),
    }
    claim_body = {
        "output_id": "output:newsroom_claim_card",
        "title": f"Verifiable claim card — {event['canonical_label']}",
        "as_of": manifest["generated_at"],
        "claims": _claims(event, target, traversal, evidence_ids),
        "evidence": citations,
        "correction_route": "https://igrm.in/corrections.html",
        "limitations": sorted(_CLAIM_LIMITATIONS),
    }
    research, research_raw = _attach_artifact(
        research_body, f"igrm-research-{stem}.json"
    )
    board, board_raw = _attach_artifact(board_body, f"igrm-board-{stem}.json")
    claim_card, claim_raw = _attach_artifact(
        claim_body, f"igrm-claim-card-{stem}.json"
    )

    audit_files, dependency_rows, excluded = _audit_dependencies(
        root=root,
        manifest_path=manifest_path,
        manifest=manifest,
        objects=validated.objects,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
        output_registry_path=output_registry_path,
    )
    for name, raw, role in (
        (f"outputs/{research['artifact']['filename']}", research_raw, "research_package"),
        (f"outputs/{board['artifact']['filename']}", board_raw, "board_brief"),
        (f"outputs/{claim_card['artifact']['filename']}", claim_raw, "newsroom_claim_card"),
    ):
        audit_files[name] = raw
        dependency_rows.append(_file_row(name, raw, role))
    readme = _audit_readme(manifest)
    audit_files["AUDIT.md"] = readme
    dependency_rows.append(_file_row("AUDIT.md", readme, "audit_instructions"))
    dependency_rows.sort(key=lambda row: cast(str, row["path"]))
    bundle_manifest = {
        "schema_version": "1.0.0",
        "object_type": "igrm_offline_audit_manifest",
        "release": _release_identity(manifest),
        "output_method": {
            "method_id": contract["method_id"],
            "version": contract["version"],
            "implementation_sha256": contract["implementation_sha256"],
        },
        "files": dependency_rows,
        "excluded_evidence_content": excluded,
        "verification": {
            "network_required": False,
            "bundled_code_execution_required": False,
            "external_authenticated_verifier_required": True,
            "canonical_validation_supported": True,
        },
        "limitations": sorted(_AUDIT_LIMITATIONS),
    }
    bundle_manifest_raw = _json_bytes(bundle_manifest)
    audit_files["bundle-manifest.json"] = bundle_manifest_raw
    archive_raw = _zip_bytes(audit_files)
    audit = {
        "output_id": "output:offline_audit_bundle",
        "artifact": _artifact(f"igrm-audit-{stem}.zip", "application/zip", archive_raw),
        "format": "deterministic_zip_store_v1",
        "bundle_manifest_sha256": _sha_bytes(bundle_manifest_raw),
        "file_count": len(audit_files),
        "canonical_validation_supported": True,
        "external_verifier_required": True,
        "excluded_evidence_content": excluded,
        "limitations": sorted(_AUDIT_LIMITATIONS),
    }
    result = cast(
        dict[str, Any],
        canonical.seal_record(
            {
                "object_type": "evidence_output_set",
                "schema_version": "1.0.0",
                "record_sha256": "0" * 64,
                "release": _release_identity(manifest),
                "contract": {
                    "schema_id": contract["output_schema_id"],
                    "schema_sha256": contract["output_schema_sha256"],
                    "common_schema_sha256": contract["common_schema_sha256"],
                    "output_registry_sha256": registry_sha,
                    "exposure_projection_registry_sha256": contract[
                        "exposure_projection_registry_sha256"
                    ],
                },
                "method": {
                    "method_id": contract["method_id"],
                    "version": contract["version"],
                    "implementation_sha256": contract["implementation_sha256"],
                    "rendering_rule": contract["rendering_rule"],
                },
                "query": {
                    "event_id": event_id,
                    "target_entity_id": target_entity_id,
                    "max_hops": max_hops,
                    "max_paths": max_paths,
                },
                "source_index": {
                    "event": _object_ref("event", event),
                    "target": _object_ref("entity", target),
                    "objects": object_index,
                    "evidence": citations,
                    "structural_paths": traversal["result"]["returned_paths"],
                    "traversal_record_sha256": traversal["record_sha256"],
                    "traversal_truncated": traversal["result"]["truncated"],
                },
                "outputs": {
                    "research_package": research,
                    "board_brief": board,
                    "newsroom_claim_card": claim_card,
                    "offline_audit_bundle": audit,
                },
                "result": {
                    "status": (
                        "compiled"
                        if traversal["result"]["returned_paths"]
                        else "compiled_no_structural_path"
                    ),
                    "output_count": 4,
                    "model_authored_facts": False,
                    "forecast_performed": False,
                    "probability_assigned": False,
                    "causal_attribution_performed": False,
                    "recommendation_generated": False,
                    "scalar_score_computed": False,
                },
                "limitations": sorted(_LIMITATIONS),
            }
        ),
    )
    _schema_check(result, validator)
    return result, archive_raw


def compile_evidence_outputs(
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
    output_registry_path: Path = OUTPUT_REGISTRY,
) -> dict[str, Any]:
    """Return four deterministic outputs from one validated release query."""

    document, _ = _compile(
        manifest_path,
        event_id,
        target_entity_id,
        max_hops=max_hops,
        max_paths=max_paths,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
        output_registry_path=output_registry_path,
    )
    return document


def build_offline_audit_bundle(
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
    output_registry_path: Path = OUTPUT_REGISTRY,
) -> bytes:
    """Return the deterministic offline audit ZIP described by the output set."""

    _, archive = _compile(
        manifest_path,
        event_id,
        target_entity_id,
        max_hops=max_hops,
        max_paths=max_paths,
        root=root,
        schema_registry_path=schema_registry_path,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
        method_registry_path=method_registry_path,
        release_signers_path=release_signers_path,
        output_registry_path=output_registry_path,
    )
    return archive


def verify_offline_audit_bundle(
    archive: bytes,
    *,
    expected_sha256: str,
) -> dict[str, Any]:
    """Authenticate, structurally verify and canonically validate an audit ZIP.

    ``expected_sha256`` is deliberately mandatory and must come from outside
    the archive.  The verifier never imports or executes bundled code.  It
    checks every entry against the internal manifest, extracts only already-
    authenticated regular files into a fresh directory, and then validates the
    signed canonical release with the caller's trusted installed verifier.
    """

    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha256)
    ):
        _fail("audit_external_digest_invalid")
    actual_sha = _sha_bytes(archive)
    if actual_sha != expected_sha256:
        _fail("audit_external_digest_mismatch")
    if len(archive) > _MAX_ARCHIVE_BYTES:
        _fail("audit_archive_too_large")
    try:
        opened = zipfile.ZipFile(io.BytesIO(archive), "r")
    except (zipfile.BadZipFile, OSError):
        _fail("audit_archive_invalid")
    with opened:
        infos = opened.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            _fail("audit_archive_duplicate_path")
        if "bundle-manifest.json" not in names:
            _fail("audit_bundle_manifest_missing")
        total = 0
        file_bytes: dict[str, bytes] = {}
        for info in infos:
            name = info.filename
            path = Path(name)
            if (
                not name
                or name.startswith("/")
                or "\\" in name
                or ".." in path.parts
                or info.is_dir()
            ):
                _fail("audit_archive_path_invalid", name)
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                _fail("audit_archive_nonregular_entry", name)
            if info.compress_type != zipfile.ZIP_STORED:
                _fail("audit_archive_compression_invalid", name)
            if info.date_time != (1980, 1, 1, 0, 0, 0):
                _fail("audit_archive_timestamp_invalid", name)
            total += info.file_size
            if total > _MAX_ARCHIVE_BYTES:
                _fail("audit_archive_expanded_too_large")
            try:
                raw = opened.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                _fail("audit_archive_entry_unreadable", name)
            if len(raw) != info.file_size:
                _fail("audit_archive_entry_size_mismatch", name)
            file_bytes[name] = raw
    try:
        manifest = json.loads(
            file_bytes["bundle-manifest.json"],
            object_pairs_hook=canonical._unique_object,
            parse_constant=canonical._reject_constant,
        )
    except canonical.CanonicalObjectError as exc:
        _fail("audit_bundle_manifest_invalid", exc.code)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail("audit_bundle_manifest_invalid")
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema_version",
        "object_type",
        "release",
        "output_method",
        "files",
        "excluded_evidence_content",
        "verification",
        "limitations",
    }:
        _fail("audit_bundle_manifest_fields_invalid")
    if (
        manifest["schema_version"] != "1.0.0"
        or manifest["object_type"] != "igrm_offline_audit_manifest"
        or not isinstance(manifest["files"], list)
    ):
        _fail("audit_bundle_manifest_identity_invalid")
    rows: dict[str, Mapping[str, Any]] = {}
    for raw_row in manifest["files"]:
        if not isinstance(raw_row, dict) or set(raw_row) != {
            "path",
            "sha256",
            "bytes",
            "role",
        }:
            _fail("audit_bundle_file_row_invalid")
        name = raw_row["path"]
        if not isinstance(name, str) or name in rows:
            _fail("audit_bundle_file_duplicate")
        rows[name] = raw_row
    expected_names = set(rows) | {"bundle-manifest.json"}
    if expected_names != set(file_bytes):
        _fail("audit_bundle_membership_mismatch")
    for name, row in rows.items():
        raw = file_bytes[name]
        if row["bytes"] != len(raw) or row["sha256"] != _sha_bytes(raw):
            _fail("audit_bundle_file_digest_mismatch", name)

    with tempfile.TemporaryDirectory(prefix="igrm-audit-verify-") as temporary:
        root = Path(temporary)
        for name, raw in file_bytes.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        try:
            summary = canonical.validate_release(
                root / "canonical" / "release.json",
                root=root,
                schema_registry_path=root
                / "governance"
                / "canonical_schema_registry.json",
                rights_registry_path=root
                / "governance"
                / "source_rights_registry.json",
                rights_signers_path=root / "governance" / "rights_signers.json",
                method_registry_path=root
                / "governance"
                / "canonical_method_registry.json",
                release_signers_path=root / "governance" / "release_signers.json",
            )
        except canonical.CanonicalObjectError as exc:
            _fail("audit_canonical_release_invalid", exc.code)
    release = manifest["release"]
    if (
        summary["release_id"] != release["release_id"]
        or summary["record_sha256"] != release["record_sha256"]
    ):
        _fail("audit_release_identity_mismatch")
    return {
        "status": "valid",
        "archive_sha256": actual_sha,
        "release_id": summary["release_id"],
        "release_record_sha256": summary["record_sha256"],
        "file_count": len(file_bytes),
        "canonical_release_status": summary["status"],
    }


def validate_evidence_outputs(
    document: Mapping[str, Any],
    manifest_path: Path,
    event_id: str,
    target_entity_id: str,
    **kwargs: Any,
) -> None:
    """Recompile the exact query and refuse any resealed semantic mutation."""

    expected = compile_evidence_outputs(
        manifest_path, event_id, target_entity_id, **kwargs
    )
    if document != expected:
        _fail("output_semantic_mismatch")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compile four evidence-bound products from one canonical release"
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument("event_id")
    parser.add_argument("target_entity_id")
    parser.add_argument("--max-hops", type=int, default=4)
    parser.add_argument("--max-paths", type=int, default=25)
    parser.add_argument("--audit-zip", type=Path)
    args = parser.parse_args(argv)
    try:
        document, archive = _compile(
            args.manifest,
            args.event_id,
            args.target_entity_id,
            max_hops=args.max_hops,
            max_paths=args.max_paths,
            root=ROOT,
            schema_registry_path=canonical.SCHEMA_REGISTRY,
            rights_registry_path=canonical.RIGHTS_REGISTRY,
            rights_signers_path=canonical.RIGHTS_SIGNERS,
            method_registry_path=canonical.METHOD_REGISTRY,
            release_signers_path=canonical.RELEASE_SIGNERS,
            output_registry_path=OUTPUT_REGISTRY,
        )
    except (canonical.CanonicalObjectError, exposure_graph.ExposureGraphError) as exc:
        reason = exc.code
        print(json.dumps({"status": "refused", "stage": "dependency", "reason": reason}))
        raise SystemExit(1) from None
    except EvidenceOutputError as exc:
        print(json.dumps({"status": "refused", "stage": "outputs", "reason": exc.code}))
        raise SystemExit(1) from None
    if args.audit_zip is not None:
        args.audit_zip.write_bytes(archive)
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
