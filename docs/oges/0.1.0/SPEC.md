# Open Geopolitical Evidence Standard — public draft 0.1.0

Effective: 2026-08-08  
Status: public draft with an IGRM reference implementation; not an ISO, BIS,
government or industry-adopted standard.

## Purpose

OGES defines a fail-closed interchange boundary for geopolitical evidence,
entities, observable events, declared universes and exposure edges. It is meant
to make a release independently inspectable without turning a schema-valid
record into a claim of truth, causation, forecast skill, legal advice or public
authority.

The normative machine profile is `profile.json`. The exact adversarial cases are
`adversarial-cases.json`. The reference commands are:

```bash
python -m src.oges_conformance profile
python -m src.oges_conformance self-test
python -m src.oges_conformance validate --bundle /path/to/bundle
```

The reference validator performs no network requests. A successful validation
prints identifiers, hashes and counts only; evidence text and exposure values do
not enter the conformance report.

## Normative release profile

A conformant release:

1. uses the exact Draft 2020-12 schema registry and schema bytes pinned by the
   profile;
2. contains a manifest whose exact bytes are signed by an effective,
   non-revoked Ed25519 release signer;
3. binds every object file and canonical record hash, with no path traversal,
   symlink, duplicate key, non-finite value or undeclared field;
4. freezes the rights registry, rights-signer registry and signed decision
   artifacts used by every evidence source;
5. keeps evidence availability, privacy and permitted-use states coherent;
6. resolves object references and exact provenance inside the same release;
7. keeps rumor/allegation/corroboration/official-confirmation roles distinct and
   requires eligible official evidence or corroboration from distinct signed
   independence groups before confirming an event;
8. binds calculated, coded and expert-derived objects to registered executable
   method bytes;
9. partitions each declared source frame into included, excluded, unmappable and
   stale members without dropping inconvenient rows;
10. keeps qualitative, unknown and quantified exposure separate, with a unit,
    denominator, period and typed uncertainty for every numeric magnitude; and
11. enforces bitemporal ordering so a release cannot claim evidence or a
    measurement that was not available by its stated knowledge boundary.

## Conformance statement

The only licensed statement is:

> This release conforms to OGES public draft 0.1.0 under the registered profile
> and reference test vector identified in its conformance report.

Conformance does **not** establish that a source statement is true, a rights
review is legally correct, two providers are empirically independent, an event
catalog is complete, an exposure is causal, a scenario is probable, or a system
is endorsed by IGRM or any government. Those questions require substantive,
legal and empirical review outside this byte-level gate.

## Synthetic fixtures

`self-test` creates a full valid release and ten invalid variants from committed,
deterministic fixture definitions. Fixture signing keys are deliberately public,
test-only keys. A production verifier must never trust their signer IDs or keys.
The suite tests signature binding, event-role eligibility, universe completeness,
method registration, quantified/qualitative separation, temporal ordering,
rights snapshot binding, strict JSON, release counts and privacy.

An implementation does not pass because it rejects *something*. Each case must
produce the exact registered status and stable refusal code. A reduced validator
that rejects every input therefore fails the valid case, while one that ignores a
boundary fails its corresponding adversarial case.

## License and attribution

The specification, machine profile, synthetic test vectors and reference code are
available under the repository's MIT License. The fixtures contain no third-party
source data. Conformance or reuse does not imply endorsement by IGRM, the author or
any public institution; users must identify the exact OGES draft version and their
own implementation in any conformance claim.

## Evolution

Version 0.1.0 is deliberately narrow: one complete release profile, JSON objects,
Ed25519 signatures and an offline reference validator. Future drafts may add
selective disclosure, alternative signature suites, streaming packages,
cross-release correction proofs and non-IGRM reference implementations. A future
version cannot retroactively change the meaning of a 0.1.0 report; it receives a
new profile and new fixtures.
