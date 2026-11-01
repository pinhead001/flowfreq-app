"""Build the basin map's small-scale water layers from Natural Earth.

Writes three files into ``map_component/``:

- ``water_base.geojson`` and ``water_detail.geojson``: river and lake centrelines
  (``ne_10m_rivers_lake_centerlines`` plus the North America supplement
  ``ne_10m_rivers_north_america``) and lakes and reservoirs (``ne_10m_lakes`` plus
  ``ne_10m_lakes_north_america``), each feature tagged ``kind`` river or lake. Features
  Natural Earth shows from zoom :data:`DETAIL_MINZ` on go in the detail file, which the
  map loads only when the user zooms that far, so first paint carries the base alone;
- ``water_labels.geojson``: a label point for each named sea, gulf, bay and sound
  (``ne_10m_geography_marine_polys``).

The map draws these below zoom 10, where the USGS NHD service draws nothing, and labels
water bodies from them. That replaces the USGS cached hydro tiles, whose labels are baked
in -- including "Gulf of America" -- and cannot be restyled or renamed. Natural Earth names
are used, through :data:`NAME_OVERRIDES` so a renamed feature in a future release cannot
slip through.

Only features with a vertex in :data:`REGIONS` (the states and territories) are kept, and
coordinates are rounded to :data:`NDIGITS` places (about 110 m, finer than a pixel below
zoom 10). Source: Natural Earth (public domain), pinned to release v5.1.2 of
github.com/nvkelso/natural-earth-vector. Regenerate with::

    python tools/build_hydro_geojson.py
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import requests

logger = logging.getLogger(__name__)

SOURCE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson"
OUT_DIR = Path(__file__).resolve().parent.parent / "map_component"
NDIGITS = 3
#: Natural Earth ``min_zoom`` from which a feature goes in the detail file.
DETAIL_MINZ = 6.0
#: Douglas-Peucker tolerance, degrees: about a pixel at zoom 9, the last zoom these draw at.
TOLERANCE = 0.003

#: (west, south, east, north) boxes around the states and territories, a little generous
#: so border rivers and the Great Lakes are kept whole.
REGIONS: Tuple[Tuple[float, float, float, float], ...] = (
    (-130.0, 23.0, -60.0, 53.0),  # CONUS and its borders
    (-180.0, 51.0, -129.0, 72.0),  # Alaska
    (172.0, 51.0, 180.0, 54.0),  # the Aleutians west of the antimeridian
    (-161.0, 18.0, -154.0, 23.0),  # Hawaii
    (-68.0, 17.0, -64.0, 19.0),  # Puerto Rico and the US Virgin Islands
    (144.0, 13.0, 146.5, 21.0),  # Guam and the Northern Mariana Islands
    (-171.5, -15.0, -168.0, -11.0),  # American Samoa
)

#: Names to correct on the way in. ``None`` drops the label. The map shows the names in
#: common use, whatever a source's release calls them.
NAME_OVERRIDES: Dict[str, Optional[str]] = {
    "Gulf of America": "Gulf of Mexico",
    "Lake America": None,
}


def real_name(name: Optional[str]) -> Optional[str]:
    """The label to show for a source name, or ``None`` for no label."""
    if not name:
        return None
    return NAME_OVERRIDES.get(name, name)


#: Last words that already say what a feature is ("Clear Creek", "Fort Peck Lake").
_WATER_WORDS = frozenset(
    "river creek wash canal bayou slough outlet draw kill run brook channel water lake "
    "lakes reservoir pool pond dam bay sea sound".split()
)
#: First words that do the same, several in French or Spanish ("Lake Mead", "Rio Grande").
_WATER_PREFIXES = frozenset(
    "lake lac laguna lago presa rio río r riviere rivière arroyo bayou".split()
)

#: First words Natural Earth's ``name_full`` has lost a letter from (308 "Rivire", 4 "Ro").
_REPAIRS = {"Rivire": "Rivière", "Ro": "Río"}


def water_name(props: Dict[str, Any], kind: str) -> Optional[str]:
    """The label for a river or lake: its full name, so Flathead Lake and the Flathead
    River do not both read "Flathead".

    Lakes use Natural Earth's ``name`` ("Flathead Lake", "Lake Mead"), not ``name_en``,
    which drops the generic word. Rivers use the North America supplement's ``name_full``
    where there is one, else ``name`` with "River" added. A river segment drawn through a
    lake (``featurecla`` "Lake Centerline") gets no label, which would sit on the lake's.
    A name that neither ends nor starts with a generic word gets "Lake" or "River" added
    ("Double Mountain Fork Brazos" is a river; "Allan Water" already says so).
    """
    if kind == "river" and props.get("featurecla") == "Lake Centerline":
        return None
    raw = (props.get("name_full") if kind == "river" else None) or props.get("name")
    parts = str(raw or props.get("name_en") or "").split()
    if parts:
        parts[0] = _REPAIRS.get(parts[0], parts[0])
    name = real_name(" ".join(parts))
    if not name:
        return None
    words = [w.strip(".,").lower() for w in name.split()]
    if words[-1] in _WATER_WORDS or (len(words) > 1 and words[0] in _WATER_PREFIXES):
        return name
    return f"{name} {'Lake' if kind == 'lake' else 'River'}"


#: Map abbreviations for the generic words of a name, used where the full name does not fit.
_SHORT = {
    "river": "R.", "lake": "L.", "reservoir": "Res.", "creek": "Cr.", "fork": "Fk.",
    "branch": "Br.", "north": "N.", "south": "S.", "east": "E.", "west": "W.",
    "middle": "Mid.", "saint": "St.", "riviere": "R.", "rivière": "R.",
}  # fmt: skip


def short_name(name: str) -> str:
    """The name with its generic words abbreviated: "South Fork Flathead River" ->
    "S. Fk. Flathead R."."""
    return " ".join(_SHORT.get(word.lower(), word) for word in name.split())


#: Label font sizes in the map (``waterLabelLayers`` in ``index.html``), pixels.
_FONT_PX = {"lake": 11.0, "river": 10.5}
#: Average glyph width of Noto Sans Italic, in ems.
_CHAR_EM = 0.55
#: Lake labels wrap at this many ems (``text-max-width``).
_LAKE_WRAP_EM = 7.0


def _span(path: Sequence[Sequence[float]]) -> float:
    """Length of a path in degrees of latitude (longitude scaled by cos latitude)."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        dx = (x2 - x1) * math.cos(math.radians((y1 + y2) / 2))
        total += math.hypot(dx, y2 - y1)
    return total


