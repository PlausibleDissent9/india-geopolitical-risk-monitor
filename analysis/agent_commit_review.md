# Cross-review: origin/main commits after 25ebb6c — 2026-08-08

Method: strictly read-only. All evidence from `git show`/`git log`/`git ls-tree` plumbing and a
`git archive origin/main` extract in scratch space; recomputation and simulation run only inside
the scratch extract and a scratch sandbox repo. Nothing in the shared checkout was read as
evidence, staged, stashed, or written. Full committed test suite executed against the extract:
**336 passed, 1 skipped** (the known `.git`-absent skip). Defect-class priors taken from
`analysis/registration_audit_2026-08-08.md` and `analysis/prose_number_audit_2026-08-08.md`.

Scope: `25ebb6c..origin/main` = three commits.

| Commit | Subject | Verdict |
|---|---|---|
| 614ee6c | F15: outlet-set drift — pairwise Jaccard | **DEFECT** (one test, see D1) — payload itself verified sound |
| 6c98550 | Contract picks up outlet_drift.json | SOUND (one versioning note, Q2) |
| 88e0791 | The staging script the Commit-data step already calls | SOUND (boundary verified by simulation; two notes) |

Authorship: all three commits are `Ishan Krishna <ishankrishna9@gmail.com>`, no
`Co-Authored-By` trailer in any message body. Verified via `git log --format='%an <%ae>%n%B'`.

---

## D1 — DEFECT (will redden scheduled runs): tests/test_outlet_drift.py:119-121 couples the docs surface to the raw store across the atomic-publication boundary, and is not marked `live`

**What breaks.** `test_payload_equals_compute` asserts
`docs/data/outlet_drift.json == outlet_drift.compute()`, and `compute()` (src/outlet_drift.py:118-121)
globs **all** standard day-caches in `data/raw/receipt_days/`. The moment the committed cache
archive gains a day that the committed payload was not regenerated over, the test is red.
Proven empirically in the extract: copying one extra day-cache in (simulating a banked
evidence commit) turns `test_payload_equals_compute` red while the other six tests stay green.

**When it fires — two arming paths, both routine per this repo's own record:**

1. *Failed daily.* daily.yml's receipts step (line 192) writes the day's cache; blind
   replication (249), freshness (274), vintage tripwire (288), and the dual-computation audit
   (452) are all deliberately fail-loud after it. On any such failure,
   `scripts/stage_daily_outputs.sh` (88e0791) does exactly what it promises: banks
   `data/raw` (new cache included), refuses `docs`. The evidence commit lands with
   cache-ahead-of-payload.
2. *"Successful" daily.* The derived-lanes step (211) is `continue-on-error: true` and
   `python -m src.outlet_drift` is its **last** line (248). Any crash in the nine modules
   before it skips the regeneration, the job still reports success, and the success path
   stages the new cache **beside the stale payload** in the same commit.

**Blast radius.**
- `ci.yml` runs the full pytest suite on every push to main, no path filter — the evidence
  commit reds CI, and every subsequent push (nowcast pushes every 2 hours) reds it again until
  the next fully-successful daily. This degrades the exact alarm 88e0791's guard test was
  built to be.
- Worse: **morning.yml's first contract gate is `python -m pytest -q -m "not live"`**
  (morning.yml:76). All 7 tests in test_outlet_drift.py collect under `-m "not live"` —
  none carries the repo's established `@pytest.mark.live` marker (used in 7 other test files
  for exactly this "current state of published payloads" class; the gate's own comment says
  such tests "must not run HERE"). After either arming path, all three 05:33/05:47/05:59 IST
  shots fail identically at the gate → **06:00 morning-contract miss**, caused by a check on a
  payload that has nothing to do with whether today's number is right.

**Repair (either suffices for the morning contract; both are needed for ci):**
- Mark the five payload-reading tests in tests/test_outlet_drift.py `@pytest.mark.live`
  (minimum: `test_payload_equals_compute`). This spares the morning gate but leaves ci red on
  evidence commits.
- Make the equality test tolerate store-ahead-of-payload without weakening it: compute over
  exactly the payload's own `days` list and assert those cells match the caches (a rewrite of
  any published cell still fails; a new banked cache day does not). The current strict-glob
  equality guarantees nothing extra — it just adds archive growth to the failure set.

Note the irony for the record: commits 1 and 3 are individually defensible and jointly armed —
88e0791 institutionalizes the raw/docs split; 614ee6c ships the only test in the repo whose
truth spans that split (verified: no other committed test equates a docs payload with a
computation over `data/raw`; test_detection_baselines.py:36 reads docs/validation surfaces
only).

## 614ee6c — the payload and code themselves: verified SOUND

- **Independent recompute, own code, no src/ import for the arithmetic**: rebuilt all six
  Jaccard matrices, per-day outlet counts, and adjacent-day summaries directly from the 11
  committed standard day-caches (group membership taken from each cache's own `matched` keys,
  anchors from dictionaries.json, www-stripping reimplemented). **Exact match on every cell**,
  including nulls. Adjacent-day means for the record: overall 0.2548, pakistan_west 0.127,
  china_east 0.0885, gulf_energy 0.2412, us_trade 0.0981, shipping 0.1024 (10 pairs each).
- Coverage block honest: n_units 11 == standard caches; first/last 2026-07-27/2026-08-06;
  `n_extended_caches_excluded` 2 == the two `-extended` files. Extended-census exclusion
  rationale (unequal sampling depth manufactures drift) is methodologically correct.
