# Canonical exposure graph projection — foundation v0.1.0

Status: **implemented as an offline projection and traversal contract; no
production canonical release or public graph pilot is published**

Effective: 2026-08-08

## Frozen scope

This is the smallest enforceable foundation of IGRM Max implementation slice 6.
It turns one fully validated `CanonicalRelease` into a bounded exposure traversal.
It does not create a second graph truth store and does not approve a source,
create a signing key, publish graph data, render a page or license an analytical
claim.

`src/exposure_graph.py` receives the records from the same successful canonical
validation pass that checked schema bytes, object hashes, source rights,
denominators, methods and the detached release signature. It never rereads object
paths after that pass. A traversal therefore cannot replace a checked object
between validation and projection.

The transformation and output contract are deny-by-default and byte-locked in
`governance/exposure_projection_registry.json`. The output is validated against
`schemas/exposure-traversal.schema.json` and carries its own canonical record
hash, the projection implementation hash, the schema hashes, the projection
registry hash and the signed release identity and policy hashes.

## Traversal rule

For one event ID and one target entity ID, the projector:

1. validates the complete signed canonical release;
2. requires the event to be the active revision and not start after the release
   effective date;
3. constructs event entry points only from the event's registered actors,
   targets, affected entities and locations;
4. projects only active entities and active exposure edges effective on the
   release effective date;
5. requires every projected edge's endpoints and declared universe release to
   be effective for that snapshot;
6. follows only the stored `source_entity_id -> target_entity_id` orientation;
7. enumerates deterministic breadth-first simple paths containing at least one
   stored exposure edge within the declared hop, path and computation bounds;
   event-root identity is never counted as exposure; and
8. returns explicit `no_path` or `paths_found`, with a visible `truncated` flag.

The event is an entry point into the release-date graph. This is not a claim that
the event caused an exposure, that the edge was contemporaneous with the event,
or that an exposure became a realized loss.

## Output boundary

The traversal includes:

- stable event, entity, edge, universe, evidence and source IDs;
- record and content hashes;
- event publication/coding status and lifecycle state;
- edge type, stored direction, effective dates and quantification status;
- complete included/excluded/unmappable/stale universe counts for every returned
  edge coverage basis;
- exact evidence IDs per returned object; and
- the signed rights-decision snapshot rows for sources used by that evidence.

It intentionally excludes canonical labels and names, evidence titles, URLs and
artifact bytes, exposure magnitudes, units and confidence values. A later public
renderer must separately prove that each rendered field is licensed and
claim-eligible. This foundation cannot be cited as measured graph accuracy,
coverage quality, calibrated confidence, decision utility, government adoption
or superiority over another product.

## Failure behaviour

The operation refuses before returning a partial traversal when the canonical
release fails any existing gate, the projection method or schema bytes differ
from their registry, an active edge points through a non-effective endpoint or
universe, the requested target is not active and effective on the release date,
or the computation budget is exceeded. Reverse traversal is not
inferred from an edge's semantic direction label. Non-effective event entry
entities remain visible in the event context but do not become search roots.

The current committed source-rights registry and canonical release-signer
registry contain no approved production authority. Consequently there is no
production input that can pass the release validator today. Synthetic signed
fixtures exercise the implementation without representing measured IGRM output.

## Offline interface

When a future signed release exists inside the repository root:

```bash
python -m src.exposure_graph path/to/release.json EVENT_ID TARGET_ENTITY_ID
```

Optional `--max-hops` and `--max-paths` values may only narrow or expand the
registered bounds. Successful JSON is a structural trace, not a public claim
bundle or canonical release. Refusals emit stable stage and reason codes without
echoing evidence or measurement content.
