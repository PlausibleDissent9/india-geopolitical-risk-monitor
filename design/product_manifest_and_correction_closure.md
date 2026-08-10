# ProductManifest and correction blast-closure: design, attacks, tests

**Status:** design only. No code, no schema committed as normative, no route.
**Assigned:** Codex `.agents/from-codex.md` — the [REQUEST] 00:35 Product
Compiler lane and its [BLOCKING] 00:42 closure constraint — now under founder
authorisation to execute Codex's direction.
**Author:** Claude, read-only pass over `src/analytical_clause.py`,
`src/event_semantic_lineage.py`, `src/evidence_outputs.py`, the admission
design (`design/live_query_admission_contract.md`), and the overlap audit
(`analysis/product_compiler_overlap_audit.md`).

**Boundary with Codex's lane, stated first:** Codex owns the Event Ledger
delta — `event_semantic_lineage.py`, its lineage operations (`supersede`,
`merge`, `split`), competition sets and signed propositions. This design
does **not** redefine or copy any of that. The ProductManifest *consumes* a
validated lineage operation's already-computed predecessor/successor object
keys as an input and never re-derives lineage semantics. One writer per
concept.

---

## 1. What is already done, so this is scoped honestly

The overlap audit's "build the cross-role invariant first, alone"
recommendation shipped: `analytical_clause.py` compiles a clause set from a
signed synthetic release, projects it into seven registered roles, carries
`proof_binding.source_object_refs[]` per clause, and refuses on any
protected-field divergence across roles. 97 adversarial cases execute.

So the **clause** is done and it is already "computable, not caller-authored"
at its own level: the source profile registers exactly two query IDs, the
caller supplies no selector, and the traversal is a deterministic bounded
BFS. Codex's [BLOCKING] asks for that same discipline one level up — at the
**product**, which groups clauses — plus a correction closure. That, and only
that, is the new work here.

## 2. The three objects

### 2.1 `SourceObjectRef` — already exists, formalise its type registry

Clauses already carry `source_object_refs[]` as `{object_type, object_id,
record_sha256}`. Codex's constraint: `object_type` must be drawn from a
**closed registry**, never an arbitrary string, and it must accommodate a
later additive `claim_proposition` type without a schema break.

    registered source_object_types (deny-by-default), enumerated from the
    actual 89-clause synthetic bundle rather than guessed:
        entity  universe_release  exposure_edge  event
        evidence_item  canonical_release        # all present in the fixture today
        claim  episode                          # Codex-named, valid, absent from this fixture
        claim_proposition                        # additive, reserved, unused until Codex ships it

A ref whose `object_type` is outside this set refuses
`manifest_source_object_type_unregistered`. The registry is versioned and
hash-pinned exactly like the predicate registry in the admission design.

**Correction to an earlier draft of this section:** the first version listed
only `event, evidence_item, entity, claim, episode` and would have refused
every real clause — the fixture's refs are 71 `entity`, 41 `universe_release`,
28 `exposure_edge`, 24 `event`, 12 `evidence_item`, 1 `canonical_release`.
Enumerating the live data first is why the registry is right; guessing the
type list is the exact mistake a scope registry exists to prevent.

### 2.2 `ProductManifest` (registered, signed)

    manifest_id            stable id
    record_sha256          typed canonical digest, self excluded
    clause_refs[]          each: {clause_id, clause_record_sha256}
    selection_scope        a REGISTERED scope predicate id + its closed bindings
    output_artifact_refs[] each: {artifact_id, artifact_record_sha256, role}
    universe_receipt       the candidate-universe receipt the scope was drawn against
    limitation_ids[]

`selection_scope` is the crux and §3 is about it. `clause_refs` pins each
clause by digest so a clause mutated after the manifest was built is a
refusal, not a silent re-target (the admission design's A5, applied to
clauses). `output_artifact_refs` binds the seven role renderings; a
manifest is not published, it is *compiled*, and publication stays the
separate human-gated act it is today.

### 2.3 `ProductCompilation` (kernel-produced receipt)

    compilation_id
    record_sha256
    manifest_id, manifest_record_sha256
    source_release_ref            the exact signed release compiled against
    resolved_clause_set[]         every clause the scope selected, recomputed
    object_clause_edges[]         object_ref -> clause_id, from recomputation
    clause_manifest_edges[]       clause_id -> manifest_id
    manifest_artifact_edges[]     manifest_id -> artifact_id
    universe_size, universe_digest
    refusal_code                  null, or one of §7

**The compilation is the authority for every edge.** The correction engine
(§4) reads edges from a *recomputed* ProductCompilation and never from a
caller-supplied graph. This is Codex's hard requirement and it is why the
compilation exists as a distinct object rather than being folded into the
manifest.

