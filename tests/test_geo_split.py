"""V20: the grey-states fix places points by geometry, not by guess."""
from __future__ import annotations

from src import geo_split


def test_known_cities_place_correctly_including_the_grey_states():
    """Telangana, Ladakh and Goa are exactly the states GDELT's FIPS
    codes cannot express; the point test must place all three."""
    states = geo_split.load_states()
    assert len(states) >= 30
    for city, lat, lon, expected in geo_split.SELFTEST:
        assert geo_split.place(lat, lon, states) == expected, city


def test_offshore_point_is_unplaced_not_snapped():
    """A point in the Arabian Sea belongs to no state. Returning None
    keeps unplaced events honest; snapping to the nearest coast would
    make a guess indistinguishable from a measurement on the map."""
    states = geo_split.load_states()
    assert geo_split.place(15.0, 68.0, states) is None


def test_ring_arithmetic_on_a_unit_square():
    square = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
    assert geo_split.point_in_ring(0.5, 0.5, square)
    assert not geo_split.point_in_ring(1.5, 0.5, square)
    assert not geo_split.point_in_ring(0.5, 1.5, square)
