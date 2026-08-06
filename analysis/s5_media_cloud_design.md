# S5: Media Cloud cross-validation — registered design (2026-08-06)

Registered BEFORE any Media Cloud data is fetched (the account/key do
not yet exist, which makes the ex-ante claim verifiable from git
alone). This is the independent-corpus replication an institutional
reviewer asks about first: if IGRM's channels are real properties of
the news environment, a different archive with different ingestion
should show the same waves.

## Design, frozen

- **Corpus**: Media Cloud's online news archive via the Search API;
  collection choice recorded in the payload at first run (default:
  the full index; a narrower registered collection may be substituted
  ONLY before first fetch, recorded here by dated amendment).
- **Queries**: the registered channel dictionaries, verbatim — each
  channel's phrases OR'd, the india anchor AND-ed where the
  registration requires it. No Media-Cloud-specific tuning, ever: the
  point is the same instrument on a different corpus.
- **Series**: daily matching-story count / daily total-story count
  (their share analog), window 2023-01-01 to present (their coverage
  is thinner further back; window recorded in the payload).
- **Transform**: the identical trailing-percentile pipeline, then
  weekly means — the exact comparison unit the robustness and
  multilingual lanes already use.
- **Statistic**: Pearson r per channel between weekly IGRM percentile
  and weekly Media Cloud percentile, plus the same on raw shares.

## Interpretation thresholds, ex-ante (the same ladder as the
back-extension registration)

- r ≥ 0.6 — the channel's salience wave replicates on an independent
  corpus; publishable as validation armor.
- 0.4 ≤ r < 0.6 — partial replication; publishes with the caveat
  prominent.
- r < 0.4 — the channel does NOT replicate on this corpus; that
  divergence publishes as the finding, prominently, with the
  candidate explanations enumerated (corpus composition, ingestion
  differences, dictionary-corpus interaction) and no post-hoc query
  editing to chase agreement.

## Budget

~12 requests total (one count-over-time call per channel plus totals)
against a 4,000/week free quota. One run per week is sufficient; the
lane is not a daily fetcher.

## What activates it

The founder creates the free Media Cloud account and adds
MEDIACLOUD_API_KEY to GitHub secrets (2 minutes; NOTES 0.23). The
module is fail-closed until then: no key, no fetch, no guessed data.
