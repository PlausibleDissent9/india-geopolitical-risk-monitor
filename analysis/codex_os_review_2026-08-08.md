# IGRM cross-review — origin/main 86b7c53..dd63bba (2026-08-08)

**No DEFECT reddens a scheduled run.** Full non-live suite at tip dd63bba:
**514 passed, 0 failed, 0 errors** (clean clone, exit 0). One DEFECT found, in
f30771d, is doc-level and CI-invisible: the spec asserts there is no public
assistant seven minutes after the public assistant shipped.

Method: read-only. `git fetch` + plumbing reads against the shared repo (whose
worktree is mid-flight with uncommitted Codex work — nothing written, staged, or
checked out there). All execution in per-commit `git archive` extracts and a
detached clean clone under the session scratchpad, with independently written
probes and arithmetic — not by re-running the commits' own tests.

Scope: `git log 86b7c53..origin/main` = exactly the two commits below.
dd63bba **is** the tip of origin/main; nothing newer exists, bot or human. Local
HEAD is 86b7c53, i.e. both commits are unpulled in the shared tree. Both are
authored **and** committed `Ishan Krishna <ishankrishna9@gmail.com>`, zero
trailers, zero Co-Authored-By, single-parent linear.

Standards input: `analysis/day_commit_review_2026-08-08.md`,
`analysis/slice_reviews_2026-08-08.md`, `analysis/slice_reviews_2026-08-08_batch2.md`
read in full from git objects (the worktree copies are deleted in the WIP).

---

## f30771d — Define the IGRM Max operating system — SOUND, one DEFECT (doc-level), two QUESTIONABLE

Three files: `IGRM_MAX_SPEC.md` (rewrite), `design/igrm_max_benchmark_contract.json`
(new), `tests/test_igrm_max_benchmark_contract.py` (new). No workflow, no `src/`,
no other test touched.

### Invariant consistency and agent authority — clean

The commit weakens no committed invariant, because it edits none: `GOVERNANCE.md`,
`scripts/gate.sh`, and every workflow are untouched. On the text, the spec is
uniformly **more** restrictive than the governance floor, never less:

- `:147` "Models may propose candidates. They may not create public ground truth."
- `:282-283` the assistant's model "may not supply public numbers, prose, dates,
  citations or confidence."
- `:436` "AI drafts and classifications are always identified in provenance."
- `:638` "No model-generated factual prose on a public path."
- `:433` "The founder signs construct definitions and public interpretations" —
  consistent with `GOVERNANCE.md:10-16`.
- Calibration: the spec never assigns labeling to a machine; `GOVERNANCE.md:15-16`
  ("Calibration rulings must be his personally") stands unchallenged.

Claims discipline is strong and self-policing: `:14-17` disclaims superiority
outright, `:514-516` makes every Part VIII row a target, and `:559-564` names the
institutional advantages IGRM does *not* claim to have surpassed (GPR's history,
ACLED's field network, ICRG's expert operation, the Baltic Dry Index's market
role). The machine contract is `status: target_only`, `default: unlicensed`,
`overall_superiority_claim_allowed: false`, every row `claim_allowed: false`.

**Founder eyes, one seam:** `:461-464` requires that no "label adjudication"
depend on "unreviewed single-person judgment" (dual control, recorded dissent),
while `GOVERNANCE.md:15-16` requires calibration rulings be the founder's
*personally*. Future institution vs current practice — `:461`'s "One person may
cover several functions during the build phase" softens it — but the two
sentences pull opposite ways on the same object. One clause reconciles them.

### DEFECT — IGRM_MAX_SPEC.md:76-78, a false negative claim about the project's own surface

The non-goals sentence reads: "There is no complete external precision/recall
result, comprehensive event frame, declared exposure universe, **public
assistant**, licensed forecast, government adoption or minted research DOI."

The public assistant exists, in this commit's own tree:

- `docs/ask.html`, added in `b12e2d0` at **13:09:22 IST**; this commit is
  **13:16:24 IST** — seven minutes later, with `b12e2d0` a verified ancestor.
- It is a served, sitemapped page: `src/sitemap.py:58-59` lists `ask.html` at
  priority 0.8 under the comment "The ask surface is the front door for
  non-technical readers." Title: "Ask IGRM, India Geopolitical Risk Monitor".
