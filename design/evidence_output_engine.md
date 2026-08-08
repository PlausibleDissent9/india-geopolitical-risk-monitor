# IGRM Evidence Output Engine — implemented synthetic foundation 1.0.0

Effective: 2026-08-08
Status: deterministic synthetic conformance foundation; no real-data output
release or external utility result yet.

## Purpose

One signed canonical evidence release should not acquire different facts when
it is turned into a research package, board brief, newsroom claim card or
institutional audit bundle. The Evidence Output Engine makes those four views
deterministic projections of one release and one bounded event-to-target query.
It does not use a language model to author facts, numbers, dates, citations,
confidence, causal claims, forecasts or recommendations.

The registered engine is `src/evidence_outputs.py`; its exact bytes, output
schema, exposure-graph dependency, output names, privacy classes, rights-use
states and size limits are pinned by
`governance/evidence_output_registry.json`. The strict output contract is
`schemas/evidence-output-set.schema.json`.

## Four products, one fact ledger

1. **Research package.** Exact object IDs and record hashes, evidence metadata,
   declared-universe coverage, bounded traversal result, limitations and a
   release-specific citation.
2. **Board-brief draft.** Three registered sections—event record, stored India
   linkage and decision boundary. Every section carries object and evidence IDs
   and is labelled `draft_requires_human_review`.
3. **Newsroom claim card.** Statements are deliberately about what the signed
   release records and what the registered traversal returned. They do not
   turn a release status into independent truth or a structural path into
   causation.
4. **Offline audit bundle.** A deterministic, uncompressed ZIP containing the
   signed release, object records, schemas, method bytes, rights decisions,
   three rendered JSON products, an exact file manifest and instructions. The
   verifier requires a SHA-256 obtained outside the ZIP, rejects traversal,
   duplicate, compressed, non-regular and non-deterministic entries, checks
   every byte, and revalidates the canonical release without executing bundled
   code.

## Refusal boundary

The public compiler refuses if any required evidence has a non-public privacy
class or a rights-use state outside the registered public set. It refuses a
source artifact that is not licensed for extract/full-record redistribution.
It also inherits every canonical-release and exposure-traversal refusal:
signature, rights, method, universe, time, provenance and schema failures stop
the entire output set.

No-path is a first-class result. The board draft says that a bounded traversal
returned no path and explicitly says this is not evidence that exposure is
absent. Output validation recompiles the query and compares the complete result,
so plausible prose or number changes fail even after an attacker reseals the
outer record hash.

## Public test vector

`docs/data/evidence_outputs_demo.json` and
`docs/downloads/igrm-evidence-outputs-demo.zip` use the OGES synthetic fixture
and public test-only keys. They prove deterministic construction, rights and
privacy refusal, byte-identical four-product rendering, authenticated safe
archive handling and canonical revalidation. They contain no real event,
entity, source, right, exposure, decision or adoption claim.

## What remains for a production claim

- a production-trusted release signer and independently anchored public key;
- rights-cleared canonical releases over a declared real exposure universe;
- human review workflow and correction linkage for board/newsroom outputs;
- accessibility and task-specific presentation layers;
- external users and frozen blinded decision tasks; and
- evidence that the products improve a declared decision task relative to a
  pre-registered baseline.

Until those gates pass, the licensed statement is only that IGRM has an
implemented synthetic four-output conformance foundation.
