# Live-query admission: design, attacks, acceptance tests

**Status:** design only. No code, no schemas committed as normative, no route.
**Assigned:** Codex execution list item 1, 2026-08-10.
**Author:** Claude (agent), read-only pass over the existing kernel.

---

## 1. The problem, stated precisely

The proof kernel today admits **registered synthetic fixtures**. Everything it
proves rests on the fact that *nobody chose the slice*: the query is part of
the registration, so a result cannot be the product of hunting for a
favourable one.

A live query is, by definition, caller-supplied. Admitting one naively
re-opens exactly the hole the kernel was built to close:

> If the caller authors the selector, the caller authors the finding.

Ten registered refusals and a signed release do not help if the caller can
run the kernel a hundred times and publish the run they liked. The proof
would be sound and the claim would still be dishonest.

**So the design question is not "how do we let queries in".** It is: *how does
a query become admissible without the caller ever holding selector
authority?*

## 2. The core move: parameters, not queries

The caller never supplies a query. The caller supplies **bound arguments to a
registered query template**.

    registered:  QueryTemplate   — the selector shape, authored and signed once
    caller:      ArgumentBinding — values drawn from closed, registered domains

A template fixes: which relation is traversed, which denominator is used,
which fields may be projected, which aggregation is applied, and the bounds.
A binding fixes: which country, which commodity, which period — each drawn
from an enumerated domain the caller did not write.

This is the same discipline the rest of the kernel already uses. The
predicate registry in `mechanism-constraint-scenario` is `default_policy:
deny` with `allowed_expected_values` enumerated per predicate. The template
registry is that idea applied to selection rather than to assertion.

**Consequence:** the space of possible queries is finite, enumerable, and
known before any caller arrives. That is what makes the next section
possible.

## 3. The candidate-universe receipt

Restricting the caller to a template still permits **selective publication**:
run all 240 admissible bindings, publish the one that looks strongest.

So admission is not per-query. It is per **universe**.

A `LiveQueryAdmission` carries:

- `template_id` and its `record_sha256`
- the **complete enumerated binding set** the template admits under the
  supplied domain restriction — not the one binding requested
- `universe_size`, and a digest over the full ordered binding list
- the requested binding's index within that universe

A published result therefore always arrives with its own denominator: *this
is 1 of 240 admissible questions, and here is the list of the other 239.*
A reader can see that a question was one of many, and a later audit can
re-run the rest.

**This is the crux of the design.** Everything else is plumbing. Selection
bias survives every cryptographic control ever invented and dies only when
the denominator of *questions asked* is published alongside the answer.

## 4. Authority rules

1. **Template authorship is a registration act, not a runtime act.** A
   template enters only through a signed governance file. No runtime path
   creates, edits or composes one.
2. **The caller supplies no selector text.** Not SQL, not a path expression,
   not a filter lambda, not a regex, not a field list. Bindings are
   enumerated domain members referenced by id.
3. **Domains are closed and registered.** A domain is a finite list, or a
   range with a registered step. Domains are versioned and hash-pinned.
4. **Template + binding + source release identity determine the result
   completely.** Same three, same bytes. There is no runtime nondeterminism
   and no caller-supplied ordering, seed, or limit.
5. **Rights are evaluated per binding, not per template.** A template may be
   admissible while a specific binding is not, because rights attach to the
   underlying evidence. A rights-ineligible binding refuses; it does not
   silently narrow the universe. See attack A4.
6. **The universe is computed by the kernel, never supplied by the caller.**
   A caller-supplied universe is a caller-authored denominator.
7. **Admission does not imply publication.** An admitted result is an
   internal artifact. Publication remains a separate, human-gated act, as it
   is today.

## 5. Proposed objects

Three new registered objects, all additive. Names indicative.

