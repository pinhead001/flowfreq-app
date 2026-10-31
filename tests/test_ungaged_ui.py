"""Tests for the ungaged-site page (``ungaged_ui``), in Streamlit's bare mode.

``estimate_at_site`` is monkeypatched: these tests check how the page maps the
library's outcomes (an estimate, an overlap, each failure) to what the user sees,
not the regression mathematics, which is the library's to test.
"""

from __future__ import annotations

import logging

import pandas as pd
import pytest
import requests

pytest.importorskip("streamlit", reason="Streamlit not installed")

from flowfreq import OverlappingRegionsError
from flowfreq.regression.equations import OutOfRangeError
from flowfreq.regression.library import EquationsUnavailable
from flowfreq.streamstats import (
    Characteristic,
    DegenerateDelineationError,
    Provenance,
    SnapResult,
    UnsnappablePointError,
    UnsupportedRegionError,
    WatershedCharacteristics,
)
from flowfreq.ungaged import QUANTILE_COLUMNS, SiteEstimate
from streamlit.testing.v1 import AppTest

import ungaged_ui

logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)

CANDIDATES = [
    ("GC344", "Tennessee 2003", 2003),
    ("GC2016", "Tennessee 2016", 2016),
    ("GC2020", "Tennessee 2025", 2025),
]


def _estimate(status: str = "verified", advisory: str = "") -> SiteEstimate:
    quantiles = pd.DataFrame(
        [[0.01, 19572.0, 12000.0, 31000.0, 0.9, "prediction interval", False, "GC2016"]],
        columns=list(QUANTILE_COLUMNS),
    )
    return SiteEstimate(
        lat=36.32,
        lon=-87.05,
        state="TN",
        method="regression",
        quantiles=quantiles,
        regions=[],
        unmatched_regions=[],
        characteristics={"DRNAREA": 12.3},
        library_status=status,
        advisory=advisory,
        estimates={},
    )


@pytest.mark.parametrize(
    "code, badge",
    [
        ("WA", "verified"),
        ("TN", "nss snapshot (not report-verified)"),
        ("DC", "none: NSS serves no peak-flow regions"),
    ],
)
def test_coverage_badge(code, badge):
    assert ungaged_ui.coverage_badge(code) == badge


def test_run_estimate_success(monkeypatch):
    est = _estimate()
    seen = {}

    def fake(lat, lon, **kw):
        seen.update(lat=lat, lon=lon, **kw)
        return est

    monkeypatch.setattr(ungaged_ui, "estimate_at_site", fake)
    out = ungaged_ui.run_estimate(36.3, -87.0, "TN", [0.01], True, region="GC2016")
    assert out == {"estimate": est}
    assert seen["state"] == "TN" and seen["aeps"] == [0.01]
    assert seen["allow_nss_snapshot"] is True and seen["region"] == "GC2016"


def test_run_estimate_no_aeps_means_all_published(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        ungaged_ui, "estimate_at_site", lambda lat, lon, **kw: seen.update(kw) or _estimate()
    )
    ungaged_ui.run_estimate(36.3, -87.0, "WA", [], False)
    assert seen["aeps"] is None


@pytest.mark.parametrize(
    "exc, kind",
    [
        (EquationsUnavailable("DC: no equations"), "equations"),
        (OutOfRangeError("DRNAREA outside range"), "out_of_range"),
        (KeyError("unknown state 'ZZ'"), "input"),
        (ValueError("bad coordinate"), "input"),
        (LookupError("no stream near the point"), "input"),
        (requests.ConnectionError("StreamStats down"), "network"),
    ],
)
def test_run_estimate_never_raises(monkeypatch, exc, kind):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(ungaged_ui, "estimate_at_site", boom)
    out = ungaged_ui.run_estimate(36.3, -87.0, "TN", [], False)
    assert out["kind"] == kind
    assert isinstance(out["error"], str) and out["error"]
    assert "estimate" not in out


