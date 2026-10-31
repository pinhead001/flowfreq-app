"""The ungaged-site page: regional-regression flood quantiles at a point.

A map (:mod:`map_component`) sits above the inputs: a left click fills the latitude,
longitude and jurisdiction; the right-click menu's *Delineate* and *Estimate* run at once;
typed coordinates move the map's marker. The page collects a latitude, longitude and
jurisdiction, calls
:func:`flowfreq.estimate_at_site` (StreamStats delineation plus the offline equation
library) and shows the estimate with its provenance. All computation is the library's;
this module formats outcomes and routes the user through the one interactive case, an
overlap of equation sets.

:func:`run_estimate` is the seam: it never raises, so the page has one code path for
failure. The pure helpers (:func:`coverage_badge`, :func:`run_estimate`) are importable
without a Streamlit runtime; :func:`render` is the page.
"""

from __future__ import annotations

import logging
import numbers
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import requests
import streamlit as st
from flowfreq import OverlappingRegionsError, estimate_at_site
from flowfreq.regression import JURISDICTIONS, available_states, nss_snapshot_states
from flowfreq.regression.equations import OutOfRangeError
from flowfreq.regression.library import EquationsUnavailable
from flowfreq.streamstats import delineate_and_get_characteristics
from flowfreq.ungaged import SiteEstimate

from map_component import MODES, basin_map
from map_geo import state_at

logger = logging.getLogger(__name__)

MODE_LABELS = {"dem": "DEM", "night": "Night", "green": "Green"}
MAP_ACTIONS = ("point", "delineate", "estimate")

BADGE_VERIFIED = "verified"
BADGE_PARTIAL = "partial"
BADGE_SNAPSHOT = "nss snapshot (not report-verified)"
BADGE_NONE = "none: NSS serves no peak-flow regions"

#: Standard AEPs offered in the selector; none selected means every AEP the regions publish.
AEP_CHOICES = (0.5, 0.2, 0.1, 0.04, 0.02, 0.01, 0.005, 0.002)

RESULT_KEY = "ungaged_result"


def coverage_badge(code: str) -> str:
    """Say what equation coverage a jurisdiction has.

    Parameters
    ----------
    code : str
        Two-letter jurisdiction code.

    Returns
    -------
    str
        ``"verified"`` or ``"partial"`` for a published library, ``"nss snapshot (not
        report-verified)"`` for a set harvested from NSS that needs the opt-in, else
        ``"none: NSS serves no peak-flow regions"``.
    """
    code = code.upper()
    status = available_states().get(code)
    if status == "verified":
        return BADGE_VERIFIED
    if status == "partial":
        return BADGE_PARTIAL
    if code in nss_snapshot_states():
        return BADGE_SNAPSHOT
    return BADGE_NONE


def run_estimate(
    lat: float,
    lon: float,
    state: str,
    aeps: Optional[Sequence[float]],
    allow_nss_snapshot: bool,
    *,
    region: Optional[str] = None,
    allow_extrapolation: bool = False,
) -> Dict[str, Any]:
    """Run :func:`flowfreq.estimate_at_site` for the page. Never raises.

    Parameters
    ----------
    lat, lon : float
        The pour point, decimal degrees.
    state : str
        Jurisdiction code.
    aeps : sequence of float, optional
        AEPs as fractions; empty or ``None`` means every AEP the regions publish.
    allow_nss_snapshot : bool
        Opt in to an NSS-snapshot equation set.
    region : str, optional
        NSS code chosen from an overlap.
    allow_extrapolation : bool
        Evaluate outside an equation's calibrated range, flagging the rows.

    Returns
    -------
    dict
        ``{"estimate": SiteEstimate}``, or ``{"error": str, "kind": str}`` with ``kind``
        one of ``overlap`` (which also carries ``candidates``, the library's
        ``(nss_code, region_name, year)`` tuples), ``equations``, ``out_of_range``,
        ``input``, ``network`` or ``unexpected``.
    """
    try:
        estimate = estimate_at_site(
            lat,
            lon,
            state=state,
            aeps=list(aeps) if aeps else None,
            allow_nss_snapshot=allow_nss_snapshot,
            allow_extrapolation=allow_extrapolation,
            region=region,
        )
    except OverlappingRegionsError as exc:
        return {"error": str(exc), "kind": "overlap", "candidates": list(exc.candidates)}
    except EquationsUnavailable as exc:
        return {"error": str(exc), "kind": "equations"}
    except OutOfRangeError as exc:
        return {
            "error": f"{exc} (tick 'Allow extrapolation' to proceed)",
            "kind": "out_of_range",
        }
    except KeyError as exc:  # unknown jurisdiction: KeyError quotes str(); use the message
        return {"error": str(exc.args[0]) if exc.args else "unknown key", "kind": "input"}
    except (ValueError, LookupError) as exc:
        return {"error": str(exc), "kind": "input"}
    except requests.RequestException as exc:
        return {"error": f"StreamStats request failed: {exc}", "kind": "network"}
    except Exception as exc:  # noqa: BLE001 - the page must show a failure, never a traceback
        logger.exception("ungaged estimate failed")
        return {"error": f"Unexpected {type(exc).__name__}: {exc}", "kind": "unexpected"}
    return {"estimate": estimate}


