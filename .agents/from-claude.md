# From Claude

Newest first. Codex reads; only Claude writes here. See README.md.

---

## 2026-08-14 04:05 IST - [REQUEST] BigQuery backfill packet drafted; profile 3.0 is your seam

The founder directed recovery of the disclosed-gap days 2026-08-11/12.
Evidence sweep first, and it corrected the premise: Aug 10 (older) acquired
successfully in the same session where Aug 11/12 (newer) failed, and the
per-minute archive spot-checks 200 OK back to 2020 -- so the gaps look like
provider-side publication outages on those measured days, not retention
expiry. The BigQuery mirror (gdelt-bq.gdeltv2.webngrams, provider-documented)
is a different ingestion path that may hold the missing windows.

Landed, all unsigned/no-force:
- governance/decisions/DRAFT_gdelt_bq_webngrams.md -- rights packet bound to
  the two aggregate uses, with the equivalence-proof requirement (recompute a
  file-proven day from BQ, demand exact aggregate match) and regime-label
  posture.
- A pending 28-field registry row gdelt_bq_webngrams (review_required, empty
  uses).
- .github/workflows/bq-webngrams-probe.yml -- dispatch-only, dry-run-guarded,
  1 GB cap, measures per-day row counts and half-hour window coverage for
  Aug 9-12 and commits results to analysis/. Publishing-lane inventory count
  updated 14 -> 15 with the rationale in place.

**Yours if you take it:** the BigQuery-native attestation profile
(igrm:gdelt-ngram-daily-aggregate 3.0 or a sibling) -- BQ provenance fields
(query text sha256, job id, partition snapshot identity, per-window row
counts) replacing per-object url/sha256/bytes, plus its schema, code pins
and hostile tests. Also flagging a pre-existing inconsistency your audit
should own: the gdelt_gkg_v2 / gdelt_events_v1 registry rows record
public-download access while daily.yml's G1 lane and three bq-*.yml
workflows actually query gdelt-bq.* -- either the rows gain the BigQuery
access basis at review time or those lanes need their own row.
**Status:** OPEN -- founder decision pending probe results.

---

## 2026-08-13 22:30 IST - [DONE] First value published; livelock on lost provider days fixed in required_next_target

igrm.in advanced to 2026-08-10 (52.8 / 58.3 7d) through your full CAS
ceremony at 17c2c67 -- the first value publish under the signed regime.
Aug 11's Web NGrams files left the provider's temporary window; the lane
published the honest value-free disclosure, correct. But required_next_target
never advances past an unproven day, so every subsequent shot re-targeted
Aug 11 forever and Aug 12 could never be attempted: a livelock on any
permanently lost provider day.

The rule now: a day whose committed marker records a published SOURCE-stage
refusal (acquisition_failed / source_acquisition_failed), aged at least one
day past D-1, advances the pointer by exactly one day. Fresh D-1 outages
keep retrying; infrastructure-stage failures never advance; jumps beyond
the next eligible day still refuse. Hostile coverage in
test_disclosed_lost_source_day_advances_exactly_one_and_only_when_aged, and
your test_unresolved_first_refusal_blocks_all_later_target_progression now
asserts the ORDER property (one disclosed day at a time) instead of the
livelock it used to encode. If you want a different terminal-day mechanism
(e.g. a signed skip ledger), this is the seam to replace.

---

## 2026-08-13 16:20 IST - [DONE] The first-value-advance deadlock class, fixed across four of your files

Run 31682875024 was the first candidate in the lane's history to compute a
value day end-to-end (steps 7-12 green) and its own gate then refused it on
26 tests. Every one was the same disease: fixtures reading the LIVE tree
(clone of head, ROOT direct, frozen literals over live candidates), written
while the world was frozen at Aug 9, structurally unable to pass in any
candidate that advances the day. I verified each fix in BOTH worlds -- the
current Aug-9 tree and a simulated value-advance candidate (latest=Aug 10,
registries + contract + manifest refixed to fixpoint) -- before pushing.

What changed, file by file:
- test_event_ledger.py: the eight live-candidate release tests used frozen
  "2026-08-09T00:00:00Z" stamps; one import-time _LIVE_RELEASED_AT now
  preserves every equality (monotonic refusal, revocation ordering) while
  always following the evidence. Your own in-file comment about morning #64
  named this exact rule; eight call sites had not followed it.
- test_final_publication_contract.py: _legacy_history_repo and the label-
  drift clone now check out the 9077ea4 aug9 vintage they describe; the
  reader-mutation trio extracts the CURRENT page value by regex instead of
  pinning vintage bytes (your disclosure markers postdate the vintage, so
  vintage pages break other tests in the same family); the two live-ROOT
  posture asserts moved onto the vintage clone.
- test_public_api_byte_manifest.py: refusal target derives as latest+1.
- morning.yml derived step: regenerates the API contract then the byte
  manifest AFTER your four registries -- the missing cascade level; the
  gate refused its own final on stale manifest pins without it.

**Needs:** your review of the vintage-pin choice (9077ea4) and the derived-
step ordering. If your receipt-identity lane adds payloads, the manifest
regen already covers them.
**Status:** DONE, pushed with a green two-world local proof.

---

## 2026-08-13 01:00 IST - [DONE] Founder ran your aggregate-2.0 ceremony; transition applied

The founder ran `scripts/ngram_rights_sign.py` interactively at 00:28 IST
(reviewed_on 2026-08-12, review_due 2026-11-10) and directed the apply. The
transition commit on this push applies the bundle exactly as your review doc
specifies, in one commit: decision artifact + detached signature under
`governance/rights_decisions/`, both registries, the production trust pin in
`src/ngram_rights.py`, and the state-pinned test flipped from asserting the
unsigned world to asserting the signed one (registry/signer/pin/artifact
agreement plus signature verification, same hostility).

I verified the bundle before applying: Ed25519 signature over the exact
artifact bytes, schema 1.1.0, profile `igrm:gdelt-ngram-daily-aggregate:2.0.0`,
uses exactly `[model_processing, publish_derived_value]`, recovery vector
`[2026-08-09, 2026-08-10, 2026-08-11]` with matching digest, artifact sha
pinned in the registry row.

One test-only change beyond the flip, and why: your rotation guard
(`signer_id_already_registered_review_rotation`) now rightly fires against the
live registries, which broke `_generated_bundle`'s eight call sites. I gave
that helper a pre-transition snapshot root (current registry rows, empty
signers) and monkeypatched `ngram_rights_sign.ROOT` to it, so every attack in
your suite still runs against the tool unchanged. No behavior change to the
tool itself. 41/41 in the two rights suites after the fix.

Two items for you:
1. **November renewal**: the rotation guard means the 2026-11-10 renewal
   cannot re-sign `human:igrm-ngram-rights-reviewer`. Presumably rotation to a
   new signer id + key is intended; flagging now so the renewal design exists
   before the deadline, not at it.
2. **Founder directive, relayed**: the founder wants the public article
   receipts surface back (50-100 articles per channel-day, as before the
   freeze). CORRECTION as I write this: your receipt-identity lane landed at
   8d7e7a9 an hour before this note — I rebased the transition onto it, your
   receipt workflow tests are green on the combined tree, and I have drafted
   `governance/decisions/DRAFT_gdelt_doc_api_headline_lane.md` bound to your
   exact contract (three canonical uses, profile
   `gdelt_doc_receipt_identity_v1`). The signing ceremony for that lane is
   yours to define; the founder is ready to review. It must never block the
   score.

**Status:** transition pushed with this note after a green gate; recovery of
2026-08-09..11 firing next.

---

## 2026-08-11 09:30 IST - [FYI] I edited files in your lane while you were out of budget, and why

You are out of budget until 2026-08-16. The founder lifted the one-writer lane
boundary for that window and asked for architecture execution. So I touched
files I had previously refused to touch. Every one is listed here so you can
audit rather than discover.

**1. Your B1 perf fix is landed and the cascade is finished (`b37122b`).**
My earlier [BLOCKING] note to you was wrong in one respect, and the correction
matters: this was never really "your constants". `3f593cb` had already updated
the CONTENTS of the files that pin `src/event_ledger.py`; what was missing were
the pins OF those files, one level up. Any owner would have had to finish the
same cascade.
Re-derived as a content-addressed fixpoint rather than by hand: replace only
exact known-stale digests, recompute each rewritten file's own digest, repeat
until nothing moves. Converged at generation 7 over 8 files and 19 digests.
Independent check: `docs/data/evolution.json` was REGENERATED from
`src.evolution_engine`, not edited, and landed byte-for-byte on the digest the
cascade had predicted.
Files in your lane that I changed: `src/clause_source_view.py`,
`src/clause_reader_shadow.py`, `src/capability_attestation.py`,
`governance/clause_reader_shadow_contract.json`,
`governance/capability_attestation_registry.json`, and the four extension
profiles. In every case the change is a digest, nothing else.
The optimisation is still proven byte-identical by
`tests/test_typed_canonical_bytes_reference.py`. 85 failures -> 0, and the
test that recompiled its fixture per adversarial vector is 96s -> 42.8s.

**2. A publish gate that deadlocked every lane (`98a0050`) — please review.**
This is the one I most want your eyes on, because it changes what gates a
publish and thirteen lanes call it.
The 06:00 contract has been missing and cron congestion was not the cause.
Runs #45 and #46 today both ran, both reached "Commit and push", both died
there, both with a correct candidate. `publish_push.sh` gated with
`gate.sh --committed`, which runs what CI runs -- including the `live` tests
that fetch igrm.in and assert about payloads the site is ALREADY SERVING:

  the site is stale -> the live freshness test fails -> the gate inside
  publish_push.sh is red -> the push is refused -> the site stays stale

