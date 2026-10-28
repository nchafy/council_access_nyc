# OBSERVATIONS

Dated evidence, so any later decision — especially about what this project shares with
`timemap_nyc` — is made from measurement instead of memory. **Read it before you generalise,
extract, or copy anything between the two projects.** Add at the moment of noticing.

**Nothing here is approved, decided, or designed.** Source of truth stays
`council-access-project-outline.md`; settled calls stay in `CLAUDE.md`. Append only, newest at the
bottom. Never rewrite, reorder or delete an entry — a stale entry is still a true dated observation.

Write an entry when an upstream lied or surprised you, when you wrote something for the second or
third time or copied it from `timemap_nyc` (**including when it did not fit** — misfits are worth
more than matches), or when you decided against something for a measured reason.

Format: `- DATE | WHERE | WHAT | SO-WHAT`. `WHERE` is a greppable anchor, `WHAT` has the number in
it, `SO-WHAT` is one clause — what would survive a second jurisdiction, or `copied:` / `misfit:` /
`refused:`. One bullet. If it needs a heading, it is an exploration doc (see
`docs/exploration-2026-09-21.md`).

## Entries

- 2026-09-21 | `CLAUDE.md` ("Mirrors `~/personal/timemap_nyc`") | Toolchain, commit markers and file
  shape were copied from `timemap_nyc` on instruction, not arrived at twice. | copied: copied
  similarity is not evidence about the domain and must never be counted as convergence.
- 2026-09-21 | `webapi.legistar.com/v1/{boston,seattle,nyc}/bodies?$top=1` | No credentials: boston
  200, seattle 200, nyc 403. | One Legistar reader with the tenant slug as input may be generic;
  which tenant blocks you is not — and if NYC's 403 lifts, the `Calendar.aspx` scraper is deletable.
- 2026-09-21 | `data.cityofnewyork.us/resource/m48u-yjt8.json` vs
  `data.boston.gov/api/3/action/datastore_search` | Socrata pages by caller-computed
  `$limit`/`$offset`, gives no pagination link, and carries `X-SODA2-Data-Out-Of-Date` in headers
  only; Boston's CKAN returns `result._links.next` and `total: 16054` in the body. | generic: a fetch
  layer that discards response headers destroys Socrata's only staleness signal.
- 2026-09-21 | `spike/node-etl:etl/fetch.mjs` (`getText`) vs timemap `scripts/geocode_compare.py` |
  Retry-with-backoff exists once across the two projects, not twice: timemap's only HTTP code has a
  User-Agent, a per-provider delay and a resumable never-refetch cache, and no retry. | misfit: the
  twice-written part is politeness plus never-refetch, so retry classification is 1x. The spike also
  puts Socrata's `X-App-Token` inside the generic retry function body.
- 2026-09-21 | `ruf7-3wgc.council_district` | 59 community-board rows carry only 44 distinct
  council-district values; districts 5, 8, 15, 20, 27, 32 and 40 appear nowhere, because the column
  records the district of the board's *office*, not the districts it covers. | refused: the one-line
  join would leave 7 of 51 districts with no board, so any administrative-geography crosswalk must
  come from geometry.
- 2026-09-21 | `crosswalks/council_to_boards.json`, `src/showup/geo.py` (`overlap_shares`) | A ~110 m
  lattice over the city resolves council-to-community-district overlap in ~35 s with no
  polygon-clipping dependency; validated against known geography (D35 → Brooklyn CB 2/8/9). |
  generic: sample a lattice instead of taking a clipping dependency, and commit the result so a
  boundary change is a reviewable diff.
- 2026-09-21 | `uvw5-9znb` district 3 vs `council.nyc.gov/district-3/` | The open dataset records a
  term ending 2026-02-03 with no successor row while the scraped page already names the new member:
  the scrape is *fresher* than the official dataset after a special election. | generic: when two
  public sources disagree, resolve toward the reading that does not remove information from the user,
  and disclose the conflict.
- 2026-09-22 | `nyc.gov/site/communityboards` | Board committees seat **non-board members of the
  public** — join the discussion, cannot vote, most boards want an application and a resume. The bar
  is far lower than testifying and almost nobody knows it. | generic: the highest-value participation
  route is often the least advertised one; look for it before building analytics.
- 2026-09-22 | `src/showup/text.py` (`strip_tags`), `tests/corpus/strip_tags.jsonl` | The fuzzer
  disproved two confidently asserted invariants: output CAN contain `<script>` (from
  `&#60;script&#62;`, decoded correctly once), and it is NOT idempotent (`"Defer&#x3C;red"` →
  `"Defer<red"` → `"Defer"`). | generic: for an HTML-stripping boundary the guarantee lives at the
  ESCAPER, not the stripper — strip exactly once on raw upstream text and audit the call sites.
- 2026-09-22 | `tests/test_privacy_guard.py` (timemap) vs `scripts/verify.py` (this repo) | Both have
  a "privacy guard" protecting opposite parties: timemap's asserts the *owner's* data is absent from
  fixtures, this one asserts *third parties'* names are absent from published pages. | misfit: a
  shared guard would have to parameterise *whose* privacy, and one protecting the wrong party is
  worse than none. Not duplication.
- 2026-09-22 | `tests/contract/test_output_contract.py` (timemap) vs the twelve upstream contract
  tests here | Same name, different mechanism: timemap validates its *own output* against a JSON
  Schema; this repo asserts *upstream* still returns the shape it parses, on a job that never gates a
  deploy. | misfit: two features wearing one word; name both concepts separately before abstracting.
- 2026-09-22 | robots.txt for the three scraped hosts | `council.nyc.gov` publishes `Crawl-delay: 10`
  (51 pages ≈ 8.5 min), `data.cityofnewyork.us` publishes 1, and `nyc.legistar.com` serves **no
  robots.txt at all** (404). | generic: read each host's own file rather than assuming a global rate;
  where none exists the delay is your choice, not a permission. An `upstream` test re-reads it.
- 2026-09-22 | `src/showup/geo.py` (`SIMPLIFY_TOLERANCE_DEG`) | Measured over a 37,000-point lattice
  against full precision: 11 m tolerance → 60 KB gzipped, 0.059% of points assigned to the *wrong*
  district; 2.2 m → 132 KB, 0.011%; unsimplified → 372 KB, 0.005%. The floor is not zero — points on
  a shared edge are ambiguous even unsimplified. | generic: choose a simplification tolerance by
  measuring assignment *correctness*, not file size. A first attempt was a no-op because the
  tolerance default binds at function definition.
- 2026-09-22 | Chrome `--headless=new --dump-dom` | Returns the page's *original source*, not the live
  DOM, so even a synchronous `textContent` change is invisible. macOS also clamps a Chrome window's
  minimum width below ~500 px, so `--window-size=390` yields a 390-wide image of a ~704-wide layout,
  which reads exactly like a CSS overflow bug. | generic: have the page report over HTTP to a
  recording server, and do not trust a screenshot's width to be the layout width.
- 2026-09-22 | `src/showup/fetch.py` (`_fetch_district_pages`), cold run on a fresh clone | A 9-minute
  polite crawl of 51 pages lost 4 to transient DNS failures, so the invariant correctly refused
  47/51 — but a fresh clone has **no previous cache to keep**, so the build could not run at all and
  the operator had to repeat the whole crawl. Fixed with one retry pass over just the failures. |
  generic: "fail closed and keep the last good copy" degrades to "fail" on first run, so any long
  polite crawl needs a retry pass over its own failures.
- 2026-09-23 | `_headers` `connect-src`, found by the first browser run behind the real CSP | The
  directive named the geocoder and omitted `'self'`, so all three same-origin fetches were refused:
  `/data/lookup.json`, `/data/districts.geo.json`, `/manifest.json`. ZIP, neighbourhood and
  district-number resolution therefore fell through to the geocoder — a policy written to protect the
  reader's address was sending **more** of their input — and the staleness notice never rendered.
  Invisible because the one browser test used a bare file server with no CSP and `verify.py` fetched
  the manifest over plain HTTP. | generic: testing a feature and testing it *under the policy shipped
  with it* are different tests, and only the second is true.
- 2026-09-23 | `tests/fixtures/a11y_broken/`, the axe negative control | The deliberate
  colour-contrast defect was in a `<style>` block and axe never reported it, because `style-src
  'self'` blocked the inline CSS and the rule applied to nothing — the negative control was itself
  testing nothing. | generic: build a negative control for the *environment* of the gate, or it proves
  the gate works on a page that cannot exist.
- 2026-09-23 | `scripts/cdp.py`, headless focus behaviour | Headless Chrome has no browser controls to
  release focus to, so Tab past the last element wraps to the top and an assertion that "focus can
  leave the page" reported all 9 page types as focus traps. The distinguishing property is
  reachability: n Tab presses must visit n distinct elements. | generic: assert the invariant a defect
  breaks, not the behaviour a windowed browser happens to have. Also `Input.dispatchKeyEvent` with
  `rawKeyDown` moves focus for Tab but skips Blink's implicit form submission for Enter, which needs
  `keyDown` carrying `text`.
- 2026-09-23 | `scripts/perf.py`, throttled cold load, 20 runs per page | Cold load to interactive on
  3G Fast + 4x CPU: front page p95 906 ms, district 741 ms, board 723 ms, against a 3000 ms promise.
  On DevTools' own Slow 3G preset the same pages take 4.3-5.1 s — three 2000 ms round trips before a
  byte of ours is considered. | refused: gating on Slow 3G, because there the number measures the
  network and not our page. Published beside the gated figure rather than dropped.
