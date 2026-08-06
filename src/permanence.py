"""
Permanence lane (M2, founder-approved 2026-08-05: "execute everything").
Citability must survive this project's own infrastructure, so after the
site deploys, the day's pages are snapshotted into the Internet Archive
and the repository is registered with Software Heritage's save-code-now
service. Both free, both unauthenticated, both fail-soft: an archive
outage never touches the pipeline, and the result of every attempt is
published in docs/data/permanence.json so the record of the record is
itself checkable.

  python -m src.permanence            snapshot + register, write payload
  python -m src.permanence --dry-run  print what would be requested
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
SITE_DATA = ROOT / "docs" / "data"

# A deliberate handful, not the whole site: the pages a citation is
# most likely to point at. The Wayback crawler follows same-origin
# assets on its own.
SNAPSHOT_URLS = [
    "https://igrm.in/",
    "https://igrm.in/methodology.html",
    "https://igrm.in/data.html",
    "https://igrm.in/status.html",
]
SWH_ORIGIN = ("https://github.com/PlausibleDissent9/"
              "india-geopolitical-risk-monitor")
SWH_API = ("https://archive.softwareheritage.org/api/1/origin/save/git/"
           f"url/{SWH_ORIGIN}/")
UA = {"User-Agent": "igrm.in permanence lane (contact: via GitHub repo)"}


def snapshot(url: str) -> dict[str, Any]:
    """One Save Page Now request. 200 means accepted (the capture may
    still process asynchronously on their side); anything else is
    recorded as-is."""
    try:
        r = requests.get(f"https://web.archive.org/save/{url}",
                         headers=UA, timeout=90, allow_redirects=True)
        return {"url": url, "status": r.status_code, "ok": r.ok}
    except requests.RequestException as e:
        return {"url": url, "status": None, "ok": False,
                "error": type(e).__name__}


def register_swh() -> dict[str, Any]:
    try:
        r = requests.post(SWH_API, headers=UA, timeout=60)
        body: dict[str, Any] = {}
        try:
            body = r.json()
        except ValueError:
            pass
        return {"origin": SWH_ORIGIN, "status": r.status_code, "ok": r.ok,
                "save_request_status": body.get("save_request_status")}
    except requests.RequestException as e:
        return {"origin": SWH_ORIGIN, "status": None, "ok": False,
                "error": type(e).__name__}


def main() -> None:
    if "--dry-run" in sys.argv[1:]:
        for u in SNAPSHOT_URLS:
            print(f"[permanence] would snapshot {u}")
        print(f"[permanence] would register {SWH_ORIGIN}")
        return
    results = []
    for u in SNAPSHOT_URLS:
        results.append(snapshot(u))
        print(f"[permanence] wayback {u}: {results[-1].get('status')}")
        time.sleep(10)  # politeness between SPN requests
    swh = register_swh()
    print(f"[permanence] software heritage: {swh.get('status')} "
          f"{swh.get('save_request_status')}")
    payload = {
        "_meta": {
            "what": ("The permanence lane's own record: the result of "
                     "the latest Internet Archive snapshot request per "
                     "page and the latest Software Heritage save-code-now "
                     "registration. Fail-soft — an archive outage is "
                     "recorded here, never hidden, and never blocks the "
                     "pipeline. Wayback captures are browsable at "
                     "web.archive.org/web/*/igrm.in."),
            "generated": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        },
        "wayback": results,
        "software_heritage": swh,
    }
    (SITE_DATA / "permanence.json").write_text(json.dumps(payload),
                                               encoding="utf-8")
    ok = sum(1 for x in results if x["ok"])
    print(f"[permanence] wrote permanence.json: {ok}/{len(results)} "
          f"snapshots accepted")


if __name__ == "__main__":
    main()
