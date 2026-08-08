> **Redaction note (added when this report was committed):** five email
> addresses in the original review text were replaced with descriptions.
> The repository's leak scanner refused the commit, correctly -- a review
> that criticises defeating that scanner must not add copies of the
> founder's address to the repository to make its own point. The
> addresses are recoverable from the files the report cites.

# IGRM registration review — origin/main 8d2d273..e7f6841 (2026-08-08)

**Two DEFECTS will redden scheduled runs. `validation/precision_v3/registration.json`
pins seven paths at WORKING-TREE locations; three of them are living files
(`dictionaries.json`, `src/fetch_ngrams.py`, `auditor/RUBRIC.md`). The next
legitimate edit to any of the seven fails
`tests/test_precision_audit_v3.py::test_repository_registration_is_pre_label_and_preserves_a_holdout`,
which runs inside `morning.yml:119` — the FIRST gate on the 06:00 IST publish
contract — and inside `ci.yml` and `daily.yml`. Shortest fuse: `src/fetch_ngrams.py`,
7 commits in the 15 days to 2026-08-08 (5 of them in the last 3 days), mean interval
2.1 days. Second: `dictionaries.json`, amended 07-24 → 07-31 → 08-05, next due ~08-12.
Independently, the same regime change makes `python -m src.precision_frame_v3
--record-latest` (daily.yml:162) raise from `_record_payload` — outside
`record_day_outcome`'s `try` — so the day cannot be recorded at all and every later
day fails the contiguity check: permanent red for the rest of the 90-day window, with
no FRAME_FAILURE record, which is the opposite of what daily.yml:152-160 now claims.**

Scope: `efdc969`, `ebd1315`, plus the two newer non-bot commits `7baf222`, `e7f6841`.
`git fetch` first; origin/main == local main == `e7f6841`. All four authored and
committed `Ishan Krishna <the committed author address>`, zero Co-Authored-By, linear, no
bot commits in range.

Method: read-only. `git fetch` + plumbing (`log`, `cat-file`, `ls-tree`, `show`,
`diff`) against the shared repo, whose worktree carries another agent's uncommitted
work — nothing written, staged, or checked out there. All execution in `git archive`
extracts and a fresh `git clone --no-hardlinks` under the session scratchpad, with
independently written arithmetic. Suite runs used the repo venv interpreter with
`PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`, cwd inside the clone.

Standards read in full before review: `analysis/registration_audit_2026-08-08.md`,
`analysis/day_commit_review_2026-08-08.md`, `analysis/slice_reviews_2026-08-08.md`,
`analysis/slice_reviews_2026-08-08_batch2.md`.

Suite, non-live, clean clone: `567606d` 433/0 (matches the prior review exactly —
harness calibrated), **`efdc969` 595 passed / 1 FAILED**, `ebd1315` 596/0,
`e7f6841` 596/0. 12 live-marked deselected each time.

---

## efdc969 — Preregister the production-linked external precision audit — DEFECT ×3, QUESTIONABLE ×3

### What verifies

**All 7 registered digests recompute exactly**, at `efdc969`, at `ebd1315`, and at
`e7f6841` (`git cat-file -p <commit>:<path> | shasum -a 256`):

| Registered path | sha256 (registration.json) | Resolves now |
|---|---|---|
| `validation/precision_v3/PROTOCOL.md` | `45fe409c…351a` | exact |
| `validation/precision_v3/CODING_MANUAL.md` | `ebd99d02…2a1e` | exact |
| `auditor/RUBRIC.md` | `2f285c9c…8d17` | exact |
| `dictionaries.json` | `4f5d3333…9b40` | exact |
| `src/fetch_ngrams.py` | `0cbf9e98…9e39` | exact |
| `src/precision_frame_v3.py` | `24489988…0250` | exact |
| `src/precision_audit_v3.py` | `973563a9…7634` | exact |
| pilot source `data/raw/receipt_days/2026-08-07-extended.json` | `8fbe366a…afbf` | exact |

Pilot source is genuinely immutable: one commit ever (`eaad1e5`), and every
`data/raw/receipt_days/*.json` in history has exactly one commit.

