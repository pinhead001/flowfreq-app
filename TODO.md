# TODO — flowfreq-app

This repo has no standing TODO.md; its work is defined by `flowfreq/TODO.md`'s "Downstream"
and "Follow-ups" sections plus drift found here.

## Status (2026-09-08)

Everything this file previously tracked -- the pin bump through v0.6.1, the
`plot_peak_timeseries` deletion and switch to `flowfreq.freq_plot.plot_peak_flows_with_thresholds`,
and assorted doc/import fixes -- is merged to `main`. Not repeated here; see `git log` if the
session-by-session detail is ever needed.

- `flowfreq` pinned at `v0.15.0` in `requirements.txt` and `CLAUDE.md`, confirmed actually
  installed via `pip show flowfreq` rather than assumed from the pin alone.
- `make check` (black --check, isort --check-only, pytest) green: 60 passed, no diffs --
  verified at v0.15.0 on 2026-10-25 (earlier: 29 passed at v0.6.1 and v0.7.0).
- No drift open right now. New drift goes here as it's found.

## Next steps (2026-11-01)

#25 (daily chart labels by span) is merged. Open PRs, each green in CI and independent of the
others; merge in any order. Each adds a
section at the top of CHANGELOG.md's Unreleased, so every merge after the first needs that
one-hunk conflict resolved.

- #27 page radio and gage number survive a page round trip; the page goes in the URL.
- #28 network errors name the service ("502 Bad Gateway from streamstats.usgs.gov").
- #29 MapLibre and the label glyphs served from `map_component/` (adds a root `.gitattributes`).
- #30 vega, vega-lite and vega-embed served from `vega_component/`. Once #29 and #30 are both
  in, delete #29's TODO line "Self-host the Vega bundles".
- #26 (another session): summary hydrograph, flow-duration curve, stationarity report.

Then, roughly in order of value:

1. **Estimate, live.** Delineate was checked live on 2026-11-01 (see
   `docs/map_manual_checks.md`); Estimate still fails because StreamStats' ss-hydro returns
   502. Re-run the Estimate and "Re-run with WY" checks when it is back.
2. **#24's resize grips in a browser.** The vega component draws (checked 2026-11-01), but
   dragging a grip to resize the period box has not been watched in a real browser.
3. **Browser Back** after an in-app page switch (below): `st.navigation`/`st.Page`. #27 made
   the radio and the URL agree; Back itself still does not rerun.
4. **`use_container_width` deprecation:** move to `width="stretch"` and raise the Streamlit
   floor from 1.40 (every chart in the app).
5. **Stationarity follow-ups:** the flags in the ZIP export and the multi-gage comparison;
   NID/NLCD basin events for attribution (needs the delineated basin).
6. **Library questions for flowfreq:** 02087500's 1968 change point is reported with no
   candidate cause although 45 of its peaks carry code 6 (`attribute_change_point`'s 5-year
   window?); `USGSgage.peak_summary()` to cut the gage page's repeated site lookup.
7. **Cosmetic:** the gage page's peak chart rounds its year axis out (to 2040 for Lees Ferry).

## Roadmap (agreed 2026-10-31)

One PR per phase, in this order. The follow-up entries below hold the detail.

1. **Map polish** (done 2026-10-31, branch `feat/map-polish`; one leftover: MapLibre logs a harmless
   AbortError when a style switch cancels terrain tiles still loading). Smaller gage symbols; style switch without a
   Streamlit rerun; the review's deferred minors: prepare the basin payload once per
   result, `maxzoom` on the coarse shade layer, parallel StreamGrid metadata, ordering
   guards on gage/grid responses, one fetch of `states.geojson`, rotation off, no context
   menu over gages, orb snaps back when Python rejects a click, one warning per malformed
   event, gage placeholder with a way back and a validated `site`, CLAUDE.md layout, the
   states build script checks its record limit and feature count.
2. **Real water-body names** (done 2026-10-31, branch `feat/water-names`). Find a label-free hydro source that keeps
   scale-dependent rivers and HUCs, then label water bodies ourselves.
3. ~~**Library delineate-only call**~~ Done 2026-10-31: Delineate uses `delineate_watershed`
   (flowfreq v0.19.0+), the polygon without `ss-hydro`.
4. **New features**: the gage page (v1 done 2026-10-31, branch `feat/gage-page`), cross-state
   comparison (option B, done 2026-10-31, branch `feat/review-polish`), then the skew-region overlay (spike on HUC geometry
   from the WBD service).

Outstanding outside the phases: the live Delineate/Estimate check once StreamStats is up.

## From the second review (2026-10-31), not yet done

- **Browser Back after an in-app page switch** leaves the URL and the page out of step until a
  refresh (Streamlit does not rerun on popstate). Fix properly with `st.navigation`/`st.Page`.
- **Sidebar page radio** recreates itself when the query params clear (its `index` flips);
  give it a key and set it from `?page=` once. A prefilled `?page=gaged&site=` is lost on a
  sidebar round trip.
- **Self-host MapLibre and the glyphs** next to `index.html` (the JS now carries an SRI hash
  and a load-failure message; the glyphs still come from MapLibre's demo server).
- **Gage page requests**: four USGS requests per view (`download_peak_flow` repeats the
  monitoring-location lookup). Library candidate: `USGSgage.peak_summary()`, which would also
  move `summarize_peaks`/`record_years` out of the app (CLAUDE.md: numbers belong in flowfreq).
- **Network errors** quote the service URL in full; fine for engineers, long on screen.

## Basin map follow-ups (spec: `docs/superpowers/specs/2026-10-30-basin-map-design.md`)

- **Skew-region overlay.** Spike 2026-10-31: feasible, not cheap. `regional_skew_hucs.csv` holds
  536 member/exclude rows at HUC2, 4, 8, 10 and 12 with per-state validity; a build-time WBD
  query per level plus simplification would give the polygons, but the rules must be drawn
  exactly as `regional_skew_at_huc` applies them, or the map would mislead.
- **Live re-check of Estimate on the map.** Delineate passed live on 2026-11-01; Estimate and
  "Re-run with WY" wait for StreamStats' `ss-hydro`, which still returned 502 that day.
- **Gage page, next.** Summary hydrograph and flow-duration curve from the daily record; raster hydrograph; the Bulletin 17C curve in place; direct data downloads. Done in `gage_ui.py`: site summary, periods of record, annual-peak chart, the zoomable daily chart, Bulletin 17C in a new window. Stationarity flags under the peak chart (v0.20.0). The screen with the Flow Frequency page's Bulletin 17C results. Not yet: the library's one-page `stationarity_report`, and NID/NLCD basin events for attribution (need the delineated basin).
- **Daily chart, from the 2026-10-31 evaluation: done** (hover readout with status, peak dots,
  in-chart log/linear keeping the zoom, quick periods, water-year lines, CSV downloads,
  provisional days in orange, parallel loading, `run=1` auto-run on the Flow Frequency page).
  Left over:
  - The log/linear switch is Vega's plain radio input, unstyled; a quick period resets it
    to log (it is a rerun).
  - Streamlit ignores a selection's starting value, so a quick period zooms the view
    without drawing the shaded box on the strip.
  - `st.altair_chart(use_container_width=...)` warns on Streamlit 1.63 (use `width=`); moving
    to `width="stretch"` needs the floor raised from 1.40. The app's other charts use it too.
