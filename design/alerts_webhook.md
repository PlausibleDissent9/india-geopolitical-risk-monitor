# Alerts and webhooks: design (unsigned — nothing here is live)

Status: DESIGN. No alert has ever been emitted. The founder signs the
trigger thresholds before the first one is; until then this file is a
proposal, and the site makes no alert promise anywhere.

## Why alerts, and why carefully

Subscribers and institutional readers have asked what "watch the
index" means operationally. Today the answer is: open the site, or
read the weekly note. An alert layer answers it better — but it is
also the easiest place for this project to quietly start editorializing
("we thought you should know") or spamming. Two standing promises
bind the design:

1. **"One email a week."** The newsletter promise is a contract.
   Alerts therefore do not use email at all in phases 0–1. An email
   alert tier would need its own explicit, separate opt-in and a
   founder decision — deliberately out of scope here.
2. **No forecasts.** An alert describes a move that has already
   happened in the published data, with its uncertainty attached.
   It never says what will happen next.

## Trigger conditions (proposed, to be registered on signing)

All conditions are computed from already-published payloads
(`history.json`, `uncertainty.json`, `latest.json`) after the daily
publish — an alert can never disagree with the site.

- **T1, band-separated daily move.** A channel's Wilson 95% sampling
  band for the new day does not overlap the previous day's band. This
  is the exact arithmetic that separated the real china_east crash
  (Aug 5: [0.4, 36.4] vs Aug 4: [45.0, 90.5]) from same-day noise. No
  point-change threshold can do this honestly on a sampled series.
- **T2, composite percentile crossing.** The composite crosses its
  trailing 90th percentile in either direction, and the crossing
  survives the band (both band edges on the same side of the
  threshold). The percentile, not a raw level, keeps the trigger
  meaningful across regime shifts in corpus size.
- **T3, integrity events.** The morning publish misses its contract
  window, or the dual-computation audit fails. The instrument's
  failures alert the same channel its successes do — fail-loud is a
  feature commitment, not tooling hygiene.

Trigger values (95%, 90th, contract time) are the registered
parameters. Changing any of them after the first alert requires an
append-only amendment entry in this file, same as a dictionary edit.

## Delivery, phased

**Phase 0 — `alerts.json` (poll model; no infrastructure).**
The daily pipeline appends to `docs/data/alerts.json`: an array of
alert objects, newest first, capped at 90 days. Consumers poll it.
This costs nothing, works under the site's strict CSP (it is just
another static payload), enters the API contract like every payload,
and lets the trigger logic run in production for weeks before anyone
builds delivery on top — the triggers earn trust before they earn
push.

```json
{
  "id": "2026-08-05-china_east-T1",
  "date": "2026-08-05",
  "type": "band_separated_move",
  "channel": "china_east",
  "direction": "down",
  "score": 4.5,
  "band": [0.4, 36.4],
  "prev_score": 74.3,
  "prev_band": [45.0, 90.5],
  "emitted": "2026-08-06T00:31:00Z"
}
```

**Phase 1 — webhook push.** A VPS cron step, after the morning
publish verifies, POSTs each new alert object to registered endpoint
URLs.
- Registration is founder-managed (an email to the founder; he adds
  the endpoint + a generated secret to a file on the VPS, outside the
  repo). No self-serve signup, no accounts, no third-party services
  in the loop.
- Authenticity: `X-IGRM-Signature: sha256=<HMAC-SHA256(secret, body)>`
  so receivers can verify origin. Secrets never enter the repo.
- Retries: 3 attempts, 30s/120s/600s backoff; a dead endpoint is
  dropped from the day's queue and logged, never retried forever.
- Idempotency: the `id` field is stable; receivers dedupe on it.

**Phase 2 — email tier. Not designed.** Explicitly deferred until the
founder decides whether a second email product can coexist with the
one-a-week promise. This file records only that the question exists.

## What this design refuses

- Alert copy with adjectives. The payload carries numbers and band
  arithmetic; any prose is generated from the same registered
  template every time.
- Post-hoc threshold tuning ("too many alerts this month, raise the
  bar quietly"). Amendments are append-only and dated.
- Predictive framing, including in field names — `direction` is the
  direction of the completed move, and stays that way.
- Third-party notification services (they would put an unaudited
  dependency between the instrument and its subscribers).

## Implementation order when signed

1. `src/alerts.py` computing T1–T3 from published payloads; unit
   tests with synthetic histories for each trigger and each
   non-trigger (band-overlap near-miss cases).
2. Contract bump adding `alerts.json`; published-promises test if any
   page mentions alerting.
3. Four weeks of Phase-0 production observation; the founder reviews
   emitted alerts against the tape.
4. Phase-1 webhook step on the VPS, dry-run mode first (logs, no
   POSTs), then live.

## Founder decisions required before anything ships

- [ ] Sign the three trigger definitions and their parameters
- [ ] Confirm 90-day retention for `alerts.json`
- [ ] Decide whether Phase 0 ships alone first (recommended) or waits
      for Phase 1
