# Claims-discipline audit of the committed reader-facing surface — 2026-08-08

**Scope.** Every reader-facing committed surface at `a09715c`: `README.md`,
`methodology.md`, all 27 `docs/*.html`, `docs/{codebook,corrections,datasheet}.md`,
`paper/` (3 files), `nef/` (4 files), `listings/` (4 files), `package/README.md`,
and the prose strings (`_meta`, `what`/`why`/`reading`/`description`/`finding`
and kin) of all `docs/data/*.json` payloads.

**Rubric.** IGRM measures press salience. No committed reader-facing surface
may state as fact: (a) construct validity — that the index measures, tracks or
captures risk, or that the methodology/index is "validated" or "proven";
(b) superiority over another index; (c) prediction (already lint-banned);
(d) a precision, recall, or placebo *result* as established while the studies
are unlabelled, unfielded, or unfavorable. The committed record itself states
the licensed position: precision UNCALIBRATED at 16 of 100 author labels
(`docs/data/precision.json`, `nef/REVIEWERS_GUIDE.md` item 2), placebo overlap
0.452 with "45.2% is not a pass" (`docs/data/validation.json → placebo`,
`paper/founder_interview.md:218`), and `docs/vs-gpr.html:125-126` forbidding
"outperforms" / "more accurate" / "validates" / "confirms IGRM measures risk"
under every outcome.

**Method.** Pattern sweep (validated/proven/measures-risk/outperforms/superior/
more-accurate/predicts/forecasts/early-warning/precision/recall/external-
validation and variants) over the full surface, then each hit read in context
and classified CLAIM / DISCUSSION / AMBIGUOUS. A banned-substring check cannot
tell a claim from a discussion of the claim (`tests/test_history_page.py:88-95`
records this failing on correct prose), so classification below is by sentence,
not by substring.

---

## CLAIM — violations (6). Every fix lands in a file carrying uncommitted co-edits in the shared checkout; reported here, not touched.

| # | Where | Sentence | Class |
|---|---|---|---|
| 1 | `docs/index.html:9` (og:description) | "Open data, validated methodology." | (a) |
| 2 | `docs/data/gpr_comparison.json:3` (`_meta.what`), regenerated nightly from `src/gpr_comparison.py:85` | "Co-movement despite zero shared pipeline is external validation; divergence is analysis." | (a) |
| 3 | `listings/kaggle_dataset_metadata.json:6` | "External validation: monthly co-movement with Caldara-Iacoviello's GPR-India at r=0.48 despite zero shared pipeline." | (a) |
| 4 | `listings/nasdaq_data_link_pitch.md:16-17` | "(d) external validation against the academic GPR-India index (monthly r=0.48, zero shared pipeline)." | (a) |
| 5 | `nef/REVIEWERS_GUIDE.md:16` | Claims table row: "Placebo channels stay quiet \| validation.html \| placebo payload; rerun `python -m src.validate placebo`" | (d) |
| 6 | `docs/data/api_contract.json` (endpoint 25 description) | Same sentence as item 2, machine-copied from `gpr_comparison.json`'s `_meta.what` by `scripts/generate_api_contract.py` | (a) |

Notes, by item:

