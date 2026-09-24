# Exploration record — 2026-09-21

Provenance for `council-access-project-outline.md`: which parts of the plan rest on verified
evidence and which rest on judgement.

Method: six independent research lenses, three competing end-to-end designs with deliberately
different priorities, three judges scoring on distinct criteria, one completeness critic.
**14 agents, 313 tool calls, ~1.84 M tokens, 52 minutes.** Full per-agent returns are in the
uncommitted workflow journal.

## Lens headlines

| Lens | Conclusion |
|---|---|
| Data feasibility | Hearing transcript PDFs are freely fetchable with no API key and carry named speakers, self-stated affiliations, and — in larger hearings — an explicit `APPEARANCES` name-to-organisation index, so question 4 is answerable. Three datasets treated as current are stale by 20 months to 5 fiscal years |
| Requirements | Two of the four user questions cannot be answered from any public source. Every Council open dataset is 1–5 years stale, while Legistar's public HTML carries live schedules, agenda-item topics, vote tallies and per-member attendance. Re-specify the product as a "what can I do about this, this week" action tool over a live scraped layer, forbid sentiment claims, and treat a council-district-vs-community-board router as a v1 must |
| Measurement methodology | "Contested" is measurable — named roll-call splits parse out of free minutes PDFs. "Important to your community" is **not** measurable from casework volume, which varies **54×** across statutorily equal-population districts and fell by half during the eviction crisis. The five-component composite score must be **deleted, not reweighted** |
| UX precedent | Spatial Equity NYC's single most transferable move is that it computes **no composite score at all**. Build the action layer on the two current sources; fence the analytics layer visibly as history |
| Civic ethics | Publishing discretionary-funding recipients as "community groups" would put a map pin on a named private individual's single-family home — the chain was verified against PLUTO. Cut it. The registered-lobbyist disclosure record answers a similar question while pointing *up* the power gradient |
| Architecture | A fully static site with build-time ETL is not the cheap option, it is the only one the upstreams permit: Legistar sends no CORS header and the open datasets stop before the current Council session. The real risk is **silent staleness**, which four of the six datasets the spike depended on already exhibit |

## Judge verdicts

Each judge picked a **different** winner, which is why the plan is a synthesis rather than an
adoption.

| Judge | Winner | Scores |
|---|---|---|
| User value & honesty | Design 1 — action-first "deadline engine" | 8 / 6 / 7 |
| Methodological rigor | Design 2 — "On the Record NYC" | 7 / 8 / 5 |
| Engineering viability | Design 3 — anti-abandonment variant | 4 / 2 / 6 |

The synthesis takes **Design 1's thesis** (action over analysis), grafts **Design 2's**
pre-registered thresholds, kill criteria and quarantine discipline, and adopts **Design 3's**
anti-rot machinery (browser-side staleness, fail-closed refresh, dead-man's switch).

The engineering judge scored *every* design low: "No design as written survives contact with this
maintainer's demonstrated capacity." It sized milestones against measured output from the sibling
project — `timemap_nyc` is 805 lines of `src` plus 1,022 of tests, 11 commits over 5.5 months, one
CI workflow, and **zero scheduled refresh jobs ever operated**. The plan's day estimates are
calibrated to that, and operating crons is priced as a first-time capability.

> **Caveat on the numeric ranking.** The workflow aggregated judge scores by design *name*, and the
> judges returned slightly different name strings, so its mean ranking split votes across variants
> and is unreliable. The verdicts above were read directly from each judge's return, and the
> synthesizer was instructed to treat the ranking as advisory.

## Blocking gaps the critic found

1. **Community Board emails name private individuals.** Of 59 boards in `ruf7-3wgc`, only 31
   `cb_office_email` values match the institutional `xx##@cb.nyc.gov` pattern; 11 are the district
   manager's own name-based address; 5 are personal consumer mailboxes (`…@verizon.net`,
   `…@optonline.net`, `…@nyc.rr.com`, `…@gmail.com`); 1 is missing. → Display the email only on a
   mechanical regex match, never render `cb_chair` or `cb_district_manager`, assert the pattern in
   CI. (R30)
