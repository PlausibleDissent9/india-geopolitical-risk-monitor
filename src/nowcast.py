"""
V2-3 nowcast: a provisional "today so far" score every two hours.

Samples the GDELT Web NGrams v5 minute-files published so far today,
using the same machinery and splice calibration as the fetch_ngrams
heal path, then ranks each channel's spliced partial-day share against
its own trailing 730 days from the frozen store, exactly as
build_index scores a finished day.

Output goes ONLY to docs/data/nowcast.json. The historical store, the
official daily score, and every published series stay untouched: the
daily pipeline supersedes the provisional number when it finalizes the
day, and the site labels this payload provisional wherever it appears.

  python -m src.nowcast          write nowcast.json (or exit 0 if too early)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import fetch_ngrams, ngram_rights
from .build_index import DEFINITION, MIN_OBS, PERCENTILE_WINDOW_DAYS

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "raw" / "gdelt_volume.csv"
CALIB = ROOT / "data" / "raw" / "ngram_calibration.json"
OUT = ROOT / "docs" / "data" / "nowcast.json"

# The bridge's minute-files trail real time; sampling right up to "now"
# just burns HEAD probes on files that do not exist yet.
FEED_LAG_MIN = 20
# Below three hours of day the sample is more noise than signal; the
# first publishable nowcast of a UTC day lands mid-morning IST.
MIN_DAY_MINUTES = 180
MIN_DOCS = 2500
_DYNAMIC_RIGHTS_FIELDS = {
    "evaluated_at_utc",
    "rights_as_of",
    "evaluated_age_days",
}


def _rights_authority_binding(proof: object) -> dict[str, object]:
    if not isinstance(proof, dict):
        raise ngram_rights.NgramRightsError("nowcast_rights_receipt_invalid")
    return {
        key: value
        for key, value in proof.items()
        if key not in _DYNAMIC_RIGHTS_FIELDS
    }


def require_release_rights(
    expected_candidate_sha: str,
    *,
    root: Path = ROOT,
    rights_authority: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict[str, object]:
    """Recheck a committed nowcast immediately before its exact SHA push."""

    if not re.fullmatch(r"[0-9a-f]{40}", expected_candidate_sha):
        raise ngram_rights.NgramRightsError("nowcast_candidate_sha_invalid")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    dirty = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if (
        head.returncode != 0
        or head.stdout.strip() != expected_candidate_sha
        or dirty.returncode != 0
        or dirty.stdout
    ):
        raise ngram_rights.NgramRightsError("nowcast_candidate_not_clean")
    blob = subprocess.run(
        ["git", "show", f"{expected_candidate_sha}:docs/data/nowcast.json"],
        cwd=root,
        capture_output=True,
    )
    try:
        payload = json.loads(blob.stdout)
        target = datetime.strptime(str(payload["date"]), "%Y-%m-%d").date()
        receipt = payload["_meta"]["rights_receipt"]
        post_fetch = receipt["post_fetch"]
        write_boundary = receipt["write_boundary"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ngram_rights.NgramRightsError(
            "nowcast_rights_receipt_invalid"
        ) from exc
    if (
        blob.returncode != 0
        or set(receipt) != {"schema_version", "post_fetch", "write_boundary"}
        or receipt.get("schema_version") != "1.0.0"
        or payload.get("provisional") is not True
    ):
        raise ngram_rights.NgramRightsError("nowcast_rights_receipt_invalid")
    try:
        post_fetch = ngram_rights.validate_public_identity_rights_proof(
            post_fetch, target=target
        )
        write_boundary = ngram_rights.validate_public_identity_rights_proof(
            write_boundary, target=target
        )
        generated_text = payload["_meta"]["generated"]
        if not isinstance(generated_text, str) or not generated_text.endswith("Z"):
            raise ValueError
        generated = datetime.fromisoformat(generated_text[:-1] + "+00:00")
        as_of = datetime.strptime(str(payload["as_of_utc"]), "%H:%M").time()
        post_fetch_at = datetime.fromisoformat(
            post_fetch["evaluated_at_utc"][:-1] + "+00:00"
        )
        write_at = datetime.fromisoformat(
            write_boundary["evaluated_at_utc"][:-1] + "+00:00"
        )
    except (KeyError, TypeError, ValueError, ngram_rights.NgramRightsError) as exc:
        raise ngram_rights.NgramRightsError(
            "nowcast_rights_receipt_invalid"
        ) from exc
    current = ngram_rights.require_public_identity_rights(
        target=target,
        root=root,
        test_authority=rights_authority,
    )
    current = ngram_rights.validate_public_identity_rights_proof(
        current, target=target
    )
    current_at = datetime.fromisoformat(
        current["evaluated_at_utc"][:-1] + "+00:00"
    )
    if (
        current["rights_as_of"] != target.isoformat()
        or generated.date() != target
        or generated.time().replace(second=0, microsecond=0) != as_of
        or generated > post_fetch_at
        or post_fetch_at > write_at
        or write_at > current_at
    ):
        raise ngram_rights.NgramRightsError("nowcast_time_order_invalid")
    current_binding = _rights_authority_binding(current)
    if (
        _rights_authority_binding(post_fetch) != current_binding
        or _rights_authority_binding(write_boundary) != current_binding
    ):
        raise ngram_rights.NgramRightsError("nowcast_rights_receipt_drift")
    return {
        "status": "nowcast_release_rights_verified",
        "candidate_sha": expected_candidate_sha,
        "target_date": target.isoformat(),
        "release_rights_evaluation": current,
    }


def _percentile_vs_store(store: pd.DataFrame, channel: str,
                         value: float, today: pd.Timestamp) -> float | None:
    """Today's provisional value ranked exactly as _trailing_percentile
    ranks a finished day: against the channel's trailing window with
    today's value included in the comparison set."""
    lo = today - pd.Timedelta(days=PERCENTILE_WINDOW_DAYS)
    window = store.loc[(store.index > lo) & (store.index < today), channel]
    v = window.to_numpy(dtype=float)
    v = v[~np.isnan(v)]
    if len(v) < MIN_OBS:
        return None
    a = np.append(v, value)
    return round(100.0 * float(np.mean(a <= value)), 1)


