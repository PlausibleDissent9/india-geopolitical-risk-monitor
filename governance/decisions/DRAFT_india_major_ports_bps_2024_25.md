# Source-rights decision packet — india_major_ports_bps_2024_25

**DECISION: UNSIGNED — NO FORCE.** Draft for founder review; authorizes
nothing; `default_policy: deny` governs until signed per
`governance/decisions/README.md`.

## 1. Identity

| | |
|---|---|
| source_id | `india_major_ports_bps_2024_25` |
| Provider | Ministry of Ports, Shipping and Waterways, Government of India |
| Registry state | `review_required`, `permitted_uses: []` |
| Access basis (registry) | `official_site_reproduction_policy_pending_signed_scope_review` |
| Terms URL | https://shipmin.gov.in/en/footer/copyrightpolicy |
| Material | Basic Port Statistics of India, 2024–25 |

## 2. Rights basis, as recorded — not as reinterpreted

The registry's review (2026-08-08) records: *"The Ministry copyright policy
appears to allow accurate attributed reproduction, but IGRM requires a
human-signed source-specific scope decision."* This packet adds no new
reading of the terms.

Registered data hazards that must survive any approval, as already recorded
in the registry notes: **loaded-country semantics, table typos, PDF blanks,
and rounding residuals remain explicit** in the committed extract
(`governance/shipmin_port_trade_2024_25.json`). Approval of use is not
approval to smooth any of them; a derived artifact states them where they
bear on a figure it shows.

## 3. Uses requested

1. `retain_committed_extract` — keep the hash-pinned normalized extract and
   its evidence files in the repository.
2. `derive_published_aggregates` — publish derived port-trade context
   series with attribution, vintage, and the hazard notes above where they
   apply.
3. `quote_attributed_figures` — cite individual figures in prose with
   attribution.
4. `redistribute_in_audit_bundle` — include the committed extract (not the
   Ministry publication) in offline audit bundles.

## 4. Uses explicitly NOT requested

- `redistribute_raw` — no re-hosting of the Ministry publication.
- No joint claims the tables do not support, and no silent correction of
  the registered typos/blanks/residuals.
- No implication of Ministry endorsement; textual attribution only.

## 5. Attribution plan

Provider in full, publication title and edition, access URL, retrieval
date, extract SHA-256, and "Derived figures and any errors are IGRM's."

## 6. Outage / revocation posture

Per the registry: keep the last dated series and mark the source
unavailable; adverse policy change halts new derivation and attaches a
dated notice to existing artifacts, which remain per the append-only
corrections doctrine.

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
