# Source-rights decision packet — india_major_ports_pdmp2

**DECISION: UNSIGNED — NO FORCE.** This is a draft prepared for founder
review. Nothing in this file authorizes any use. The registry's
`default_policy: deny` governs until a signed decision lands per
`governance/decisions/README.md`.

## 1. Identity

| | |
|---|---|
| source_id | `india_major_ports_pdmp2` |
| Provider | Ministry of Ports, Shipping and Waterways, Government of India |
| Registry state | `review_required`, `permitted_uses: []` |
| Access basis (registry) | `official_site_reproduction_policy_pending_signed_scope_review` |
| Terms URL | https://shipmin.gov.in/en/footer/copyrightpolicy |
| Material | Monthly cargo traffic handled at Major Ports (February 2026 report; pages 6–7: cargo by port, cargo by commodity) |

## 2. Rights basis, as recorded — not as reinterpreted

The registry's own review (2026-08-08) records: *"The Ministry policy
appears to permit accurate attributed reproduction, but IGRM still requires
a signed source-specific decision."* This packet adds no new reading of the
terms. If the founder wants a fresh terms review before signing, that
review should be dated and attached as an annex; the packet is written so
it does not need one to be understood.

What the pipeline has already done, under committed integrity bounds
(`design/port_commodity_marginals.md`): registered the exact PDF URL,
SHA-256, valid period and table pages; extracted the two marginal tables
with dual-method reconciliation; committed the normalized extract to
governance fixtures. **No public observation is authorized or published.**
The compiler emits marginals and an immutable empty joint block — the
report supplies no port-by-commodity cells, and the packet requests no
right to pretend otherwise.

## 3. Uses requested (vocabulary: decisions/README.md)

1. `retain_committed_extract` — keep the hash-pinned normalized extract and
   its evidence files in the repository.
2. `derive_published_aggregates` — publish the two marginal arrays (tonnes
   by port; tonnes by commodity) and derived context series, each carrying
   provider attribution, the report's identity, and the extract's digest.
3. `quote_attributed_figures` — cite individual figures in analysis prose
   with attribution.
4. `redistribute_in_audit_bundle` — include the committed extract (not the
   Ministry PDF) in offline audit bundles per `design/offline_audit_bundle.md`.

## 4. Uses explicitly NOT requested

- `redistribute_raw` — no re-hosting of Ministry PDFs or page images.
- No joint port-by-commodity claims: the source publishes marginals only,
  and the compiler's empty-joint invariant stays load-bearing regardless of
  what is signed here.
- No characterization of Ministry data as endorsing IGRM, and no use of
  the national emblem or Ministry branding beyond textual attribution.
- No personal data (none exists in the tables; stated for completeness).

## 5. Attribution plan

Every derived artifact carries: provider name in full, report title and
month, access URL, retrieval date, and the registered extract SHA-256.
Wording: "Data: Ministry of Ports, Shipping and Waterways, Government of
India (Monthly Cargo Traffic, February 2026). Derived figures and any
errors are IGRM's."

## 6. Outage / revocation posture

Per the registry: keep the last dated series and mark the source
unavailable. If the Ministry's policy changes adversely, published derived
aggregates gain a dated notice and no further derivation runs; committed
extracts remain in history (append-only corrections doctrine) with the
notice attached.

## 7. Decision block — for the founder alone

    Decision:            [ ] APPROVE uses 1-4    [ ] APPROVE subset: ______
                         [ ] DENY
    decision_id:         ____________________
    signer_id:           ____________________
    signed_on (UTC):     ____________________
    Registry updated in same commit:  [ ]
    Signature file:      governance/decisions/<this-file>.sig

*Drafted 2026-08-10 by the overnight agent. The drafter has not signed,
will not sign, and has made no registry change.*
