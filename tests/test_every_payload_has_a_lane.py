"""Every module that writes a published payload must be run by something.

This exists because `src/publish_shares.py` shipped on 2026-08-07 as the
answer to a referee finding -- raw shares promoted to "a first-class
published artifact" -- and was wired into no workflow at all. It ran
once, by hand, and `docs/data/shares.csv` would have sat frozen on
2026-08-06 forever while the site advertised it as the daily quantity.
Nothing failed. Nothing went red. The file was simply never written
again.

That is the most dangerous shape of bug this project can have, because
the honesty surfaces are exactly the things nobody looks at twice: a
stale gap list, a frozen provenance record, a syndication multiplier
from last week. They keep serving plausible numbers after they stop
being true.

So: if a module writes into docs/data and can be run as a script, some
workflow must invoke it.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
WORKFLOWS = ROOT / ".github" / "workflows"

# Modules that write a payload but are deliberately invoked BY another
# module rather than by a workflow line of their own. Each one needs a
# named caller, so an entry here is a claim that can be checked, not a
# way to opt out of the rule.
INVOKED_BY_ANOTHER_MODULE = {
    "build_index": "src.run_daily",
    "render_site": "src.run_daily",
    "event_study": "src.run_daily",
    "maps_data": "its own workflow step",
    "receipts": "src.receipts_ngrams (artlist fallback)",
    "nowcast": "nowcast.yml",
    # Genuinely one-shot or human-paced, not oversights. Each is
    # justified here because "it doesn't need a lane" is a claim, and an
    # unjustified entry is how this test gets hollowed out.
    "fetch_cow": ("static: Correlates of War MID 5.0 is a frozen "
                  "historical release, fetched once, 208 years that do "
                  "not change overnight"),
    "fetch_ucdp": ("pinned release, manual --backfill; UCDP publishes "
                   "annually and the version is deliberately fixed"),
    "fetch_trends": ("Google Trends is rate-limited and unreliable "
                     "enough that an automated daily call would fail "
                     "more often than it succeeded; run deliberately"),
    "retest": ("founder-paced: writes a blind labelling sheet for a "
               "human to fill, so regenerating it nightly would "
               "reissue the draw before anyone answered it"),
    "ai_gpr_benchmark": (
        "one-shot registered benchmark: the source, IGRM input, analysis-code "
        "hashes, and output sequence are frozen in "
        "analysis/ai_gpr_benchmark_registration.json; a recurring lane would "
        "either fail its vintage checks or violate the registration"
    ),
    "splice_sensitivity": (
        "frozen historical study through 2026-08-09: recomputation reads "
        "retained identity-bearing NGram evidence and is rights-refused until "
        "a current signed decision covers the complete study window"
    ),
    "uncertainty": (
        "frozen historical sampling-band study through 2026-08-07: "
        "recomputation reads retained identity-bearing NGram evidence and is "
        "rights-refused until a signed decision covers the complete window"
    ),
    "precision_frame_v3": (
        "prospective protocol frozen before its first attestation: frame "
        "collection reads retained identity-bearing NGram evidence and is "
        "paused until a current signed processing decision exists"
    ),
}

WRITES_PAYLOAD = re.compile(
    r"SITE_DATA\s*/|docs\"\s*/\s*\"data\"|docs/data/[\w.]+\"")


def _module_names_run_by_workflows() -> set[str]:
    seen: set[str] = set()
    for wf in WORKFLOWS.glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        seen.update(re.findall(r"python -m src\.(\w+)", text))
    # run_daily orchestrates several modules in-process.
    rd = (SRC / "run_daily.py").read_text(encoding="utf-8")
    seen.update(re.findall(r"from \. import ([\w, ]+)", rd)[0].split(", ")
                if re.findall(r"from \. import ([\w, ]+)", rd) else [])
    return seen


def test_every_payload_writing_module_is_invoked_somewhere():
    run = _module_names_run_by_workflows()
    orphans = []
    for path in sorted(SRC.glob("*.py")):
        name = path.stem
        if name.startswith("_"):
            continue
        text = path.read_text(encoding="utf-8")
        if not WRITES_PAYLOAD.search(text):
            continue
        if 'if __name__ == "__main__"' not in text:
            continue
        if name in run or name in INVOKED_BY_ANOTHER_MODULE:
            continue
        orphans.append(name)

    assert not orphans, (
        "these modules write into docs/data but no workflow runs them, so "
        "their payloads would freeze at whatever value they last had "
        f"while the site keeps serving them: {orphans}. Wire them into a "
        "workflow, or add them to INVOKED_BY_ANOTHER_MODULE with the "
        "name of the caller.")


def test_the_shares_lane_specifically_is_wired():
    """The regression that motivated this file. Named explicitly so a
    future reordering that drops it fails with an obvious message."""
    run = _module_names_run_by_workflows()
    assert "publish_shares" in run, (
        "publish_shares is not invoked by any workflow; docs/data/shares.csv "
        "would go stale while being advertised as the daily quantity")


def test_shares_dependencies_run_in_the_right_order():
    """provenance -> publish_shares -> monthly. Out of order, each
    silently consumes yesterday's version of the previous one."""
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    order = [m for m in re.findall(r"python -m src\.(\w+)", daily)
             if m in ("provenance", "publish_shares", "monthly")]
    assert order == ["provenance", "publish_shares", "monthly"], (
        f"dependency order broken in daily.yml: {order}")


