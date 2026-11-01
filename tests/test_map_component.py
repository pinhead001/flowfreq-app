"""Tests for ``map_component``: the files the component serves, and the argument
preparation that runs before every render.

The JavaScript itself is checked by hand (``docs/map_manual_checks.md``); these tests pin
what can be pinned from Python: the served files exist, the HTML loads one pinned MapLibre
over HTTPS, and the args are JSON-serialisable with the basin rounded and fingerprinted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="Streamlit not installed")

import map_component
import map_geo

ROOT = Path(map_component.__file__).parent
HTML = (ROOT / "index.html").read_text(encoding="utf-8") if (ROOT / "index.html").exists() else ""

BASIN = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
            [[[-108.123456789, 44.9], [-107.9, 44.9], [-107.9, 45.1], [-108.123456789, 44.9]]]
        ],
    },
}


def _args(**kw):
    base = dict(
        point=(46.87, -113.99),
        basin=None,
        snap=None,
        mode="dem",
        overlays=frozenset(),
        coverage={"MT": "verified"},
        height=520,
    )
    base.update(kw)
    return map_component.prepare_args(**base)


def test_component_files_exist():
    assert (ROOT / "index.html").is_file()
    assert (ROOT / "states.geojson").is_file()


def test_html_loads_the_bundled_maplibre_and_only_https():
    # Served next to index.html: no CDN to be down or to change under a pinned URL.
    for name in ("maplibre-gl.js", "maplibre-gl.css"):
        assert f'"vendor/{name}"' in HTML
    assert "unpkg.com" not in HTML and "demotiles.maplibre.org" not in HTML
    assert "MapLibre contributors" in (ROOT / "vendor" / "LICENSE.txt").read_text()
    assert "http://" not in HTML


@pytest.mark.parametrize("name", ["maplibre-gl.js", "maplibre-gl.css"])
def test_bundled_maplibre_matches_its_integrity_hash(name):
    import base64
    import hashlib

    pinned = re.search(rf'"vendor/{re.escape(name)}" integrity="(sha384-[^"]+)"', HTML)
    digest = hashlib.sha384((ROOT / "vendor" / name).read_bytes()).digest()
    assert pinned and pinned.group(1) == "sha384-" + base64.b64encode(digest).decode()


def test_html_lists_streamgrid_services():
    # The StreamStats stateServices directory as of 2026-10-30: states, territories with
    # a grid, and the river-basin services.
    listed = re.search(r"STREAMGRID_SERVICES = \[([^\]]*)\]", HTML)
    assert listed is not None
    names = re.findall(r'"([a-z_]+)"', listed.group(1))
    assert len(names) == 55
    assert {"mt", "ak", "hi", "pr", "crb", "drb"} <= set(names)
    assert "fl" not in names  # no StreamStats grid for Florida: the chip says so


def test_html_declares_all_three_actions():
    assert 'emit("point"' in HTML  # left click
    for action in ('data-act="delineate"', 'data-act="estimate"'):  # context menu
        assert action in HTML


def test_html_gage_popup_links():
    assert 'textContent = "Gage page"' in HTML  # opens the app's gage page (see below)
    assert "https://waterdata.usgs.gov/monitoring-location/" in HTML


def test_html_has_the_four_jump_buttons():
    for label in ("CONUS", "Alaska", "Hawaii", "Territories"):
        assert f">{label}<" in HTML or f'"{label}"' in HTML


def test_prepare_args_rounds_and_hashes_the_basin():
    args = _args(basin=BASIN)
    ring = args["basin"]["geometry"]["coordinates"][0][0]
    assert ring[0] == [-108.123457, 44.9]
    assert args["basin"]["properties"]["hash"] == map_geo.geojson_hash(args["basin"])
    assert BASIN["properties"] == {}  # the caller's feature is not modified


def test_prepare_args_serialises():
    args = _args(basin=BASIN, snap=(44.95, -108.0), overlays=frozenset({"coverage"}))
    decoded = json.loads(json.dumps(args))
    assert decoded["point"] == [46.87, -113.99]
    assert decoded["snap"] == [44.95, -108.0]
    assert decoded["overlays"] == ["coverage"]
    assert decoded["mode"] == "dem" and decoded["height"] == 520


def test_prepare_args_passes_none_through():
    args = _args(point=None)
    assert args["point"] is None and args["basin"] is None and args["snap"] is None


def test_prepare_args_rejects_unknown_mode():
    with pytest.raises(ValueError, match="mode"):
        _args(mode="sepia")


def test_html_wraps_click_longitudes():
    # Clicks on a repeated world copy must reach Python inside +-180.
    assert "lngLat.wrap()" in HTML


def test_html_nonce_is_unique_per_page_load():
    # A remounted iframe must not reuse nonces Python has already seen.
    assert re.search(r"nonce = Date\.now\(\)", HTML)


def test_html_pages_past_the_gage_record_limit():
    assert "exceededTransferLimit" in HTML and "resultOffset" in HTML


def test_prepare_args_prepares_a_basin_once(monkeypatch):
    calls = []
    real = map_component.round_coords
    monkeypatch.setattr(map_component, "round_coords", lambda b: calls.append(1) or real(b))
    map_component._PREPARED.clear()
    first = _args(basin=BASIN)
    second = _args(basin=BASIN)
    assert len(calls) == 1
    assert first["basin"] == second["basin"]
    other = {**BASIN, "geometry": {**BASIN["geometry"]}}
    _args(basin=other)
    assert len(calls) == 2  # a different object is prepared afresh


def test_html_has_style_buttons_on_the_map():
    for mode in ("dem", "night", "green"):
        assert f'data-mode="{mode}"' in HTML
    assert 'action: "mode"' in HTML


def test_html_disables_rotation():
    assert "dragRotate: false" in HTML
    assert "disableRotation()" in HTML


def test_html_coarse_shade_stops_at_zoom_12():
    layer = re.search(r'\{ id: "shade-coarse"[^}]*', HTML).group(0)
    assert "maxzoom: 12" in layer


def test_html_fetches_states_once():
    assert HTML.count('fetch("./states.geojson")') == 1
    assert 'data: "./states.geojson"' not in HTML


def test_html_keeps_a_clicked_style_until_python_confirms_it():
    # A rerun already in flight carries the previous style; it must not undo the click.
    assert "pendingMode" in HTML


# --- Phase 2: real water-body names -------------------------------------------------


def test_html_drops_the_labelled_usgs_hydro_tiles():
    # Their labels are baked in ("Gulf of America") and cannot be renamed.
    assert "USGSHydroCached" not in HTML


def test_html_exports_nhd_and_wbd_without_labels():
    assert '"https://hydro.nationalmap.gov/arcgis/rest/services"' in HTML
    assert "/MapServer/export?" in HTML
    assert 'exportTiles("nhd",' in HTML and 'exportTiles("wbd",' in HTML
    assert "showLabels: false" in HTML


def test_html_labels_water_from_bundled_files():
    for name in ("water_base.geojson", "water_detail.geojson", "water_labels.geojson"):
        assert name in HTML
        assert (ROOT / name).is_file()
    # Glyphs are bundled too, resolved against the page's own address.
    assert re.search(r'glyphs: [^,]*"fonts/\{fontstack\}/\{range\}\.pbf"', HTML)


def test_bundled_glyphs_cover_every_bundled_name():
    font = re.search(r'const WATER_FONT = \["([^"]+)"\]', HTML).group(1)
    ranges = set()
    for name in ("water_base", "water_detail", "water_labels", "states"):
        data = json.loads((ROOT / f"{name}.geojson").read_text(encoding="utf-8"))
        for feature in data["features"]:
            for value in (feature.get("properties") or {}).values():
                if isinstance(value, str):
                    ranges.update(ord(c) // 256 for c in value)
    for r in ranges:
        assert (ROOT / "fonts" / font / f"{r * 256}-{r * 256 + 255}.pbf").is_file()
    assert "Open Font License" in (ROOT / "fonts" / "OFL.txt").read_text(encoding="utf-8")


def test_bundled_water_labels_use_real_names():
    import json as _json

    names = set()
    for name in ("water_base.geojson", "water_detail.geojson", "water_labels.geojson"):
        fc = _json.loads((ROOT / name).read_text(encoding="utf-8"))
        names |= {f["properties"].get("name") for f in fc["features"]}
    assert "Gulf of Mexico" in names
    assert not any(n and n.endswith(" America") and n.startswith(("Gulf", "Lake")) for n in names)


# --- Review polish -------------------------------------------------------------------


def test_html_starts_with_the_attribution_collapsed():
    # Expanded, the attribution bar covers labels along the bottom ("Gulf of Mexico").
    assert "maplibregl-compact-show" in HTML


def test_html_lightens_huc_lines_when_zoomed_out():
    # HUC2 regions fill the CONUS view; they fade up to full strength by zoom 8.
    assert "3, r.opacity * 0.45, 8, r.opacity" in HTML


# --- Second review: map ---------------------------------------------------------------


def test_html_gage_link_goes_through_python_not_top_navigation():
    # The component iframe may not navigate the top window (no allow-top-navigation).
    assert 'target = "_top"' not in HTML
    assert 'action: "gage"' in HTML


def test_html_reopens_at_the_last_view():
    assert "args.view" in HTML


def test_html_shows_progress_while_streamstats_works():
    assert 'id="chip-busy"' in HTML


def test_html_closes_popups_when_the_view_jumps_away():
    assert "closePopups()" in HTML


def test_html_brings_a_typed_point_into_view():
    assert "easeTo" in HTML


def test_html_guards_the_maplibre_load():
    assert re.search(r'vendor/maplibre-gl\.js" integrity="sha384-[A-Za-z0-9+/=]+"', HTML)
    assert "typeof maplibregl" in HTML


def test_prepare_args_passes_the_view():
    assert _args(view=(46.87, -113.99, 9.0))["view"] == [46.87, -113.99, 9.0]
    assert _args()["view"] is None


def test_identity_cache_is_bounded_and_keyed_by_object():
    cache = map_component.IdentityCache(maxsize=2)
    a, b, c = {"n": 1}, {"n": 2}, {"n": 3}
    calls = []
    make = lambda obj: calls.append(obj) or obj["n"] * 10  # noqa: E731
    assert cache.get(a, make) == 10 and cache.get(a, make) == 10
    assert len(calls) == 1
    cache.get(b, make)
    cache.get(c, make)  # evicts a
    cache.get(a, make)
    assert len(calls) == 4
    assert cache.get({"n": 1}, make) == 10 and len(calls) == 5  # equal is not the same object


def test_identity_cache_survives_concurrent_eviction():
    from concurrent.futures import ThreadPoolExecutor

    cache = map_component.IdentityCache(maxsize=4)
    objs = [{"i": i} for i in range(400)]
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda o: cache.get(o, lambda x: x["i"]), objs))
    assert results == list(range(400))


def test_water_names_have_a_short_form_and_the_zoom_the_full_one_fits():
    # The build measures each label against its feature; the map shows "Flathead R." until
    # the zoom from which "Flathead River" fits.
    for name in ("water_base.geojson", "water_detail.geojson"):
        features = json.loads((ROOT / name).read_text(encoding="utf-8"))["features"]
        shortened = [f["properties"] for f in features if "short" in f["properties"]]
        assert shortened, name
        assert all(isinstance(p.get("fullz"), (int, float)) for p in shortened)
    assert '["get", "fullz"]' in HTML and '["get", "short"]' in HTML
