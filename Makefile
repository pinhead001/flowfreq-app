# Developer entry points. CI calls these same targets, so what you run locally
# and what the build runs cannot drift apart.

PYTHON ?= python
PKGS := . tests/

PYTEST := $(PYTHON) -m pytest

# Both of these are set with target-specific `export` rather than inline as
# `VAR=1 command`, which is shell syntax cmd.exe does not understand -- make
# itself puts them in the recipe's environment, so the Makefile works on
# Windows as well as Unix.
#
# PYTHONSAFEPATH=1 stops Python prepending the working directory to sys.path,
# which is what the `pytest` console script does and `python -m pytest` does
# not. Without it a local run can pass while CI fails on imports.
#
# PYTHONUTF8=1 makes Python use UTF-8 regardless of the platform's locale.
# streamlit_app.py contains a non-ASCII character, and on a Windows console
# isort cannot encode it to cp1252 -- it then reports "Unable to parse file"
# and *skips the file*, so `isort --check` passes without having checked the
# one file that matters. Linux CI defaults to UTF-8 and never sees it.

.DEFAULT_GOAL := help
.PHONY: help check lint fmt test clean clean-verify run

help:  ## Show this help
	@awk -F':.*?## ' '/^[a-z-]+:.*## /{printf "  %-8s %s\n", $$1, $$2}' Makefile

check: lint test  ## Everything CI checks, in CI's order

lint: export PYTHONUTF8 := 1
lint:  ## Formatting check (does not modify files)
	$(PYTHON) -m black --check --diff $(PKGS)
	$(PYTHON) -m isort --check-only --diff $(PKGS)

fmt: export PYTHONUTF8 := 1
fmt:  ## Apply formatting
	$(PYTHON) -m black $(PKGS)
	$(PYTHON) -m isort $(PKGS)

# Importing streamlit_app.py executes the whole script in Streamlit's bare
# mode, so this exercises the app end to end short of a button press.
test: export PYTHONSAFEPATH := 1
test:  ## Run the suite as CI does
	$(PYTEST) tests/

clean:  ## Remove test and build artifacts
	rm -rf .pytest_cache .mypy_cache build/ dist/ *.egg-info
	find . -name "__pycache__" -type d -print0 2>/dev/null | xargs -0 rm -rf

# A stray flowfreq/ directory containing nothing but __pycache__ -- left over
# from before the split removed the package -- was enough to make isort classify
# flowfreq as first-party and pass `isort --check` locally while CI, with a
# clean checkout, failed on the same file and the same isort version. Every file
# in it was gitignored, so `git status` reported a clean tree throughout.
# known_third_party in pyproject.toml fixes that specific case; this target
# closes the general one.
clean-verify: clean  ## Wipe every artifact, then run the full gate
	$(MAKE) check

run:  ## Serve the app locally
	streamlit run streamlit_app.py
