"""The labeling tool writes the pipeline's exact format, binds loopback
only, and never invents a ruling."""
from __future__ import annotations

import csv
import importlib.util
import inspect
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from src import precision_auditor

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "label_session.py"

_spec = importlib.util.spec_from_file_location("label_session", SCRIPT)
assert _spec is not None and _spec.loader is not None
ls = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ls)


def _queue(tmp_path: Path, n: int = 3) -> Path:
    p = tmp_path / "audit_queue.csv"
    rows = [{"date": "2026-08-01", "channel": "shipping",
             "url": f"https://example.test/{i}",
             "title": f"Suez Canal reroute {i}", "domain": "example.test",
             "machine_label": "ON", "rubric_version": "1.0.0",
             "human_label": ""} for i in range(n)]
    ls.atomic_write_store(p, list(precision_auditor.FIELDS), rows)
    return p


def test_round_trip_a_decision_through_the_pipelines_reader(tmp_path, monkeypatch):
    """A synthetic ruling written by this tool must be counted by
    src/precision_auditor.publish() -- same file, same schema, no
    intermediate format."""
    queue = _queue(tmp_path)
    out = tmp_path / "precision.json"
    monkeypatch.setattr(precision_auditor, "QUEUE", queue)
    monkeypatch.setattr(precision_auditor, "AUTHOR", tmp_path / "none.csv")
    monkeypatch.setattr(precision_auditor, "OUT", out)

    ls.apply_label(queue, "2026-08-01", "https://example.test/0", "ON")
    ls.apply_label(queue, "2026-08-01", "https://example.test/1", "ABSTAIN")
    precision_auditor.publish()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["author_labels_n"] == 1
    assert payload["author_abstained_n"] == 1

    with queue.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(precision_auditor.FIELDS)
        rows = list(reader)
    assert rows[0]["human_label"] == "ON"
    assert rows[1]["human_label"] == "ABSTAIN"
    assert rows[2]["human_label"] == ""


def test_the_tool_targets_the_registered_store_and_schema():
    """The script labels the exact path the auditor reads, and the real
    committed queue still carries the schema both sides assume."""
    assert ls.QUEUE == precision_auditor.QUEUE
    assert ls.CALIBRATION_N == precision_auditor.CALIBRATION_N
    with precision_auditor.QUEUE.open(encoding="utf-8") as f:
        assert csv.DictReader(f).fieldnames == list(precision_auditor.FIELDS)


def test_server_binds_loopback_only():
    """Structural: the one server construction binds 127.0.0.1 explicitly,
    and no wildcard bind appears anywhere in the file."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'ThreadingHTTPServer(("127.0.0.1", port)' in text
    assert "0.0.0.0" not in text


def test_no_label_is_written_without_an_explicit_decision(tmp_path):
    queue = _queue(tmp_path)
    before = queue.read_bytes()

    for bad in ("", "   ", None, 1, "MAYBE", "ONN", ["ON"]):
        try:
            ls.apply_label(queue, "2026-08-01", "https://example.test/0", bad)
            raise AssertionError(f"{bad!r} was accepted as a decision")
        except ValueError:
            pass
        assert queue.read_bytes() == before, f"{bad!r} mutated the store"

    # The decision parameter cannot default to anything.
    assert inspect.signature(ls.apply_label).parameters["label"].default \
        is inspect.Parameter.empty

    # Reading state (the GET path) never writes.
    ls.build_state(queue, 0, {}, {}, {"title": "", "preamble": "", "sections": []}, False)
    assert queue.read_bytes() == before


def test_refuses_to_overwrite_or_invent_rows(tmp_path):
    queue = _queue(tmp_path)
    ls.apply_label(queue, "2026-08-01", "https://example.test/0", "off")
    after_first = queue.read_bytes()
    try:
        ls.apply_label(queue, "2026-08-01", "https://example.test/0", "ON")
        raise AssertionError("second ruling on the same row was accepted")
    except ls.AlreadyLabeledError:
        pass
    try:
        ls.apply_label(queue, "2026-08-01", "https://nowhere.test/x", "ON")
        raise AssertionError("a ruling landed on a row that does not exist")
    except ls.UnknownRowError:
        pass
    assert queue.read_bytes() == after_first
    rows = list(csv.DictReader(after_first.decode("utf-8").splitlines()))
    assert rows[0]["human_label"] == "OFF"  # normalized, still explicit


def test_state_keeps_the_founder_blind_to_the_machine_label(tmp_path):
    """The queue carries machine labels; the page must never see them,
    or the agreement statistic stops meaning anything."""
    queue = _queue(tmp_path)
    state = ls.build_state(queue, 0, {}, {},
                           {"title": "", "preamble": "", "sections": []}, False)
    assert "machine_label" not in json.dumps(state)
    assert set(state["row"]) == {"date", "channel", "url", "title", "domain",
                                 "rubric_version", "channel_label"}


def test_matched_terms_and_rubric_are_faithful():
    spans = ls.matched_spans("Suez Canal blocked; suez canal again",
                            ["Suez Canal", "Canal"])
    assert [(s, e) for s, e, _ in spans] == [(0, 10), (20, 30)]
    assert all(t == "Suez Canal" for _, _, t in spans)  # longest term wins

    rubric_text = (ROOT / "auditor" / "RUBRIC.md").read_text(encoding="utf-8")
    rubric = ls.parse_rubric(rubric_text)
    assert {s["channel"] for s in rubric["sections"]} == {
        "pakistan_west", "china_east", "gulf_energy", "us_trade", "shipping"}
    for section in rubric["sections"]:
        assert section["text"] in rubric_text  # verbatim, never rewritten
    assert "ABSTAIN" in rubric["preamble"]


def test_http_session_end_to_end_on_loopback(tmp_path):
    """Serve a temp store on an ephemeral loopback port, label one row
    through the real POST path, and watch progress move."""
    queue = _queue(tmp_path)
    server = ls.make_server(queue, 0, False)
    try:
        assert server.server_address[0] == "127.0.0.1"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def get(path: str) -> dict:
            with urllib.request.urlopen(base + path, timeout=5) as r:
                return json.loads(r.read().decode("utf-8"))

        def post(payload: dict) -> tuple[int, dict]:
            req = urllib.request.Request(
                base + "/api/label", method="POST",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                return e.code, json.loads(e.read().decode("utf-8"))

        state = get("/api/state?pos=0")
        assert state["progress"]["firm"] == 0 and state["pending"] == 3
        row = state["row"]

        code, body = post({"date": row["date"], "url": row["url"], "label": "ON"})
        assert code == 200 and body["progress"]["firm"] == 1
        code, _ = post({"date": row["date"], "url": row["url"], "label": "OFF"})
        assert code == 409  # one ruling per row, ever
        code, _ = post({"date": "2026-08-01", "url": "https://example.test/2",
                        "label": "PROBABLY"})
        assert code == 400  # not a rubric answer

        after = get("/api/state?pos=0")
        assert after["pending"] == 2
        assert after["row"]["url"] != row["url"]
    finally:
        server.shutdown()
        server.server_close()

    rows = list(csv.DictReader(queue.open(encoding="utf-8")))
    assert [r["human_label"] for r in rows] == ["ON", "", ""]
