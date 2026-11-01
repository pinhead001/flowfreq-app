"""The basin map: a build-less MapLibre GL component for the ungaged page.

``index.html`` in this directory is the whole frontend: MapLibre and the Streamlit
component protocol written by hand, so there is no npm build. MapLibre 5.6.0
(``vendor/``, BSD-3) and the label glyphs (``fonts/``, Noto Sans, OFL) are served from
this directory rather than a CDN. This module declares it and prepares its arguments.

The component's value is the latest event that needs Python, or ``None``::

    {"action": "point" | "delineate" | "estimate", "lat": float, "lon": float,
     "zoom": float, "nonce": int}
    {"action": "mode", "mode": "dem" | "night" | "green", "nonce": int}

``point`` is a left click, ``delineate`` and ``estimate`` are context-menu items, ``mode``
is the on-map style buttons (already applied by the map; Python only remembers it).
``nonce`` increments per event so two events at the same spot differ. Copy and
zoom-to-point never reach Python.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

import streamlit.components.v1 as components

from map_geo import geojson_hash, round_coords

#: Map styles, in the order the page offers them.
MODES: Tuple[str, ...] = ("dem", "night", "green")

_component = components.declare_component("basin_map", path=str(Path(__file__).parent))


class IdentityCache:
    """Values computed once per object, keyed by the object's identity; thread-safe.

    For per-result work the page repeats on every rerun: a stored result keeps the same
    objects across reruns, so each is computed once. Each entry holds its key object, so
    a recycled ``id`` can never match a different one. Shared by every session's thread,
    hence the lock.

    Parameters
    ----------
    maxsize : int
        Entries kept; the oldest is dropped first.
    """

    def __init__(self, maxsize: int = 16) -> None:
        self._maxsize = maxsize
        self._entries: "OrderedDict[int, Tuple[Any, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def clear(self) -> None:
        """Forget every entry."""
        with self._lock:
            self._entries.clear()

    def get(self, obj: Any, make: Callable[[Any], Any]) -> Any:
        """The value for ``obj``, computing it with ``make(obj)`` the first time."""
        with self._lock:
            hit = self._entries.get(id(obj))
            if hit is not None and hit[0] is obj:
                return hit[1]
        value = make(obj)  # outside the lock: it may be slow
        with self._lock:
            self._entries[id(obj)] = (obj, value)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
        return value


def _prepare(basin: Dict[str, Any]) -> Dict[str, Any]:
    sent = round_coords(basin)
    sent["properties"]["hash"] = geojson_hash(sent)
    return sent


#: Prepared (rounded, fingerprinted) basins, one per stored Feature.
_PREPARED = IdentityCache()


def _prepared(basin: Dict[str, Any]) -> Dict[str, Any]:
    return _PREPARED.get(basin, _prepare)


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
    view: Optional[Tuple[float, float, float]] = None,
) -> Dict[str, Any]:
    """Turn the page's state into the JSON the component receives.

    Parameters
    ----------
    point : (lat, lon), optional
        Where to draw the pulsing marker: the typed or clicked coordinate.
    basin : dict, optional
        GeoJSON Feature of the delineated basin. Sent rounded to 6 dp with a
        ``properties["hash"]`` fingerprint so the map skips re-adding an unchanged basin;
        the same object is prepared only once.
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
    view : (lat, lon, zoom), optional
        Where a newly mounted map opens (the last place the user clicked), instead of
        CONUS. Ignored once the map exists, so it never fights the user's panning.

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
    return {
        "point": _pair(point),
        "basin": None if basin is None else _prepared(basin),
        "snap": _pair(snap),
        "mode": mode,
        "overlays": sorted(overlays),
        "coverage": dict(coverage),
        "height": int(height),
        "view": None if view is None else [float(v) for v in view],
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
    view: Optional[Tuple[float, float, float]] = None,
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
        view=view,
    )
    return _component(**args, key=key, default=None)
