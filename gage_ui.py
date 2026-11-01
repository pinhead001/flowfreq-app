"""The gage page: one USGS streamgage at a glance, opened from the map's gage popups.

``?page=gage&site=NNNNNNNN`` lands here. The page shows the site (name, drainage area,
state, HUC, location), its periods of record for daily flow and annual peaks, the daily
record (zoomable to a period of interest) and the annual peaks as charts, a stationarity
screen of the peaks, and the ways on: Bulletin 17C on the Flow Frequency page (in a new window),
the USGS pages, the basin map. All
data comes from the flowfreq library (:class:`flowfreq.usgs.USGSgage`);
this module only formats it.

:func:`load_site`, :func:`load_peaks` and :func:`load_daily` are the seams: cached, and they never raise, so
the page has one code path for failure. :func:`render` is the page.
"""

from __future__ import annotations

import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from flowfreq.hydrograph import Hydrograph
from flowfreq.regime import flow_duration_curve
from flowfreq.stationarity import (
    POT_LOW_QUANTILE,
    pot_counts,
    stationarity_report,
    stationarity_screen,
)
from flowfreq.usgs import USGSgage
from flowfreq.waterdata import download_daily
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from vega_component import vega_chart

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
        "max_date": (
            pd.Timestamp(top["peak_date"]).strftime("%Y-%m-%d")
            if top is not None and pd.notna(top["peak_date"])
            else None
        ),
    }


