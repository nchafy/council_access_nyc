# council_access_nyc — Show Up NYC

A static site that tells a New Yorker the specific, dated things they can still
do about their city government this week: which City Council hearings are
happening, where the room is, how to get in, that they can walk in without
registering, and how many hours are left to file written testimony.

## The development loop

```bash
make fetch    # refresh the upstream cache (~9 min cold; skips anything fresh)
make verify   # build + lint + ~9,000 tests + 357 live-response assertions. The gate.
make serve    # look at it: http://127.0.0.1:8000, with the real headers applied
make shot     # screenshots to screenshots/ — layout bugs are invisible to HTTP checks
make browser  # every browser gate in one pytest run (~100 s)
make gates    # the same four gates as operator tools, with readable output
```

`make gates` is `axe` (WCAG 2.2 AA over all 114 pages), `a11y` (real `Tab` keypresses and
the accessibility tree), `console` (any console error or CSP violation) and `perf` (page
weight, and cold-load p95 on throttled 3G). They are deliberately **not** part of `make
verify`: together they are about two minutes of real browser time, and the fast gate has to
stay fast to keep being used. CI runs them as a separate job, and fails loudly rather than
skipping if the runner has no Chrome.

Fetch and build are separate stages on purpose: the build never touches the
network, so it is reproducible and a flaky download cannot half-write a site. A
download is validated against a size floor **and** a body invariant before it
replaces a cache entry — these hosts return HTTP 200 carrying error pages, so a
status check is not enough.

Never serve with `python -m http.server`: it sends no CSP, so policy violations
would surface for the first time at deploy. `scripts/serve.py` applies the real
`_headers`. Skills: `verify-site`, `add-source-adapter`, `refresh-data`.

`district-3` is the deliberate degraded-state page — vacant-seat handling, the
source-conflict notice, missing committees, designed empty states. Check it after
any renderer change.

**State of play (2026-09-23).** Phase 1 is **built and runs locally**: 110 pages
(51 district, 59 board), seven fetchers, 100% enforced coverage, CI green. Not
deployed — no domain, no hosting, no scheduled refresh, all deferred together.

The accessibility and performance pass is now built and gated in CI: axe clean on all
114 pre-rendered pages at WCAG 2.2 AA, 122 keyboard and accessibility-tree checks over
9 page types, no console error or CSP violation on any page, 13.9 KB gzipped on the
heaviest page against the 60 KB budget, and a 906 ms cold-load p95 on throttled 3G
against the 3 s promise. **The one open Phase 1 item is a real screen-reader pass**,
which is the one part of R39 no gate can stand in for — the procedure and the record
are in `docs/accessibility-pass.md`. `README.md` has the done/not-done list;
`docs/phase-1-scope.md` §6 has the exit criteria ticked individually.

Building a gate? **Serve behind the real `_headers`, always.** `scripts/serve.py` has
`background_server()` for this. The CSP already broke a shipped feature silently once:
`connect-src` omitted `'self'`, so the address box's local index could not be fetched
and every query fell through to the geocoder — the opposite of what the privacy design
promises. It was invisible because the only browser test used a bare file server that
sent no policy. Testing a feature and testing it under the policy shipped with it are
different tests, and only the second one is true.

**On a fresh clone, run `make fetch` first.** `etl/raw/` is gitignored, so there is
no data until you do; `make build` exits 2 and says so. Roughly 9 minutes cold,
almost all of it the 51 district pages at the crawl delay `council.nyc.gov` asks
for.

**Building right now? Read `docs/phase-1-scope.md`** — it is what was scoped and
built, and it supersedes the outline's milestones.

For context: `product-brief.md` has the purpose, users and the eleven product
requirements; `council-access-project-outline.md` is the engineering plan beneath
it — architecture, data contracts, and the 57 constraints that deliver those
requirements. The brief governs *what*, the outline governs *how*, and the phase
doc governs *what now*. This file carries the working conventions and the settled
calls.

**Security is the owner's stated top priority.** The threat model is in
`docs/phase-1-scope.md` §4. The short version, because it is easy to get wrong:
this product has no accounts, so the primary risk is **injection through scraped
upstream content** — committee names, meeting topics and bill titles are
third-party text we render. Never `innerHTML`; strip tags at ingest; allowlist
upstream URLs by host and scheme; `default-src 'none'` CSP with no
`unsafe-inline`; zero third parties; the typed address goes only to the geocoder
with `private=true` and never into a URL, storage or log.

## The bar for starting work

**Do not implement from a vague ask.** If the request does not already say what the
thing is, who it is for, and how you would know it worked, the first deliverable is
a clear ask — not code.

A clear ask names:

- **the user-visible outcome**, in a sentence someone outside the project would
  understand;
- **the data it rests on**, specifically enough to check it exists (a dataset id, an
  endpoint, a page);
