"""Import smoke test for ``streamlit_app.py``.

The app is a top-level script, not a module with a ``main()``: importing it
executes the entire body -- every widget call, every ``st.session_state``
default, and every flowfreq call reachable before the first button press.
Streamlit calls this *bare mode*, widgets return their declared defaults, and
``download_data`` is therefore ``False``, so nothing here contacts NWIS.

That makes a plain import a real check, and it is coverage the app did not
have: CI linted ``flowfreq/`` and ``tests/`` only and ran no app tests at all,
which is why Streamlit changes could not be reviewed with any confidence. This
catches a stale import, a ``NameError`` on a branch no test takes, and -- the
one that matters -- an app call that no longer matches a flowfreq signature.

Skipped when Streamlit is absent, which includes the 3.9 matrix job: Streamlit
requires Python >= 3.10. The ``app`` job in ``.github/workflows/tests.yml``
installs ``app/requirements.txt`` so that this actually runs somewhere.
"""

from __future__ import annotations

import importlib
import logging
import pathlib

import pytest

pytest.importorskip(
    "streamlit",
    reason="Streamlit not installed; pip install -r app/requirements.txt",
)

# One 'missing ScriptRunContext!' warning per widget call, and the app builds
# dozens. Expected in bare mode, and it would bury a real failure in the log.
logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)

# Names the app pulls out of flowfreq and ffa_*. If one of these stops
# resolving, the app is broken for every user even though flowfreq's own tests
# are green -- which is exactly the failure this module exists to catch.
WIRED_CALLABLES = (
    "run_ffa",
    "format_parameters_df",
    "format_quantile_df",
    "build_skew_curves_dict",
    "compute_skew_tables",
    "export_comparison_csv",
    "export_ffa_to_zip",
    "plot_frequency_curve",
    "plot_peak_flows_with_thresholds",
    "USGSgage",
    "Hydrograph",
)


@pytest.fixture(scope="module")
def app_module():
    """The imported app. Importing it *is* the smoke test; assertions follow."""
    return importlib.import_module("streamlit_app")


def test_app_imports(app_module):
    assert app_module.__name__ == "streamlit_app"


@pytest.mark.parametrize("name", WIRED_CALLABLES)
def test_wired_entry_point_resolves(app_module, name):
    attr = getattr(app_module, name, None)
    assert attr is not None, f"streamlit_app.py no longer exposes {name}"
    assert callable(attr), f"{name} is not callable"


def test_app_reports_the_installed_hydrolib_version(app_module):
    from flowfreq import __version__

    assert app_module.__version__ == __version__


def test_skew_options_are_offered(app_module):
    """SKEW_OPTIONS drives a sidebar selectbox; an empty one would render a dead control."""
    assert app_module.SKEW_OPTIONS


