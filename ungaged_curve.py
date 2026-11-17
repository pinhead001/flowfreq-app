"""The ungaged page's frequency curve: the regression estimate, and a gage's fit over it.

The regression gives a flow at each published annual exceedance probability, most with a
prediction interval. This module draws them as a curve on the axes a flood-frequency plot
uses (flow on a log scale against AEP on a normal-probability scale) and, where the point is
at a streamgage, lays that gage's Bulletin 17C fit over it with its confidence limits.

Nothing here computes a flow. The regression's numbers are the estimate's ``quantiles``;
the gage's are the Flow Frequency page's default fit, handed in by the app as a callable,
so the overlay is that page's analysis and not a second one. :func:`nearest_gage` is a
lookup in flowfreq's gage catalog.

:func:`regression_frame`, :func:`gage_frame`, :func:`nearest_gage` and :func:`curve_chart`
are importable without a Streamlit runtime; :func:`show` is the page section.
"""

from __future__ import annotations

from functools import lru_cache
from statistics import NormalDist
from typing import Any, Callable, Dict, List, Optional, Sequence

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from flowfreq.catalog import load_catalog
from flowfreq.ungaged import SiteEstimate

#: A gage this close to the point (km) is offered for the overlay. Catalog coordinates are
#: the gage house, and a click or a snapped pour point is rarely on it, so the test is
#: loose; the drainage areas, shown beside the offer, say whether it is the same stream.
GAGE_NEAR_KM = 1.0

#: The AEPs the probability axis is labelled at, in percent.
AXIS_AEP_PCT = (99.0, 95.0, 90.0, 80.0, 50.0, 20.0, 10.0, 4.0, 2.0, 1.0, 0.5, 0.2)

REGRESSION = "Regional regression"
#: Series colours and dashes: the app's blue and orange, told apart by dash and point
#: shape as well, so the two do not depend on colour.
_COLOUR = {"regression": "#1f77b4", "gage": "#ff7f0e"}
_DASH = {"regression": [1, 0], "gage": [6, 3]}
_SHAPE = {"regression": "circle", "gage": "diamond"}

#: Session state key: the points whose gage overlay the user asked for in this session.
_REQUESTED = "_ungaged_gage_overlays"

_COLUMNS = ["series", "aep", "aep_pct", "z", "flow", "lower", "upper"]


def aep_position(aep: float) -> float:
    """Where an AEP sits on a normal-probability axis: the standard normal quantile of
    its non-exceedance probability, so rarer floods are further right.

    Raises
    ------
    ValueError
        ``aep`` is not strictly between 0 and 1.
    """
    if not 0.0 < aep < 1.0:
        raise ValueError(f"an AEP is a probability between 0 and 1, got {aep!r}")
    return NormalDist().inv_cdf(1.0 - aep)


def _frame(series: str, aep: Sequence[float], flow: Any, lower: Any, upper: Any) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "series": series,
            "aep": pd.to_numeric(pd.Series(list(aep)), errors="coerce"),
            "flow": pd.to_numeric(pd.Series(list(flow)), errors="coerce"),
            "lower": pd.to_numeric(pd.Series(list(lower)), errors="coerce"),
            "upper": pd.to_numeric(pd.Series(list(upper)), errors="coerce"),
        }
    )
    # A log axis has no place for a zero flow, nor a probability axis for an AEP of 0 or 1.
    frame = frame[(frame["aep"] > 0) & (frame["aep"] < 1) & (frame["flow"] > 0)]
    # A limit that cannot be drawn on a log axis is left out with its partner.
    bad = ~((frame["lower"] > 0) & (frame["upper"] > 0))
    frame.loc[bad, ["lower", "upper"]] = np.nan
    frame["aep_pct"] = frame["aep"] * 100.0
    frame["z"] = [aep_position(a) for a in frame["aep"]]
    return frame.sort_values("z").reset_index(drop=True)[_COLUMNS]


def regression_frame(estimate: SiteEstimate) -> pd.DataFrame:
    """The regression estimate's quantiles as chart rows.

    Parameters
    ----------
    estimate : flowfreq.ungaged.SiteEstimate

    Returns
    -------
    pandas.DataFrame
        ``series``, ``aep``, ``aep_pct``, ``z`` (:func:`aep_position`), ``flow``, ``lower``,
        ``upper`` (NaN where the equations give no interval), one row per AEP, common
        floods first.
    """
    q = estimate.quantiles
    return _frame(REGRESSION, q["aep"], q["flow_cfs"], q["lower"], q["upper"])


def gage_label(site_no: str) -> str:
    """The overlay's series name."""
    return f"USGS {site_no} Bulletin 17C fit"


