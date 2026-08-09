# Cross-engine governed-state join

Registered method: `method:igrm.max_state_join@1.0.0`
Registry: `governance/max_state_join_registry.json`
Schema: `schemas/max-state-join.schema.json`
Implementation: `src/max_state_join.py`
Composed world: `src/max_state_join_fixture.py`
Tests: `tests/test_max_state_join.py`
Public vector: `docs/data/max_state_join_demo.json`

## The defect this closes

`IGRM_MAX_SPEC.md` requires that products are "views over one governed
state, not separate products that can disagree", and lists
`role_invariant_outputs` and `proof_carrying_clauses` among the launch
capabilities. Until 2026-08-09 nothing in the repository compared one
engine's output to another's.

Each Max engine built its own world. `oges_fixture` produces a signed
release; `sensor_fusion_fixture` then rewrites the event and the rights
registry to add seven lanes; `shock_compiler_fixture` and
`evidence_outputs_fixture` each install their contract over a *fresh*
`oges_fixture` root. The four conformance artifacts published on
2026-08-08 therefore disagreed in public:

| artifact | release record | event record | rights registry |
|---|---|---|---|
| `evidence_outputs_demo.json` | `e6cc1e33…` | `26102763…` | `759cc8c4…` |
| `shock_compiler_demo.json` | `e6cc1e33…` | — | `759cc8c4…` |
| `sensor_fusion_demo.json` | `8fd9d220…` | `224bc5ff…` | `0b456d38…` |

All three name release `rel:oges.fixture.2026-08-08` and event
`evt:oges.fixture.policy.001`. Two of them describe a different world
under those identifiers. Every engine gate was green, because every
engine gate was correct about its own inputs. A downstream reader
joining a fusion matrix to a shock compilation on `event_id` would have
performed a silent cross-world join with no error available anywhere.

## What the join does

`join_engine_states` takes a mapping of registered `engine_id` to that
engine's sealed output and certifies — or refuses — that they describe one
governed state. It is deliberately ignorant of engine internals: it
re-derives nothing, and each engine's own gate still owns its schema,
signature, freshness and rights checks.

**Release identity.** Every release-bearing engine must report the
identical release block, governance registry digests included. An engine
that compiled against a different rights registry compiled against a
different world. A field an engine's schema omits — `exposure_traversal`
carries no `generated_at` — is not compared; a field two engines both
report and disagree on is a refusal.

**Object identity.** The join walks each document generically and
extracts `(identifier, digest-kind, digest)` bindings. An identifier
bound to two different digests of one kind anywhere in the joined set is
a refusal. There is no reconciliation step and no "prefer the newer"
rule: two answers to "what is this object" means the system does not have
one governed state.

Ownership matters. A mapping's digest describes the mapping itself, not
every identifier it mentions — a shock scenario carries `scenario_id`,
`record_sha256` and a foreign `event_id`, and binding that digest to the
event would invent a collision. `_IDENTITY_PRECEDENCE` fixes the owner.
`_OBJECT_TYPE_NAMESPACE` puts `{"object_type": "event", "object_id": X}`
and `{"event_id": X}` in one namespace, which is what makes the
2026-08-08 divergence visible at all.

**Rights.** One `source_id` reported with two different decision triples
is a refusal.

**Temporal.** No engine's knowledge cutoff may be later than the release
generation time. At least one engine must supply that time, because it is
the anchor every cutoff is checked against.

**Coverage.** Two engines counting one population differently is a
refusal. The denominator travels as a count, not as a label.

## Evidence class and licensed maturity

The join **computes** these; it never accepts them from an input.

The rule is monotone downward. One unapproved source makes the whole
world unapproved and unpublishable. One synthetic access basis caps the
whole world at `synthetic_nonproduction`. There is no averaging and no
majority. Without the release's own source records the join cannot prove
an approval state, so it caps at synthetic rather than assuming
observation.

`maturity_policy` in the registry is a ceiling, not an award:

| evidence class | licensed maturity |
|---|---|
| `unapproved_rights` | L0 (and refused outright) |
| `synthetic_nonproduction` | L0 |
| `observed` | L1 |

`observed` stops at L1 because agreement across engines proves that
rights-approved observations composed without contradiction. It audits no
crosswalk, so it cannot license the L2 bounded dependency map. Advancing
any class requires the corresponding external study in
`IGRM_MAX_SPEC.md` Part V, not a further engine.

Every source in `governance/source_rights_registry.json` is currently
`decision_state: review_required` with `permitted_uses: []` under a
`default_policy: deny`. No real-source world can reach this join until a
human signs a rights decision, and that is the correct state.

## What this is not

Agreement is not accuracy. Four engines can agree perfectly about a world
that no observation supports, and the published vector is exactly that:
a synthetic world, licensed at L0, carrying no dependency, exposure,
propagation, adoption or utility claim. Composition is evidence that the
contract holds together. It is never evidence that a real dependency
exists.

Absence of a collision is also bounded by the engines actually supplied.
The join cannot see a world no engine reported.
