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