- **what it refuses to claim** — this product's failure mode is confident wrongness,
  so the honesty boundary is part of the spec, not a polish pass;
- **how it is verified**, i.e. which assertion would fail if it broke.

When an ask is unclear, say which of those four is missing and propose a reading.
Building the wrong well-tested thing is more expensive than asking. This has already
paid for itself: "add an interest score" and "show community boards" both turned out
to mean something materially different from the first reading, and one of them was
only buildable because the disagreement surfaced before the code.

The exception is a genuinely trivial mechanical change. If you are unsure whether it
qualifies, it does not.

## Testing is not optional, and 100% is the floor

- **100% line coverage, enforced** (`--cov-fail-under=100`). Not a target — the
  build fails below it. When new code drops coverage, write the test; do not lower
  the number.
- **`# pragma: no cover` needs a reason on the same line.** It is for lines that
  genuinely cannot run in a test (a `__main__` guard, an unreachable defensive
  branch). A pragma without a stated reason is a coverage hole with extra steps.
- **Fuzz the parsers, and keep the corpus.** Every input-parsing function has a
  committed corpus under `tests/corpus/` of input → expected-output pairs, and a
  generative fuzzer that asserts invariants (never raises, never emits markup,
  output is plain text) over mutated inputs. **When the fuzzer finds a new
  interesting input, add it to the corpus with its expected result and commit it.**
  The corpus is the durable artifact; the fuzzer is how it grows. See the
  `fuzz-and-corpus` skill.
- Coverage is necessary and not sufficient. The XSS boundary (`text.py`, `urls.py`)
  and anything that renders a date or a deadline need tests that assert *behaviour
  under hostile input*, not just line execution.

## Decisions already made — don't relitigate

Reopening one requires an ADR citing new evidence, not a preference. The full
list with its evidence is §2 of the outline; these are the ones that most often
get re-argued.

- **Static site, build-time ETL, no origin server.** Forced, not chosen:
  `nyc.legistar.com` and `council.nyc.gov` send no `Access-Control-Allow-Origin`,
  so a browser cannot read them directly.
- **No composite "importance" / "salience" / "relevance" score for a
  neighbourhood.** Its heaviest proposed input varies 54.2x across
  equal-population districts and fell 58% during the eviction moratorium, at peak
  need; the rescale-to-100 step turned a measured gap of 0.000 into a 100-vs-99
  headline. Separate, individually interpretable figures or nothing.
  **This does not forbid the shortlist (P11).** Ranking what the *Council* is
  demonstrably working on — upcoming agenda items, hearing counts, pipeline
  stage, repeated lay-overs, divided votes — is measuring the institution's own
  published record, and is in scope. Inferring what *residents* care about is
  not, and no headline may imply it. v1 orders and explains in words; it does not
  emit a 0-100 number. See `product-brief.md` §4 P11 and §7.
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
- **Community boards are joined by geometry, never by `ruf7-3wgc.council_district`.**
  That column has 44 distinct values across 59 rows and omits 7 council districts;
  it records the board office's district, not the ones it covers. The join lives in
  the committed `crosswalks/council_to_boards.json`, regenerated with
  `showup crosswalk` (~35 s) when either boundary file changes. Read the diff.
- **Board chairs and district managers are never rendered**, but every published
  office email is. The harm is the name-to-mailbox pairing, not the address —
  11 boards publish only the district manager's work email and withholding it
  would leave them uncontactable. R30 in the outline carries the measurement.
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

## Sibling project and shared-core intent

`~/personal/timemap_nyc` (`git@github.com:nchafy/timemap_nyc.git`; this repo has
no remote configured) is the same owner's transit-isochrone map. It matters
because it already has working code for the pipeline shape this repo has only
specified — `csv_source.py`/`geojson_source.py` → `normalize.py` → `writer.py` +
`report.py`, on branch `001d-ingest-pipeline`, not on its default branch. A core
both projects sit on is a someday goal, not a plan. `docs/shared-core-notes.md`
holds the evidence, the candidate seams and the open questions; nothing in it is
approved architecture and none of it overrides §2 of the outline.

**Do not design the core, a plugin contract, or a shared interface.** No core
package, shared library, third repository, or jurisdiction/city parameter that
today takes exactly one value. Not adopting pluggy, entry points, or an ABC
registry is a decision rather than an omission — adding one to be helpful is
reopening it. No Boston or data.gov adapter or probe. When something is needed
in both projects, copy it verbatim with a comment naming the source file, and
keep the Legistar, Socrata and NYC names as they are: they mark where the domain
leaks in, and neutral names erase that.

Append one dated line to `docs/OBSERVATIONS.md` when an upstream lies or carries
an error inside an HTTP 200, when you measure a number worth citing later, and
when you copy something to or from timemap — including when you try and it does
not fit. The format is in that file's header.
