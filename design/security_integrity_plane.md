# IGRM security integrity plane — repository baseline 1.0.0

Effective 2026-08-08. This is an enforceable repository baseline, not a
security certification and not a claim that IGRM is institutionally secure.

## Threats this slice addresses

1. A workflow tag moves after review and executes different third-party code.
2. A shallow checkout makes a frozen registration unverifiable.
3. A publisher installs fewer dependencies than CI and therefore cannot run
   the same gate honestly.
4. A scheduled workflow rebases onto a newer `main`, pushes a combined tree
   that CI never tested, and the token-originated push does not trigger a new
   push workflow.
5. A workflow silently receives a broader token permission.

## Enforced controls

- Every external action reference is an exact, registered 40-character
  commit identity. Moving version tags are refused.
- Every checkout fetches complete history because registrations resolve
  historical commits. Checkout does not persist a repository credential for
  later build or test steps.
- Every workflow declares top-level token permissions. Only four registered
  dispatching lanes may request `actions: write`.
- Every publishing lane installs both exact runtime and development
  requirements.
- After every successful rebase and immediately before every push path, the
  registered publishers run `bash scripts/gate.sh --publish` against the exact
  candidate commit. This mode still extracts and checks committed `HEAD`; it
  excludes only live-site assertions about the deployment being replaced and
  non-gating coverage output. A red candidate is refused even if that loses
  the scheduled update.
- The repository write token is supplied only to the final publication step,
  converted to a non-exported ephemeral Git header, and removed from the
  environment before repository code or the candidate gate executes.
- The implementation, gate and publisher scripts are hash-registered. The
  validator refuses silent drift and emits one deterministic public report.

The machine registry is
`governance/security_integrity_registry.json`; the public bounded report is
`docs/data/security_integrity.json`. CI regenerates the report and refuses a
diff.

## What this does not establish

The repository cannot verify GitHub-account MFA, branch or environment
protection, secret-storage policy, the behavior of GitHub Pages, or the
founder's device. There has been no independent penetration test, security
certification, formal privacy audit or continuous vulnerability-response
operation. Those are later institutional gates. Public language must say
"repository-control baseline," never "secure," "zero trust," "audited" or
"certified."

## Next security layers

1. Founder-controlled hardware-key MFA and signed release authorization.
2. Protected deployment environment with two-person approval for production.
3. Dependency and secret scanning with triaged advisories and response clocks.
4. Browser and content-security adversarial tests across every public route.
5. External threat-model review, penetration test and documented remediation.
6. Incident, disclosure, backup, recovery and continuity exercises with
   measured results.
