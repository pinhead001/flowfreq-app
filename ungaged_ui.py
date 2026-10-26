"""The ungaged-site page: regional-regression flood quantiles at a point.

The page collects a latitude, longitude and jurisdiction, calls
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
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import requests
import streamlit as st
from flowfreq import OverlappingRegionsError, estimate_at_site
from flowfreq.regression import JURISDICTIONS, available_states, nss_snapshot_states
from flowfreq.regression.equations import OutOfRangeError
from flowfreq.regression.library import EquationsUnavailable
from flowfreq.ungaged import SiteEstimate

logger = logging.getLogger(__name__)

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


def _show_estimate(estimate: SiteEstimate) -> None:
    if estimate.library_status == "nss_snapshot" or estimate.advisory:
        st.warning(
            estimate.advisory
            or "These equations were harvested from NSS and are not report-verified."
        )
    st.subheader(f"Estimate at {estimate.lat:.4f}, {estimate.lon:.4f} ({estimate.state})")
    st.caption(f"Method: {estimate.method}. Equation library: {estimate.library_status}.")
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


def render() -> None:
    """Draw the ungaged-site page."""
    st.header("Ungaged site: regional regression")
    st.markdown(
        "Estimate flood quantiles at a point from the published regional regression "
        "equations. The basin is delineated with StreamStats; the equations come from "
        "the flowfreq library."
    )
    codes = [j.code for j in JURISDICTIONS]
    col_lat, col_lon, col_state = st.columns(3)
    lat = col_lat.number_input(
        "Latitude", value=None, min_value=-90.0, max_value=90.0, format="%.6f"
    )
    lon = col_lon.number_input(
        "Longitude", value=None, min_value=-180.0, max_value=180.0, format="%.6f"
    )
    state = col_state.selectbox("Jurisdiction", codes, format_func=_state_label)
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

    if st.button("Estimate", type="primary"):
        if lat is None or lon is None:
            st.session_state[RESULT_KEY] = {
                "outcome": {"error": "Enter a latitude and a longitude.", "kind": "input"}
            }
        else:
            _store(
                {
                    "lat": float(lat),
                    "lon": float(lon),
                    "state": state,
                    "aeps": [float(a) for a in aeps],
                    "snapshot": bool(snapshot),
                    "extrapolate": bool(extrapolate),
                }
            )

    result = st.session_state.get(RESULT_KEY)
    if not result:
        return
    outcome = result["outcome"]
    inputs = result.get("inputs")

    if "estimate" in outcome:
        _show_estimate(outcome["estimate"])
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
