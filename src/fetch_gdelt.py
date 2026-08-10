"""
Fetch daily news-volume intensity per channel from the GDELT DOC 2.0 API.

Method (mirrors Caldara-Iacoviello's article-share logic):
  mode=timelinevol returns, per day, the % of ALL global articles GDELT
  monitored that match the query. Using a share rather than a raw count
  partially controls for GDELT's secular volume growth; we still
  normalize downstream in build_index.py.

Coverage: DOC API reaches back to ~1 Jan 2017. That is the backfill floor.

Known failure modes (expect these in the first debug loop):
  - GDELT sometimes returns an HTML error page with HTTP 200. We detect
    non-JSON bodies and retry with backoff.
  - Very long date ranges are chunked (180 days) to keep responses small.
  - Be polite: 1s sleep between calls. This is a free public API.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

API = "https://api.gdeltproject.org/api/v2/doc/doc"
# Verified 2026-07-25: a single timelinevol request returns the full
# 2017->today range at daily granularity (3,467 points). The original
# 180-day chunking spent 140 rate-limited requests where 7 suffice; the
# chunk machinery remains for cache reuse and future range growth.
CHUNK_DAYS = 3700
# GDELT rejects long queries with an HTTP-200 "Your query was too short or
# too long" body. Measured 2026-07-24: 222 chars accepted, 271 rejected.
# Channels whose full term set composes past this budget are partitioned
# into sub-queries and their shares SUMMED -- a slight upper bound on the
# union share when two groups match the same article (methodology s3).
QUERY_MAX_CHARS = 230
# Days a chunk must be fully in the past before it is cached: GDELT
# revises recent days, so only settled chunks are reused.
CACHE_SETTLE_DAYS = 3
# GDELT DOC API rate-limits at a stated 1 request / 5s, but in practice
# (observed 2026-07-24) even 10s spacing trips sustained multi-minute 429
# storms. Steady 15s spacing plus the supervisor script's relaunch-with-
# cooldown (scripts/backfill_supervisor.sh) rides them out; the chunk
# cache makes every crash resumable, so persistence is cheap.
SLEEP_S = 15.0
RETRIES = 6
# A multi-year timelinevol query takes GDELT minutes to compute; the old
# 60s ceiling hung up mid-computation and looked like a failure. A read
# timeout means ACCEPTED-and-working (unlike a 429, refused instantly),
# so wait it out. Verified 2026-07-26: a 3,447-day series returned on the
# first attempt once the deadline was generous.
TIMEOUT_S = 420
# Extra pause specifically after a 429 before retrying, in seconds.
# GDELT's limiter has been observed to persist for a minute-plus, so the
# escalation must reach past it rather than burning retries inside it.
RATE_LIMIT_BACKOFF_S = 30
HEADERS = {
    "User-Agent": "IGRM/1.0 (india-geopolitical-risk-monitor; research index)"
}

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
CHUNK_CACHE_DIR = RAW_DIR / "gdelt_chunks"


class QueryTooLongError(RuntimeError):
    """GDELT rejected the query's length; retrying cannot help."""


class AcquisitionDeadlineExceeded(RuntimeError):
    """The caller's acquisition budget expired before a safe retry.

    This is distinct from an HTTP failure: callers such as the multilingual
    backfill use it to stop cleanly, bank completed series, and leave enough
    runner time for stamping and publication instead of being killed by the
    workflow timeout while a 420-second request is still in flight.
    """


def _remaining_deadline_seconds(deadline_monotonic: float | None) -> float | None:
    if deadline_monotonic is None:
        return None
    remaining = deadline_monotonic - time.monotonic()
    if remaining <= 0:
        raise AcquisitionDeadlineExceeded("acquisition deadline exhausted")
    return remaining


def _sleep_with_deadline(seconds: float, deadline_monotonic: float | None) -> None:
    """Sleep only when the full pause fits inside the caller's budget."""
    remaining = _remaining_deadline_seconds(deadline_monotonic)
    if remaining is not None and seconds >= remaining:
        raise AcquisitionDeadlineExceeded(
            f"acquisition deadline leaves {remaining:.1f}s; refusing "
            f"a {seconds:.1f}s retry pause"
        )
    time.sleep(seconds)


