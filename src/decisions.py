"""The founder decision queue: what is blocked on Ishan, checked not listed.

WHY IT EXISTS
The work that only Ishan can do is not labour, it is authority: minting a
DOI, signing a registration, labelling calibration articles, deciding
which construct the paper argues for. No agent removes those and none
should. What an agent CAN remove is the cost of finding out what they
are -- which is currently reading a 750-line NOTES_FOR_ISHAN.md and
remembering which sections were resolved in chat three days ago.

WHY IT IS NOT JUST A LIST
A hand-written to-do list is the exact artifact this project keeps
deleting: a claim with nothing checking it. It rots the moment an item is
done somewhere else, and then it lies in the same confident tone.

So every item carries a PREDICATE -- a function that inspects the repo
and answers "is this still blocked?" The DOI item is blocked because
CITATION.cff has no `doi:` field. Calibration is blocked because
precision.json says 16 of 100. When Ishan does the thing, the predicate
goes false on the next run and the item disappears without anyone
editing this file. An item that cannot be checked does not belong here.

  python -m src.decisions            write docs/data/decisions.json
  python -m src.decisions --check    print the queue, exit 0 always
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

# (blocked, detail). Detail is shown to the founder, so it carries the
# number rather than an adjective.
Predicate = Callable[[], "tuple[bool, str]"]


def _read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _json(rel: str) -> dict:
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _doi_missing() -> tuple[bool, str]:
    cff = _read("CITATION.cff")
    m = re.search(r"^doi:\s*(\S+)", cff, re.M | re.I)
    if m:
        return False, f"minted: {m.group(1)}"
    return True, "CITATION.cff has no doi: field"


def _orcid_missing() -> tuple[bool, str]:
    if re.search(r"orcid", _read("CITATION.cff"), re.I):
        return False, "present in CITATION.cff"
    return True, "no ORCID on the author record"


def _calibration_incomplete() -> tuple[bool, str]:
    d = _json("docs/data/precision.json")
    n = d.get("author_labels_n")
    need = d.get("calibration_threshold")
    if n is None or need is None:
        return True, "precision.json does not report its label count"
    if n >= need:
        return False, f"{n} of {need} — calibrated"
    return True, (f"{n} of {need} labels; precision publishes as "
                  f"UNCALIBRATED until the threshold is reached")


def _subscribe_list_unwired() -> tuple[bool, str]:
    m = re.search(r'BUTTONDOWN_USER\s*=\s*"([^"]*)"', _read("docs/app.js"))
    if m and m.group(1):
        return False, f"wired to {m.group(1)}"
    return True, ("BUTTONDOWN_USER is empty; addresses relay to the author's "
                  "inbox instead of a real list, so nobody receives the "
                  "weekly note the site promises")


def _interview_unanswered() -> tuple[bool, str]:
    text = _read("paper/founder_interview.md")
    if not text:
        return True, "paper/founder_interview.md is missing"
    # Count the ANSWERS carrying a marker, not the markers -- several
    # answers carry two (a heading flag and a blockquote note), and
    # reporting 8 when 4 answers need work is the kind of small false
    # number this whole project exists to not ship.
    sections = re.split(r"^## ", text, flags=re.M)[1:]
    flagged = [s.split("\n", 1)[0].strip() for s in sections
               if "\U0001F534" in s]
    if not flagged:
        return False, "no guessed answers remain"
    return True, (f"{len(flagged)} drafted answers are still marked as "
                  "guesses; the paper's voice has to be the founder's")


def _notes_open_sections() -> tuple[bool, str]:
    """NOTES_FOR_ISHAN.md marks a settled item by putting RESOLVED in its
    heading. Everything else is still waiting."""
    heads = re.findall(r"^#{2,3} (.+)$", _read("NOTES_FOR_ISHAN.md"), re.M)
    if not heads:
        return False, "no notes file"
    open_ = [h for h in heads if "RESOLVED" not in h.upper()]
    if not open_:
        return False, "every section resolved"
    return True, (f"{len(open_)} of {len(heads)} sections in "
                  f"NOTES_FOR_ISHAN.md carry no RESOLVED marker")


ITEMS: list[dict[str, Any]] = [
    {
        "id": "zenodo_doi",
        "title": "Mint the Zenodo DOI",
        "minutes": 10,
        "predicate": _doi_missing,
        "why_it_matters": (
            "It converts IGRM from a website into a citable dataset, which "
            "is the only asset here that compounds. Everything else built "
            "accrues to it. It is also the binding constraint on the paper: "
            "CITATION.cff is otherwise correct and complete."),
        "why_only_you": "A Zenodo deposit is made from an account, by a person.",
    },
    {
        "id": "orcid",
        "title": "Get an ORCID and put it on the author record",
        "minutes": 2,
        "predicate": _orcid_missing,
        "why_it_matters": (
            "Free, and it should exist BEFORE the DOI so the two link from "
            "the start rather than being reconciled later."),
        "why_only_you": "It is an identity record.",
    },
    {
        "id": "calibration_labels",
        "title": "Label the remaining calibration articles",
        "minutes": None,
        "predicate": _calibration_incomplete,
        "why_it_matters": (
            "Precision is the one statistic on the site that still reads "
            "UNCALIBRATED. Everything else in the honesty apparatus is "
            "automated and green; this is the only number waiting on a "
            "human."),
        "why_only_you": (
            "A machine labelling its own precision set is not a validation, "
            "it is a mirror. This one is not delegable even in principle."),
    },
    {
        "id": "founder_interview",
        "title": "Correct the guessed answers in the founder interview",
        "minutes": 20,
        "predicate": _interview_unanswered,
        "why_it_matters": (
            "It unblocks the working paper. The answers exist in draft with "
            "every number sourced; what is missing is the parts that have to "
            "be true about you rather than about the index."),
        "why_only_you": (
            "A paper whose 'what surprised me' was written by a model has a "
            "fabricated premise in it."),
    },
    {
        "id": "subscribe_list",
        "title": "Wire the newsletter to a real list",
        "minutes": 5,
        "predicate": _subscribe_list_unwired,
        "why_it_matters": (
            "The site promises one email a week and shows a signup modal. "
            "Addresses currently relay to your inbox, so the promise is "
            "being made and not kept by anything automatic."),
        "why_only_you": "It needs an account and a sending identity.",
    },
    {
        "id": "notes_backlog",
        "title": "Clear the decision backlog in NOTES_FOR_ISHAN.md",
        "minutes": None,
        "predicate": _notes_open_sections,
        "why_it_matters": (
            "Several are registrations that cannot proceed without a "
            "signature, so the work behind them is built and parked."),
        "why_only_you": "Each one is a methodology choice with your name on it.",
    },
]


def build() -> dict[str, Any]:
    blocked, cleared = [], []
    for item in ITEMS:
        is_blocked, detail = item["predicate"]()
        row = {k: v for k, v in item.items() if k != "predicate"}
        row["detail"] = detail
        (blocked if is_blocked else cleared).append(row)

    from src import stamp_meta
    return {
        "_meta": {
            **stamp_meta.universal_fields("decisions.json"),
            "what": (
                "Everything currently blocked on the founder, with the "
                "check that decided it. Each item carries a predicate over "
                "the repository -- CITATION.cff has no doi: field, "
                "precision.json says 16 of 100 -- so an item clears itself "
                "when the thing is done and nobody has to remember to "
                "delete it."),
            "why_predicates": (
                "A hand-maintained to-do list is a claim with nothing "
                "checking it. It rots the moment an item is completed "
                "elsewhere, and then it goes on asserting itself in the "
                "same confident tone as the parts that are still true."),
            "n_blocked": len(blocked),
            "n_cleared": len(cleared),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "blocked": blocked,
        "cleared": cleared,
    }


def main() -> None:
    payload = build()
    SITE_DATA.mkdir(parents=True, exist_ok=True)
    (SITE_DATA / "decisions.json").write_text(
        json.dumps(payload, indent=1), encoding="utf-8")

    b = payload["blocked"]
    print(f"[decisions] {len(b)} blocked on the founder, "
          f"{len(payload['cleared'])} cleared")
    for row in b:
        mins = f"~{row['minutes']}m" if row["minutes"] else "ongoing"
        print(f"[decisions]   {mins:>8}  {row['title']}")
        print(f"[decisions]             {row['detail']}")
    if "--check" in sys.argv:
        return


if __name__ == "__main__":
    main()
