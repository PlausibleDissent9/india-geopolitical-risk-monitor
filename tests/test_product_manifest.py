"""ProductManifest: computed scope, recomputed edges, correction blast-closure.

Design: design/product_manifest_and_correction_closure.md
Codex's [BLOCKING] (.agents/from-codex.md, 00:42): product dependency closure
must be COMPUTABLE, not caller-authored, and the correction closure must catch
a successor that enters a product's scope after a split even though no old
clause referenced it. This suite drives the real 89-clause synthetic bundle
and asserts every attack A1-A8 and the acceptance tests.
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest
from src import product_manifest as pm

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "acsb_fixtures", ROOT / "tests" / "test_analytical_clause_source_binding.py")
_fx = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_fx)

CRUDE = "ent:commodity.synthetic_crude"
ORIGIN = "ent:country.synthetic_origin"


def _bundle(tmp_path: Path):
    _fixture, source, _proof = _fx._compiled(tmp_path / "base")
    return source


def _scope(entity_id: str) -> dict:
    return {"predicate_id": "scope:objects_touching_entity",
            "bindings": {"entity_id": entity_id}}


def _manifest(source, entity_id: str, manifest_id: str = "pm:test") -> dict:
    contract = pm.load_contract()
    scope = _scope(entity_id)
    selected = pm.compute_scope(source["clauses"], scope, contract)["selected_clause_ids"]
    by_id = {c["clause_id"]: c for c in source["clauses"]}
    return {
        "object_type": "product_manifest",
        "schema_version": "0.1.0",
        "manifest_id": manifest_id,
        "record_sha256": "unset",
        "clause_refs": [{"clause_id": c, "clause_record_sha256": by_id[c]["record_sha256"]}
                        for c in selected],
        "selection_scope": scope,
        "output_artifact_refs": [
            {"artifact_id": f"{manifest_id}:research", "artifact_record_sha256": "a" * 64,
             "role": "research"}],
        "universe_receipt": {},
        "limitation_ids": [],
    }


def _op(topology: str, predecessors: list[tuple[str, str]],
        successors: list[tuple[str, str]], validated: bool = True) -> dict:
    return {
        "validated": validated,
        "topology": topology,
        "predecessors": [{"object_type": t, "object_id": i} for t, i in predecessors],
        "successors": [{"object_type": t, "object_id": i} for t, i in successors],
    }


# --- acceptance: the layer works at all -------------------------------------

def test_contract_is_deny_by_default_and_loads() -> None:
    contract = pm.load_contract()
    assert contract["default_policy"] == "deny"
    # Inventory lock: this set moves in the same change that registers a
    # predicate, never loosened to a subset check.
    assert set(contract["scope_predicates"]) == {
        "scope:objects_touching_entity", "scope:objects_touching_event"}


def test_a_real_product_compiles_and_is_deterministic(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    a = pm.compile_product(source, manifest)
    b = pm.compile_product(source, manifest)
    assert a["record_sha256"] == b["record_sha256"], "compilation is non-deterministic (A6)"
    assert len(a["resolved_clause_ids"]) == 43, "crude scope selects 43 of 89"
    assert a["universe_size"] == 89
    assert a["edges_recomputed"] is True


def test_scope_membership_is_computed_not_taken_from_the_manifest(tmp_path: Path) -> None:
    """A2-of-membership: the manifest cannot smuggle in a clause the scope does
    not select, nor omit one it does. clause_refs is a checked pin."""
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    # sneak an extra clause_ref for a clause the scope does not select
    origin_only = [c for c in source["clauses"]
                   if CRUDE not in {r["object_id"] for r in c["proof_binding"]["source_object_refs"]}]
    manifest["clause_refs"].append(
        {"clause_id": origin_only[0]["clause_id"],
         "clause_record_sha256": origin_only[0]["record_sha256"]})
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_clause_ref_unregistered"


# --- attacks ---------------------------------------------------------------

def test_a1_caller_supplied_edge_graph_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["object_clause_edges"] = [{"object_id": "x", "clause_id": "y"}]
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_caller_dependency_graph_supplied"


def test_a2_successor_entering_scope_after_split_is_caught(tmp_path: Path) -> None:
    """The novel property. A manifest with NO clause referencing the
    predecessor (reverse-only misses it) but a clause referencing the
    successor must still be in the blast closure via forward scope match."""
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    by_id = {c["clause_id"]: c for c in source["clauses"]}
    selected = [by_id[r["clause_id"]] for r in manifest["clause_refs"]]
    events = sorted({r["object_id"] for c in selected
                     for r in c["proof_binding"]["source_object_refs"]
                     if r["object_type"] == "event"})
    assert events, "fixture must have an event in a crude clause for this test"
    successor = ("event", events[0])            # referenced -> forward match
    predecessor = ("event", "evt:absent.predecessor")  # not referenced -> reverse miss

    caught = pm.correction_closure([manifest], source, _op("split", [predecessor], [successor]))
    assert caught["affected_manifest_ids"] == ["pm:test"]
    assert caught["affected_artifact_ids"] == ["pm:test:research"]

    # Prove reverse-only would miss: predecessor alone, no successor.
    reverse_only = pm.correction_closure([manifest], source, _op("supersede", [predecessor], []))
    assert reverse_only["affected_manifest_ids"] == [], (
        "a predecessor no clause references must not appear via reverse deps; "
        "this is what makes the forward match in the split case load-bearing")


def test_a3_predecessor_removal_keeps_the_manifest_in_closure(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    by_id = {c["clause_id"]: c for c in source["clauses"]}
    selected = [by_id[r["clause_id"]] for r in manifest["clause_refs"]]
    entity_pred = ("entity", CRUDE)  # every selected clause references this
    assert all(entity_pred in {(r["object_type"], r["object_id"])
                               for r in c["proof_binding"]["source_object_refs"]}
               for c in selected)
    res = pm.correction_closure([manifest], source, _op("supersede", [entity_pred], []))
    assert res["affected_manifest_ids"] == ["pm:test"], (
        "a supersede of an entity every clause references is a reverse-dep hit")


def test_a4_closure_must_not_shrink_without_cause(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    entity_pred = ("entity", CRUDE)
    op = _op("supersede", [entity_pred], [])
    # prior run affected pm:test; a recompute that no longer includes it, with
    # prior_affected asserting it did, must refuse.
    with pytest.raises(pm.ProductManifestError) as err:
        pm.correction_closure(
            [], source, op, prior_affected=["pm:test"])
    assert err.value.code == "correction_closure_shrank_without_cause"


def test_a5_clause_mutation_after_manifest_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["clause_refs"][0]["clause_record_sha256"] = "0" * 64  # stale pin
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_clause_digest_mismatch"


def test_a6_determinism_is_byte_level(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, ORIGIN)
    digests = {pm.compile_product(source, manifest)["record_sha256"] for _ in range(3)}
    assert len(digests) == 1


def test_a7_caller_authored_scope_text_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["selection_scope"] = {"predicate_id": "objects WHERE entity LIKE '%crude%'",
                                   "bindings": {"entity_id": CRUDE}}
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_scope_predicate_unregistered"


def test_a8_unvalidated_lineage_operation_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    op = _op("split", [("event", "evt:x")], [("event", "evt:y")], validated=False)
    with pytest.raises(pm.ProductManifestError) as err:
        pm.correction_closure([manifest], source, op)
    assert err.value.code == "correction_lineage_operation_unvalidated"


# --- acceptance: coverage of the type registry + artifact roles -------------

def test_unregistered_source_object_type_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    source = dict(source)
    clauses = [dict(c) for c in source["clauses"]]
    # corrupt one ref's object_type to something off-registry
    bad = dict(clauses[0])
    pb = dict(bad["proof_binding"])
    refs = [dict(r) for r in pb["source_object_refs"]]
    refs[0] = {**refs[0], "object_type": "arbitrary_smuggled_type"}
    pb["source_object_refs"] = refs
    bad["proof_binding"] = pb
    clauses[0] = bad
    source["clauses"] = clauses
    manifest = _manifest(_bundle(tmp_path / "clean"), CRUDE)
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_source_object_type_unregistered"


def test_artifact_role_must_be_registered(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["output_artifact_refs"][0]["role"] = "marketing"
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_artifact_not_registered_role_projection"


# --- second scope predicate: objects_touching_event -------------------------

EVENT = "evt:oges.fixture.policy.001"


def test_event_scope_predicate_compiles_without_a_runtime_change(tmp_path: Path) -> None:
    """scope:objects_touching_event is a contract addition; compute_scope
    already generalizes over match_object_type/binding_parameter, so no code
    change was needed. 24 of 89 clauses reference the fixture event."""
    source = _bundle(tmp_path)
    contract = pm.load_contract()
    scope = {"predicate_id": "scope:objects_touching_event",
             "bindings": {"event_id": EVENT}}
    selected = pm.compute_scope(source["clauses"], scope, contract)["selected_clause_ids"]
    assert len(selected) == 24, "the fixture event is referenced by 24 clauses"
    by_id = {c["clause_id"]: c for c in source["clauses"]}
    manifest = {
        "object_type": "product_manifest", "schema_version": "0.1.0",
        "manifest_id": "pm:event", "record_sha256": "unset",
        "clause_refs": [{"clause_id": c, "clause_record_sha256": by_id[c]["record_sha256"]}
                        for c in selected],
        "selection_scope": scope,
        "output_artifact_refs": [
            {"artifact_id": "pm:event:research", "artifact_record_sha256": "a" * 64,
             "role": "research"}],
        "universe_receipt": {}, "limitation_ids": [],
    }
    comp = pm.compile_product(source, manifest, contract=contract)
    assert len(comp["resolved_clause_ids"]) == 24

    # A supersede of that event is a direct reverse-dep hit on the event product.
    op = _op("supersede", [("event", EVENT)], [])
    res = pm.correction_closure([manifest], source, op, contract=contract)
    assert res["affected_manifest_ids"] == ["pm:event"]


# --- verify_compilation: an external compilation is reproduced, not trusted ---

def test_verify_compilation_reproduces_a_faithful_external_compilation(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    external = pm.compile_product(source, manifest)  # a faithful external artifact
    result = pm.verify_compilation(external, source, manifest)
    assert result["verified"] is True
    assert result["recomputed_from_bytes"] is True


def test_verify_rejects_a_tampered_release_ref(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    external = dict(pm.compile_product(source, manifest))
    external["source_release_ref"] = {"release_id": "rel:forged", "release_signer_id": "x"}
    with pytest.raises(pm.ProductManifestError) as err:
        pm.verify_compilation(external, source, manifest)
    assert err.value.code == "compilation_release_mismatch"


def test_verify_rejects_a_tampered_edge_set(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    external = dict(pm.compile_product(source, manifest))
    external["clause_manifest_edges"] = external["clause_manifest_edges"][:-1]  # drop one edge
    with pytest.raises(pm.ProductManifestError) as err:
        pm.verify_compilation(external, source, manifest)
    assert err.value.code == "compilation_edge_not_recomputed"


def test_verify_rejects_a_tampered_record_digest(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    external = dict(pm.compile_product(source, manifest))
    # keep every edge faithful but claim a different record digest
    external["record_sha256"] = "0" * 64
    with pytest.raises(pm.ProductManifestError) as err:
        pm.verify_compilation(external, source, manifest)
    assert err.value.code == "compilation_nondeterminism_detected"


# --- acceptance #1: no caller-authored selection exists in the request path -

def test_no_caller_authored_selection_path_exists_in_the_runtime() -> None:
    """Acceptance test #1 (design §9). Membership must be by identity against a
    registered predicate, never by evaluating caller-supplied text. Assert the
    runtime contains no dynamic-evaluation or caller-regex path that could turn
    a binding value into a selector: no eval/exec/compile, and the scope match
    is an identity `in` check, not a pattern match."""
    src = (ROOT / "src" / "product_manifest.py").read_text(encoding="utf-8")
    for forbidden in ("eval(", "exec(", "re.compile(", "re.match(",
                      "re.search(", "fnmatch", "glob("):
        assert forbidden not in src, (
            f"{forbidden!r} in product_manifest.py: a caller binding could "
            "become a selector, re-opening the caller-authored-selection hole")
    # The one membership operator is identity against the registered key.
    assert "(match_type, bound_value) in _clause_object_keys(clause)" in src, (
        "scope membership must be identity against the registered object key; "
        "if this line changed, re-verify no pattern match slipped in")


# --- acceptance #4: correction closure is monotone in P u S -----------------

def test_correction_closure_is_monotone_in_predecessors_and_successors(tmp_path: Path) -> None:
    """Acceptance test #4 (design §9). Adding a successor can only grow the
    affected set, never shrink it. Property-checked over random key sets rather
    than the single A2/A3 examples."""
    source = _bundle(tmp_path)
    manifests = [_manifest(source, CRUDE, "pm:crude"),
                 _manifest(source, ORIGIN, "pm:origin")]
    # a pool of real object keys the manifests' clauses actually reference
    keys = sorted({(r["object_type"], r["object_id"])
                   for c in source["clauses"]
                   for r in c["proof_binding"]["source_object_refs"]
                   if r["object_type"] in ("entity", "event")})
    rng = random.Random(20260811)
    for _ in range(60):
        predecessors = rng.sample(keys, rng.randint(0, len(keys)))
        base_succ = rng.sample(keys, rng.randint(0, len(keys)))
        extra = rng.sample(keys, rng.randint(0, len(keys)))
        op_small = _op("split", predecessors, base_succ)
        op_large = _op("split", predecessors, sorted(set(base_succ) | set(extra)))
        small = set(pm.correction_closure(manifests, source, op_small)["affected_manifest_ids"])
        large = set(pm.correction_closure(manifests, source, op_large)["affected_manifest_ids"])
        assert small <= large, (
            f"closure shrank when successors grew: {small} not subset of {large} "
            f"(P={predecessors}, added successors={extra})")


# --- dedicated triggering case for each remaining refusal code --------------

def test_malformed_clause_refuses_cleanly_not_crashes() -> None:
    """Adversarial self-review: source_bundle is a caller parameter, so a clause
    missing proof_binding (or clause_id, or a well-formed ref) must refuse with a
    typed code per refusal-first, never raise a bare KeyError."""
    contract = pm.load_contract()
    scope = _scope(CRUDE)
    for bad_clause in (
        {"clause_id": "c1", "record_sha256": "0" * 64},   # no proof_binding
        {"clause_id": "c1", "proof_binding": {}},          # no source_object_refs
        {"clause_id": "c1",
         "proof_binding": {"source_object_refs": [{"object_id": "x"}]}},  # ref missing type
        {"proof_binding": {"source_object_refs": []}},     # no clause_id
    ):
        with pytest.raises(pm.ProductManifestError) as err:
            pm.compute_scope([bad_clause], scope, contract)
        assert err.value.code == "manifest_scope_not_recomputable", bad_clause


def test_scope_binding_wrong_key_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["selection_scope"]["bindings"] = {"wrong_key": CRUDE}
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_scope_binding_not_in_domain"


def test_duplicate_clause_id_in_universe_is_not_recomputable(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    dup = dict(source)
    dup["clauses"] = list(source["clauses"]) + [source["clauses"][0]]  # duplicate id
    manifest = _manifest(source, CRUDE)
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(dup, manifest)
    assert err.value.code == "manifest_scope_not_recomputable"


def test_universe_exceeding_the_bound_refuses() -> None:
    contract = pm.load_contract()
    # synthetic universe over the 100k bound; each clause minimal but well-formed
    big = [{"clause_id": f"clause:{i}",
            "proof_binding": {"source_object_refs": []}}
           for i in range(100_001)]
    scope = {"predicate_id": "scope:objects_touching_entity",
             "bindings": {"entity_id": CRUDE}}
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compute_scope(big, scope, contract)
    assert err.value.code == "manifest_universe_exceeds_bound"


def test_empty_artifact_digest_refuses(tmp_path: Path) -> None:
    source = _bundle(tmp_path)
    manifest = _manifest(source, CRUDE)
    manifest["output_artifact_refs"][0]["artifact_record_sha256"] = ""
    with pytest.raises(pm.ProductManifestError) as err:
        pm.compile_product(source, manifest)
    assert err.value.code == "manifest_artifact_digest_mismatch"


def test_every_contract_refusal_code_is_reachable_by_the_runtime() -> None:
    """Stronger than a subset check: every code the contract lists must be one
    the module can actually raise. A contract that claims a code the runtime
    cannot produce is claiming more than the code proves."""
    contract = pm.load_contract()
    reachable = {
        "manifest_source_object_type_unregistered",
        "manifest_clause_ref_unregistered",
        "manifest_clause_digest_mismatch",
        "manifest_scope_predicate_unregistered",
        "manifest_scope_binding_not_in_domain",
        "manifest_scope_not_recomputable",
        "manifest_universe_exceeds_bound",
        "manifest_caller_dependency_graph_supplied",
        "manifest_artifact_not_registered_role_projection",
        "manifest_artifact_digest_mismatch",
        "compilation_edge_not_recomputed",
        "compilation_nondeterminism_detected",
        "compilation_release_mismatch",
        "correction_closure_shrank_without_cause",
        "correction_lineage_operation_unvalidated",
    }
    registered = set(contract["refusal_codes"])
    assert registered == reachable, {
        "in_contract_not_reachable": registered - reachable,
        "reachable_not_in_contract": reachable - registered,
    }
