"""The ungaged page's frequency curve (``ungaged_curve``): frames, gage lookup, chart, section."""

from __future__ import annotations

from typing import Any, Dict

import pandas as pd
import pytest
from flowfreq.ungaged import SiteEstimate
from streamlit.testing.v1 import AppTest

import ungaged_curve

#: Big Sandy River at Bruceton, TN (USGS 03606500): the gage house, and its drainage area.
BIG_SANDY = (36.0394, -88.2281)


def _estimate(lower=(900.0, 1400.0, 2100.0), upper=(3700.0, 5000.0, 12500.0)) -> SiteEstimate:
    aeps, flows = (0.5, 0.2, 0.01), (1855.0, 2638.0, 5163.0)
    quantiles = pd.DataFrame(
        {
            "aep": aeps,
            "flow_cfs": flows,
            "lower": lower,
            "upper": upper,
            "interval_level": 0.9,
            "interval_method": "average variance of prediction",
            "extrapolated": False,
            "regions": "HA4",
        }
    )
    return SiteEstimate(
        lat=BIG_SANDY[0],
        lon=BIG_SANDY[1],
        state="TN",
        method="regression",
        quantiles=quantiles,
        regions=[],
        unmatched_regions=[],
        characteristics={"DRNAREA": 205.0},
        library_status="verified",
        advisory="",
        estimates={},
    )


def _fit() -> Dict[str, Any]:
    table = pd.DataFrame(
        {
            "Return Interval (yr)": [2.0, 10.0, 100.0],
            "AEP (%)": [0.5, 0.1, 0.01],
            "Flow (cfs)": [4948.0, 12315.0, 27265.0],
            "Lower 90% CI": [4344.0, 10447.0, 20808.0],
            "Upper 90% CI": [5648.0, 15166.0, 42026.0],
        }
    )
    return {"quantile_df": table, "error": None, "converged": True}


class TestAepPosition:
    def test_the_median_is_the_origin_and_rarer_is_further_right(self):
        assert ungaged_curve.aep_position(0.5) == pytest.approx(0.0, abs=1e-12)
        assert ungaged_curve.aep_position(0.01) == pytest.approx(2.326348, abs=1e-6)
        assert ungaged_curve.aep_position(0.99) == pytest.approx(-2.326348, abs=1e-6)

    @pytest.mark.parametrize("aep", [0.0, 1.0, -0.1, 50.0])
    def test_refuses_what_is_not_a_probability(self, aep):
        with pytest.raises(ValueError, match="between 0 and 1"):
            ungaged_curve.aep_position(aep)


class TestFrames:
    def test_regression_rows_are_the_estimates_quantiles(self):
        frame = ungaged_curve.regression_frame(_estimate())
        assert list(frame["series"].unique()) == [ungaged_curve.REGRESSION]
        assert list(frame["aep_pct"]) == [50.0, 20.0, 1.0]  # common floods first
        assert list(frame["flow"]) == [1855.0, 2638.0, 5163.0]
        assert list(frame["lower"]) == [900.0, 1400.0, 2100.0]
        assert frame["z"].is_monotonic_increasing

    def test_a_missing_limit_leaves_the_flow_and_drops_its_partner(self):
        estimate = _estimate(lower=(900.0, float("nan"), 2100.0))
        frame = ungaged_curve.regression_frame(estimate)
        assert list(frame["flow"]) == [1855.0, 2638.0, 5163.0]
        assert frame["lower"].isna().tolist() == [False, True, False]
        assert frame["upper"].isna().tolist() == [False, True, False]

    def test_gage_rows_come_from_the_fits_quantile_table(self):
        frame = ungaged_curve.gage_frame(_fit(), "03606500")
        assert list(frame["series"].unique()) == ["USGS 03606500 Bulletin 17C fit"]
        assert frame["aep"].tolist() == pytest.approx([0.5, 0.1, 0.01])
        assert list(frame["flow"]) == [4948.0, 12315.0, 27265.0]
        assert list(frame["upper"]) == [5648.0, 15166.0, 42026.0]

    def test_a_failed_fit_is_refused_with_its_own_message(self):
        failed = {"quantile_df": pd.DataFrame(), "error": "This record is regulated."}
        with pytest.raises(ValueError, match="This record is regulated"):
            ungaged_curve.gage_frame(failed, "03606500")
        with pytest.raises(ValueError, match="no fitted quantiles"):
            ungaged_curve.gage_frame({"quantile_df": pd.DataFrame()}, "03606500")