class TestPilfOverrideWiring:
    """The PILF override was reachable only from Python; now it is in the UI.

    run_ffa has always accepted low_outlier_threshold_override, but
    streamlit_app.py never passed it. These check the wiring end to end: the
    sidebar value reaches run_ffa, and the applied cut is drawn on the record
    rather than only changing a number in the parameter table.
    """

    @staticmethod
    def _peaks():
        import pandas as pd

        from tests.fixtures.big_sandy import SYSTEMATIC_PEAKS

        return pd.DataFrame(
            {
                "water_year": sorted(SYSTEMATIC_PEAKS),
                "peak_flow_cfs": [SYSTEMATIC_PEAKS[y] for y in sorted(SYSTEMATIC_PEAKS)],
            }
        )

    def test_app_passes_the_override_to_run_ffa(self, app_module):
        """Both call sites, not just the download path.

        Both now go through run_site_ffa, which makes the one run_ffa call; each
        call site must hand it the sidebar's override.
        """
        source = pathlib.Path(app_module.__file__).read_text()
        assert source.count("low_outlier_threshold_override=pilf_override or None") == 1
        assert source.count("pilf_override=pilf_override,") == 2

    def test_year_boxes_reset_when_a_new_gage_is_downloaded(self, app_module):
        """A stored widget key outlives the gage it was chosen for.

        Streamlit lets a value stored under `key=` win over the `value=`
        default on every render after the first, so the FFA year boxes carry
        one gage's range into the next. Downloading 12363000 (record from 1922)
        after 09355500 left them reading 1955-2013: the download fit the full
        record and reported Q100 120,106, while the boxes claimed a range that,
        on the next Update Plots, silently refit a subset nobody selected.

        Both keys must be dropped in the download handler, before the widgets
        are rebuilt, or the boxes and the displayed fit disagree.
        """
        source = pathlib.Path(app_module.__file__).read_text()
        start = source.index("if download_data and gage_list:")
        block = source[start : start + 1600]
        assert 'st.session_state.pop("peak_start_year", None)' in block
        assert 'st.session_state.pop("peak_end_year", None)' in block

    def test_refit_trigger_is_cleared_for_the_new_gage(self, app_module):
        """Stale prev_ffa_inputs would suppress the first refit after download."""
        source = pathlib.Path(app_module.__file__).read_text()
        start = source.index("if download_data and gage_list:")
        assert "st.session_state.prev_ffa_inputs = None" in source[start : start + 1600]

    def test_override_participates_in_the_refit_trigger(self, app_module):
        """Changing it without refitting would leave the curve silently stale."""
        source = pathlib.Path(app_module.__file__).read_text()
        start = source.index("current_ffa_inputs = (")
        assert "pilf_override" in source[start : start + 400]

    def test_plot_marks_censored_peaks_when_a_threshold_applies(self, app_module):
        fig = app_module.plot_peak_flows_with_thresholds(
            self._peaks(),
            site_name="Big Sandy",
            site_no="03606500",
            mgbt_threshold=2000.0,
            mgbt_threshold_source="override",
        )
        labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
        assert any("censored" in label for label in labels)
        assert any("2,000 cfs (override)" in label for label in labels)

    def test_plot_is_unchanged_when_no_threshold_applies(self, app_module):
        fig = app_module.plot_peak_flows_with_thresholds(
            self._peaks(), site_name="Big Sandy", site_no="03606500"
        )
        assert fig.axes[0].get_legend() is None

    def test_a_threshold_below_every_peak_censors_nothing(self, app_module):
        """Guard against drawing an empty 'censored' series and a stray legend
        entry -- the threshold line itself still draws (a real, applied cut
        worth showing even when it happens to exclude nothing), just with no
        "censored" wording and no hollow bars."""
        fig = app_module.plot_peak_flows_with_thresholds(
            self._peaks(), site_name="Big Sandy", site_no="03606500", mgbt_threshold=1.0
        )
        labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
        assert not any("censored" in label for label in labels)
        assert all(p.get_facecolor()[3] != 0 for p in fig.axes[0].patches)


# ---------------------------------------------------------------------------
# flowfreq 0.10.0: skew source, peak codes, regulation screen, data source
# ---------------------------------------------------------------------------


def _coded_peaks():
    """Big Sandy's systematic record with codes on two years, as NWIS returns them."""
    import pandas as pd

    from tests.fixtures.big_sandy import SYSTEMATIC_PEAKS

    years = sorted(SYSTEMATIC_PEAKS)
    codes = [None] * len(years)
    codes[0] = "2,7"
    codes[-1] = "6"
    return pd.DataFrame(
        {
            "water_year": years,
            "peak_flow_cfs": [SYSTEMATIC_PEAKS[y] for y in years],
            "qualification_code": pd.array(codes, dtype="string"),
        }
    )


class _RunFfaSpy:
    """Stands in for run_ffa and records the keyword arguments it was given."""

    def __init__(self, raises=None):
        self.calls = []
        self.raises = raises

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return {
            "b17c": None,
            "converged": True,
            "method": "ema",
            "parameters": {"regional_skew_source": "user"},
            "quantile_df": None,
            "error": None,
        }


def _fit(app_module, **overrides):
    kwargs = dict(
        skew_source=app_module.SKEW_SOURCE_STATION,
        regional_skew=None,
        regional_skew_se=None,
        pilf_override=0.0,
        apply_peak_codes=True,
        allow_regulated=False,
    )
    kwargs.update(overrides)
    return app_module.run_site_ffa("03606500", _coded_peaks(), **kwargs)


def _source(app_module):
    return pathlib.Path(app_module.__file__).read_text(encoding="utf-8")


