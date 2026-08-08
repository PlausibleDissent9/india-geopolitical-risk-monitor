# IGRM cross-review — origin/main f52f63b..fe45a4e (2026-08-08)

**No DEFECT reddens a scheduled run: full suite green at tip fe45a4e (365 "not live" + 14 "live", 0 failures, clean clone).** One transient red window existed on main between eaad1e5 (05:32Z) and fe45a4e (05:38Z) — the inherited `== 37` splice pin (97ed7a8, pre-scope) met the 38th bridged day; fixed append-safe within the window.

Method: read-only. `git fetch` + plumbing reads against the repo; all execution in `git archive` extracts and a scratch clone under the session scratchpad. Nothing in the shared tree was written, staged, or checked out. origin/main advanced twice mid-review (1240c4d, fe45a4e — both after f52f63b, reviewed in scope). 20 commits total: 11 by `Ishan Krishna <ishankrishna9@gmail.com>`, 9 by `igrm-bot <actions@github.com>`, zero Co-Authored-By trailers, zero merges.

Standards input: `analysis/registration_audit_2026-08-08.md` and `analysis/prose_number_audit_2026-08-08.md` read in full. **`analysis/agent_commit_review.md` does not exist** — not at origin/main, not anywhere in history (`git log --all`), not in the worktree. See 8502180.

---

## Verdicts (chronological)

### 3bcd690, cf5beac, 9fc93f4, fb50581 — nowcast bot commits — SOUND
Single-file `docs/data/nowcast.json` refreshes. Sampled fb50581: payload `_meta.generated` 2026-08-08T05:24:33Z vs commit 05:26:33Z (build-to-push skew only); `date: 2026-08-08, provisional: true` — correct shape for the ex-ante nowcast.

