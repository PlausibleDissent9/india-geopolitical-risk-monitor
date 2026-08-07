"""Founder calibration labeling session -- the tool, never the labeler.

HOW TO RUN (Ishan)

    cd ~/india-geopolitical-risk-monitor
    .venv/bin/python scripts/label_session.py            # label the real queue
    .venv/bin/python scripts/label_session.py --dry-run  # practice on a copy
    .venv/bin/python scripts/label_session.py --port 9000

Open http://127.0.0.1:8765 in a browser. One unlabeled queue row at a
time, with the rubric (auditor/RUBRIC.md, rendered verbatim) beside it.

    y = ON    n = OFF    u = ABSTAIN    arrow keys = skip, no label

Each keypress writes ONE ruling to the human_label column of
data/raw/audit_queue.csv -- the exact store src/precision_auditor.py
reads -- via an atomic whole-file replace, so the session is resumable
at any point (close the tab, Ctrl-C the server, run it again later).
The machine_label column is never shown: rulings stay blind. The tool
never fills a label itself, refuses to overwrite an existing ruling,
and has no bulk path -- one decision, one keypress, by design. A slip
is fixed by editing that row's human_label in the CSV by hand.

Serves on 127.0.0.1 only; nothing is uploaded anywhere; the page loads
no external asset (inline CSS/JS only).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.precision_auditor import CALIBRATION_N, QUEUE  # noqa: E402

RUBRIC_PATH = ROOT / "auditor" / "RUBRIC.md"
DICT_PATH = ROOT / "dictionaries.json"
ALLOWED = ("ON", "OFF", "ABSTAIN")
DEFAULT_PORT = 8765

_WRITE_LOCK = threading.Lock()


class UnknownRowError(KeyError):
    """The (date, url) pair does not identify a queue row."""


class AlreadyLabeledError(ValueError):
    """The row already carries a founder ruling; the tool refuses to overwrite."""


def read_store(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if "human_label" not in fieldnames:
        raise ValueError(f"{path} has no human_label column; refusing to serve it")
    return fieldnames, rows


def atomic_write_store(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    """Whole-file rewrite via a same-directory temp file and os.replace."""
    if "human_label" not in fieldnames:
        raise ValueError("refusing to write a store without a human_label column")
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply_label(path: Path, row_date: str, url: str, label: object) -> str:
    """Record ONE explicit founder decision. The label argument has no
    default anywhere in this file: no decision input, no write."""
    if not isinstance(label, str) or not label.strip():
        raise ValueError("no decision given; nothing written")
    norm = label.strip().upper()
    if norm not in ALLOWED:
        raise ValueError(f"label must be one of {ALLOWED}, got {label!r}")
    fieldnames, rows = read_store(path)
    for row in rows:
        if row.get("date") == row_date and row.get("url") == url:
            if (row.get("human_label") or "").strip():
                raise AlreadyLabeledError(
                    f"row already labeled {row['human_label']!r}; "
                    "fix by hand in the CSV if that ruling is wrong")
            row["human_label"] = norm
            atomic_write_store(path, fieldnames, rows)
            return norm
    raise UnknownRowError(f"no queue row with date={row_date!r} url={url!r}")


def progress(rows: list[dict]) -> dict:
    labels = [(r.get("human_label") or "").strip().upper() for r in rows]
    firm = sum(1 for v in labels if v in ("ON", "OFF"))
    abstain = sum(1 for v in labels if v == "ABSTAIN")
    return {"firm": firm, "abstain": abstain,
            "pending": sum(1 for v in labels if not v),
            "total_rows": len(rows), "threshold": CALIBRATION_N}


def pending_indices(rows: list[dict]) -> list[int]:
    return [i for i, r in enumerate(rows)
            if not (r.get("human_label") or "").strip()]


def load_channel_meta(path: Path) -> tuple[dict, dict]:
    """(terms, display labels) per channel from the frozen dictionaries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    terms: dict = {}
    labels: dict = {}
    for ch, entry in data.items():
        if ch.startswith("_") or not isinstance(entry, dict):
            continue
        terms[ch] = [t.strip().strip('"').strip() for t in entry.get("terms", [])
                     if t and t.strip().strip('"').strip()]
        labels[ch] = entry.get("label", ch)
    return terms, labels


def matched_spans(title: str, terms: list[str]) -> list[list]:
    """Non-overlapping case-insensitive occurrences of dictionary terms in
    the headline, longest term first. Display aid only: the pipeline's own
    matching is its own registered procedure."""
    spans: list[tuple[int, int, str]] = []
    low = title.lower()
    for term in sorted(set(terms), key=len, reverse=True):
        needle = term.lower()
        start = 0
        while True:
            i = low.find(needle, start)
            if i < 0:
                break
            j = i + len(needle)
            if all(j <= s or i >= e for s, e, _ in spans):
                spans.append((i, j, term))
            start = i + 1
    spans.sort()
    return [[s, e, t] for s, e, t in spans]