def _room(geometry: Dict[str, Any], kind: str) -> float:
    """The room a label has, in degrees of latitude: a lake's east-west width (labels are
    horizontal), or the length of a river's longest part (labels follow one line)."""
    coords, gtype = geometry["coordinates"], geometry["type"]
    if kind == "river":
        lines = [coords] if gtype == "LineString" else coords
        return max((_span(line) for line in lines), default=0.0)
    polys = [coords] if gtype == "Polygon" else coords
    best = 0.0
    for poly in polys:
        xs, ys = [p[0] for p in poly[0]], [p[1] for p in poly[0]]
        width = (max(xs) - min(xs)) * math.cos(math.radians((max(ys) + min(ys)) / 2))
        best = max(best, width)
    return best


def full_name_zoom(name: str, geometry: Dict[str, Any], kind: str) -> float:
    """The zoom from which ``name`` fits the feature; below it the map shows the short name.

    An estimate: the label's width from its length in characters, against the feature's
    room (:func:`_room`) at 512-pixel tiles.
    """
    em = _FONT_PX[kind]
    width = len(name) * _CHAR_EM * em
    if kind == "lake":
        width = min(width, _LAKE_WRAP_EM * em)
    room = _room(geometry, kind)
    if room <= 0:
        return 24.0
    return round(min(24.0, max(0.0, math.log2(width * 360 / (512 * room)))), 1)


def _vertices(coords: Any) -> Iterator[Sequence[float]]:
    if not coords:
        return  # Natural Earth has a few features with empty parts
    if isinstance(coords[0], (int, float)):
        yield coords
    else:
        for part in coords:
            yield from _vertices(part)


def in_regions(geometry: Dict[str, Any]) -> bool:
    """Whether any vertex of a geometry falls in one of :data:`REGIONS`."""
    return any(
        w <= v[0] <= e and s <= v[1] <= n
        for v in _vertices(geometry["coordinates"])
        for w, s, e, n in REGIONS
    )


