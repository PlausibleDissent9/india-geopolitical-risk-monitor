# Evidence-locked IGRM assistant — implementation contract v0.1.0

Status: **implemented safety core; no public endpoint; no model authorized**

Effective: 2026-08-08

## Product objective

IGRM Max includes an ask-anything interface. The feature is not cancelled after
the daily-brief incident; its trust boundary is changed. The assistant should
eventually make the index easier to use for researchers, businesses, journalists
and public readers while remaining no less auditable than a downloaded JSON
payload.

The answer surface must never depend on a user accepting that a language model
"probably" copied a number correctly. Every publishable sentence is a
deterministic function of registered fact identifiers whose exact source bytes,
JSON pointers, types, units, denominators and dates are reverified at render
time.

## Architecture

```text
user question
      |
      v
intent/fact selector  (deterministic now; model may replace only this box)
      |
      v
strict plan JSON      (template_id + registered fact_ids; no prose or values)
      |
      v
evidence verifier     (source hash, pointer, type, unit, denominator, date join)
      |
      +---- any mismatch ----> stable refusal
      |
      v
registered renderer   (deterministic text + fact-level evidence ledger)
```

Only the first box may later use a model. Model output is parsed with an exact
field allowlist. It has no field through which to supply prose, literal numbers,
dates, entity names, citations, calculations or denominators. The renderer never
interpolates the user's text.

## Implemented v0.1 surface

`src/evidence_assistant.py` currently supports four bounded question classes:

1. latest 7-day headline;
2. one channel's latest 7-day reading;
3. a deterministic comparison of exactly two channel readings; and
4. the instrument definition carried by `latest.json`.

It refuses forecasting, price direction, investment advice, trading
recommendations and hedging questions before reading a data payload. Questions
outside the registered grammar receive a finite, non-personalized refusal. The
local command is:

```bash
python -m src.evidence_assistant "What is the latest IGRM headline?"
```

The returned JSON contains the answer, its completed news day, template ID,
every fact ID and, for each fact, the source file, RFC 6901 pointer, source
SHA-256, unit, denominator and public citation URL.

## Typed fact contract

A fact is not merely a value. Its registered identity binds:

- repository-relative source path;
- JSON pointer;
- scalar type;
- semantic kind;
- unit;
- denominator;
- completed-news-day vintage;
- public citation URL; and
- SHA-256 of the exact source bytes.

At render time the verifier re-opens the source, confirms it is inside the
repository root, checks the exact digest and pointer value (including Python
type, so `true` cannot masquerade as `1`), validates numeric range and
finiteness, and checks that every fact in the sentence has one identical
vintage. Metadata such as the denominator is checked against the code registry,
not trusted from the proposed answer plan.

## Threat model and refusal rules

The core is designed to fail closed against:

- prompt injection or a request to repeat arbitrary text;
- model-invented prose, facts, numbers, entities or links;
- stale catalogs after a payload changes;
- missing or redirected JSON pointers;
- boolean/number and string/number type confusion;
- non-finite or out-of-range readings;
- swapped units or denominators;
- score/evidence joins across different news days;
- unknown or duplicate fact IDs;
- unauthorized templates;
- ambiguous multi-channel questions; and
- forecast, advice, hedge, buy/sell or price-direction requests.

The system does not claim to validate open-ended geopolitical interpretation.
It removes that interpretation from the publishable path.

## Conditions before a model or public endpoint

This core may not be described as a public chatbot yet. A successor slice must
meet all of the following before deployment:

1. Register a finite intent taxonomy and a versioned fact catalog for the
   additional payloads it exposes.
2. Keep model output limited to the strict plan schema; publish no raw model
   prose, chain of thought or tool output.
3. Add receipts only after their latest-day, display-cap, title-key and
   score-denominator semantics are separate fact types.
4. Add historical answers only with explicit date-window and missing-data
   facts; never silently substitute the latest vintage.
5. Add business-exposure answers only from the registered sector mapping and
   clearly labelled descriptive associations.
6. Add per-answer rate, latency, abstention and verifier-failure telemetry that
   contains no question text or personal data.
7. Red-team prompt injection, fact-ID substitution, date drift, denominator
   swapping, stale-source races and malformed Unicode with a frozen adversarial
   suite.
8. Put a hard model-spend ceiling and global kill switch outside the model's
   control.
9. Obtain independent review of the intent selector and all new templates.
10. Publish a corrections route and versioned answer schema before the first
    external user.

## Maximum-version roadmap

After those gates, the same architecture can expand without weakening the
instrument:

- conversational follow-ups represented as prior fact IDs, not copied prose;
- receipts and tier-one-source retrieval with exact evidence-card citations;
- researcher mode with API paths, hashes and downloadable query manifests;
- business mode over registered sector/corridor mappings;
- multilingual question classification while answers retain one canonical fact
  ledger;
- alerts that link back to the exact fact bundle that triggered them; and
- an optional model selector that improves language understanding but cannot
  change a rendered claim.

The feature is therefore sequenced, not sacrificed: user breadth grows at the
selector and fact-catalog layers while the evidence verifier remains the fixed
publication boundary.
