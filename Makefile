# The development cycle, as one target per thing you actually want.
#
# `make verify` is the gate: it builds, lints, tests, then starts the real server
# and asserts against live responses. If it passes, the change is validated rather
# than assumed — which is the whole point of having it.
#
# uv manages the toolchain; nothing here needs a pre-activated virtualenv.

.DEFAULT_GOAL := help
.PHONY: help setup build serve test browser lint fmt check verify shot clean fetch open \
	axe a11y console perf gates

PORT ?= 8000
ROOT ?= site

help: ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## install the toolchain and dev dependencies
	uv sync

fetch: ## refresh the upstream cache (~9 min cold; skips fresh sources)
	uv run showup fetch

fetch-calendar: ## refresh just the daily-changing calendar
	uv run showup fetch --only calendar --force

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

test: ## unit and contract tests (no network, no browser)
	uv run pytest -m "not upstream and not browser"

browser: build ## every browser gate in one pytest run (~110 s)
	# --no-cov: the 100% floor in addopts applies to whatever subset runs, and the
	# browser gates deliberately touch ~70% of `showup` — they drive the built site,
	# not every parser. `make test` is where the floor means something.
	uv run pytest -m browser -v --no-cov

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

# The four M5 gates. Each runs against the real site/ here and against a
# fixture-built site in CI, using the same code either way — see tests/browser/.
# `make verify` deliberately does not call them: together they are about two
# minutes of real browser time, and the fast gate has to stay fast to stay used.

axe: build ## axe-core over every page type (add ALL=1 for all 114)
	uv run python scripts/axe_check.py $(if $(ALL),--all,)

a11y: build ## real Tab keys and the accessibility tree, over every page type
	uv run python scripts/a11y_audit.py

console: build ## fail on any console error or CSP violation (add ALL=1 for all 114)
	uv run python scripts/console_check.py $(if $(ALL),--all,)

perf: build ## page weight, and cold load p95 on throttled 3G (slow: ~2 min)
	uv run python scripts/perf.py

gates: ## every M5 gate, in the order a failure is cheapest to read
	@$(MAKE) --no-print-directory axe
	@$(MAKE) --no-print-directory a11y
	@$(MAKE) --no-print-directory console
	@$(MAKE) --no-print-directory perf

clean: ## remove build output
	rm -rf site site.building screenshots .pytest_cache .ruff_cache .coverage
