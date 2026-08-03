"""
Expert-attention layer (practitioner item 3): what the registered
think-tank roster is publishing, tagged to channels by the same frozen
dictionaries the press layer uses. Titles, links, and dates only,
never content. The roster lives in think_tanks.json; institutions
without a public feed are carried with that status, not dropped.

Store: data/raw/expert_attention.csv   append-only, deduped by URL
Site:  docs/data/expert_shelf.json     last 45 days, per channel + general

  python -m src.expert_attention
"""
from __future__ import annotations

import csv
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "think_tanks.json"
DICTS = ROOT / "dictionaries.json"
STORE = ROOT / "data" / "raw" / "expert_attention.csv"
OUT = ROOT / "docs" / "data" / "expert_shelf.json"

FIELDS = ["date", "institution", "channel", "title", "url"]
SHELF_DAYS = 45
HEADERS = {"User-Agent": "Mozilla/5.0 (research; IGRM expert-attention; titles only)"}


def _norm(text: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("-", " ")).split()


def _subseq(phrase: tuple[str, ...], tokens: list[str]) -> bool:
    m = len(phrase)
    return any(tuple(tokens[i:i + m]) == phrase for i in range(len(tokens) - m + 1))


def _channel_phrases() -> dict[str, list[tuple[str, ...]]]:
    with open(DICTS, encoding="utf-8") as f:
        d = json.load(f)
    out = {}
    for ch, spec in d.items():
        if ch.startswith("_"):
            continue
        out[ch] = [tuple(_norm(t.strip('"'))) for t in spec["terms"]]
    return out


def _parse_feed(blob: bytes) -> list[dict]:
    items = []
    root = ET.fromstring(blob)
    ns_atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):  # RSS
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        desc = it.findtext("description") or ""
        items.append({"title": title, "url": link, "pub": pub, "summary": desc})
    for it in root.iter(f"{ns_atom}entry"):  # Atom
        title = (it.findtext(f"{ns_atom}title") or "").strip()
        link_el = it.find(f"{ns_atom}link")
        link = link_el.get("href", "") if link_el is not None else ""
        pub = it.findtext(f"{ns_atom}updated") or ""
        desc = it.findtext(f"{ns_atom}summary") or ""
        items.append({"title": title, "url": link, "pub": pub, "summary": desc})
    return items


def _item_date(pub: str) -> str:
    for parser in (parsedate_to_datetime,
                   lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))):
        try:
            return parser(pub).date().isoformat()
        except Exception:  # noqa: BLE001 - feed date formats vary wildly
            continue
    return date.today().isoformat()


def main() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))["institutions"]
    phrases = _channel_phrases()

    existing: dict[str, dict] = {}
    if STORE.exists():
        with STORE.open(encoding="utf-8") as f:
            existing = {r["url"]: r for r in csv.DictReader(f)}

    added = 0
    for key, inst in registry.items():
        if not inst.get("feed"):
            continue
        try:
            req = urllib.request.Request(inst["feed"], headers=HEADERS)
            blob = urllib.request.urlopen(req, timeout=30).read()
            items = _parse_feed(blob)
        except Exception as e:  # noqa: BLE001 - one dead feed never kills the run
            print(f"[experts] {key}: feed error {type(e).__name__}; skipped")
            continue
        for it in items:
            if not it["url"] or it["url"] in existing:
                continue
            if not it["url"].startswith(("http://", "https://")):
                continue
            tokens = _norm(it["title"] + " " + it["summary"][:300])
            channel = "general"
            for ch, phs in phrases.items():
                if any(len(p) <= len(tokens) and _subseq(p, tokens) for p in phs):
                    channel = ch
                    break
            existing[it["url"]] = {
                "date": _item_date(it["pub"]), "institution": key,
                "channel": channel, "title": it["title"][:300], "url": it["url"],
            }
            added += 1

    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in sorted(existing.values(), key=lambda r: r["date"]):
            w.writerow(row)

    cutoff = (date.today() - timedelta(days=SHELF_DAYS)).isoformat()
    recent = [r for r in existing.values() if r["date"] >= cutoff]
    shelf: dict = {"_meta": {
        "what": ("Latest publications from the registered think-tank roster "
                 "(think_tanks.json), tagged to channels by the frozen "
                 "dictionaries. Titles and links only. Institutions without "
                 "public feeds are listed in the registry with that status."),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "window_days": SHELF_DAYS,
        "labels": {k: v["label"] for k, v in registry.items()},
    }, "channels": {}}
    for r in sorted(recent, key=lambda r: r["date"], reverse=True):
        shelf["channels"].setdefault(r["channel"], []).append(
            {"date": r["date"], "institution": r["institution"],
             "title": r["title"], "url": r["url"]})
    for ch in shelf["channels"]:
        shelf["channels"][ch] = shelf["channels"][ch][:15]
    OUT.write_text(json.dumps(shelf), encoding="utf-8")
    per = {ch: len(v) for ch, v in shelf["channels"].items()}
    print(f"[experts] +{added} new items; shelf window {SHELF_DAYS}d: {per}")


if __name__ == "__main__":
    main()
