# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## Project Overview

The **FlowFreq** Streamlit web application: an interactive front end for USGS streamflow
retrieval and Bulletin 17C flood frequency analysis. It downloads peak-flow data, runs the
analysis, plots the frequency curve, and exports results as a ZIP.

**This repository contains no analysis code.** Every computation happens in the
[flowfreq](https://github.com/pinhead001/flowfreq) library, which this app installs as a
pinned dependency. If a fix belongs in the Bulletin 17C mathematics, the EMA implementation,
the USGS client, or the frequency plot, it belongs in that repository — not here. What lives
here is the Streamlit UI and the display formatting that serves it.

## Repository Layout

```
streamlit_app.py     the app; a top-level script, not a module with a main()
ffa_runner.py        display formatting: pandas frames of pre-formatted strings
ffa_export.py        ZIP export (PNG, CSV, LP3 parameters)
requirements.txt     runtime deps, including the pinned flowfreq tag
tests/fixtures/big_sandy.py   static USGS 03606500 data, copied from the library repo
```

Modules sit at the repository root rather than under `app/`. That is deliberate: Streamlit
puts the *script's own directory* on `sys.path` and never the repository root, so a nested
layout needs a `sys.path.insert` hack to import its siblings. Flattening makes the two the
same directory and the imports resolve with nothing added. **Do not reintroduce an `app/`
subdirectory** without also restoring that hack.

## The pinned dependency

```
flowfreq @ git+https://github.com/pinhead001/flowfreq@v0.3.0
```

A change in the library does not reach this app until that tag is bumped. When you need a
library change, land it there, tag a release, then bump this line — one edit, deliberate.
Never point it at `main`: a regression upstream would reach the deployed app with no warning.

`numpy`, `pandas`, `matplotlib` and `scipy` are declared even though `flowfreq` pulls them
in, because `streamlit_app.py` imports all four directly and a direct import should not lean
on a transitive dependency.

## Build & Development Commands

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pinned; see below

make check     # what CI runs: lint then test
make test      # importing streamlit_app.py runs the whole script in Streamlit's bare mode
make run       # serve locally at http://localhost:8501
make fmt       # apply black + isort
```

**Install the dev tooling from `requirements-dev.txt`, not by name.** This line used to
read `pip install black isort pytest`, and following it gets you whatever black is current
-- black 26 reformats `streamlit_app.py`'s footer that black 24, which CI pins, leaves
alone. You then "fix" a correctly formatted file and turn CI red. CI installs the same
file, so the pins cannot drift.

**On Windows.** Three things differ, all handled by the Makefile so `make check` behaves
the same as on Linux -- worth knowing if you run the tools directly:

- `make` is not installed by default (`winget install ezwinports.make`), and its recipes
  run through `cmd.exe`, which cannot parse Unix inline env-var syntax. Both variables
  below are therefore set with target-specific `export`, which make applies itself.
- `PYTHONUTF8=1` is required for `lint` and `fmt`. `streamlit_app.py` has a non-ASCII
  character; without UTF-8 mode isort cannot encode it to cp1252, reports "Unable to parse
  file", and **skips the file** -- `isort --check` then passes without having checked it.
- `PYTHONSAFEPATH=1` is required for `test`, for the `sys.path` reason described below.

**Reproduce CI faithfully.** `python -m pytest` puts the working directory on `sys.path`;
CI runs the `pytest` console script, which does not. `make test` sets `PYTHONSAFEPATH=1` to
match. `tests/__init__.py` is load-bearing for the same reason — because `tests` is a
package, pytest puts the repository root on `sys.path`, which is what resolves both
`tests.fixtures` and the flat `ffa_runner`. Deleting it passes locally and fails in CI.

Python 3.10 or newer; Streamlit sets that floor. The app itself is developed,
tested and deployed on **3.12**, pinned in `.python-version` — CI reads that file rather
than carrying its own literal, and `uv venv` reads it too, so a local environment matches
CI without anyone having to remember. Without it uv falls back to its own default and a
developer can silently end up on a different interpreter. Streamlit Community Cloud's
version is configured in the app's settings, not from this repository; it has to be kept
in step by hand.

## Conventions

- Run `black` and `isort` before every commit; settings live in `pyproject.toml` and match
  the library repo's exactly, so a file moved between them formats identically
- Type hints on all signatures; NumPy-format docstrings on public functions
- No bare `except:`; no `print()` — use `logging.getLogger(__name__)`
- Keep computation out of this repository. A function that returns numbers rather than
  formatted strings is a sign it belongs in `flowfreq.workflow`

## Testing

`tests/test_streamlit_app.py` imports the app, which in Streamlit's bare mode executes the
entire script body — every widget call and every library call reachable before the first
button press. Widgets return their declared defaults, so `download_data` is `False` and
nothing contacts NWIS. That makes a plain import a real check: it catches a stale import, a
`NameError` on an untaken branch, and the one that matters most here — an app call that no
longer matches a `flowfreq` signature after a version bump.

## Deployment

Streamlit Community Cloud, from `main`, entry point `streamlit_app.py`. See
`docs/vignette_streamlit_web.md`. The app makes no authenticated calls; USGS NWIS is public
and no secrets are needed.
