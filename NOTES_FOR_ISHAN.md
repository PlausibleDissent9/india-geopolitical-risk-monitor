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

## 0.2 RESOLVED 2026-08-05: maps now use India's official depiction

You decided in chat ("execute the Indian map as India has it... J&K and
PoK is an integral part of India"). Done the same hour: the world map
uses Natural Earth's India point-of-view admin-0 geometry (India's
polygon verified reaching 37.1N, i.e. including PoK, Gilgit-Baltistan
and Aksai Chin), and the states map now draws the full national
outline as its outer border with the administered states inside it,
the way official Indian maps are drawn. A depiction disclosure is on
the maps page. Original memo below for the record.

## 0.2 (original memo) Map boundary depiction

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

## 0.4 Source tier-4 designations need your citations

source_tiers.json ranks receipts credible-first. Four syndication mills
are tier 4 on evidence our own datapacks contain. The broadcast outlets
you named (Aaj Tak, Zee, Republic, Times Now) are held at tier 3 until
you attach citations to documented incidents (IFCN fact-checks, the
Karachi broadcast): a public tier-4 designation is an accusation, and
the project only publishes what it can cite. Send links, they move.

## 0.9 Dictionary amendment memo: the swimmer leak (shipping precision, your sign-off)

The FICCI director found a charity swim story ("Five swimmers to take
on English Channel for Havens hospices") on the shipping receipts card.
Diagnosis, exact: the shipping dictionary has no India anchor by
registered design (chokepoints are global corridors), and GDELT matches
full article text, so any story whose body mentions "shipping lanes"
(Channel swim stories always describe dodging them) or "maritime
security" boilerplate enters the channel. The score impact is tiny (one
article in a share-of-all-coverage denominator); the credibility impact
of a swimmer on the evidence card is not.

Options, ex-ante compliant in all cases:

