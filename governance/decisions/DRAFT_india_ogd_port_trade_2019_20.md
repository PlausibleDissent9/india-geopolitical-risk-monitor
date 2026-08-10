# Source-rights decision packet — india_ogd_port_trade_2019_20

**DECISION: UNSIGNED — NO FORCE.** Draft for founder review; authorizes
nothing; `default_policy: deny` governs until signed per
`governance/decisions/README.md`.

## 1. Identity

| | |
|---|---|
| source_id | `india_ogd_port_trade_2019_20` |
| Provider | Ministry of Ports, Shipping and Waterways via Open Government Data Platform India |
| Registry state | `review_required`, `permitted_uses: []` |
| Access basis (registry) | `government_open_data_license_india_pending_signed_scope_review` |
| Terms URL | https://www.data.gov.in/sites/default/files/NDSAP_OpenDataLicense.pdf (GODL-India) |
| Material | Overseas cargo (principal commodities) unloaded and loaded by country at Major Ports, 2019–20 |

## 2. Rights basis, as recorded — not as reinterpreted

The registry's review (2026-08-08) records: *"The OGD page states that
published resources are licensed under GODL-India, but IGRM still requires
a human-signed source-specific scope decision."* GODL-India is a standing
open license; the reason this packet exists anyway is the project's rule
that **no source is used on an agent's reading of a license** — the signed
decision is the authorization, not the license text.

One semantic hazard is registered and must survive any approval: the loaded
table's **"Country of Origin" heading is preserved as an ambiguity**, never
silently interpreted as destination. Any derived artifact states the
heading as printed.

## 3. Uses requested

1. `retain_committed_extract` — keep the hash-pinned loaded table
   (`governance/ogd_port_trade_baseline.json`) and evidence files.
2. `derive_published_aggregates` — publish derived port-trade context
   (2019–20 baseline shares) with attribution and the ambiguity note.
3. `quote_attributed_figures` — cite individual cells in prose with
   attribution.
4. `redistribute_in_audit_bundle` — include the committed extract in
   offline audit bundles.

## 4. Uses explicitly NOT requested

- `redistribute_raw` — no re-hosting of the OGD resource files themselves.
- No resolution of the origin/destination ambiguity by assumption, in any
  derived artifact, under any framing.
- No presentation of the 2019–20 vintage as current-year trade structure;
  every derived artifact carries the vintage in its label.
- No personal data (none in the tables; stated for completeness).

## 5. Attribution plan

GODL-India's attribution pattern, plus IGRM's own: provider, platform,
catalog title, vintage, retrieval date, extract SHA-256, and "Derived
figures and any errors are IGRM's."

## 6. Outage / revocation posture

OGD catalog withdrawal: retain the committed extract with a dated notice;
no further derivation. License-version change: re-review before any new
derivation; existing artifacts keep the license version they were derived
under, stated.

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
