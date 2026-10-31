"""Geometry for the basin map: which jurisdiction a point is in, and basin preparation.

Pure Python over the bundled ``map_component/states.geojson`` (see
``tools/build_states_geojson.py``); no shapely. This is lookup, not analysis: the basin
itself comes from the flowfreq library.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

STATES_PATH = Path(__file__).resolve().parent / "map_component" / "states.geojson"

#: Basin vertices tested against the state polygons, at most. StreamStats outlines trace
#: 10 m DEM cells and run to thousands of vertices; a state line crossing that falls
#: between two of this many evenly spaced samples would be a sliver of the basin.
MAX_BASIN_SAMPLES = 600

Ring = Sequence[Sequence[float]]
BBox = Tuple[float, float, float, float]


def _polygons(geometry: Dict[str, Any]) -> List[List[Ring]]:
    """A Polygon or MultiPolygon as a list of polygons, each a list of rings."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"]]
    if geometry["type"] == "MultiPolygon":
        return list(geometry["coordinates"])
    raise ValueError(f"expected Polygon or MultiPolygon, got {geometry['type']}")


def _vertices(polygons: List[List[Ring]]) -> Iterator[Sequence[float]]:
    for polygon in polygons:
        for ring in polygon:
            yield from ring


def _bbox(polygons: List[List[Ring]]) -> BBox:
    xs, ys = zip(*((v[0], v[1]) for v in _vertices(polygons)))
    return min(xs), min(ys), max(xs), max(ys)


def _in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _in_polygons(x: float, y: float, polygons: List[List[Ring]]) -> bool:
    # Even-odd over every ring of a polygon: a point in a hole crosses twice.
    return any(sum(_in_ring(x, y, ring) for ring in polygon) % 2 == 1 for polygon in polygons)


def _in_bbox(x: float, y: float, b: BBox) -> bool:
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


@lru_cache(maxsize=1)
def load_states() -> Dict[str, Any]:
    """The bundled states, DC and territories FeatureCollection.

    Returns
    -------
    dict
        GeoJSON FeatureCollection; each feature's ``properties`` is ``{"code": "XX"}``.
    """
    return json.loads(STATES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _indexed() -> List[Tuple[str, List[List[Ring]], BBox]]:
    out = []
    for feature in load_states()["features"]:
        polygons = _polygons(feature["geometry"])
        out.append((feature["properties"]["code"], polygons, _bbox(polygons)))
    return out


def state_at(lat: float, lon: float) -> Optional[str]:
    """The two-letter code of the state or territory containing a point.

    Parameters
    ----------
    lat, lon : float
        Decimal degrees WGS84.

    Returns
    -------
    str or None
        The code, or ``None`` when the point is in no bundled boundary (ocean, abroad).
    """
    for code, polygons, bbox in _indexed():
        if _in_bbox(lon, lat, bbox) and _in_polygons(lon, lat, polygons):
            return code
    return None


def states_touching(basin: Dict[str, Any]) -> List[str]:
    """The states and territories a basin polygon lies in, sorted.

    A state counts when a basin vertex falls inside it (up to
    :data:`MAX_BASIN_SAMPLES` evenly spaced vertices are tested) or when one of its
    own vertices falls inside the basin, which catches a state wholly inside it.

    Parameters
    ----------
    basin : dict
        GeoJSON Feature with a Polygon or MultiPolygon geometry.

    Returns
    -------
    list of str
        Sorted, deduplicated codes; empty when the basin lies outside every boundary.
    """
    basin_polygons = _polygons(basin["geometry"])
    basin_box = _bbox(basin_polygons)
    candidates = [
        (code, polygons, bbox)
        for code, polygons, bbox in _indexed()
        if bbox[0] <= basin_box[2]
        and basin_box[0] <= bbox[2]
        and bbox[1] <= basin_box[3]
        and basin_box[1] <= bbox[3]
    ]
    vertices = list(_vertices(basin_polygons))
    step = max(1, len(vertices) // MAX_BASIN_SAMPLES)
    found = set()
    for vertex in vertices[::step]:
        x, y = vertex[0], vertex[1]
        for code, polygons, bbox in candidates:
            if code not in found and _in_bbox(x, y, bbox) and _in_polygons(x, y, polygons):
                found.add(code)
                break
    for code, polygons, _ in candidates:
        if code in found:
            continue
        if any(
            _in_bbox(v[0], v[1], basin_box) and _in_polygons(v[0], v[1], basin_polygons)
            for v in _vertices(polygons)
        ):
            found.add(code)
    return sorted(found)


def _round(coords: Any, ndigits: int) -> Any:
    if isinstance(coords[0], (list, tuple)):
        return [_round(c, ndigits) for c in coords]
    return [round(c, ndigits) for c in coords]


def round_coords(geojson: Dict[str, Any], ndigits: int = 6) -> Dict[str, Any]:
    """A copy of a GeoJSON Feature with its coordinates rounded.

    Parameters
    ----------
    geojson : dict
        GeoJSON Feature.
    ndigits : int
        Decimal places; 6 is about 10 cm, halving the JSON sent to the browser.

    Returns
    -------
    dict
        A new Feature; the input is not modified.
    """
    geometry = geojson["geometry"]
    return {
        **geojson,
        "properties": dict(geojson.get("properties") or {}),
        "geometry": {**geometry, "coordinates": _round(geometry["coordinates"], ndigits)},
    }


def geojson_hash(feature: Dict[str, Any]) -> str:
    """A 12-hex-digit fingerprint of a Feature's coordinates.

    The map uses it to skip re-uploading a basin it already holds.
    """
    text = json.dumps(feature["geometry"]["coordinates"], separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