def build_query(terms: list[str], anchor: str | None = None) -> str:
    """One valid GDELT query per channel.

    GDELT DOC API grammar is crude: a space means AND, OR may appear only
    inside parentheses, parens may not be nested, and a paren group may
    not mix AND and OR. So every term must be a single quoted phrase, and
    any disambiguation happens through one channel-level `anchor` word
    ANDed outside the group:  anchor ("t1" OR "t2" ...).
    Enforced by tests/test_dictionaries.py."""
    q = "(" + " OR ".join(terms) + ")"
    return f"{anchor} {q}" if anchor else q


def build_queries(terms: list[str], anchor: str | None = None) -> list[str]:
    """Partition a channel's terms into as few queries as fit the length
    budget, preserving term order. Most channels need two groups."""
    groups: list[list[str]] = []
    cur: list[str] = []
    for term in terms:
        if len(build_query([term], anchor)) > QUERY_MAX_CHARS:
            raise ValueError(f"single term exceeds query budget: {term!r}")
        if cur and len(build_query(cur + [term], anchor)) > QUERY_MAX_CHARS:
            groups.append(cur)
            cur = []
        cur.append(term)
    if cur:
        groups.append(cur)
    return [build_query(g, anchor) for g in groups]


def _fetch_chunk(
    query: str, start: date, end: date, mode: str = "timelinevol",
    retries: int = RETRIES,
    deadline_monotonic: float | None = None,
) -> list[dict]:
    """Fetch one chunk, consulting the on-disk chunk cache first.

    Settled chunks (fully CACHE_SETTLE_DAYS in the past) are cached under a
    key of (mode, query, start, end), which makes interrupted backfills and
    the robustness/placebo refetches resume instead of re-spending the rate
    budget. Cache hits skip the politeness sleep; network fetches pay it."""
    # IGRM_OFFLINE refuses the chunk cache too, not just the network:
    # the cache is an acquisition channel, and serving it here would
    # overwrite store days whose committed values came from a different
    # lane (2026-08-06: the cached reproduce failed on Jul 23-31 because
    # the vintage was ngram-healed -- the VPS's DOC pass had died on a
    # rate limit -- while the rebuild's cache hits rewrote those days
    # with DOC values for exactly the channels that had cached chunks).
    # Offline means the committed store is the only data source.
    if os.environ.get("IGRM_OFFLINE"):
        print(f"[gdelt] OFFLINE: acquisition for {start}..{end} refused; "
              "store values kept")
        return []
    settled = end < date.today() - timedelta(days=CACHE_SETTLE_DAYS)
    # Default mode keeps the original key format so existing caches stay
    # valid; other modes get a distinct namespace.
    key_src = (f"{query}|{start}|{end}" if mode == "timelinevol"
               else f"{mode}|{query}|{start}|{end}")
    key = hashlib.sha1(key_src.encode()).hexdigest()[:16]
    cache_path = CHUNK_CACHE_DIR / f"{key}.json"
    if settled and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    rows = _fetch_chunk_network(
        query, start, end, mode, retries,
        deadline_monotonic=deadline_monotonic,
    )
    if settled:
        CHUNK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(rows), encoding="utf-8")
    # This pause protects the *next* request. Do not throw away a successful
    # response merely because its caller's budget expired while GDELT was
    # computing it; return the complete chunk and let the next network entry
    # enforce the deadline. Sleeping the remaining fraction prevents an
    # immediate follow-up while still letting the caller persist this unit.
    if deadline_monotonic is None:
        time.sleep(SLEEP_S)
    else:
        remaining = max(0.0, deadline_monotonic - time.monotonic())
        if remaining:
            time.sleep(min(SLEEP_S, remaining))
    return rows


