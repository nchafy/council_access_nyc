# Phase 1 — scope

**What this is for:** the exact, small thing to build first. **When to read it:** before writing
any code, and instead of the outline's §8 milestones, which this supersedes for the near term.

**Status: built and running locally as of 2026-09-23.** Exit criteria in §6 are ticked
individually. Six of seven are met. The seventh, criterion 5, is met except for one thing that
cannot be automated: **a real screen-reader pass has not been run** — see
`docs/accessibility-pass.md` §3.2. Everything else in it is gated in CI. Run it with
`make fetch && make serve`, and the gates with `make gates`.

Decided by the owner 2026-09-21: barebones. One input — a dropdown or an address — produces one
page of information and links. No map. No analysis. Security is the top priority. P8, P9 and P10
(never mislead / accessible and private / still true in two years) are all in.

**Phase 1 runs locally only.** No domain, no hosting, no public deploy, nothing indexed. The
`_headers` file and the Cloudflare Pages decision stay in the plan for later, but nothing is
published in this phase and no deploy credential is created. Two consequences worth stating:
the security posture improves (there is no production surface, and the build needs no secrets at
all, so there is nothing for a malicious dependency or PR to exfiltrate), and the header work
does **not** get deferred — a local dev server must apply the real headers, because a CSP that is
not served is not a CSP and one discovered at deploy time is one rewritten under pressure.

Estimated **8–11 days** for one person, down from 10–13 now that hosting and deploy are out.

---

## 1. What Phase 1 is

A user arrives, identifies where they are **once**, and gets a page answering: who represents me,
where and when can I show up, what can I still do about it, and who do I call. Every fact links to
the official source it came from.

**Two views, added 2026-09-22 on the owner's decision.** They answer different questions and are
not variants of each other:

- **`/district/{1-51}`** — the City Council view. Who legislates for you, the committees your
  member sits on, the next five Council meetings with addresses, and how to testify including the
  written-testimony window.
- **`/board/{code}`** — the community board view. The most local unit of City government: the
  standing monthly cadence, the zoning review role, the office to call, the council districts
  that cover it — and the route almost nobody knows, that **board committees seat non-board
  members of the public**.

The board view is deliberately not a district page with different data. A board has no hearing
calendar we can read (no City dataset publishes board agendas), so the page says so and sends the
reader to the board's own site; and its participation route is committee membership and
appointment by the Borough President rather than testimony.

Ways in, all producing one of those two pages:

1. **Two dropdowns**, one per view, each with a plain-link list below it for the
   no-JavaScript, keyboard and screen-reader path.
