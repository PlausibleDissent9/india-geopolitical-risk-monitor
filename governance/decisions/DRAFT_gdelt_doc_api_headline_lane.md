# Source-rights decision packet — gdelt_doc_api (receipt-identity lane)

**DECISION: UNSIGNED — NO FORCE.** This is an evidence packet for the
founder's review, drafted at the founder's direction to restore the public
article-receipts surface. It authorizes nothing, changes no registry field,
pins no signer, and does not unblock acquisition. The registry's
`default_policy: deny` remains controlling until a complete signed transition
is reviewed and committed. The daily score does not depend on this decision
and must never wait on it.

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

    Decision:            [ ] DEFER  [ ] APPROVE the three canonical uses  [ ] DENY
    decision_id:         ______________________________________________
    signer_id:           ______________________________________________
    signed_on (UTC):     ______________________________________________
    review_due (UTC):    ______________________________________________
    retention window:    ______________________________________________

*Drafted 2026-08-13 by Claude at the founder's direction, aligned to Codex's
receipt-identity lane at 8d7e7a9. The drafter has not signed, has not changed
the registry, and makes no legal determination. The signing ceremony for this
lane is Codex's to define; this packet exists so the founder's review can
start from evidence, not from zero.*