**Sequence — clean.** `registered_at` 2026-08-08T10:33:23Z; commit authored
16:20:27 +0530 = 10:50:27Z, 17 min later. Window opens on the 2026-08-08 UTC score
day, which had not completed: `data/raw/ngram_days/` holds 39 caches, newest
2026-08-07. `data/raw/precision_v3_days/` does not exist at any commit in range. No
v3 sample, sheet, key, packet, freeze receipt, or label file exists anywhere in the
tree. The four v2 sheets that do exist (`validation/blind_audit_500/`) recount to
**1,520 rows, 0 filled label cells** — `v1_or_v2_labels_reused: false` holds, and
CODING_MANUAL.md:6-7 forbids their reuse. Cohort arithmetic recomputed:
2026-08-08..2026-09-18 = 42 days, 2026-09-19..2026-11-05 = 48, total 90; windows
contiguous, disjoint, `labels_may_begin_after` strictly after each `window_end`
(enforced, src/precision_audit_v3.py:221-222). Seeds distinct, 64-hex, frozen before
any source day existed — seed search is impossible by construction, not by promise.

**Founder authority / model path — clean.** `src/precision_audit_v3.py` and
`src/precision_frame_v3.py` import stdlib only: zero `anthropic`, zero `openai`, zero
`requests`/`urllib.request`/`httpx`/`socket`, zero `api_key`, zero `messages.create`.
Labels enter only as external coder CSVs (`_coder_labels`); `score_package` computes
gates and never assigns or adjudicates a label; adjudication is registered as
secondary and has no code path to a primary. `precision_audit_v3` has **no scheduled
caller** (grep across `src/`, `scripts/`, `.github/`): CLI only.

**Estimator math — recomputed independently, 0 mismatches.** I rewrote the
hypergeometric in log space and inverted it by exhaustive linear scan over every
candidate population success count (the module uses binary inversion):
10/10 finite-population intervals agree exactly, e.g. N=2000 n=500 x=430 →
`[0.831, 0.8855]`; N=3000 n=500 x=445 → `[0.862, 0.9137]`; degenerate census
N=n=500 x=470 → `[0.94, 0.94]`. Wilson 4/4 and Gwet AC1 agree with independently
written closed forms. Gate behaviour worth stating in the protocol: the
ABSTAIN-as-OFF finite-population bound, not the "≥400 firm labels" rule, is what
binds — at n=500 the gate needs **ON ≥ 418 of 500** for a 20k frame (≥417 at 5k,
≥416 at 2k, ≥413 at 1k, ≥400 at census). 100 abstentions with a perfect firm record
FAILS (fp_lcb 0.7627). The registered ≥400-firm-label criterion is slack by ~18 rows.

**Claims discipline — held.** README, docs/data.html, docs/validation.html and
nef/REVIEWERS_GUIDE.md all still say "no v3 sample, label or result exists" /
"not a precision result", and `tests/test_precision_frame_v3.py:337-340` pins that
phrasing on all four surfaces. No precision claim is licensed anywhere in the diff.

---

### DEFECT 1 — every registered pin is a working-tree pin; three of the seven paths are living. `src/precision_audit_v3.py:181-187`, `validation/precision_v3/registration.json:40-76`, `tests/test_precision_audit_v3.py:267`

`_registration()` resolves each `registered_files[].path` against the live root and
compares `sha256(file_path.read_bytes())` to the registered digest, raising
`registered file changed: <path>`. The registration carries **no `base_commit` and no
`base_commit_rule`** — there is no immutable anchor to verify against, by construction.
`tests/test_precision_audit_v3.py:266-275` calls `audit._registration(ROOT)` on the
live tree, so the runtime refusal is also a CI assertion.

Simulated the next legitimate change to each of the seven paths in a throwaway copy —
**all seven refuse**:

```
dictionaries.json amended (one new registered term) -> REFUSED: registered file changed
src/fetch_ngrams.py            + one line          -> REFUSED
auditor/RUBRIC.md              + one line          -> REFUSED
validation/precision_v3/PROTOCOL.md                -> REFUSED
validation/precision_v3/CODING_MANUAL.md           -> REFUSED
src/precision_frame_v3.py                          -> REFUSED
src/precision_audit_v3.py                          -> REFUSED
```

Then executed it as CI would: amended `dictionaries.json` in the clone with one new
phrase term and ran the file —
`FAILED tests/test_precision_audit_v3.py::test_repository_registration_is_pre_label_and_preserves_a_holdout`.

Blast radius, in order of when it bites:

