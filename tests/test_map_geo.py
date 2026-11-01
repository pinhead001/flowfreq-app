"""Tests for ``map_geo``: point-in-state over the bundled boundaries, and the helpers that
prepare a basin polygon for the map."""

from __future__ import annotations

import copy

import pytest

import map_geo


@pytest.mark.parametrize(
    "lat, lon, code",
    [
        (46.87, -113.99, "MT"),  # Missoula
        (61.22, -149.90, "AK"),  # Anchorage
        (52.90, 173.20, "AK"),  # Attu, west of the antimeridian
        (21.31, -157.86, "HI"),  # Honolulu
        (18.40, -66.10, "PR"),  # San Juan, inland
        (13.47, 144.75, "GU"),
        (-14.30, -170.70, "AS"),  # Tutuila
        (18.34, -64.93, "VI"),  # St Thomas
        (15.19, 145.75, "MP"),  # Saipan
    ],
)
def test_state_at(lat, lon, code):
    assert map_geo.state_at(lat, lon) == code


def test_state_at_ocean_is_none():
    assert map_geo.state_at(27.0, -89.0) is None  # Gulf of Mexico


def test_state_at_mt_wy_line_returns_one_code():
    # 45 N is the Montana-Wyoming line; either answer is fine, but exactly one.
    assert map_geo.state_at(45.0, -108.0) in {"MT", "WY"}


def _square(lon0: float, lat0: float, lon1: float, lat1: float) -> dict:
    ring = [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]}}


def test_states_touching_two_state_polygon():
    assert map_geo.states_touching(_square(-108.1, 44.9, -107.9, 45.1)) == ["MT", "WY"]


def test_states_touching_one_state_polygon():
    assert map_geo.states_touching(_square(-114.1, 46.8, -113.9, 46.9)) == ["MT"]


def test_states_touching_finds_a_state_wholly_inside_the_basin():
    # A basin vertex is never inside Rhode Island, but Rhode Island's vertices are
    # inside the basin.
    assert "RI" in map_geo.states_touching(_square(-72.5, 40.8, -70.5, 42.5))


def test_round_coords_multipolygon_copies_at_6dp():
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[-113.123456789, 46.987654321], [-113.1, 46.9]]]],
        },
    }
    original = copy.deepcopy(feature)
    rounded = map_geo.round_coords(feature)
    assert rounded["geometry"]["coordinates"][0][0][0] == [-113.123457, 46.987654]
    assert feature == original


def test_geojson_hash_is_12_hex_and_stable():
    a = _square(-108.1, 44.9, -107.9, 45.1)
    h = map_geo.geojson_hash(a)
    assert len(h) == 12 and int(h, 16) >= 0
    assert map_geo.geojson_hash(copy.deepcopy(a)) == h
    moved = copy.deepcopy(a)
    moved["geometry"]["coordinates"][0][1][0] = -107.8
    assert map_geo.geojson_hash(moved) != h
