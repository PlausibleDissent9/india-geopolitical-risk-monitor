# Notes for the author — changes needing your words

## 0.1 Beyond V4: three candidate directions, your call only

You asked what V5, V6, V7 could be. Each of these changes what IGRM is
(a new construct or a new public claim), so per the mission rules none
of it gets built until you choose. Sketches, in the order I would rank
them:

- **V5, the English-bias audit.** IGRM measures English-language
  coverage only (DOC API default; the NGrams bridge filters lang=en).
  Build parallel channel series from GDELT's translated multilingual
  corpus and publish the divergence between English and multilingual
  attention per channel, a number that says how much of the index is
  Anglophone attention specifically. Measuring your own instrument's
  bias is the most credible upgrade available, and it reuses the whole
  existing pipeline.
- **V6, the actors and narratives layer.** From counting to
  characterizing, still zero prediction: which country pairs drive each
  spike (the dyad store already has this), cooperation-conflict balance
  by partner over time (Goldstein-weighted), and term-level attribution
  showing which sub-dictionary vocabulary carried each episode
  (computable from the sub-query shares already stored).
- **V7, the citable instrument.** Quarterly versioned data releases
  with Zenodo DOIs, a frozen v1 API contract page, a monthly
  fresh-clone reproduce-from-nothing CI job, and the paper submission
  package. This is what turns a website into something other people
  cite.

A cheaper alternative worth considering before any of these: the
precision audit program (hand-label article samples per channel,
publish precision numbers). It slots into V5 naturally.

## 0.15 The ladder past V4, authorized 2026-07-31 ("execute up until v14")

Now in the mission queue, one verified increment per night: V5
measurement quality (English-vs-multilingual bias audit, precision
samples, uncertainty bands); V6 actors and narratives; V7 citable
instrument (Zenodo packaging, frozen API, reproduce-from-nothing CI,
preprint assembly); V8 GRM template (country monitors as config); V9
priced-risk panel (CDS, risk reversals; markets forecast, IGRM reads);
V10 outcome layer (UCDP/ACLED ground truth, out-of-sample scoreboard);
V11 pre-registered forecast experiments, Brier-scored; V12 the fork
decided only by V11's evidence (probability product with published
calibration, or the negative published prominently); V13 platform
(package, widgets, alerts; still no PyPI upload); V14 institution
(governance, external replication kit, annual report).

Past V14 the lever is adoption, not code: V15 research program (second
paper from the bias audit); V16 data-platform listings (DBnomics,
Nasdaq Data Link, Kaggle, R package); V17 the replication wedge
(re-run a published GPR-India result with IGRM, send to the authors
who cite GPR); V18 monthly practitioner brief for think tanks and data
journalists; V19 open calibration challenge; V20 state-level and
regional-language buildout; V21 self-sustaining series (advisory
board, annual review, continuity plan). I build every artifact and
draft every email; each send, submission, listing, and account stays
yours under the hard limits, and those sends are what convert the
spike from top-1% to world-class.

If IGRM ever measures risk rather than salience, the honest path is:
priced-risk panel first (measurement), then the V3 predictability
study (does salience lead outcomes at all), then an outcome
arrival-rate model, then a scored forecast layer; the last two change
what IGRM is and follow only from evidence, per V11-V12.

## 0.2 Map boundary depiction, please review before you share the Maps page

The new Maps page uses Natural Earth geometry: standard (de facto)
worldview at admin-0, and Indian states as administered at admin-1,
which includes Jammu and Kashmir and Ladakh as Indian states. Two
things you should look at once and decide:

1. The world map at 110m draws the India-Pakistan and India-China
   boundaries per Natural Earth's default international depiction, not
   per Survey of India. Natural Earth publishes an India-worldview
   admin-0 variant (ne_10m_admin_0_countries_ind); switching is a
   one-line change in scripts/prepare_map_geometry.py if you want it.
