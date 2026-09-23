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
- 2026-09-21 | `ruf7-3wgc.council_district` | 59 community-board rows carry only 44 distinct
  council-district values; districts 5, 8, 15, 20, 27, 32 and 40 appear nowhere, because the
  column records the district of the board's *office*, not the districts it covers. | refused:
  the obvious one-line join would have left 7 of 51 districts with no board. Any
  administrative-geography crosswalk must come from geometry, and a second jurisdiction will
  have the same trap under a different column name.
- 2026-09-21 | `crosswalks/council_to_boards.json`, `src/showup/geo.py` (`overlap_shares`) | A
  ~110 m lattice sampled over the city resolves council-to-community-district overlap in ~35 s
  with no polygon-clipping dependency; results validated against known geography (D35 → Brooklyn
  CB 2/8/9). | generic: "sample a lattice instead of taking a clipping dependency" survives any
  jurisdiction; committing the result so a boundary change is a reviewable diff is the part
  worth copying.
- 2026-09-21 | `uvw5-9znb` district 3 vs `council.nyc.gov/district-3/` | The open dataset records
  a term ending 2026-02-03 with no successor row while the scraped page already names the new
  member — the scrape is *fresher* than the official dataset after a special election. | generic:
  when two public sources disagree, resolve toward the reading that does not remove information
  from the user, and disclose the conflict on the page. A seat is filled if either source says so.
- 2026-09-22 | `nyc.gov/site/communityboards` | Board committees seat **non-board members of the
  public** — join the discussion, cannot vote, most boards want an application and a resume.
  Almost nobody knows this and the bar is far lower than testifying. | generic: the highest-value
  participation route is often the least advertised one; look for it before building analytics.
- 2026-09-22 | `src/showup/text.py` (`strip_tags`), `tests/corpus/strip_tags.jsonl` | The fuzzer
  disproved two invariants asserted confidently: `strip_tags` output CAN contain the characters
  `<script>` (from `&#60;script&#62;`, decoded correctly once), and it is NOT idempotent
  (`"Defer&#x3C;red"` → `"Defer<red"` → `"Defer"`). | generic: for an HTML-stripping boundary the
  guarantee lives at the ESCAPER, not the stripper; assert it there. Apply stripping exactly once,
  to raw upstream text, and audit the call sites rather than trusting idempotence.
- 2026-09-22 | `tests/test_privacy_guard.py` (timemap) vs `scripts/verify.py` (this repo) | Both
  repos have a "privacy guard" and they protect opposite parties: timemap's asserts the *owner's*
  data is absent from fixtures, this one asserts *third parties'* names are absent from published
  pages. | misfit: a shared guard would have to parameterise *whose* privacy, and a passing guard
  protecting the wrong party is worse than none. Not a duplication — do not count it as one.
- 2026-09-22 | `tests/contract/test_output_contract.py` (timemap) vs the twelve upstream contract
  tests here | Same name, different mechanism: timemap validates its *own output* against a JSON
  Schema; this repo asserts *upstream* still returns the shape it parses, on a job that never
  gates a deploy. | misfit: two features wearing one word. Any shared vocabulary needs both
  concepts named separately before either is abstracted.
- 2026-09-22 | robots.txt for the three scraped hosts | `council.nyc.gov` publishes
  `Crawl-delay: 10` (51 pages ≈ 8.5 min), `data.cityofnewyork.us` publishes 1, and
  `nyc.legistar.com` serves **no robots.txt at all** (404). | generic: read each host's own file
  rather than assuming a global rate, and where none exists the delay is your choice and not a
  permission you were granted. An `upstream` test re-reads it so following it is not a memory.
- 2026-09-22 | `src/showup/geo.py` (`SIMPLIFY_TOLERANCE_DEG`) | Measured over a 37,000-point
  lattice against full precision: 11 m tolerance → 60 KB gzipped and 0.059% of points assigned to
  the *wrong* district; 2.2 m → 132 KB and 0.011%; unsimplified → 372 KB and 0.005%. The floor is
  not zero — points on a shared edge are ambiguous even unsimplified. | generic: choose a
  simplification tolerance by measuring assignment *correctness*, not file size, and keep the test
  so loosening it cannot pass silently. A first attempt at this sweep was a no-op because the
  tolerance default binds at function definition.
