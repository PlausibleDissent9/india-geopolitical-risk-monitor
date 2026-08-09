# OGES Decision Switch extension — public draft 0.1.0

Effective: 2026-08-09. Status: executable contract-only sidecar with
test-generated synthetic fixtures and no adoption claim.

## Purpose

Decision Switch answers three narrow questions over an exact, complete set of
fully recomputed OGES Scenario Proof executions:

1. which user-registered hypothetical options satisfy every required
   constraint for every value in each registered marginal interval across a
   complete finite binary assumption lattice;
2. which inclusion-minimal registered assumption subsets change that robust
   option set relative to the empty-atom baseline; and
3. how much resolving a registered set of binary atoms can reduce ambiguity
   among the lattice's decision-state signatures.

It does not modify Scenario Proof or Shock Compiler, and it does not infer an
objective, option order, utility function, expected value, probability,
recommendation, purchase decision, causal effect, joint distribution or
real-world feasibility. Every option, binary switch atom and information scope
is supplied by the request and explicitly remains hypothetical.

## Option classification

Every option binds exactly one constraint for every registered constraint slot,
and the Scenario Proof constraint universe must equal that registered slot
universe. Extra, omitted, duplicated or ignored constraints refuse the whole
execution. The classification is deliberately conservative:

- any unavailable input or mixed marginal relation makes the option
  `indeterminate_due_to_mixed_or_unavailable_registered_inputs`;
- otherwise, any universally violated constraint makes it
  `excluded_by_registered_hypothetical_violation`; and
- only universal satisfaction of every required constraint makes it
  `robustly_satisfies_all_registered_hypothetical_bounds`.

The last status proves a conjunction of universal marginal bounds. The mixed
status does not assert that a jointly feasible realization exists.

## Switch sets and observation priority

The request supplies every member of the powerset of at most six binary atoms,
and every variant supplies a complete Scenario Proof bundle for every option.
The executor fully recomputes every bundle, proves that active atoms use their
registered alternative semantic values, inactive atoms use their baselines,
and no unregistered scenario, constraint, time or hypothesis field changed.
It then emits every inclusion-minimal atom subset whose robust option set
differs from the empty-atom baseline. Minimality is exact only inside that
complete registered binary lattice; it is not a claim about the smallest real
intervention.

Information candidates bind registered atom subsets and the sole 0.1
synthetic resolution method. For each candidate the executor partitions the
complete lattice, counts distinct decision-state signatures, reports worst-
and best-case remaining signature counts, exact set-cardinality reduction,
fixed-background fibers whose signatures change, and affected option IDs.
Candidates receive Pareto layers over those exact dimensions. There is no
weighted score or total priority. Counts over a finite lattice are not entropy,
probability, expected uncertainty reduction, expected utility, acquisition
value or purchase advice. The launch `value_of_information` capability remains
`target_only` until separately registered real resolution methods and a
validated expectation model exist.

## Proof boundary

The reference implementation validates every hash-bound profile artifact,
requires the exact Scenario Proof implementation and profile, fully
recomputes the supplied Scenario Proof, evaluates only registered operators,
emits a typed-canonical execution and validates any supplied execution by full
recomputation. Every constraint and hypothesis is also bound to the normalized
semantics of its referenced path; preserving the same unordered path set while
remapping an object to another path is an unregistered semantic change. A
failed dependency emits no partial decision result.

Repository-authored fixtures keep maturity at `contract_only`. Non-synthetic
public rendering still requires the existing claim-bundle and release gates.
No real option, decision, observation acquisition, feasibility, expected value,
forecast, advice or decision-quality claim is licensed by this extension.