## 3. `selection_scope`: computable, not caller-authored

A manifest must not carry a hand-listed set of clause IDs, because a
hand-list is a caller-authored dependency graph wearing a data structure.
Instead:

1. `selection_scope` names a **registered scope predicate** by id, from a
   closed registry (`default_policy: deny`), plus bindings drawn from
   enumerated domains — the exact discipline of the admission contract's
   template+binding split.
2. The kernel **computes** the clause set the predicate selects, over the
   candidate universe of clauses the source release admits, and records
   `universe_size` + `universe_digest`. The caller never lists members.
3. Membership is by the recomputed predicate, evaluated against each
   clause's `source_object_refs`. Example predicate:
   `scope:objects_touching_entity` bound to `entity_id=E`, which selects
   every clause whose `source_object_refs` include a ref to E.

**Consequence that makes §4 possible:** because scope is a *predicate* over
object refs and not a frozen list, a *new* object that satisfies the
predicate is automatically in scope on the next recomputation. This is the
property the correction closure needs, and it falls out of refusing to let
the caller author the list.

## 4. Correction blast-closure

The problem Codex named precisely: after a `split`, a new successor can newly
match a product **even though no old clause referenced it**, so reverse
references from predecessors alone under-cover.

Given a validated lineage operation with predecessor keys `P` and successor
keys `S` (both consumed from Codex's `event_semantic_lineage`, never
recomputed here), the blast closure is:

    affected_manifests =
        { m : m had a clause_manifest_edge from a clause whose
              object_clause_edge referenced any p in P }          # reverse deps
      ∪ { m : m.selection_scope predicate, recomputed against the
              post-operation release, selects any clause referencing
              any x in (P ∪ S) }                                  # forward scope match

    affected_artifacts = { a : manifest_artifact_edge(m -> a),
                           m in affected_manifests }

The first set is reverse dependency (what already pointed at a predecessor).
The second is forward scope match over **P ∪ S** — the successors included,
which is the half a reverse-only closure misses. The union is the blast
radius; artifacts follow by the manifest→artifact edges of the *recomputed*
compilation.

Two invariants:

- **Recompute, don't trust.** Both sets are computed from a freshly validated
  ProductCompilation against the post-operation release. A caller-supplied
  edge list is refused (`manifest_caller_dependency_graph_supplied`).
- **Closure is monotone in P ∪ S.** Adding a successor can only grow the
  affected set, never shrink it. A recomputation that drops a
  previously-affected manifest without a corresponding scope or clause change
  is a bug and is asserted against (test 4).

## 5. Worked example (the split that reverse-refs miss)

Release r0: event `E1` ("border incident, ambiguous"). Manifest `M`,
scope `scope:objects_touching_entity` bound to entity `Gulf`. Clause `C1`
references `E1`, which references `Gulf`. So `M ⊇ {C1}`, artifact `A`.

Lineage `split`: `E1 → {E1a (naval), E1b (trade)}`. `E1b` newly references
`Gulf` too (trade touches the Gulf entity). No existing clause referenced
`E1b` — it did not exist.

- Reverse-only closure from `P={E1}`: finds `C1 → M → A`. Misses that `E1b`
  now needs a clause and that `M` must recompile to include it.
- This design's closure: forward scope match over `P ∪ S = {E1, E1a, E1b}`
  recomputes `M`'s predicate and finds `E1b` in scope, so `M` and `A` are
  correctly in the blast radius and `A` recompiles with the successor.

Test 2 is exactly this scenario, asserted to include `A`.

## 6. Cross-role invariant is inherited, not re-proved

Every artifact in `output_artifact_refs` is a role rendering compiled by the
existing `analytical_clause` role projector, so the protected-field
invariant (no role changes a fact, number, date, unit, denominator,
epistemic type, uncertainty, missingness, citation, rights state or proof
binding) already holds per artifact. The manifest layer adds no new prose
path and no renderer — a manifest that tried to would refuse
`manifest_artifact_not_registered_role_projection`.

## 7. Refusal codes

Deny-by-default.

    manifest_source_object_type_unregistered
    manifest_clause_ref_unregistered
    manifest_clause_digest_mismatch
    manifest_scope_predicate_unregistered
    manifest_scope_binding_not_in_domain
    manifest_scope_not_recomputable
    manifest_universe_exceeds_bound
    manifest_caller_dependency_graph_supplied
    manifest_artifact_not_registered_role_projection
    manifest_artifact_digest_mismatch
    compilation_edge_not_recomputed
    compilation_nondeterminism_detected
    compilation_release_mismatch
    correction_closure_shrank_without_cause
    correction_lineage_operation_unvalidated

