# Changelog

All notable changes to the FlowFreq app are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Bumped flowfreq to v0.10.1

The pin moves from v0.7.0 to v0.10.1 (library release notes: v0.8.0, v0.9.0, v0.10.0, v0.10.1). v0.10.1 reads site info from the Water Data API and accepts `pd.NA` peak codes, so the app's workarounds for both are gone.
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
  or Streamlit secret) to raise it. The legacy NWIS site service, still used for site info,
  returned 503s on 2026-10-03; a failure there no longer affects the download. The site name
  and drainage area fall back to the Water Data API, and the daily record is requested in
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