class TestSkewSource:
    """The sidebar's skew choice reaches run_ffa as exactly one flowfreq skew source."""

    def test_no_nationwide_default_wording(self, app_module):
        assert "Nationwide default" not in _source(app_module)

    def test_choices_offered(self, app_module):
        assert app_module.SKEW_SOURCE_CHOICES[0] == app_module.SKEW_SOURCE_PUBLISHED
        assert "-0.302" in app_module.SKEW_SOURCE_FALLBACK

    def test_published_study_value_reaches_run_ffa(self, app_module, monkeypatch):
        from flowfreq.regional_skew import RegionalSkew

        rs = RegionalSkew(
            state="WA",
            skew_region="Pacific Northwest",
            skew=-0.07,
            skew_mse=0.18,
            citation="Mastin and others, 2016, SIR 2016-5118",
        )
        monkeypatch.setattr(app_module, "lookup_published_skew", lambda site_no: rs)
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        result = _fit(app_module, skew_source=app_module.SKEW_SOURCE_PUBLISHED)
        call = spy.calls[0]
        assert call["regional_skew"] == -0.07
        assert call["regional_skew_se"] == pytest.approx(0.18**0.5)
        assert "station_skew_only" not in call and "use_default_skew" not in call
        assert result["skew_info"]["citation"].startswith("Mastin")
        assert result["parameters"]["skew_note"] == "WA Pacific Northwest study"

    def test_unavailable_study_is_an_error_not_a_fallback(self, app_module, monkeypatch):
        from flowfreq.regional_skew import RegionalSkewUnavailable

        def unavailable(site_no):
            raise RegionalSkewUnavailable("No verified regional skew study covers HUC 0204.")

        monkeypatch.setattr(app_module, "lookup_published_skew", unavailable)
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        result = _fit(app_module, skew_source=app_module.SKEW_SOURCE_PUBLISHED)
        assert spy.calls == []
        assert result["error_kind"] == "skew"
        assert "No verified regional skew study covers HUC 0204." in result["error"]

    def test_station_skew_only(self, app_module, monkeypatch):
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        _fit(app_module, skew_source=app_module.SKEW_SOURCE_STATION)
        assert spy.calls[0]["station_skew_only"] is True
        assert "regional_skew" not in spy.calls[0]

    def test_custom_value(self, app_module, monkeypatch):
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        _fit(
            app_module,
            skew_source=app_module.SKEW_SOURCE_CUSTOM,
            regional_skew=0.1,
            regional_skew_se=0.3,
        )
        assert spy.calls[0]["regional_skew"] == 0.1
        assert spy.calls[0]["regional_skew_se"] == 0.3

    def test_fallback_is_offered_as_nationwide(self, app_module):
        assert app_module.SKEW_SOURCE_FALLBACK.startswith("Nationwide (")

    def test_unsourced_fallback_is_explicit(self, app_module, monkeypatch):
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        _fit(app_module, skew_source=app_module.SKEW_SOURCE_FALLBACK)
        assert spy.calls[0]["use_default_skew"] is True

    def test_fitted_skew_under_station_skew_only(self, app_module):
        """skew_weighted is None there; the plots must use skew_used instead."""
        params = {"skew_station": -0.19, "skew_weighted": None, "skew_used": -0.19}
        assert app_module.fitted_skew(params) == -0.19
        assert app_module.fitted_skew({"skew_weighted": -0.1}) == -0.1

    def test_plots_do_not_read_skew_weighted_directly(self, app_module):
        """A station-skew fit crashed the peak plot with float(None)."""
        source = _source(app_module)
        assert 'params["skew_weighted"]' not in source
        assert 'params.get("skew_weighted"' not in source
        assert "['skew_weighted']" not in source

    def test_both_call_sites_pass_the_skew_choice(self, app_module):
        assert _source(app_module).count("skew_source=skew_source,") == 2

    def test_skew_choice_participates_in_the_refit_trigger(self, app_module):
        source = _source(app_module)
        start = source.index("current_ffa_inputs = (")
        block = source[start : source.index(")", start)]
        for name in ("skew_source", "apply_peak_codes", "allow_regulated"):
            assert name in block