class _Unreachable(Exception):
    """USGS could not be reached; raised inside the cached fetchers so it is never cached."""


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _fetch_site(site_no: str) -> Dict[str, Any]:
    gage = USGSgage(site_no)
    gage.fetch_site_info()
    # fetch_site_info logs a failed request instead of raising it.
    failure = getattr(gage, "_last_api_error", None)
    found = gage.site_name or gage.daily_por_start is not None or gage.latitude is not None
    if failure and not found:
        raise _Unreachable(failure)
    if not found:
        return {}
    return {
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


@st.cache_data(ttl=CACHE_TTL_S, show_spinner=False)
def _fetch_peaks(site_no: str) -> Optional[pd.DataFrame]:
    return USGSgage(site_no).download_peak_flow()


#: Daily records kept at once: a century of daily values is about 0.6 MB.
_DAILY_ENTRIES = 32


@st.cache_data(ttl=CACHE_TTL_S, max_entries=_DAILY_ENTRIES, show_spinner=False)
def _fetch_daily(site_no: str) -> Optional[pd.DataFrame]:
    # waterdata.download_daily, not USGSgage.download_daily_flow: the same values, with
    # each day's approval and qualifiers kept (qualification_code), so the chart can tell
    # provisional days apart.
    return download_daily(site_no)


def clear_caches() -> None:
    """Forget every cached lookup (tests; and a user's explicit retry)."""
    _fetch_site.clear()
    _fetch_peaks.clear()
    _fetch_daily.clear()


def load_site(site_no: str) -> Dict[str, Any]:
    """The site's attributes and daily period of record. Never raises.

    Answers are cached for :data:`CACHE_TTL_S`; failures are not, so a passing outage
    is retried on the next view.

    Returns
    -------
    dict
        ``{"info": {...}}`` with ``site_no``, ``name``, ``drainage_area``, ``state``,
        ``huc``, ``lat``, ``lon``, ``daily_start``, ``daily_end``; or ``{"error": str,
        "kind": "missing" | "unreachable"}``.
    """
    try:
        info = _fetch_site(site_no)
    except Exception as exc:  # noqa: BLE001 - the page must show a failure, never a traceback
        logger.warning("site lookup failed for %s: %s", site_no, exc)
        return {
            "error": "USGS could not be reached just now. Try again in a minute.",
            "kind": "unreachable",
        }
    if not info:
        return {"error": f"USGS has no monitoring location {site_no}.", "kind": "missing"}
    return {"info": info}


def load_peaks(site_no: str) -> Dict[str, Any]:
    """The site's annual peak flows. Never raises; failures are not cached.

    Returns
    -------
    dict
        ``{"peaks": DataFrame}`` or ``{"error": str}``.
    """
    try:
        peaks = _fetch_peaks(site_no)
    except Exception as exc:  # noqa: BLE001 - shown on the page, never a traceback
        logger.warning("peak download failed for %s: %s", site_no, exc)
        return {"error": "Annual peaks could not be downloaded just now. Try again in a minute."}
    if peaks is None or peaks.empty:
        return {"error": "USGS has no annual peak record for this site."}
    return {"peaks": peaks}


def load_daily(site_no: str) -> Dict[str, Any]:
    """The site's full daily mean flow record. Never raises; failures are not cached.

    Returns
    -------
    dict
        ``{"daily": DataFrame}`` (``flow_cfs`` indexed by ``date``) or ``{"error": str}``.
    """
    try:
        daily = _fetch_daily(site_no)
    except Exception as exc:  # noqa: BLE001 - shown on the page, never a traceback
        logger.warning("daily download failed for %s: %s", site_no, exc)
        return {"error": "Daily values could not be downloaded just now. Try again in a minute."}
    if daily is None or daily.empty:
        return {"error": "USGS has no daily values for this site."}
    return {"daily": daily}


def load_all(site_no: str) -> Dict[str, Dict[str, Any]]:
    """:func:`load_site`, :func:`load_peaks` and :func:`load_daily` at once, in threads:
    the page waits for the slowest of the three, not their sum. Never raises.

    Returns
    -------
    dict
        ``{"site": ..., "peaks": ..., "daily": ...}``, each that loader's answer.
    """
    loaders = {"site": load_site, "peaks": load_peaks, "daily": load_daily}
    ctx = get_script_run_ctx()

    def run(load: Any) -> Dict[str, Any]:
        if ctx is not None:  # the cached fetchers expect the page's script context
            add_script_run_ctx(threading.current_thread(), ctx)
        return load(site_no)

    with ThreadPoolExecutor(max_workers=len(loaders)) as pool:
        futures = {name: pool.submit(run, load) for name, load in loaders.items()}
        return {name: future.result() for name, future in futures.items()}


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
            f"largest {summary['max_cfs']:,} cfs"
            + (f" on {summary['max_date']}" if summary["max_date"] else "")
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


def peak_chart(peaks: pd.DataFrame, change_year: Optional[int] = None) -> alt.Chart:
    """Annual peaks as bars on a numeric water-year axis, so gaps in the record show.

    A ``change_year`` (from :func:`change_year`) draws a dashed line there, labelled.
    """
    data = peaks.dropna(subset=["peak_flow_cfs"]).assign(
        peak_date=lambda d: pd.to_datetime(d["peak_date"]).dt.strftime("%Y-%m-%d").fillna(""),
        qualification_code=lambda d: d["qualification_code"].astype("string").fillna(""),
    )
    data["kind"] = data["qualification_code"].map(peak_kind)
    bars = (
        alt.Chart(data)
        .mark_bar(size=3)
        .encode(
            x=alt.X("water_year:Q", title="Water year", axis=alt.Axis(format="d")),
            y=alt.Y("peak_flow_cfs:Q", title="Peak flow (cfs)"),
            color=alt.Color(
                "kind:N",
                title=None,
                scale=alt.Scale(domain=list(PEAK_KINDS), range=list(PEAK_KINDS.values())),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("water_year:Q", title="Water year", format="d"),
                alt.Tooltip("peak_date:N", title="Date"),
                alt.Tooltip("peak_flow_cfs:Q", title="Peak (cfs)", format=","),
                alt.Tooltip("qualification_code:N", title="Codes"),
            ],
        )
        .properties(height=260)
    )
    if change_year is None:
        return bars
    marker = alt.Chart(pd.DataFrame({"x": [0]}))
    rule = marker.mark_rule(color="#444", strokeDash=[6, 4]).encode(x=alt.datum(change_year))
    label = marker.mark_text(align="left", dx=4, y=8, baseline="top", color="#444").encode(
        x=alt.datum(change_year), text=alt.value(f"Change point {change_year}")
    )
    return alt.layer(bars, rule, label)


#: Quick periods for the daily chart (:func:`period_window`).
PERIODS = ("Whole record", "Last 10 years", "Last water year")

Window = Tuple[pd.Timestamp, pd.Timestamp]


def period_window(choice: str, start: pd.Timestamp, end: pd.Timestamp) -> Optional[Window]:
    """The dates a quick period zooms the daily chart to, within a record ``start..end``.

    ``"Last water year"`` is the last complete one (October 1 to September 30) ending on
    or before ``end``; ``"Last 10 years"`` runs back from ``end``. ``None`` for the whole
    record, or when the record is too short to hold the period.
    """
    if choice == "Last 10 years":
        window = (max(start, end - pd.DateOffset(years=10)), end)
    elif choice == "Last water year":
        last = end.year if (end.month, end.day) >= (9, 30) else end.year - 1
        window = (max(start, pd.Timestamp(last - 1, 10, 1)), pd.Timestamp(last, 9, 30))
    else:
        return None
    return window if window[0] < window[1] else None


#: Readable names for the qualification-code tokens (``A`` approved needs no note).
_NOTES = {"P": "provisional", "e": "estimated"}


def status_note(code: Optional[str]) -> str:
    """A day's status for the readout, from its qualification code: ``"P:e"`` ->
    ``"provisional, estimated"``; ``""`` for an approved day without qualifiers."""
    if not code or not isinstance(code, str):
        return ""
    tokens = [t for t in code.split(":") if t and t != "A"]
    return ", ".join(_NOTES.get(t, t.lower()) for t in tokens)


def _with_log(frame: pd.DataFrame) -> pd.DataFrame:
    # log10 of the flow for the log axis; zero flows have none (a log axis cannot place them).
    return frame.assign(log_flow=np.log10(frame["flow_cfs"].where(frame["flow_cfs"] > 0)))


def _ms(ts: pd.Timestamp) -> int:
    # A naive timestamp as Vega sees one from Streamlit: milliseconds since the epoch.
    return int(pd.Timestamp(ts).value // 10**6)


#: Water-year lines show while the visible span is under this, in milliseconds.
_WY_SPAN_MS = 15 * 365.25 * 86400000


#: The flow axis follows the chart's own log/linear switch (the ``flowscale`` parameter).
_Y_EXPR = "flowscale == 'log' ? datum.log_flow : datum.flow_cfs"
_Y_LABEL = "flowscale == 'log' ? format(pow(10, datum.value), ',.2~r') : format(datum.value, ',')"
_READOUT = (
    "timeFormat(datum.date, '%b %-d, %Y') + ': ' + "
    "(isValid(datum.flow_cfs) ? format(datum.flow_cfs, ',.0f') + ' cfs' : 'no value') + "
    "(datum.note ? ' (' + datum.note + ')' : '')"
)


def daily_chart(
    daily: pd.DataFrame,
    peaks: Optional[pd.DataFrame] = None,
    log: bool = True,
    period: Optional[Window] = None,
) -> alt.VConcatChart:
    """The daily record: a detail view over a strip showing the whole record.

    Drag across the strip to zoom the detail to that period, drag the shaded box to move
    along the record, drag either end of the box to lengthen or shorten the period
    (:mod:`vega_component` adds the grips), double-click the strip to see it all again. Hovering the detail
    reads out the day and its flow; dashed lines mark water years (October 1) once zoomed;
    red dots are the annual peaks. A switch under the chart toggles log and linear. All of
    it happens in the browser, without a rerun, so a zoomed period survives the switch.

    Missing days show as gaps rather than being bridged. On the log axis (the default:
    daily flows span orders of magnitude) zero flows are left out, as it cannot place them.

    Parameters
    ----------
    daily : pandas.DataFrame
        :meth:`flowfreq.usgs.USGSgage.download_daily_flow` output: ``flow_cfs`` indexed
        by ``date``, days without a value absent.
    peaks : pandas.DataFrame, optional
        :meth:`flowfreq.usgs.USGSgage.download_peak_flow` output; those inside the daily
        record are drawn as dots.
    log : bool
        Whether the switch starts on log.
    period : (start, end), optional
        A period to open zoomed to (:func:`period_window`).
    """
    flows = daily["flow_cfs"].astype("float64")
    # Every calendar day, the missing ones as nulls, so the line breaks across a gap.
    days = pd.date_range(flows.index.min(), flows.index.max(), freq="D", name="date")
    data = _with_log(flows.reindex(days).rename("flow_cfs").to_frame())
    has_codes = "qualification_code" in daily
    if has_codes:
        codes = daily["qualification_code"].reindex(days)
        data["provisional"] = codes.str.startswith("P").fillna(False).astype(bool)
        notes = {code: status_note(code) for code in codes.dropna().unique()}
        data["note"] = codes.map(notes).fillna("")
    data = data.reset_index()
    # The strip shows only the shape of the record: monthly means keep it light.
    strip = flows.resample("MS").mean().rename("flow_cfs").rename_axis("date").reset_index()

    flowscale = alt.param(
        name="flowscale",
        value="log" if log else "linear",
        bind=alt.binding_radio(options=["log", "linear"], name="Flow axis: "),
    )
    # A quick period opens as a box on the strip, so its edges can be dragged too.
    zoom = alt.selection_interval(
        encodings=["x"],
        name="period",
        **({"value": {"x": [_datetime(period[0]), _datetime(period[1])]}} if period else {}),
    )
    # What the detail shows: the brushed period, else the quick period, else everything.
    # The domain falls back to the quick period too, so the detail opens zoomed even
    # before the selection's starting value has reached the store.
    lo, hi = period if period else (days[0], days[-1])
    shown = f"period.date ? period.date : [{_ms(lo)}, {_ms(hi)}]"
    hover = alt.selection_point(
        name="hover", nearest=True, on="pointerover", clear="pointerout", encodings=["x"],
        empty=False,
    )  # fmt: skip

    x = alt.X(
        "date:T",
        title=None,
        scale=alt.Scale(domain=alt.ExprRef(shown)),
        axis=alt.Axis(format="%b %Y", labelOverlap=True),
    )

    def flow_axis(field: str) -> alt.Y:
        return alt.Y(
            f"{field}:Q",
            title="Daily mean flow (cfs)",
            scale=alt.Scale(zero=alt.ExprRef("flowscale == 'linear'")),
            axis=alt.Axis(labelExpr=_Y_LABEL),
        )

    y = flow_axis("y")
    # Clipped to the plot, and no default tooltip: Streamlit turns one on for every mark,
    # which on the hover points would show the plotted value -- log10 of the flow.
    quiet = {"clip": True, "tooltip": False}
    # Only the days in view, so the flow axis fits the period shown (and less is drawn).
    in_view = f"inrange(datum.date, {shown})"
    base = alt.Chart(data).transform_filter(in_view).transform_calculate(y=_Y_EXPR).encode(x=x)
    layers = [
        base.mark_line(strokeWidth=1, color="#1f77b4", **quiet).encode(y=y),
        # Invisible points the nearest-day hover snaps to.
        base.mark_point(opacity=0, **quiet).encode(y=y).add_params(hover),
        base.mark_rule(color="#555", **quiet).transform_filter(hover),
        base.mark_circle(color="#1f77b4", size=40, **quiet).encode(y=y).transform_filter(hover),
        # The readout sits in the top-left corner: beside the pointer it is cut off at the
        # right edge.
        base.mark_text(align="left", baseline="top", fontSize=12, fontWeight="bold", **quiet)
        .encode(x=alt.value(6), y=alt.value(4), text="readout:N")
        .transform_filter(hover)
        .transform_calculate(readout=_READOUT),
    ]
    if has_codes:
        # Provisional days over the record, in orange; the other days are null, so the
        # line breaks between provisional spans instead of joining them.
        layers.insert(
            1,
            base.transform_calculate(py="datum.provisional ? datum.y : null")
            .mark_line(strokeWidth=1.3, color="#ff7f0e", **quiet)
            .encode(y=flow_axis("py")),
        )
    octobers = pd.date_range(days[0], days[-1], freq="YS-OCT", name="date")
    if len(octobers):
        # Water years, shown while under 15 years are in view: across a century, a blur.
        span = f"(({shown})[1] - ({shown})[0])"
        layers.append(
            alt.Chart(octobers.to_frame(index=False))
            .mark_rule(
                color="#888",
                strokeDash=[3, 3],
                opacity=alt.ExprRef(f"{span} < {_WY_SPAN_MS} ? 0.7 : 0"),
                **quiet,
            )
            .encode(x=x)
        )
    dots = _peak_dots(peaks, days[0], days[-1])
    if dots is not None:
        layers.append(
            alt.Chart(dots)
            .transform_filter(in_view)
            .transform_calculate(y=_Y_EXPR)
            .mark_point(filled=True, color="#d62728", size=36, clip=True)
            .encode(
                x=x,
                y=y,
                tooltip=[
                    alt.Tooltip("water_year:Q", title="Water year", format="d"),
                    alt.Tooltip("date:T", title="Peak date", format="%b %-d, %Y"),
                    alt.Tooltip("flow_cfs:Q", title="Annual peak (cfs)", format=",.0f"),
                ],
            )
        )
    detail = alt.layer(*layers).properties(height=280, width="container")
    overview = (
        alt.Chart(strip)
        .mark_area(color="#9ecae1", line={"color": "#3182bd", "strokeWidth": 0.5}, tooltip=False)
        .encode(
            x=alt.X("date:T", title="Drag here to zoom to a period; double-click to reset"),
            # Linear always: an area fills down to zero, which a log axis does not have.
            y=alt.Y("flow_cfs:Q", title=None, axis=None, scale=alt.Scale(zero=True)),
        )
        .add_params(zoom)
        .properties(height=60, width="container")
    )
    # Streamlit would size a vconcat holding a layer with autosize "pad", which adds the
    # axes on top of the container width and overflows the page by their width.
    fit = alt.AutoSizeParams(type="fit-x", contains="padding")
    return alt.vconcat(detail, overview, spacing=6, autosize=fit).add_params(flowscale)


def _datetime(when: pd.Timestamp) -> alt.DateTime:
    # A date as Vega-Lite's DateTime, for a selection's starting value.
    return alt.DateTime(year=when.year, month=when.month, date=when.day)


def _peak_dots(
    peaks: Optional[pd.DataFrame], first: pd.Timestamp, last: pd.Timestamp
) -> Optional[pd.DataFrame]:
    # The annual peaks inside the daily record, in the daily chart's columns. Outside it
    # they would stretch the detail's time axis away from the strip's.
    if peaks is None or peaks.empty:
        return None
    dates = pd.to_datetime(peaks["peak_date"], errors="coerce")
    keep = dates.between(first, last) & peaks["peak_flow_cfs"].notna()
    if not keep.any():
        return None
    frame = pd.DataFrame(
        {
            "date": dates[keep],
            "flow_cfs": peaks.loc[keep, "peak_flow_cfs"].astype("float64"),
            "water_year": peaks.loc[keep, "water_year"].astype(int),
        }
    )
    return _with_log(frame).reset_index(drop=True)


#: A leap water year (WY 2020) whose dates label the summary hydrograph's day axis.
_DOWY_ORIGIN = pd.Timestamp("2019-10-01")


def _log_axis(frame: pd.DataFrame, columns: Tuple[str, ...]) -> bool:
    # Log unless some value to be drawn is zero or negative, which a log axis cannot place.
    values = frame[list(columns)].to_numpy(dtype=float)
    return bool((values[np.isfinite(values)] > 0).all())


def summary_hydrograph_chart(daily: pd.DataFrame) -> alt.LayerChart:
    """Daily flow percentiles by day of the water year, from
    :meth:`flowfreq.hydrograph.Hydrograph.get_summary_stats`.

    The 10-90 and 25-75 percent bands, the median and the mean, on a log axis (linear
    when a percentile reaches zero). Hover for the day's values.
    """
    stats = Hydrograph.get_summary_stats(daily[["flow_cfs"]])
    stats["date"] = _DOWY_ORIGIN + pd.to_timedelta(stats["day_of_water_year"] - 1, unit="D")
    log = _log_axis(stats, ("p10", "p90", "p50"))
    scale = alt.Scale(type="log") if log else alt.Scale(zero=True)
    x = alt.X("date:T", title="Water year (October to September)", axis=alt.Axis(format="%b"))
    base = alt.Chart(stats).encode(x=x)
    flow = "Daily mean flow (cfs)"
    hover = alt.selection_point(
        nearest=True, on="pointerover", clear="pointerout", encodings=["x"], empty=False
    )
    tooltip = [
        alt.Tooltip("date:T", title="Day", format="%b %-d"),
        alt.Tooltip("p90:Q", title="90th percentile", format=",.0f"),
        alt.Tooltip("p75:Q", title="75th percentile", format=",.0f"),
        alt.Tooltip("p50:Q", title="Median", format=",.0f"),
        alt.Tooltip("mean:Q", title="Mean", format=",.0f"),
        alt.Tooltip("p25:Q", title="25th percentile", format=",.0f"),
        alt.Tooltip("p10:Q", title="10th percentile", format=",.0f"),
    ]
    return alt.layer(
        base.mark_area(color="#c6dbef", tooltip=False).encode(
            y=alt.Y("p10:Q", title=flow, scale=scale), y2="p90:Q"
        ),
        base.mark_area(color="#9ecae1", tooltip=False).encode(
            y=alt.Y("p25:Q", scale=scale), y2="p75:Q"
        ),
        base.mark_line(color="#08519c", strokeWidth=1.5, tooltip=False).encode(
            y=alt.Y("p50:Q", scale=scale)
        ),
        base.mark_line(color="#d62728", strokeDash=[4, 3], strokeWidth=1, tooltip=False).encode(
            y=alt.Y("mean:Q", scale=scale)
        ),
        base.mark_rule(color="#555")
        .encode(opacity=alt.condition(hover, alt.value(0.6), alt.value(0)), tooltip=tooltip)
        .add_params(hover),
    ).properties(height=260, title="Summary hydrograph")


#: Exceedance percentages the flow-duration curve is drawn at: dense in the tails.
FDC_PCT = tuple(
    sorted(
        {0.1, 0.2, 0.5, 99.5, 99.8, 99.9}
        | {float(v) for v in np.arange(1, 100)}
        | {float(v) for v in np.arange(0.5, 1.0, 0.1).round(1)}
    )
)


def duration_curve_chart(daily: pd.DataFrame) -> alt.Chart:
    """The flow-duration curve of the daily record, from
    :func:`flowfreq.regime.flow_duration_curve`, on a log axis (linear with zero flows)."""
    curve = flow_duration_curve(daily[["flow_cfs"]], exceedance_pct=FDC_PCT)
    log = _log_axis(curve, ("flow_cfs",))
    return (
        alt.Chart(curve)
        .mark_line(color="#08519c", strokeWidth=1.5, point=alt.OverlayMarkDef(size=12, opacity=0))
        .encode(
            x=alt.X(
                "exceedance_pct:Q",
                title="Percent of days the flow is equaled or exceeded",
                scale=alt.Scale(domain=[0, 100]),
            ),
            y=alt.Y(
                "flow_cfs:Q",
                title="Daily mean flow (cfs)",
                scale=alt.Scale(type="log") if log else alt.Scale(zero=True),
            ),
            tooltip=[
                alt.Tooltip("exceedance_pct:Q", title="Exceeded on (% of days)", format="g"),
                alt.Tooltip("flow_cfs:Q", title="Flow (cfs)", format=",.0f"),
            ],
        )
        .properties(height=260, title="Flow-duration curve")
    )


def _regime_section(daily: Dict[str, Any]) -> None:
    frame = daily.get("daily")
    if frame is None or frame.empty:
        return
    left, right = st.columns(2)
    left.altair_chart(summary_hydrograph_chart(frame), use_container_width=True)
    right.altair_chart(duration_curve_chart(frame), use_container_width=True)
    st.caption(
        "From every published day, provisional included. Summary hydrograph: the bands are "
        "the 10-90 and 25-75 percent ranges of the flows on each day of the water year, the "
        "line their median, the dashed line their mean. Flow-duration curve: q10 is the "
        "flow equaled or exceeded on 10 percent of days."
    )


def daily_csv(daily: pd.DataFrame) -> str:
    """The daily values as CSV: ``date,flow_cfs[,qualification_code]``, one row per
    published day."""
    columns = [c for c in ("flow_cfs", "qualification_code") if c in daily]
    return daily[columns].to_csv(date_format="%Y-%m-%d")


def peaks_csv(peaks: pd.DataFrame) -> str:
    """The annual peaks as CSV, as USGS reports them."""
    return peaks.to_csv(index=False, date_format="%Y-%m-%d")


#: Bar categories for the peak chart, with their colours. Codes are USGS peak
#: qualification codes: 7 historic peak; 5 and 6 affected by regulation or diversion;
#: C affected by urbanization or channelization.
PEAK_KINDS = {
    "No code": "#1f77b4",
    "Historic (code 7)": "#9467bd",
    "Regulated or diverted (5, 6)": "#d62728",
    "Urbanized (C)": "#ff7f0e",
    "Other code": "#7f7f7f",
}


def peak_kind(codes: str) -> str:
    """The chart category for a peak's comma-separated qualification codes."""
    found = {c.strip() for c in str(codes or "").split(",") if c.strip()}
    if not found:
        return "No code"
    if "7" in found:
        return "Historic (code 7)"
    if found & {"5", "6"}:
        return "Regulated or diverted (5, 6)"
    if "C" in found:
        return "Urbanized (C)"
    return "Other code"


#: Significance level of the stationarity screen (the library's default, stated here
#: because :func:`change_year` reads the change-point p-value against it).
SCREEN_ALPHA = 0.05


def screen_peaks(peaks: pd.DataFrame) -> Dict[str, Any]:
    """The library's stationarity screen of an annual peak record; never raises.

    The same input ``run_ffa`` screens on the Flow Frequency page: every peak with its
    qualification codes (so a change point can be attributed), in log10 when every peak
    is positive.

    Parameters
    ----------
    peaks : pandas.DataFrame
        :meth:`flowfreq.usgs.USGSgage.download_peak_flow` output.

    Returns
    -------
    dict
        :func:`flowfreq.stationarity.stationarity_screen`'s result, or ``{"error": msg}``
        when the screen cannot run (fewer than ten peaks).
    """
    values, codes, log = _peak_series(peaks)
    try:
        return stationarity_screen(values, log=log, alpha=SCREEN_ALPHA, peak_codes=codes)
    except ValueError as exc:
        logger.info("stationarity screen not run for the gage page: %s", exc)
        return {"error": str(exc)}


def change_year(screen: Dict[str, Any]) -> Optional[int]:
    """The water year of a significant change point in :func:`screen_peaks`'s result."""
    pettitt = screen.get("pettitt") or {}
    year, p_value = pettitt.get("year"), pettitt.get("p_value")
    if year is None or p_value is None or p_value >= SCREEN_ALPHA:
        return None
    return int(year)


def _peak_series(peaks: pd.DataFrame) -> Tuple[pd.Series, Optional[list], bool]:
    # Peaks by water year, their codes, and whether to screen in log10 (every peak > 0).
    values = pd.Series(
        peaks["peak_flow_cfs"].to_numpy(dtype=float),
        index=peaks["water_year"].to_numpy(dtype=int),
    )
    finite = values.dropna()
    codes = (
        peaks["qualification_code"].astype("string").fillna("").tolist()
        if "qualification_code" in peaks
        else None
    )
    return values, codes, bool(len(finite)) and bool((finite > 0).all())


def event_counts(daily: Optional[pd.DataFrame]) -> Any:
    """Peaks-over-threshold counts per water year for the report, or None.

    Two events a year, the usual choice for rain-driven floods; where that pulls the
    threshold below the 75th percentile of daily flow (a snowmelt river, whose freshet
    is one event), one a year instead, as :func:`flowfreq.stationarity.pot_counts`
    advises. None without a daily record or with under five complete water years.
    """
    if daily is None or daily.empty:
        return None
    flows = daily["flow_cfs"].astype("float64")
    try:
        counts = pot_counts(flows, events_per_year=2.0)
        if counts.quantile < POT_LOW_QUANTILE:
            counts = pot_counts(flows, events_per_year=1.0)
    except ValueError as exc:
        logger.info("no event counts for the stationarity report: %s", exc)
        return None
    return counts


@st.cache_data(ttl=CACHE_TTL_S, max_entries=16, show_spinner=False)
def report_files(
    site_no: str, name: str, peaks: pd.DataFrame, daily: Optional[pd.DataFrame]
) -> Dict[str, Any]:
    """The library's one-page stationarity report, as files to download.

    Parameters
    ----------
    site_no, name : str
        For the title and file names.
    peaks : pandas.DataFrame
        :meth:`flowfreq.usgs.USGSgage.download_peak_flow` output.
    daily : pandas.DataFrame, optional
        The daily record, for the event-count trend (:func:`event_counts`).

    Returns
    -------
    dict
        ``markdown`` (str) and ``png`` (bytes), or ``{"error": msg}`` when the screen
        cannot run (fewer than ten peaks).
    """
    import matplotlib.pyplot as plt

    values, codes, log = _peak_series(peaks)
    title = f"USGS {site_no} {name}".strip() + ": annual peaks"
    try:
        report = stationarity_report(
            values,
            log=log,
            alpha=SCREEN_ALPHA,
            peak_codes=codes,
            pot=event_counts(daily),
            title=title,
        )
    except ValueError as exc:
        return {"error": str(exc)}
    buffer = io.BytesIO()
    report.figure.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    plt.close(report.figure)
    return {"markdown": report.markdown, "png": buffer.getvalue()}


def _report_downloads(site_no: str, name: str, peaks: pd.DataFrame, daily: Any) -> None:
    frame = daily.get("daily") if isinstance(daily, dict) else None
    files = report_files(site_no, name, peaks, frame)
    if "error" in files:
        return
    cols = st.columns(3)
    cols[0].download_button(
        "Stationarity report (Markdown)",
        files["markdown"],
        file_name=f"{site_no}_stationarity.md",
        mime="text/markdown",
    )
    cols[1].download_button(
        "Stationarity figure (PNG)",
        files["png"],
        file_name=f"{site_no}_stationarity.png",
        mime="image/png",
    )


def stationarity_section(screen: Dict[str, Any]) -> None:
    """A stationarity screen's flags, or why there are none: under the gage page's peak
    chart, and with the Flow Frequency page's Bulletin 17C results."""
    if "error" in screen:
        st.caption(f"Stationarity screen not run: {screen['error']}.")
        return
    first, last = screen["years"]
    span = f"{screen['n']} annual peaks, {first}\u2013{last}"
    if not screen["flags"]:
        st.caption(
            f"Stationarity screen: no significant trend, change point or change in "
            f"variability in the {span} ({SCREEN_ALPHA:.0%} level)."
        )
        return
    st.warning(
        f"**Stationarity screen** ({span}):\n\n"
        + "\n".join(f"- {flag[0].upper()}{flag[1:]}" for flag in screen["flags"])
    )
    st.caption(
        "Trend and change-point tests from flowfreq, for information: the screen does not "
        "change the Bulletin 17C fit, which assumes a stationary record."
    )


def back_button() -> None:
    """The same-tab "Back to the map" control."""
    st.button("\u2190 Back to the map", on_click=_go, args=("ungaged",), key="back_to_map")


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
    # A link, so the analysis opens in a new window (or tab, as the browser prefers) and
    # this page stays as it is. The new window is a new session: the site travels in the
    # URL, which the Flow Frequency page reads as a hand-off; run=1 starts the analysis there.
    col_run.link_button(
        "Open in Bulletin 17C (Flow Frequency page)",
        f"?page=flowfrequency&site={site_no}&run=1",
        type="primary",
        disabled=not can_run,
        help=(
            "Opens the Flow Frequency page in a new window and runs Bulletin 17C on this site there."
            if can_run
            else "Needs an annual peak record."
        ),
    )
    col_links.markdown(_links(site_no))


def _daily_section(daily: Dict[str, Any], peaks: Optional[pd.DataFrame]) -> None:
    head, quick = st.columns([1, 2], vertical_alignment="bottom")
    head.subheader("Daily mean flow")
    if "error" in daily:
        st.warning(daily["error"])
        return
    frame = daily["daily"]
    choice = quick.segmented_control(
        "Period",
        PERIODS,
        default=PERIODS[0],
        key="daily_period",
        label_visibility="collapsed",
    )
    window = period_window(choice or PERIODS[0], frame.index.min(), frame.index.max())
    # A key per period: Streamlit keeps a chart's view when only its parameters change,
    # which would ignore the new period's starting zoom. A new key draws a new chart.
    vega_chart(
        daily_chart(frame, peaks=peaks, period=window),
        resizable=["period"],
        height=440,
        key=f"daily_chart_{PERIODS.index(choice) if choice in PERIODS else 0}",
    )
    st.caption(
        "Daily mean flow as USGS publishes it, provisional values included; red dots are the "
        "annual (instantaneous) peaks; orange days are provisional. Hover for a day's flow. Drag across the strip under the "
        "chart to zoom to a period, drag the shaded box to move along the record, drag its "
        "ends to lengthen or shorten the period, double-click the strip to see it all; dashed lines mark water years once zoomed. Gaps are days "
        "with no published value."
    )


def _downloads(site_no: str, daily: Dict[str, Any], peaks: Dict[str, Any]) -> None:
    cols = st.columns(3)
    if "daily" in daily:
        cols[0].download_button(
            "Daily values (CSV)",
            daily_csv(daily["daily"]),
            file_name=f"{site_no}_daily.csv",
            mime="text/csv",
        )
    if "peaks" in peaks:
        cols[1].download_button(
            "Annual peaks (CSV)",
            peaks_csv(peaks["peaks"]),
            file_name=f"{site_no}_peaks.csv",
            mime="text/csv",
        )


def render(site_no: str) -> None:
    """Draw the gage page for one validated site number."""
    back_button()
    with st.spinner(f"Downloading USGS {site_no}..."):
        loaded = load_all(site_no)
    site, peaks, daily = loaded["site"], loaded["peaks"], loaded["daily"]
    if "error" in site:
        st.header(f"USGS {site_no}")
        st.error(site["error"])
        if site.get("kind") == "unreachable":
            st.button("Try again", on_click=clear_caches)
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

    summary = summarize_peaks(peaks.get("peaks"))

    st.subheader("Period of record")
    st.table(_record_frame(info, summary))
    _daily_section(daily, peaks.get("peaks"))
    _regime_section(daily)
    if "error" in peaks:
        st.warning(peaks["error"])
    else:
        st.subheader("Annual peak flows")
        screen = screen_peaks(peaks["peaks"])
        st.altair_chart(peak_chart(peaks["peaks"], change_year=change_year(screen)))
        st.caption(
            "Bars are the annual peaks as USGS reports them, coloured by qualification code. "
            "Bulletin 17C applies the codes, low-outlier tests and skew; it runs on the Flow Frequency "
            "page."
        )
        stationarity_section(screen)
        _report_downloads(site_no, info["name"], peaks["peaks"], daily)

    _actions(site_no, can_run="peaks" in peaks)
    _downloads(site_no, daily, peaks)
    with st.expander("Coming to this page"):
        st.markdown(
            "- Raster hydrograph (day of year by year)\n"
            "- The Bulletin 17C frequency curve in place, without leaving the page\n"
            "- Dams and land-cover change in the basin beside a change point"
        )
