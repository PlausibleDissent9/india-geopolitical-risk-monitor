# OGES Event Ledger extension — public draft 0.1.0

Effective: 2026-08-09
Status: synthetic, non-production reference implementation; no adoption,
source-rights, truth, legal-authority or production-trust claim.

## Scope

This extension adds typed `Claim`, `Episode` and `CorrectionImpact` records to
the existing IGRM Global Event and Episode Ledger. It is a sidecar over signed
OGES canonical releases selected by the existing knowledge-replay ledger. It
does not create another event store, ingestion pipeline, release authority or
truth engine. Base `EvidenceItem` and `Event` bytes remain governed by OGES
0.1.0 and are referenced by exact record hash.

The extension's analytical chain is:

```text
EvidenceItem -> Claim -> canonical Event relationship -> Episode
                         |
                         +-> append-only CorrectionImpact -> replay + blast radius
```

The arrows are typed references, not truth promotion. Evidence verification,
claim assertion state, Event record/lifecycle state and Episode detector state
are independent axes.

## Claim boundary

A Claim preserves exactly one of six assertion states: `allegation`,
`coded_inference`, `official_confirmation`, `observed_disruption`, `disputed`
or `superseded`. An EvidenceItem with `official_record` verification does not
automatically change a Claim state. State is explicit and its role links are
validated separately.

Every `official_confirmation` role link must reference an exact eligible
official EvidenceItem from an authenticated base release and signed, approved
source-rights state. Corroborating links must resolve to different signed
source-independence groups; two mirrors or two sources in one group never
become two confirmations. An `official_confirmation` Claim always needs an
eligible official link. Two independent corroborators may satisfy a separate
base Event confirmation rule, but they cannot be relabelled as an official
Claim. Observed disruption requires an explicitly positive verification state,
an eligible physical or official observation, and an approved rights/source
role; disputed, withdrawn and merely unverified evidence are refused.

A Claim can describe no Event state effect, or it can bind an already present
one-to-one Event revision. Promotion is admitted only by the registered
deterministic evidence-role rule or by a named human coder/adjudicator already
bound into the successor Event's signed OGES provenance. A model identity is
never eligible, and the extension never writes an Event.

## Episode boundary

An Episode is not an Event and is never counted as one. A model may propose a
cluster with any declared confidence from zero through one. Model formation is
proposal-only regardless of confidence: it cannot close a detector window,
adjudicate a cluster, alter a Claim, or promote a canonical Event. Every Event
link on an Episode is relationship-only by schema and output contract.

Detector-window states (`detector_window_open` and
`detector_window_closed`) describe threshold mechanics only. They do not mean
allegation, confirmation, disruption, response or recovery.

The schema reserves deterministic-method and named-human formation shapes, but
the synthetic 0.1.0 profile binds neither an Episode method registry nor an
Episode human-authority registry. Both non-model formation kinds therefore
fail closed in 0.1.0; an arbitrary authority ID or plausible 64-character
implementation digest is not registration.

## Correction and history boundary

Extension snapshots correspond one-for-one with complete releases in an
already validated `knowledge_replay` ledger. Each snapshot can resolve only
base objects present in its authenticated release prefix and uses the exact
signed rights snapshot bound to that release; a future object or later rights
change cannot authorize earlier state. Claim and Episode archives are
cumulative. Existing identifiers must retain byte-equivalent typed hashes;
new revisions name exactly one predecessor; a predecessor can have at most one
successor. CorrectionImpact records are cumulative and immutable. Deletion,
merge, split, same-ID rewrite and fork are refused rather than inferred.

Every correction transition binds the exact predecessor and successor record
hashes. Event transitions must match the OGES lifecycle/correction link;
Claim/Episode transitions must match their explicit one-to-one predecessor.
For Claim and Episode transitions, the successor's `valid_from` is exactly the
CorrectionImpact `valid_from`, and the successor must already be known when the
correction is recorded (`successor.known_at <= correction.known_at <= snapshot
available_at`).
The validator recomputes the affected object closure from exact subject,
membership and supersession references. It then derives affected products from
the closed product registry and affected releases from exact snapshot/release
membership. A declared object, product, release or count mismatch refuses the
bundle.

Replay keeps valid time and knowledge time separate. A cutoff before a
correction's receipt selects the old signed snapshot; a later cutoff can select
the corrected snapshot even for the same `valid_on` date. The old bytes remain
addressable and are never rewritten into the corrected state. Within the
selected knowledge snapshot, only a successor applicable on `valid_on`
suppresses its predecessor. A known but future-effective successor therefore
does not erase the predecessor that still governs the query date, while a
retroactive successor does. The same valid-date selection is applied to exact
Event correction transitions, so every returned Claim's subject Event revision
remains present in the replay rather than disappearing with the latest release.

## Count-unit firewall

Every snapshot carries the existing Event Ledger's four distinct units:

1. aggregate source rows;
2. deduplicated source events;
3. canonical geopolitical Events; and
4. detected salience Episodes.

The first two are unavailable in the synthetic fixture. A GDELT aggregate row
is never treated as a unique event. Claim archive counts are metadata and never
substitute for any of the four units.

## Trust boundary

Version 0.1.0 accepts only `synthetic_nonproduction` bundles and always emits
`production_trust: false`. Its deterministic public test keys and signed
fixtures cannot authorize a real source, establish legal rights, amend OGES
0.1.0, add a production signer, or establish that any assertion is true. A
future production profile would require a separately reviewed extension
release/signature policy; this draft does not supply one.

Reference validation and replay:

```bash
python -m src.event_ledger_extension --bundle /path/to/bundle.json
python -m src.event_ledger_extension --bundle /path/to/bundle.json \
  --knowledge-cutoff 2026-08-09T14:30:00Z --valid-on 2026-08-08
```

Validation is offline and emits structural identifiers, states and hashes only.
It does not emit evidence text, source extracts, event labels, confidence prose
or measurements.
