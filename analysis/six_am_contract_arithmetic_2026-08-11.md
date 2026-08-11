# Can the 06:00 IST contract actually be met?

The site promises "Publication target: 6:00 AM IST". This is the arithmetic
behind whether that promise is keepable, done with measured step costs rather
than estimates, after the publish-gate fixes of 2026-08-11.

## The window is 30 minutes, and it cannot be widened

The measured UTC day closes at **00:00 UTC (05:30 IST)**. Nothing can heal or
build the final day before then -- the heal explicitly refuses days newer than
today-1. The promise is **00:30 UTC (06:00 IST)**. So the entire pipeline has
**30 minutes**, and no scheduling change creates more.

## Measured step costs

Sources: morning.yml's own recorded measurements for the lane steps, and my
timing of the gate on this laptop today.

| step | measured | source |
|---|---|---|
| heal (`--heal 5`) | 11.0 - 11.1 min | runs #26, #27 |
| pipeline (`run_daily`) | 14.9 - 20.8 min | runs #27, #26 |
| derived lanes | ~2 min | daily #102 |
| gate inside the push | **was 37.1 min** | ci #532 |
| gate after today's fixes | **~18 min (ESTIMATE)** | 441s on this laptop x ~2.5 hosted factor |
| commit / rebase / push | 1 - 2 min | observed |

**Total after today's fixes: ~48 - 54 minutes.**

The gate estimate is the one soft number here: 441s measured locally, scaled
by the ~2.5-3x hosted-runner factor this repo has used before. It should be
replaced with a real hosted measurement from the first successful run.

## The verdict

A 05:35 start finishes at **06:23 - 06:29 IST**. The 06:00 promise is missed
by roughly 25 minutes, and that is the BEST case -- it assumes no GDELT
throttle, no scheduler delay, no queueing behind another lane.

Before today's fixes the same arithmetic gave ~67-73 minutes, which is why the
cap climbed 20 -> 35 -> 45 -> 60 -> 90 in one night and why the contract was
missing routinely. Today's work removed ~19 minutes from every publish. It did
not remove enough to reach 06:00, and no honest reading of these numbers says
otherwise.

## What would actually reach 06:00, and what each costs

| change | saves | real cost |
|---|---|---|
| `pytest-xdist` parallel test run | ~7 min | a new dependency; test isolation must hold under parallelism |
| heal 5 days -> 2 days in this lane only | ~6 min | less resilience to upstream gaps; the full daily still heals 35 |
| publish the number BEFORE the derived lanes | ~2 min | the gate then refuses, because derived payloads must match |

Both of the first two together: **~34 - 40 min**. Still outside 30.

The window cannot be met by trimming. Reaching 06:00 requires a structural
change -- publishing the final index without a full CI gate in the same
critical path, which trades the property that no unverified bytes are ever
served. That trade is a founder decision, not a tuning exercise, and this note
does not make it.

## Recommendation

State a target the pipeline can actually hold. **06:30 IST** is met by the
measured numbers with ~5 minutes of margin; 06:00 is not, and has not been for
as long as the gate has been inside the publish path.

The honest interim position is already live and correct: the front page
computes lateness against the 06:00 target and says "one measured day behind
the 6:00 AM IST target" when it slips, with `role="status"`. A promise the
system cannot keep, plus a truthful admission when it breaks, is worse for
credibility than a promise it keeps.

Changing a published target is a claim change and belongs to the founder. The
arithmetic is here so the decision can be made on numbers.