- 2026-09-23 | page weight, gzipped, at the 60 KB R40 budget | Front page 13.9 KB, district pages
  7.6 KB, board pages 6.1 KB, 404 at 4.3 KB; all JavaScript together 6.7 KB; geometry 132 KB against
  its separate 300 KB after-first-paint budget. | generic: a budget met at 22% is worth a second,
  tighter ceiling on the part that can grow without bound — here script alone at 12 KB, because React
  with its DOM package is ~45 KB gzipped and would hide comfortably inside 60 KB.
- 2026-09-23 | `site/index.html`, `site/district/index.html`, `site/board/index.html` | All three are
  byte-identical (29,458 bytes): the front page carries both link lists, so both index routes are
  copies of it. Not a defect — it is what makes the no-JavaScript form target work — but the axe and
  console sweeps test the same bytes three times. | generic: when enumerating "every page" for a gate,
  dedupe by content hash before spending browser time on it.
- 2026-09-24 | `render.py` board page, "No City dataset publishes community board agendas or meeting
  dates" | **False as written, and it was rendered to users.** `dg92-zbpx` (City Record Online) carries
  dated community-board hearing notices with `event_date`, `building_name`, `street_address_1`, `zip` —
  all 59 boards appear. But coverage is tiny and decaying: 33 rows in 2026 (6 with a structured street
  address) vs 101 in 2016, and it is ULURP/land-use notices only, never the monthly full board. Two
  other CB datasets (`3gkd-ddzn`, `dy27-rrad`) carry office address plus the same cadence string, no
  venue, no dates, and were last updated 2017 and 2019. | refused: a blanket "nobody publishes this" is
  a factual claim and needs the same provenance as a number. Narrowed to "no City dataset publishes a
  board meeting calendar" and the page now names dg92-zbpx.
- 2026-09-24 | `ruf7-3wgc.cb_office_address` vs the board's own published venue | **The office is not
  the meeting venue.** Differs on 8 of 8 boards where both are known: CB401 office 45-02 Ditmars Blvd
  vs venue The Marquee at Astoria; CB409 Room 310A vs Room 200; CB101 Room 2202-N vs 19th Floor
  Southside; CB102, CB108, CB206, CB308, CB314 all at unrelated buildings. The office is where
  *committees* meet. | refused: rendering `cb_office_address` as "where it meets" would have been wrong
  for the full board every time. The dataset has no venue field; the page now says so.
- 2026-09-24 | `ruf7-3wgc.cb_board_meeting` cadence vs the boards' own sites | Disagrees for 5 of 8
  sampled: CB409 7:45pm vs 7:15pm; CB102 "Fourth Tuesday" vs Thursday 18:30; CB206 "Second Wednesday"
  vs fourth; CB302 "Second Wednesday" vs third; CB314 "Second Monday 7:30pm" vs 18:30 and third Monday.
  Queens CB9's own page warns "Meeting Locations are subject to Change" and lists two months as "To Be
  Determined". | generic: a verbatim quote from an authoritative-looking dataset is still a claim about
  the world. The page now presents the cadence as the City's record of it, not as the board's schedule.
- 2026-09-24 | the 59 `cb_website` URLs | Five host families, not one: 37 on the nyc.gov AEM CMS with
  **zero feeds**, 9 on `*.cityofnewyork.us` WordPress + The Events Calendar (uniform
  `/wp-json/tribe/events/v1/events`, but the `venue` object is null on some), 10 independent domains, 2
  legacy 2000s CMS, 1 null. 15 of 59 nyc.gov slugs now 404 because the board left. 3 of 13 sampled
  hosts refuse automated clients (two 403 on robots.txt, one Cloudflare challenge). `is_virtual` was
  `false` on every event inspected, including ones whose own text says "via Zoom". | refused: scraping
  venues in Phase 1. Not one scraper and not 59 — about 5 families plus a long tail, ~23% unscrapeable,
  and trusting `is_virtual` would send people to meetings that are online-only.
- 2026-09-29 | all 59 board websites, full census (`docs/board-meeting-sources.json`) | Full-board venue
  obtainable for **39 of 59**, but only **14** from a structured field — the other 25 are prose on an
  unpredictable page (About, FAQ, home, or a PDF). Future dates for 47. Both for 34. **27 boards publish
  no feed of any kind.** Host families: 37 nyc.gov CMS, 12 cityofnewyork.us WordPress, 7 independent, 3
  other. 4 hosts refused automated clients. | generic: "is this data available" is the wrong question;
  "available in the same shape across the set" is the one that decides cost. Two thirds coverage in five
  different formats is not two thirds of a feature.
- 2026-09-29 | The Events Calendar `venue` field, across the 12 boards that expose it | **Right on some
  boards, wrong on others, and the failures point the wrong way.** It works exactly as wanted on Brooklyn
  CB14 and CB11 — committees at the district office, the full board at a different building on a dated
  future event with a structured street address. It fails on Manhattan CB1 (populated with the board
  OFFICE while the real venue sits in the description), Bronx CB6 (populated for committees, null for all
  7 upcoming full-board meetings), Manhattan CB10 (two contradictory venues for one meeting) and Brooklyn
  CB2 (full-board LOCATION empty while all nine committee series are filled). | refused: trusting the
  field uniformly. A source that is correct on some members of a set and confidently wrong on others
  cannot be consumed by one parser — it needs per-board verification, which is a maintenance cost, not a
  parsing problem.
- 2026-09-29 | my own first reading of that field | I reported it to the owner as "a trap, not a
  solution", which overstated it: that conclusion came from the four boards where it fails, before the
  two where it works were checked. The accurate claim is unreliability, not uselessness. | generic: when
  a source fails on the first few members sampled, the finding is "unreliable across the set", not
  "broken" — and the difference decides whether a feature is impossible or merely expensive.
- 2026-09-29 | refusal copy, calibrated against the evidence | "No City dataset publishes a board
  meeting calendar" is TRUE. "Nobody has aggregated this" is TRUE. **"This data does not exist anywhere"
  would be FALSE** — roughly 5 of 59 boards expose structured venue-carrying feeds right now, and 39 of
  59 publish a venue somewhere. | generic: a refusal has a scope, and the scope is part of the claim.
  Widening "we do not have this" into "it does not exist" is the same class of error as inventing a fact.
- 2026-09-29 | Wayback CDX, 2003 → 2026, searching for a central City list of board meeting times | None
  ever existed. The Mayor's Community Affairs Unit's only central calendar was street-fair permits, and
  in 2003 it told readers to "find the dates and times by contacting your local community board." | so
  what: this is a 20-year gap, not a withdrawal. The refusal the board page renders is not a temporary
  state waiting on a dataset, and can be written as durable.
- 2026-09-29 | robots.txt handling during this survey | One lapse, disclosed: an agent fetched
  `brooklyncb11.org/calendar/` in the same batched command that retrieved that host's robots.txt, so its
  `Disallow: /calendar/` was not evaluated before the request. One GET, no retries, host abandoned, and
  no content from that path was used or recorded. | generic: robots.txt must be a blocking gate in its
  own step, never batched with content requests for the same host. Also: robots permission does not
  predict access in either direction — `cb8m.com` permits everything and returns 403, while other hosts
  allow our UA and their WAF blocks it anyway.
- 2026-09-29 | office-vs-venue near misses | An address comparison cannot catch this. Brooklyn CB5:
  same building, office 2nd floor, board 3rd. Brooklyn CB15: same street address at Kingsborough CC,
  office C124 vs Faculty Dining Room U112. Staten Island CB2: office 900 South Avenue, venue 1100 South
  Avenue. Venues also rotate monthly on at least 7 boards (Man 104/107, Bx 202, Bk 302/308/310). |
  generic: a cached or inferred venue is wrong for a moving target; the room is the part the public
  needs and the part that differs.
- 2026-09-29 | central City sources, and the third-party field | DCP's **ZAP API** (undocumented; base
  extracted from the SPA's own `<meta>` config) exposes `dispositions` carrying CB hearing date, time and
  a prose venue for **59/59 boards** over a 3-year backfill — but it is **retrospective, median +8 days
  after the hearing**, so it cannot answer "show up this week". The only prospective city source is City
  Record `dg92-zbpx`: 19/59 boards, 56 rows in 13 months, median 6 days lead, structured address on
  10/56. **No third party has solved this**: 59boards.nyc, nyc.councilmatic.org and community-board.nyc
  are all NXDOMAIN, CityScrapers has 0 NYC spiders, BetaNYC has no calendar repo. | generic: when a
  niche is empty and three attempts died in it, price the maintenance, not the build.
- 2026-09-29 | "15 of 59 nyc.gov board slugs now 404" — **my own claim, and it is wrong** | The 404s came
  from *constructing* slugs (`nyc.gov/site/{borough}cb{N}`), not from any published list. Status-checking
  all 57 `ruf7-3wgc.cb_website` URLs gives 52x200, 4x403 bot-block, 1 connection failure, **0x404**; the
  central nyc.gov directory gives 56x200, 3x403, **0x404**. The 200s were confirmed as real pages by
  title, not SPA soft-404s. | generic: never derive a URL when the publisher gives you a list. A
  constructed-slug failure rate says nothing about the data's availability and I reported it as if it did.
- 2026-09-29 | `nyc.gov/site/communityboards/about/<borough>-boards.page` | An authoritative central
  directory of all 59 boards with their current site URLs and cadence, which this project had not found.
  59/59 present, 56/59 live, 0 dead. Supersedes `ruf7-3wgc.cb_website` for URL discovery. | so what: the
  "stale URL" problem was partly self-inflicted; there is a maintained spine to key off.