### 7a04222 — multilingual chunk cache (bot) — SOUND
The landing commit: 7 gdelt chunks + `data/raw/multilingual_salience.csv` + **first-ever `docs/data/multilingual.json`** (verified: `--diff-filter=A` shows this is the payload's creation commit, exactly as 6ee6cc7 claims).

### 6ee6cc7 — multilingual.json leaves NOT_YET — SOUND
Recomputed: payload exists at origin/main; delisting comment cites the correct bot commit; all 4 tests in `tests/test_wired_lanes_produce_their_payload.py` pass against the extract, and `test_a_pending_payload_leaves_the_list_once_it_lands` makes the delisting *forced*, not optional — the list's own rule executed on itself. "71 empty runs" is an Actions-history claim, not repo-verifiable; it is consistent with the test docstring's independent 2026-08-07 record ("run 71 times across a week").
**Founder eyes (payload, not this commit):** multilingual.json carries 2 of 5 channels × 3 languages (6 of 15 series) with no `n_channels_expected`-style partial-state disclosure in `_meta` — the China lane's partial-legibility discipline (`n_channels_registered/collected`) is the house standard and this payload doesn't meet it. Freshness covers the backfill window (30-day cadence, "V5 still backfilling", src/freshness.py:66).

### d546ee9 — contract picks up multilingual.json — SOUND, one QUESTIONABLE
Recomputed: contract description == payload `_meta.what` byte-identical (generator borrows it — not hand-typed); frozen_fields `[_meta, channels]` == payload's actual top-level keys; **regenerated `scripts/generate_api_contract.py` in the extract: byte-identical to the committed contract** (0 diff lines). Payload semantics verified independently: "divergence is English minus mean non-English" recomputed across all 368 weeks × both channels — 0 mismatches. Claims discipline: "Measures the instrument's bias; association, not risk" — correctly licensed.
**QUESTIONABLE:** endpoint added with no version bump. 0e13cc5 (same day, pre-scope) set the precedent that endpoint additions get a minor bump (2.1.0→2.2.0 for country_china); this commit leaves two distinct contract bodies (80 and 81 endpoints) both stamped "2.2.0, frozen 2026-08-08", and the generator's CONTRACT_VERSION comment still describes 2.2.0 as "country_china added" only. The `_meta.promise` technically only mandates bumps for removals/renames, so no rule is broken — but the version no longer identifies the content. One-line fix: 2.3.0 in `scripts/generate_api_contract.py:24` or an amended comment.

### 3d1c1d0 — OpenAPI + datasheet to 81 endpoints — SOUND
Recomputed from the contract itself: 81 endpoints = 75 JSON + 5 CSV + 1 RSS — datasheet sentence exact; openapi.json has exactly 81 paths; multilingual present in both. Both files regenerate **byte-identical** from `scripts/generate_openapi.py` in the extract (datasheet included), and `tests/test_openapi.py::test_the_spec_and_datasheet_match_their_generator` enforces committed==generated inside a `git archive HEAD` extract in CI — the numbers are generator output, not hand-typed.

### a6158f6 — Indic gradient study (A2) — SOUND
Recomputed every headline number from `analysis/indic_gradient_2026-08-08.json`'s raw per-channel entries (not its own summary block): 14 language-channel pairs cleared the floors (hi 5, bn 5, mr 2, ta 1, ur 1); English leads on both levels and changes in **14 of 14**; a language beats English on changes in **0**; mean changes margins recompute exactly (ta 0.0646 < ur 0.0779 < mr 0.2119 < hi 0.2601 < bn 0.2633), so the ranking and "Hindi ranks 4 of 5" hold; 4 of 29 titles missing in all six languages (CAATSA, Houthi movement, Sanctions against Iran, Trade policy of the United States) matches. Scope honest: analysis/ only, no src or docs touched — "nothing here changes a score" verified by the file list. The 20-views and 180-day floors are imported from committed `src/wiki_hindi.py`; scope-consistent.
**Founder eyes:** (1) `MIN_RESOLVED = 15` (analysis/indic_gradient.py:105) is new to this study and Telugu refused at 14/29 — one article under the floor. The floor and the result land in the same commit, so ex-ante status is unprovable from git; if Telugu's refusal is ever quoted as a finding, say the floor was set in the same analysis that applied it. (2) The pageviews caches for the five new languages are not committed (`data/raw/wiki_indic_cache/<lang>`, disclosed in Provenance) — the committed-half/uncommitted-pair pattern; replication requires refetching from Wikimedia, whose counts revise. Disclosed, so QUESTIONABLE-minor, not a defect. (3) Tamil's rank-1 rests on a single channel (us_trade); the table discloses this.

### 236228c, b265e28 — multilingual chunk caches (bot) — SOUND
Chunk-cache-only commits (4 and 3 files, `data/raw/gdelt_chunks/` only); the backfill lane continuing after the payload landed. Consistent with the 30-day freshness allowance.

### 99aaf90 — morning timeout 20→35 — SOUND
YAML valid. The stated failure ("cancelled by its own 20-minute cap at 20m15s"; "82+ minutes late") is Actions-run history, not repo-verifiable — flagged as trusted-context, and the fix is correct under its own description. Checked the interaction it claims: morning shares daily.yml's concurrency group (`igrm-pipeline-v3-${{ github.ref }}`, verified identical strings) with `cancel-in-progress: false`, so a 35-minute morning shot can overlap daily's 00:51Z backup cron by up to ~13 min — but the daily run *queues*, it is not killed; "35 still clears well before the daily cron" is loose arithmetic against the 00:51 slot, harmless in effect. The miss stays in reliability.json — verified the ledger exists and scores honestly (see eaad1e5).

### 862331c — permanence snapshot record (bot) — SOUND
`docs/data/permanence.json`: only `_meta.generated` changed (1+/1−) — today's archive pass returned identical per-page results. Correct fail-soft behavior; the timestamp is the evidence the lane ran.

### a09715c — scheduler-independent trigger — SOUND
Both halves in one commit: the `on.push.paths: [.trigger/morning]` trigger AND `.trigger/morning` itself (blob 05693ce at origin/main) — the exact committed-half discipline `tests/test_workflow_scripts_exist.py` was written for, honored. YAML valid (all 15 workflows parse). Cron arithmetic checked: 45 23 = 05:15 IST, 3 0 = 05:33, 17 0 = 05:47, 29 0 = 05:59 — all comment labels correct. The idempotence guard makes the 23:45Z early shot a no-op whenever today's final already published (guard compares latest.json `generated` date to `date -u`), and a redundant push-trigger fire likewise. The layers are genuinely independent.
**Notes, founder eyes:** (1) "the resident machine checks at 05:40 IST" is an out-of-repo dependency — the trigger's value requires that external cron to actually exist; nothing in the repo can verify it. (2) `on.push.paths` has no `branches:` filter — a push touching `.trigger/morning` on any branch fires the lane on that ref and its publish path would run from that checkout. Writer-only exposure; a one-line `branches: [main]` closes it. (3) Same-day evidence: the trigger landed 09:41 IST, after today's window — today's contract was already missed (see eaad1e5); the machinery is for tomorrow.

### beb64b3 — claims audit — SOUND
Every factual anchor recomputed: validation.json placebo `{115, 52, 0.452}` exact; founder_interview "45.2% is not a pass" present (:216); vs-gpr.html forbidden-claims list at :125-126 verbatim; index.html og:description at :9 with "validated methodology"; exactly one "external validation" occurrence each in gpr_comparison.json and api_contract.json; surface counts in the companion commit ("16 markdown, 27 pages, 77 payloads") recomputed **exactly** 16/27/77. The ledger-not-fix decision is internally consistent with the shared-tree constraint and was discharged 55 minutes later by 1240c4d. "Every fix site carries uncommitted co-edits" is a claim about the 2026-08-08 worktree state, unverifiable after the fact; nothing contradicts it.

### e69cb69 — claims-discipline test — SOUND (verified property, not just run)
The commit's central claim — calibrated to zero false positives with exactly six pinned violations — was **verified by re-running the scan engine with the pin ledger disabled** against the eaad1e5 corpus: exactly 6 hits, and they are exactly the audit's 6 rows (file and sentence), no more, no less. So simultaneously: zero false positives on honest prose (including all the near-miss sentences the patterns document), zero misses against the manual audit, and pins that tolerate only their exact sentence. Anti-vacuity guard present and real (`test_the_scan_actually_covers_the_surface` pins floor counts of 12/20/25 against a silently-empty glob). The pattern set is 13 patterns as the handoff says. Pin lifecycle worked as designed: all six pins died with their fixes in 1240c4d, same commit, and the pins-disabled rescan at fe45a4e returns **0 hits** — the reader-facing surface is currently clean under the rubric.
**Residual, disclosed by design:** the `_NEG` guard treats any quote character or "than"/"not" within 100 chars as discussion — a future real claim adjacent to quoted text would be excused (false-negative bias chosen deliberately; documented in the docstring). JSON scanning is limited to PROSE_KEYS; a claim under an unlisted key is invisible (scope stated in comments).

### fb50581 — nowcast (bot) — SOUND (covered above)

### 8502180 — Codex handoff — DEFECT (doc-level, non-CI)
**`analysis/agent_commit_review.md` does not exist anywhere** — the handoff's closing instruction ("start with analysis/agent_commit_review.md for the standard the overnight fleet was held to") is a dangling pointer in a document whose stated premise is "coordination by committed artifact, the only channel that survives both agents' context resets." A returning agent with no context cannot follow it. Fix: commit the review standard or repoint to the two committed audits. Breaks nothing scheduled; misdirects the named consumer at the worst time (context reset).
Everything else in the doc verifies: bea58fe contains the monthly.py halves, d080024 the placebo baseline + negative_results live-read conversion, ac26c50 exists as described; Codex's WIP on `tests/test_blind_audit_500.py` is in the worktree (M); `scripts/gate.sh --committed` exists with its rationale; docs/vintages.html has zero inbound links from other docs pages (recomputed: 0); "13 patterns, six violations pinned" both exact; "contract 81 endpoints" exact; the queue's items 1-3 map one-to-one onto the audits' findings.

### eaad1e5 — data: update 2026-08-08 (bot, daily lane) — SOUND
Payload coherence recomputed across the trio: latest.json date 2026-08-07, composite7 61.5→60.1 == history.json last (60.1), all five channels7 equal (86.9/26.2/77.0/24.8/85.6), composite 55.9 == history.csv last row, 3306 rows in both JSON dates and CSV; history.csv gained exactly one row. monthly.json 2026-08: 7/7 days == history's August days, `n_days_composite_present`/`composite_coverage` present (bea58fe's disclosure fields live in production data). freshness.json: zero stale payloads. reliability.json: on_time 0/5, rate 0.0 — published honestly; note the ledger's newest row is day 2026-08-06 because build_reliability.py scores from git evidence *before* this commit exists, so today's miss (day 2026-08-07, published 11:02 IST vs 06:00 contract) appears one publish later, by construction — consistent with how every prior row landed. The task brief's "#99" label is not reproducible from git (27 `data:`-prefixed publishes; 97 bot commits touching docs/data); presumably an Actions run number.
**Known transient:** this commit put the 38th bridged day into the store, arming the inherited `== 37` pin in tests/test_splice_sensitivity.py (from 97ed7a8, pre-scope — the registration audit's TIME-BOMB class, in a file that audit didn't cover). Bot pushes don't trigger ci.yml (GITHUB_TOKEN), so main showed green until the next human push.

