# TODO — flowfreq-app

This repo has no standing TODO.md; its work is defined by `flowfreq/TODO.md`'s "Downstream"
and "Follow-ups" sections plus drift found here. Written 2026-09-05 during Phase 0 of a
coordinated two-repo session; see `flowfreq/TODO.md` for the library-side counterpart.
Updated later the same day once the four items below were worked through on
`bump-flowfreq-0.4.0`.

## Resolved this session

- [x] **`CLAUDE.md`'s pinned-dependency quote was stale.** Fixed the "The pinned dependency"
      section to quote `flowfreq @ git+.../flowfreq@v0.4.0`, matching `requirements.txt`. The
      pin itself was already correct; only the doc needed the edit.
- [x] **`streamlit_app.py`'s import of `plot_frequency_curve_streamlit` switched to
      `plot_frequency_curve`.** Updated the `from flowfreq.freq_plot import ...` line and both
      call sites (the on-page frequency-curve plot and the export-to-ZIP path). Updated
      `tests/test_streamlit_app.py`'s `WIRED_CALLABLES` tuple to check for `plot_frequency_curve`
      instead of the old alias name. `freq_plot.py`'s `plot_frequency_curve_streamlit` alias is
      no longer referenced anywhere in this repo (confirmed by grep of the tracked tree; the
      old name still shows up under `.claude/worktrees/agent-*`, but those are other agents'
      untouched worktree copies, not files this repo's tooling lints or tests).
- [x] **`make check` passes against the bumped pin.** Reinstalled dev tooling from
      `requirements-dev.txt` (black 24.10.0, isort 5.13.2, pytest 7.4.4 -- by version, not by
      name) and reinstalled runtime deps from `requirements.txt`, which pulled `flowfreq`
      0.3.0 -> 0.4.0 (`pip show flowfreq` now reports 0.4.0). `make check` (black --check,
      isort --check-only, pytest) is green: 28 tests pass, no diffs.
      No numeric test values needed updating. Checked deliberately, not assumed: every test
      in this repo that touches FFA-shaped numbers (`tests/test_ffa_export.py`,
      `tests/test_ffa_runner.py`) builds its own mock `ffa_result`/parameter dict rather than
      calling `flowfreq.workflow.run_ffa` on real peak data, and
      `tests/test_streamlit_app.py`'s `TestPilfOverrideWiring` tests exercise
      `plot_peak_timeseries` (a plotting function, this repo's own code) with fixture peaks
      but assert only legend text, not computed discharges. So the 0.4.0 station-skew fix --
      which does change reported discharges per `flowfreq/TODO.md`'s Downstream item -- has
      nothing to shift in this repo's suite; the app is exercised end-to-end for wiring
      (`test_app_imports`, `test_wired_entry_point_resolves`) but never asserts a specific
      flowfreq-computed number. That is consistent with `CLAUDE.md`'s "no analysis code here"
      framing: the numeric behavior lives in, and is tested by, the library repo.

## Resolved (session continued after v0.5.0/v0.6.0/v0.6.1 landed on the library)

- [x] **Pin bumped to `flowfreq@v0.6.1`** (through `v0.5.0` and `v0.6.0` first, as each landed
      on the library). `requirements.txt` and `CLAUDE.md`'s pin quote both updated;
      `pip install -r requirements.txt --upgrade` confirmed `flowfreq==0.6.1` actually
      installed, not just declared.
- [x] **`plot_peak_timeseries` deleted; `streamlit_app.py` now calls
      `flowfreq.freq_plot.plot_peak_flows_with_thresholds` directly.** All four features the
      app's copy had (return-period lines, max-peak annotation, PILF/MGBT hollow-bar
      censoring, linear/log toggle) landed on the library function across `v0.5.0`/`v0.6.0`/
      `v0.6.1` before this switch, so nothing was lost. `lp3_params` is built from
      `mean_log`/`std_log`/`skew_weighted` (same triple the app's old `estimate_ri_from_lp3`
      calls elsewhere already use) whenever the user wants either return-period lines or the
      max-peak estimate; `return_periods` uses the user's `show_quantile_lines` multiselect
      (falls back to the library's own default set only when that's empty but the max-peak
      annotation is still wanted, a minor edge-case behavior change from before -- previously
      no lines would draw in that combination). `mgbt_threshold`/`mgbt_threshold_source` carry
      the existing PILF-override wiring across unchanged. `estimate_ri_from_lp3` itself was
      NOT touched -- still used at its two other call sites (frequency-curve max-flow label,
      ZIP export).
- [x] **Numeric/visual equivalence checked, not assumed.** The library's analytic reference
      lines were verified against `run_ffa`'s actual `quantile_df` on both a censored and an
      uncensored fixture before the v0.6.1 release (0.0% diff, see `flowfreq/TODO.md`); this
      session additionally rendered a real figure with app-shaped inputs (Big Sandy, PILF
      override, linear y-axis, three return periods) and confirmed it visually -- hollow bars
      below the threshold line, correct dotted reference lines and labels, correct max-peak
      annotation, correct title format.
- [x] **`make check` green** with the three rewired `TestPilfOverrideWiring` plot tests
      (updated to call `plot_peak_flows_with_thresholds` with its new parameter names) and a
      new `WIRED_CALLABLES` entry for it: 29 passed.

## Open

- [ ] **Branch not yet merged or pushed.** Still local only, now several commits ahead of
      `main` (pin bump through v0.6.1, doc/import/test fixes, the plot_peak_timeseries
      deletion and rewiring). Merging into `main` and pushing to `origin` is the user's call.

## Found already in progress, not yet landed (as of Phase 0, now folded into "Resolved" above)

- **Local branch `bump-flowfreq-0.4.0`** already bumped `requirements.txt` to `v0.4.0` before
  this session started. This session verified `make check` is green against that pin with
  no unexplained numeric drift (see "Resolved" above) -- the pin bump itself needed no
  correction, only the doc/import follow-through it implied.

## Status snapshot (2026-09-07, session continued)

- `origin/main` tip: `a41b918` ("Merge pull request #2 from pinhead001/windows-friction"),
  unchanged this session.
- Local branch, renamed `bump-flowfreq` (was `bump-flowfreq-0.4.0`, then `-0.5.0` -- dropped
  the version from the name since it kept needing another bump as the library gained the
  features this migration needed). Still not pushed to `origin`; not merged into `main`.
- `flowfreq` pinned at `v0.6.1` in `requirements.txt` and `CLAUDE.md`, and actually installed
  in the active environment (confirmed via `pip show flowfreq`).
