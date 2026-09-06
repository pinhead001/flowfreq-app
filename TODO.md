# TODO — flowfreq-app

This repo has no standing TODO.md; its work is defined by `flowfreq/TODO.md`'s "Downstream"
and "Follow-ups" sections plus drift found here. Written 2026-09-05 during Phase 0 of a
coordinated two-repo session; see `flowfreq/TODO.md` for the library-side counterpart.

## Open

- [ ] **`CLAUDE.md`'s pinned-dependency quote is stale.** It says
      `flowfreq @ git+...@v0.3.0`; `requirements.txt` (on the local `bump-flowfreq-0.4.0`
      branch, see below) already pins `v0.4.0`. Fix the doc to match the pin, not the other
      way around.
- [ ] **`streamlit_app.py`'s import of `plot_frequency_curve_streamlit` should switch to
      `plot_frequency_curve`.** It survives in `flowfreq.freq_plot` only as a module-level
      alias (`freq_plot.py:554`) kept for exactly this transition; the current name is
      `plot_frequency_curve`.
- [ ] **`make check` needs to pass against the bumped pin.** The active environment still has
      `flowfreq==0.3.0` installed (`pip show flowfreq`, 2026-09-05) even though
      `requirements.txt` now names `v0.4.0` -- a reinstall is needed before `make check` means
      anything here. The 0.4.0 station-skew fix changes reported discharges (per
      `flowfreq/TODO.md`'s Downstream item), so expect the app's own numbers to move and
      confirm that's the only thing that changed, not a new failure.
- [ ] **`plot_peak_timeseries`'s return-period lines and max-peak annotation still need to
      move to the library** (`flowfreq/freq_plot.py`) before this app's copy can be deleted --
      tracked on the library side in `flowfreq/TODO.md`'s Follow-ups section. Do not delete
      the local copy until that lands and this app's pin moves past it; switching to the
      library's `plot_peak_flows_with_thresholds` today would lose those two features.

## Found already in progress, not yet landed

- **Local branch `bump-flowfreq-0.4.0`** (current checkout, one commit ahead of `main`,
  not pushed to `origin`) already bumps `requirements.txt` to `v0.4.0`. This is the
  "Downstream" pin bump from `flowfreq/TODO.md` -- already done in substance, just not
  merged or pushed. Verify identical numbers against the pre-bump app (per the library
  TODO's instruction) before merging, since a difference would be a defect, not the change
  landing as expected.

## Status snapshot (2026-09-05)

- `origin/main` tip: `a41b918` ("Merge pull request #2 from pinhead001/windows-friction").
- Local branch `bump-flowfreq-0.4.0`: `4c8a69f` ("bump flowfreq pin to v0.4.0"), one commit
  ahead of `main`, not on `origin`.
- `flowfreq` pinned at `v0.4.0` (tag exists on the library's remote).
