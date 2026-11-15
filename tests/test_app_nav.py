"""Page switching (`app_nav`) and the link to a point on the ungaged page."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

import app_nav
import ungaged_ui

CODES = ["KY", "MT", "TN"]


# --- app_nav ------------------------------------------------------------------------


def test_go_rejects_an_unknown_page():
    with pytest.raises(ValueError, match="unknown page 'map'"):
        app_nav.go("map")


def test_register_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown page name"):
        app_nav.register({"map": object()})


def _two_pages():
    import streamlit as st

    import app_nav
    import gage_ui

    def gage():
        gage_ui.back_button()
        st.write("the gage page")

    def ungaged():
        st.write("the map page, query " + str(sorted(st.query_params.to_dict().items())))
        if st.button("Open a gage"):
            app_nav.go("gage", site="12340500")

    pages = {
        "gage": st.Page(gage, title="Gage", default=True),
        "ungaged": st.Page(ungaged, title="Ungaged site", url_path="ungaged"),
    }
    app_nav.register(pages)
    st.navigation(list(pages.values())).run()


def _text(at):
    return " ".join(m.value for m in at.markdown)


def test_back_button_switches_to_the_registered_page():
    at = AppTest.from_function(_two_pages, default_timeout=30).run()
    assert "the gage page" in _text(at)
    [b for b in at.button if "Back to the map" in b.label][0].click()
    at.run()
    assert not at.exception
    assert "the map page" in _text(at) and "the gage page" not in _text(at)
    # A switch to a registered page is by its path: no ?page= is left behind.
    assert "page" not in at.query_params


def _only_a_page():
    import streamlit as st

    import app_nav

    if st.button("Open a gage"):
        app_nav.go("gage", site="12340500")


def test_go_without_registered_pages_leaves_a_page_link():
    # A page module run by itself: the link is what streamlit_app redirects.
    at = AppTest.from_function(_only_a_page, default_timeout=30).run()
    at.button[0].click()
    at.run()
    assert not at.exception
    assert "gage" in str(at.query_params["page"])
    assert "12340500" in str(at.query_params["site"])


# --- The link to a point ------------------------------------------------------------


def test_link_query_is_the_point_and_the_jurisdiction():
    inputs = {"lat": 36.1, "lon": -88.25, "state": "TN", "aeps": [0.01], "snapshot": True}
    assert ungaged_ui.link_query(inputs) == {
        "lat": "36.100000",
        "lon": "-88.250000",
        "state": "TN",
    }


def test_link_query_without_a_jurisdiction():
    assert ungaged_ui.link_query({"lat": 36.1, "lon": -88.25, "state": None}) == {
        "lat": "36.100000",
        "lon": "-88.250000",
    }


@pytest.mark.parametrize("inputs", [{"lat": None, "lon": -88.2}, {"lat": 36.1, "lon": None}, {}])
def test_no_link_without_both_coordinates(inputs):
    assert ungaged_ui.link_query(inputs) is None


def test_point_from_link_round_trips_link_query():
    query = ungaged_ui.link_query({"lat": 36.1234567, "lon": -88.2, "state": "TN"})
    assert ungaged_ui.point_from_link(query, CODES) == (36.123457, -88.2, "TN")


def test_point_from_link_takes_the_state_from_the_point_when_the_link_has_none():
    # Big Sandy River at Bruceton, Tennessee.
    assert ungaged_ui.point_from_link({"lat": "36.04", "lon": "-88.23"}, CODES) == (
        36.04,
        -88.23,
        "TN",
    )


def test_point_from_link_ignores_a_state_that_is_not_offered():
    lat, lon, code = ungaged_ui.point_from_link(
        {"lat": "36.04", "lon": "-88.23", "state": "<b>"}, CODES
    )
    assert code == "TN"
    # In the ocean, and no usable state: the point alone.
    assert ungaged_ui.point_from_link({"lat": "30.0", "lon": "-40.0", "state": "ZZ"}, CODES) == (
        30.0,
        -40.0,
        None,
    )


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"lat": "36.1"},
        {"lat": "north", "lon": "-88.2"},
        {"lat": "91", "lon": "-88.2"},
        {"lat": "36.1", "lon": "-181"},
        {"lat": "nan", "lon": "-88.2"},
        {"lat": "36.1", "lon": "inf"},
    ],
)
def test_point_from_link_rejects_what_is_not_a_point(params):
    assert ungaged_ui.point_from_link(params, CODES) is None


def test_point_url_off_the_pages_own_path_names_the_page():
    # No browser behind this call, so no address: a relative link, with page=ungaged.
    url = ungaged_ui.point_url({"lat": "36.100000", "lon": "-88.200000", "state": "TN"})
    assert url == "?page=ungaged&lat=36.100000&lon=-88.200000&state=TN"


class _Context:
    def __init__(self, url):
        self.url = url


@pytest.mark.parametrize(
    "address, expected",
    [
        ("https://app.example/ungaged", "https://app.example/ungaged?lat=1.000000&lon=2.000000"),
        (
            "https://app.example/ungaged?lat=9&lon=9",
            "https://app.example/ungaged?lat=1.000000&lon=2.000000",
        ),
        ("https://app.example", "https://app.example?page=ungaged&lat=1.000000&lon=2.000000"),
    ],
)
def test_point_url_is_absolute_when_the_address_is_known(monkeypatch, address, expected):
    monkeypatch.setattr(ungaged_ui.st, "context", _Context(address))
    assert ungaged_ui.point_url({"lat": "1.000000", "lon": "2.000000"}) == expected


class _MapStub:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return None


def _page():
    from ungaged_ui import render

    render()


@pytest.fixture
def linked(monkeypatch):
    """The ungaged page opened on a link, with the estimate recorded instead of run."""
    calls = []

    def fake_run_estimate(lat, lon, state, aeps, snapshot, **kwargs):
        calls.append((lat, lon, state))
        return {"error": "stub", "kind": "input"}

    stub = _MapStub()
    monkeypatch.setattr(ungaged_ui, "basin_map", stub)
    monkeypatch.setattr(ungaged_ui, "run_estimate", fake_run_estimate)

    def open_link(**query):
        at = AppTest.from_function(_page, default_timeout=30)
        for key, value in query.items():
            at.query_params[key] = value
        return at.run()

    open_link.calls = calls
    open_link.map = stub
    return open_link


def test_a_link_fills_the_inputs_and_starts_the_estimate(linked):
    at = linked(lat="36.04", lon="-88.23", state="TN")
    assert not at.exception
    assert at.number_input(key="ungaged_lat").value == 36.04
    assert at.number_input(key="ungaged_lon").value == -88.23
    assert at.session_state["ungaged_state"] == "TN"
    assert linked.calls == [(36.04, -88.23, "TN")]
    assert linked.map.calls[-1]["view"] == (36.04, -88.23, ungaged_ui.LINK_ZOOM)


def test_a_link_is_applied_once(linked):
    at = linked(lat="36.04", lon="-88.23", state="TN")
    at.run()  # the same address again: nothing more is run
    assert linked.calls == [(36.04, -88.23, "TN")]
    assert all(key in at.query_params for key in ungaged_ui.LINK_PARAMS)


def test_a_link_outside_every_jurisdiction_fills_the_point_and_runs_nothing(linked):
    at = linked(lat="30.0", lon="-40.0")
    assert not at.exception
    assert at.number_input(key="ungaged_lat").value == 30.0
    assert linked.calls == []


def test_a_bad_link_changes_nothing(linked):
    at = linked(lat="north", lon="-88.23", state="TN")
    assert not at.exception
    assert at.number_input(key="ungaged_lat").value is None
    assert linked.calls == []


def test_moving_the_point_takes_the_link_out_of_the_address(linked):
    at = linked(lat="36.04", lon="-88.23", state="TN")
    at.number_input(key="ungaged_lat").set_value(36.5)
    at.run()
    assert not at.exception
    assert not any(key in at.query_params for key in ungaged_ui.LINK_PARAMS)
    assert at.number_input(key="ungaged_lat").value == 36.5  # and the link is not reapplied
    assert linked.calls == [(36.04, -88.23, "TN")]


def test_the_page_offers_a_link_to_its_point(linked):
    at = linked(lat="36.04", lon="-88.23", state="TN")
    assert [c.value for c in at.code] == ["?page=ungaged&lat=36.040000&lon=-88.230000&state=TN"]


def test_no_link_is_offered_without_a_point(linked):
    at = linked()
    assert not at.exception
    assert not at.code
