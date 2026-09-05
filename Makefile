# Developer entry points. CI calls these same targets, so what you run locally
# and what the build runs cannot drift apart.

PYTHON ?= python
PKGS := . tests/

# PYTHONSAFEPATH=1 stops Python prepending the working directory to sys.path,
# which is what the `pytest` console script does and `python -m pytest` does
# not. Without it a local run can pass while CI fails on imports.
PYTEST := PYTHONSAFEPATH=1 $(PYTHON) -m pytest

.DEFAULT_GOAL := help
.PHONY: help check lint fmt test run

help:  ## Show this help
	@awk -F':.*?## ' '/^[a-z-]+:.*## /{printf "  %-8s %s\n", $$1, $$2}' Makefile

check: lint test  ## Everything CI checks, in CI's order

lint:  ## Formatting check (does not modify files)
	$(PYTHON) -m black --check --diff $(PKGS)
	$(PYTHON) -m isort --check-only --diff $(PKGS)

fmt:  ## Apply formatting
	$(PYTHON) -m black $(PKGS)
	$(PYTHON) -m isort $(PKGS)

# Importing streamlit_app.py executes the whole script in Streamlit's bare
# mode, so this exercises the app end to end short of a button press.
test:  ## Run the suite as CI does
	$(PYTEST) tests/

run:  ## Serve the app locally
	streamlit run streamlit_app.py
