"""Nine workflows commit into docs/. All of them must stamp.

WHAT BROKE
The codebook promises every download carries its licence, citation and
codebook link, and `src/stamp_meta.py` was written to make that true. I
put it in daily.yml, wrote a test asserting it ran after every payload
writer IN THAT FILE, and reported the guarantee as held.

It was held for one lane out of nine.

On 2026-08-07 at 14:31Z the notes lane published and:

  * rewrote note_latest.json with no `_meta` at all -- dropping four
    frozen contract fields, which the API-contract test then caught
  * regenerated codebook.html, corrections.html and methodology.html
    with unversioned stylesheet links, because render_site.py emits
    `href="site.css"` and stamp_assets lives in daily.yml

Neither is the bot's fault. Both are mine: I scoped a global guarantee
to a single workflow and then asserted it globally. The ordering test I
was proud of -- the one that caught me placing the stamp step wrong
twice -- only ever looked at daily.yml.

This is the generalisation. Any workflow that commits into docs/ is a
publishing lane and must stamp before it commits.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


# How a lane publishes. `git commit` was the only form until the eleven
# hand-rolled push loops were replaced by one shared script -- at which
# point this detector matched NOTHING and the tests below failed loudly
# rather than passing on an empty set. That is the right failure for a
# derived check, and the reason to keep both forms listed here.
PUBLISH_MARKERS = ("publish_push.sh", "git commit")


def _publishing_lanes() -> dict[str, str]:
    """Workflows that commit changes into docs/."""
    lanes = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        publishes = any(m in text for m in PUBLISH_MARKERS)
        if publishes and re.search(r"git add[^\n]*docs|docs/data", text):
            lanes[path.name] = text
    return lanes


def _commit_position(text: str) -> int:
    """Where the lane hands its work to git. The shared script both
    commits and pushes, so its call site is the boundary; a lane still
    using a bare `git commit` is measured at its LAST one (daily.yml
    commits mid-run to bank the backfill chunk cache)."""
    at = text.rfind("publish_push.sh")
    return at if at != -1 else text.rfind("git commit")


def test_there_is_more_than_one_publishing_lane():
    """The premise. If this ever drops to one, the rest of this file is
    over-engineering and should be simplified rather than left to rot."""
    lanes = _publishing_lanes()
    assert len(lanes) > 1, (
        f"only {len(lanes)} publishing lane(s); this test assumed several")


def test_every_publishing_lane_stamps_metadata():
    missing = [name for name, text in _publishing_lanes().items()
               if "src.stamp_meta" not in text]
    assert not missing, (
        f"these lanes commit into docs/ without stamping payload "
        f"metadata: {missing}. Anything they publish ships without the "
        "licence and citation the codebook promises every download "
        "carries -- which is exactly what the notes lane did to "
        "note_latest.json on 2026-08-07.")


def test_every_publishing_lane_stamps_asset_versions():
    missing = [name for name, text in _publishing_lanes().items()
               if "src.stamp_assets" not in text]
    assert not missing, (
        f"these lanes commit into docs/ without re-stamping asset "
        f"versions: {missing}. render_site.py emits href=\"site.css\" with "
        "no version, so any lane that regenerates a page and commits it "
        "leaves returning readers on cached CSS.")


def test_the_stamps_run_before_the_commit_in_each_lane():
    """Position, not presence. A stamp step after the commit stamps
    files that have already shipped -- which is the same mistake I made
    inside daily.yml twice, one scope up."""
    late = []
    for name, text in _publishing_lanes().items():
        # The LAST handoff, not the first. daily.yml commits mid-run inside
        # the backfill retry loop -- `git commit -m "backfill chunk cache:
        # pass $i"` -- to bank progress against a job timeout. That one
        # writes data/raw, not docs, and anchoring on it reported daily.yml
        # as unstamped when it is the one lane that has always stamped
        # correctly.
        commit_at = _commit_position(text)
        assert commit_at != -1, f"{name} has no recognisable publish step"
        for module in ("src.stamp_meta", "src.stamp_assets"):
            at = text.find(module)
            if at == -1 or at > commit_at:
                late.append(f"{name}:{module}")
    assert not late, (
        f"these stamps run at or after their lane's commit: {late}")


def test_note_latest_specifically_carries_the_universal_fields():
    """Named because it is the file that actually lost them. A generic
    'all payloads' assertion existed and passed for weeks while this
    lane was quietly republishing without them between runs."""
    import json
    payload = json.loads(
        (ROOT / "docs" / "data" / "note_latest.json").read_text(encoding="utf-8"))
    meta = payload.get("_meta") or {}
    for field in ("license", "citation", "codebook", "source"):
        assert meta.get(field), (
            f"note_latest.json has no _meta.{field}; the notes lane "
            "republished it unstamped")


# Payloads that are recomputed FROM docs/data/receipts.json. A lane that
# rewrites receipts must rewrite these in the same candidate, or it ships
# a tree where the derived files still describe the previous bytes.
RECEIPTS_CASCADE = ("src.status_data", "src.assistant_answers")


def _receipts_writing_lanes() -> dict[str, str]:
    """Workflows that run the module which writes receipts.json."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOWS.glob("*.yml"))
        if "src.receipts_ngrams" in path.read_text(encoding="utf-8")
    }


def test_every_lane_that_rewrites_receipts_runs_its_cascade():
    """Same mistake as this file's docstring, one payload deeper.

    daily.yml has always run the cascade -- status_data, then the stamps,
    then assistant_answers. receipts-extended.yml rewrote the same
    payload and stopped at the stamps. On 2026-08-20 (run 32342408405)
    its scan SUCCEEDED, writing receipts.json for 2026-08-19 with 5/5
    channels and 130,662 docs sampled, and the publish was refused
    because three payloads still described the old bytes.

    The instructive failure was test_consequence_plan's: it asserts a
    date-mismatch refusal and got 'evidence_unavailable', because the
    assistant's registered fact snapshots still pinned the previous
    receipts bytes, so verification failed before the date check was
    reached. A stale cascade does not merely look stale -- it changes
    which refusal the machine surface returns.
    """
    lanes = _receipts_writing_lanes()
    assert len(lanes) >= 2, (
        f"expected daily.yml and receipts-extended.yml to write receipts; "
        f"found {sorted(lanes)} -- if the module was renamed this check is "
        "matching nothing and guarding nothing")
    for name, text in lanes.items():
        missing = [m for m in RECEIPTS_CASCADE if m not in text]
        assert not missing, (
            f".github/workflows/{name} runs src.receipts_ngrams but not "
            f"{missing}. Those payloads are recomputed from receipts.json, "
            "so a lane that moves receipts and not them publishes a tree "
            "whose machine answers still verify against the previous bytes "
            "-- the publish gate refuses it, after the whole scan has run.")


def test_the_answers_cite_hashes_so_they_follow_the_stamps():
    """assistant_answers cites stamped hashes; running it before the
    stamps would cite hashes that the stamps then change."""
    for name, text in _receipts_writing_lanes().items():
        answers = text.index("src.assistant_answers")
        stamps = text.index("src.stamp_assets")
        assert stamps < answers, (
            f".github/workflows/{name} runs src.assistant_answers before "
            "src.stamp_assets; the answers cite hashes the stamp step "
            "rewrites, so they would be stale on arrival")
