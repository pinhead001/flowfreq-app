# Changelog

All notable changes to the FlowFreq app are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Ungaged page: the estimate as a frequency curve, with a gage's fit over it

An estimate is now drawn as well as tabulated: flow on a log axis against annual exceedance probability on a
normal-probability axis, the regression's quantiles joined by a line with its prediction interval as a band (where
the equations publish one). Where the point is within 1 km of a gage in flowfreq's catalog, the page names the gage,
its distance and both drainage areas, and **Overlay the fit** downloads that gage's peaks and lays its Bulletin 17C
curve and 90-percent confidence limits over the regression. The fit is the Flow Frequency page's default one, the
same the gage page draws; nothing is downloaded or fitted until the button is pressed, and a fit that is refused (a
regulated record, no published skew) says so under the regression curve. The two curves differ in colour, dash and
point shape.

### Ungaged page: estimate from basin characteristics you enter

A "Basin characteristics (no StreamStats)" form on the ungaged page takes a region and the characteristics its
equations read, with each one's units and calibrated range, and runs flowfreq's `estimate_from_characteristics`. It
opens by default for Florida, Michigan and Nebraska, where StreamStats has no stream grid, and StreamStats' refusal
there points to it. It needs flowfreq 0.26 and stays hidden on an older pin.

### Ungaged page: says when StreamStats is not answering

An outage or a refusal used to show only after **Delineate** or **Estimate** was pressed, as a failed request.
The page now asks StreamStats one small question when it opens (the NSS region list: one request, one try, a
4-second wait) and warns above the map when the answer is a refusal (HTTP 401, 403 or 429), an error, or none,
saying which, when it was checked, and that the basin-characteristics form still works. The answer is kept for
10 minutes for every session, so the check does not add to the load on a server that is turning this one away;
a request of the page's own that goes the other way has the next run check again. The check reaches the host
the pour-point snap and the NSS services are on, not the per-region delineation servers, so an outage of one
of those alone still shows only when the request fails.

### Ungaged page: names the set the library chose

Where sets overlap and the library picks one by a stated limit or preference, the page now names it,
says why, and lists the sets not used. Before, this appeared only in the full report.

### Gage page: an outage of the basin outline or the dam inventory is waited out once

The stationarity screen looks for dams in the gage's basin: the outline from USGS NLDI, the dams from the
National Inventory of Dams. When either could not be had, every rerun of the page (a slider, a tab) asked again
and waited again, up to 60 seconds for NLDI and three tries at an 82 MB download for the inventory. A failure
is now remembered for 5 minutes: the same note comes back at once, and says when the page tries again. The
outline is remembered per gage, the inventory for every gage.

### Shorter network errors

- A failed web request reads as one line naming the service -- "StreamStats request failed: 502 Bad Gateway from streamstats.usgs.gov", "could not connect to api.waterdata.usgs.gov" -- instead of quoting the whole URL with its query string. The full text goes to the log. Applies to the Ungaged page's Delineate and Estimate, and to the Flow Frequency page's regional-skew lookup, peak download and processing errors.

### Pages have their own addresses, and a point has a link

- Each page has its own address: `/` (Flow Frequency), `/ungaged` and `/gage?site=NNNNNNNN`. The pages are chosen
  from a menu at the top of the sidebar, which replaces the **Page** radio, and the browser's Back and Forward
  buttons now move between them. Links in the older form (`?page=ungaged`, `?page=gage&site=`,
  `?page=flowfrequency&site=&run=1`) still work: they are redirected to the page's own address.
- The Ungaged page offers a **Link to this point** in the sidebar once a point is set, e.g.
  `/ungaged?lat=36.040000&lon=-88.230000&state=TN`. Opening it fills the point and the jurisdiction, zooms the map
  there and runs the estimate. The link carries the point and the jurisdiction only, not the AEPs or the snapshot
  and extrapolation switches. Moving the point takes the link out of the address bar.
