# Show Up NYC — project outline

**Repository:** `~/personal/council_access_nyc` → `git@github.com:nchafy/council_access_nyc.git`, default branch `mainline`
**This file:** `council-access-project-outline.md` (repo root). This document is the project's source of truth. `CLAUDE.md` carries the working conventions and a "Decisions already made — don't relitigate" section that mirrors §2 of this file.
**Status:** plan, not yet built. Written 2026-09-21 from a six-lens exploration, three competing designs, three judge panels and a completeness critique. All HTTP facts cited below were verified live on 2026-09-21 unless explicitly marked unverified.

---

## 1. What this is

Show Up NYC is a static website that tells a New Yorker the specific, dated things they can still do about their city government this week: which New York City Council hearings are happening, where the room is and how to get into it, that they can walk in without registering, and how many hours are left to file written testimony on a hearing that already happened. It is built entirely from build-time fetches of `nyc.legistar.com` and `council.nyc.gov` plus a handful of NYC Open Data datasets, and it ships as pre-rendered HTML and static JSON on a CDN with no server, no database and no accounts. It refuses to compute the things the City does not publish — there is no measure of public support, opposition, sentiment, or hearing attendance anywhere in it, because no public source records any of those, and that refusal is enforced by tests rather than by good intentions. It is for a resident with a problem and a short attention budget: a tenant, a parent, a first-time attendee, an organizer covering three districts, a small-business owner — someone who needs a room number and a deadline, not a dashboard. It is also for the journalist or community-board member who needs the underlying primary document, which is why every number links to the exact PDF or Legistar page it came from.

---

## 2. Decisions already made — don't relitigate

Each line is settled. If you want to reopen one, write an ADR that cites new evidence, not a preference.

1. **Static site, build-time ETL, no origin server.** Forced, not chosen: `nyc.legistar.com/Calendar.aspx` and `council.nyc.gov/district-N/` both return HTTP 200 with **no** `Access-Control-Allow-Origin` header, so a browser cannot read them.
2. **No composite "importance" / "salience" / "relevance" score, ever.** Its heaviest proposed input varies 54.2x across statutorily equal-population districts, two proposed inputs correlate at ρ 0.892, the "friction" sub-score's own parts correlate at −0.704, and the rescale-to-100 step converts a measured #1-vs-#2 gap of exactly 0.000 into a 100-vs-99 headline.
3. **No sentiment, support, opposition, controversy or attendance metric.** Verified grounding: *"NOTHING the City publishes records WHO attended or testified at a hearing, WHAT they said, or WHICH SIDE they took."* Fabricating it is this product's worst available failure mode.
4. **No cross-district ranking, percentile, league table, per-capita normalisation, or indicator-coloured choropleth.** "My district is darker" becomes the mental model regardless of the legend.
5. **Constituent-services casework (`b9km-gdpy`) is cut from v1 entirely.** It effectively ends in 2023 (477 rows in 2024, 4 in 2025), 21.3% of rows are not district-attributable, and its district codes predate the current boundaries. The construct is falsified by its own natural experiment: housing casework fell 58% during the eviction moratorium — peak need.
6. **Discretionary funding (`4d7f-74pe`) is cut permanently, not deferred.** It ends at FY2021; `council_district` is the recipient's mailing-address district, not the awarding member's; and a verified join to PLUTO (`64uk-42ks`) found ~19% of sampled addresses in residential building classes including `bldgclass A1, unitsres=1` single-family homes owned by named natural persons, geocodable to six decimals. A label cannot fix a doorstep.
7. **Forward-looking dates come only from the live Legistar layer.** `m48u-yjt8` max `meeting_date` = 2024-12-19 and can never answer "when is the next meeting". The build fails if any rendered future date traces to a source whose max record date is in the past.
8. **One plain unauthenticated GET of `Calendar.aspx`; never `__VIEWSTATE` pagination.** Page 1 is date-descending and already spans 2026-09-02 → 2026-12-17 (59 future rows). Page 2 requires POSTing a ~374 KB `__VIEWSTATE` for the least valuable data.
9. **v1 is fully functional with zero authenticated access.** `webapi.legistar.com/v1/nyc/...` returns **HTTP 403 "Token is required"**. Votes, agendas, topics and transcripts are all reachable without a key.
10. **Body invariants, not status codes.** Three verified endpoints return HTTP 200 carrying an error: `Feed.ashx?M=Calendar&...` → 721-byte `<title>Invalid feed</title>`; `LegislationDetail.aspx?ID=7861919&GUID=X` → 19-byte body `Invalid parameters!`; `View.ashx?M=AO&ID=181205` → 302 to `/Error`. The RSS route is dead and removed from consideration.
11. **`as_of` is computed from `max(date)` inside the rows, never from Socrata metadata.** `b9km-gdpy` reports `rowsUpdatedAt` 2026-09-10 with data ending 2025-01-09; `4d7f-74pe` reports modified 2025-12-30 with data ending FY2021.
12. **Staleness is computed in the browser, not baked at build.** `manifest.json` carries per-source `fetched_at` + `max_age`; the client compares to `Date.now()`. No `degraded: bool` or `age_hours` scalar is ever emitted. This is what keeps an abandoned site honest.
13. **Fail closed.** A refresh run below a row floor or violating an invariant fails the job and leaves the previous deploy serving, labelled with its real age.
14. **Python 3.12 + uv + ruff + pytest for ETL; vanilla ES modules for the frontend.** Mirrors `~/personal/timemap_nyc/pyproject.toml` (target py312, 20-rule ruff select, `--cov-fail-under=90`, `filterwarnings = ["error"]`). The only shared ETL/browser logic is ~25 lines of ray-casting, so Node's one-language argument is empty. One pinned npm devDependency: `mapshaper`.
15. **MapLibre GL JS + OpenFreeMap, self-hosted vendor bundle. No Google Maps, no Mapbox, no analytics, no tag manager, no third-party fonts.** The model site `spatialequity.nyc` ships gtag and Mapbox in its bundle; we borrow its metric-registry schema and its refusal to composite, and reject its telemetry stack.
16. **No LLM or NLP step inside the build.** Organisation and member aliasing is reviewed YAML, so every artifact is byte-reproducible in CI at zero model cost.
17. **The typed address never leaves the browser except to the geocoder, never enters a URL, storage, cookie or log.** Shareable URLs carry `/district/35` only.
18. **Written-testimony deadlines are published as a provable lower bound, never derived from an adjournment time.** No official source publishes adjournment timestamps.
19. **Organisation-level aggregation only; no individual private resident is ever named in any artifact.** Recorded as an ADR, enforced by a test.
20. **The grounding line "Visible-text structure is IDENTICAL across them" (the 51 district pages) is WRONG.** Verified variance: `Office Hours` absent on D35 and D51; three phone-label conventions (`Phone: 718-260-9191`, `(718) 984-5151 phone`, `phone 1`/`phone 2`); two email conventions (`District35@council.nyc.gov`, `Morano@council.nyc.gov`); `250 Broadway, 1551` with no "Suite" on D51; committees absent for districts 3, 5, 9, 14, 25, 26. Every field is independently optional.
21. **`council.nyc.gov`'s `wp-json` is not a substitute for scraping the rendered page.** Its `content.rendered` gives District 1's office as "101 Lafayette St, 9th Floor" while the live page says "65 East Broadway".
22. **Cloudflare Pages, not GitHub Pages.** CSP with an explicit `connect-src` allowlist is what makes "zero third parties" browser-enforced against a future commit; GitHub Pages has no mechanism to set response headers.
23. **The district is a filter, not the organising key.** Committee hearings are citywide and belong to no district. `/hearing/{id}` and `/committee/{slug}` are first-class destinations; `/district/N` exists, is pre-rendered and linkable, but the primary journey is the citywide "this week" list.

---

## 3. Requirements

`[USER]` = explicit in the user's ask. `[ADD]` = added during exploration; the owner can veto any `[ADD]` line without breaking the four user questions unless noted. The user explicitly asked for **four things** (R1, R6, R11, R15) and **two interactions** (R19, R20); everything else is flagged.

### The four questions and two interactions

