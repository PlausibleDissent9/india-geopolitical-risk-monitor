# Adding a country monitor: the documented recipe

This is the exact process the China monitor followed
(`countries/china_DRAFT.json`). It exists so that a third party — or
the author in six months — can add a country without reverse-engineering
the discipline from git history. The discipline is the product: a
monitor whose dictionary was tuned after looking at the numbers it
produces is not a measurement instrument, it is a chart that agrees
with its author.

## What a country monitor is (and is not)

A country monitor tracks salience of registered risk themes in that
country's English-language news coverage, on the same GDELT substrate
and the same share-of-corpus construction as the India channels. It is
**not** a comparator: comparators (Indonesia, Vietnam) were chosen
ex-ante for scale similarity and exogeneity to India's channels, and
adding a large, endogenous country (China, the US) to the comparator
panel would contaminate the placebo logic. A monitor stands beside the
index; it never enters any India score.

## The process, in order

Every step that fixes a measurement choice happens **before** the first
score is computed. The founder's signature is what converts a draft
into an instrument.

1. **Draft the channel roster** — 3 to 6 channels, each a named risk
   theme with a one-paragraph construct rationale. Copy the structure
   of `countries/china_DRAFT.json`: a `_meta` block (status,
   drafted-on date, signature line, splice/calibration plan) and a
   `channels` map.

2. **Draft the dictionaries with per-term rationales.** Every phrase
   carries a written reason it belongs to the construct. Rules that
   already bind the India dictionaries bind here too:
   - phrases must be specific enough that a child could not flag an
     obvious false positive (the "English Channel swimming" test);
   - anchor terms (e.g. requiring the country name in-document) are
     declared per sub-query, exactly as `dictionaries.json` does with
     its `query_grammar`;
   - no term added or removed after the first score without an
     append-only amendment entry (`amended` list with date + reason),
     mirroring the India dictionaries' `ex_ante_rule`.

3. **Write the exclusions before looking at output.** What the
   channels deliberately do not cover, and why. (China draft example:
   domestic protest coverage is excluded because the construct is
   external-facing geopolitical risk, not regime stability.)

4. **Founder review and signature.** The founder reads the rationales,
   edits or strikes terms, and signs by moving the file from
   `*_DRAFT.json` to registered status with a `frozen_on` date. Nothing
   downstream runs until this happens. An agent signing on the
   founder's behalf is fabrication of the instrument's provenance.

5. **Backfill and calibrate.** Run the standard backfill for the
   registered dictionaries. If the ngram bridge supplies part of the
   history, compute the per-channel splice calibration on the same
   window rules as India (`src/fetch_ngrams.py`), and record the ratio
   and window in the country's `_meta` before publishing any series.

6. **Transform exactly as India.** Trailing-percentile transform, same
   window length, same composite rule (envelope mean), same Wilson
   sampling bands. No per-country tuning of transform parameters —
   that is the whole point of a shared construction.

7. **Tests before publish.** Add the country to:
   - the dictionary-rules test (structure, anchors, amendment
     discipline);
   - the API contract (`scripts/generate_api_contract.py` — new
     payloads must be enumerated, and the contract version bumped);
   - the published-promises test if any page states a stat about the
     country.

8. **Publish with the honesty surfaces on day one.** Receipts lanes,
   sampling bands, and the caveat block are not later polish; a
   country page without them does not ship.

## Checklist for a pull request

- [ ] `countries/<name>.json` registered (signed, `frozen_on` set)
- [ ] per-term rationales present for every phrase
- [ ] exclusions written before first output
- [ ] splice calibration recorded in `_meta` (if bridged history)
- [ ] tests extended; contract version bumped
- [ ] no forecast or prediction language anywhere (lint enforces this)
- [ ] no change to any India series, weight, or comparator

## What gets refused

Dictionary edits justified by the numbers they produce; a country
added to the comparator panel; any channel whose construct rationale
is "coverage volume looked interesting"; publishing before signature.
These are refused because each one converts the instrument back into
an opinion.