def test_run_estimate_overlap_carries_candidates(monkeypatch):
    def boom(*a, **k):
        raise OverlappingRegionsError("TN", CANDIDATES)

    monkeypatch.setattr(ungaged_ui, "estimate_at_site", boom)
    out = ungaged_ui.run_estimate(36.3, -87.0, "TN", [], True)
    assert out["kind"] == "overlap"
    assert out["candidates"] == CANDIDATES
    assert "GC2016" in out["error"]


BASIN = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[-113.97, 46.93], [-114.0, 47.0], [-113.9, 47.05], [-113.97, 46.93]]],
    },
}


def _watershed(polygon=BASIN, area=142.3) -> WatershedCharacteristics:
    return WatershedCharacteristics(
        region="MT",
        snap=SnapResult(46.93, -113.97, 46.9312, -113.9688, True, 13.2),
        polygon_geojson=polygon,
        characteristics={"DRNAREA": Characteristic("DRNAREA", "Drainage area", "", area, "mi2")},
        provenance=Provenance(
            service_versions={},
            request_urls=[],
            requested_at_utc="2026-10-30T00:00:00+00:00",
            server_used="test",
        ),
        polygon_area_sq_mi=area,
    )


def test_run_delineation_success(monkeypatch):
    ws = _watershed()
    monkeypatch.setattr(ungaged_ui, "delineate_and_get_characteristics", lambda *a, **k: ws)
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out == {"basin": BASIN, "snap": (46.9312, -113.9688), "area_sq_mi": 142.3}


def test_run_delineation_asks_for_drainage_area_only(monkeypatch):
    seen = {}

    def fake(*args, **kw):
        seen.update(args=args, **kw)
        return _watershed()

    monkeypatch.setattr(ungaged_ui, "delineate_and_get_characteristics", fake)
    ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert seen["args"] == ("MT", 46.93, -113.97)
    assert seen["characteristic_codes"] == ["DRNAREA"]


def test_run_delineation_without_a_polygon_is_an_input_error(monkeypatch):
    monkeypatch.setattr(
        ungaged_ui, "delineate_and_get_characteristics", lambda *a, **k: _watershed(polygon=None)
    )
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out["kind"] == "input" and "polygon" in out["error"]


@pytest.mark.parametrize(
    "exc, kind",
    [
        (UnsnappablePointError("no stream within reach of the point"), "input"),
        (DegenerateDelineationError("degenerate watershed"), "input"),
        (UnsupportedRegionError("FL has no StreamStats service"), "input"),
        (ValueError("bad coordinate"), "input"),
        (requests.ConnectionError("StreamStats down"), "network"),
        (RuntimeError("boom"), "unexpected"),
    ],
)
def test_run_delineation_never_raises(monkeypatch, exc, kind):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(ungaged_ui, "delineate_and_get_characteristics", boom)
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out["kind"] == kind
    assert str(exc) in out["error"]
    assert "basin" not in out


def _page():
    from ungaged_ui import render

    render()


def _run(result):
    at = AppTest.from_function(_page, default_timeout=30)
    at.session_state["ungaged_result"] = result
    return at.run()


def test_advisory_shown_for_nss_snapshot():
    text = "NSS snapshot: not checked against the source report."
    at = _run({"outcome": {"estimate": _estimate("nss_snapshot", text)}})
    assert not at.exception
    assert any(text in w.value for w in at.warning)


def test_no_advisory_for_verified():
    at = _run({"outcome": {"estimate": _estimate("verified", "")}})
    assert not at.exception
    assert not at.warning


def test_download_payload_is_to_markdown(monkeypatch):
    import streamlit as st

    est = _estimate()
    payloads = []
    real = st.download_button
    monkeypatch.setattr(
        st, "download_button", lambda *a, **k: payloads.append(k.get("data")) or real(*a, **k)
    )
    _run({"outcome": {"estimate": est}})
    assert payloads == [est.to_markdown()]


