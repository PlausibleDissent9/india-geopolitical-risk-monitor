# IGRM design system — the rules, and why each one exists

The freelance brief (`DESIGN_BRIEF.md`) asked for four things: a token
set, a redesigned homepage hero, one redesigned evidence template, and
**a short usage note so the system can be applied to the remaining
pages**. This is that note.

Character: **dark, calm, technical.** Night is the committed default;
light is a persisted choice and must stay equally legible. Reference
points are FT data journalism, the Economist's data pages, and FRED. The
identity is not being rebranded: Fraunces over Archivo, terracotta
accent, unchanged.

This line used to end "Nothing decorative — no gradients, no glass, no
glow," which was **false about the site it describes**. There is a
blurred gradient field behind everything, a glass masthead, a glow on
the headline number and gradient-clipped eyebrow text: an "Elevation
v1.2, the cinematic pass" shipped on 2026-08-04 and this document was
written two days later without checking. A rule the code does not follow
is worse than no rule, because it teaches the next reader that the rules
here are decorative too. The real one:

> **Atmosphere may sit behind the data or around it. Nothing that
> carries a number may animate indefinitely, and no effect may change a
> value's apparent magnitude.**

Gradients that encode a scale — the calm→elevated→severe band track —
are legends, not decoration. The background field may drift forever
because it sits at `z-index: -1` and carries no information. The band
tick may not, and used to: see §4.

---

## 1. One source of truth: `docs/tokens.css`

Both stylesheets import it. `style.css` is the homepage; `site.css` is
the other nineteen pages and keeps its historical variable names
(`--bg`, `--fg`, `--line`, `--card`) as *aliases* onto the tokens.

**Never declare a colour in either sheet.** They each used to hold their
own copy of the palette under a comment asking the next editor to keep
them in step. That failed on 2026-07-31: the homepage names resolved
empty in `site.css`, which crashed the gap chart's gradient and greyed
every chart on the analysis page. `test_design_tokens.py` now fails if a
raw hex appears in either sheet's `:root`.

## 2. Type: eight steps, no exceptions

```
--fs-micro   11px   table headers, eyebrows
--fs-fine    12px   fine print, footnotes
--fs-small   13px   captions, chart notes
--fs-dense   14px   table cells, dense UI
--fs-body    16px   reading prose
--fs-lead    18px   standfirst, h3
--fs-h2      20px   section heads
--fs-stat    24px   inline stat numbers
--fs-h1      28px   page title
--fs-display 80px   the headline number
```

The site previously rendered **thirteen** sizes: 11.2, 11.52, 12, 12.48,
12.8, 13.6, 14.08, 14.4, 16, 19.2, 21.6, 27.2, 80. Values like 11.52 and
14.08 are not decisions, they are nested `em` compounding. The
consequence was that size stopped meaning rank — subpage `h2` sat at
16.8px against 16px body.

**A literal `font-size` is a bug report about the ramp**, and a test
enforces it. The one legitimate exception is inline `<code>` at `0.85em`,
which should track its surrounding text rather than snap to a step.

## 3. Colour: contrast is measured, not eyeballed

Every text token clears **WCAG AA (4.5:1)** against its paper in both
themes, and a test computes it. Body text is AAA (≈15:1).

`--faint` was first `#626C7C` — 3.59:1, which is AA-*large* only, and
that token exists for small text. Caught by measuring before a single
rule used it. If you add a text colour, add it to the contrast test.

The five channel colours differ in **luminance as well as hue**, so the
series survive greyscale and the common colour-vision deficiencies. A
legend that only works for trichromats is not a legend. Tested with a
minimum luminance gap.

State colour (`--calm` / `--elevated` / `--severe`) is the only place
colour carries meaning about the world. Do not use it decoratively.

## 3b. Spacing is NOT systematised, on purpose

The brief asked for a "spacing rhythm" and this document briefly claimed
one. It was not true: a `--sp-1..--sp-16` ramp shipped and was used
**zero times**, which is the same promise-without-a-fact the rest of this
project spent the day removing. The dead tokens are gone rather than
left to look like rigour.

