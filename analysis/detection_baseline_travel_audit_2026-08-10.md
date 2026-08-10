# The headline detection figure did not travel with its baseline — 2026-08-10

**Scope.** The visitor-facing claim sweep requested by the founder, item 3 of
Codex's reprioritized list. This document covers one finding from it. The
2026-08-08 claims audit (`analysis/claims_audit_2026-08-08.md`) is its
predecessor; all six violations that audit recorded have since been fixed and
its `KNOWN_VIOLATIONS` ledger in `tests/test_claims_discipline.py` is now
empty.

**Verdict.** No false statement was found. A distribution problem was.

---

## 1. The finding

`docs/data/detection_baselines.json` publishes four numbers over the same 29
registered episodes:

| Quantity | Value |
|---|---|
| registered corresponding-channel hits | **24** |
| naive any-channel hits | **26** |
| strict start-based hits | 19 |
| expected by chance | 6.8 |

A detector that asks only *"did any channel move?"* — ignoring which one, which
is the entire apparatus — scores **two events higher** than the registered
detector.

A sweep of the reader-facing surface counted where each number appeared:

| | occurrences |
|---|---|
| the registered figure (`24 of 29` / `24/29` / `83%`) | **18** |
| accompanied by the naive baseline | **3** |

The three: `docs/datasheet.md` (twice, in the negative-results section) and one
row of `nef/REVIEWERS_GUIDE.md`. The other fifteen included **both paper
abstracts, the README, the methodology, and both external dataset listings**.

Two documents deserve to be named separately. `methodology.md` and
`paper/IGRM_paper_v1.md` — the two a referee opens first — contained the word
"naive" **zero times**, the string "26 of 29" **zero times**, and the word
"chance" **zero times**, while both stated the registered figure as a result.
`methodology.md` called it "this project's key figure".

## 2. Why this is a claims-discipline defect and not a style note

Every one of the fifteen sentences was true. Several were carefully written.
The defect is not in any sentence; it is in the corpus.

"24 of 29 (83%) detected" read alone is a detection result and a good one.
Read against its own published baselines it is not a detection result at all —
detection is cheap, a dumb rule does it better — it is a **channel-attribution**
result, which is a narrower and more defensible claim that the project can
actually support. The favourable framing travelled to fifteen surfaces
including two external distribution platforms; the deflating one stayed in the
datasheet.

This is the failure mode a banned-substring test structurally cannot catch.
There is no bad word here. The defect is an **absence**, and an absence is only
visible as a ratio between two counts. `tests/test_claims_discipline.py` passed
throughout, correctly — it was never asked this question.

The project's own rubric already licensed the honest reading. `docs/datasheet.md`
states it exactly: *"detection alone is cheap; the channel attribution is what
the apparatus actually contributes."* The knowledge was never missing. Its
distribution was.

## 3. What was changed

Each change adds a **committed** number (from `detection_baselines.json`)
beside an existing one. Nothing was deleted, softened, or reworded to say less.

| File | Change |
|---|---|
| `methodology.md` | New paragraph after the key-figure passage giving all three baselines and stating that the naive rule wins. Regenerates `docs/methodology.html`. |
| `paper/IGRM_paper_v1.md` | Abstract factual spine now carries the baselines inline. |
| `paper/founder_interview.md` | The verifiability boast at §"Its pre-registered episode detection recovers 24 of 29" now states the naive comparison in the same sentence. |
| `README.md` | "Strict-start, naive and chance baselines publish beside that result" replaced with the actual numbers and the direction. Also fixes `docs/datasheet.md`, which copies this section. |
| `listings/kaggle_dataset_metadata.json` | Description carries the baselines; the subtitle no longer quotes the bare figure. |
| `listings/dbnomics_submission.md` | Validation parenthetical carries the baselines. |
| `scripts/generate_api_contract.py` | The `validation.json` endpoint description said "plus baselines"; it now names them. Machine-copies into `docs/data/api_contract.json` and `docs/openapi.json` — the same generator path as item 6 of the 2026-08-08 audit, fixed at the generator so the nightly lane cannot restore the old string. |

### Deliberately not changed

Three sites keep the bare figure, registered in `EXEMPT` with the argument:

- **`paper/WORKING_PAPER.md`** — a SUPERSEDED banner listing what the
  superseding paper carries. A pointer, not an assertion, and the paper it
  points at now states the baselines.
- **`paper/founder_interview.md`, the gauge passage** — here 24 of 29 is the
  *comparator* used to show the four-source gauge failing at 2 of 29. The
  number is already doing unflattering work; adding the naive baseline would
  blunt a negative result.
- **`paper/founder_interview.md`, the claim-to-payload table** — each row tells
  a reader which file to open.

## 4. Enforcement

`tests/test_detection_figure_carries_its_baseline.py`, five tests.

