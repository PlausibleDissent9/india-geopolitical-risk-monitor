# Seven open dependabot PRs, tested: none can merge as proposed

Tested 2026-08-08 against the actual environments, not against release
notes. Every verdict below was reached by resolving the package on the
Python the project actually runs, or by reading the served workflow.

## The constraint that decides six of the seven

`pyproject.toml` declares `requires-python = ">=3.9"` and
`REPLICATION.md` tells an external reproducer "Python 3.9+ works".
That promise is load-bearing: `tests/test_dependency_floor.py` exists
to defend it, and numpy is pinned at 2.0.2 because that is the last
release supporting 3.9.

The measurement that makes this concrete: **the project's own dev
virtualenv is Python 3.9.6** — deliberately at the floor, so the gate a
maintainer runs locally is the gate CI runs. A dev dependency that
requires 3.10+ does not fail CI (runners use 3.11). It fails
`scripts/gate.sh` on the maintainer's machine, which is the check that
stands between a bad commit and a push. Breaking the local gate to
satisfy a version bump trades the protection for the number.

## Verdicts

| PR | Bump | requires_python | Verdict |
|---|---|---|---|
| #1 | actions/setup-python 5 → 7 | n/a | **CLOSE — already applied.** `ci.yml:20` is on `@v7`. |
| #2 | actions/checkout 4 → 7 | n/a | **CLOSE — already applied.** `ci.yml:15` is on `@v7`. |
| #3 | numpy 2.0.2 → 2.5.1 | **>=3.12** | **HOLD.** Breaks the 3.9 promise and fails `pip install` on CI's 3.11 runners before a test runs. Already documented. |
| #4 | types-requests → 2.33.0.20260712 | **>=3.10** | **HOLD.** Dev-only; uninstallable on the 3.9 dev env, so the local gate stops running. |
| #5 | yfinance 1.2.0 → 1.5.2 | unspecified | **HOLD.** Metadata is silent but resolution fails: it requires `curl_cffi>=0.15`, which has no distribution for 3.9. Runtime dependency of the market lane. |
| #6 | mypy 1.19.0 → 2.3.0 | **>=3.10** | **HOLD.** Not resolvable on 3.9 at all (pip does not even list it). A major version bump would also need a type-error pass on 73 modules. |
| #7 | types-Markdown → 3.10.2.20260712 | **>=3.10** | **HOLD.** Same as #4. |

## What this is not

It is not neglect, and the PRs are not noise to be merged for tidiness.
Six of the seven are the 3.9 floor doing exactly what it was chosen to
do: refuse upgrades that would quietly drop the reproducers the project
promised to support. The remaining two are already applied by hand and
only need closing.

## The decision that actually needs making

The floor is a founder-level promise, not a maintenance detail. Raising
it to 3.10 would unblock four of these PRs and cost the "Python 3.9+
works" claim in `REPLICATION.md`, the datasheet and `pyproject.toml`.
Keeping it means these bumps stay closed and dependabot will keep
re-opening them.

A middle path exists and is worth considering: keep the runtime floor
at 3.9 (numpy, yfinance — what a reproducer needs) and let the DEV
tooling move to 3.10+ (mypy, type stubs — what only a maintainer
needs), accepting that the local gate then requires 3.10 while the
published promise stays 3.9. That keeps the promise and the tooling
current, at the cost of the local-gate-equals-CI-gate property that
caught real defects today.

Not a machine decision either way.