- `docs/data/assistant_answers.json` is a promised contract endpoint with
  `_meta.n_questions 23`, `n_answered 16`, `n_refused 7`.

The same file contradicts itself: `:579` (Program 0) instructs to "preserve the
evidence-locked assistant's closed truth boundary" — an instruction about
existing work.

Every other item in that sentence recomputes **true**: no complete external
precision/recall result; no comprehensive event frame; no declared exposure
universe (`docs/exposure.html` carries no universe/denominator/frozen language);
no licensed forecast; no government adoption; no minted IGRM DOI (the only DOI
anywhere is third-party, `10.1257/aer.20191823` in vs-gpr.html).

Nothing catches this: `IGRM_MAX_SPEC.md` sits in `MD_EXCLUDED`
(`tests/test_claims_discipline.py:62`, "the internal build spec, a working
document") — a **pre-existing** exclusion this commit did not touch, so no dodge,
but also no net. Breaks no CI and no scheduled run; it is wrong bytes in a public
repo, in the one paragraph whose entire job is to be conservative about what
exists. Fix: one clause.

### QUESTIONABLE 1 — dangling pointer to a section this commit deleted

The rewrite removed `### V.1 — DICTIONARIES` (present at `86b7c53:261`).
`tests/test_dictionaries.py:2` still cites "IGRM_MAX_SPEC.md section V.1" as the
authority for rules it enforces in CI. Same class as the day review's 8502180
DEFECT, lower blast radius: the substantive rules survive in their second home,
`methodology.md` §2 "Term selection and the ex-ante rule" (cited in the same
docstring, verified present, 19 dictionary references). No rule was lost — one of
two pointers rotted. One-line docstring fix.

### QUESTIONABLE 2 — the roster guard is one-directional, the message says "aligned"

The commit message claims "tests that keep the human and machine rosters
aligned." `tests/test_igrm_max_benchmark_contract.py:69-72` iterates **contract**
rows and asserts each name appears somewhere in the spec — a subset check, and a
substring match rather than table membership.

Demonstrated, not asserted:

- Appending a 13th row ("Fictional Sovereign Risk Meter") to the Part VIII table
  → **all three tests still pass**.
- Deleting a name from the spec → correctly **fails**.

Not vacuous otherwise (count pinned at 12, ids unique, `claim_allowed is False`
per row, https enforced, gates >= 3). Fix: compare against the parsed table, or
assert set equality both ways.

### Recomputed

- 12 contract benchmarks == 12 Part VIII table rows; symmetric set difference
  empty in **both** directions; all 12 names verbatim in the spec.
- `required_comparison_properties` == 10 (test floor `>= 10`).
- 3 gates per benchmark, all 36 period-terminated; all 12 `canonical_source`
  URLs https with 12 distinct hosts.

---

## dd63bba — Make public claim eligibility fail closed — SOUND

Ten files, all additions (+2165, −0): `src/publication_guard.py` (942),
`tests/test_publication_guard.py` (648), four `governance/` registries,
`design/publication_claim_guard.md`, `src/publication_transforms.py`, and the
dependency pins.

### It actually fails closed — 47 independent probes, zero passthrough

I wrote my own harness from the design contract (not copied from their tests):
build a genuinely valid bundle, break exactly one input, assert refusal.

**Baseline complete bundle → `eligible`. 38/38 broken-input probes REFUSED with
stable codes. Zero passthrough, zero crash, zero unstable exception.**

| Probe | Refusal |
|---|---|
| evidence bytes swapped after bundling (catalog→render race) | `fact_source_digest_mismatch` |
| declared value != evidence value | `fact_value_source_mismatch` |
| pointer to absent node / at whole document | `fact_pointer_missing` / `fact_pointer_invalid` |
| 6 prose-smuggling top-level fields (prose, narrative, citation, confidence, model_output, summary) | `bundle_fields_invalid` |
| extra field inside a fact | `fact_fields_invalid` |
| approved source, signer registry emptied | `rights_source_signer_unregistered` |
| forged 64-byte detached signature | `rights_source_decision_signature_invalid` |
| registry grants a use absent from the signed artifact | `rights_source_decision_artifact_mismatch` |
| signed decision artifact edited after signing | `rights_source_decision_artifact_digest_mismatch` |
| signer revoked before review date | `rights_source_signer_inactive` |
| rights decision expired at generation | `fact_source_rights_expired` |
| path escape via `..` / absolute path | `fact_source_path_invalid` |
| evidence reached through a symlink | `fact_source_symlink_forbidden` |
| duplicate JSON key / `Infinity` literal in evidence | `json_duplicate_key` / `json_non_finite` |
| cross-date join (evidence day != as_of) | `fact_temporal_join_invalid` |
| declared date contradicts evidence bytes | `fact_effective_date_source_mismatch` |
| evidence older than `max_current_age_days` | `fact_current_evidence_stale` |
| registry edited after bundling | `bundle_policy_digest_mismatch` |
| transformation implementation bytes changed | `transformation_implementation_drift` |
| unregistered transformation | `bundle_transformation_unregistered` |
| bundle mutated without rehash | `bundle_digest_mismatch` |
| 5 forbidden claim classes | `claim_class_unlicensed` |
| rights registry deleted / zero sources / `default_policy: allow` | `rights_registry_unreadable` / `rights_sources_empty` / `rights_registry_policy_invalid` |
| numeric fact claiming `not_applicable` uncertainty | `fact_numeric_uncertainty_required` |

**Against the committed registries:** a bundle citing the real `gdelt_doc_api`
refuses `fact_source_not_approved`. The commit message's "No source is approved
until the founder establishes a real signing key" is executable truth, not prose.

**Derived-source anti-laundering (9 further cases), all correct:** no upstream →
`fact_upstream_sources_required`; approved upstream + matching manifest →
`eligible`; pending upstream → `fact_upstream_source_not_approved`;
manifest/fact upstream disagreement → `fact_lineage_manifest_mismatch`; manifest
binding a different artifact hash → `fact_lineage_manifest_mismatch`; manifest
edited after hashing → `fact_lineage_manifest_digest_mismatch`; self-referential
upstream → `fact_upstream_sources_invalid`. The doc's claim that a first-party
CC BY label "cannot conceal an unreviewed GDELT" holds mechanically.

### Tests are fixture-rooted — yesterday's bomb class is absent

Every adversarial test builds its own `tmp_path` root, its own generated Ed25519
keypair, and its own four registries. Zero references to `docs/data` payloads,
zero live dates, no `!=` pin on today's anomaly. The two tests that read
committed state (`:591`, `:624`) read **policy** files, not living data, and use
append-safe floors (`len(sources) >= 10`, not `== 14`) — the shape `fe45a4e` was
praised for.

**Founder eyes:** `:609-621` assert `approved == []` and every source
`review_required`. The founder's first real signed approval **will** red CI until
those assertions are updated. Near-certainly the intended tripwire, but it should
say so in the docstring so it is not misread as a regression at 2 a.m.

### Recomputed

- `governance/source_rights_registry.json`: **14** sources, all
  `decision_state: review_required`, all `permitted_uses: []`, all
  `signer_id: null`; exactly **one** `bundle_declared` (`igrm_public_payloads`),
  13 `primary`.
- `governance/rights_signers.json`: **0** signers, `default_policy: deny`.
- `transformation_registry` implementation hash for `src/publication_transforms.py`
  recomputed independently:
  `d8d3a4d7b78313aee422e14196d54fb23517b2a7af72a1f9f988eaafbe6fdafc` — **exact**.
- Claim contract: 3 allowed classes, 6 forbidden, 1 template (`direct_fact_v1`,
  min 1 / max 1 fact), temporal policy set exactly `{same_effective_date}`.

### Claims discipline and pairing

Adds **no** reader-facing surface. `publication_guard` is referenced only from
`design/publication_claim_guard.md` and its own test — no workflow, script, or
page. `design/` is `MD_EXCLUDED` and `governance/*.json` falls outside
`JSON_FILES` (`docs/**.json` + `EXTRA_PAYLOADS`); the commit touched neither the
scan nor its exclusions, so the scan legitimately has nothing to see rather than
being dodged. The design doc states its own non-coverage (`:82-94`, "this module
must not be cited as coverage it does not yet provide") — the discipline the
0831ce3 incident was about, applied pre-emptively.

Dependency pairs with its tests: `cryptography==50.0.0` (requirements.txt) and
`>=50,<51` (pyproject). All three pytest-running workflows install
requirements.txt — `ci.yml:19`, `daily.yml:57`, `morning.yml:75` — so no
tests-ahead-of-pairs. Verified installable and green on 3.9.6 locally; CI is 3.11.

### QUESTIONABLE (founder eyes) — what the guard permits

Round-2 probes on acceptance rather than refusal:

1. **`value_type: "string"` is an unbounded text channel.** A full advisory
   sentence — "India's geopolitical risk is elevated and investors should reduce
   exposure to shipping equities ahead of an expected escalation" — validates
   **ELIGIBLE** as a "scalar" fact, provided those exact bytes sit at that
   pointer in a registered evidence file. The binding is real (a model cannot
   invent the text; the claim_class gate still applies), but
   `design/publication_claim_guard.md:71-72` describes `direct_fact_v1` as "one
   verified scalar, without interpretation," and an arbitrary-length sentence is
   not obviously that. Ruling wanted: restrict the template to non-string
   scalars, cap string length, or register an enum.
2. **`unit` and `denominator` are non-emptiness checks only**
   (`src/publication_guard.py:892-893`), while the design doc lists "unit and
   denominator" among what the guard checks. A number honestly bound to its bytes
   still validates while carrying a false unit/denominator label. This is the
   sharp one: the daily-brief incident's confirmed failures #2 and #3 were
   *exactly* denominator mislabeling (display share as pool quality; display
   count as score denominator) — the guard as written would not have caught
   either. Narrow the doc's phrasing or add a registered unit/denominator
   vocabulary.
3. **Cosmetic.** `src/publication_guard.py:858`'s first disjunct
   `hashlib.sha256(raw_bytes).hexdigest() != actual_sha` is always False —
   `actual_sha` *is* that digest, computed in `_read_json`. Dead sub-expression;
   the second disjunct does the real work (probe 01 confirms tampering is caught).

---

## Suite

`pytest -m "not live"` at **dd63bba**, clean detached clone, python 3.9.6,
cryptography 50.0.0: **514 passed, 0 failed, 0 errors, exit 0.**

Note for future runs: the same suite in a bare `git archive` extract yields 6
`test_blind_audit_500` failures + 1 `test_openapi` error, purely because those
tests need a real `.git` (base-commit resolution and `git archive HEAD`). Extract
artifact, not a defect — all pass in the clone.

Standing item confirmed **discharged**: the two `eba2d47` time bombs the batch2
review called the only near-certain incoming red
(`tests/test_evidence_assistant.py:140` and `:113`) were defused in `e90fae4`;
the live checks now assert `answer.status in ("answered", "refused")` with the
reasoning recorded in the docstring.

---

## Summary

| Commit | Verdict |
|---|---|
| f30771d (IGRM Max operating system) | **SOUND, one DEFECT (doc-level, no CI impact)** — spec `:76-78` claims "no public assistant" 7 minutes after `docs/ask.html` shipped and is self-contradicted at `:579`; QUESTIONABLE: `tests/test_dictionaries.py:2` now points at a deleted spec section (rules survive in methodology.md §2); QUESTIONABLE: roster guard is a subset check, a 13th spec row passes green |
| dd63bba (publication claim guard) | **SOUND** — fails closed under 47 independent probes with zero passthrough, including against the committed registries; tests fully fixture-rooted, no live-state pins; registry counts and transform hash recompute exactly; founder eyes on string-scalar prose channel and unvalidated unit/denominator |

## Open items, priority order

1. **f30771d DEFECT:** amend `IGRM_MAX_SPEC.md:76-78` — the public assistant
   exists (`docs/ask.html`, `assistant_answers.json`); reconcile with `:579`.
2. **Rule on the string-scalar channel and the unit/denominator gap** in
   dd63bba before any lane is wired — both are cheapest to fix while the guard is
   still unwired, and #2 is the exact class that produced the brief incident.
3. Repoint `tests/test_dictionaries.py:2` at `methodology.md` §2 (one line).
4. Make the benchmark roster test bidirectional (parse the Part VIII table).
5. Docstring the deliberate CI trip at `tests/test_publication_guard.py:609` so
   the founder's first signed approval reads as expected, not as breakage.
6. Reconcile `IGRM_MAX_SPEC.md:461-464` (dual control over label adjudication)
   with `GOVERNANCE.md:15-16` (calibration rulings are the founder's personally).