- 2026-09-22 | Chrome `--headless=new --dump-dom` | Returns the page's *original source*, not the
  live DOM — even a synchronous `textContent` change is invisible. Also, macOS clamps a Chrome
  window's minimum width below ~500 px, so `--window-size=390` yields a 390-wide image of a
  ~704-wide layout, which reads exactly like a CSS overflow bug. | generic: for browser assertions
  without a CDP dependency, have the page report over HTTP to a recording server. Do not trust a
  screenshot's width to be the layout width.
- 2026-09-22 | `src/showup/fetch.py` (`_fetch_district_pages`), cold run on a fresh clone | A
  9-minute polite crawl of 51 pages lost 4 to transient DNS failures, so the invariant correctly
  refused 47/51 — but a fresh clone has **no previous cache to keep**, so the build could not run
  at all and the operator had to repeat the whole crawl. Fixed with one retry pass over just the
  failures. | generic: "fail closed and keep the last good copy" degrades to "fail" on first run.
  Any long polite crawl needs a retry pass over its own failures, or the cold path is a coin flip.
- 2026-09-23 | `_headers` `connect-src`, found by the first browser run behind the real CSP | The
  directive named the geocoder and omitted `'self'`, so all three same-origin fetches were refused:
  `/data/lookup.json`, `/data/districts.geo.json`, `/manifest.json`. Local resolution of a ZIP,
  neighbourhood or district number therefore fell through to the geocoder — a policy written to
  protect the reader's address was causing **more** of their input to be sent — and the staleness
  notice silently never rendered. Invisible because the one browser test served the site from a
  bare file server with no CSP, and `verify.py` fetched the manifest over plain HTTP. | generic:
  testing a feature and testing it *under the policy shipped with it* are different tests, and the
  second one is the only one that is true. Any project with a CSP needs a gate that loads every
  page in a browser behind the real headers and fails on any console error.
- 2026-09-23 | `tests/fixtures/a11y_broken/`, the axe negative control | The deliberate
  colour-contrast defect was in a `<style>` block and axe never reported it, because `style-src
  'self'` blocked the inline CSS and the rule applied to nothing. The negative control was itself
  testing nothing, and caught that by being the thing under test. | generic: a negative control
  built for a gate must be built for the *environment* of the gate. Write it to the same
  constraints as production, or it proves the gate works on a page that cannot exist.
- 2026-09-23 | `scripts/cdp.py`, headless focus behaviour | Tabbing past the last focusable element
  does not release focus to the browser's own controls in headless Chrome — there are none, so
  focus wraps to the top. An assertion that "focus can leave the page" reported all 9 page types as
  focus traps. The property that actually distinguishes a trap is reachability: n Tab presses must
  visit n distinct elements. | generic: assert the invariant a defect breaks, not the behaviour a
  windowed browser happens to have. Also: `Input.dispatchKeyEvent` with `rawKeyDown` moves focus for
  Tab but skips Blink's implicit form submission for Enter, which needs `keyDown` carrying `text`.
- 2026-09-23 | `scripts/perf.py`, throttled cold load, 20 runs per page | Cold load to interactive
  on 3G Fast + 4x CPU: front page p95 906 ms, district page 741 ms, board page 723 ms, against a
  3000 ms promise. On DevTools' own Slow 3G preset the same pages take 4.3-5.1 s, which is three
  2000 ms round trips before a byte of ours is considered. | refused: gating on Slow 3G, because
  under it the number measures the network and not our page — the only way to pass would be to stop
  loading a stylesheet. Measured and published beside the gated figure rather than dropped.
- 2026-09-23 | page weight, gzipped, at the 60 KB R40 budget | Front page 13.7 KB, district pages
  7.4 KB, board pages 6.1 KB, 404 at 4.3 KB; all JavaScript together 6.5 KB; geometry 132 KB
  against its separate 300 KB after-first-paint budget. | generic: a budget met at 22% is worth a
  second, tighter ceiling on the part that can grow without bound — here, script alone at 12 KB,
  because React with its DOM package is ~45 KB gzipped and would hide comfortably inside 60 KB.
- 2026-09-23 | `site/index.html`, `site/district/index.html`, `site/board/index.html` | All three
  are byte-identical (29,458 bytes): the front page carries both link lists, so both index routes
  are copies of it. Not a defect — it is what makes the no-JavaScript form target work — but the
  axe and console sweeps test the same bytes three times. | generic: when enumerating "every page"
  for a gate, dedupe by content hash before spending browser time on it.