def run_delineation(lat: float, lon: float, state: str) -> Dict[str, Any]:
    """Delineate the basin at a point, without equations. Never raises.

    The map's *Delineate* action. Asks StreamStats for the drainage area only; the
    library's StreamStats cache is shared with :func:`run_estimate`, so an *Estimate* at
    the same point afterwards does not delineate again.

    Parameters
    ----------
    lat, lon : float
        The pour point, decimal degrees.
    state : str
        StreamStats region (jurisdiction code).

    Returns
    -------
    dict
        ``{"basin": Feature, "snap": (lat, lon), "area_sq_mi": float}``, or
        ``{"error": str, "kind": str}`` with ``kind`` one of ``input`` (including an
        unsnappable point, a degenerate delineation and a region StreamStats does not
        serve), ``network`` or ``unexpected``.
    """
    try:
        ws = delineate_and_get_characteristics(state, lat, lon, characteristic_codes=["DRNAREA"])
    except ValueError as exc:  # unsnappable, degenerate, unsupported region, bad input
        return {"error": str(exc), "kind": "input"}
    except requests.RequestException as exc:
        return {"error": f"StreamStats request failed: {exc}", "kind": "network"}
    except Exception as exc:  # noqa: BLE001 - the page must show a failure, never a traceback
        logger.exception("delineation failed")
        return {"error": f"Unexpected {type(exc).__name__}: {exc}", "kind": "unexpected"}
    if ws.polygon_geojson is None:
        return {"error": "StreamStats returned no watershed polygon here.", "kind": "input"}
    area = ws.polygon_area_sq_mi
    if area is None and "DRNAREA" in ws:
        area = ws["DRNAREA"].value
    return {
        "basin": ws.polygon_geojson,
        "snap": (ws.snap.snapped_lat, ws.snap.snapped_lon),
        "area_sq_mi": area,
    }


def _theme_type() -> Optional[str]:
    """``"dark"`` or ``"light"`` as the browser shows the app, else the configured base."""
    theme = getattr(getattr(st, "context", None), "theme", None)
    detected = getattr(theme, "type", None)
    return detected or st.get_option("theme.base")


def default_mode() -> str:
    """The map style to open with: Night under a dark theme, else the grey DEM."""
    return "night" if _theme_type() == "dark" else "dem"


@lru_cache(maxsize=1)
def _coverage() -> Dict[str, str]:
    """Every jurisdiction's coverage badge, for the map's tint. Fixed for the process."""
    return {j.code: coverage_badge(j.code) for j in JURISDICTIONS}


def handle_map_event(event: Any, codes: Sequence[str]) -> Optional[str]:
    """Apply a new map event to the input widgets' session state.

    Must run before the input widgets are created. Writes ``ungaged_lat`` and
    ``ungaged_lon``, and ``ungaged_state`` when the point lies in one of ``codes``; a
    point in the ocean or outside them leaves the jurisdiction as it was.

    Parameters
    ----------
    event : any
        The component's value (see :mod:`map_component`), or ``None``.
    codes : sequence of str
        The jurisdiction selectbox's options.

    Returns
    -------
    str or None
        The action applied, or ``None`` when there was no new, well-formed event.
    """
    if event is None:
        return None
    ok = (
        isinstance(event, dict)
        and event.get("action") in MAP_ACTIONS
        and all(
            isinstance(event.get(k), numbers.Real) and not isinstance(event.get(k), bool)
            for k in ("lat", "lon", "nonce")
        )
    )
    if not ok:
        logger.warning("ignored malformed map event: %r", event)
        return None
    if event["nonce"] == st.session_state.get("map_event_nonce"):
        return None  # the component keeps returning its last value; already applied
    st.session_state["map_event_nonce"] = event["nonce"]
    lat, lon = round(float(event["lat"]), 6), round(float(event["lon"]), 6)
    st.session_state["ungaged_lat"] = lat
    st.session_state["ungaged_lon"] = lon
    code = state_at(lat, lon)
    if code in codes:
        st.session_state["ungaged_state"] = code
    return event["action"]