def _fetch_chunk_network(
    query: str, start: date, end: date, mode: str = "timelinevol",
    retries: int = RETRIES,
    deadline_monotonic: float | None = None,
) -> list[dict]:
    # Unreachable via _fetch_chunk (which refuses all offline
    # acquisition above), but kept as a guard for any direct caller:
    # offline never touches the network.
    if os.environ.get("IGRM_OFFLINE"):
        print(f"[gdelt] OFFLINE: cache miss for {start}..{end} skipped")
        return []
    params = {
        "query": query,
        "mode": mode,
        "format": "json",
        "startdatetime": start.strftime("%Y%m%d") + "000000",
        "enddatetime": end.strftime("%Y%m%d") + "235959",
    }
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            remaining = _remaining_deadline_seconds(deadline_monotonic)
            request_timeout = (
                TIMEOUT_S if remaining is None else min(TIMEOUT_S, remaining)
            )
            r = requests.get(
                API, params=params, timeout=request_timeout, headers=HEADERS
            )
            if r.status_code == 429:
                # Rate limited: wait the dedicated backoff, then retry.
                raise RuntimeError(f"HTTP 429 rate limit: {r.text[:150]}")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            if "query was too short or too long" in r.text[:120]:
                # Permanent rejection served as HTTP 200 -- do not retry.
                raise QueryTooLongError(f"GDELT rejected query length: {query[:80]}...")
            body = r.json()  # raises ValueError on HTML error pages
            series = body.get("timeline", [])
            if not series:
                return []
            return series[0].get("data", [])
        except QueryTooLongError:
            raise
        except AcquisitionDeadlineExceeded:
            raise
        except (ValueError, requests.RequestException, RuntimeError) as e:
            last_err = e
            # Longer wait if it was a rate-limit; escalating otherwise.
            if "429" in str(e):
                _sleep_with_deadline(
                    RATE_LIMIT_BACKOFF_S * attempt, deadline_monotonic
                )
            else:
                _sleep_with_deadline(2 * attempt, deadline_monotonic)
    raise RuntimeError(
        f"GDELT fetch failed after {retries} attempts for "
        f"{start}..{end}. Last error: {last_err}"
    )


def _fetch_query_series(
    query: str,
    start: date,
    end: date,
    *,
    deadline_monotonic: float | None = None,
) -> pd.Series:
    """Daily volume series for one composed query over [start, end].

    Chunks split at a STABLE settle boundary: the most recent month-end
    at least CACHE_SETTLE_DAYS in the past. Stability is the point -- a
    boundary that moves with today's date changes the historical chunk's
    cache key at every UTC midnight and orphans everything banked (which
    is exactly what happened across the first backfill night). Month-end
    anchoring bounds refetches to twelve per year instead."""
    today = date.today()
    split = date(today.year, today.month, 1) - timedelta(days=1)
    if (today - split).days <= CACHE_SETTLE_DAYS:
        split = date(split.year, split.month, 1) - timedelta(days=1)
    frames: list[pd.DataFrame] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        if cur <= split < chunk_end:
            chunk_end = split
        # The tail (post-split, never cached) is now survivable, so it
        # fails fast: six escalating retries per query wasted ~50 minutes
        # a pass on a range we are willing to go without.
        is_tail = bool(frames)
        try:
            rows = _fetch_chunk(query, cur, chunk_end,
                                retries=2 if is_tail else RETRIES,
                                deadline_monotonic=deadline_monotonic)
        except AcquisitionDeadlineExceeded:
            # A caller deadline is an authority boundary, not an ordinary
            # wide-chunk failure that may be retried as twelve yearly calls.
            raise
        except RuntimeError:
            if frames:
                # The historical range is already in hand; only the recent
                # (never-cached) tail is refused. Publishing a decade of
                # data that ends a few weeks early beats publishing none,
                # and the next successful run fills the gap in.
                print(f"[gdelt] tail {cur}..{chunk_end} unavailable; "
                      "keeping the data already fetched")
                break
            # A decade-wide request is expensive for GDELT to compute and
            # is the first thing its limiter refuses. Fall back to yearly
            # slices: each is cheap, individually cached, and partial
            # success carries over to the next attempt.
            if (chunk_end - cur).days <= 400:
                raise
            print(f"[gdelt] wide chunk refused; retrying {cur}..{chunk_end} "
                  "in yearly slices")
            rows = []
            sub = cur
            while sub <= chunk_end:
                sub_end = min(date(sub.year, 12, 31), chunk_end)
                rows.extend(_fetch_chunk(
                    query, sub, sub_end,
                    deadline_monotonic=deadline_monotonic,
                ))
                sub = sub_end + timedelta(days=1)
        if rows:
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"]).dt.date
            frames.append(df[["date", "value"]])
        cur = chunk_end + timedelta(days=1)
    if not frames:
        return pd.Series(dtype=float, name="value")
    return (
        pd.concat(frames)
        .drop_duplicates(subset="date")
        .set_index("date")["value"]
        .sort_index()
    )


