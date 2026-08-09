# OGES TRACE_NARY_ASSOCIATION extension — public draft 0.1.0

Effective: 2026-08-09
Status: executable contract-only surface with test-generated synthetic fixtures.
The Ministry reference remains rights-review-required and emits no labels,
tuples, values, traces, page or API.

## Purpose

`TRACE_NARY_ASSOCIATION` is a deterministic sidecar over one exact signed
Source Frame / Entity Foundry package. It reuses the existing
`DependencyObservation`, `SourceLabelFrame`, `EntityCrosswalkRelease`,
`UniverseRelease`, canonical release, rights and method machinery. It does not
create another truth store, graph, rights system, proof engine, replay engine or
assistant.

Its request adopts ConsequencePlan's closed identifiers-only rule: the caller
selects one registered operator and output profile and cannot supply prompts,
literal facts, prose, values, URLs, paths or arbitrary expressions. The exact
ConsequencePlan profile is hash-bound by this extension; trace execution remains
a separate narrow operator because ConsequencePlan 0.1.0 correctly excludes
dependency tracing from its own three profiles.

The only successful 0.1.0 query selects the complete registered historical
joint frame. Every returned path contains the originating observation ID and
record hash, all indispensable roles, exact mapping states, value or typed
missingness state, unit, denominator, period, four distinct time axes, source
locator, rights snapshot and parser/method binding. A path is a historical
source association. It is not a dependency edge, route or causal mechanism.

Record and tuple digests reuse the hash-bound
`igrm-typed-canonical-f64-v1` profile and
`event_ledger._typed_canonical_sha256` primitive already used by Event Ledger
and ConsequencePlan. A tuple array is wrapped in the registered
`trace_nary_tuple_canonical_value` object before hashing; the extension defines
no second JSON encoder. The bound cross-runtime fixture freezes integer/float
normalization, signed zero, exponent, Unicode and UTF-8 key-order behavior;
unsafe integers refuse. Trace self-digests reuse Event Ledger extension's
`typed_record_sha256` convention, which removes `record_sha256` before typed
hashing; raw typed hashing is used only for non-record tuple and execution
identity values.

## Denominator rule

The runtime captures the package once and re-executes Foundry validation over
the same exact byte digest. It emits exactly one trace path for every signed
`DependencyObservation`; no tuple may be
decomposed, omitted or manufactured from a cross-product. Source-label members
are partitioned into matched, unmatched, ambiguous and withheld. Joint cells
are partitioned into positive, zero, blank, missing, suppressed and
not-applicable.

Mass is reported only for observations carrying an allowed numeric measure.
For each semantic slot, the same complete observed mass is partitioned by that
slot's four mapping states. Slot partitions are separate denominators and are
never summed across slots. Missing cells never acquire mass and zero remains an
observed zero.

Manifest, package and optional Event Ledger context bytes are captured once.
Successful validation must return the same exact byte digests and loaded
documents, and replay consumes that validated in-memory context. A path is
never reopened after validation to obtain trace or proof content.

## Projection rule

The sole registered projection is a one-to-one identity index. Each projection
row names exactly one originating trace path and observation record, retains the
full n-ary tuple digest, carries no independent value, and is labelled
`projection_not_source_fact`. The source-path denominator, projection-row
denominator and unique origin set must be identical. Binary decomposition,
cross-product expansion, repeated origins and nonreconstructable rows refuse.

## Claim, Episode and correction boundary

An optional context binding may name exact Claim or Episode records from a
separately validated OGES Event Ledger extension bundle. Version 0.1.0 has no
registered method asserting a relationship between those records and a source
observation. It therefore emits only a typed `no_registered_association`
proof—not a fact, assumption, impact or inference.

The runtime consumes only `CorrectionImpact` records from that validated
extension. It deterministically identifies context-proof outputs whose exact
Claim/Episode references are superseded predecessors in a validated correction
transition (whose blast radius has already been recomputed by Event Ledger).
Those proof outputs become invalidated; all n-ary source paths and unaffected
proof outputs remain byte-identical. The caller cannot supply a blast radius.
Only records active on the requested valid date are eligible, except an exact
superseded predecessor invalidated by a correction effective on that date. A
known future-effective correction is reported as not applied and cannot
invalidate a proof early; a future or otherwise non-effective context ref
refuses.

## Time and rights

Source period, observation time, retrieval/knowledge time, system compilation
time, query valid date, knowledge cutoff and explicit execution as-of remain
distinct and ordered. The runtime reopens the exact rights and signer
registries, computes the intersection of required uses, and checks decision
state, expiry, signer effectiveness, revocation and registered signer role at
the explicit as-of time. Foundry, universe, crosswalk, source, parser, release
or rights drift refuses before any path is returned.
The execution rights decision and registry/signer hashes must equal the snapshot
carried by every source observation; separately valid snapshots cannot be
composed across one execution.

Each output carries an exact execution-contract envelope: request transport and
typed-semantic hashes, trace profile/contract/schema hashes, projection and
canonicalization bindings, reused extension profiles and implementation hash.
Execution and run IDs are derived from typed request semantics plus the bound
package, manifest, profile, method and governed rights snapshot. Caller IDs are
not execution identities.

## Real-source refusal

The committed Ministry contract is `rights_blocked_contract_only`. It binds the
expected 483 unloaded table rows × 13 Major-Port/dock columns but withholds the
real tuple and label frame. `TRACE_NARY_ASSOCIATION --status` returns a
non-value-bearing refusal. There is no real trace artifact, route, page or API.

## Claim boundary

Conformance proves only deterministic structural execution over exact signed
synthetic inputs generated during tests. No independently authenticated
synthetic execution receipt is shipped, so capability maturity remains
`contract_only`. This extension never claims causality, dependency, route,
firm, vessel, capacity, buffer, substitution, disruption, forecast,
probability, advice, live/current state, all-India coverage, L1/L2 maturity,
legal clearance, production readiness or benchmark superiority.
