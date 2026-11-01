# Changelog

All notable changes to the FlowFreq app are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Gage page

- **New page** at `?page=gage&site=NNNNNNNN`, opened from the map's gage popups: the site's name, drainage area, state, HUC and location; periods of record for daily flow and annual peaks (with the largest peak); a chart of the annual peaks on a true water-year axis (gaps in the record show); **Run Bulletin 17C on this site**, which opens the Gaged page with the site filled in (`?page=gaged&site=`), in the same tab; links to the USGS pages. Lookups are cached for six hours and never raise: a failed or unknown site is reported on the page.

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
  list. State and territory lines; an optional tint by equation coverage (verified / partial / snapshot).
- **StreamStats StreamGrid** from zoom 13: the cells that will snap and delineate, with a
  chip naming states that have no grid.
- **Streamgages** from zoom 8 as hollow triangles; a popup links the gage page (a
  placeholder for now, `?page=gage&site=`) and the USGS monitoring-location page.
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
