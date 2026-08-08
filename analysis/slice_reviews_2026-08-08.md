# IGRM slice reviews — origin/main fe45a4e..832d5e3 (2026-08-08)

Continues `analysis/day_commit_review_2026-08-08.md` (same standards, same
verdict key: SOUND / DEFECT / QUESTIONABLE) into the slices Codex landed
after that review's tip. Scope: `git log fe45a4e..origin/main` — three
commits at first read, plus two more (c82bbf9, 832d5e3) that landed while
this batch was gating and were reviewed after the push rejection surfaced
them. All five authored `Ishan Krishna <ishankrishna9@gmail.com>` per repo
convention, zero bot commits, zero merges, zero Co-Authored-By. This
batch's own commits are outside scope by construction.

Method: read-only against the shared checkout; every diff read in full from
a detached scratch worktree at origin/main; every recomputation executed in
per-commit `git archive` extracts under the session scratchpad with
independently written arithmetic (not the commits' own test code). Nothing
in the shared tree was written, staged, or checked out.

---

## 6270d58 — Invalidate blind-audit v2 before coding — SOUND

The commit's central factual record (`validation/blind_audit_500/V2_INVALID.md`,
mirrored in corrections.md/html and validation.html) was recomputed line by
line from the committed caches in the 6270d58 extract, with fresh code:

- 2026-08-05 production score cache `data/raw/ngram_days/2026-08-05.json`:
  n_samples **48**, n_docs_sampled **33,961**; registered v2 receipt cache
  `data/raw/receipt_days/2026-08-05.json`: **39** / **28,575**; omitted
  documents **5,386** — all three exact.
- Sampled rows drawn from the deficient cache: **49 of 500**
  (**40** article_instance + **9** story_cluster); by channel
  pakistan_west **10**, china_east **8**, gulf_energy **17**, us_trade **10**,
  shipping **4** — exact.
- Estimand defect: recomputed group-qualified contributions vs unique
  eligible document keys across all registered receipt sources
  (union-plus-india-anchor, url/title/8-digit-date eligibility):
  pakistan_west **287 vs 264**, gulf_energy **8,178 vs 8,156** — exact.
  Multi-group sampled article-instance rows: **9** — exact.
- `registration.json` SHA-256 recomputes to
  `c313c7a5…924a9b87`, matching the constant pinned in the new
  `scripts/verify_blind_audit_v2.py`, and the file is unchanged by this
  commit (the invalidation supersedes interpretation without touching
  frozen bytes — the correct discipline).

Design verified, not just read: the test rework moves living instruments
(rubric, dictionaries, production matchers) to base-commit resolution while
keeping study-specific evidence byte-pinned at HEAD, and the two sets are
asserted disjoint; tamper cases fail closed. The V1_INVALID note now states
that the retained v1 `.ots` does not authenticate v2 and that
`registration.json.ots` was restamped for the exact v2 bytes — the stamp's
calendar attestation itself is not verifiable offline and is taken as
trusted context; the SHA it claims to stamp is verified above.

This discharges the standing open item on the four blind-audit
working-tree pins (the Codex WIP the day review said to land), and it lands
as invalidate-before-field — the negatives-are-products pattern, applied to
the project's own study before any coder saw a row.

**Founder eyes:** `scripts/verify_blind_audit_v2.py` runs a full frozen
rebuild inside two of the tests; the suite absorbs the cost. The
invalidation's "no external or pilot label had been collected" is
recomputed as far as the repo can show it (every coder_label cell in the
committed sheets is empty; the tests now assert exactly that); whether any
sheet left the repo before 2026-08-08 is not repo-verifiable.

## b5d5eb9 — The morning guard asks the remote tip — SOUND

All four claimed defect fixes verified against the committed code:

1. Early-shot deletion: cron arithmetic recomputed — the removed
   `45 23 * * *` is 05:15 IST; the measured UTC day closes 00:00 UTC =
   05:30 IST; the surviving shots `3/17/29 0 * * *` are 05:33/05:47/05:59
   IST, every comment label correct. The "could only squat" premise holds
   in code: heal's `last_allowed = date.today() - PUBLISH_LAG_DAYS` with
   `PUBLISH_LAG_DAYS = 1` (src/fetch_ngrams.py:73) refuses days newer than
   today−1, so a pre-close shot cannot produce the target day; and
   morning.yml and daily.yml share the identical concurrency group string
   `igrm-pipeline-v3-${{ github.ref }}` with cancel-in-progress false, so
   the invalid shot's only effect was queue occupancy.
