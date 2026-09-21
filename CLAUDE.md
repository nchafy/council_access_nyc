# council_access_nyc — Show Up NYC

A static site that tells a New Yorker the specific, dated things they can still
do about their city government this week: which City Council hearings are
happening, where the room is, how to get in, that they can walk in without
registering, and how many hours are left to file written testimony.

Read `council-access-project-outline.md` first — it is the source of truth for
requirements, methodology, architecture, milestones, and the open decisions.
This file carries only the working conventions and the settled calls.

## Decisions already made — don't relitigate

Reopening one requires an ADR citing new evidence, not a preference. The full
list with its evidence is §2 of the outline; these are the ones that most often
get re-argued.

- **Static site, build-time ETL, no origin server.** Forced, not chosen:
  `nyc.legistar.com` and `council.nyc.gov` send no `Access-Control-Allow-Origin`,
  so a browser cannot read them directly.
- **No composite "importance" / "salience" / "relevance" score, ever.** Its
  heaviest proposed input varies 54.2x across equal-population districts, and
  the rescale-to-100 step turned a measured gap of 0.000 into a 100-vs-99
  headline. Separate, individually interpretable figures or nothing.
- **No sentiment, support, opposition, controversy, or attendance metric.**
  Nothing the City publishes records who attended or testified at a hearing,
  what they said, or which side they took. Fabricating it is this product's
  worst available failure mode.
- **No cross-district ranking, percentile, league table, or indicator-coloured
  choropleth.** "My district is darker" becomes the mental model regardless of
  what the legend says.
- **Casework (`b9km-gdpy`) and discretionary funding (`4d7f-74pe`) are cut.**
  Casework effectively ends in 2023 and its construct is falsified by its own
  natural experiment (housing casework fell 58% during the eviction moratorium —
  peak need). Funding ends at FY2021 and ~19% of sampled recipient addresses are
  single-family homes owned by named natural persons. A label cannot fix a
  doorstep.
- **The district is a filter, not the organising key.** Committee hearings are
  citywide and belong to no district. `/hearing/{id}` and `/committee/{slug}`
  are first-class; `/district/N` is pre-rendered and linkable but not the
  primary journey.
- **Python 3.12 + uv + ruff + pytest for ETL; vanilla ES modules for the
  frontend.** Mirrors `~/personal/timemap_nyc`. The only logic shared between
  ETL and browser is ~25 lines of ray-casting, so the one-language argument for
  Node is empty. One pinned npm devDependency: `mapshaper`.
- **MapLibre GL JS + OpenFreeMap, self-hosted vendor bundle.** No Google Maps,
  no Mapbox, no analytics, no tag manager, no third-party fonts. The model site
  `spatialequity.nyc` ships gtag and Mapbox; we borrow its metric-registry
  schema and its refusal to composite, and reject its telemetry.
- **Cloudflare Pages, not GitHub Pages** — only a CSP with an explicit
  `connect-src` allowlist makes "zero third parties" browser-enforced against a
  future commit, and GitHub Pages cannot set response headers.
- **The typed address never leaves the browser except to the geocoder**, and
  never enters a URL, storage, cookie, or log. Shareable URLs carry
  `/district/35` only.
- **Fail closed.** A refresh run below a row floor or violating a body invariant
  fails the job and leaves the previous deploy serving, labelled with its real
  age.
- **Staleness is computed in the browser, not baked at build.** `manifest.json`
  carries per-source `fetched_at` + `max_age`; the client compares against the
  current time. This is what keeps an abandoned site honest.
- **Interaction SLA: selecting a district paints its answer in under 1 s at
  p95** (§6A). Decomposed, because the two paths differ: a map click, list
  selection, or district number is **local only** and budgeted at p95 ≤ 200 ms
  with no network on the critical path; an address adds a geocoder round trip we
  do not control, so our own share is budgeted at ≤ 270 ms and the external leg
  is measured rather than promised. Consequences that are settled: the compact
  51-district index is **inlined** (≤ 22 KB gzipped) and answers the click;
  `district/NN.json` is a below-the-fold detail payload prefetched on
  hover/focus, never on the click path; geometry is resident before the map is
  presented as clickable, with the keyboard list serving until then; hit-testing
  uses a bbox prefilter.