### 5.1 `QueryTemplate` (registered, signed)

    template_id            stable id
    record_sha256          typed canonical digest, self excluded
    relation               which registered traversal this selects over
    denominator_rule       how the universe for a result is computed
    projection             closed list of fields the result may carry
    aggregation            registered aggregation id, or "none"
    parameters[]           each: {parameter_id, domain_id, required}
    bounds                 max hops, max rows, max universe size
    rights_use_required    the evidence use this template needs
    limitation_ids[]       limitations that attach to every result

### 5.2 `ArgumentBinding` (caller-supplied, validated)

    template_id
    template_record_sha256   caller must pin the exact template it read
    arguments[]              each: {parameter_id, domain_id, member_id}
    requested_at             UTC

Note `template_record_sha256`: a caller binding against a template it has not
actually seen is a caller guessing. Pinning makes template drift a refusal
rather than a silent re-target.

### 5.3 `LiveQueryAdmission` (kernel-produced receipt)

    admission_id
    record_sha256
    template_id, template_record_sha256
    source_release_id, source_release_sha256
    domain_versions{}          domain_id -> record_sha256
    universe_size
    universe_digest            typed canonical digest of the ordered binding list
    universe_truncated         bool; true only when bounds.max_universe exceeded
    requested_index            index of the caller's binding in that universe
    rights_state_per_binding   admitted | refused_rights | refused_coverage
    admitted                   bool
    refusal_code               null, or one of §6
    limitation_ids[]

## 6. Refusal codes

Deny-by-default. Every path below refuses rather than degrades.

    admission_template_unregistered
    admission_template_digest_mismatch
    admission_parameter_unregistered
    admission_domain_unregistered
    admission_domain_digest_mismatch
    admission_member_not_in_domain
    admission_required_parameter_missing
    admission_extra_parameter_supplied
    admission_selector_text_supplied
    admission_universe_exceeds_bound
    admission_universe_not_recomputable
    admission_binding_rights_ineligible
    admission_source_release_unregistered
    admission_source_release_refused
    admission_result_exceeds_projection
    admission_aggregation_unregistered
    admission_nondeterminism_detected
    admission_receipt_digest_mismatch

`admission_selector_text_supplied` is deliberately its own code rather than a
generic schema error: the day something starts sending a filter string is the
day this design has been quietly abandoned, and the log should say so in one
searchable word.

## 7. Attacks

Each is a test to be written before the feature, not after.

**A1 — Caller authors a selector.** Supply a filter expression in a parameter
value, a field list in `projection`, or a `member_id` containing a wildcard.
*Expect:* `admission_selector_text_supplied` or
`admission_member_not_in_domain`. Membership is by identity against the
registered list, never by pattern match.

**A2 — Universe shopping.** Run all admissible bindings, publish the
favourable one. *Expect:* not refused — this is legal and must remain so —
but every result carries `universe_size` and `universe_digest`, so the
selective publication is visible. The test asserts a published result cannot
exist without them.

**A3 — Universe shrinking.** Supply a domain restriction that narrows the
universe so the published denominator looks small and the result looks
central. *Expect:* the restriction itself is a registered domain with its own
id and digest, recorded in `domain_versions`. An unregistered narrowing is
`admission_domain_unregistered`.

**A4 — Rights-driven narrowing.** Choose a binding set where the
rights-ineligible members are silently dropped, shrinking the denominator to
the eligible favourable subset. *Expect:* refused bindings appear in
`rights_state_per_binding` and still count in `universe_size`. A rights
refusal must reduce what is *answerable*, never what is *counted*.

**A5 — Template drift.** Amend a template after a caller read it; the caller's
pinned digest no longer matches. *Expect:*
`admission_template_digest_mismatch`. Never re-target to the new template.

**A6 — Domain drift.** Same, for a domain that gained or lost members between
read and execution. *Expect:* `admission_domain_digest_mismatch`. Silent
domain growth changes a denominator retroactively.

**A7 — Bound evasion.** Request a binding whose traversal exceeds max hops or
whose universe exceeds `max_universe_size`. *Expect:*
`admission_universe_exceeds_bound`, and `universe_truncated` must never be
used to publish a partial denominator as if complete.

