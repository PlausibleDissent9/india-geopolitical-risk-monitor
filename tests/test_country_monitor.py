"""Country monitor: the refuse-unsigned gate and the schema adapter."""
from __future__ import annotations

from src import country_monitor


def test_draft_status_is_refused():
    assert not country_monitor.registered(
        {"status": "DRAFT awaiting signature"})
    assert not country_monitor.registered({})


def test_frozen_on_or_registered_status_passes():
    assert country_monitor.registered({"frozen_on": "2026-08-07"})
    assert country_monitor.registered(
        {"status": "REGISTERED 2026-08-05 on founder delegation"})


def test_terms_dict_with_rationales_adapts_to_query_list():
    spec = {"channels": {"ch": {
        "label": "X",
        "terms": {'"alpha beta"': "why alpha", '"gamma"': "why gamma"},
    }}}
    d = country_monitor._fetch_dicts(spec)
    assert d["ch"]["terms"] == ['"alpha beta"', '"gamma"']
    assert d["ch"]["anchor"] is None


def test_china_is_registered_and_frozen():
    """Flipped deliberately on the founder's signature ('sign china',
    2026-08-06) -- exactly the ceremony the old refusal test demanded.
    The registration must carry its frozen_on date."""
    specs = country_monitor.discover()
    assert "china" in specs
    assert country_monitor.registered(specs["china"]["_meta"])
    assert specs["china"]["_meta"]["frozen_on"] == "2026-08-06"


def test_a_partial_backfill_persists_each_channel(tmp_path, monkeypatch):
    """The China defect: update() fetched every channel and wrote once
    at the end, so a 429 on any channel meant the store was never
    created -- and the store's absence is what selects BACKFILL_START,
    so the next run restarted the same doomed backfill. It ran nightly
    for days and produced nothing, green every time."""
    import pandas as pd
    from src import country_monitor as cm

    monkeypatch.setattr(cm, "_store_path",
                        lambda name: tmp_path / f"{name}.csv")
    spec = {"_meta": {"status": "signed"},
            "channels": {"a": {"label": "A", "terms": ["x"]},
                         "b": {"label": "B", "terms": ["y"]},
                         "c": {"label": "C", "terms": ["z"]}}}
    monkeypatch.setattr(cm, "_fetch_dicts", lambda s: s["channels"])

    idx = pd.date_range("2024-01-01", periods=30, freq="D")
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("HTTP 429 rate limit")
        return pd.Series(range(30), index=idx, dtype=float)

    monkeypatch.setattr(cm.fetch_gdelt, "fetch_channel", flaky)
    vol = cm.update("testland", spec)

    assert (tmp_path / "testland.csv").exists(), "partial run wrote nothing"
    assert sorted(vol.columns) == ["a", "c"], "the survivors were not kept"


def test_a_channel_still_missing_publishes_as_uncollected(tmp_path,
                                                          monkeypatch):
    """A partial monitor must be legible as partial: never crash, and
    never silently omit a channel so the payload looks complete."""
    import json

    import pandas as pd
    from src import country_monitor as cm

    monkeypatch.setattr(cm, "SITE_DATA", tmp_path)
    spec = {"_meta": {"status": "signed", "frozen_on": "2026-08-06"},
            "channels": {"a": {"label": "A"}, "b": {"label": "B"}}}
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    vol = pd.DataFrame({"a": range(5)}, index=idx, dtype=float)

    monkeypatch.setattr(cm.build_index, "build_scores",
                        lambda v: pd.DataFrame(
                            {"a": [50.0] * 5, "composite": [50.0] * 5},
                            index=idx))
    cm.publish("testland", spec, vol)

    payload = json.loads((tmp_path / "country_testland.json").read_text())
    assert payload["channels"]["a"]["collected"] is True
    assert payload["channels"]["b"]["collected"] is False
    assert payload["channels"]["b"]["score"] is None
    assert payload["n_channels_collected"] == 1
    assert payload["n_channels_registered"] == 2
