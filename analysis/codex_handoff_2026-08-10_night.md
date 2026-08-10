# Handoff to Codex — night of 2026-08-10

From the overnight Claude session. Everything below is committed or
explicitly marked not-committed. The founder authorized continuous work
through the night; pushes go through `scripts/ship.sh` (now SHA-pinned,
see §3).

## 1. `[BLOCKING]` — yours, in priority order

**B1. The 96-second test is now killing a lane outright.**
`test_normative_adversarial_registry_is_complete_and_executed` (96.38s,
profiled in the earlier report) puts the committed gate at ~37 minutes.
The nowcast lane pays that gate via `publish_push.sh` every two hours to
publish one provisional file: measured per-step, its commit step is
38–39 min of a 45-min cap, and runs #83–#85 all died at the cap after
computing a perfectly good nowcast. The lane is bounded and loud now
(40m step timeout with a diagnostic naming the gate), but it will keep
failing every two hours until the test is optimised. Arithmetic when you
land it: 6.5 compute + ~16 gate + 0.5 = ~23 against 45, recovery with no
further change. `analysis/nowcast_lane_gate_cost_2026-08-10.md`.

**B2. The Max join certifies a world the site does not publish.**
`analysis/max_join_audit_2026-08-10.md`. The join fixture composes a
fresh tempdir world; the record digests its published join demo binds
overlap the published per-engine demos NOWHERE, and the published set
still carries the original 2026-08-08 defect the module was written
about: three demos claiming `rel:oges.fixture.2026-08-08` /
`evt:…policy.001` while `sensor_fusion_demo` compiled against rights
registry `0b456d38…` and the other two against `759cc8c4…`. Two worlds,
one set of identifiers, public today. Three fix directions ranked in the
audit; I touched no engine code per the cross-review boundary. I would
inherit gladly a CI join over the published files.

## 2. Landed tonight (all through green gates)

- **Claims sweep, third pass** (`5422909`, `1f36ed1`): the 24/29
  detection figure now travels with the 26/29 naive baseline everywhere
  (15 bare sites fixed, two papers/README/methodology/both listings);
  GPR levels-r carries changes-r; the AI-GPR tile carries its CI; the
  founder-interview replication boast now names the two refused
  channels. Enforced by two payload-coupled tests, both
  mutation-verified. `analysis/detection_baseline_travel_audit_2026-08-10.md`.
- **Homepage staleness guard** (`10688bb`, `40561a9`): the finalized
  measure now admits lateness; verified against five fixed clocks.
- **Nowcast lane bounded** (`f49de53`): see B1.
- **Receipts lane fixed** (`c8310c0`): the 95-minute scan published
  nothing because the publish step never staged
  `data/raw/syndication.csv`, which the lane's own derivatives step
  writes. One path in a `git add`, plus a test that reads the path FROM
  `src.syndication` and checks every out-of-docs writer. This also
  un-sticks `syndication.json` from `n_days: 2`.
- **ship.sh TOCTOU closed** (`d248352`): pins the SHA before gating,
  pushes the pin; a commit landing mid-gate can no longer ride its
  parent's green light.
- **Port-marginals red-team** (`e015f8c`): 11 of 42 refusal codes fired
  under test before; now 14, and the three new ones are the
  policy-critical set — partial approval (`rights_use_not_approved`,
  via a re-keyed validly-signed one-use grant), backdating
  (`source_knowledge_predates_registration`), duplicate JSON keys.
  One structural finding in your favour: growing
  `required_permitted_uses` past an old signature is impossible — the
  compiler pins the list, so requirements move only with implementation
  digest. Nice.
- **Designs** (`ca6d159`, `951450a`, `8bb18f1`): live-query admission
  (item 1, with your per-universe denominator preserved and eager
  enumeration as first reference profile), offline audit bundle
  (item 2 — open question for you: whole-tree vs transform-closure for
  stratum C), comparator benchmark protocol (item 8 — open question:
  main-only vs all-refs for the precomputed-statistic sweep).
- **CI hostile review** (item 6 slice, `951450a`): PASS. All 19
  workflows SHA-pinned, least-privilege, no credential persistence, no
  dangerous triggers. Four scanner false positives documented.
- **Ministry rights packets** (item 9 slice, `669c79f`): three DRAFT
  decision artifacts + lifecycle README under `governance/decisions/`,
  UNSIGNED, enforced inert by `tests/test_decision_drafts_have_no_force.py`
  (mutation-verified: a permitted_use sneaked into the registry while
  the draft is unsigned fails the suite). Founder signs or nobody does.

## 3. Route audit (item 4) closed clean

Payload refs (24 pages, 64 refs, 0 broken), accessibility (0 unnamed
controls, 0 positive tabindex), mobile overflow (0 at 375px), console
errors (0), route graph + sitemap: every orphan/omission hit explained
by documented design (`noindex` trio in `src/sitemap.py`;
`predictions.html` deliberately excluded from front-surface nav in
`excluded_routes` with `protected: true`).

## 4. The method tally, said plainly

Across today's sweeps: **17 scanner accusations against correct
prose/config/design; 4 real claim defects; 3 real lane/tooling defects.**
Every real defect was found by *verification* (payload diffs, step
timings, digest comparison), never by pattern-match alone; every
pattern-match hit that was acted on without reading would have damaged
something correct. In this repo a scanner hit is a question. The comment
density that defeats grep is the same property that makes the code
auditable; keep it.

## 5. Standing coordination

- I held pushes for your landing window ~5 hours; nothing landed, the
  founder closed the window, and I resumed shipping. If you were blocked
  by my pushes, the SHA-pinned ship.sh at least makes my pushes atomic
  and announced.
- Shared-tree rules held all night: no stash, no `add -A`, worktree
  only, Event Ledger untouched.
- The splice `median_absolute_shift` change (`5b52129`) still carries
  its `REVIEW-ME`; second opinion welcome, revert offered.
