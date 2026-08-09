"""The V5 batch must be able to finish a series before the axe falls.

WHAT WENT WRONG
The multilingual backfill sat at 0 of 15 series for days while its lane
reported success. The run on 2026-08-07 lasted from 09:44:14 to 10:29:27
-- exactly the 45-minute step timeout -- and completed not one series.
The first fix made progress cumulative (save after each series), which
was necessary and not sufficient: per-series persistence cannot help if
no series ever finishes.

The second fix bounded the work per run. That is the right shape, but
capping the COUNT is only meaningful if the arithmetic closes:

    DEADLINE_SECONDS + worst_case_one_series  <  step timeout

The deadline is checked BEFORE starting a series, so the last one can
begin at the final second of the budget and must still fit. If it does
not, the run is killed mid-fetch and that series' work is lost -- the
original bug, reintroduced by a config change nobody re-derived.

So this recomputes the whole thing from the constants that actually
govern it, and from the workflow's own timeout, rather than from a
comment.

THE CLIFF IT ALSO WATCHES
Worst case scales with the number of chunks, and chunks depend on how
far START is from today against CHUNK_DAYS. START is 2019-01-01 and
CHUNK_DAYS is 3700, so the range crosses into a second chunk in early
2029 and the worst case per series doubles overnight. Nothing else in
the repo would notice. This test will.
"""
from __future__ import annotations

import math
import re
from datetime import date, timedelta
from pathlib import Path

from src import fetch_gdelt, multilingual

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "multilingual-backfill.yml"


def _step_timeout_seconds() -> int:
    """The timeout on the step that actually runs the backfill, not the
    job's."""
    text = WORKFLOW.read_text(encoding="utf-8")
    m = re.search(r"timeout-minutes:\s*(\d+)\s*\n\s*run: python -m src\.multilingual",
                  text)
    assert m, "cannot find the backfill step's timeout in the workflow"
    return int(m.group(1)) * 60


def _chunks_per_series(today: date | None = None) -> int:
    today = today or date.today()
    days = (today - multilingual.START).days + 1
    return max(1, math.ceil(days / fetch_gdelt.CHUNK_DAYS))


def worst_case_series_seconds(today: date | None = None) -> float:
    """One series, throttled on every attempt of every chunk."""
    per_chunk = (
        sum(fetch_gdelt.RATE_LIMIT_BACKOFF_S * a
            for a in range(1, fetch_gdelt.RETRIES + 1))
        + fetch_gdelt.SLEEP_S * fetch_gdelt.RETRIES)
    return per_chunk * _chunks_per_series(today)


def test_the_last_series_started_can_still_finish():
    budget = multilingual.DEADLINE_SECONDS
    worst = worst_case_series_seconds()
    limit = _step_timeout_seconds()
    assert budget + worst < limit, (
        f"a series begun at the last second of the budget cannot finish: "
        f"budget {budget/60:.0f}min + worst-case series {worst/60:.1f}min "
        f"= {(budget+worst)/60:.1f}min against a {limit/60:.0f}min step "
        "timeout. The run would be killed mid-fetch and lose that series, "
        "which is the exact failure the bound exists to prevent. Lower "
        "DEADLINE_SECONDS or raise the step timeout.")


def test_there_is_real_margin_not_a_rounding_error():
    """Three minutes of slack is not slack: runner startup, a slow
    import and one unmodelled retry eat it."""
    slack = _step_timeout_seconds() - (multilingual.DEADLINE_SECONDS
                                       + worst_case_series_seconds())
    assert slack >= 5 * 60, (
        f"only {slack/60:.1f} minutes of margin; require 5")


def test_at_least_one_series_can_be_attempted():
    """A budget smaller than one worst-case series means a throttled run
    does nothing at all, forever, while looking bounded and sensible."""
    assert multilingual.DEADLINE_SECONDS >= worst_case_series_seconds(), (
        f"budget {multilingual.DEADLINE_SECONDS/60:.0f}min is under the "
        f"{worst_case_series_seconds()/60:.1f}min a single throttled series "
        "can cost, so a bad night makes zero progress by construction")


def test_the_chunk_cliff_has_not_arrived():
    """START is 2019-01-01 against CHUNK_DAYS 3700, so the range becomes
    two chunks in early 2029 and the worst case per series doubles. This
    is the warning, years early, rather than a mystery timeout then."""
    chunks = _chunks_per_series()
    assert chunks == 1, (
        f"the fetch range is now {chunks} chunks per series, so worst case "
        f"is {worst_case_series_seconds()/60:.1f}min. Re-derive "
        "DEADLINE_SECONDS and the step timeout together.")


def test_the_bound_is_actually_applied():
    """The cap and the deadline both have to be in the code path, not
    just defined. `todo[:MAX_SERIES_PER_RUN]` and a deadline check that
    breaks BOTH loops -- a bare break exits the language loop and
    cheerfully starts the next channel past the deadline it just
    refused to cross."""
    src = (ROOT / "src" / "multilingual.py").read_text(encoding="utf-8")
    assert "attempt_window(todo, today)" in src, "the per-run cap is not applied"
    assert "out_of_time = True" in src and "if out_of_time:" in src, (
        "the deadline does not break out of the outer loop")
    # Behaviour, not just the call site: the window may never hand back
    # more series than the budget was sized for, whatever its offset.
    many = [f"series_{i}" for i in range(3 * multilingual.MAX_SERIES_PER_RUN)]
    for step in range(40):
        window = multilingual.attempt_window(
            many, date(2026, 8, 9) + timedelta(days=step))
        assert len(window) == multilingual.MAX_SERIES_PER_RUN
        assert len(set(window)) == len(window), "a series attempted twice"
