# Three pages scroll sideways on a phone, and none of it is the tables

Measured 2026-08-08 against the live site at a 375x812 viewport, every
non-Atlas route (21 pages). Three pages exceed the viewport width, so
the whole document slides under the reader's thumb and the fixed header
travels with it.

The fix is in `docs/site.css`, which is being reworked tonight, so this
is a report rather than a commit. Nothing here is an Atlas route.

## The measurements

| Page | scrollWidth | clientWidth | Offending element |
|---|---|---|---|
| methodology.html | **459** | 375 | `CODE` w=428 — `validation/validation_episod…` |
| codebook.html | **386** | 375 | `CODE` w=370 — `shares.json._meta.instrument` |
| validation.html | **478** | 375 | `DIV.toggle` w=451 — the channel selector row |

The other 18 are clean at 375px: start, analysis, notes, data, api,
viewer, corrections, status, break, explorer, history, vs-gpr,
divergence, receipts, vintages, workbench, 404, embed.

## What it is not

It is not the tables, and I checked that the hard way. My first reading
was that unwrapped `<table>` elements were the cause: methodology and
codebook put tables straight into `div.prose`, validation had 3 of its 6
tables outside `.table-scroll`, and pages that wrap them look fine.

That reading came from listing the widest elements on the page, which is
wrong. A child inside a container that already scrolls horizontally
still reports a bounding rect past the viewport, so `.table-scroll`
content shows up in that list looking exactly like a defect. `history.html`
proves it: same `div.prose`, a 403px table, no wrapper, and a
scrollWidth of 375. Re-measured excluding any element with a scrollable
ancestor, every table disappeared from the list and the three elements
above are what remain.

Wrapping the tables changes nothing a reader can see. The wrapping is
still an inconsistency worth tidying one day -- 3 of validation's 6
tables are wrapped and 3 are not -- but it is cosmetic, and it is not
this bug.

## The actual causes

**Inline `<code>` cannot break.** `methodology.md` and `codebook.md`
carry file paths and dotted payload keys inside backticks. The converted
`<code>` is inline, so it never gets the `overflow-x: auto` that
`site.css:850` gives `pre`, and a path like
`validation/validation_episodes.csv` has no space or hyphen to wrap at.
At 375px one token is wider than the column. Both pages are converted by
`_render_md_page`, so this reaches any future prose page with a long
path in it.

**The channel toggle is a fixed-width row.** `validation.html`'s
`div.toggle` lays its channel buttons out in a single 451px line.

## Suggested fix, for whoever owns site.css tonight

Both are stylesheet-level and neither needs markup changes:

    code            { overflow-wrap: anywhere; }
    .toggle         { flex-wrap: wrap; }   /* or overflow-x: auto */

`overflow-wrap: anywhere` on inline code only affects tokens that
already do not fit, so shorter code spans are untouched. Confirm against
`pre code`, which sets `white-space: pre` at `site.css:858` and should
keep scrolling rather than wrapping.

## How to re-measure

Load each route in a 375px frame and compare
`documentElement.scrollWidth` against `clientWidth`. When hunting the
cause, skip any element having an ancestor whose computed `overflow-x`
is `auto`, `scroll` or `hidden` -- otherwise every correctly contained
table reads as a defect, which is the mistake this note exists to record.

## Separately: three title conventions are in use

Not a defect, but visible in the same sweep and relevant to an
institutional design pass:

- `Start here — India Geopolitical Risk Monitor` (em dash) — start,
  methodology, codebook, corrections, status, break, 404
- `Validation, India Geopolitical Risk Monitor` (comma) — validation,
  analysis, notes, data, api, viewer, explorer, history, vs-gpr,
  divergence, receipts, vintages, workbench
- `Knowledge Replay, IGRM` (comma, short name) — the pages added
  tonight: replay, sensors, dna, shock

Every page carries exactly one `h1`, `lang="en"`, a viewport meta and a
description (404 has no description, which is right for a page that
should not be indexed). No image is missing alt text, because no
non-Atlas page carries an `img` at all.
