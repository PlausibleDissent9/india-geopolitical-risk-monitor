# GDELT aggregate-profile rights review

Production remains blocked until a human reviews the official GDELT terms,
creates a signed decision, and separately reviews the proposed production
trust pin. The relevant official terms are on the [GDELT About
page](https://www.gdeltproject.org/about.html). The proposed decision is
deliberately narrower than those terms: it names only `model_processing` and
`publish_derived_value` for aggregate profile 2.0.

The signed decision uses closed schema `1.1.0`, binds the exact aggregate
profile and official GDELT citation, and signs an exact recovery vector and
digest. The vector is derived from the fixed outage start `2026-08-09` through
the day before `reviewed_on`; it is capped at `2026-08-31` and 23 entries. A
review outside that bounded window refuses rather than creating an open-ended
exception. Listed dates do not widen the ongoing `max_current_age_days` rule
for later prospective days and do not authorize the incumbent identity-bearing
path.

From an interactive human terminal, prepare a closed review bundle outside the
repository:

```sh
python scripts/ngram_rights_sign.py \
  --private-key /an/outside-repository/location/ngram-rights.pem \
  --output /an/outside-repository/location/ngram-rights-review \
  --reviewed-on YYYY-MM-DD \
  --review-due YYYY-MM-DD
```

There is no non-interactive or `--yes` path. The encrypted Ed25519 private key
must remain outside Git with mode 0600. The command writes the detached
signature, signed decision, proposed signer and source registries, and a
review-only code-pin snippet as one atomic bundle. It never applies the pin,
edits the live registries, commits, pushes, or publishes a score.

Before applying anything, a human reviewer must verify the official terms,
signer identity and public key out of band; confirm the dates and exact two-use
scope; then apply the artifact, signature, registries and code pin together in
one reviewed change and run the complete publication gate. Identity retention,
extract publication, full-record redistribution, source truth, precision,
forecast and adoption claims remain outside this profile.