class TestNearestGage:
    def test_finds_the_gage_at_the_point(self):
        gage = ungaged_curve.nearest_gage(*BIG_SANDY)
        assert gage is not None
        assert gage["site_no"] == "03606500" and "BIG SANDY" in gage["site_name"]
        assert gage["distance_km"] < 0.5
        assert gage["drainage_area_sqmi"] == pytest.approx(205.0)
        assert gage["n_peaks"] > 40

    def test_none_when_no_gage_is_that_close(self):
        assert ungaged_curve.nearest_gage(36.2, -88.0) is None
        assert ungaged_curve.nearest_gage(*BIG_SANDY, max_km=0.001) is None

    def test_refuses_a_point_off_the_globe(self):
        with pytest.raises(ValueError, match="not a latitude and longitude"):
            ungaged_curve.nearest_gage(136.0, -88.0)


class TestChart:
    def test_one_series_has_a_band_a_line_and_points_and_no_legend(self):
        spec = ungaged_curve.curve_chart(ungaged_curve.regression_frame(_estimate())).to_dict()
        marks = [layer["mark"]["type"] for layer in spec["layer"]]
        assert marks == ["area", "line", "point"]
        line = spec["layer"][1]["encoding"]
        assert line["y"]["scale"]["type"] == "log"
        assert line["color"]["legend"] is None
        axis = line["x"]["axis"]
        # Ticks at the standard AEPs inside the data, labelled in percent.
        assert axis["values"] == pytest.approx(
            [ungaged_curve.aep_position(p) for p in (0.5, 0.2, 0.1, 0.04, 0.02, 0.01)]
        )
        assert "? '50' :" in axis["labelExpr"] and "? '1' :" in axis["labelExpr"]

    def test_a_gage_adds_a_second_series_and_a_legend(self):
        regression = ungaged_curve.regression_frame(_estimate())
        gage = ungaged_curve.gage_frame(_fit(), "03606500")
        spec = ungaged_curve.curve_chart(regression, gage).to_dict()
        assert [layer["mark"]["type"] for layer in spec["layer"]] == [
            "area",
            "area",
            "line",
            "point",
        ]
        line, points = spec["layer"][2]["encoding"], spec["layer"][3]["encoding"]
        names = [ungaged_curve.REGRESSION, "USGS 03606500 Bulletin 17C fit"]
        assert line["color"]["scale"]["domain"] == names
        assert line["color"]["legend"]["orient"] == "top"
        # Told apart by dash and point shape as well as colour.
        assert line["strokeDash"]["scale"]["range"] == [[1, 0], [6, 3]]
        assert points["shape"]["scale"]["range"] == ["circle", "diamond"]
        low, high = line["y"]["scale"]["domain"]
        assert low < 900.0 and high > 42026.0  # both bands are inside the flow axis

    def test_nothing_to_draw_is_an_error(self):
        empty = ungaged_curve.regression_frame(_estimate()).iloc[0:0]
        with pytest.raises(ValueError, match="no quantiles to draw"):
            ungaged_curve.curve_chart(empty)


class TestBandCaption:
    def test_names_the_interval_and_the_gages_limits(self):
        estimate = _estimate()
        alone = ungaged_curve.band_caption(estimate, False)
        assert alone == "The band around the regression is its 90-percent prediction interval."
        both = ungaged_curve.band_caption(estimate, True)
        assert both.endswith(
            "The band around the gage's fit is its 90-percent confidence interval."
        )

    def test_says_when_some_or_all_aeps_have_no_interval(self):
        nan = float("nan")
        some = ungaged_curve.band_caption(_estimate(lower=(900.0, nan, 2100.0)), False)
        assert some.endswith("prediction interval, at the AEPs that have one.")
        none = ungaged_curve.band_caption(_estimate(lower=(nan,) * 3, upper=(nan,) * 3), False)
        assert "publish no prediction interval" in none