def parse_rubric(text: str) -> dict:
    """Split RUBRIC.md into title, preamble, and per-channel sections.
    The text is passed through verbatim; this never rewrites the instrument."""
    lines = text.splitlines()
    title = ""
    body = lines
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()
        body = lines[1:]
    preamble: list[str] = []
    sections: list[dict] = []
    current: dict | None = None
    for line in body:
        if line.startswith("## "):
            current = {"channel": line[3:].strip(), "text": []}
            sections.append(current)
        elif current is None:
            preamble.append(line)
        else:
            current["text"].append(line)
    for s in sections:
        s["text"] = "\n".join(s["text"]).strip()
    return {"title": title, "preamble": "\n".join(preamble).strip(),
            "sections": sections}


def build_state(store: Path, pos: int, terms: dict, labels: dict,
                rubric: dict, dry_run: bool) -> dict:
    """Assemble the JSON the page renders. Reads only; never writes.
    The row dict is built field by field: machine_label stays server-side
    so the founder's ruling is blind to the machine's."""
    _, rows = read_store(store)
    pend = pending_indices(rows)
    prog = progress(rows)
    row = None
    spans: list[list] = []
    if pend:
        pos = max(0, min(pos, len(pend) - 1))
        r = rows[pend[pos]]
        row = {"date": r.get("date", ""), "channel": r.get("channel", ""),
               "url": r.get("url", ""), "title": r.get("title", ""),
               "domain": r.get("domain", ""),
               "rubric_version": r.get("rubric_version", ""),
               "channel_label": labels.get(r.get("channel", ""), r.get("channel", ""))}
        spans = matched_spans(row["title"], terms.get(row["channel"], []))
    else:
        pos = 0
    return {"row": row, "spans": spans, "pos": pos, "pending": len(pend),
            "progress": prog, "rubric": rubric, "dry_run": dry_run,
            "store": str(store)}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IGRM calibration labels</title>
<style>
:root { --bg:#f6f7f9; --card:#ffffff; --ink:#1a1f27; --dim:#5b6572;
        --line:#dde2e8; --mark:#ffe58a; --accent:#2456a6; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#14181e; --card:#1d232b; --ink:#e8ecf1; --dim:#98a2ad;
          --line:#303842; --mark:#7a6414; --accent:#7aa5e0; } }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
       font:16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
header { display:flex; align-items:center; gap:1rem; flex-wrap:wrap;
         padding:.7rem 1.2rem; border-bottom:1px solid var(--line);
         background:var(--card); position:sticky; top:0; }
header h1 { font-size:1rem; margin:0; }
#dry { display:none; background:#b45309; color:#fff; padding:.1rem .55rem;
       border-radius:4px; font-size:.8rem; }
#prog { font-variant-numeric:tabular-nums; color:var(--dim); font-size:.9rem; }
#bar { height:6px; width:180px; background:var(--line); border-radius:3px; }
#bar div { height:100%; width:0; background:var(--accent); border-radius:3px; }
main { display:grid; grid-template-columns:minmax(0,1fr) 400px; gap:1.2rem;
       padding:1.2rem; max-width:1200px; margin:0 auto; }
@media (max-width:900px) { main { grid-template-columns:1fr; } }
.card { background:var(--card); border:1px solid var(--line);
        border-radius:8px; padding:1.1rem 1.3rem; }
.meta { color:var(--dim); font-size:.85rem; display:flex; gap:.8rem;
        flex-wrap:wrap; align-items:center; }
.pill { border:1px solid var(--accent); color:var(--accent);
        border-radius:999px; padding:.05rem .6rem; font-size:.8rem; }
#title { font-size:1.35rem; line-height:1.35; margin:.6rem 0; overflow-wrap:anywhere; }
mark { background:var(--mark); color:inherit; padding:0 .1em; border-radius:2px; }
#url a { color:var(--accent); font-size:.85rem; overflow-wrap:anywhere; }
#terms { font-size:.85rem; color:var(--dim); margin-top:.5rem; }
#rubric h2 { font-size:.95rem; margin:0 0 .5rem; }
#rubric pre { white-space:pre-wrap; font:inherit; font-size:.85rem; margin:.3rem 0; }
#rubric .pre { color:var(--dim); }
#rubric .now { border-left:3px solid var(--accent); padding-left:.7rem; }
#rubric details { margin:.3rem 0; }
#rubric summary { cursor:pointer; font-size:.85rem; color:var(--dim); }
#actions { position:sticky; bottom:0; background:var(--card);
           border-top:1px solid var(--line); padding:.7rem 1.2rem;
           display:flex; gap:.7rem; align-items:center; flex-wrap:wrap; }
