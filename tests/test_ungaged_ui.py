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
    RegionNotDelineatedError,
    RegulatedDelineationError,
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
    monkeypatch.setattr(ungaged_ui, "delineate_watershed", lambda *a, **k: ws)
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out == {"basin": BASIN, "snap": (46.9312, -113.9688), "area_sq_mi": 142.3}


def test_run_delineation_asks_for_the_polygon_only(monkeypatch):
    seen = {}

    def fake(*args, **kw):
        seen.update(args=args, **kw)
        return _watershed()

    def no_characteristics(*a, **k):
        raise AssertionError("Delineate must not ask ss-hydro for characteristics")

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", fake)
    monkeypatch.setattr(
        "flowfreq.streamstats.delineate_and_get_characteristics", no_characteristics
    )
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert seen["args"] == ("MT", 46.93, -113.97)
    assert seen["cache"] is not None
    assert out["area_sq_mi"] == pytest.approx(142.3)


def test_estimate_and_delineation_share_one_streamstats_cache(monkeypatch):
    caches = {}

    def fake_delineate(*args, **kw):
        caches["delineate"] = kw.get("cache")
        return _watershed()

    def fake_estimate(lat, lon, **kw):
        caches["estimate"] = kw.get("cache")
        return _estimate()

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", fake_delineate)
    monkeypatch.setattr(ungaged_ui, "estimate_at_site", fake_estimate)
    ungaged_ui.run_delineation(46.93, -113.97, "MT")
    ungaged_ui.run_estimate(46.93, -113.97, "MT", [], False)
    assert caches["delineate"] is not None
    assert caches["delineate"] is caches["estimate"]


def test_run_delineation_without_a_polygon_is_an_input_error(monkeypatch):
    monkeypatch.setattr(ungaged_ui, "delineate_watershed", lambda *a, **k: _watershed(polygon=None))
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out["kind"] == "input" and "polygon" in out["error"]


@pytest.mark.parametrize(
    "exc, kind",
    [
        (UnsnappablePointError("no stream within reach of the point"), "unsnappable"),
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

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", boom)
    out = ungaged_ui.run_delineation(46.93, -113.97, "MT")
    assert out["kind"] == kind
    # A refusal reads plainly and keeps the library's message as its detail.
    assert str(exc) in (out["detail"] if kind in ungaged_ui.REFUSAL_KINDS else out["error"])
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
    monkeypatch.setattr(ungaged_ui, "delineate_watershed", fake_delineate)
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


# --- Results on the map: basin, GeoJSON download, other states ------------------------

TWO_STATE_BASIN = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [[-108.1, 44.9], [-107.9, 44.9], [-107.9, 45.1], [-108.1, 45.1], [-108.1, 44.9]]
        ],
    },
}
MT_INPUTS = {
    "lat": 45.05,
    "lon": -108.0,
    "state": "MT",
    "aeps": [],
    "snapshot": False,
    "extrapolate": False,
}


def _estimate_with_basin(basin, state="MT"):
    est = _estimate()
    est.state = state
    est.provenance = {"snap": {"snapped_lat": 45.051, "snapped_lon": -108.001}}
    est.basin_geojson = basin  # SiteEstimate.basin_geojson, flowfreq >= 0.18
    return est


def _seeded_matching(monkeypatch, outcome, inputs=MT_INPUTS):
    """Run with the widgets matching ``inputs`` and ``outcome`` stored."""
    stub = _MapStub(None)
    monkeypatch.setattr(ungaged_ui, "basin_map", stub)
    at = AppTest.from_function(_page, default_timeout=30)
    at.session_state["ungaged_lat"] = inputs["lat"]
    at.session_state["ungaged_lon"] = inputs["lon"]
    at.session_state["ungaged_state"] = inputs["state"]
    at.session_state["ungaged_result"] = {"inputs": inputs, "outcome": outcome}
    return at.run(), stub


def _labels(at):
    return [d.proto.label for d in at.get("download_button")]


def test_estimate_basin_reaches_the_component_and_download(monkeypatch, recorders):
    est = _estimate_with_basin(BASIN)
    at, stub = _seeded_matching(monkeypatch, {"estimate": est})
    assert not at.exception
    assert stub.calls[-1]["basin"] is BASIN
    assert stub.calls[-1]["snap"] == (45.051, -108.001)
    assert "Download basin (GeoJSON)" in _labels(at)


