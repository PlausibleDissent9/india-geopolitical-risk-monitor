# IGRM slice reviews — origin/main 832d5e3..567606d (2026-08-08, second batch)

Continues `analysis/slice_reviews_2026-08-08.md` (same standards, same verdict
key) past that review's own batch commits (e4b3704, 0ba2291 — outside scope by
its construction and this one's). Scope: 0831ce3, 103925a, eba2d47, plus
567606d, which landed on origin/main mid-review. All four authored AND
committed `Ishan Krishna <ishankrishna9@gmail.com>`, zero Co-Authored-By,
zero merges, linear. **All four commit messages are subject-only — no body.**
The house convention to date has been a full narrative body per slice; the
stories exist, but only in committed files, not in the log.

Method: read-only. `git fetch` + plumbing reads against the shared repo (whose
worktree is mid-flight with uncommitted Codex work — nothing written, staged,
or checked out there); all execution in per-commit `git archive` extracts and
a scratch clone under the session scratchpad, with independently written
arithmetic. Full non-live suite run per commit in the clean clone:
0831ce3 **392 passed / 0 failed**, 103925a **407/0**, eba2d47 **419/0**,
567606d **433/0** (12 live-marked deselected each time).

---

## 0831ce3 — Withdraw ungrounded machine briefs — DEFECT (live honesty surface; machinery itself sound)

**The withdrawal machinery is exemplary and fully verified.** Everything the
task's checklist asks:

- Reversible/documented: the tombstone (`docs/data/daily_brief.json`) keeps
  the frozen v2 shape (`_meta/date/composite/channels`), `composite` and all
  five channels null, `_meta.status = withdrawn_factual_grounding_failure`;
  the ten prose versions stay byte-preserved in git as incident evidence, and
  the incident file lists them. Recomputed: exactly 10 commits ever touched
  the payload (eb5bb33..eaad1e5), news days 2026-08-03..07, commit-to-day
  mapping in `analysis/daily_brief_incident_2026-08-08.md` exact.
  Deprecation window 2026-08-08 → 2026-11-06 = exactly 90 days (contract
  policy minimum), enforced by `test_public_endpoint_is_only_the_contract_safe_null_tombstone`
  (`>= 90` days, recomputed).
- No silent disappearance: corrections.md/html gained a full append-only
  entry linking the incident file; codebook entry rewritten; status.json lane
  renamed "Machine brief (withdrawn)" reading `_meta.withdrawn`
  (src/status_data.py:111-112, test-locked); freshness EXEMPT with a dated
  must-not-refresh reason (test-locked); NOTES_FOR_ISHAN 0.10 flipped to
  WITHDRAWN, the API-key instruction re-scoped to aptness only, the WhatsApp
  distribution channel cancelled; REPLICATION.md updated. The one quiet spot:
  docs/receipts.html — the page where briefs actually rendered — simply stops
  showing the block (null channels fail its display condition) and its code
  comment still describes a live brief; the explanation lives one page away
  on corrections/status/codebook. Acceptable (absence was always a designed
  state there), noted for founder eyes.
- Nothing still promises the prose: `test_separation_no_forecast_payload_on_front_surfaces`
  rewritten to REQUIRE the tombstone (it now fails if prose returns);
  `test_main_is_a_hard_withdrawal_with_no_model_or_write_branch` sets a key,
  plants a sentinel payload, and asserts no write, no `import anthropic`, no
  `client.messages.create` in source; `test_daily_workflow_cannot_receive_the_model_key`
  greps the workflow block. Contract marks the endpoint deprecated (window
  recomputed), openapi carries `"deprecated": true`, datasheet regenerated.
  Contract/openapi/datasheet all regenerate **byte-identical** in the extract;
  81 endpoints = 75 JSON + 5 CSV + 1 RSS recomputed. Freshness arithmetic
  70 fresh + 0 stale + 11 exempt = 81 ✓. `ANTHROPIC_API_KEY` survives in
  exactly one place repo-wide: the founder-approved aptness step in daily.yml
  (GitHub secrets env — the only allowed pattern). Contract version finally
  moved (2.2.0 → 2.2.1 with a fresh generator comment), so the standing
  version-identity QUESTIONABLE stops compounding.