- 2026-09-29 | City Record `dg92-zbpx`, corrections to the 2026-09-24 entry above | Two errors. (1) The
  per-board `agency_name` labels (`QUEENS COMMUNITY BOARD #8` etc.) are **payroll notices**, not hearings:
  all 827 rows across 62 labels carry `event_date = null` and `section_name: "Changes in Personnel"`. Only
  the bulk `agency_name='Community Boards'` bucket has hearings. (2) "Never the monthly full board" was
  too strong — 6 of 56 notices are explicitly the monthly meeting, e.g. Brooklyn CB18's "Monthly Meeting"
  at 1097 Bergen Avenue. Real figures: 51 rows in the last 12 months across 19/59 boards, median 6 days of
  lead, `event_date` carries a start time. | generic: a `$where` on `agency_name` that returns 0 may be an
  encoding artefact, not an absence — `curl --data-urlencode` re-encodes a literal `%25`.
- 2026-09-29 | `api.nyc.gov/calendar/search` | The City already runs a citywide events API with
  `startDate`, `address`, `boroughs[]` and a **"Hearings and Meetings" category that returns
  `totalItems: 0`**. All 141 pages swept: 1,683 items, 5 agencies, **zero community boards**. | so what:
  nothing technical is missing. Boards simply do not publish into the pipe that already exists, which is a
  far more tractable ask than new infrastructure — and a better thing to advocate for than a scraper.
- 2026-09-29 | the `*.cityofnewyork.us` WordPress network, as a City-run source | One uniform
  unauthenticated call per board returns future meetings with a structured venue, full board and committees
  distinguished by title. Verified: Manhattan CB4 returns `2026-10-07 18:30 | Full Board | Pier 57, 25 11th
  Avenue` — a future full-board meeting at a venue that is not the board office. 9 of 59 boards, ~780
  upcoming events. `Crawl-delay: 10`. `cbqueens` and `cbstatenisland` hostnames exist but are empty, so
  coverage grows for free if the City migrates more boards. | so what: this is the one city-run path with
  future dates AND venues, and it is 9 boards, not 59.
- 2026-09-29 | `ruf7-3wgc.cb_website`, and a bug that had shipped | The field arrives from Socrata as a
  nested `{"url": "..."}`, not a string. `boards.py` read it as a string, producing
  `"{'url': 'https://...'}"`, which failed every URL check — so **no board page has ever carried a
  website link**, for any of the 59, while the page copy told readers the board's own site is where the
  agendas and meeting location are published. Found only by surveying the websites the page never linked.
  | generic: a field that silently normalises to None looks identical to a field the publisher left empty.
  Parse failures on an optional field need to be counted and reported, not coalesced to absent.
- 2026-09-29 | Brooklyn CB5's listed domain | `ruf7-3wgc` still points at `brooklyncb5.org`; that domain
  lapsed and now redirects `dreamydrawfest.com` -> `acrosstheponddc.com` -> `eurekabikekitchen.org` ->
  `bouxseinlab.org`, an unrelated biology lab. Its nyc.gov page is live and the dataset does not mention
  it. | refused: linking board-owned domains at all. 48 of 59 boards are on `nyc.gov` or
  `*.cityofnewyork.us`, where the City controls registration and a board cannot lose it by forgetting to
  renew; those are linked. The other 10 get their hostname as plain text with the reason. A civic site
  handing a reader a re-registered domain is doing the one thing it exists not to do, and the City's own
  dataset cannot be relied on to notice.
- 2026-09-29 | `www1.nyc.gov` and `http://www.nyc.gov` in the same field | 33 of 59 rows use the old
  `www1` hostname, which 301s to `www.nyc.gov`; 6 more are published as `http`. Both were being rejected
  on host or scheme. Normalising them is not a widening of the allowlist — the publisher and the
  destination are identical. | generic: an allowlist needs the publisher's aliases in it, or it rejects
  the publisher.
- 2026-09-29 | `tests/browser/test_perf.py` under concurrent browser load | 5 of 8 cold-load tests errored
  with `cdp.CDPError: connection closed mid-frame` while 67 Chrome processes were live from a parallel
  survey. The same tests pass 8/8 in isolation, and the full browser suite had passed 73/73 twice before
  and after. | so what: the throttled cold-load gate is sensitive to machine contention, which CI does not
  have (one job, one browser). Not hardened with a retry, because a retry would also hide a real
  disconnect. If it ever flakes in CI, the fix is to serialise, not to retry.
- 2026-09-30 | `vn4m-mk4t` (OMB Register of Community Board Budget Requests), licence cleared by the owner
  | **`boro` is alphabetical by borough acronym, not the standard NYC code**: 1=Bronx, 2=Brooklyn,
  3=Manhattan, 4=Queens, 5=Staten Island. Verified by geography rather than by documentation — boro=1
  board=01 asks about Mott Haven, boro=2 about Greenpoint and McGolrick Park, boro=3 about 26 Broadway
  and "Lower manhattan", boro=4 about Hallet's Point, boro=5 about Bay Street. The standard NYC code has
  1=Manhattan and 2=Bronx, so a naive join silently swaps three boroughs. | generic: verify a code column
  against something in the payload that names a place, never against the convention you expect.