def _self_stamps(module: str) -> bool:
    """True if the module carries the universal _meta fields itself.

    Such a module does not depend on the post-run sweep reaching it, so
    its position relative to stamp_meta does not decide whether its
    download honours the codebook's promise.
    """
    path = SRC / f"{module}.py"
    if not path.exists():
        return False
    return "universal_fields(" in path.read_text(encoding="utf-8")


def test_a_self_stamping_module_really_carries_the_fields():
    """Guard the exemption above: `universal_fields(` in the source is
    only evidence if calling it actually produces the promised keys.

    Without this, renaming or gutting universal_fields would silently
    widen the exemption to every module that still mentions it.
    """
    from src import stamp_meta
    fields = stamp_meta.universal_fields("assistant_answers.json")
    for key in ("license", "citation", "codebook", "source"):
        assert key in fields, (
            f"stamp_meta.universal_fields no longer supplies {key!r}, so "
            "self-stamping modules are not actually exempt from the "
            "post-run sweep")


def test_stamp_meta_runs_after_every_payload_writer():
    """Placement, not intent, is what makes 'stamp everything' true.

    This step was placed mid-workflow, then after the audits. Both times
    later lanes rewrote payloads without the stamp -- the second time,
    TWELVE of them (daily_brief, aptness, tone, themes, forecasts,
    alerts, expert_attention, precision_auditor, reliability,
    sector_feeds, status_data). Found by rehearsing the whole sequence,
    not by reasoning about it.
    """
    daily = (WORKFLOWS / "daily.yml").read_text(encoding="utf-8")
    order = re.findall(r"python -m src\.(\w+)", daily)
    assert "stamp_meta" in order, "the stamp step is gone from daily.yml"
    idx = order.index("stamp_meta")
    # Modules that write into docs/data and therefore must precede it.
    writers = set()
    for path in SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if WRITES_PAYLOAD.search(text):
            writers.add(path.stem)
    after = [m for m in order[idx + 1:] if m in writers]
    # audit and make_datapack read/verify rather than publish payloads.
    after = [m for m in after if m not in ("audit", "make_datapack")]
    # A module that stamps ITSELF may legitimately run after the sweep.
    # freshness, vintages and nowcast already did -- each writes after
    # its own last chance and calls stamp_meta.universal_fields() to
    # carry the promised fields regardless of step order. Derived by
    # reading the modules rather than by listing their names here,
    # because a hand-kept exemption list is the second copy this repo
    # keeps getting bitten by.
    #
    # assistant_answers joined them on 2026-08-09 for the opposite
    # reason to the others: it records a source_sha256 of the payloads it
    # cites, so it MUST run after the last rewrite of those payloads --
    # which is this very step. See
    # tests/test_answer_hashes_are_stamped_first.py.
    after = [m for m in after if not _self_stamps(m)]
    assert not after, (
        f"these payload writers run AFTER stamp_meta: {after}. Their "
        "output ships without the licence and citation the codebook "
        "promises every download carries. A module that must run this "
        "late should call stamp_meta.universal_fields() itself, the way "
        "freshness, vintages, nowcast and assistant_answers do.")


# Every lane that both writes payloads and stamps them. Derived, not
# listed: hardcoding "daily.yml" is precisely how morning.yml went nine
# writers deep without anyone evaluating the invariant against it.
def _stamping_lanes() -> list[str]:
    lanes = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        if "python -m src.stamp_meta" in path.read_text(encoding="utf-8"):
            lanes.append(path.name)
    return lanes


def test_every_stamping_lane_stamps_after_its_last_writer():
    """The invariant above, applied to every lane instead of one filename.

    WHAT HAPPENED (2026-08-17)

    test_stamp_meta_runs_after_every_payload_writer reads
    WORKFLOWS / "daily.yml" by name, so it had never been evaluated
    against morning.yml -- the lane that actually publishes the 06:00
    contract. Measured: daily.yml 0 writers after its stamp, morning.yml
    9. It stamped at step 6 of 24 and then rewrote payloads for the rest
    of the run, so the payloads that SHIPPED were the unstamped ones, and
    stamp_meta.audit() reported nine on main with no licence, citation,
    codebook or source.

    Fixed by moving morning.yml's stamp below its last writer, which
    forced assistant_answers down with it -- it embeds a source_sha256 of
    the payloads it cites, and had been running before five writers that
    invalidated its hashes behind its back.

    A ratchet held this at nine while the repair was pending. The ratchet
    is gone because the gap is closed; this replaces it, and it is a lock,
    not a bound.
    """
    lanes = _stamping_lanes()
    assert lanes, "no workflow runs src.stamp_meta; the module name is stale"
    offenders = {lane: sorted(_writers_after_the_stamp(lane)) for lane in lanes}
    bad = {lane: mods for lane, mods in offenders.items() if mods}
    assert not bad, (
        f"payload writers run after the last stamp_meta in {bad}. Their "
        "output ships without the licence, citation, codebook and source "
        "the codebook promises every download carries. Move the writer "
        "above the stamp, or have it call stamp_meta.universal_fields() "
        "itself. If you move the stamp down instead, move "
        "src.assistant_answers down with it -- see "
        "tests/test_answer_hashes_are_stamped_first.py.")


