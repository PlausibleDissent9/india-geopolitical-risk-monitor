# Source-rights decision packet — gdelt_bq_webngrams (lost-day backfill)

**DECISION: UNSIGNED — NO FORCE.** This is an evidence packet for the
founder's review. It authorizes nothing, changes no registry decision field,
pins no signer, and does not unblock acquisition. The registry's
`default_policy: deny` remains controlling until a complete signed transition
is reviewed and committed. The daily score does not depend on this decision
and must never wait on it: prospective days publish through the signed
aggregate-2.0 profile; this packet exists only to recover days that are
already honest disclosed gaps.

## 1. Identity and purpose

| | |
|---|---|
| source_id | `gdelt_bq_webngrams` |
| Provider | The GDELT Project, mirrored as a Google BigQuery public dataset |
| BigQuery table | `gdelt-bq.gdeltv2.webngrams` (provider-documented) |
| Registry state | `review_required`, `permitted_uses: []` |
| Material | Web News NGrams rows: per-window ngram frequency data, 2020-01 to present backfile |
| Requested role | Aggregate-only recomputation of disclosed lost-source days (first: 2026-08-11, 2026-08-12) |

2026-08-11 and 2026-08-12 are published value-free gaps with cryptographic
refusal receipts and durable ledger entries: their per-minute source-file
acquisitions failed while an OLDER day (2026-08-10) acquired successfully in
the same session. That ordering is inconsistent with a retention window and
consistent with provider-side publication gaps on those measured days —
meaning some of the 48 required half-hour files may never have existed. The
BigQuery mirror is a different provider ingestion path that may hold those
windows; whether it actually does is a measured question (section 4), not an
assumption.

## 2. Uses requested (executable vocabulary)

1. `model_processing` — query the table for the exact target days, compute
   the same per-window numerators and English-document denominator the
   production dictionaries define.
2. `publish_derived_value` — publish the recovered days' composite and
   channel values, labeled with their acquisition regime.

Uses explicitly not requested: `publish_extract`,
`redistribute_full_record`, `cite_metadata`. No identity retention, no
article metadata, no membership lists — the same aggregate-only boundary the
founder signed for profile 2.0.

## 3. Rights evidence

- GDELT's official Terms of Use: "all datasets released by the GDELT Project
  are available for unlimited and unrestricted use for any academic,
  commercial, or governmental use of any kind without fee," with
  redistribution expressly permitted and only citation + link required
  (https://www.gdeltproject.org/about.html#termsofuse).
- GDELT's data page states "All GDELT datasets are available in Google
  BigQuery" (https://www.gdeltproject.org/data.html), and GDELT's own
  announcement names the exact table: "You can also query the dataset in
  BigQuery: gdelt-bq.gdeltv2.webngrams"
  (https://blog.gdeltproject.org/announcing-the-new-web-news-ngrams-3-0-dataset/).
- Google's public-dataset terms add cost mechanics, not rights constraints:
  Google pays storage, the querying account pays queries, first 1 TB/month
  free (https://docs.cloud.google.com/bigquery/public-data). The Cloud
  Marketplace GDELT listing points licensing back to gdeltproject.org's own
  terms with an AS-IS disclaimer.
- No sentence on gdeltproject.org explicitly binds the ToU to the BigQuery
  copies; the case rests on "all datasets released" plus GDELT's statement
  that all its datasets are in BigQuery. The reviewer should weigh that
  inference deliberately.
- Cost precedent already governed in this repository: every existing
  BigQuery lane runs under `maximum_bytes_billed` caps of 1-25 GB with the
  `GCP_SA_JSON` / `GCP_PROJECT_ID` secrets, fail-closed without them.

## 4. Measured questions that must be answered before signing

1. **Dataset-generation equivalence.** The production feed is the per-minute
   v5 NGram/TOC files; the documented BigQuery table is the Web News NGrams
   3.0 backfile. Whether they are the same generation with the same schema
   and coverage is unverified. Required check: recompute one day already published from the file feed
   (2026-08-09 or 2026-08-10) from BigQuery with the frozen dictionaries and
   require an exact match to the published aggregates before any gap day is
   trusted.
2. **Window coverage of the gap days.** Whether the table actually holds the
   half-hour windows the file feed never published for 2026-08-11/12. A
   capped dispatch-only probe workflow accompanies this packet to measure
   per-day window coverage and row counts; its committed results should be
   attached to this packet before signature.
3. **Calibration regime.** The splice calibration was derived against the
   file-fed acquisition regime. If BigQuery-derived counts differ beyond
   rounding on the equivalence day, the recovered days need their own
   registered regime label rather than silent splicing.

## 5. Architecture this decision would govern (not build)

The signed aggregate-2.0 attestation is cryptographically bound to
per-minute file object identity (48 windows of exact URL + sha256 + bytes),
so this path CANNOT reuse profile 2.0. It requires a BigQuery-native
attestation profile (working name 3.0) whose provenance binds: the exact
query text sha256, the BigQuery job id, the table/partition snapshot
identity, per-window row counts, and the same closed method bindings
(dictionaries, calibration, matcher). That profile, its schema, its
code-pinned constants, and its hostile tests are a reviewed engineering
deliverable in the finality plane's lane; this packet only records the
rights decision such a profile would execute under. A recovered day must be
published with its regime disclosed, and a day absent from both the file
feed and the mirror stays a disclosed gap.

## 6. Human review questions

1. Do GDELT's "all datasets released" terms cover the BigQuery mirror, given
   GDELT's own statements but no explicit ToU sentence naming BigQuery?
2. Is the equivalence-day proof (section 4.1) sufficient to treat
   BigQuery-derived aggregates as the same measure, or should recovered days
   carry a permanent regime annotation regardless?
3. What query-cost cap and review horizon are justified? (Precedent: 1-25 GB
   caps; the probe is dispatch-only and capped at 3 GB.)
4. Should recovery scope be exactly the currently-disclosed gap days, or any
   future day whose refusal ledger entry ages past the retry window?

## 7. Decision block — for the founder (and reviewer) alone

    Decision:            [ ] DEFER pending probe results / equivalence proof
                         [ ] APPROVE uses 1-2 for enumerated gap days only
                         [ ] APPROVE uses 1-2 for any ledger-disclosed lost day
                         [ ] DENY
    decision_id:         ______________________________________________
    signer_id:           ______________________________________________
    signed_on (UTC):     ____________________________________________
    review_due (UTC):    ______________________________________________
    query cost cap:      ______________________________________________
    recovery scope:      ______________________________________________

*Drafted 2026-08-14 by Claude at the founder's direction, from repository
and provider evidence gathered 2026-08-13/14. The drafter has not signed,
has not changed any registry decision field, and makes no legal
determination. The BigQuery-native attestation profile is proposed to the
finality plane's owner in .agents/from-claude.md.*
