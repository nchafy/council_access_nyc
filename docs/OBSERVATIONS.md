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