Migrating ~50 padding and margin literals across two live stylesheets is
a real regression risk, verified at only two viewports, for a modest
gain: the values already cluster on a 2px grid, and spacing does not
carry meaning the way size carries rank. When it is done it should be
its own change, measured page by page — not a side effect of a token
file.

Use `--radius` / `--radius-lg` for corners. For spacing, match the
values around you.

## 4. Motion: five durations, one easing, and an off switch that works

`--dur-instant` 90ms (press feedback, hover tint) · `--dur-quick` 160ms
(colour, border) · `--dur-calm` 260ms (size, padding, layout settle) ·
`--dur-slow` 420ms (deliberate reveals, the band tick arriving) ·
`--dur-ambient` 32s (the one background loop).

The sheets held **15 distinct durations across 46 literals** — 60, 80,
120, 140, 150, 160, 180, 220, 240, 300, 400, 420, 500, 550, 600ms. The
font-size problem in the time dimension: numbers that happened rather
than numbers that were chosen.

**This section previously said "Now four, enforced by a test", and the
test could not see three of them.** Its regex matched `\d+ms`, so `36s`,
`28s` and `3.2s` — sitting in `animation:` shorthands — were invisible
to it. The test was cited as the evidence for a claim it was structurally
incapable of checking. It matches seconds now.

**One easing, and it must not overshoot.** The sheets used
`cubic-bezier(0.22, 1, 0.36, 1)`, which rises past its target and
settles back. On an instrument that reads as the number wobbling, which
is the opposite of calm.

"One easing" was also **false when written**: there were four, across 33
declarations — 27 bare `ease` (which is `cubic-bezier(0.25, 0.1, 0.25,
1)`, a different curve applied to most of the site purely by default), 3
`ease-in-out`, 2 `linear`. Two exceptions survive and are now *tokens*
so they can be counted rather than assumed:

- `--ease-linear` for the reading-progress bar. An eased progress
  indicator reports a position the reader is not at; linear is the
  honest curve for a measurement.
- `--ease-loop` for the single infinite background drift. An asymmetric
  curve reverses at full speed at each turnaround and visibly snaps.

Any third exception has to be argued for in the test.

**Nothing that carries a number animates forever.** `.band-tick` — the
marker showing where today's value sits between calm and severe — ran
`tickpulse 3.2s infinite`: a permanent glow on the data itself, the
loudest element on a page whose stated character is calm, and on a phone
a compositor job with no end. Motion attached to a number should report
a finding, and "still here" is not one. It arrives once and stops.

**The scale covers the charts too, and did not.** `app.js` and
`analysis.html` carried `animation: { duration: 900, easing:
"easeOutQuart" }` — a sixth duration, more than twice the longest in the
ramp, on the two most prominent charts on the site. Every test written to
enforce this section reads CSS, so none of them could see it, and this
document said "enforced by a test" anyway.

It mattered more than the CSS did: `!important` does not reach a number
passed to a canvas library, so those two charts were the **only** motion
on the site that ignored `prefers-reduced-motion` outright. Chart motion
now comes from `docs/motion.js` — one shared helper, not six lines pasted
per page — which reads the duration token and returns `false` under
reduced motion. Chart.js takes a named easing rather than a curve, so
`easeOutCubic` is used as the nearest non-overshooting equivalent to
`--ease`; a test rejects `Back`, `Elastic` and `Bounce`.

**Keyframes live in `tokens.css`, never in a sheet.** `igrm-drift` and
`igrm-pagein` were each defined **twice**, once per stylesheet — the
same two-copies-of-the-palette failure that broke the gap chart on
2026-07-31, moved into the time dimension.