2. Stale-checkout guard: the guard now runs `git fetch origin main` after
   the lane is acquired and reads `git show origin/main:docs/data/latest.json`
   — the remote tip, never its own trigger-time checkout.
3. Predicate: compares `latest.date` (the measured day; verified a real
   top-level payload field, currently 2026-08-07) to yesterday-UTC, not the
   wall-clock `_meta.generated` stamp. This is the correct target: a
   degraded run can stamp today onto stale data, but cannot make the
   measured day advance.
4. `branches: [main]` present on the push trigger — closing the writer-only
   exposure the day review flagged on a09715c (open item 3).

Also verified: the landed `analysis/day_commit_review_2026-08-08.md` is
byte-identical to the version at tip, and `analysis/agent_commit_review.md`
now exists with the method and verdicts 8502180 pointed to — the day
review's only DEFECT (the dangling handoff pointer, open item 1) is
discharged. The claims-test docstring documents the tried-and-reverted
sentence-boundary cut; the revert-within-the-hour narrative is
working-tree history and not repo-verifiable, but the surviving behavior
(zero false positives on the committed corpus) is verified in this batch's
own work below. The four-defect "external review" origin story is
trusted context; every fix stands on its own code regardless.

**Founder eyes:** `date -u -d "yesterday"` is GNU-date syntax — fine on
ubuntu runners, not portable to a macOS shell; the guard lives only in the
workflow, so nothing local runs it. The guard's fetch assumes the runner
checkout can reach origin — on a fork or a token-less mirror it would fall
to the empty-string branch and never skip, which fails open toward an extra
no-op run, the safe direction.

## 5463bfe — Keep public prose aligned with data — SOUND, one QUESTIONABLE

Every number the prose rewrite pins was recomputed from its payload in the
5463bfe extract:

- Back-extension range: the payload's own series months span **1979-01 ..
  2019-12** across both publishing channels — "1979–2019" is what the data
  says; the replaced "1979–2016" was stale against the committed payload.
  Fixed at the generator (`src/back_extension.py`), payload `_meta.what`,
  contract, openapi, codebook (md+html), and research/history.html
  coherently; both `scripts/generate_api_contract.py` and
  `scripts/generate_openapi.py` regenerate **byte-identical** files in the
  extract, so the numbers are generator output, not hand-typed.
- Citation version: CITATION.cff says **1.11.0**; data.html and igrm.bib
  now both carry it (replacing a hand-typed 1.0.1), and the new test
  derives the expected string from CITATION.cff rather than repeating it.
  The DOI sentence now states no DOI exists — replacing forecast-flavored
  "is planned" prose, consistent with house style.
- Dictionary prose: `"maritime security"` left the shipping terms in the
  registered v1.2.0 amendment (b4c970c, 2026-08-05) — the methodology's
  "Three generic phrases" had been stale for three days; "Two generic
  phrases" matches the committed dictionary ("energy security" in
  gulf_energy, "Suez Canal" in shipping — both verified present). Prose
  follows the registered instrument, not the reverse.
- break.html: `validation.json → hit_rate.overall.n` is **29**; the page's
  new "29 pre-registered episodes across two frozen tranches" replaces the
  stale n=21 (single-tranche) claim.
- Receipts section: `receipts_ngrams.MAX_PUBLISHED` = **150**,
  `receipts.MAX_ARTICLES_PUBLISHED` = **75**; the rewritten prose states
  both and the obsolete "capped at 25 per channel" is gone. The new test
  reads the constants from src, so the prose cannot silently drift again.