def test_overlap_shows_candidate_selector():
    at = _run_matching(
        {
            "outcome": {"error": "overlap", "kind": "overlap", "candidates": CANDIDATES},
            "inputs": INPUTS,
        }
    )
    assert not at.exception
    sel = [s for s in at.selectbox if s.label == "Equation set"]
    assert len(sel) == 1
    assert len(sel[0].options) == 3 and "GC2016" in sel[0].options[1]
    assert not at.error


def test_failure_is_shown_as_error():
    at = _run({"outcome": {"error": "No stream near the point", "kind": "input"}})
    assert [e.value for e in at.error] == ["No stream near the point"]


def test_page_wired_into_app(app_module=None):
    import importlib

    mod = importlib.import_module("streamlit_app")
    assert mod.ungaged_ui is ungaged_ui


INPUTS = {
    "lat": 36.3,
    "lon": -87.0,
    "state": "TN",
    "aeps": [],
    "snapshot": True,
    "extrapolate": False,
}


def _seeded(result):
    at = AppTest.from_function(_page, default_timeout=30)
    at.session_state["ungaged_result"] = result
    at.run()
    return at


def test_stale_result_cleared_when_inputs_change():
    result = {
        "outcome": {"error": "overlap", "kind": "overlap", "candidates": CANDIDATES},
        "inputs": INPUTS,
    }
    # Widgets default to lat/lon None, so they differ from the stored inputs.
    at = _seeded(result)
    assert not at.exception
    assert not [s for s in at.selectbox if s.label == "Equation set"]
    assert "ungaged_result" not in at.session_state


def _run_matching(result):
    """Run with the widgets set to INPUTS and ``result`` stored."""
    at = AppTest.from_function(_page, default_timeout=30).run()
    at.number_input[0].set_value(INPUTS["lat"])
    at.number_input[1].set_value(INPUTS["lon"])
    at.selectbox[0].set_value("TN")
    at.checkbox[0].check()
    at.session_state["ungaged_result"] = result
    return at.run()


def test_result_kept_when_inputs_match():
    at = _run_matching(
        {
            "outcome": {"error": "overlap", "kind": "overlap", "candidates": CANDIDATES},
            "inputs": INPUTS,
        }
    )
    assert [s for s in at.selectbox if s.label == "Equation set"]


def test_chosen_set_caption():
    from types import SimpleNamespace

    est = _estimate()
    est.regions = [SimpleNamespace(code="GC2016", name="TN_Peakflow_Region_2_SIR_2024-5130")]
    est.provenance = {
        "options": {"region": "GC2016"},
        "alternative_regions": [
            {"code": "GC344", "year": 2003},
            {"code": "GC2020", "year": 2025},
        ],
    }
    text = ungaged_ui.chosen_set_caption(est)
    assert text.startswith("Equation set chosen: GC2016 (TN_Peakflow_Region_2_SIR_2024-5130")
    assert text.endswith("Not used: GC344 (2003), GC2020 (2025).")
    at = _run({"outcome": {"estimate": est}})
    assert any(text == c.value for c in at.caption)


def test_no_caption_without_a_choice():
    assert ungaged_ui.chosen_set_caption(_estimate()) == ""


# --- The map: events from the component fill the inputs ------------------------------


class _MapStub:
    """Stands in for ``basin_map``: returns a chosen event and records its kwargs."""

    def __init__(self, event=None):
        self.event = event
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.event


def _event(action="point", lat=46.87, lon=-113.99, nonce=1):
    return {"action": action, "lat": lat, "lon": lon, "zoom": 9.0, "nonce": nonce}


@pytest.fixture
def recorders(monkeypatch):
    calls = {"estimate": [], "delineate": []}

    def fake_estimate(lat, lon, **kw):
        calls["estimate"].append((lat, lon, kw))
        return _estimate()

    def fake_delineate(state, lat, lon, **kw):
        calls["delineate"].append((state, lat, lon))
        return _watershed()

    monkeypatch.setattr(ungaged_ui, "estimate_at_site", fake_estimate)
    monkeypatch.setattr(ungaged_ui, "delineate_and_get_characteristics", fake_delineate)
    return calls