- Null-vs-zero discipline real: `jaccard()` returns None on any empty set; test asserts
  null **iff** empty, both directions.
- No hand-typed numbers anywhere in payload, prose, or tests; no tautologies (the fixture test
  exercises the real `channel_doc_keys`; the payload tests check the shipped file, with an
  explicit anti-vacuity cardinality guard `n_units >= 2` and overall-nonempty-every-day).
- Commit-message claims recomputed: "network-free" true (pure file reads); "the grain the
  archive supports" true (receipt_days is the only committed store with outlet identity);
  test list in the message matches the shipped tests one-for-one.

**Q1 — QUESTIONABLE (latent, founder eyes):** `day_outlet_sets` applies **current**
`group_specs()` (living dictionaries.json, amended twice in 12 days) to **day-frozen** cache
group keys. Today they align on all 11 days (verified per-day). A future amendment that changes
a channel's sub-query partitioning breaks asymmetrically: a *new* sub-query → KeyError → red
derived lane (loud, arguably fine); a *removed* sub-query → the cache's extra group is silently
ignored → outlet sets quietly stop being the day's estimator sets, no error anywhere. The quiet
direction is the losing one. Precedent: src/spike_breadth.py:57 has the identical exposure, so
this is a house pattern, not an invention of this commit — but neither module guards
cache-keys ⊆ spec-keys, and one `assert` would make both directions loud.

## 6c98550 — contract pickup: SOUND

- `scripts/generate_api_contract.py` re-run in the extract: **generated == committed**, byte
  and value identical (80 endpoints, v2.2.0). The entry's description is the payload's own
  `_meta.what` verbatim (derived, not hand-typed); `frozen_fields` equals the payload's real
  top-level keys. tests/test_api_contract.py (including the generated==committed assertion)
  passes.
- **Q2 — minor, founder eyes:** the endpoint was added with **no CONTRACT_VERSION bump** and
  the 2.2.0 comment still reads "country_china.json endpoint added", which now under-describes
  the surface. Practice is already inconsistent (v1.x bumped minor per endpoint; v2-era
  pickups 5a1ddde/830ad33/9dd4891 did not), and the contract's written promise only mandates
  bumps for removals — but a version string that cannot date an endpoint's entry is drift of
  the register-vs-reality kind this repo audits for. One-line decision: either bump on
  pickup or amend the promise to say additive endpoints don't bump.

## 88e0791 — staging script + guard test: SOUND

- **Boundary recomputed by simulation** in a scratch git repo (not by reading the script):
  - failed job, tracked+untracked changes everywhere → staged set is exactly
    `data/raw/*` (modified and new), docs/notes-inbox/.trigger reverted to HEAD and stashed,
    exit 0;
  - failed job with nothing to stash → `git stash push` no-ops cleanly, exit 0 (the
    `set -e` trap I went looking for is not there);
  - failed job, untracked-only under docs → stashed, boundary holds;
  - no changes at all → exit 0; success path → everything staged.
  The "prove, don't trust" cached-diff check is real and fails closed (a non-raw staged path
  aborts before publish — the correct direction).
- Interplay verified: the Commit-data step configures git identity **before** the script runs
  (stash needs it); `${{ job.status }}` is always a valid argument under `if: always()`;
  daily-run writers are confined to docs/, data/raw/, notes-inbox/, .trigger (validation/ is
  read-only in the daily lane; forecasts writes its frozen file only if absent), so no dirty
  path survives to break publish_push's rebase.
- Commit-message story verified against git objects: at 25ebb6c, daily.yml:479 already calls
  the script and `git ls-tree 25ebb6c scripts/` shows it **absent** — the next scheduled daily
  would have died at Commit data. The wiring commit is ac26c50 as claimed (its subject is the
  detection_baselines work; its diff also touches the Commit-data step — the classic
  committed-half-of-a-pair). No scheduled daily ran in the exposure window (evening cron
  20:53 IST predates ac26c50 22:40; fix landed 01:07, next cron 05:37).
- Guard test: regex covers every committed invocation form (all are `bash scripts/…` or
  `python scripts/…`; 4 distinct scripts found, floor of 3 makes regex blindness loud). Two
  scoped limitations, both honest: (a) it checks `Path.is_file()`, so it only catches the
  uncommitted-script class **in CI's clean checkout** — in a dev working tree the stray file
  passes; the commit message scopes the claim to "a red CI", which is exactly true, but a
  `git ls-files` check would catch it at the desk too; (b) a *comment* containing
  `bash scripts/<nonexistent>` would false-positive — none exists today.
- Note, not a defect: the failure-path stash is called "recoverable in a persistent runner";
  GitHub-hosted runners are ephemeral, so in production the stash is always lost. Harmless —
  the refused derived docs are recomputable from the banked raw store — but the comment
  promises recovery that will never happen where this runs.

---

## Bottom line

- 614ee6c: payload, arithmetic, and disclosure verified sound by independent recompute;
  **one DEFECT in its test file** (D1) that, combined with 88e0791's (correct) staging
  boundary and morning.yml's pytest gate, converts the first post-receipts daily failure —
  or any crash inside the continue-on-error derived-lanes step — into red CI on every push
  and a plausible 06:00 morning-contract miss. Fix is small (mark `live` and/or scope the
  equality to the payload's own day list) and should land **before the next daily cron**.
- 6c98550: sound; decide the endpoint-versioning rule once (Q2).
- 88e0791: sound; the boundary does what it says under simulation, including the empty-change
  edge cases.
- Authorship clean on all three.