- The gage page opened without a site (the browser's Back button returns to `/gage` without one) shows the gage
  this session last opened.
- On a phone-width screen the map's style buttons (DEM, Night, Green) sit below the jump buttons instead of over
  them.
- Needs Streamlit 1.55 or later (`requirements.txt` says so).

### Page switching keeps your place

- The Flow Frequency page's gage number and the Ungaged page's point survive a trip to another page: a gage number typed, or filled in from a gage page's Bulletin 17C link, is still there after visiting the Ungaged page.
### Ungaged page: cautions about extrapolation and marks it

Ticking 'Allow extrapolation' now shows a caution before anything runs, and a refusal says what ticking it means
rather than only how to proceed. An extrapolated result carries a warning naming the AEPs and the inputs outside
the calibrated range, the status line says so, and a comparison names the states affected. The table's column and
the report's caveat already recorded it.

### Ungaged page: a caution near a border where two states' equations disagree

flowfreq measured, at gages within 20 km of each state line, how far the neighboring state's equations run from
the home state's on the same basins. On 17 borders the difference is systematic: Connecticut's equations give a
median 2.39 times Rhode Island's at the 1 percent AEP on Rhode Island basins near the line, for one. An estimate
at a point within 20 km of such a neighbor now says so above the result: how far the other state is, what was
measured, and which state's equations sat nearer the at-site Bulletin 17C fits. Nothing is adjusted. Distances
come from the bundled state outlines (`map_geo.states_within`), which are simplified, so they are good to a
kilometre or two. It needs flowfreq 0.27 (`flowfreq.regression.border_offsets_between`) and stays hidden on an
older pin.

### Basin map: back to the point after a basin zooms out

A delineated basin already zooms the map out to its whole extent. Two buttons now appear under the jump buttons
whenever a basin is shown: "Back to point" returns to the clicked point (or StreamStats' snapped pour point) at the
zoom you clicked from, at least stream level, and "Whole basin" zooms out again.

### Gage page: the fitted curve as a download, one request fewer, a year axis that stops at the record

- **Fitted curve (CSV)** under the Bulletin 17C curve downloads the fit's quantile table (flow and its
  90-percent confidence limits at each return interval, unrounded) as `<site>_b17c_curve.csv`. With the daily
  values and annual peaks buttons already at the foot of the page, that is the three downloads the page listed
  under "Coming to this page", so that note is gone.
- The annual peaks no longer ask USGS for the monitoring-location record a second time: the page already has
  the name, area and location from its own site lookup. A gage page view makes one request fewer.
- The annual-peak chart's year axis runs from the year before the first peak to the year after the last. Left
  to round itself it ran to the next round number, 2040 for a record that ends in 2025, with empty space to the
  right of the bars. A record of a few years gets whole-year ticks only.

### Gage page: dams and impervious cover beside a change point

- When the stationarity screen finds a change point, the gage page lists the dated basin changes
  (`stationarity.basin_change_events`): each National Inventory of Dams dam holding at least 10% of the
  basin's NID storage, at its completion year, and the year half of that storage was in place. The table
  gives each one's distance from the change point and marks those within 5 years as candidate causes.
  They are drawn as dotted green lines on the peak chart, named in the change-point flag, and passed to
  the stationarity report downloads.
- The basin is the USGS NLDI basin of the gage (NHDPlus catchments upstream), not a StreamStats
  delineation, so dams need no StreamStats request. The NID is downloaded once per server and cached.
- Impervious cover (the NLCD epoch in which it reached 5%) needs StreamStats basin characteristics, so it
  is requested only with a "Check impervious cover (StreamStats)" button. Without it, or when StreamStats
  fails or refuses, the page says so and shows the dams alone. Records with no change point make none of
  these requests.

### Gage page: summary hydrograph, flow-duration curve, stationarity report

- A summary hydrograph (daily flow percentiles by day of the water year,
  `Hydrograph.get_summary_stats`) and a flow-duration curve
  (`regime.flow_duration_curve`, 0.1-99.9 percent) under the daily chart. Both use a log
  axis unless the drawn flows reach zero.
- The library's one-page `stationarity_report` of the annual peaks, as Markdown and PNG
  downloads under the stationarity flags. Its event-count trend uses peaks over a
  threshold from the daily record: two events a year, or one where two would pull the
  threshold below the 75th percentile of daily flow (a snowmelt river).

### Gage page: the Bulletin 17C curve in place

- **Draw the Bulletin 17C curve** on the gage page fits the annual peaks and draws the frequency
  curve there, under the stationarity screen, without leaving the page: the fitted LP3 curve with
  its 90% confidence limits and the peaks at their plotting positions on an AEP axis, the
  frequency table in an expander. It is the Flow Frequency page's own analysis, not a second
  one: the same `run_site_ffa` call with the page's default settings (published regional skew,
  NWIS peak codes applied, regulated gages refused, MGBT, the whole record), the same figure
  and tables. A failed or refused fit shows the Flow Frequency page's message; a regulated
  gage's hint says to tick **Analyze regulated gage** on the Flow Frequency page, which
  **Open in Bulletin 17C** still opens for other settings and year ranges.