def _writers_after_the_stamp(workflow: str) -> set[str]:
    """The check above, as a function of the workflow it reads.

    It was written against daily.yml and hardcodes that filename, so the
    invariant it enforces had never been evaluated for any other lane.

    The LAST stamp_meta, not the first. A lane may legitimately stamp
    early and again late -- morning.yml now does -- and what decides
    whether a payload ships stamped is the final one. Measuring from the
    first occurrence would report morning.yml as still broken after it
    was fixed, and would let a late stamp be deleted without complaint.
    tests/test_answer_hashes_are_stamped_first.py already reasons this
    way about the same step.
    """
    order = _invocations(WORKFLOWS / workflow)
    if "stamp_meta" not in order:
        return set()
    writers = {p.stem for p in SRC.glob("*.py")
               if WRITES_PAYLOAD.search(p.read_text(encoding="utf-8"))}
    last_stamp = len(order) - 1 - order[::-1].index("stamp_meta")
    after = order[last_stamp + 1:]
    return {m for m in after
            if m in writers
            and m not in ("audit", "make_datapack")
            and not _self_stamps(m)}


# Invocations that inspect rather than write. A module named on a line
# carrying one of these is not rewriting a payload, so it does not need to
# precede the stamp.
READ_ONLY_FLAGS = ("--status", "--check")


def _invocations(workflow: Path) -> list[str]:
    """Modules a workflow actually RUNS, in order.

    A bare `re.findall(r"python -m src\\.(\\w+)")` over the file text is
    wrong twice, and generalising the stamp invariant to every lane is
    what exposed both:

      receipts-extended.yml line 62 mentions `python -m src.syndication`
      inside a COMMENT. The regex counted it as a run.

      multilingual-backfill.yml runs `python -m src.multilingual --status`
      twice AFTER its stamp. That is a status probe, not a rewrite, but
      the regex captured the module name without the flag.

    Both reported as payload writers running after the stamp. Neither was.
    Had the lanes been "fixed" on that evidence the work would have been
    chasing ghosts, so the reading is narrowed here rather than the
    findings being explained away one at a time.
    """
    return _invocations_from_lines(workflow.read_text(encoding="utf-8").splitlines())


def _invocations_from_lines(lines: list[str]) -> list[str]:
    found: list[str] = []
    for raw in lines:
        line = raw.strip()
        if line.startswith("#"):
            continue
        # An inline `# ...` comment on a real command line: only the part
        # before it runs.
        code = line.split(" #", 1)[0]
        for match in re.finditer(r"python -m src\.(\w+)([^\n;&|]*)", code):
            module, rest = match.group(1), match.group(2)
            if any(flag in rest for flag in READ_ONLY_FLAGS):
                continue
            found.append(module)
    return found


def _writers_after_step(workflow: str, step_name_prefix: str) -> set[str]:
    """Payload writers a lane runs after a named step.

    Uses the same narrowed reading as _invocations: a module mentioned in
    a comment, or invoked with --status/--check, is not a rewrite.
    """
    path = WORKFLOWS / workflow
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((n for n, line in enumerate(lines)
                  if line.startswith(f"      - name: {step_name_prefix}")), None)
    assert start is not None, f"{workflow} has no step named {step_name_prefix!r}"
    below = _invocations_from_lines(lines[start:])
    writers = {p.stem for p in SRC.glob("*.py")
               if WRITES_PAYLOAD.search(p.read_text(encoding="utf-8"))}
    return {m for m in below
            if m in writers and m not in ("audit", "make_datapack", "freshness")}


def test_the_freshness_audit_really_does_run_last():
    """Its own comment said so, and had quietly stopped being true.

    "Runs last among the enrichment lanes, so it audits what this run
    actually produced" was accurate when written. Steps kept being
    appended after it -- tone, aptness, forecasts, alerts, episode
    themes, the expert shelf, the precision auditor, the per-sector
    feeds, status -- so it audited payloads this run had not written yet
    and failed the lane on their staleness. Being fail-loud, it then
    skipped the 18 steps below it, including those very writers.

    Run 31979586398: 33 payloads reported stale, at least 25 of them
    written after this step. The audit was the reason its own complaint
    stayed true.

    A comment cannot notice a step appended beneath it. This can.
    """
    after = _writers_after_step("daily.yml", "Freshness audit")
    assert not after, (
        f"these payload writers run AFTER the freshness audit: "
        f"{sorted(after)}. The audit will report their previous run's "
        "output as stale and, being fail-loud, skip the steps that would "
        "refresh it. Move the audit below them -- it is safe after the "
        "_meta stamp, which never touches _meta.generated.")
