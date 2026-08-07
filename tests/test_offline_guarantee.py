"""Cached reproduce mode claims to be strictly offline. Hold it to that.

scripts/reproduce.sh --use-cache says: "ALL acquisition is refused --
network and the settled-chunk cache alike -- so the committed store is
the only data source and the rebuild is a pure recompute of the
committed vintage."

That claim is only as strong as the modules the script actually runs. An
audit on 2026-08-07 found that of twelve modules making network calls,
exactly ONE (fetch_gdelt) checks IGRM_OFFLINE. The guarantee holds today
because reproduce.sh runs only run_daily plus four pure-computation
lanes -- but nothing stopped the next person adding a fetching module to
that script and quietly turning a reproduction into a re-fetch.

So the invariant is pinned here rather than left to memory: every module
reproduce.sh invokes must either honour IGRM_OFFLINE or make no network
calls at all.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from src import fetch_markets

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
REPRODUCE = ROOT / "scripts" / "reproduce.sh"

NETWORK = re.compile(r"\brequests\.\w+\(|urllib\.request|urlopen\(")


def _modules_reproduce_runs() -> set[str]:
    text = REPRODUCE.read_text(encoding="utf-8")
    return set(re.findall(r"python -m src\.(\w+)", text))


def _reachable(module: str, seen: set[str] | None = None) -> set[str]:
    """module plus the src modules it imports, transitively."""
    seen = seen if seen is not None else set()
    if module in seen:
        return seen
    path = SRC / f"{module}.py"
    if not path.exists():
        return seen
    seen.add(module)
    text = path.read_text(encoding="utf-8")
    for m in re.findall(r"from \.\s*import ([\w, ]+)", text):
        for name in m.split(","):
            _reachable(name.strip(), seen)
    for m in re.findall(r"from src import ([\w, ]+)", text):
        for name in m.split(","):
            _reachable(name.strip(), seen)
    for m in re.findall(r"from \.(\w+) import", text):
        _reachable(m, seen)
    return seen


def test_the_module_set_is_not_empty():
    """The extraction keys on `python -m src.`; a launcher rename would
    empty the set and pass the offline guarantee on nothing."""
    assert len(_modules_reproduce_runs()) >= 10, (
        f"only {len(_modules_reproduce_runs())} modules extracted from "
        "reproduce.sh; ~15 existed when this was written")


def test_reproduce_only_runs_modules_that_can_be_forced_offline():
    offenders = []
    for entry in sorted(_modules_reproduce_runs()):
        for mod in sorted(_reachable(entry)):
            path = SRC / f"{mod}.py"
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            if NETWORK.search(text) and "IGRM_OFFLINE" not in text:
                offenders.append(f"{mod} (reached from {entry})")
    assert not offenders, (
        "reproduce.sh runs modules that can reach the network and do not "
        f"honour IGRM_OFFLINE: {sorted(set(offenders))}. Cached mode "
        "promises a pure recompute of the committed vintage; a module "
        "that refetches makes that claim false.")


def test_the_offline_flag_is_actually_checked_by_the_fetch_path():
    """fetch_gdelt is the acquisition path run_daily depends on. If its
    offline guard ever disappears, cached reproduce silently starts
    hitting the API again."""
    text = (SRC / "fetch_gdelt.py").read_text(encoding="utf-8")
    assert text.count("IGRM_OFFLINE") >= 2, (
        "fetch_gdelt must refuse BOTH the network and the settled-chunk "
        "cache under IGRM_OFFLINE; a cache hit that overwrites "
        "ngram-healed store days is how the 2026-08-06 reproduce "
        "divergence happened")


def test_reproduce_declares_its_coverage():
    """A reproduce run that compares a file no module rebuilt is
    comparing a committed copy to itself. The script must report how
    many payloads it actually regenerated."""
    text = REPRODUCE.read_text(encoding="utf-8")
    assert "COVERAGE" in text, (
        "reproduce.sh must report how many payloads it genuinely "
        "regenerated, not just that the diff passed")


def test_market_fetch_fails_closed_when_offline_cache_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IGRM_OFFLINE", "1")
    monkeypatch.setattr(fetch_markets, "RAW_DIR", tmp_path)

    def forbidden_download(*_args, **_kwargs):
        raise AssertionError("offline mode attempted a market download")

    monkeypatch.setattr(fetch_markets, "_download", forbidden_download)
    with pytest.raises(fetch_markets.OfflineMarketDataUnavailable):
        fetch_markets.load_or_update()
