# Phase 1 — scope

Read this before writing any code. It supersedes the outline's §8 milestones for the near term.

**Status: built and running locally as of 2026-09-23.** Six of seven exit criteria (§6) are met.
Criterion 5 is met except for the one thing that cannot be automated: **a real screen-reader pass has
not been run** (`docs/accessibility-pass.md` §3.2). Run with `make fetch && make serve`, gates with
`make gates`.

Owner decisions, 2026-09-21: barebones; one input produces one page of facts and links; no map; no
analysis; security is the top priority; P8, P9, P10 all in. **Phase 1 runs locally only** — no domain,
hosting, public deploy, indexing or deploy credential. Two consequences: the build needs no secrets,
so there is nothing to exfiltrate; and the header work is *not* deferred, because a CSP discovered at
deploy time is a CSP rewritten under pressure. **8–11 days** for one person, down from 10–13 with
hosting out.

## 1. What Phase 1 is

A user identifies where they are **once** and gets a page answering: who represents me, where and when
can I show up, what can I still do about it, who do I call. Every fact links to its official source.

Two views, decided 2026-09-22 — different questions, not variants of each other:

| Route | Content |
|---|---|
| `/district/{1-51}` | Council view: member, their committees, next five Council meetings with addresses, how to testify including the written-testimony window |
| `/board/{code}` | Community board view: monthly cadence, zoning review role, office to call, covering council districts, and the route almost nobody knows — **board committees seat non-board members of the public** |