2. Indian law has expectations about how maps of India depict J&K,
   Aksai Chin, and Arunachal Pradesh. The states map (as administered)
   is the safer of the two; the world map is where the default
   depiction may differ from the official Indian position. Your call
   whether to switch the world layer to the IND worldview file.

## 0.0 Activate the subscribe list (5 minutes, only you can)

1. Create the free account at buttondown.com (use your normal email).
2. Settings → paste the welcome email below (edit voice as you like).
3. Tell Claude your Buttondown username — one constant flips and the
   centered subscribe modal goes live for every visitor.

**Welcome email, final version (paste into Buttondown):**

Subject: Welcome to the IGRM weekly note

> You're in.
>
> Every Friday you'll get one short read, about 250 words, on what
> actually moved in India's geopolitical salience that week. Which of
> the five channels ran hot: the Pakistan border, the China border,
> Gulf and energy security, US and trade policy, or shipping. What
> drove it, with the sources. And what it does and does not imply,
> stated plainly.
>
> Two minutes of your time. No filler, no doom, no forecasts dressed
> up as insight.
>
> Why trust a number from a stranger's website? Because you don't have
> to. Every claim links back to a live, open index: daily data since
> 2017, downloadable by anyone, with a public methodology tested
> against 21 major historical episodes chosen in advance. It detected
> 18. The three it missed are documented on the site, with reasons.
> When something in the method changes, a dated changelog says so.
>
> What you get as a subscriber:
> - The Friday note, before it appears anywhere else
> - The sourced dossier behind it: the actual articles that drove the
>   week's biggest mover
> - First look at new analyses, like when press attention runs ahead
>   of what markets are pricing, and when markets move first
> - Early access to the working paper this autumn
>
> One email a week. Free forever. Unsubscribe in one click.
>
> If a note ever looks wrong to you, reply and say so. The methodology
> has a changelog for exactly that reason.
>
> Ishan
> https://plausibledissent9.github.io/india-geopolitical-risk-monitor/

## 0.1 Circularity audit of the delegated fills (2026-07-24, post-review)

A review caught a real violation: **"Galwan River"** was in the
china_east Wikipedia list while the Galwan Valley clash is a validation
episode. The page's pageviews are near-zero before June 2020, so the
Wikipedia series would have detected that episode by construction — and
*Galwan* is on the banned list the CI test enforces; the test just did
not cover the Wikipedia file. Fixed: article removed, wiki_volume.csv
rebuilt without it, and the ex-ante CI test now covers
`wikipedia_articles.json` and `trends_terms.json` too.

The rest of the audit, applying the operative principle (a query-list
entry must have meaningful attention baseline independent of any
validation episode):

- **Houthi movement** (shipping) — KEPT. Standing actor page with years
  of pre-2023 baseline (Yemen war since 2014); unlike Galwan River, the
  page does not exist because of the validation events.
- **OPEC** (gulf) vs the "OPEC+ collapse" episode — KEPT. Decades of
  baseline; the episode is named after the institution, not vice versa.
- **Iran–Israel relations** (gulf) vs the four Iran/Israel episodes —
  KEPT. Standing bilateral page, long baseline.
- **Suez Canal** (shipping dictionary and wiki) vs the Ever Given
  episode — KEPT. Permanent chokepoint baseline.
- **"Tawang"** (GDELT dictionary) vs the 2022 Tawang-clash episode —
  KEPT but worth one honest sentence in your §8: the town has standing
  dispute coverage predating the clash, but the shared name makes that
  one episode easier to detect than a name-free case would be.
- **"eastern Ladakh"** (GDELT dictionary) — KEPT, same one-sentence
  treatment: it is sector vocabulary, not an event name, but its heavy
  press usage dates from the 2020 standoff.
- **"ladakh standoff"** (Trends) — SWAPPED for "india china standoff":
  the 2020 event is commonly *called* the Ladakh standoff, which is too
  close to an event name for a query list.
- **alt_weights.json**, **pre-2022 episode appends** — no circularity
  surface (weights touch no queries; episode names never enter any
  query list, and the banned list covers them).

