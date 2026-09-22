---
name: refresh-data
description: Refresh Show Up NYC's upstream data and fixtures — re-fetch the Legistar calendar, the 51 council.nyc.gov district pages, and the NYC Open Data members dataset. Use when the site shows stale data, when a staleness banner appears, when fixtures need regenerating, or when asked to update/re-fetch/re-scrape the data.
---

# Refreshing data

## Where the data lives now

`etl/raw/` holds cached upstream payloads. It is **gitignored** — 78 MB of
re-fetchable city data does not belong in git. The build reads from it and never
touches the network, so a build is reproducible and a network failure can never
half-write a site.

| File | Source | Changes |
|---|---|---|
| `legistar_calendar.html` | `nyc.legistar.com/Calendar.aspx` | daily |
| `district_pages.json` | 51 × `council.nyc.gov/district-N/` | per session, or on a special election |
| `members.json` | Open Data `uvw5-9znb` | per session, lags reality |

The others (`meetings.json`, `bills.json`, `funding.json`, `constituent.json`,
`committee_membership.json`, `districts.geojson`) are from the Phase 0 spike and
**not used by Phase 1**. Do not wire them in without checking the plan: casework
and discretionary funding are cut on evidence, not deferred.

## Re-fetching

A `showup fetch` command does not exist yet — Phase 1 reads the existing cache.
Until it does, the throwaway Node spike on branch `spike/node-etl` does the
fetching, and it is the reference for what a Python fetch stage must reproduce:

```bash
git show spike/node-etl:etl/fetch.mjs > /tmp/fetch.mjs   # read it, do not run it as the answer
```

What that stage must preserve when it is ported:

- **One plain GET** of `Calendar.aspx`. Never POST the ~374 KB `__VIEWSTATE` for
  page 2 — page 1 is date-descending and already spans months ahead.
- **Polite rates.** `council.nyc.gov` at 1 request / 10 s (51 pages ≈ 8.5 min).
  Hammering a city website is a security failure in the direction we control.
- **Body invariants, not status codes.** Legistar serves error bodies with HTTP
  200: `Feed.ashx` returns a 721-byte `<title>Invalid feed</title>`, a bad
  `LegislationDetail` GUID returns a 19-byte `Invalid parameters!`.
- **Stable `$order` when paging Socrata**, or rows silently duplicate and vanish.
- **Write to a cache, then build.** Fetch and transform stay separate stages.

`webapi.legistar.com` needs a token (`403 Token is required`) and Phase 1 must
work without one. A free key can be requested at
`council.nyc.gov/legislation/api/`, but nothing may depend on it.

## Rebuild and check

```bash
make verify
```

`build` reports what it saw:

```
meetings parsed : 100
calendar through: 2026-12-17
pages with gaps : 6
```

Compare those to the previous run. A large drop in `meetings parsed`, or
`pages with gaps` jumping, means an upstream change — investigate before
committing. If a floor is breached the build refuses and keeps the old site,
which is the intended behaviour.

## Refreshing fixtures

Fixtures are frozen snapshots and should change rarely and deliberately: they
encode the pathological cases that tests depend on. When an upstream redesign
makes them unrepresentative:

1. Re-fetch into `etl/raw/`.
2. Regenerate only the affected fixture, keeping the same trimming (drop
   `__VIEWSTATE`, drop inline script/style bodies) so the diff is readable.
3. Run `make test` and read every failure before changing an expectation — a
   failing test here usually means upstream changed, not that the test is wrong.
4. Note what changed in `docs/OBSERVATIONS.md` with the date. That log is the
   evidence base for later decisions.

Keep district pages 1, 3, 35 and 51: they are the reference layout, the
source-conflict and no-committees case, and the two missing-`Office Hours` cases.

## Staleness

`manifest.json` carries per-source `fetched_at` and `max_age_hours`; the **browser**
compares them to the reader's clock and shows the banner. The build never bakes in
a `degraded` boolean — that is what would let an abandoned site keep claiming to be
fresh. To test the banner, hand-edit `fetched_at` in `site/manifest.json` to
something old and reload.
