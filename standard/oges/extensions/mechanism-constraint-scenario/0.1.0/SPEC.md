# OGES Scenario Proof extension — public draft 0.1.0

Effective: 2026-08-09. Status: executable contract-only sidecar with
test-generated synthetic fixtures and no adoption claim.

## Purpose

Scenario Proof evaluates two narrow questions over an exact existing IGRM
`ShockScenario` and a fully recomputed `ShockCompilation`:

1. does every, no, or only some value in a registered hypothetical interval
   satisfy an exact user-supplied upper bound; and
2. do closed structural falsifier predicates make a registered mechanism
candidate compatible, incompatible or indeterminate with that compiled
hypothetical scenario?

It does not modify Shock Compiler 1.0, create a second shock engine, register a
new Max State Join engine or expand ConsequencePlan 0.1.0. It delegates exact
release, rights, exposure, scenario and compilation validation to the existing
Shock Compiler before evaluating any sidecar object.

## Constraints

Every `RegisteredConstraint` binds one exact scenario, compilation and path.
Version 0.1.0 supports only `upper_bound_lte` over gross affected share,
residual affected share or residual duration. The threshold is a
`hypothetical_normative_boundary`, is supplied by the user, carries no evidence
ID and cannot be described as observed capacity.

For threshold `T` and registered interval `[L,U]`, equality satisfies the
constraint:

- `U <= T`: `all_registered_values_satisfy`;
- `L > T`: `no_registered_values_satisfy`;
- otherwise: `mixed_within_registered_interval`.

The exact margin interval is `[T-U,T-L]`. Stale, unknown-freshness and abstained
upstream paths never produce a satisfied scenario-feasibility status. Each
numeric result carries lower and upper analytical corner witnesses derived from
the already registered monotone Shock transforms. The corners are ranges of
hypothetical inputs, not probabilities or confidence intervals.

## Mechanism hypotheses

Every `MechanismHypothesis` remains `candidate_not_established`, names at least
one non-self rival and at least one closed registered falsifier. Rivalry is
symmetric. The executable predicates are limited to path quantification status,
path gap presence and a constraint interval relation. A triggered falsifier
makes a hypothesis incompatible with the compiled scenario; an unevaluable
predicate makes it indeterminate. Otherwise it is compatible with the compiled
scenario but not supported.

Those words are a hard claim boundary. Compatibility is not evidence for a
mechanism, causal identification, real-world falsification, probability,
ranking, optimality, advice or completeness of the rival set.

Every hypothesis carries a computed registration-timing class. A hypothesis
registered after the scenario was created is `retrospective`; it cannot be
presented as a prospective test merely because its record was later sealed.

## Proof boundary

The reference implementation validates every hash-bound profile artifact,
recomputes the Shock compilation, evaluates deny-by-default operators and
predicates, emits a typed-canonical execution and validates any supplied
execution through full recomputation. A failed input emits no partial proof.
Non-synthetic public rendering still requires the existing claim-bundle gate.

Repository-authored fixtures and tests keep capability maturity at
`contract_only`; they are not independently authenticated execution evidence.
No real source, exposure, capacity, buffer, substitution, disruption,
feasibility, forecast or decision claim is licensed by this extension.