1. `morning.yml:119` `python -m pytest -q -m "not live"` — the first gate on the
   06:00 IST contract, no `continue-on-error` on that step. **A dictionary amendment
   blocks the morning publish.** The step's own comment (morning.yml:103-118) says
   "a test that reaches outside the code it tests does not belong in the contract's
   gate. Same mistake, third time today." efdc969 added the fourth, into that gate.
2. `daily.yml:59` `python -m pytest -q`.
3. `ci.yml:31`.

Fuse lengths, measured:

| Pinned living path | Evidence | Fuse |
|---|---|---|
| `src/fetch_ngrams.py` | 7 commits 07-24..08-08 (07-29, 07-31, 08-06 ×2, 08-07 ×2, 08-08); mean interval 2.1 d | **days** |
| `dictionaries.json` | v1.0.0 07-24 → v1.1.0 07-31 → v1.2.0 08-05; registered dated-amendment process | **~4 days** (next ~08-12) |
| `auditor/RUBRIC.md` | its own header: "Versioned like any instrument; changes are dated amendments" | first amendment |
| `src/precision_frame_v3.py`, `src/precision_audit_v3.py` | born 567606d and efdc969; frame_v3 was rewritten within 24 h of birth, by this very commit | first bug fix |
| `PROTOCOL.md`, `CODING_MANUAL.md` | frozen by intent, no amendment clause | SOUND to pin |

This is the exact class `analysis/registration_audit_2026-08-08.md` §7 named
TB-1/TB-2/TB-4 hours earlier, on the same three paths — and the repo already shipped
the fix on 2026-08-08 in `6270d58`: `scripts/verify_blind_audit_v2.py` resolves living
inputs via `git show <base_commit>:<path>`, and
`tests/test_blind_audit_500.py:69-93::test_living_registered_inputs_resolve_at_base_not_mutable_head`
asserts that the living set is **disjoint** from the working-tree pin set. efdc969
reintroduces the defect the same day the pattern landed, in a second registration.

Fix, using machinery already in the tree: add `base_commit` (efdc969 itself, or a
registration-only child) plus a `base_commit_rule` to registration.json; resolve
`dictionaries.json`, `src/fetch_ngrams.py`, `auditor/RUBRIC.md` (and both v3 modules,
which must stay editable) at that blob with the shallow-clone skip Codex added to
ci.yml; keep working-tree pins only for PROTOCOL.md, CODING_MANUAL.md and the pilot
receipt day, which are genuinely single-purpose frozen artifacts.

### DEFECT 2 — the regime-change path is unrecordable and permanently red; daily.yml:152-160 claims the opposite. `src/precision_frame_v3.py:466-479` vs `:399-406`, `:373-383`

`record_day_outcome` wraps only `build_day_attestation` in its `try`; `_record_payload`
is called **outside** it (`:479`). The regime check lives in `_record_payload:399-406`.
So a dictionary or matcher change mid-window raises past the FRAME_FAILURE handler.

Simulated: recorded three eligible days from the window start, applied one legitimate
edit to `src/fetch_ngrams.py`, wrote day 4's cache (self-consistent, new hashes):

```
day 4 after matcher fix -> FrameValidationError: production matcher or dictionary
                           regime changed inside v3
   attestation written?   False
day 5                   -> FrameValidationError: prospective source window has a
                           missing, extra, or out-of-order day
```

Day 4 is never recorded, so day 5 fails contiguity, and so does every day after it.
`daily.yml:162` runs `python -m src.precision_frame_v3 --record-latest` with no
`continue-on-error` → the enrichment job is red every day for the remainder of the
90-day window. The comment this commit added at daily.yml:152-160 states that an
ineligible day "is preserved as a permanent FRAME_FAILURE record: it invalidates that
cohort without hiding the calendar day **or preventing the later holdout from being
collected**", and PROTOCOL.md:49-54 says the same. Both are false for the regime-change
class: the holdout v3b can never be collected either, because every prior eligible
attestation is compared against every new one.

This is the founder-eyes exposure `analysis/slice_reviews_2026-08-08_batch2.md` (item
3) asked to be ruled on. The ruling was made — FRAME_FAILURE — but it does not cover
the case that the registration's own `regime_rule` singles out. Fix: move
`_record_payload` inside the `try` (or catch its regime error) so the regime change
lands as an immutable FRAME_FAILURE and the chain continues, and make the workflow
comment match whichever behaviour is chosen.

