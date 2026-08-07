# IGRM blind 500-article audit: coder instructions

> **Package identity:** use only the v2 sheet whose SHA-256 appears in
> `registration.json`. The earlier v1 draw was invalidated before any external
> label existed because its sampler omitted the production India-anchor step.
> Never label, merge or score a v1 copy; see `V1_INVALID.md`.

## What you are judging

For each row, decide whether the linked article is substantively about the named IGRM
channel under `auditor/RUBRIC.md`. Use exactly one label:

- `ON`: substantively about the channel construct.
- `OFF`: not substantively about the channel construct.
- `ABSTAIN`: the title and accessible page do not support a defensible ruling.

The channel must be visible because the rubric is channel-specific. Everything else that
could bias the ruling is hidden: matched phrase, query group, machine label, source tier,
sampling stratum, IGRM score and prior human labels.

## Before the scored sheet

1. Read `auditor/RUBRIC.md` once in full.
2. Label the 20 rows in `pilot_sheet.csv`.
3. If there are two coders, compare the pilot only and discuss how the written rubric
   applies. The pilot is never scored and none of its URLs or normalized headlines appears
   in the 500-row sheet.
4. Any rubric amendment must be written, dated and committed before either coder opens the
   scored sheet. Do not tune the rubric during the scored audit.

## Scored audit

The coordinator sends `coder_sheet_c1.csv` to coder 1 and
`coder_sheet_c2.csv` to coder 2. They contain the same registered rows in two
different frozen random orders; do not reorder either sheet. Work
independently. Do not discuss individual rows after opening the scored sheet
and do not inspect the IGRM repository, website, queries, machine labels or
another coder's answers until both copies are locked. Use a normal browser for
linked evidence. Do not use an LLM, automated classifier, bulk-label tool or
another person to decide or draft any scored label.

For every row:

1. Read the frozen title in the sheet; that title is the immutable primary
   evidence captured with the source corpus.
2. Open the URL when the title alone is not enough. Use only the visible
   summary/lead; do not infer unseen content. Because a live page can change,
   record `LIVE YYYY-MM-DDThh:mmZ`, `PAYWALL`, or `DEAD` in `coder_note` whenever
   you consult it. A dead or changed URL is never replaced with another item.
3. Enter `ON`, `OFF` or `ABSTAIN` in `coder_label`.
4. Enter `HIGH`, `MEDIUM` or `LOW` in `coder_confidence`.
5. Use `coder_note` for an abstention, low-confidence ruling or genuinely ambiguous edge.

Do not delete, reorder or deduplicate rows. Repeated URLs or stories can be
intentional because the primary stratum samples the exact production document
instances that IGRM counts; the separate story stratum samples normalized-title
clusters. The strata may overlap and are never pooled.
Do not use automated translation. If a non-English item cannot be judged from accessible
English evidence, label `ABSTAIN`.

## Independence and payment

A coder must not have helped design IGRM, its dictionaries, this sample or its machine
auditor. Disclose any relationship with the project or its founder. Compensation must be a
fixed amount agreed before labelling and must not depend on agreement, precision, pass/fail
status or the direction of the result.

One completed sheet estimates one coder's precision judgments. It does not create
inter-coder reliability. Two independently completed sheets permit raw agreement and
Gwet's AC1 under the frozen evaluability rule. Cohen's kappa is also published
descriptively with a prevalence caveat. Each coder's Wilson precision estimates remain
separate; there is no consensus or adjudicated primary estimate.

Reliability requires at least 400 firm-label overlaps. No minimum OFF prevalence is
imposed. An exactly all-ON or all-OFF overlap is reported as not identifiable from
constant labels, not as a pass or failure.

## Return

Return the filled CSV unchanged except for the three coder columns. The scorer is:

```bash
python -m src.blind_audit_500 --score coder_1.csv coder_2.csv --output results.json
```

With one coder, omit the second file. The result must still say that inter-coder reliability
was not measured.
