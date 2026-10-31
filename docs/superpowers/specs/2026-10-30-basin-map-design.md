# Basin map for the ungaged page — design

Date: 2026-10-30. Status: approved in conversation, awaiting written review.

## Intent

Add an interactive map to the ungaged-site page so a user can zoom to a stream, click
it, and get the delineated basin and its regional-regression flood quantiles — the
page's existing workflow, with the map supplying the pour point and the jurisdiction.

The map opens on the conterminous United States and reaches Alaska, Hawaii, Puerto Rico
and the USVI, Guam and the CNMI, and American Samoa through jump buttons. Its default look is a pixelated
grayscale DEM in the manner of the early USGS 1:250,000 DEMs; a dark theme offers a
night view (Black Marble city lights under the hillshade) and a green iridescent
hillshade. Zoomed out, only major hydrologic units and large rivers show; zooming in
brings finer HUCs, smaller streams and sharper hillshade. State boundaries are light
lines. Streamgages appear at regional scale as hollow triangles. Close in, the
StreamStats stream grid shows which cells will snap and delineate.

Success: a user who knows nothing about StreamStats can find a stream, see that it will
delineate, click it, press Estimate, and see the basin drawn with its quantiles — with
no step slower than the StreamStats call itself.

Non-goals (written to `TODO.md`): comparing equation sets across a state line in one
view (option B below); a skew-region HUC overlay unless HUC geometry is cheap; the gage
page itself (Spec 2).

## Decisions made