**The expected numbers are read from the payload, never hard-coded.** Pinning
`26` in the test would mean that the day a recomputation moves the baseline,
the prose goes stale and the test keeps passing — precisely the "true when
typed" fuse `tests/test_page_claims_match_payloads.py` was written about. The
coupling is deliberate and it is load-bearing: if the baseline moves, every
prose site fails at once and the failure message lists them by path and line.
A red gate there is correct, because publishing last week's baseline beside
this week's headline is the harm.

**The premise is asserted separately.** Every sentence added above says the
naive rule scores *higher*. If that ever flips, those sentences become false in
the other direction, and a test that only checked co-occurrence would keep
enforcing a lie. `test_the_naive_rule_still_beats_the_registered_one` fails in
that case and names the files to rewrite.

**Exemptions are anchored by sentence**, not by file or line. A file-wide
exemption would also disable enforcement on the sentences in that file that
were fixed — `founder_interview.md` holds both kinds. A line number would drift
silently. An anchor dies when its sentence is rewritten, which is exactly when
the argument needs re-reading. Same shape as `KNOWN_VIOLATIONS`.

### Verified by mutation, not by passing

A passing test proves nothing about a defect that is already fixed. Two
mutations were run against the restored tree:

1. **Baseline paragraph removed from `methodology.md`** → caught by two
   independent tests (`..._never_travels_without_its_baseline` and
   `..._authoritative_documents_state_the_direction`).
2. **Payload edited so `naive_any_channel_hits = 22`** (naive no longer wins) →
   caught by `..._naive_rule_still_beats_the_registered_one`, with a message
   naming every file whose prose would need rewriting.

Both reverted; suite green after restore.

## 5. Incidental defect found while regenerating

Running `python -m src.render_site` alone **strips the content-hash cache-
busting stamps** from the pages it rewrites (`site.css?v=044019ad` → `site.css`
in `docs/codebook.html` and `docs/corrections.html`). `src/stamp_assets` re-adds
them and the nightly lane runs both in order, so this never reaches production
— but a human regenerating one page by hand ships unstamped references and
readers get cached CSS. Recorded here rather than fixed: the ordering belongs
to the pipeline lane, and changing `render_site` to self-stamp would duplicate
the stamp registry.

## 6. The same ratio test on the other headline numbers

Run after the detection pass, on the same surface. The defect turned out to be
a *shape*, not a one-off, but the corpus is in much better condition elsewhere.

| Pair | accompanied | bare | real defects |
|---|---|---|---|
| GPR levels `r = 0.484` vs changes `r = 0.232` | 3 | 3 | **1** |
| Back-extension published `0.893 / 0.848` vs refused `0.216 / 0.153` | 13 | 2 | **1** |
| AI-GPR `rho 0.256` vs its 95% interval `[0.050, 0.407]` | 12 | 2 | **2** |

Four of the seven "bare" hits were **my scanner being wrong, not the prose**:

- `listings/nasdaq_data_link_pitch.md` and `listings/kaggle_dataset_metadata.json`
  qualify the GPR figure in words — "limited co-movement between related
  measures rather than validation" — without quoting 0.232. That is a correct
  qualification. The pattern only looked for the number.
- `methodology.md` (twice) and `docs/datasheet.md` state the AI-GPR interval as
  *"95% **interval** of [0.050, 0.407]"*. The pattern accepted only "95% CI",
  and a `\b` after `0.05` cannot match inside `0.050`.

This is the third time in this sweep that a scan flagged correct prose (the
first was `README.md` on the detection pass). Recorded because the ratio method
is only as good as its companion patterns, and a pattern that is too narrow
manufactures violations that a careless fixer would then "fix".

### The three real ones, fixed

| File | Defect |
|---|---|
| `paper/IGRM_paper_v1.md` | Abstract gave `r = 0.484` in monthly levels and never the composite's `0.232` in changes — the construction that carries information once both series' trends are removed. |
| `paper/founder_interview.md` | The verifiability boast quoted the two channels that replicate at 0.89 and 0.85 without saying that two others scored 0.216 and 0.153 and were **refused publication** by a pre-registered threshold. Four channels went in; two came out. The paper's abstract already handled this correctly; the interview did not. |
| `docs/index.html`, `docs/divergence.html` | Both display `ρ 0.256` as a headline stat tile with no interval. The registered moving-block 95% CI is `[0.050, 0.407]` — a lower bound that near zero is the finding. Verified in-browser at 375px after the fix: no page overflow, no clipped text. |

Generalised into `tests/test_headline_numbers_carry_their_companion.py`, three
rows, values read from the payloads, companions accepted as a **set** so that an
honest prose qualification passes without quoting a number. Mutation-verified:
stripping the back-extension refusal sentence and stripping the CI from the
divergence tile are each caught at the exact line.

## 7. What this audit still does not establish

The robustness gulf (0.527) and the syndication multiplier have not been put
through the same test. Neither has any number that appears only inside
`docs/data/*.json` prose fields, since this pass scoped payloads out on the
grounds that a human does not read a claim there — that reasoning is defensible
for `_meta.what` strings but not obviously right for the `finding` and
`reading` fields, which the site renders. That is the next pass.
