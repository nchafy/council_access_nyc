# Show Up NYC

Find out what your New York City Council is doing this week, and what you can
still do about it — which hearings are happening, where the room is, how to get
in, and how many hours are left to file written testimony.

Inspired by [spatialequity.nyc](https://spatialequity.nyc/), but where that site
is a *diagnosis* product, this is an *action* product: it is built to change what
someone does this week, not to score their neighbourhood.

See
[council-access-project-outline.md](council-access-project-outline.md) for the
full plan — requirements, methodology, architecture, milestones, and the
decisions still open.

## What it answers

1. **Where and when are Council meetings?** Live from Legistar, with the real
   street address, the entry rules (NYPD security, photo ID at 250 Broadway, no
   signs larger than 8.5" × 11"), and a calendar file. Never presented as
   confirmed — hearings get deferred without notice.
2. **What is being discussed?** Per-item agenda topics, and recorded votes of
   Council Members parsed from Stated Meeting minutes. **Not** community
   sentiment — see below.
3. **How do you get heard?** In-person testimony needs no pre-registration.
   Written testimony is accepted up to 72 hours after a hearing adjourns. Only
   Council Members can introduce legislation, so there is no public petition
   route onto the agenda, and the site says so first.
4. **Which groups show up, and who do you call?** Your council office, your
   community board, and — conditionally, pending a feasibility spike — which
   organisations spoke on the record, measured from hearing transcripts.

## What it deliberately does not do

No dataset published by New York City records who attended a hearing, who
testified, what they said, or which side they took. So this site has **no
sentiment score, no support/opposition metric, no attendance metric, and no
composite "importance" or "relevance" index** — and no cross-district ranking or
league table. Those refusals are enforced by tests, not by good intentions.

Where an answer is a proxy, the site says which proxy and why. Where a fact is
published nowhere official — the testimony registration cut-off and the
per-speaker time limit both are — it says that too, and gives you the number to
call instead of a guess.

## Speed

Clicking a district or entering an address populates the answer in **under one
second at p95** — and because the two paths have different dependencies, the
budget is split rather than averaged:

| Interaction | Target (p95) | Network on the critical path? |
|---|---|---|
| Map click / keyboard list / district number | **≤ 200 ms** | none |
| Address entry, end to end | **≤ 1000 ms** | one geocoder round trip |
| Address entry, our own share | **≤ 270 ms** | — |
| Autocomplete suggestion | ≤ 300 ms | one geocoder round trip |
| Cold load to interactive (throttled 3G) | ≤ 3 s | — |

The geocoder (`geosearch.planninglabs.nyc`) is a city service we do not operate
and it publishes no SLA, so its latency is **measured and disclosed, not
promised**. When it is slow the UI says so by name at 1.2 s and hands you the map
and list paths at 5 s. All figures are synthetic CI measurements on a reference
device (mid-tier Android, 4× CPU throttle, 4G) — there is no real-user
monitoring, because there are no analytics. See §6A of the outline.

## Stack

- **ETL:** Python 3.12 (uv, ruff, pytest), build-time only, no origin server
- **Frontend:** vanilla ES modules + MapLibre GL JS with OpenFreeMap tiles
- **Hosting:** Cloudflare Pages, CSP with an explicit `connect-src` allowlist
- **Third parties:** none. No analytics, no tag manager, no hosted fonts. The
  address you type is sent to the NYC geocoder and nowhere else, and never enters
  a URL, cookie, or log.

## Status

Planning complete, not yet built. Milestones (§8 of the outline):

- [ ] **M0** — skeleton that is visibly alive: one hearing card from a committed fixture, live URL, staleness banner provable (3d)
- [ ] **M1** — live calendar refreshing 3×/day, fails closed (5d)
- [ ] **M2** — the deadline ledger: `.ics`, 72-hour bound, accommodation deadlines, `/testify` (6d) → **answers Q3**
- [ ] **M3** — address search + interactive map + keyboard-navigable list (5d) → **both interactions**
- [ ] **M4** — district pages, members, community boards (4d) → **Q4 routing**
- [ ] **M5** — accessibility, performance budget, methodology pages → **public launch** (4d)
- [ ] **M6** — agenda items and recorded votes (5d) → **Q2**
- [ ] **M7** — transcript feasibility spike, with a written kill criterion (5d)
- [ ] **M8** — participation panel, conditional on M7 (8d) → **Q4 measured**

**27 days to launch; 45 to all four questions at maximum honest fidelity.**

## Data sources

NYC Open Data (`m48u-yjt8` meetings, `6ctv-n46c` legislation, `uvw5-9znb`
members, `aabe-yfm9` committee membership, `872g-cjhh` district geometry,
`ruf7-3wgc` community boards), `nyc.legistar.com` (live calendar, agendas,
minutes, transcripts), `council.nyc.gov` (district offices, testimony
procedure), and `geosearch.planninglabs.nyc` for geocoding. Full list with
verification dates in §14 of the outline.
