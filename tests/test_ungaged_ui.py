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
