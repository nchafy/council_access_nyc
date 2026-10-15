# Scheduled refresh

**The problem, measured 2026-10-07.** Four of five sources were inside their window. The fifth,
`legistar_calendar`, was **360 hours old against a 12-hour window** — 30× over. It is the only
source of forward-looking meeting dates, so the one thing the site exists to say was the one
thing fifteen days out of date, on a page that otherwise looked current.

Nothing was broken. There is simply no scheduled refresh, because `make fetch` is a local
command and Phase 1 has no hosting. The footer now states the fetch time plainly rather than
judging it, which is the honest presentation — **and it only stays honest if something actually
refreshes.** A timestamp is not a freshness mechanism.

## Windows, and what each implies

| Source | Window | Changes | Needs |
|---|---|---|---|
| `legistar_calendar` | **12 h** | daily — hearings are added, deferred and moved | **twice daily** |
| `board_budget_requests` | 720 h | ~3×/year | monthly |
| `district_pages` | 960 h | rarely; after an election | monthly |
| `members` | 960 h | rarely; after an election | monthly |
| `community_boards` | 2160 h | rarely | quarterly |

One source drives the cadence. A twice-daily calendar fetch plus a monthly sweep of the rest
covers every window, and the calendar fetch is a single unauthenticated GET — cheap, and the
politest thing in the pipeline.

## Why it is not built yet

It needs somewhere to run and somewhere to publish, and both are deferred with hosting
(`docs/phase-1-scope.md`). Specifically it cannot be a scheduled GitHub Action today:

- `etl/raw/` is gitignored on purpose (~80 MB of re-fetchable payloads), and committing fetched
  upstream data is forbidden. So a scheduled job cannot persist the cache into the repo.
- A build artifact has nowhere to go without a deploy target.

So the shape is fixed by the hosting decision, not by this document.

## The design, for when hosting lands

1. **Scheduled job, twice daily**, running `showup fetch --only calendar` then `showup build`
   then `scripts/verify.py`, and deploying only if all three pass.
2. **Fail closed, which already works.** A fetch below its row floor or violating its body
   invariant leaves the previous cache in place and exits non-zero, so a bad upstream day leaves
   the last good site serving — labelled with its real fetch time, which is now what the footer
   says.
3. **Monthly job** for the other four sources. The district-page crawl is ~8.5 minutes at the
   crawl delay `council.nyc.gov` asks for, so it does not belong on a twice-daily schedule.
4. **A dead-man's switch.** The failure that matters is not a failed job — that is loud — it is
   a job that silently stops running. The site already computes staleness in the browser from
   `manifest.json`, so an abandoned deploy reports its own age to every reader without needing
   a monitor. That property is why staleness is computed at read time and not baked at build.
5. **No new secret in the build.** Deploy credentials belong to the deploy step only, never to a
   step that processes untrusted upstream content (§4.5).

## Until then

`make fetch` before `make build`, and the footer states the fetch time. Anyone running the site
locally for more than a day should assume the calendar is stale — and now they can see it.