def fetch_channel(
    terms: list[str], start: date, end: date, anchor: str | None = None,
    query_suffix: str = "",
    *,
    deadline_monotonic: float | None = None,
) -> pd.Series:
    """Daily volume-intensity series for one channel over [start, end]:
    the SUM of its sub-query group shares (see QUERY_MAX_CHARS).
    query_suffix appends verbatim operators (e.g. " sourcelang:hin" for
    the V5 multilingual audit); the share stays relative to the matching
    corpus slice, so per-language series rank against their own history."""
    parts = []
    for query in build_queries(terms, anchor):
        series = _fetch_query_series(
            query + query_suffix,
            start,
            end,
            deadline_monotonic=deadline_monotonic,
        )
        if not series.empty:
            parts.append(series)
    if not parts:
        return pd.Series(dtype=float, name="value")
    return pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).sort_index()


def fetch_corpus_norm(query: str, start: date, end: date) -> pd.DataFrame:
    """timelinevolraw for one query: per-day matching-article counts
    ('value') and the total monitored corpus ('norm'). The norm column is
    the denominator behind every share and the direct measure of GDELT's
    corpus drift (validate.py drift mode)."""
    frames: list[pd.DataFrame] = []
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=CHUNK_DAYS - 1), end)
        rows = _fetch_chunk(query, cur, chunk_end, mode="timelinevolraw")
        if rows:
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"]).dt.date
            frames.append(df[["date", "value", "norm"]])
        cur = chunk_end + timedelta(days=1)
    if not frames:
        return pd.DataFrame(columns=["value", "norm"])
    return (
        pd.concat(frames)
        .drop_duplicates(subset="date")
        .set_index("date")
        .sort_index()
    )


def fetch_articles(
    query: str, start: date, end: date, maxrecords: int = 15,
    sort: str = "hybridrel",
) -> list[dict]:
    """Article list for a query window (mode=artlist): headline, source
    domain, date, URL. Used by the precision audit and the weekly dossier.
    Not chunk-cached: article lists are small, ad hoc, and date-scoped."""
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(maxrecords),
        "sort": sort,
        "startdatetime": start.strftime("%Y%m%d") + "000000",
        "enddatetime": end.strftime("%Y%m%d") + "235959",
    }
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(API, params=params, timeout=TIMEOUT_S, headers=HEADERS)
            if r.status_code == 429:
                raise RuntimeError(f"HTTP 429 rate limit: {r.text[:150]}")
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            arts = r.json().get("articles", [])
            time.sleep(SLEEP_S)
            return [
                {
                    "title": a.get("title", ""),
                    "domain": a.get("domain", ""),
                    "date": a.get("seendate", "")[:8],
                    "url": a.get("url", ""),
                }
                for a in arts
            ]
        except (ValueError, requests.RequestException, RuntimeError) as e:
            last_err = e
            time.sleep(RATE_LIMIT_BACKOFF_S * attempt if "429" in str(e) else 2 * attempt)
    raise RuntimeError(f"GDELT artlist failed after {RETRIES} attempts: {last_err}")


def fetch_all(dictionaries: dict, start: date, end: date) -> pd.DataFrame:
    """DataFrame indexed by date, one column per channel."""
    cols = {}
    for ch, spec in dictionaries.items():
        if ch.startswith("_"):
            continue
        print(f"[gdelt] {ch}: {start} -> {end}")
        cols[ch] = fetch_channel(spec["terms"], start, end, spec.get("anchor"))
    return pd.DataFrame(cols)


