# The development cycle, as one target per thing you actually want.
#
# `make check` is the gate: it lints, then runs every test. There is nothing to serve and
# nothing to screenshot — this project generates data and stops. The front end it used to
# build moved to the `webxp` repository on 2026-11-09, and the eighteen scripts that drove
# a browser went with it, along with `serve`, `verify`, `shot` and the five `gates`.
#
# `make build` writes eight JSON artifacts into site/. A consumer commits them as static
# files; `scripts/refresh_showup.py` over there performs the copy, and `--check` reports
# when its copy is behind this one.
#
# uv manages the toolchain; nothing here needs a pre-activated virtualenv.

.DEFAULT_GOAL := help
.PHONY: help setup build test lint fmt check clean fetch fetch-calendar

help: ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## install the toolchain and dev dependencies
	uv sync

fetch: ## refresh the upstream cache (~9 min cold; skips fresh sources)
	uv run showup fetch

fetch-calendar: ## refresh just the daily-changing calendar
	uv run showup fetch --only calendar --force

build: ## generate the eight JSON artifacts into site/
	uv run showup build

lint: ## ruff check and format check
	uv run ruff check .
	uv run ruff format --check .

fmt: ## apply ruff formatting
	uv run ruff format .
	uv run ruff check --fix .

# COVERAGE_FILE is per-process: two suites in one worktree otherwise share the default
# .coverage and overwrite each other, which reports a wrong total while every test passes.
test: ## every test (no network, no browser)
	COVERAGE_FILE=.coverage.$$$$ uv run pytest -m "not upstream"
	@rm -f .coverage.*

check: ## the gate: lint + test
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test

clean: ## remove build output
	rm -rf site site.building .pytest_cache .ruff_cache .coverage