- (a) Drop the two generic terms ("shipping lanes", "maritime
  security") in dictionaries v1.2.0. Cleanest precision gain; recall
  cost: genuine corridor stories that use only generic vocabulary are
  lost.
- (b) RECOMMENDED. Keep the concepts but scope them: replace the bare
  terms with corridor-anchored forms, e.g. "shipping lanes" AND (Red
  Sea OR Suez OR Hormuz OR Malacca OR Aden OR India), same for
  "maritime security". Kills the swimmer class, keeps corridor recall,
  per-term rationale documented, and the precision auditor measures
  the effect within days.
- (c) No amendment; presentation-only mitigation (title-hit stories
  already sort first, body-text-only matches get labeled "full-text
  match" so odd stories explain themselves).

Reply "approve shipping memo with a/b/c" (edit freely first);
registration, changelog, and CI-test updates follow the same night.

## 0.10 AI serving layer on the site (FICCI ask, your money and your voice, so your call)

The director asked whether the site could carry an AI method that
summarises or serves whatever the visitor asks. Three honest options:

- (a) FREE, SHIPPABLE NOW, no decision needed: auto-assembled daily
  briefs per channel, template-generated from payloads the site already
  publishes (what moved, by how much, which receipts, event record,
  transits). No LLM, zero cost, labeled "auto-assembled" and never in
  your voice. The night crew builds this regardless unless you say
  stop.
- (b) LLM-WRITTEN NIGHTLY SUMMARIES: one API call per channel per day
  inside the daily CI run. Order-of-magnitude cost at current API
  pricing: well under $5/month. Needs your API account (the money
  hard limit binds me), a "machine-written, not the author" label, and
  a decision on whether generated prose belongs on a measurement
  instrument at all. My honest note: this is a credibility trade, not
  a technical one.
- (c) INTERACTIVE ASK-ANYTHING: needs a backend or serverless proxy,
  key management, abuse control, and a spend cap. Real product work,
  real standing cost, real injection-attack surface. If you want it,
  it is a V13-adjacent build with its own design memo first.

Reply "approve ai memo a", "a+b", or "a+b+c"; (a) alone needs no reply.

### 0.10 RESOLVED: you approved a+b in chat, 2026-08-04

The machinery is built and pushed (c5a828c): registered prompt
(prompts/daily_brief.md v1.0.0), lint, fail-closed paths, workflow
step, codebook entry, page rendering. It activates the day you do the
one part only you can (about 10 minutes):

1. Create an account at console.anthropic.com (your normal email).
2. Billing: add the minimum credit ($5 covers roughly 2-3 months) and
   set a monthly spend limit of $5 so a bug can never run up a bill.
3. Create an API key, copy it once.
4. Repo Settings > Secrets and variables > Actions > New repository
   secret, name ANTHROPIC_API_KEY, paste the key.

The next daily run after that publishes the first brief. Until then
the step prints a skip line and the site shows nothing. Option c
(ask-anything chat) stays open; nothing is built for it.

Reproduce cannot byte-match event-study numbers because their market
inputs (Yahoo) are gitignored by the redistribution-license decision.
Current policy: those two files verify within a 0.06 tolerance band,
documented in reproduce.sh. If you ever want byte-exact replication,
the option is committing derived_returns.csv (log returns, not
prices); whether derived returns clear the license line is your call,
not mine. Everything else byte-reproduces.

## 0.6 V8 decision memo: Pakistan monitor architecture (founder signs before any registration)

The GRM template needs each country's channel architecture decided by
you. Proposal for GRM-Pakistan, five channels mirroring the IGRM
design logic (geography, institutions, doctrine, chokepoints), all
terms ex-ante (no event names). Term lists below are DRAFTS for your
edit; final lists get per-term rationale at registration, same as
India's.

1. india_east: the mirror of our pakistan_west. Draft terms: "Line of
   Control", "ceasefire violations", "cross-border firing", "Kashmir
   dispute", "surgical strikes", "airspace violation".
2. afghanistan_border: Durand Line security. Drafts: "Durand Line",
   "border fencing", "Torkham crossing", "cross-border militancy",
   "refugee influx".
3. internal_security: standing insurgencies and militancy. Drafts:
   "Balochistan insurgency", "TTP", "sectarian violence", "security
   operation", "suicide bombing" (category vocabulary, not events).
4. china_cpec: the China relationship as economic-security corridor.
   Drafts: "CPEC", "Gwadar port", "Chinese workers", "Belt and Road",
   "project security".
5. economy_external: IMF dependence and external stress. YOUR CALL
   FLAG: this stretches "geopolitical" toward macro-financial risk;
   Caldara-Iacoviello country series do include economic-coercion
   vocabulary, but a pure-geopolitical Pakistan monitor would drop
   this channel for, say, gulf_relations (Saudi/UAE bailout politics).
   Decide the construct: economy_external or gulf_relations.

Also your call: anchor word ("Pakistan" per the comparator precedent)
and whether GRM-Pakistan publishes on the IGRM site or waits for the
platform. Reply "approve pakistan memo with X" and registration
follows with full rationale; then Indonesia and Vietnam memos come one
per night.

## 0.7 Dictionary amendment memo: military-institution vocabulary (your sign-off)

You caught a real recall gap: statements by military leadership (the
DG ISPR class of story) can carry zero of pakistan_west's current
phrases, so they are never counted, and no sample-depth fix reaches
what the dictionary does not match. Proposed dated amendment,
institution-category vocabulary, ex-ante compliant (standing
institutions, not event names):

- pakistan_west, add: "ISPR" (the military's media wing; statements
  are recurring coverage), "army chief" (standing office vocabulary
  in both countries' press), "DGMO" (the hotline-talks office that
  anchors de-escalation coverage).
- Consider also: "Pakistan army" as anchor-paired phrase; your call on
  whether it is too broad (it will match sport-adjacent and human
  interest stories; the precision auditor will measure exactly how
  much).

Effect: recall rises for leadership-statement coverage; precision
impact gets measured by the auditor within days and published as
found. Amendment ships as dictionaries v1.2.0 with per-term rationale
and a changelog entry the moment you reply "approve dictionary memo"
(edit the list freely first).

### 0.7 addendum, after your inflation concern (2026-08-04)

Your instinct is technically sharp on two counts. First, the
percentile absorbs CONSTANT rhetoric: if ISPR statements are steady
background, ranks do not move; only rhetoric SPIKES would register.
Second, and this is the real issue: adding statement vocabulary makes
rhetoric variation part of the construct, and Pakistani military
communication is prolific enough that rhetoric waves would then move
the channel even when the border itself is quiet. That is a different
instrument, and "Pakistan reads hot forever" is a fair caricature of
the risk.

REVISED RECOMMENDATION: do NOT amend. Instead, document the exclusion
as a construct decision in methodology section 2: leadership rhetoric
is out of construct by choice; such stories are counted only when
they co-occur with structural vocabulary (a rhetoric story that
mentions the LoC counts; pure rhetoric does not). The receipts
quality depth (now 150-article pools) will still SURFACE those
stories whenever they brush the construct. If you ever want rhetoric
measured, the honest form is a separate labeled sub-series, never a
quiet widening of the main channel. Reply "approve exclusion note"
and the methodology sentence ships; the amendment memo is withdrawn
unless you say otherwise.

## 0.8 IST rebinning of event layers (practitioner item 6): scope and your call

The mission file's practitioner layer asks for event data rebinned
onto IST calendar days (5:30 AM boundary) from GDELT's 15-minute
files, instead of the current convention: `src/fetch_events.py`
attributes each event to "the day GDELT's file arrived," which is a
UTC/US-Eastern publication-day convention, not IST, and is currently
disclosed as such in the codebook.

Why this is a decision, not just a build task: rebinning would
recompute the day-boundary for the entire committed events history
(`data/raw/events_daily.csv`, `events_dyads.csv`, `events_states.csv`,
3,927 days) onto a different clock. Some events currently counted on
day D would shift to D-1 or D+1. That changes every published event
count, dyad count, and state count in the historical record, not just
future days. Per the mission rule against silently changing anything
that would alter a published number, this needs your sign-off before
any registration, even though the change is "just" a clock convention
and not a new construct.

Two honest paths, your call:

1. **Forward-only cutover.** Keep the existing UTC/publication-day
   history exactly as published (disclosed as such, permanently), and
   switch only new days going forward to IST-15-minute rebinning,
   dated and versioned like the chokepoint sub-dictionaries were. The
   series has a documented, dated seam; nothing already published
   changes. Cheapest, and matches how the site already treats other
   methodology changes (append, don't rewrite).
2. **Full retroactive rebin.** Refetch and reprocess the entire
   history on GDELT's 15-minute files (a meaningfully larger fetch
   than the current daily-file backfill; GDELT 2.0's 15-minute exports
   go back to 2015, so coverage exists, but at roughly 96x the file
   count of the current daily approach) and republish the full series
   under the new convention, with the old convention's numbers kept
   only in the corrections ledger. Byte-for-byte "IST-native" history,
   but every previously-cited number in a note or the paper would
   technically now read differently, which is the kind of silent
   change the corrections ledger exists to prevent, not commit.

My recommendation is option 1: it delivers the IST framing the
practitioner layer wants for everything reported going forward,
costs a bounded amount of new engineering, and never quietly moves a
number anyone has already cited. Reply "approve forward-only IST
rebin" (or specify option 2, or a cutover date) and it enters the
queue as a normal dated registration, methodology changelog entry
included.

## 0.11 Your complete list through V21 (reconfirmed 2026-08-04)

You said keep climbing through V21. The machine builds every artifact;
this is everything only you can do, ordered by unblock value per
minute of your time. August override still binds: items marked AUG fit
inside it; everything else can wait for September unless you say
otherwise.

ACCOUNTS AND KEYS, one-time, ~45 minutes total:
1. AUG ANTHROPIC_API_KEY repo secret (activates daily briefs; steps in
   0.10 RESOLVED above). ~10 min.
2. AUG Zenodo account (V7 DOI; packaging is ready and waiting). ~10 min.
3. Buttondown account (weekly note delivery + subscribe modal; welcome
   email ready in 0.0). ~5 min.
4. ACLED access key at acleddata.com (unblocks V10 outcome layer). ~10 min.
5. indiconomics repo creation on GitHub (starts track two). ~1 min.

DECISIONS, reply in chat, ~2 minutes each:
6. Memo 0.9 swimmer amendment: a/b/c (recommendation: b).
7. "Approve exclusion note" (0.7 addendum, leadership rhetoric).
8. V8 Pakistan memo: economy_external or gulf_relations, plus anchor.
9. IST rebinning memo (0.8).
10. Map worldview: IND variant or default (0.2).
11. Derived returns licensing (0.5).
12. Tier-4 citations for broadcast outlets, or leave at tier 3 (0.4).
13. Four staging memos in ~/indiconomics-staging/DECISION_MEMOS.md.
14. V5 range-cut (2019-2022) if Kalev stays silent another week.

RECURRING, small:
15. AUG Daily Why-card taps, 10-15 inside your normal reading; two
    weeks of this makes the precision auditor citable (n~100).
16. Friday note, ~250 words from the pre-assembled evidence; biweekly
    is fine in August per your own override.

SENDS THAT CONVERT V15-V21 (drafted by the machine, sent by you;
these ARE the top rungs; September unless you choose sooner):
17. World Monitor proposal issue (text ready in section 4).
18. Kalev follow-up if no reply by ~Aug 10 (raises every data ceiling).
19. Mint the V7 Zenodo DOI once your account exists (two clicks).
20. V15 paper: write your voice sections (methodology intent,
    interpretation, conclusions; the factual apparatus is drafted for
    you), then submit the preprint (SSRN or arXiv account, your name).
21. V16 listings: DBnomics, Nasdaq Data Link, Kaggle datasets; account
    + submission each, packages prepared for you.
22. V17 replication wedge: send the prepared replication note to
    authors who cite GPR (emails drafted, your send).
23. V18 practitioner brief: forward the monthly brief to the FICCI
    director and the think-tank list (via Buttondown once it exists).
24. V19 calibration challenge: one announcement post, your account.
25. V21 institution: invite 2-3 people to an advisory shell and one
    external replicator to run reproduce.sh (invitation drafts ready);
    an institution is real when someone outside reproduces it.

The math of it: roughly 45 minutes of accounts, 25 minutes of
decisions, and the taps make everything below V15 fully autonomous.
V15-V21 then cost you one send at a time, each with the artifact
already built and the draft already written.

## 0.12 BigQuery lane setup (approved 2026-08-04; ~15 minutes, only you)

You approved the GDELT-via-BigQuery lane and full-scale LLM aptness.
Both go live the day these secrets exist. Likely cost: $0 for
BigQuery (Google's 1TB/month query free tier covers our volumes;
every query is also hard-capped with maximum_bytes_billed so a bad
one fails instead of billing), $8-15/month for aptness + briefs
combined.

BigQuery (~15 min):
1. console.cloud.google.com, sign in with your Google account.
2. Top bar > New project > name it igrm-data. No billing card needed
   to start (the free "sandbox" tier is enough); if Google ever asks
   for billing later, add it WITH a budget alert at $10.
3. Left menu > IAM & Admin > Service Accounts > Create service
   account > name igrm-ci > grant it the role "BigQuery Job User" on
   the project > done.
4. Open the new service account > Keys > Add key > JSON. A .json
   file downloads.
5. Repo > Settings > Secrets and variables > Actions:
   - New secret GCP_SA_JSON: paste the ENTIRE contents of that file.
   - New secret GCP_PROJECT_ID: the project id (e.g. igrm-data-4711).
6. Delete the downloaded .json from your machine afterward.

Aptness (piggybacks on the brief key):
7. When you do the ANTHROPIC_API_KEY step from 0.10, set the console
   monthly spend cap to $20 instead of $5. That is the only change.

The night crew builds src/fetch_bigquery.py and the batch aptness
classifier the first night both secrets exist. Declined and closed:
paid designer, bounties/prizes, commercial market data.

## 0.13 Business exposure layer + the ask-anything assistant (your idea, 2026-08-05; your call)

You asked how IGRM becomes functional for businesses: a textile owner
arrives and wants to know what this means for him, with the economic
ramifications foregrounded. The instinct is right and it is the
biggest usefulness upgrade on the board. It also carries the one risk
that could end the project, so the design below separates what is
safe and buildable now from what needs your signature.

THE HARD LINE, non-negotiable in any version: the instrument measures
press salience, not risk, and makes no forecasts. An assistant that
says "prices will rise" or "you should hedge" is (a) a claim the index
cannot support, (b) the end of the salience-not-risk discipline that
is the project's whole credibility, and (c) advisory territory with
regulatory weight in India. Everything below is retrieval,
description, and disclosed historical association only.

PART A, EXPOSURE LAYER (buildable now, no construct change, needs
only your sector list). A registered sectors.json mapping Indian
export/import sectors to the channels that touch them, built with the
same discipline as dictionaries.json: ex-ante, versioned, per-sector
rationale, append-only changelog. Draft starting set, edit freely:
textiles and apparel (shipping, us_trade), gems and jewellery
(shipping, gulf_energy), pharmaceuticals (us_trade, shipping),
IT services (us_trade), auto components (us_trade, shipping),
agriculture and food (shipping, gulf_energy), energy-intensive
manufacturing (gulf_energy), chemicals (gulf_energy, shipping),
defence and aerospace (pakistan_west, china_east), electronics
(china_east, us_trade). Each sector gets a page: which channels touch
it and why, today's readings for those channels, the receipts behind
them, corridor transit data where relevant (PortWatch), and the
market echo already computed. Zero new claims; it is a re-cut of
published data by the reader's own frame.

PART B, THE ASSISTANT (this is memo 0.10 option c, still unapproved).
A question box that answers ONLY from published payloads, always with
citations, and refuses to forecast by construction: same prompt
registration and measurement-language lint as the daily brief, plus
hard refusal on any request for prediction, advice, or price
direction. Cost with a spend cap: perhaps 10-40 dollars a month
depending on traffic, and it needs a small backend (the VPS can host
it). It should ship only AFTER Part A, because Part A is what gives
it something honest to say.

WHAT IT DOES FOR THE PROJECT: this is what makes practitioners use
the thing weekly instead of admiring it once. Usage generates the
feedback that has been worth more than any feature (FICCI proved it).
Revenue is NOT the reason to build it now, and the open core must
stay free forever; if a paid tier ever exists it is alerts, API
volume, and custom sector dashboards, never the index itself.

Reply "approve exposure layer" (Part A alone, recommended now) or
"approve exposure layer and assistant" (both), and edit the sector
list however you like first; your list is the registration.

### 0.13 APPROVED AND EXPANDED in chat 2026-08-05 ("execute all, make this max")

The exposure program is a build order now; the architecture from the
brainstorm is the spec. What the founder approved: exposure as a
DERIVED object (trade flows to corridors to channels to measured
sensitivity), three doors (sector tap, sentence extraction, HS codes),
profiles in the URL with no accounts, measured sectoral sensitivities
from NSE indices (feasibility verified 2026-08-05: 13-19 years of
daily data per sector, free), the macro transmission table, per-sector
feeds, the reverse lens, personalized analogues, computation shown on
every personalized page, alerts later on the VPS, API via V13. Core
free forever; no logins; no forecasts anywhere, enforced by the same
lint discipline as the briefs.

Still yours, two items:
1. sectors.json first registration: the ten-sector draft in 0.13 above
   plus per-sector corridor rationale ships as DRAFT v0.9 for your
   edit; reply "freeze sectors" (with any edits) and it registers as
   v1.0.0.
2. WhatsApp Channel for the daily brief: only you can create it (your
   WhatsApp, Updates tab > Channels > Create). Say the word when made
   and the crews wire the daily post into your review flow; nothing
   posts without your tap in August.

## 0.14 Tranche-2 validation episodes — YOUR SIGNATURE NEEDED (MI4)

`validation/validation_episodes_tranche2_DRAFT.json` holds 8 new candidate
episodes (2 pakistan_west, 4 gulf_energy, 2 us_trade — exactly the thin
channels), drafted blind from external chronology without consulting the
series, with ex-ante criteria and recorded exclusions. NO hit-rate has been
or will be computed until you sign. To sign: say "sign tranche 2" (or move
the entries into validation_episodes.json yourself in a dated commit).
If any date or event looks wrong to you, strike it before signing —
striking candidates before grading is exactly what the process is for.
Also registered there: the out-of-sample rule (future episodes registered
within 7 days of occurrence, graded mechanically at +3 days).

## 0.15 Two decisions from the morning audit (2026-08-06)

**A. The 06:00 morning contract is structurally unmeetable right now.**
The measured day closes 05:30 IST; the heal then needs ~25-30 min. Your
last three mornings published 07:03 / 10:27 / ~06:44 — honestly recorded
as late on your own reliability page. Choose one (both are honest):
  (a) restate the contract to 07:00 IST (one dated methodology line), or
  (b) approve the heal parallelization (same files, same math, ~4-6x
      faster download+parse; publish ~05:45) — specced for the crew.
Recommendation: (b), and say "parallelize the heal". Cron overlap is
already fixed (flock) either way.

**B. china_east splice ratio predates the v1.2.0 amendment.** Detail in
analysis/reviewer_audit_2026-08-06.md item 5. One sentence added to the
methodology splice note would fully disclose it; say "disclose the
china_east ratio" and it ships. Read Aug 5's china_east 4.5 with this
in mind (the crash itself is real: Aug 4/Aug 5 bands do not overlap).

## 0.16 UCDP V10 — context live; the construct decision is yours

UCDP monthly context is published (ucdp_context.json, 2017-present,
candidate months flagged preliminary; Pahalgam/Sindoor months visibly
spike — the lane face-checks). What remains founder-gated before UCDP
can be SCORED against channels: (a) corridor mapping — which UCDP
events count toward pakistan_west vs china_east (by dyad? by state
geography? Kashmir insurgency events are the hard call); (b) the
outcome variable (events? deaths_best? binary violent-month?); (c) the
comparison design (does a salience episode within ±k days of recorded
violence count as corroboration?). Say "draft the V10 registration"
and a signed-before-scored draft lands like tranche 2 did.

## 0.17 China V8 monitor — registered; dictionaries will come for signature

Your "add china to v8" is registered (monitor, not comparator — the
control group stays clean). The V8 night will produce five draft China
channel dictionaries with per-term rationales; nothing is fetched until
you sign them, same as India's own registration discipline.

## 0.18 Your two ideas from today, registered

**A. Machine BS-filter (your framing: "let me do the heavy lifting, but
a child could kill the rainfall stories").** Building as the approved
aptness classifier: Haiku labels receipts articles ON/OFF under the
registered rubric; the page collapses OFF with a visible count (never
silent deletion); your taps become the audit of the machine
(agreement published); scores untouched. No action needed from you —
except taps remain the calibration gold standard.

**B. India Domestic Monitor (states + investment salience).** Registered
as a post-Aug-15 second instrument on the V8 monitors-as-config chassis:
state-level configs with their own ex-ante dictionaries (policy,
investment, FDI-attention channels), same validation discipline. Say
"prioritize domestic" if you want it ahead of V15-V21.

## 0.19 V11 forecast registration — YOUR SIGNATURE STARTS THE CLOCK

validation/forecast_registration_DRAFT.json: weekly mechanical spike
questions per channel, dumb-baseline vs salience-informed arms, Brier
scoring, ex-ante V12 fork criterion (beat climatology by 5% relative,
26+ weeks, or the negative result publishes prominently). The whole
point is elapsed time — every unsigned day is a week of evidence the
Aug 15 page cannot show accruing. Say "sign the forecast registration"
and question generation ships the same day, clearly separated on a
research page that presumes the null.

## 0.20 China V8 dictionaries — DRAFTED FOR YOUR SIGNATURE

countries/china_DRAFT.json: five channels from China's own exposure
(Taiwan Strait, South China Sea, US tech & trade, India border — the
deliberate mirror of our china_east — and energy/supply lanes), every
term with a rationale, ex-ante rule enforced. Strike anything, then say
"sign china" and the V8 template build begins. Nothing fetches unsigned.

## 0.22 The code license — RESOLVED 2026-08-06 (MIT shipped)

The repo declares the DATA as CC BY 4.0 everywhere, but the CODE
carries no license file at all, which legally means all-rights-
reserved — a replicator running scripts/reproduce.sh is technically
infringing. This is a founder decision because it changes what the
project legally is. Recommendation: MIT for code (research-standard,
maximally reusable, keeps attribution), CC BY 4.0 stays for data.
RESOLVED: the codebook was already publicly promising "code MIT", so
the LICENSE file (MIT, your copyright) shipped 2026-08-06 under your
"do everything" — the published claim is now true. Data stays CC BY
4.0. If you ever want a different code license, that is a new dated
decision.

## 0.21 Alerts/webhook design — DRAFTED FOR YOUR SIGNATURE (V13)

design/alerts_webhook.md: three trigger conditions computed only from
already-published payloads — T1 band-separated daily move (the exact
arithmetic that caught the china_east crash), T2 composite 90th-
percentile crossing that survives its band, T3 integrity failures
(missed morning contract, audit red) alerting the same channel as
everything else. Delivery is phased: alerts.json static payload first
(free, CSP-safe, triggers earn trust in production before anyone
builds push), HMAC-signed webhooks from the VPS second, and NO email
tier — that collides with "one email a week" and is left as an open
question, not a design. Thresholds become registered parameters the
moment you sign; after that, changing one is an append-only amendment
like a dictionary edit. Say "sign alerts" and src/alerts.py ships with
its trigger tests the same day. Beside it, countries/RECIPE.md now
documents the full new-country process (the China playbook, written
down: draft → rationales → exclusions → your signature → calibrate →
identical transform → tests → publish with honesty surfaces on day
one) — that plus the recipe closes V13's design surface; the
pip-installable package restructure waits for a quiet slot because it
moves module paths that live cron lanes are executing tonight.
