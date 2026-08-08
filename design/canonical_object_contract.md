# IGRM Max canonical objects — implementation contract v0.1.0

Status: **schemas and offline release validator implemented; no production
canonical-object release exists yet**

Effective: 2026-08-08

## Purpose

The canonical-object layer is the source of truth from which future event pages,
exposure traversals, research exports and evidence-locked assistant answers can be
built. The graph is a projection of these records; it is not a separate store in
which unsupported relationships may appear.

The layer currently defines:

- `EvidenceItem` — a rights-bound, time-bound evidence locator or retained
  artifact, never an assertion that its contents are true;
- `Entity` — a versioned identity with evidence-backed identifiers and optional
  hash-locked geometry;
- `Event` — an observable-action record with typed actors, targets, locations,
  knowledge times, coding state and evidence roles;
- `UniverseRelease` — the complete declared denominator for one entity frame,
  including excluded, unmappable and stale members; and
- `ExposureEdge` — a typed structural connection between two entities, grounded
  in a declared universe and evidence.

`CanonicalRelease` binds the exact bytes of every included object and the exact
schema-registry bytes. No object outside that manifest exists for that release.

## Files

The Draft 2020-12 schemas live in `schemas/`:

- `common.schema.json`
- `evidence-item.schema.json`
- `entity.schema.json`
- `event.schema.json`
- `universe-release.schema.json`
- `universe-frame.schema.json`
- `exposure-edge.schema.json`
- `canonical-release.schema.json`

`governance/canonical_schema_registry.json` pins every schema ID, version, path
and SHA-256. A schema edit without an explicit registry update fails closed.
`governance/canonical_method_registry.json` independently pins executable method
bytes and the object types each method may create. It begins empty. The separate
`governance/release_signers.json` begins empty until the founder establishes a
release-signing key outside the repository.

`src/canonical_objects.py` performs JSON Schema validation and the invariants
which JSON Schema cannot establish by itself. It can be run with:

```bash
python -m src.canonical_objects path/to/release.json
```

Its success response contains IDs and counts only. It does not echo evidence,
event descriptions or exposure values.

## Release gates

A release is refused unless all of the following hold:

1. JSON is duplicate-key-free, finite and valid under an exact registered
   schema with no undeclared fields.
2. Every object carries a canonical record hash, and the release manifest binds
   both that record hash and the exact file bytes.
3. Every referenced object is present in the same release. Paths cannot escape
   the release root or traverse a symlink.
4. Every evidence source has a currently approved, Ed25519-authenticated rights
   decision for the exact public use. The current committed rights registry has
   zero approved sources, so it intentionally cannot publish a canonical release.
   The release freezes exact rights-registry, rights-signer and decision-artifact
   hashes, plus each source's signed authority class and independence group.
   Restricted evidence cannot expose artifact bytes or a public URL, and redacted
   evidence must publish only its registered extract.
5. Evidence, entity, event, universe and edge provenance resolves to the exact
   source set implied by their evidence links.
6. Evidence, event, universe, edge and release times cannot claim knowledge or
   effective data after the applicable retrieval, observation or release boundary.
   Event coding roles and confirmation evidence are coherent. “Official
   confirmation” requires an official document or statement marked as an official
   record from a signed `official_primary` source. Otherwise confirmation needs
   eligible corroboration from at least two distinct signed independence groups;
   mirrors under one provider group count once. A final event cannot be machine-only.
7. Every universe member remains in the denominator as included, excluded,
   unmappable or stale. The member rows must exactly partition a hash-locked,
   enumerated source-frame artifact containing its source version, extraction
   query, evidence ID and extraction time. Published counts equal those rows.
8. Every exposure edge names a declared universe and an included covered entity.
   The covered entity must be one of the edge endpoints.
9. A quantified edge has a numeric magnitude, unit, denominator, period and typed
   uncertainty. A qualitative or unknown edge has no numeric magnitude. Unknown
   magnitude requires an explicit limitation code; qualitative edges require a
   categorical/non-estimated confidence and `magnitude_not_quantified`.
10. Inclusion-rule, geometry, evidence-artifact and schema bytes are rehashed at
    validation time. Nothing is trusted because a manifest says it existed.
11. Every method resolves to an effective, non-superseded registry entry and exact
    executable bytes licensed for that object type. An invented 64-character hash
    is not method provenance.
12. The final manifest is signed over its exact bytes by an effective,
    non-revoked canonical-release signer. Editing the manifest, policy snapshot or
    object list invalidates the detached signature.

## Meaning boundaries

Schema-valid does not mean substantively correct. It means the record is
complete enough to audit and cannot silently change shape, evidence, denominator
or provenance. External coding and graph-edge studies must still estimate event
error, edge precision, known-unknown rates, staleness and missingness.

An `EvidenceItem` records what a source made available; it does not certify the
source statement. `Event.record_status=confirmed` describes the registered event
coding decision, not complete ground truth. `ExposureEdge` describes a registered
connection, not event probability, causation, realized loss, business advice or
government endorsement. Confidence categories are not probabilities unless a
future calibration study licenses that interpretation.

## Corrections and evolution

Records are never silently overwritten. A correction creates a new revision,
links the prior stable object through lifecycle fields and preserves the earlier
release. Schema changes require a new semantic version, new registry hash,
migration notes and adversarial tests. The graph pilot must consume these objects
without weakening their rights, denominator or uncertainty rules.
