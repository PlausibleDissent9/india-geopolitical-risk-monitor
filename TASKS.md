# IGRM Max — execution worker ledger

Single source of truth for the Max-execution worker run. One task per session.
Operating rules: refusal-first, minimal reversible changes, do not push/merge/deploy,
claim no more than code proves, validate every gating change with a negative case.

Local-only: commits are made but NOT pushed (per operating rule). `origin/main`
is unchanged from `331a807`; three prior commits sit local and unpushed
(drift lane fix, typed-canonical perf fix, Product Compiler first slice).

Legend: TODO / DOING / DONE / BLOCKED(reason).

---

## T1 — Product Compiler contract must not claim refusal codes the runtime cannot raise
Status: DONE (local commit; NOT pushed)
Priority: highest (violated "claim no more than code proves", in freshly-built code)
Defect: `governance/product_manifest_contract.json` listed 15 refusal codes;
`src/product_manifest.py` raised 12. Unraised: `compilation_edge_not_recomputed`,
`compilation_nondeterminism_detected`, `compilation_release_mismatch`.
Fix (smallest safe change): added `verify_compilation(external, source, manifest)`
which RECOMPUTES a ProductCompilation from committed bytes and compares release
ref / every edge set / record digest, raising exactly the three codes on
divergence. An external compilation is reproduced, never trusted.
Files changed: `src/product_manifest.py`, `tests/test_product_manifest.py`, `TASKS.md`.
Commands run: `pytest tests/test_product_manifest.py -q` (18 passed),
`ruff check` (clean), `mypy src/product_manifest.py` (clean).
Assertions: +4 tests — one positive (faithful external compilation reproduces)
and one focused negative per new code (tampered release ref -> release_mismatch;
dropped edge -> edge_not_recomputed; tampered digest -> nondeterminism_detected);
plus `test_every_contract_refusal_code_is_reachable_by_the_runtime` now asserts
contract codes == reachable codes (15 == 15), so the over-claim cannot recur.
Gates hit: pytest/ruff/mypy all pass. Not shipped (do-not-push rule).

## T2 — Second scope predicate `scope:objects_touching_event`
Status: DONE (local commit; NOT pushed)
Design listed it (design/product_manifest_and_correction_closure.md §10).
Fix: registered `scope:objects_touching_event` in the contract only —
`compute_scope` already generalized over match_object_type/binding_parameter,
so NO runtime change was needed (smallest safe change confirmed).
Files changed: `governance/product_manifest_contract.json`,
`tests/test_product_manifest.py`, `TASKS.md`.
Commands run: `pytest tests/test_product_manifest.py` (19 passed),
`ruff check` (clean).
Assertions: new test compiles a 24-clause event-scoped product and asserts its
correction closure catches a supersede of that event; the inventory-lock test
`test_contract_is_deny_by_default_and_loads` was moved to the new 2-predicate
set in the SAME change (existing test correctly caught the addition — not
loosened to a subset check).
Gates hit: pytest/ruff pass. Not shipped (do-not-push rule).

## T5 — Every ProductManifest refusal code must have a dedicated triggering test
Status: DONE (local commit; NOT pushed)
Codex acceptance test #5 (design §9): "every refusal code reachable by a test."
Added a focused negative case that actually TRIGGERS each of the four codes that
previously had none: wrong scope binding key -> manifest_scope_binding_not_in_domain;
duplicate clause id in the universe -> manifest_scope_not_recomputable; a synthetic
100_001-clause universe -> manifest_universe_exceeds_bound; empty artifact digest
-> manifest_artifact_digest_mismatch. All 15 contract codes now have a triggering
test, so the reachability set-assertion is backed by real firing, not just a list.
Files changed: `tests/test_product_manifest.py`, `TASKS.md` (no runtime change).
Commands run: `pytest tests/test_product_manifest.py` (23 passed), `ruff` (clean).
Gates hit: pytest/ruff pass. Not shipped (do-not-push rule).

## T3 — Codex B2: Atlas Max join certifies an unpublished world
Status: BLOCKED(codex-lane) — engine files are Codex's; audit filed at
`analysis/max_join_audit_2026-08-10.md`, reported in `.agents/from-claude.md`.
Not actionable by this worker without touching Codex-owned engine code.

## T4 — Verify lane recovery after the perf fix lands
Status: BLOCKED(do-not-push) — the perf fix (local commit `3f593cb`) recovers
the nowcast/morning gate margin, but confirming recovery requires the commit on
`origin` and a lane run. Cannot push. Human action needed to push, then observe.
