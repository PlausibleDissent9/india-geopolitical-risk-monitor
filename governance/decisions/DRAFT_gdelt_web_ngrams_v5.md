# Source-rights decision packet — gdelt_web_ngrams_v5

**DECISION: UNSIGNED — NO FORCE.** This is an evidence packet for the
founder's review. It authorizes nothing, changes no registry field, pins no
signer, and does not unblock acquisition. The registry's `default_policy:
deny` remains controlling until the complete signed transition described in
section 8 is reviewed and committed.

## 1. Identity and present blocker

| | |
|---|---|
| source_id | `gdelt_web_ngrams_v5` |
| Provider | The GDELT Project |
| Registry state | `review_required`, `permitted_uses: []` |
| Access basis (registry) | `public_object_access_pending_terms_review` |
| Terms URL in registry | none registered (candidate official terms: https://www.gdeltproject.org/about.html#termsofuse) |
| Material | Temporary Web NGrams v5 per-minute NGram and TOC files |
| Production role | Daily press-salience score bridge and evidence frame |

`src/ngram_rights.py` refuses before any source probe, retained-identity read,
or publication while this decision is pending. The production trusted-signer
map is also intentionally empty. A registry edit or signature by itself is
therefore insufficient and must not be treated as authorization.

## 2. Source evidence found — and what it does not establish

Official GDELT material currently supports these factual observations:

1. GDELT's official Terms of Use state that every dataset released by the
   GDELT Project is available for unlimited and unrestricted academic,
   commercial, or governmental use without fee. The same page expressly
   permits redistribution, rehosting, republication, and mirroring in any
   form, provided the use or redistribution cites the GDELT Project and links
   to its website:
   https://www.gdeltproject.org/about.html#termsofuse
2. GDELT's June/July 2026 Web NGrams v5 announcement describes the temporary
   dataset as a downloadable, non-consumptive NGram dataset intended to let
   researchers perform their own keyword searches. It says the NGram payload
   contains frequency histograms and no article full text:
   https://blog.gdeltproject.org/using-the-new-web-ngrams-dataset-to-find-relevant-coverage/
3. GDELT's 2022 Web NGrams 3.0 guidance recommends the downloadable dataset for
   high-volume querying and describes local querying as unlimited:
   https://blog.gdeltproject.org/ukraine-api-rate-limiting-web-ngrams-3-0/
4. The production module records a 2026-07-28 maintainer response directing
   this project to the temporary NGrams dataset instead of the APIs. The
   original correspondence should be attached or archived by the founder
   before relying on it; a code comment is not independent evidence.

The first item is express provider permission for use and redistribution of
GDELT-released datasets, subject to citation and linking. That is materially
stronger than an inference from public downloadability. A human reviewer must
still decide whether the temporary v5 NGram and TOC files are within the page's
phrase "all datasets released by the GDELT Project," whether any third-party
content embedded in TOC metadata changes the analysis, and whether IGRM's
current retained metadata is actually necessary. The packet records those
questions instead of silently answering them.

## 3. Exact uses the current implementation requires

The active production gate requires all four registered uses below. The names
are the executable vocabulary in `src/publication_guard.py` and
`src/ngram_rights.py`, not friendly paraphrases.

1. `model_processing` — download and parse the NGram/TOC files; match the
   frozen dictionary; compute per-channel numerators and the English-document
   denominator.
2. `publish_derived_value` — publish the calibrated daily composite and channel
   values derived from those counts.
3. `publish_extract` — commit the target-day evidence cache, including
   domain-separated document-identity commitments and matched-article metadata.
4. `redistribute_full_record` — permit the current public evidence-retention
   surface as classified by the production rights gate. The cache does not
   contain article full text or raw NGram files, but it does contain retained
   source-derived metadata and is committed to a public repository.

Approval of only uses 1–2 does **not** unblock the current code. The official
terms provide an explicit provider basis for considering uses 3–4, but the
founder/reviewer must affirm that those terms cover the exact temporary files
and retained metadata surface. Approval is not automatic merely because the
packet found favorable language.

## 4. Narrower architecture available for separate review

If the founder cannot support uses 3–4, the honest engineering alternative is
to version a new aggregate-only evidence profile. It would keep raw and
identity-bearing source material out of the public repository, publish only
the derived numerator/denominator aggregates and their method/byte
commitments, and narrow the requested decision to `model_processing` and
`publish_derived_value`.

That alternative has a real trade-off: a public reader could recompute the
arithmetic from released aggregates but could not independently reconstruct
document membership. The product must disclose that limit rather than call the
aggregate-only receipt independent denominator verification. This is a new
reviewed contract, not a bypass or a silent downgrade of the existing proof.

## 5. Uses explicitly not requested

- Re-hosting source article full text, images, or raw per-minute GDELT files.
- Training or tuning a model on source article content.
- Republishing GDELT as a substitute data service.
- Claiming GDELT endorses IGRM or validates the score.
- Removing attribution, source-vintage, sampling, incompleteness, or
  experimental-feed disclosures.
- Converting a press-salience measure into event severity, truth, forecast,
  investment, or policy advice.

## 6. Attribution and source-change posture

Every derived publication should identify The GDELT Project, the Web NGrams
v5 feed, the UTC measurement date, the exact sampling frame, and IGRM's own
transformation version. Wording must state that derived calculations and any
errors are IGRM's.

If the source becomes unavailable, its format changes, the provider objects,
or the decision expires/is revoked, acquisition and value publication refuse.
No partial day may be promoted. Previously published values retain a dated
rights/source notice; they do not silently inherit a later decision.

## 7. Human review questions

Before signing, the founder should answer and retain evidence for each:

1. Does GDELT's official unlimited/unrestricted-use clause cover the temporary
   v5 NGram and TOC files used by this pipeline?
2. Does its express redistribution clause cover public retention of hashed
   document identities plus matched title/URL/date metadata, including any
   third-party content interests in that metadata?
3. Is the requested `redistribute_full_record` classification genuinely
   intended, or should the pipeline move to the aggregate-only profile first?
4. What review horizon and `max_current_age_days` are justified? A short,
   explicit horizon is safer than an indefinite authorization.
5. Who is the named human signer, and what role (`principal_investigator` or
   `rights_reviewer`) are they personally accepting?

If any answer is missing, choose **DEFER**, leave the registry pending, and
keep the public value-free refusal.

## 8. Complete transition required after a human decision

A valid approval is atomic and includes all of the following in one reviewed
commit:

1. exact signed JSON decision artifact and detached Ed25519 signature;
2. human signer entry in `governance/rights_signers.json`;
3. matching approved source row, digest, paths, dates, maximum age, and closed
   uses in `governance/source_rights_registry.json`;
4. exact signer ID, public key, and role pinned in
   `src/ngram_rights.py::PRODUCTION_TRUSTED_SIGNERS`;
5. hostile tests for artifact/registry/key/use/date/revocation substitution;
6. the full publication gate at the immutable candidate commit.

An agent-generated key, a mutable-registry-only key, an unsigned artifact, a
signature without the production code pin, or a decision entered by an agent
must continue to refuse.

## 9. Decision block — for the founder (and reviewer) alone

    Decision:            [ ] DEFER pending explicit terms/permission
                         [ ] APPROVE current uses 1-4 after documented review
                         [ ] AUTHORIZE aggregate-only redesign; do not approve yet
                         [ ] DENY
    decision_id:         ______________________________________________
    signer_id:           ______________________________________________
    signer role:         [ ] principal_investigator  [ ] rights_reviewer
    reviewed_on (UTC):   ______________________________________________
    review_due (UTC):    ______________________________________________
    max_current_age_days: _____________________________________________
    evidence annex:      ______________________________________________
    Registry, signer pin, artifact and signature in same commit: [ ]

*Drafted 2026-08-12 by Codex from repository and official-source evidence.
The drafter has not signed, has not changed the registry, and makes no legal
determination. A parent/guardian and qualified rights professional should
review this decision if the founder is a minor.*