def gage_frame(result: Dict[str, Any], site_no: str) -> pd.DataFrame:
    """A Bulletin 17C fit's quantiles as chart rows.

    Parameters
    ----------
    result : dict
        The Flow Frequency page's fit (``run_site_ffa``): its ``quantile_df`` has
        ``Return Interval (yr)``, ``Flow (cfs)`` and the 90% confidence limits.
    site_no : str

    Returns
    -------
    pandas.DataFrame
        As :func:`regression_frame`, under :func:`gage_label`.

    Raises
    ------
    ValueError
        The fit failed (``result["error"]``) or has no quantile table.
    """
    table = result.get("quantile_df")
    if result.get("error") or table is None or len(table) == 0:
        raise ValueError(result.get("error") or f"USGS {site_no} has no fitted quantiles.")
    years = pd.to_numeric(table["Return Interval (yr)"], errors="coerce")
    return _frame(
        gage_label(site_no),
        1.0 / years,
        table["Flow (cfs)"],
        table["Lower 90% CI"],
        table["Upper 90% CI"],
    )


@lru_cache(maxsize=1)
def _gages() -> pd.DataFrame:
    catalog = load_catalog()
    located = catalog.dropna(subset=["latitude", "longitude"])
    return located.reset_index(drop=True)


def nearest_gage(lat: float, lon: float, max_km: float = GAGE_NEAR_KM) -> Optional[Dict[str, Any]]:
    """The catalog gage nearest a point, if one is within ``max_km``.

    Parameters
    ----------
    lat, lon : float
        The point, in decimal degrees.
    max_km : float
        How far away a gage may be and still count as at the point.

    Returns
    -------
    dict or None
        ``site_no``, ``site_name``, ``distance_km``, ``drainage_area_sqmi`` (None when the
        catalog has none) and ``n_peaks``; None when no gage is that close.

    Raises
    ------
    ValueError
        The point is not a latitude and longitude.
    """
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"not a latitude and longitude: {lat!r}, {lon!r}")
    gages = _gages()
    if gages.empty:
        return None
    phi1, phi2 = np.radians(lat), np.radians(gages["latitude"].to_numpy(dtype=float))
    dlon = np.radians(gages["longitude"].to_numpy(dtype=float) - lon)
    a = np.sin((phi2 - phi1) / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlon / 2) ** 2
    km = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
    nearest = int(np.argmin(km))
    if km[nearest] > max_km:
        return None
    row = gages.iloc[nearest]
    area, peaks = row.get("drainage_area_sqmi"), row.get("n_peaks")
    return {
        "site_no": str(row["site_no"]),
        "site_name": str(row.get("site_name") or ""),
        "distance_km": float(km[nearest]),
        "drainage_area_sqmi": None if pd.isna(area) else float(area),
        "n_peaks": None if pd.isna(peaks) else int(peaks),
    }


def _axis_ticks(z: pd.Series) -> List[Dict[str, float]]:
    low, high = float(z.min()), float(z.max())
    ticks = [{"pct": pct, "z": aep_position(pct / 100.0)} for pct in AXIS_AEP_PCT]
    return [t for t in ticks if low - 1e-9 <= t["z"] <= high + 1e-9]


def curve_chart(regression: pd.DataFrame, gage: Optional[pd.DataFrame] = None) -> alt.LayerChart:
    """The frequency curve: flow on a log axis against AEP on a normal-probability axis.

    Each series is a line through its quantiles with a point at each, over a band between
    its lower and upper limits where it has them. A second series brings a legend; the two
    differ in colour, dash and point shape.

    Parameters
    ----------
    regression : pandas.DataFrame
        :func:`regression_frame`.
    gage : pandas.DataFrame, optional
        :func:`gage_frame`, drawn over the regression.

    Returns
    -------
    altair.LayerChart

    Raises
    ------
    ValueError
        ``regression`` has no rows to draw.
    """
    if regression.empty:
        raise ValueError("the estimate has no quantiles to draw")
    frames = [regression] if gage is None or gage.empty else [regression, gage]
    data = pd.concat(frames, ignore_index=True)
    names = [str(f["series"].iloc[0]) for f in frames]
    kinds = ["regression", "gage"][: len(names)]
    legend = alt.Legend(orient="top", title=None, symbolStrokeWidth=2) if len(names) > 1 else None

    ticks = _axis_ticks(data["z"])
    # The axis is in z; its labels are the AEPs those z stand for.
    label = "".join(f"abs(datum.value - ({t['z']!r})) < 1e-6 ? '{t['pct']:g}' : " for t in ticks)
    pad = 0.04 * (float(data["z"].max()) - float(data["z"].min()) or 1.0)
    x = alt.X(
        "z:Q",
        title="Annual exceedance probability (percent)",
        scale=alt.Scale(
            domain=[float(data["z"].min()) - pad, float(data["z"].max()) + pad], nice=False
        ),
        axis=alt.Axis(values=[t["z"] for t in ticks], labelExpr=label + "''", grid=True),
    )
    colours = alt.Scale(domain=names, range=[_COLOUR[k] for k in kinds])
    colour = alt.Color("series:N", scale=colours, legend=legend)
    tooltip = [
        alt.Tooltip("series:N", title="Curve"),
        alt.Tooltip("aep_pct:Q", title="AEP (%)", format="g"),
        alt.Tooltip("flow:Q", title="Flow (cfs)", format=",.0f"),
        alt.Tooltip("lower:Q", title="Lower limit (cfs)", format=",.0f"),
        alt.Tooltip("upper:Q", title="Upper limit (cfs)", format=",.0f"),
    ]
    # The flow axis runs a little past the data, not out to the next power of ten.
    drawn = data[["flow", "lower", "upper"]]
    flows = alt.Scale(
        type="log", domain=[float(drawn.min().min()) / 1.25, float(drawn.max().max()) * 1.25]
    )
    base = alt.Chart(data)
    # One band per series, in a fixed colour: an encoded one would join the legend.
    bands = [
        base.transform_filter(alt.datum.series == name)
        .transform_filter("isValid(datum.lower) && isValid(datum.upper)")
        .mark_area(opacity=0.16, color=_COLOUR[kind], tooltip=False)
        .encode(
            x=x,
            y=alt.Y("lower:Q", scale=flows, title="Peak flow (cfs)", axis=alt.Axis(format="~s")),
            y2="upper:Q",
        )
        for name, kind in zip(names, kinds)
    ]
    line = base.mark_line(strokeWidth=2, tooltip=False).encode(
        x=x,
        y=alt.Y("flow:Q", scale=flows),
        color=colour,
        strokeDash=alt.StrokeDash(
            "series:N",
            scale=alt.Scale(domain=names, range=[_DASH[k] for k in kinds]),
            legend=legend,
        ),
    )
    points = base.mark_point(size=70, filled=True, opacity=1).encode(
        x=x,
        y=alt.Y("flow:Q", scale=flows),
        color=colour,
        shape=alt.Shape(
            "series:N",
            scale=alt.Scale(domain=names, range=[_SHAPE[k] for k in kinds]),
            legend=legend,
        ),
        tooltip=tooltip,
    )
    return alt.layer(*bands, line, points).properties(height=380)


