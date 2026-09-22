# The development cycle, as one target per thing you actually want.
#
# `make verify` is the gate: it builds, lints, tests, then starts the real server
# and asserts against live responses. If it passes, the change is validated rather
# than assumed — which is the whole point of having it.
#
# uv manages the toolchain; nothing here needs a pre-activated virtualenv.

.DEFAULT_GOAL := help
.PHONY: help setup build serve test lint fmt check verify shot clean fetch open

PORT ?= 8000
ROOT ?= site

help: ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## install the toolchain and dev dependencies
	uv sync

build: ## build the static site into site/
	uv run showup build

serve: build ## build, then serve locally with the real security headers
	@echo "→ http://127.0.0.1:$(PORT)"
	uv run python scripts/serve.py --port $(PORT) --root $(ROOT)

open: build ## build and open the site in a browser
	@uv run python scripts/serve.py --port $(PORT) --root $(ROOT) & \
	sleep 1; open http://127.0.0.1:$(PORT); wait

lint: ## ruff check and format check
	uv run ruff check .
	uv run ruff format --check .

fmt: ## apply ruff formatting
	uv run ruff format .
	uv run ruff check --fix .

test: ## unit and contract tests (no network)
	uv run pytest -m "not upstream and not browser"

check: ## the fast gate: lint + test
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test

verify: build ## the real gate: build, lint, test, then assert against a live server
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory test
	uv run python scripts/verify.py
	@echo "verified."

shot: build ## screenshot the built site with headless Chrome
	uv run python scripts/shot.py

clean: ## remove build output
	rm -rf site site.building screenshots .pytest_cache .ruff_cache .coverage
