# Adversarial review: OGES Scenario Proof

**Commit under review:** `ceb37c4` (head of the Scenario Proof slice;
`7d34012` → `f28b9e4` → `ceb37c4`). CI #518 green. Hash-stable before review.
**Reviewer:** Claude (agent). **Date:** 2026-08-09.
**Assigned vectors:** causal/feasibility overclaims, registry/hash
substitution, stale-input laundering, rival/falsifier loopholes,
mobile/public-copy drift.

**Verdict: PASS_WITH_FOLLOWUP.** One finding, no P0/P1. Detail in §3.

---

## 1. What the author's own suite already closes

Re-ran independently: `test_scenario_proof.py`, `test_capability_attestation.py`,
`test_evolution_engine.py` — **55 passed**.

Four of my five assigned vectors are directly covered by tests already in the
commit, and I could not find daylight in them:

| Assigned vector | Covering test |
|---|---|
| stale-input laundering | `test_stale_inputs_are_visible_and_never_called_satisfied` |
| " | `test_unknown_freshness_makes_constraint_falsifier_unevaluable` |
| registry substitution | `test_runtime_shock_registry_must_equal_profile_bound_registry` |
| hash substitution | `test_profile_binds_every_normative_byte_and_preserves_shock_1_0` |
| forged / resealed output | `test_resealed_output_mutation_fails_full_recomputation` |
| " | `test_supplied_compilation_is_recomputed_before_any_proof` |
| feasibility overclaim | `test_upstream_abstention_is_visible_and_never_called_satisfied` |
| capability overpromotion | `test_adversarial_case_registry_is_complete_and_capability_is_not_overpromoted` |

The claim vocabulary is disciplined and does the work in the names
themselves: `compatible_with_compiled_scenario_not_supported`,
`incompatible_with_compiled_scenario_not_real_world_falsified`,
`hypothetical_scenario_feasibility_not_real_world_feasibility`. Seven
guardrails are pinned false, including `causal_attribution_performed`,
`probability_assigned` and `objective_optimized`.

`_readiness()` degrades correctly: a stale hop yields `stale_inputs`, an
unknown policy yields `unknown_freshness`, and a falsifier over a constraint
that is not `current_inputs` returns `not_evaluable`, which resolves the
hypothesis to `indeterminate_missing_registered_result` rather than to
compatible. **Staleness cannot buy a clean verdict.** That is the right
direction of failure.

The registration-time honesty is also already stated rather than hidden:
`pre_scenario_registration_time_is_self_declared_not_independently_timestamped`.

## 2. Rival structure: the obvious loophole is closed

`_hypothesis_compatibility()` takes a **set** of falsifier statuses. An empty
set contains neither `triggered` nor `not_evaluable`, so a hypothesis with no
falsifiers would fall through to *compatible* — the classic unfalsifiable
rival.

It cannot happen. `mechanism-hypothesis.schema.json` sets `"minItems": 1` on
`falsifiers`, and `_validate_request` additionally enforces:

- `scenario_proof_rival_asymmetric` — if A names B a rival, B must name A
- rivals sorted, never self-referential, subset of known hypothesis ids
- falsifiers sorted and unique
- predicates drawn from a `default_policy: deny` registry, with
  `allowed_expected_values` enumerated per predicate

## 3. FINDING — symmetric rivalry does not imply symmetric falsifiability

**Severity: follow-up, not a defect.** The code does exactly what it claims.
The gap is between what the output says and what a reader will take from it.

Every structural rule constrains the **form** of a falsifier. Nothing
constrains its **force** — whether the falsifier could have fired at all
against the scenario actually compiled.

Demonstrated against the real `_falsifier_result` and
`_hypothesis_compatibility`, with the compiled constraint at
`all_registered_values_satisfy`:

| Hypothesis | Registered falsifier expects | Status | Verdict |
|---|---|---|---|
| A | `all_registered_values_satisfy` | `triggered` | `incompatible_with_compiled_scenario_not_real_world_falsified` |
| B | `no_registered_values_satisfy` | `not_triggered` | `compatible_with_compiled_scenario_not_supported` |

Both are structurally valid: one falsifier each, drawn from the registry,
expected values inside `allowed_expected_values`, and symmetric rivalry can
hold between them. **Only A was ever at risk.** B's falsifier could not fire
against this scenario, and the published output contains nothing that would
let a reader tell the two cases apart.

The name `compatible_with_compiled_scenario_not_supported` is already
carefully weak. But a reader comparing rivals side by side will still infer
that B survived something. Here, B survived nothing.

### Suggested remedy (cheap, and computable)

For `predicate:scenario.constraint_interval_relation_equals` the outcome
space is enumerated — four values, and the compiled scenario determines which
obtains. So per falsifier you can publish whether its expected value was
**reachable** given that constraint, and per hypothesis whether **any** of
its falsifiers had discriminating power.

Something like `falsifier.could_have_fired: true|false|not_evaluable`, and a
hypothesis-level `discriminating_falsifier_count`. A rival whose count is
zero is then visibly untested rather than invisibly safe, without inventing
any judgement about hypothesis quality — which the system correctly refuses
to make.

This does not make registrations honest. It makes a dishonest one legible,
which is the same move the project already makes everywhere else.

## 4. Not executed

**Mobile / public-copy drift was not tested**: this slice publishes no public
page or copy that I could find, so there is no rendered surface to drift from
the payload yet. When one lands, that vector is still open.

Also untested here: file-swap races under concurrency, and rights expansion
beyond what the trace review already covered.

## 5. Standing caveat

This is an AI adversarial review by an agent working on the same project as
the code's author, with the same blind spots available to both. It is not
external certification and must never be described as one. The single finding
above is an epistemic legibility gap, not a security defect: nothing here
lets a forged, stale, or resealed input produce a clean verdict.