def band_caption(estimate: SiteEstimate, with_gage: bool) -> str:
    """What the shaded bands are, in words."""
    q = estimate.quantiles
    has = q["lower"].notna() & q["upper"].notna()
    if not has.any():
        text = "These equations publish no prediction interval, so the regression has no band."
    else:
        levels = sorted({float(v) for v in q.loc[has, "interval_level"].dropna()})
        level = f"{levels[0] * 100:g}-percent " if len(levels) == 1 else ""
        text = f"The band around the regression is its {level}prediction interval"
        text += "." if has.all() else ", at the AEPs that have one."
    if with_gage:
        text += " The band around the gage's fit is its 90-percent confidence interval."
    return text


def _offer_text(gage: Dict[str, Any], area: Optional[float]) -> str:
    metres = gage["distance_km"] * 1000.0
    text = f"USGS {gage['site_no']} {gage['site_name']}".strip()
    text += f" is {metres:,.0f} m from this point"
    if gage["n_peaks"]:
        text += f", with {gage['n_peaks']} annual peaks"
    areas = []
    if gage["drainage_area_sqmi"] is not None:
        areas.append(f"gage {gage['drainage_area_sqmi']:,.1f} sq mi")
    if area is not None:
        areas.append(f"this estimate {area:,.1f} sq mi")
    if areas:
        text += f". Drainage area: {', '.join(areas)}"
    return text + "."


def _request(key: str) -> None:
    # A button callback: remember the point, so the overlay stays drawn on later reruns.
    st.session_state[_REQUESTED] = {*st.session_state.get(_REQUESTED, ()), key}


def show(
    estimate: SiteEstimate,
    gage_fit: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> None:
    """Draw the estimate's frequency curve, offering a gage's fit where one is at the point.

    Parameters
    ----------
    estimate : flowfreq.ungaged.SiteEstimate
    gage_fit : callable, optional
        ``gage_fit(site_no) -> result``: the Flow Frequency page's default fit of a gage's
        peaks, which never raises. Without it no overlay is offered.
    """
    regression = regression_frame(estimate)
    if len(regression) < 2:
        return  # one quantile is not a curve; the table has it
    gage = nearest_gage(estimate.lat, estimate.lon) if gage_fit is not None else None
    overlay: Optional[pd.DataFrame] = None
    if gage is not None and gage_fit is not None:
        key = f"{gage['site_no']}@{estimate.lat:.5f},{estimate.lon:.5f}"
        area = (getattr(estimate, "characteristics", None) or {}).get("DRNAREA")
        st.caption(_offer_text(gage, None if area is None else float(area)))
        if key not in st.session_state.get(_REQUESTED, ()):
            st.button(
                f"Overlay the fit at USGS {gage['site_no']}",
                on_click=_request,
                args=(key,),
                key="ungaged_overlay",
                help="Downloads the gage's annual peaks and fits Bulletin 17C (EMA) with "
                "the Flow Frequency page's default settings.",
            )
        else:
            with st.spinner(f"Fitting Bulletin 17C at USGS {gage['site_no']}..."):
                result = gage_fit(gage["site_no"])
            try:
                overlay = gage_frame(result, gage["site_no"])
            except ValueError as exc:
                st.warning(f"The fit at USGS {gage['site_no']} could not be drawn: {exc}")
    st.altair_chart(curve_chart(regression, overlay), use_container_width=True)
    st.caption(band_caption(estimate, overlay is not None))
