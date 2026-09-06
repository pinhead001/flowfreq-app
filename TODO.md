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

## Open

- [ ] **`plot_peak_timeseries`'s return-period lines and max-peak annotation still need to
      move to the library** (`flowfreq/freq_plot.py`) before this app's copy can be deleted --
      tracked on the library side in `flowfreq/TODO.md`'s Follow-ups section. Do not delete
      the local copy until that lands and this app's pin moves past it; switching to the
      library's `plot_peak_flows_with_thresholds` today would lose those two features. Not
      touched this session, per the coordinator's explicit non-goal.
- [ ] **Branch not yet merged or pushed.** `bump-flowfreq-0.4.0` is now three commits ahead of
      `main` (the original pin bump plus this session's doc/import/test fixes), still local
      only. Merging into `main` and pushing to `origin` is the coordinator's call, once the
      cross-repo sequence (library lanes land -> tag -> this bump) is confirmed complete
      across all four lanes.

## Found already in progress, not yet landed (as of Phase 0, now folded into "Resolved" above)

- **Local branch `bump-flowfreq-0.4.0`** already bumped `requirements.txt` to `v0.4.0` before
  this session started. This session verified `make check` is green against that pin with
  no unexplained numeric drift (see "Resolved" above) -- the pin bump itself needed no
  correction, only the doc/import follow-through it implied.

## Status snapshot (2026-09-05, end of session)

- `origin/main` tip: `a41b918` ("Merge pull request #2 from pinhead001/windows-friction"),
  unchanged this session.
- Local branch `bump-flowfreq-0.4.0`: started at `4c8a69f` ("bump flowfreq pin to v0.4.0"),
  now ahead of that with this session's commits (CLAUDE.md fix, import switch, TODO.md
  update). Still not pushed to `origin`; not merged into `main`.
- `flowfreq` pinned at `v0.4.0` in `requirements.txt`, and now actually installed in the
  active environment (was still 0.3.0 at the start of this session).
