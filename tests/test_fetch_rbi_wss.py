"""Parse contract for the RBI WSS reserves fetcher.

The fixture fragment mirrors the verified page structure (heading, As-on
line, eight numeric cells per row: Rs Cr / US$ Mn level + three variation
pairs). Values are the REAL published week of 2026-07-31, the one
cross-validated against the DBIE gateway to the million before the module
shipped -- the fixture is a miniature of a real page, not an invention.
"""
from __future__ import annotations

import pytest
from src.fetch_rbi_wss import WssParseError, parse_reserves

_PAGE = (
    "<h2>2. Foreign Exchange Reserves*</h2><td>As on Jul. 31, 2026</td>"
    "<tr><td>1 Total Reserves</td><td>6612148</td><td>692866</td>"
    "<td>24233</td><td>10512</td><td>58287</td><td>1758</td>"
    "<td>581731</td><td>3995</td></tr>"
    "<tr><td>1.1 Foreign Currency Assets #</td><td>5388865</td><td>564680</td>"
    "<td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td></tr>"
    "<tr><td>1.2 Gold</td><td>999586</td><td>104735</td>"
    "<td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td></tr>"
    "<tr><td>1.3 SDRs</td><td>178069</td><td>18657</td>"
    "<td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td></tr>"
    "<tr><td>1.4 Reserve Position in the IMF</td><td>45628</td><td>4794</td>"
    "<td>1</td><td>2</td><td>3</td><td>4</td><td>5</td><td>6</td></tr>"
)


def test_parses_the_verified_week() -> None:
    as_on, values = parse_reserves(_PAGE)
    assert as_on == "2026-07-31"
    assert values["1 Total Reserves"] == 692866  # == DBIE 6.92866E11, verified
    assert values["1.2 Gold"] == 104735
    assert len(values) == 5


def test_refuses_a_page_without_the_table() -> None:
    with pytest.raises(WssParseError):
        parse_reserves("<html>maintenance page</html>")


def test_refuses_a_table_missing_a_row() -> None:
    with pytest.raises(WssParseError):
        parse_reserves(_PAGE.replace("1.3 SDRs", "1.3 Something Else"))