def load_or_update(
    dictionaries: dict,
    backfill_from: date | None = None,
    *,
    end_date: date | None = None,
    immutable_through: date | None = None,
) -> pd.DataFrame:
    """Incremental store: keep raw volumes in data/raw/gdelt_volume.csv.
    Daily runs fetch a 14-day tail and merge (GDELT revises recent days);
    --backfill fetches from backfill_from (default 2017-01-01).

    A finalized-publication caller supplies ``end_date=D-1`` and the last
    already-published day as ``immutable_through``.  That mode fetches only
    unpublished days, refuses a store that already contains D0/future rows,
    and cannot silently revise a prior final.
    """
    store = RAW_DIR / "gdelt_volume.csv"
    today = date.today()
    end = end_date or today
    if end > today:
        raise RuntimeError(f"GDELT end date {end} is later than today {today}")
    if immutable_through is not None and immutable_through > end:
        raise RuntimeError("immutable publication boundary is later than fetch end")
    existing = None
    if store.exists():
        existing = pd.read_csv(store, parse_dates=["date"])
        existing["date"] = existing["date"].dt.date
        existing = existing.set_index("date").sort_index()
        if immutable_through is not None and any(day > end for day in existing.index):
            raise RuntimeError(
                "GDELT store contains D0/future rows beyond the finalized target"
            )

    if backfill_from is not None:
        fetched = fetch_all(dictionaries, backfill_from, end)
    else:
        start = end - timedelta(days=14)
        if immutable_through is not None:
            start = max(start, immutable_through + timedelta(days=1))
        fetched = (
            fetch_all(dictionaries, start, end)
            if start <= end
            else pd.DataFrame()
        )

    if immutable_through is not None and not fetched.empty:
        if any(day <= immutable_through or day > end for day in fetched.index):
            raise RuntimeError(
                "GDELT fetch crossed the immutable finalized-day boundary"
            )

    if existing is not None and backfill_from is None:
        merged = fetched.combine_first(existing)  # new tail wins on overlap? No:
        # combine_first keeps `fetched` where present, fills gaps from existing —
        # exactly what we want: fresh values overwrite the revised tail.
    else:
        merged = fetched

    merged = merged.sort_index()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_csv(store, index_label="date")
    return merged


def harvest_missing() -> None:
    """Opportunistic completion: try once, politely, to fetch any query's
    settled historical chunk that is not yet cached (currently gulf's
    "crude oil supply" sub-query). Run daily by CI with continue-on-error:
    each attempt costs a handful of requests, every success is cached
    permanently, and the loop ends itself when nothing is missing."""
    with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
        d = json.load(f)
    today = date.today()
    split = date(today.year, today.month, 1) - timedelta(days=1)
    if (today - split).days <= CACHE_SETTLE_DAYS:
        split = date(split.year, split.month, 1) - timedelta(days=1)
    start = date(2017, 1, 1)
    missing = 0
    for ch, spec in d.items():
        if ch.startswith("_"):
            continue
        for q in build_queries(spec["terms"], spec.get("anchor")):
            key_src = f"{q}|{start}|{split}"
            key = hashlib.sha1(key_src.encode()).hexdigest()[:16]
            if (CHUNK_CACHE_DIR / f"{key}.json").exists():
                continue
            missing += 1
            print(f"[harvest] attempting {ch}: {q[:60]}...")
            try:
                rows = _fetch_chunk(q, start, split)
                print(f"[harvest] LANDED {ch} ({len(rows)} days)")
            except Exception as e:
                print(f"[harvest] not today ({type(e).__name__}); will retry next run")
    if not missing:
        print("[harvest] nothing missing; historical cache is complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--harvest":
        harvest_missing()
    else:
        with open(ROOT / "dictionaries.json", encoding="utf-8") as f:
            d = json.load(f)
        df = load_or_update(d, backfill_from=date(2017, 1, 1))
        print(df.tail())