def simplify(path: Sequence[Sequence[float]], tolerance: float) -> List[List[float]]:
    """Douglas-Peucker simplification; the ends (and so a ring's closure) are kept.

    A ring is never reduced below four points, so it stays a valid polygon ring.
    """
    points = [[p[0], p[1]] for p in path]
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (x1, y1), (x2, y2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        norm = (dx * dx + dy * dy) ** 0.5
        best, index = -1.0, -1
        for i in range(first + 1, last):
            px, py = points[i]
            if norm == 0:  # a closed ring: measure from the shared end point
                dist = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            else:
                dist = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
            if dist > best:
                best, index = dist, i
        if index != -1 and best > tolerance:
            keep[index] = True
            stack.extend(((first, index), (index, last)))
    out = [p for p, k in zip(points, keep) if k]
    if points[0] == points[-1] and len(out) < 4:
        return points  # too small to simplify without collapsing
    return out


def _round_path(path: Sequence[Sequence[float]], ndigits: int, closed: bool) -> List[List[float]]:
    out: List[List[float]] = []
    for x, y in ((p[0], p[1]) for p in simplify(path, TOLERANCE)):
        point = [round(x, ndigits), round(y, ndigits)]
        if not out or out[-1] != point:
            out.append(point)
    if closed and out and out[0] != out[-1]:
        out.append(out[0])
    return out


def round_geometry(geometry: Dict[str, Any], ndigits: int = NDIGITS) -> Dict[str, Any]:
    """A copy of a line or polygon geometry, rounded, with repeated vertices dropped."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "LineString":
        new: Any = _round_path(coords, ndigits, closed=False)
    elif kind == "MultiLineString":
        new = [_round_path(line, ndigits, closed=False) for line in coords]
    elif kind == "Polygon":
        new = [_round_path(ring, ndigits, closed=True) for ring in coords]
    elif kind == "MultiPolygon":
        new = [[_round_path(ring, ndigits, closed=True) for ring in poly] for poly in coords]
    else:
        raise ValueError(f"unsupported geometry {kind}")
    return {"type": kind, "coordinates": new}


def _ring_area(ring: Sequence[Sequence[float]]) -> float:
    return 0.5 * sum(
        ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)
    )


def label_point(geometry: Dict[str, Any]) -> Tuple[float, float]:
    """A label position: the area centroid of the outer ring of the largest part."""
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    ring = max((poly[0] for poly in polys), key=lambda r: abs(_ring_area(r)))
    area = _ring_area(ring)
    if area == 0:
        xs, ys = zip(*((p[0], p[1]) for p in ring))
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = 0.0
    for i in range(len(ring) - 1):
        cross = ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
        cx += (ring[i][0] + ring[i + 1][0]) * cross
        cy += (ring[i][1] + ring[i + 1][1]) * cross
    return round(cx / (6 * area), NDIGITS), round(cy / (6 * area), NDIGITS)


def split_tiers(
    features: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split features into the base tier and the detail tier (``minz >= DETAIL_MINZ``)."""
    base = [f for f in features if f["properties"]["minz"] < DETAIL_MINZ]
    detail = [f for f in features if f["properties"]["minz"] >= DETAIL_MINZ]
    return base, detail


def _fetch(name: str) -> List[Dict[str, Any]]:
    response = requests.get(f"{SOURCE}/{name}.geojson", timeout=180)
    response.raise_for_status()
    return response.json()["features"]


def _number(value: Any, default: float) -> float:
    return float(value) if isinstance(value, (int, float)) else default


def _water(features: List[Dict[str, Any]], kind: str) -> List[Dict[str, Any]]:
    kept = []
    for f in features:
        geometry = f.get("geometry")
        if not geometry or not in_regions(geometry):
            continue
        p = f["properties"]
        props: Dict[str, Any] = {
            "kind": kind,
            "rank": int(_number(p.get("scalerank"), 10)),
            "minz": _number(p.get("min_zoom"), 0),
        }
        name = water_name(p, kind)
        if name:
            props["name"] = name
            short = short_name(name)
            if short != name:
                props["short"] = short
                props["fullz"] = float(full_name_zoom(name, geometry, kind))
            props["labelz"] = _number(p.get("min_label"), props["minz"] + 1)
        kept.append({"type": "Feature", "properties": props, "geometry": round_geometry(geometry)})
    return kept


def _marine_labels(features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    labels = []
    for f in features:
        geometry = f.get("geometry")
        name = real_name(f["properties"].get("name_en") or f["properties"].get("name"))
        if not geometry or not name or not in_regions(geometry):
            continue
        x, y = label_point(geometry)
        labels.append(
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "rank": int(_number(f["properties"].get("scalerank"), 10)),
                    "labelz": _number(f["properties"].get("min_label"), 3),
                },
                "geometry": {"type": "Point", "coordinates": [x, y]},
            }
        )
    return labels


def _write(name: str, features: List[Dict[str, Any]]) -> None:
    text = json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    path = OUT_DIR / name
    path.write_text(text, encoding="utf-8")
    logger.info("%s: %d features, %d KB", path.name, len(features), len(text) // 1024)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rivers = _water(
        _fetch("ne_10m_rivers_lake_centerlines") + _fetch("ne_10m_rivers_north_america"),
        "river",
    )
    lakes = _water(_fetch("ne_10m_lakes") + _fetch("ne_10m_lakes_north_america"), "lake")
    base, detail = split_tiers(lakes + rivers)  # lakes first: rivers draw over them
    _write("water_base.geojson", base)
    _write("water_detail.geojson", detail)
    _write("water_labels.geojson", _marine_labels(_fetch("ne_10m_geography_marine_polys")))


if __name__ == "__main__":
    main()
