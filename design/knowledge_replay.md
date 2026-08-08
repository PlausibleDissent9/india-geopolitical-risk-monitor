# IGRM knowledge replay — implementation contract v0.1.0

Status: **signed synthetic conformance implementation and public demonstration;
no production world-state ledger or signer authority**

Effective: 2026-08-08

## Product boundary

Knowledge replay is the enforceable foundation of the IGRM Max knowledge time
machine. It answers a narrow structural question: which complete canonical
release had entered the separately signed availability chain by a stated
knowledge cutoff, and which records in that release were effective on a separately
stated valid date?

It does not infer the truth of an event, reconstruct unrecorded public knowledge,
forward-fill a missing universe, calculate exposure, attribute causation, forecast
an outcome or issue advice. The current public example contains deterministic
synthetic objects only.

## Three signed layers

1. A `CanonicalRelease` signs a complete object snapshot and its exact schema,
   method, rights and signer-policy bytes.
2. A separate `KnowledgeAvailabilityReceipt` signer identity signs the release
   bytes and the time they entered a contiguous hash chain. Release generation
   time never acts as its own availability proof. Distinct signer IDs and keys are
   role separation, not proof of institutional independence.
3. A `KnowledgeReplayLedger` signs the ordered complete-release index and closes
   at an explicit timestamp. Queries before its first receipt or after that close
   time refuse rather than assume completeness.

Canonical release, availability and replay-ledger roles must resolve to three
distinct signer identities and three distinct Ed25519 public keys. Duplicate keys
under differently named identities refuse, and one knowledge signer cannot hold
both availability and ledger roles. This is cryptographic role separation,
not proof that three institutions independently control those keys. The committed
production knowledge-signer registry contains zero signers. Deterministic public
test keys exist only inside the fixture builder and must never be installed as a
production trust root.

## Replay algorithm

`src/knowledge_replay.py`:

1. rehashes its own registered implementation and all three output/input schemas;
2. validates the ledger signature and deny-by-default signer registry;
3. verifies every receipt signature, contiguous sequence, previous-receipt hash and
   strictly increasing availability time, and refuses a later receipt that rolls
   back to a non-newer release generation;
4. validates every complete canonical release against the historical governance
   files named and hash-bound in that ledger entry;
5. rejects a changed record under the same object ID, a revision without a parent
   in a prior release, non-contiguous revision numbers, lineage forks, parent and
   successor retained together, and unexplained deletions from complete snapshots;
6. selects the latest receipt at or before `knowledge_cutoff`; and
7. evaluates lifecycle and effective intervals only inside that selected release
   on `valid_on`.

The result carries object IDs, object types, record hashes, lifecycle revision and
state, event epistemic state, evidence verification state, selection reason,
release/receipt identity, policy hashes and added/removed IDs. It excludes labels,
evidence text, URLs, magnitude, unit, confidence and analytical prose.

## Exact interfaces

- `schemas/knowledge-availability-receipt.schema.json`
- `schemas/knowledge-replay-ledger.schema.json`
- `schemas/knowledge-replay.schema.json`
- `governance/knowledge_replay_registry.json`
- `governance/knowledge_replay_signers.json`
- `src/knowledge_replay.py`
- `src/knowledge_replay_fixture.py`
- `docs/data/knowledge_replay_demo.json`
- `docs/replay.html`

Local query:

```bash
python -m src.knowledge_replay LEDGER.json \
  --knowledge-cutoff 2026-08-08T14:30:00Z \
  --valid-on 2026-08-08 --object-type event
```

## Known limitation and production gate

A signed chain is not yet an externally witnessed transparency log. A controlling
signer could create a fork outside the public chain. Before production, IGRM must
establish independently controlled keys, rights-reviewed real releases, secure key
rotation and revocation, a public append-only publication channel, and an external
transparency or timestamp receipt whose verification is part of the gate. Until
then the honest claim is executable bitemporal behavior over a synthetic fixture,
not exact reconstruction of the real world.