class TestPeakCodes:
    def test_codes_and_screen_inputs_reach_run_ffa(self, app_module, monkeypatch):
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        _fit(app_module, apply_peak_codes=False, allow_regulated=True)
        call = spy.calls[0]
        expected = _coded_peaks()["qualification_code"]
        assert len(call["peak_codes"]) == len(expected)
        assert list(call["peak_codes"].dropna()) == list(expected.dropna())
        # Passed through unchanged: flowfreq >= 0.10.1 reads pd.NA as "no code".
        assert call["peak_codes"].isna().iloc[1]
        assert call["apply_peak_codes"] is False
        assert call["allow_regulated"] is True
        assert call["site_no"] == "03606500"

    def test_refit_filters_codes_with_the_flows(self, app_module, monkeypatch):
        """One year mask selects flows, years and codes, so they stay aligned."""
        peaks = _coded_peaks()
        start, end = int(peaks["water_year"].iloc[0]), int(peaks["water_year"].iloc[10])
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        _fit(app_module, start_year=start, end_year=end)
        call = spy.calls[0]
        expected = peaks.iloc[:11]
        assert list(call["water_years"]) == list(expected["water_year"])
        assert list(call["peak_flows"]) == list(expected["peak_flow_cfs"])
        assert len(call["peak_codes"]) == 11
        assert call["peak_codes"].iloc[0] == "2,7"
        assert "6" not in list(call["peak_codes"].dropna())

    def test_empty_year_range_is_an_error(self, app_module, monkeypatch):
        spy = _RunFfaSpy()
        monkeypatch.setattr(app_module, "run_ffa", spy)
        result = _fit(app_module, start_year=1800, end_year=1801)
        assert spy.calls == [] and result["error"]

    def test_real_fit_reports_codes_applied(self, app_module):
        """Unmocked: flowfreq applies the codes and returns its provenance.

        The code 6 peak makes the screen class the gage regulated, so this fit
        needs the override -- which is itself recorded.
        """
        result = _fit(app_module, allow_regulated=True)
        assert result["error"] is None, result["error"]
        params = result["parameters"]
        assert params["regional_skew_source"] == "station"
        assert params["peak_codes_applied"]  # code 7 and code 6 both acted on
        assert "n_mgbt_outliers" in params
        assert params["site_classification"]["site_no"] == "03606500"
        assert params["site_classification"]["regulation_override"] is True

    def test_real_code_6_peak_is_refused_without_the_override(self, app_module):
        """Unmocked: run_ffa raises RegulatedRecordError; the app returns it as an error."""
        result = _fit(app_module)
        assert result["error_kind"] == "regulated"
        assert "classified regulated" in result["error"]

    def test_both_call_sites_pass_the_code_and_screen_choices(self, app_module):
        # Two call sites, plus run_site_ffa's own run_ffa call.
        source = _source(app_module)
        assert source.count("apply_peak_codes=apply_peak_codes,") == 3
        assert source.count("allow_regulated=allow_regulated,") == 3


class TestRegulationScreen:
    def test_refusal_becomes_a_displayable_error(self, app_module, monkeypatch):
        from flowfreq.regulation import RegulatedRecordError

        spy = _RunFfaSpy(raises=RegulatedRecordError("USGS 01426500 is classified regulated"))
        monkeypatch.setattr(app_module, "run_ffa", spy)
        result = _fit(app_module)
        assert result["error_kind"] == "regulated"
        assert "classified regulated" in result["error"]

    def test_refusal_is_shown_with_the_override_hint(self, app_module, monkeypatch):
        shown = []

        class _St:
            def error(self, msg):
                shown.append(("error", msg))

            def info(self, msg):
                shown.append(("info", msg))

        monkeypatch.setattr(app_module, "st", _St())
        app_module.show_ffa_error(
            "01426500", app_module._ffa_error("classified regulated", kind="regulated")
        )
        assert shown[0][0] == "error" and "classified regulated" in shown[0][1]
        assert "Analyze regulated gage" in shown[1][1]

    def test_errors_display_with_the_gage_not_only_during_download(self, app_module):
        """Download-loop messages are wiped by st.rerun(); the display loop must show them."""
        source = _source(app_module)
        start = source.index("# Generate/display plots for each gage")
        assert "show_ffa_error(site_no" in source[start:]