- **SLA evidence is synthetic, and we say so.** Because analytics are banned
  there is no real-user monitoring, so every published latency figure is a CI
  measurement on a reference device, never an observed field percentile.

## Domain notes

- **Legistar is two layers.** The open dataset `m48u-yjt8` ends 2024-12-19 and
  can never answer "when is the next meeting". Forward dates come only from the
  live layer: `Calendar.aspx` (one unauthenticated GET; never POST the ~374 KB
  `__VIEWSTATE` for page 2) and `MeetingDetail.aspx` per meeting.
- **`webapi.legistar.com/v1/nyc/...` returns HTTP 403 "Token is required".** A
  key is free but human-mediated. v1 must work with zero authenticated access;
  votes, agendas, topics, and transcripts are all reachable without one.
- **Check body invariants, not status codes.** Several Legistar endpoints return
  HTTP 200 carrying an error: `Feed.ashx` yields a 721-byte
  `<title>Invalid feed</title>`, and a bad `LegislationDetail` GUID yields a
  19-byte `Invalid parameters!`.
- **Committees are renamed every session** ("Committee on Transportation" →
  "…and Infrastructure"; "Women's Issues" → "Women and Gender Equity"), so any
  historical grouping must go through a dated crosswalk, never a name match.
- **`6ctv-n46c.primary_sponsor` is a bare surname** (207 distinct, literal `NA`
  when absent) and "Adams" spans two members. Minutes vote blocks are surnames
  too. One shared resolver keyed on (surname, date) against `uvw5-9znb` term
  windows, with Unicode normalisation for `Avilés`/`Ossé`/`Cabán`/`Farías`. It
  must quarantine unresolvable rows, never guess.
- **Recorded votes live in Stated Meeting minutes PDFs**
  (`View.ashx?M=M&ID=<event_id>`) as `Affirmative:` / `Negative:` / `Abstain:` /
  `Non-voting:` blocks ending in a printed tally. **Hard invariant:** parsed
  name count must equal the printed integer or quarantine the whole document —
  a silently dropped `Negative:` block would make everything look unanimous.
- **Floor dissent is rare and blocs are persistent.** One sampled Stated Meeting
  had 1 divided vote in 113 items, with the same nine members dissenting
  together. Publish `bloc_concentration` beside any dissent figure; above 0.60
  the copy withdraws the topic-level reading and presents it as a member voting
  pattern.
- **Every district-page field is independently optional.** `Office Hours` is
  absent on D35 and D51, three phone-label conventions exist, two email
  conventions exist, and committees are absent for districts 3, 5, 9, 14, 25,
  26. Do not assume a uniform layout.
- **`wp-json` is not a substitute for the rendered page** — it reports District
  1's office as "101 Lafayette St, 9th Floor" while the live page says "65 East
  Broadway".
- **Two facts residents most want are published nowhere official:** the
  registration cut-off before a hearing, and the per-speaker time limit. These
  render as explicit refusal strings pointing at
  `hearings@council.nyc.gov` / 212-482-4219. Never invent them.
- **Written-testimony deadline is a provable lower bound**, `start + 72h`, never
  derived from an adjournment time — adjournment timestamps are not published,
  and adjournment is always at or after the start, so the bound is safe.

## Conventions

- Milestones M0–M8 are in §8 of the outline; work proceeds in that order. M0 is
  three days and must end in a live URL rendering one hearing card from a
  committed fixture.
- **TDD, with commit markers.** `test: … (RED)` then `feat(scope): … (GREEN)`,
  matching `~/personal/timemap_nyc`. Conventional commits throughout.
- Never commit fetched upstream payloads (`etl/raw/`, PDFs, the 3.8 MB district
  GeoJSON) — scripts download and derive them. Committed fixtures under
  `tests/fixtures/` are the deliberate exception and are stored byte-exact.
- Every user-facing number carries its denominator, its window, and a link to
  the primary document it came from. A number without provenance is a bug.
- No LLM or NLP step inside the build: organisation and member aliasing is
  reviewed YAML, so artifacts are byte-reproducible in CI at zero model cost.
- `spike/node-etl` holds the throwaway Node spike that verified source
  availability. It is reference only — do not build on it.
