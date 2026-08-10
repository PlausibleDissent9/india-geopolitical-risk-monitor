# The nowcast lane is dead, and the cost is the gate, not the nowcast

**Status:** live failure at time of writing. Runs #83, #84, #85 all dead.
**Found:** 2026-08-10, during lane verification.

---

## 1. What is happening

The nowcast lane runs every two hours (`cron: "43 */2 * * *"`). Its last three
runs were killed at the 45-minute job cap. The last payload it managed to
publish is `2026-08-10T06:00:50Z` — over six hours stale at the time of
writing, and the gap is growing by two hours every two hours.

The site is not lying about it: `renderNowcast` refuses any payload not dated
today, and the rendered line carries "as of HH:MM IST". A reader who checks the
timestamp can see it. A reader who does not will read a provisional number
computed six hours ago as if it were current.

## 2. The label that hid it for hours

The GitHub run list shows these as **`cancelled`**, not `failure`. Combined
with `cancel-in-progress: false` on the lane's concurrency group, that reads
exactly like pending-run eviction — the failure mode this repo has already been
bitten by, and the one I went looking for first.

It is not eviction. **GitHub reports a `timeout-minutes` kill as
`conclusion: cancelled`.** Three consecutive runs at *exactly* 45.3 minutes
against a `timeout-minutes: 45` is a cap, not a coincidence, and no amount of
staring at concurrency groups was going to show that.

Worth writing down as a repo fact: in this project's run history, `cancelled`
means "hit the cap" far more often than it means "someone cancelled it".

## 3. Where the time actually goes

Per-step, from the Actions API across four runs. My first hypothesis was that
`src.nowcast` had got slow during the GDELT DOC API disruption. **It had not.**

| step | #82 (ok) | #83 | #84 | #85 |
|---|---|---|---|---|
| pip install | 0.3 | — | 0.5 | 0.4 |
| Morning-contract guarantor | 0.0 | — | 0.0 | 0.0 |
| Compute provisional today-so-far | 3.5 | — | 5.4 | **6.5** |
| Stamp payload metadata | 0.0 | — | 0.0 | 0.0 |
| **Commit nowcast payload** | **39.2** | — | **39.2** | **38.2** |

The compute is 6 minutes. The *commit* is 39.

And note #82: it **succeeded**, and still spent 39.2 minutes in that step. The
lane was already paying the full cost while it looked healthy. It did not
degrade — it crossed a line.

`6.5 + 39.2 + 0.4 = 46.1` against a 45-minute cap. The lane is failing by
about a minute.

## 4. What the commit step is actually doing

```
git add docs/data/nowcast.json
bash scripts/publish_push.sh "nowcast: ..."
```

`publish_push.sh` runs the **full committed gate** — all 15 CI checks,
including the complete test suite and coverage — before it pushes. That gate is
currently ~37 minutes because one test,
`test_normative_adversarial_registry_is_complete_and_executed`, costs 96.38s
inside a suite that nine publishing lanes each run in full.

So the nowcast lane spends **85% of its wall clock gating, and 14% computing the
thing it exists to compute.**

Thirteen workflows call `publish_push.sh`. Nowcast calls it twelve times a day.
That is roughly **7.8 runner-hours per day of gating, to publish one provisional
JSON file every two hours.**

## 5. What was changed here, and what deliberately was not

**Changed:** the commit step is now bounded at 40 minutes, below the job cap, so
it fails with a diagnostic naming the gate instead of the job being killed
anonymously mid-sentence. This is the same treatment `daily.yml` already gives
`src.run_daily`, and the same doctrine: failing loudly beats hanging, and the
concurrency lane is released either way.

**Not changed: the cap.** It was already raised once today, 30 → 45, and that
bought four runs before saturating. A third raise would be the second fix that
treats a shared-gate cost as though it were this lane's problem. The measured
distribution does not support a number — it supports the observation that this
lane's duration is a function of the *suite's* duration, so any cap chosen here
is a bet on someone else's test.

**Not changed: the gating scope.** The obvious question is whether publishing
one provisional payload should run the entire CI suite. It probably should not.
But `publish_push.sh` is shared by all thirteen lanes and is sha256-pinned in
`governance/security_integrity_registry.json`; narrowing what it verifies is a
security-relevant architectural decision, not a performance tweak, and it is not
mine to make unilaterally while a coordination window with Codex is open.

## 6. The actual fix, and who owns it

The root cause is the 96-second test, already reported to Codex as `[BLOCKING]`
with the profile. When it lands, this lane's commit step drops from ~39 minutes
to ~16, the arithmetic becomes `6.5 + 16 + 0.4 = 23` against a 45-minute cap,
and the nowcast lane recovers without anything else changing.

Until then the lane will keep failing every two hours. That is the honest
status: **this document does not fix the nowcast lane.** It bounds the failure,
names the cost, and puts the number where the next person looking at a
`cancelled` run will find it.

## 7. Two smaller things found on the way

- `daily.yml`'s concurrency group did not show up in a first scan because
  `group:` sits several comment lines below `concurrency:`. A shallow
  `grep -A3` reported `<none>` for it and for four other workflows. Any audit of
  concurrency in this repo has to parse the block, not grep near the key —
  reporting "no concurrency group" on `daily.yml` would have been a serious
  false negative.
- `validate.yml` uses group `igrm-pipeline-${{ github.ref }}` while `daily.yml`
  and `morning.yml` use `igrm-pipeline-v3-${{ github.ref }}`. These are
  currently distinct, which is correct and probably intentional, but the names
  differ by a version suffix that exists to be bumped. A future bump to `-v4`
  is safe; a rename of `validate.yml`'s group to match the others would
  silently serialise the weekly validation behind the daily publish. Noted, not
  changed.
