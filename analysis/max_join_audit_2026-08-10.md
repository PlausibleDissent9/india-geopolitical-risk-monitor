# Atlas Max audit: the join certifies a world the site does not publish

**Scope.** Codex execution-list item 3, cross-review pass over the Max
agreement gate (`src/max_state_join.py`, `src/max_state_join_fixture.py`,
the CI step "Max engines describe one governed state") and the published
Max artifacts in `docs/data/`.

**Verdict.** The join module itself is sound and its own doctrine is
right. But it is aimed at a private world, and the published artifact set
still contains the exact defect the module's docstring narrates as the
reason it exists. `[BLOCKING]` for Codex's lane; no engine code touched
here, per the cross-review boundary.

---

## 1. What the join actually certifies today

CI runs `python -m src.max_state_join_fixture` and diffs
`docs/data/max_state_join_demo.json`. That fixture builds **one fresh
composed synthetic world in a tempdir**, runs all four engines over it,
joins their outputs, and publishes the join. The join PASSES — over that
world.

The four per-engine demos on the site are built by four *separate*
fixtures, each installing its contract over its own root.

## 2. The measurement

Record digests bound by the published join demo, versus the records the
published per-engine demos actually carry:

| engine | join demo certifies | published demo carries |
|---|---|---|
| evidence_output_set | `0b63a5b7…` | `bb9c26e1…` |
| sensor_fusion | `fe16ce20…` | `18edde03…` |
| shock_compilation | `d9399289…` | `7a347249…` |
| exposure_traversal | `1ee9dbf4…` | **no published demo at all** |

**Zero overlap.** The site publishes a certificate of agreement for a
world whose engine outputs it does not publish, next to engine outputs
whose agreement nothing certifies. (The published `exposure_dna_demo.json`
is a different artifact — before/after snapshots, not a traversal — so the
published set cannot even be *submitted* to the join: it refuses
`join_engine_missing: exposure_traversal`.)

## 3. The published set still contains the original defect

Identifiers across the three published engine records:

| | release_id | event_id | rights_registry_sha256 |
|---|---|---|---|
| evidence_outputs_demo | `rel:oges.fixture.2026-08-08` | `evt:…policy.001` | `759cc8c4…` |
| shock_compiler_demo | `rel:oges.fixture.2026-08-08` | `evt:…policy.001` | `759cc8c4…` |
| **sensor_fusion_demo** | `rel:oges.fixture.2026-08-08` | `evt:…policy.001` | **`0b456d38…`** |

Same release identifier, same event identifier, **two different rights
registries** — the module's own docstring describes this exact shape, on
these exact artifacts, as "the most expensive shape of defect an evidence
system can have", and its 2026-08-08 example is these files. The join was
built, the join works, and the public disagreement it was built about is
still on the site, because the join never reads these files.

A downstream reader who joins `sensor_fusion_demo` to
`shock_compiler_demo` by `event_id` today performs a silent cross-world
join with no error anywhere. That sentence is the module's, and it still
holds.

## 4. Mitigations that are genuinely present

- Every demo labels itself synthetic; the join demo's own labels are
  correct about the world *it* joined.
- The join demo publishes `synthetic_nonproduction` / L0, so no maturity
  claim is inflated.
- The per-engine demos each pass their own conformance CI step; the
  defect is exclusively *between* them.

None of these reaches the composite claim. The panel of artifacts, read
together as the Max section of the site invites, still describes two
worlds wearing one set of identifiers.

## 5. Fix directions — Codex's call, not taken here

In descending order of strength:

1. **Publish the certified world.** The composed world's four engine
   outputs become the published demos; the per-engine fixtures consume
   the composed root instead of building their own. The join demo then
   certifies the exact bytes on the site, and the CI diff makes drift
   impossible. This retires four world-building code paths.
2. **Join the published world.** Keep separate fixtures but point a
   second CI join at the published files (requires publishing an
   exposure-traversal demo). Weaker: two worlds continue to exist and
   both must be maintained agreeing.
3. **Rename honestly.** Give each fixture world its own release/event
   identifiers so a cross-demo join by id is impossible rather than
   silently wrong. Weakest: abandons the composite claim for the
   published set, but at least stops the identifier collision.

Option 1 is the one consistent with the module's own doctrine ("views
over one governed state, not separate products that can disagree" —
IGRM_MAX_SPEC.md). The engines are Codex's lane; this audit changes no
engine code and adds no red test, but the join-the-published-files check
in option 1/2 is the test I would want to inherit.

## 6. Method note

The finding required no code reading beyond entry points: extract the
record digests the join demo binds, extract the digests the published
demos carry, compare. Verification over reasoning, again — the module's
prose says "the composite was never assembled"; the bytes say the
composite was assembled about somewhere else.