- Nothing is fitted until the button is pressed (EMA takes about a second). The fit is cached
  per site and peak record for six hours, and the curve stays drawn on later reruns of the
  page. A failed regional-skew lookup is not cached.
- The Flow Frequency page's sidebar defaults, its frequency figure (display and ZIP export) and
  its frequency tables now come from `DEFAULT_FIT_SETTINGS`, `DEFAULT_SKEW_LABELS`,
  `frequency_figure` and `frequency_tables`, which the gage page uses too, so the two pages
  cannot drift apart. No change to what the Flow Frequency page shows.

### Map library and label glyphs served by the app

- MapLibre GL JS 5.6.0 and the Noto Sans Italic glyphs for the water labels are bundled in `map_component/` (`vendor/`, BSD-3 licence; `fonts/`, SIL Open Font License) instead of loading from unpkg.com and MapLibre's demo tile server. The map no longer depends on two outside hosts, one of them a demo service. The bundled files are byte-identical to the published ones (the same SRI hashes); a test checks the hashes and that the glyph ranges cover every bundled name.

### Gage page: raster hydrograph

- A raster hydrograph under the summary hydrograph: every day of the daily record as a
  cell, one row per water year (earliest at the top), October 1 to September 30 across,
  coloured by daily mean flow on a log scale (yellow dry to purple wet). Days with no
  published value stay blank; zero-flow days, which a log scale cannot place, are brown;
  provisional days are outlined in the daily chart's orange. Days sit on a fixed leap-year
  calendar, so February 29 has its own column (blank in other years) and a calendar date
  is in the same column every year. Drawn from the daily record the page already loads.

### Resizable period on the gage page; Flow Frequency page

- **Gage page:** drag either end of the box on the strip under the daily chart to lengthen
  or shorten the period shown. Dragging the box still slides it, and double-click still
  shows the whole record. A quick period (last year, 10 years ...) now opens as a box too,
  so its ends can be dragged. The chart is drawn by `vega_component`, a build-less
  vega-embed component (scripts from jsDelivr, pinned with SRI hashes). It patches the
  compiled Vega-Lite to add a grip at each end of the brush, which Vega-Lite itself cannot
  resize.
- **Gaged page renamed Flow Frequency.** `?page=flowfrequency` opens it; the old
  `?page=gaged` links still land there.
