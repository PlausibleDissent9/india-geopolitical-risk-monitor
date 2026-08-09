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