1. The adjacent `meta name="description"` on the same page ("with open data,
   validation, and a public methodology") names the battery and is fine; the
   og:description asserts the methodology *is validated*. The committed record
   says otherwise: splice ratios "not described as validated"
   (`methodology.md:101-102`), precision uncalibrated, recall unfielded.
2-4, 6. All four call GPR co-movement "external validation". `docs/vs-gpr.html:126`
   forbids "validates" under every outcome, and `docs/vs-gpr.html:89` states the
   licensed reading: "limited co-movement between related measures... not proof
   that either instrument is superior." r=0.484 in levels, 0.232 in changes,
   cannot be validation under the project's own rules. Item 2 is the worst of
   the three because the string re-publishes nightly from the generator; a fix
   must land in `src/gpr_comparison.py`, not the payload. Item 6 is the same
   sentence again: `docs/data/api_contract.json` is clean of co-edits itself,
   but its endpoint descriptions are machine-copied from each payload's
   `_meta.what` by `scripts/generate_api_contract.py` (co-edited), so editing
   the contract file directly would desync it from the payload and be
   overwritten on the next regeneration — item 6 heals when item 2's generator
   fix lands and the contract regenerates.
5. The committed placebo block (`docs/data/validation.json → placebo`) reports
   `n_placebo_episodes: 115, n_overlapping: 52, overlap_fraction: 0.452`, and
   `paper/founder_interview.md:218` lists "that the placebo test passed — 45.2%
   is not a pass" under claims that would be dishonest. The guide presents the
   opposite as a checkable claim; a reviewer who runs the cited check finds the
   reverse of the row.

## AMBIGUOUS (4) — flagged, not classed as violations

| # | Where | Sentence | Note |
|---|---|---|---|
| A1 | `docs/index.html:176` | "A descriptive research index of news salience, validated against a pre-registered episode list (see Validation)." | Scoped to the episode study and pointed at the page that carries the caveats. "Evaluated against" would match the revised spec language; "validated against" is the verb the current baseline itself uses. |
| A2 | `paper/WORKING_PAPER.md:61-62` | "its detection claims are validated against a pre-registered episode list rather than illustrated anecdotally" | Same verb, scoped to detection claims. Same preferred rewrite. |
| A3 | `docs/data/latest.json` `_meta.what` | "verified to reach 99.5 the morning after a real onset (Pahalgam)" | A true statement about one series value, but it illustrates detection anecdotally — the exact move A2 says the project does not make. Regenerated by the pipeline; a rewrite belongs in the generator. |
| A4 | `nef/REVIEWERS_GUIDE.md:15`, `docs/data/api_contract.json:983` | "hit-rate 18/21" / "the 21-episode list" | Stale counts, not claim-class violations: the committed baseline record is 24 of 29 (`docs/data/detection_baselines.json`, validation page). The claims ledger should cite the current registered record. |

## DISCUSSION — honest prose that any enforcement must never fire on (calibration set)

- "not a validated headline measure" — `methodology.md:345`, `docs/data.html:87`, `docs/analysis.html:78`
- "The production ratios remain frozen, but they are not described as validated." — `methodology.md:101-102`
- "Claims such as "outperforms", "more accurate", "validates" or "confirms IGRM measures risk" are forbidden under every outcome." — `docs/vs-gpr.html:125-126`
- "It is not proof that either instrument is superior." — `docs/vs-gpr.html:89`
- "This does not establish that either is more accurate." — `methodology.md:22-23`, `docs/datasheet.md:59-60`
- "This is not a test of which is more accurate." — `paper/IGRM_paper_v1.md:216`
- "The index measures English-language attention to India better than it measures Indian-language attention" — `paper/IGRM_paper_v1.md:352-354`
- "The index itself predicts nothing" — `docs/predictions.html:38`; "press salience predicts none of..." — `methodology.md:397`
- "this index is not an early-warning system for anything priced" — `docs/datasheet.md:377`, `docs/data/negative_results.json`
- "a better narrative-tracker than early-warning system" — `paper/WORKING_PAPER.md:128`
- "that its precision is established — it's uncalibrated, 16 of 100" and the whole "Dishonest, all of these" list — `paper/founder_interview.md:210-219`
- "placebo channels that must stay quiet" (design requirement, not result) — `docs/validation.html` header
- "The 7-day headline barely beats chance as a detector" — `docs/datasheet.md:350` (negative result about chance, not superiority over an index)
- `_meta.forbidden_claims` lists in `docs/data/ai_gpr_benchmark.json` (quoted deny-list, not claims)
- "'Measuring Geopolitical Risk', American Economic Review" — Caldara-Iacoviello citation in `docs/data/gpr_comparison.json` `_meta.attribution` and on vs-gpr pages (a paper title, not a claim)

## Enforcement decision

Every violation's fix site carries uncommitted co-edits in the shared
checkout (`git status --short` shows `M` for each; item 6's contract file is
clean but regenerates from a co-edited generator), so no prose was changed
here. `tests/test_claims_discipline.py` (committed with this audit) enforces
the rubric structurally on the full surface, with the six violating sentences
pinned as a known-violations ledger: each pin tolerates exactly the sentence
recorded above and nothing else, so a new unlicensed claim in those files still
fails, and each pin dies naturally when the fix lands. Every pattern in the
test was run against the full committed corpus and carries its nearest honest
miss as a comment; the suite passes at `a09715c` with zero tolerated hits
outside the six pinned sentences. (Item 6 was itself found by the test's
first run, not the manual sweep — the sweep read `api_contract.json`'s
endpoint descriptions but missed that endpoint 25 mirrors the violating
`_meta.what`; verification beat reading, again.)

For the founder / the co-editing agent: items 1-4 are one-line rewrites
("validated methodology" → "public methodology"; "is external validation" →
"is convergent behavior between related measures, not validation"); item 5 is
a row deletion or an honest restatement ("Placebo overlap is 45.2% and is
reported as unfavorable, descriptive, unregistered"). Item 2's rewrite must
land in `src/gpr_comparison.py:85` or the nightly lane restores the claim.
