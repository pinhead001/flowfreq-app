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