### DEFECT 3 — efdc969 was pushed red. `tests/test_no_secrets_or_subscribers.py:64`

Ran the suite at efdc969 in a clean clone: **1 failed, 595 passed** —
`test_no_unexpected_email_address_is_committed`. `tests/test_precision_audit_v3.py:219`
contained the literal `precision-v3-test<at>example.invalid`, which `EMAIL_RE` matches
(verified) and `ALLOWED_EMAILS` does not list. Main was red for 110 s (16:20:27 →
16:22:17 IST). Any morning or daily run firing in that window would have been blocked
at its first gate. Discharged by ebd1315; recorded because the local gate
(`scripts/gate.sh`: pytest, ruff, mypy) evidently did not run before the push of a
preregistration commit.

### QUESTIONABLE — the registration contradicts itself on the number of precision gates

`registration.json:132`: "All **ten** coder-channel precision gates and all five
channel reliability gates". `PROTOCOL.md:149`: "All **five** coder/channel gates and
all five reliability gates". The code implements ten (2 coders × 5 channels;
`_coder_summary` per coder, `score_package:1280-1286` conjoins both summaries plus
reliability). PROTOCOL.md is the document linked from docs/validation.html and README
for public readers, it is hash-pinned, and it understates the gate by half. One word.

### QUESTIONABLE — GOVERNANCE.md is not amended and now reads against practice

GOVERNANCE.md:15-16: "Calibration rulings must be his personally; a machine supplying
them would fabricate the instrument's ground truth." This registration assigns every
label to two external coders and declares `maintainer_eligible_as_coder: false` —
the founder is excluded by design, for independence. The intent (no machine labels)
is satisfied; the letter is not, and GOVERNANCE.md contains no "external audit"
carve-out (grep: "coder" appears zero times). GOVERNANCE.md:4-6 says a disagreement
between the file and practice "is itself a bug to be fixed in the open". One dated
paragraph closes it. Founder's call.

### QUESTIONABLE — `write_package` will happily write the rights-restricted packet inside the repository. `src/precision_audit_v3.py:577-589`

`output` is taken verbatim; the only guard is refuse-if-exists. The packet contains
third-party titles and URLs which the registration says are "not a public-data
licence" (`rights_and_release.private_packet`). The same module already has
`_safe_path` enforcing the inverse invariant for registered paths. `data/private/` is
gitignored, so the fix is either a three-line refusal when `output` resolves inside
`root` (except under `data/private/`), or naming that path in the docstring instead of
the ambiguous `/private/path`.

### Notes, not defects

- No external timestamp. AI-GPR and blind-audit v2 both carry `.ots` proofs; v3's
  pre-label status rests entirely on git commit times plus the (correct, well-designed)
  freeze-receipt-before-coder-access anchor at `verify_git_anchor`. A `.ots` on
  registration.json costs one command and pre-empts the referee question.
- `validation/` is excluded from the claims scan (`tests/test_claims_discipline.py:76-78`)
  with a coherent reason — a lint must not demand edits to hash-frozen bytes. Consequence
  worth knowing: PROTOCOL.md is publicly linked from docs/validation.html and README yet
  is unreachable by the claims rubric. I read it in full; no unlicensed claim in it.
- Everything else in the test file is fixture-rooted (`tmp_path`, `_fixture_root`
  rewrites the registered digests for the fixture tree) — none of the live-state
  pinning that produced eba2d47. The single live-root test is DEFECT 1.

**Verdict: DEFECT.** The study design, the estimand discipline, the fail-closed
package/receipt/attestation chain and the interval math are the strongest work in this
repo's registration history. The freeze is attached to the tree with the wrong kind of
nail, twice, in the two places that are scheduled to run.

---

## ebd1315 — Keep the precision anchor fixture scanner-safe — DEFECT (minor, non-CI)

One line, `tests/test_precision_audit_v3.py:219`:
`"precision-v3-test<at>example.invalid"` → `"precision-v3-test" + chr(64) + "example.invalid"`.
It works — verified: `EMAIL_RE` matches the first form, returns `[]` on the second,
and the suite goes 595/1 → 596/0.