Per the build manual I don't write methodology prose. Two things surfaced
during the build that section 3 should state; suggested language below,
edit as you see fit, then delete this file.

## 1. Sum-of-group-shares construction (methodology §3)

GDELT's DOC API rejects queries longer than ~250 characters (measured
2026-07-24: 222 accepted, 271 rejected). Channels whose full term set
exceeds the budget are partitioned into sub-queries (currently
pakistan_west and gulf_energy, two groups each) and the channel's raw
series is the **sum of the group shares**. Where two groups match the
same article, that article counts twice, so the sum is a slight upper
bound on the true union share. Suggested §3 sentence:

> Where a channel's term set exceeds the API's query-length limit, the
> channel series is the sum of two sub-query shares; an article matching
> both sub-queries counts twice, making the series a slight upper bound
> on the union share. The partition is fixed and versioned with the
> dictionaries.

## 2. Layer-4b/4d fetch window (methodology §8)

The robustness and placebo harnesses fetch 2022-onward only (request
budget), while the primary series extends to 2017. The §8 numbers should
say which window each check covers.

## 3. Validation numbers (methodology §8)

After `python -m src.validate hit-rate|placebo|robustness` you'll have
`docs/data/validation.json`. §8's hit-rate table, placebo overlap, and
robustness correlations are yours to transcribe and interpret — a missed
episode explained honestly is a finding, not a failure.

## 4. World Monitor connection (drafted 2026-07-31, awaiting your go)

World Monitor (worldmonitor.app) checks out: open source under AGPL-3.0 at
github.com/koala73/worldmonitor, 65,000+ stars, 116 contributors, WIRED
coverage, 2M+ users, a real engineering culture. Its Country Instability
Index fuses per-country signals from 65+ external providers, which is
exactly the shape IGRM has for India.

The right first move in a repo that size is a proposal issue, not a cold
pull request. Post the text below at
https://github.com/koala73/worldmonitor/issues/new from your account.
Post it exactly as written or edit it first; either is fine, but it goes
out under your name, so read it once before you click.

---

**Title:** Data source proposal: India Geopolitical Risk Monitor (open
daily India risk-salience index, CC BY 4.0, CORS-open JSON)

**Body:**

I maintain the India Geopolitical Risk Monitor (IGRM), a daily
press-salience index for India-related geopolitical risk in the
Caldara-Iacoviello article-share tradition: five channels (Pakistan /
western border, China / eastern border, Gulf and energy security, US and
trade policy, shipping and chokepoints) computed over GDELT coverage
since 2017, percentile-normalized against each channel's own trailing
two years.

Site: https://plausibledissent9.github.io/india-geopolitical-risk-monitor/

Why it might fit World Monitor:

- It is a validated index, not a feed: 86% hit rate (18 of 21) against a
  pre-registered episode list, with placebo, robustness, and drift checks
  published at /data/validation.json and a full public methodology.
- It is decomposed. The India country dossier could show not just that
  India-related pressure rose, but on which border or corridor.
- Integration cost is near zero: stable JSON over GitHub Pages with
  Access-Control-Allow-Origin: *, no key, one small fetch a day.
  Machine endpoints are documented in the "For integrators" section at
  /data.html; the smallest useful payload is /data/latest.json (date,
  composite, five channel scores, definition in _meta).
- License is CC BY 4.0, AGPL-compatible for data consumption with
  attribution.

Honest scope note: IGRM measures press salience (attention), not risk
itself, and updates once daily, so it is a slower, structured complement
to your real-time signals rather than another live feed. It seems
closest in spirit to a CII component or a country-dossier enrichment for
India.

If this is of interest I am happy to open a PR against src/config and
the relevant service following CONTRIBUTING.md, or to adapt the output
format to whatever the CII ingestion side prefers.

---

Two things before you post, both optional but both strengthen the pitch:

1. The notes archive should not be empty when a maintainer clicks
   through. Your first Friday note is due today.
2. If the maintainer replies with interest, tell me and I will build the
   actual PR (TypeScript, their conventions) for you to submit from a
   fork.
