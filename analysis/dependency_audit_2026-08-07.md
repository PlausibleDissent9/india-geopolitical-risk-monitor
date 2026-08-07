# Dependabot backlog: what is safe to merge, and what is not

Seven PRs, all opened 2026-07-28, all still open on 2026-08-07. Their CI
results are ten days stale, so "green" on the PR page proves nothing about
today's tree. Audited by resolving each target's `requires_python` against
the two Python versions this project actually commits to.

**Nothing was merged.** Dependency changes to a live pipeline are the
founder's call, and one of these would break the build outright.

## The two constraints in play

| | version | declared where |
|---|---|---|
| CI runs | **3.11** | every workflow's `setup-python` |
| Project floor | **3.9** | `pyproject.toml: requires-python = ">=3.9"` and REPLICATION.md: "Python 3.9+ works" |

The floor is a published promise to external reproducers, not an
implementation detail. It is the reason `numpy` is pinned at 2.0.2 —
that is the **last numpy release supporting Python 3.9**.

## Verdicts

| PR | change | requires_python | verdict |
|---|---|---|---|
| **#3** | numpy 2.0.2 → **2.5.1** | **>=3.12** | **BREAKS CI.** Runners are on 3.11. `pip install` fails at the install step, before any test runs. Merging this stops every lane, not just `ci`. |
| #6 | mypy 1.19.0 → 2.3.0 | >=3.10 | CI-safe. Breaks the local 3.9 venv used for development. Also a major version — expect new errors on a tree that has 67 files passing today. |
| #7 | types-markdown → 3.10.2.20260712 | >=3.10 | CI-safe, dev-only, low risk. Breaks a 3.9 dev venv. |
| #4 | types-requests → 2.33.0.20260712 | >=3.10 | CI-safe, dev-only, low risk. Breaks a 3.9 dev venv. |
| #5 | yfinance 1.2.0 → 1.5.2 | none declared | Installs anywhere. **Highest behavioural risk of the five**: it is the only one that fetches data feeding `event_study` and `priced_risk`, and REPLICATION.md already documents those two as the ±0.06 exceptions because Yahoo revises recent bars. Needs a before/after diff, not a version check. |
| #2 | actions/checkout 4 → 7 | n/a | Workflow-level. Test on one lane before all fifteen. |
| #1 | actions/setup-python 5 → 7 | n/a | Workflow-level. Same. |

## The numpy question, and why it is not just a pin

`numpy 2.5.1` cannot be installed on 3.11 at all, so PR #3 is a build
break rather than a numerical risk. But the interesting question sits
underneath it: **would upgrading numpy change any published number?**

That question is now answerable in three seconds, which it was not last
week. `src/blind_replicator.py` rebuilds the entire published series from
the codebook and `shares.csv` with no access to the pipeline. Run it under
the candidate numpy and compare:

```
# baseline, numpy 2.0.2
[blind_replicator] best: weak / calendar -- 19830/19830 values agree (100.0000%)
```

Any float-behaviour change large enough to move a published percentile
shows up as a number below 19830. That is the test to run when the floor
eventually moves — not "did the suite pass", which would also pass on a
tree whose numbers had all shifted by 0.05.

## Recommended order, when Ishan wants to do this

1. **#1 and #2** (the actions) — merge one, watch one lane, then the other.
2. **#4 and #7** (type stubs) — dev-only, no runtime effect.
3. **#6** (mypy 2.x) — expect a batch of new errors; that is a code task,
   not a merge.
4. **#5** (yfinance) — merge only alongside a recorded before/after of
   `event_study.json` and `priced_risk.json`, since those are the two
   payloads that already carry a documented tolerance.
5. **#3** (numpy) — **close it, or raise the floor first.** Taking it means
   moving CI to 3.12 *and* abandoning the published "Python 3.9+" promise,
   which is a decision about who can reproduce this index, not a version
   bump. If the floor moves, REPLICATION.md, `pyproject.toml` and every
   workflow have to move with it, in one change.

`tests/test_dependency_floor.py` now fails if a pin in `requirements.txt`
stops supporting the floor that `pyproject.toml` and REPLICATION.md
promise, so this cannot be merged in by accident later.
