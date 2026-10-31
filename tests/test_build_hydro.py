"""Tests for tools/build_hydro_geojson.py's pure helpers (no network)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "tools" / "build_hydro_geojson.py"
_spec = importlib.util.spec_from_file_location("build_hydro_geojson", _PATH)
hydro = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hydro)


def _line(*coords):
    return {"type": "LineString", "coordinates": [list(c) for c in coords]}


def test_name_overrides_restore_real_names():
    assert hydro.real_name("Gulf of America") == "Gulf of Mexico"
    assert hydro.real_name("Lake America") is None  # not a real water body: no label
    assert hydro.real_name("Lake Superior") == "Lake Superior"
    assert hydro.real_name("") is None and hydro.real_name(None) is None


def test_in_regions_keeps_us_features_and_drops_others():
    assert hydro.in_regions(_line((-113.9, 46.9), (-113.8, 47.0)))  # Montana
    assert hydro.in_regions(_line((-157.9, 21.3), (-157.8, 21.4)))  # Oahu
    assert hydro.in_regions(_line((144.7, 13.4), (144.8, 13.5)))  # Guam
    assert not hydro.in_regions(_line((2.3, 48.8), (2.4, 48.9)))  # Paris
    assert not hydro.in_regions(_line((-58.4, -34.6), (-58.3, -34.5)))  # Buenos Aires


def test_round_geometry_drops_repeated_vertices():
    g = hydro.round_geometry(_line((-113.90001, 46.9), (-113.90002, 46.90001), (-113.8, 47.0)), 3)
    assert g["coordinates"] == [[-113.9, 46.9], [-113.8, 47.0]]


def test_round_geometry_keeps_closed_rings_valid():
    ring = [[0, 0], [0.00001, 0], [1, 0], [1, 1], [0, 0]]
    g = hydro.round_geometry({"type": "Polygon", "coordinates": [ring]}, 3)
    out = g["coordinates"][0]
    assert out[0] == out[-1] and len(out) >= 4


def test_label_point_is_inside_the_bbox_of_the_largest_part():
    square = [[[-98, 18], [-82, 18], [-82, 30], [-98, 30], [-98, 18]]]
    tiny = [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0]]]
    x, y = hydro.label_point({"type": "MultiPolygon", "coordinates": [tiny, square]})
    assert -98 < x < -82 and 18 < y < 30


def test_empty_geometry_is_not_in_any_region():
    assert not hydro.in_regions({"type": "MultiLineString", "coordinates": []})
    assert not hydro.in_regions({"type": "MultiLineString", "coordinates": [[]]})


def test_simplify_drops_collinear_vertices_and_keeps_ends():
    line = [[0, 0], [1, 0.0001], [2, 0], [3, 1]]
    out = hydro.simplify(line, 0.01)
    assert out[0] == [0, 0] and out[-1] == [3, 1]
    assert [1, 0.0001] not in out


def test_simplify_keeps_a_closed_ring_closed_and_valid():
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    out = hydro.simplify(ring, 0.01)
    assert out[0] == out[-1] and len(out) >= 4


def test_features_split_into_a_base_and_a_detail_tier():
    base, detail = hydro.split_tiers(
        [
            {"properties": {"minz": 2.0, "kind": "river"}},
            {"properties": {"minz": 5.9, "kind": "lake"}},
            {"properties": {"minz": 6.0, "kind": "river"}},
        ]
    )
    assert [f["properties"]["minz"] for f in base] == [2.0, 5.9]
    assert [f["properties"]["minz"] for f in detail] == [6.0]
