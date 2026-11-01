"""Tests for the gage page (``gage_ui``). The library calls are monkeypatched: these check
how the page shows a site, its periods of record and its links, not the USGS services."""

from __future__ import annotations

import logging

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="Streamlit not installed")

from streamlit.testing.v1 import AppTest

import gage_ui

logging.getLogger("streamlit.runtime.scriptrunner_utils.script_run_context").setLevel(logging.ERROR)

SITE = "12340500"
INFO = {
    "site_no": SITE,
    "name": "Clark Fork above Missoula MT",
    "drainage_area": 6021.0,
    "state": "30",
    "huc": "170102040104",
    "lat": 46.8767638888889,
    "lon": -113.932119444444,
    "daily_start": "1929-03-01",
    "daily_end": "2026-10-29",
}
PEAKS = pd.DataFrame(
    {
        "water_year": [1908, 1930, 2018],
        "peak_date": pd.to_datetime(["1908-06-01", "1930-04-28", "2018-05-10"]),
        "peak_flow_cfs": [48000, 9200, 19100],
        "qualification_code": ["2,7", "", ""],
    }
)

DAILY = pd.DataFrame(
    {
        "flow_cfs": [1850.0, 0.0, 2100.0, 2400.0],
        # flowfreq.waterdata.download_daily: approval (A/P), then qualifiers (e = estimated).
        "qualification_code": ["A", "A:e", "P", "P"],
    },
    index=pd.DatetimeIndex(
        ["1929-03-01", "1929-03-02", "1929-03-03", "1929-03-06"], name="date"
    ),  # 1929-03-04 and -05 missing: a gap
)


def test_state_abbreviation_from_fips_or_code():
    assert gage_ui.state_abbrev("30") == "MT"
    assert gage_ui.state_abbrev("72") == "PR"
    assert gage_ui.state_abbrev("MT") == "MT"
    assert gage_ui.state_abbrev(None) == ""


def test_summarize_peaks():
    s = gage_ui.summarize_peaks(PEAKS)
    assert (s["first"], s["last"], s["count"]) == (1908, 2018, 3)
    assert (s["max_cfs"], s["max_date"]) == (48000, "1908-06-01")


def test_summarize_no_peaks_is_none():
    assert gage_ui.summarize_peaks(PEAKS.iloc[0:0]) is None
    assert gage_ui.summarize_peaks(None) is None


def test_record_years():
    assert gage_ui.record_years("1929-03-01", "2026-10-29") == pytest.approx(97.7, abs=0.1)
    assert gage_ui.record_years(None, "2026-10-29") is None


class _FakeGage:
    """Stands in for USGSgage: ``mode`` is "ok", "empty" (no such site) or "down"."""

    mode = "ok"

    def __init__(self, site):
        self.site_no = site
        self.site_name = self.drainage_area = self.state_code = self.huc = None
        self.latitude = self.longitude = self.daily_por_start = self.daily_por_end = None
        self._last_api_error = None

    def fetch_site_info(self):
        if _FakeGage.mode == "ok":
            self.site_name, self.latitude, self.longitude = "Clark Fork", 46.9, -113.9
        elif _FakeGage.mode == "down":
            # The library logs a failed request instead of raising it.
            self._last_api_error = "HTTPSConnectionPool(host='api.waterdata.usgs.gov'): Max retries"

    def download_peak_flow(self):
        if _FakeGage.mode == "down":
            raise ConnectionError("HTTPSConnectionPool(host='api.waterdata.usgs.gov'): Max retries")
        return PEAKS


def _fake_download_daily(site):
    """Stands in for flowfreq.waterdata.download_daily, which keeps the approval codes."""
    if _FakeGage.mode == "down":
        raise ConnectionError("HTTPSConnectionPool(host='api.waterdata.usgs.gov'): Max retries")
    return DAILY


