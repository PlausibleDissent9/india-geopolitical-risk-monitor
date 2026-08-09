# OGES Event Ledger semantic-lineage extension — synthetic draft 0.1.0

Effective: 2026-08-10

Status: contract-only synthetic reference implementation. It creates no public
value route, production capability, source-rights authority, Event authority or
truth-selection authority.

## Additive boundary

This profile is a sidecar over an OGES Event Ledger extension bundle that passes
its registered schema, integrity, signature, rights and replay checks. It does
not create a second Claim, Episode or Event store. The base extension remains
solely responsible for EvidenceItem-to-Claim roles, Event
promotion, Episode proposal limits, complete authenticated releases, rights at
release time, count units, append-only one-to-one corrections and bitemporal
replay. Their schemas and implementation are pinned and unchanged.

The delta is exactly three objects:

1. `ClaimProposition` gives one existing Claim and its exact subject Event a
   registered predicate, ordered typed arguments and an affirms, denies or
   questions stance. Registry argument roles are executable: competition
   hashes cover exactly predicate plus context arguments, while position
   hashes cover exactly stance plus answer arguments. There is no proposition
   prose field. Every object fixes
   `truth_selected` to false and `event_state_effect` to `none`.
2. `CompetitionSet` is recomputed from every proposition in one knowledge
   snapshot. It preserves every distinct position. Only the registered
   affirm-versus-deny relation over identical ordered arguments is opposition;
   all other distinct positions are divergence. It never selects a winner.
3. `LineageOperation` overlays one-to-one supersession, many-to-one merge or
   one-to-many split while retaining exact immutable object bytes. Many-to-many
   operations are not representable and refuse.

## Proposition and attribution boundary

The predicate registry defaults to deny. Argument position, name, type and any
registered-term value must match its row exactly. Position and competition
hashes are recomputed with the existing typed canonical profile. An immutable
ClaimProposition competition hash binds predicate, context and its exact Event
record. A computed CompetitionSet has a separate snapshot-specific competition
hash: it replaces the exact Event with the deterministic component of the
validated Event-only lineage graph known in that signed semantic snapshot.
Supersession may normalize versions, and merge may normalize its predecessors
with its successor. Split does not normalize: its predecessor becomes an
explicit `ambiguous_split_ancestor`, while every successor remains a distinct
`distinct_split_branch` unless a later signed supersede or merge maps it.
Computed component status participates in the component digest. Later lineage
knowledge therefore never rewrites old proposition bytes; unrelated Events and
split siblings never compete merely because their arguments match. A
competition key groups registered alternatives; it is not a claim that the
alternatives are mutually exclusive.

Attribution has three closed states. `named_entity` requires an exact Entity
record plus a registered locator. A span is called `verified_source_bytes` only
when the validator reads the exact EvidenceItem artifact, verifies its bound
bytes and hashes the selected byte range. When source bytes are unavailable,
the explicit `hash_bound_locator_unverified_span` class preserves the locator
and self-attested span hash without calling it verified. `publisher_only` requires the
EvidenceItem's exact publisher Entity and the publisher-metadata locator; it
cannot be changed into a speaker attribution. `explicit_unknown` carries no
Entity but still binds exact EvidenceItem bytes, asserted time, content-span
hash and content locator. Every attribution authority and locator comes from
the deny-by-default authority registry. A model or generic agent is ineligible.
Rights are evaluated against the signed registry in the exact selected release,
so later approval cannot authorize earlier extraction.

Semantic availability is not inferred from a proposition's declared
`known_at`. Each snapshot has a chained receipt signed by the profile-pinned
synthetic semantic-availability signer. The receipt binds the exact snapshot,
base bundle, base release, profile and a `semantic_available_at` no earlier than
the profile and signer effective time. Replay selects the latest authenticated
semantic receipt at the knowledge cutoff. The 2026-08-08/09 fixture semantics
therefore become replayable only through their 2026-08-10 semantic receipts;
they are not represented as historically available before this draft existed.

## Lineage boundary

Each operation names exact predecessor and successor record hashes, registered
reason, exact basis EvidenceItems, knowledge and valid times, per-object-type
count delta and a signed closed-registry authorization. The authorization binds
the pinned authority-registry digest, signer, role, effective/revoked window,
canonical payload and statement hashes, and synthetic public-test trust class.
Supersede is 1→1,
merge n→1 and split 1→n. Merge and split require a human lineage adjudicator.
Models and agents may not authorize any operation.

Legacy 1→1 operations must match the predecessor link already present in the
unchanged base object. Merge and split successors must instead be root records,
making this overlay their only lineage edge. A predecessor is consumed once;
successors are produced once; intrinsic children may not be hidden. Cycles,
future successors, double consumption, deletion and rewrite all refuse.

An Event successor must already be present in an authenticated complete release.
Its signed Event provenance must name the same human authorizer as a coder or
adjudicator and reviewer; merge/split requires the adjudicator role specifically.

Replay selects the latest signed semantic receipt at or before the knowledge
cutoff, then validates and replays the exact base release bound by that receipt;
it never independently selects a newer base release. Before the first receipt
it refuses. It then applies an operation only when both its `known_at` and
`valid_from` are in scope. Before that point its successors are hidden and its
predecessors remain. Event, Episode and Claim
active sets and counts are emitted separately. The four inherited source count
units remain separate and are never inferred from the active sets. "Active"
means effective on the requested valid date: Event `starts_at`/`ends_at` and
Claim/Episode `valid_from`/`valid_to` are enforced for both base records and
overlay successors. A merely known record is not counted as valid-date-active.
Applicable operations are applied in deterministic dependency-topological
order; `(known_at, valid_from, operation_id)` breaks ties only among ready,
independent operations. A consumer whose producer is pending or unavailable
refuses rather than materializing both an intermediate and terminal version.

## Product Compiler boundary

This version binds no `AnalyticalClause`, `ProductManifest` or
`ProductCompilation` schema. Product closure is a strict `unavailable` object
with no caller-authored dependency graph and no affected manifest IDs. A future
version may enable correction closure only after it pins and validates the exact
Product Compiler contract, recomputes its complete manifest-set denominator and
derives predecessor reverse dependencies union every registered scope matching
any predecessor or successor. This draft deliberately freezes none of those
still-external schemas.

Reference validation and replay are offline:

```bash
python -m src.event_semantic_lineage --bundle /path/to/bundle.json
python -m src.event_semantic_lineage --bundle /path/to/bundle.json \
  --knowledge-cutoff 2026-08-09T14:30:00Z --valid-on 2026-08-08
```

Conformance establishes only the structural invariants above over synthetic
fixtures. It does not establish that a proposition, Claim, Event or attribution
is true; that alternatives are exhaustive; that an operation is substantively
correct; or that any production capability exists.
Every replay carries exact semantic/base bundle file and record hashes,
semantic/base profile and runtime hashes, selected snapshot/receipt hashes and
the typed query hash. `verify_replay` validates the supplied record, reopens the
captured inputs through the full validators, re-executes the query and requires
byte-equivalent typed output. Re-sealing a mutated active set does not verify.