**A8 — Nondeterminism.** Execute the same template + binding + release twice,
expect byte-identical admission and result. Any drift is
`admission_nondeterminism_detected`. Includes ordering, dict iteration, and
float formatting.

**A9 — TOCTOU on the universe.** Compute the universe, mutate the underlying
domain or release, then produce the result. *Expect:* the receipt's
`universe_digest` is recomputed at result time and compared; mismatch
refuses. (This is the same class the shadow compiler's ABA finding closed —
verify-to-use gaps on caller-reachable state. Design it out now rather than
patch it later.)

**A10 — Projection escape.** Return a field outside the template's
`projection`. *Expect:* `admission_result_exceeds_projection`. The projection
is an allowlist, and the result is checked against it, not trusted to it.

**A11 — Aggregation laundering.** Use an aggregation that hides missingness —
a mean over rows where some are `source_blank`. *Expect:* registered
aggregations declare their missingness behaviour, and one that would silently
skip nulls is either unregistered or must emit the null count in the result.
No zero substitution, consistent with every other lane.

**A12 — Replay across releases.** Present an admission receipt from release A
alongside a result computed on release B. *Expect:* refusal on
`source_release_sha256` mismatch. Receipts bind to exactly one release.

## 8. Acceptance tests

The feature is not done when it works. It is done when these hold:

1. **No caller-authored selection exists anywhere in the request path.** A
   test greps the request schema and the runtime for any free-text field
   reaching selection, and fails on one.
2. **Every result carries its question denominator.** A result object without
   `universe_size` and `universe_digest` cannot be constructed.
3. **The universe recomputes.** Given the receipt, an independent run
   reproduces the identical ordered binding list and digest, from committed
   bytes alone.
4. **A rights refusal shrinks answerability, not the denominator.** Asserted
   directly, per A4.
5. **Every refusal code in §6 is reachable by a test**, and every code the
   runtime can raise is registered in the contract. (The clause layer already
   does this by scraping `_fail(` out of the module; reuse that.)
6. **Determinism is byte-level**, asserted twice-run, per A8.
7. **Public surface unchanged.** Admission is internal; no route, no payload,
   no public schema changes in the first slice.
8. **The claim boundary is registered and asserted.** See §9.

## 9. Claim boundary, to be registered with the contract

> Admission establishes that a question was drawn from a registered template
> and a closed domain, that the complete set of admissible questions was
> enumerated and digested, and that the result is reproducible from committed
> bytes. It does **not** establish that the question is a good one, that the
> answer is true, that the underlying source is accurate, that the result is
> publishable, or that the caller had no preference among the answers. It
> makes selective publication **visible**, not impossible.

That last sentence is the honest one and should survive into any public copy.

## 10. What I would build first, and what I would not

**First slice:** template registry + domain registry + binding validation +
universe enumeration + admission receipt. No execution against real sources.
Everything above is testable with synthetic domains, and A1–A8 all fire
without a single real query.

**Not in the first slice:** live source execution, any public route, any
caller-facing API, aggregation beyond `none`. Those add rights, latency and
abuse surface to a design whose central claim has not yet been attacked.

**Deliberately not designed here:** rate limiting, authentication, quota. They
are real and they are a different threat model. Mixing them in would let a
reader think selection bias had been handled by an API key.

---

## Open question for Codex

The universe enumeration is the expensive part: it is `O(product of domain
sizes)` per admission, and A9 requires recomputing it at result time. For a
country × commodity × port template that is plausibly tens of thousands of
bindings. Two options, and I do not think it is my call:

- **enumerate eagerly**, digest the full list, accept the cost; or
- **enumerate lazily** with a deterministic ordering and digest a
  *specification* of the universe rather than its materialisation.

The second is much cheaper and strictly weaker: it proves the universe was
*defined*, not that it was *computed*. Given the cost pressure the gate is
already under, I would still choose the first for the initial slice — the
whole point is the denominator, and a specification-digest is exactly the
kind of shortcut that reads fine until someone checks.