@pytest.fixture
def fake_gage(monkeypatch):
    monkeypatch.setattr(gage_ui, "USGSgage", _FakeGage)
    monkeypatch.setattr(gage_ui, "download_daily", _fake_download_daily)
    gage_ui.clear_caches()
    _FakeGage.mode = "ok"
    yield _FakeGage
    gage_ui.clear_caches()


def test_load_site_never_raises(monkeypatch):
    class Broken:
        def __init__(self, site):
            raise RuntimeError("API down")

    monkeypatch.setattr(gage_ui, "USGSgage", Broken)
    gage_ui.clear_caches()
    out = gage_ui.load_site(SITE)
    assert "error" in out


def test_unreachable_usgs_is_not_called_a_missing_site(fake_gage):
    fake_gage.mode = "down"
    out = gage_ui.load_site(SITE)
    assert out.get("kind") == "unreachable"
    assert "no monitoring location" not in out["error"]
    assert "HTTPSConnectionPool" not in out["error"]  # the detail goes to the log


def test_a_failure_is_not_cached(fake_gage):
    fake_gage.mode = "down"
    assert "error" in gage_ui.load_site(SITE)
    assert "error" in gage_ui.load_peaks(SITE)
    assert "error" in gage_ui.load_daily(SITE)
    fake_gage.mode = "ok"
    assert gage_ui.load_site(SITE)["info"]["name"] == "Clark Fork"
    assert "peaks" in gage_ui.load_peaks(SITE)
    assert len(gage_ui.load_daily(SITE)["daily"]) == 4


def test_an_unknown_site_says_so(fake_gage):
    fake_gage.mode = "empty"
    out = gage_ui.load_site(SITE)
    assert out.get("kind") == "missing" and "no monitoring location" in out["error"]


def test_summarize_peaks_tolerates_a_missing_date():
    odd = PEAKS.assign(peak_date=[pd.NaT, PEAKS["peak_date"][1], PEAKS["peak_date"][2]])
    assert gage_ui.summarize_peaks(odd)["max_date"] is None


def test_peak_chart_colours_bars_by_qualification():
    spec = gage_ui.peak_chart(PEAKS).to_dict()
    assert spec["encoding"]["color"]["field"] == "kind"
    kinds = {row["kind"] for row in spec["datasets"][next(iter(spec["datasets"]))]}
    assert "Historic (code 7)" in kinds and "No code" in kinds


def _page():
    import gage_ui as page

    page.render("12340500")


def _run(monkeypatch, info=INFO, peaks=PEAKS, daily=DAILY):
    monkeypatch.setattr(
        gage_ui,
        "load_site",
        lambda site: {"info": info} if info else {"error": "Site lookup failed: API down"},
    )
    monkeypatch.setattr(
        gage_ui,
        "load_peaks",
        lambda site: {"peaks": peaks} if peaks is not None else {"error": "no peaks"},
    )
    monkeypatch.setattr(
        gage_ui,
        "load_daily",
        lambda site: {"daily": daily} if daily is not None else {"error": "no daily values"},
    )
    return AppTest.from_function(_page, default_timeout=30).run()