2. **An address box.** Built 2026-09-22. Submit-only — there is no
   autocomplete-as-you-type, which removes a class of keystroke leakage to a third
   party. An address, ZIP, neighbourhood name or district number all work, and
   everything except a street address resolves **entirely locally** from a
   committed index, never touching the geocoder. ZIPs straddle districts, so a ZIP
   offers the choice instead of guessing. `private=true` on every geocoder call,
   asserted by the gate. Out-of-city input is refused by name ("that looks like
   Newark") from what the geocoder says it *parsed*, before anything renders.

`/district/35` and `/board/302` are the canonical, shareable URLs. The typed address never
appears in either.

## 2. What is on the page

Six blocks, in this reading order. Everything is a fact plus a link; nothing is computed except
the two deadlines in block 4.

1. **Where you are.** Council district number and neighbourhood names. The overlapping community
   board(s). One sentence distinguishing the two, because residents routinely conflate them and
   the board is often the correct venue.
2. **Your Council Member.** Name, party, seat status, email, district office address and phone,
   legislative office at 250 Broadway, and a link to their council.nyc.gov page. Vacant seats are
   a designed state, not an error.
3. **The committees they sit on**, with chair and co-chair roles marked. This is the honest
   district-level answer to "what is being worked on for me" — these are the rooms where your
   representative has a seat.
4. **The next 5 meetings.** Citywide and chronological — no ranking, no scoring. Each shows
   date, time (or `Deferred`), whether it is in person, hybrid or remote, the venue's real street
   address, the committee, and the topic where the agenda is published. Each links to its
   Legistar meeting-detail page and its agenda PDF. Two computed values per meeting: the
   **written-testimony safe-until timestamp** (`start + 72h`, a provable lower bound) and the
   **accommodation request-by date** (3 business days before, against a committed holiday table).
5. **How to be heard.** The verified procedural facts: in-person testimony needs no
   pre-registration; remote requires the Register to Testify form; written testimony is accepted
   up to 72 hours after adjournment, DOC/DOCX/PDF, 10 MB. Entry rules — NYPD security and metal
   detectors, photo ID at 250 Broadway, no signs larger than 8.5" × 11". The refusal strings:
   the registration cut-off and the per-speaker time limit are published nowhere official, so we
   give `hearings@council.nyc.gov` / 212-482-4219 instead of a guess. Leads with the fact that
   **only Council Members introduce legislation** — there is no public petition route.
6. **Your community board(s).** Matched by **geometry**, not by the boards dataset's own
   `council_district` column, which omits seven council districts entirely. Most districts
   overlap two or three boards, listed by how much of the district each covers. Office address,
   phone, email, website, and the meeting cadence quoted verbatim. Board chairs and district
   managers are never named — we publish the office, which is staffed and whose job is to hear
   from you.

Plus a persistent footer: when each source was last fetched, and the covered forward window
stated literally.

## 3. Explicitly not in Phase 1

Cut for now, each recoverable later:

- **The map.** No MapLibre, no tiles, no choropleth, no rendered geometry.
- **All analysis.** No shortlist ranking, no salience, no vote parsing, no dissent figures, no
  `bloc_concentration`, no agenda-item classification, no PDF parsing of any kind.
- **Transcripts and participation data.** The whole of J4's measured half.
- **Per-committee and per-hearing pages.** Phase 1 has one page type plus a front page.
- **Calendar files (`.ics`).** Cheap, but not needed to prove the product.
- **Search by subject, and the citywide browse view.**

**Note on geometry:** the address path needs the district polygons, because the NYC geocoder
returns coordinates but *not* a council district, so the lookup is a point-in-polygon test in the
browser. Phase 1 ships simplified geometry **for resolution only, never for display** — the
accuracy bar is correctness of assignment, not appearance, and no tile or rendering library is
involved.

The tolerance was chosen by measurement, not taste. Over a 37,000-point citywide lattice,
comparing the district each point resolves to against full precision: 11 m tolerance gives 60 KB
gzipped and 0.059% wrong; **2.2 m gives 132 KB and 0.011%**; no simplification gives 372 KB and
0.005%. The floor is not zero — even unsimplified geometry disagrees on 2 points that sit exactly
on a shared edge. 2.2 m is close to the floor at a third of the 300 KB budget, and
`tests/unit/test_geo.py::TestSimplifiedGeometryAgrees` fails if the tolerance is loosened without
re-measuring. Because boundary cases remain possible, the address result always offers the City's
own lookup: our geometry is a copy of DCP's published lines, not the legal definition.

## 4. Security — the top priority

Stated as a threat model, because this product has no accounts, no sessions and no database, so
the usual checklist does not apply and the real risks are elsewhere.

### 4.1 Injection through scraped upstream content — the primary risk

We render text we did not author: committee names, meeting topics, bill titles, venue strings,
member names, community board cadence strings. All of it arrives from third-party HTML that we do
not control. A hostile or merely malformed value reaching a page unescaped is the most likely way
this site ever hurts someone.

- **All upstream text is untrusted input.** Tags are stripped at ingest, entities decoded once,
  and the result stored as plain text. No upstream HTML is ever stored as HTML.
- **The frontend never uses `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or
  `eval`.** Text goes in via `textContent`; attributes via `setAttribute`. A CI grep fails the
  build on those identifiers.
- **URLs from upstream are allowlisted by host and scheme** before becoming an `href` —
  `nyc.legistar.com`, `legistar.council.nyc.gov`, `council.nyc.gov`, `data.cityofnewyork.us`,
  `nyc.gov`, https only. `javascript:` and `data:` can never survive. Anything else renders as
  inert text.
- **Fixtures include a hostile case.** A committed fixture carries a committee name containing
  `<script>`, a quote, and an entity, and a test asserts it renders inert.

### 4.2 Headers and transport

- `Content-Security-Policy: default-src 'none'` and add back only what is needed —
  `connect-src` limited to `geosearch.planninglabs.nyc`, `script-src 'self'`, `style-src 'self'`,
  `img-src 'self'`. **No inline scripts, no inline styles, no `unsafe-inline`.**
- `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, HSTS with a long max-age, HTTPS only.
- `rel="noopener noreferrer"` on every outbound link.
- Committed as a `_headers` file for the eventual Cloudflare Pages deploy, because these must be
  **response** headers and a meta tag cannot deliver most of them.
- **Locally, a small stdlib dev server reads `_headers` and applies it** (`scripts/serve.py`, no
  dependencies, matching the sibling project's stdlib-only preference). Developing against
  `python -m http.server` would send no CSP at all, so every violation would surface for the
  first time at deploy — which is exactly when it gets waived. A test asserts that the served
  response carries the headers, run against the local server in Phase 1 and against the deploy
  later.

### 4.3 Zero third parties

No analytics, no tag manager, no hosted fonts, no CDN scripts, no embeds. Legistar's own pages
embed AddThis; we link to them and never iframe them. Every asset is first-party, which is what
makes the CSP above enforceable rather than decorative.

### 4.4 The user's address

- Sent only to the geocoder, with `private=true`, on submit only — no autocomplete-as-you-type in
  Phase 1, which removes a whole class of keystroke leakage.
- Never written to a URL, query string, fragment, cookie, `localStorage`, `sessionStorage` or any
  log. The redirect target is `/district/35`.
- A CI grep fails the build if a geocoder call site omits `private=true`.

### 4.5 Supply chain and build integrity

- Dependencies stay minimal and pinned via lockfile. **Phase 1 needs no PDF parser and no map
  library**, which is a security benefit of the reduced scope, not just a time saving.
- GitHub Actions pinned to commit SHAs, not tags. `permissions:` set to least privilege
  (`contents: read` by default).
- The build requires **no secrets**, so there is nothing for a malicious PR to exfiltrate.
  Deploy credentials live only in the deploy job and are never exposed to build steps that
  process untrusted upstream content.
- `mainline` is protected: no force-push, no direct push.

### 4.6 Not being the attacker

Polite crawl rates — `council.nyc.gov` at 1 request / 10 s, honouring `Crawl-delay`. We are a
guest on these servers, and hammering a city website is a security failure in the direction we
control most easily.

## 5. The SLA in Phase 1

The outline's §6A budgets are written around a map click, which does not exist yet. They still
apply, reassigned:

- **Dropdown selection → page rendered: p95 ≤ 200 ms.** This inherits SLA-1 unchanged. It is
  easier to hit than the map version, because the pages are pre-rendered and a selection is a
  navigation to a static document. There is no geometry to hit-test and nothing to prefetch.
- **Address submit → page rendered: p95 ≤ 1 s**, our own share ≤ 270 ms. Unchanged, and the
  geocoder leg is still measured rather than promised.
- **Autocomplete (SLA-3) does not apply.** Phase 1 is submit-only, by the privacy decision in
  §4.4 — which removes the interaction the budget existed for.

The consequence for §6A.3's design constraints: the inline 51-district index and the
prefetch-on-hover machinery are **not needed in Phase 1**. Pre-rendering one page per district
achieves the same latency more simply. Those constraints return when the map does.

## 6. Exit criteria

1. ✅ `scripts/serve.py` serves the built site locally, and picking any of the 51 districts from
   the dropdown — or typing an address, ZIP, neighbourhood or district number — renders all six
   blocks correctly. 59 community board pages as well, which was added after this list was written.
2. ✅ An address outside NYC is refused by name ("that looks like Newark") rather than silently
   mis-assigned, checked against what the geocoder says it *parsed* before anything renders.
3. ✅ Response headers from the local server match §4.2, asserted by `scripts/verify.py` against
   live responses. `_headers` is committed for the later deploy and the assertion can be pointed
   at a real host unchanged.
4. ✅ The hostile-content fixture renders inert, asserted end to end — plus ~8,500 generated fuzz
   cases over the parsers and a committed corpus of 104 input/expected pairs.
5. ⚠️ **Mostly met; one half genuinely open.** Built 2026-09-23.
   - ✅ **axe** clean on **all 114** pre-rendered pages at WCAG 2.2 AA, gated in CI, with a
     committed negative control (`tests/fixtures/a11y_broken/`) proving the gate can still fail
     and a floor on rules-exercised per page proving it actually ran.
   - ✅ **The keyboard pass**, automated: 122 checks over 9 page types, driven with real `Tab`
     keypresses in a real browser — skip link first and visible, focus into `<main>`, DOM order,
     reachability, a ≥2px ring at every stop, `Shift+Tab` in reverse. Plus the accessibility tree
     (landmarks, accessible names, one h1, no skipped heading levels), and the no-JavaScript path
     verified with script execution disabled in the browser rather than inferred from the markup.
   - ❌ **The screen-reader pass has not been run.** Reading the accessibility tree is not
     listening to a screen reader, and automating that distinction away is the one shortcut this
     product cannot take. `docs/accessibility-pass.md` §3.2 is the procedure, §4 is the record,
     and the record says NOT RUN. **This is the one thing left in Phase 1.**
   - ✅ **The 60 KB budget**, gated in CI as arithmetic over the built bytes — front page 13.7 KB
     gzipped, district pages 7.4 KB, boards 6.1 KB, all JavaScript 6.5 KB against a separate
     12 KB ceiling, geometry 132 KB against its 300 KB after-first-paint budget.
   - ✅ **The 3 s throttled-3G gate**: p95 over 20 cold runs per page on 3G Fast with a 4× CPU
     throttle — 906 ms, 741 ms and 723 ms against 3000 ms. Thresholds and profiles live in the
     committed `perf-budget.json`. DevTools' Slow 3G preset yields 4.3–5.1 s; it is reported but
     not gated, and the reasoning is in that file rather than being a quiet omission.
6. ✅ The refresh is runnable as one local command (`make fetch`), fails closed on a bad fetch,
   and the staleness notice provably appears when `manifest.json` is hand-aged. Running it *on a
   schedule* is deferred with hosting. Crawl rates come from each host's own `robots.txt`, and an
   `upstream` test fails if the City raises its delay above ours.
   **Corrected 2026-09-23:** the staleness claim used to be true only over HTTP and false in a
   browser. `connect-src` omitted `'self'`, so `/manifest.json` could not be fetched at all and
   the notice never rendered for any reader. The tick now rests on
   `tests/browser/test_console.py::TestTheStalenessNoticeReallyRenders`, which ages the manifest,
   loads a real page in a real browser behind the real headers, and asserts the rendered text
   names the source, its age in days, and the instruction not to rely on the meeting times.
7. ✅ Every fact on the page carries its source link, and the footer carries each source's fetch
   date with the covered forward window stated literally.

## 7. Open, for the owner

1. ~~Domain name and indexing.~~ **Resolved 2026-09-21: neither.** Phase 1 is local only.
2. **Shortlist size confirmed at 5** for Phase 1 as "the next 5 meetings". When ranking arrives
   in a later phase, is 5 still right, or does a ranked list want more?
3. Project identity and the correction-contact address (brief §8.4) — deferred with publishing,
   since nothing is public in Phase 1 and there is no one to receive a correction yet.
4. Whether `council_access_nyc` should be a **public or private** GitHub repository. It has no
   remote today, so nothing is published either way until one is added.
