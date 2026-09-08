# TODO — flowfreq-app

This repo has no standing TODO.md; its work is defined by `flowfreq/TODO.md`'s "Downstream"
and "Follow-ups" sections plus drift found here.

## Status (2026-09-08)

Everything this file previously tracked -- the pin bump through v0.6.1, the
`plot_peak_timeseries` deletion and switch to `flowfreq.freq_plot.plot_peak_flows_with_thresholds`,
and assorted doc/import fixes -- is merged to `main`. Not repeated here; see `git log` if the
session-by-session detail is ever needed.

- `flowfreq` pinned at `v0.7.0` in `requirements.txt` and `CLAUDE.md`, confirmed actually
  installed via `pip show flowfreq` rather than assumed from the pin alone.
- `make check` (black --check, isort --check-only, pytest) green: 29 passed, no diffs --
  verified at both v0.6.1 and v0.7.0, since v0.7.0 changes nothing this app's code path
  reaches (see `flowfreq/TODO.md`'s Downstream item for why).
- No open items right now. New drift goes here as it's found.
