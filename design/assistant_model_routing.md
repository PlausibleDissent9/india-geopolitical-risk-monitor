# IGRM assistant model routing — implementation contract v0.1.0

Status: **implemented locally; kill switch closed; no public endpoint**

Effective: 2026-08-08

## Decision

IGRM uses model capability as question-understanding capacity, never as factual
authority. The deterministic grammar runs first and costs nothing. Only an
otherwise unsupported, bounded question may receive one selector call.

The intended deployment mapping is provider-neutral:

| Tier | Suitable model family | Role | Output allowance |
|---|---|---|---:|
| fast | Haiku or a fast Terra-class model | short, single-entity intent selection | 128 tokens |
| balanced | Sonnet or Terra | comparisons, evidence requests, moderate ambiguity | 192 tokens |
| deep | Opus-class model | methodology, validation and institutional-research wording | 256 tokens |

These are aliases, not hardcoded vendor model IDs. Exact IDs are deployment
configuration because providers revise names and availability. The current
adapter supports Anthropic IDs supplied through environment variables; the
`Planner` protocol permits a separately reviewed Terra/provider adapter without
changing the evidence boundary.

## What the model may emit

Exactly one JSON object:

```json
{"schema_version":"1.0.0","intent":"channel_reading","channels":["shipping"]}
```

It has no field for prose, values, dates, citations, links, denominators, fact
IDs, confidence, hidden reasoning or tool instructions. Code verifies the exact
field set, intent and channel cardinality, requires selected channels to equal
the registered channel names actually present in the question, and compiles
the selection into the existing fixed fact plan. Any mismatch becomes the
ordinary unsupported-question refusal.

The model never sees a data payload. The evidence verifier re-opens exact source
bytes and the deterministic renderer remains the only component authorized to
publish an answer.

## Routing policy

1. Forecast, trading, hedging and advice requests refuse before any model call.
2. Questions already understood by the registered grammar remain deterministic.
3. Empty or over-500-character questions refuse without a model call.
4. Complex validation/research language selects `deep`; comparison/evidence or
   moderate-length language selects `balanced`; short questions select `fast`.
5. There is at most one model call. A provider failure, malformed JSON,
   unbound entity, unknown intent or verifier failure refuses; it never
   cascades through increasingly expensive models.

One strong selector is preferable to a model committee here. Consensus among
models can multiply cost while preserving correlated classification errors.
Correctness comes from the finite selection schema, question binding and
deterministic evidence verifier—not from voting over generated prose.

## Cost and operations boundary

Model access requires both an explicit CLI flag and
`IGRM_ASSISTANT_MODELS_ENABLED=1`. Each tier also requires its exact configured
model ID. The router rejects any model planner without a budget implementation;
the adapter checks its kill switch and tier configuration before the local
budget atomically reserves the worst-case output allowance. Closed or
unconfigured routes therefore make and reserve zero calls. Defaults are capped
at 50 selector calls and 8,000 reserved output tokens per UTC day. Failed calls
consume their reservation, preventing a retry loop from spending through the
ceiling. The ledger lives under ignored
`data/private/` and contains no question text or question hash.

Routing metadata contains only path, tier, reason, configured model alias,
call count, provider-reported token counts and verifier status. A public service
must add authenticated server-side enforcement, rate limits and aggregate
latency/cost monitoring before opening the kill switch.

## Current limitations

- Routing does not expand the six registered answer classes. Opus cannot turn
  an absent methodology fact catalog into a licensed open-ended answer.
- A model may misunderstand intent; explicit channel binding prevents entity
  invention, while any remaining ambiguity can still produce a safe but
  unhelpful refusal.
- Questions are sent to the configured provider when models are enabled. A
  public interface needs a privacy notice and must discourage personal data.
- The file ledger is appropriate for the local single-host adapter, not a
  horizontally scaled service, and its lock is POSIX-only. A shared
  transactional budget store is required before multi-instance deployment.
- Better models improve classification, not the truth or coverage of IGRM's
  underlying evidence.

## Public-deployment gates

The model path remains closed until the existing evidence-assistant gates are
met and, additionally: model IDs and provider retention terms are reviewed;
the selector is evaluated on a frozen labelled question set; every tier's
abstention, wrong-intent and wrong-channel rates publish; prompt-injection and
Unicode adversaries pass; the server budget cannot be bypassed by concurrency;
and an operator kill switch is tested end to end.