`manifest_caller_dependency_graph_supplied` is its own code, like the
admission design's `admission_selector_text_supplied`: the day something
starts passing an edge list is the day this design was abandoned, and the
log should say so in one searchable word.

## 8. Attacks (each a test before the feature)

**A1 — Forged caller dependency graph.** Supply object→clause or
clause→manifest edges alongside the request. *Expect:*
`manifest_caller_dependency_graph_supplied`; every edge is recomputed.

**A2 — Successor entrance after split** (§5). *Expect:* the new successor's
manifest and artifact are in the blast closure via forward scope match, not
dropped because no old clause referenced it.

**A3 — Predecessor removal.** A `supersede` retires a predecessor with no
successor carrying its scope. *Expect:* the manifest is in the closure
(reverse dep) and recompiles to *drop* the clause, and the artifact
recompiles smaller — a removal is a correction, not a silent shrink.

**A4 — Scope / universe shrinkage.** Between compile and recompute, the
registered domain a scope binds to loses members. *Expect:*
`manifest_scope_binding_not_in_domain` or a recorded `universe_digest`
change; the closure never shrinks silently
(`correction_closure_shrank_without_cause`).

**A5 — Clause mutation after manifest.** Amend a clause a manifest pins.
*Expect:* `manifest_clause_digest_mismatch`, never a re-target.

**A6 — Nondeterminism.** Compile the same manifest + release twice.
*Expect:* byte-identical compilation; any drift is
`compilation_nondeterminism_detected`. Includes edge ordering and
`universe_digest`.

**A7 — Caller-authored scope text.** Pass a filter string or lambda as
`selection_scope`. *Expect:* `manifest_scope_predicate_unregistered`;
scope is a registered predicate id, never text.

**A8 — Unvalidated lineage input.** Feed the correction engine a lineage
operation that did not pass Codex's `event_semantic_lineage` validation.
*Expect:* `correction_lineage_operation_unvalidated`; the engine consumes
only validated operations and refuses to recompute lineage itself.

## 9. Acceptance tests

1. No caller-authored edge or selector exists anywhere in the request path
   (grep the schema + runtime, fail on any free-text reaching selection or
   any incoming edge list).
2. Every manifest carries `universe_size` + `universe_digest`; a compilation
   without them cannot be constructed.
3. The scope recomputes: given the compilation, an independent run
   reproduces the identical resolved clause set and edges from committed
   bytes alone.
4. Correction closure is monotone in P ∪ S (A2, A3, A4 together): a property
   test over random predecessor/successor sets asserts the affected set only
   grows as S grows.
5. Every refusal code in §7 is reachable by a test; every code the runtime
   raises is registered (scrape `_fail(`, the clause layer's existing
   pattern).
6. Determinism is byte-level, twice-run (A6).
7. Public surface unchanged: synthetic/contract-only, no route, no payload.
8. `evidence_outputs.py` is byte-for-byte unchanged (its four views become
   clause consumers in a *later* slice, per the overlap audit).

## 10. First slice, and what stays out

**First slice:** source-object-type registry + `ProductManifest` schema +
`selection_scope` predicate registry (one predicate:
`scope:objects_touching_entity`) + `ProductCompilation` with recomputed
edges + the correction blast-closure + tests 1–8 and attacks A1–A8. No new
role renderers — reuse the seven that exist. No public route.

**Out of the first slice:** migrating `evidence_outputs`' four views onto the
clause layer; any second scope predicate; any real (non-synthetic) release;
`claim_proposition` refs (reserved in the type registry, unused until Codex
ships the proposition). Those are additive and each is its own reviewable
commit.

**Ship discipline (Codex's, adopted):** pin every schema/registry/
implementation/test byte; preserve old engines byte-for-byte; one exact
independently-reviewable commit through `scripts/ship.sh`; and — Codex's
explicit stop condition — **do not ship if deterministic scope recomputation
is not yet possible.** Test 3 is that condition made executable; it is the
gate on this slice.

## 11. Claim boundary

The compilation establishes that a product's clause set is the deterministic
image of a registered scope predicate over a signed release, that every
object→clause→manifest→artifact edge was recomputed and not supplied, and
that a correction's blast radius is the monotone union of reverse
dependencies and forward scope matches over predecessors and successors. It
does **not** establish that the product is worth compiling, that the scope
predicate is the right question, that any underlying number is true, or that
the artifact is publishable. It makes a caller-authored dependency graph
**impossible to pass off as computed**, not the product correct.
