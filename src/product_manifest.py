"""Compile registered AnalyticalClauses into products by a COMPUTED scope.

A ProductManifest groups clauses from one signed synthetic release into an
audience-agnostic product. The manifest never carries a hand-listed clause
set -- a hand-list is a caller-authored dependency graph wearing a data
structure. It carries a registered ``selection_scope`` predicate, and this
module RECOMPUTES which clauses the predicate selects, then checks the
manifest's pinned ``clause_refs`` against that recomputation. A clause the
scope does not select, or one it selects that the manifest omits, refuses.

The correction blast-closure (``correction_closure``) answers "which products
does a lineage operation touch". Reverse dependencies alone under-cover: after
a split, a NEW successor can match a product's scope even though no old clause
referenced it. So the closure is the union of reverse dependencies over
predecessors and forward scope matches over predecessors AND successors,
recomputed against the post-operation release -- never a caller-supplied graph.

Design, attacks and acceptance tests: design/product_manifest_and_correction_closure.md
Boundary: the Event Ledger semantic-lineage extension (Codex's lane) is
authoritative for lineage operations; this module consumes their already
validated predecessor/successor keys and never re-derives lineage semantics.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, cast

from src import event_ledger_extension

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "governance" / "product_manifest_contract.json"

_MANIFEST_FIELDS = frozenset({
    "object_type", "schema_version", "manifest_id", "record_sha256",
    "clause_refs", "selection_scope", "output_artifact_refs",
    "universe_receipt", "limitation_ids",
})
_SCOPE_FIELDS = frozenset({"predicate_id", "bindings"})
_CLAUSE_REF_FIELDS = frozenset({"clause_id", "clause_record_sha256"})
_ARTIFACT_REF_FIELDS = frozenset({"artifact_id", "artifact_record_sha256", "role"})
_MAX_UNIVERSE = 100_000


class ProductManifestError(ValueError):
    """Stable fail-closed refusal for the product-manifest compiler."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _fail(code: str, detail: str = "") -> NoReturn:
    raise ProductManifestError(code, detail)


def _typed_sha(value: object) -> str:
    return event_ledger_extension.typed_record_sha256(cast(Mapping[str, Any], value))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            _fail("manifest_caller_dependency_graph_supplied", "json_duplicate_key")
        out[key] = value
    return out