`prefers-reduced-motion` zeroes **every** duration in the scale and both
delay properties, and kills smooth scroll. `--dur-slow` was missing from
that list for a day; the `*` catch-all hid it, which is exactly why
nobody noticed — a rule that works by accident is indistinguishable from
one that works on purpose until the accident stops. The test now compares
the declared list against the zeroed list instead of trusting the
comment. Zeroing a stagger's *duration* while leaving its *delay* also
means the page assembles itself in silence rather than simply being
present, so delays are zeroed too.

## 4b. Cache versions are derived, not typed

Every reference to a stylesheet or script carries `?v=<first 8 hex of
its sha256>`, written by `python -m src.stamp_assets` and checked by
`tests/test_asset_versions.py`.

Before this, versions were hand-typed, and `@import url("tokens.css")`
in **both** sheets had no version at all. That is not a stale-look bug.
A returning visitor would get the new `style.css` asking for
`var(--dur-ambient)` against a cached `tokens.css` that had never heard
of it — and an undefined custom property does not fall back, the whole
declaration is dropped. Three pages (corrections, codebook, methodology)
linked `site.css` bare, and `reveal.js`/`labels.js` were pinned at a
version eight days older than the files.

`src/render_site.py` writes `href="site.css"` unversioned every night,
so this cannot be fixed by hand once. The stamp step runs in `daily.yml`
after everything that writes HTML, and the test checks that position
against the workflow's real order.

## 5. Responsive rules go LAST in the sheet

`style.css` declares `.big-number` three times and `header h1` twice.
Later wins, so a media query placed mid-file is silently undone by
whichever duplicate follows it. That is not hypothetical: the phone
font-size was written, measured, and found to have **no effect at all**
until the block moved to the end. A test fails if a top-level rule
appears after the responsive block.

## 6. What phones changed, and the principle behind it

Measured at 375×812 before any of this: the homepage put **zero** channel
rows in the first screen, and validation.html scrolled the whole page
sideways by 108px.

The principle: **the instrument is the hero; reference content is one tap
away; the page never scrolls sideways.**

- Nav scrolls in one row rather than wrapping to three (109px → 34px).
- The masthead tagline clamps to its first sentence — the construct
  definition. The rest repeats what the page says lower down.
- The row sparkline hides below 640px. It takes a fixed 90px of a 347px
  row, which forced channel names onto three lines and made every row
  96px tall. Hidden, rows are 54px.
- The nowcast chips hide: they list the same five channels as the rows
  directly beneath them.
- Tables scroll inside their own box. Panning a data table is a normal
  gesture; panning an article is a bug.

Reference blocks (the receipts tier legend, the exact-query block)
collapse into native `<details>` — no JS, keyboard-reachable, announced
as disclosures, fully present without CSS.

## 7. Verifying a change

Do not trust `scrollWidth > clientWidth` as proof of horizontal
scrolling — a scroll container's clipped children still count toward it,
and it reported 483 against a 375px viewport on a page that could not be
panned at all. The honest test:

```js
window.scrollTo(500, 0); const overflows = window.scrollX > 0; window.scrollTo(0, 0);
```

Also confirm the browser pane has a real width before measuring layout.
A collapsed pane reports `clientWidth: 0`, which makes every overflow
check return true and every measurement meaningless.

Run `pytest tests/test_design_tokens.py tests/test_csp.py
tests/test_site_links.py` — contrast, the ramp, the single palette,
reduced motion, the phone rules, the self-hosted-only guarantee, and
dead links.

## 8. What is still open

The brief's items 2 and 3 are done to the point of diminishing returns,
not to perfection:

- Three of five channel rows reach the first phone screen, not five. The
  remaining 286px is eyebrow, number, delta, band and nowcast — all
  substantive. Getting the fourth would mean reordering the card with
  `display: contents`, which was judged not worth the fragility.
- The evidence page's first article sits at 1,157px, down from 1,823px.
  Getting it above the fold would mean cutting the machine-written brief
  or the sampling caveat, both of which a reader should see.

A designer hired against `DESIGN_BRIEF.md` should start here rather than
from scratch: the tokens, the contrast floor and the phone constraints
are settled and tested. What remains is judgement about hierarchy and
the information architecture of the evidence card.
