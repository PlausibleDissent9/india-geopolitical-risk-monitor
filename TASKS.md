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
Status: TODO
Design already lists it (design/product_manifest_and_correction_closure.md §10).
Additive; strengthens the closure over event-scoped products.

## T3 — Codex B2: Atlas Max join certifies an unpublished world
Status: BLOCKED(codex-lane) — engine files are Codex's; audit filed at
`analysis/max_join_audit_2026-08-10.md`, reported in `.agents/from-claude.md`.
Not actionable by this worker without touching Codex-owned engine code.

## T4 — Verify lane recovery after the perf fix lands
Status: BLOCKED(do-not-push) — the perf fix (local commit `3f593cb`) recovers
the nowcast/morning gate margin, but confirming recovery requires the commit on
`origin` and a lane run. Cannot push. Human action needed to push, then observe.
