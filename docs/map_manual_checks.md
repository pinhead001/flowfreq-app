# Basin map: manual checks

The map's JavaScript (`map_component/index.html`) has no automated tests; pytest pins only
what Python can see (`tests/test_map_component.py`). Run this list against `make run`
before a PR that touches the component, and record the date and anything that failed.

Use a real stream: Rattlesnake Creek above Missoula, MT (46.93, -113.97).

## Styles and detail

- [ ] DEM style: grey relief in visible blocks at zoom 4; smooth shading by zoom 12; no
      tile-seam grid lines
- [ ] Night style: dark blue-grey relief, city lights, navy water, light labels
- [ ] Green style: dark ground, lit faces glowing green, cyan/lime accent on steep slopes
- [ ] Under a dark Streamlit theme the map opens in Night
- [ ] Rivers and HUC lines appear and gain detail with zoom; state lines are light
- [ ] Equation coverage toggle tints jurisdictions and shows the four-swatch legend

## Layers by zoom

- [ ] Zoom 8 over Yellowstone: hollow triangles (streamgages)
- [ ] Clicking a triangle opens a popup: site number, name, "Gage page" (switches this tab
      to the gage page; "Back to the map" returns to the same view) and "USGS" (new tab)
- [ ] Zoom 13 over Montana: StreamGrid cells appear; the chip reads "StreamGrid: click a lit
      cell"
- [ ] Zoom 13 over Florida: the chip reads "no StreamStats grid for FL"

## Navigation

- [ ] Opens on CONUS
- [ ] Alaska, Hawaii jump; Territories cycles PR/USVI -> Guam/CNMI -> American Samoa; CONUS
      returns

## Clicks

- [ ] Delineate or Estimate from the menu shows "Delineating with StreamStats (10-30 s)" on the
      map, then the outcome just under the map
- [ ] A typed point outside the view pans the map to it
- [ ] Left click fills latitude, longitude and jurisdiction; the orb moves at once; nothing
      runs
- [ ] Typing a latitude moves the orb
- [ ] Right click opens the menu at the cursor with the coordinate as its header; Escape
      closes it; panning closes it
- [ ] Copy lat/lon puts "lat, lon" on the clipboard (header flashes "copied")
- [ ] Zoom to point flies to zoom 14
- [ ] Delineate: the basin and snapped point are drawn and the map fits them; caption shows
      the area; GeoJSON download offered; no quantile table
- [ ] Estimate: as Delineate, plus the quantile table and the Markdown report
- [ ] A basin crossing a state line (try the MT/WY line near 45.0, -108.0) offers
      "Re-run with WY"

## Last run: 2026-11-01 (Playwright against `streamlit run`, Chrome 1400x1300)

Delineate, live: right click at 46.93, -113.97 -> "Delineate (basin only)" showed the
"Delineating with StreamStats" chip, then drew the basin and fitted the map to it (zoom 12.5),
with "Basin delineated: 1.6 sq mi. Press Estimate for flood quantiles." under the map, the
GeoJSON download, and no quantile table; no console errors. (The point snaps to a small
tributary, not Rattlesnake Creek itself.) Estimate and "Re-run with WY" still unchecked:
`ss-hydro` returned 502 on every attempt that day, while `ss-delineate` answered in about 12 s.

## Last run: 2026-10-31 (Playwright against `streamlit run`, Chrome 1400x1300)

All items above checked except the two marked here:

- Delineate and Estimate: the page flow ran (menu -> spinner -> result area) but StreamStats'
  `ss-hydro` returned 502 for every point that day, so the page showed "StreamStats request
  failed ... after 3 attempts" instead of a basin. The basin drawing itself was checked by
  sending the component a polygon directly. Re-check when StreamStats is up.
- Re-run with WY: covered by `test_other_states_offered_for_a_two_state_basin`, not live
  (same outage).

Measured: first map paint 1.37 s after a cold load of `?page=ungaged`; left click to filled
inputs 0.07 s; style switch 0.12-0.16 s (one Streamlit round trip).

## Gage page (`?page=gage&site=12340500`)

- [ ] Daily mean flow chart draws the whole record, log scale; red dots are the annual peaks;
      the strip under it shows the record's shape
- [ ] Dragging across the strip zooms the chart to that period (axis reads "Apr 1979"...) and
      the flow axis fits it; dragging the shaded box pans; double-click resets
- [ ] Hovering reads out "Jun 10, 2008: 10,500 cfs" in the top-left corner; recent days add
      "(provisional)" and draw in orange
- [ ] "Flow axis: linear" under the chart switches scale and keeps the zoom
- [ ] "Last 10 years" and "Last water year" zoom the chart, with dashed water-year lines
- [ ] "Daily values (CSV)" and "Annual peaks (CSV)" download
- [ ] "Open in Bulletin 17C (Gaged page)" opens a new window that downloads the site and runs
      Bulletin 17C by itself; the gage page stays open
- [ ] Map over Flathead Lake (47.9, -114.0): zoom 6.5 reads "Flathead L.", "L. Pend Oreille";
      zoom 8.5 reads "Flathead Lake", "Flathead River"

Last run 2026-10-31 (Playwright, Chrome 1400x1300): all eight pass, no console errors.
