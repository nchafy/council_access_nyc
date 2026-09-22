---
name: verify-site
description: Build, test and validate the Show Up NYC site end to end — use after any change to the ETL, renderer, assets or headers, and before any commit. Covers running the local server, the live-response checks, and screenshots. Use when asked to "check my work", "does it still work", "run the site", "see the site", "take a screenshot", or when a build or verify step fails.
---

# Verifying a change

The loop that makes a change *validated* rather than assumed. Run the whole thing
before committing; run pieces while iterating.

## The one command

```bash
make verify
```

Builds, lints, runs the tests, then starts the real local server and asserts
against live responses. Exit code is non-zero on the first failure. If this
passes, the change is good.

## The pieces, when iterating

| Command | What it does | When |
|---|---|---|
| `make build` | Cached sources → `site/` | after any ETL or renderer change |
| `make test` | 132 tests, 85% coverage floor | after any logic change |
| `make lint` | ruff check + format check | before committing |
| `make serve` | Serve on :8000 **with the real headers** | to look at it in a browser |
| `make shot` | Screenshots to `screenshots/` | to check layout, or to show someone |
| `make check` | lint + test, no build | fast inner loop |

## Looking at it

```bash
make serve      # then open http://127.0.0.1:8000
```

Always use `make serve`, never `python -m http.server`. The project server applies
`_headers`, so the CSP is exercised. A plain static server sends no CSP, and every
violation would then surface for the first time at deploy — which is when it gets
waived instead of fixed.

## Reading the screenshots

`make shot` writes `index`, `district-35` and `district-3` at two widths. Look at
them; an unstyled page, a collapsed region or a clipped column is invisible to an
HTTP assertion and obvious in an image.

District 3 is the deliberate degraded-state page: vacant-seat handling, the
source-conflict notice, the missing-committees gap, and the designed empty state.
If a change breaks a "designed state", it shows up there first.

The narrow shot is **500px, not 390px**. macOS clamps Chrome's minimum window
width below ~500, so asking for 390 yields a 390-wide image of a ~704-wide
layout — a silent crop that looks exactly like a CSS overflow bug. Do not
"fix" the CSS in response to it.

## What verify actually checks

230 assertions across: the security headers being served (not just present in
`_headers`), no inline `<script>` or `style=` attribute anywhere, no
`javascript:` URL, every internal link resolving to a real file, every external
link being https and on the allowlist, the six content blocks present on district
pages, the procedural facts present verbatim, `/district/99/` returning 404, and
`manifest.json` carrying freshness *inputs* rather than a baked verdict.

## When a build refuses

```
build refused: calendar: parsed 3 rows, floor is 40.
```

This is **fail-closed working correctly**, not a bug to route around. A source
parsed below its floor means the upstream shape probably changed. The previous
`site/` is deliberately left untouched. Fix the parser or update the fixture —
never lower the floor to make it pass.

## Simulating CI before you push

`make verify` uses `etl/raw/`, which is **gitignored**. A test that reads from it
passes locally and errors in CI. Reproduce the CI environment by hiding the cache:

```bash
mv etl/raw /tmp/raw_hidden
uv run pytest -m "not upstream and not browser" -q   # must pass
mv /tmp/raw_hidden etl/raw
```

This has already caught one real failure: the community-board integration tests
read `etl/raw/community_boards.json` and CI could not find it. Test data belongs in
`tests/fixtures/`, always.

## Coverage floor

`--cov-fail-under=85` (currently ~90%). If a change drops it, add the test rather
than lowering the number. `src/showup/text.py` and `src/showup/urls.py` are the XSS
boundary; they should stay near 100% and every new branch in them needs a test.