def _object(value: object, fields: frozenset[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or frozenset(value) != fields:
        _fail(code)
    return cast(dict[str, Any], value)


def _text(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


# ---------------------------------------------------------------------------
# Contract


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"),
                              object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductManifestError("manifest_scope_not_recomputable",
                                   "contract_unreadable") from exc
    if contract.get("default_policy") != "deny":
        _fail("manifest_scope_not_recomputable", "contract_not_deny_by_default")
    return cast(dict[str, Any], contract)


# ---------------------------------------------------------------------------
# Scope: the computed clause set


def _clause_object_keys(clause: Mapping[str, Any]) -> set[tuple[str, str]]:
    refs = clause["proof_binding"]["source_object_refs"]
    return {(ref["object_type"], ref["object_id"]) for ref in refs}


def _validate_source_object_types(
    source_clauses: Sequence[Mapping[str, Any]], contract: Mapping[str, Any]
) -> None:
    allowed = set(contract["source_object_types"])
    for clause in source_clauses:
        for ref in clause["proof_binding"]["source_object_refs"]:
            if ref["object_type"] not in allowed:
                _fail("manifest_source_object_type_unregistered", ref["object_type"])


def compute_scope(
    source_clauses: Sequence[Mapping[str, Any]],
    selection_scope: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute which clauses a registered scope predicate selects.

    Returns the ordered selected clause-id list, the universe size/digest over
    the full ordered clause-id list, and the object->clause edges the match
    produced. The caller supplies no member list; membership is by predicate.
    """
    scope = _object(selection_scope, _SCOPE_FIELDS, "manifest_scope_predicate_unregistered")
    predicate_id = _text(scope["predicate_id"], "manifest_scope_predicate_unregistered")
    registry = contract["scope_predicates"]
    if predicate_id not in registry:
        _fail("manifest_scope_predicate_unregistered", predicate_id)
    spec = registry[predicate_id]
    bindings = scope["bindings"]
    if not isinstance(bindings, dict):
        _fail("manifest_scope_predicate_unregistered", "bindings_not_object")
    param = spec["binding_parameter"]
    if frozenset(bindings) != frozenset({param}):
        _fail("manifest_scope_binding_not_in_domain", "unexpected_binding_keys")
    bound_value = _text(bindings[param], "manifest_scope_binding_not_in_domain")
    match_type = spec["match_object_type"]

    universe_ids = [clause["clause_id"] for clause in source_clauses]
    if len(universe_ids) > _MAX_UNIVERSE:
        _fail("manifest_universe_exceeds_bound", str(len(universe_ids)))
    if len(set(universe_ids)) != len(universe_ids):
        _fail("manifest_scope_not_recomputable", "duplicate_clause_id_in_universe")

    selected: list[str] = []
    object_clause_edges: list[dict[str, str]] = []
    for clause in source_clauses:
        keys = _clause_object_keys(clause)
        if (match_type, bound_value) in keys:
            selected.append(clause["clause_id"])
            object_clause_edges.append({
                "object_type": match_type,
                "object_id": bound_value,
                "clause_id": clause["clause_id"],
            })
    return {
        "predicate_id": predicate_id,
        "bindings": dict(bindings),
        "selected_clause_ids": selected,
        "universe_size": len(universe_ids),
        "universe_digest": _typed_sha({"ordered_clause_ids": universe_ids}),
        "object_clause_edges": sorted(
            object_clause_edges, key=lambda e: (e["object_id"], e["clause_id"])),
    }


# ---------------------------------------------------------------------------
# Compilation: recomputed edges, never trusted


def _reject_caller_edges(manifest: Mapping[str, Any]) -> None:
    """No object->clause, clause->manifest or manifest->artifact edge list may
    arrive from the caller. Only clause_refs (pins), a scope (predicate) and
    artifact_refs (pins) are legal inputs; any *_edges key is a supplied graph."""
    for key in manifest:
        if key.endswith("_edges") or key in {
                "object_clause_edges", "clause_manifest_edges",
                "manifest_artifact_edges"}:
            _fail("manifest_caller_dependency_graph_supplied", key)


def compile_product(
    source_bundle: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a manifest against a source bundle and emit a ProductCompilation
    whose every edge is recomputed. The manifest's clause_refs are a PIN checked
    against the recomputed scope, not an authority for membership."""
    contract = contract or load_contract()
    _reject_caller_edges(manifest)
    man = _object(manifest, _MANIFEST_FIELDS, "manifest_scope_not_recomputable")

    source_clauses = source_bundle["clauses"]
    _validate_source_object_types(source_clauses, contract)
    by_id = {c["clause_id"]: c for c in source_clauses}

    scope_result = compute_scope(source_clauses, man["selection_scope"], contract)
    recomputed_ids = scope_result["selected_clause_ids"]

    # clause_refs is a pin: recomputed scope membership must match it exactly,
    # by id and by digest. This is what makes the manifest a checkable claim
    # rather than a caller-authored clause list.
    claimed = man["clause_refs"]
    if not isinstance(claimed, list):
        _fail("manifest_clause_ref_unregistered", "clause_refs_not_list")
    claimed_map: dict[str, str] = {}
    for ref in claimed:
        r = _object(ref, _CLAUSE_REF_FIELDS, "manifest_clause_ref_unregistered")
        cid = _text(r["clause_id"], "manifest_clause_ref_unregistered")
        if cid in claimed_map:
            _fail("manifest_clause_ref_unregistered", f"duplicate:{cid}")
        claimed_map[cid] = _text(r["clause_record_sha256"], "manifest_clause_ref_unregistered")
    if set(claimed_map) != set(recomputed_ids):
        _fail("manifest_clause_ref_unregistered", "clause_refs_disagree_with_recomputed_scope")
    for cid in recomputed_ids:
        if cid not in by_id:
            _fail("manifest_clause_ref_unregistered", cid)
        if claimed_map[cid] != by_id[cid]["record_sha256"]:
            _fail("manifest_clause_digest_mismatch", cid)

    # Artifact refs must each name a registered role; digests are pins.
    artifacts = man["output_artifact_refs"]
    if not isinstance(artifacts, list):
        _fail("manifest_artifact_not_registered_role_projection", "artifact_refs_not_list")
    roles = set(contract.get("roles", ())) or _default_roles()
    artifact_edges: list[dict[str, str]] = []
    for art in artifacts:
        a = _object(art, _ARTIFACT_REF_FIELDS, "manifest_artifact_not_registered_role_projection")
        role = _text(a["role"], "manifest_artifact_not_registered_role_projection")
        if role not in roles:
            _fail("manifest_artifact_not_registered_role_projection", role)
        _text(a["artifact_record_sha256"], "manifest_artifact_digest_mismatch")
        artifact_edges.append({
            "manifest_id": man["manifest_id"],
            "artifact_id": _text(a["artifact_id"],
                                 "manifest_artifact_not_registered_role_projection"),
            "role": role,
        })

    clause_manifest_edges = [
        {"clause_id": cid, "manifest_id": man["manifest_id"]}
        for cid in recomputed_ids
    ]
    compilation = {
        "object_type": "product_compilation",
        "manifest_id": man["manifest_id"],
        "source_release_ref": dict(source_bundle["source_release"]),
        "resolved_clause_ids": list(recomputed_ids),
        "object_clause_edges": scope_result["object_clause_edges"],
        "clause_manifest_edges": clause_manifest_edges,
        "manifest_artifact_edges": sorted(
            artifact_edges, key=lambda e: e["artifact_id"]),
        "universe_size": scope_result["universe_size"],
        "universe_digest": scope_result["universe_digest"],
        "edges_recomputed": True,
    }
    compilation["record_sha256"] = _typed_sha(compilation)
    return compilation


def _default_roles() -> set[str]:
    return {"research", "board", "newsroom", "public", "api",
            "priority_language", "offline"}


def verify_compilation(
    external_compilation: Mapping[str, Any],
    source_bundle: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify an untrusted ProductCompilation by recomputing it from bytes.

    An external caller (an audit bundle, a second runtime, a stored artifact)
    presents a compilation. Trusting it would re-open the hole compile_product
    closed: the whole point is that edges are recomputed, not supplied. So this
    recomputes the compilation from the source bundle and manifest and compares.

    - release ref must match           -> compilation_release_mismatch
    - every edge set must match exactly -> compilation_edge_not_recomputed
    - the record digest must match      -> compilation_nondeterminism_detected

    A pass means the external compilation is the deterministic image of the
    committed bytes; it is not trusted, it is reproduced.
    """
    contract = contract or load_contract()
    recomputed = compile_product(source_bundle, manifest, contract=contract)

    if external_compilation.get("source_release_ref") != recomputed["source_release_ref"]:
        _fail("compilation_release_mismatch", external_compilation.get("manifest_id", ""))

    for edge_key in ("object_clause_edges", "clause_manifest_edges",
                     "manifest_artifact_edges", "resolved_clause_ids"):
        if external_compilation.get(edge_key) != recomputed[edge_key]:
            _fail("compilation_edge_not_recomputed", edge_key)

    if external_compilation.get("record_sha256") != recomputed["record_sha256"]:
        _fail("compilation_nondeterminism_detected", recomputed["record_sha256"])

    return {
        "verified": True,
        "manifest_id": recomputed["manifest_id"],
        "record_sha256": recomputed["record_sha256"],
        "recomputed_from_bytes": True,
    }


# ---------------------------------------------------------------------------
# Correction blast-closure


def correction_closure(
    manifests: Sequence[Mapping[str, Any]],
    source_bundle_after: Mapping[str, Any],
    lineage_operation: Mapping[str, Any],
    *,
    contract: Mapping[str, Any] | None = None,
    prior_affected: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Which manifests (and their artifacts) a validated lineage operation
    touches. Union of reverse dependencies over predecessors and forward scope
    matches over predecessors AND successors, recomputed against the
    post-operation release. Monotone non-decreasing in predecessor+successor
    keys."""
    contract = contract or load_contract()

    if lineage_operation.get("validated") is not True:
        _fail("correction_lineage_operation_unvalidated", "operation_not_validated")
    predecessors = {(_text(k["object_type"], "correction_lineage_operation_unvalidated"),
                     _text(k["object_id"], "correction_lineage_operation_unvalidated"))
                    for k in lineage_operation["predecessors"]}
    successors = {(_text(k["object_type"], "correction_lineage_operation_unvalidated"),
                   _text(k["object_id"], "correction_lineage_operation_unvalidated"))
                  for k in lineage_operation["successors"]}
    union_keys = predecessors | successors

    source_clauses = source_bundle_after["clauses"]
    _validate_source_object_types(source_clauses, contract)

    affected: set[str] = set()
    affected_artifacts: set[str] = set()
    for manifest in manifests:
        _reject_caller_edges(manifest)
        mid = manifest["manifest_id"]
        # Recompute the scope against the POST-operation release.
        scope_result = compute_scope(source_clauses, manifest["selection_scope"], contract)
        selected = set(scope_result["selected_clause_ids"])
        selected_clauses = [c for c in source_clauses if c["clause_id"] in selected]

        # Reverse dependency: a selected clause references any predecessor.
        reverse = any(
            (predecessors & _clause_object_keys(c)) for c in selected_clauses)
        # Forward scope match: a selected clause references any key in P u S
        # (this is the half a reverse-only closure misses -- new successors).
        forward = any(
            (union_keys & _clause_object_keys(c)) for c in selected_clauses)
        if reverse or forward:
            affected.add(mid)
            for art in manifest["output_artifact_refs"]:
                affected_artifacts.add(art["artifact_id"])

    if prior_affected is not None:
        dropped = set(prior_affected) - affected
        if dropped:
            _fail("correction_closure_shrank_without_cause", ",".join(sorted(dropped)))

    return {
        "topology": lineage_operation.get("topology"),
        "predecessor_keys": sorted(f"{t}:{i}" for t, i in predecessors),
        "successor_keys": sorted(f"{t}:{i}" for t, i in successors),
        "affected_manifest_ids": sorted(affected),
        "affected_artifact_ids": sorted(affected_artifacts),
    }


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover - CLI
    parser = argparse.ArgumentParser(
        description="Validate the ProductManifest contract is loadable and deny-by-default.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        contract = load_contract()
        print(f"[product-manifest] contract {contract['contract_id']} ok; "
              f"{len(contract['source_object_types'])} types, "
              f"{len(contract['refusal_codes'])} codes")
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
