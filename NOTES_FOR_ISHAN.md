# Notes for the author — changes needing your words

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
