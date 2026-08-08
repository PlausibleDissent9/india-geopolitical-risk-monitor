# IGRM Max publication guard — implementation contract v0.1.0

Status: **validator and governance registries implemented; no existing public
lane may claim coverage from this guard until that lane is explicitly wired**

Effective: 2026-08-08

## Purpose

The publication guard turns the IGRM Max atomic promise into code. A future
analytical sentence or assistant answer is eligible only when a strict bundle
binds it to the exact policy, evidence and transformation bytes that support it.
The validator returns eligibility metadata; it has no field for public prose and
does not authorize a model to write any claim.

`src/publication_guard.py` checks:

- exact schemas with no extra prose, citation, confidence or model-output field;
- a default-deny source and rights decision;
- decision expiry and the exact permitted public use;
- a detached Ed25519 signature over the exact rights-decision artifact, verified
  against a registered public key;
- approved upstream sources for every derived source;
- a non-symlinked repository evidence file and exact SHA-256;
- strict JSON without duplicate keys;
- an RFC 6901 pointer, scalar type and exact source value;
- unit and denominator;
- typed uncertainty, including a required status for every numeric value;
- effective and observation timestamps resolved from registered pointers inside
  the evidence bytes, plus a same-effective-date join and current-evidence age;
- a registered transformation version and implementation-file hash;
- hashes of all four policy registries; and
- a canonical hash over the completed bundle.

Any mismatch yields a stable refusal code. The guard performs no network access
and emits no fact value in its success response.

## Governance files

- `governance/source_rights_registry.json` — source-by-source acquisition and
  public-use decisions. It is deny-by-default. Every source, including
  IGRM-authored payload expression, begins `review_required` with no permitted
  uses. A source becomes approved only when its exact decision artifact has a
  valid signature from `governance/rights_signers.json`. The listed external
  sources remaining unresolved does not declare them unlawful; it refuses to
  invent a legal conclusion.
- `governance/rights_signers.json` — Ed25519 public keys, roles, effective dates
  and revocations for people authorized to sign source-rights decisions. It is
  intentionally empty until the founder establishes a key through a separate,
  human-controlled ceremony; no private key belongs in this repository.
- `governance/claim_eligibility_contract.json` — allowed claim classes,
  forbidden high-risk classes, temporal policies and registered templates.
- `governance/transformation_registry.json` — allowed transformation versions,
  claim classes and exact implementation bytes.

Policy hashes sit inside each evidence bundle. Editing a registry after a bundle
was created invalidates the bundle rather than silently changing its meaning.
Editing a rights record and recomputing hashes is still insufficient: the exact
authorization fields must match the independently signed decision artifact.

## Derived-source rule

An IGRM payload is not allowed to launder its upstream provider. A fact whose
source has `lineage_policy: bundle_declared` must name at least one distinct
upstream source. Every upstream decision must be approved, unexpired and permit
the fact's requested use. A first-party CC BY label therefore cannot conceal an
unreviewed GDELT, UCDP, PortWatch, Yahoo, Wikimedia or other input.

## Initial supported claim surface

The only registered template is `direct_fact_v1`: one verified scalar, without
interpretation, under a descriptive-current, descriptive-historical or
methodology claim class. Forecasts, causal claims, investment advice, policy
directives, security assurances and superiority claims have no licensed template.

This narrow start is deliberate. A new template must land with its renderer,
fact shape, transformation registration, adverse tests and the publishing surface
that consumes it in the same commit.

## Wiring gates

The validator is not yet a claim that the current website is wholly guarded. The
integration order is:

1. complete and sign provider-specific rights reviews;
2. make source acquisition emit immutable evidence and upstream-lineage IDs;
3. make payload builders emit bundles from staged outputs;
4. validate every bundle before atomic promotion;
5. require the evidence-locked assistant and analytical pages to render only
   eligible bundle IDs; and
6. publish a rights-safe evidence ledger and bundle hash beside each claim.

Until a lane completes those steps, its existing tests and claim discipline still
govern it; this module must not be cited as coverage it does not yet provide.