def test_page_shows_the_site(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    assert any(SITE in h.value and "Clark Fork above Missoula" in h.value for h in at.header)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Drainage area"] == "6,021 sq mi"
    assert metrics["State"] == "MT"
    assert metrics["HUC"] == "170102040104"
    assert any("46.8768, -113.9321" in c.value for c in at.caption)  # not squeezed into a metric


def test_page_shows_periods_of_record(monkeypatch):
    at = _run(monkeypatch)
    table = at.table[0].value if at.table else at.dataframe[0].value
    text = table.to_string()
    assert "1929-03-01" in text and "2026-10-29" in text
    assert "1908" in text and "2018" in text and "48,000" in text


def test_page_links_to_usgs(monkeypatch):
    at = _run(monkeypatch)
    md = " ".join(m.value for m in at.markdown)
    assert f"https://waterdata.usgs.gov/monitoring-location/{SITE}/" in md


def _b17c(at):
    links = [
        e.proto for e in at.get("link_button") if e.proto.label.startswith("Open in Bulletin 17C")
    ]
    assert len(links) == 1
    return links[0]


def test_b17c_link_opens_the_gaged_page_in_a_new_window(monkeypatch):
    # A link button (target _blank), so the gage page stays open beside the analysis. The
    # new window is a new session: the site travels in the URL, not in session state.
    link = _b17c(_run(monkeypatch))
    assert link.url == f"?page=flowfrequency&site={SITE}&run=1"  # and run it on arrival
    assert not link.disabled


def test_back_button_returns_to_the_map(monkeypatch):
    at = _run(monkeypatch)
    [b for b in at.button if "Back to the map" in b.label][0].click()
    at.run()
    assert "ungaged" in str(at.query_params["page"])


def test_peak_chart_spaces_years_by_value():
    chart = gage_ui.peak_chart(PEAKS)
    spec = chart.to_dict()
    assert spec["encoding"]["x"]["type"] == "quantitative"  # 1908 to 1930 is a gap, not a step


def test_page_reports_a_failed_lookup(monkeypatch):
    at = _run(monkeypatch, info=None)
    assert not at.exception
    assert any("API down" in e.value for e in at.error)


def test_page_without_peaks_still_shows_the_site(monkeypatch):
    at = _run(monkeypatch, peaks=None)
    assert not at.exception
    assert any("Clark Fork" in h.value for h in at.header)
    assert any("no peaks" in w.value for w in at.warning)


def test_b17c_link_is_disabled_without_peaks(monkeypatch):
    assert _b17c(_run(monkeypatch, peaks=None)).disabled


def _charts(at):
    return [e for e in at.main.children.values() if getattr(e, "type", "") == "vega_lite_chart"]


def test_page_plots_the_daily_record(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    assert any("Daily mean flow" in h.value for h in at.subheader)
    assert len(_charts(at)) == 1  # annual peaks
    # The daily record, in the resizable-brush component (vega_component).
    assert len(at.get("component_instance")) == 1


def test_page_without_daily_values_says_so(monkeypatch):
    at = _run(monkeypatch, daily=None)
    assert not at.exception
    assert any("no daily values" in w.value for w in at.warning)
    assert len(_charts(at)) == 1  # the peaks still plot


def _views(spec):
    detail, overview = spec["vconcat"]
    return detail, overview


def _param(spec, name):
    return next(p for p in spec["params"] if p["name"] == name)


def _mark(view):
    mark = view["mark"]
    return mark if isinstance(mark, str) else mark["type"]


def _layers(spec):
    detail, _ = _views(spec)
    return detail["layer"]


def _line(spec):
    return next(v for v in _layers(spec) if _mark(v) == "line")


def _rows(spec, view, parent=None):
    data = view.get("data") or (parent or {}).get("data")
    return spec["datasets"][data["name"]]


def test_daily_chart_zooms_the_detail_to_the_brushed_period():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    detail, overview = _views(spec)
    brush = _param(spec, "period")  # Altair hoists it, naming the view it is drawn on
    assert brush["views"] == [overview["name"]]  # brushed on the strip
    assert brush["select"]["type"] == "interval"
    assert brush["select"]["encodings"] == ["x"]  # a period of time, not a box
    x = _line(spec)["encoding"]["x"]
    # The brushed period when there is one, else the whole record (or a quick period):
    # Streamlit drops a selection's starting value, so the fallback lives in the domain.
    domain = x["scale"]["domain"]["expr"]
    assert domain.startswith("period.date ? period.date : ")
    first, last = (int(pd.Timestamp(d).value // 10**6) for d in ("1929-03-01", "1929-03-06"))
    assert domain.endswith(f"[{first}, {last}]")
    assert x["type"] == "temporal"
    # Zoomed in, Vega's default ticks read "April", "October": say which year.
    assert x["axis"]["format"] == "%b %Y"
    assert all(v["mark"].get("clip") for v in _layers(spec))  # nothing drawn past the axes


def test_daily_chart_shows_gaps_in_the_record():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    detail, _ = _views(spec)
    rows = _rows(spec, _line(spec), detail)
    assert len(rows) == 6  # 1929-03-01 .. 03-06, the missing days as nulls: the line breaks
    assert sum(r["flow_cfs"] is None for r in rows) == 2


def test_log_and_linear_switch_in_the_browser_keeping_the_zoom():
    # The switch is a chart parameter, not a Streamlit widget: a widget reruns the script
    # and redraws the chart, which drops the zoomed period.
    spec = gage_ui.daily_chart(DAILY).to_dict()
    scale = _param(spec, "flowscale")
    assert scale["bind"]["input"] == "radio" and scale["bind"]["options"] == ["log", "linear"]
    assert scale["value"] == "log"
    linear = gage_ui.daily_chart(DAILY, log=False).to_dict()
    assert _param(linear, "flowscale")["value"] == "linear"


def test_log_values_leave_out_zero_flows():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    detail, _ = _views(spec)
    rows = {
        r["date"][:10]: r for r in _rows(spec, _line(spec), detail) if r["flow_cfs"] is not None
    }
    assert rows["1929-03-02"]["flow_cfs"] == 0  # drawn on the linear scale
    assert rows["1929-03-02"]["log_flow"] is None  # a log axis cannot place it
    assert rows["1929-03-01"]["log_flow"] == pytest.approx(3.2672, abs=1e-4)  # log10(1850)


def test_the_strip_stays_linear():
    # An area fills down to zero, which a log axis does not have.
    _, overview = _views(gage_ui.daily_chart(DAILY).to_dict())
    assert overview["encoding"]["y"].get("scale", {}).get("type", "linear") == "linear"


def test_hovering_reads_out_the_date_and_flow():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    hover = _param(spec, "hover")
    assert hover["select"]["nearest"] is True
    assert hover["select"]["encodings"] == ["x"]
    readout = [v for v in _layers(spec) if _mark(v) == "text"]
    assert len(readout) == 1
    calc = " ".join(str(t) for t in readout[0].get("transform", []))
    assert "flow_cfs" in calc and "cfs" in calc  # the real flow, not its logarithm


PEAKS_IN_RECORD = pd.DataFrame(
    {
        "water_year": [1908, 1929],
        "peak_date": pd.to_datetime(["1908-06-01", "1929-03-03"]),
        "peak_flow_cfs": [48000, 2500],
        "qualification_code": ["7", ""],
    }
)


def _dots(spec):
    return [v for v in _layers(spec) if _mark(v) == "point" and v["mark"].get("filled")]


def test_annual_peaks_are_dots_on_the_daily_record():
    spec = gage_ui.daily_chart(DAILY, peaks=PEAKS_IN_RECORD).to_dict()
    (dots,) = _dots(spec)
    # Only the peaks inside the daily record: the two views must share one time axis.
    assert [r["flow_cfs"] for r in _rows(spec, dots)] == [2500]


def test_no_peaks_no_dots():
    assert not _dots(gage_ui.daily_chart(DAILY, peaks=None).to_dict())


def test_water_year_lines_show_only_when_zoomed():
    daily = pd.DataFrame(
        {"flow_cfs": 1.0}, index=pd.date_range("2019-07-01", "2022-02-01", name="date")
    )
    spec = gage_ui.daily_chart(daily).to_dict()
    (rules,) = [v for v in _layers(spec) if _mark(v) == "rule" and v["mark"].get("strokeDash")]
    dates = [r["date"][:10] for r in _rows(spec, rules)]
    assert dates == ["2019-10-01", "2020-10-01", "2021-10-01"]
    # Shown while the visible span is under 15 years: across a century they are a blur.
    opacity = rules["mark"]["opacity"]["expr"]
    assert "period.date" in opacity and str(15 * 365.25 * 86400000) in opacity


@pytest.mark.parametrize(
    "choice, end, expected",
    [
        ("Whole record", "2026-10-30", None),
        ("Last 10 years", "2026-10-30", ("2016-10-30", "2026-10-30")),
        ("Last water year", "2026-10-30", ("2025-10-01", "2026-09-30")),
        ("Last water year", "2026-09-30", ("2025-10-01", "2026-09-30")),
        ("Last water year", "2026-09-29", ("2024-10-01", "2025-09-30")),
    ],
)
def test_quick_periods(choice, end, expected):
    got = gage_ui.period_window(choice, pd.Timestamp("1929-03-01"), pd.Timestamp(end))
    want = None if expected is None else tuple(pd.Timestamp(d) for d in expected)
    assert got == want


def test_a_quick_period_never_starts_before_the_record():
    start, end = pd.Timestamp("2020-01-01"), pd.Timestamp("2026-10-30")
    assert gage_ui.period_window("Last 10 years", start, end) == (start, end)


def test_a_quick_period_opens_the_chart_zoomed():
    window = (pd.Timestamp("1929-03-02"), pd.Timestamp("1929-03-04"))
    spec = gage_ui.daily_chart(DAILY, period=window).to_dict()
    domain = _line(spec)["encoding"]["x"]["scale"]["domain"]["expr"]
    first, last = (int(t.value // 10**6) for t in window)
    assert domain.endswith(f"[{first}, {last}]")
    # ... and as a box on the strip, whose ends can then be dragged.
    start, end = _param(spec, "period")["value"]["x"]
    assert (start["year"], start["month"], start["date"]) == (1929, 3, 2)
    assert (end["year"], end["month"], end["date"]) == (1929, 3, 4)


def test_without_a_quick_period_the_strip_starts_with_no_box():
    assert "value" not in _param(gage_ui.daily_chart(DAILY).to_dict(), "period")


def test_the_daily_chart_is_drawn_with_resizable_period_grips(monkeypatch):
    seen = {}
    monkeypatch.setattr(gage_ui, "vega_chart", lambda chart, **kw: seen.update(kw, chart=chart))
    gage_ui._daily_section({"daily": DAILY}, None)
    assert seen["resizable"] == ["period"]
    assert _param(seen["chart"].to_dict(), "period")["select"]["type"] == "interval"


def test_csv_of_the_daily_values():
    lines = gage_ui.daily_csv(DAILY).splitlines()
    assert lines[0] == "date,flow_cfs,qualification_code"
    assert lines[1] == "1929-03-01,1850.0,A"
    plain = gage_ui.daily_csv(DAILY[["flow_cfs"]]).splitlines()
    assert plain[0] == "date,flow_cfs"


def test_page_offers_the_data_as_csv(monkeypatch):
    labels = [e.proto.label for e in _run(monkeypatch).get("download_button")]
    assert any("Daily values" in x for x in labels) and any("Annual peaks" in x for x in labels)


def test_page_has_quick_periods_and_no_rerunning_log_toggle(monkeypatch):
    at = _run(monkeypatch)
    assert not at.toggle  # the log switch lives in the chart
    (periods,) = at.get("button_group")
    assert "Last 10 years" in str(periods.proto)


def test_site_daily_and_peaks_load_in_parallel(monkeypatch):
    import time

    def slow(result):
        def load(site):
            time.sleep(0.4)
            return result

        return load

    monkeypatch.setattr(gage_ui, "load_site", slow({"info": INFO}))
    monkeypatch.setattr(gage_ui, "load_peaks", slow({"peaks": PEAKS}))
    monkeypatch.setattr(gage_ui, "load_daily", slow({"daily": DAILY}))
    started = time.perf_counter()
    got = gage_ui.load_all(SITE)
    assert time.perf_counter() - started < 0.9  # one after another is 1.2 s
    assert set(got) == {"site", "peaks", "daily"} and got["site"]["info"] is INFO


def test_daily_chart_fits_the_page_width():
    # Streamlit gives a vconcat holding a layer autosize "pad", which lays the axes on top
    # of the container width and overflows the page by their width. fit-x keeps it inside.
    spec = gage_ui.daily_chart(DAILY).to_dict()
    assert spec["autosize"] == {"type": "fit-x", "contains": "padding"}


def test_only_the_peak_dots_carry_a_tooltip():
    # Streamlit turns Vega's default tooltip on for every mark: on the hover points it shows
    # the plotted value, which on the log axis is log10 of the flow. The readout says it.
    spec = gage_ui.daily_chart(DAILY, peaks=PEAKS_IN_RECORD).to_dict()
    _, overview = _views(spec)
    for view in _layers(spec) + [overview]:
        if "tooltip" not in view.get("encoding", {}):
            assert view["mark"].get("tooltip") is False, view["mark"]


def test_the_flow_axis_fits_the_period_in_view():
    # Only the days in view reach the line, so a zoomed year is not drawn against the
    # whole record's range of flows (and the browser draws less).
    spec = gage_ui.daily_chart(DAILY, peaks=PEAKS_IN_RECORD).to_dict()
    for view in (_line(spec), _dots(spec)[0]):
        filters = [t["filter"] for t in view.get("transform", []) if "filter" in t]
        assert any("inrange(datum.date, period.date ? period.date" in str(f) for f in filters)


@pytest.mark.parametrize(
    "code, note",
    [
        ("A", ""),
        ("P", "provisional"),
        ("A:e", "estimated"),
        ("P:e", "provisional, estimated"),
        ("A:e:ICE", "estimated, ice"),
        ("A:BACKWATER:e", "backwater, estimated"),
        (None, ""),
    ],
)
def test_status_notes_for_the_readout(code, note):
    assert gage_ui.status_note(code) == note


def test_provisional_days_are_drawn_apart():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    detail, _ = _views(spec)
    rows = {r["date"][:10]: r for r in _rows(spec, _line(spec), detail)}
    assert rows["1929-03-03"]["provisional"] is True
    assert rows["1929-03-01"]["provisional"] is False
    assert rows["1929-03-02"]["note"] == "estimated"
    lines = [v for v in _layers(spec) if _mark(v) == "line"]
    assert len(lines) == 2  # the record, and the provisional days over it
    assert lines[1]["mark"]["color"] != lines[0]["mark"]["color"]


def test_the_readout_carries_the_status():
    spec = gage_ui.daily_chart(DAILY).to_dict()
    (readout,) = [v for v in _layers(spec) if _mark(v) == "text"]
    assert "datum.note" in " ".join(str(t) for t in readout.get("transform", []))


def test_a_record_without_codes_still_draws():
    spec = gage_ui.daily_chart(DAILY[["flow_cfs"]]).to_dict()
    assert len([v for v in _layers(spec) if _mark(v) == "line"]) == 1


def test_the_readout_sits_in_a_fixed_corner():
    # Beside the pointer it is cut off at the right edge; a corner keeps it whole.
    spec = gage_ui.daily_chart(DAILY).to_dict()
    (readout,) = [v for v in _layers(spec) if _mark(v) == "text"]
    assert "value" in readout["encoding"]["x"] and "value" in readout["encoding"]["y"]


_YEARS = list(range(1960, 2000))
_WIGGLE = [1.00, 1.08, 0.93, 1.05, 0.97, 1.11, 0.90, 1.03, 0.95, 1.07]
STEPPED = pd.DataFrame(  # a dam in 1980: peaks fall to a third
    {
        "water_year": _YEARS,
        "peak_date": pd.to_datetime([f"{y}-05-15" for y in _YEARS]),
        "peak_flow_cfs": [
            (12000 if y < 1980 else 4000) * _WIGGLE[i % 10] for i, y in enumerate(_YEARS)
        ],
        "qualification_code": ["" if y < 1980 else "6" for y in _YEARS],
    }
)
STATIONARY = STEPPED.assign(
    peak_flow_cfs=[12000 * _WIGGLE[(i * 7) % 10] for i in range(len(_YEARS))],
    qualification_code="",
)


def test_screen_flags_a_stepped_record():
    screen = gage_ui.screen_peaks(STEPPED)
    assert any("change point in 19" in f for f in screen["flags"])
    assert any("peak code 5/6" in f for f in screen["flags"])  # the codes reach the screen
    assert gage_ui.change_year(screen) in range(1978, 1983)


def test_screen_of_a_stationary_record_has_no_flags():
    screen = gage_ui.screen_peaks(STATIONARY)
    assert screen["flags"] == []
    assert gage_ui.change_year(screen) is None


def test_screen_of_a_short_record_says_why_and_never_raises():
    screen = gage_ui.screen_peaks(PEAKS)
    assert "10" in screen["error"]
    assert gage_ui.change_year(screen) is None


def test_screen_tolerates_zero_and_missing_peaks():
    peaks = STATIONARY.copy()
    peaks.loc[3, "peak_flow_cfs"] = 0.0
    peaks.loc[5, "peak_flow_cfs"] = float("nan")
    assert "flags" in gage_ui.screen_peaks(peaks)  # tested in linear units, not refused


def test_peak_chart_marks_the_change_point():
    spec = gage_ui.peak_chart(STEPPED, change_year=1980).to_dict()
    marks = [layer["mark"]["type"] for layer in spec["layer"]]
    assert "rule" in marks and "text" in marks
    rule = spec["layer"][marks.index("rule")]
    assert rule["encoding"]["x"]["datum"] == 1980


def test_peak_chart_without_a_change_point_has_no_marker():
    assert "layer" not in gage_ui.peak_chart(STEPPED).to_dict()


def test_page_shows_the_stationarity_flags(monkeypatch):
    at = _run(monkeypatch, peaks=STEPPED)
    assert not at.exception
    flagged = [w.value for w in at.warning if "Stationarity screen" in w.value]
    assert flagged and "Change point in 19" in flagged[0]
    assert any("does not change" in c.value for c in at.caption)


def test_page_says_when_the_record_screens_clean(monkeypatch):
    at = _run(monkeypatch, peaks=STATIONARY)
    assert not at.exception
    assert any(
        "no significant trend" in c.value and "40 annual peaks, 1960–1999" in c.value
        for c in at.caption
    )


def test_page_says_why_a_short_record_was_not_screened(monkeypatch):
    at = _run(monkeypatch)
    assert not at.exception
    assert any("Stationarity screen not run" in c.value for c in at.caption)


def test_axis_reads_months_over_a_year_and_water_years_over_a_decade():
    daily = pd.DataFrame(
        {"flow_cfs": 1.0}, index=pd.date_range("2019-07-01", "2022-02-01", name="date")
    )
    axis = _line(gage_ui.daily_chart(daily).to_dict())["encoding"]["x"]["axis"]
    values, label = axis["values"]["expr"], axis["labelExpr"]
    two_years, fifteen = str(2 * 365.25 * 86400000), str(15 * 365.25 * 86400000)
    assert two_years in values and fifteen in values  # chosen by the span in view
    assert "period.date" in values
    # Ticks are local midnights, built in the browser, as Vega reads the dates and the
    # brush works in local time: a UTC tick at Oct 1 falls outside a brushed water year.
    assert "datetime(2020, 10, 1)" in values  # 1 November 2020: month starts, up to two years
    assert "datetime(2021, 3, 1)" in values  # 1 April 2021: mid water year, up to fifteen
    assert "timeFormat(datum.value, '%b')" in label  # "Oct", "Nov" ...
    assert "timeFormat(datum.value, '%b %Y')" in label  # ... "Jan 2021"
    assert "'WY ' + year(datum.value)" in label  # April 1 2021 is in WY 2021
    assert "utc" not in label + values
    assert label.endswith("datum.label")  # longer spans keep the "%b %Y" format
    assert two_years in axis["gridOpacity"]["expr"]  # no grid line mid water year


def test_stationarity_section_is_shared_with_the_gaged_page():
    assert callable(gage_ui.stationarity_section)