The defect is what was fixed instead of the address. `tests/test_no_secrets_or_subscribers.py:64-66`
documents its own contract: "A subscriber address reaching the public repo cannot be
unpublished, so the allowlist is **exhaustive** rather than indicative", and a companion
test (`:82`) forces every allowlisted address to carry a reason. After this commit the
repo contains an address that is on no allowlist and invisible to the scan, and the
exhaustiveness claim is false. The precedent — runtime concatenation defeats the leak
scanner — is the whole cost; a real subscriber address hidden the same way would pass.

Two fixes without the precedent: add `"precision-v3-test<at>example.invalid": "a throwaway
git identity for the v3 freeze-receipt anchor fixture"` to `ALLOWED_EMAILS` (four
tracked words, and the reason test then covers it), or drop the `@` entirely — git does
not validate `user.email`, so `precision-v3-test.example.invalid` is accepted.

**Verdict: DEFECT (documentation/control level, no CI or scheduled-run impact).**

---

## 7baf222 — A weekly note without a heading became a 590-character RSS headline — SOUND fix, DEFECT in its own number

The three fixes are right and I verified each by regenerating from source, not by
rereading the code:

- `_feed_title` — heading-only rule. 2026-W32 (has `# …`) → 60-char title; 2026-W31
  (no heading) → `2026-W31`. Both regenerate from `notes/*.md` and appear byte-exact
  in the committed `docs/feed.xml`.
- `_feed_pubdate` — ISO-week Friday. `date.fromisocalendar(2026, 32, 5)` = 2026-08-07
  and `(2026, 31, 5)` = 2026-07-31; emitted `Fri, 07 Aug 2026 12:00:00 +0000` and
  `Fri, 31 Jul 2026 12:00:00 +0000`. Correct, and correctly falls back to build time
  on a malformed week.
- `_feed_summary` — prose, word boundary, ellipsis. Old descriptions: both exactly 400
  chars, one containing literal `#`, one ending `"…ontrol, alon"`. New: 398 and 395
  chars, no `#`, both ending `…` on a word.

**DEFECT — the headline number is wrong, in three places including source code.**
Recomputed from both the note source and the served payload:

| | claimed | actual |
|---|---|---|
| W31 RSS title, note text | 590 chars | **691** |
| W31 RSS title, full `<title>` incl. `2026-W31 — ` | — | **702** chars / 704 bytes |
| W32 RSS title | "63 chars" (sweep doc D2) | **60** |

`notes/2026-W31.md` has exactly one commit (b2c1c94, 2026-08-01) and every historical
`docs/feed.xml` version back to a6652ae carries a 702-character item title — 590 was
never true of any state of this repo. It now lives in `src/render_site.py:130`, where
it will outlive the commit message, plus `analysis/post_redesign_sweep_2026-08-08.md`
:156/:170/:241, `analysis/codex_handoff_2026-08-08.md:98`, and the commit subject and
body. Not on any public page (`docs/*.html`, `docs/*.md`: zero hits) — internal record
and code comment only.

**Second gap: zero tests.** Three named defect classes were fixed in one function and
nothing was test-locked; the only test touching the feed is `test_api_contract.py:45-52`
(the endpoint exists). The repo's rule since e69cb69 is that a fixed class gets a test
that fails before the fix. Three assertions against `_feed_title`/`_feed_pubdate`/
`_feed_summary` on a fixture note with no heading would cost five lines.

**Verdict: DEFECT (prose-number class, non-CI) on a SOUND fix.**

---

## e7f6841 — The post-redesign sweep, and the one defect that is the founder's call — SOUND, two provenance corrections

Analysis-only (`analysis/post_redesign_sweep_2026-08-08.md` +254,
`analysis/codex_handoff_2026-08-08.md` +21). Every repo-checkable number in the sweep
recomputes:

| Sweep claim | Recomputed |
|---|---|
| 82 contract endpoints = 76 JSON + 5 CSV + 1 RSS | 82 = 76/5/1 exact |
| sitemap 26 pages | 26 `<loc>` |
| CSP on 30/30 HTML files | 30 files under `docs/`, 30 carry the meta |
| `assistant_answers` 26 = 19 answered + 7 refused | exact; by-status recount matches `_meta` |
| 5 of 7 refusals `evidence_date_mismatch`, 2 `forecast_or_advice` | exact |
| `data_state` score 2026-08-07 vs receipts 2026-08-06, `aligned: false` | exact |
| `history.csv` 3307 × 7, last row `2026-08-07,…,55.9` | exact |