**THE DEFECT — the published incident narrative misstates the central
mechanism, and git history falsifies it.** The incident file
(`analysis/daily_brief_incident_2026-08-08.md`, Confirmed failure #1) and the
live corrections ledger (docs/corrections.md and .html, 2026-08-08 entry)
state: "`src.daily_brief.build_context()` supplied only latest.json scores and
receipts.json display evidence; **it never read or supplied
stress_gauge.json**. The values therefore had no machine-readable provenance
in the model input" / "Nine stated a stress-gauge value **even though the
generator never supplied that gauge to the model**."

Recomputed against history:

- `c5a828c` (2026-08-04, the feature's own creation commit) put
  `gauge = read("stress_gauge.json")` and `"stress_gauge": gauge.get("gauge")`
  INTO `build_context()`; `55441aa` (2026-08-07 21:50 IST) removed both lines.
- Of the 9 gauge-citing brief versions, **8 were generated inside that window
  and their claimed values match the gauge payload in their own tree exactly**
  (65.1, 65.1, 60.5, 60.5, 65.7, 65.7, 65.7, 65.7 — recomputed per commit).
  Those eight values had exact machine-readable provenance in the model
  input; the model copied its input correctly.
- Exactly **one** brief is genuinely unsupported: `88b9cbc` (generated
  2026-08-07 18:02:42Z — after the removal; 55441aa is an ancestor and that
  tree's daily_brief.py has zero stress_gauge references). Its "the stress
  gauge at 65.7" had no gauge field in its input at all, and the payload
  committed beside it says gauge **57.2** (day 2026-08-05). That is the real
  fabrication — a gauge sentence invented whole, carrying the prior day's
  published value the model could not see.

So the true story is sharper than the published one: the input field was
silently removed mid-experiment (in `55441aa`, an unrelated "site:" commit)
without withdrawing or regenerating the already-published gauge-citing briefs,
and the very next generation hallucinated the gauge line. The corrections
ledger instead indicts all nine values on a mechanism ("never supplied") that
is false for eight of them. Failures #2 (display share as pool quality), #3
(display count as score denominator) and #4 (2026-08-07 scores joined to
2026-08-06 receipts — recomputed: latest 08-07 vs receipts 08-06 at eaad1e5)
are all real and verified in the old code and payloads. But #1, the headline
failure, is wrong as published — on the site's append-only honesty surface,
in the tombstone's `reason`, the contract's deprecation `reason`, and the
codebook. A withdrawal for ungrounded claims whose own public record contains
an ungrounded claim needs a correction-to-the-correction (append-only, per the
ledger's own rule). Fix: append a corrections entry and amend the incident
file; the tombstone/contract reasons regenerate from the generator override in
`scripts/generate_api_contract.py`.

Breaks no CI and no scheduled run; the falsehood is live on
https://igrm.in/corrections.html.

## 103925a — Build evidence-locked assistant core — SOUND

**What the assistant IS:** a local, offline CLI module
(`src/evidence_assistant.py`, `python -m src.evidence_assistant "<question>"`)
plus a design contract (`design/evidence_locked_assistant.md`) and tests.
It is NOT a page, NOT an API endpoint, NOT a workflow step, and makes NO
model call: recomputed — zero references to it anywhere in docs/, .github/,
or scripts/; imports are stdlib-only (no network module, no `anthropic`, no
`os.environ`, no key). The CSP question is therefore moot at this commit:
nothing is served. The design doc says so honestly ("no public endpoint; no
model authorized") and gates any future endpoint behind ten conditions
(spend cap, kill switch, red-team suite, independent review).

**"Evidence-locked" holds mechanically — verified by my own adversarial
probes in the extract, not by rereading their tests:**

- Headline answer renders **60.1 on 2026-08-07** == payload composite7; every
  evidence row's SHA-256 equals my independently computed hash of
  docs/data/latest.json.
- Comparison arithmetic recomputes: gulf 77.0 vs shipping 85.6, "higher by
  8.6 points" — all three numbers derived from the payload, none typed.
- Tamper-after-catalog race (flip composite7 to 99.9 on disk between catalog
  build and render): rejected, `source_digest_mismatch`.
- Forged plan pairing shipping's label with china_east's score7 (denominator
  substitution): rejected, `plan_shape_invalid` — the plan grammar binds
  label/score to the same channel structurally.
- Plan with an extra free-text field: rejected, `plan_fields_invalid` (exact
  field-set allowlist; the model-facing schema has no channel for prose,
  numbers, dates, entities or citations — checked field by field).
- Prompt-injection question: refused with a fixed string; the user's text
  never appears in any answer or refusal (probe marker absent from the full
  JSON output).
- Forecast/advice/hedge/buy-sell: refused before any payload read
  (`forecast_or_advice`), test-locked.

Every emitted sentence is a registered template interpolating only verified
payload values (labels, scores, the payload's own `definition` text); range
(0-100), finiteness, bool/number and str/number type splits enforced at
verify time. The guards question: wired-lanes and contract guards correctly
have nothing to see (no payload, no endpoint); the claims scan's markdown
manifest covers the new tracked .md via e4b3704's ls-files rule, and
`design/` falls under the **pre-existing** exclusion ("design working
notes") added in e4b3704 for design/alerts_webhook.md — the commit did not
touch the scan or its exclusions, so nothing was dodged. The moment a page or
endpoint ships, the sitemap/contract equality tests force it into the scan.

**Founder eyes:** NOTES_FOR_ISHAN (rewritten 10 minutes earlier in 0831ce3)
says of Part B "No backend or model-serving work should begin before that
design passes independent review." This core is neither backend nor
model-serving, and the design doc self-labels unauthorized — but it is
assistant implementation begun the same hour the notes deferred it, before
any independent review and before Part A. Letter kept, spirit worth a ruling.

## eba2d47 — Lock assistant evidence to receipt dates — DEFECT (test-level time bombs; module itself sound)

The module work is right, and I verified it against the live data state:

- Receipt facts are typed per displayed entry (date/title/domain/url/lane),
  each with the "displayed, not a denominator" framing in unit/denominator
  metadata and rendered text; the legacy tier-share and n_articles semantics
  from the brief incident are structurally absent (test asserts the forbidden
  terms never render).
- The receipt-date lock is mechanical: class-6 plans span latest.json and
  receipts.json, and `render_plan` requires the fact set's `as_of` values to
  be a singleton — probe against today's genuinely misaligned tree (latest
  2026-08-07, receipts 2026-08-06) refuses with `evidence_date_mismatch` and
  a fixed sentence. Each displayed entry's compact date must equal the
  receipts payload day (probe-verified via the tests' mutations); URL scheme
  allowlisted (a planted `javascript:` URL dies as `fact_url_invalid`);
  displayed domain is bound to the URL's actual host; <5 entries fails
  closed; titles reject control characters. Class-5 answers name the receipt
  day and recompute grounded: all five shipping titles/domains/urls in my
  probe trace byte-exact to receipts.json.

**DEFECT — tests/test_evidence_assistant.py:140:**
`assert latest["date"] != receipts["date"], "fixture must exercise the guard"`
(in `test_current_score_evidence_refuses_the_real_cross_date_join`). This
pins the LIVE tree to today's anomalous misaligned state. Recomputed across
the last 15 receipts-bearing data commits: **13 of 15 have
receipts.date == latest.date — alignment is the normal state**; today's lag
is the residue of the morning miss. The next completed daily receipts refresh
(expected within ~24 h) realigns the payloads, the assert fails, and ci.yml —
the only pytest runner, push-triggered — reddens on the next human push,
red-latent until then exactly like the `== 37` splice pin (bot pushes don't
trigger ci). This is the TIME-BOMB class the day review documented and
fe45a4e was praised for killing, reintroduced the same day, in a commit whose
entire point is date discipline. The companion test at :149 already shows the
fix: put the misaligned case in a tmp_path fixture too.

**Second instance, same file, :113-131**
(`test_each_channel_has_a_complete_finite_receipt_plan`): requires every live
channel to yield an "answered" receipt plan, i.e. ≥5 displayed articles per
channel in the live payload. china_east displayed **0** articles on
2026-08-03 (eb5bb33 — within the last week); any quiet-channel day <5 turns
the module's correct fail-closed refusal into a suite failure. Same class,
lower frequency. Same fix: fixture roots.

Suite is green today (419/0) — both pins are armed by future normal data
states, not the current one.

## 567606d — Capture prospective precision frame at scoring — SOUND

The v2 lesson ("a reproducible sample from the wrong population is still the
wrong study") turned into acquisition-time infrastructure: `fetch_ngrams`
now embeds `_matcher_evidence` (located/loaded/missing stamps, canonical
matcher specs + SHA, dictionary and matcher-file SHAs, group-qualified
document keys, India anchor set, per-key date/title/url) in the production
day cache on the same pass that computes the score; `src.precision_frame_v3`
independently re-derives eligibility and requires every group's contribution
count to reproduce its published six-decimal share exactly, then writes an
append-only, hash-chained, label-free day attestation
(`data/raw/precision_v3_days/`) that re-verifies every prior day's source
cache before accepting a new one. Recomputed with my own runs:

- The two independent spec constructions
  (`frame._active_specs_from_dictionary` vs
  `fetch_ngrams._canonical_specs(group_specs())`) agree exactly: **7 groups**
  (pakistan_west 2, gulf_energy 2, china_east/us_trade/shipping 1), **57
  phrases == 57 dictionary terms**, partition complete.
- Window 2026-08-08..2026-11-05 = **90 days inclusive**, matching the
  protocol's "all 90 day attestations".
- The fixture's share arithmetic recomputes by hand (2/2 → 100.0, 1/2 →
  50.0 with the India anchor applied).
- Fail-closed paths verified in the code: partial days, ≠48 samples, hash
  drift, regime change, gap/out-of-order windows, revised prior attestation,
  keys outside loaded stamps — all raise; `record_day` is write-once with
  fsync+link and refuses byte-different concurrency.
- Claims discipline: README, data.html, validation.html, REVIEWERS_GUIDE all
  say "label-free source-frame collection ... not a precision result", and a
  new test pins that phrasing on all four surfaces (which are all inside the
  e4b3704 manifests). The tests are fixture-rooted — none of the live-state
  pinning that mars eba2d47. Suite 433/0.

**Founder eyes, one structural exposure:** the daily gate
(`--record-latest`, no continue-on-error) is deliberately fail-loud, but the
attestation chain accepts ONLY eligible days and `record_day` requires the
prior-day sequence to be gapless. One ineligible day (a partial GDELT day, a
47-sample day, a missed run) can never attest, so every later day fails the
contiguity check: the enrichment step goes red and STAYS red for the rest of
the 90-day window. The protocol says a frame failure "must be reported; it is
not an exclusion" — but no committed frame-failure record type exists, so
there is no mechanism to report one AND continue the chain. Decide now, not
on day 41: either that permanent red is the intended tripwire (then say so in
the workflow comment) or add a founder-signed `FRAME_FAILURE` attestation
type that preserves the gap in the record without silencing it.

---

## Summary

| Commit | Verdict |
|---|---|
| 0831ce3 (brief withdrawal) | **DEFECT** — withdrawal machinery sound and fully test-locked, but the live corrections ledger + incident file misstate the mechanism: "never supplied that gauge" is false for 8 of the 9 indicted briefs (input contained the exact values, c5a828c..55441aa); only 88b9cbc (65.7 vs published 57.2, post-removal) was fabricated |
| 103925a (assistant core) | SOUND — local offline CLI only; no endpoint/page/model/key; evidence lock verified by independent tamper, forged-plan, injection and race probes; guards correctly see nothing because nothing is served |
| eba2d47 (receipt-date lock) | **DEFECT** — module sound (cross-date refusal verified against today's real misalignment), but tests/test_evidence_assistant.py:140 pins the live tree to the anomalous misaligned state (aligned is normal, 13/15 recent commits) and :113 requires ≥5 live articles per channel (china_east had 0 on 08-03); ci.yml reddens on the next human push after the next normal daily refresh — the documented ==37 time-bomb class, reintroduced |
| 567606d (precision v3 frame) | SOUND — spec parsers agree (7 groups/57 phrases), 90-day window exact, share identity enforced at six decimals, append-only chain fail-closed; founder eyes: one ineligible day reds the enrichment step for the remaining window with no committed frame-failure path |

Authors: all four `Ishan Krishna <ishankrishna9@gmail.com>` (author ==
committer), zero Co-Authored-By, linear history. All four messages
subject-only — the narrative-body convention lapsed this batch.

## Open items, priority order

1. **Defuse tests/test_evidence_assistant.py:140 and :113** (fixture-root
   both live-state cases) before the next human push lands after tonight's
   daily run — this is the only near-certain incoming red.
2. **Append a correction to the corrections ledger** (and amend
   analysis/daily_brief_incident_2026-08-08.md + the generator-override
   reasons): the gauge was supplied to 8 of the 9 briefs; the fabrication is
   88b9cbc alone, generated after 55441aa silently removed the input field
   without re-checking published prose. The ledger's own append-only rule
   applies to its own error.
3. Rule on the precision-v3 permanent-red exposure (founder decision:
   intended tripwire vs FRAME_FAILURE record type).
4. Retired: the contract-version QUESTIONABLE (2.2.1 shipped in 0831ce3;
   version moves again). Residual: the four historical 2.2.0 bodies remain
   ambiguous in git history — a note in the generator comment would close it
   entirely.
5. Stale code comment in docs/receipts.html still describes a live
   machine-written brief; harmless, one line.