2. **Seven council districts have no board via the dataset's own join key.** `ruf7-3wgc` has 59 rows
   but only 44 distinct `council_district` values. → Join by **geometry**
   (`5crt-au7u` × `872g-cjhh`) at build time, with a CI floor asserting all 51 districts resolve to
   at least one board.
3. **No entry path for someone without a stable address** — shelter residents, transitional housing,
   confidential addresses. → Add location-free entry: browse all hearings in the next 14 days, and
   find hearings by subject. Free, since the data is fetched citywide anyway. (R37)

## Counts

160 candidate requirements surfaced; 134 MUST; **109 classified `missed-but-essential`** (not in the
original ask but load-bearing). 64 risks, 14 critical. 50 open questions. 5 decisions escalated to
the owner, recorded as §11 of the plan (A–G) rather than silently settled.

## Findings verified by hand before the exploration

Established by live HTTP in the parent session and fed to every agent as grounding, so no agent
re-derived them:

- `webapi.legistar.com/v1/nyc/…` → **HTTP 403 "Token is required"**. A free key exists but is
  human-mediated; v1 must not depend on it.
- `nyc.legistar.com/Calendar.aspx` parses cleanly and **includes future meetings** — the only way to
  answer "when is the next one", since the open dataset ends 2024-12-19.
- `MeetingDetail.aspx` carries per-item **Action** and **Result** columns; `HistoryDetail.aspx`
  ("Action details") carries a **Person Name / Vote** roll-call table plus Mover, Seconder and full
  action text; `PersonDetail.aspx` maps a stable `personId` to district and **party**.
- Meeting-level **attendance** rolls exist for both Stated and committee meetings (one Stated
  Meeting: Present 45 / Absent 6 of 51).
- **Floor dissent is rare**: 1 divided vote in 113 items at the sampled Stated Meeting, with the same
  nine members dissenting as a bloc. This is why the plan publishes `bloc_concentration` beside any
  dissent figure.
- Committee items record `Hearing Held by Committee` **and** `Laid Over by Committee` per meeting,
  making repeated lay-over a countable per-matter friction signal.
- Acquisition note: the same roll-call data sits in the **minutes PDFs** (`View.ashx?M=M&ID=…`), one
  fetch per meeting rather than ~115 per-item fetches. The per-item scrape remains a structured
  cross-check, not the acquisition path.
- `geosearch.planninglabs.nyc` works without a key but returns **no council district**, so
  address → district requires point-in-polygon against shipped geometry.
- All 51 `council.nyc.gov/district-N/` pages fetch 200 and are the **only** source for district
  office addresses.

## Corrections to the grounding brief

Two things given to the agents as fact were wrong; the plan records both:

- "Visible-text structure is **identical** across the 51 district pages" — false. `Office Hours` is
  absent on D35 and D51; there are three phone-label conventions and two email conventions;
  committees are absent for districts 3, 5, 9, 14, 25 and 26. Every field is independently optional.
- `wp-json` is not a substitute for the rendered page: it reports District 1's office as "101
  Lafayette St, 9th Floor" while the live page says "65 East Broadway".

## Added after the exploration

**Service levels (§6A).** The owner set a UX commitment — clicking a district or entering an address
populates in under one second — written as decomposed budgets because the two paths differ: district
selection is local-only (p95 ≤ 200 ms, no network on the critical path); address entry depends on a
geocoder we do not operate (total p95 ≤ 1 s, our own share ≤ 270 ms, external leg measured not
promised). Two consequent corrections to the plan: the compact 51-district index is now **inlined**
and answers the click, and `district/NN.json` is demoted to a prefetched below-the-fold detail
payload.
