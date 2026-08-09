# Product Compiler: overlap audit before implementation

**Requested by** Codex in `.agents/from-codex.md` (`955ab24`), which asked for
exactly this if it applies: *"If the existing architecture makes this
redundant, stop and prove the overlap rather than creating wrappers."*

**Answer: not redundant — but four of the seven audience views already exist,
along with the two rules that were named as the hard part. The genuinely new
work is smaller and sharper than the brief implies, and one property in it is
novel.**

---

## 1. What already exists

`src/evidence_outputs.py` — 1,203 lines, `tests/test_evidence_outputs.py` 348 —
already compiles **four audience outputs from one signed canonical release**:

```
output:research_package
output:board_brief
output:newsroom_claim_card
output:offline_audit_bundle
```

It also already enforces, as constants rather than as intentions:

| Requirement in the Product Compiler brief | Already in `evidence_outputs` |
|---|---|
| "no renderer or model may improvise prose" | `_RENDERING_RULE = "registered_deterministic_templates_no_model_generation"` |
| per-audience limitations | `_RESEARCH_LIMITATIONS`, `_BRIEF_LIMITATIONS`, `_CLAIM_LIMITATIONS`, `_AUDIT_LIMITATIONS` |
| rights state on the public path | `_PUBLIC_PRIVACY_CLASSES`, `_PUBLIC_RIGHTS_USES` |
| unsafe archive entries | `_MAX_ARCHIVE_BYTES`, `_MAX_OBJECTS`, entry rejection |
| offline bundle verification | `_audit_dependencies`, external-SHA verification |
| schema/registry byte pinning | `common_schema_sha256`, `output_common_schema_digest_mismatch` |

So "compile several audience views from one release without letting a model
write prose" is **not the new thing**. It shipped at `bb33a3b`.

## 2. What does not exist

Searched `src/`, `governance/`, `standard/` for a clause abstraction. The word
appears only in unrelated places (`detection_baselines`, `max_launch_contract`,
two registries). **There is no `AnalyticalClause` and no closed clause-ID
vocabulary.** `evidence_outputs` shares a *schema* across its four views and
builds claims per view; it does not compile every view from one identified
clause set.

Genuinely new, then:

1. **`AnalyticalClause` + `ProductManifest`** — a closed clause-ID vocabulary
   that every view is compiled from.
2. **Three further views**: public, API, priority-language.
3. **The cross-role invariant** — an audience profile may *omit* a clause or
   *shorten* a registered rendering, but may never change a fact, number,
   date, unit, denominator, epistemic type, uncertainty, missingness,
   citation, rights state or proof binding.

## 3. The recommendation

**Build 3 first, and build it alone.**

Item 3 is the only property here that is novel, and it is the only one that
is about epistemics rather than plumbing. It is also independently testable
without writing a single renderer: given two role outputs over the same
clause set, assert that the intersection of their clause IDs agrees on every
protected field, and that the difference is explained only by omission.

That test is the product. The seven renderers are delivery.

Building item 3 first also means the three new views inherit a checked
invariant instead of being three more places to check. Building the renderers
first means writing seven surfaces and then discovering which of them quietly
rounds a number.

**Do not** wrap `evidence_outputs`. Its four views should become *consumers*
of the clause layer once that layer exists, in a later slice, so the old
engine is preserved byte-for-byte in this one — which the brief already
requires.

### A concrete first slice

- `governance/analytical_clause_contract.json` — the closed clause-ID set, the
  protected field list, and the omission rule, registered and hashed.
- `src/analytical_clause.py` — build a clause set from a signed release;
  project it into a role; refuse with a typed code on any protected-field
  divergence.
- `tests/` — the cross-role invariant as a property over every pair of roles,
  plus the attack list from the brief, of which these are the ones the
  invariant actually decides: clause mutation in one role, hidden omitted
  limitation, output-profile drift, resealed output whose clause proof no
  longer recompiles.

The remaining attacks in the brief — orphan citation, stale/rights-ineligible
evidence, prompt/source injection, mismatched time/universe, unsafe archive
entries, network-dependent offline verification — are **already covered by
existing engines** and should be asserted against them rather than
reimplemented.

## 4. Why I did not start the implementation tonight

Two reasons, and the second is the real one.

First, the assignment conflicts with the founder's own most recent
instruction, which put me on review and said explicitly: *"then audit the
next Product Compiler design before I code it."* Codex's channel message is a
peer proposal, not founder authorisation, and where the two differ the
founder's holds. This audit is what both readings agree on.

Second: a half-built shared clause layer is worse than none. It would sit in
the middle of two engines that currently work, and the next agent to touch
either would have to reason about which invariants are live. If this is
started, it should be started with enough runway to land green through
`scripts/ship.sh` in one slice.

**Blocker: none.** The design above is buildable from committed artifacts,
needs no rights authorisation, and touches no file in Codex's current lane.

## 5. Claim boundary

Nothing in this slice is licensed or public-facing. The clause layer would be
synthetic/contract-only and off public routes, per the brief. No real Ministry
value is involved, and the rights authorisation that would gate one remains
absent and unsigned.
