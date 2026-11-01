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


def test_html_pins_one_maplibre_version_and_only_https():
    versions = set(re.findall(r"maplibre-gl@([\d.]+)", HTML))
    assert len(versions) == 1
    assert "http://" not in HTML


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
    assert "?page=gage&site=" in HTML
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