def test_estimate_without_basin_shows_table_only(monkeypatch, recorders):
    est = _estimate_with_basin(None)
    at, stub = _seeded_matching(monkeypatch, {"estimate": est})
    assert not at.exception
    assert at.dataframe
    assert stub.calls[-1]["basin"] is None
    assert "Download basin (GeoJSON)" not in _labels(at)


def test_delineation_result_shows_caption_and_download_no_table(monkeypatch, recorders):
    outcome = {"basin": BASIN, "snap": (46.9312, -113.9688), "area_sq_mi": 142.3}
    at, stub = _seeded_matching(monkeypatch, outcome)
    assert not at.exception
    # The summary line sits just under the map, where the user is looking.
    assert any("142.3 sq mi" in m.value and "Press Estimate" in m.value for m in at.success)
    assert not at.dataframe
    assert "Download basin (GeoJSON)" in _labels(at)
    assert stub.calls[-1]["basin"] is BASIN
    assert stub.calls[-1]["snap"] == (46.9312, -113.9688)


def test_other_states_offered_for_a_two_state_basin(monkeypatch, recorders):
    at, _ = _seeded_matching(monkeypatch, {"estimate": _estimate_with_basin(TWO_STATE_BASIN)})
    assert not at.exception
    assert any("also lies in WY" in i.value for i in at.info)
    rerun = [b for b in at.button if b.label == "Re-run with WY"]
    assert rerun
    rerun[0].click()
    at.run()
    assert not at.exception
    assert at.session_state["ungaged_state"] == "WY"
    assert [kw["state"] for _, _, kw in recorders["estimate"]] == ["WY"]


def test_no_other_states_for_a_one_state_basin(monkeypatch, recorders):
    at, _ = _seeded_matching(monkeypatch, {"estimate": _estimate_with_basin(BASIN)})
    assert not [b for b in at.button if b.label.startswith("Re-run with")]


def test_basin_download_name():
    name = ungaged_ui.basin_download_name("MT", 46.87, -113.99)
    assert name == "ungaged_MT_46.8700_-113.9900.geojson"


def test_estimate_button_hands_the_basin_to_the_map(monkeypatch):
    est = _estimate_with_basin(BASIN)
    monkeypatch.setattr(ungaged_ui, "estimate_at_site", lambda lat, lon, **kw: est)
    stub = _MapStub(None)
    monkeypatch.setattr(ungaged_ui, "basin_map", stub)
    at = AppTest.from_function(_page, default_timeout=30)
    at.session_state["ungaged_lat"] = 45.05
    at.session_state["ungaged_lon"] = -108.0
    at.session_state["ungaged_state"] = "MT"
    at.run()
    [b for b in at.button if b.label == "Estimate"][0].click()
    at.run()
    assert not at.exception
    assert stub.calls[-1]["basin"] is BASIN  # the rerun after Estimate reached the map


# --- Review fixes -------------------------------------------------------------------


def test_wrapped_longitude_is_normalised(monkeypatch, recorders):
    # A click on the world copy west of the antimeridian: Attu reported as -186.8.
    at, _ = _with_map(monkeypatch, _event("point", lat=52.9, lon=-186.8))
    assert not at.exception
    assert at.session_state["ungaged_lon"] == pytest.approx(173.2)
    assert at.session_state["ungaged_state"] == "AK"


def test_nonce_restarts_after_the_map_remounts(monkeypatch, recorders):
    stub = _MapStub(None)
    monkeypatch.setattr(ungaged_ui, "basin_map", stub)
    at = AppTest.from_function(_page, default_timeout=30)
    at.session_state["map_event_nonce"] = 1  # from before a page switch
    at.run()  # the remounted map has no value yet
    stub.event = _event("point", nonce=1)  # its counter restarted
    at.run()
    assert at.session_state["ungaged_lat"] == 46.87


def test_point_event_clears_the_drawn_basin(monkeypatch, recorders):
    outcome = {"basin": BASIN, "snap": (46.9312, -113.9688), "area_sq_mi": 142.3}
    at, stub = _seeded_matching(monkeypatch, outcome)
    assert stub.calls[-1]["basin"] is BASIN
    stub.event = _event("point", lat=46.0, lon=-112.0, nonce=7)
    at.run()
    assert not at.exception
    assert stub.calls[-1]["basin"] is None  # the map no longer shows the old basin


def test_basin_cache_is_bounded_and_in_memory():
    cache = ungaged_ui.BasinCache(maxsize=2)
    cache.set("a", {"n": 1})
    cache.set("b", {"n": 2})
    assert cache.get("a") == {"n": 1}  # touching "a" makes "b" the oldest
    cache.set("c", {"n": 3})
    assert cache.get("b") is None
    assert cache.get("a") == {"n": 1} and cache.get("c") == {"n": 3}


