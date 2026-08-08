# External precision audit v3 — coder manual

Status: **PREREGISTERED INSTRUCTIONS. NO V3 SAMPLE OR LABEL EXISTS.**

This manual applies only to a private package whose `package_manifest.json`
and public freeze receipt pass the v3 verifier. Do not use any v1 or v2 sheet.
Both earlier audit packages are invalidated and quarantined.

Before opening the pilot or scored sheet, obtain the public v3 cohort freeze
receipt and its repository commit identifier from the coordinator. Verify that
the receipt predates coder access and that the scoring command accepts it via
`--freeze-receipt`. A private manifest without this external pre-label anchor
is not an eligible package.

## Eligibility and independence

A primary coder must not have designed IGRM, its dictionary, rubric, audit,
sample, assistant or website. Disclose prior relationships with the founder,
National Economic Forum, FICCI, any project adviser and the recruitment source.
Compensation is a fixed amount agreed before coding and never depends on
agreement, the number of ON labels, a pass, publication or publicity.

Two coders complete the same sampled evidence in different frozen orders. Read
the rubric once. Complete the separate pilot sheet, discuss only the pilot and
resolve procedural questions before either coder opens a scored sheet. After
that point, do not discuss scored rows, inspect the IGRM repository or website,
use another coder's work, or use an LLM/classifier to decide labels.

## The decision

For every row, judge whether the evidence is substantively about the named
channel under `auditor/RUBRIC.md`:

- `ON`: substantively about the channel construct.
- `OFF`: not substantively about the channel construct.
- `ABSTAIN`: the frozen title and lawfully accessible live evidence are
  insufficient for a defensible ruling.

Enter `HIGH`, `MEDIUM` or `LOW` confidence. Explain every ABSTAIN and LOW
confidence ruling in `coder_note`.

The channel is visible because each channel has a different construct. The
matched phrase, query group, score, source tier, selection rank, machine label,
sampling denominator and prior human labels are intentionally hidden.

## Evidence and access record

The frozen title and URL are evidence captured during production. The URL is
auxiliary and may later change. Do not replace a dead, changed or paywalled
page with another article.

Use exactly one access status:

- `TITLE_ONLY`: no live page opened; leave the access timestamp blank.
- `LIVE`: linked page or lawful preview opened.
- `PAYWALL`: page opened but the relevant text was inaccessible.
- `DEAD`: URL failed or no longer resolved.
- `OTHER_UNAVAILABLE`: another access problem, explained in the note.

For every status except `TITLE_ONLY`, enter the access time as an ISO-8601 UTC
timestamp such as `2026-09-21T14:05:00Z`. Do not quote or copy article bodies
into the sheet. A minimal note may describe the ambiguity.

Repeated titles or URLs are not an error. One source document can contribute
to more than one production query group, and the audit samples the exact
group-qualified contribution population. Do not deduplicate or reorder rows.

## Lock and return

Change only these five columns:

1. `coder_label`
2. `coder_confidence`
3. `evidence_access_status`
4. `evidence_accessed_at_utc`
5. `coder_note`

Return the file unchanged otherwise. Record completion time and the file's
SHA-256 in the coordinator log before viewing another coder's work or any
provisional result.

Return a separate private coder-attestation JSON that binds your opaque coder
ID, assigned sheet hash, public freeze-receipt hash and anchor commit. It must
record, in order, packet receipt, pilot completion, scored-sheet completion
and attestation times. It also affirms independence from IGRM design, no
collaboration on scored rows, no LLM/classifier labelling, outcome-independent
compensation, pilot-first ordering and no viewing of IGRM outputs or prior
labels while scoring. The scorer refuses duplicate coder IDs, byte-identical
primary submissions, incomplete statements, impossible chronology or any
sheet/receipt/commit mismatch. These are private process attestations, not a
claim that software can prove a person's independence.

## What the result can and cannot mean

Each coder retains a separate primary estimate. A third reviewer may examine
disagreements after both sheets are locked, but no consensus/adjudicated label
replaces a primary estimate. The audit estimates matched-contribution
precision for one fixed prospective cohort. It does not estimate recall,
event truth, causal impact, forecasting accuracy, historical validity or
superiority over another index.
