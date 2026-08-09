"""Fail-closed agreement gate across every IGRM Max engine output.

WHAT THIS EXISTS TO CATCH

`IGRM_MAX_SPEC.md` requires that the maps, the assistant and every product
are "views over one governed state, not separate products that can
disagree".  Until this module, nothing checked that.  Each engine
validated its own inputs impeccably and none of them was ever compared
against another, so the four conformance artifacts published on
2026-08-08 disagreed in public and nothing said so:

    docs/data/evidence_outputs_demo.json   release rel:oges.fixture.2026-08-08
                                           record  e6cc1e33...
                                           event   evt:oges.fixture.policy.001
                                           record  26102763...

    docs/data/sensor_fusion_demo.json      release rel:oges.fixture.2026-08-08
                                           record  8fd9d220...
                                           event   evt:oges.fixture.policy.001
                                           record  224bc5ff...

Same release identifier, same event identifier, different sealed bytes,
different rights-registry digest, shipped side by side as evidence that
the contract works.  Each engine was individually correct.  The *system*
was two systems wearing one set of identifiers.

That is the most expensive shape of defect an evidence system can have,
because every engine's own gate stays green while the composite claim --
"this is what IGRM knows about this event" -- is already false.  A
downstream reader who joins a fusion matrix to a shock compilation by
`event_id` gets a silent cross-world join with no error anywhere.

WHAT THIS DOES

The join is deliberately ignorant of engine internals.  It walks every
supplied document generically and extracts three kinds of binding:

  identity     an identifier (`release_id`, `event_id`, `evidence_id`,
               `scenario_id`, object ids, ...) bound to a content digest
  governance   the registry digests and release identity each engine
               says it compiled against
  rights       the source-level decision each engine says authorised it

An identifier bound to two different digests anywhere in the joined set
is a refusal, not a warning.  There is no reconciliation step and no
"prefer the newer" rule: two answers to "what is this object" means the
system does not have one governed state, and the correct output is an
abstention.

The join computes -- never accepts -- the evidence class and the licensed
digital-twin maturity level.  A world whose sources are synthetic test
authorisations is `synthetic_nonproduction` and is licensed at L0, the
contract level, regardless of how much machinery ran over it.  A world
containing an unapproved rights decision is not publishable at all.  A
join therefore cannot be talked upward by adding engines to it.

WHAT THIS IS NOT

It validates each engine's output schema, content seal and exact registered
implementation/schema/registry identity.  It does not semantically recompile
an engine result or independently verify the underlying release signature;
those remain the engine gate's job.  It proves agreement, not correctness.
Agreement across four synthetic engines is evidence that the contract
composes; it is never evidence that a real dependency, observation or
exposure exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry, Resource

from src import canonical_objects as canonical

ROOT = Path(__file__).resolve().parents[1]
JOIN_REGISTRY = ROOT / "governance" / "max_state_join_registry.json"

_METHOD_ID = "method:igrm.max_state_join"
_METHOD_VERSION = "1.0.0"
_OUTPUT_SCHEMA_ID = "https://igrm.in/schemas/max-state-join.schema.json"
_SCHEMA_VERSION = "1.0.0"

# Keys whose value identifies something the system must have exactly one
# of, in OWNERSHIP order.  A mapping's digest describes the mapping
# itself, not every identifier it happens to mention: a shock scenario
# carries `scenario_id`, `record_sha256` and a foreign `event_id`, and
# binding that digest to the event would invent a collision with the
# event's real record.  The first key present therefore owns the digest
# and the rest are read as references.
#
# Adding an engine that introduces a new identifier kind must add it
# here, or the join silently stops covering it.
_IDENTITY_PRECEDENCE = (
    "object_id",
    "scenario_id",
    "ledger_id",
    "universe_release_id",
    "release_id",
    "evidence_id",
    "edge_id",
    "event_id",
    "entity_id",
)

# Canonical object types share a namespace with the typed identifier key
# that names the same thing.  Without this, `{"object_type": "event",
# "object_id": X}` and `{"event_id": X}` would live in separate
# namespaces and the two engines that disagreed about event X on
# 2026-08-08 would still not be compared.
_OBJECT_TYPE_NAMESPACE = {
    "canonical_release": "release_id",
    "entity": "entity_id",
    "event": "event_id",
    "evidence_item": "evidence_id",
    "exposure_edge": "edge_id",
    "universe_release": "universe_release_id",
}

# Digest keys, in the order a binding prefers them.  `record_sha256` is
# the sealed identity of a canonical object; `content_sha256` is the
# bytes a source served; `file_sha256` is an on-disk artifact.  They are
# separate namespaces and are never compared against one another.
_DIGEST_KEYS = ("record_sha256", "content_sha256", "file_sha256")

# Release-identity fields every engine reports.  All of them must agree
# across every joined document, including the governance registry
# digests: an engine that compiled against a different rights registry
# compiled against a different world.
_RELEASE_REQUIRED_FIELDS = (
    "release_id",
    "record_sha256",
    "effective_date",
    "release_signer_id",
    "schema_registry_sha256",
    "method_registry_sha256",
    "rights_registry_sha256",
    "rights_signers_sha256",
    "release_signers_sha256",
)

# Fields some engine schemas legitimately omit. `exposure_traversal` binds
# the release by effective date and digest and carries no generation
# time. Absence is structural and is not a disagreement; a *different*
# value where two engines both report one is.  At least one engine must
# supply `generated_at`, because it is the anchor every knowledge cutoff
# is checked against.
_RELEASE_OPTIONAL_FIELDS = ("generated_at",)
_RELEASE_FIELDS = _RELEASE_REQUIRED_FIELDS + _RELEASE_OPTIONAL_FIELDS

_RIGHTS_FIELDS = ("decision_id", "decision_artifact_sha256", "signer_id")

_EVIDENCE_CLASSES = ("unapproved_rights", "synthetic_nonproduction", "observed")
_MATURITY_LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")

_MAX_DOCUMENT_BYTES = 25_000_000
_MAX_BINDINGS = 200_000
_MAX_DEPTH = 40

_LIMITATIONS = (
    "The join proves that every supplied engine output describes one release, "
    "one set of object identities and one rights position; it does not "
    "re-derive any engine's result.",
    "Each engine output is schema-checked and bound to registered code, schema "
    "and engine-registry bytes, but semantic recompilation and underlying "
    "release-signature validation remain the engine gate's responsibility.",
    "Agreement is not accuracy: four engines can agree perfectly about a world "
    "that no observation supports.",
    "The evidence class and licensed maturity level are computed from the "
    "joined rights positions and are never accepted from an input.",
    "A synthetic world is licensed at L0 and carries no dependency, exposure, "
    "propagation, adoption or utility claim.",
    "Absence of a collision is bounded by the engines actually supplied; the "
    "join cannot see a world no engine reported.",
    "The join performs no numeric fusion, averaging, unit conversion, forecast, "
    "probability, causal attribution or scalar scoring.",
)


class MaxStateJoinError(ValueError):
    """A stable fail-closed refusal to certify one governed state."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise MaxStateJoinError(code, detail)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("join_json_duplicate_key", key)
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    _fail("join_json_non_finite")