- Predictability: salience-leads permutation p-values recompute as
  events 0.738, vix 0.385, inr_vol 0.797 — min **0.385 ≥ 0.05**, so
  removing the copied nightly p-values from prose ("Exact values live in
  the payload") is licensed, and the new test asserts the premise.

This is the discharge of the day review's remaining prose-number STALE/WRONG
queue (handoff items 2–3), done the right way: every fixed sentence gained a
test that derives the number from its committed home.

**QUESTIONABLE (carried forward from d546ee9, now compounded):** the
contract body changed again — `_meta` gained four self-citation fields,
`event_study.json` gained two frozen_fields entries, back_extension's
description changed — and `CONTRACT_VERSION` is still "2.2.0", its comment
still reading "country_china.json endpoint added". Three distinct contract
bodies now share the stamp "2.2.0, frozen 2026-08-08". No stated rule is
broken (`_meta.promise` mandates bumps only for removals/renames) and the
new fields are additive, but the version has stopped identifying the
content, and the day review's open item 2 asked for exactly this one-line
fix. Still one line: bump to 2.3.0 in `scripts/generate_api_contract.py:24`
(or amend the comment), regenerate, and let the suite carry it.

## c82bbf9 — Expose vintages and machine documentation — SOUND

Discovery-links slice, small and fully verifiable. Recomputed in the
c82bbf9 extract: vintages.html inbound linkers are now exactly
{data.html, start.html} — at 8502180 the day review recomputed **0**
inbound links, so the orphaned-page finding is discharged; data.html and
api.html both link openapi.json and datasheet.md, and docs/datasheet.md is
a served file, so no link 404s. Both properties gained tests
(`test_the_page_has_contextual_inbound_links`,
`test_generated_machine_documents_are_linked_from_public_data_surfaces`),
so the links cannot silently rot. Prose additions are descriptive
("reconstruct each published daily series as it stood that morning" —
matches what vintages_panel.json actually does) and make no new claims.

## 832d5e3 — Expose partial multilingual coverage honestly — SOUND

The day review's open item 4 (China-lane-style partial-state disclosure
for multilingual.json), discharged at the generator, the payload, the
contract, and the page in one slice. Recomputed in the 832d5e3 extract
with independent arithmetic:

- Coverage block: 5 registered channels x 3 registered languages =
  **15 expected series**; the channels' own `languages_compared` lists
  yield **4 published** (pakistan_west hin/urd/zho, china_east hin)
  across **2 of 5** channels; `complete: false`; the 11-entry
  `missing_series` list equals the recomputed set difference exactly.
  The new test derives every one of these numbers from the payload's own
  series rather than trusting the block.
- `latest_divergence` recomputes from the series ends: pakistan_west
  english_pct[-1] minus mean of its three languages' last values =
  **−3.4**; china_east (Hindi only) = **−22.6** — both exact.
- Regeneration coherence: payload `_meta.what` == contract description ==
  openapi description (both operation and response), byte-identical — the
  borrowing chain intact.
- The reframing ("English-bias audit" -> "English-language coverage
  comparison" that "does not establish which corpus is correct, represent
  all Indian-language news, validate the index, or change any score") is
  claims-negative: it removes interpretive load rather than adding any.
- Fail-loud display: the section is no longer `hidden`; a missing payload
  renders "failed to load; no result is displayed" instead of silence;
  ALLOWED_ABSENT_FETCHES emptied now that the payload exists, with a new
  test that any listed exemption must actually be absent — the stale-
  exemption class killed at the list itself.

**Founder eyes:** the contract body changed again (multilingual
description) under the same "2.2.0, frozen 2026-08-08" stamp — the
version-identity QUESTIONABLE below now covers a fourth body. Also the
payload's earlier state was noted in the day review as "6 of 15 series";
the regenerated payload publishes 4 (china_east currently completes only
Hindi) — the new coverage block is precisely the machinery that makes such
shifts visible instead of anecdotal.

---

## Summary

| Commit | Verdict |
|---|---|
| 6270d58 (v2 invalidated before coding) | SOUND — every frame/estimand number recomputes exactly; frozen bytes untouched |
| b5d5eb9 (remote-tip guard, early shot deleted) | SOUND — all four fixes verified in code; day review's only DEFECT discharged |
| 5463bfe (prose aligned with data) | SOUND — every pinned number recomputes; QUESTIONABLE: contract version 2.2.0 now stamps a third distinct body |
| c82bbf9 (vintages + machine docs linked) | SOUND — inbound-link and served-file claims recompute; both gained tests |
| 832d5e3 (partial multilingual disclosure) | SOUND — coverage block and divergences recompute exactly; day review item 4 discharged |

Standing open items after this range: the contract version bump is now the
only survivor from the day review's list (items 1, 3, 4 and the blind-audit
pins are discharged above; the v2 `.ots` concern is superseded by the
6270d58 restamp — the new `.ots` claims the verified v2 SHA, calendar
attestation trusted). Four distinct contract bodies now share "2.2.0,
frozen 2026-08-08"; the fix remains one line in
`scripts/generate_api_contract.py:24` plus a regeneration.
