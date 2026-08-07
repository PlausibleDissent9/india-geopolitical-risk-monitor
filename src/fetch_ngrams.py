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

from . import provenance
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
    for attempt in (1, 2):
        try:
            r = requests.get(url, timeout=120, headers=HEADERS)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if attempt == 2:
                return None
            time.sleep(3)
    return None


def _probe_window(day: date, base_minute: int, window_min: int) -> str | None:
    """First existing timestamp inside one sampling window, probing its
    minutes in order (the heartbeat drops files at arbitrary minutes)."""
    if os.environ.get("IGRM_OFFLINE"):
        raise RuntimeError(
            "[ngrams] IGRM_OFFLINE is set; refusing to probe for "
            f"{day} minute-files. Offline mode serves committed caches "
            "only.")
    for offset in range(window_min):
        m = base_minute + offset
        ts = f"{day:%Y%m%d}{m // 60:02d}{m % 60:02d}00"
        try:
            r = requests.head(f"{BASE}{ts}.ngrams.txt.gz",
                              timeout=30, headers=HEADERS)
        except requests.RequestException:
            continue
        if r.status_code == 200:
            return ts
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
) -> dict | None:
    """Pooled-sample shares for one day; None if no files exist. The
    nowcast passes until_minute for a partial day and a lower min_docs
    (its payload discloses the sample size; the heal path keeps the
    full-day floor)."""
    stamps = _day_minute_files(day, until_minute)
    if not stamps:
        return None

    # Fast pre-filter: any line worth tokenizing contains one of these.
    fragments = sorted({p[0] for s in specs.values() for p in s["phrases"]})
    trigger = re.compile("|".join(re.escape(f) for f in fragments + ["india"]))

    en_docs: set[str] = set()
    india_docs: set[str] = set()
    matched: dict[str, set[str]] = {g: set() for g in specs}

    for ts, toc_gz, ng_gz in prefetch_pairs(stamps):
        if not toc_gz or not ng_gz:
            continue
        toc_en: set[str] = set()
        for line in gzip.decompress(toc_gz).decode("utf-8", "replace").splitlines():
            line = line.strip().rstrip(",")
            if not line or line in "[]":
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("lang") == "en":
                toc_en.add(str(rec.get("ID")))
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
                            break

    total = len(en_docs)
    if total < min_docs:  # a sample this thin is a feed gap, not a measurement
        return None
    shares = {}
    for g, s in specs.items():
        hits = matched[g] & india_docs if s["anchor"] == "india" else matched[g]
        shares[g] = round(100.0 * len(hits & en_docs) / total, 6)
    return {"date": day.isoformat(), "n_docs_sampled": total,
            "n_samples": len(stamps), "shares": shares}


def _cached_day(day: date, specs: dict[str, dict]) -> dict | None:
    DAY_CACHE.mkdir(parents=True, exist_ok=True)
    cache = DAY_CACHE / f"{day.isoformat()}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    result = compute_day(day, specs)
    if result is not None:
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
    """Fill store days missing/NaN for any channel, newest window first.
    Returns the number of days written."""
    specs = group_specs()
    channels = sorted({s["channel"] for s in specs.values()})
    store = pd.read_csv(STORE, parse_dates=["date"]).set_index("date")
    last_allowed = date.today() - timedelta(days=PUBLISH_LAG_DAYS)
    first_needed = min(store.dropna(how="any").index.max().date(),
                       last_allowed - timedelta(days=max_days))

    targets = []
    d = first_needed
    while d <= last_allowed:
        ts = pd.Timestamp(d)
        if ts not in store.index or store.loc[ts, channels].isna().any():
            targets.append(d)
        d += timedelta(days=1)
    if not targets:
        print("[ngrams] store already current; nothing to heal")
        return 0

    calib_path = RAW_DIR / "ngram_calibration.json"
    if not calib_path.exists():
        sys.exit("[ngrams] no calibration -- run --calibrate first; the "
                 "bridge must never splice uncalibrated levels")
    calib = json.loads(calib_path.read_text(encoding="utf-8"))

    wrote = 0
    for day in targets:
        print(f"[ngrams] sampling {day}")
        result = _cached_day(day, specs)
        if result is None:
            print(f"[ngrams] {day}: no usable files; skipping")
            continue
        for ch, v in _channel_sums(result, specs).items():
            if ch not in calib:
                continue
            store.loc[pd.Timestamp(day), ch] = v / calib[ch]["ratio"]
        # A spliced day is a different instrument's measurement wearing
        # the API's scale. Recording that at the moment it happens is
        # the only way the published series can ever say so honestly;
        # everything earlier than this line has to be RECONSTRUCTED
        # (src/provenance.py) because nothing wrote it down.
        provenance.record_bridged(day.isoformat())
        wrote += 1

    store.sort_index().to_csv(STORE, index_label="date")
    print(f"[ngrams] healed {wrote} day(s) into {STORE.name}")
    return wrote


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
