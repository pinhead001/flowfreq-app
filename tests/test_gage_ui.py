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


@pytest.fixture
def fake_gage(monkeypatch):
    monkeypatch.setattr(gage_ui, "USGSgage", _FakeGage)
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
    fake_gage.mode = "ok"
    assert gage_ui.load_site(SITE)["info"]["name"] == "Clark Fork"
    assert "peaks" in gage_ui.load_peaks(SITE)


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


def _run(monkeypatch, info=INFO, peaks=PEAKS):
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


def test_b17c_button_opens_the_gaged_page_in_the_same_tab(monkeypatch):
    at = _run(monkeypatch)
    [b for b in at.button if b.label.startswith("Open in Bulletin 17C")][0].click()
    at.run()
    assert at.query_params["page"] == ["gaged"] or at.query_params["page"] == "gaged"
    assert SITE in str(at.query_params["site"])


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


def test_b17c_button_is_disabled_without_peaks(monkeypatch):
    at = _run(monkeypatch, peaks=None)
    button = [b for b in at.button if b.label.startswith("Open in Bulletin 17C")][0]
    assert button.disabled
