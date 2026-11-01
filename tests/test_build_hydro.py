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


def test_lake_labels_carry_the_full_name():
    # Natural Earth's name_en drops "Lake": Flathead Lake and the Flathead River both read
    # "Flathead". The full name tells them apart.
    lake = {"name": "Flathead Lake", "name_en": "Flathead", "featurecla": "Lake"}
    assert hydro.water_name(lake, "lake") == "Flathead Lake"
    mead = {"name": "Lake Mead", "name_en": "Mead", "featurecla": "Reservoir"}
    assert hydro.water_name(mead, "lake") == "Lake Mead"
    assert hydro.water_name({"name": "Hebgen", "featurecla": "Reservoir"}, "lake") == "Hebgen Lake"
    assert hydro.water_name({"name": "Lac Bert", "featurecla": "Lake"}, "lake") == "Lac Bert"
    dam = {"name": "La Boquilla Dam", "featurecla": "Reservoir"}
    assert hydro.water_name(dam, "lake") == "La Boquilla Dam"


def test_river_labels_say_river():
    assert (
        hydro.water_name({"name": "Flathead", "featurecla": "River"}, "river") == "Flathead River"
    )
    supplement = {"name": "S.  Fk.  Flathead", "name_full": "South Fork Flathead River"}
    assert hydro.water_name(supplement, "river") == "South Fork Flathead River"
    assert hydro.water_name({"name": "S.  Fk.  Flathead"}, "river") == "S. Fk. Flathead River"
    # Only the last word, or a leading one, says what a feature is.
    fork = {"name": "Double Mountain Fork Brazos", "featurecla": "River"}
    assert hydro.water_name(fork, "river") == "Double Mountain Fork Brazos River"
    kept_names = ("Rio Grande", "Atchafalaya River", "Clear Creek", "Erie Canal",
                  "R. des Outaouais", "Arroyo Altar", "Allan Water")  # fmt: skip
    for kept in kept_names:
        assert hydro.water_name({"name": kept, "featurecla": "River"}, "river") == kept


def test_a_river_through_a_lake_is_not_labelled_on_the_lake():
    segment = {"name": "Flathead", "featurecla": "Lake Centerline"}
    assert hydro.water_name(segment, "river") is None


def test_water_names_still_pass_the_overrides():
    assert hydro.water_name({"name": "Lake America", "featurecla": "Lake"}, "lake") is None


def test_damaged_source_names_are_repaired():
    # Natural Earth's name_full drops some accented letters: "Rivire Magpie", "Ro Bravo".
    quebec = {"name": "Magpie", "name_full": "Rivire Magpie"}
    assert hydro.water_name(quebec, "river") == "Rivière Magpie"
    assert hydro.water_name({"name_full": "Ro Bravo"}, "river") == "Río Bravo"


def test_short_names_abbreviate_the_generic_words():
    assert hydro.short_name("Flathead River") == "Flathead R."
    assert hydro.short_name("Flathead Lake") == "Flathead L."
    assert hydro.short_name("Lake Mead") == "L. Mead"
    assert hydro.short_name("South Fork Flathead River") == "S. Fk. Flathead R."
    assert hydro.short_name("Hungry Horse Reservoir") == "Hungry Horse Res."
    assert hydro.short_name("Clear Creek") == "Clear Cr."
    assert hydro.short_name("Rivière Magpie") == "R. Magpie"
    assert hydro.short_name("Saint Mary River") == "St. Mary R."
    assert hydro.short_name("Rio Grande") == "Rio Grande"  # nothing to shorten
    assert hydro.short_name("Salton Sea") == "Salton Sea"


def _box(west, south, east, north):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def test_full_name_zoom_grows_as_the_feature_shrinks():
    # The zoom from which the full name fits: a wider lake fits it sooner.
    big = hydro.full_name_zoom("Flathead Lake", _box(-114.3, 47.7, -114.0, 48.0), "lake")
    small = hydro.full_name_zoom("Flathead Lake", _box(-114.3, 47.7, -114.25, 48.0), "lake")
    assert small > big
    # A longer name needs more room, up to the 7-em wrap width.
    box = _box(-114.3, 47.7, -114.0, 48.0)
    assert hydro.full_name_zoom("Bear Lake", box, "lake") < big
    assert hydro.full_name_zoom("Flathead Lake Reservoir", box, "lake") == big  # both wrap


def test_full_name_zoom_for_a_river_uses_its_length():
    short_line = _line((-114.0, 47.0), (-113.98, 47.0))
    long_line = _line((-114.0, 47.0), (-113.0, 47.0))
    name = "Middle Fork Flathead River"
    assert hydro.full_name_zoom(name, short_line, "river") > hydro.full_name_zoom(
        name, long_line, "river"
    )
    # 26 characters at 10.5 px is about 150 px; 1 degree of longitude at 47 N is 0.68
    # degrees of latitude, 150 px of it at zoom 7.3.
    assert hydro.full_name_zoom(name, long_line, "river") == 7.3


def test_water_features_carry_short_names_and_their_zoom():
    lake = {
        "type": "Feature",
        "properties": {"name": "Flathead Lake", "featurecla": "Lake", "scalerank": 3},
        "geometry": _box(-114.3, 47.7, -114.0, 48.0),
    }
    (out,) = hydro._water([lake], "lake")
    props = out["properties"]
    assert props["name"] == "Flathead Lake" and props["short"] == "Flathead L."
    assert isinstance(props["fullz"], float)
