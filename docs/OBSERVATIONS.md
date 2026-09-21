# OBSERVATIONS

**What this is for:** recording what this project measured or was surprised by, one dated line
each, so a later decision — in particular any decision about what this project shares with
`timemap_nyc` — is made from evidence instead of memory. **When to read it:** before you
generalise, extract, or copy anything between the two projects. Add to it at the moment of
noticing, not afterwards.

**Nothing here is approved, decided, or designed.** The source of truth remains
`council-access-project-outline.md` and the settled calls remain in `CLAUDE.md`. Do not
implement anything from this file. Append only, newest at the bottom; never rewrite, reorder or
tidy an entry, because a stale entry is still a true dated observation. Long-form work still
gets its own dated file in `docs/`, as `docs/exploration-2026-09-21.md` does.

Write an entry when an upstream lied or surprised you, when you wrote something for the second
or third time or copied it from `timemap_nyc` (**including when you tried and it did not fit** —
the misfits are worth more than the matches), or when you decided against something for a
measured reason. Format: `- DATE | WHERE | WHAT | SO-WHAT`, where `WHERE` is an anchor you can
grep for, `WHAT` has the number in it, and `SO-WHAT` is one clause — what would survive a second
jurisdiction, or `copied:` / `misfit:` / `refused:`. One bullet. If it needs a heading, it is an
exploration doc.

## Entries

- 2026-09-21 | `CLAUDE.md` ("Mirrors `~/personal/timemap_nyc`", "matching
  `~/personal/timemap_nyc`") | The toolchain, the commit markers and the shape of that file were
  copied from `timemap_nyc` on instruction, not arrived at twice independently. | Copied
  similarity is not evidence about the problem domain and must never be counted as convergence.
- 2026-09-21 | `webapi.legistar.com/v1/{boston,seattle,nyc}/bodies?$top=1` | Probed with no
  credentials: boston 200, seattle 200, nyc 403. Same vendor, same resource, same absence of a
  key. | One Legistar reader with the tenant slug as an input may be generic; which tenant
  blocks you is not. NYC's 403 is the only reason the `Calendar.aspx` HTML path exists
  (`CLAUDE.md`, "Legistar is two layers"), so if the 403 lifts that scraper becomes deletable.
- 2026-09-21 | `data.cityofnewyork.us/resource/m48u-yjt8.json` vs
  `data.boston.gov/api/3/action/datastore_search` | Socrata pages by caller-computed
  `$limit`/`$offset` and returns no pagination link, but carries `X-SODA2-Data-Out-Of-Date` in
  the response headers only; Boston's CKAN returns `result._links.next` and `total: 16054` in
  the body. | A pager needs a stable sort and a stop condition either way; whether the next page
  is given or computed differs — and a fetch layer that discards response headers destroys
  Socrata's only staleness signal.
- 2026-09-21 | `spike/node-etl:etl/fetch.mjs` (`getText`) vs `timemap_nyc`
  `scripts/geocode_compare.py` | Retry-with-backoff has been written once across the two
  projects, not twice: timemap's only HTTP code has a User-Agent, a per-provider delay and a
  resumable never-refetch cache, and no retry at all. | misfit: the genuinely twice-written part
  is politeness plus never-refetch; retry classification is 1x, so it is not convergence. Note
  the spike puts Socrata's `X-App-Token` inside the same function body as the generic retry.