| # | Req | Level | Origin |
|---|---|---|---|
| R1 | Show where Council meetings occur, the street address, when, and whether a schedule exists — distinguishing Stated Meetings (fixed months ahead), committee hearings (notice-driven) and community-board meetings (recurring monthly). | MUST | `[USER]` |
| R2 | Source every forward-looking date from one unauthenticated GET of `https://nyc.legistar.com/Calendar.aspx` per refresh, with `https://legistar.council.nyc.gov/Calendar.aspx` as failover host. No `__VIEWSTATE` paging. | MUST | `[ADD]` |
| R3 | Render `Deferred`, `HYBRID HEARING`, `REMOTE HEARING (VIRTUAL ROOM 1..4)` and off-site venues as first-class states with their own copy. `Deferred` (≈15% of page-1 rows) must never occupy the position where a time belongs. | MUST | `[ADD]` |
| R4 | Merge joint hearings on (date, time, room), combine committee names, and strip `Jointly with the Committee on …` out of the location cell before venue normalisation. | MUST | `[ADD]` |
| R5 | State the covered forward window literally (e.g. "we see hearings through 17 Dec 2026") rather than implying completeness. | MUST | `[ADD]` |
| R6 | Show what the topics of discussion are. | MUST | `[USER]` |
| R7 | Derive topics from `MeetingDetail.aspx` agenda items (File #, Name, Type, Summary, Action, Result), never from the calendar's placeholder `Multiple meeting items, please see Meeting Details for more information`. | MUST | `[ADD]` |
| R8 | Ship an explicit "agenda not yet published" state with a link to the published agenda PDF, because near-term meetings carry 1–5 items and a Stated Meeting at T+87 carries no items grid at all. | MUST | `[ADD]` |
| R9 | Answer the "support / disagreement / discourse" half **only** as named Affirmative / Negative / Abstain / Non-voting counts parsed from Stated Meeting minutes PDFs, labelled "Recorded votes of Council Members — not community opinion". | MUST | `[USER]` (reframed; see §4.2 and §11.C) |
| R10 | Publish, next to any dissent figure, the share of all recorded dissent in the window cast by the five most frequent dissenters, so the reader can see whether dissent tracks the topic or the member. | MUST | `[ADD]` |
| R11 | Explain the avenues to get an issue heard and where to register. | MUST | `[USER]` |
| R12 | Lead that answer with the truth: **only Council Members introduce legislation**, and there is no public petition route onto the agenda. Then the real levers in order of immediacy. | MUST | `[ADD]` |
| R13 | Compute and display, per hearing: the in-person fact ("**IN-PERSON hearings require NO pre-registration**"), the remote-registration requirement, the written-testimony window as a provable lower bound with hours remaining, and the ASL/CART and interpretation request-by dates in business days. | MUST | `[ADD]` |
| R14 | Render explicit "not published" refusals for the registration cut-off time and the per-speaker time limit, with `hearings@council.nyc.gov` / `212-482-4219`. Never display an inferred value. | MUST | `[ADD]` |
| R15 | Answer which community groups are consistently present, and help users get in touch. | MUST | `[USER]` (partial; see §4.4) |
| R16 | State plainly, in place, that no City source records who attended or testified, and route to the resident's community board, district office and the Register to Testify form. | MUST | `[ADD]` |
| R17 | If and only if the M7 spike clears its threshold, publish organisation-level participation as "spoke on the record at N of the M hearings we have transcripts for", with the pending-transcript denominator in the same element. | SHOULD | `[ADD]` |
| R18 | Never invent contact details for an organisation. No EIN join, no address, no coordinates, no map pin for any organisation, ever. | MUST | `[ADD]` |
| R19 | A search bar where a user enters an address and gets that location's information. | MUST | `[USER]` |
| R20 | An interactive map where clicking a council district shows that district's information, at full parity with the address path and requiring no network call. | MUST | `[USER]` |

### Data integrity and honesty

| # | Req | Level | Origin |
|---|---|---|---|
| R21 | Every external fetch asserts a body invariant in addition to HTTP status: PDFs begin `%PDF`; iCal begins `BEGIN:VCALENDAR`; `Calendar.aspx` yields ≥40 parsed rows of which ≥1 is future-dated; a Legistar page body is not `Invalid parameters!`. | MUST | `[ADD]` |
| R22 | Every displayed number and date carries `data-source` and `data-as-of` in the DOM **and** `source_id` / `as_of` / `n` / `denominator` / `method_id` / `limitations` as fields in the emitted JSON. Build fails on a bare scalar in a display position. | MUST | `[ADD]` |
| R23 | Coverage renders **above** the data it qualifies, not below: hearings in window, hearings with a transcript, hearings with Final minutes, pending items with their ages. | MUST | `[ADD]` |
| R24 | A refresh run below a per-source row floor, or violating an invariant, fails the job and leaves the previous deploy serving. | MUST | `[ADD]` |
| R25 | Any committee name or venue string absent from the committed crosswalks fails the build and demands a human mapping decision. Committees are keyed by stable internal id with an alias table (`Transportation` → `Transportation and Infrastructure`; `Women's Issues` → `Women and Gender Equity`). | MUST | `[ADD]` |
| R26 | Unmapped and unresolved records go to a counted quarantine file whose count is surfaced in the UI as a coverage figure. Never silently dropped. | MUST | `[ADD]` |
| R27 | Current-session committee rosters and chairs come from dated agenda/minutes PDF headers; `aabe-yfm9` has **zero rows** starting after 2026-01-01 and is used only for pre-2026 history. | MUST | `[ADD]` |
| R28 | Member currency predicate is `term_start <= today AND term_end >= today`, with District 3 (vacant; Bottcher's `term_end` 2026-02-03) as a pinned regression fixture. `uvw5-9znb` is never authoritative for member→district (52 of 558 rows have NULL district, including Justin L. Brannan through 2025). | MUST | `[ADD]` |
| R29 | The vacant seat is a designed result, not an error: names the vacancy and its date, keeps every member-independent action live, explains the special-election path. | MUST | `[ADD]` |
| R30 | Community-board office email displays only when it matches `^(mn\|bx\|bk\|qn\|si)\d{2}@cb\.nyc\.gov$`. Otherwise show no email and link the live CB page. `cb_chair` and `cb_district_manager` are never rendered. `dy27-rrad` (2019) and `3gkd-ddzn` (2017) are blocklisted by dataset id in code. | MUST | `[ADD]` |
| R31 | The council-district → community-district mapping is built from geometry (`5crt-au7u` against `872g-cjhh`) at build time, not from `ruf7-3wgc.council_district`, which has only 44 distinct values for 51 districts. CI floor: all 51 districts resolve to ≥1 board. | MUST | `[ADD]` |
| R32 | Disclose the coverage gap between `m48u-yjt8`'s 2024 end and the Legistar calendar's 2026 window rather than implying a continuous history. | SHOULD | `[ADD]` |

### Privacy, access, durability

| # | Req | Level | Origin |
|---|---|---|---|
| R33 | Every geocoder request includes `private=true`, enforced by a CI grep over call sites. Submit-only; no autocomplete. CORS-simple GET only (`OPTIONS` returns 403, so any preflight-triggering request works in curl and fails in production). | MUST | `[ADD]` |
| R34 | Out-of-area is detected on `geocoding.query.parsed_text.region` / `.locality` before anything renders — never on zero features and never on `match_type`. `1 Main St Newark NJ` returns `1 MAIN STREET, Brooklyn` at confidence 0.8, and `match_type` is `fallback` even for a perfect in-NYC hit. | MUST | `[ADD]` |
| R35 | Candidates dedupe by rounded coordinate (or BBL from the addendum) before display, disambiguate borough-first, and render title-cased. `100 B'WAY, Brooklyn` and `100 BROADWAY, Brooklyn` are the same point; `100 Broadway` is genuinely ambiguous across three boroughs. | MUST | `[ADD]` |
| R36 | District numbers, district names, neighbourhood names and ZIPs resolve against a local index and are never forwarded to GeoSearch, which reads `11217` as a house number and `Bushwick` as a swimming pool. | MUST | `[ADD]` |
| R37 | Provide at least one location-free entry path: browse all hearings in the next 14 days, and find hearings by subject. Serves shelter residents, people with confidential addresses, and anyone whose issue is not where they sleep. | MUST | `[ADD]` |
| R38 | Ship CSP with an explicit `connect-src` allowlist (`self`, `geosearch.planninglabs.nyc`), `Referrer-Policy: no-referrer`, `<meta name="referrer" content="no-referrer">`, and `rel="noopener noreferrer"` on every outbound link. Legistar's MeetingDetail embeds AddThis; never iframe or embed it. | MUST | `[ADD]` |
| R39 | WCAG 2.2 AA. All procedural content works with JavaScript disabled (pages are pre-rendered). axe over every pre-rendered page in CI, plus a documented keyboard-only and screen-reader pass per release. Every map answer reachable from a keyboard-navigable list of all 51 districts. | MUST | `[ADD]` |
| R40 | Performance budget enforced in CI: initial HTML + CSS + district JSON under 60 KB gzipped; geometry and MapLibre load after first paint; **cold** first answer under 3 s on a throttled 3G / mid-tier Android profile. | MUST | `[ADD]` |
| R40a | **Interaction SLA — the headline commitment.** Once the page is interactive, selecting a district resolves and paints its answer in **under 1 s at p95**. Measured per §6A, decomposed into a local budget and an external-geocoder budget, and gated in CI. Distinct from R40, which governs cold load. | MUST | `[USER]` |
| R40b | A district selection by map click, keyboard list, or district number **makes no network request on the critical path**. The compact 51-district index ships inline with the document; per-district detail is prefetched on hover / focus, so the click is a local lookup. | MUST | `[ADD]` |
| R40c | An address lookup shows a resolving state at 150 ms, a "still looking up" state at 1.2 s that names the geocoder as the slow dependency, and at 5 s abandons the lookup and offers the map and list paths. A spinner with no escape hatch is a defect. | MUST | `[ADD]` |
| R40d | Inputs resolvable without the network — a district number, a ZIP, or a neighbourhood name in the committed index — bypass the geocoder entirely and are held to the local budget, not the address budget. | MUST | `[ADD]` |
| R40e | The SLA is verified **synthetically in CI only**. Decision §2.15 forbids analytics, so there is no real-user monitoring and no production percentile. The published SLA is a CI-measured claim about a reference device, not an observed field measurement, and `/methodology/` says so in those words. | MUST | `[ADD]` |
| R41 | Publish an accessibility statement with a working feedback address, and gate procedural copy on a pinned readability threshold in CI. | SHOULD | `[ADD]` |
| R42 | All UI strings externalised from code in v1. **English only at launch** — the list of designated citywide languages could not be verified (the canonical nyc.gov page is 404 today) and no translator, budget or re-translation gate exists. Machine translation is never the delivery mechanism for a deadline. | MUST | `[ADD]` |
| R43 | Generate our own `.ics` (`DTSTART` with `TZID=America/New_York`, real `DTEND` where known, venue street address in `LOCATION`, entry rules and accommodation deadline in `DESCRIPTION`, stable `UID`). Legistar's per-row `View.ashx?M=IC` export is surfaced only as a secondary "Legistar's own calendar file" — verified 284 bytes, no `UID`, **no `TZID`** (floating local time), empty `DESCRIPTION`, synthetic start+1h `DTEND`. | MUST | `[ADD]` |
| R44 | Three independent refresh workflows with independently reported freshness, plus a separately-named scheduled contract job that fails distinguishably from unit-test failure. Every successful run commits `manifest.json` even when derived data is unchanged, to defeat GitHub's disabling of crons in quiet repositories. | MUST | `[ADD]` |
| R45 | Crawl politely: `council.nyc.gov` at 1 request / 10 s (`Crawl-delay: 10`; 51 pages ≈ 8.5 min), `data.cityofnewyork.us` at 1 request / s (`Crawl-delay: 1`), Legistar at low volume. One documented descriptive User-Agent with a contact URL. Raw bytes cached and never refetched. | MUST | `[ADD]` |
| R46 | Dead-man's switch: a scheduled job that replaces the site with a single page pointing at Legistar and `council.nyc.gov` if no refresh has succeeded in N days. | MUST | `[ADD]` |
| R47 | Ship a `LICENSE` and a machine-readable terms note in `site/data/`, and decide `noindex` for `/data/`. Derived JSON is public and re-fetchable; its guards must be fields, not page chrome. | SHOULD | `[ADD]` |
| R48 | Publish a correction channel, a dated public correction log, and an organisation-removal request path honoured within a stated period with no justification required. | SHOULD | `[ADD]` |
| R49 | Decode `Video.aspx?URL=<base64>` to deep-link the Viebit recording, and use the venue code and to-the-second timestamp in the filename (`NYCC-250-8-1_260909-102026.mp4` = 250 Broadway 8th Floor Room 1, 2026-09-09 10:20:26) to cross-check blank and `Deferred` calendar times. | SHOULD | `[ADD]` |
| R50 | Phase-aware Participatory Budgeting card. **NOT-V1** — requires probing 51 hand-authored non-uniform member microsites, and `council.nyc.gov/pb/` publishes no online idea form, no voter eligibility age, and no list of participating districts. | NOT-V1 | `[ADD]` |
| R51 | City Clerk eLobbyist layer (`fmf3-knd8`). **NOT-V1** — 77% of sampled 2024+ filings name no council district and 5.5% shotgun all 51, so most district pages would say "nobody paid to contact your member". | NOT-V1 | `[ADD]` |
| R52 | 311-vs-office-vs-board channel router. **COULD**, post-launch, guidance-only with its basis shown, defaulting to "311 first, and tell your council office". | COULD | `[ADD]` |

---

## 4. How each of the user's four questions gets answered

### 4.1 "Where do council meetings occur? Address? When? Is there a schedule?" — **fully answered**

**Data source.** One unauthenticated `GET https://nyc.legistar.com/Calendar.aspx` (≈890 KB, ASP.NET Telerik grid) three times daily at 06:10 / 12:10 / 18:10 ET, failover host `https://legistar.council.nyc.gov/Calendar.aspx` (byte-identical response verified). Then `GET https://nyc.legistar.com/MeetingDetail.aspx?ID=<event_id>&GUID=<guid>&Options=info|` for every meeting in the next 14 days, which carries the richer location string (`Council Chambers - City Hall Jointly with the Committee on Education.`) that the calendar cell does not.

**Computation.** Parse rows into `{committees[], date, time_raw, location_raw, topic_raw, meeting_detail_url, agenda_pdf, minutes_pdf, ics_url, video_url}`. Then:
- `time_state ∈ {scheduled, deferred, time_not_published}` — `Deferred` appears literally in the time column on ~15% of page-1 rows.
- `attendance_mode ∈ {in_person, hybrid, remote}` from the `HYBRID HEARING` / `REMOTE HEARING (VIRTUAL ROOM n)` prefix.
- Joint-hearing merge on `(date, time, room)` with committee names combined; `Jointly with the Committee on …` stripped before venue matching.
- `venue_id` resolved through `crosswalks/venues.yaml`: ~30+ raw spellings (en-dash and double-space variants included) collapse to about five real venues, each carrying a real street address and the verified entry facts.
- Recess-vs-breakage discriminator: a fetch that passes body invariants and yields ≥40 rows but **zero** future-dated rows is a quiet period or recess; a fetch that fails an invariant or falls below the floor is breakage. These render different copy and trigger different operator behaviour.

**Honesty boundary.** No hearing is ever presented as confirmed. `Confirm on Legistar before you travel` sits **inside** every card, with the fetch timestamp and a deep link to that hearing's own `MeetingDetail.aspx` as the authority. We cover a forward window of roughly 3.5 months and say so literally. We never infer a next meeting from historical cadence, and never take a forward date from `m48u-yjt8`. Same-day changes between the 18:10 fetch and the next morning are structurally invisible to us; three-times-daily refresh with a 12-hour staleness gate narrows that window and nothing closes it.

**UI must disclose.** Fetch timestamp per card; the confirm-before-you-travel line inside the card; the covered window; `Deferred` as "postponed, no new date published"; remote/hybrid virtual-room state; the sentence that committee hearings are citywide and belong to no district.

### 4.2 "What are the topics of discussion? Can we quantify whether a topic is important or relevant — with support / disagreement / discourse?" — **topics fully answered; quantification answered only as a narrow, differently-labelled substitute. This is the partial answer.**

**Data source.** Agenda items from `MeetingDetail.aspx`'s "Meeting Items" grid (File #, Ver., Prime Sponsor, Agenda #, Name, Type, Summary, Action, Result) — real values look like `T2026-2017 | Oversight – Examining Screen Time and the Use of Digital Devices in New York City Public Schools | Oversight | Hearing Held by Committee`. Recorded votes from Stated Meeting minutes PDFs at `https://nyc.legistar.com/View.ashx?M=M&ID=<event_id>` (verified: `ID=1442554`, Stated Meeting 9/10/26, 207,020 bytes, 33 pages).

**Computation.** Per agenda item: a binary, individually explainable class — `oversight` when `Type == "Oversight"`, `legislative` when the file number matches `^(Int|Res|LU|T)\d`, else `procedural` — with `class_reason` rendered next to the badge. Counts of items by type per committee over a rolling 12 months. Never aggregated into a district-level figure.

Per matter in a Stated Meeting: parse the `Affirmative: Speaker Menin, Abreu, … and Zhuang  49 -`, `Negative:`, `Abstain:`, `Non-voting: Gutiérrez 1 -`, `Bereavement:`, `Parental:`, `Excused:` blocks with `pdfplumber` (never hand-rolled zlib stream extraction). `dissent_share = (negative + abstain) / (affirmative + negative + abstain)`, dissenting members named. **Hard invariant:** the count of parsed names must equal the printed trailing integer or the entire document is quarantined — a silently vanishing `Negative:` block would make everything look unanimous. Only ~24 Stated Meetings a year are crawled, not the ~13,700 committee minutes.

Alongside it, one standing honesty statistic: `bloc_concentration` = share of all recorded dissent in the window cast by the five most frequent dissenters. If it exceeds 0.60, the card's own copy flips at build time to withdraw the topic-level reading and present the figure as a member voting-record pattern. The single sampled Stated Meeting showed the same nine members (Ariola, Borelli, Carr, Hanks, Holden, Marmorato, Paladino, Vernikov, Zhuang) dissenting as a bloc, so firing is the expected outcome.

**Honesty boundary.** There is **no** importance score, salience index, relevance percentage, 0-100 anything, or cross-district comparison. The dissent figure is *recorded disagreement among Council Members on a final vote* — it is not community sentiment, and it is never aggregated into a per-topic contention statistic. The user's literal request — quantified community support and disagreement — **cannot be answered**, and the site says so in the same element as the numbers it does show. Casework is absent entirely, so the site makes no claim at all about what matters to a neighbourhood.

**UI must disclose.** "Recorded votes of Council Members — not community opinion." The standing statement that nothing the City publishes records who testified or which side they took. `bloc_concentration` next to every dissent figure. Per-item `class_reason`. "Agenda not yet published" where the items grid is absent, with the agenda PDF linked. Agenda-item counts carry their window and their `n`, with no ordering implied below a stated minimum denominator.

### 4.3 "What are the avenues to get your motions into the schedule? Where to register?" — **fully answered, and the answer contains a refusal**

**Data source.** Hand-authored, per-claim-sourced content in `crosswalks/procedures.yaml`, every fact carrying `source_url` and `verified_on`, ported as a specification from the prior spike's `procedures.mjs`. Sources: `council.nyc.gov/testify/`, `council.nyc.gov/legislation/`, `council.nyc.gov/visit-the-council/`, `council.nyc.gov/land-use/`. Plus `crosswalks/nyc_holidays.yaml` for business-day arithmetic.

**Computation.** Three values are computed rather than restated, per hearing:
1. `written_testimony.safe_until = start_local + 72h` — a **provable one-sided bound.** Written testimony is accepted up to 72 hours after the hearing is *adjourned*; adjournment is always at or after the start; therefore filing before `start + 72h` is certainly inside the window. When the start time is absent or reads `Deferred`, fall back to `00:00 local of the hearing date + 72h`, which keeps the bound conservative. `basis: start_plus_72h_lower_bound`. This always renders for any hearing in the window — it is never gated on a minutes document that posts 1–3 weeks late.
2. `asl_cart_request_by` = `interpretation_request_by` = `hearing_date` minus 3 business days, excluding weekends and the committed NYC holiday table, with a designed `too_late_for_accommodation` state that still shows `EEOOfficer@council.nyc.gov` / `212-788-6936` and `translationservice@council.nyc.gov` rather than hiding the row.
3. `in_person = {kind: no_registration}` — the constant, verified fact.

`/testify` is a GOV.UK-style one-question-per-page branch: "Can you be in the room?" → walk in, no registration, here is what to bring (photo ID at 250 Broadway; NYPD security and metal detectors; tell officers which hearing; Sergeant-at-Arms on each floor; no food, no beverage containers, no signs larger than 8.5" × 11"). → No → "Do you want to speak live?" → Register to Testify form. → No → written testimony, the safe-until timestamp, **DOC, DOCX, PDF only, max 10 MB** (the upload control's stricter rule, not the page prose's looser `.doc, .rtf, .txt and.pdf`; the contradiction is recorded in the methodology notes).

**Honesty boundary.** The page leads with what cannot be done: **only Council Members introduce legislation**; bills are crafted with the Legislation Division and introduced at Stated Meetings; **there is no public petition route onto the agenda**. The two facts residents most want — the registration cut-off time before a hearing and the per-speaker time limit — are **published nowhere official**, and render as explicit refusal strings with `hearings@council.nyc.gov` / `212-482-4219`. The site never proxies, pre-fills or submits testimony. The Subcommittee on Zoning and Franchises and the Subcommittee on Landmarks, Public Sitings and Dispositions use `council.nyc.gov/land-use/` instead of the general form.

**UI must disclose.** Before every outbound link to the Register to Testify form: the form requires Full Name, Email and Phone ("we use this to verify your identity") and submissions become part of the **permanent public record**. The `safe_until` card states that the real deadline is 72 hours after adjournment, which the Council does not publish, and that filing before the shown time is certainly inside the window. The after-you-testify sequence (committee hearing → possible amendment → committee majority → full Council majority → Mayor's 30 days to sign, veto or allow → 2/3 override) with the bill's current position in it. The public 2022 Bill Drafting Manual, so a resident can arrive with draft text.

### 4.4 "Which community groups are consistently present at these meetings, and can we help users get in touch with them?" — **answered worst of the four. Routing ships at launch; the measured half is conditional on a spike.**

**Data source, routing half (launch).** `ruf7-3wgc` NYC Community Boards (data 2025-12-26) for board number, office address, institutional email, website, recurring board and cabinet meeting cadence, precinct. `council.nyc.gov/district-N/` rendered HTML for the district office and legislative office. `council.nyc.gov/testify/` for the testimony route.

**Data source, measured half (conditional on M7).** Hearing transcript PDFs at `https://nyc.legistar.com/View.ashx?M=F&ID=<file_id>&GUID=<guid>`, reachable token-free. Two were fetched: `ID=15869017` (Transportation & Infrastructure 6/25/26, 449,297 bytes, 58 pages, **no APPEARANCES block**, ordinary single-spaced text) and `ID=15834804` (Health 9/2/26, 1,076,061 bytes, 225 pages, positional `A P P E A R A N C E S` index on pages 2–4, doubled inter-character spacing). Transcripts are **not** linked from `MeetingDetail`; discovery is `Calendar → MeetingDetail → per-item LegislationDetail.aspx → attachment link text matching /Hearing Transcript/`, and the same file is attached to every matter heard at that meeting (five of six checked matters from the 9/2/26 Health meeting pointed at one document), so dedupe by numeric file ID before download is mandatory.

**Computation, routing half.** Council district → community district(s) by build-time areal overlap of `872g-cjhh` against `5crt-au7u`, largest share first, with the resident's own board named when address-level resolution succeeds. Email shown only when it matches `^(mn|bx|bk|qn|si)\d{2}@cb\.nyc\.gov$` — of 59 boards only 31 do; eleven publish the district manager's own name-based address and five publish consumer mailboxes (`bklcb15@verizon.net`, `bxbrd09@optonline.net`, `cb11q@nyc.rr.com`, `brooklyncb8@gmail.com`, `brxcb2@optonline.net`). The cadence string is reproduced **verbatim** (`Second Tuesday, 7:45pm`) and, where it parses unambiguously, accompanied by a computed next occurrence labelled "we computed this from the published cadence — confirm with the board."

**Computation, measured half.** Weekly harvest of meetings aged 7–35 days (measured transcript lag is 1–3 weeks). Two independent extraction strategies, reconciled: (a) coordinate-aware `pdfplumber.extract_words` with x-position clustering over the APPEARANCES block when present — name and organisation are separated only by horizontal offset, so line-flattening makes `Ida Goldstein` (no org) indistinguishable from `Saundrea Coleman / Stanley Isaacs Houses`; (b) ALL-CAPS-label-plus-colon speaker detection after aggressive whitespace normalisation, plus first-utterance self-introduction matching. Affiliation asserted only when both fire and agree, or when only one exists and parses cleanly; disagreement emits `null` and a quarantine row. Speaker class ∈ `{council_member, city_official, organization_representative, individual_resident_no_stated_affiliation, unknown}`. Canonicalisation through hand-curated `crosswalks/org_aliases.yaml` only. Each appearance carries `basis: appearances_block | self_introduction` in the shipped artifact, so a strategy collapse is visible in the data.

**Honesty boundary.** The phrase "consistently present" is banned. The metric, if it ships, is "spoke on the record at N of the M hearings we have transcripts for", with the pending count adjacent. Roughly **half** of verified public witnesses state no organisation at all — `Heaven Berhane` ("I am a resident of 3333… on the west side of Harlem"), `Blake Walker` ("I live in Park Slope, Brooklyn") — so they are a counted cohort, never dropped and never given a guessed affiliation. No individual private resident is named in any artifact. Written-testimony-only filers, sign-ups who were not called, and hearings whose transcripts are not yet posted are structurally invisible, stated in place. **"Get in touch" is not answered by inventing contact details:** transcripts carry none, no EIN join is performed, and the funding dataset is cut. The user gets the source transcript PDF and the organisation's stated name — plus the board, office and testify routes, which are institutions with a duty to be contacted.

**UI must disclose.** Above the list: the coverage denominator and the pending-transcript count. Next to each organisation: appearance count, committees appeared before, and a link to each source transcript PDF. The unaffiliated-resident cohort count as a peer figure. The standing statement that no City source records attendance or testimony. A correction and removal channel. And on `/methodology`: that this is the question the product answers least well, because it cannot currently put a resident in touch with a human at a community group.

---

## 5. The measurement methodology

### 5.1 What is computed

| id | `method_id` | value | units | source | window |
|---|---|---|---|---|---|
| D1 | `deadline.written.v1` | `start_local + 72h`, hours remaining | timestamp | `Calendar.aspx` + `procedures.yaml` | live |
| D2 | `deadline.accommodation.v1` | `hearing_date − 3 business days` excl. weekends + `nyc_holidays.yaml` | date | same | live |
| D3 | `deadline.inperson.v1` | constant `no_registration` | — | `council.nyc.gov/testify/` | — |
| A1 | `agenda.v1` | count of agenda items by `Type` per committee, rolling 12 months | items | `MeetingDetail.aspx` | rolling 12 mo |
| A2 | `agenda.class.v1` | per-item `oversight` / `legislative` / `procedural` + `class_reason` | label | `MeetingDetail.aspx` | per item |
| V1 | `rollcall.v1` | named Affirmative / Negative / Abstain / Non-voting counts; `dissent_share` per matter | votes | `View.ashx?M=M` | rolling 12 mo |
| V2 | `rollcall.bloc.v1` | share of all dissent cast by the top-5 dissenters | share | derived from V1 | rolling 12 mo |
| C1 | `coverage.v1` | hearings in window / with transcript / with Final minutes; median publication lag; pending list with ages; quarantine counts | counts | derived | rolling 12 mo |
| P1 | `speakers.v1` *(conditional on M7)* | distinct organisations with per-org hearing counts; unaffiliated-resident cohort count | orgs, people | `View.ashx?M=F` | rolling 6 mo |
| G1 | `geometry.v1` | address → district by ray-casting against simplified polygons, with ≤150 m nearest-district snap | district id | `872g-cjhh` (DCP release **26b**) | quarterly |

Every one of these is emitted as a `Measured` record and cannot serialise without `value, units, n, denominator, as_of, window, source_id, source_url, method_id, limitations`. `emit/provenance.py` refuses an incomplete record; `tests/test_provenance_complete.py` walks every file under `site/data/` and fails on any bare scalar in a display position.

### 5.2 What is deliberately NOT computed

- **Any composite, weighted, blended or rescaled score** of topic importance, salience, relevance, engagement or equity. No `score`, `index`, `salience`, `sentiment`, `importance`, or `rank` field may exist; a schema gate rejects field names matching `^(score|index|salience|sentiment|importance|rank)`.
- **Public sentiment, support, opposition, controversy, consensus, or hearing attendance** in any form, by any proxy.
- **Casework topic composition.** Not demoted, not gated — absent. (See §11.C.)
- **Any cross-district comparison**: level, rate, per-capita figure, percentile, league table, or indicator-driven choropleth.
- **`dissent_share` aggregated per topic or per committee.** Per matter only; V2 exists specifically to show why aggregation would be unsound.
- **A deadline derived from an adjournment time.** No official source publishes one. `minutes_status: Final` indicates minutes exist; it does not supply a timestamp.
- **An inferred registration cut-off or per-speaker time limit.**
- **Any organisation address, coordinate pair, EIN join, or map pin.**
- **Any individual private resident's name.**
- **A pre-2023 → 26b areal crosswalk**, and therefore any historical per-district attribution.

### 5.3 Falsifiable sanity checks that must pass before any number ships

Deploy-blocking, hermetic, run on committed fixtures:

- **S1 Calendar floor.** ≥40 parsed rows, ≥1 future-dated, and the printed window equals the parsed min/max. Fail → previous deploy stands.
- **S2 Body invariants.** `%PDF` prefix on every PDF (verified on all 9 downloaded); `BEGIN:VCALENDAR` on iCal; body ≠ `Invalid parameters!`; no 302 to `/Error`.
- **S3 Geometry.** `mapshaper -simplify 20% keep-shapes` **without `-clean`** (`-clean` silently undoes simplification: 90,728 positions instead of 6,784). Score a 500×500 grid (89,437 in-city points) against the unsimplified 3.82 MB source: assert **0 points in two districts** and misclassification **≤0.08%** (measured 0.05%). Additionally score **2,000 real geocoded building addresses** stratified toward boundaries and coastline, because a synthetic grid clusters differently from real buildings. Geometry pinned by sha256 with DCP release `26b` recorded; CI fails on change to force a redistricting review.
- **S4 Roll-call tally invariant.** Parsed name count == printed trailing integer for 100% of retained vote blocks; otherwise the whole document is quarantined. `… and Zhuang  49 -` must yield exactly 49 names.
- **S5 Deadline arithmetic.** `safe_until > hearing start` always. `accommodation_request_by` verified against 12 hand-computed cases including Thanksgiving week and a Monday holiday. A `Deferred` or missing time must produce the `00:00 + 72h` conservative bound, not a crash and not a later timestamp.
- **S6 Name resolution.** ≥98% of last-name-only references resolved through `resolve/member_names.py` (NFC/NFKC normalisation; suffix and particle stripping — the measured failure was `Rafael Salamanca, Jr.` collapsing to last-token `jr`, which also broke Cornegy, Comrie, Recchia, Addabbo, Sanders, Espinal, Vallone and Diaz across ~600 bills, not genuine ambiguity; then a `(surname, date)` join against `uvw5-9znb` term windows; then a ~25-entry reviewed alias YAML covering the city's own typos `Williiams`, `Kalllos`, `Corengy`, `Rodriquez`, `Greenfiled`, `Gennaroi`, `Jospeh`, `Sanchez \nSanchez`). `Public Advocate Williams` and `Committee on Rules` are distinct output classes, not failures. Remainder quarantined and counted.
- **S7 Record floors.** 51 districts with a non-empty office street address; 51 districts resolving to exactly one member-or-declared-vacancy; 51 districts resolving to ≥1 community board; 0 unmapped venue strings; 0 unmapped committee strings.
- **S8 No stale forward date.** Build fails if any rendered future date traces to a source whose `max(record date)` < today.
- **S9 Transcript floors are measured, not guessed.** No participation panel ships until M7 has parsed a stratified sample of 25 transcripts across Land Use, Finance, budget and oversight hearings and published a measured coverage and affiliation-yield rate. The CI floor is set from that measurement. Two documents is not a calibration.
- **S10 Bloc withdrawal.** `bloc_concentration` is always published; if > 0.60 the vote card's rendered copy is the member-voting-record framing, asserted by a test on the rendered HTML.
- **S11 Community-board email pattern.** Every rendered CB email matches the institutional regex; the count of boards with no displayable email is published.
- **S12 Privacy guard.** Zero fields sourced from `4d7f-74pe`; zero `latitude`/`longitude`/`address` on any organisation record; zero person-name-shaped fields in participation artifacts; no address-shaped string in any URL, storage key or log sink; `private=true` present at every geosearch call site.
- **S13 Copy guards.** A denylist over every rendered string and every emitted JSON key for `sentiment`, `support score`, `approval`, `oppose`, `controversy`, `salience`, `importance score`. A refusal grep asserting every occurrence of `time limit`, `minutes to speak`, `sign up by`, `deadline to register` sits inside an element marked `data-refusal="true"`.
- **S14 Golden-output diff.** A committed snapshot of all 51 derived district JSONs is diffed on every build, so any aggregate shift is visible in the pull request even when no test covers the case.

Non-blocking, in the separately-named scheduled contract job (`contract.yml`): live upstream shape assertions, all 51 district pages, geosearch lat/lng, and the procedural source-URL canary. **403 from an Akamai-fronted `nyc.gov` host is treated as "reachable, bot-blocked", not "dead link"** — a bare curl to `nyc.gov` returns 403 and a permanently-red canary is how a solo maintainer learns to ignore CI.

---

## 6. Architecture

**Stack.** Python 3.12 / uv / ruff / pytest for ETL (`httpx`, `pdfplumber`, `PyYAML`; one pinned npm devDependency `mapshaper`, invoked by subprocess). Vanilla ES modules for the frontend — no bundler, no runtime npm dependency, one `state` object and a `render(state)` function, ~600 lines. MapLibre GL JS + OpenFreeMap, vendored into `site/vendor/`. Cloudflare Pages, deployed by wrangler from GitHub Actions.

**Build-vs-runtime split.** Everything derived from Legistar, `council.nyc.gov` or Socrata is precomputed into static JSON and into pre-rendered HTML for `/`, `/hearings/`, 51 `/district/N/`, every `/hearing/{id}/`, every `/committee/{slug}/`, `/testify/`, `/methodology/`, `/limits/`, `/glossary/`, `/corrections/`. All procedural content works with JavaScript disabled. The **only** live network call from a browser is geocoding, straight to `geosearch.planninglabs.nyc/v2/search` with `private=true`, on explicit submit. Point-in-polygon runs client-side (~25 lines of ray-casting) against the shipped simplified geometry, with a ≤150 m nearest-district snap that discloses itself when it fires (28 of 89,437 grid points fall outside every simplified polygon — coastal addresses are real addresses).

**Data flow.**

```
  UPSTREAM (build time only, no browser ever touches these)
  ┌──────────────────────────────────────────────────────────────┐
  │ nyc.legistar.com          council.nyc.gov     data.cityofnewyork.us
  │  Calendar.aspx  ──┐        /district-N/  ──┐    872g-cjhh (geom, 26b)
  │  MeetingDetail ───┤        /testify/     ──┤    5crt-au7u (CD geom)
  │  LegislationDetail┤        /legislation/ ──┤    ruf7-3wgc (boards)
  │  View.ashx?M=M ───┤        /visit-the-.. ──┤    uvw5-9znb (members)
  │  View.ashx?M=F ───┘  (1 req/10s)           │   (1 req/s)
  └────────┬───────────────────────┬───────────┴──────┬──────────┘
           │ body invariant asserted per endpoint      │
           ▼                       ▼                   ▼
  ┌────────────────────────────────────────────────────────────┐
  │ data/raw/  (gitignored, keyed by id, + .meta.json sidecar  │
  │  carrying url / fetched_at / status / bytes; never refetch) │
  └────────────────────────┬───────────────────────────────────┘
                           ▼
  ┌────────────────────────────────────────────────────────────┐
  │ parse/ → normalize/ (crosswalks/*.yaml) → compute/          │
  │   unmapped or unresolved ──► data/quarantine/*.csv (counted)│
  │   floors + invariants fail ──► JOB FAILS, prior deploy stands│
  └────────────────────────┬───────────────────────────────────┘
                           ▼
  ┌────────────────────────────────────────────────────────────┐
  │ site/  pre-rendered HTML  +  site/data/*.json  +  .ics      │
  │        manifest.json {per-source fetched_at, max_age}       │
  └────────────────────────┬───────────────────────────────────┘
                           ▼  wrangler
  ┌────────────────────────────────────────────────────────────┐
  │ Cloudflare Pages   CSP connect-src: 'self'                  │
  │                    geosearch.planninglabs.nyc               │
  │                    Referrer-Policy: no-referrer             │
  └────────────────────────┬───────────────────────────────────┘
                           ▼
  ┌────────────────────────────────────────────────────────────┐
  │ BROWSER                                                     │
  │  reads manifest.json ──► compares fetched_at to Date.now()  │
  │                      ──► renders staleness banner ITSELF    │
  │  address submit ──► geosearch (private=true) ──► lat/lng     │
  │                 ──► client-side point-in-polygon ──► ?d=NN   │
  │  map click ──► queryRenderedFeatures ──► ?d=NN  (0 requests) │
  │  URL only ever carries /district/NN or ?d=NN. Never address. │
  └────────────────────────────────────────────────────────────┘
```

**Refresh pipeline.** Four GitHub Actions workflows with independent freshness and independent failure:

| workflow | schedule | does | floor |
|---|---|---|---|
| `refresh-calendar.yml` | 06:10 / 12:10 / 18:10 ET | `Calendar.aspx`; `MeetingDetail` for next 14 days; joint merge; venues; deadlines; `.ics` | ≥40 rows, ≥1 future |
| `refresh-weekly.yml` | Sun 09:00 ET | Stated Meeting minutes (vote blocks); transcripts for meetings aged 7–35 d; committee rosters from dated PDF headers | tally invariant 100% |
| `refresh-monthly.yml` | 1st, 08:00 ET | 51 district pages @1 req/10 s; members; community boards; geometry checksum; procedure link canary | 51 office addresses |
| `contract.yml` | daily, independent of commits | live upstream shape assertions; fails distinguishably | — |

Every successful run commits `site/data/manifest.json` with the run timestamp **even when nothing changed**, because GitHub disables scheduled workflows in quiet repositories — exactly the quiet periods when nobody would notice.

**Failure and staleness behaviour.**
- Invariant violation or below-floor → job fails, previous deploy keeps serving, a GitHub issue is opened/updated, and notification reaches the owner outside GitHub.
- The client compares `manifest.json`'s per-source `fetched_at` against `max_age` (calendar 12 h, weekly 10 d, monthly 40 d) and renders a site-wide banner itself. Past the calendar threshold, the hearing list is **replaced** by a direct link to `Calendar.aspx` — it does not age into a confident lie.
- Zero future-dated rows on a healthy fetch → the recess / quiet-period state, which names both possibilities, shows the last successful check and the most recent past hearing, and lists the routes that remain (written testimony on any recent hearing, the district office, the board's next meeting).
- MapLibre `error` → a no-basemap style that still draws and hit-tests all 51 polygons. OpenFreeMap states plainly that it offers no SLA.
- No successful refresh in N days → the dead-man's switch replaces the site with a single page pointing at Legistar and `council.nyc.gov`.

---

## 6A. Service levels and performance budgets

The owner's commitment: **clicking a district or entering an address populates the answer in under one second.** That is a user-experience promise, so it is written here as a budget with named components, a measurement definition, and a defined behaviour when it is missed — not as an aspiration.

### 6A.1 Why one number is not enough

The two interactions have fundamentally different dependency graphs, and collapsing them into a single "under 1 s" would hide the only part we do not control.

- **Map click / list selection / district number** — entirely local. No network on the critical path. A sub-second target here is generous; the real budget is a fifth of that.
- **Address entry** — requires a round trip to `geosearch.planninglabs.nyc`, a third-party service we do not operate, which publishes no SLA. We cannot *guarantee* a total under 1 s because we cannot guarantee their response time. We can budget everything on our side so that the total is under 1 s whenever the geocoder behaves normally, measure what it actually does, and degrade honestly when it does not.

Stating a single flat number across both would be the same category of dishonesty this project refuses elsewhere: presenting something we cannot know as something we measured.

### 6A.2 The budgets

Reference device for every figure below: mid-tier Android profile, 4× CPU throttle, 4G network shaping (≈9 Mbps down, 85 ms RTT), page already interactive. p95 over ≥ 20 scripted runs in CI.

**SLA-1 — District selection (map click, keyboard list, district number): p95 ≤ 200 ms, p99 ≤ 400 ms, hard fail > 1 s.**

| Step | Budget |
|---|---|
| Hit-test pointer → district id (ray-casting over loaded geometry) | ≤ 16 ms (one frame) |
| Look up district record from the inline index | ≤ 5 ms |
| Paint the above-the-fold answer | ≤ 120 ms |
| Headroom | ≈ 60 ms |

Network appears nowhere in that table, which is the point, and is what R40b enforces.

**SLA-2 — Address entry → answer painted: p95 ≤ 1000 ms end to end.**

| Step | Budget | Under our control? |
|---|---|---|
| Debounce / input settle | ≤ 120 ms | yes |
| Geocode round trip to `geosearch.planninglabs.nyc` | ≤ 600 ms | **no** |
| Point-in-polygon resolution of the returned coordinate | ≤ 30 ms | yes |
| Paint the answer | ≤ 120 ms | yes |
| Headroom | ≈ 130 ms | — |

Our own share is **≤ 270 ms**. That is the number CI actually gates, because it is the only part a commit can regress. The geocoder's contribution is measured and recorded, not promised.

**SLA-3 — Autocomplete suggestions: p95 ≤ 300 ms** from keystroke to suggestion list, debounced at 120 ms, stale requests aborted, results cached by normalised query for the session. A slow suggestion must never block submitting the address the user already typed.

**SLA-4 — Cold load to interactive: p95 ≤ 3 s** on throttled 3G (this is the pre-existing R40 and is deliberately unchanged; it is a different measurement from SLA-1 and SLA-2, which both assume an interactive page).

### 6A.3 What the budgets force in the design

These are consequences, not options. Two of them correct decisions made earlier in this document.

1. **The compact 51-district index ships inline with the document.** Every district's above-the-fold answer — member, seat status, office address and phone, board, and whether a walk-in or written-testimony window is currently open — is in the initial payload. Budget: **≤ 22 KB gzipped for all 51**, inside the 60 KB envelope of R40.
2. **`district/NN.json` is demoted from the critical path.** §7 originally had it "fetched on selection, so a visitor downloads one district not fifty-one". That is a network hop on click and it violates SLA-1. It is now a **detail** payload, prefetched on hover / focus / keyboard focus and rendered below the fold; the inline index answers the click. Its contract is unchanged, only when it is fetched.
3. **Geometry must be resident before the first click.** Simplified district geometry is fetched during idle time after first paint, budget **≤ 300 KB gzipped**, and the map is not presented as clickable until it is loaded. Before then the keyboard-navigable list of all 51 districts — which needs no geometry at all — is the interaction, so the SLA holds from the first paint via that path.
4. **Point-in-polygon runs on a bounding-box prefilter first.** 51 MultiPolygons with water included is far too much to ray-cast exhaustively inside one frame; the bbox index reduces it to one or two candidate polygons.
5. **Geometry simplification is now SLA-bound, not just payload-bound.** The `mapshaper` tolerance has a second constraint: it must keep the shipped polygons accurate enough for correct district assignment (the S3 sanity check over 2,000 real addresses in M3), while staying inside the 300 KB budget. If those two conflict, correctness wins and the map gets a coarser *render* layer than its *hit-test* layer.
6. **No runtime joins, ever.** Everything a district card shows is precomputed at build time. This was already true for other reasons; the SLA makes it load-bearing.

### 6A.4 Measurement and enforcement

- A Playwright script in CI drives all four SLAs against the built site on the reference profile and fails the build on a p95 regression. Thresholds live in one committed file so a change to a promise is a reviewable diff.
- The geocoder leg of SLA-2 is measured against a **recorded fixture** in CI so the gate is hermetic and cannot fail because of someone else's bad afternoon. A separate, non-blocking scheduled job measures the **live** geocoder and records its p50/p95, so the published claim stays connected to reality.
- **There is no production percentile and there never will be** (R40e). Decision §2.15 bans analytics, which means no real-user monitoring. Every SLA figure this project publishes is a synthetic CI measurement on a reference device, and `/methodology/` states that in plain words rather than letting "p95 ≤ 1 s" imply observed field data.

### 6A.5 When an SLA is missed

- **SLA-1 miss** is a defect, not a degraded state: it can only be caused by our own code or payload, so it fails CI and never reaches a user.
- **SLA-2 miss** is expected occasionally and is a *user-visible state*, not an error: resolving at 150 ms, "still looking up — the city's address lookup is slow right now" at 1.2 s, and at 5 s the lookup is abandoned with the map and list offered instead (R40c). The address path is never the only way to an answer.
- **Geocoder outage** falls back to the location-free paths already required by R37 — browse the next 14 days, search by subject — plus district number, ZIP, and neighbourhood resolution from the committed local index (R40d).

---

## 7. Data contracts

Shipped artifacts under `site/data/`. All are public, re-fetchable, and therefore carry their guards as **fields**, not page chrome.

**`manifest.json`**
```json
{ "built_at": "2026-09-21T18:14:02Z", "git_sha": "…",
  "sources": {
    "legistar_calendar": {"fetched_at":"…","host":"nyc.legistar.com","max_age_hours":12,
      "rows":106,"future_rows":59,"window":["2026-09-02","2026-12-17"]},
    "legistar_minutes":  {"fetched_at":"…","max_age_days":10,"meetings_parsed":24},
    "legistar_transcripts":{"fetched_at":"…","max_age_days":10,
      "meetings_with_transcript":38,"meetings_in_window":57,"pending":19},
    "council_district_pages":{"fetched_at":"…","max_age_days":40,
      "districts_with_office_address":51,"districts_with_committees":45},
    "socrata_uvw5-9znb":{"as_of":"2026-04-10","catalog_says":"2026-04-10"},
    "socrata_ruf7-3wgc":{"as_of":"2025-12-26","catalog_says":"2025-12-26"}
  },
  "geometry": {"dataset":"872g-cjhh","dcp_release":"26b","sha256":"…","as_of":"2026-05-26"},
  "quarantine": {"unresolved_members":0,"unmapped_committees":0,"unmapped_venues":0,
                 "rollcall_tally_mismatch":0,"speaker_affiliation_disagreement":0},
  "limitations": "No source records who attended or testified at a hearing, what they said, or which side they took." }
```
No `degraded`, no `age_hours`. The client derives staleness.

**`districts.geo.json`** — 51 features, properties `{coundist}` only. 459 KB raw / 117 KB gzipped.

**`districts.index.json`** *(inlined into the document, never fetched separately — this is what answers a click inside SLA-1)* — one compact record per district: `{district, member_name, seat_status, district_office{street,city_state_zip,phone}, primary_board, open_windows{walk_in_next_14d,written_open_now}}`. Budget **≤ 22 KB gzipped for all 51**, counted inside R40's 60 KB envelope. Everything above the fold comes from here.

**`district/NN.json`** *(detail payload, prefetched on hover / focus, rendered below the fold — deliberately **not** on the click critical path, per §6A.3)* — `district`, `boundary_note` ("DCP release 26b; lines redrawn after the 2020 census — your district may not be the one you remember"), `member{name, seat_status: filled|vacant, vacant_since?, term{start,end}, committees[{id,name_as_seen,role}], email, district_office{street,city_state_zip,phone,fax,hours|null}, legislative_office{…}, field_provenance{<field>:{source_url,seen_at}}}`, `neighborhoods[]`, `community_boards[{borough,board,overlap_share,office,institutional_email|null,website,board_meeting_verbatim,cabinet_meeting_verbatim,next_occurrence_computed?,as_of:"2025-12-26",source_id:"ruf7-3wgc"}]`, `member_hearing_ids[]`, `open_windows{walk_in_next_14d,written_open_now}`.

**`hearings.json`** / **`hearing/{event_id}.json`** — `{id, legistar_url, committees[], joint, date, start_local, time_state, attendance_mode, venue{id,name,address,floor,room,entry_rules[]}, agenda_items[{file_num,name,type,summary,action,result,class,class_reason}], agenda_state: published|not_yet_published, topic_source: meeting_detail|calendar_placeholder, deadlines{in_person,remote_registration{state:"cutoff_not_published",contact[]},written_testimony{safe_until,basis:"start_plus_72h_lower_bound",true_deadline_note},asl_cart_request_by,interpretation_request_by,business_days_basis,too_late: bool}, vote?{matters[{file_num,affirmative{count,names[]},negative,abstain,non_voting,source_pdf_url,tally_verified:true}]}, ics_url, legistar_ics_url, video?{viebit_url,venue_code,observed_start}, transcript{status: pending|absent|parsed}, provenance{source_urls[],fetched_at}}`.

**`participation.json`** *(conditional on M7)* — `{window, coverage{hearings_in_window,hearings_with_transcript,hearings_pending,median_lag_days}, unaffiliated_resident_speakers, organizations[{canonical,seen_as[],hearings,committees[],evidence[{meeting_id,date,transcript_url,basis:"appearances_block"|"self_introduction"}]}], limitations}`. No address, no lat/lng, no EIN, no person names.

**`votes.json`**, **`coverage.json`**, **`procedures.json`** (compiled from YAML; each claim `{text, source_url, verified_on, refusal?: true}`), **`quarantine_summary.json`**, **`ics/{event_id}.ics`**.

**Reviewable research-as-data** in `crosswalks/`, every entry carrying `source` and `verified_on`, loaded by thin code and covered by table-driven tests: `venues.yaml`, `committees.yaml` (stable ids + alias crosswalk), `member_aliases.yaml`, `org_aliases.yaml`, `procedures.yaml`, `nyc_holidays.yaml`, `copy_denylist.yaml`, `refusal_strings.yaml`.

### Upstream contract tests (in `contract.yml`, must fail loudly and distinguishably)

| test | asserts | fails when |
|---|---|---|
| `test_calendar_shape` | `Calendar.aspx` 200, ≥40 rows parse, ≥1 future-dated, per-row `MeetingDetail` + iCal links present | Telerik grid markup or column order changes |
| `test_calendar_sort_order` | page 1 is strictly date-descending | sort becomes a session/VIEWSTATE preference — the entire single-GET strategy depends on this and it has never been checked |
| `test_meetingdetail_columns` | items grid carries File #, Ver., Prime Sponsor, Name, Type, Summary, Action, Result | grid reshapes |
| `test_pdf_prefix` | minutes and transcript bytes begin `%PDF` | `View.ashx` starts returning an HTML error page |
| `test_legislationdetail_not_error` | body ≠ `Invalid parameters!` and length > 1 KB | GUID scheme changes |
| `test_district_pages_51` | all 51 `/district-N/` yield a member name and a non-empty office street address | WordPress template change |
| `test_socrata_columns` | required columns present on `uvw5-9znb`, `ruf7-3wgc`, `872g-cjhh` | schema change |
| `test_socrata_max_dates` | each dataset's `max(date)` ≥ a committed baseline | silent regression or unnoticed refresh |
| `test_geosearch_contract` | `/v2/search` 200, lat/lng + `geocoding.query.parsed_text` present, `private=true` echoed, `ACAO: *` | Pelias fork changes |
| `test_geometry_checksum` | `872g-cjhh` sha256 == pinned | quarterly re-release / redistricting |
| `test_procedure_links` | every `source_url` in `procedures.yaml` reachable (403 from Akamai = reachable) | link rot on `council.nyc.gov` |
| `test_vocabulary_drift` | every committee name and venue string in fresh data exists in the crosswalks | committee rename or new off-site venue |

---

## 8. Milestones

Estimates are days for one person, and are deliberately calibrated against measured output: `~/personal/timemap_nyc` is 805 lines of `src` plus 1,022 of tests, reached in 11 commits over 5.5 months, with one CI workflow and **zero scheduled refresh jobs ever operated**. Operating crons is a first-time capability with its own cost, priced into M1.

| M | Name | Days | Exit criterion | Demo |
|---|---|---|---|---|
| **M0** | Skeleton that is visibly alive | **3** | Repo initialised (`mainline`, CLAUDE.md, README, this outline, `.gitignore`, `.specify/`, `_headers`) with fixtures already committed. `ci.yml` green on hermetic tests. A real Cloudflare Pages URL renders **one hearing card** parsed from the committed `calendar_2026-09-21.html` fixture, with CSP and `Referrer-Policy` verified in response headers. `manifest.json` ships and the client-side staleness banner provably appears when the manifest is hand-aged. | "Here is a live URL showing tomorrow's General Welfare hearing, and here is the banner that appears the moment the data goes stale — with nobody watching." |
| **M1** | Live calendar + citywide "this week" | **5** | `refresh-calendar.yml` runs 3×/day against the real host with failover, body invariants, row floor, joint-hearing merge, five canonical venues, `Deferred`/hybrid/remote/off-site states, recess-vs-breakage discriminator. `/hearings/` pre-rendered. A forced failure leaves the prior deploy serving. | "The site is now refreshing itself. I broke the parser on purpose and the deploy did not move." |
| **M2** | The deadline ledger | **6** | Per-hearing `.ics` with `TZID=America/New_York`; `safe_until` provable bound with countdown, rendering for **every** hearing in the window; accommodation request-by in business days against the holiday table with a `too_late` state; `/testify/` one-question-per-page branch; `procedures.yaml` with per-claim `source_url` + `verified_on`; refusal strings for cut-off and time limit, grep-enforced. **First and full answer to question 3; completes question 1.** | "A hearing adjourned Friday and this page tells you you have 31 hours left, what file formats, and the number to call for what nobody publishes." |
| **M3** | Address and map resolution | **5** | Geometry simplified and pinned; S3 passes on both the grid and 2,000 real addresses; `private=true` submit-only geosearch; out-of-area gate on `parsed_text`; coordinate dedupe + borough-first disambiguation; local index for district/neighbourhood/ZIP; keyboard-navigable 51-district list; MapLibre map with neutral fill and no-basemap fallback; location-free browse path. Inline 51-district index within its 22 KB budget; bbox prefilter; detail prefetch on hover/focus; the three degraded address states at 150 ms / 1.2 s / 5 s. **SLA-1 (p95 ≤ 200 ms) and SLA-2's local leg (p95 ≤ 270 ms) gated green in CI.** **Answers both user interactions.** | "Type an address, click the map, pick from a list, or browse everything — four paths, same answer, Newark is refused by name, and the click repaints in under a fifth of a second on a throttled mid-tier Android." |
| **M4** | District pages and where to take it | **4** | `refresh-monthly.yml` scrapes 51 district pages at 1 req/10 s with per-field provenance and the 51-office floor; members with the currency predicate and District 3 vacancy state; community boards joined by geometry with the institutional-email regex and verbatim cadence. **First (routing) half of question 4.** | "Here is your member, your office, your board, your board's next meeting, and one sentence on which one to call." |
| **M5** | Launch hardening | **4** | axe over every pre-rendered page; 60 KB gzipped budget and 3 s throttled-3G gate in CI; keyboard + screen-reader pass documented; accessibility statement with a working feedback address; readability gate; `/methodology/`, `/limits/`, `/glossary/`, `/corrections/` with generated coverage and quarantine counts; `LICENSE` + data terms; dead-man's switch armed; owner-identity decision (§11.D) implemented. **→ PUBLIC LAUNCH.** | "The site a real person can use, on a bad phone, with a screen reader, and it will tell the truth about itself in 2029." |
| **M6** | Agenda items and recorded votes | **5** | `MeetingDetail` agenda items for the next 14 days with `class` + `class_reason` and the "agenda not yet published" state; Stated Meeting minutes vote parsing with the tally invariant and document-level quarantine; `resolve/member_names.py` at ≥98%; `bloc_concentration` published with the >0.60 copy withdrawal; `/committee/{slug}/` pages with rosters from dated PDF headers. **First and only answer to question 2.** | "This is what the Council actually heard, and here is a 41-9 vote with the nine named — plus the number that tells you it was the same nine all year." |
| **M7** | Transcript feasibility spike *(hard kill criterion)* | **5** | A stratified sample of **25** transcripts across Land Use, Finance, budget and oversight hearings is harvested via the three-hop crawl with dedupe by file ID, and a written report publishes: crawl success rate, APPEARANCES-block presence rate by hearing type, affiliation yield per strategy, and producer-layout count. **Kill criterion, written before the sample is parsed:** proceed to M8 only if ≥60% of sampled meetings yield a downloadable transcript **and** ≥50% of parsed transcripts yield at least one asserted affiliation. Otherwise question 4's measured half is cut and `/methodology/` says so with the measured numbers. | "Here is the measured yield. Here is the decision it forces. Here are the floors, set from data instead of from two documents." |
| **M8** | Participation panel *(conditional on M7)* | **8** | `refresh-weekly.yml` harvests meetings aged 7–35 days; dual-strategy extraction with `null`-on-disagreement and quarantine; `basis` published per appearance; organisation-level output with coverage denominator and unaffiliated cohort; privacy guard green. **Completes the measured half of question 4.** | "Four organisations spoke on the record at 12 of the 31 hearings we have transcripts for — 19 still pending — and here is the page of the PDF for each one." |

**Days to public launch: 27 (M0–M5). Days to all four questions answered at maximum honest fidelity: 45, plus 8 conditional (M8).**

**Which milestone first fully answers each user question:** Q1 → **M2** (M1 gets where/when; M2 adds the entry facts and the calendar file). Q2 → **M6**, and only partially, and by substitution. Q3 → **M2**, fully. Q4 → **M4** for the routing half; **M8** for the measured half, conditional on M7. The two interactions → **M3**.

---

## 9. Testing strategy

Convention, matching the sibling project: conventional commits with `(RED)` / `(GREEN)` markers. Every pure function is written test-first — the RED commit lands the failing test with the pathological fixture, the GREEN commit lands the implementation. `pytest --strict-markers --strict-config --cov-fail-under=90`, `filterwarnings = ["error"]`.

**Unit-tested pure logic (no network, no fixtures beyond tables).** Venue normalisation; committee alias resolution; joint-hearing merge on (date, time, room); time-state classification; business-day subtraction; the `safe_until` bound; agenda-item classification; member-name resolution; point-in-polygon; out-of-area detection; candidate dedupe; ICS serialisation. Fixture tables carry the enumerated pathological inputs: en-dash and double-space venue spellings; `Deferred` in the time column; `Rafael Salamanca, Jr.`; `Carmen N. De La Rosa`; `Public Advocate Williams`; `Williiams`; `Sanchez \nSanchez`; `Avilés`/`Ossé`/`Gutiérrez`/`Cabán`; a hearing with no start time; Thanksgiving week; a Monday holiday.

**Needs committed fixtures (bytes that cannot be refetched — extract from the spike's `etl/raw/` before deleting it).** `tests/fixtures/`:
- `calendar/calendar_2026-09-21.html` (106 rows, 59 future, 15 `Deferred`, the Education/Higher Education joint pair on 10/20).
- `meeting_detail/1441286.html`, `1416976.html` (items grid with 4 items and a Roll call row).
- `district_pages/{1,3,5,9,14,25,26,35,51}.html` — 3/5/9/14/25/26 are the named committee-parse RED cases; 3 is also the vacant-seat fixture; 1/35/51 cover the three phone-label conventions, both email conventions, and the missing `Office Hours` line.
- `minutes/stated_2026-09-10.pdf` (`View.ashx?M=M&ID=1442554`; 11 `Affirmative`, 10 `Negative`, 5 `Abstain`, plus `Non-voting` and `Bereavement`) and one committee minutes PDF with **no** vote blocks.
- `transcripts/tr_plain_no_appearances.pdf` (`ID=15869017`, Transportation 6/25/26, 58 pp, single-spaced, APPEARANCES absent) and `transcripts/tr_wwd_appearances.pdf` (`ID=15834804`, Health 9/2/26, 225 pp, doubled inter-character spacing, positional APPEARANCES columns). **Both are committed in M0, before the parser is deferred**, so M7/M8 resume from RED tests rather than from an archaeology session.
- `geocoder/` out-of-area responses for Newark, Yonkers, Jersey City, Hoboken; the `100 Broadway` three-borough case; the `100 B'WAY` / `100 BROADWAY` duplicate-alias case; `11217`, `Bushwick`, `District 35`.

**Needs upstream contract tests (network, separate scheduled job, fails distinguishably).** The twelve tests in §7. These never gate a deploy, because CI going red for Granicus's reasons is how a solo maintainer learns to ignore CI.

**SLA gates (Playwright, blocking, hermetic).** The four SLAs in §6A are driven against the built site on the reference profile — mid-tier Android, 4× CPU throttle, 4G shaping — with p95 over ≥ 20 runs and thresholds in one committed file so changing a promise is a reviewable diff. The geocode leg runs against a recorded fixture so the gate can never fail because of someone else's outage. Cases that must be asserted, not just measured: geometry not yet loaded (the list path must still meet SLA-1); the bbox prefilter's worst case, which is a click in a district with extensive water geometry; and the three degraded address states firing at their thresholds. A separate **non-blocking** scheduled job measures the live geocoder's p50/p95 and records it, so the published SLA-2 claim stays tethered to reality without a third party being able to redden the build.

**Monitored, not tested.** Real-user latency. There is none to observe — §2.15 bans analytics, so no RUM exists and no production percentile is ever published (R40e). This is a deliberate, stated trade: browser-enforced zero-third-party privacy in exchange for synthetic-only performance evidence.

**Monitored rather than tested.** Quarantine counts and their trend (a parser regression shows as a coverage drop, not as a crash). Transcript publication lag distribution. The share of hearings whose `topic_source` is `calendar_placeholder`. Row-count swings beyond threshold. Geometry checksum drift. `bloc_concentration` drift. Deploy-token validity — the refresh jobs can succeed while wrangler deploys silently stop, which the staleness banner catches only after the fact.

**Guard tests that encode the reasoning, each carrying a comment citing the specific measured evidence** so a future reviewer sees the evidence before deleting the check: the `bldgclass A1, unitsres=1` finding on the privacy guard; the 156-district-code count and the 58% housing collapse on the casework exclusion; the −0.704 friction correlation and the 0.000 #1-vs-#2 gap on the no-composite schema gate; the 54.2x volume spread on the no-cross-district-comparison gate.

**ADRs** (`docs/adr/`), because these will otherwise be relitigated: no composite score; no sentiment or attendance metric; casework cut; discretionary funding cut; organisation-level aggregation only and no individual resident names; no LLM in the build; Cloudflare over GitHub Pages; Legistar API key requested but not depended on; the district is a filter, not the key; written-testimony bound rather than estimate; English-only at launch; transcripts behind a measured kill criterion.

---

## 10. Risks and mitigations

Ranked by expected harm × likelihood. Each carries the trigger that tells you it is materialising.

1. **The project never ships.** Every design reviewed was 3–10× the owner's entire demonstrated lifetime output, and all depended on unattended crons the owner has never operated.
 *Mitigation:* launch at M5 (27 days) with only the two fully-answerable questions plus routing. M6–M8 are post-launch and separately specced. Casework, PB probing, eLobbyist, ten-language translation, OG-image binaries and RTL wiring are all out of v1.
 *Trigger:* M0–M2 takes more than 20 days, or two consecutive weeks pass with no commit.
2. **The site sends someone to a room on the wrong day.** ~15% of page-1 rows read `Deferred`; same-day changes are structurally invisible; the calendar can go stale.
 *Mitigation:* 3×/day refresh, 12-hour gate that replaces rather than ages the panel, fetch timestamp and "Confirm on Legistar before you travel" **inside** every card, `MeetingDetail` deep link as the authority, `Deferred` as its own state.
 *Trigger:* any correction report about a hearing that did not happen; `contract.yml` red for more than 24 hours.
3. **A build reports success while shipping empty or partial data.** Three verified endpoints return HTTP 200 carrying an error body.
 *Mitigation:* body invariants over status codes; row and field floors; vocabulary-drift gate; fail closed with the prior deploy serving; quarantine counts in the UI.
 *Trigger:* a quarantine count moves off zero; `districts_with_office_address` < 51; `future_rows` = 0 on a healthy fetch.
4. **A number is read as community sentiment.** The user asked for it; readers will supply it even where we do not.
 *Mitigation:* no composite, no sentiment field, copy denylist over rendered strings **and** JSON keys, `limitations` as a required field so the caveat survives a raw `/data/` fetch, "Recorded votes of Council Members — not community opinion" in the same element as the counts, `bloc_concentration` published alongside.
 *Trigger:* a citation of the site that reframes a vote split as public opinion; a pull request that adds a score-shaped field.
5. **Honest emptiness reads as "nobody organises where you live."** The single most demoralising false message this product can send, and it arrives through truthful thinness, not fabrication.
 *Mitigation:* any card that can render near-empty carries an in-place sentence that absence is a property of the published record, not of the neighbourhood, plus the routes that remain. If a card cannot carry that sentence credibly, it does not ship. The M7 kill criterion exists precisely so a thin participation panel never launches.
 *Trigger:* M7 measures affiliation yield under 50%; a district page renders with zero organisations and zero open windows.
6. **The Legistar scrape breaks and the forward layer empties.** `nyc.legistar.com` is a Granicus-operated vendor ASP.NET deployment with no robots.txt (404), no published terms we have read, no versioning and no SLA.
 *Mitigation:* one adapter (`src/council_access/sources/legistar.py`) as the single seam; body invariants; failover host; `contract.yml` on an independent schedule so breakage surfaces without a commit; degrade to stale-but-labelled, then to a Legistar link; request the API key now (§11.E) so it exists behind the seam if needed.
 *Trigger:* `test_calendar_shape` or `test_calendar_sort_order` fails; a 403 or 429 from `nyc.legistar.com`.
7. **Misattributing a statement, a vote, or an organisational affiliation to a named person.** PDF text extraction plus regex, in a product about who speaks for whom.
 *Mitigation:* organisation-level aggregation only; no individual resident named anywhere; tally invariant with document-level quarantine; APPEARANCES and self-introduction must agree or emit `null`; ≥98% name-resolution floor with the remainder quarantined, never guessed; every claim links its source PDF; published correction and removal channels.
 *Trigger:* any quarantine row in `speaker_affiliation_disagreement.csv` or `rollcall_tally_mismatch.csv`; a single correction report about a named person.
8. **The typed address leaks.** The audience includes tenants in active disputes and residents wary of any government-adjacent data trail; the address necessarily travels to a third party as a GET query string.
 *Mitigation:* `private=true` at every call site (grep-enforced); submit-only, no autocomplete; never in URL, storage, cookie or log; disclosure in one plain sentence at the input naming NYC Planning as recipient; map-click and district-list paths that disclose nothing, at full parity; CSP `connect-src` allowlist; `Referrer-Policy: no-referrer`.
 *Trigger:* the privacy Playwright test finds an address-shaped string anywhere; any non-allowlisted origin appears in a network trace.
9. **Redistricting or a quarterly geometry update silently invalidates every district answer.** `872g-cjhh` is re-released periodically; the current version is `26b`.
 *Mitigation:* sha256 pin with CI failure on change to force an explicit review; boundary-vintage note on every district page; full-precision source authoritative for the misclassification test; simplified copy display-and-lookup only with the bounds asserted.
 *Trigger:* `test_geometry_checksum` fails.
10. **A stale contact sends someone to a closed office.** District office addresses exist in no dataset, and the CB list publishes personal mailboxes for five boards.
 *Mitigation:* per-field provenance and `seen_at`; institutional-email regex gate; never render `cb_chair` or `cb_district_manager`; `dy27-rrad` and `3gkd-ddzn` blocklisted by id; a 24-month staleness gate that hides the panel rather than ageing into a lie.
 *Trigger:* `districts_with_office_address` < 51; a correction report about an office.
11. **Abandonment with the lights on.** A stale-but-bannered site still ranks in search and still sends people to rooms.
 *Mitigation:* client-side manifest banner; dead-man's switch that replaces the site with a signpost page after N days without a successful refresh; a written sunset policy and a second credential holder in the repo.
 *Trigger:* no successful refresh for 14 days.
12. **Permission and politeness.** Nobody has read Granicus's terms; `nyc.legistar.com/robots.txt` is a 404 and "no robots.txt" is not permission. `nyc.gov`'s current Terms of Use (modified 2025-07-14) contains no automated-access prohibition, but `council.nyc.gov` is a distinct host whose terms were never checked.
 *Mitigation:* read `granicus.com/legal` in a real browser and record an ADR; email the Council's legislative/data contact describing exactly what is fetched and at what rate (which is also the natural moment to request the API key); state the basis relied on in `/methodology/`; keep volume low, honour `Crawl-delay: 10` and `Crawl-delay: 1`, one descriptive User-Agent with a contact URL.
 *Trigger:* any block, throttle or takedown contact.
13. **Scope creep re-acquires a cut harm.** "Add the org map back" looks like a small feature request once the reasoning has left everyone's head.
 *Mitigation:* every hard constraint is an executable test whose comment cites the measured evidence; twelve ADRs; §12 of this document.
 *Trigger:* a pull request that adds a score-shaped field, an organisation coordinate, or a person-name field.

---

## 11. Decisions needed from the owner

These are the calls the critic identified as yours. The plan body above encodes the **recommendation** as a provisional default so the document is buildable; each entry states what changes if you choose otherwise. None is silently settled.

**A. What is actually in v1.**
*Options:* (1) Q1 + Q3 only — a complete, honest, small product. (2) Q1 + Q3 + routing for Q4 + agenda items and recorded votes for Q2, launching at M5 with M6 immediately after. (3) The full four-question product before any launch.
*Recommendation:* **(2), with launch at M5 and M6 landing post-launch.** Q1 and Q3 are the only parts the evidence fully supports and the only parts that change what someone does this week. Q4's routing half is four days and genuinely useful. Q2's substitute is five days and is the only defensible thing anyone can say about "disagreement."
*Consequence:* (1) ships in ~4 weeks but publishes nothing about topics or groups, which will read as not delivering. (2) ships in ~5.5 weeks with all four questions addressed at different fidelities by week 8. (3) is a 12–20 month horizon and the most likely outcome is that nothing ships. **Every other decision here is downstream of this one.**

**B. Is the council district the organising unit, or a filter?**
*Options:* (1) District-first: 51 district pages as the centre of gravity. (2) Calendar/topic-first: the citywide 14-day list and per-committee/per-hearing pages are primary, with the district as a highlight and filter. (3) Hybrid: district pages exist and are linkable, but the home page and primary journey are citywide.
*Recommendation:* **(3).** Five independent findings say the district is the wrong unit — committee hearings are citywide and belong to no district, casework cannot be attributed to current lines, funding is attributed by recipient address, and the genuinely local body is the community board. It costs almost nothing because the data is fetched citywide regardless, and it is the only version that serves people without a fixed address and people whose issue is not where they sleep.
*Consequence:* (1) promises a district-level personalisation the data cannot deliver, and excludes shelter residents and multi-district organisers at the front door. (3) makes the map a selector rather than the hero, which slightly weakens the "click a district and learn its info" interaction you asked for — it still works, it just is not the centre.

**C. Does any "what matters in this district" panel ship?**
*Options:* (1) None in v1; Q2 answers with agenda items and recorded vote splits only. (2) Within-district casework composition with Beta-Binomial intervals, empirical-Bayes shrinkage, n<1,500 suppression and an office-intake label, demoted below the fold. (3) Casework re-keyed to community district with a blocking external-validity gate against HPD violations.
*Recommendation:* **(1).** The construct is falsified by its own natural experiment (housing casework fell 58% during the eviction moratorium — peak need), the data effectively ends in 2023, the district codes predate the current boundaries, and the honest statistical apparatus is the largest single block of work in the project. Say on `/methodology/` exactly why it is absent, with the numbers.
*Consequence:* (1) is the visible gap between what you asked for and what ships, and it is also the difference between a 5.5-week launch and a 4-month one. (2) keeps the hardest code in the project serving the least-defended surface. (3) requires building an independent HPD-violations-per-occupied-unit dataset at matched vintage, whose designed outcome is to *block* a feature.

**D. Are you named publicly, and what is the kill condition?**
*Options:* (1) Your legal name plus a personal correction address. (2) A project identity with a role address (`corrections@…`) and a stated response-time commitment. (3) Either of the above plus a dead-man's switch that replaces the site with a signpost page after N days without a successful refresh.
*Recommendation:* **(2) + (3), with N = 14.** A site publishing named officials' recorded votes in an election-heavy jurisdiction is a harassment surface, and a staleness banner does not decide whether an eighteen-month-stale site should still be online — a scheduled job can.
*Consequence:* (1) is irreversible once indexed. (2) trades a small amount of "accountability" signalling for a real reduction in personal exposure. Without (3), the abandonment story the whole architecture is built around has no ending.

**E. Transcripts: mandatory v1 stage, time-boxed spike, or cut?**
*Options:* (1) Mandatory v1 ETL stage. (2) A five-day spike (M7) parsing a stratified sample of 25 transcripts across Land Use, Finance, budget and oversight, publishing measured coverage and affiliation yield, shipping the panel only if it clears a threshold written down *before* the sample is parsed. (3) Cut; answer Q4 by routing only.
*Recommendation:* **(2), with the thresholds as stated in M7 (≥60% harvest success, ≥50% affiliation yield).** Two competing designs planned to set a CI alarm from a sample of two documents, and both named the failure mode as a quiet undercount of organisational participation — the "nobody organises where you live" inversion. Commit both producer-layout fixtures in M0 regardless, so the work resumes from RED tests whenever it resumes.
*Consequence:* (1) is the largest and least bounded work in the project and risks the action layer shipping late or not at all. (2) delays the measured answer by roughly two weeks past launch and may cut it on evidence. (3) forfeits the only measured route to the question you actually asked, and the exploration proved the capability is real.

**F. Do we request the free Legistar API key?**
*Options:* (1) Do not request it; record the refusal. (2) Request it now via `council.nyc.gov/legislation/api/`, ship v1 unauthenticated, keep it behind the adapter as an optional accelerator with CI always exercising the unauthenticated path.
*Recommendation:* **(2) — a departure from all three designs.** They win the capability argument (votes, agendas, topics and transcripts are all reachable without it) but do not rebut the option-value argument: requesting a key creates no obligation to depend on it, the latency is human-mediated and unknown, and the scraper is a vendor-controlled single point of failure. The request email is also the natural moment to disclose the crawl and ask whether the Council objects (Risk 12).
*Consequence:* (1) means that if Granicus reshapes the grid, the fallback is a manual runbook and you request the key under time pressure. (2) costs one email and one secret that only Actions ever sees, and creates a per-person licence question to read before use.

**G. Publishing individual public speakers' names.**
*Options:* (1) Organisation-level aggregation only; no private individual named in any artifact. (2) Republish the public record as-is, since transcripts are public documents.
*Recommendation:* **(1).** Transcripts name residents alongside their medical and housing circumstances; re-publishing that as a searchable index is a meaningful escalation of reach even though every fact is already public, and a misattributed affiliation from a regex error would be a false claim about a named private person.
*Consequence:* (1) structurally overstates how organisation-dominated hearings are — roughly half of verified witnesses state no affiliation — which the counted resident cohort mitigates but does not fix. (2) is a change to the data model, not just the UI, and should not be made by default.

---

## 12. Explicitly out of scope for v1

| Excluded | Reason |
|---|---|
| Any composite importance / salience / engagement / equity score, and the rescale-to-100 step | Components are incommensurable and two are near-collinear (ρ 0.892); the rescale manufactures rankings from a measured 0.000 gap. Permanently out, enforced by a schema gate. |
| Sentiment, support, opposition, controversy, consensus, attendance counts, any inferred stance field | No public source records any of it. Permanently out. |
| Cross-district ranking, percentile, league table, per-capita normalisation, indicator choropleth | "My district is darker" is the mental model regardless of the legend; districts are equal-population by law so per-capita adds a false incidence implication. |
| Constituent-services casework (`b9km-gdpy`) in any form | Effectively ends 2023; 21.3% not district-attributable; codes predate current boundaries; construct falsified by the 58% pandemic collapse. |
| Discretionary funding (`4d7f-74pe`) in any form, including a labelled historical panel | FY2021 end; district is the recipient's mailing address; ~19% of addresses are residentially classed with verified single-family homes owned by named individuals. Permanently out. |
| City Clerk eLobbyist (`fmf3-knd8`) | Current and honest, but 77% of sampled filings name no district and targeting concentrates on the Speaker's seat, so most district pages would read "nobody organises here." Revisit as a v2 accountability surface. |
| Bills and sponsor history (`6ctv-n46c`) and any "friction" construct | `max(intro_date)` 2025-02-27; `primary_sponsor` is a bare last name; friction's own components correlate −0.704, so it has no coherent construct. |
| `__VIEWSTATE` postback pagination and any 2025 historical backfill | 374 KB postback for the least valuable data; the 2024→2026 coverage gap is disclosed instead. |
| A pre-2023 → 26b areal crosswalk | Requires prior-plan geometry from DCP BYTES that we do not have; without it, no historical per-district attribution is defensible. |
| Participatory Budgeting per-district probing | 51 hand-authored non-uniform microsites; `council.nyc.gov/pb/` publishes no online idea form, no eligibility age and no participating-district list. |
| Community Board member rosters; any named CB chair or district manager | Unpaid volunteer appointees; `dy27-rrad` is seven years stale with a contact field truncated mid-email. |
| An organisation directory, map pin, street address, coordinate pair or EIN join | Aggregation harm: a geocoded directory of small nonprofits is a targeting tool, and 8,854 distinct org names map to only 5,262 EINs with 1,594 fiscal-conduit rows. |
| Individual private residents' names; any searchable speaker index | Escalation of reach beyond the public record; requires a separate documented decision. |
| Any LLM or NLP step inside the build, including org-name canonicalisation | Reproducibility and zero model cost in CI are worth the coverage loss. |
| Geocoder autocomplete | One request per keystroke streams partial home addresses to a third party for cosmetic polish on a one-shot lookup. |
| User accounts, email or SMS reminders, saved searches, comments, forums; proxying, pre-filling or submitting testimony; any server-side log pairing an IP with a district | All require a server and PII, and the last would be a political-activity record. |
| Full translation into the designated citywide languages | The list itself could not be verified (canonical nyc.gov page is 404 today), no translator or re-translation gate exists, and a mistranslated deadline is a harm. Strings are externalised so this is purely additive. |
| The "~23% LEP" figure | Not sourceable to a fetchable document. |
| `ye4r-qpmp` district demographics, `cgwq-3ie6` broadband, `szq8-b4uy` housing database | `ye4r-qpmp` is a non-tabular "blobby" XLSX attachment and returns a Socrata error; the others are context we do not need to answer the four questions. |
| Committee minutes vote parsing at scale (~13,700 PDFs, ~4-hour crawl) | Stated Meetings only (~24/year) gives the same signal at 0.2% of the crawl. |
| Self-hosted map tiles | The MIT licence and weekly planet download are a researched escape hatch, noted not built. |
| A copyable pre-filled testimony template | Highest-leverage conversion step and the most open to a coaching charge. Revisit after user testing. |
| Other cities; real-time vote tracking; any runtime scrape from the browser | Scope, and CORS makes the last impossible. |
| Build-time OG card PNG rendering via a pinned native binary | A native binary in the build chain is what silently breaks on a runner-image change in eighteen months and never gets fixed. |
| A Playwright suite that loads the production site and asserts the live map and geocoder work, as a deploy gate | Makes CI red on third-party outages, which trains a solo maintainer to ignore CI. Lives in `contract.yml` instead. |

---

## 13. Open questions / further research

1. **Do Granicus's terms of use permit automated retrieval of `nyc.legistar.com`?** Nobody has read them. `robots.txt` is a 404 and the legal pages are JS-rendered. This is the product's entire spine. Read in a real browser; record an ADR; email the Council. `council.nyc.gov`'s own terms, if any, are also unchecked. (`nyc.gov`'s current ToU was checked and contains no automated-access prohibition, but that is a different host.)
2. **Does `private=true` actually suppress server-side logging?** We verified only that the flag is echoed in the `geocoding.query` block — that proves it was parsed, not that anything was done with it. This is the most load-bearing privacy claim in the plan and it is presented to users as a guarantee. Ask NYC Planning Labs directly, and soften the copy until answered.
3. **Is `Calendar.aspx`'s date-descending sort guaranteed, or a session/VIEWSTATE-persisted preference?** The entire single-GET strategy depends on it. `test_calendar_sort_order` catches a change after the fact; a direct probe (fetch with a cold session, then after interacting) would establish it.
4. **Does any minutes PDF print an adjournment time?** If yes, `safe_until` can be upgraded from a lower bound to the exact deadline on the weekly job. If no, the bound is permanent. Nobody has looked.
5. **Does APPEARANCES-block presence correlate with hearing type, length, or transcription vendor?** Two documents is not a sample. M7 answers this or the panel does not ship.
6. **Is there an authoritative source for Council recess dates?** The row-count discriminator distinguishes "healthy fetch, no future rows" from "breakage", but published recess dates would let the empty state say *why*. Check the Council Rules and the annual legislative calendar before declaring them unavailable.
7. **What is NYC's actual list of designated citywide languages, and does a non-agency civic tool have any obligation?** Every nyc.gov language-access URL attempted returned 403/404/490 and the canonical page is still 404 today. Do not assert the list from memory.
8. **NYC prior art and a review partner.** `nyc.councilmatic.org` does not resolve. Nobody looked for BetaNYC, Open Plans, City Limits' tools, or the Council's own data team. A one-person project with a multi-month v1 is exactly the case where joining existing work is higher-leverage — and a friendly read from one council office and one civic-tech group would catch procedural misstatements no dataset can validate.
9. **Is there a second source for district office addresses?** Four lenses assert `council.nyc.gov/district-N/` is the only one, but nobody checked the Council's published member directory or the City's Green Book. A second source for the field whose silent parse failure is our worst data outcome would be cheap insurance.
10. **The mobile-share assumption.** 56.8% mobile comes from `analytics.usa.gov` aggregate federal-site traffic on a 2025-02-05 snapshot described as rolling-30-day. The performance budget is right regardless, but the figure should not be quoted on the site.
11. **Is a copyable testimony template neutral information or coaching?** Highest-leverage step from intent to action; decide after user testing, not by drift.
12. **How should refresh failures reach a human?** A failed scheduled Action in a quiet personal repo is easy to miss for weeks — precisely the scenario the fail-loud requirement exists to catch. The staleness banner reaches users; nothing yet reliably reaches the owner.

---

## 14. Sources

**Legistar (Granicus, vendor-hosted; no robots.txt — 404)**
- `https://nyc.legistar.com/Calendar.aspx` — primary schedule; failover `https://legistar.council.nyc.gov/Calendar.aspx`
- `https://nyc.legistar.com/MeetingDetail.aspx?ID=1416976&GUID=890BAAD0-…&Options=info|` — agenda items grid
- `https://nyc.legistar.com/MeetingDetail.aspx?ID=1418199` — Stated Meeting 12/17/2026
- `https://nyc.legistar.com/View.ashx?M=M&ID=1442554` — Stated Meeting minutes 9/10/26, vote blocks
- `https://nyc.legistar.com/View.ashx?M=F&ID=15869017&GUID=54BFF892-5DEC-4B15-A977-92F80D8C506D` — transcript, Transportation & Infrastructure 6/25/26, 58 pp, no APPEARANCES
- `https://nyc.legistar.com/View.ashx?M=F&ID=15834804&GUID=FB520B19-0116-492C-A03A-6B2496AF4B35` — transcript, Health 9/2/26, 225 pp, APPEARANCES, doubled spacing
- `https://nyc.legistar.com/View.ashx?M=IC&ID=1418199&GUID=D910E40A-…` — per-row iCalendar, 284 bytes, no TZID
- `https://webapi.legistar.com/v1/nyc/bodies` — **HTTP 403 "Token is required"**
- `https://webapi.legistar.com/Home/Examples` — Granicus API reference
- Dead or error-carrying routes recorded so nobody re-tries them: `Feed.ashx` (410 bare; 200 + "Invalid feed" parameterised), `DepartmentDetail.aspx` (410), `View.ashx?M=AO&ID=181205` (302 → `/Error`), `LegislationDetail.aspx?ID=7861919&GUID=X` (200, 19-byte `Invalid parameters!`)
- `https://councilnyc.viebit.com/vod/?s=true&v=NYCC-250-8-1_260909-102026.mp4` — decoded from `Video.aspx?URL=<base64>`; no captions, no m3u8, `/api` → 404

**council.nyc.gov** (`Crawl-delay: 10`)
- `/district-1/` … `/district-51/` — member, committees, district office, legislative office
- `/testify/` — in-person no pre-registration; remote form; written testimony 72 h after adjournment; DOC/DOCX/PDF ≤10 MB; permanent public record; ASL/CART `EEOOfficer@council.nyc.gov` / 212-788-6936, ≥3 business days; interpretation `translationservice@council.nyc.gov`, ≥3 business days; general `hearings@council.nyc.gov` / 212-482-4219
- `/legislation/` — only Council Members introduce legislation; no public petition route
- `/legislation/api/` — free API key request form
- `/land-use/` — Zoning & Franchises and Landmarks subcommittee exception
- `/visit-the-council/` — photo ID at 250 Broadway; NYPD screening and metal detectors; Sergeant-at-Arms each floor; no food, beverage containers, or signs larger than 8.5" × 11"
- `/pb/` — Participatory Budgeting cycle; `pbnyc@council.nyc.gov`; ≥$50,000 and ≥5-year lifespan
- `/accessibility/`, `/procedures-governing-member-and-public-remote-attendance/`
- NYC Bill Drafting Manual (2022), public

**NYC Open Data / Socrata** (`data.cityofnewyork.us`, `Crawl-delay: 1`)
- `m48u-yjt8` City Council Meetings (1999–2024), 16,104 rows — `max(meeting_date)` **2024-12-19**
- `6ctv-n46c` Legislation, 11,622 rows — `max(intro_date)` 2025-02-27; `primary_sponsor` is a bare last name, 207 distinct values, literal `NA`
- `4d7f-74pe` Discretionary Funding, 97,002 rows — `max(fiscal_year)` **FY2021**; catalog reports modified 2025-12-30 — **cut**
- `b9km-gdpy` Constituent Services, 341,299 rows — `max(opendate)` 2025-01-09, effectively ends 2023; 60,444 NULL districts; 156 distinct `council_dist` values — **cut**
- `aabe-yfm9` Committee Membership — **zero rows** with `start_date >= 2026-01-01`
- `uvw5-9znb` Members (1999–present), 558 rows — 52 with NULL district; District 3 `term_end` 2026-02-03
- `872g-cjhh` City Council Districts — GeoJSON export 3,824,478 bytes, 51 MultiPolygons, 97,703 positions, "Current version: **26b**", quarterly, last 2026-05-26
- `5crt-au7u` Community Districts — GeoJSON, 3.79 MB
- `ruf7-3wgc` NYC Community Boards — 59 rows, 44 distinct `council_district`, 31 institutional emails
- `dy27-rrad` CB Contact List (2019) — **blocklisted**; `3gkd-ddzn` CB Leadership (2017) — **blocklisted**
- `fmf3-knd8` City Clerk eLobbyist, 79,726 rows — NOT-V1
- `64uk-42ks` PLUTO — used once, to establish the funding-address privacy harm
- `ye4r-qpmp` council-district demographics — non-tabular "blobby" XLSX, not queryable
- `cgwq-3ie6` Broadband Adoption by Council District; `szq8-b4uy` Housing Database — out of scope
- `mkqi-d8x3` / `jgqm-ccbd` — water-included district geometry variants, not used

**Geocoding**
- `https://geosearch.planninglabs.nyc/v2/search?text=…&size=…&private=true` — `ACAO: *` on GET, **403 on OPTIONS**; `geocoding.query.parsed_text` is the only out-of-area detector
- `https://geosearch.planninglabs.nyc/v2/autocomplete` — exists; deliberately unused

**Mapping and hosting**
- `https://openfreemap.org/` — no limits, no keys, no cookies, MIT, commercial use permitted, weekly planet downloads, **no SLA**
- MapLibre GL JS; Cloudflare Pages (brotli + arbitrary response headers); GitHub Pages (no header mechanism) — rejected

**Standards, precedent and method**
- W3C WAI — WCAG 2.2 (published 2023-10-05, updated 2024-12-12); conformance to 2.2 implies 2.1 and 2.0
- `ada.gov` Title II web rule fact sheet — WCAG 2.1 AA for state/local government content; deadlines 2027-04-26 and 2028-04-26
- `https://spatialequity.nyc/static/js/main.5fdf13d5.js` — 18 independent metrics, per-source `methodologyWarning`, `boundTexts`, `higherValueIsBad`, `mapTooltipSnippet`; **no composite anywhere**. Ships gtag and Mapbox, which we reject.
- `https://chicago.councilmatic.org/` — "Non-Routine" classification; action verb paired with every date; terminology note
- `https://pluralpolicy.com/find-your-legislator`, `https://portal.311.nyc.gov`, `https://www.gov.uk/check-uk-visa`, `https://howfar.nyc/` — entry-point and empty-state precedent
- `screeningtool.geoplatform.gov` (CEJST) — threshold-and-count instead of weighted composite; **now fails DNS resolution**, which is itself a requirement: all derived data must be regenerable from committed scripts and all scraped sources archived locally
- Saisana, Saltelli & Tarantola, *JRSS-A* 2005, doi:10.1111/j.1467-985X.2005.00350.x — uncertainty and sensitivity analysis as prerequisites for composite rankings
- Becker, Paruolo & Saisana, "Weights and Importance in Composite Indicators: Mind the Gap", doi:10.1007/978-3-319-12385-1_40
- Ravallion, *J. Development Economics* 2012, doi:10.1016/j.jdeveco.2012.01.003
- Minkoff, *Urban Affairs Review* 2015, doi:10.1177/1078087415577796 — 311 contacting propensity vs condition
- O'Brien, Sampson & Winship, *Sociological Methodology* 2015, doi:10.1177/0081175015576601
- Kontokosta & Hong, *Sustainable Cities and Society* 2021, doi:10.1016/j.scs.2020.102503
- *Health & Place* 2020, doi:10.1016/j.healthplace.2019.102282 — NYC 311 socio-spatial reporting bias
- `analytics.usa.gov/data/live/devices.json` — 56.8% mobile, snapshot 2025-02-05 (used for the budget, not quoted on the site)

**Internal**
- `~/personal/timemap_nyc` — `pyproject.toml` shape (py312, 20-rule ruff select, `--cov-fail-under=90`, `filterwarnings = ["error"]`), CLAUDE.md conventions, `.specify/`
- The prior spike at `~/personal/council_access_nyc` — 11 files, zero commits, no tests, no transform stage, 78 MB untracked. Discarded. Ported as specifications: `topics.mjs` (28-topic ordered-rule crosswalk with its explicit `unmapped` bucket), `procedures.mjs` (per-claim `SOURCES` map + `LAST_VERIFIED`), `venues.mjs` (canonical venues with entry instructions), `fetch.mjs` (raw cache, stable `$order` paging, retry with backoff, server-side `$group`). Discarded: `geo.mjs` simplification, `salience.mjs`, `html.mjs`. **Fixtures extracted from `etl/raw/` before deletion — those pathological rows are a dated snapshot that cannot be refetched.**