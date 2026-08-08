# IGRM registration audit — origin/main @ 88b9cbc (2026-08-07T18:35Z)

> **Superseded precision-study status, 2026-08-08:** this file is a historical
> audit of the named `origin/main` snapshot. A later source-frame audit found
> that blind-audit v2's registered 2026-08-05 receipt cache omitted 5,386
> documents present in the score-producing cache and that its unique-document
> frame was not the score's group-contribution estimand. V2 is invalid before
> coding; see `validation/blind_audit_500/V2_INVALID.md`. The byte-freeze
> findings below remain useful provenance but do not authorize fielding v2.

Method: all reads from `git show origin/main:<path>` or a `git archive origin/main` extract in scratch space. No working-tree file was read as evidence; nothing in the repo was written, staged, or checked out. Hash checks executed against real git objects in the repo (read-only plumbing: `cat-file`, `show`, `log`, `ls-tree`). The six registration-enforcement test files were run with the repo venv against the extract: **42 passed, 1 skipped** (the skip is `test_registered_inputs_match_code_and_repository`'s base-commit probe, which skips where `.git` is absent; the same check was executed manually against the repo — results below).

Verdict key: SOUND / TIME-BOMB (will break on legitimate future change) / DRIFTED (registered ≠ implemented) / UNVERIFIABLE.

---

## 1. AI-GPR preregistration — SOUND (verified now)

Registered: `analysis/ai_gpr_benchmark_registration.json` (registered_at 2026-08-07T14:43:30Z, commit 58ca6c0; results published fce2ac7, 14 min later — commit sequence A→B honored, no result in commit A).

Pins verified against immutable objects, 2026-08-08:

| Pin | Registered | Resolves to | Match |
|---|---|---|---|
| `base_commit` e075a24f7c4c...43d1 | — | `git cat-file -t` → `commit` | yes |
| `docs/data/history.csv` @ base | 79885e7bf472...4b32c | blob sha256 | exact |
| `validation/validation_episodes.json` @ base | 5730d7a8b611...f8254 | blob sha256 | exact |
| `src/ai_gpr_benchmark.py` (script freeze) | 9578f6ccdc01...21de0 | working/committed file @ origin/main | exact |
| source CSV (external) | 22750ad1e1bf...7d3e3 | = `AI_GPR_SHA256`, src/ai_gpr_benchmark.py:34 | exact |

- The re-pinned test (tests/test_ai_gpr_registration.py:54-82) reads input blobs at `base_commit`, not the living paths. Both blob hashes match. IMMUTABLE — the fix for tonight's time-bomb is correctly in place at origin/main.
- Module constants (src/ai_gpr_benchmark.py:34-37) equal the registration's values; runtime refuse-on-drift exists (`_verify_local_inputs`, SystemExit at :81; `_verify_registration` at :59) and tests assert its presence (test:85-100).
- Note (not a defect): the script itself is *not* at base_commit e075a24 — it landed one commit later (58ca6c0). The registration pins it by sha256, not by base_commit path, so the freeze still binds.
- Fact useful to a referee: `docs/data/history.csv` at origin/main *still* hashes to the registered value (last data commit 6ef9b6e, "final 2026-08-06"; no append since). So the old on-disk check would not have failed yet; the re-pin landed before the bomb went off, not after.
- Residual hazard (latent, manual-only): while history.csv is unchanged, `python -m src.ai_gpr_benchmark` would re-run successfully and rewrite `docs/data/ai_gpr_benchmark.json` with a fresh `generated` timestamp, breaking tests/test_divergence_register.py:58-62, which requires sha256(payload) to appear verbatim in `analysis/ai_gpr_benchmark_run_log.md`. No lane invokes the module (grep: zero callers in src/run_daily.py, scripts/, .github/workflows). Exposure window closes at the next history.csv append, when `_verify_local_inputs` starts refusing. `src/stamp_meta.py:52-58` already SKIPs this payload for exactly this reason; `src/freshness.py:70-74` exempts it. Flagged for completeness.
- Script pin is a working-tree path (test:24-25) but the artifact is a one-shot frozen analysis script that must never change — the pin *is* the freeze. SOUND by intent.

## 2. Alerts design registration vs src/alerts.py — constants SOUND, T3 scope DRIFTED

Signed doc: `design/alerts_webhook.md` (SIGNED 2026-08-06, "sign alerts"; signed header registers the 730-day T2 window at lines 6-8).

| Registered parameter | Signed doc | Implementation | Match |
|---|---|---|---|
| T1 band non-overlap, Wilson 95% | :34-38 | src/alerts.py:45-46, 65; z=1.96 in src/uncertainty.py:50-54 | yes |
| T2 90th percentile | :39-43, "90th" :49 | `PCTL_THRESHOLD = 0.90`, src/alerts.py:41 | yes |
| T2 window 730 days | :7-8 | `PCTL_WINDOW_DAYS = 730`, src/alerts.py:42 | yes |
| T2 both band edges beyond threshold | :41-42 | src/alerts.py:104 (`band[0] > threshold` on up, `band[1] < threshold` on down) | yes |
| 90-day retention | :57, :123 | `RETENTION_DAYS = 90`, src/alerts.py:40, prune :151-153 | yes |
| No email, no forecast fields | :20-26, :103-104 | `direction` = completed move only; poll model | yes |
| Near-miss non-triggers tested | :110-112 | tests/test_alerts.py:28 (bands touch), :53 (band straddles) | yes |

DRIFTED — T3. The signed doc registers T3 as **two** events: "The morning publish misses its contract window, **or the dual-computation audit fails**" (design/alerts_webhook.md:44-47). src/alerts.py:117-131 implements only `morning_contract_miss`. The narrowing rationale ("an audit failure blocks publication entirely, so it surfaces as the missed morning it causes") lives in the module docstring (src/alerts.py:17-23) — but the doc's own rule (:49-51) requires "an append-only dated amendment entry in this file" for any change, and design/alerts_webhook.md contains no amendment section (file ends at :125). The reasoning may be right; the register is wrong. One dated amendment paragraph fixes it.

Unregistered parameter: T2 requires ≥180 trailing observations in the window (src/alerts.py:93) — a trigger-suppressing constant absent from the signed doc.

Committed payload conforms: docs/data/alerts.json `_meta.triggers` states "90th pctl, 730d window"; 7 alerts retained, ids match the registered stable-id scheme (e.g. `2026-08-05-composite-T2`).

## 3. Back-extension OVERLAP_THRESHOLDS — SOUND

Registered: `analysis/back_extension_memo.md` (SIGNED 2026-08-06, "sign back-extensions"), decision D at :85-88: r ≥ 0.6 tracks; 0.4–0.6 publishable with caveat; < 0.4 does not publish.

- Code: `OVERLAP_THRESHOLDS = {"tracks": 0.6, "partial": 0.4}` — src/back_extension.py:66; verdict ladder :163-165; refusal channels excluded from published series :192-197.
- docs/history.html:57-58 quotes "r ≥ 0.6 ... Below 0.4 it does not publish at all" — matches.
- docs/research/history.html:55-57 quotes the 0.4 publication floor — matches (0.6/0.4 registered floor confirmed everywhere; nobody quotes a different number).
- Committed payload `docs/data/back_extension.json`: pakistan_west r=0.893 (tracks), china_east r=0.848 (tracks), us_trade r=0.216 (refused), gulf_energy r=0.153 (refused); `series` contains exactly the two passing channels. Page prose (0.893/0.848/0.216/0.153, "two cleared, two refused", 6-of-9 anchors) equals payload values.
- Anchor list in code (src/back_extension.py:55-65) matches memo decision C; Kargil graded at 1999-06, inside the registered 1999-05..07 range.
- Unregistered addition (conservative): a `< 24` overlap-months → "insufficient" verdict (src/back_extension.py:160-161) not in the memo. It can only refuse, never admit; note it, don't fix under pressure.
- Enforcement note: no test pins the 0.6/0.4 constants; the freeze is memo + code + page-claims agreement. Currently consistent.

## 4. V11 forecast freeze — SOUND, enforcement thin

Registered: `validation/forecast_registration.json` (founder-signed 2026-08-06). Freeze artifact: `validation/forecast_logit_frozen.json` — coefficients [-0.645479, 0.003153, 0.008114], n_obs 2210, base_rate 0.3846, train window 2018-01-07..2026-08-03 (pre-registration Mondays only).

- The freeze is a **committed constant**: single commit 9dd72d7 (2026-08-06T16:10:45+05:30), zero changes since. Runtime reads the committed coefficients (src/forecasts.py:157) and fits only if the file is absent (src/forecasts.py:242-245). No re-fit on any run while the file exists. The freeze is real.
- Questions committed before windows: `validation/forecast_questions.json` committed 9dd72d7 (2026-08-06); first window_start 2026-08-10 — 4 days of margin. Void-by-late-commit rule stated in payload `_meta` and module (src/forecasts.py:9, :145).
- Gap 1: tests/test_forecasts.py:26-33 checks only shape (`len(coefficients) == 3`, `n_obs > 500`) — a silently edited coefficient passes CI. The "refits are new registrations" rule is enforced by git history only.
- Gap 2: `fit_frozen_logit` hardcodes `"fit_date": "2026-08-06"` (src/forecasts.py:119). If the frozen file were ever deleted, a re-fit on post-registration data would regenerate it stamped with the original registration date — a forged provenance by accident. Recommend a value-pin test (assert the three registered coefficients) which closes both gaps at once.

## 5. China monitor — SOUND

Registered: `countries/china.json` (`REGISTERED 2026-08-06`, `frozen_on: 2026-08-06`, "sign china"); 5 channels, 39 phrase terms with per-term rationale. Single commit since signing (8f7c40f, 2026-08-06T16:13:44+05:30); zero amendments; registered content unchanged.

- Refuse-unsigned is real: `registered()` gate src/country_monitor.py:42-44; refusal with loud line :200-204; `sys.exit` when an explicitly requested country is unsigned :208-209. Tested: tests/test_country_monitor.py:7-16 (drafts refused), :29-36 (china registered, frozen_on == 2026-08-06 asserted).
- First payload `docs/data/country_china.json` first committed at 88b9cbc (2026-08-07T18:35:38Z — the nightly data commit). Conformance to registration: all 5 registered channels present by name; 3 collected (taiwan_strait 67.1, us_tech_trade 32.9, south_china_sea collected with null score), 2 uncollected published as `score: null, collected: false` (india_border, energy_supply_lanes); `n_channels_registered: 5`, `n_channels_collected: 3`; composite null while partial — exactly the partial-state-legible behavior tested at tests/test_country_monitor.py:72-98. Same construction as India lane (share → trailing-730-day percentile), monitor-never-comparator stated in `_meta`. Registration text and frozen_on are carried verbatim in the payload `_meta`.
- Notes: (a) no hash pin on countries/china.json — the term freeze is git-history + procedure, not test-enforced; a silent term edit would pass CI. (b) `registered()` trusts any `frozen_on` value or a status string starting "REGISTERED" — the signature is a chat event, unverifiable from the repo. Both acceptable for a monitor, worth a pin if China numbers ever feed a claim.

## 6. Splice freeze — SOUND (verified: nothing adopted, nothing moved)

Freeze: NOTES_FOR_ISHAN.md §0.24 — production ratios stay frozen pending the founder's splice decision; §0.15B addendum records the measured sensitivity (china_east daily max shift 18.7, 7-day 25.6).

- Production constants live in `data/raw/ngram_calibration.json`: pakistan_west 1.9547 (n=5), china_east 3.3612 (n=5), gulf_energy 1.791 (n=5), us_trade 2.5616 (n=1), shipping 2.9747 (n=1). **Single commit ever**: a08fd02 (2026-07-29). Unchanged through origin/main. Matches the §0.24 "production ratio" column exactly, and `production_ratio` fields in docs/data/splice_sensitivity.json.
- The independent audit's ratios (2.4634 / 2.6998 / 1.8098) appear only in the audit artifacts, never in any production constant. Consumers divide by the frozen ratio read-only: src/nowcast.py:92, src/fetch_ngrams.py:384.
- Audit is test-locked to immutable inputs: tests/test_splice_overlap_audit.py pins independent_n=18, ratios 2.4634/2.6998/1.8098, changes +26.0/-19.7/+1.0, n=1 channels reported as not re-estimable; snapshot `analysis/splice_overlap_api_091c25e.csv` committed once (97ed7a8) and its source commit 091c25e resolves (`cat-file -t` → commit).
- Gap: no test pins the five production ratios themselves, and `python -m src.fetch_ngrams --calibrate D0 D1` (src/fetch_ngrams.py:311-344) overwrites `data/raw/ngram_calibration.json` unconditionally — no freeze guard, no refusal. A rerun would silently replace the frozen constants and CI would stay green. One 5-line test (assert the five values) converts the procedural freeze into an enforced one.

## 7. Blind-audit-500 — freeze verified 24/24; four TIME-BOMBS in its enforcement test; stale .ots (see §8)

Registered: `validation/blind_audit_500/registration.json` (v2, FROZEN 2026-08-07T17:15:16Z, base_commit 119edac).

- **All 24 sha256 pins verify at base_commit 119edac AND at origin/main** (11 receipt days, 2 pilot frames, rubric, dictionaries, builder/scorer, instructions, 2 matcher files, 3 coder sheets, sample key, pilot sheet): 24 ok, 0 mismatch, 0 missing. Ran the actual pytest file: passes.
- Sample and criteria frozen before labels: all three 500-row coder sheets and the 20-row pilot sheet are committed with **0 filled label cells** (checked all `coder_label`/`coder_confidence` cells in coder_sheet.csv, coder_sheet_c1.csv, coder_sheet_c2.csv, pilot_sheet.csv). No labeled sheet exists anywhere at origin/main. Attestation block: no external or pilot labels seen before freeze.
- v1 invalidated **before any label** (validation/blind_audit_500/V1_INVALID.md, 2026-08-07): sampler omitted the production India anchor; no-reuse rule registered in v2's `supersedes` block. Correction trail intact in git (989c43f → 119edac → 295fe59).
- CONFIRMATORY_PLAN.md committed at 119edac (2026-08-07T22:46:59+05:30); its source window is the first 90 complete UTC days **beginning 2026-08-08** — frame fixed before any label, one day before the window opens. Criteria (LCB ≥ 0.80, ≥400 firm labels/coder/channel, agreement ≥ 0.90, AC1 ≥ 0.70) fixed in the same pre-label commit. Nothing labels-side has leaked in: no label file, no partial result, no per-item output exists at origin/main.

**TIME-BOMBS** — tests/test_blind_audit_500.py `test_registered_builder_inputs_and_outputs_are_unchanged` hashes **working-tree paths** (`ROOT / path`, lines 38-52) for all 24 pins. For frozen study artifacts that is correct (the pin is the freeze). Four of the pinned files are living by their own declaration:

| # | Pinned living file | Test line | Evidence it lives | Fuse length |
|---|---|---|---|---|
| TB-1 | `dictionaries.json` | tests/test_blind_audit_500.py:40 | v1.0.0 (7dae91b 2026-07-24) → v1.1.0 (6d299b8 2026-07-31) → v1.2.0 (b4c970c 2026-08-05); amendment process is registered and active | ~1 amendment/week observed. **Next dictionary amendment turns CI permanently red.** |
| TB-2 | `src/fetch_ngrams.py` | tests/test_blind_audit_500.py:47 (matcher loop) | 4 commits 2026-08-06..08-07 (1c4a6ba, 3f01c0f, 7a31dde, c940016) — highest-churn production module in the repo | Days. The next matcher fix breaks the registration test. |
| TB-3 | `src/receipts_ngrams.py` | tests/test_blind_audit_500.py:47 | 3 commits 2026-08-06..08-07 | Days-to-weeks. |
| TB-4 | `auditor/RUBRIC.md` | tests/test_blind_audit_500.py:39 | Its own header: "Versioned like any instrument; changes are dated amendments" (v1.0.0, registered 2026-08-03) | First rubric amendment. |

This is exactly the class fixed tonight for history.csv, with the same correct repair: the registration already carries `base_commit` 119edac and a `base_commit_rule`; verify these four against `git show 119edac:<path>` blobs (with the same shallow-clone skip Codex added to ci.yml for the AI-GPR test), keeping working-tree pins only for the true frozen study artifacts (sheets, sample key, instructions, builder/scorer, receipt-day files — all single-commit, never legitimately edited). Note the coupling: the matcher pins currently verify at origin/main only because the last matcher commit (c940016) is an ancestor of the freeze — confirmed via `merge-base --is-ancestor`. Any commit touching those files flips all of tests/test_blind_audit_500.py red.

Receipt-day inputs are effectively immutable in practice: each `data/raw/receipt_days/*.json` in the frame has exactly one commit; no pruning/retention code touches that directory (grep across src/ and workflows: none).

## 8. OpenTimestamps files — one SOUND, one DRIFTED

Two `.ots` files exist at origin/main. Each stamps the sha256 of its neighbor at stamp time (digest extracted from the OTS header, tag 0x08):

| .ots | Stamped digest | Current neighbor digest | Verdict |
|---|---|---|---|
| `analysis/ai_gpr_benchmark_registration.json.ots` (committed fce2ac7) | 7c82a05494...8370 | 7c82a05494...8370 | **SOUND** — stamps the exact current bytes. |
| `validation/blind_audit_500/registration.json.ots` (committed 989c43f) | a394918644...5255 | c313c7a557...9b87 | **DRIFTED** — the stamp binds registration.json **as of 989c43f, i.e. the superseded v1 registration**. The file was rewritten twice since (119edac, 295fe59). `ots verify` against the current v2 file fails; **the v2 registration has no timestamp proof at all.** |

The stale stamp is honest evidence *for the v1 correction trail* but sits beside a v2 file it does not cover, which a referee will read as a broken seal. Fix: re-stamp the current v2 bytes; keep the old proof renamed as v1 evidence (it corroborates V1_INVALID.md's timeline).

Timing note: the AI-GPR .ots was committed 14 minutes after its registration commit (58ca6c0 20:17 → fce2ac7 20:31 IST), inside commit B. The registration's own rule (publication.external_timestamp) only requires disclosure, satisfied.

## 9. General-class sweep — every hardcoded pin at origin/main, classified

64-hex sha256 literals in committed code (tests/, src/, scripts/, conftest.py):

| Location | Pins | Verifies against | Class |
|---|---|---|---|
| src/ai_gpr_benchmark.py:34 | external AI-GPR CSV bytes | file supplied at run time | IMMUTABLE (external bytes; provider revision → refuse, by design) |
| src/ai_gpr_benchmark.py:36-37 | history.csv, episodes.json | on-disk at run time (refuse-to-run), blobs at base_commit in test | IMMUTABLE where enforced (test); runtime on-disk check will refuse after next append — intended |
| src/blind_audit_500.py:44-92 (20 hashes) | study inputs | inside a file that is itself pinned by the registration | IMMUTABLE (self-consistent) |
| tests/test_ai_gpr_registration.py:25 | frozen analysis script @ working tree | — | LIVING path, frozen-by-intent artifact: SOUND |
| tests/test_blind_audit_500.py:38,41,48-52 | scorer, instructions, sheets, key @ working tree | — | LIVING paths, single-purpose frozen artifacts: SOUND |
| tests/test_blind_audit_500.py:39 | auditor/RUBRIC.md @ working tree | — | **LIVING, versioned — TIME-BOMB (TB-4)** |
| tests/test_blind_audit_500.py:40 | dictionaries.json @ working tree | — | **LIVING, amended twice in 12 days — TIME-BOMB (TB-1)** |
| tests/test_blind_audit_500.py:43,45 | 13 receipt-day files @ working tree | — | day-frozen, one commit each, no pruning code: SOUND |
| tests/test_blind_audit_500.py:47 | src/fetch_ngrams.py, src/receipts_ngrams.py @ working tree | — | **LIVING production code — TIME-BOMBS (TB-2, TB-3)** |
| tests/test_divergence_register.py:59 | sha256(docs/data/ai_gpr_benchmark.json) must appear in run log | working tree | LIVING-in-principle; defended by stamp_meta SKIP (src/stamp_meta.py:52-58) and freshness EXEMPT (src/freshness.py:70-74); breaks only on a manual rerun during the pre-append window — latent, low |

`git show`/`rev-parse` of branch/living paths in committed code: **none found**. All git plumbing in src/tests resolves fixed SHAs (src/vintages.py:37-38,144 — per-vintage `git show <SHA>:docs/data/history.csv`, immutable by construction; tests/test_ai_gpr_registration.py:65-79 — blobs at registration base_commit, immutable; scripts/build_reliability.py and src/vintages.py:81-87 handle shallow clones explicitly). sha1 usage (scripts/harvest.py:63,98,116) is cache-key derivation, not a pin.

Value-pins (constants, not hashes) enforcing registrations: tests/test_splice_overlap_audit.py (independent ratios — SOUND); tests/test_forecasts.py:26-33 (shape only — gap, §4); no pin for the five production splice ratios (gap, §6); no pin for OVERLAP_THRESHOLDS (§3) or the alerts constants (§2) — currently consistent, drift would surface only via page-claims tests.

---

## Summary table

| # | Registration | Verifies now | Classification |
|---|---|---|---|
| 1 | AI-GPR preregistration | yes — 2/2 input blobs @ base_commit, script hash, ots digest | SOUND |
| 2 | Alerts (signed 2026-08-06) | constants 90th/730d/95%/90d all match | constants SOUND; **T3 DRIFTED** (audit-failure trigger dropped without a dated amendment); unregistered 180-obs guard |
| 3 | Back-extension 0.6/0.4 | memo = code = both pages = payload | SOUND |
| 4 | V11 forecast freeze | committed constant, one commit, refit-guarded | SOUND; enforcement thin (no value pin; fit_date forgery hazard src/forecasts.py:119) |
| 5 | China monitor | refuse-unsigned enforced+tested; first payload conforms | SOUND; no hash pin on the registered dictionary |
| 6 | Splice freeze | ratios unchanged since a08fd02; audit values not adopted | SOUND; `--calibrate` can silently overwrite — add a value pin |
| 7 | Blind-audit-500 v2 | 24/24 pins @ base commit and @ main; 0 label cells filled; plan pre-dates window | freeze SOUND; **4 TIME-BOMBS in its test** (dictionaries.json, fetch_ngrams.py, receipts_ngrams.py, RUBRIC.md pinned at working-tree paths) |
| 8 | .ots stamps | AI-GPR exact; blind-audit stamps superseded v1 bytes | AI-GPR SOUND; **blind-audit DRIFTED** (v2 unstamped) |
| 9 | Sweep | all pins enumerated | 4 time-bombs (all in test_blind_audit_500.py), 1 latent (divergence-register hash), 0 unresolvable pins |

Priority order for repair (by fuse length): TB-1 dictionaries.json and TB-2 fetch_ngrams.py (days — both break the moment normal project work resumes), TB-3 receipts_ngrams.py, TB-4 RUBRIC.md, then the stale blind-audit .ots (a referee can find it in one command), then the three enforcement gaps (forecast value pin, splice-ratio pin, alerts T3 amendment).