- 2026-09-30 | `vn4m-mk4t.publication` | The newest value is **`20270217`, dated five months in the
  future** (today is 2026-09-30), so `ORDER BY publication DESC LIMIT 1` selects it. It is not a
  duplicate: same 3,809 rows and same tracking codes as `20260630`, but with terser agency responses
  ("Agency does not support and cannot accommodate" where 20260630 has "OMB supports the agency's
  position as follows: ..."). | refused: selecting the newest publication. The rule is the newest
  publication **not dated in the future**, which fails closed and is a one-line guard. A future-dated row
  in a published register is either a typo or a forward-planned cycle, and neither is safe to serve.
- 2026-09-30 | `vn4m-mk4t.priority` | Runs 01-25 zero-padded, but **repeats within a board**: 1,387 rows
  across 59 boards carry priority 01. Manhattan CB1's three priority-01 rows have tracking codes ending
  `C`, `CS` and `E` — capital, capital-support and expense. So priority is ranked *within a budget
  category*, and "the board's number one request" does not exist as a single row. | refused: rendering a
  single top ask. Coverage is 59/59 boards at 9-134 requests each.
- 2026-09-30 | `vn4m-mk4t.response` | Free text whose leading sentence looks classifiable ("Agency
  supports and can accommodate" / "does not support and cannot accommodate") but varies in phrasing and
  prefix between publications of the same row. | refused: bucketing it into supported/not-supported. It
  is quoted verbatim, because a mis-bucketed "no" reads as a promise.
- 2026-09-30 | `vn4m-mk4t.tracking_code` | Ten or eleven characters: `boro`+`board` (the
  alphabetical code, so `101…` is Bronx CB1), a four-digit fiscal year, a two-digit sequence
  number, then `C`/`CS`/`E`. Two traps. The prefix is **not** the repo's board code, so a code
  must never be derived from it. And the sequence digits are **not** the `priority` column:
  Brooklyn CB2's `202202704C` carries priority 01, and five of its 61 rows in publication
  `20260630` are priority 01. | generic: a composite key that looks like it encodes the other
  columns is a second source that can disagree with them; verify each field against its own column.
- 2026-09-30 | `vn4m-mk4t` coverage, mapped through the alphabetical `boro` | Publication
  `20260630` is 3,809 rows over exactly 59 distinct `boro`/`board` pairs, 9-134 per board, one
  fiscal year (2027), `responded_by` uniformly `OMB`. Mapped 1→2xx, 2→3xx, 3→1xx, 4→4xx, 5→5xx
  the 59 pairs are exactly the 59 real board codes in `ruf7-3wgc.community_board_1`. | so what:
  the code mapping is checkable without geometry — a wrong mapping still yields 59 codes, but not
  the same 59 the boards dataset publishes.
- 2026-09-30 | Chrome's `/devtools/page/...` endpoint vs `websocket-client` defaults | Chrome **403s a
  WebSocket upgrade that carries an `Origin` header**: `Rejected an incoming WebSocket connection from
  the http://127.0.0.1:PORT origin`, suggesting `--remote-allow-origins`. The hand-rolled client sent no
  `Origin` and so never met this; `websocket-client` synthesises one from the host unless
  `suppress_origin=True`. Verified both ways against a live headless Chrome in one run. | so what: the
  fix is `suppress_origin=True`, not a Chrome flag — `--remote-allow-origins=*` would widen what may
  drive the browser. A library's defaults are tuned for web servers, and a debugging endpoint is not one.
- 2026-09-30 | `websocket-client` 1.9.2 internals, measured while replacing the hand-rolled RFC 6455
  client | Two numbers worth keeping. Its pure-Python `validate_utf8` is a **per-byte loop costing
  0.106 s per megabyte, ~800x the 0.00013 s of `bytes.decode('utf-8')`** — real money on a
  multi-megabyte `Accessibility.getFullAXTree`, and redundant because `recv` decodes strictly anyway, so
  `skip_utf8_validation=True`. And its `_mask` fallback is the **same `int.from_bytes`/`to_bytes`
  big-integer XOR** the hand-rolled code used for the ~567 KB axe payload, so that optimisation
  survived the swap without us restating it. It imposes **no read ceiling at all**, so
  `MAX_FRAME_BYTES = 256 MB` had nothing to configure. | so what: when a library absorbs hand-rolled
  code, check whether it kept the optimisation the comment was defending — here it had, and the
  ceiling it replaced turned out not to exist, which is why the guard moved into a test.
- 2026-09-30 | `sources/calendar.py` `_HREF`, found by swapping the regexes for beautifulsoup4 |
  The hand-rolled reader matched an `href`'s **characters**, so Legistar's `&amp;` never decoded:
  every stored detail, agenda and minutes URL carried `?ID=…&amp;GUID=…`, rendered as
  `&amp;amp;GUID=` on **255 links across all 51 district pages**. Checked live both ways: both
  return HTTP 200 and render the same meeting ("Committee on Transportation and Infrastructure on
  9/30/2026 at 10:00 AM"), because `MeetingDetail.aspx` and `View.ashx` key on `ID` alone and
  silently ignore the bogus `amp;GUID` parameter. So no reader was ever misrouted. | so what:
  "tags stripped, entities decoded once" was enforced on text and silently not on attributes, and
  an upstream tolerant enough to ignore the malformed half is why nothing ever went red.
- 2026-09-30 | comparing two Legistar responses, correcting the entry above | That entry first
  read "both forms return HTTP 200 with the same bytes". **Not true, and not checkable that way**:
  fetching one URL twice gives different bytes, and still differs after `__VIEWSTATE` is stripped,
  because the page carries several per-request tokens. The byte counts matched (221,016 each),
  which is what made the wrong claim look verified. | generic: on an ASP.NET page, equality of
  responses has to be asserted on rendered content — here the `<title>` and the meeting fields —
  never on bytes or length. A byte comparison there produces a confident answer to a question it
  cannot answer.
- 2026-09-30 | `text.py` extractors, beautifulsoup4 vs the `html.parser` state machines they
  replaced | Compared over **74,615 inputs** — the whole corpus, ~8,500 fuzz mutations, the 4 real
  district fixtures, all 51 cached district pages, the real calendar, and every string field of
  four Socrata payloads. **5 differ, all one cause: a stray end tag.** The state machine emitted a
  word break for every `</p>`, `</td>` or `</div>` it saw, matched or not; bs4 drops an unmatched
  end tag. Neither is HTML5-conformant — the spec ignores a stray `</div>` and synthesises an
  empty paragraph for a stray `</p>` — so the old code was accidentally right about `</p>` and
  wrong about the rest. Not reachable from any real page. | so what: "a real parser behaves like a
  browser" is only true of a real *HTML5* parser; `html.parser` and bs4 over it both do less error
  recovery than Chrome, and the difference is in error recovery, not in tag handling.
- 2026-09-30 | the six board PDFs, tested before building a parser for them | All six URLs still
  resolve on `www.nyc.gov` (one already-allowlisted host, so no 59-site crawl). Text extraction:
  **405 Queens CB5, 408 Queens CB8, 412 Queens CB12 and 503 SI CB3 extract cleanly** (1.4-2.9 KB of
  text each); **501 SI CB1 yields 4 characters from a 12 MB file and 502 SI CB2 yields 1** — both
  confirmed scans. This **corrects the 2026-09-29 survey on 412**, which recorded it as glyph-coded
  and unparseable; it carries 7 `ToUnicode` maps and extracts fine. | generic: a font-object header
  sniff is not an extraction test. Run the extractor.
- 2026-09-30 | the same four parseable PDFs, and why a PDF venue parser was **refused** | The first
  street address in these documents is the **office letterhead**, not the meeting venue. Queens CB8's
  PDF opens "Community Board 8 / 197-15 Hillside Avenue / Hollis NY" above a phone and fax; SI CB3's
  opens "Community Board #3 / 1243 Woodrow Road 2nd Floor" — while its actual full-board venue is
  the CYO-MIV Community Center on Hylan Boulevard. So naive extraction returns the office and labels
  it the venue, which is the exact failure the 2026-09-29 entries document and refuse. | refused:
  reading venues out of these PDFs. Doing it correctly needs four bespoke in-context parsers (CB5's
  venue is in the body of a "PUBLIC HEARINGS NOTICE" paragraph, not the letterhead), against URLs
  that rot monthly — `BoardMeetingNoticeSept9-2026.pdf`, `September-2026-Calendar.pdf`,
  `2026.10.01.pdf`; only CB8's is annual. Four boards, four parsers, monthly rot, and two letterheads
  that actively mislead is a bad trade against the 39/59 the site already has honestly.
- 2026-10-01 | the board office, reconsidered — it IS a venue, for the right meeting | Four boards
  publish the split explicitly: Bronx CB11's "Meeting Preferences" table reads "Board Office" against
  every committee and "Varies/Webex" against the full board; Brooklyn CB4 states "Committee meetings
  are held at the board's District Office (1420 Bushwick Avenue)"; SI CB3 separates its "Office
  Conference Room, 1243 Woodrow Road" from the full-board venue; Bronx CB10 is the counter-example and
  says to ring before assuming. | so what: I had been treating `cb_office_address` purely as a trap.
  It is a trap for the FULL-BOARD question and the answer to the COMMITTEE one — and committee
  membership is the participation route this product singles out as "the route most people do not know
  about". The board page listed the office and pitched committee membership in separate sections and
  connected them nowhere; it now states the split, with the caveat, and a test pins it.

- 2026-10-07 | `src/showup/templates/*.html`, `docs/voice.md` | Applying the voice policy removed 38
  second-person uses and 16 imperative sentences from the four templates but only 23% of the words
  (1,804 -> 1,385, measured with Jinja and HTML tags stripped and alphabetic tokens counted). The
  brief asked for roughly half. What stopped it: of what remains, the great majority is quoted
  Charter and City wording, provenance (source link + denominator + window), or a refusal string,
  and all three are protected. Only ~15% of the starting prose was direction or explanation —
  i.e. the thing the policy removes. | so what: on a provenance-first page, "halve the prose" and
  "keep every citation" are not the same lever and the second one binds first. A word-count target
  is the wrong instrument for a voice change in either jurisdiction; count imperatives and
  second-person uses instead, because those go to zero and words do not.

- 2026-10-07 | `src/showup/templates/board.html`, `scripts/a11y_audit.py` | Chrome's accessibility
  tree exposes an `<h3>` nested inside a `<summary>` as a real level-3 heading *and* exposes the
  `summary` as a `DisclosureTriangle` with `expanded`, so progressive disclosure costs no heading
  outline — `/board/302/` still names all five request cards while collapsed, and axe reports 0
  WCAG 2.2 AA violations across 115 pages. Two things did break: `summary` was absent from the
  keyboard audit's focusable selector (`a[href], button, input, select, textarea, [tabindex]`), so
  the Tab budget ran one short per card; and a closed `<details>` hides its children with
  `content-visibility` rather than `display: none`, so a computed-style filter alone still counts
  them as reachable. Both are now in `TAG_FOCUSABLE_JS`. | so what: `<details>` is a free win for
  disclosure, but any audit that enumerates focusable elements by selector has to be told about it,
  and a `display`/`visibility` check is not a substitute.

- 2026-10-07 | `site/`, `scripts/perf.py` | Moving three disclosure paragraphs off the pages onto a
  new `/references/` made every document lighter — board 4,106 -> 3,678 gzipped bytes (-10%),
  district/35 3,720 -> 3,701, index 5,049 -> 4,993, 404 664 -> 610 — while `site.css` grew 2,059 ->
  2,267 and `site.js` 1,640 -> 1,869 for the disclosure rules and a locale-free date formatter. Per
  page on the critical path that is about +0.4 KB, because the critical path counts the shared CSS
  and JS every time. `/references/` is 2,822 gzipped, 11% of the 60 KB budget. | so what: on a site
  this small the shared assets dominate a page-weight diff, so "the page got lighter" and "the
  critical path got lighter" are different claims and the second one is the gated number.
- 2026-10-08 | three commit bodies on this branch that misstate what they contain | **`8da7d2d`**
  claims an `address.js` change and a docs figure sweep that are in `dca9d85`, not in it — and it
  shipped `test_our_own_broken_data_is_reported_as_our_fault`, which asserts a string `address.js`
  did not yet contain, so it left a browser gate red with no `(RED)` marker and a body written as
  though green. **`be7fbf7`** and **`a3480a1`** carry a pasted shell transcript: `be7fbf7`'s body is
  100,938 bytes, 153 lines of it terminal output, and it truncates two sentences mid-clause.
  Cause: the message was passed with `-m "…"` in double quotes containing backticks around
  `make verify`, so the shell ran it as command substitution and spliced the output in.
  **`1e808a4`** has an empty body; its measurement is in the diff instead. | so what: this repo
  strips comments from code, so the body is the only record — a body that names a file the diff does
  not touch is not untidy, it is false. Not rewritten: `be7fbf7` is three commits deep, the branch
  is pushed with a PR open, and a rebase would collide with concurrent work. Use a quoted heredoc
  (`<<'MSG'`) for any message containing backticks, and read `git log -1` before pushing.
- 2026-10-20 | `scripts/reflow_check.py`, `site.css` (`overflow-wrap: anywhere`) | First render of
  any page below 500 px. Two upstream strings carry no break opportunity, and each forces the
  layout viewport wider than the width asked for: a board website URL rendered as link text
  (`www.nyc.gov/site/statenislandcb2/index.page`, 345 px) and a board email
  (`communityboard@queenscb3.cityofnewyork.us`, 363 px). 4 pages failed at 320 px, 3 more at 390 px
  — a WCAG 1.4.10 failure that had been live in every build. The fix is `overflow-wrap: anywhere`
  and not `break-word`: only `anywhere` lowers the min-content width, and min-content is what
  widens the initial containing block. | A publisher does not control the length of a string a
  city hands it. Any site rendering an upstream URL, email or ID needs this rule at the point the
  value lands, and needs it gated below 390 px, because no desktop window can be made that narrow.
- 2026-10-20 | `scripts/cdp.py` (`emulate_device`), `docs/accessibility-pass.md` §6 | The recorded
  gap said `cdp.py` "can now do device emulation, so fixable". It could not: it had
  `Network.emulateNetworkConditions` and `setCPUThrottlingRate` and no
  `Emulation.setDeviceMetricsOverride`. The claim had sat unchallenged since 2026-09-23. | A known
  gap that names its own fix is still a claim, and a plausible one is the kind nobody re-derives.
  The repo's own review rule 1 applies to its gap list, not only to PR descriptions.
- 2026-10-20 | `scripts/reflow_check.py` (`_violates`), `scripts/pageset.py` | The signal had to be
  `window.innerWidth` exceeding the requested width. A per-element overflow check reported **0
  offenders on every failing page**: once the layout viewport widens to 369 px, every element fits
  inside 369 px. The widest offender was also a bare text node on one page, owned by no element.
  Separately, the representative set missed the worse of the two defects — the 390 px one — so the
  cheap gate was green while `ALL=1` was red. | measuring the container tells you nothing when the
  container is what moved; and a representative set is only representative of the failures someone
  already thought of.
- 2026-10-21 | `scripts/cdp.py` (`--use-angle=swiftshader`) | Every browser gate launched Chrome
  with `--disable-gpu`, which gives no WebGL2, and MapLibre refuses to initialise without it:
  `WebGL2 is required to display this map`. The map drew nothing and axe, a11y, console and
  reflow all reported the page clean. Fixed by adding `--enable-unsafe-swiftshader`,
  `--use-gl=angle` and `--use-angle=swiftshader`; all 85 browser tests still pass, because a
  page that creates no GL context is unaffected. | A gate that renders a feature differently
  from the reader is not testing the feature. Headless defaults are chosen for speed, and the
  first WebGL or canvas feature in any project silently falls outside every existing gate.
- 2026-10-21 | `site/vendor/maplibre-gl.css`, `_headers` (`img-src 'self'`) | MapLibre's control
  icons are **39 `url("data:image/svg+xml...")` background-images**, all refused by
  `img-src 'self'`. The zoom buttons rendered as blank boxes and **Chrome logged nothing** —
  `console_check.py` reported 0 complaints on the page. Replaced with two of our own
  `<button>` elements, which are also in the tab order, which MapLibre's control is not. |
  A blocked CSS background-image is the quietest CSP failure there is: no console error, no
  network error, just missing pixels. `img-src` is the directive to re-read before trusting any
  third-party stylesheet, and "0 console complaints" does not mean "nothing was blocked".
- 2026-10-21 | `scripts/a11y_audit.py` (`_settled_focusables`) | The audit snapshotted the
  focusable list once, then pressed Tab that many times. The map's zoom buttons ship `hidden`
  and are revealed when MapLibre finishes drawing, seconds after `load`, so the list grew
  mid-run: 2 of 54 elements reported unreachable and `Shift+Tab` appeared to retrace the wrong
  order. Neither was a page defect. Fixed by reading the list until two consecutive reads
  agree. | The address box has had the same shape since M3 and never tripped it, because its
  reveal lands within milliseconds. A race that only a slow async reveal exposes was latent in
  the gate from the start, and it failed by inventing defects rather than by missing them.
- 2026-10-21 | `maplibre-gl` 6.15.0 from `registry.npmjs.org` | What a reader actually
  downloads is **449 KB gzipped**, not the ~200 KB assumed: `maplibre-gl.mjs` 292 KB,
  a separate `maplibre-gl-worker.mjs` 147 KB, `maplibre-gl.css` 10 KB (1.69 MB raw). v6 ships
  **ESM only** — no UMD build — so it needs `<script type="module">`, and the worker is a
  second file rather than an inlined blob. | The published "bundle size" of a map library is
  the main chunk. The worker is the half nobody quotes. Against a 12 KB script ceiling this is
  the difference between a budget and a rounding error, so it is gated separately in
  `perf-budget.json` rather than inside the page budget it would hide in.
- 2026-10-21 | the probe behind `_headers`, before `src/showup/templates/map.html` existed |
  A first measurement concluded MapLibre required `style-src 'unsafe-inline'`, with a
  reproducible CSP violation to show for it. **Wrong**: the inline `style` attribute was on the
  probe page's own `<div id="map" style="height:400px">`. MapLibre contains no `cssText` and no
  `setAttribute('style')` — zero occurrences in 1.1 MB. Against the real policy, unchanged, it
  paints with no console output at all. | The violation was real, the attribution was not. A
  measurement that indicts a dependency must be run with the dependency as the only variable,
  or it indicts the harness. Had this gone unchecked, the site's CSP would have been
  permanently loosened for a defect in a throwaway file.
- 2026-10-21 | `src/showup/assets/site.css` (`.map-toggle:not([hidden])`) | A `display` rule beats
  the `hidden` attribute. `.map-selection { display: inline-block }` overrode the UA stylesheet's
  `display: none`, so a link that ships `hidden` and empty was visible, focusable and nameless:
  one axe `link-name` violation and three keyboard failures, on three elements that all shipped
  `hidden` and were all styled with `display`. | `hidden` is a UA default, not a guarantee. Any
  element that ships hidden and is revealed by script needs `:not([hidden])` on its display rule,
  or the attribute does nothing. The gates caught it; reading the CSS would not have.
- 2026-10-21 | `src/showup/render.py` (`render_index(..., with_map=...)`) | `render_index` renders
  three pages — `/`, `/district/` and `/board/` — so putting the map in that template put it on
  all three, and each would have downloaded 449 KB. Caught by
  `test_no_other_page_mentions_maplibre`, which exists only because `docs/dependencies.md` makes
  load-gating a condition of allowing the dependency. | A shared template is a shared cost. The
  rule that made this a test rather than a discovery was written before the feature, which is the
  only reason it was cheap.
- 2026-10-21 | `src/showup/assets/address.js` (`announce`) | With the map on the front page, a
  resolved address could highlight instead of navigating — which is the point of a map — but
  applying that to a typed **district number** would have broken SLA-1's ≤200 ms promise by adding
  a click to the one path meant to be instant. It also made `test_a_district_number_resolves`
  race: it passed only because the map had not finished loading before the submit. Resolved by
  offering the map only a **geocoded coordinate**; a district number, ZIP or neighbourhood still
  navigates. | A feature that changes what an existing promise means has to be scoped against that
  promise, not bolted on. The flake was the tell: a test that passes because something else is
  slow is already failing.
- 2026-10-21 | `site/data/boards.geo.json` | The board layer needed geometry the site never
  shipped: `community_districts.geojson` was in the cache for the build-time board↔district join
  only. Simplified at the same 2.2 m tolerance it is **96 KB gzipped** for 59 features, against
  135 KB for the 51 council districts. Both now ship, 226 KB of the 300 KB geometry budget. |
  The board polygons are smaller than the council ones despite there being more of them, because
  council districts are drawn to equal population and so split dense areas into many-sided
  shapes. Also: putting the map on the front page means every visitor fetches both layers, where
  before geometry was fetched only on the street-address path. Front-page cold load moved from
  865 ms to 1294 ms p95 on 3G Fast, and 5.0 s to 6.5 s on Slow 3G.
- 2026-10-22 | `src/showup/assets/site.css` (`.map` height, not `.mapshell`) | The map-first
  layout shipped with the height on the shell and the panel in normal flow inside it, so on a
  390 px viewport the panel overflowed the shell and **rendered on top of the `h1` and the
  paragraph below it** — three layers of text in the same pixels. **Every gate passed**: axe 0
  violations, a11y 148/148, console 0 complaints, reflow 0 violations, perf inside every budget.
  It was found by looking at a screenshot. | Overlapping text is invisible to all five gates.
  axe checks contrast against a computed background, not against whatever is painted over it; the
  reflow gate measures the layout viewport, and an overflowing child inside a fixed-height parent
  does not widen it. `make shot` being "the only gate a human reads" is not a nicety — it is the
  only one that can see this class of defect at all.
- 2026-10-22 | `/` (`.map-panel` over the map) | axe now reports one **`color-contrast`
  incomplete** on the front page, which it did not before: the panel is
  `rgba(255, 255, 255, .95)` over a canvas, and axe cannot compute a contrast ratio against
  pixels it did not paint. Checked by eye at 1440 px and 390 px — the panel is effectively opaque
  white over a light map, and the text is the site's normal ink. | "Incomplete" is axe declining
  to decide, not a pass and not a failure. Any translucent surface over a canvas will produce
  one, so the count is expected to stay at 1 and a change in it is worth reading.
- 2026-10-22 | `/map/` as a route, `.app` in `site.css` | **A map inside a scrolling page steals
  the wheel.** With the map on the landing page, scrolling down zoomed the map out instead of
  moving the page — reported by the owner, caught by no gate. Fixed by making the map a route
  whose body does not scroll at all (`height: 100%; overflow: hidden`, flex column, map takes
  what the header and footer do not): `scrollHeight == clientHeight` at 390 px and 1440 px, so
  there is no page scroll for the map to take. | Wheel capture is a property of the
  *combination*, not of either part, which is why no page-level check sees it. An embedded map
  and a scrolling document are mutually exclusive; one of them has to give. Moving the map off
  the landing page also restored two things it had cost: the landing page is 5 KB again and
  loads no library, and geometry is once more fetched only on the street-address path.
- 2026-10-22 | `.app main` (`margin: 0`) | The app shell rendered as a blank 44rem column with
  two thin slivers. `main` computed to **width 0** while reporting `max-width: none` and
  `flex: 1 1 auto`: the base rule centres it with `margin: 0 auto`, and an auto inline margin on
  a column flex item makes it shrink to its content rather than stretch — and its children are
  all absolutely positioned, so that content is nothing. | `margin: 0 auto` is inert on a block
  and load-bearing on a flex item. Overriding `max-width` was not enough; the margin had to go
  too. Found by dumping computed styles, not by reading the CSS, and not by any gate: axe, a11y,
  console and reflow all passed on a page that rendered almost nothing.
- 2026-10-22 | `layout.html` (`.caveat.sources`), `.app footer.site` | Hiding the app footer's
  caveats for height also hid the **sources link**, which lives in one of those paragraphs. The
  link stayed in the DOM at 0x0 and so could not be focused: the keyboard gate reported "9 of 10
  elements were reachable" and nothing else noticed. Every page is required to link what it is
  built from. | The audit's visibility filter checks the element's own computed style, not its
  ancestors', which is why a child of a `display: none` parent was still counted as focusable.
  That strictness is a feature here — a looser filter would have passed the page and the missing
  sources link would have shipped.
- 2026-10-22 | `_headers` (`connect-src https://tiles.openfreemap.org`) | The basemap needed
  **one CSP directive and no others.** OpenFreeMap's `liberty` style pulls five kinds of thing
  from one host — a 43 KB style JSON, vector tiles via `/planet`, raster relief PNGs at low
  zoom, glyph `.pbf` and sprites — and all five arrive through `fetch`, so `img-src`,
  `worker-src` and `blob:` were each measured unnecessary. | The instinct with a tile host is
  to widen `img-src` for the tiles. MapLibre has not fetched raster tiles through `Image()` for
  some versions, so that instinct buys a directive nobody needs. Four variants, measured, before
  one line was added.
- 2026-10-22 | `scripts/console_check.py` (`VENDOR_STYLE_WARNINGS`) | Taking a third party's
  data put **their defects inside our gates**. Two layers of OpenFreeMap's own style,
  `highway-shield-non-us` and `highway-shield-us-interstate`, carry a filter whose first operand
  is null; MapLibre validates, warns, and falls back to false. Nothing here is wrong and nothing
  here can fix it. Exempted by **layer name**, not by shape, so a third broken layer still fails
  and someone has to look. | This is the part of a third-party dependency nobody prices. The
  tiles were the decision; inheriting their style's bugs, and the judgement about which of their
  warnings to silence, came free with it. A gate that silences a class rather than an instance
  would have hidden the next one.
- 2026-10-22 | `product-brief.md` §5, `tests/unit/test_csp.py` | **The "no third party sees a
  reader's request" promise was withdrawn**, by owner decision, in exchange for a basemap: 51
  polygons on an empty field read as floating. What a tile host can observe is the sequence of
  tiles fetched — the area being read and roughly how closely. It cannot see a typed address,
  which still goes only to the City geocoder. | The promise was traded, not disproved, and the
  brief says so in those words. The CSP test was rewritten from "exactly one external host" to
  an explicit two-host allowlist rather than deleted, so a third host is still a decision
  somebody has to make on purpose instead of a diff nobody reads.
- 2026-10-22 | `src/showup/assets/map.mjs` (`DROPPED_SOURCE_LAYERS`) | The basemap's roads were
  competing with the district boundaries drawn over them, so the style is now fetched and its
  `transportation` (20 road and pier layers) and `transportation_name` (6 road labels and
  highway shields) source layers are dropped before MapLibre is handed the object. Water,
  waterways, parks, landuse, buildings, administrative boundaries and place labels survive, and
  the district boundaries become the strongest linework on the map. | Filtering the style is
  better than hiding layers after load: nothing paints and then disappears, so there is no
  flash of roads on a slow connection. It also deleted a silencer — the two null-filter
  highway-shield layers live in `transportation_name`, so removing roads removed the warnings
  they emitted, and `VENDOR_STYLE_WARNINGS` went with them. A vendor exemption that becomes
  unnecessary should be deleted the same day, or it sits there hiding the next thing.
- 2026-10-22 | `src/showup/assets/map.mjs` (`firstLabelLayerId`) | howfar.nyc's basemap is Esri's
  Light Gray Canvas, loaded as **two raster layers** — `World_Light_Gray_Base` and
  `World_Light_Gray_Reference`. The split is the design: the reference layer is drawn above the
  data, so place names stay readable over an overlay. Copied for the vector style by inserting
  our district layers *before* the style's first `symbol` layer, which is one argument to
  `addLayer`. | The thing worth taking from another map is rarely its colours. Labels under a
  translucent overlay are muddy at any palette, and no amount of style-switching fixes it.
- 2026-10-22 | the Esri probe, `scripts/serve.py` (`background_server`) | The first attempt to
  render Esri's tiles failed with `AJAXError: Failed to fetch (0)` and the conclusion drawn was
  CORS. **Wrong.** Esri sends `Access-Control-Allow-Origin: *`. The probe had patched
  `site/_headers`, but `background_server` reads the **repo root** `_headers`, so the CSP being
  enforced was the unpatched one and it blocked the host. | A third party was almost recorded as
  CORS-broken on the strength of a path mistake in the harness. This is the same lesson as
  2026-09-23 in a new costume: a feature tested against the wrong headers is not tested, and
  here the wrong headers were a file one directory away from the right ones. `curl -D -` cost
  two seconds and settled it.
- 2026-10-26 | `_headers`, `src/showup/assets/map.mjs` (`esri-light-gray` now the default) |
  The basemap moved from OpenFreeMap positron to **Esri's Light Gray Canvas**, by owner
  preference: clearer park colours and labelling at lower zoom. `tiles.openfreemap.org` left
  the CSP as `server.arcgisonline.com` entered it, so the two-host count is unchanged. The
  licensing caveat stands and was accepted knowingly: these are keyless endpoints on a
  commercial Esri service and nobody here has confirmed they are licensed for this use.
  Attribution is set on the source. | The CSP allowlist earned its keep — swapping one tile
  host for another touched `_headers` and `tests/unit/test_csp.py`, so the change was visible
  in the diff instead of being a URL edit in a JS file.
- 2026-10-26 | `src/showup/assets/map.mjs` (`fill-opacity` by state) | The overlay was washing
  out the basemap that had just been added for its parks and water: at 0.45 flat, the thing
  underneath stopped reading. The resting fill is now **0.12**, with hover at 0.35 and
  selection at 0.55, and the boundary line went 0.8 → 1.1 px to carry the identification on
  its own. | A district is identified by its boundary, not its tint. Two requests — "give me a
  real basemap" and "the underlying map is not clear" — were the same note twice: the overlay
  was the problem both times, not the tiles.
- 2026-10-26 | `src/showup/assets/map.mjs` (`PAN_MARGIN_DEG`, `MAX_ZOOM`, `setMinZoom`) | The
  zoom and pan are now bounded, as the MTA map does it. The floor is **computed per viewport**
  — whatever zoom `fitBounds` lands on becomes `minZoom`, so the city can never be zoomed out
  into a speck — and the pan box is the geometry's own bounds plus 0.12°. Order matters:
  `fitBounds`, then `setMinZoom`, then `setMaxBounds`, because MapLibre re-checks bounds
  against the current zoom. Verified by driving the controls: 10 zoom-outs leave the view
  pixel-identical, 5 zoom-ins past the ceiling change nothing, and 14 eastward drags settle on
  one unchanging frame. | A fixed `minZoom` constant would have been wrong at every viewport
  but one. Deriving it from the fit is what makes "as far out as the whole city, and no
  further" true on a phone and on a desktop.
- 2026-10-26 | `src/showup/assets/map.mjs` (`PAINT_OVERRIDES`), basemap back to positron |
  **Raster tiles blur on a 2x display and vector ones do not.** Esri's Light Gray Canvas is a
  256 px bitmap set with no retina variant, so its labels upscale and soften; MapLibre
  rasterises a vector style at the device ratio. The basemap returned to OpenFreeMap positron
  and the two things Esri was chosen for were taken by overriding its paint instead: positron
  paints parks `rgb(230,233,229)` against a `rgb(242,243,240)` background — **12/255 apart**,
  which is why green space did not read — and faded woodland in only between zoom 8 and 12. |
  "Which tile set" was the wrong question twice over. The park problem was a 12/255 colour
  difference and the blur was raster-vs-vector; neither needed a different provider, and one of
  them could not be fixed by choosing one.
- 2026-10-26 | `etl/raw/districts.geojson` vs `site/data/districts.geo.json`, district 35 |
  A district boundary that visibly cuts across the street grid at zoom 15 was reported as the
  overlay not matching the basemap. Four hypotheses, three refuted by measurement: our
  simplification deviates **2.6 m at worst** with **0 of 259 raw vertices more than 10 m off**;
  the line sits in the **identical** position on Esri raster and OpenFreeMap vector tiles, so it
  is not tile registration; and `872g-cjhh` is DCP version **26b, updated 2026-05-26**, so it is
  not a stale vintage. What is left is that the City's own published line runs mid-block there.
  | Raising `MAX_ZOOM` to 15 is what made this visible — the geometry is resolution-grade and
  was never meant to be read at 3.6 m/px. The useful discipline was refusing to "fix" it before
  measuring: the obvious story, that our own simplification had cut the corner off a staircase,
  was wrong by a factor of twenty.
- 2026-10-26 | `tests/integration/test_map_route.py` (`_district_paint`) | The choropleth guard
  grepped the whole module for `interpolate`, `step` and `match`, and fired on an `interpolate`
  added to the **basemap's** woodland opacity — a zoom ramp on somebody else's layer, shading
  nothing of ours. Now scoped to the district layers' own paint block, and joined by a check
  that the fill reads `feature-state` and never `get`. | A guard that cannot distinguish our
  paint from a vendor's is a guard that will be edited away the first time it cries wolf.
  Scoping it cost four lines and made it able to state what it actually forbids.
- 2026-10-26 | `src/showup/assets/map.mjs` (`lockPanAtMinZoom`) | At full zoom out on a laptop
  the whole city could still be dragged up and down. `maxBounds` does not prevent it: MapLibre
  constrains the **centre**, and setting the box to the rendered extent still left a step of
  tolerance — two attempts at tightening it (taking `getBounds()` after `fitBounds`, then again
  after an `idle`) both still moved. `dragPan.disable()` below `minZoom + 0.01`, re-enabled on
  `zoomend`, is deterministic. Measured: centre unchanged at `[-73.97779, 40.70616]` after four
  downward drags, and 40.70616 → 40.83590 after the same drag two zoom steps in. | At full zoom
  out the city is already entirely in frame, so there is nothing to pan to and nothing lost by
  turning the handler off. Chasing a geometric fix for two rounds was the wrong instinct when
  the honest statement was "panning is meaningless here".
- 2026-10-26 | the drift test itself | Three rounds of "still drifting" were **the test being
  wrong**, not the fix. The drag moves the cursor across districts, which sets the hover state,
  which repaints a polygon — so the screenshot hash changed while the map had not moved at all.
  The control that settled it: three screenshots with no interaction, which were byte-identical,
  and then reading `map.getCenter()` instead of hashing pixels. | A pixel hash is a proxy for
  "did the view move" and this feature has a second thing that changes pixels. Measure the
  quantity, not a photograph of it — and when a fix appears not to work three times, suspect the
  instrument.
- 2026-10-26 | `data/lookup.json`, reused by the map | Both layers already had neighbourhood
  names and the City's own board labels, shipped for the address box at **5.7 KB gzipped**:
  `districts[].hoods`, `boards[].label` and `boards[].hoods`. The map cards now read "Council
  District 35 — Fort Greene, Clinton Hill, Prospect Heights, Crown Heights" and "Brooklyn
  Community Board 2" rather than a derived label. | The names were one fetch away the whole
  time, and the derived `Community Board 2, Brooklyn` was worse than the City's own string.
  Worth asking what the build already ships before adding anything.
- 2026-10-26 | `data/preview.json`, `render.preview_payload` | Selecting a polygon now opens a
  split view with the page's headline facts, which needed a build-time artifact: the member,
  committees, cadence, office and filed budget requests existed only inside the rendered HTML.
  First cut carried each request's explanation and the agency response and came to **41 KB
  gzipped**; cut to the ask and its priority it is **8.1 KB**, and the board page still has the
  rest. `next_meeting` is top-level and not per district, because Council and committee
  meetings are citywide and belong to no district — the same reason the district is a filter in
  this project and never the organising key. | A preview is a different artifact from a page,
  not a copy of one. Shipping the page's fields verbatim cost five times the bytes for text no
  panel renders.
- 2026-10-26 | `scripts/reflow_check.py` (`_settled_measurement`) | The reflow gate began
  failing inside `make browser` while passing standalone and twice in isolation: a 3 px widened
  viewport, on **a different board page each run** — `/board/304/` then `/board/306/`.
  `Page.loadEventFired` is not the end of layout, and under the full suite (several Chromes,
  one throttled to a quarter speed) a pending style recalc was caught mid-flight. Now it reads
  until two consecutive measurements agree, as the a11y audit already did. | "Different page
  each run" is the tell for a race; a data defect picks the same page every time. This is the
  second gate in this repo to need a settle, and both were written measuring once because a
  single read is obviously enough right up until the suite gets heavier.
- 2026-10-27 | `src/showup/assets/site.css` (the XP theme block), `docs/accessibility-pass.md` §7 |
  The whole site moved to a Windows XP (Luna) aesthetic by owner decision. **Luna's own palette
  fails WCAG AA in two places and both had to be changed**: its pale-blue title text `#dfe8f5`
  on the gradient's light end measures **4.30:1**, under the 4.5 normal text needs, and the
  close box's lightest gradient stop `#e8785a` gives white only **2.89:1**. Changed to white
  and `#c8341a`. axe reports **12 `color-contrast` incomplete**, one per page, because it
  cannot compute a ratio against a gradient. | A period aesthetic is not a licence to inherit
  its contrast. The gate goes quiet on gradients, so the nine ratios are computed and written
  down in §7 — the only thing standing behind them is that somebody worked them out, which is
  worth saying out loud rather than leaving as 12 silent "incompletes".
- 2026-10-27 | `src/showup/assets/map.mjs` (`LAYER_OVERRIDES`) | Big parks rendered in pieces:
  positron ships `landcover_wood` with **`minzoom: 10`**, and this map opens at about zoom 9.6,
  so the wooded part of Central Park and Prospect Park was not drawn at all — only the `park`
  polygon — and the woods appeared the moment the reader crossed zoom 10. The paint override
  that faded woods in across zoom 8–12 was dead code below 10 for the same reason. Fixed with a
  layer-level override, `minzoom: 0`, which needed a mechanism separate from the paint one. |
  A raster basemap has no such seam, which is why Esri looked complete and this did not: its
  tiles are drawn at every level. Two overrides were fighting each other, and the one that
  looked like the fix — opacity by zoom — was below the floor where the layer existed at all.
- 2026-10-27 | Jamaica Bay, `872g-cjhh` vs the OSM basemap | District outlines trace marsh
  islands — Fishkill Hassocks, Sails Point Hassock, Black Wall and several unnamed rings — that
  the basemap draws no land for, so they read as outlines floating in navy water. Others in the
  same bay (Canarsie Pol, Ruler's Bar Hassock, Winhole Hassock) do have land under them. Our
  geometry is DCP's **shoreline-clipped** council districts; the basemap is OSM, which has not
  mapped every hassock. **Nothing in our pipeline is wrong** and the outlines are the real
  boundary. | The saturated palette is what exposed it: at pale grey the same disagreement was
  invisible. DCP also publishes water-areas-included variants (`mkqi-d8x3`, `jgqm-ccbd`) whose
  districts cover the bay solidly and would not trace islands at all — a data decision, not a
  styling one, because `/references/` names the dataset the site resolves addresses against.
- 2026-10-27 | `wwhr-5ven`, `qm5f-frjb`, `wa6b-r9jh`, `council.nyc.gov/pb/` | Asked to show
  participatory budgeting **per district where it exists**, and no source publishes that. The
  three NYC Open Data PB datasets all report `rows_updated` 2020-02-08 and the projects table's
  newest `vote_year` is **2017** — nine years stale, and keyed to district numbers the 2023
  redistricting replaced, so its "district 35" is not today's district 35. The Council's own
  `/pb/` page covers the FY2027 cycle and **names no participating districts at all**, only the
  four members who started the programme in 2011. | So the programme is stated as a fact about
  the Council — residents vote on small capital projects, minimum $50,000, physical
  infrastructure in a public space, five-year life — and the per-district claim is refused out
  loud, in the same shape as the testimony cut-off refusal. A stale dataset keyed to superseded
  boundaries is worse than no dataset: it is wrong twice and looks authoritative.
- 2026-10-27 | `render_index(meetings=...)`, `src/showup/assets/map.mjs` | The next Council
  meeting moved off the district panel and onto the landing page. It was never a district fact:
  Council and committee meetings are citywide, and showing one inside "Council District 35"
  invited the reading that the district holds it. Rendered at build time, so the landing page
  needs no script for it. | This was already written down as a principle — the district is a
  filter, never the organising key — and the panel had broken it within a day of being built.
  The `(citywide)` label it carried was a patch over a placement that was wrong.
- 2026-10-27 | `src/showup/assets/map.mjs` (`refit`) | Opening the panel at full zoom out left
  the city half-hidden behind it with no way to recover: `minZoom` had been computed from the
  fit across the **full-width** map, so once the panel took 25rem the city no longer fit at
  that zoom — and pan is locked at `minZoom`, so it could not be dragged back. The fit, the
  floor derived from it and the pan box derived from the floor all depend on the container, so
  all three are now recomputed together whenever the width changes. | Three values computed
  once from a width that then changes. Deriving the floor from the fit was the right idea and
  exactly what made the bug unrecoverable, because the lock trusted a stale floor.
- 2026-10-27 | the board share bars, `site.css` (`.share-fill`) | Shares render as bars, not a
  stacked bar: they are measured per board and do not sum to 100 (44 + 29 + 23 for district
  35), so a stacked bar would imply a partition the data does not make. One series, so one hue
  and no legend — each bar is named by its own link. Width is an **SVG geometry attribute**,
  because `style-src 'self'` refuses the usual `style="width:44%"`, and the ends are square
  because `preserveAspectRatio="none"` is what lets the bar stretch and would distort a corner
  radius. Measured: fill 5.17:1 on the group background, and the track only **1.45:1**, so the
  track carries a border rather than relying on fill. | The CSP shaped the chart. Every
  familiar way to draw a proportional bar sets an inline style, and the one that does not —
  geometry attributes — costs the rounded ends.
- 2026-10-27 | the panel's budget heading and priorities | The heading read "Fiscal 2027 budget
  requests — 56 filed", which changes with every edition, and three requests all rendered as
  "1." — because **priority is the rank within a budget category**, so it repeats. This repeat
  is already recorded in `docs/voice.md` as a note the board page has to carry, and the panel
  reproduced the exact misreading that note exists to prevent. Heading is now "Budget
  requests"; the fiscal year and count moved into the lines; the number is gone and the
  category carries the meaning. | A fact about the data does not belong in a label. And a
  misreading already written down in the voice doc was reintroduced the first time the same
  field was shown somewhere new — the note was attached to the page, not to the field.
- 2026-10-27 | `council.nyc.gov/press/wp-json/wp/v2/posts` | **Supersedes the entry above that
  refused the per-district participatory budgeting claim.** The press releases are on a
  *second* WordPress install with its own public REST API, which is why searching the main
  site's API suggests PB coverage stopped in 2019 — the main install has no press post type at
  all. `?search=participatory%20budgeting&per_page=100` returns 43 posts; two are results
  releases. Post **3126** (`/press/2026/05/22/3126/`) enumerates 22 districts **and states "22
  Council Districts" in its own body**, so the parse has a checksum rather than a guess.
  Verified against post 2892 (FY2026, 24 stated / 24 parsed). | The checksum is the reason this
  is usable at all: a reworded release fails loudly instead of dropping a district, which would
  render as "not taking part". FY2025 has no results release — only a vote-week post naming a
  count and no districts — so cycles are not uniformly recoverable.
- 2026-10-27 | `rnd.council.nyc.gov/ideamap/map/` | The only source for the cycle that is **open
  now**: 24 districts carry a `data-district` attribute. The page states **no year, no fiscal
  year and no vote date** — grepped `FY20\d\d`, `[Ff]iscal [Yy]ear 20\d\d` and `20\d\d`, all
  zero matches — so any "FY2028" label is inference, not a published fact, and is not rendered.
  The visible Council-member table lists every district, so a name there is not evidence of
  participation; only the attribute is read. | refused: labelling the open cycle with a year we
  derived. The page is unversioned and overwritten each cycle, which is why the roster is
  fetched weekly rather than pinned.
- 2026-10-27 | `etl/raw/district_pages.json` | Tried the cheapest possible PB signal — a
  `council.nyc.gov/<member>/pb/` link in a district page's own nav, already in the cache at zero
  extra fetch cost. It appears on **1 of 51** pages (district 35). Zero false positives, 23
  false negatives against the idea map. | refused: a signal that only some members opt into
  measures the member's site habits, not the programme. Worth not re-testing.
- 2026-10-27 | `showup.sources.participatory_budgeting` | The two rosters **disagree**: 24 in the
  open cycle, 22 in the FY2027 results, **21 in both**; 4/17/21 are open-only and 8 is
  FY2027-only. | So participation is a fact about a *cycle*, never a standing property of a
  district. Both views state each roster separately with its own date and link, and a district
  in neither is reported as unlisted — not as having no programme, which is a claim neither
  source supports.
- 2026-10-27 | `council.nyc.gov/pb/` | On this date the programme page still advertised the
  **already-closed** FY2027 vote window ("April 11-19, 2026") and "Thank you for your
  participation this cycle." | So `/pb/` is linked as the programme's own page and never parsed:
  a cycle read off it would have been a year stale. Dead ends also confirmed:
  `/ideamap/districts/` returns HTTP 200 with a literal `[]`; `/ideamap/ideas/` and
  `/ideamap/api/` 404; and `/pb/vote/`, `/pb/districts/` and `/budget/participatory-budgeting/`
  return a real 404 **carrying a ~46 KB styled page with an empty `<title>`** — the inverse of
  the usual trap, so check the status *and* the title.
- 2026-10-27 | `mkqi-d8x3` vs `872g-cjhh` | Switched the shipped council geometry to DCP's
  **water-areas-included** districts. Measured ring counts per district: **42 goes from 28
  rings / 7,417 points to 1 ring / 340**, 32 from 13 to 1, 31 from 11 to 1; city-wide 185
  rings to 53. Districts away from water are the same line — 36 is 197 points against 195,
  35 is 259 against 257 — so this is not a different boundary over land, it is the same
  boundary without the marsh islands the basemap never draws. The file is 862 KB against
  3.8 MB. | So the second report of "islands look weird" (district 42, after Rockaway) is
  fixed at the data layer rather than by styling. Land points hit-test identically, which
  is where addresses are; a point in open water now resolves to a district instead of to
  nothing, which is the City's own assignment.
- 2026-10-27 | `crosswalks/council_to_boards.json` | Regenerating the crosswalk against the
  water-included districts **halved every coastal share**: district 1 went 0.5375/0.2997/
  0.1318 to 0.2688/0.1475/0.0645, so its three boards summed to **0.48** instead of 0.97,
  and district 5's single board went 0.9813 to 0.5814. The missing half is open water,
  because the shares are areal and the boards stay shoreline-clipped. | refused: one
  geometry for both jobs. `872g-cjhh` is kept as a build-only source purely as the
  **denominator** for "what share of this district does board N cover"; it is never
  shipped and never drawn. With that split the regenerated crosswalk is byte-identical to
  the committed one, and 0 of 215 ZIP assignments changed.
- 2026-10-27 | `map.mjs` fill-opacity | A `['*', <feature-state case>, <interpolate on
  ['zoom']>]` expression is **invalid**: MapLibre requires `['zoom']` to be the top-level
  expression or sit inside a top-level `interpolate`/`step`. It does not report this as an
  error — it **discards the whole style and falls back**, so the symptom was a map showing
  district outlines on the fallback `#f6f7f9` background, no basemap, no fill. `make
  console` reported 0 complaints, an injected `window.onerror` collector caught nothing,
  and the only external evidence was that `tiles.openfreemap.org/planet` was fetched once
  and aborted and no `.pbf` ever followed. | The fix is `['interpolate', ['linear'],
  ['zoom'], 12, <case>, 15, <case>]` — zoom outside, the data-driven case as each stop's
  output. Gated now by `TestTheMapActuallyFinishesLoading::test_the_basemap_really_drew`,
  which asserts a vector tile was fetched; verified by reintroducing the bad expression.
  Isolating this cost a bisect against a rebuilt pre-swap tree, because the obvious suspect
  was the geometry change landing at the same time and it was not that.
- 2026-10-28 | `872g-cjhh` ring areas | Tried to keep the land-only boundary and simply drop
  the marsh rings. **There is no threshold that works.** The Jamaica Bay hassocks in
  districts 31, 32 and 42 measure 0.10-1.07 km2, and the real islands elsewhere sit in the
  same band: Governors Island 0.71, Roosevelt Island 0.58, City Island 0.30. Of 185 rings,
  71 are under 0.01 km2 and 61 are over 1.0, but the middle is a continuum. | refused:
  an area filter. It would have had to drop Governors Island to drop a hassock.
- 2026-10-28 | `map.mjs` `districtInsertionId` | Owner disliked the water-included districts
  tinting open water. Fixed without changing the data: the district layers are inserted
  **beneath the basemap's water fill** rather than beneath the first symbol layer, so the
  water paints over exactly the part of each polygon that is water. A district then reads
  as land-only while its geometry stays water-inclusive, which is what keeps the marsh
  islands from being traced. The boundary across open water is hidden too, which is no
  loss — nobody needs the line down the middle of the bay. | So "which geometry" and "what
  the reader sees" turned out to be separable, and the layer order was the cheaper lever.
  Roads, parks and labels now draw above the tint as well, which also helps legibility.
- 2026-10-28 | `map.mjs` layer order | Putting the district **line** under the water also put
  it under the roads and building footprints, and the boundary came out visibly broken.
  Split into two insertion points: the fill goes beneath the water fill, the line stays
  before the first symbol layer. | The fill and the boundary want opposite things from the
  stacking order, so they cannot share a `beforeId`.
- 2026-10-28 | `data/zips.geo.json` | Measured the ZIP outline overlay at four
  simplifications: ~2 m is 125 KB gzipped, ~11 m is 51 KB, ~33 m is 33 KB, ~88 m is 18 KB.
  The rest of the map's data is 145 KB gzipped in total, so the finest option would have
  been an 86% increase for a feature only a ZIP search uses. Shipped at ~11 m / 4 dp and
  fetched **on the first ZIP lookup only**. | ~11 m is still finer than the ~110 m lattice
  the crosswalk samples at, so the overlay is not the weak link in anything. Nothing is
  hit-tested against it: the crosswalk answers which districts and boards a ZIP covers.
- 2026-10-28 | `crosswalks/council_to_boards.json` | Added `zip_boards` (a third overlap
  sweep, ZCTAs against community districts) and `zip_zcta` (real ZIP -> the modified ZCTA
  polygon that covers it, because several real ZIPs share one shape). All 215 ZIPs resolve
  to at least one board, so the board layer answers a ZIP as completely as the council
  layer does. | A typed ZIP could not be drawn without `zip_zcta`: the geometry is keyed by
  ZCTA and 11249-style ZIPs are members of another code's polygon.
