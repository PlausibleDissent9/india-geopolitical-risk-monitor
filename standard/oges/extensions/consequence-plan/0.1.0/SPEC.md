# OGES Consequence Plan profile 0.1.0

Status: public draft, synthetic reference implementation, no adoption claim.

This profile proves a deliberately narrow proposition: a finite registered
query was executed against exact bound bytes with registered operators, time
rules, output rules and a machine-readable proof or refusal. It does **not**
prove that an input is true, compute a geopolitical consequence, establish
causality or completeness, issue a forecast, probability, recommendation or
risk score, or grant publication rights.

The profile reuses the OGES 0.1.0 trust boundary. It does not create a second
evidence standard. Version 0.1.0 has three closed execution profiles:

* `legacy_assistant_answer` selects registered facts from one or two exact
  payloads, asserts a common effective date and delegates byte-for-byte to the
  existing registered assistant renderer. Current production payloads have no
  signed source-rights grant and therefore remain
  `legacy_unverified_internal_regression`, never publication eligible.
* `knowledge_replay_query` delegates to the existing signed bitemporal replay
  engine. The reference fixture is synthetic and non-production.
* `registered_refusal` emits one registered refusal without values or
  evidence.

Plans contain identifiers only. They cannot carry question text, prompts,
literal facts, values, URLs, citations, units, denominators, renderer prose,
paths or arbitrary expressions. A source registry resolves paths; the plan
also binds the exact expected file digest. Execution re-opens each source and
refuses on drift. Operators and output profiles are closed and hash-pinned.

## Epistemic kinds

The only kinds in 0.1.0 are `registered_fact_reference_set`,
`integrity_verified_payload_fact_set`, `same_effective_date_fact_set`,
`verified_signed_replay_ledger`, `bitemporal_state_selection`,
`descriptive_registered_answer`, `structural_replay_report` and
`registered_refusal`. No operator may emit or imply an observation, event,
exposure, consequence, causal effect, forecast or recommendation.

## Time, rights and universe

Assistant source time comes from the opened payload bytes and must agree
across sources. Replay keeps knowledge cutoff and valid date distinct; a
future-effective record may already be knowable. Plans grant no rights.
Required uses come from the registered output profile and compose by
intersection. An unsigned execution envelope is evidence of deterministic
execution only; production meaning requires inclusion in an independently
signed release. Version 0.1.0 makes no completeness claim and refuses a
coverage percentage without an exact `UniverseRelease` binding.

## Compatibility and refusal

The legacy assistant and replay APIs remain unchanged. Adapters must produce
the exact existing `Answer.to_dict()` or replay document. Engine refusal is
distinct from a successfully executed registered refusal. A refused execution
contains only a stable stage and code; it cannot contain facts, values,
citations or a partial result.

## Out of scope

Dependency or exposure tracing, event-to-mechanism semantics, scenarios,
Decision Switch, value of information, arbitrary joins or SQL, open-ended AI
planning or prose, global indicator population, comparability certificates,
causal or policy output, and a production endpoint are out of scope. The next
consequence-bearing profile must begin with a rights-cleared, source-complete
DependencyObservation release rather than another interface.
