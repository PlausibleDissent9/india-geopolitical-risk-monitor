# IGRM prose-number audit — origin/main @ 88b9cbc947c0e9884dc22aff6f6a2bd2fdb9c467

Audited 2026-08-08 against a clean `git archive origin/main` extract. Every countable claim on
index / validation / methodology / history / data / break / start / codebook / corrections /
status pages plus `negative_results.json` strings, checked against the committed payload that is
its source of truth. `&nbsp;` entities normalized before matching. Recomputation used the
committed payloads only; where a figure had no payload field it was recomputed from committed
inputs or flagged. Line numbers refer to the committed files.

**Headline: 4 of 5 tests in `tests/test_data_contract_disclosures.py` FAIL on origin/main**
(KeyError on fields the codebook still documents). The repo's own falsification page
(break.html item 4) dares readers to "find one page-claimed number absent from its payload
(CI enforces this)" — there are four live schema absences, each pinned by a committed red test.

---

## TRUE — recomputed, matches (87 claims)

### index.html
- :89-91 composite7 61.5 on 2026-08-06, ▼ −4.7 vs yesterday → history.json `/composite7` (61.5, 66.2 on 08-05). Exact.
- :100-104 five SSR component rows 65.1/−25.1, 5.3/+0.8, 77.7/−0.8, 15.6/−20.0, 80.9/−2.3 → latest.json `/channels/*/score` + history.json day-over-day. All exact.
- :110 "AI-GPR India · ρ 0.256" → ai_gpr_benchmark.json `/primary/rho` = 0.256.
- :111 "Seven published divergences" → divergence_register.json `/entries` len 7 (5 ai_gpr + 2 physical-flow).
- :112 "1979–2019 proxy" → back_extension.json `/series/*/months` 1979-01..2019-12.
- :137-139 "~30,000-article daily sample" → data/raw/ngram_days/*.json `n_docs_sampled` 28,267–35,423 (48 samples/day).
- :76-79 hero facts (2017–present; five channels; 730 days; CC BY 4.0) → history.json (first date 2017-06-29, 5 channels), payload `_meta` license.
- :153 episode rule "90-day mean + two standard deviations" → matches codebook/src convention (2σ/90d, lagged baseline).
- :23 JSON-LD "five channels … since 2017"; temporalCoverage 2017-01-01 → shares.csv and data/raw/gdelt_volume.csv start 2017-01-01. Note: the two named distributions (history.csv/json) start 2017-06-29 (180-obs minimum); defensible, not exact.

### validation.html
- :46-51 24 of 29 / 19 of 29 / ≈6.8 of 29 / 26 of 29 (written with `&nbsp;`) → detection_baselines.json `/hit_rate_context` {24, 19, 6.8, 26, n_events 29}. All four exact. window ±3 ✓.
- :55 "trailing 90-day mean + 2σ" ✓.
- :92 gulf narrow 0.527 → validation.json `/robustness/narrow/gulf_energy`. "lowest number on this page" — see WRONG-minor below.
- :93-97 "keeps only four of the channel's eleven registered phrases (Strait of Hormuz, Israel–Iran, Gulf tensions, one supply-disruption phrasing)" → dictionaries.json gulf_energy 11 terms; dictionaries_alt.json narrow = exactly those 4. Dropped-list names all verified dropped.
- :100 composite "vs narrow 0.796, vs broad 0.880" → validation.json `/robustness/{narrow,broad}/composite` 0.796/0.88.
- :81-82 "2022–present overlap" → robustness_series.json `_meta.window` [2022-01-01, 2026-07-31]. Loose "present" (ends 7 days before generation) but variants exist from 2022 ✓.

### methodology.html
- :42-43 "110 months shared" → gpr_comparison.json `/series/*/months` = 110.
- :44-46 rho 0.256 in 106 changes, CI [0.050, 0.407] → ai_gpr_benchmark.json `/sample/n_changes` 106, `/primary/moving_block_bootstrap_95_ci/6`.
- :61 "Channels hold 10-14 terms" → dictionaries.json 14/10/11/12/10.
- :84-89 "Russian oil" in us_trade ✓; "No term appears in two channels" ✓ (zero duplicates across all 5 term sets).
- :126-173 splice audit table: 1.9547(5)→2.4634(18) +26.0% 0.3296; 3.3612(5)→2.6998(18) −19.7% 0.3954; 1.7910(5)→1.8098(18) +1.0% 0.0976; us_trade 2.5616(1); shipping 2.9747(1) → splice_sensitivity.json `/calibration_audit/*`. All exact.
- :123-125 "recovered window 2026-06-30 to 2026-07-21 … 18 independent days" → analysis/splice_overlap_api_091c25e.csv (18 rows, those dates); `independent_n` 18. Commit `091c25e` exists.
- :178-180 "Pakistan moves down 8.0, China up 5.1" → `/summary/daily/{pakistan_west,china_east}/latest_shift` −7.99, 5.05.
- :186-253 sensitivity table (8 rows) → `/summary/{daily,trailing_7_day}` all match to display rounding (6.59→6.6 … 25.63→25.6, 23.52→+23.5).
- :255-256 "37 mechanically bridged days from 2026-07-01 to 2026-08-06" → `/dates` len 37, `affected_start/end`.
- :274-284 saturation: 2.2 points (97.8–100.0), share 5.5-fold (0.214%→1.173%) → history.json pctl window min/max 97.8/100.0; shares.csv window min/max 0.2142/1.1727 (×5.47). Exact.
- :390-408 §8a: 18 of 21 (86%) tranche 1; 6 of 8 tranche 2; combined 24 of 29 (83%); 13+8=21 registered at/after freeze; episodes 2017-2025 (tranche-1 dates 2017-06-16..2025-08-06); the two tranche-2 misses are BrahMos and OPEC+ → validation.json `/hit_rate/episodes` by `tranche`. All exact.
- :431-463 §9: 2 of 29 (hit rate) → stress_gauge.json `/validation`; weights 0.35/0.25/0.25/0.15 → validation/stress_gauge_weights.json; rule "gauge ≥ 90 within 3 days" ✓.
- :465-473 §10 "ten structural phrases" → comparators.json `shared_terms` len 10.
- :481-482 "events leading salience the only near-threshold direction" ✓ directionally (see STALE #3-4 for the p-values).
- :523-538 changelog v1.11.0: 106 changes; CI [0.050,0.407]; 12-month [0.082,0.364]; "five largest benchmark rank gaps and two salience-versus-physical-flow gaps" (5+2 = register's 7); commit `58ca6c0` exists.
- :567-604 v1.10.0: 3,394 overlapping days ✓ (in wiki_hindi.json); changes correlations 0.223/0.340/0.589/0.117/0.564 (EN) vs 0.160/0.132/0.163/0.050/0.030 (HI) → exact (0.2233…0.0296); us_trade −0.136 the only negative level ✓; six of twenty-nine unresolved (29 registered − 23 resolved) with the six named topics ✓; pw 6/6, ce 5/5, others 4/6 ("lose a third") ✓; traffic medians 602 / 161 present in payload ✓.
- :609-611 v1.9.0 "21 known missing days" → shares.json `_meta.known_gaps` len 21.
- :628-644 v1.8.0: china_east 33.5→74.3→4.5 on 2026-08-03..05 with shares 0.0134%/0.0232%/0.0070%, two-year median 0.0165% → history.json + shares.csv, exact (median recomputed 0.0165). "99.5 the morning after Pahalgam" → channels7.pakistan_west on 2025-04-23 = 99.5, exact. "96–98 through Article 370" → pw7 97.4–98.6 across 2019-08-05..12; approximately right, top of range is 98.6 not 98.
- :677-680 v1.6.0: 16 rulings toward n=100, agreement 0.875 → precision.json {author_labels_n 16, calibration_threshold 100, agreement 0.875 on n=16}.
- :722-737 v1.1.0 chokepoints Hormuz 5 / Bab el-Mandeb 5 / Suez 3 / Malacca 3 → dictionaries.json shipping.chokepoints. Exact.
- :738-754 v1.0.1 ratios 1.95/3.36/1.79/2.56/2.97 with log-sd 0.38/0.46/0.15 → shares.json splice block (1.9547/0.3819, 3.3612/0.456, 1.791/0.1475). Exact to stated precision.
- :769-781 v1.1.0-dev "4 cells now flag significant" → event_study.json currently 4 of 90 BH-flagged cells; still true.
- :782-787 v1.0.0 frozen parameters (730/180/2σ/90-day/3-day/1-5-20/1,000 resamples) → consistent everywhere checked.

### history.html
- "forty-one years" (1979–2019) ✓; series begins **December 1983** → first non-null `pctl_10y` month = 1983-12, exact; **28-month hole Feb 2015–May 2017** → exactly 28 null months 2015-02..2017-05.
- :56-58 thresholds stated correctly: r ≥ 0.6 publishes clean, below 0.4 does not publish, over 36 months → analysis/back_extension_memo.md:85-88 + overlap_audit months=36. (This page gets right what negative_results gets wrong.)
- Two channels cleared (0.893, 0.848) and two withheld (0.216, 0.153) ✓.
- "eight of the nine" anchors chartable (the ninth is us_trade, no series) ✓; "Six cleared it; three did not" → 6 of 9 `top_decile` ✓; misses 52.3 / 54.8 / 89.1 ✓; Mumbai "missed by roughly one percentile point" (90 − 89.1) ✓.

### data.html
- "five endpoints … quick-start set" → table has exactly 5 rows.
- "frozen v2 API contract" → api_contract.json `_meta.contract_version` 2.1.0.
- "6:00 AM IST (00:30 UTC)" ✓ arithmetic.
- stress_gauge row "published 2/29 hit rate, and a 365-day history" → validation 2/29; history_365d has 365 entries.
- ai_gpr row "five largest divergences" → `largest_rank_divergences` len 5.

### break.html / start.html / status.html / corrections.html
- start.html "Six ways to falsify" → break.html has exactly 6 falsify blocks.
- status.html "scored … since 2026-08-02" → reliability.json first contract day 2026-08-02.
- corrections.html: all dated ledger entries left as history per doctrine; "1 of 21" entry protected by test_page_claims_match_payloads.py::test_the_gauge_number_in_the_ledger_is_left_alone ✓; the 2026-08-07 entry's +26.0%/−19.7%/+1.0% match the audit payload ✓.

### docs/data/negative_results.json (readings/findings)
- #1 "2 of 29 (hit rate 0.069) vs 24 of 29" → stress_gauge + validation, exact; "a twelfth" = 2/24 ✓.
- #2 "52 of 115 (45.2%)" → validation.json `/placebo`, exact. "**chance ~35.6%**" → in NO payload field; recomputed from committed validation.json placebo episodes + episodes.json under random placement over the 2022-05-15..2026-06-20 span: expected 40.9/115 = **35.6%** exactly (geo-day coverage 27.8%, matching the referee report). Number TRUE; source-of-truth gap flagged under UNVERIFIABLE.
- #3 "naive 26 of 29 vs registered 24 of 29; chance 6.8" → detection_baselines.json, exact.
- #4 "5 of 5 channels, both levels and changes, none in the other direction" → wiki_hindi.json, recomputed 5/5 levels and 5/5 changes.
- #5 r=0.153 / r=0.216 values → back_extension.json overlap_audit, exact (the "floor of 0.6" clause is WRONG #1).
- #6 "(2026-08-06, 39 cells) NO cell survived" → verbatim from sector_sensitivity.json `_meta.multiple_comparisons`; recomputed 39 cells, 0 with `bh_significant_10pct`.
- #7 "largest association at lag −8" → priced_risk.json `lead_lag.reading` verbatim; recomputed max |corr| over ccf (21 lags) is at −8 (0.0588).
- #8 "16 of 100; 0.875 on n=16" → precision.json, exact.
- #9 "25.63 points" → splice_sensitivity.json `/summary/trailing_7_day/china_east/maximum_absolute_shift`, exact.
- `_meta.n_findings` 9 = findings length ✓.

### codebook.html
- :715 "19,830 of 19,830 published values exactly" → replication.json `best` {19830, 19830, agreement 1.0}.
- :1035 "10 of 12 vintages" → vintages.json `_meta` {n_vintages_clean 10, n_vintages 12}; "(101 values across 17 days, max 99.4)" matches the larger 2026-07-27 vintage row (the other revised vintage is 50/17/52.7 — the parenthetical describes one of the two, note only).
- :1059 "521 of 523 analysed episodes" → detector_blindness.json `_meta`, exact; "2,158 distinct channel-days, 12.4%" → 2158; recomputed base 3,484 share-days × 5 = 17,420 → 12.39% ✓; "median multiple ~1.4" ✓.
- :1063-1068 worked example 0.0244 (2025-04-21), 0.6912 (2025-07-20), 28× (=28.3), 0.1340 (2025-05-20), "five and a half times" (5.49) → all present in payload, arithmetic checks.
- :1093-1102 3,394 days; 5 of 5; correlation lists; −0.136; traffic ordering → wiki_hindi.json ✓ (`channels_where_english_leads_on_both` = all five).
- :1103 "Six registered articles have no Hindi counterpart" → 29 − 23 ✓.
- :1122 "2025-06 has 14 of 30 days" → monthly.json {n_days_present 14, n_days_expected 30} ✓; 80% floor ✓; "2026-06 is the first such [mixed] month" ✓ (only mixed row).
- :977-980 "doc_api (3,446 days) … ngram_bridge (38 days, 2026-06-30 onward)" → shares.csv source column counts 3446/38, first bridge day 2026-06-30. Exact.
- :993-1000 syndication: 160 articles / 46 stories ×3.478 (pw 2026-08-05); 17/17 ×1.000 (ce); 1.923 @ 28,575 vs 3.478 @ 119,349; ≥60,000 floor → syndication.json series + `_meta.known_bias` + `min_docs_for_history` 60000. All exact.
- :895 "fifteen per-sector feeds" → 15 sector_*.json files (excl. sector_sensitivity).
- :1012 "status.json watches ten upstream sources" → status.json sources len 10.
- :755 predictability "300 draws" → `_meta.permutations` 300.
- :270 "CI from 1,000 episode resamples" ✓ (consistent with §6).
- :667 receipts "up to 150 publish per channel" → observed per-channel counts 14–150, none above 150 ✓ (this is the current truth §11 of the methodology contradicts — see STALE #2).
- :139-144 ai_gpr_benchmark stamped-meta exception documented ✓ (and it is indeed unstamped).
- quick-start "five lines" → 5 numbered commands ✓.

**Universal-stamp sweep** (the "every payload carries X" class, iterated over ALL 74 docs/data/*.json, no sampling): 70 dict payloads carry license+citation+codebook+source; episodes.json and notes.json are bare arrays (documented exception); ai_gpr_benchmark.json unstamped (documented exception); **api_contract.json unstamped and NOT documented as an exception** → WRONG #8.

---

## STALE — payload moved, prose didn't (8)

1. **methodology.html:80-83** — "Three generic phrases are accepted … `"energy security"` and `"maritime security"` … and `"Suez Canal"`." `"maritime security"` was dropped from shipping in the 2026-08-05 precision amendment (documented in this page's own changelog, :755-768). Payload: dictionaries.json `/shipping/terms` — no such term. Prose says 3 accepted generic phrases; the dictionary now carries 2 of them.
2. **methodology.html:485-492 (§11)** — receipts described as "GDELT `mode=artlist`, capped at 25 per channel." Superseded by v1.6.0 corpus receipts (three lanes, cap 150). Payload: receipts.json — per-channel published articles 14/56/83/150/150; artlist lane alone is ≤25. §11 body never rewritten after its own changelog entry.
3. **methodology.html:479** — "p 0.37 to 0.82" for the three salience-leads pairs. Payload: predictability.json `/pairs/*/p_permutation` = 0.399 / 0.661 / 0.817 → range 0.40–0.82. Permutation p-values regenerate nightly; the prose is hand-typed.
4. **methodology.html:480** — "events leading salience (p 0.053)". Payload: `/pairs/events_leads_salience/p_permutation` = 0.05.
5. **data.html:154-164** — citation and BibTeX say "**Version 1.0.1**". CITATION.cff and methodology.html:31 are at **1.11.0** (test_citation.py pins those two to each other but not this page). The downloadable igrm.bib also disagrees with the on-page BibTeX (different title, no version). Every reader who copies the on-page citation stamps a version ten minors old.
6. **break.html:66** — "pre-registered episode list (n=21)". Payload: validation/validation_episodes.json has **29** episodes (tranche 2 signed 2026-08-06); validation.json `/hit_rate/overall/n` = 29.
7. **codebook.html:1012-1013** — "this watches all ~66 payloads". Payload: freshness.json currently lists **76**.
8. **negative_results.json `_meta.why`** (and src/negative_results.py:3) — "scattered across seven payloads". The file's own findings cite **9** distinct source payloads. Hand-typed in the generator's docstring/meta; two findings were added and the "seven" wasn't.

Historical/dated (left alone per doctrine, noted): methodology v1.5.0 "27 endpoints" (contract now 78 under v2.1.0); codebook :146 "three payloads out of sixty-four" (now 74 json files); corrections ledger entries; §8a "18 of 21 (86%) on first run" is explicitly a first-run record.

---

## WRONG — never matched, or contradicts the committed payload beside it (10)

1. **negative_results.json findings[4]** — "gulf_energy r=0.153, us_trade r=0.216 **against a registered floor of 0.6**". The registration (analysis/back_extension_memo.md:85-88) is: r ≥ 0.6 tracks; 0.4–0.6 publishable with caveat; **< 0.4 does not publish**. The withholding floor is 0.4, not 0.6 — a channel at 0.5 would have published. history.html:56-58 states the two-threshold rule correctly, so the site contradicts itself. Hand-typed at src/negative_results.py:88.
2. **negative_results.json `_meta.what`** — "Read live from those payloads at build time, **never hand-typed**, so a row that stops being true stops being published." Three constants in the register are hand-typed in src/negative_results.py: "vs 24 of 29" (:41), "~35.6%" (:54), "floor of 0.6" (:88) — the third is wrong today. The register's warrant is its generation discipline; the claim of that discipline is false as shipped.
3. **codebook.html:126-129 & :282-284** — "`available_outcomes` and `unavailable_outcomes` in the JSON disclose what the current source cache actually supports … At the 2026-08-07 audit, Brent was unavailable and therefore correctly belongs in `unavailable_outcomes`, not in the published result grid." Payload: event_study.json (generated 2026-08-07T16:53Z) has **neither field**, and `brent_ret` **is in the grid** with populated cells (n=86–114) in both JSON and CSV. Pinned by test_data_contract_disclosures.py::test_event_study_lists_unavailable_outcomes_instead_of_null_grid — **which fails on origin/main**.
4. **methodology.html:334-336** — same claim ("the JSON explicitly lists available and unavailable outcomes"). Same absent fields.
5. **codebook.html:1059-1062** — "The payload's `excluded_episodes` lists any detected episode the diagnostic cannot evaluate … the current one-row exclusion is caused by an absent pre-episode source day." Payload: detector_blindness.json has **no** `excluded_episodes` / `n_episodes_excluded`. The exclusion is real (523 analysed vs 524 in episodes.csv) and now undocumented in the payload. Pinned by ::test_detector_diagnostic_accounts_for_every_detected_episode — **fails on origin/main**.
6. **codebook.html:1136-1139** — "`n_days_composite_present` and `composite_coverage` separately report … a monthly composite below the same 80% floor is null with a `composite_refused_reason`." Payload: monthly.json rows carry **none of the three fields**. Pinned by ::test_monthly_json_uses_null_and_separate_composite_coverage — **fails on origin/main**.
7. **codebook.html:802-803** — "`_meta.available_days` and `complete_window` disclose whether all seven cache days exist." Payload: receipts_archive.json `_meta` has only {days, per_day_cap, …} — **no** available_days/complete_window/target_days. Pinned by ::test_receipts_archive_never_promises_missing_days — **fails on origin/main**.
8. **codebook.html:131-134** — "**Every** dict-shaped JSON published by the pipeline embeds a `_meta` object (what, **license, citation, codebook link, source URL**, generation date)." Counterexample by full iteration: api_contract.json lacks all four universal fields and is not among the three stated exceptions. (Defense available — "published by the pipeline", and src/stamp_meta.py:51 deliberately SKIPs it — but the codebook states the other exceptions and not this one. This is the exact "licence in every payload" failure class recurring.)
9. **codebook.html:933** (and back_extension.json `_meta.what`) — "The historical attention proxy, **1979–2016**". The payload's own series runs 1979-01..**2019-12** (492 months), and history.html/index.html say 1979–2019. Two committed descriptions of the same payload disagree; the data supports 2019.
10. **validation.html:91-92** (minor) — 0.527 called "the lowest number on this page." The page's cross-source table renders −0.02 (pakistan_west) and 0.043 (us_trade) from validation.json `/cross_source/per_channel`. False under a literal reading; intended scope was the robustness table.

---

## UNVERIFIABLE — no committed source of truth (3)

1. **methodology.html:103-104** — query-length limit "(measured ~250 characters)". No committed measurement artifact; the operational constant is `QUERY_MAX_CHARS = 230` (src/fetch_gdelt.py:41). The 250-vs-230 relationship (measured limit vs safety margin) is stated nowhere. Every such sentence is a future stale claim.
2. **break.html:50-51** — reproduce.sh "(~5 minutes, no credentials)". No committed timing record; drifts silently as the pipeline grows.
3. **negative_results.json findings[1]** — "~35.6%" chance rate: recomputes exactly (see TRUE), but exists in **no payload field**; the row cites data/validation.json, which does not contain it, and detection_baselines.json — its natural home, which publishes the other chance rate — omits it. A reader cannot check the register's second-most-quoted number without rebuilding the simulation.

---

## (a) Count per classification

| Classification | Count |
|---|---|
| TRUE (recomputed, matches) | 87 |
| STALE (payload moved, prose didn't) | 8 |
| WRONG (never matched / contradicts committed payload) | 10 |
| UNVERIFIABLE (no committed source of truth) | 3 |
| Dated ledger entries (exempt by doctrine, verified unaltered) | 12 |

Counted at the granularity of an individually checkable number or field claim; multi-number
tables counted per row.

## (b) Ten most reader-damaging discrepancies, ranked

1. **origin/main fails its own disclosure tests** — 4 of 5 tests in tests/test_data_contract_disclosures.py KeyError on committed payloads (event_study, detector_blindness, monthly, receipts_archive). Every schema promise in those codebook sections is currently false, while break.html item 4 tells readers CI enforces the opposite.
2. **Brent in the grid the docs say excludes it** (codebook :282-284, methodology :334-336). A reader pooling "available" outcomes inherits 6 extra cells (2 outcomes × 3 windows are descriptive; brent alone adds up to 15 channel-cells) the documentation says aren't published.
3. **"registered floor of 0.6"** in negative_results — misstates the pre-registration in the project's honesty showcase; contradicted by history.html on the same site. A referee who reads the memo catches it in one minute.
4. **"never hand-typed"** in negative_results `_meta` — the register's entire epistemic warrant, falsified by three hand-typed constants in its own generator, one of them (the 0.6) wrong right now.
5. **data.html citation "Version 1.0.1"** — propagates into other people's bibliographies (the one place errors can't be fixed later); ten minor versions stale and inconsistent with the igrm.bib download beside it.
6. **break.html "n=21"** — the falsification invitation understates the registered evidence base by 8 episodes; an adversarial reader who counts the file concludes the invitation itself is stale.
7. **methodology §11 "capped at 25 per channel"** — misdescribes the current receipts product by 6× and names the wrong mechanism (artlist vs corpus lanes); §11 is the page cited whenever a receipt is quoted.
8. **methodology §2 "maritime security" as an accepted generic phrase** — contradicted by the same page's changelog and the frozen dictionary; undermines the "the dictionary file, not this page, is the term-level record" discipline.
9. **detector_blindness `excluded_episodes` gone** — exactly one detected episode is unaccounted for (523/524) and the payload no longer says which or why; the codebook says it does.
10. **predictability p-values (0.37→0.399, 0.053→0.05)** — headline negative-result numbers that regenerate nightly, hand-typed into §10; today's drift is cosmetic, tomorrow's need not be.

Honourable mentions: "~66 payloads" (76); "seven payloads" (9); "1979–2016" vs the payload's own 2019-12 series end; "lowest number on this page".

## (c) Test-gap list

| Discrepancy | Test that SHOULD catch it |
|---|---|
| event_study available/unavailable fields + Brent (W3, W4) | **EXISTS AND IS RED**: tests/test_data_contract_disclosures.py::test_event_study_lists_unavailable_outcomes_instead_of_null_grid. Gap is enforcement: payload-publishing lanes commit without gating on this suite. |
| detector_blindness excluded_episodes (W5) | **EXISTS AND IS RED**: ::test_detector_diagnostic_accounts_for_every_detected_episode. Same enforcement gap. |
| monthly composite-coverage fields (W6) | **EXISTS AND IS RED**: ::test_monthly_json_uses_null_and_separate_composite_coverage. Same. |
| receipts_archive available_days/complete_window (W7) | **EXISTS AND IS RED**: ::test_receipts_archive_never_promises_missing_days. Same. |
| "maritime security" in §2 (S1) | none exists — test_dictionaries.py checks banned event names, not page/dictionary agreement. Natural home: test_page_claims_match_payloads.py asserting every §2-named phrase is in dictionaries.json. |
| receipts "capped at 25" (S2) | none exists — test_receipts.py checks payload shape only. Belongs in test_page_claims (assert the codebook/methodology cap equals the payload's observed max/cap). |
| predictability p-values (S3, S4) | none exists — belongs in test_page_claims (format the payload p's, assert presence). |
| data.html "Version 1.0.1" (S5) | test_citation.py — covers CITATION.cff↔methodology only; extend to data.html's `#cite` block and igrm.bib. |
| break.html n=21 (S6) | none exists — one-line addition to test_page_claims against validation_episodes.json length. |
| "~66 payloads" (S7) | none exists — assert codebook count within tolerance of len(freshness payloads). |
| "seven payloads" (S8) | none exists — src/negative_results.py could compute len({r["source"]}) and refuse to hand-type; a test could grep its own docstring. |
| "floor of 0.6" (W1) | none exists — generator should read the threshold from back_extension.json `_meta`/memo instead of typing it; test asserts the register's threshold equals the registered one. |
| "never hand-typed" (W2) | none exists — a test could assert every digit-bearing token in each `number` string (minus the live-formatted parts) appears in the cited source payload. |
| api_contract missing universal fields (W8) | test_stamp_meta.py asserts the SKIP deliberately — the gap is the codebook sentence; test_page_claims could assert the codebook lists every SKIP member as an exception. |
| "1979–2016" vs series end 2019-12 (W9) | none exists — assert the codebook/back_extension `_meta` period equals `series.months[0]..months[-1]`. |
| "lowest number on this page" (W10) | not mechanically testable; rewrite the prose to scope it ("lowest robustness correlation"). |
| "~250 characters" (U1) | none exists — either publish the measurement or state the code constant (230) and test equality. |
| "~5 minutes" (U2) | none exists — record reproduce.sh wall time into a committed artifact and bound-check, or delete the number. |
| "~35.6%" homeless (U3) | none exists — publish `placebo_chance_rate` in detection_baselines.json (the module's own docstring already derives it) and make negative_results read it; test both. |

Structural note on the existing guard: test_page_claims_match_payloads.py matches with plain
spaces (`_says`). validation.html writes its hit-rate numbers with `&nbsp;`
("24&nbsp;of&nbsp;29"), which that matching style cannot see — the exact false-negative class
that bit tonight. Any extension of that test should normalize `&nbsp;`/`&thinsp;` and
`&asymp;` before matching.