D1 (receipts stall, freshness blind spot) is the real finding and is stated with the
right mechanism. The 302/297 live-assertion totals are HTTP-run evidence, not
repo-verifiable — trusted context, consistent with everything checkable.

D5 verified in the code, exactly as described: `docs/app.js:237-239` claims the modal
is "Gated on BUTTONDOWN_USER"; `initSubscribe`'s only early return is
`if (!overlay) return;` (`:241-242`); `#subscribe-overlay` is present in
`docs/index.html`; the modal auto-opens at 15000 ms (`:261-265`); with
`BUTTONDOWN_USER === ""` the submit handler takes the else branch and relays to
`https://formsubmit.co/ajax/<the founder's personal address>` (`:286`). Leaving it for the
founder is the correct call under GOVERNANCE.md:10-13 — it is a published commitment
and a personal inbox, not an agent's decision. **Surfaced, not touched.**

**Two provenance corrections** (both in the sweep doc, neither changing its conclusion):

- "Pre-existing … introduced in `55441aa`" — no. `git log -S` puts the
  `formsubmit.co/ajax/…` relay in **`078fcc9` (2026-07-31)**, whose subject is
  "Popup live for all visitors via no-signup relay" — a deliberate decision, live
  **8 days**, not 1. The "Gated on BUTTONDOWN_USER" comment came from `6579f90`, the
  `BUTTONDOWN_USER` const from `12692e0`. `55441aa`'s app.js hunks are the theme-toggle
  label and one definition string — nothing in the subscribe block.
- "`9d4d9aa` changed 7 lines of `app.js`" — `--numstat` says **3 insertions, 2
  deletions**, and neither is in the subscribe block (both are motion-token lines).
  The claim's conclusion holds; the count does not.

**Verdict: SOUND**, with the two provenance lines to correct in the analysis file.

---

## Summary

| Commit | Verdict |
|---|---|
| `efdc969` (preregistration) | **DEFECT ×3** — 7 working-tree pins, 3 on living files, next edit blocks the morning publish (fuse: days); regime change unrecordable and permanently red, contradicting the comment the same commit added; pushed red (110 s). QUESTIONABLE: 5-vs-10 gate contradiction between the two registered documents; GOVERNANCE label-authority letter unamended; `write_package` has no in-repo refusal |
| `ebd1315` (scanner-safe fixture) | **DEFECT (minor, non-CI)** — the leak scanner was evaded, not used; its documented exhaustiveness claim is now false |
| `7baf222` (RSS) | **DEFECT (prose-number, non-CI)** on a SOUND fix — the headline was 691 chars, not 590; the wrong number is now in `src/render_site.py:130`; zero regression tests for three fixed classes |
| `e7f6841` (sweep) | **SOUND** — every repo-checkable number recomputes; two provenance lines wrong (relay introduced 078fcc9 2026-07-31, not 55441aa; 9d4d9aa touched 5 lines, not 7) |

## Open items, priority order

1. **Re-pin the v3 registration to a `base_commit`** before the next edit to
   `src/fetch_ngrams.py` or `dictionaries.json`. This is the only finding that stops
   the 06:00 publish. The pattern, the helper and the test name already exist in
   `scripts/verify_blind_audit_v2.py` and `tests/test_blind_audit_500.py:69`.
2. **Move `_record_payload` inside `record_day_outcome`'s `try`** (or catch the regime
   error) so a regime change records a FRAME_FAILURE instead of reddening the daily
   lane for 90 days — and make daily.yml:152-160 and PROTOCOL.md:49-54 describe what
   the code does.
3. Correct **590 → 691** in `src/render_site.py:130` and the three analysis files;
   add the three feed assertions.
4. Reconcile **PROTOCOL.md:149 "five" with registration.json:132 "ten"** (re-pinning
   in item 1 makes the edit cheap; today it costs a registration amendment).
5. Founder ruling: **GOVERNANCE.md label authority** vs external-coder calibration —
   one dated paragraph.
6. Founder decision, still open from the sweep: **the subscribe modal** (implement the
   gate its comment claims, or wire a real list).
7. `ALLOWED_EMAILS` entry (or drop the `@`) in
   `tests/test_precision_audit_v3.py:219`; restore the scanner's exhaustiveness.
8. `write_package` in-repo destination guard; `.ots` stamp on registration.json.
