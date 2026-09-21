# Phase 1 — scope

**What this is for:** the exact, small thing to build first. **When to read it:** before writing
any code, and instead of the outline's §8 milestones, which this supersedes for the near term.

Decided by the owner 2026-09-21: barebones. One input — a dropdown or an address — produces one
page of information and links. No map. No analysis. Security is the top priority. P8, P9 and P10
(never mislead / accessible and private / still true in two years) are all in.

Estimated **10–13 days** for one person. It is a launchable product on its own.

---

## 1. What Phase 1 is

A user arrives, identifies where they are **once**, and gets a single page answering: who
represents me, where and when can I show up, what can I still do about it, and who do I call.
Every fact links to the official source it came from.

Two ways in, both producing the identical page:

1. **A dropdown of all 51 council districts**, labelled with neighbourhood names so they are
   recognisable — `District 35 — Fort Greene, Clinton Hill, Prospect Heights`. Requires no
   network call and no geometry.
2. **An address box.** Geocode the address, resolve which district the point falls in, redirect
   to the same page.

`/district/35` is the canonical, shareable URL. The typed address never appears in it.

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
6. **Your community board.** Office address, website, the meeting cadence quoted verbatim, and
   the office email only when it matches the institutional pattern.

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

**Note on geometry:** the address path still needs the district polygons, because the NYC
geocoder returns coordinates but *not* a council district, so the lookup is a point-in-polygon
test. Phase 1 therefore ships simplified geometry **for resolution only, never for display** —
a meaningful distinction, since the accuracy bar is correctness of assignment rather than
appearance, and no tile or rendering library is involved.

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
- Cloudflare Pages via `_headers`, because these must be response headers; a meta tag cannot
  deliver most of them. **A test asserts the deployed headers**, since a CSP that is not served
  is not a CSP.

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

## 5. Exit criteria

1. A live URL where picking any of the 51 districts from the dropdown, or typing any NYC address,
   renders all six blocks correctly.
2. An address outside NYC is refused by name ("that looks like Newark") rather than silently
   mis-assigned.
3. Deployed response headers match §4.2, asserted by a test.
4. The hostile-content fixture renders inert, asserted by a test.
5. axe clean on the two page types; full keyboard navigation; works with JavaScript disabled for
   everything except the address box.
6. Refresh runs on a schedule, fails closed, and the staleness notice provably appears when the
   manifest is hand-aged.
7. Every fact on the page carries its source link and fetch date.

## 6. Open, for the owner

1. **Domain name**, and whether the site is publicly indexed at this phase.
2. **Shortlist size confirmed at 5** for Phase 1 as "the next 5 meetings". When ranking arrives
   in a later phase, is 5 still right, or does a ranked list want more?
3. Project identity and the correction-contact address (brief §8.4).