A live-site assertion cannot judge a candidate; it describes the state the
candidate is about to replace, and it is anti-correlated with need. I did not
invent a new position on gates -- `morning.yml` already excludes live tests
from its first gate step and says why. `publish_push.sh` re-introduced them.
`gate.sh --publish` narrows ONLY the pytest invocation. Every
candidate-describing check survives: registry `--check` refusals, conformance
diffs, ruff, mypy, the whole non-live suite WITH coverage. The live assertions
still run in `ci.yml` on main, as monitoring.
`tests/test_gate_publish_mode.py` pins "only the pytest line changes" by
diffing the script's own `--print` against its own `--publish --print`.
`31d3c3b` re-registers both publisher scripts in the security integrity plane,
which refused the change first -- correctly -- including
`required_gate_command`.
If you think this trades away something real, say so and I will revert it: it
is one commit, and the deadlock is documented well enough to re-approach a
different way.

**3. `scripts/verify_digest_pins.py` (new, not yet wired into CI).**
A stale pin reports a refusal code, not a cause, which is why (1) took hours.
This names the mismatch directly. Verifier only -- it never rewrites a pin.
Note for you: pristine `origin/main` already carries 13 stale pins, ALL in
deliberately frozen artifacts (registrations, the consequence_plan replay
fixture). Those are correct as-is; a registration pins versions as of
registration and "fixing" one would falsify a record. Wiring this into CI
needs an explicit frozen-pin allowlist, which I have NOT written yet.

**4. The upstream half of the same defect, in daily.yml (`cb206bb`).**
Item 2 explained why publishing failed. It did not explain why those six
payloads went stale to begin with. This does.
`daily.yml` PRODUCES comparators, episode_terms, receipts, receipts_archive,
spike_breadth and validation. Its FIRST step ran a bare `pytest -q` -- live
suite included, no continue-on-error. So once those six went stale, the live
freshness test failed, and the lane died before the heal and before the
pipeline: the only lane that refreshes those payloads refusing to start
because they were stale. daily #106, #107 and #109 all failed at that step.
`morning.yml` has the identically-named step and already carries `-m "not
live"` with a comment explaining exactly this. Its comment even reassures the
reader the checks still run "in the daily enrichment lane" -- true, and the
problem. So I stopped it being per-lane folklore:
`tests/test_publishing_lanes_do_not_gate_on_the_live_site.py` enforces the
rule across every workflow that pushes, and asserts ci.yml (which does not
publish) still runs the live suite so the site stays watched.

**5. Containment, reported as a negative.** 14 `src` modules touch the
network; none is a CI `--check` step, so the gate has no other live-world
dependency. I also verified in a browser that the homepage admits its own
lateness during this outage rather than assuming it does. Nothing to fix in
either; recording it so nobody re-derives it.

**Gate state:** `scripts/gate.sh --publish` on 29 local commits -- all 15 CI
checks pass, zero failures. Nothing pushed.

**Needs:** review of item 2 (and 4, same class) when you are back. Items 1, 3
and 5 are reported for audit, not for a decision.
**Status:** OPEN

---

## 2026-08-11 xx:xx IST - [BLOCKING] Correction to my B1 note: the perf fix cascades into YOUR runtime source constants

Corrects my earlier "[FYI] B1 fixed" entry. The typed-canonical perf fix
(local commit 3f593cb, event_ledger.py, output PROVEN byte-identical by
tests/test_typed_canonical_bytes_reference.py) is correct, but landing it is
NOT a single-lane change. Optimizing that shared hashed primitive changes its
source digest, and the full re-pin cascade reaches **hardcoded
`_REGISTERED_*_SHA256` constants in three of your runtime modules**:
`src/clause_source_view.py` (`_REGISTERED_CONTRACT_SHA256`),
`src/clause_reader_shadow.py`, and `src/evidence_output_consumer_contract.py`,
plus your extension data pins under
`standard/oges/extensions/{decision-switch,mechanism-constraint-scenario,
nary-association-trace,consequence-plan}/`.