def _basin_payload(
    result: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Tuple[float, float]]]:
    """The basin polygon and snapped pour point a stored result carries, if any."""
    return None, None


def _state_label(code: str) -> str:
    names = {j.code: j.name for j in JURISDICTIONS}
    return f"{code} - {names[code]} ({coverage_badge(code)})"


def _candidate_label(candidate: Sequence[Any]) -> str:
    code, name, year = candidate
    return f"{code} - {name} ({year if year is not None else 'year unknown'})"


def _quantile_frame(estimate: SiteEstimate) -> pd.DataFrame:
    q = estimate.quantiles
    return pd.DataFrame(
        {
            "AEP (%)": [f"{a * 100:g}" for a in q["aep"]],
            "Flow (cfs)": [f"{v:,.0f}" for v in q["flow_cfs"]],
            "Lower": ["" if pd.isna(v) else f"{v:,.0f}" for v in q["lower"]],
            "Upper": ["" if pd.isna(v) else f"{v:,.0f}" for v in q["upper"]],
            "Interval": list(q["interval_method"]),
            "Extrapolated": ["yes" if e else "no" for e in q["extrapolated"]],
            "Regions": list(q["regions"]),
        }
    )


def chosen_set_caption(estimate: SiteEstimate) -> str:
    """One line naming the equation set chosen from an overlap, or ``""`` if none was.

    Built from ``provenance["options"]["region"]`` and
    ``provenance["alternative_regions"]``.
    """
    region = (estimate.provenance.get("options") or {}).get("region")
    alternatives = estimate.provenance.get("alternative_regions") or []
    if not region:
        return ""
    used = next((r for r in estimate.regions if r.code == region), None)
    if used is None and len(estimate.regions) == 1:
        used = estimate.regions[0]
    code = used.code if used is not None else region
    detail = []
    if used is not None and getattr(used, "name", ""):
        detail.append(used.name)
    for per_region in estimate.estimates.values():
        for _, e in per_region:
            year = e.equation.citation.year
            if year:
                detail.append(str(year))
            break
        break
    text = f"Equation set chosen: {code}" + (f" ({', '.join(detail)})" if detail else "") + "."
    if alternatives:
        text += " Not used: " + ", ".join(
            f"{a['code']} ({a['year']})" if a.get("year") else str(a["code"]) for a in alternatives
        )
        text += "."
    return text


def _show_estimate(estimate: SiteEstimate) -> None:
    if estimate.library_status == "nss_snapshot" or estimate.advisory:
        st.warning(
            estimate.advisory
            or "These equations were harvested from NSS and are not report-verified."
        )
    st.subheader(f"Estimate at {estimate.lat:.4f}, {estimate.lon:.4f} ({estimate.state})")
    st.caption(f"Method: {estimate.method}. Equation library: {estimate.library_status}.")
    chosen = chosen_set_caption(estimate)
    if chosen:
        st.caption(chosen)
    st.dataframe(_quantile_frame(estimate), hide_index=True)
    with st.expander("Full report"):
        st.markdown(estimate.to_markdown())
    st.download_button(
        "Download report (Markdown)",
        data=estimate.to_markdown(),
        file_name=f"ungaged_{estimate.state}_{estimate.lat:.4f}_{estimate.lon:.4f}.md",
        mime="text/markdown",
    )


def _store(inputs: Dict[str, Any], region: Optional[str] = None) -> None:
    with st.spinner("Delineating the basin with StreamStats..."):
        outcome = run_estimate(
            inputs["lat"],
            inputs["lon"],
            inputs["state"],
            inputs["aeps"],
            inputs["snapshot"],
            region=region,
            allow_extrapolation=inputs["extrapolate"],
        )
    st.session_state[RESULT_KEY] = {"inputs": inputs, "outcome": outcome, "region": region}


def _store_basin(inputs: Dict[str, Any]) -> None:
    with st.spinner("Delineating the basin with StreamStats..."):
        outcome = run_delineation(inputs["lat"], inputs["lon"], inputs["state"])
    st.session_state[RESULT_KEY] = {"inputs": inputs, "outcome": outcome}


