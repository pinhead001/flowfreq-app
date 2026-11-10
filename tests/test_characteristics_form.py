"""The ungaged page's characteristics form (flowfreq 0.26's estimate_from_characteristics)."""

from __future__ import annotations

import pytest

import ungaged_ui

needs = pytest.mark.skipif(
    ungaged_ui.estimate_from_characteristics is None,
    reason="the pinned flowfreq has no estimate_from_characteristics yet",
)


@needs
def test_inputs_are_the_regions_characteristics_with_ranges():
    rows = ungaged_ui.characteristic_inputs("FL", "1")
    codes = [r["code"] for r in rows]
    assert codes[:2] == ["DRNAREA", "LC92STOR"]
    drn = rows[0]
    assert drn["units"] and drn["minimum"] < drn["maximum"]


@needs
def test_run_reproduces_a_florida_gage():
    out = ungaged_ui.run_from_characteristics(
        "FL", "1", {"DRNAREA": 105.0, "LC92STOR": 43.3}, 30.4, -84.3, [0.01], False
    )
    assert round(out["estimate"].quantiles.loc[0, "flow_cfs"], -1) == 5160  # SIR 2011-5034's 5,160


@needs
def test_run_refuses_with_reasons():
    out = ungaged_ui.run_from_characteristics(
        "FL", "1", {"DRNAREA": 1e7, "LC92STOR": 43.3}, 30.4, -84.3, None, False
    )
    assert out["kind"] == "out_of_range" and "no estimate was made" in out["error"]
    out = ungaged_ui.run_from_characteristics(
        "FL", "9", {"DRNAREA": 10.0}, 30.4, -84.3, None, False
    )
    assert out["kind"] == "equations" and "choose from" in out["error"]


@needs
def test_form_opens_for_a_state_without_streamstats():
    from streamlit.testing.v1 import AppTest

    def page():
        import streamlit as st

        from ungaged_ui import render

        st.session_state["ungaged_state"] = "FL"
        render()

    at = AppTest.from_function(page, default_timeout=30).run()
    assert not at.exception
    form = [e for e in at.expander if e.label == "Basin characteristics (no StreamStats)"]
    assert form and form[0].proto.expanded
    assert {n.label.split(" ")[0] for n in form[0].number_input} >= {"DRNAREA", "LC92STOR"}


def test_form_is_hidden_on_an_older_pin(monkeypatch):
    monkeypatch.setattr(ungaged_ui, "estimate_from_characteristics", None)
    out = ungaged_ui.run_from_characteristics("FL", "1", {}, 30.4, -84.3, None, False)
    assert out["kind"] == "input"