def _with_map(monkeypatch, event):
    stub = _MapStub(event)
    monkeypatch.setattr(ungaged_ui, "basin_map", stub)
    at = AppTest.from_function(_page, default_timeout=30).run()
    return at, stub


def test_point_event_fills_inputs_and_runs_nothing(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, _event("point"))
    assert not at.exception
    assert at.session_state["ungaged_lat"] == 46.87
    assert at.session_state["ungaged_lon"] == -113.99
    assert at.session_state["ungaged_state"] == "MT"
    assert at.number_input[0].value == 46.87
    assert recorders == {"estimate": [], "delineate": []}


def test_same_nonce_is_ignored_on_rerun(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, _event("point"))
    at.number_input[0].set_value(45.0)
    at.run()
    assert at.session_state["ungaged_lat"] == 45.0  # the old click did not come back


def test_new_nonce_updates_the_inputs(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, _event("point"))
    stub.event = _event("point", lat=44.5, lon=-110.0, nonce=2)
    at.run()
    assert at.session_state["ungaged_lat"] == 44.5
    assert at.session_state["ungaged_state"] == "WY"


def test_ocean_click_leaves_jurisdiction(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, _event("point"))  # MT
    stub.event = _event("point", lat=27.0, lon=-89.0, nonce=2)  # Gulf of Mexico
    at.run()
    assert not at.exception
    assert at.session_state["ungaged_lat"] == 27.0
    assert at.session_state["ungaged_state"] == "MT"


@pytest.mark.parametrize(
    "event",
    [
        {"action": "point"},
        {"action": "point", "lat": "north", "lon": -110.0, "nonce": 1},
        {"action": "teleport", "lat": 45.0, "lon": -110.0, "nonce": 1},
        "not a dict",
    ],
)
def test_malformed_event_is_ignored(monkeypatch, recorders, caplog, event):
    with caplog.at_level(logging.WARNING, logger="ungaged_ui"):
        at, _ = _with_map(monkeypatch, event)
    assert not at.exception
    assert at.session_state["ungaged_lat"] is None
    assert any("map event" in r.getMessage() for r in caplog.records)


def test_delineate_event_calls_delineation_only(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, _event("delineate"))
    assert not at.exception
    assert recorders["delineate"] == [("MT", 46.87, -113.99)]
    assert recorders["estimate"] == []


def test_estimate_event_calls_estimate(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, _event("estimate"))
    assert not at.exception
    assert len(recorders["estimate"]) == 1
    lat, lon, kw = recorders["estimate"][0]
    assert (lat, lon, kw["state"]) == (46.87, -113.99, "MT")
    assert at.dataframe  # the quantile table


def test_typed_coordinates_reach_the_component(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, None)
    assert stub.calls[-1]["point"] is None
    at.number_input[0].set_value(44.5)
    at.number_input[1].set_value(-110.0)
    at.run()
    assert stub.calls[-1]["point"] == (44.5, -110.0)


def test_coverage_passed_for_every_jurisdiction(monkeypatch, recorders):
    from flowfreq.regression import JURISDICTIONS

    _, stub = _with_map(monkeypatch, None)
    coverage = stub.calls[-1]["coverage"]
    assert set(coverage) == {j.code for j in JURISDICTIONS}
    assert coverage["DC"] == ungaged_ui.BADGE_NONE


def test_coverage_toggle_switches_the_overlay(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, None)
    assert stub.calls[-1]["overlays"] == frozenset()
    at.toggle[0].set_value(True)
    at.run()
    assert stub.calls[-1]["overlays"] == frozenset({"coverage"})


@pytest.mark.parametrize("theme, mode", [("dark", "night"), ("light", "dem"), (None, "dem")])
def test_mode_defaults_from_theme(monkeypatch, theme, mode):
    monkeypatch.setattr(ungaged_ui, "_theme_type", lambda: theme)
    assert ungaged_ui.default_mode() == mode
