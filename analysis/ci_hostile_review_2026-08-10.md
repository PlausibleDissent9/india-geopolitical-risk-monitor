# Hostile review of the CI/publish surface — 2026-08-10

**Scope.** Codex execution-list item 6, first bounded slice: the 19 workflow
files, their token grants, trigger surfaces, action pinning, credential
persistence, and injection paths from untrusted input into `run:` blocks.
Kernel/runtime code is a separate slice.

**Verdict: PASS.** Every preliminary finding died on verification. The
surface is deliberately hardened and internally consistent. Because a
review that reports only findings teaches nothing about its own method,
the false-positive trail is part of the deliverable.

---

## 1. What was checked and what held

| Surface | Result |
|---|---|
| Third-party action pinning | **All `uses:` pinned to full 40-char SHAs** with version comments. Zero tag or branch references. |
| Token permissions | **All 19 workflows carry explicit `permissions:` blocks.** Read-only for `ci`, `reproduce`, `evolution`, `lane-env`, `bq-smoke`; `contents: write` only on publishing lanes; `actions: write` only where a lane dispatches another (`nowcast`'s morning guarantor, `watchdog`, the two backfills). Least privilege as a practiced pattern, not an aspiration. |
| Dangerous triggers | **No `pull_request_target`, no `issue_comment`.** The one `workflow_run` (validate ← daily-update) is same-repo and gated on `conclusion == 'success'`. |
| Credential persistence | **Every real checkout sets `persist-credentials: false`.** Pushes authenticate per-step: `publish_push.sh` builds its own basic-auth header from `IGRM_PUBLISH_TOKEN`, then **unsets** `IGRM_PUBLISH_TOKEN`, `PUBLISH_TOKEN`, `GH_TOKEN`, and `GITHUB_TOKEN` before doing anything else. A compromised later step in any job finds no ambient git credential. |
| Injection into `run:` | Every `${{ }}` inside run blocks resolves to workflow-dispatch inputs (which require write access to supply), numeric step outputs, or `job.status`. No path from untrusted external input to shell text. |
| Secrets inventory | `GITHUB_TOKEN` (13 uses), `GCP_SA_JSON`/`GCP_PROJECT_ID` (BigQuery lanes), `ANTHROPIC_API_KEY` (display-only aptness labels), `MEDIACLOUD_API_KEY`. No secret appears in a read-only lane that does not need it. |

## 2. The false-positive trail — four in one pass

Every one of these was a *reported-looking* finding that reading killed:

1. **"No `permissions:` blocks anywhere."** A shell one-liner interpolating
   filenames into `python -c` failed silently per file and printed empty for
   all 19. The proper YAML parse shows explicit blocks in every workflow.
   A silent per-file failure that *looks like a uniform answer* is the most
   dangerous scanner failure mode there is — a uniform wrong answer reads as
   a systemic finding.
2. **"`validate.yml:39` executes a step output as a run block."** Line 39 is
   `run: ${{ steps.check.outputs.run }}` — inside a job-level `outputs:`
   map. It *declares* an output named `run`; nothing executes it. The grep
   matched the YAML key, not a step.
3. **"morning.yml has a checkout that persists credentials."** The "second
   checkout" was a *comment* — prose explaining a 2026-08-08 stale-checkout
   fix contains the string `actions/checkout`. `grep -c` counted it.
4. **"ci/evolution/lane-env persist credentials."** Their checkout blocks
   carry explanatory comments before the options, pushing
   `persist-credentials: false` past a `grep -A3` window. Widening the
   window shows all three set it.

Running tally for today: the claims sweep produced 8 scanner false positives
against 4 real defects; this pass produced 4 against 0. The pattern is
stable and worth stating as doctrine: **in this repo, a scanner hit is a
question, not a finding.** The comment density that makes the codebase
auditable by humans is exactly what defeats naive pattern-matching — the
prose keeps naming the hazards it guards against.

## 3. What this slice did not cover

- The GCP service-account JSON's own scope (checked only that it stays out
  of read-only lanes; its IAM grants are not visible from the repo).
- Branch-protection and environment-protection settings (server-side, not
  in the tree; the `publish-lane environment` runs suggest an environment
  gate exists).
- Runner supply chain (`ubuntu-latest` image trust) — out of scope by
  declaration, unfixable from a workflow file.
- The kernel/runtime slice (event ledger, shock compiler, admission paths)
  — separately owned by Codex per the cross-review rule.

## 4. One residual, filed without a fix

`daily.yml:142` compares `${{ github.event.inputs.backfill }}` inside
`[ ... ] = "true"`. Dispatch inputs need write access, so this is not an
injection *today*; but the value is interpolated as raw shell text rather
than passed through an env var, and the hardening convention elsewhere in
this repo is env-var indirection. If a future edit adds a free-text
dispatch input to this lane, this line's pattern is the one that becomes
a hole. Cosmetic now; cheap to normalise the next time daily.yml is open
for a real change. Not worth a solo commit on a file two agents share.
