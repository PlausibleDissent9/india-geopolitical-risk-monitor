"""
GDELT Web NGrams v5 bridge -- the maintainer-sanctioned temporary path.

On 2026-07-28 Kalev Leetaru (GDELT's maintainer) replied to this
project's backfill request: "switch to the temporary new ngrams dataset
instead of using the APIs." This module computes the SAME construct as
the DOC API's timelinevol -- percent of monitored English articles
matching each sub-query -- directly from the raw per-minute quadgram
files, and heals missing recent days in data/raw/gdelt_volume.csv.

Files (per minute, irregular within 15-minute heartbeats):
  .../gdeltv5/weblegacy/ngrams/YYYYMMDDHHMMSS.ngrams.txt.gz
      DOCID <tab> QUADGRAM <tab> COUNT
  .../gdeltv5/weblegacy/ngrams/YYYYMMDDHHMMSS.toc.json.gz
      one JSON record per line: ID, date, img, lang, title, url

Method, per day:
  - Sample the first available minute-file in each hour (24 samples;
    ~90k articles). A day's share is estimated over the pooled sample.
  - A document matches a phrase if the phrase's normalized tokens appear
    as a contiguous subsequence of any of its quadgrams (all dictionary
    terms are <= 4 tokens; enforced by test).
  - Channel anchors (e.g. India) apply per document -- a stricter, truer
    AND than the API's -- and matching is restricted to lang == "en",
    mirroring timelinevol's English default.
  - Channel series value = sum of its sub-query group shares, matching
    the frozen construction, in the same percent units.

Sampling noise (~hourly x ~3.8k articles) and the source switch are
disclosed in the methodology changelog -- the author's wording; see
NOTES_FOR_ISHAN.md.

Usage:
  python -m src.fetch_ngrams --heal 35      # fill missing days in store
  python -m src.fetch_ngrams 2026-07-05     # recompute one day (debug)
Cache: data/raw/ngram_days/YYYY-MM-DD.json (one file per healed day).
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from . import ngram_rights
from .fetch_gdelt import build_queries

BASE = ("https://storage.googleapis.com/data.gdeltproject.org/"
        "gdeltv5/weblegacy/ngrams/")
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DAY_CACHE = RAW_DIR / "ngram_days"
STORE = RAW_DIR / "gdelt_volume.csv"

# 48 half-hourly samples (~30k articles/day): calibration at 24 showed
# the thin channels' daily scatter is pure Poisson noise in the sampled
# match counts, so sample size is the lever. Ratios calibrated at 24
# remain valid -- sampling moves variance, not level.
SAMPLES_PER_DAY = 48
# The heartbeat drops files at arbitrary minutes (observed :01, :02, :16),
# so every minute of a sampling window is probed until the first hit.
HEADERS = {"User-Agent": "IGRM/1.0 (ngrams bridge, per maintainer guidance)"}
PUBLISH_LAG_DAYS = 1          # today's files are still accumulating
DOCUMENT_IDENTITY_DOMAIN = b"igrm-ngram-document-identity-v1\0"
MATCHER_EVIDENCE_VERSION = "1.1.0"
_IDENTITY_EVIDENCE_FIELDS = frozenset(
    {
        "english_document_identities",
        "english_document_counts_by_stamp",
        "india_document_keys",
        "matched_document_keys",
        "article_meta",
    }
)


class NgramAcquisitionError(RuntimeError):
    """The source could not be classified as absent because I/O failed."""


def _norm_tokens(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " ")).split()


def group_specs() -> dict[str, dict]:
    """{group_key: {channel, phrases(token tuples), anchor}} from the
    frozen dictionaries, one group per sub-query."""
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        d = json.load(f)
    out: dict[str, dict] = {}
    for ch, spec in d.items():
        if ch.startswith("_"):
            continue
        anchor = (spec.get("anchor") or "").lower() or None
        # Recover each sub-query's term list by re-partitioning exactly
        # as build_queries does, then stripping quotes per term.
        queries = build_queries(spec["terms"], spec.get("anchor"))
        remaining = [t.strip('"') for t in spec["terms"]]
        for qi, q in enumerate(queries):
            n_terms = q.count('"') // 2
            phrases = [tuple(_norm_tokens(t)) for t in remaining[:n_terms]]
            remaining = remaining[n_terms:]
            out[f"{ch}/q{qi + 1}"] = {
                "channel": ch, "phrases": phrases, "anchor": anchor,
            }
    return out


def _canonical_specs(specs: dict[str, dict]) -> dict[str, dict]:
    """JSON-safe snapshot of the matcher semantics used for one score day."""
    return {
        group: {
            "channel": spec["channel"],
            "anchor": spec.get("anchor"),
            "phrases": [list(phrase) for phrase in spec["phrases"]],
        }
        for group, spec in sorted(specs.items())
    }


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document_identity(key: str) -> str:
    """Commit a source document identity without redistributing its raw ID."""

    stamp, separator, source_id = key.partition(":")
    if not separator or not stamp or not source_id:
        raise ValueError("document key must contain stamp and source ID")
    digest = hashlib.sha256(
        DOCUMENT_IDENTITY_DOMAIN
        + stamp.encode("ascii")
        + b"\0"
        + source_id.encode("utf-8")
    ).hexdigest()
    return f"{stamp}:{digest}"


def _matcher_evidence(
    day: date,
    specs: dict[str, dict],
    located_stamps: list[str],
    loaded_stamps: list[str],
    missing_stamps: list[str],
    english_docs: set[str],
    india_docs: set[str],
    matched: dict[str, set[str]],
    article_meta: dict[str, dict[str, str]],
) -> dict:
    """Freeze the exact numerator and denominator frame in the day cache.

    This is prospective study infrastructure, not a precision result.  It
    prevents a future audit from reconstructing a look-alike corpus after the
    score has already been published (the defect that invalidated audit v2).
    Denominator membership is a domain-separated hash commitment, not raw
    source IDs or source content.  This is an integrity/recomputation choice;
    it does not assert redistribution approval, which remains an independent
    rights review.
    """
    identities = {key: _document_identity(key) for key in english_docs}
    english_identities = sorted(identities.values())
    counts_by_stamp = {
        stamp: sum(identity.startswith(f"{stamp}:") for identity in english_identities)
        for stamp in loaded_stamps
    }
    canonical_specs = _canonical_specs(specs)
    encoded_specs = json.dumps(
        canonical_specs, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "schema_version": MATCHER_EVIDENCE_VERSION,
        "day": day.isoformat(),
        "located_stamps": located_stamps,
        "loaded_stamps": loaded_stamps,
        "missing_stamps": missing_stamps,
        "matcher_specs": canonical_specs,
        "matcher_specs_sha256": hashlib.sha256(encoded_specs).hexdigest(),
        "dictionaries_sha256": _sha256_path(ROOT / "dictionaries.json"),
        "production_matcher_sha256": _sha256_path(Path(__file__)),
        "english_document_identities": english_identities,
        "english_document_counts_by_stamp": counts_by_stamp,
        "india_document_keys": sorted(identities[key] for key in india_docs),
        "matched_document_keys": {
            group: sorted(identities[key] for key in keys)
            for group, keys in sorted(matched.items())
        },
        "article_meta": {
            identities[key]: article_meta[key] for key in sorted(article_meta)
        },
    }


def _fetch(url: str) -> bytes | None:
    # IGRM_OFFLINE is the reproducibility contract: scripts/reproduce.sh
    # --use-cache promises "ALL acquisition is refused" so the committed
    # store is the only data source. fetch_gdelt honoured that; the
    # NGrams bridge never did, so any lane reaching it -- src.uncertainty
    # reads day caches through it -- could silently refetch mid-run and
    # turn a reproduction into a recomputation against newer data.
    # Refusal is loud rather than an empty return: a caller that quietly
    # got None would treat a policy refusal as a missing file.
    if os.environ.get("IGRM_OFFLINE"):
        raise RuntimeError(
            f"[ngrams] IGRM_OFFLINE is set; refusing to fetch {url}. "
            "Offline mode serves committed caches only.")
    last_error: requests.RequestException | None = None
    for attempt in (1, 2):
        try:
            r = requests.get(url, timeout=120, headers=HEADERS)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(3)
    raise NgramAcquisitionError(
        f"GET failed without a source-absence response: {url}"
    ) from last_error


def _probe_window(day: date, base_minute: int, window_min: int) -> str | None:
    """First existing timestamp inside one sampling window, probing its
    minutes in order (the heartbeat drops files at arbitrary minutes)."""
    if os.environ.get("IGRM_OFFLINE"):
        raise RuntimeError(
            "[ngrams] IGRM_OFFLINE is set; refusing to probe for "
            f"{day} minute-files. Offline mode serves committed caches "
            "only.")
    last_error: requests.RequestException | None = None
    for offset in range(window_min):
        m = base_minute + offset
        ts = f"{day:%Y%m%d}{m // 60:02d}{m % 60:02d}00"
        try:
            r = requests.head(f"{BASE}{ts}.ngrams.txt.gz",
                              timeout=30, headers=HEADERS)
            if r.status_code == 200:
                return ts
            if r.status_code != 404:
                r.raise_for_status()
        except requests.RequestException as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise NgramAcquisitionError(
            f"HEAD probe failed without proving source absence for {day} "
            f"window {base_minute}:{base_minute + window_min}"
        ) from last_error
    return None


def _day_minute_files(day: date, until_minute: int | None = None,
                      samples: int = SAMPLES_PER_DAY) -> list[str]:
    """One existing timestamp per sampling window (`samples` equal
    windows across the day; the scoring default is SAMPLES_PER_DAY, and
    samples=1440 degenerates to one-minute windows, i.e. every existing
    file -- the receipts extended scan). Windows are independent, so
    they are probed concurrently (founder-approved parallelization,
    2026-08-06); results keep window order, so the stamp list is
    identical to the sequential scan's. until_minute stops early for
    partial-day sampling (the nowcast)."""
    window_min = 1440 // samples
    bases = []
    for w in range(samples):
        base_minute = w * window_min
        if until_minute is not None and base_minute >= until_minute:
            break
        bases.append(base_minute)
    with ThreadPoolExecutor(max_workers=8) as pool:
        found = pool.map(lambda b: _probe_window(day, b, window_min), bases)
    return [ts for ts in found if ts is not None]


def scoring_stamps(all_stamps: list[str], day: date) -> set[str]:
    """Which of a day's stamps the SCORING sample would have used: the
    first existing file in each of the SAMPLES_PER_DAY windows. Derived
    arithmetically from the full stamp list, no extra probing, so the
    receipts extended scan can label 'in scored sample' exactly."""
    window_min = 1440 // SAMPLES_PER_DAY
    first_in_window: dict[int, str] = {}
    prefix = f"{day:%Y%m%d}"
    for ts in sorted(all_stamps):
        if not ts.startswith(prefix):
            continue
        minute = int(ts[8:10]) * 60 + int(ts[10:12])
        w = minute // window_min
        first_in_window.setdefault(w, ts)
    return set(first_in_window.values())


def prefetch_pairs(stamps: list[str], workers: int = 4, ahead: int = 6):
    """Yield (ts, toc_gz, ng_gz) in stamp order while later downloads
    run ahead on threads. The parse stays serial (and byte-identical);
    only the waiting overlaps. Submission is BOUNDED at `ahead` in
    flight: an unbounded map would buffer every finished ~21MB blob
    ahead of a slow parser and can exhaust a 2GB droplet; six in flight
    caps the buffer near 150MB while keeping the workers saturated."""
    def fetch_pair(ts: str) -> tuple[str, bytes | None, bytes | None]:
        return (ts, _fetch(f"{BASE}{ts}.toc.json.gz"),
                _fetch(f"{BASE}{ts}.ngrams.txt.gz"))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending: deque = deque()
        idx = 0
        while idx < len(stamps) and len(pending) < ahead:
            pending.append(pool.submit(fetch_pair, stamps[idx]))
            idx += 1
        while pending:
            ts, toc_gz, ng_gz = pending.popleft().result()
            if idx < len(stamps):
                pending.append(pool.submit(fetch_pair, stamps[idx]))
                idx += 1
            yield ts, toc_gz, ng_gz


def _subseq(phrase: tuple[str, ...], tokens: list[str]) -> bool:
    n, m = len(tokens), len(phrase)
    return any(tuple(tokens[i:i + m]) == phrase for i in range(n - m + 1))


def compute_day(
    day: date, specs: dict[str, dict],
    until_minute: int | None = None, min_docs: int = 5000,
    *,
    rights_authority: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict | None:
    """Pooled-sample shares for one day; None if no files exist. The
    nowcast passes until_minute for a partial day and a lower min_docs
    (its payload discloses the sample size; the heal path keeps the
    full-day floor)."""
    # This is the common network and identity-construction entry point used
    # by finalized acquisition, calibration, debugging and nowcast. Rights
    # must dominate the first source probe, not merely later cache/promotion
    # paths. The current production registry is pending, so every caller
    # refuses before touching the source until an applicable decision exists.
    ngram_rights.require_public_identity_rights(
        target=day, root=ROOT, test_authority=rights_authority
    )
    stamps = _day_minute_files(day, until_minute)
    if not stamps:
        return None

    # Fast pre-filter: any line worth tokenizing contains one of these.
    fragments = sorted({p[0] for s in specs.values() for p in s["phrases"]})
    trigger = re.compile("|".join(re.escape(f) for f in fragments + ["india"]))

    en_docs: set[str] = set()
    india_docs: set[str] = set()
    matched: dict[str, set[str]] = {g: set() for g in specs}
    article_meta: dict[str, dict[str, str]] = {}
    loaded_stamps: list[str] = []
    missing_stamps: list[str] = []

    for ts, toc_gz, ng_gz in prefetch_pairs(stamps):
        if not toc_gz or not ng_gz:
            missing_stamps.append(ts)
            continue
        loaded_stamps.append(ts)
        toc_en: dict[str, dict[str, str]] = {}
        for line in gzip.decompress(toc_gz).decode("utf-8", "replace").splitlines():
            line = line.strip().rstrip(",")
            if not line or line in "[]":
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("lang") == "en":
                docid = str(rec.get("ID"))
                raw_date = re.sub(r"[^0-9]", "", str(rec.get("date") or ""))[:8]
                toc_en[docid] = {
                    "url": str(rec.get("url") or ""),
                    "title": str(rec.get("title") or ""),
                    "date": raw_date or f"{day:%Y%m%d}",
                }
        en_docs |= {f"{ts}:{i}" for i in toc_en}

        with gzip.open(io.BytesIO(ng_gz), "rt", encoding="utf-8",
                       errors="replace") as fh:
            for raw in fh:
                low = raw.lower()
                if not trigger.search(low):
                    continue
                parts = raw.rstrip("\n").split("\t")
                if len(parts) < 2:
                    continue
                docid, quad = parts[0], parts[1]
                if docid not in toc_en:
                    continue
                key = f"{ts}:{docid}"
                tokens = _norm_tokens(quad)
                if "india" in tokens:
                    india_docs.add(key)
                for g, s in specs.items():
                    if key in matched[g]:
                        continue
                    for ph in s["phrases"]:
                        if len(ph) <= len(tokens) and _subseq(ph, tokens):
                            matched[g].add(key)
                            article_meta.setdefault(key, toc_en[docid])
                            break

    total = len(en_docs)
    if total < min_docs:  # a sample this thin is a feed gap, not a measurement
        raise NgramAcquisitionError(
            f"located source frame has {total} documents; minimum is {min_docs}"
        )
    shares = {}
    for g, s in specs.items():
        hits = matched[g] & india_docs if s["anchor"] == "india" else matched[g]
        shares[g] = round(100.0 * len(hits & en_docs) / total, 6)
    result = {
        "date": day.isoformat(),
        "n_docs_sampled": total,
        # Preserve the legacy meaning: located sampling windows.  Loaded and
        # missing counts are additive so a partial acquisition cannot look
        # complete to a future reviewer.
        "n_samples": len(stamps),
        "n_samples_loaded": len(loaded_stamps),
        "partial": bool(missing_stamps or len(loaded_stamps) != len(stamps)),
        "shares": shares,
        "_matcher_evidence": _matcher_evidence(
            day,
            specs,
            stamps,
            loaded_stamps,
            missing_stamps,
            en_docs,
            india_docs,
            matched,
            article_meta,
        ),
    }
    # Network work may cross a rights deadline or revocation boundary. Do not
    # hand identity-bearing evidence to any caller under a stale pre-fetch
    # decision; writers perform their own additional boundary check.
    ngram_rights.require_public_identity_rights(
        target=day, root=ROOT, test_authority=rights_authority
    )
    return result


def _cached_day(
    day: date,
    specs: dict[str, dict],
    *,
    rights_authority: ngram_rights.NonGitTestRightsAuthority | None = None,
) -> dict | None:
    cache = DAY_CACHE / f"{day.isoformat()}.json"
    if cache.exists():
        raw = cache.read_bytes()
        cached = json.loads(raw)
        evidence = cached.get("_matcher_evidence") if isinstance(cached, dict) else None
        # A version label is attacker-controlled metadata, not a rights
        # boundary.  Identity retention is classified from the evidence
        # fields themselves.  The sole rights-free read is the exact Aug-9
        # object whose full public history is pinned by final_publication.
        from . import final_publication

        legacy_exception = final_publication.is_exact_legacy_cache_exception(
            ROOT, day, cache_bytes=raw
        )
        if legacy_exception:
            return cached
        identity_bearing = isinstance(evidence, dict) and bool(
            _IDENTITY_EVIDENCE_FIELDS.intersection(evidence)
        )
        if identity_bearing or not legacy_exception:
            ngram_rights.require_public_identity_rights(
                target=day,
                root=ROOT,
                test_authority=rights_authority,
            )
        return cached
    result = compute_day(day, specs, rights_authority=rights_authority)
    if result is not None:
        ngram_rights.require_public_identity_rights(
            target=day,
            root=ROOT,
            test_authority=rights_authority,
        )
        DAY_CACHE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(result), encoding="utf-8")
    return result


def _channel_sums(result: dict, specs: dict[str, dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for g, share in result["shares"].items():
        ch = specs[g]["channel"]
        out[ch] = out.get(ch, 0.0) + share
    return out


def calibrate(days: list[date]) -> dict:
    """Splice calibration: per-channel geometric-mean ratio of ngram to
    API values over overlap days, with the ratio spread (CV) as the
    bridge's published fidelity metric. Standard ratio linking for a
    source change; disclosed in the methodology changelog."""
    import math

    specs = group_specs()
    store = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")
    ratios: dict[str, list[float]] = {}
    for day in days:
        result = _cached_day(day, specs)
        if result is None:
            print(f"[ngrams] {day}: no data; skipped in calibration")
            continue
        sums = _channel_sums(result, specs)
        ts = pd.Timestamp(day)
        for ch, v in sums.items():
            api = store.loc[ts, ch] if ts in store.index else float("nan")
            if pd.notna(api) and api > 0 and v > 0:
                ratios.setdefault(ch, []).append(v / api)
    calib = {}
    for ch, rs in ratios.items():
        log_rs = [math.log(r) for r in rs]
        mean = math.exp(sum(log_rs) / len(log_rs))
        sd = (sum((math.log(r) - sum(log_rs) / len(log_rs)) ** 2
                  for r in rs) / max(len(rs) - 1, 1)) ** 0.5
        calib[ch] = {"ratio": round(mean, 4), "log_sd": round(sd, 4),
                     "n_days": len(rs)}
        print(f"[ngrams] {ch}: ratio {mean:.2f} (log-sd {sd:.3f}, n={len(rs)})")
    path = RAW_DIR / "ngram_calibration.json"
    path.write_text(json.dumps(calib, indent=1), encoding="utf-8")
    print(f"[ngrams] wrote {path}")
    return calib


def heal(max_days: int) -> int:
    """Compatibility entrypoint for the exact append-only D-1 recovery.

    The historical implementation searched a window and wrote every located
    day straight into the canonical store.  That could revise an already
    published prefix and could bank a one-stamp day because ``partial`` only
    described missing *located* stamps.  Final recovery is now target-only:
    the existing promotion boundary acquires fresh bytes, requires the
    registered 48/48 attestation, binds the calibration and matcher regime,
    and appends exactly one D-1 row or writes only a value-free refusal.

    ``max_days`` remains accepted so existing scheduled invocations do not
    change shape; widening it no longer broadens publication authority.
    """

    _ = max_days
    from . import final_publication

    today = final_publication.utc_today()
    target = final_publication.required_target(today)
    status = final_publication.acquire_target(target, today=today, root=ROOT)
    state = status["status"]
    if state == "target_ready":
        print(f"[ngrams] exact 48/48 D-1 candidate banked for {target}")
        return 1
    if state == "already_finalized":
        print(f"[ngrams] exact D-1 final already published for {target}")
        return 0
    print(f"[ngrams] {target}: {state}; canonical value/provenance unchanged")
    return 0


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--heal":
        heal(int(sys.argv[2]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "--calibrate":
        d0, d1 = (date.fromisoformat(s) for s in sys.argv[2:4])
        days = []
        while d0 <= d1:
            days.append(d0)
            d0 += timedelta(days=1)
        calibrate(days)
    elif len(sys.argv) == 2:
        result = _cached_day(date.fromisoformat(sys.argv[1]), group_specs())
        print(json.dumps(result, indent=1))
    else:
        sys.exit("usage: python -m src.fetch_ngrams --heal N | "
                 "--calibrate D0 D1 | YYYY-MM-DD")


if __name__ == "__main__":
    main()
