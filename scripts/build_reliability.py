"""
Reliability record from git evidence: every daily-publish commit's
timestamp vs the morning contract (final by 06:30 IST since 2026-08-11,
06:00 before it). The repository
is the log; nothing self-reported.

Writes docs/data/reliability.json: per measured day, the first commit
that published it and whether it beat the contract. The contract
formally began 2026-08-02 (first morning after the crons shipped);
earlier days are listed as pre-contract context.

  python scripts/build_reliability.py
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "data" / "reliability.json"

IST = timezone(timedelta(hours=5, minutes=30))
CONTRACT_START = "2026-08-02"

# The published target, and the date each version of it took effect.
#
# THE DEADLINE IS NOT RETROACTIVE. On 2026-08-11 the public target moved from
# 06:00 to 06:30 IST, because 06:00 gave the pipeline a 30-minute window
# against 48-54 minutes of measured work (see
# analysis/six_am_contract_arithmetic_2026-08-11.md). Scoring the whole
# history against the NEW, later deadline would silently repaint days that
# were genuinely late under the promise in force at the time -- a public
# reliability record that improves when you relax the promise is worthless.
#
# So each day is judged against the target that was published on that day.
# Newest first; the first entry whose date is <= the measured day wins.
CONTRACT_SCHEDULE = (
    ("2026-08-11", timedelta(hours=6, minutes=30)),
    ("2026-08-02", timedelta(hours=6)),
)


def contract_offset(day: str) -> timedelta:
    """The publication deadline in force for measured day `day`, as an offset
    from midnight of D+1."""
    for effective, offset in CONTRACT_SCHEDULE:
        if day >= effective:
            return offset
    return CONTRACT_SCHEDULE[-1][1]


def main() -> None:
    # CI checkouts are shallow (fetch-depth 1): git log sees one commit
    # and this script would write an EMPTY record over the good one --
    # which is exactly what happened every daily run until 2026-08-06.
    # Self-heal by unshallowing; the guard at the bottom makes the
    # failure loud if history is still missing.
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        capture_output=True, text=True, cwd=ROOT).stdout.strip()
    if shallow == "true":
        subprocess.run(["git", "fetch", "--quiet", "--unshallow", "origin"],
                       cwd=ROOT, check=True)
    log = subprocess.run(
        ["git", "log", "--all", "--format=%H|%cI|%s", "--", "docs/data/latest.json"],
        capture_output=True, text=True, cwd=ROOT, check=True).stdout
    # First (earliest) publish commit per measured day, from any lane.
    # "data: final" is the VPS/local morning lane's subject; missing it
    # meant the actual contract-beating commits never counted.
    first: dict[str, dict] = {}
    for line in reversed(log.strip().splitlines()):
        sha, ciso, subject = line.split("|", 2)
        m = re.search(r"(?:data: update|data: final|final publish)", subject)
        if not m:
            continue
        # The measured day is what latest.json said AT that commit.
        show = subprocess.run(
            ["git", "show", f"{sha}:docs/data/latest.json"],
            capture_output=True, text=True, cwd=ROOT)
        if show.returncode != 0:
            continue
        try:
            day = json.loads(show.stdout)["date"]
        except Exception:  # noqa: BLE001 - malformed historical payloads skipped
            continue
        if day in first:
            continue
        ts = datetime.fromisoformat(ciso.replace("Z", "+00:00")).astimezone(IST)
        first[day] = {"published_ist": ts.strftime("%Y-%m-%d %H:%M"),
                      "commit": sha[:7]}

    days = []
    for day in sorted(first):
        rec = first[day]
        pub = datetime.strptime(rec["published_ist"], "%Y-%m-%d %H:%M")
        # Contract: day D final by the target published on day D, on D+1.
        deadline = (datetime.strptime(day, "%Y-%m-%d")
                    + timedelta(days=1) + contract_offset(day))
        in_contract = day >= CONTRACT_START
        days.append({
            "day": day, **rec,
            "deadline_ist": deadline.strftime("%Y-%m-%d %H:%M"),
            "on_time": (pub <= deadline) if in_contract else None,
            "contract": in_contract,
        })

    # Fail-loud floor: publish commits exist in a full clone, so an
    # empty result means broken history access, not a clean slate.
    # Dying here (the CI step is non-gating) preserves the committed
    # record instead of overwriting it with zeros.
    if not days:
        raise SystemExit("[reliability] no publish commits found in git "
                         "history; refusing to overwrite the record")

    scored = [d for d in days if d["contract"]]
    on_time = sum(1 for d in scored if d["on_time"])
    payload = {
        "_meta": {
            "what": ("The morning contract's measured record, computed from "
                     "git commit timestamps, nothing self-reported: day D "
                     "final by the target published on day D, on D+1 -- 06:30 "
                     "IST from 2026-08-11, 06:00 IST before it. Each day is "
                     "scored against the promise in force at the time, never "
                     "re-scored against a later one. Pre-contract days shown "
                     "as context. Misses stay listed forever."),
            "contract_start": CONTRACT_START,
            "contract_schedule": [
                {"effective_from": day, "deadline_ist_on_d_plus_1":
                 f"{offset.seconds // 3600:02d}:{offset.seconds % 3600 // 60:02d}"}
                for day, offset in reversed(CONTRACT_SCHEDULE)
            ],
            # Canonical UTC, like every other payload. This stamped IST
            # wall-clock until 2026-08-19, when a 20:52 UTC run wrote
            # "2026-08-20 02:22 IST" and the freshness auditor read a
            # payload from the future -- undatable, red. The IST instant
            # is this payload's subject matter, so it stays, as display.
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "generated_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        },
        "on_time": on_time, "scored_days": len(scored),
        "rate": round(on_time / len(scored), 3) if scored else None,
        "days": days,
    }
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[reliability] {on_time}/{len(scored)} on time in-contract; "
          f"{len(days)} days recorded")


if __name__ == "__main__":
    main()
