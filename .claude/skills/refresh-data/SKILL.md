---
name: refresh-data
description: Refresh Show Up NYC's upstream data and fixtures — the Legistar calendar, the 51 council.nyc.gov district pages, the NYC Open Data members/boards datasets, and the three geometry files. Use when the site shows stale data, when a staleness banner appears, when a fetch is refused, when fixtures need regenerating, or when asked to update/re-fetch/re-scrape the data.
---

# Refreshing data

## The commands

```bash
make fetch                                  # refresh anything stale, skip what's fresh
make fetch-calendar                         # just the daily-changing calendar
uv run showup fetch --only boards --force   # one named source, ignoring freshness
uv run showup build                         # then rebuild the site
```

A cold `make fetch` takes **about 9 minutes**, almost all of it the 51 district
pages at the 10-second crawl delay `council.nyc.gov` asks for. Everything else is
seconds. Sources younger than their `max_age_hours` are skipped, so running it
often is cheap.

## Where the data lives

`etl/raw/` holds the cache. It is **gitignored** — re-fetchable city data does not
belong in git. The build reads from it and never touches the network, so a build is
reproducible and a flaky download cannot half-write a site.

| Source name | File | Refresh after |
|---|---|---|
| `calendar` | `legistar_calendar.html` | 12 h |
| `districts` | `district_pages.json` (51 pages) | 30 d |
| `members` | `members.json` | 30 d |
| `boards` | `community_boards.json` | 60 d |
| `council-geometry` | `districts.geojson` | 1 y |
| `community-geometry` | `community_districts.geojson` | 1 y |
| `zip-geometry` | `modzcta.geojson` | 1 y |

`meetings.json`, `bills.json`, `funding.json`, `constituent.json` and
`committee_membership.json` are leftovers from the Phase 0 spike and **not used**.
Do not wire them in without reading the plan: casework and discretionary funding
are cut on evidence, not deferred.

## When a fetch is refused

```
boards: 12 rows, floor is 59. Keeping the previous cache.
```

**This is the design working.** A download is validated against a size floor *and*
a body invariant before it replaces anything, so the cache holds either the last
known-good payload or a new known-good one. Never a truncated file, never an error
page.

Do not raise the floor to make it pass. Work out what changed upstream:

- **Body invariant failed** — the shape changed. Check the real response by hand,
  then fix the parser and the fixture together.
- **Row/feature count changed** — could be legitimate (boundaries redrawn, a board
  merged) or a truncated export. Verify before accepting, because
  `council-geometry` demands *exactly* 51 features and the address lookup depends
  on it.
- **One source failed, others succeeded** — deliberate. A dead host does not block
  the rest, and the build's own floors catch a partly-refreshed cache. Re-run with
  `--only <source> --force`; the rest stay cached.
- **`47 of 51 district pages have content`** — transient network failures during the
  9-minute crawl. Failed pages now get one automatic retry pass, added after a cold
  run on a fresh clone lost four to DNS blips. If it refuses twice, re-run
  `--only districts --force`. Note the asymmetry worth remembering: "fail closed and
  keep the last good copy" degrades to plain "fail" on a **first** run, when there is
  no previous copy — which is why the retry exists.

## Why body invariants and not status codes

Three verified cases where these hosts return **HTTP 200 carrying an error**:
`nyc.legistar.com/Feed.ashx` yields a 721-byte `<title>Invalid feed</title>`; a bad
`LegislationDetail` GUID yields a 19-byte `Invalid parameters!`; and a Socrata query
error arrives as JSON with an `error` key. A status check would cache all three
happily.

The district-pages invariant goes further and checks that pages 1, 26 and 51 each
contain their own heading — 51 copies of a login wall would otherwise clear both
the count and the size floor.

## Politeness

Rates come from each host's own `robots.txt`, checked 2026-09-22:

| Host | Declared | Ours |
|---|---|---|
| `council.nyc.gov` | `Crawl-delay: 10` | 10 s |
| `data.cityofnewyork.us` | `Crawl-delay: 1` | 1 s |
| `nyc.legistar.com` | **no robots.txt (404)** | 2 s, our own choice |

An `upstream`-marked test re-reads `council.nyc.gov/robots.txt` and fails if the
City raises its delay above ours. Run it with `uv run pytest -m upstream`. Never
lower a delay to speed up a run — we are a guest on these servers.

Two rules that are not negotiable: **one plain GET of `Calendar.aspx`** (never POST
the ~374 KB `__VIEWSTATE` for page 2, which holds the least valuable rows), and a
**stable `$order=:id`** on every Socrata page, or rows silently duplicate and vanish
between pages.

## After a geometry change

`crosswalks/council_to_boards.json` is derived from two of the geometry files and is
**committed**. If either changes, regenerate it and read the diff:

```bash
uv run showup crosswalk   # ~35 s sweep
git diff crosswalks/
```

A boundary change moving a board between council districts should be a reviewable
diff, not a silent shift in what the site tells people. The command refuses to write
a crosswalk that leaves any of the 51 districts without a board.

## Refreshing fixtures

Fixtures under `tests/fixtures/` are frozen snapshots encoding the pathological
cases tests depend on. Change them rarely and deliberately:

1. `make fetch --force` for the affected source.
2. Regenerate only that fixture, keeping the same trimming (drop `__VIEWSTATE`,
   drop inline script and style bodies) so the diff stays readable.
3. `make test` and read every failure before changing an expectation — a failure
   here usually means upstream changed, not that the test is wrong.
4. Note what changed in `docs/OBSERVATIONS.md` with the date.

Keep district pages 1, 3, 35 and 51: the reference layout, the
source-conflict-and-no-committees case, and the two missing-`Office Hours` cases.
`tests/fixtures/community_boards.json` must stay too — the privacy test checks real
officer names against it.

## Staleness at runtime

`manifest.json` carries per-source `fetched_at` and `max_age_hours`; the **browser**
compares them to the reader's clock and shows the banner. The build never bakes in a
`degraded` boolean — that is what would let an abandoned site keep claiming to be
fresh. To see the banner, hand-edit a `fetched_at` in `site/manifest.json` to
something old and reload.