def test_shared_cache_is_the_in_memory_one():
    assert isinstance(ungaged_ui._streamstats_cache(), ungaged_ui.BasinCache)


# --- Phase 1: map polish ---------------------------------------------------------------


def test_mode_event_sets_the_mode_and_fills_nothing(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, {"action": "mode", "mode": "green", "nonce": 5})
    assert not at.exception
    assert at.session_state["map_mode"] == "green"
    assert at.session_state["ungaged_lat"] is None
    at.run()
    assert stub.calls[-1]["mode"] == "green"
    assert recorders == {"estimate": [], "delineate": []}


def test_unknown_mode_is_ignored(monkeypatch, recorders, caplog):
    with caplog.at_level(logging.WARNING, logger="ungaged_ui"):
        at, _ = _with_map(monkeypatch, {"action": "mode", "mode": "sepia", "nonce": 5})
    assert not at.exception
    assert at.session_state["map_mode"] in ("dem", "night")
    assert any("map event" in r.getMessage() for r in caplog.records)


def test_no_style_selector_below_the_map(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, None)
    assert not at.get("button_group")  # the style buttons live on the map now


def test_malformed_event_is_logged_once(monkeypatch, recorders, caplog):
    with caplog.at_level(logging.WARNING, logger="ungaged_ui"):
        at, _ = _with_map(monkeypatch, {"action": "point", "nonce": 3})
        at.run()
        at.run()
    assert sum("map event" in r.getMessage() for r in caplog.records) == 1


def test_basin_extras_computed_once_per_basin(monkeypatch, recorders):
    calls = []
    real = ungaged_ui.states_touching
    monkeypatch.setattr(ungaged_ui, "states_touching", lambda b: calls.append(1) or real(b))
    ungaged_ui._BASIN_EXTRAS.clear()
    at, _ = _seeded_matching(monkeypatch, {"estimate": _estimate_with_basin(TWO_STATE_BASIN)})
    at.run()
    at.run()
    assert not at.exception
    assert len(calls) == 1


# --- Option B: compare the states a basin crosses -------------------------------------


def test_comparison_frame_lines_up_aeps_across_states():
    mt, wy = _estimate_with_basin(TWO_STATE_BASIN, "MT"), _estimate_with_basin(
        TWO_STATE_BASIN, "WY"
    )
    wy.quantiles = wy.quantiles.assign(flow_cfs=[15000.0])
    frame = ungaged_ui.comparison_frame({"MT": mt, "WY": wy})
    assert list(frame.columns) == ["AEP (%)", "MT (cfs)", "WY (cfs)"]
    assert frame.iloc[0].tolist() == ["1", "19,572", "15,000"]


def test_compare_button_runs_each_state_and_shows_them_side_by_side(monkeypatch, recorders):
    at, _ = _seeded_matching(monkeypatch, {"estimate": _estimate_with_basin(TWO_STATE_BASIN)})
    compare = [b for b in at.button if b.label.startswith("Compare")]
    assert compare and "MT" in compare[0].label and "WY" in compare[0].label
    compare[0].click()
    at.run()
    assert not at.exception
    assert [kw["state"] for _, _, kw in recorders["estimate"]] == ["WY"]  # MT is already here
    assert at.session_state["ungaged_state"] == "MT"  # the primary result is unchanged
    assert any("WY (cfs)" in str(df.value.columns.tolist()) for df in at.dataframe)
    assert [t.label for t in at.tabs] == ["MT", "WY"]


def test_compare_shows_a_failed_state_in_its_tab(monkeypatch, recorders):
    def failing(lat, lon, **kw):
        raise EquationsUnavailable(f"{kw['state']}: no equations")

    at, _ = _seeded_matching(monkeypatch, {"estimate": _estimate_with_basin(TWO_STATE_BASIN)})
    monkeypatch.setattr(ungaged_ui, "estimate_at_site", failing)
    [b for b in at.button if b.label.startswith("Compare")][0].click()
    at.run()
    assert not at.exception
    assert any("WY: no equations" in e.value for e in at.error)


# --- Second review ------------------------------------------------------------------


def test_gage_event_opens_the_gage_page(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, {"action": "gage", "site": "12340500", "nonce": 9})
    assert not at.exception
    assert "gage" in str(at.query_params["page"])
    assert "12340500" in str(at.query_params["site"])