| Question | Decision |
|---|---|
| Replace or accompany the typed inputs? | Accompany. A click fills the latitude/longitude/jurisdiction boxes; typing moves the map marker. |
| Basin crosses a state line | **Option A.** Default to the clicked state; offer the other touched states as one-click re-runs. Option B (run several states and compare) is a TODO. |
| Map technology | MapLibre GL JS in a build-less Streamlit custom component. `streamlit-folium` rejected (CSS-filtered Leaflet can't do the look); pydeck rejected (returns clicks only on picked objects). |
| Basin geometry | Returned by the library on `SiteEstimate.basin_geojson` (flowfreq v0.18.0), not re-fetched by the app. |
| Gage symbol | Hollow triangle. |
| Gage popup | Site number, name, link to the in-app gage page (`?page=gage&site=…`), link to the USGS monitoring-location page. |
| Marker | CSS-pulsing orb: green in Night and Green modes, amber in DEM mode. |
| Left click | Fills latitude/longitude/jurisdiction only; the user presses Estimate. |
| Right click | Context menu at the cursor: **Delineate** (basin only, no equations), **Estimate** (basin and quantiles), **Copy lat/lon**, **Zoom to point**. |

## Architecture

```
streamlit_app.py           adds query-param routing (page, site) beside the sidebar radio
ungaged_ui.py              render(): map on top, inputs below; click -> inputs; basin -> map
map_component/
  __init__.py              basin_map(...) -> declare_component wrapper; arg preparation
  index.html               MapLibre, Streamlit component protocol, layers, modes
  states.geojson           Census 20m cartographic boundaries, states + DC + 5 territories
map_geo.py                 pure geometry: state_at(), states_touching(), round_coords()
docs/map_manual_checks.md  the JS checklist run before a PR
```

All modules stay at the repository root (CLAUDE.md: Streamlit puts the script's own
directory on `sys.path`, not the repository root). `map_component/` is a package
directory because `declare_component(path=...)` serves a directory.

### Data flow

1. `render()` reads the number inputs and the stored result, computes the component
   args, and calls `basin_map(...)` once with a fixed `key`.
2. The component returns `None` or `{"action", "lat", "lon", "zoom", "nonce"}` for the
   latest event that needs Python. `action` is `"point"` (left click), `"delineate"` or
   `"estimate"` (context-menu items). `nonce` is a counter the JS increments per event
   so two events at the same spot are distinguishable. Copy and Zoom-to-point are handled
   entirely in the JS and never reach Python.
3. If the nonce differs from `st.session_state["map_event_nonce"]`, `render()` writes
   lat/lon into the number inputs' session-state keys, sets the jurisdiction to
   `state_at(lat, lon)` when that is a served jurisdiction, and stores the nonce. Then,
   by action: `"point"` → `st.rerun()` so the widgets show the new values, nothing else;
   `"delineate"` → `_store_basin(...)` (below) then rerun; `"estimate"` → `_store(...)`,
   the existing estimate path, then rerun. A left click never calls StreamStats; the two
   menu items do so because the user asked by name.
4. On every run the number inputs' current values go back as `point`, so the marker
   follows typing with no extra state.
5. After an estimate, `outcome["estimate"].basin_geojson` (coordinates rounded to 6 dp,
   plus a short content hash) is passed as `basin`; the map fits to it and draws it with
   the snapped pour point from `provenance["snap"]`. After a delineation only, the
   stored outcome is `{"basin": Feature, "snap": (lat, lon), "area_sq_mi": float}` and the
   page shows a one-line caption ("Basin delineated: 142.3 sq mi. Press Estimate for
   quantiles.") plus the GeoJSON download, no quantile table. The existing stale-result
   logic clears either when inputs change.

### Delineate only

`run_delineation(lat, lon, state) -> dict` in `ungaged_ui.py`, the sibling of
`run_estimate` and like it never raises: calls
`flowfreq.streamstats.delineate_and_get_characteristics(state, lat, lon,
characteristic_codes=["DRNAREA"])` and returns `{"basin", "snap", "area_sq_mi"}` or
`{"error", "kind"}` with the same `kind` vocabulary (`input`, `network`, `unexpected`;
`UnsnappablePointError` and `DegenerateDelineationError` map to `input` with the
library's message). It shares the library's StreamStats cache with `estimate_at_site`,
so Delineate followed by Estimate pays for one delineation.

## The component

### Python interface (`map_component/__init__.py`)

```python
def basin_map(
    *,
    point: tuple[float, float] | None,
    basin: dict | None,                 # GeoJSON Feature, already rounded
    snap: tuple[float, float] | None,   # snapped pour point from provenance
    mode: Literal["dem", "night", "green"],
    overlays: frozenset[str],           # subset of {"coverage"}
    coverage: dict[str, str],           # jurisdiction code -> coverage badge
    height: int = 520,
    key: str = "basin_map",
) -> dict | None
```

`basin` is passed with a `"hash"` property (first 12 hex of sha1 of the coordinate
JSON) so the JS can skip re-adding an unchanged source. `coverage` is built once per
run from `coverage_badge(code)` for every code in `JURISDICTIONS`.

### JavaScript (`index.html`)

Single file. MapLibre GL JS from a CDN at a pinned version; the Streamlit component
protocol by hand (`streamlit:componentReady`, `streamlit:render` listener,
`streamlit:setComponentValue`, `streamlit:setFrameHeight`). No build step, no npm.

**Diffing.** The render handler keeps the last args and only touches what changed:
mode → swap paint properties and layer visibility; point → move the DOM marker; basin
→ compare hash, replace the GeoJSON source and `fitBounds` only when it changed;
overlays/coverage → set a feature-state or filter. A typed digit moves one marker and
nothing else. Panning and zooming never call Python.

**Layers, bottom to top.**

| # | Layer | Source | Visibility |
|---|---|---|---|
| 1 | Black Marble lights | NASA GIBS `VIIRS_Black_Marble` raster tiles | Night only |
| 2 | Coarse hillshade | AWS Terrain Tiles (Terrarium PNG), `raster-dem`, source `maxzoom` 9, `raster-resampling: nearest`, `hillshade-exaggeration` high so greys band | always; fades out z10–12 |
| 3 | Fine hillshade | same tiles, full resolution | fades in z10–12 |
| 4 | Rivers and HUCs | USGS `USGSHydroCached` raster tiles (scale-dependent NHD + WBD rendering is server-side: HUC2/4 and big rivers far out, HUC12 and small streams close in) | always; per-mode `raster-brightness`/`raster-saturation`/`raster-hue-rotate` |
| 5 | StreamGrid | `gis.streamstats.usgs.gov/arcgis/rest/services/stateServices/{st}/MapServer/export` with `{bbox-epsg-3857}`, layer `StreamGrid`, one raster source per state in view, `raster-resampling: nearest` | z ≥ 13 only |
| 6 | State fill (coverage tint) | bundled `states.geojson`, 25 % opacity: verified green, partial yellow, snapshot orange, none clear | "coverage" overlay |
| 7 | State lines | same source, 0.6 px, light per mode | always |
| 8 | Streamgages | `nationalLayers/MapServer/0/query` for the viewport bbox, `f=geojson`, 300 ms debounce after `moveend`, cached by tile key; one GeoJSON source, `symbol` layer with a hollow-triangle sprite (inline SVG data URI) | z ≥ 8 |
| 9 | Basin | GeoJSON source: outline + translucent fill; snapped pour point as a small circle | when a basin exists |
| 10 | Marker | DOM `maplibregl.Marker` with a CSS pulse animation | when `point` exists |

**Chips.** Small fixed-position chips in the map corner: the current StreamGrid state
("StreamGrid: click a lit cell" / "no StreamStats grid for XX") when z ≥ 13; a
four-swatch coverage legend when the overlay is on. The 55 state services available are
enumerated in the JS (list fetched once at build time, hard-coded with a comment
pointing at the services directory).

**Controls.** Jump buttons: CONUS, Alaska, Hawaii, Territories (cycles PR/USVI → Guam/
CNMI → American Samoa). Zoom control. Initial view: `fitBounds` over CONUS, so the
first paint is the familiar pixelated country; Alaska, Hawaii and the territories are one
jump-button click away. (A Guam-to-USVI opening view was considered and rejected: it
shows everything and makes nothing usable.)

**Context menu.** `contextmenu` on the map (not on a gage feature) opens a small
HTML menu at the cursor with the clicked coordinate as its header and four items:
*Delineate*, *Estimate*, *Copy lat/lon*, *Zoom to point*. Delineate and Estimate move
the marker and send `{"action": ..., ...}` to Python. Copy writes `"lat, lon"` (6 dp)
to the clipboard and flashes "copied" in the menu header. Zoom to point flies to z14
centred on the coordinate, which also brings the StreamGrid into view. The menu closes
on item choice, Escape, or any map interaction. The browser's own context menu is
suppressed only over the map canvas.

**Gage popup.** On click of a gage feature: a MapLibre popup with the site number and
name (from the feature properties), a link `?page=gage&site=NNNNNNNN` that opens in the
same tab, and a link to `https://waterdata.usgs.gov/monitoring-location/NNNNNNNN/` that
opens in a new tab. Period-of-record statistics live on the gage page (Spec 2), not in
the popup.

**Modes.**

| | DEM (default on light theme) | Night (default on dark theme) | Green |
|---|---|---|---|
| Background | `#d9d9d9` | black + Black Marble | `#06100c` |
| Hillshade highlight / shadow / accent | `#ffffff` / `#2b2b2b` / `#6e6e6e` | `#4a5a80` / `#000000` / `#1a2240` | `#7dffb3` / `#021a10` / `#1f8f5f` |
| Rivers | native blue | brightness raised, reads as glow | hue-rotated to cyan-white |
| State lines | `#555555` | `#99aaaa` at 60 % | `#55ffdd` at 50 % |
| Marker | amber `#d97706` | green `#39ff14` | green `#39ff14` |
| StreamGrid | deep blue | cyan | cyan |
| Gages | `#222222` | `#ffd166` | `#b6ffd9` |

All mode values live in one JS object; a fourth mode is a dozen lines.

## Page wiring (`ungaged_ui.py`)

- Layout: map (full width, 520 px) → a row with the mode selector (`st.segmented_control`
  or radio: DEM / Night / Green) and the Coverage toggle → the existing latitude,
  longitude, jurisdiction, AEPs, checkboxes, Estimate, results.
- Number inputs get explicit keys (`ungaged_lat`, `ungaged_lon`) and the jurisdiction
  selectbox `ungaged_state`, so a click can set them through session state.
- Mode defaults from `st.get_option("theme.base")` (`"dark"` → Night, else DEM) the
  first time; thereafter the user's choice persists in session state.
- After an estimate with a basin, `states_touching(basin)` minus the used state gives
  the "also lies in" list; each is a button that sets `ungaged_state` and re-runs via
  `_store`. Default remains the clicked state.
- A second download button, "Download basin (GeoJSON)", serves `basin_geojson` as
  `ungaged_{state}_{lat}_{lon}.geojson`. Only when a basin exists.
- Jurisdictions not served (`coverage_badge == BADGE_NONE`) still get selected by a
  click when the point is in them; the existing info line already explains why Estimate
  will fail. A click in the ocean leaves the jurisdiction unchanged.

## Routing (`streamlit_app.py`)

`st.query_params.get("page")` overrides the sidebar radio when present and valid
(`ungaged`, `gage`; `gage` renders a one-line placeholder until Spec 2 lands). The
sidebar radio stays the normal navigation; the query param exists so a popup link can
land on a page. Setting the radio clears the param.

## Geometry (`map_geo.py`)

Pure Python, no shapely.

- `load_states() -> dict` — the bundled GeoJSON, cached with `functools.lru_cache`
  (and `st.cache_resource` at the call site).
- `state_at(lat, lon) -> str | None` — ray casting over every ring of every state;
  holes respected; `None` outside. First match wins; the file's polygons don't overlap.
- `states_touching(basin: dict) -> list[str]` — states containing any basin vertex,
  plus states with a vertex inside the basin (catches a state wholly inside a basin).
  Sorted, deduplicated.
- `round_coords(geojson: dict, ndigits: int = 6) -> dict` — recursive, returns a copy.

## Library change (flowfreq → v0.18.0)

Branch from the library's `main` (not `feat/outlet-coordinates`).

- `SiteEstimate.basin_geojson: Optional[Dict[str, Any]] = None` — the validated
  `WatershedCharacteristics.polygon_geojson` Feature (WGS84, `[lon, lat]`, Polygon or
  MultiPolygon). Default keeps every existing construction valid.
- `estimate_at_site` sets it from `ws.polygon_geojson`. No new parameters; no new
  network calls.
- `to_markdown()` unchanged; the polygon stays out of the report.
- Tests: through the existing mocked-StreamStats path, assert `basin_geojson is` the
  fixture polygon; assert a directly constructed `SiteEstimate` defaults to `None`.
- CHANGELOG entry; tag `v0.18.0`; bump `requirements.txt`, `CLAUDE.md`, `README.md` here.

## Performance

- The component iframe persists across reruns (stable `key`); the JS diffs args.
- Clicks cause exactly one rerun; typing moves one marker.
- Only two dynamic request types: StreamGrid exports (z ≥ 13, states in view only) and
  gage queries (z ≥ 8, debounced, cached). Everything else is cached tiles.
- Basin coordinates rounded to 6 dp (≈10 cm) before serialization; hash prevents
  re-upload on mode toggles.
- Python: states GeoJSON loaded once; coverage computed once per run from in-memory
  tables; point-in-state is microseconds.
- Budgets, measured and recorded in the PR: first map paint < 1.5 s cold; mode switch or
  typed coordinate < 100 ms perceived; click-to-filled-inputs bounded by one rerun.

## Error handling

- Tile or export failures: MapLibre logs and leaves the layer blank; the page keeps
  working. The StreamGrid chip reports a state without a service.
- Gage query failure: silently no gages; retried on the next `moveend`.
- A `basin_geojson` of `None` (old cache entry, or a library before v0.18.0): the map
  draws nothing and the GeoJSON download is hidden; the estimate still shows.
- `state_at` returning `None` (ocean, outside the US): inputs filled, jurisdiction left
  as is.
- Component returns malformed value: ignored with a `logger.warning`.

## Testing

- `tests/test_map_geo.py` — `state_at` for a point in CONUS, AK, HI, PR, GU; the Gulf
  → `None`; a point on the MT/WY line → exactly one code; `states_touching` on a
  hand-built two-state polygon; `round_coords` returns a copy at 6 dp.
- `tests/test_ungaged_ui.py` additions in the existing `AppTest` style, with `basin_map`
  monkeypatched to return a chosen event dict: a `point` event fills lat/lon and
  jurisdiction and calls neither library function; a second event with a new nonce
  updates them, the same nonce is ignored; a `delineate` event calls the delineation
  (monkeypatched) and shows the caption and GeoJSON download but no quantile table; an
  `estimate` event calls `estimate_at_site` and shows the table; typing after a click
  changes the `point` passed to the component; a multi-state basin shows re-run buttons;
  mode defaults follow the theme option. `run_delineation` gets the same never-raises
  parametrized test as `run_estimate`.
- `tests/test_map_component.py` — `index.html` and `states.geojson` exist; the HTML
  pins one MapLibre version and contains no `http://` URL; args serialize to JSON with
  rounding applied and a hash present.
- The existing import test runs the whole script, which now covers the declaration and
  the query-param routing.
- JS has no automated tests. `docs/map_manual_checks.md` lists: three modes; pixel
  blocks at z4 vs smooth at z12; StreamGrid appears at z13 and the chip names the state;
  gage triangles at z8 and a popup with two links; the four jump buttons; a left click
  fills the inputs and nothing runs; right click opens the menu, each of its four items
  works, and it closes on Escape; a basin draws and fits after Delineate and after
  Estimate; a typed coordinate moves the orb.

## Open items (→ `TODO.md`)

- **Option B:** run the estimate for every state the basin touches and show results
  side by side (tabs), one StreamStats call per state.
- **Skew overlay:** HUC fill by Bulletin 17C skew region from `regional_skew_hucs.csv`,
  if HUC geometry turns out to be cheap to obtain; otherwise dropped.
- **Spec 2, the gage page:** site header, POR for daily and peak flows via
  `flowfreq.waterdata`, "Run Bulletin 17C on this site", placeholders for summary
  hydrograph, raster hydrograph, data-access links.
