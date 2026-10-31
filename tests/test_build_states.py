"""Tests for tools/build_states_geojson.py's validation (no network)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "tools" / "build_states_geojson.py"
_spec = importlib.util.spec_from_file_location("build_states_geojson", _PATH)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def _feature(code):
    return {
        "type": "Feature",
        "properties": {"STUSAB": code},
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    }


def test_truncated_response_is_refused():
    payload = {"features": [_feature("MT")], "properties": {"exceededTransferLimit": True}}
    with pytest.raises(ValueError, match="truncated"):
        build.features_of(payload)


def test_complete_response_passes():
    assert build.features_of({"features": [_feature("MT")]}) == [_feature("MT")]


def test_wrong_feature_count_is_refused():
    collection = {"features": [_feature("MT")] * 55}
    with pytest.raises(ValueError, match="56"):
        build.check_count(collection)