The board view is not a district page with different data: no City dataset publishes a board meeting
calendar or venue, so the page says so and links the board's own site, and its participation route is
committee membership and Borough President appointment rather than testimony. The precise wording
matters — see the 2026-09-24 entry in `docs/OBSERVATIONS.md`, where the earlier blanket claim ("no
City dataset publishes community board agendas or meeting dates") turned out to be false.

Three ways in, all landing on one of those two pages:

1. **Two dropdowns**, one per view, each with a plain-link list below for the no-JavaScript, keyboard
   and screen-reader path.
2. **An address box** (built 2026-09-22). Submit-only, so no autocomplete keystroke leakage. Address,
   ZIP, neighbourhood name or district number all work; everything except a street address resolves
   **entirely locally** from a committed index and never reaches the geocoder. ZIPs straddle districts,
   so a ZIP offers the choice instead of guessing. `private=true` on every geocoder call, gated.
3. Out-of-city input is refused by name ("that looks like Newark") from what the geocoder says it
   *parsed*, before anything renders.

`/district/35` and `/board/302` are the canonical shareable URLs; the typed address never appears in
either.

## 2. What is on the page

Six blocks in this reading order. Everything is a fact plus a link; nothing is computed except the two
deadlines in block 4.

| # | Block | Content |
|---|---|---|
| 1 | Where you are | District number, neighbourhood names, overlapping community board(s), and one sentence distinguishing the two — residents conflate them and the board is often the right venue |
| 2 | Your Council Member | Name, party, seat status, email, district office address and phone, legislative office at 250 Broadway, link to their council.nyc.gov page. A vacant seat is a designed state, not an error |
| 3 | Their committees | With chair and co-chair roles marked |
| 4 | The next 5 meetings | Citywide, chronological, no ranking. Each shows date, time (or `Deferred`), in person / hybrid / remote, the venue's real street address, the committee, and the topic where the agenda is published; each links to its Legistar meeting-detail page and agenda PDF. Two computed values: the **written-testimony safe-until timestamp** (`start + 72h`, a provable lower bound) and the **accommodation request-by date** (3 business days before, against a committed holiday table) |
| 5 | How to be heard | In-person testimony needs no pre-registration; remote requires the Register to Testify form; written testimony is accepted up to 72 hours after adjournment, DOC/DOCX/PDF, 10 MB. Entry: NYPD security and metal detectors, photo ID at 250 Broadway, no signs larger than 8.5" × 11". The refusal strings — registration cut-off and per-speaker time limit are published nowhere official, so we give `hearings@council.nyc.gov` / 212-482-4219 instead of a guess. Leads with the fact that **only Council Members introduce legislation**; there is no public petition route |
| 6 | Your community board(s) | Matched by **geometry**, not the boards dataset's own `council_district` column, which omits seven council districts entirely. Most districts overlap two or three boards, listed by how much of the district each covers. Office address, phone, email, website, cadence quoted verbatim. Chairs and district managers are never named; we publish the office, whose job is to hear from you |

Plus a persistent footer: when each source was last fetched, and the covered forward window stated
literally.

## 3. Explicitly not in Phase 1

Cut for now, each recoverable later: the map (no MapLibre, tiles, choropleth or rendered geometry);
all analysis (no shortlist ranking, salience, vote parsing, dissent figures, `bloc_concentration`,
agenda-item classification or PDF parsing); transcripts and participation data (all of J4's measured
half); per-committee and per-hearing pages; `.ics` files; search by subject and the citywide browse
view.

**Geometry is the exception.** The NYC geocoder returns coordinates but *not* a council district, so
the address path needs district polygons for an in-browser point-in-polygon test. Phase 1 ships
simplified geometry **for resolution only, never for display** — no tile or rendering library. The
tolerance was chosen by measuring each point's resolved district against full precision over a
37,000-point citywide lattice: 11 m → 60 KB gzipped and 0.059% wrong; **2.2 m (shipped) → 132 KB and
0.011%**; unsimplified → 372 KB and 0.005%.

The floor is not zero: even unsimplified geometry disagrees on 2 points sitting exactly on a shared
edge. 2.2 m is near the floor at a third of the 300 KB budget, and
`tests/unit/test_geo.py::TestSimplifiedGeometryAgrees` fails if the tolerance is loosened without
re-measuring. Because boundary cases remain, the address result always offers the City's own lookup —
our geometry copies DCP's published lines, it is not the legal definition.

## 4. Security — the top priority

A threat model, not a checklist: this product has no accounts, no sessions and no database, so the
usual checklist does not apply and the real risks are elsewhere.

### 4.1 Injection through scraped upstream content — the primary risk

We render text we did not author — committee names, meeting topics, bill titles, venue strings, member
names, board cadence strings — all from third-party HTML we do not control. A hostile or merely
malformed value reaching a page unescaped is the most likely way this site ever hurts someone.

- **All upstream text is untrusted input.** Tags stripped at ingest, entities decoded once, result
  stored as plain text. No upstream HTML is ever stored as HTML.
- **The frontend never uses `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write` or
  `eval`.** Text via `textContent`, attributes via `setAttribute`. A CI grep fails the build on those
  identifiers.
- **Upstream URLs are allowlisted by host and scheme** before becoming an `href`: `nyc.legistar.com`,
  `legistar.council.nyc.gov`, `council.nyc.gov`, `data.cityofnewyork.us`, `nyc.gov`, https only.
  `javascript:` and `data:` can never survive; anything else renders as inert text.
- **A committed fixture carries a hostile case** — a committee name containing `<script>`, a quote and
  an entity — and a test asserts it renders inert.

### 4.2 Headers and transport

`Content-Security-Policy: default-src 'none'`, adding back only `connect-src` limited to
`geosearch.planninglabs.nyc`, `script-src 'self'`, `style-src 'self'`, `img-src 'self'`. **No inline
scripts, no inline styles, no `unsafe-inline`.** Plus `frame-ancestors 'none'`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, HSTS with a long max-age, HTTPS
only, and `rel="noopener noreferrer"` on every outbound link.

Committed as a `_headers` file for the eventual Cloudflare Pages deploy, because these must be
**response** headers and a meta tag cannot deliver most of them. **Locally, `scripts/serve.py` reads
`_headers` and applies it** (stdlib only, matching the sibling project): under `python -m http.server`
there is no CSP, so every violation would first surface at deploy — exactly when it gets waived. A
test asserts the served response carries the headers, against the local server now and a real host
later.

### 4.3 Zero third parties

No analytics, tag manager, hosted fonts, CDN scripts or embeds. Legistar's own pages embed AddThis; we
link to them and never iframe them. Every asset is first-party, which is what makes §4.2 enforceable
rather than decorative.

### 4.4 The user's address

Sent only to the geocoder, with `private=true`, on submit only. Never written to a URL, query string,
fragment, cookie, `localStorage`, `sessionStorage` or any log — the redirect target is `/district/35`.
A CI grep fails the build if a geocoder call site omits `private=true`.

### 4.5 Supply chain and build integrity

- Dependencies minimal and pinned via lockfile. **Phase 1 needs no PDF parser and no map library** — a
  security benefit of the reduced scope, not just a time saving.
- GitHub Actions pinned to commit SHAs, not tags; `permissions:` least privilege (`contents: read` by
  default).
- The build requires **no secrets**. Deploy credentials will live only in the deploy job, never in
  build steps that process untrusted upstream content.
- `mainline` is protected: no force-push, no direct push.

### 4.6 Not being the attacker

Polite crawl rates — `council.nyc.gov` at 1 request / 10 s, honouring `Crawl-delay`. Hammering a city
website is a security failure in the direction we control most easily.

## 5. The SLA in Phase 1

The outline's §6A budgets are written around a map click that does not exist yet. They still apply,
reassigned:

| Path | Budget | Note |
|---|---|---|
| Dropdown selection → page rendered | p95 ≤ 200 ms | SLA-1 unchanged, and easier than the map version: pages are pre-rendered, so a selection is a navigation to a static document |
| Address submit → page rendered | p95 ≤ 1 s, our share ≤ 270 ms | Unchanged; the geocoder leg is measured, not promised |
| Autocomplete (SLA-3) | Does not apply | Phase 1 is submit-only by the §4.4 privacy decision |

Consequence for §6A.3: the inline 51-district index and the prefetch-on-hover machinery are **not
needed in Phase 1** — pre-rendering one page per district hits the same latency more simply. Those
constraints return when the map does.

## 6. Exit criteria

| # | Status | Criterion |
|---|---|---|
| 1 | ✅ | `scripts/serve.py` serves the built site locally, and any of the 51 districts — by dropdown, address, ZIP, neighbourhood or district number — renders all six blocks correctly. Plus 59 community board pages, added after this list was written |
| 2 | ✅ | An address outside NYC is refused by name ("that looks like Newark") rather than silently mis-assigned, checked against what the geocoder says it *parsed* before anything renders |
| 3 | ✅ | Response headers from the local server match §4.2, asserted by `scripts/verify.py` against live responses. `_headers` is committed for the later deploy and the assertion can be pointed at a real host unchanged |
| 4 | ✅ | The hostile-content fixture renders inert, asserted end to end, plus ~8,500 generated fuzz cases over the parsers and a committed corpus of 104 input/expected pairs |
| 5 | ⚠️ | **Mostly met; one half genuinely open.** Built 2026-09-23. Five legs below |
| 6 | ✅ | The refresh runs as one local command (`make fetch`), fails closed on a bad fetch, and the staleness notice provably appears when `manifest.json` is hand-aged. Running it *on a schedule* is deferred with hosting. Crawl rates come from each host's own `robots.txt`, and an `upstream` test fails if the City raises its delay above ours |
| 7 | ✅ | Every fact carries its source link, and the footer carries each source's fetch date with the covered forward window stated literally |

Criterion 5, leg by leg:

| Leg | Status | Detail |
|---|---|---|
| axe | ✅ | Clean on **all 114** pre-rendered pages at WCAG 2.2 AA, gated in CI, with a committed negative control (`tests/fixtures/a11y_broken/`) proving the gate can still fail and a floor on rules-exercised per page proving it ran |
| Keyboard, automated | ✅ | 122 checks over 9 page types with real `Tab` keypresses in a real browser: skip link first and visible, focus into `<main>`, DOM order, reachability, ≥2px ring at every stop, `Shift+Tab` in reverse. Plus the accessibility tree (landmarks, accessible names, one h1, no skipped levels) and the no-JavaScript path verified with script execution disabled, not inferred from markup |
| **Screen reader** | ❌ | **Has not been run.** Reading the accessibility tree is not listening to a screen reader, and automating that distinction away is the one shortcut this product cannot take. `docs/accessibility-pass.md` §3.2 is the procedure, §4 the record, and the record says NOT RUN. **This is the one thing left in Phase 1.** |
| 60 KB page budget | ✅ | Gated in CI as arithmetic over built bytes: front page 13.9 KB gzipped, district pages 7.6 KB, boards 6.1 KB; all JavaScript 6.7 KB against a separate 12 KB ceiling; geometry 132 KB against its 300 KB after-first-paint budget |
| 3 s throttled-3G gate | ✅ | p95 over 20 cold runs per page on 3G Fast with a 4× CPU throttle: 906 ms, 741 ms, 723 ms against 3000 ms. Thresholds and profiles in the committed `perf-budget.json`. DevTools' Slow 3G preset yields 4.3–5.1 s: reported but not gated, with the reasoning in that file rather than as a quiet omission |

**Criterion 6, corrected 2026-09-23:** the staleness claim used to be true only over HTTP and false in a
browser — `connect-src` omitted `'self'`, so `/manifest.json` could not be fetched and the notice never
rendered for any reader. The tick now rests on
`tests/browser/test_console.py::TestTheStalenessNoticeReallyRenders`, which ages the manifest, loads a
real page in a real browser behind the real headers, and asserts the rendered text names the source,
its age in days, and the instruction not to rely on the meeting times.

## 7. Open, for the owner

1. ~~Domain name and indexing.~~ **Resolved 2026-09-21: neither.** Phase 1 is local only.
2. **Shortlist size confirmed at 5** for Phase 1 as "the next 5 meetings". When ranking arrives later,
   is 5 still right, or does a ranked list want more?
3. Project identity and the correction-contact address (brief §8.4) — deferred with publishing, since
   nothing is public and there is no one to receive a correction yet.
4. Should `council_access_nyc` be a **public or private** GitHub repository? It now has a remote
   (`github.com/nchafy/council_access_nyc`), so this is live rather than hypothetical.
