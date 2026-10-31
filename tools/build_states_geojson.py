"""Build ``map_component/states.geojson``: state, DC and territory outlines for the map.

The basin map draws these as light lines, tints them by equation coverage, and
:mod:`map_geo` uses them to name the jurisdiction under a click. Sources, both Census
TIGERweb (Generalized ACS 2023, State_County MapServer), checked 2026-10-30:

- layer 9, "States 20M": the 50 states, DC and Puerto Rico;
- layer 8, "States 5M": American Samoa, Guam, the Northern Mariana Islands and the US
  Virgin Islands, which the 20M layer omits.

Coordinates are rounded to 4 decimal places (about 11 m), far finer than the 20M
generalization, and properties are reduced to ``{"code": "XX"}``. Regenerate with::

    python tools/build_states_geojson.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import requests

logger = logging.getLogger(__name__)

SERVICE = (
    "https://tigerweb.geo.census.gov/arcgis/rest/services/"
    "Generalized_ACS2023/State_County/MapServer"
)
LAYER_20M = 9
LAYER_5M = 8
SMALL_TERRITORIES = ("AS", "GU", "MP", "VI")
OUT = Path(__file__).resolve().parent.parent / "map_component" / "states.geojson"


def _query(layer: int, where: str) -> List[Dict[str, Any]]:
    response = requests.get(
        f"{SERVICE}/{layer}/query",
        params={"where": where, "outFields": "STUSAB", "returnGeometry": "true", "f": "geojson"},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["features"]


def _round(coords: Any) -> Any:
    if isinstance(coords[0], list):
        return [_round(c) for c in coords]
    return [round(coords[0], 4), round(coords[1], 4)]


def build() -> Dict[str, Any]:
    """Fetch both layers and return the combined, rounded FeatureCollection."""
    territories = ",".join(f"'{c}'" for c in SMALL_TERRITORIES)
    raw = _query(LAYER_20M, "1=1") + _query(LAYER_5M, f"STUSAB IN ({territories})")
    features = [
        {
            "type": "Feature",
            "properties": {"code": f["properties"]["STUSAB"]},
            "geometry": {
                "type": f["geometry"]["type"],
                "coordinates": _round(f["geometry"]["coordinates"]),
            },
        }
        for f in raw
    ]
    features.sort(key=lambda f: f["properties"]["code"])
    return {"type": "FeatureCollection", "features": features}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    collection = build()
    text = json.dumps(collection, separators=(",", ":"))
    OUT.write_text(text, encoding="utf-8")
    logger.info("%d features, %d KB -> %s", len(collection["features"]), len(text) // 1024, OUT)


if __name__ == "__main__":
    main()
