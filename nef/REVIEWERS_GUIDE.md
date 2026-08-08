# IGRM — a guide for the NEF methodological review

*Written by the author for the NEF research team's 30-day review
(August 2026). The premise of this document: the fastest honest way to
review an instrument is to try to break it, so this guide tells you
where every claim lives, how to check each one independently, and
where the known soft spots are — before you find them.*

## What IGRM claims, and where each claim is checkable

| Claim | Where it is made | How to check it independently |
|---|---|---|
| The index measures press salience, not risk | every page footer, methodology §1 | The banned-language lint (no forecast verbs anywhere) is enforced in CI; grep the repo |
| Dictionaries are registered, ex-ante, never event-chasing | methodology changelog | `dictionaries.json` per-term rationales + dated append-only amendments in git history |
| The index detects real episodes it was never told about | validation.html, hit-rate 18/21 | `validation/validation_episodes.json` was frozen 2026-07-24 (commit history proves date); event names never appear in query terms |
| The placebo diagnostic is unfavorable | validation.html | 52 of 115 placebo episodes overlap registered-episode days (45.2%), versus about 35.6% under duration-preserving random placement; inspect the placebo payload and rerun the documented command |
| External human accuracy evidence is incomplete | validation.html; `validation/blind_audit_500/` | Precision v2 was invalidated before coding after source-frame and estimand defects were found; no v3 is frozen and no v2 label or result exists |
| Results are not an artifact of one term list | validation.html robustness | correlations AND the weekly overlay chart; the weak case (gulf narrow 0.527) is discussed by name on the page |
| Recent daily scores carry quantified sampling noise | index chart band, uncertainty.json | Wilson-interval construction documented in the codebook; every published point sits inside its own band (checkable in one script) |
| Every number has receipts | receipts.html | most receipt articles are drawn from the same sampled corpus the score was computed over ("in scored sample" label) — the estimator's own evidence, enumerated |
| The site publishes on time or admits it didn't | data.html reliability record | scored from git commit timestamps, not self-reporting; misses are permanent |
| Machine consumers get stability promises | api.html | frozen contract v1.3.0, 30 endpoints; CI test fails if a served payload leaves the contract |

## Known limitations, stated by the author first

1. **The gulf & energy channel is term-dependent at the narrow margin**
   (0.527 vs the narrow variant). The channel deliberately composites
   conflict-proximity and energy-supply vocabularies; cut to the
   conflict core it is a different series. Treat single-day moves in
   this channel with caution; the validation page says the same thing
   publicly.
2. **Machine precision on two channels was poor before the 2026-08-05
   dictionary amendment** (us_trade 0.0, china_east 0.167 on labeled
   samples — published as found in precision.json). The amendment
   removed both leak classes (weather/monsoon contamination; sidebar
   boilerplate); post-amendment precision will publish as it
   accumulates. Author-machine agreement on the calibration overlap is
   currently 0.875 with n=16 author labels against a registered
   threshold of 100 — the precision series is flagged UNCALIBRATED on
   the site until that threshold is met.
3. **The external precision study has no result.** V2 is reproducible as a
   frozen artifact but invalid as a production-frame precision study: one
   registered source day omitted 5,386 production documents, and its
   unique-document frame did not match the score's group-contribution
   numerator. It was invalidated before any label; do not field or score it.
4. **The 2026 source switch is spliced.** GDELT's maintainer directed
   this project from the DOC API to the ngrams dataset; series levels
   are ratio-linked over an overlap window (calibration file published,
   log-sd per channel). Two channels' ratios rest on 1 overlap day —
   thin, disclosed, and improving as overlap accumulates.
5. **Sampling design changed variance.** Ngrams-era scores are
   estimated from ~30k-document daily samples; that is exactly why the
   sampling bands exist and why they do not extend to API-era days.
6. **Sub-national event geography has vintage gaps.** GDELT's FIPS
   coding predates Telangana and Ladakh; their events count under
   parent codes, the maps page hover says so per state.
7. **Coverage drift diagnostics are being recomputed** against the
   amended dictionaries (drift mode exists in `src/validate.py`; the
   payload publishes under `validation.json → drift`). If the field is
   absent when you read this, a CI test is failing loudly about it —
   that test exists precisely so a promised statistic cannot silently
   not exist.

## How to reproduce the index

```
git clone https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor
cd india-geopolitical-risk-monitor && pip install -r requirements.txt
python -m pytest            # the full test suite, including honesty guards
python -m src.run_daily     # rebuild today from the committed raw stores
```

Every payload the site serves is a committed file; the site fetches
nothing at read time from anywhere but its own origin (strict CSP,
self-hosted everything).

## What the author asks of the review

Scrutiny, in writing, on the record. Anything you break goes into the
public corrections ledger (igrm.in/corrections.html) with a dated
entry; anything you cannot break you can cite. Questions and findings:
ishankrishna9@gmail.com.