### 1240c4d — Replace six unlicensed public claims — SOUND
Textbook discharge of the audit: all six sentences rewritten with licensed language ("descriptive comparisons between related measures, not validation or an accuracy test"); **the generator fixed at src/gpr_comparison.py (not just the payload), so the nightly lane cannot restore the claim**; contract and openapi carry the regenerated description consistently (payload `_meta.what` == contract == openapi, all three edited in the same commit — regeneration-coherent); pins emptied in the same commit per the ledger's own rule; docstring updated to say so. The new REVIEWERS_GUIDE placebo row now states the unfavorable result with its numbers — and every number has a committed home: 52/115 = 0.4522 recomputed; "about 35.6%" == detection_baselines.json `placebo_context.random_placement_overlap_fraction` 0.3558 — closing the prose-number audit's UNVERIFIABLE #3 (the homeless 35.6%). Claims scan at this tree with no pins: 0 hits.

### fe45a4e — Keep disclosure gates append-safe — SOUND
Kills two documented defect classes in one commit. (1) The `== 37` living-count pin becomes an append-safe invariant: `adjusted_store_dates` published in the payload (38 dates, verified 2026-07-01..2026-08-07 inclusive = 38), test now asserts sorted-unique, count==len, >= 37 — can never redden on a legitimate new day, still catches shrinkage and miscount. (2) stress_gauge components now emit the registered four-component schema with explicit `market: null` instead of dropping the key — the "promised field absent from payload" class (prose audit WRONG #3-#7) fixed at the generator with the availability disclosure kept. Suite at this tip: 365 + 14 pass, 0 fail.

---

## Summary table

| Commit | Verdict |
|---|---|
| 3bcd690 / cf5beac / 9fc93f4 / fb50581 (nowcast) | SOUND |
| 7a04222 (V5 payload lands) | SOUND |
| 6ee6cc7 (NOT_YET delisting) | SOUND — payload partial-state disclosure gap noted |
| d546ee9 (contract +multilingual) | SOUND — QUESTIONABLE: 81-endpoint body reuses "2.2.0 frozen 2026-08-08" |
| 3d1c1d0 (openapi/datasheet 81) | SOUND — all counts generator-derived, regenerate byte-identical |
| a6158f6 (Indic gradient) | SOUND — 14/14 and margins recompute exactly; MIN_RESOLVED=15 same-commit-as-result; uncommitted caches disclosed |
| 236228c / b265e28 (chunk caches) | SOUND |
| 99aaf90 (timeout 35) | SOUND — run-history premises not repo-verifiable |
| 862331c (permanence) | SOUND |
| a09715c (push trigger) | SOUND — external resident-cron dependency; no branches: filter on the push trigger |
| beb64b3 (claims audit) | SOUND — all anchors recomputed |
| e69cb69 (claims test) | SOUND — zero-FP property independently verified: pins-off scan = exactly the 6 audit rows |
| 8502180 (Codex handoff) | **DEFECT** — analysis/agent_commit_review.md referenced, exists nowhere (no CI impact) |
| eaad1e5 (data publish) | SOUND — latest/history/csv/monthly coherent; armed the inherited ==37 pin |
| 1240c4d (claim rewrites) | SOUND — generator-level fix, pins died same commit |
| fe45a4e (append-safe gates) | SOUND — closes the transient red; suite green |

Authors: all 11 human commits `Ishan Krishna <ishankrishna9@gmail.com>`, all 9 bot commits `igrm-bot <actions@github.com>`, zero Co-Authored-By, linear history.

## Open items, priority order
1. **Commit `analysis/agent_commit_review.md`** (or repoint 8502180's reference) — the only DEFECT in range.
2. Contract version: bump to 2.3.0 or amend the generator comment — two bodies currently share "2.2.0 frozen 2026-08-08" (d546ee9).
3. `branches: [main]` on morning.yml's push trigger (a09715c).
4. multilingual.json: add China-lane-style partial-state fields (`n_channels_registered/landed`) while V5 backfills.
5. From the standing audits, still open at fe45a4e: the four blind-audit-500 working-tree pins (Codex WIP holds the fix — land it), the stale blind-audit v2 .ots, and the prose-number STALE/WRONG items on Codex's reworked pages (handoff queue items 2-3).