class TestDataSource:
    def test_site_info_failure_does_not_block_the_download(self, app_module):
        """flowfreq >= 0.10.1 reads site info from the Water Data API; a failure
        there is logged and the download proceeds with the attributes unset."""
        source = _source(app_module)
        call = source.index("gage.fetch_site_info()")
        assert "try:" in source[call - 60 : call]
        assert "site_name, drainage_area = gage.site_name, gage.drainage_area" in source
        assert "fill_site_metadata" not in source

    def test_daily_download_does_not_use_legacy_por_dates(self, app_module):
        """The legacy site catalog's first daily row can be another parameter.

        For 12449500 it is water temperature, 2002-04-18 to 2002-09-29, which
        cut the daily record to 165 days. flowfreq fetches the full record
        when given no dates.
        """
        source = _source(app_module)
        assert "daily_data = gage.download_daily_flow()" in source
        assert "gage.daily_por_start" not in source

    def test_api_key_is_mentioned(self, app_module):
        assert "1,000 requests/hour" in _source(app_module)


class TestComparisonExportFiltersErrors:
    def test_failed_fits_are_left_out_of_the_comparison_export(self, app_module):
        source = " ".join(_source(app_module).split())
        block = source.split("site_results_for_export = {}")[1].split("export_comparison_csv")[0]
        assert 'not st.session_state.ffa_results[ sno ].get("error")' in block


@pytest.mark.parametrize(
    "params, page",
    [
        ({"page": "ungaged"}, "Ungaged site"),
        ({"page": "flowfrequency"}, "Flow Frequency"),
        ({"page": "gaged"}, "Flow Frequency"),  # the old name still lands
        ({"page": "gage", "site": "12358500"}, "Gage"),
        ({"page": "nope"}, None),
        ({}, None),
    ],
)
def test_requested_page(app_module, params, page):
    assert app_module.requested_page(params) == page


def _app_with(params):
    from streamlit.testing.v1 import AppTest

    path = pathlib.Path(__file__).resolve().parent.parent / "streamlit_app.py"
    at = AppTest.from_file(str(path), default_timeout=60)
    for key, value in params.items():
        at.query_params[key] = value
    return at.run()


def test_ungaged_param_opens_the_ungaged_page():
    at = _app_with({"page": "ungaged"})
    assert not at.exception
    assert any("Ungaged site" in h.value for h in at.header)


@pytest.mark.parametrize("site", ["<script>alert(1)</script>", "[x](https://evil.example)", "12"])
def test_gage_page_rejects_a_bad_site(site):
    at = _app_with({"page": "gage", "site": site})
    assert not at.exception
    assert not any(site in h.value for h in at.header)
    assert any("not a valid" in e.value for e in at.error)


def test_gage_param_renders_the_gage_page(monkeypatch):
    import gage_ui

    calls = []
    monkeypatch.setattr(gage_ui, "render", lambda site: calls.append(site))
    at = _app_with({"page": "gage", "site": "12340500"})
    assert not at.exception
    assert calls == ["12340500"]


def test_gaged_param_prefills_the_gage_number():
    at = _app_with({"page": "gaged", "site": "12340500"})
    assert not at.exception
    assert at.text_input[0].value == "12340500"


def test_gaged_param_ticks_ffa_and_says_what_to_do():
    at = _app_with({"page": "gaged", "site": "12340500"})
    assert not at.exception
    ffa = [c for c in at.checkbox if c.label == "Enable Flood Frequency Analysis"][0]
    assert ffa.value is True
    assert any("12340500" in i.value and "Download Data" in i.value for i in at.info)


def test_map_and_gage_pages_have_their_own_titles():
    at = _app_with({"page": "ungaged"})
    assert not [t for t in at.title if "Hydrograph-erator" in t.value]


def test_bad_site_page_uses_the_back_button():
    at = _app_with({"page": "gage", "site": "12"})
    assert [b for b in at.button if "Back to the map" in b.label]


