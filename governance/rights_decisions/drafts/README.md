# Unsigned rights-decision drafts

Nothing in this directory is authority. These are drafts prepared for the
founder to review and sign; a decision only becomes real when a signed
`.sig` exists beside a decision artifact in the parent directory AND the
registry row in `governance/source_rights_registry.json` points at it.

Nothing enumerates this directory. Decisions are located by explicit
`decision_artifact_path` from the registry, so a file sitting here cannot
be picked up as a grant by accident.

## How each was produced

Each source's terms were fetched and read, a decision drafted
conservatively from what the terms actually say, and then a SECOND
reviewer attacked the draft looking for overclaiming — a permission the
terms do not grant — fetching the terms independently rather than
trusting the first reading.

`_draft_only.permitted_uses_as_drafted` and
`..._after_verification` show where those two disagreed. Where they
disagree, the verified set is what the artifact carries.

## Read `_draft_only` before signing anything

- `terms_confidence` — `terms_read_directly`, `terms_inferred`, or
  `terms_unavailable`. Two sources are `terms_unavailable`
  (`imf_portwatch`, `cow_mids`): their terms pages could not be reached,
  so they grant NOTHING and must not be signed until someone reads them.
- `adversarial_verdict` — `SAFE`, `UNDERCLAIMS`, `OVERCLAIMS`,
  `UNVERIFIABLE`.
- `unresolved_for_founder` — what the drafter could not settle alone.

## The three that need your judgement, not just your signature

**`india_ogd_port_trade_2019_20` — OVERCLAIMS.** The draft claimed
`publish_extract`; the verifier found the terms do not support it. The
artifact carries the reduced set. This is the one the adversarial pass
caught.

**`gdelt_events_v1` and `gdelt_gkg_v2` — UNDERCLAIMS, and this one is
load-bearing.** The drafts granted only `model_processing`. The verifier
found that too narrow against terms which grant "unlimited and
unrestricted use ... of any kind", and — more importantly — that signing
them as drafted would leave `docs/data/event_ledger.json` permanently
blocked, because its release gate requires `cite_metadata` and
`publish_derived_value`. The artifacts carry the widened set. Widening is
the verifier's judgement, so confirm it before signing.

`yahoo_finance`, `jodi_oil` and `ai_gpr_dataset` all came back with an
empty `permitted_uses` from a direct reading of their terms. An empty
grant is a real outcome, not a failure to decide.
