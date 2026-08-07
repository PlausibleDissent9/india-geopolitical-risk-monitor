# IGRM blind 500-article audit: coder instructions

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

Make one private copy of `coder_sheet.csv` per coder. Work independently. Do not discuss
individual rows after opening the scored sheet and do not inspect the IGRM repository,
website, queries, machine labels or another coder's answers until both copies are locked.
Use a normal browser for linked evidence. Do not use an LLM, automated classifier,
bulk-label tool or another person to decide or draft any scored label.

For every row:

1. Read the title.
2. Open the URL when the title alone is not enough. Use the visible article or summary;
   do not infer unseen content.
3. Enter `ON`, `OFF` or `ABSTAIN` in `coder_label`.
4. Enter `HIGH`, `MEDIUM` or `LOW` in `coder_confidence`.
5. Use `coder_note` for an abstention, low-confidence ruling or genuinely ambiguous edge.

Do not delete, reorder or deduplicate rows. Repeated stories are intentional because part
of the design estimates the precision of article instances, which is what IGRM counts.
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
