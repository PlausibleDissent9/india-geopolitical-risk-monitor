# Reviewer-simulation audit — first pass, 2026-08-06 morning

MI7 work order: read every methodology/validation/codebook claim as a
hostile reviewer; every finding is fixed or disclosed, and the list
itself is the record. Context: the 02:06 crew session died two minutes
in (its transcript ends mid-health-check), so this first pass was done
by the overnight interactive session in the final hour before 08:00.
It is a FIRST pass — a full line-by-line night remains queued for the
next crew, and this file is append-only.

## Findings, each with disposition

1. **"hourly samples" was stale in four places** (methodology.md and
   methodology.html, §3 and the limitations table). The bridge moved to
   48 half-hourly samples on 2026-08-03; the text still said hourly.
   FIXED: now "half-hourly" in all four locations.

2. **methodology.md's version line said 1.5.0 while its own changelog
   carried a 1.6.0 entry** (the html twin was bumped, the md was not).
   FIXED: both files now say 1.6.0.

3. **Start Here hard-coded "Thirty endpoints"** — true today, stale the
   day the contract grows. FIXED: now "Every endpoint frozen with
   promised fields" (the contract test guards the actual membership).

4. **The 06:00 morning deadline is structurally unmeetable under the
   current heal design.** The UTC day closes at 05:30 IST; the heal
   then downloads ~48 ngrams files (~1GB) and parses them in pure
   Python, ~25-30 minutes on the VPS — so the earliest possible publish
   is ~06:05, and the last three mornings' reliability rows honestly
   show late publishes (07:03, 10:27, and today ~06:44). DISPOSITION:
   disclosed here and to the founder; two honest options are his call:
   (a) re-state the public contract to 07:00 IST with a dated
   methodology note, or (b) parallelize the heal's download+parse
   (same files, same arithmetic, ~4-6x faster, publish ~05:45) and keep
   06:00. Recommendation: (b), specced for the next crew night, with
   (a) as the honest interim statement either way. Also fixed today:
   cron shots now flock-serialized (three overlapping heals ran
   simultaneously this morning, wasting the window).

5. **china_east splice ratio predates the 2026-08-05 dictionary
   amendment.** The published ratio (3.3612) was calibrated against the
   pre-amendment dictionary; Aug 5 onward the series is computed with
   v1.2.0 terms but spliced with the old ratio. The error is bounded by
   the removed terms' share contribution (the monsoon-leak class the
   amendment deleted), and the direction is conservative (the amendment
   removed contamination, so the old ratio slightly over-divides), but
   it is real. DISPOSITION: disclosed here; queued for the founder —
   either recalibrate on post-amendment overlap (if any API days
   return) or add one sentence to the methodology splice note. The
   Aug 5 china_east reading (4.5, band [0.4, 36.4]) should be read
   with this in mind, alongside the genuine coverage collapse the
   non-overlapping bands establish.

6. **SUPERSEDED 2026-08-08: the daily brief could lag the published day.**
   The page hid a stale brief, but the generator itself later joined
   2026-08-07 scores to 2026-08-06 receipts and published unsupported claims.
   The experiment is withdrawn; see the corrections ledger and
   `analysis/daily_brief_incident_2026-08-08.md`.

7. Claims spot-checked and verified true today: hit-rate 18/21 with
   frozen-list commit history; placebo counts; robustness numbers and
   the 0.527 discussion; drift years and correlations (now guarded by
   tests/test_published_promises.py); precision author_labels_n=16
   with UNCALIBRATED flag; contract v1.3.0 with 30 endpoints; CSP
   self-hosted-only on all pages (two Google Fonts relics found and
   removed tonight); reliability record showing its own misses —
   which is the point of it.
