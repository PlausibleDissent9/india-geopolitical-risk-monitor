# First real Atlas evidence vertical: major-port and commodity marginals

Status: compiler complete; **no public observation is authorized**. The source
remains `review_required` and has zero permitted uses in the signed-rights
registry.

The February 2026 Ministry report contains two official tables on pages 6 and
7. Table 1 provides cargo tonnes by each of the 12 Major Ports. Table 2 provides
cargo tonnes by commodity across those Major Ports. The two totals reconcile,
but the report supplies no joint port-by-commodity cells. The compiler therefore
emits two marginal arrays and an empty, immutable joint block. It cannot emit a
dependency edge.

## Integrity boundary

- The exact candidate PDF URL, SHA-256, valid period, publication date, table
  pages and first IGRM registration date are registered together. A snapshot
  cannot relabel the same bytes as a different month or claim knowledge before
  the registered vintage existed in IGRM.
- The local PDF bytes must match the snapshot hash before any compilation.
- All 12 port members and all 20 tonne-denominated commodity rows must appear
  once, in the registered order, with the exact registered labels.
- Both marginal sums must independently equal the declared total.
- Container TEUs remain a separate unit and never enter tonne reconciliation.
- Dual-method reconciliation requires two distinct evidence files: a text/table extraction and
  a visual table review. Each file is hash-bound in the source snapshot and
  must independently name the exact source-PDF hash and normalized observation
  hash. Merely listing two reviewer names is insufficient. The snapshot also
  preserves estimate status, valid period, retrieval time and knowledge time.
- Any non-empty joint cell, dependency edge, partial denominator, unknown
  member, altered label, bad source host, source-byte drift or rights mismatch
  refuses compilation.
- Publication additionally requires an Ed25519-verified source-rights decision
  granting metadata citation, derived-value publication and extract publication.

Coverage is 12 of 12 **within the Major Port frame**. It is never stated as a
percentage of all Indian ports because non-major ports are outside this source
frame. KDS and HDC are subcomponents of SMP Kolkata, not extra Major Ports.

The Ministry's [copyright policy](https://shipmin.gov.in/en/footer/copyrightpolicy)
states that site material may be accurately reproduced free of charge with
prominent acknowledgement, except identified third-party material. That public
statement is evidence for legal review, not an agent-issued authorization.
Until IGRM records a signed source-specific decision, the current registry
forces every compilation attempt to stop at `rights_not_approved`.