def _read_json(path: Path, code: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except (OSError, UnicodeDecodeError):
        _fail(code, str(path))
    if len(raw) > _MAX_DOCUMENT_BYTES:
        _fail("join_document_too_large", str(path))
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(code, str(path))
    if not isinstance(parsed, dict):
        _fail(code, str(path))
    return cast(dict[str, Any], parsed), hashlib.sha256(raw).hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(value: object, code: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(code, repr(value))
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        _fail(code, value)
    if parsed.tzinfo != timezone.utc:
        _fail(code, value)
    return parsed


# ---------------------------------------------------------------------------
# contract
# ---------------------------------------------------------------------------


class _Contract:
    """The registered join contract and its pinned digests."""

    def __init__(
        self,
        row: Mapping[str, Any],
        registry_sha: str,
        root: Path,
        engine_validators: Mapping[str, Draft202012Validator],
    ):
        self.row = row
        self.registry_sha = registry_sha
        self.root = root
        self.engine_validators = engine_validators


def _safe_file(root: Path, raw: object, code: str) -> Path:
    if not isinstance(raw, str) or not raw:
        _fail(code)
    base = root.resolve()
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        _fail(code, raw)
    if not candidate.is_file():
        _fail(code, raw)
    return candidate


def _schema_validator(root: Path, schema_path: Path) -> Draft202012Validator:
    """Load one registered schema and every local relative ``$ref`` it uses."""

    schemas_root = (root / "schemas").resolve()
    pending = [schema_path.resolve()]
    loaded: dict[Path, dict[str, Any]] = {}
    resources: list[tuple[str, Resource[Any]]] = []
    while pending:
        path = pending.pop()
        if path in loaded:
            continue
        try:
            path.relative_to(schemas_root)
        except ValueError:
            _fail("join_engine_schema_path_invalid", str(path))
        document, _ = _read_json(path, "join_engine_schema_unreadable")
        loaded[path] = document
        resource = Resource.from_contents(document)
        resources.append((path.name, resource))
        schema_id = document.get("$id")
        if isinstance(schema_id, str) and schema_id:
            resources.append((schema_id, resource))
        for _, node in _walk(document, "", 0):
            reference = node.get("$ref")
            if not isinstance(reference, str) or reference.startswith("#"):
                continue
            relative = reference.split("#", 1)[0]
            if not relative or "://" in relative:
                continue
            dependency = (path.parent / relative).resolve()
            try:
                dependency.relative_to(schemas_root)
            except ValueError:
                _fail("join_engine_schema_reference_invalid", reference)
            if not dependency.is_file():
                _fail("join_engine_schema_reference_missing", reference)
            pending.append(dependency)
    schema = loaded[schema_path.resolve()]
    try:
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(
            schema,
            registry=Registry().with_resources(resources),
            format_checker=FormatChecker(),
        )
    except SchemaError:
        _fail("join_engine_schema_invalid", str(schema_path))


def _load_contract(root: Path, registry_path: Path) -> _Contract:
    document, registry_sha = _read_json(registry_path, "join_registry_unreadable")
    if document.get("schema_version") != "1.0.0":
        _fail("join_registry_schema_version_invalid")
    if document.get("default_policy") != "deny":
        _fail("join_registry_default_policy_invalid")
    row = document.get("join")
    if not isinstance(row, dict):
        _fail("join_registry_row_invalid")
    if row.get("method_id") != _METHOD_ID or row.get("version") != _METHOD_VERSION:
        _fail("join_registry_method_invalid")
    implementation = root / cast(str, row.get("implementation_path", ""))
    if not implementation.is_file() or _sha(implementation) != row.get("implementation_sha256"):
        _fail("join_implementation_digest_mismatch")
    schema_path = root / cast(str, row.get("output_schema_path", ""))
    if not schema_path.is_file() or _sha(schema_path) != row.get("output_schema_sha256"):
        _fail("join_output_schema_digest_mismatch")
    common_path = root / cast(str, row.get("common_schema_path", ""))
    if not common_path.is_file() or _sha(common_path) != row.get("common_schema_sha256"):
        _fail("join_common_schema_digest_mismatch")
    if row.get("output_schema_id") != _OUTPUT_SCHEMA_ID:
        _fail("join_output_schema_id_invalid")
    engines = row.get("engines")
    if not isinstance(engines, list) or not engines:
        _fail("join_registry_engines_invalid")
    seen: set[str] = set()
    engine_validators: dict[str, Draft202012Validator] = {}
    for engine in engines:
        if not isinstance(engine, dict):
            _fail("join_registry_engines_invalid")
        engine_id = engine.get("engine_id")
        if not isinstance(engine_id, str) or engine_id in seen:
            _fail("join_registry_engines_invalid")
        seen.add(engine_id)
        for field in (
            "object_type",
            "method_id",
            "method_version",
            "implementation_path",
            "implementation_sha256",
            "output_schema_id",
            "output_schema_path",
            "output_schema_sha256",
            "engine_registry_path",
            "engine_registry_sha256",
            "document_schema_id_field",
            "document_schema_sha256_field",
            "document_registry_sha256_field",
        ):
            if not isinstance(engine.get(field), str):
                _fail("join_registry_engines_invalid")
        if not isinstance(engine.get("required"), bool):
            _fail("join_registry_engines_invalid")
        if not isinstance(engine.get("carries_release_identity"), bool):
            _fail("join_registry_engines_invalid")
        implementation = _safe_file(
            root, engine["implementation_path"], "join_engine_implementation_missing"
        )
        if _sha(implementation) != engine["implementation_sha256"]:
            _fail("join_engine_implementation_digest_mismatch", engine_id)
        schema_path = _safe_file(
            root, engine["output_schema_path"], "join_engine_schema_missing"
        )
        if _sha(schema_path) != engine["output_schema_sha256"]:
            _fail("join_engine_schema_digest_mismatch", engine_id)
        schema_document, _ = _read_json(schema_path, "join_engine_schema_unreadable")
        if schema_document.get("$id") != engine["output_schema_id"]:
            _fail("join_engine_schema_id_mismatch", engine_id)
        engine_registry = _safe_file(
            root, engine["engine_registry_path"], "join_engine_registry_missing"
        )
        if _sha(engine_registry) != engine["engine_registry_sha256"]:
            _fail("join_engine_registry_digest_mismatch", engine_id)
        engine_validators[engine_id] = _schema_validator(root, schema_path)
    policy = row.get("maturity_policy")
    if not isinstance(policy, dict) or set(policy) != set(_EVIDENCE_CLASSES):
        _fail("join_registry_maturity_policy_invalid")
    for value in policy.values():
        if value not in _MATURITY_LEVELS:
            _fail("join_registry_maturity_policy_invalid")
    markers = row.get("synthetic_access_basis_markers")
    if not isinstance(markers, list) or not markers or not all(
        isinstance(marker, str) and marker for marker in markers
    ):
        _fail("join_registry_synthetic_markers_invalid")
    return _Contract(row, registry_sha, root, engine_validators)


def _output_validator(contract: _Contract) -> Draft202012Validator:
    schema_path = contract.root / cast(str, contract.row["output_schema_path"])
    common_path = contract.root / cast(str, contract.row["common_schema_path"])
    schema, _ = _read_json(schema_path, "join_output_schema_unreadable")
    common, _ = _read_json(common_path, "join_common_schema_unreadable")
    registry = Registry().with_resources(
        [
            ("common.schema.json", Resource.from_contents(common)),
            (cast(str, common.get("$id", "")), Resource.from_contents(common)),
        ]
    )
    try:
        return Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
    except SchemaError:
        _fail("join_output_schema_invalid")


# ---------------------------------------------------------------------------
# generic binding extraction
# ---------------------------------------------------------------------------


def _walk(node: object, path: str, depth: int) -> Iterator[tuple[str, Mapping[str, Any]]]:
    """Yield every mapping in *node* with the JSON pointer that reaches it."""

    if depth > _MAX_DEPTH:
        _fail("join_document_too_deep", path)
    if isinstance(node, Mapping):
        yield path, node
        for key, value in node.items():
            if isinstance(value, (Mapping, list)):
                yield from _walk(value, f"{path}/{key}", depth + 1)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, (Mapping, list)):
                yield from _walk(value, f"{path}/{index}", depth + 1)


def _identity_bindings(
    engine_id: str, document: Mapping[str, Any]
) -> list[dict[str, str]]:
    """Extract every (identifier, digest-kind, digest) binding in *document*.

    A mapping contributes a binding when it carries both an identifier and
    a digest.  `object_id` binds under the value of a sibling
    `object_type` when present so that two different object kinds can
    never be forced into one namespace by an id collision.
    """

    bindings: list[dict[str, str]] = []
    for pointer, node in _walk(document, "", 0):
        digests = {
            key: node[key]
            for key in _DIGEST_KEYS
            if isinstance(node.get(key), str)
        }
        if not digests:
            continue
        owner = next(
            (
                key
                for key in _IDENTITY_PRECEDENCE
                if isinstance(node.get(key), str) and node[key]
            ),
            None,
        )
        if owner is None:
            continue
        identifier = cast(str, node[owner])
        kind = owner
        if owner == "object_id":
            object_type = node.get("object_type")
            kind = (
                _OBJECT_TYPE_NAMESPACE.get(object_type, f"object:{object_type}")
                if isinstance(object_type, str)
                else "object"
            )
        for digest_key, digest in sorted(digests.items()):
            bindings.append(
                {
                    "engine_id": engine_id,
                    "identifier_kind": kind,
                    "identifier": identifier,
                    "digest_kind": digest_key,
                    "digest": digest,
                    "pointer": pointer or "/",
                }
            )
            if len(bindings) > _MAX_BINDINGS:
                _fail("join_too_many_bindings", engine_id)
    return bindings


def _collisions(bindings: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    """Return every identifier bound to more than one digest of a kind."""

    grouped: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for binding in bindings:
        key = (binding["identifier_kind"], binding["identifier"], binding["digest_kind"])
        grouped.setdefault(key, {}).setdefault(binding["digest"], []).append(
            f"{binding['engine_id']}{binding['pointer']}"
        )
    collisions: list[dict[str, Any]] = []
    for (kind, identifier, digest_kind), digests in sorted(grouped.items()):
        if len(digests) < 2:
            continue
        collisions.append(
            {
                "identifier_kind": kind,
                "identifier": identifier,
                "digest_kind": digest_kind,
                "digests": [
                    {"digest": digest, "reported_by": sorted(where)}
                    for digest, where in sorted(digests.items())
                ],
            }
        )
    return collisions


# ---------------------------------------------------------------------------
# per-engine checks
# ---------------------------------------------------------------------------


def _engine_rows(contract: _Contract) -> dict[str, Mapping[str, Any]]:
    return {
        cast(str, row["engine_id"]): row
        for row in cast(list[Mapping[str, Any]], contract.row["engines"])
    }


def _check_engine(
    contract: _Contract,
    engine_id: str,
    row: Mapping[str, Any],
    document: Mapping[str, Any],
) -> None:
    if document.get("object_type") != row["object_type"]:
        _fail("join_engine_object_type_mismatch", engine_id)
    method = document.get("method")
    if not isinstance(method, Mapping):
        _fail("join_engine_method_missing", engine_id)
    if method.get("method_id") != row["method_id"]:
        _fail("join_engine_method_mismatch", engine_id)
    if method.get("version") != row["method_version"]:
        _fail("join_engine_method_version_mismatch", engine_id)
    if method.get("implementation_sha256") != row["implementation_sha256"]:
        _fail("join_engine_implementation_mismatch", engine_id)
    engine_contract = document.get("contract")
    if not isinstance(engine_contract, Mapping):
        _fail("join_engine_contract_missing", engine_id)
    checks = (
        ("document_schema_id_field", "output_schema_id", "join_engine_schema_id_mismatch"),
        (
            "document_schema_sha256_field",
            "output_schema_sha256",
            "join_engine_schema_digest_mismatch",
        ),
        (
            "document_registry_sha256_field",
            "engine_registry_sha256",
            "join_engine_registry_digest_mismatch",
        ),
    )
    for field_name, registered_name, code in checks:
        document_field = cast(str, row[field_name])
        if engine_contract.get(document_field) != row[registered_name]:
            _fail(code, engine_id)
    errors = sorted(
        contract.engine_validators[engine_id].iter_errors(document),
        key=lambda error: (list(error.absolute_path), str(error.validator)),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.absolute_path)
        _fail("join_engine_schema_violation", f"{engine_id}:{path or '/'}:{first.validator}")
    sealed = document.get("record_sha256")
    if not isinstance(sealed, str):
        _fail("join_engine_unsealed", engine_id)
    if canonical.canonical_record_sha256(document) != sealed:
        _fail("join_engine_digest_mismatch", engine_id)


def _release_identity(
    engine_id: str, document: Mapping[str, Any]
) -> dict[str, str]:
    release = document.get("release")
    if not isinstance(release, Mapping):
        _fail("join_engine_release_missing", engine_id)
    identity: dict[str, str] = {}
    for field in _RELEASE_REQUIRED_FIELDS:
        value = release.get(field)
        if not isinstance(value, str) or not value:
            _fail("join_engine_release_field_invalid", f"{engine_id}:{field}")
        identity[field] = value
    for field in _RELEASE_OPTIONAL_FIELDS:
        value = release.get(field)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            _fail("join_engine_release_field_invalid", f"{engine_id}:{field}")
        identity[field] = value
    return identity


def _rights_rows(
    engine_id: str, document: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    """Collect source_id -> decision triple from anywhere in *document*."""

    rows: dict[str, dict[str, str]] = {}
    for pointer, node in _walk(document, "", 0):
        source_id = node.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            continue
        present = [field for field in _RIGHTS_FIELDS if field in node]
        if present and not all(
            isinstance(node.get(field), str) and node.get(field)
            for field in _RIGHTS_FIELDS
        ):
            _fail("join_rights_position_incomplete", f"{engine_id}:{pointer or '/'}")
        if not present:
            continue
        decision = {field: cast(str, node[field]) for field in _RIGHTS_FIELDS}
        held = rows.get(source_id)
        if held is not None and held != decision:
            _fail("join_rights_decision_disagreement", source_id)
        rows[source_id] = decision
    return rows


def _knowledge_cutoffs(engine_id: str, document: Mapping[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for pointer, node in _walk(document, "", 0):
        value = node.get("knowledge_cutoff")
        if isinstance(value, str) and value:
            found.append(
                {"engine_id": engine_id, "pointer": pointer or "/", "knowledge_cutoff": value}
            )
    return found


def _coverage_denominators(
    engine_id: str, document: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Collect every declared coverage denominator with its population key."""

    rows: list[dict[str, Any]] = []
    for pointer, node in _walk(document, "", 0):
        counts = node.get("counts")
        universe = node.get("universe_release_id")
        if isinstance(counts, Mapping) and isinstance(universe, str):
            total = counts.get("total_eligible")
            if isinstance(total, int) and not isinstance(total, bool):
                rows.append(
                    {
                        "engine_id": engine_id,
                        "pointer": pointer or "/",
                        "population_key": f"universe:{universe}",
                        "denominator": total,
                    }
                )
            continue
        denominator = node.get("denominator")
        fraction = node.get("fraction")
        if isinstance(denominator, str) and denominator and fraction is not None:
            observed = node.get("observed_lane_ids")
            missing = node.get("missing_lane_ids")
            if isinstance(observed, list) and isinstance(missing, list):
                rows.append(
                    {
                        "engine_id": engine_id,
                        "pointer": pointer or "/",
                        "population_key": f"named:{denominator}",
                        "denominator": len(observed) + len(missing),
                    }
                )
    return rows


# ---------------------------------------------------------------------------
# evidence class and licensed maturity
# ---------------------------------------------------------------------------


def _evidence_class(
    contract: _Contract,
    rights: Mapping[str, Mapping[str, str]],
    source_states: Mapping[str, Mapping[str, Any]] | None,
) -> str:
    """Compute -- never accept -- the evidence class of the joined world.

    The rule is monotone downward.  One unapproved source makes the whole
    world unapproved; one synthetic authorisation caps the whole world at
    synthetic.  There is no averaging and no majority.
    """

    if not rights:
        _fail("join_no_rights_position")
    if source_states is None:
        # Without the release's own source records the join cannot see an
        # approval state, so it refuses to certify anything stronger than
        # the weakest class it can prove.
        return "synthetic_nonproduction"
    markers = cast(list[str], contract.row["synthetic_access_basis_markers"])
    weakest = "observed"
    for source_id in sorted(rights):
        state = source_states.get(source_id)
        if state is None:
            _fail("join_rights_source_not_in_release", source_id)
        if state.get("decision_state") != "approved":
            return "unapproved_rights"
        basis = state.get("access_basis")
        if not isinstance(basis, str) or any(marker in basis for marker in markers):
            weakest = "synthetic_nonproduction"
    return weakest


def _validated_source_states(
    release: Mapping[str, str],
    rights: Mapping[str, Mapping[str, str]],
    *,
    rights_root: Path | None,
    rights_registry_path: Path | None,
    rights_signers_path: Path | None,
) -> Mapping[str, Mapping[str, Any]] | None:
    """Load the exact signed rights snapshot sealed by the joined release.

    A caller-supplied dictionary is not evidence of an approval.  Observation
    status is reachable only from registry bytes whose digest and signer
    registry digest are the ones every joined engine reports.
    """

    supplied = (
        rights_root is not None,
        rights_registry_path is not None,
        rights_signers_path is not None,
    )
    if not any(supplied):
        return None
    if not all(supplied):
        _fail("join_rights_validation_inputs_incomplete")
    assert rights_root is not None
    assert rights_registry_path is not None
    assert rights_signers_path is not None
    try:
        source_states, registry_sha, signers_sha = canonical._validate_rights(
            rights_root, rights_registry_path, rights_signers_path
        )
    except canonical.CanonicalObjectError as error:
        _fail("join_rights_registry_invalid", error.code)
    if registry_sha != release["rights_registry_sha256"]:
        _fail("join_rights_registry_digest_mismatch")
    if signers_sha != release["rights_signers_sha256"]:
        _fail("join_rights_signers_digest_mismatch")
    for source_id, decision in rights.items():
        state = source_states.get(source_id)
        if state is None:
            _fail("join_rights_source_not_in_release", source_id)
        expected = {
            "decision_id": state.get("decision_id"),
            "decision_artifact_sha256": state.get("decision_artifact_sha256"),
            "signer_id": state.get("signer_id"),
        }
        if decision != expected:
            _fail("join_rights_decision_registry_mismatch", source_id)
    return source_states


def _licensed_maturity(contract: _Contract, evidence_class: str) -> str:
    policy = cast(Mapping[str, str], contract.row["maturity_policy"])
    level = policy.get(evidence_class)
    if level is None:
        _fail("join_maturity_policy_missing_class", evidence_class)
    return level


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def join_engine_states(
    engine_documents: Mapping[str, Mapping[str, Any]],
    *,
    root: Path = ROOT,
    join_registry_path: Path = JOIN_REGISTRY,
    rights_root: Path | None = None,
    rights_registry_path: Path | None = None,
    rights_signers_path: Path | None = None,
) -> dict[str, Any]:
    """Certify that every supplied engine output describes one governed state.

    ``engine_documents`` maps a registered ``engine_id`` to that engine's
    sealed output. Observation status requires the exact signed rights and
    signer registries sealed by the release; without those byte-level inputs
    the join caps the world at ``synthetic_nonproduction``.
    """

    contract = _load_contract(root, join_registry_path)
    rows = _engine_rows(contract)

    if not isinstance(engine_documents, Mapping) or not engine_documents:
        _fail("join_no_engine_documents")
    for engine_id in engine_documents:
        if engine_id not in rows:
            _fail("join_engine_unregistered", engine_id)
    for engine_id, row in rows.items():
        if row["required"] and engine_id not in engine_documents:
            _fail("join_engine_missing", engine_id)

    ordered = sorted(engine_documents)
    bindings: list[dict[str, str]] = []
    releases: dict[str, dict[str, str]] = {}
    rights: dict[str, dict[str, str]] = {}
    rights_conflicts: list[dict[str, Any]] = []
    cutoffs: list[dict[str, str]] = []
    coverage: list[dict[str, Any]] = []

    for engine_id in ordered:
        document = engine_documents[engine_id]
        if not isinstance(document, Mapping):
            _fail("join_engine_document_invalid", engine_id)
        row = rows[engine_id]
        _check_engine(contract, engine_id, row, document)
        bindings.extend(_identity_bindings(engine_id, document))
        if row["carries_release_identity"]:
            releases[engine_id] = _release_identity(engine_id, document)
        for source_id, decision in sorted(_rights_rows(engine_id, document).items()):
            held = rights.get(source_id)
            if held is None:
                rights[source_id] = decision
            elif held != decision:
                rights_conflicts.append(
                    {
                        "source_id": source_id,
                        "engine_id": engine_id,
                        "held": held,
                        "reported": decision,
                    }
                )
        cutoffs.extend(_knowledge_cutoffs(engine_id, document))
        coverage.extend(_coverage_denominators(engine_id, document))

    if not releases:
        _fail("join_no_release_identity")

    # One governed state: every release-bearing engine must report the
    # identical release identity, registry digests included. A field an
    # engine's schema omits is not compared; a field two engines both
    # report and disagree on is a refusal.
    reference: dict[str, str] = {}
    reported_by: dict[str, str] = {}
    for engine_id in sorted(releases):
        for field, value in sorted(releases[engine_id].items()):
            agreed = reference.get(field)
            if agreed is None:
                reference[field] = value
                reported_by[field] = engine_id
            elif agreed != value:
                _fail(
                    "join_release_identity_disagreement",
                    f"{field}:{reported_by[field]}!={engine_id}",
                )
    if "generated_at" not in reference:
        _fail("join_release_generated_at_unavailable")

    collisions = _collisions(bindings)
    if collisions:
        first = collisions[0]
        _fail(
            "join_object_identity_collision",
            f"{first['identifier_kind']}:{first['identifier']}",
        )

    if rights_conflicts:
        _fail("join_rights_decision_disagreement", rights_conflicts[0]["source_id"])

    generated_at = _utc(reference["generated_at"], "join_release_generated_at_invalid")
    for row_cutoff in cutoffs:
        moment = _utc(row_cutoff["knowledge_cutoff"], "join_knowledge_cutoff_invalid")
        if moment > generated_at:
            _fail(
                "join_knowledge_cutoff_after_release",
                f"{row_cutoff['engine_id']}{row_cutoff['pointer']}",
            )

    denominators: dict[str, set[int]] = {}
    for row_coverage in coverage:
        denominators.setdefault(cast(str, row_coverage["population_key"]), set()).add(
            cast(int, row_coverage["denominator"])
        )
    for population_key, values in sorted(denominators.items()):
        if len(values) > 1:
            _fail("join_coverage_denominator_disagreement", population_key)

    source_states = _validated_source_states(
        reference,
        rights,
        rights_root=rights_root,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
    )
    evidence_class = _evidence_class(contract, rights, source_states)
    licensed_maturity = _licensed_maturity(contract, evidence_class)
    if evidence_class == "unapproved_rights":
        _fail("join_world_not_publishable", "unapproved_rights")

    document = canonical.seal_record(
        {
            "object_type": "max_state_join",
            "schema_version": _SCHEMA_VERSION,
            "release": dict(reference),
            "contract": {
                "output_schema_id": _OUTPUT_SCHEMA_ID,
                "output_schema_sha256": contract.row["output_schema_sha256"],
                "common_schema_sha256": contract.row["common_schema_sha256"],
                "join_registry_sha256": contract.registry_sha,
            },
            "method": {
                "method_id": _METHOD_ID,
                "version": _METHOD_VERSION,
                "implementation_sha256": contract.row["implementation_sha256"],
            },
            "engines": [
                {
                    "engine_id": engine_id,
                    "object_type": cast(str, rows[engine_id]["object_type"]),
                    "method_id": cast(str, rows[engine_id]["method_id"]),
                    "method_version": cast(str, rows[engine_id]["method_version"]),
                    "record_sha256": cast(str, engine_documents[engine_id]["record_sha256"]),
                    "carries_release_identity": bool(rows[engine_id]["carries_release_identity"]),
                }
                for engine_id in ordered
            ],
            "identity": {
                "bindings_examined": len(bindings),
                "distinct_identifiers": len(
                    {(row["identifier_kind"], row["identifier"]) for row in bindings}
                ),
                "collisions": [],
            },
            "rights": [
                {"source_id": source_id, **rights[source_id]}
                for source_id in sorted(rights)
            ],
            "temporal": {
                "release_generated_at": reference["generated_at"],
                "knowledge_cutoffs": sorted(
                    {row_cutoff["knowledge_cutoff"] for row_cutoff in cutoffs}
                ),
            },
            "coverage": [
                {"population_key": key, "denominator": sorted(values)[0]}
                for key, values in sorted(denominators.items())
            ],
            "result": {
                "status": "one_governed_state",
                "evidence_class": evidence_class,
                "licensed_maturity": licensed_maturity,
                "public_claim_state": (
                    "requires_claim_bundle"
                    if licensed_maturity != "L0"
                    else "contract_conformance_only"
                ),
                "numeric_fusion_performed": False,
                "forecast_performed": False,
                "probability_assigned": False,
                "causal_attribution_performed": False,
                "recommendation_generated": False,
                "scalar_score_computed": False,
            },
            "limitations": list(_LIMITATIONS),
        }
    )
    validator = _output_validator(contract)
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        _fail("join_output_schema_violation", canonical._schema_error_detail(errors[0]))
    if canonical.canonical_record_sha256(document) != document["record_sha256"]:
        _fail("join_output_digest_mismatch")
    return document


def join_engine_state_files(
    paths: Mapping[str, Path],
    *,
    pointer: str | None = None,
    root: Path = ROOT,
    join_registry_path: Path = JOIN_REGISTRY,
    rights_root: Path | None = None,
    rights_registry_path: Path | None = None,
    rights_signers_path: Path | None = None,
) -> dict[str, Any]:
    """Join engine outputs read from disk.

    ``pointer`` names a single top-level key to unwrap, for published
    demo payloads that wrap the sealed engine record in a `_meta` header.
    """

    documents: dict[str, Mapping[str, Any]] = {}
    for engine_id, path in sorted(paths.items()):
        parsed, _ = _read_json(path, "join_engine_document_unreadable")
        if pointer is not None:
            inner = parsed.get(pointer)
            if not isinstance(inner, Mapping):
                _fail("join_engine_document_pointer_missing", f"{engine_id}:{pointer}")
            documents[engine_id] = cast(Mapping[str, Any], inner)
        else:
            documents[engine_id] = parsed
    return join_engine_states(
        documents,
        root=root,
        join_registry_path=join_registry_path,
        rights_root=rights_root,
        rights_registry_path=rights_registry_path,
        rights_signers_path=rights_signers_path,
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Certify that IGRM Max engine outputs describe one governed state."
    )
    parser.add_argument(
        "--engine",
        action="append",
        default=[],
        metavar="ENGINE_ID=PATH",
        help="Sealed engine output to join. Repeat once per engine.",
    )
    parser.add_argument(
        "--pointer",
        default=None,
        help="Top-level key to unwrap in each document (e.g. compilation).",
    )
    parser.add_argument("--registry", type=Path, default=JOIN_REGISTRY)
    parser.add_argument("--rights-root", type=Path)
    parser.add_argument("--rights-registry", type=Path)
    parser.add_argument("--rights-signers", type=Path)
    args = parser.parse_args(argv)

    paths: dict[str, Path] = {}
    for entry in args.engine:
        engine_id, separator, raw = str(entry).partition("=")
        if not separator or not engine_id or not raw:
            print("join_cli_engine_argument_invalid", file=sys.stderr)
            raise SystemExit(2)
        paths[engine_id] = Path(raw)
    if not paths:
        print("join_cli_no_engines", file=sys.stderr)
        raise SystemExit(2)
    try:
        document = join_engine_state_files(
            paths,
            pointer=args.pointer,
            join_registry_path=args.registry,
            rights_root=args.rights_root,
            rights_registry_path=args.rights_registry,
            rights_signers_path=args.rights_signers,
        )
    except MaxStateJoinError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