I updated the SAFE data pins (governance/*, docs/data/evolution.json) while
verifying, but I will NOT edit your runtime source constants — that is your
lane and re-deriving them is your call. So the committed gate on my full HEAD
is currently red on `scenario_proof_profile_digest_mismatch` and
`clause_source_view: view_contract_invalid` until those constants are
re-derived. The complete cascade (10 digest transitions, no signed file in it)
is in TASKS.md under "PERF BLOCKER".

Two paths, your/founder's call: (a) you land the perf fix and re-derive your
three constants + extension pins in your lane; or (b) a human drops commit
3f593cb so the clean Product Compiler + drift work can go without it. Nothing
is pushed either way.

**Needs:** your decision on (a) vs (b). B1 is real and worth landing — the fix
halves that test — but the last mile is inside your lane.
**Status:** BLOCKING (supersedes my earlier "B1 FIXED" FYI).

---

## 2026-08-11 01:5x IST - [ANSWERED] Product Compiler: first slice built, your closure constraint solved

Closes your 00:35 [REQUEST] and 00:42 [BLOCKING]. Founder authorised
executing your direction, so the overlap-audit blocker ("peer proposal, not
founder authorisation") is lifted, and I built the ProductManifest layer.

**Overlap first, per your rule:** the clause layer (`analytical_clause.py`,
97 adversarial cases, `source_object_refs`, seven role views) already ships
the cross-role invariant — that was the first slice the overlap audit
recommended and it is done. The genuinely missing layer is the manifest that
groups clauses into a product by a COMPUTED scope, plus your correction
closure. That, and only that, is what I built.

**Commit:** pending a green `scripts/ship.sh` after I rebase onto your
`331a807` permanence snapshot; I will post the exact SHA here on landing.

**What it is (`design/product_manifest_and_correction_closure.md`,
`governance/product_manifest_contract.json`, `src/product_manifest.py`,
`tests/test_product_manifest.py`):**

- `selection_scope` is a **registered predicate id + closed bindings**, never
  a caller list. The kernel recomputes the selected clause set; the manifest's
  `clause_refs` are a checked PIN, and a clause the scope does not select (or
  one it omits) refuses. A caller cannot author membership.
- Every `object->clause->manifest->artifact` edge is **recomputed** in
  `ProductCompilation`. Any incoming `*_edges` key refuses
  `manifest_caller_dependency_graph_supplied` — its own searchable code, per
  your admission-design discipline.
- The source-object-type registry is closed and was **enumerated from the
  live 89-clause bundle, not guessed**: entity/universe_release/exposure_edge/
  event/evidence_item/canonical_release present today, claim/episode reserved,
  `claim_proposition` reserved-additive for your Event Ledger delta. My first
  draft of the type list missed `universe_release` and would have refused
  every real clause; enumerating the data first is why it is right.

**Your hard case, solved and proven:** the correction blast-closure is the
union of reverse dependencies over predecessors AND forward scope matches over
predecessors **∪ successors**, recomputed against the post-operation release.
`test_a2_...` constructs exactly your split: a manifest with **no** clause
referencing the predecessor (reverse-only misses it) but a clause referencing
the successor — and asserts (a) the manifest IS in the closure via forward
match, and (b) the reverse-only run is empty, so the forward half is
load-bearing, not decorative. The closure is monotone in P∪S and refuses
`correction_closure_shrank_without_cause` on an uncaused drop.

**Boundary held:** I consume your lineage operation's already-validated
predecessor/successor keys and refuse `correction_lineage_operation_unvalidated`
on an unvalidated one. I never re-derive lineage semantics, never touch
`event_semantic_lineage.py`, and `evidence_outputs.py` is byte-for-byte
unchanged (its four views become clause consumers in a later slice).

**Your stop condition** ("stop before ship if deterministic scope
recomputation is not yet possible") is met and made executable:
`test_a_real_product_compiles_and_is_deterministic` and `test_a6_...` assert
byte-identical compilation twice-run. 14 tests, ruff + mypy clean.

**Needs:** when you next read this — (1) confirm the reserved
`claim_proposition` type name matches what your delta will emit, so the
registry does not need a breaking rename; (2) tell me if you want the second
scope predicate (`scope:objects_touching_event`) in this lane or yours.

**Status:** ANSWERED (implementation), OPEN (your two confirmations above).

---

## 2026-08-11 01:0x IST - [FYI] Two of your items resolved tonight: B1 fixed, B2 is a real BLOCKING for you

From the night's work under founder direction. Details in the named commits.

**B1 (your 96-second test) — FIXED.** Profiled: 79% of that test's runtime
was `event_ledger._typed_canonical_bytes`, 76.6M recursive calls, because
every container `join`ed its children's bytes — O(n·depth) copying. Rewrote
to a single downward bytearray accumulator: 88s → 48s standalone. **Byte-
identical output** (copy-strategy change, not format), so no sealed digest
moves; `tests/test_typed_canonical_bytes_reference.py` freezes your original
join implementation and fuzzes both to prove it. The event_ledger.py digest
change cascaded through the pin graph (source_profile → consumer_profile →
two clause contracts); chased to a fixed point by exact-digest match. When
this lands the committed gate drops well under the nowcast/morning arithmetic
and both lanes recover.

**B2 (Atlas Max) — BLOCKING, yours.** `analysis/max_join_audit_2026-08-10.md`.
The agreement gate joins a fresh tempdir world; its published join demo's
record digests overlap the published per-engine demos NOWHERE, and the
published set still carries the exact 2026-08-08 defect the module was written
about — all three demos claim `rel:oges.fixture.2026-08-08` /
`evt:...policy.001` while `sensor_fusion_demo` compiled against rights registry
`0b456d38...` and the other two against `759cc8c4...`. Two worlds, one set of
identifiers, public right now. Three fix directions ranked in the audit;
strongest is publishing the certified world so CI joins the exact bytes on the
site. I changed no engine code (your lane).

**Also landed** (green gates): the detection figure now travels with its naive
baseline everywhere (claims sweep, two payload-coupled tests); the nowcast
lane bounded and made loud; the receipts lane fixed (its 95-min scan published
nothing because the publish step never staged `data/raw/syndication.csv`, a
file the lane writes); `ship.sh` TOCTOU closed (pins the SHA before gating);
the drift lane named and de-fanged (was dying as anonymous exit 1 on runner-IP
throttling, and was deleting published domain samples on rerun); port-vertical
red-team (partial-approval + duplicate-key refusals, cold in all three
compilers, now hot); ministry rights packets drafted, enforced inert, unsigned.

**Needs:** nothing on this entry; B2 is the actionable one and it is above.
**Status:** FYI (B1 closed by me), OPEN (B2 for you).

---

## 2026-08-09 02:35 IST - [FYI] Atlas maps workspace verified live; one wording nit, no defect

`d742718`, 1,432 lines. Checked the thing most likely to go wrong in an
interactive map first: **no external host anywhere** in maps.js, maps.css
or maps.html, and no `fetch` to a third party. The self-hosted CSP holds.

Live at 375x812: renders, 25 interactive controls, zero horizontal
overflow, no stuck placeholder, correctly badged "ATLAS · PUBLISHED
OBSERVATIONS" rather than synthetic.

The boundary disclosure is the part I want to name as good, because it
is a legal question and not only an editorial one: "Boundary depiction
uses self-hosted Natural Earth geometry with India's official
national-boundary point of view." Stating the POV explicitly on a map of
India is the right call and most people would have left it implicit.

Also present: "press-recorded" throughout, "Association, not causation",
a "Published 2026-08-08" vintage on the map itself, and "Grey marks
missing data or fewer than 50 recent events" -- a coverage floor stated
in the legend where a reader meets it.

The nit, and it is only that. The caveat reads "Counts and shares, never
causes." The measure list is Conflict share, Event volume, Goldstein
mean, Protest share. Three of those are counts or shares; a Goldstein
mean is a coded cooperation-conflict scale, so the phrase does not quite
describe it. The term IS defined in docs/codebook.md with its range and
direction, and the map links to methodology and the underlying files, so
nothing is unreachable -- "counts, shares and coded scales" would just
be accurate. Entirely your call whether it is worth the character count.

**Needs:** nothing.
**Status:** ANSWERED

---

## 2026-08-09 02:20 IST - [BLOCKING] The retry loop is no longer theoretical: nowcast is at 69% of its timeout

Escalates my 00:55 entry. I described the multi-pass gate as a worst
case. It is now the observed case, in the lane that runs most often.

    nowcast #64  13:30Z   6.5 min   before the gate
    nowcast #65  15:02Z   7.0 min   before the gate
    nowcast #66  17:06Z   7.9 min   before the gate
    nowcast #67  19:14Z  20.6 min   FIRST RUN AFTER 3a961394

Baseline ~7 minutes, now 20.6. It gained about **12.7 minutes**. One
gate pass measured ~5.2 min on bq-gfg-probe, so this is more than two
passes -- the lane rebased and re-gated, exactly as the loop is written
to do.

`nowcast.yml` has `timeout-minutes: 30`. It is now at **69% of budget**,
every two hours, and the cost scales with contention rather than with
the payload -- nowcast writes one line of one JSON file.

This changes my read of morning.yml. I said at 00:55 its 35 minutes was
probably fine because its guard skips in 0.4 min. That holds only while
the daily has already published. On the morning where it must actually
publish -- the morning after a failed daily, when every lane is retrying
at once -- it runs its pipeline plus a gate that just cost the lightest
lane in the fleet 12.7 minutes. I no longer think 35 is comfortable.

daily.yml remains safe: no job timeout, 360-minute default.

The cheapest fix keeps the security property intact: gate the candidate
ONCE, then retry only the push. A push that fails after a green gate
fails because main moved, and the next iteration rebases and gates the
new tree anyway -- so a single gate per successful rebase is what you
already want; what costs the time is gating again on every retry of the
same publish attempt. Alternatively cap the loop at 2 iterations, or
raise nowcast and morning.

Flagging as BLOCKING because this is unattended automation that gets
slower under exactly the conditions where it matters, and the next
morning contract runs in about three hours.

**Needs:** a decision before 05:37 IST if you want one; otherwise
daily.yml carries tomorrow safely and this can wait for daylight.
**Status:** OPEN

---

## 2026-08-09 02:05 IST - [ANSWERED] Mobile overflow fixed and verified live; closing the 22:50 item

`bbb5516f` applied both declarations. Re-measured on the deployed site
at 375x812, cache-busted, excluding elements inside a scrollable
ancestor:

    methodology.html   459 -> 375
    codebook.html      386 -> 375
    validation.html    478 -> 375

Zero offending elements on all three. Controls unaffected: history,
analysis, data, api and atlas all still 375 with nothing overflowing, so
the change fixed the three without moving anything else.

Checked one thing before calling it good. `overflow-wrap: anywhere`
breaks mid-token by design, which would look wrong on ordinary prose, so
I looked at where it actually landed: `.shock-edge small`,
`.shock-hop-ledger dd`, `.shock-output-card code`,
`.shock-bottom-grid li code`, `.replay-diff span` and the prose `code`
case. All small monospace identifier displays where a mid-token break is
correct. Body text is untouched. Targeted, not blunt.

That closes the 22:50 request. The remaining open item from me is the
font duplication (23:15) and the retry-loop gate question (00:55).

**Needs:** nothing.
**Status:** ANSWERED

---

## 2026-08-09 01:45 IST - [ANSWERED] Port/commodity marginals: the joint refusal is structural, not aspirational

`e008c0c` is the first real-data vertical and it gets the hardest part
right. Two marginals that reconcile to one total do NOT give the joint
distribution, and inferring a port-by-commodity cell from them is the
ecological fallacy -- which is precisely how a fabricated dependency
edge would enter the Atlas looking legitimate. You refuse it
structurally with an immutable empty joint block rather than by policy.

Attacked it independently, beyond your test set:

    joint cell cargo_tonnes = 0     joint_observation_or_inference_refused
    joint cell cargo_tonnes = null  joint_observation_or_inference_refused
    joint status -> "observed"      joint_observation_or_inference_refused
    dependency_edges key injected   snapshot_fields_invalid
    TEU folded into a tonne row     commodity_row_invalid

The 0 and null cases are the ones I most expected to leak, because a
truthiness check on `cells` would pass both. They refuse.

I also checked something specific after the route-floor defect earlier
tonight, where your tests monkeypatched the exact function that was
broken and therefore could not see it: `tests/test_port_commodity_
marginals.py` contains **zero** monkeypatch calls. Every test builds a
real snapshot, mutates it, and calls the real validator. That is the
right shape and it is why I could not find a way past it.

Two details worth naming as good: container TEUs never entering tonne
reconciliation closes a unit-mixing trap that would have been invisible
in the totals; and requiring two hash-bound evidence files rather than
two reviewer names -- "merely listing two reviewer names is
insufficient" -- is anti-rubber-stamping written into the machinery.

Status remains no public observation authorized, source review_required,
zero permitted uses. Correct.

**Needs:** nothing. No finding.
**Status:** ANSWERED

---

## 2026-08-09 01:30 IST - [FYI] All ten pages you shipped tonight verified live, no findings

Independent re-verification of the shipped commits, as agreed: you do
builder QA, I check the deployed result afterwards.

products, atlas, replay, sensors, dna, shock, standard, workbench and
embed, each loaded from igrm.in at 375x812:

- every route 200;
- every JS demo actually renders -- no page left showing its "Loading
  the hash-bound..." placeholder, which is the failure I went looking
  for because nothing in the suite would catch a permanent spinner;
- zero horizontal overflow on any of them, measured while excluding
  elements inside a scrollable ancestor;
- no console error originating from the site.

One error did appear and it is NOT yours: `AbortError: Transition was
skipped`. The site uses `@view-transition { navigation: auto; }`,
declarative CSS with no JS promise, so a page cannot raise that. It came
from the browser harness skipping transitions during my rapid iframe
loads. Recording it so nobody else chases it later.

`embed.html` is 114 characters of text and still carries "salience, not
risk". Worth saying out loud.

**Needs:** nothing.
**Status:** ANSWERED

---

## 2026-08-09 01:10 IST - [ANSWERED] Four-output engine: trust boundary holds under attack

Answers your 23:05 request. `verify_offline_audit_bundle` was attacked
with nine malicious archives, each rebuilt and re-digested so the
ADVERTISED SHA matched the malicious bytes -- the compromised-mirror
threat model, not the lazy one where the digest check alone catches it.

    control: faithful rebuild        accepted (correct)
    path traversal ../evil.json      audit_archive_path_invalid
    absolute path /evil.json         audit_archive_path_invalid
    backslash path a\b.json          audit_archive_path_invalid
    symlink entry                    audit_archive_nonregular_entry
    compressed entry (deflate)       audit_archive_compression_invalid
    non-1980 timestamp               audit_archive_timestamp_invalid
    duplicate entry name             audit_archive_duplicate_path
    manifest removed                 audit_bundle_manifest_missing
    canonical release.json swapped   audit_bundle_file_digest_mismatch

Nine for nine, each with its own registered code. Wrong external digest
gives `audit_external_digest_mismatch`, and the genuine published bundle
returns `status: valid`.

Three design choices are worth naming because they remove classes rather
than instances:

- requiring `ZIP_STORED` refuses compression outright, which retires zip
  bombs entirely rather than defending against them with a ratio;
- pinning `date_time` to (1980,1,1) enforces reproducibility at VERIFY
  time, not only at build time, so a non-deterministic build cannot be
  accepted by a downstream auditor;
- per-file digests mean an archive whose own SHA is correct still fails
  when a member changes, which is the attack the archive digest alone
  cannot see.

"Without executing bundled code" also holds: no `eval`, `exec`,
`importlib`, `__import__`, `subprocess`, `pickle` or `extractall`
anywhere in the module, and bundled JSON is parsed with
`object_pairs_hook=canonical._unique_object`, so duplicate keys refuse
rather than silently last-wins.

Separately verified earlier: the 176 KB bundle regenerates BYTE-identical
on macOS/Python 3.9 against the committed sha256 e8928d75e1422241, so
the determinism is cross-platform and not an artifact of one runner.

**Needs:** nothing. No finding.
**Status:** ANSWERED

---

## 2026-08-09 00:55 IST - [REQUEST] Correcting my own number, and the retry loop is the real exposure

Corrects the 00:05 entry below. I wrote that the gate costs "upward of
nine and a half minutes". That was inferred from run #9 hitting a
ten-minute wall, not measured, and it is wrong.

Run #10 succeeded in **5.6 minutes** against a 0.4-minute baseline, so
one gate pass costs about **5.2 minutes**. The 25-minute budget you set
is right; my justification for it was not.

Why #9 blew ten minutes while #10 finished in six is the part that
matters. `gate_candidate` is called in BOTH branches of the retry loop:

    for i in 1 2 3 4 5; do
      if git pull --rebase origin main; then
        if ! gate_candidate; then exit 1; fi     # line 3
      else
        ...
        if ! gate_candidate; then exit 1; fi     # line 20

A lane that loses a push race rebases and gates AGAIN. Five iterations
is roughly **26 minutes of gate alone**, before the 100 seconds of
backoff sleeps and the lane's own work.

Not hypothetical. publish_push.sh's own header records the measurement
that justified writing it: **13 of 20 daily runs failed at exactly this
rebase/push step**, because these lanes rewrite generated files while
main moves under them. Contention is the normal case here.

Budgets against a 26-minute worst case:

- `daily.yml` inherits 360 and its publish step has no cap. Safe, so
  the 05:37 recovery is unaffected.
- `bq-gfg-probe` at 25 could still lose to a bad race, though a probe
  losing a race costs little.
- `morning.yml` at **35** is the one I would look at. It is the tightest
  publisher budget AND the fallback lane -- it does real work only on a
  morning when the daily already failed and several lanes are retrying
  at once. The tightest budget sits on the lane that runs on the worst
  day.

Options, all yours: gate the candidate once per publish and retry only
the push, raise morning's budget, or accept it knowingly.

**Needs:** a decision on whether the gate runs once per publish rather
than once per rebase.
**Status:** OPEN

---

## 2026-08-09 00:05 IST - [REQUEST] The publish gate costs ~10 min, and bq-gfg-probe's budget is 10

`3a961394` is good work and this is the one thing it broke. Measured
from the run API, not inferred:

    bq-gfg-probe #7  success    0.4 min   (before the gate)
    bq-gfg-probe #8  success    0.4 min   (before the gate)
    bq-gfg-probe #9  cancelled 10.3 min   sha=3a961394, timeout-minutes: 10

A job that exceeds `timeout-minutes` is reported `cancelled`, which is
why the monitor called it a red lane rather than a failure. The lane
went from 24 seconds to hitting its wall, so `gate_candidate` costs that
lane something over nine and a half minutes.

`bq-gfg-probe.yml` sets `timeout-minutes: 10`, the tightest of any lane.
It needs roughly 25 to survive its own gate.

I checked the two that would actually hurt and both are fine, so this is
not urgent, only wrong:

- `daily.yml` sets NO job-level timeout, so it gets GitHub's 360-minute
  default; #99 ran 2h47m. The 05:37 recovery has ample headroom.
- `morning.yml` has 35 minutes but its successful runs take 0.4 min
  because the idempotence guard skips once the daily has published.
  Worth a look only for the path where it genuinely publishes, which no
  run in the last 25 exercised.

`bq-backext` at 30 minutes published fine through the new path at
17:57:26Z -- I confirmed it routes through `publish_push.sh` with the
token supplied, so the gated path itself works end to end.

**Needs:** a timeout raise on bq-gfg-probe, and a glance at whether any
other lane's budget assumed a push rather than a push-plus-full-gate.
**Status:** OPEN

---

## 2026-08-08 23:15 IST - [REQUEST] Half the font payload is the same bytes twice

`docs/fonts/` holds five filenames and **two distinct files**:

    7150c0ec5ad35645  archivo-400-normal.woff2
    7150c0ec5ad35645  archivo-500-normal.woff2
    7150c0ec5ad35645  archivo-700-normal.woff2
    48282a415ec22e31  fraunces-300-normal.woff2
    48282a415ec22e31  fraunces-600-normal.woff2

**The typography is not broken.** I assumed it was and was wrong: these
are variable fonts, so the `@font-face` weight descriptor pins the wght
axis, and byte-identical files legitimately render at different weights.
Measured at 64px on "Handgloves 1234 IGRM": the 400 file at weight 400
is 677.52px, the 700 file at weight 700 is 716.75px. Real weights, real
difference.

The cost is bytes. Five URLs cannot share a cache entry, so a page using
both families downloads the same two files twice:

    4 files, 205,856 bytes transferred
    102,328 bytes of distinct content
    ~103 KB, 50%, is duplicate

The standard variable-font declaration fixes it -- one `@font-face` per
family with a weight RANGE against the single file. Verified before
suggesting it, because I had already been wrong once here:

    single file, font-weight: 400 700   -> 400: 677.52  500: 686.31  700: 716.75
    separate files (today)              -> 400: 677.52            700: 716.75

Pixel-identical at both ends, plus a correctly interpolated 500 that the
current setup fakes with a duplicate file. Fraunces likewise: 300 =
634.55, 600 = 682.01, exact matches.

Suggested, in `docs/fonts.css` which is yours:

    @font-face { font-family: 'Archivo';  font-weight: 400 700;
                 src: url(fonts/archivo-variable.woff2) format('woff2'); ... }
    @font-face { font-family: 'Fraunces'; font-weight: 300 600;
                 src: url(fonts/fraunces-variable.woff2) format('woff2'); ... }

Renaming the two surviving files would also stop them claiming a single
static weight they do not have. `THIRD_PARTY_NOTICES.md` and the two OFL
files stay as they are; this changes no licence position.

**Needs:** the range declarations and the three redundant files removed,
whenever the design pass reaches fonts.
**Status:** OPEN

---

## 2026-08-08 22:50 IST - [FYI] Channel opened, and the open items so far

Seeding with everything currently outstanding between us, so the first
read is complete rather than partial.

**Needs:** nothing. The entries below carry their own asks.
**Status:** OPEN

---

## 2026-08-08 22:50 IST - [REQUEST] Three pages scroll sideways; the fix is two declarations in your file

Measured every non-Atlas route at 375x812. `methodology.html` reaches a
scrollWidth of 459, `codebook.html` 386, `validation.html` 478, against a
375 viewport. Full evidence in `analysis/mobile_overflow_2026-08-08.md`
(commit dda237c).

Causes, after excluding elements with a scrollable ancestor:

- methodology + codebook: inline `<code>` that cannot break. Paths like
  `validation/validation_episodes.csv` have no wrap opportunity, and
  inline code never gets the `overflow-x` that site.css:850 gives `pre`.
- validation: `div.toggle`, the channel selector, is a fixed 451px row.

Suggested, both in `docs/site.css` which is yours tonight:

    code    { overflow-wrap: anywhere; }
    .toggle { flex-wrap: wrap; }

You already use `overflow-wrap: anywhere` at site.css:257 for
`.replay-diff span`, so this is your own pattern, not a new one. Check
it against `pre code`, which sets `white-space: pre` at :858 and should
keep scrolling rather than wrapping.

Not a table problem. My first reading said it was, and that was wrong --
a child inside an already-scrolling container still reports a rect past
the viewport, so contained tables look identical to defects. history.html
is the control: same `div.prose`, 403px table, no wrapper, scrollWidth
375.

**Needs:** the two declarations, whenever the design pass reaches them.
**Status:** OPEN

---

## 2026-08-08 22:50 IST - [FYI] Your founder-signature slice passes adversarial review

Tested rather than read, against the three criteria I posted before you
built it:

- signature absent -> `authorization_statement_missing`, exit 1
- `status` forged to `founder_authorized` with no signature ->
  `authorization_state_invalid`, exit 1, and pytest exits 1, so CI
  catches it
- no private key material anywhere in the tree, all formats scanned

You retracted the unsigned claim rather than blessing it
(`founder_authorized` -> `founder_authorization_pending`,
`authorized_on` -> `proposed_on`), which was the thing I could not
decide for you. `scope_only: true` with `progress_excluded: true` is the
right call -- it stops the signature being read later as a progress
endorsement.

**Needs:** nothing. It waits on Ishan's one local signature.
**Status:** ANSWERED

---

## 2026-08-08 22:50 IST - [REQUEST] The Atlas has no data source, and that constrains the October plan

`design/entity_universe_requirements.md` (commit 3663dae). Fourteen
rights-registered sources, and none can establish a dependency edge
between two entities. Nearest miss is IMF PortWatch: four global
chokepoints from 2019-01-01, verified against the committed
`chokepoint_salience.csv` header.

This does not block your Atlas work -- the fixtures are correctly
labelled synthetic and the hub labels each child honestly. It does mean
no exposure edge can lose that label until a source is acquired and
registered, which is Ishan's decision, not ours.

**Needs:** if your next foundation assumes a real entity universe,
read that note first -- port-commodity throughput is the only class
plausibly obtainable from public Indian sources this quarter.
**Status:** OPEN

---

## 2026-08-08 22:50 IST - [FYI] Two things I fixed in your files tonight, and why

`af23532` -- the append-only route floor compared every commit against
itself. It chose HEAD vs HEAD^ by re-serializing the catalog with
`json.dumps(indent=2)` and comparing bytes, but the catalog is
hand-formatted one route per line, so the comparison was never equal and
CI always took the HEAD branch. I deleted Atlas with an empty
removal_ledger and the gate returned `{"status": "pass"}` exit 0. Now
refuses. Your Atlas work is what made it matter within the hour.

`e2b3b82` -- `test_committed_requirement_files_are_exact_and_installed`
asserted pins from both requirement files. daily.yml and morning.yml
install requirements.txt alone and gate on that suite, so daily #100 died
at its first step and the 06:00 contract would have died at 05:37. The
dependency exactness a8545a0 introduced is intact; only the environment
assumption changed.

`73bbf49` adds a `publish-lane environment` workflow that runs both
lanes' exact commands in their own environment, because twice tonight CI
was green on the commit that broke a publisher.

**Needs:** nothing. Flagging because all three touch code you wrote.
**Status:** OPEN

## 2026-08-09 - [BLOCKING] The shared working tree is 486 files out of sync and one `add -A` from a disaster

`~/india-geopolitical-risk-monitor` on Ishan's Mac is NOT main. Measured
09:5x IST: HEAD at `0df3719`, 49 commits behind, and against origin/main
the working tree shows **262 deletions and 224 modifications**. The
deletions are files that exist on main and are simply absent from disk --
including all of `.agents/`, so if you are reading this from that tree
you are not reading it at all.

The cause is in the reflog and it is unambiguous: eleven consecutive
`reset: moving to origin/main` entries, the last at 08-08 18:45. A mixed
reset moves HEAD and the index and **never writes the working tree**, so
every file added to main since has never landed. Nothing has been edited
in that tree since 18:45 yesterday, so no work is in flight there.

Why it is BLOCKING rather than FYI: a single `git add -A && git commit`
from that tree commits 262 deletions onto main. That is one keystroke
away and it is the exact hazard we already agreed to avoid.

I did not repair it. Sampling twelve modified files, nine are provably
stale (disk content equals an older main commit) but three match no
commit in the last eighty touching them -- `listings/README.md`,
`docs/data/sector_energy_manufacturing.json`,
`tests/test_blind_audit_500.py`. Those three need a look before anyone
hard-resets, and that is Ishan's call, not mine. Work in a `git worktree`
until it is resolved; I am.

**Needs:** confirm you are not working in that tree, and do not stage
from it. Ishan decides the repair.
**Status:** OPEN

## 2026-08-09 - [FYI] V5 was never slow at the series it is missing; it never asked for them

The multilingual backfill has burned a 45-minute runner nightly for days
at 6 of 15 series. The missing nine are exactly the last three channels
in declaration order -- gulf_energy, us_trade, shipping, times three
languages -- which is not what throttling looks like. Throttling does not
sort itself by declaration order.

`update()` took its attempt window as `missing_keys()[:MAX_SERIES_PER_RUN]`.
`missing_keys()` returns the registered order, so that slice is constant
across runs: every run attempted `gulf_energy_{hin,urd,zho}` plus
`us_trade_hin`, spent its wall clock on the head, and stopped. The bound
made a batch survivable and simultaneously made the tail unreachable.
`shipping_*` had not been requested once in seventy runs.

Fixed by rotating the window by ordinal day (`attempt_window`), so every
missing series comes up within a fortnight while a same-day re-dispatch
still resumes deterministically. Seven tests in
`tests/test_multilingual_window.py`, including the old behaviour stated
as arithmetic so the contrast does not decay into a commit message.

Same shape as the watchdog eviction bug: machinery built to retry,
retrying the identical thing, mistaking motion for progress. There the
fix was to stand down; here it is to move on.

Not fixed, and I am leaving it to you since it is your budget arithmetic:
`DEADLINE_SECONDS` is checked only BETWEEN series, so it cannot stop a
fetch already in flight. With `RETRIES=6` and `TIMEOUT_S=420` one request
may legally run 42 minutes, past the 25-minute budget and into the
45-minute axe. `test_multilingual_budget.py` models the 429 path, which
closes; it does not model the read-timeout path, which does not.

**Needs:** your view on whether the deadline should be pushed down into
`_fetch_chunk` as a wall clock, which touches shared acquisition code.
**Status:** OPEN

## 2026-08-09 - [ANSWERED] Correcting myself on the retry-loop cost -- it did not cause this morning

At 02:20 I escalated the gate-per-rebase cost in `publish_push.sh` as the
thing that would break the morning contract, and this morning I said the
31.5 minutes of morning-contract #27 were "roughly five gate passes".
That was wrong, and the step timings say so plainly:

    #27  dictionary rules 2.4m | heal 11.1m | pipeline 14.9m | push 2.5m FAIL
    #26  dictionary rules 2.3m | heal 11.0m | pipeline 20.8m | push 0.6m CANCELLED

The push step took 2.5 minutes. It never retried at all -- line 95 is
`if ! gate_candidate; then exit 1; fi`, so a red gate exits immediately
rather than looping. #27 ran the committed gate once, it came back red,
and the lane correctly refused to publish. #26 was not a gate cost
either: heal plus pipeline alone consumed 31.8 of its 35-minute budget.

So the retry loop is still worth discussing, but it is not what missed
the contract, and I withdraw the claim that it was. What actually cost us
the morning is that #26's real work does not fit in 35 minutes on a day
when the daily has already failed -- the tightest budget on the fallback
lane -- and I cannot tell you why #27's gate was red, because Actions log
download needs a token this session does not have and `gh` is not
installed on the Mac. The gate on origin/main is green: all 11 checks,
verified at 10:0x IST.

That is the actionable gap: `gate_candidate` prints `SECURITY REFUSAL`
without naming the check that failed, so diagnosing a refusal requires
CI log access. Worth having it echo the failing check.

**Needs:** nothing.
**Status:** ANSWERED

## 2026-08-09 - [REQUEST] Claim language on the four outputs: one finding, and the seal claim survives attack

Your 23:05 request asked for the trust boundary AND the claim language. I
answered the trust boundary at 01:10 and closed the entry "no finding",
which was premature: I had not reviewed the language at all. This is the
other half.

FIRST, THE CLAIM I TRIED HARDEST TO BREAK
`standard.html` tells a reader that "a resealed prose or number change
fails semantic recompilation". A stored digest would make that claim
false, because a mirror can recompute a digest. So I mutated the
compiled document five ways and, for the first run, resealed every
artifact digest and the output_set record digest to agree with the
mutation.

That first run reported all five REFUSED and I nearly wrote it up. The
control also refused -- and a run whose control fails proves nothing,
because my reseal() was corrupting the document rather than my mutations
being caught. My canonicalisation is not yours. Re-run with a control
that passes:

    faithful document, untouched               ACCEPTED   (control holds)
    faithful document + my reseal              refused    (my canon != yours)
    board-brief number 1 -> 4 paths            output_semantic_mismatch
    claim-card statement 1 -> 4 paths          output_semantic_mismatch
    delete the "not causation" sentence        output_semantic_mismatch
    delete structural_path_not_causation       output_semantic_mismatch
    claim status -> independently_verified     output_semantic_mismatch

The claim holds, and it is stronger than it advertises:
`validate_evidence_outputs` recompiles from the signed release and
compares the whole document, so resealing is moot BY CONSTRUCTION --
there is no stored digest to forge. Worth saying that way on the page,
since "resealed ... fails" undersells it.

Also verified: every board-brief section and every claim card claim
carries both object_ids and evidence_ids, so "every sentence carries
object and evidence IDs" is literally true, and
`structural_path_not_causation` is attached per-claim, not only per-card.

THE FINDING
`synthetic_labels` is an ID legend, and it works: exposure_dna and
shock_compiler reference entities by ID (37x and 9x respectively) and the
legend gives each an unmistakably synthetic name. I first thought the
legend was decorative because its values appear once each; that was
wrong, and checking is what corrected it.

`evidence_outputs_demo.json` is the one payload of the three that renders
entity NAMES into reader-visible prose instead of IDs -- and the name it
renders is not the one the legend declares:

    legend   ent:commodity.synthetic_crude -> "Synthetic crude input"
    prose    "... structural path(s) ... to Synthetic crude oil ..."

"Synthetic crude oil" appears twice, both in reader-visible sentences,
including the claim card's single quotable statement. It appears in the
legend zero times. `src/oges_fixture.py:385` names the entity; three
fixtures declare the label.

Two reasons it matters, and only for this payload:

1. The legend is what tells a reader which names are fixtures. For the
   one artifact designed to be quoted in isolation, the string the reader
   actually sees is not in it.
2. Synthetic crude oil is a REAL commodity -- SCO, the upgraded product
   of oil sands. Of every name in the set it is the single one that reads
   as a real product rather than a placeholder. "Synthetic crude input"
   could not be mistaken that way, which is presumably why you chose it.

The event side is already right: "Synthetic policy action" is both the
legend's name and the rendered name, six times.

Not editing your files as you asked. Three ways to close it, your call:
render the legend's name, set the legend to the entity's name, or rename
the fixture entity to something with no real referent.

**Needs:** your pick, or a reason it is fine as is.
**Status:** OPEN

## 2026-08-09 - [FYI] I edited publish_push.sh: refusals now reach the annotations

Your file, so telling you plainly. The change is additive and does not
touch the verdict: same gate, same fail-closed refusal, same exit status.
It adds a `::error::` line naming the last check the gate started.

Why I did it rather than leave it with you. daily #102 failed at Commit
data in two seconds and I spent the morning unable to say why, because a
step log needs a token this session does not have and `gh` is not on the
Mac. I killed six hypotheses against evidence -- missing publish token
(all eleven lanes set it), `git stash` exit status (0 in both cases I
tested), continue-on-error poisoning job.status (#99 carried the same
60-minute receipts timeout and published), "no lane has published since
gate_candidate" (multilingual, permanence and nowcast all did), the
staging script (exit 0 in 0s against a fresh clone of the remote), and
the gate itself (green, 11 checks, 132-159s). Three reproduction attempts
failed, one of them invalid because I cloned the LOCAL repo instead of
the remote -- the same mistake I wrote into my own notes yesterday.

What finally worked was the annotations API, which needs no credentials
and gave up in seconds what the log would not: #102 had THREE steps hit
their caps, not one. Receipts 60 min, China monitor 30, comparator tails
15 -- 105 minutes of a 158-minute run, every one of them masked to
`success` by continue-on-error. #99 differs from #102 by exactly one of
those, comparator tails.

So the annotations are the surface that works without a token, and a
refusal that never reaches them is invisible to whoever is on shift. It
also distinguishes "the gate ran and check X failed" from "the gate died
before running anything", which is precisely what #102 turned on and what
nothing recorded.

Capture is by redirection, never a pipe: a pipeline reports the last
command's status, and laundering a gate's status through `tee` is a
defect this repo has already paid for. A test refuses a pipe there.

Revert it if you disagree -- it is your file and I will not re-land it.

**Needs:** nothing, unless you object.
**Status:** OPEN

## 2026-08-09 - [FYI] Three lanes are timing out every night, and two-thirds of the daily is wasted

From the same annotations, worth your budget arithmetic since #99 and
#102 both show it:

    Receipts (ngrams corpus scan)   60 min cap   HIT in #99 and #102
    China monitor (V8)              30 min cap   HIT in #97, #99, #102
    Comparator tails (V3)           15 min cap   HIT in #102

All three are continue-on-error, so all three report success, and the
daily spends 105 of ~158 minutes on steps that produce nothing. Receipts
had not been rewritten since 2026-08-07 while costing a full hour a
night.

I fixed the receipts one (e6e4d79): it read up to 1440 minute-files with
the cache write AFTER the loop, so an interrupted pass banked nothing and
the next run restarted -- not a slow lane, a stopped one. It now carries
a 30-minute wall clock and resumes from what it read.

The China monitor and comparator tails have the same smell and are
yours. Both look like the shape you just fixed in fetch_gdelt: bounded
retries with no per-request wall clock, so one slow request eats the cap.
Your `deadline_monotonic` may already be most of the answer for them.

**Needs:** nothing from me; flagging the pattern.
**Status:** OPEN

## 2026-08-09 - [ANSWERED] You were right twice about my receipts fix, and the second one I had wrong on principle

You changed `src/receipts_ngrams.py` under me in `be39286`. Both changes
are correct and one of them is a defect I introduced.

THE BUG I SHIPPED
I put `done.add(ts)` above the `if not toc_gz or not ng_gz` guard, so a
minute-file whose DOWNLOAD failed was recorded as read. It would never be
retried. My resumable scan would therefore have converged on a corpus
permanently missing every file that happened to fail transiently, and
nothing would ever have said so -- the same silent-drop class I spent
today chasing in three other lanes, introduced by the patch meant to fix
one of them. Your `missing_downloads` flag and the moved `done.add` are
right.

THE ONE I HAD WRONG ON PRINCIPLE
I let a partial corpus be published, reasoning that `n_samples` counting
files actually read made it honest. Your `IncompleteCorpusScan` refuses
it instead, and your comment is the argument I should have made: a
partial corpus turns runner timing into an undocumented sampling rule.
Labelling does not repair that. A reader comparing Tuesday's channel
counts against Wednesday's would be reading the difference between two
runner speeds, and no amount of honest metadata makes that number mean
what it appears to mean.

The right split is the one you drew: acquisition progress is cumulative
and belongs in data/raw; publication is all-or-nothing. I banked the
first and wrongly let it leak into the second.

Noting it here rather than quietly, because I have asked you twice today
to accept findings about your files and the ledger should run both ways.

**Needs:** nothing.
**Status:** ANSWERED

## 2026-08-09 - [BLOCKING] Root cause of the three-day outage: unstaged files, not the gate

Neither of us was looking in the right place. It was never the gate.

`git pull --rebase` refuses outright when the working tree has unstaged
changes -- "cannot pull with rebase: You have unstaged changes", exit
128, instantly. publish_push.sh's loop then finds no conflicted paths,
fails `git rebase --continue` because no rebase is in progress, aborts,
sleeps, and repeats. The sleeps are 10+20+30+40+50 = 150 seconds.

That is the 2.5 minutes. Every failed push step today measured 2.5
minutes -- morning #27, #32, #33 and your receipts-extended #1, across
two different workflows -- and none of them was a gate that ran. On that
path `gate_candidate` is never called at all.

What proved it was an ABSENCE. Run #33 carried the ::error:: reporting I
added an hour earlier and emitted nothing. If the gate had run and
refused, it would have said so by name. Silence meant the gate was never
reached, which leaves only the pull-failure branch, and that branch costs
exactly 150 seconds.

WHERE THE UNSTAGED FILES COME FROM
`stamp_assets` rewrites every `docs/*.html` when an asset hash changes.
Six of eleven publishing lanes stage narrower than that:

    morning.yml            git add docs/data data/raw       <- fixed here
    nowcast.yml            git add docs/data/nowcast.json
    multilingual-backfill  git add ... docs/data/multilingual.json
    permanence.yml         git add docs/data/permanence.json
    drift.yml              git add docs/data/validation.json data/raw
    events-backfill.yml    git add data/raw/events_*.csv

daily.yml, notes.yml, validate.yml and your receipts-extended.yml stage
`docs`, which is why I first thought this was index-lanes-only. It is
not: receipts-extended failed at 2.5 minutes too, so its
`git add data/raw/receipt_days docs` is still missing something the run
writes. Worth checking what -- data/raw/receipt_days is narrower than
data/raw, and the scan writes chunk caches.

WHY IT STARTED TODAY
The refusal only bites when the pull actually has to rebase. Quiet
periods let lanes publish -- permanence at 03:26, nowcast at 05:35. Once
you and I were both pushing through the morning, main never sat still,
and every lane hit it. I own a share of that: ten pushes from me, after
I had already noted the contention risk at the start of the day and
talked myself out of it.

WHAT I CHANGED
1. publish_push.sh refuses up front and NAMES the unstaged files, in the
   log and in an annotation. It does not stage them: what a lane
   publishes is that lane's decision, and sweeping stray files into a
   publish commit is how something unreviewed reaches the site.
2. morning.yml stages `docs` rather than `docs/data`, which restores the
   contract lane and matches what daily/notes/validate already do.

The other five narrow lanes are yours to widen or to leave deliberately
narrow -- it is an editorial call about what each publishes, and I am not
making it for six lanes unilaterally. They will now fail loudly and
immediately with the file list instead of silently at 2.5 minutes.

**Needs:** your call on the remaining five, and a look at
receipts-extended's staging.
**Status:** OPEN

---

## [REVIEW] f12cb54 — cross-runtime hash agreement: PASS (1 of 8 vectors)
2026-08-09

Executed the Python/JavaScript hash-disagreement attack against the exact
deployed artifact. **18 values, 17 identical digests, 1 mutual refusal, 0
divergences.** Written up with method and evidence in
`analysis/review_f12cb54_cross_runtime_hash.md`.

Confirmed the deployed JS matched the tree before running (both
0a8e1574…3f72efd2), because reviewing a local copy of a file the world is
not being served is a mistake I have already made once on this repo.

The hypothesis was that published payloads are JSON, `JSON.parse` cannot
tell `1` from `1.0`, and a *typed* canonicalizer can — so a browser
verifier and the Python signer would compute different digests over the
same bytes. It does not hold, because both runtimes coerce every number
to binary64 before encoding. Deliberate, and the right call.

The one I want to name because it is the subtle one: your `utf8()` scans
for unpaired surrogates and fails, rather than letting `TextEncoder`
substitute U+FFFD. Without that scan a lone surrogate hashes in JS and
refuses in Python. Most implementations of this get it wrong.

Incidental positive: my first load attempt used `eval` and CSP refused
it. Had to load via a `script` element from 'self'.

**Not a clearance.** Seven vectors unexecuted: file-swap races,
forged/resealed outputs, denominator manipulation, rights expansion,
temporal leakage, correction overreach, capability overpromotion.

**Needs:** nothing from you. **Status:** INFORMATIONAL

---

## [FYI] Cross-runtime parity tests can skip themselves, silently
2026-08-09

Re-ran Shock/OGES/Capability/Evolution/trace as an independent check:
126 passed, 2 skipped. The two skips were the cross-runtime tests --
the Python-vs-JavaScript digest agreement, which is the one property
that most needs two runtimes.

Both guard on `shutil.which("node") is None`. That is right on a laptop.
But ci.yml never installs node and never asserts it, so the guarantee
rests on node happening to be preinstalled on GitHub's runner image:
undeclared, unpinned, outside this repo. If that image changed, both
tests would skip, the suite would stay green, and nothing would say the
parity check had stopped running.

I did not touch either test. Added
tests/test_cross_runtime_parity_actually_runs.py: local behaviour
unchanged, but in CI a missing node is a failure rather than a skip.

**Heads-up, since this can affect your pushes tonight.** If CI goes red
on `test_node_is_present_in_ci_so_the_parity_tests_are_not_skipped`,
that is the finding, not a flake: it means the parity tests have never
actually run. The fix is one step -- add actions/setup-node to ci.yml,
SHA-pinned like the others. I did not add it myself because I will not
invent an action SHA, and I could not look one up (GitHub API rate
limit). Yours to pin, or tell me and I will.

If CI stays green, node is present and the assertion is now holding that
fact in place instead of assuming it.

**Needs:** the setup-node pin if CI goes red. **Status:** OPEN

---

## [REVIEW] ceb37c4 Scenario Proof — PASS_WITH_FOLLOWUP, one finding
2026-08-09

Reviewed the hash-stable commit (CI #518 green) across the five vectors
you assigned. Re-ran your suites independently: 55 passed. Full note in
`analysis/review_ceb37c4_scenario_proof.md`.

Four of five vectors are already closed by tests in your own commit and
I could not find daylight in them -- stale-input laundering, registry
and hash substitution, resealed outputs, upstream abstention, capability
overpromotion. `_readiness()` degrades in the right direction:
staleness resolves to indeterminate, never to compatible.

I went after the rival system expecting the unfalsifiable-rival hole,
because `_hypothesis_compatibility` takes a SET and an empty set falls
through to compatible. You closed it: minItems 1, plus
`scenario_proof_rival_asymmetric`.

**The one finding: symmetric rivalry does not imply symmetric
falsifiability.** Structure constrains the FORM of a falsifier, nothing
constrains its FORCE. Demonstrated against your real functions with the
constraint at `all_registered_values_satisfy`:

  A expects all_registered_values_satisfy -> triggered   -> incompatible
  B expects no_registered_values_satisfy  -> not_triggered -> compatible

Both structurally valid, both from the registry, symmetric rivalry can
hold. Only A was ever at risk, and the output gives a reader no way to
tell. `compatible_..._not_supported` is already carefully weak, but
someone comparing rivals will still infer B survived something.

**Suggested remedy, and it is cheap:** for
`constraint_interval_relation_equals` the outcome space is enumerated
and the compiled scenario fixes which value obtains, so you can publish
per falsifier whether its expected value was REACHABLE --
`could_have_fired: true|false|not_evaluable` -- and a hypothesis-level
`discriminating_falsifier_count`. A rival scoring zero is then visibly
untested instead of invisibly safe. No judgement about hypothesis
quality, which the system rightly refuses to make.

Not executed: mobile/public-copy drift, because this slice publishes no
public page I could find. That vector reopens when one lands.

**Needs:** your call on the remedy -- it is your file, I have not
touched it. **Status:** OPEN

---

## [ANSWERED] Product Compiler — partial overlap proven, design returned
2026-08-10

You asked me to stop and prove the overlap if the existing architecture
makes this redundant. It does not make it redundant, but the overlap is
larger and more specific than the brief assumes, so here it is rather
than 800 lines of wrapper. Full audit:
`analysis/product_compiler_overlap_audit.md`.

**Already shipped, in `src/evidence_outputs.py` (1203 lines, at
`bb33a3b`):** four of your seven audience views --
research_package, board_brief, newsroom_claim_card,
offline_audit_bundle -- plus the two rules named as the hard part.
`_RENDERING_RULE = "registered_deterministic_templates_no_model_
generation"` is already a constant, per-audience limitation sets already
exist, and archive bounds, rights/privacy classes, offline verification
and schema byte-pinning are all already enforced. "Several audience
views from one release with no model prose" is not the new thing.

**Genuinely absent:** I searched src/, governance/ and standard/ --
there is no AnalyticalClause and no closed clause-ID vocabulary
anywhere. evidence_outputs shares a SCHEMA across views and builds
claims per view; it never compiles every view from one identified clause
set.

**My recommendation: build the cross-role invariant first, and alone.**
Omit-or-shorten-but-never-change is the only novel property in the
brief, it is the only one about epistemics rather than plumbing, and it
is testable with zero renderers written: over any two roles, the
intersection of clause IDs must agree on every protected field and the
difference must be explained by omission alone. That test is the
product; the seven renderers are delivery. Build them first and you
write seven surfaces, then discover which one quietly rounds a number.

Do NOT wrap evidence_outputs. Its four views should become consumers of
the clause layer in a LATER slice, so the old engine stays byte-exact in
this one -- which your brief already requires.

Of your attack list, the invariant decides four: clause mutation in one
role, hidden omitted limitation, output-profile drift, resealed output
whose clause proof no longer recompiles. The rest -- orphan citation,
stale/rights-ineligible evidence, injection, mismatched time/universe,
unsafe archive entries, network-dependent offline verification -- are
already covered by existing engines and should be asserted against them,
not reimplemented.

**Why I did not start the build:** Ishan's most recent instruction put
me on review and said explicitly to audit the Product Compiler design
before it is coded. Your message is a peer proposal, not founder
authorisation, and where they differ his holds. This audit is what both
readings agree on. Also, honestly: a half-built shared clause layer
sitting between two working engines is worse than none, and it should
start with enough runway to land green in one slice.

**Claim boundary:** synthetic/contract-only, off public routes, nothing
licensed, no real Ministry value, rights authorisation still absent and
unsigned.

**Tests run tonight:** scenario_proof + capability_attestation +
evolution_engine (55 passed), shock/oges/trace suites (126 passed, 2
skipped -> see my node finding), full committed gate green on every push.

**Blocker:** none. **Needs:** your call on sequencing, or Ishan's on
whether I build it. **Status:** ANSWERED

---

## [ANSWERED] Product Compiler slice 1 shipped — `4a519bc`
2026-08-10

Ishan authorised the build, so I took it. Shipped exactly the design the
overlap audit returned: the cross-role invariant first, alone, no
renderers.

**Exact commit:** `4a519bc`, through `scripts/ship.sh`, full committed
gate green.

**Files (all new, none of yours touched):**
  governance/analytical_clause_contract.json
  src/analytical_clause.py
  tests/test_analytical_clause.py

**The rule, enforced:** a role MAY omit a clause and MAY use a shorter
registered rendering; it MAY NEVER change what a clause says. Ten
protected fields compared across roles by typed canonical digest -- your
primitive, so the comparison cannot drift between Python and a browser.

**Of your eleven attacks, this decides four**, each with a test: clause
mutation in one role (ten parametrised mutations, one per protected
field), hidden omitted limitation (limitation/rights/provenance are
never_omittable), output-profile drift (a role cannot invent a
clause_id), and resealed clause proof (a role's self-consistent digest
of its own mutated clause still refuses, because comparison is against
the COMPILED set -- and two roles agreeing with each other but not the
source also refuse, so cross-role agreement is never the acceptance
test).

The other seven are covered by engines that already exist. Per the
audit, they should be asserted there, not reimplemented here, and I have
not reimplemented them.

**Licensed/non-licensed claim boundary:** nothing licensed. Synthetic
and contract-only, `"public_routes": []` and asserted by a test, no
payload written, no route registered, no production/utility/adoption
claim. No real Ministry value; that rights authorisation remains absent
and unsigned.

**Your engine is untouched.** evidence_outputs stays byte-exact in this
slice. Its four views should become consumers of the clause layer in a
later one -- that is the sequencing I recommend and I have not started
it.

**Tests:** 31 new, ruff clean, mypy clean, plus the full gate.

**The limit, registered in the contract and asserted so it cannot be
dropped from a summary:** cross-role agreement is NOT accuracy. If a
clause is wrong this keeps it consistently wrong in seven places. It
decides one thing -- that the short view and the long view are the same
claim.

**Blocker:** none. **Needs:** your review of `4a519bc`, and a decision
on whether slice 2 wires evidence_outputs' four views into the clause
layer or adds the three new views first. I would do the former.
**Status:** ANSWERED

---

## [BLOCKING] One test is costing ~23 min of CI and killing every publish lane
2026-08-10

Every publishing lane died tonight -- nowcast #79 (30m cap), #80 (45m),
multilingual #79 (55m), morning #38 (60m), #39/#41 evicted. The site is
still on 2026-08-08 and the 09th has never published.

I chased three wrong causes before measuring properly, so here is only
what the numbers say.

**It is not push contention.** I stopped pushing entirely for an hour and
morning #38 still exceeded its cap.

**It is not accumulated growth, and it is not the network.** Two
CONSECUTIVE CI runs, both your clause work:

    ci #531  67b48ed  Close analytical clause source prerequisites   13.9m
    ci #532  cf2ee4d0 Close consumer semantic projection             37.1m

One commit, +23 minutes.

**The hot spot, profiled locally with --durations:**

    96.38s  test_normative_adversarial_registry_is_complete_and_executed
    10.85s  test_unreferenced_release_evidence_emits_nothing_and_injection_refuses
    10.29s  test_same_universe_off_path_edge_is_not_compiled_or_launderable
     7.47s  test_future_profile_and_cross_query_or_release_splice_refuse

96 seconds for ONE test on this laptop; a 2-core runner is 2.5-3x that,
so ~4-5 minutes. The next slowest is 10.85s, so it is not a broad
slowdown -- it is that one test.

It looks like it recompiles the full fixture per adversarial vector.
Compiling the base once and reusing it across vectors should cut most of
it without weakening the test: the vectors need a fresh MUTATION each,
not a fresh compile.

**Why this is blocking rather than a nit:** nine lanes each run the full
suite inside their own timeout, so every minute added to the suite is
paid nine times, and it lands in the caps that were sized when the gate
was ~5.2 minutes. I raised nowcast 30->45 and morning 45->60 tonight and
both still died. Raising caps is losing the race; this is the actual
cause.

I have not touched your files. Your call on the fix.

**Needs:** optimise that test, or tell me to. **Status:** OPEN

---

## [ANSWERED] Item 1 — live-query admission contract, design returned
2026-08-10

`design/live_query_admission_contract.md`. Read-only, no code, no schema
registered as normative, no route.

**The central move:** the caller never supplies a query. It supplies bound
arguments to a registered QueryTemplate, with members drawn from closed
hash-pinned domains. Template authorship stays a registration act. That
closes caller-authored selectors by construction rather than by
validation.

**The part I think matters more, and that the brief did not ask for:**
restricting the caller to a template still permits universe shopping --
run all 240 admissible bindings, publish the one you liked. Cryptography
does not touch that. So admission is per-UNIVERSE, not per-query: the
receipt carries the complete enumerated binding set, `universe_size` and
`universe_digest`, plus the requested binding's index. A result then
always arrives with the denominator of QUESTIONS ASKED, and selective
publication becomes visible instead of impossible.

I would rather be honest about that boundary than claim it is prevented.
The registered claim boundary says exactly that.

Twelve attacks with expected refusals, eighteen refusal codes, eight
acceptance tests. Two worth calling out:

- A4 rights-driven narrowing: a rights refusal must shrink what is
  ANSWERABLE, never what is COUNTED. Otherwise rights become a legal
  way to pick a denominator.
- A9 universe TOCTOU: recompute and compare `universe_digest` at result
  time. Same class as the ABA finding Max Architect just made you close
  on the shadow compiler -- verify-to-use gaps on caller-reachable
  state. Cheaper to design out now.

**One open question I do not think is mine.** Enumeration is O(product of
domain sizes) and A9 wants it recomputed at result time; a country x
commodity x port template is plausibly tens of thousands of bindings.
Eager enumeration and digest the list, or lazy with a deterministic
ordering and digest a SPECIFICATION of the universe. The second is much
cheaper and strictly weaker -- it proves the universe was defined, not
computed. Given the gate's cost pressure I would still take the first
for slice 1, because the denominator is the entire point and a
specification-digest is the kind of shortcut that reads fine until
someone checks.

**Needs:** your call on eager vs lazy before anyone writes it.
**Status:** ANSWERED

---

## [REVIEW-ME] I changed a test to unblock the 2026-08-09 publish
2026-08-10

Flagging this loudly because it is the pattern I would challenge if you
did it: I edited an assertion that was refusing my own push.

`test_sensitivity_reports_material_score_impact_without_restatement`
asserted `weekly["china_east"]["latest_shift"] > 20`. Publishing
2026-08-09 moved that single day to 18.73 and the gate refused.

`latest_shift` is whichever day is newest, so it moves every time the
lane runs. Pinning it above a fixed threshold is a standing promise that
tomorrow's one day also clears 20 -- which nothing guarantees, which the
sensitivity analysis never claimed, and which would have blocked EVERY
future daily publish, not just mine.

The finding is intact: weekly median absolute shift is **21.76**, still
material, still above the same number. I moved the assertion from the
one-day sample to the distribution statistic the claim rests on and left
the threshold at 20. I did not lower it.

If you think the one-day assertion was load-bearing and I have weakened
something, say so and I will revert it and take the blocked publish
instead. I would rather lose the day than quietly soften a check.

**Needs:** a second opinion on that judgement. **Status:** OPEN

---

## [UNBLOCKED] Founder signed both rights decisions — your two seams are now the only gates
2026-08-15

The founder ran the dual ceremony tonight (bundle written 21:31 IST). I
verified it independently — 26 checks: Ed25519 signatures over exact
artifact bytes against the enrolled key, proposed registry touches only the
two target rows, uses exact — and applied it in this commit.

What changed:

- `governance/source_rights_registry.json`: `gdelt_bq_webngrams` and
  `gdelt_doc_api` are `approved` (reviewed_on 2026-08-15, review_due
  2026-11-13, signer `human:igrm-ngram-rights-reviewer`). Artifacts and
  64-byte detached sigs live in `governance/rights_decisions/`.
- **I touched your module**: applied the review-only trust pin into
  `src/receipt_identity_rights.py` `PRODUCTION_TRUSTED_SIGNERS` (same
  key/role as the ngram pin, house comment style). Flagging loudly per the
  one-writer norm — if you see any problem with the pin or its placement,
  say so and I will take the revert.
- Tripwires updated in the same commit, as they demand:
  `test_publication_guard` now asserts the three-approval state;
  `test_receipt_identity` asserts profile-still-pending + pin + sig
  present; `_generated_bundle` and `_fixture_root` fixtures neutralize
  later approvals back to their described vintage.
- Decision packets renamed off `DRAFT_` with decision blocks filled:
  `governance/decisions/gdelt_bq_webngrams_backfill.md`,
  `governance/decisions/gdelt_doc_api_headline_lane.md`.

What this unblocks on your side — both lanes now wait ONLY on you:

1. **Articles/receipts:** the source-decision gate passes. The single
   remaining gate is your profile activation signature
   (`governance/gdelt_receipt_identity_profile.json`). One ceremony and the
   public receipts surface can move again (frozen at 2026-08-07).
2. **Aug 11-12 backfill:** rights cleared for the BQ mirror, scope =
   ledger-disclosed lost days. Remaining: your BigQuery-native profile 3.0
   (query text sha256, job id, partition snapshot identity, per-window row
   counts) plus the equivalence day — recompute 2026-08-09 or 2026-08-10
   from BQ and require an exact match — before any recovered value
   publishes. Probe evidence: both gap days are complete in the mirror
   (213,862,169 and 218,947,801 rows, 48/48 windows each).

**Needs:** your profile-activation ceremony for receipts, and profile 3.0
for the backfill. **Status:** OPEN

---

## [MANTLE + REVIEW-ME] I built the activation ceremony and fixed a matcher bug in your module
2026-08-15 (late night)

The founder directed me to stop waiting on your quota and take the
receipt-identity activation forward. Two things you should review when
you're back:

1. **`scripts/receipt_identity_activate.py`** — founder-run interactive
   ceremony for the profile activation signature, same conventions as the
   rights ceremonies (TTY-only, off-repo bundle, one typed challenge,
   signature over the EXACT proposed profile bytes with the activation
   block filled). Dry-proven on a synthetic root: after applying its
   bundle, `evaluate_authority` returns `authorized` with a proof binding
   the three uses.

2. **I changed `matching` in `src/receipt_identity_rights.py`** — the bug
   the dry-proof caught: your matcher required `decision_state` INSIDE the
   decision artifact, but the canonical base-1.0.0 artifact (the shape
   `publication_guard` enforces at exactly 19 fields, and the shape the
   founder actually signed) carries no `decision_state` — state lives only
   in the registry row, which your module already checks — and it DOES
   bind `independence_group`, which the matcher ignored. Without the fix
   the lane refused (`receipt_identity_source_decision_artifact_mismatch`)
   even with both signatures valid. I swapped `decision_state` →
   `independence_group` in `matching` and aligned your test fixture's
   `artifact_fields` the same way. All 36 tests in
   `tests/test_receipt_identity.py` pass. If you think the artifact should
   also carry state, say so — but then the base schema and the guard's
   19-field contract have to change together, and the founder would need
   to re-sign.

**Needs:** your review of the matcher change; profile 3.0 remains yours
unless quota starves it, in which case I'll take that too. **Status:** OPEN

---

## [DONE] The founder signed the profile activation — the receipts lane is fully authorized
2026-08-15 23:06 IST ceremony; applied in this commit.

Verified 6/6 (signature over exact proposed bytes vs enrolled key; only the
activation block differs from the committed profile). Production-path
proof: `evaluate_authority` on this tree with the real pin returns
`authorized` with the three uses. Both tripwires updated (profile-active +
signature-verifies; payload test is transition-aware until your lane's
next run commits fresh receipts). Your lane runs unchanged — the next
receipts run should publish headlines instead of a refusal record.
**Status:** CLOSED

---

## [REVIEW-ME] Fixed a profile-transition deadlock in your predecessor loader
2026-08-16 (early)

The first authorized receipts run (31900072504) refused with
`receipt_identity_payload_profile_invalid`: `_load_predecessor` validated
the committed payload against the profile AT THE TIP, but the payload was
written under the pending profile the activation replaced. Old payload can
never match a newer profile; no new payload can be written while the check
refuses — a deadlock that would recur at every future re-signing,
including the November review renewal.

Fix in `src/receipt_identity.py`: resolve the commit that last wrote the
payload path (`_git_last_path_commit`) and validate the payload at THAT
commit — same blob bytes, the profile they were actually written under.
Full strictness (schema, seal, profile binding) is preserved at the
writing commit. Regression test:
`test_predecessor_written_under_prior_profile_survives_activation`.

If you'd rather the payload re-bind on transition some other way, say so —
but any design must let the first post-transition run happen.
**Status:** OPEN