def render() -> None:
    """Draw the ungaged-site page."""
    st.header("Ungaged site: regional regression")
    st.markdown(
        "Estimate flood quantiles at a point from the published regional regression "
        "equations. The basin is delineated with StreamStats; the equations come from "
        "the flowfreq library."
    )
    codes = [j.code for j in JURISDICTIONS]
    st.session_state.setdefault("ungaged_lat", None)
    st.session_state.setdefault("ungaged_lon", None)
    st.session_state.setdefault("map_mode", default_mode())
    st.session_state.setdefault("map_coverage", False)

    # The map comes first and reads the widgets' state as of this run; its event is
    # applied before the input widgets exist, so the write lands in this same run.
    typed_lat, typed_lon = st.session_state["ungaged_lat"], st.session_state["ungaged_lon"]
    basin, snap = _basin_payload(st.session_state.get(RESULT_KEY))
    event = basin_map(
        point=None if typed_lat is None or typed_lon is None else (typed_lat, typed_lon),
        basin=basin,
        snap=snap,
        mode=st.session_state["map_mode"] or default_mode(),
        overlays=frozenset({"coverage"}) if st.session_state["map_coverage"] else frozenset(),
        coverage=_coverage(),
    )
    action = handle_map_event(event, codes)
    col_mode, col_cov = st.columns([3, 2])
    col_mode.segmented_control(
        "Map", MODES, format_func=MODE_LABELS.get, key="map_mode", label_visibility="collapsed"
    )
    col_cov.toggle(
        "Equation coverage",
        key="map_coverage",
        help="Tint jurisdictions by their regression library: verified, partial, NSS snapshot.",
    )
    st.caption(
        "Click a stream to fill the coordinates, then Estimate. Right-click for Delineate, "
        "Estimate, Copy and Zoom. From zoom 13 the StreamStats grid shows which cells snap."
    )

    col_lat, col_lon, col_state = st.columns(3)
    lat = col_lat.number_input(
        "Latitude", min_value=-90.0, max_value=90.0, format="%.6f", key="ungaged_lat"
    )
    lon = col_lon.number_input(
        "Longitude", min_value=-180.0, max_value=180.0, format="%.6f", key="ungaged_lon"
    )
    state = col_state.selectbox(
        "Jurisdiction", codes, format_func=_state_label, key="ungaged_state"
    )
    aeps: List[float] = st.multiselect(
        "AEPs (none selected: every AEP the regions publish)",
        AEP_CHOICES,
        format_func=lambda a: f"{a * 100:g}%",
    )
    snapshot = st.checkbox(
        "Allow NSS snapshot equations (not report-verified)",
        value=False,
        help="Needed for jurisdictions whose library is harvested from NSS.",
    )
    extrapolate = st.checkbox("Allow extrapolation outside the calibrated range", value=False)

    badge = coverage_badge(state) if state is not None else BADGE_NONE
    if badge == BADGE_NONE:
        st.info(f"{state}: {BADGE_NONE}.")
    elif badge == BADGE_SNAPSHOT and not snapshot:
        st.info(f"{state}: tick 'Allow NSS snapshot equations' to use its harvested set.")

    current = {
        "lat": None if lat is None else float(lat),
        "lon": None if lon is None else float(lon),
        "state": state,
        "aeps": [float(a) for a in aeps],
        "snapshot": bool(snapshot),
        "extrapolate": bool(extrapolate),
    }
    stored = st.session_state.get(RESULT_KEY)
    if stored and stored.get("inputs") is not None and stored["inputs"] != current:
        # The widgets moved on: the result (and any overlap choice) belongs to old inputs.
        del st.session_state[RESULT_KEY]
        st.session_state.pop("ungaged_candidate", None)

    if action == "delineate":
        _store_basin(current)
        st.rerun()  # so the map receives the basin
    if action == "estimate":
        _store(current)
        st.rerun()

    if st.button("Estimate", type="primary"):
        if lat is None or lon is None:
            st.session_state[RESULT_KEY] = {
                "outcome": {"error": "Enter a latitude and a longitude.", "kind": "input"}
            }
        else:
            _store(current)

    result = st.session_state.get(RESULT_KEY)
    if not result:
        return
    outcome = result["outcome"]
    inputs = result.get("inputs")

    if "estimate" in outcome:
        _show_estimate(outcome["estimate"])
    elif "basin" in outcome:
        area = outcome.get("area_sq_mi")
        size = f"{area:,.1f} sq mi" if area is not None else "area unknown"
        st.caption(f"Basin delineated: {size}. Press Estimate for quantiles.")
    elif outcome.get("kind") == "overlap" and inputs is not None:
        st.info(
            "NSS serves more than one equation set for this area (superseded and current "
            "reports side by side). They are alternatives, not parts of the basin: choose one."
        )
        if result.get("region"):
            # The choice was refused (it covers part of the basin, or StreamStats did not
            # use it): the library says why.
            st.warning(outcome["error"])
        chosen = st.selectbox(
            "Equation set",
            outcome["candidates"],
            format_func=_candidate_label,
            key="ungaged_candidate",
        )
        if st.button("Run with this equation set") and chosen is not None:
            _store(inputs, region=chosen[0])
            st.rerun()
    else:
        st.error(outcome["error"])
