# Source-rights decision packet — gdelt_doc_api (receipt-identity lane)

**DECISION: SIGNED 2026-08-15 — the three canonical uses approved.** The
founder-run interactive ceremony signed this decision on 2026-08-15. The
signed artifact and its detached Ed25519 signature live at
`governance/rights_decisions/gdelt_doc_api-receipt-identity-1.0.{json,sig}`,
and the registry row moved to `approved` in the same commit. This clears the
source-rights gate only: the lane stays inactive until its own profile
signature (`governance/gdelt_receipt_identity_profile.json`) verifies through
its own ceremony. The daily score does not depend on this decision and must
never wait on it.

## 1. Identity — bound to the executable lane, not a paraphrase

| | |
|---|---|
| source_id | `gdelt_doc_api` |
| Provider | The GDELT Project |
| Registry state | `review_required`, `permitted_uses: []` |
| Lane | `src/receipt_identity.py` + `src/receipt_identity_rights.py` (landed 8d7e7a9, inactive) |
| Profile | `gdelt_doc_receipt_identity_v1`, state `inactive_pending_human_signature` |
| Uses the lane requires | exactly `cite_metadata`, `model_processing`, `publish_extract` |
| Material | DOC 2.0 API article rows: title, URL, source domain, seendate |
| Founder's goal | 50-100 headline links per channel per day, as before the freeze |

The uses above are `receipt_identity_rights.CANONICAL_REQUIRED_USES` — the
three-use decision that module accepts, verbatim. A decision naming any other
set fails closed against the running code.

## 2. What the lane does and refuses (from the shipped module)

The lane accepts only the exact title/link profile; production signer trust
is empty until a reviewed human transition pins a key (same ceremony class as
the signed aggregate-2.0 transition). It is inactive until both the profile
signature and the three-use source decision verify. No body text, no images,
no model training on article content, no substitution for the score's
aggregate denominator; the headline list is a bounded, attributed sample and
the surface must say so.

## 3. Rights evidence to weigh

GDELT's official Terms of Use state all released datasets are available for
unlimited, unrestricted use with citation, including redistribution
(https://www.gdeltproject.org/about.html#termsofuse). Open questions for the
founder: whether DOC API responses fall under "released datasets"; whether
headline text carries third-party publisher interests that public retention
implicates; and the honest retention window (proposal: rolling 90 days, then
links-only). Title+link+domain republication with attribution is the
established aggregator posture, and the lane retains no body text.

## 4. Decision block — for the founder (and reviewer) alone

    Decision:            [ ] DEFER  [x] APPROVE the three canonical uses  [ ] DENY
    decision_id:         rights:gdelt_doc_api:receipt-identity-1.0:2026-08-15
    signer_id:           human:igrm-ngram-rights-reviewer
    signed_on (UTC):     2026-08-15
    review_due (UTC):    2026-11-13
    retention window:    not fixed by the artifact; the section 3 proposal
                         (rolling 90 days, then links-only) stands as the lane
                         posture for the profile ceremony to bind

*Drafted 2026-08-13 by Claude at the founder's direction, aligned to Codex's
receipt-identity lane at 8d7e7a9. Signed 2026-08-15 by the enrolled human
reviewer through the interactive ceremony in `scripts/source_rights_sign.py`;
the drafter did not sign and makes no legal determination. The profile
activation ceremony remains Codex's to define; this decision clears only the
source-rights half of the lane's two gates.*