def main(
    *,
    rights_authority: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    until_minute = now.hour * 60 + now.minute - FEED_LAG_MIN
    if until_minute < MIN_DAY_MINUTES:
        print(f"[nowcast] only {max(until_minute, 0)} usable minutes of "
              f"{now:%Y-%m-%d} so far; too early, not writing")
        return

    if not CALIB.exists():
        sys.exit("[nowcast] no splice calibration; refusing to publish "
                 "uncalibrated levels")
    calib = json.loads(CALIB.read_text(encoding="utf-8"))

    specs = fetch_ngrams.group_specs()
    # compute_day, not _cached_day: a partial-day result must never
    # poison the heal path's per-day cache.
    result = fetch_ngrams.compute_day(
        now.date(),
        specs,
        until_minute=until_minute,
        min_docs=MIN_DOCS,
        rights_authority=rights_authority,
    )
    if result is None:
        print("[nowcast] sample too thin or feed gap; not writing")
        return
    post_fetch_rights = ngram_rights.require_public_identity_rights(
        target=now.date(), root=ROOT, test_authority=rights_authority
    )

    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        dictionaries = json.load(f)
    store = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")

    sums = fetch_ngrams._channel_sums(result, specs)
    today = pd.Timestamp(now.date())
    channels: dict[str, dict] = {}
    scores = []
    for ch, raw in sums.items():
        if ch not in calib:
            continue
        spliced = raw / calib[ch]["ratio"]
        score = _percentile_vs_store(store, ch, spliced, today)
        channels[ch] = {"label": dictionaries[ch]["label"], "score": score}
        scores.append(score)

    valid = [s for s in scores if s is not None]
    # Strict like the daily composite (skipna=False): one unscorable
    # channel means no composite, not a shifted mean.
    composite = (round(float(np.mean(valid)), 1)
                 if valid and len(valid) == len(scores) else None)
    # nowcast.yml is its own workflow and never runs stamp_meta, so a
    # payload stamped by the daily lane gets overwritten unstamped a few
    # hours later -- which is exactly what happened at 11:34 today.
    # Carrying the universal fields here makes it independent of which
    # lane wrote last, the same fix freshness.py needed.
    from src import stamp_meta
    payload = {
        "_meta": {
            **stamp_meta.universal_fields("nowcast.json"),
            "what": ("PROVISIONAL today-so-far scores from a partial-day "
                     "sample of the GDELT Web NGrams bridge. Superseded by "
                     "the daily run's finalized number; never part of the "
                     "historical series."),
            "definition": DEFINITION,
            "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "date": now.date().isoformat(),
        "as_of_utc": now.strftime("%H:%M"),
        "provisional": True,
        "n_samples": result["n_samples"],
        "n_docs_sampled": result["n_docs_sampled"],
        "composite": composite,
        "channels": channels,
    }
    write_rights = ngram_rights.require_public_identity_rights(
        target=now.date(), root=ROOT, test_authority=rights_authority
    )
    payload["_meta"]["rights_receipt"] = {
        "schema_version": "1.0.0",
        "post_fetch": post_fetch_rights,
        "write_boundary": write_rights,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload), encoding="utf-8")
    print(f"[nowcast] {now.date()} as of {payload['as_of_utc']}Z: "
          f"composite {composite} from {result['n_docs_sampled']} docs "
          f"across {result['n_samples']} samples")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check-release-rights":
        print(json.dumps(require_release_rights(sys.argv[2]), indent=1))
    else:
        main()
