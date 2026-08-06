# Governance

How decisions get made in this project, who makes them, and what can
never be decided silently. This file is descriptive of practice already
in force; where practice and this file disagree, that disagreement is
itself a bug to be fixed in the open.

## Roles

**The founder** (Ishan Krishna) owns every measurement choice: channel
constructs, dictionary terms, weights, thresholds, comparator rosters,
calibration labels, and every public claim the project makes. A
construct choice becomes real only through his signature — moving a
`*_DRAFT` file to registered status with a `frozen_on` date, or an
explicit signed entry. Calibration rulings must be his personally; a
machine supplying them would fabricate the instrument's ground truth.

**Machine lanes** (CI, the VPS cron, agent sessions) implement, fetch,
draft, test, and publish what is already registered. They may propose
anything and decide nothing constructal. Drafts are labeled as drafts.
Machine lanes commit as `igrm-bot <actions@github.com>`; the founder's
own lane commits under his name.

## Append-only surfaces

These files record history and are never rewritten, only appended to:

- `validation/validation_episodes.json` — the registered episode list
- dictionary `amended` lists — every term change, dated, with reason
- `docs/corrections.md` — the corrections ledger
- the methodology changelog
- (when signed) trigger-parameter amendments in `design/alerts_webhook.md`

Rewriting any of them is treated as an integrity incident, disclosed
in the corrections ledger like any other.

## Change classes

1. **Construct changes** (anything that could move a published number
   or its meaning): methodology version bump, changelog entry written
   *before* the change ships, founder signature.
2. **Code changes** (implementation with no construct effect): the
   three local gates (pytest, ruff, mypy) plus CI; the changelog entry
   states explicitly when series values are bit-identical.
3. **Data revisions**: the heal window (35 days) is the only sanctioned
   revision mechanism; committed store and outputs pair at each daily
   data commit. Vintage differences between a committed record and a
   fresh rebuild are documented behavior, not errors
   (`scripts/reproduce.sh` states the tolerance and the reason).

## Deprecation policy (project level)

The API contract (methodology §12) governs payload fields. Above that:

- **A payload, page, or channel is retired, never deleted.** Retirement
  requires: a changelog entry announcing it at least 30 days before
  removal, a major contract version bump if any frozen field goes, and
  a tombstone (the page states what stood there and why it went, with
  the last-served data downloadable). History files keep the retired
  series' past values.
- **A methodology section is superseded, not erased**: the old text
  stays reachable through git history and the changelog names the
  commit.
- Nothing has been deprecated as of 2026-08-06.

## Failure policy

Failures publish. A missed morning contract, a red audit, a wrong
number — each gets a corrections entry with the cause, in plain
language, kept forever. Negative results (a validation that fails, a
forecast experiment that loses to climatology) publish with the same
prominence their positive versions would have had. The site's honesty
surfaces (corrections, limitations, uncertainty bands, reliability
record) are load-bearing product, and no lane may sanitize them.

## Dependencies and bus factor

External dependencies, in full: GDELT (DOC API + Web NGrams v5 on
public GCS), UCDP bulk CSVs, IMF PortWatch, Yahoo Finance (prices;
not redistributed), GitHub (repo, CI, Pages), one VPS, the domain
`igrm.in`, and optionally the Anthropic API for display-layer labels
(fail-closed without it). No aggregator or third-party index is ever
a data input.

Everything needed to rebuild the site exists in this repository plus
those public sources; `REPLICATION.md` is the proof procedure. Keys
(GitHub secrets, VPS access, domain registrar) are held by the founder
alone. If the project goes unmaintained, the last published data,
methodology, and this governance record remain valid as a dated
instrument — the archive-mirror preparation (V14) exists so that even
the hosting is not a single point of failure.
