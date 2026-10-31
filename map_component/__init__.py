"""The basin map: a build-less MapLibre GL component for the ungaged page.

``index.html`` in this directory is the whole frontend: MapLibre from a CDN and the
Streamlit component protocol written by hand, so there is no npm build. This module
declares it and prepares its arguments.

The component's value is the latest event that needs Python, or ``None``::

    {"action": "point" | "delineate" | "estimate", "lat": float, "lon": float,
     "zoom": float, "nonce": int}

``point`` is a left click, the other two are context-menu items; ``nonce`` increments per
event so two events at the same spot differ. Copy and zoom-to-point never reach Python.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import streamlit.components.v1 as components

from map_geo import geojson_hash, round_coords

#: Map styles, in the order the page offers them.
MODES: Tuple[str, ...] = ("dem", "night", "green")

_component = components.declare_component("basin_map", path=str(Path(__file__).parent))


def _pair(value: Optional[Tuple[float, float]]) -> Optional[list]:
    return None if value is None else [float(value[0]), float(value[1])]


def prepare_args(
    *,
    point: Optional[Tuple[float, float]],
    basin: Optional[Dict[str, Any]],
    snap: Optional[Tuple[float, float]],
    mode: str,
    overlays: frozenset,
    coverage: Mapping[str, str],
    height: int,
) -> Dict[str, Any]:
    """Turn the page's state into the JSON the component receives.

    Parameters
    ----------
    point : (lat, lon), optional
        Where to draw the pulsing marker: the typed or clicked coordinate.
    basin : dict, optional
        GeoJSON Feature of the delineated basin. Sent rounded to 6 dp with a
        ``properties["hash"]`` fingerprint so the map skips re-adding an unchanged basin.
    snap : (lat, lon), optional
        StreamStats' snapped pour point.
    mode : str
        One of :data:`MODES`.
    overlays : frozenset of str
        Overlays switched on; currently ``{"coverage"}`` or empty.
    coverage : mapping
        Jurisdiction code to its coverage badge, for the coverage tint.
    height : int
        Frame height in pixels.

    Returns
    -------
    dict
        JSON-serialisable arguments.

    Raises
    ------
    ValueError
        For a mode not in :data:`MODES`.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    sent_basin = None
    if basin is not None:
        sent_basin = round_coords(basin)
        sent_basin["properties"]["hash"] = geojson_hash(sent_basin)
    return {
        "point": _pair(point),
        "basin": sent_basin,
        "snap": _pair(snap),
        "mode": mode,
        "overlays": sorted(overlays),
        "coverage": dict(coverage),
        "height": int(height),
    }


def basin_map(
    *,
    point: Optional[Tuple[float, float]],
    basin: Optional[Dict[str, Any]],
    snap: Optional[Tuple[float, float]],
    mode: str,
    overlays: frozenset,
    coverage: Mapping[str, str],
    height: int = 520,
    key: str = "basin_map",
) -> Optional[Dict[str, Any]]:
    """Draw the basin map and return its latest event.

    Parameters are those of :func:`prepare_args`, plus ``key``, which must stay fixed so
    the map's iframe survives reruns instead of remounting.

    Returns
    -------
    dict or None
        The latest event (see the module docstring), or ``None`` before any.
    """
    args = prepare_args(
        point=point,
        basin=basin,
        snap=snap,
        mode=mode,
        overlays=overlays,
        coverage=coverage,
        height=height,
    )
    return _component(**args, key=key, default=None)
