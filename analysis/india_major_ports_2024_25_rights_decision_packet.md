# Human decision packet — India Major Ports 2024–25 unloaded-cargo frame

**Prepared:** 2026-08-10  
**Status:** decision packet only; no authorization, signature, legal conclusion or
publication authority  
**Source ID:** `india_major_ports_bps_2024_25`

## Decision required

An authorized human reviewer must choose one of the following outcomes for the
exact source and scope below:

1. **Approve all three required uses:** `cite_metadata`,
   `publish_derived_value`, and `publish_extract`.
2. **Approve a narrower subset.** This does not unlock the current Foundry or
   n-ary Trace release when any required use remains absent; the system must
   continue to refuse value-bearing output.
3. **Refuse the proposed use.** The source stays acquired but rights-blocked.

No agent, model, test fixture, repository maintainer or unsigned registry edit
may make this decision. A signed decision records a human scope judgment; it
does not prove that the judgment is legally correct.

## Exact source under review

- Provider: Ministry of Ports, Shipping and Waterways, Government of India.
- Publication: *Basic Port Statistics of India 2024–25*.
- Source page:
  <https://shipmin.gov.in/en/content/basic-port-statistics-india-2024-25>
- PDF URL:
  <https://shipmin.gov.in/sites/default/files/BPS%202024-25_compressed.pdf>
- Registered PDF SHA-256:
  `c443531e8b7acd3d6912b25b99c97b2b2388fcba9d18d60123e2513fcd76e478`.
- Registered file size: 2,469,332 bytes; 243 pages.
- Source-page observation: the Ministry page names the publication, links the
  PDF and identifies the 2024–25 year. The page showed a 29 April 2026 update
  when checked on 2026-08-10.
- Copyright-policy page:
  <https://shipmin.gov.in/en/footer/copyrightpolicy>.
- Policy observation on 2026-08-10: the Ministry page states that site material
  may be reproduced without a separate permission if reproduction is accurate,
  not derogatory or misleading, and prominently acknowledges the source; it
  excludes third-party copyrighted material. This observation is evidence for
  the reviewer, not an IGRM legal conclusion.

The release must bind the exact registered source-page, policy-page and PDF
bytes/digests available to the decision process. A later page or policy change
does not silently retarget an earlier decision.

## Exact proposed analytical scope

Only **unloaded cargo, table 2.1.6, pages 106–117** is in scope.

- Fiscal period: 1 April 2024–31 March 2025; historical baseline, not live.
- Provider flow: unloaded.
- Country semantics: country of origin.
- Source row frame: exactly 483 country-within-commodity detail rows.
- Joint frame: 483 rows × 13 registered Major-Port table columns = 6,279
  source cells.
- Registered positive cells: 870.
- Port-table frame: 13 columns, comprising two Syama Prasad Mookerjee Port
  dock-system columns and 11 other Major Port Authority columns.
- Commodity frame: the 15 exact provider categories registered in
  `governance/shipmin_port_trade_2024_25.json`.
- Unit: thousand metric tonnes.
- Missingness: PDF blanks remain `source_blank`; they are never zero.
- Rounding: printed totals and registered rounding residuals remain visible.
- Provider labels and apparent typographical errors remain source labels until
  a separately reviewed crosswalk resolves them.

## Proposed outputs if—and only if—the decision passes

The approved release may emit:

1. citation metadata pointing to the Ministry publication and exact source
   page/table;
2. the exact source-label frame, typed missingness partition and complete
   denominator needed to audit coverage;
3. reviewed country, commodity and port crosswalks with every unmatched,
   ambiguous and withheld label retained;
4. lossless n-ary country-of-origin × commodity × Major-Port observations;
5. bounded historical association traces that preserve the n-ary fact and
   publish mapped/unmapped mass and member coverage; and
6. derived historical quantities whose transformation, unit, denominator,
   uncertainty, source hash, rights decision and implementation hash recompile.

The repository does **not** redistribute the source PDF under this proposed
release. It may retain the exact PDF privately as a proof dependency if the
reviewer permits that retention.

## Immutable exclusions

Approval of this packet must not authorize or imply:

- loaded cargo or a loaded-cargo destination interpretation;
- live/current port traffic;
- all Indian ports or non-major ports;
- firms, buyers, suppliers, consignees, vessels, shipments or end-to-end routes;
- capacity, inventory, buffer, substitution, lag or economic loss;
- binary decomposition of an n-ary source fact;
- causation, disruption, forecast, probability, advice or policy directive;
- comparison with 2019–20 without a separate comparability certificate;
- raw-PDF redistribution;
- third-party copyrighted material not covered by the Ministry policy; or
- a claim that IGRM, its founder or its counsel is independently validated.

## Questions the human reviewer must answer

Record answers beside the final signed artifact; do not rely on an oral answer.

1. Does the Ministry copyright policy apply to the exact linked PDF and tables,
   or is any relevant material identified as third-party copyright?
2. Does accurate, attributed reproduction permit the exact proposed source
   label/cell extracts, or only metadata and derived quantities?
3. What attribution must appear on every public extract, derived artifact and
   offline proof?
4. Is private retention of the exact PDF as a non-redistributed proof dependency
   permitted?
5. Are any field-level redactions required before publishing provider labels or
   source cells?
6. What review-expiry date and re-review trigger are appropriate for this
   source/policy pair?
7. What `max_current_age_days` value is appropriate for an explicitly
   historical 2024–25 baseline? The reviewer must choose it; an agent may not
   invent a permissive number.
8. Is the reviewer acting as founder rights approver, external counsel rights
   approver, or another role? Any family-firm or compensation relationship must
   be disclosed and must not be described as independent review.

## Validator-compatible decision fields

After the human answers the questions, a separate generation step may create a
closed JSON decision artifact with exactly these fields. The placeholders below
are intentionally not a valid decision and must never be signed as-is.

```json
{
  "schema_version": "1.0.0",
  "source_id": "india_major_ports_bps_2024_25",
  "name": "Basic Port Statistics of India 2024-25 joint cargo tables",
  "provider": "Ministry of Ports, Shipping and Waterways, Government of India",
  "role": "official_latest_fiscal_port_country_commodity_observations",
  "authority_class": "official_primary",
  "independence_group": "india_ministry_ports",
  "decision_id": "__HUMAN_ASSIGNED__",
  "decision_owner": "__HUMAN_ASSIGNED__",
  "signer_id": "__REGISTERED_HUMAN_SIGNER__",
  "reviewed_on": "__YYYY-MM-DD__",
  "review_due": "__YYYY-MM-DD__",
  "access_url": "https://shipmin.gov.in/en/content/basic-port-statistics-india-2024-25",
  "terms_url": "https://shipmin.gov.in/en/footer/copyrightpolicy",
  "access_basis": "__HUMAN_REVIEWED_BASIS__",
  "lineage_policy": "primary",
  "max_current_age_days": "__HUMAN_DECISION_REQUIRED__",
  "permitted_uses": ["__HUMAN_DECISION_REQUIRED__"],
  "statement": "__HUMAN_SCOPE_STATEMENT_REQUIRED__"
}
```

The final JSON must byte-match the corresponding fields in
`governance/source_rights_registry.json`, carry a detached 64-byte Ed25519
signature, and verify against an active public key in
`governance/rights_signers.json`. The private key must never enter the
repository.

## Ceremony and release sequence

1. Founder appoints the reviewer and records role, independence/conflict and
   compensation status.
2. Reviewer receives this packet, the exact PDF hash, source page, current
   policy page, registered extraction scope and exclusions.
3. Reviewer chooses approve-subset/refuse, fills every decision field and signs
   the exact final JSON with a human-controlled key.
4. A separate operator registers only the public key and allowed human role;
   the repository verifies effective/revocation dates and the detached
   signature.
5. Code regenerates the rights registry, Foundry package and trace candidate
   from the signed decision; no value is copied from a blocked draft.
6. Tests require the exact decision, signer, source, parser, schema, crosswalk,
   universe, canonical release and public artifact hashes.
7. An independent reviewer reruns the release at the exact candidate commit.
8. Founder signs the release scope. Only then may value-bearing output activate.

Any missing signature, inactive signer, future review, expired decision,
unapproved use, source/policy drift, frame mismatch or stronger public claim
keeps the current value-free `rights_blocked_contract_only` state.

