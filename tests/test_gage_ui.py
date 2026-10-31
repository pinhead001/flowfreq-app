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


def test_load_site_never_raises(monkeypatch):
    class Broken:
        def __init__(self, site):
            raise RuntimeError("API down")

    monkeypatch.setattr(gage_ui, "USGSgage", Broken)
    out = (
        gage_ui.load_site.__wrapped__(SITE)
        if hasattr(gage_ui.load_site, "__wrapped__")
        else (gage_ui.load_site(SITE))
    )
    assert "error" in out and "API down" in out["error"]


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
    [b for b in at.button if b.label == "Run Bulletin 17C on this site"][0].click()
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