- **Flow Frequency page:** the y axis defaults to log (the "Per Plot" boxes start ticked
  too). The stationarity screen of the fitted peaks (`run_ffa`'s `stationarity`) is shown
  with the Bulletin 17C results, as on the gage page.
- Labels: the skew source *Unsourced fallback* is now *Nationwide (-0.302)* (still warned
  as having no located source), and *Analyze anyway (regulated gage)* is now *Analyze
  regulated gage*.

### Chart library served by the app

- The gage page's daily chart loads vega 6.4.0, vega-lite 6.4.1 and vega-embed 7.3.0 from `vega_component/vendor/` (BSD-3 licences alongside) instead of cdn.jsdelivr.net; the files are the published ones, with the same SRI hashes, which a test recomputes.

### Ungaged page: controls in the sidebar, progress you can see, the basin kept on failure

- The inputs, Estimate, the coverage toggle and the map-view buttons are in the sidebar, and the map is taller.
  "Back to point" and "Whole basin" now drive the map from the sidebar, shown whenever a basin is on it.
- While StreamStats works, the page shows a watershed tracing itself (delineation) and frequency bars rising
  (estimation), and says what is running: ss-delineate for the basin, ss-hydro for its characteristics, then the
  state's equations. The map's busy chip says the same.
- A failed Estimate at the point of an earlier basin keeps that basin on the map and says so. Estimate still asks
  StreamStats again, since only its ss-hydro service computes the characteristics.
- A StreamStats failure names the step that failed (delineation, basin characteristics or the NSS region lookup)
  and says it is the service, not the inputs.

### Delineate without ss-hydro

The map's *Delineate* uses `flowfreq.streamstats.delineate_watershed`: the polygon from
StreamStats' delineation service, without the ss-hydro basin-characteristics request. It is
one round trip shorter and keeps working when ss-hydro alone is down (it returned HTTP 502
for a day from 2026-10-30; Delineate at the Methow near Pateros still drew the 1,792 sq mi
basin). An *Estimate* after a *Delineate* at the same point now delineates again, since it
needs the characteristics. The "state StreamStats does not delineate" warning names the
state plainly.

### Gage page: period box in red in dark mode

Vega-Lite's grey brush and the blue grips disappeared against a dark page and the blue strip; in dark mode both are now red (`#ff4b4b`), and switching theme redraws the chart.

### Plain messages for StreamStats refusals (flowfreq v0.20.0)

Estimate and Delineate show a warning that says what to do, instead of the library's error,
when StreamStats refuses for a reason that is the point, the basin or the state:
- a point off the stream network: move it onto the stream (the StreamGrid layer from zoom 13);
- a basin StreamStats flags regulated: choose a point upstream of the dam or diversion;
- a state StreamStats does not delineate (FL, MI, NE): no point there can be delineated.

The library's own message is kept as the outcome's `detail`. Uses flowfreq v0.20.0's
`RegionNotDelineatedError` and `RegulatedDelineationError`.

### flowfreq v0.27.1

The pin moves from v0.27.0 to v0.27.1. Estimate and Delineate wait up to 200 seconds for StreamStats to delineate a
basin and to compute its characteristics, and no longer send either request again after a timeout. A large basin
that used to fail after three 60-second tries now answers on the first, or fails once after 200 seconds. This
finishes the change USGS asked for in flowfreq issue 365.

### flowfreq v0.27.0

The pin moves from v0.26.0 to v0.27.0. Existing calls still work, but an estimate can change. What it brings the app:

- **StreamStats region lookups are gentler**: an NSS `bylocation` call waits up to 200 seconds, is never retried
  after a timeout, and runs one at a time. This is the fix USGS asked for after blocking an address (flowfreq issue
  365), so an Estimate on a slow basin can take longer before it answers.
- **Twelve more states average a basin spanning two regions in flow**, as their reports do (AZ, CA, CO, FL, GA, IA,
  MT, NC, NJ, NV, NY, SC), so such an estimate rises a little. A Montana basin weighting the Northwest region with
  the Northwest Foothills carries a caution in its advisory at AEPs of 4 percent and rarer.
- The library gains `flowfreq.regression.border` (the border caution of app #52 needs it), `summarize_peaks` and
  `record_years` (the gage page still uses its own copies), and report building (`flowfreq.reporting`), which the
  app does not use.

### flowfreq v0.26.0

The pin moves from v0.25.0 to v0.26.0. Existing calls still work, but an estimate can change. What it adds for the app:

- **The characteristics form** (app #45) switches on: Florida, Michigan and Nebraska, and any basin StreamStats can't
  delineate, can be estimated from characteristics the user enters.
- **Summary hydrograph dates** are right from March on: the library's day of the water year now has 366 days, with
  February 29 its own.
- **South Dakota, Wyoming and Kentucky** basins spanning regions are averaged in flow, as their reports do; **New
  Hampshire and New York** use their drainage-area-only sets where they apply; **Illinois** urban intervals use the
  report's degrees of freedom.

### flowfreq v0.25.0

The pin moves from v0.24.0 to v0.25.0. Existing calls still work, but an estimate or a refusal can change. What it adds
for the app:

- **Texas** uses its regional sets before the statewide set, so fewer Texas sites ask for an equation set.
- **Louisiana's south**, where NSS locates no current region, gets the 1998 Non-Pine Hills equations with a caution and
  no interval, instead of no estimate.
- **Maryland** estimates carry a caution that the 2023 Sixth Edition replaces these equations for state practice.
- **Iowa** above a CCM of 3.87 uses the drainage-area-only set instead of refusing, and **AL and TN** intervals are
  sharper. The caption names a preferred set passed over for a missing characteristic.

### flowfreq v0.24.0

The pin moves from v0.23.0 to v0.24.0. Existing calls still work, but an estimate or a refusal can change. What it adds
for the app:

- **Indiana** selects its region at the point, as its report does. Sites that stopped on an overlap or on a neighboring
  region's range now return an estimate, and a basin on a region boundary can move.
- **Known-miss cautions:** estimates near Sweetwater Creek, OK, Little Cedar River, MN and White Bayou, LA carry a
  warning, through the advisory the page already shows.
- **The report** names the inputs outside the calibrated range in its extrapolation caveat.

### flowfreq v0.23.0

The pin moves from v0.22.0 to v0.23.0. Existing calls still work, but an estimate or a refusal can change. What it
adds for the app:

- **Delaware is verified,** making 51 of 56, with 5 that have none. The coverage map no longer shows a partial
  jurisdiction, and Delaware's estimates now use its verified set, with wider Coastal Plain intervals.
- **Arkansas's Mississippi Alluvial Plain set** reads the corrected slope, so its estimates can rise.
- **Fewer region choices:** AL at 5 mi2 or less uses Small streams, AR uses that alluvial plain set over region D
  where it covers the basin, and GA, NC and SC at 1 mi2 or less use the 2023 set up to 10 percent impervious and the
  2014 sets above it.

### flowfreq v0.22.0

The pin moves from v0.20.0 to v0.22.0, through v0.21.0. Existing calls still work, but an estimate or a
refusal can change. What it adds for the app:

- **Verified equations:** 50 of 56 jurisdictions are now verified, Delaware is partial and 5 have none,
  so the coverage map no longer shows a snapshot-only jurisdiction. `allow_nss_snapshot=True` returns the
  verified set rather than the snapshot, and its coefficients, limits and errors differ from NSS where the
  report does. The library's `docs/VERIFICATION_PLAN.md` says what verified rests on.
- **Fewer region choices:** more overlapping sets resolve without one, including Iowa, Connecticut, Maine,
  Vermont, Tennessee and Illinois, and sets whose stated limits exclude the basin. Those not used are listed
  in the full report. Urban and NRCS-regulated basins, and some others, still ask.
- **Karst:** StreamStats' karst warning no longer stops an estimate. It appears under Caveats in the full
  report.
- **Oregon and Montana:** Oregon interior basins resolve to Region 2A or 2B, and Montana estimates no longer
  stop on StreamStats' channel widths of 0.

### flowfreq v0.20.0

The pin moves from v0.19.0 to v0.20.0. Existing calls are unchanged. What it adds for the app:
- `run_ffa` results carry `stationarity`, the trend and change-point screen of the annual
  peaks (plain-language `flags`); the gage page shows the same screen (see Gage page).
- StreamStats failures no pour point can fix are their own errors:
  `RegionNotDelineatedError` (FL, MI and NE have no stream grid) and
  `RegulatedDelineationError` (a basin StreamStats flags regulated). Both are `ValueError`s,
  so the current handlers still catch them.
- Alaska ungaged estimates no longer need a region choice (the two statewide drainage-area
  classes are chosen by drainage area).

### Gage page

- **New page** at `?page=gage&site=NNNNNNNN`, opened from the map's gage popups: the site's name, drainage area, state, HUC and location; periods of record for daily flow and annual peaks (with the largest peak); a chart of the annual peaks on a true water-year axis (gaps in the record show), coloured by qualification code; **Open in Bulletin 17C (Gaged page)**, which opens the Gaged page in a new window and runs the download and Bulletin 17C there on arrival (`?page=gaged&site=&run=1`, once per session), leaving the gage page open; links to the USGS pages; CSV downloads of the daily values (with their approval codes) and the annual peaks. Site, daily values and peaks download in parallel (1.2 s instead of 5.0 s for 12340500, cold).
- **Daily mean flow chart** of the whole daily record: drag across the strip under it to zoom to a period of interest, drag the shaded box to move along the record, double-click to reset, or pick a quick period (whole record, last 10 years, last water year). Hovering reads out the day, its flow and its status (provisional, estimated, ice); provisional days are drawn in orange; annual peaks are red dots; dashed lines mark water years when under 15 years are in view; the flow axis fits the period in view. Log or linear from a switch inside the chart, so a zoomed period survives it. Missing days show as gaps. Lookups are cached for six hours and never raise: a failed or unknown site is reported on the page.
- **Stationarity screen** of the annual peaks, under the peak chart (flowfreq v0.20.0's `stationarity_screen`, the same screen `run_ffa` attaches): trend, change-point and variability flags in plain language, with candidate causes from the peak codes ("change point in 1963 ... regulation or diversion (peak code 5/6)"), and a dashed line on the chart at a significant change point. A record that screens clean says so; one under ten peaks says why it was not screened. Information only: the Bulletin 17C fit is unchanged.
- **Daily chart labels follow the span in view:** months up to two years ("Oct", "Nov", "Jan 2026"; *Last water year*), one "WY 2017" label per water year up to fifteen (*Last 10 years*), centred between the dashed water-year lines; the whole record keeps "Jan 1930". A brushed period of the same length labels the same way.

### Basin map on the Ungaged-site page

Draws the delineated watershed from `SiteEstimate.basin_geojson` (flowfreq v0.18.0). The
Streamlit floor rises to 1.40 (`st.segmented_control`).

- **Map above the inputs**, opening on CONUS with jump buttons to Alaska, Hawaii and the
  territories (PR/USVI, Guam/CNMI, American Samoa). Three styles: **DEM** (pixelated,
  banded grey shading, the early-USGS-DEM look), **Night** (city lights under blue-grey
  relief; the default under a dark theme) and **Green** (iridescent hillshade). The
  hillshade is computed in the browser from AWS Terrain Tiles.
- Rivers, lakes and hydrologic units, more detail with zoom: Natural Earth rivers and lakes
  (bundled, styled per mode) below zoom 10, USGS NHD streams from zoom 10, USGS WBD HUC2-HUC12
  throughout, all without baked-in labels. Water bodies are labelled by the map itself with
  their real names ("Gulf of Mexico"); `tools/build_hydro_geojson.py` holds the correction
  list. Rivers and lakes carry their full names, so Flathead Lake and the Flathead River no
  longer both read "Flathead"; where the full name does not fit its feature at the current zoom the map shows a short form ("Flathead R.", "L. Mead", "S. Fk. Flathead R."); names Natural Earth has damaged ("Rivire") are repaired. State and territory lines; an optional tint by equation coverage (verified / partial / snapshot).
- **StreamStats StreamGrid** from zoom 13: the cells that will snap and delineate, with a
  chip naming states that have no grid.
- **Streamgages** from zoom 8 as hollow triangles; a popup opens the gage page and the USGS monitoring-location page.
- **Left click** fills latitude, longitude and the jurisdiction under the point; nothing
  runs until Estimate. **Right click**: Delineate (basin only), Estimate (basin and
  quantiles), Copy lat/lon, Zoom to point. Typed coordinates move the pulsing marker.
- The basin and snapped pour point are drawn after Delineate or Estimate, with a
  **GeoJSON download**. A basin crossing into another served jurisdiction offers
  "Re-run with XX".
- `?page=ungaged` and `?page=gage&site=NNNNNNNN` open those pages directly.

### flowfreq v0.19.0

The pin moves from v0.18.0 to v0.19.0. Existing calls are unchanged. What it adds for the app:
- `flowfreq.streamstats.delineate_watershed`: the watershed polygon without the ss-hydro
  basin-characteristics request, for the basin map's Delineate action. It still works when
  ss-hydro alone is down (it returned 502 all night on 2026-10-31).
- Library-only additions the app does not call yet: `flowfreq.stationarity`,
  `flowfreq.naturalize`, monthly and duration transfer variance, and a more robust GLS fit.

### flowfreq v0.18.0

The pin moves from v0.17.0 to v0.18.0. Existing calls are unchanged. What it adds for the app:
- `SiteEstimate.basin_geojson`, the delineated watershed polygon, which the basin map needs.
- Ungaged estimates in Wyoming region 1 (outlet longitude taken from the pour point) and in
  Minnesota's Rainy River Basin (GC1775).
- Regional skew by hydrologic unit in NY, PA, VA, WV, MA, LA, KY, TN and Alaska. In Alaska,
  `regional_skew_for_site` now refuses a gage outside its skew area's drainage-area range
  ("use station skew").

### flowfreq v0.17.0

The pin moves from v0.16.0 to v0.17.0. The library's API is unchanged for the app. What
reaches the Ungaged-site page:
- GA, NC and SC equations parse (SIR 2023-5006).
- 32 LA, AR and MS equations now give prediction intervals.
- The region selector accepts a boundary basin's codes (`region=` with several codes).
- `region=` works in Wyoming and Nevada, where NSS locates no peak-flow region.

### Ungaged-site page, flowfreq v0.16.0

The pin moves from v0.15.0 to v0.16.0, which adds `flowfreq.estimate_at_site`.

- **New page: Ungaged site** (sidebar "Page" switch). Enter a latitude, longitude and
  jurisdiction; the basin is delineated with StreamStats and flood quantiles come from the
  offline regional regression library, with the regions used, basin characteristics, caveats
  and a Markdown report download. Each jurisdiction is labelled with its coverage
  (verified, partial, NSS snapshot, or none); NSS-snapshot sets need an explicit opt-in and
  show their advisory.
- **Overlapping equation sets.** Where NSS serves superseded and current equations side by
  side (Tennessee: GC344, GC2016, GC2020), the page offers them as a selector and re-runs
  with the chosen set; a refused choice shows the library's reason.
- `ungaged_ui.py` holds the page; `run_estimate` never raises and returns an error dict
  with a `kind`.

### Bumped flowfreq to v0.15.0

The pin moves from v0.7.0 to v0.15.0 (library release notes: v0.8.0 through v0.15.0). v0.10.1 and later read site info from the Water Data API and accept `pd.NA` peak codes, so the app's workarounds for both are gone.
What changes for someone using the app:

- **New default gages.** The single-gage default is now 12358500 (Middle Fork Flathead River
  near West Glacier, MT; GAGES-II reference); the multi-gage default is 12358500 and
  12449500 (Methow River near Pateros, WA). The old defaults, 09355500 and 11066460, are
  classified regulated (dam storage 607 and 2,033 days of runoff) and would be refused by
  the new regulation screen on a first run.

- **Skew source picker.** The two number inputs that presented -0.302 / SE 0.55 as a
  "nationwide default" are gone; Bulletin 17C has no such default. Choose instead:
  - *Published regional study* (the default): the gage is looked up with
    `flowfreq.regional_skew.regional_skew_for_site`, and the value, MSE and citation are
    shown with the results. Where no verified study covers the gage the fit is not run, and
    the message says why; nothing is substituted.
  - *Station skew only*: no regional weighting.
  - *Custom value*: a skew and standard error you enter.
  - *Unsourced fallback (-0.302)*: kept for comparison with old runs, labelled as having
    no source.
  The source is shown in the parameter table, the multi-gage comparison and the export.
- **NWIS peak codes applied.** Qualification codes now reach the analysis and are treated as
  peakfq treats them (code 7 historic; 3, O, 6 and C removed). An *Apply NWIS peak codes*
  checkbox (on by default) turns this off. The codes applied are listed with the results,
  and a year-range refit filters the codes with the same mask as the flows.
- **Regulation screen.** Each gage is screened with flowfreq's GAGES-II / peak-code
  classification. A regulated gage is refused with the reason, shown with that gage's
  results; *Analyze anyway (regulated gage)* fits it and records the override.
- **New data source.** Peaks and daily values (and IV, which the app does not use) now come
  from the USGS Water Data OGC API. Without a key it allows 1,000 requests/hour per IP; set `USGS_API_KEY` (environment
  or Streamlit secret) to raise it. The legacy NWIS site service, which the app used for site
  info, returned 503s on 2026-10-03. As of flowfreq v0.10.1 site info comes from the Water Data
  API, and a failure there does not affect the download. The daily record is requested in
  full rather than between the legacy service's POR dates. Those dates came from the first
  daily series in its catalog, which for 12449500 was water temperature, so that gage's daily
  record had been cut to 165 days in 2002.
- **Results move toward peakfq 8.1.0.** The library's EMA fixes (fixed-point iteration,
  near-zero-skew bounds, zero-flow years, perception thresholds and others) change fitted
  values slightly. "PILFs" is now peakfq's `gbnlow`, and MGBT's own count is shown beside it
  as "MGBT Outliers", in the table and the export.
- Station-skew-only fits no longer crash the peak plot and the max-peak annotation. These
  now use the skew the fit actually used (`skew_used`), because `skew_weighted` is empty
  when there is no regional skew to weight with.
- Fit errors are now shown with the gage's results. Before, they were shown only during the
  download, and the rerun that followed cleared them.

## [0.1.0]

First release as a standalone repository, split out of `pinhead001/hydrolib`.

### Changed
- The analysis code is now the separate
  [flowfreq](https://github.com/pinhead001/flowfreq) library, installed from a pinned tag.
  A library change reaches this app only when `requirements.txt` is bumped.
- Modules moved from `app/` to the repository root. Streamlit puts the script's own
  directory on `sys.path` and never the repository root, so the nested layout required a
  `sys.path.insert` hack to import its siblings; flattening makes the two the same
  directory and the hack is gone from all three files that carried it.
- `ffa_runner` is display formatting only. The analysis half it used to contain —
  `run_ffa`, `compute_skew_tables`, `build_skew_curves_dict` — moved into
  `flowfreq.workflow`, where a second consumer can reach it.

### Notes
- The app's version is a display string, not a release contract; it does not track the
  library's.
- Pre-split history is preserved in this repository and in the archived
  [pinhead001/hydrolib](https://github.com/pinhead001/hydrolib).
