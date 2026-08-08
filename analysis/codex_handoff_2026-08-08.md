# Handoff to Codex — 2026-08-08, from the other resident agent

You went rate-limited mid-batch around 2026-08-07 ~23:00 IST. Your
uncommitted work in the shared tree was never touched; everything below
happened around it, through green committed gates. The founder has
upgraded your plan; welcome back.

## What landed while you were out (all cross-review-relevant)

- Your monthly.py publication-cutoff halves were verified and landed
  verbatim with credit (bea58fe); your receipts_archive patch was
  REFUSED because it calls your uncommitted receipts_ngrams rework —
  land them together.
- Your placebo baseline + register live-read conversion landed with the
  F16 composite7 battery (d080024). Your validation-page placebo test
  is NOT committed — it waits in the tree for your page rework, on
  purpose (a committed test asserting uncommitted page content reddened
  main once already tonight; see below).
- Main went red overnight from exactly that class: your disclosure
  tests landed ahead of their generating src. Fixed by regeneration +
  landing your src halves. Lesson is now in
  tests/test_workflow_scripts_exist.py's docstring and applies to us
  both — the other direction bit me the same night (ac26c50 wired a
  script I never committed; nearly killed the nightly).
- New enforcement you should know before pushing pages:
  tests/test_claims_discipline.py (e69cb69) — 13 patterns, zero false
  positives on the committed corpus, six CURRENT violations pinned by
  their exact sentences. The pins are designed to DIE as you fix each
  sentence; delete the pin with the fix, same commit.

## Your queue (things only you can land, since the files are yours)

1. The six unlicensed claims — analysis/claims_audit_2026-08-08.md has
   file:line and a one-line rewrite for each. Highest value:
   docs/index.html og:description "validated methodology" and
   src/gpr_comparison.py:85 "is external validation" (regenerates
   nightly; fix the generator, payload + contract follow).
2. The four hash-pin time-bombs in tests/test_blind_audit_500.py
   (analysis/registration_audit_2026-08-08.md §7) — your WIP already
   rewrites them against base_commit; land it.
3. The prose-number fixes on your reworked pages —
   analysis/prose_number_audit_2026-08-08.md §STALE/§WRONG (the
   "maritime security" ghost term, receipts §11 cap 25→150, data.html
   citation 1.0.1→current, break.html n=21→29, codebook counts).
4. Inbound links: docs/vintages.html (new, live, zero inbound links),
   /openapi.json + /datasheet.md from data.html.
5. V5 display: multilingual.json landed (71 empty runs → live payload,
   contract 81 endpoints); the page section is yours.
6. The daily-brief withdrawal (withdrawn_factual_grounding_failure in
   your WIP): the founder needs the story — what did the brief get
   wrong? Surface it to him before landing.

## Invariants (unchanged, both of us)

Push only through `bash scripts/gate.sh --committed` green (ship.sh
does this); author "Ishan Krishna <ishankrishna9@gmail.com>", never
Co-Authored-By; explicit-path adds; check `git diff --cached` for
staged riders; never stash/add -A in the shared tree; integrate via a
detached worktree cherry-pick when the remote moves, never autostash.
The founder asks you to land the batch IN SLICES and to match reasoning
effort to the turn — ultra on design and review, lean on rebases. The
quota you burned yesterday was mostly rebase-rework at max depth.

Cross-review continues both directions: I gate your landings, you're
welcome to audit mine — start with analysis/agent_commit_review.md for
the standard the overnight fleet was held to.

## Added 2026-08-08 afternoon

7. `analysis/freshness_measures_writing_not_measuring_2026-08-08.md` --
   freshness.json calls receipts.json fresh while it carries a day-old
   measured date; both modules that would carry the fix are yours. The
   note has the evidence and a suggested treatment (publish the state,
   do not fail on it -- a throttled upstream is a legitimate state).
8. The watchdog was the mechanism of today's missed contract, not a
   bystander: twelve morning runs created, twelve cancelled, each
   dispatch evicting the one queued ahead of it in the shared
   concurrency group. Fixed in 5741d95 (stand down when a run is
   already queued). Worth knowing before you touch morning.yml.

9. `analysis/post_redesign_sweep_2026-08-08.md` -- 302 live assertions
   against igrm.in after your design pass. The pass itself is clean
   (26/26 pages on the new shell, 0 dead links, 0 stale stamps, 0
   external egress, 86/86 endpoints). Two items are yours:
   - **D5, live and user-facing:** `docs/app.js`'s subscribe modal is
     NOT gated as its own comment claims. `BUTTONDOWN_USER` is empty,
     but `initSubscribe()` only returns early on a missing overlay, so
     the modal still auto-opens after 15s and relays visitor addresses
     through formsubmit.co into the founder's personal Gmail -- no
     list, no double opt-in, and the address sits in clear text in
     public JS. Pre-existing (55441aa), not a redesign regression. Left
     for the founder because it is his newsletter promise and his
     inbox, not a bug I should silently switch off.
   - **D1 follow-through:** the freshness blind spot from item 7 is now
     measured, not theoretical -- the receipts lane stall refuses 5 of
     26 questions on the Ask surface's launch day while
     `freshness.json` reports the payload fresh.
   The three RSS defects in the same report (590-char title, missing
   pubDate, raw-Markdown descriptions) were all in one function and are
   fixed in 7baf222.
