# Comparator benchmark protocol

**Status:** design/protocol draft. Unsigned; binds nothing until adopted.
**Assigned:** Codex execution list item 8, 2026-08-10.
**Precedent:** the registered AI-GPR benchmark
(`analysis/ai_gpr_benchmark_registration.json`, frozen 2026-08-07,
`.ots`-anchored, executed by `src/ai_gpr_benchmark.py` at pinned inputs).
This document generalises what that execution did right into rules any
future comparator benchmark must satisfy, and names the places where the
precedent's own honesty must not be lost in generalisation.

## 0. What a benchmark is for, and is not for

A comparator benchmark measures **relationship**, never rank.
`docs/vs-gpr.html` already forbids "outperforms", "more accurate",
"validates", "confirms IGRM measures risk" **under every outcome**, and the
AI-GPR payload embeds that as `_meta.forbidden_claims`. This protocol
inherits both, unconditionally: a benchmark whose favourable outcome would
be publishable as superiority is misregistered from the start.

## 1. Preconditions to registration

1. **Source pin.** Exact file URL, sha256, `accessed_at_utc`, `data_through`,
   and a revision note stating the provider can revise and that the hash is
   therefore load-bearing. A provider page is not a pin; bytes are.
2. **Rights.** The comparator source must be `approved` in the signed-rights
   registry for the uses the benchmark needs, before registration. The
   AI-GPR precedent predates the registry's current posture; new benchmarks
   do not inherit that grandfathering.
3. **IGRM input pin.** `history.csv` (and any episode list used) by sha256.
   A benchmark against "current" IGRM is a benchmark against a moving
   target; the registration freezes both sides.
4. **Analysis freeze.** The complete analysis script committed, its sha256
   and the base commit recorded in the registration, before any joint
   statistic is computed. The script declares the primary statistic, the CI
   method and block lengths, sample-construction rules, and the exact
   decision language for every outcome cell.

## 2. The attestation, kept honest

The precedent's most valuable lines are its confessions, and every future
registration must carry equivalents, filled truthfully:

    data_was_already_in_hand:            true/false
    provider_charts_could_have_been_seen: true/false
    blindness_claimed:                   almost always false
    statistic_computed_before_freeze:    must be false, and is the one
                                         entry that voids the registration
                                         if it cannot be truthfully false
    founder_review_limit:                who did NOT line-edit or sign
    ai_assistance_disclosed:             true, with roles

A registration that claims blindness it cannot prove is worth less than one
that documents its sight. The AI-GPR registration says the founder did not
line-edit the protocol before freeze — that sentence survives because it
was written down at freeze time. This field set makes that survival
structural.

## 3. Registered interpretation, before results exist

The registration must contain, verbatim, the sentence that will be
published for each region of outcomes — strong positive, weak, null,
negative — so no outcome arrives without its words already frozen. The
AI-GPR decision language ("share a common component but are far from
redundant") was frozen this way. Discussion frames (corpus difference,
construct difference, anchoring difference) are registered alongside, and
published analysis may not introduce a new frame without labelling it
post-hoc.

## 4. Timestamping and execution

- The registration file is `.ots`-anchored at freeze.
- Execution happens in CI or an equally logged environment, from the pinned
  bytes, by the frozen script, once. Re-runs are reproductions, not
  re-rolls: same inputs, same statistic, byte-equal output.
- The payload publishes the point estimate **with its interval in the same
  object**, the sample sizes, the robustness windows, the forbidden-claims
  list, and the registered decision language. (Today's rule from the claims
  sweep applies: the interval travels with the estimate on every rendered
  surface, enforced by `tests/test_headline_numbers_carry_their_companion.py`.)

## 5. Revision and re-registration

- Provider revises its file → the old benchmark stands as a statement about
  the pinned vintage; a new benchmark requires a full new registration.
  No "refreshing" a result under an old registration id.
- IGRM restates history (vintage diff shows changed values) → same rule,
  same direction.
- A registration, once frozen, is never edited. Errors get a dated
  correction entry beside it, per the corrections doctrine.

## 6. Refusal conditions for the executing lane

    benchmark_source_hash_mismatch      pinned bytes not on disk
    benchmark_registration_missing_ots  no timestamp proof
    benchmark_rights_not_approved       registry state short of the uses
    benchmark_statistic_precomputed     any joint statistic in git history
                                        predating the freeze commit
    benchmark_decision_language_absent  outcome cell without frozen words
    benchmark_forbidden_claim_in_payload  the deny-list itself missing, or
                                        a claim matching it in any _meta

`benchmark_statistic_precomputed` is checkable: the freeze commit is
recorded, and the executing lane greps the repository history before it for
the statistic's identifiers. Imperfect — a statistic computed off-repo is
invisible — which is exactly why the attestation of §2 exists and why the
protocol never claims blindness on its behalf.

## 7. Acceptance tests before this protocol is adopted

1. Re-run the AI-GPR benchmark under the protocol's checks; every check
   passes on the existing artifacts (this is a validation of the checks
   against a known-good execution, not a re-roll of the result).
2. A fixture registration with one attestation flipped to a lie the tree
   can detect (statistic in history before freeze) is refused.
3. A fixture payload whose `_meta` contains "outperforms" is refused by
   the same lint that already enforces forbidden claims site-wide.
4. The registration schema round-trips through the typed-canonical
   profile, so a registration can be digest-pinned and `.ots`-anchored
   byte-stably.

## 8. Open question for Codex

Whether §6's history-grep for precomputed statistics should extend to the
*analysis branch* namespace (agents' scratch commits) or only `main`. Main-
only is cheap and honest about its limits; all-refs is stronger and slower,
and could be gamed by rebasing anyway. I lean main-only with the limit
stated in §2's attestation, consistent with "state the boundary rather than
imply the stronger check".
