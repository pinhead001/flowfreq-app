"""The gage page: one USGS streamgage at a glance, opened from the map's gage popups.

``?page=gage&site=NNNNNNNN`` lands here. The page shows the site (name, drainage area,
state, HUC, location), its periods of record for daily flow and annual peaks, a chart of
the annual peaks, and the ways on: Bulletin 17C on the Gaged page, the USGS pages, the
basin map. All data comes from the flowfreq library (:class:`flowfreq.usgs.USGSgage`);
this module only formats it.

:func:`load_site` and :func:`load_peaks` are the seams: cached, and they never raise, so
the page has one code path for failure. :func:`render` is the page.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import altair as alt
import pandas as pd
import streamlit as st
from flowfreq.usgs import USGSgage

logger = logging.getLogger(__name__)

#: How long a site's lookups are reused. Metadata and annual peaks change rarely.
CACHE_TTL_S = 6 * 3600

#: FIPS state codes to postal abbreviations: the Water Data API reports the former.
_FIPS = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP", "72": "PR", "78": "VI",
}  # fmt: skip


def state_abbrev(code: Optional[str]) -> str:
    """A postal abbreviation from a FIPS code (``"30"`` -> ``"MT"``) or an abbreviation."""
    if not code:
        return ""
    code = str(code).strip()
    return _FIPS.get(code.zfill(2), code.upper()) if code.isdigit() else code.upper()


def record_years(start: Optional[str], end: Optional[str]) -> Optional[float]:
    """Length of a period of record in years, from ``YYYY-MM-DD`` strings."""
    if not start or not end:
        return None
    return (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25


def summarize_peaks(peaks: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
    """First and last water year, count, and the largest peak of an annual peak record.

    Parameters
    ----------
    peaks : pandas.DataFrame, optional
        :meth:`flowfreq.usgs.USGSgage.download_peak_flow` output.

    Returns
    -------
    dict or None
        ``first``, ``last``, ``count``, ``max_cfs``, ``max_date`` (``YYYY-MM-DD``), or
        ``None`` for no record.
    """
    if peaks is None or peaks.empty:
        return None
    flows = peaks.dropna(subset=["peak_flow_cfs"])
    top = flows.loc[flows["peak_flow_cfs"].idxmax()] if not flows.empty else None
    return {
        "first": int(peaks["water_year"].min()),
        "last": int(peaks["water_year"].max()),
        "count": int(len(peaks)),
        "max_cfs": None if top is None else int(top["peak_flow_cfs"]),
        "max_date": None if top is None else pd.Timestamp(top["peak_date"]).strftime("%Y-%m-%d"),
    }


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def load_site(site_no: str) -> Dict[str, Any]:
    """The site's attributes and daily period of record. Never raises.

    Returns
    -------
    dict
        ``{"info": {...}}`` with ``site_no``, ``name``, ``drainage_area``, ``state``,
        ``huc``, ``lat``, ``lon``, ``daily_start``, ``daily_end``; or ``{"error": str}``.
    """
    try:
        gage = USGSgage(site_no)
        gage.fetch_site_info()
    except Exception as exc:  # noqa: BLE001 - the page must show a failure, never a traceback
        logger.warning("site lookup failed for %s: %s", site_no, exc)
        return {"error": f"Site lookup failed: {exc}"}
    if not gage.site_name and gage.daily_por_start is None and gage.latitude is None:
        return {"error": f"USGS has no monitoring location {site_no}."}
    return {
        "info": {
            "site_no": site_no,
            "name": gage.site_name or "",
            "drainage_area": gage.drainage_area,
            "state": gage.state_code,
            "huc": gage.huc,
            "lat": gage.latitude,
            "lon": gage.longitude,
            "daily_start": gage.daily_por_start,
            "daily_end": gage.daily_por_end,
        }
    }


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def load_peaks(site_no: str) -> Dict[str, Any]:
    """The site's annual peak flows. Never raises.

    Returns
    -------
    dict
        ``{"peaks": DataFrame}`` or ``{"error": str}``.
    """
    try:
        peaks = USGSgage(site_no).download_peak_flow()
    except Exception as exc:  # noqa: BLE001 - shown on the page, never a traceback
        logger.warning("peak download failed for %s: %s", site_no, exc)
        return {"error": f"Annual peaks could not be downloaded: {exc}"}
    if peaks is None or peaks.empty:
        return {"error": "USGS has no annual peak record for this site."}
    return {"peaks": peaks}


def _record_frame(info: Dict[str, Any], summary: Optional[Dict[str, Any]]) -> pd.DataFrame:
    daily_years = record_years(info.get("daily_start"), info.get("daily_end"))
    rows = [
        {
            "Record": "Daily mean flow",
            "From": info.get("daily_start") or "none",
            "To": info.get("daily_end") or "",
            "Length": f"{daily_years:.1f} years" if daily_years is not None else "",
            "Notes": "",
        }
    ]
    if summary is not None:
        largest = (
            f"largest {summary['max_cfs']:,} cfs on {summary['max_date']}"
            if summary["max_cfs"] is not None
            else ""
        )
        rows.append(
            {
                "Record": "Annual peaks",
                "From": f"WY {summary['first']}",
                "To": f"WY {summary['last']}",
                "Length": f"{summary['count']} peaks",
                "Notes": largest,
            }
        )
    return pd.DataFrame(rows).set_index("Record")


def peak_chart(peaks: pd.DataFrame) -> alt.Chart:
    """Annual peaks as bars on a numeric water-year axis, so gaps in the record show."""
    data = peaks.dropna(subset=["peak_flow_cfs"]).assign(
        peak_date=lambda d: pd.to_datetime(d["peak_date"]).dt.strftime("%Y-%m-%d"),
        qualification_code=lambda d: d["qualification_code"].astype("string").fillna(""),
    )
    return (
        alt.Chart(data)
        .mark_bar(size=3)
        .encode(
            x=alt.X("water_year:Q", title="Water year", axis=alt.Axis(format="d")),
            y=alt.Y("peak_flow_cfs:Q", title="Peak flow (cfs)"),
            tooltip=[
                alt.Tooltip("water_year:Q", title="Water year", format="d"),
                alt.Tooltip("peak_date:N", title="Date"),
                alt.Tooltip("peak_flow_cfs:Q", title="Peak (cfs)", format=","),
                alt.Tooltip("qualification_code:N", title="Codes"),
            ],
        )
        .properties(height=260)
    )


def _go(page: str, site_no: Optional[str] = None) -> None:
    # A button callback: switch page in this tab (a markdown link opens a new one).
    params = {"page": page}
    if site_no:
        params["site"] = site_no
    st.query_params.from_dict(params)


def _links(site_no: str) -> str:
    return (
        f"[USGS monitoring location](https://waterdata.usgs.gov/monitoring-location/{site_no}/)"
        f" \u00b7 [Annual peaks (NWIS)](https://nwis.waterdata.usgs.gov/nwis/peak?site_no={site_no})"
    )


def _actions(site_no: str, can_run: bool) -> None:
    col_run, col_links = st.columns([1, 2], vertical_alignment="center")
    col_run.button(
        "Run Bulletin 17C on this site",
        type="primary",
        disabled=not can_run,
        on_click=_go,
        args=("gaged", site_no),
        help="Opens the Gaged page with this site filled in.",
    )
    col_links.markdown(_links(site_no))


def render(site_no: str) -> None:
    """Draw the gage page for one validated site number."""
    st.button("\u2190 Back to the map", on_click=_go, args=("ungaged",), type="tertiary")
    with st.spinner(f"Looking up USGS {site_no}..."):
        site = load_site(site_no)
    if "error" in site:
        st.header(f"USGS {site_no}")
        st.error(site["error"])
        _actions(site_no, can_run=False)
        return
    info = site["info"]
    st.header(f"USGS {site_no} \u2014 {info['name']}" if info["name"] else f"USGS {site_no}")
    lat, lon = info.get("lat"), info.get("lon")
    if lat is not None and lon is not None:
        st.caption(f"{lat:.4f}, {lon:.4f}")

    area, state = info.get("drainage_area"), state_abbrev(info.get("state"))
    cols = st.columns(3)
    cols[0].metric("Drainage area", f"{area:,.0f} sq mi" if area else "unknown")
    cols[1].metric("State", state or "unknown")
    cols[2].metric("HUC", info.get("huc") or "unknown")

    with st.spinner("Downloading annual peaks..."):
        peaks = load_peaks(site_no)
    summary = summarize_peaks(peaks.get("peaks"))

    st.subheader("Period of record")
    st.table(_record_frame(info, summary))
    if "error" in peaks:
        st.warning(peaks["error"])
    else:
        st.subheader("Annual peak flows")
        st.altair_chart(peak_chart(peaks["peaks"]))
        st.caption(
            "Bars are the annual peaks as USGS reports them, before any qualification code "
            "is applied. Bulletin 17C, with peak codes, low-outlier tests and skew, is on the "
            "Gaged page."
        )

    _actions(site_no, can_run=True)
    with st.expander("Coming to this page"):
        st.markdown(
            "- Summary hydrograph and flow-duration curve from the daily record\n"
            "- Raster hydrograph (day of year by year)\n"
            "- The Bulletin 17C frequency curve in place, without leaving the page\n"
            "- Direct data downloads (daily values, peaks, site metadata)"
        )