def test_ungaged_inputs_survive_a_trip_to_the_gaged_page():
    at = _app_with({"page": "ungaged"})
    at.number_input(key="ungaged_lat").set_value(46.87)
    at.number_input(key="ungaged_lon").set_value(-113.99)
    at.run()
    # Streamlit drops the state of widgets a run does not draw, as on the Gaged page.
    at.sidebar.radio[0].set_value("Flow Frequency")
    at.run()
    at.sidebar.radio[0].set_value("Ungaged site")
    at.run()
    assert not at.exception
    assert at.number_input(key="ungaged_lat").value == 46.87
    assert at.number_input(key="ungaged_lon").value == -113.99


def test_a_hand_off_with_run_starts_the_download_once(app_module):
    # The gage page's Bulletin 17C link carries run=1: the new window downloads and runs
    # the analysis on arrival, once; later reruns wait for the button as usual.
    state = {}
    assert app_module.auto_run_requested({"run": "1"}, state)
    assert not app_module.auto_run_requested({"run": "1"}, state)


def test_no_run_flag_no_automatic_download(app_module):
    assert not app_module.auto_run_requested({}, {})
    assert not app_module.auto_run_requested({"run": "yes"}, {})


def test_flow_frequency_page_defaults_to_a_log_y_axis():
    at = _app_with({})
    scale = next(r for r in at.sidebar.radio if r.label == "Y-Axis Scale")
    assert scale.value == "Log"
    scale.set_value("Per Plot").run()
    boxes = [c for c in at.sidebar.checkbox if c.label.startswith("Log: ")]
    assert len(boxes) == 5 and all(c.value for c in boxes)


def test_flow_frequency_results_show_the_stationarity_screen(app_module):
    """run_ffa's screen of the fitted peaks is drawn with the Bulletin 17C results."""
    source = " ".join(_source(app_module).split())
    block = source.split('with st.expander("Flood Frequency Results"')[0]
    assert 'gage_ui.stationarity_section(ffa_result["stationarity"])' in block


def _page_radio(at):
    return next(r for r in at.sidebar.radio if r.label == "Page")


def _gage_box(at):
    return next(t for t in at.sidebar.text_input if t.label == "USGS Gage Number")


def test_a_linked_site_survives_a_trip_to_the_ungaged_page():
    at = _app_with({"page": "gaged", "site": "12340500"})
    _page_radio(at).set_value("Ungaged site")
    at.run()
    _page_radio(at).set_value("Flow Frequency")
    at.run()
    assert not at.exception
    assert _gage_box(at).value == "12340500"


def test_a_typed_gage_number_survives_a_trip_to_the_ungaged_page():
    at = _app_with({})
    _gage_box(at).set_value("09380000")
    at.run()
    _page_radio(at).set_value("Ungaged site")
    at.run()
    _page_radio(at).set_value("Flow Frequency")
    at.run()
    assert not at.exception
    assert _gage_box(at).value == "09380000"


def test_choosing_a_page_puts_it_in_the_url():
    at = _app_with({"page": "gaged", "site": "12340500", "run": "1"})
    _page_radio(at).set_value("Ungaged site")
    at.run()
    assert not at.exception
    assert at.query_params["page"] == ["ungaged"]
    assert "site" not in at.query_params and "run" not in at.query_params


def test_a_link_to_a_page_moves_the_radio_after_a_hand_choice():
    # The gage page's "Back to the map" sets ?page=ungaged after the radio was used.
    at = _app_with({})
    _page_radio(at).set_value("Ungaged site")
    at.run()
    _page_radio(at).set_value("Flow Frequency")
    at.run()
    at.query_params["page"] = "ungaged"
    at.run()
    assert not at.exception
    assert _page_radio(at).value == "Ungaged site"
    assert any("Ungaged site" in h.value for h in at.header)


def test_back_from_a_gage_page_returns_to_the_ungaged_page(monkeypatch):
    import gage_ui

    monkeypatch.setattr(gage_ui, "render", lambda site: None)
    at = _app_with({})
    _page_radio(at).set_value("Ungaged site")
    at.run()
    at.query_params.clear()
    at.query_params["page"] = "gage"  # a gage popup on the map ...
    at.query_params["site"] = "12340500"
    at.run()
    at.query_params.clear()
    at.query_params["page"] = "ungaged"  # ... and "Back to the map"
    at.run()
    assert not at.exception
    assert _page_radio(at).value == "Ungaged site"
