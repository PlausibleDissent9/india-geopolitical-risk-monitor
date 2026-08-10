# Source-rights decision packets

Draft decision artifacts for the signed-rights registry
(`governance/source_rights_registry.json`). One file per source.

## Lifecycle, stated so it cannot be blurred

1. An agent may **draft** a packet. A draft binds nothing, permits nothing,
   and changes nothing in the registry. Every draft carries
   `DECISION: UNSIGNED — NO FORCE` until the moment it does not.
2. Only the founder signs. Signing means: filling the decision block, signing
   the artifact's bytes, and updating the registry entry's `decision_state`,
   `decision_id`, `signer_id`, `decision_artifact_path`,
   `decision_artifact_sha256` and `decision_signature_path` **in the same
   commit**. A registry that points at unsigned bytes is a defect.
3. Until step 2, `default_policy: deny` governs and `permitted_uses` stays
   empty. Machinery that consults the registry must keep refusing exactly as
   it refuses today.

An agent that edits `permitted_uses`, `decision_state`, or any signature
field has exceeded its authority — the mission's standing rule is *prepare
packets, never sign*.

## What a packet must contain

- Registry identity: `source_id`, provider, the registry's own recorded
  access basis and notes (the packet quotes the registry's recorded review,
  not terms the drafter has independently reinterpreted).
- Uses **requested**, enumerated and mapped to actual pipeline behavior.
- Uses **explicitly not requested**, so silence cannot widen scope later.
- Attribution plan and outage/revocation posture.
- An empty decision + signature block.

## Proposed `permitted_uses` vocabulary

Registered here so packets and future registry entries share one language;
also unsigned, also carrying no force until a signed decision uses it:

    retain_committed_extract     keep the hash-pinned bytes already in git
    derive_published_aggregates  publish derived tables/series with attribution
    quote_attributed_figures     cite individual figures in prose with source
    redistribute_in_audit_bundle include the extract in offline audit bundles
    redistribute_raw             re-host the source's own files wholesale
