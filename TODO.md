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

## Basin map follow-ups (spec: `docs/superpowers/specs/2026-10-30-basin-map-design.md`)

- **Option B, cross-state comparison.** When the delineated basin touches more than one
  jurisdiction, run `estimate_at_site` once per state and show the results side by side
  (tabs), so the two states' equations can be compared for the same basin. One
  StreamStats call per state; the overlap chooser and downloads need to work per state.
  The map ships with option A: default to the clicked state, one-click re-run for the
  others.
- **Skew-region overlay.** HUC fill coloured by Bulletin 17C regional-skew region from the
  library's `regional_skew_hucs.csv`. Needs HUC geometry; only worth doing if that is
  cheap (a small bundled file or a light service), otherwise drop.
- **Live re-check of Delineate/Estimate on the map.** StreamStats' `ss-hydro` returned 502
  everywhere on 2026-10-31, so the live path from the context menu to a drawn basin was not
  seen end to end (the component draws an injected polygon correctly; the page shows the
  outage as an error). Re-run the two unchecked items in `docs/map_manual_checks.md`.
- **Library: a delineate-only call that skips `ss-hydro`.** The map's *Delineate* uses
  `delineate_and_get_characteristics`, which always calls `ss-hydro` for characteristics
  although the polygon comes from `ss-delineate`. A polygon-only path in flowfreq would make
  Delineate faster and immune to `ss-hydro` outages like the one above. Library work.
- **Style switch without a rerun.** Switching DEM/Night/Green costs one Streamlit round
  trip (0.12-0.16 s measured). Map-side buttons that restyle locally and report the choice
  back would make it instant.
- **Spec 2, the gage page.** `?page=gage&site=NNNNNNNN`, linked from the map's gage
  popups: site header, period of record for daily and peak flows via
  `flowfreq.waterdata`, "Run Bulletin 17C on this site", then summary hydrograph, raster
  hydrograph and data-access links. Brainstorm after the map spec is approved.