button { font:inherit; border:1px solid var(--line); border-radius:6px;
         padding:.45rem 1rem; cursor:pointer; background:var(--bg); color:var(--ink); }
#b-on { border-color:#15803d; } #b-off { border-color:#b91c1c; }
kbd { border:1px solid var(--line); border-bottom-width:2px; border-radius:4px;
      padding:0 .35em; font-size:.8em; background:var(--bg); }
#flash { color:#b91c1c; font-size:.85rem; min-height:1.2em; }
#done { display:none; text-align:center; padding:3rem 1rem; }
.hint { color:var(--dim); font-size:.8rem; }
</style>
</head>
<body>
<header>
  <h1>IGRM calibration labels</h1>
  <span id="dry">DRY RUN &mdash; writing to a copy</span>
  <div id="bar"><div></div></div>
  <span id="prog"></span>
</header>
<main>
  <section class="card" id="article">
    <div class="meta">
      <span class="pill" id="channel"></span>
      <span id="date"></span><span id="domain"></span><span id="posinfo"></span>
    </div>
    <div id="title"></div>
    <div id="url"></div>
    <div id="terms"></div>
  </section>
  <aside class="card" id="rubric"></aside>
</main>
<div id="done" class="card"><h2>No unlabeled rows left.</h2>
  <p id="donedetail"></p></div>
<div id="actions">
  <button id="b-on">ON <kbd>y</kbd></button>
  <button id="b-off">OFF <kbd>n</kbd></button>
  <button id="b-abstain">ABSTAIN <kbd>u</kbd></button>
  <button id="b-prev" title="previous, no label">&#8592;</button>
  <button id="b-next" title="next, no label">&#8594;</button>
  <span class="hint">one keypress = one ruling, written immediately; arrows skip without labeling</span>
  <span id="flash"></span>
</div>
<script>
"use strict";
let pos = 0, state = null, busy = false;
const $ = id => document.getElementById(id);
const esc = s => s.replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function markup(title, spans) {
  let out = "", last = 0;
  for (const [s, e] of spans) {
    out += esc(title.slice(last, s)) + "<mark>" + esc(title.slice(s, e)) + "</mark>";
    last = e;
  }
  return out + esc(title.slice(last));
}

async function load() {
  const r = await fetch("/api/state?pos=" + pos, {cache: "no-store"});
  if (!r.ok) { $("flash").textContent = "state fetch failed: HTTP " + r.status; return; }
  state = await r.json();
  pos = state.pos;
  render();
}

function render() {
  const p = state.progress;
  $("prog").textContent = p.firm + " / " + p.threshold + " firm rulings · "
    + p.abstain + " abstained · " + p.pending + " pending";
  $("bar").firstElementChild.style.width =
    Math.min(100, 100 * p.firm / p.threshold) + "%";
  document.title = p.firm + "/" + p.threshold + " · IGRM labels";
  $("dry").style.display = state.dry_run ? "inline-block" : "none";
  const row = state.row;
  if (!row) {
    $("article").style.display = "none";
    $("rubric").style.display = "none";
    $("done").style.display = "block";
    $("donedetail").textContent = p.firm + " firm rulings and " + p.abstain
      + " abstentions are in " + state.store + ".";
    return;
  }
  $("article").style.display = "";
  $("rubric").style.display = "";
  $("done").style.display = "none";
  $("channel").textContent = row.channel_label + " (" + row.channel + ")";
  $("date").textContent = row.date;
  $("domain").textContent = row.domain;
  $("posinfo").textContent = "row " + (pos + 1) + " of " + state.pending + " pending";
  $("title").innerHTML = markup(row.title, state.spans);
  $("url").innerHTML = '<a href="' + esc(row.url)
    + '" target="_blank" rel="noopener noreferrer">' + esc(row.url) + "</a>";
  $("terms").textContent = state.spans.length
    ? "Dictionary terms in headline: " + state.spans.map(s => "“" + s[2] + "”").join(", ")
    : "No dictionary term appears in the headline; the match may sit in the article body.";
  const rb = state.rubric;
  let html = "<h2>" + esc(rb.title) + "</h2>"
    + '<pre class="pre">' + esc(rb.preamble) + "</pre>";
  for (const s of rb.sections) {
    if (s.channel === row.channel) {
      html += '<div class="now"><strong>' + esc(s.channel) + "</strong><pre>"
        + esc(s.text) + "</pre></div>";
    } else {
      html += "<details><summary>" + esc(s.channel) + "</summary><pre>"
        + esc(s.text) + "</pre></details>";
    }
  }
  $("rubric").innerHTML = html;
  $("flash").textContent = "";
}