def _section(with_fit: bool = True, fit_error: str = ""):
    """A page that shows the section for an estimate at the Big Sandy gage."""
    import pandas as pd
    import streamlit as st

    import ungaged_curve
    from tests.test_ungaged_curve import _estimate, _fit

    def gage_fit(site_no):
        st.session_state["fitted"] = [*st.session_state.get("fitted", []), site_no]
        if fit_error:
            return {"quantile_df": pd.DataFrame(), "error": fit_error}
        return _fit()

    ungaged_curve.show(_estimate(), gage_fit if with_fit else None)


def _page_alone():
    import ungaged_ui

    ungaged_ui.render()


def _charts(at: AppTest) -> list:
    # Streamlit has named the element both ways.
    return [*at.get("vega_lite_chart"), *at.get("arrow_vega_lite_chart")]


class TestSection:
    def test_without_a_fit_the_curve_is_the_regressions_alone(self):
        at = AppTest.from_function(_section, kwargs={"with_fit": False}, default_timeout=30).run()
        assert not at.exception
        assert len(_charts(at)) == 1 and not at.button
        assert [c.value for c in at.caption] == [
            "The band around the regression is its 90-percent prediction interval."
        ]

    def test_a_gage_at_the_point_is_offered_and_fitted_only_on_request(self):
        at = AppTest.from_function(_section, default_timeout=30).run()
        assert not at.exception
        offer = at.caption[0].value
        assert offer.startswith("USGS 03606500 BIG SANDY RIVER AT BRUCETON, TN is ")
        assert "Drainage area: gage 205.0 sq mi, this estimate 205.0 sq mi." in offer
        assert "fitted" not in at.session_state  # nothing is downloaded before the click
        (button,) = at.button
        assert button.label == "Overlay the fit at USGS 03606500"

        at = button.click().run()
        assert not at.exception
        assert at.session_state["fitted"] == ["03606500"]
        assert not at.button and len(_charts(at)) == 1
        assert at.caption[-1].value.endswith("its 90-percent confidence interval.")

    def test_a_fit_that_fails_is_a_warning_under_the_regression_curve(self):
        at = AppTest.from_function(
            _section, kwargs={"fit_error": "This record is regulated."}, default_timeout=30
        ).run()
        at = at.button[0].click().run()
        assert not at.exception
        assert [w.value for w in at.warning] == [
            "The fit at USGS 03606500 could not be drawn: This record is regulated."
        ]
        assert len(_charts(at)) == 1
        assert at.caption[-1].value == (
            "The band around the regression is its 90-percent prediction interval."
        )

    def test_one_quantile_is_not_drawn(self):
        def page():
            import ungaged_curve
            from tests.test_ungaged_ui import _estimate

            ungaged_curve.show(_estimate())

        at = AppTest.from_function(page, default_timeout=30).run()
        assert not at.exception and not _charts(at)


def test_the_page_draws_the_curve_and_hands_on_the_apps_fit():
    def page():
        import ungaged_ui
        from tests.test_ungaged_curve import _fit

        ungaged_ui.render(gage_fit=lambda site_no: _fit())

    at = AppTest.from_function(page, default_timeout=30)
    at.session_state["ungaged_result"] = {"outcome": {"estimate": _estimate()}}
    at.run()
    assert not at.exception
    assert len(_charts(at)) == 1
    (button,) = [b for b in at.button if b.label.startswith("Overlay the fit")]
    at = button.click().run()
    assert not at.exception
    assert [c for c in at.caption if c.value.endswith("its 90-percent confidence interval.")]
    assert not [b for b in at.button if b.label.startswith("Overlay the fit")]


def test_the_page_offers_no_overlay_without_the_apps_fit():
    at = AppTest.from_function(_page_alone, default_timeout=30)
    at.session_state["ungaged_result"] = {"outcome": {"estimate": _estimate()}}
    at.run()
    assert not at.exception
    assert len(_charts(at)) == 1
    assert not [b for b in at.button if b.label.startswith("Overlay the fit")]
