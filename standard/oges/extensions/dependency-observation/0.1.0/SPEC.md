# OGES DependencyObservation extension — public draft 0.1.0

Effective: 2026-08-09
Status: public draft with an IGRM reference implementation; no government,
industry, ISO or BIS adoption claim.

## Purpose

This extension preserves source facts that have more than two indispensable
roles. A country × commodity × port quantity is not losslessly represented by
two binary edges: doing so destroys the joint association and can make an
unobserved country–port or commodity–port relationship appear established.

`DependencyObservation` therefore records the complete role tuple, provider
labels, crosswalk state, value or missingness state, period, bitemporal
availability, source locator, signed rights snapshot, registered method and
declared joint-frame denominator. It does not itself produce an
`ExposureEdge`.

## Normative files

- `profile.json` pins the base OGES profile, schemas, role registry,
  adversarial cases and reference implementation.
- `dependency-observation.schema.json` defines each joint cell.
- `source-label-frame.schema.json` defines the complete provider-label census
  for one semantic slot.
- `entity-crosswalk-release.schema.json` forces every provider label into
  exactly one matched, unmatched, ambiguous or withheld state.
- `role-registry.json` defines the two initial port-cargo flow semantics and
  explicitly preserves the loaded-country ambiguity.
- `adversarial-cases.json` registers the exact refusal surface.

Reference command for a bundle carrying `observations`, `frames`, `crosswalks`
and `known_entity_ids`:

```bash
python -m src.dependency_observation --bundle /path/to/bundle.json
```

Validation performs no network requests and returns counts, identifiers and
hashes only. It does not print provider values or measurements.

## Complete-frame rule

A conformant bundle contains every member of its declared joint frame. Positive
values, observed zeros, source blanks, explicit source-missing cells,
suppressed cells and not-applicable cells form a mutually exclusive,
exhaustive partition. A blank is never converted to an observed zero or
collapsed into an explicit missing marker. The validator recomputes that
partition and a canonical frame hash from the observations. Publishing only the
positive rows cannot conform.

This rule prevents a producer from hiding zeros or inconvenient missingness and
then presenting the surviving cells as comprehensive coverage.

## Crosswalk rule

Every unique provider label used by a role is present in a hash-bound source
label frame. The corresponding crosswalk release must contain exactly one entry
for every frame member. A `matched` entry requires a known canonical entity,
review evidence and a reviewer. Unmatched, ambiguous and withheld entries keep
their canonical entity null and remain visible in the denominator.

Distinct raw source labels may converge on one canonical identity only when
the downstream release records that alias convergence explicitly. The source
labels remain distinct members of this frame and crosswalk, so convergence
cannot shrink the source denominator. This base extension validates the review
and evidence on each match; a foundry profile may impose the additional
convergence-record requirement.

The crosswalk resolves identity only. It does not resolve the meaning of an
ambiguous source heading. In the Ministry loaded-cargo table, the provider's
`Country of Origin` heading remains the registered ambiguous role; relabelling
it `destination` fails conformance.

## Projection rule

An observation may be marked eligible for a separately registered projection
only when its value is positive, all roles are matched and all role semantics
are resolved. Eligibility is not an edge and does not establish dependence.
Any projection to an OGES `ExposureEdge` needs its own executable method,
universe, evidence, uncertainty and claim boundary.

## Rights and time

The observation binds the exact rights registry, signer registry and signed
decision artifact used for its source. The reference implementation revalidates
the signature and required uses. The source period must end no later than the
observation timestamp, and observation, knowledge-availability and compilation
timestamps must be ordered. This prevents later information from being labelled
as historically knowable.

## Licensed statement

The strongest licensed statement is:

> This joint source-observation frame conforms to the OGES
> DependencyObservation public draft 0.1.0 under the profile identified in its
> conformance report.

Conformance does not establish source truth, national completeness, legal
correctness of a signed rights decision, causal dependence, disruption,
substitution, economic loss, forecast skill, advice or institutional
endorsement.