async function decide(label) {
  if (busy || !state || !state.row) return;
  busy = true;
  try {
    const r = await fetch("/api/label", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({date: state.row.date, url: state.row.url, label: label})
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      $("flash").textContent = e.error || ("write failed: HTTP " + r.status);
    }
  } catch (err) {
    $("flash").textContent = "write failed: " + err;
  } finally {
    busy = false;
  }
  await load();
}

function skip(delta) { pos = Math.max(0, pos + delta); load(); }

document.addEventListener("keydown", ev => {
  if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
  if (ev.key === "y") decide("ON");
  else if (ev.key === "n") decide("OFF");
  else if (ev.key === "u") decide("ABSTAIN");
  else if (ev.key === "ArrowRight" || ev.key === "ArrowDown") { ev.preventDefault(); skip(1); }
  else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") { ev.preventDefault(); skip(-1); }
});
$("b-on").onclick = () => decide("ON");
$("b-off").onclick = () => decide("OFF");
$("b-abstain").onclick = () => decide("ABSTAIN");
$("b-prev").onclick = () => skip(-1);
$("b-next").onclick = () => skip(1);
load();
</script>
</body>
</html>
"""


def make_handler(store: Path, terms: dict, labels: dict, rubric: dict,
                 dry_run: bool) -> type:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; "
                "script-src 'unsafe-inline'; connect-src 'self'; "
                "base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, "application/json; charset=utf-8",
                       json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
            elif parsed.path == "/api/state":
                q = parse_qs(parsed.query)
                try:
                    pos = int(q.get("pos", ["0"])[0])
                except ValueError:
                    pos = 0
                self._json(200, build_state(store, pos, terms, labels,
                                            rubric, dry_run))
            elif parsed.path == "/favicon.ico":
                self._send(204, "image/x-icon", b"")
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if urlparse(self.path).path != "/api/label":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                row_date, url = body["date"], body["url"]
                label = body["label"]
            except (ValueError, KeyError, TypeError):
                self._json(400, {"error": "body must be JSON with date, url, label"})
                return
            try:
                with _WRITE_LOCK:
                    norm = apply_label(store, row_date, url, label)
            except AlreadyLabeledError as e:
                self._json(409, {"error": str(e)})
                return
            except UnknownRowError as e:
                self._json(404, {"error": str(e)})
                return
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            _, rows = read_store(store)
            prog = progress(rows)
            print(f"[label-session] {norm:<7} {url}  "
                  f"(firm {prog['firm']}/{prog['threshold']}, "
                  f"abstained {prog['abstain']})")
            self._json(200, {"ok": True, "label": norm, "progress": prog})

        def log_message(self, fmt: str, *args: object) -> None:
            pass  # decisions are logged above; request noise is not

    return Handler


def make_server(store: Path, port: int, dry_run: bool) -> ThreadingHTTPServer:
    terms, labels = load_channel_meta(DICT_PATH)
    rubric = parse_rubric(RUBRIC_PATH.read_text(encoding="utf-8"))
    handler = make_handler(store, terms, labels, rubric, dry_run)
    # Loopback only: nothing on the network can reach this, and it can
    # reach nothing -- the session never leaves the machine.
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Serve the founder labeling UI against the audit queue.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--dry-run", action="store_true",
                    help="serve against a copy of the queue; the real store is untouched")
    args = ap.parse_args(argv)

    for required in (QUEUE, RUBRIC_PATH, DICT_PATH):
        if not required.exists():
            print(f"[label-session] missing {required}; run from a full checkout")
            return 1

    store = QUEUE
    if args.dry_run:
        copy_dir = Path(tempfile.mkdtemp(prefix="igrm-label-dryrun-"))
        store = copy_dir / QUEUE.name
        shutil.copy2(QUEUE, store)
        print(f"[label-session] DRY RUN: labeling a copy at {store}")
        print(f"[label-session] the real store {QUEUE} is untouched")
    else:
        print(f"[label-session] store: {QUEUE}")

    _, rows = read_store(store)
    prog = progress(rows)
    print(f"[label-session] firm {prog['firm']}/{prog['threshold']}, "
          f"abstained {prog['abstain']}, pending {prog['pending']}")
    try:
        server = make_server(store, args.port, args.dry_run)
    except OSError as e:
        print(f"[label-session] cannot bind 127.0.0.1:{args.port} ({e}); "
              "try --port with a free port")
        return 1
    print(f"[label-session] open http://127.0.0.1:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[label-session] stopped; the store keeps every ruling written so far")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