def test_gage_event_with_a_bad_site_is_ignored(monkeypatch, recorders, caplog):
    with caplog.at_level(logging.WARNING, logger="ungaged_ui"):
        at, _ = _with_map(monkeypatch, {"action": "gage", "site": "<b>", "nonce": 9})
    assert "page" not in at.query_params


def test_the_map_reopens_where_the_user_was(monkeypatch, recorders):
    at, stub = _with_map(monkeypatch, _event("point", lat=46.87, lon=-113.99))
    at.run()
    assert stub.calls[-1]["view"] == (46.87, -113.99, 9.0)


def test_a_typed_edit_clears_the_drawn_basin(monkeypatch, recorders):
    outcome = {"basin": BASIN, "snap": (46.9312, -113.9688), "area_sq_mi": 142.3}
    at, stub = _seeded_matching(monkeypatch, outcome)
    assert stub.calls[-1]["basin"] is BASIN
    at.number_input[0].set_value(45.5)
    at.run()
    assert stub.calls[-1]["basin"] is None


def test_delineate_outside_the_jurisdictions_is_refused(monkeypatch, recorders):
    at, _ = _with_map(monkeypatch, _event("delineate", lat=27.0, lon=-89.0))
    assert not at.exception
    assert recorders["delineate"] == []
    assert any("outside" in w.value for w in at.warning)


def test_a_failure_shows_once_just_below_the_map(monkeypatch, recorders):
    def degenerate(*a, **k):
        raise DegenerateDelineationError("degenerate watershed polygon")

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", degenerate)
    at, _ = _with_map(monkeypatch, _event("delineate"))
    errors = [e.value for e in at.error if "degenerate" in e.value]
    assert len(errors) == 1


def test_a_refusal_shows_once_as_a_warning(monkeypatch, recorders):
    def unsnappable(*a, **k):
        raise UnsnappablePointError("could not snap to a stream")

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", unsnappable)
    at, _ = _with_map(monkeypatch, _event("delineate"))
    warnings = [w.value for w in at.warning if "stream network" in w.value]
    assert len(warnings) == 1
    assert not [e.value for e in at.error if "snap" in e.value]


def test_gage_event_remembers_where_the_map_was(monkeypatch, recorders):
    event = {
        "action": "gage",
        "site": "12340500",
        "lat": 44.7,
        "lon": -110.6,
        "zoom": 9.5,
        "nonce": 9,
    }
    at, _ = _with_map(monkeypatch, event)
    assert at.session_state["map_view"] == (44.7, -110.6, 9.5)


# StreamStats refusals that are the point, the basin or the state, not an app failure
# (flowfreq v0.20.0): a plain message and a warning, from both Estimate and Delineate.
REFUSALS = [
    (
        RegionNotDelineatedError(
            "StreamStats' snap service has no stream grid for region 'MI' (No such region)"
        ),
        "unsupported_region",
        "does not delineate basins in",
    ),
    (
        RegulatedDelineationError(
            "StreamStats delineation warning at (46.37, -100.93) in region 'ND': "
            "REGULATED: CANNONBALL RIVER"
        ),
        "regulated",
        "regulated (Cannonball River)",
    ),
    (
        UnsnappablePointError("StreamStats could not snap (55.39, -131.19) in region 'AK'"),
        "unsnappable",
        "not on StreamStats' stream network",
    ),
]


@pytest.mark.parametrize("exc, kind, text", REFUSALS)
def test_estimate_refusals_read_plainly(monkeypatch, exc, kind, text):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(ungaged_ui, "estimate_at_site", boom)
    out = ungaged_ui.run_estimate(44.4, -85.7, "MI", [], False)
    assert out["kind"] == kind and kind in ungaged_ui.REFUSAL_KINDS
    assert text in out["error"]


@pytest.mark.parametrize("exc, kind, text", REFUSALS)
def test_delineation_refusals_read_plainly(monkeypatch, exc, kind, text):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(ungaged_ui, "delineate_watershed", boom)
    out = ungaged_ui.run_delineation(44.4, -85.7, "MI")
    assert out["kind"] == kind
    assert text in out["error"]


def test_unsupported_region_names_the_state():
    exc = RegionNotDelineatedError("no stream grid for region 'NE'")
    out = ungaged_ui.streamstats_refusal(exc, "NE")
    assert "Nebraska" in out["error"]
    assert "StreamStats does not delineate basins in Nebraska:" in out["error"]


def test_other_value_errors_stay_input_errors():
    assert ungaged_ui.streamstats_refusal(ValueError("bad coordinate"), "TN") is None
