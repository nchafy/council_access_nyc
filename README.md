# Show Up NYC

Find out what your New York City Council is doing this week, and what you can still do
about it — which hearings are happening, where the room is, how to get in, and how many
hours are left to file written testimony.

Inspired by [spatialequity.nyc](https://spatialequity.nyc/), but where that site is a
*diagnosis* product, this is an *action* product: built to change what someone does this
week, not to score their neighbourhood.

## Status — Phase 1 built, running locally, not deployed

110 pages generated from live city data: **51 council district pages** and **59 community
board pages**. There is no domain and no hosting yet, by decision — see
[docs/phase-1-scope.md](docs/phase-1-scope.md).

```bash
uv sync         # install the toolchain
make fetch      # ~9 min cold; see the note below
make serve      # then open http://127.0.0.1:8000
```

**`make fetch` is required on a fresh clone.** The upstream cache (`etl/raw/`) is
gitignored because it is ~80 MB of re-fetchable city data. `make build` exits 2 and tells
you so if you skip it. Most of those 9 minutes is the 51 `council.nyc.gov` district pages
at the 10-second crawl delay that site's `robots.txt` asks for; everything else takes
seconds, and a second run skips whatever is still fresh.

If a source is refused — `districts: 47 of 51 district pages have content` — that is the
design working: a size floor and a body invariant must both pass before a download replaces
a cache entry, because these hosts return HTTP 200 carrying error pages. Failed district
pages get one automatic retry pass. If it still refuses, re-run
`uv run showup fetch --only districts --force`; the other six sources are already cached and
will be skipped.

| | |
|---|---|
| Tests | **~9,000**, of which ~8,500 are generated fuzz cases |
| Coverage | **100%**, enforced (`--cov-fail-under=100`) |
| Live checks | **~350** against a running server (`make verify`) |
| Runtime dependencies | **zero** — stdlib only |

## What it answers today

1. **Where and when are Council meetings?** ✅ Live from Legistar: the next five meetings
   with real street addresses, the entry rules (NYPD security, photo ID at 250 Broadway,
   no signs larger than 8.5" × 11"), and whether each is in person, hybrid or remote.
   Never presented as confirmed — hearings are deferred without notice.
2. **What is being discussed?** ⚠️ **Partly.** A meeting's published topic where Legistar
   gives one, and the committees your own member sits on. Per-item agenda detail and
   recorded votes are **verified reachable but not built** — that is M6.
3. **How do you get heard?** ✅ Fully, and this is the sharpest thing the site does. In
   person needs no pre-registration; written testimony is accepted up to 72 hours after a
   hearing adjourns, and the site computes how long you have left. Only Council Members
   can introduce legislation, so there is no public petition route — the site says that
   first rather than last.
4. **Who do you call?** ⚠️ **The routing half.** Your member's district office, and the
   community board(s) covering you with their office, phone, email and monthly cadence —
   plus the route most people do not know, that board committees seat non-board members
   of the public. Measuring *which organisations actually show up* needs the transcript
   spike (M7) and is not built.

## What it deliberately does not do

No dataset published by New York City records who attended a hearing, who testified, what
they said, or which side they took. So this site has **no sentiment score, no
support/opposition metric, no attendance metric, and no composite "importance" index** —
and no cross-district ranking. Those refusals are enforced by tests, not by intentions.

Where an answer is a proxy, the site says which proxy and why. Where a fact is published
nowhere official — the testimony registration cut-off and the per-speaker time limit both
are — it says so and gives you the number to call instead of a guess.

## Two views, because they answer different questions

- **`/district/{1-51}`** — who legislates for you, their committees, the next five Council
  meetings, and how to testify.
- **`/board/{101-503}`** — the most local unit of City government: monthly cadence, the
  zoning review role, who to call, and how to get appointed or sit on a committee.

Both are reachable from the front page by dropdown, by a plain link list, or by typing an
address, a ZIP, a neighbourhood, or just a district number.

## Speed

Selecting a district resolves in **under a second**, and the budget is split rather than
averaged because the two paths have different dependencies:

| Interaction | Budget (p95) | Network on the critical path? |
|---|---|---|
| Dropdown, link list, or district number | ≤ 200 ms | none — pages are pre-rendered |
| Address entry, end to end | ≤ 1000 ms | one geocoder round trip |
| Address entry, our own share | ≤ 270 ms | — |

Anything resolvable locally — a district number, a ZIP, a neighbourhood or board name —
never touches the network at all. Only a street address does, and the geocoder
(`geosearch.planninglabs.nyc`) is a city service we do not operate and which publishes no
SLA, so **its latency is measured and disclosed, not promised**: the UI names it as the
slow dependency at 1.2 s and hands over the list paths at 5 s.

**The page-weight and cold-load budgets are gated in CI as of 2026-09-23** — not by
Playwright but by a ~160-line stdlib DevTools-protocol client (`scripts/cdp.py`), which
keeps the project's zero runtime and dev dependencies intact. Two measurements of
deliberately different kinds:

| Gate | How | Measured |
|---|---|---|
| Page weight ≤ 60 KB gzipped | arithmetic over the built bytes, no browser | 13.9 KB heaviest |
| All JavaScript ≤ 12 KB gzipped | the same arithmetic | 6.7 KB |
| Geometry ≤ 300 KB, after first paint | plus "no page names it as a subresource" | 132 KB |
| Cold load to interactive ≤ 3 s | Chrome, network-shaped, 4× CPU, 20 cold runs, p95 | 906 ms |

Thresholds live in the committed [`perf-budget.json`](perf-budget.json), each carrying a
note recording where its number came from, so changing a promise is a reviewable diff.

The p95 interaction budgets in the table above are **not** gated — those need the map and
the prefetch machinery that Phase 1 cut. There will never be a real-user percentile either,
because there are no analytics; every figure this project publishes is a synthetic
measurement on a reference profile, and the gate's own output says so in those words. See
§6A of the outline.

## Stack

- **ETL:** Python 3.12 (uv, ruff, pytest), build-time only, no origin server
- **Frontend:** vanilla ES modules. No framework. One ~7 KB script for the address box
- **Runtime dependencies: none.** Stdlib only, which is a security decision given that
  the primary threat is untrusted upstream content, not thrift
- **Third parties: none.** No analytics, no tag manager, no hosted fonts, no map tiles.
  The address you type goes to the NYC geocoder and nowhere else, and never enters a URL,
  cookie, storage or log
- **Planned, not present:** MapLibre GL JS + OpenFreeMap for the interactive map, and
  Cloudflare Pages for hosting. Both deliberately out of Phase 1

## What is done and what is not

**Done**

- **M0–M2** — the skeleton, the live calendar with fail-closed refresh, and the deadline
  ledger (the 72-hour written-testimony bound and accommodation deadlines in business days)
- **M3, partly** — address / ZIP / neighbourhood / district-number lookup and
  keyboard-navigable lists. The interactive **map is deliberately cut** from Phase 1;
  geometry ships for *resolution only*, never for display
- **M4** — district pages, members, and community boards joined by geometry
- The fetch stage: seven sources, each with a freshness window, a size floor and a body
  invariant
- The community board view — a second page type, not a variant of the first
- 100% coverage, a committed fuzz corpus, and the testing rules in `CLAUDE.md`
- **M5, nearly all of it** — axe clean on all 114 pages at WCAG 2.2 AA; 122 keyboard and
  accessibility-tree checks over 9 page types driven with real `Tab` keypresses; a gate
  that fails on any console error or CSP violation; the 60 KB and 3 s budgets enforced.
  All four run in CI, and all four fail loudly rather than skipping if Chrome is absent.
  The gates immediately found a real one: the CSP's `connect-src` omitted `'self'`, so the
  address box's local index could not be fetched and every query fell through to the
  geocoder — the opposite of what the privacy design promises. Fixed, and now covered from
  both the policy side and the browser side

**Not done**

- **A real screen-reader pass.** **This is the one open item in Phase 1.** The gates read
  Chrome's accessibility tree, which is the data a screen reader is handed; that is not the
  same as listening to one, and automating the difference away is the shortcut this
  product cannot take. [docs/accessibility-pass.md](docs/accessibility-pass.md) §3.2 is
  the procedure and §4 is the record, which currently reads NOT RUN
- **Hosting, a domain, and a scheduled refresh**, deferred together. `make fetch` refreshes
  on demand and the browser-side staleness banner covers the gap, so the site is
  correct-on-demand rather than self-maintaining.
- **M6** — per-item agenda detail and recorded votes → question 2. The data is verified
  reachable (`docs/OBSERVATIONS.md`); nothing is built.
- **M7 / M8** — the transcript feasibility spike and, conditional on it, the participation
  panel → question 4's measured half.

## Where to start reading

In this order:

1. **[product-brief.md](product-brief.md)** — what the product is, who it is for, and the
   eleven requirements. The document to argue with.
2. **[docs/phase-1-scope.md](docs/phase-1-scope.md)** — what was in scope, and the security
   threat model (§4), which is the part most likely to be got wrong.
3. **[CLAUDE.md](CLAUDE.md)** — the settled decisions, the domain gotchas that cost real
   time to discover, and the working rules including the 100% coverage floor.
4. **[council-access-project-outline.md](council-access-project-outline.md)** — the
   engineering plan: architecture, data contracts, and 57 numbered constraints.

Also: `docs/OBSERVATIONS.md` is a dated log of what this project measured or was surprised
by — read it before assuming anything about the upstream data.
`.claude/skills/` holds four skills for the common operations (verify, fetch, add a source,
fuzz).

## Data sources

NYC Open Data — `uvw5-9znb` (members), `ruf7-3wgc` (community boards), `872g-cjhh`
(council district geometry), `5crt-au7u` (community districts), `pri4-ifjk` (ZIP areas).
`nyc.legistar.com` for the live calendar. `council.nyc.gov` for district offices and the
testimony procedure. `geosearch.planninglabs.nyc` for geocoding.

Not used, and cut on evidence rather than deferred: `b9km-gdpy` (constituent casework) and
`4d7f-74pe` (discretionary funding). The reasons are in `CLAUDE.md` and are worth reading
before proposing either — both cuts were driven by measurement.
