# OGES Source Frame / Entity Foundry extension — public draft 0.1.0

Effective: 2026-08-09
Status: executable contract-only L0 surface with a test-generated signed
synthetic fixture. No independently authenticated synthetic-verification claim
is shipped; the Ministry reference source is rights-blocked and produces no
public value artifact.

## Purpose

This profile composes existing OGES and IGRM machinery. It does not introduce a
parallel entity store, observation format or release system. A conformant
package contains existing `SourceLabelFrame`, `EntityCrosswalkRelease` and
`DependencyObservation` records, binds canonical entities and
`UniverseRelease` denominators from one already validated canonical release,
and is itself hash-bound as an evidence item in that signed release.

The primary reference contract is the exact 2024–25 Ministry Basic Port
Statistics table 2.1.6: unloaded cargo only, the 483 printed country-of-origin
within principal-commodity source rows × the 13 printed Major-Port/dock-system
columns on registered PDF pages 106–117. The real source has no signed decision
authorizing all required uses, so its exact row-tuple frame is withheld and the
reference command emits only a contract/refusal state.

## Source-frame and normalization rules

Every raw provider label remains a distinct member of its label frame. A
normalization registry states the exact operation used to produce an indexing
key, while the raw label remains authoritative in the frame, crosswalk and
observation. Two raw labels producing the same normalized key refuse the
package; a producer must revise the registered rule instead of silently
collapsing labels.

Many-to-one crosswalk convergence is permitted for genuine reviewed aliases.
Each convergence must be recorded explicitly with all raw labels, review
evidence, reviewers and the `many_to_one_alias_convergence` limitation. The raw
labels continue to count separately in source coverage. Duplicate source
entries are forbidden by the base crosswalk validator, while duplicate
canonical entity definitions are forbidden by canonical-release identity
checks.

Matched, unmatched, ambiguous and withheld states exactly partition every
label frame. Only distinct matched canonical identities enter the bound
`UniverseRelease`; unresolved raw labels remain visible in the source-label
denominator and coverage report. No unresolved label is guessed.

Each universe binding pins the exact `UniverseRelease.record_sha256`. This
profile uses a dedicated canonical release: its complete Entity set must equal
both the union of matched crosswalk identities and the union of members in the
three bound universes. An unrelated Entity or a same-ID universe revision
refuses the package rather than inflating or retargeting foundry scope.

## Complete joint-frame rule

The source contract enumerates separate raw country, commodity and port label
frames plus an ordered, hash-sealed row-tuple frame. Each row tuple preserves
the printed country and commodity labels together with its page and source-row
identity. The package must contain exactly one n-ary observation for every
registered row tuple × dock-column coordinate. It must not invent the absent
cross-pairs that a global country × commodity Cartesian product would create.
The signed release binds the package bytes and the profile binds the source
contract, preventing a coordinated package/denominator shrink.

Observed positive, observed zero, source blank, explicit source missing,
suppressed and not-applicable are mutually exclusive and exhaustive. A blank
cannot become zero, and a positive-only extract cannot claim completeness.
All locators must use the registered document, table, page and printed column.

## Rights and release rule

Validation first executes the canonical release verifier, including schema,
method, rights-decision, signer, expiry, object and signature checks. It then
executes the DependencyObservation verifier against the same rights snapshot.
The package must be an exact public-extract evidence artifact named by the
signed release.

A human signature is evidence that a registered human made the recorded scope
decision. It is not a claim that the decision is legally correct. Missing,
expired, revoked or wrong-use authorization refuses the package.

## Refused semantics

This V0 profile refuses loaded cargo, any inferred loaded-cargo destination,
firms, vessels, routes, capacity, buffers, live/current state, all-India port
coverage, causality and binary dependency-edge decomposition. A conformant
package establishes structural synthetic conformance only. It is not a real
vertical, L1 observation layer, L2 dependency map, legal clearance,
all-source completeness claim or production-readiness claim.

## Commands

Real-source refusal/readiness status:

```bash
python -m src.source_frame_entity_foundry --status
```

Validate an authorized package already bound into a canonical release:

```bash
python -m src.source_frame_entity_foundry \
  --manifest /path/to/release.json \
  --package /path/to/foundry-package.json
```
