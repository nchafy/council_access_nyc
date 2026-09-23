# Show Up NYC — product brief

**What this is for:** agreeing on the product before anyone argues about how to build it.
**When to read it:** first, and instead of `council-access-project-outline.md` unless you are
implementing. The outline is the engineering plan — 57 numbered constraints, of which only 8
come from the product. This file is the 8.

**Status 2026-09-22:** Phase 1 is built and runs locally (`make fetch && make serve`).
Requirements P1–P5 and P8–P10 are met, P6 is met as a budget but not yet gated in CI, P7 and
P11 are not built. The per-requirement state is in the §4 table.

Everything here is a claim you should accept or reject. If a line is wrong, the outline is
wrong downstream of it.

---

## 1. Purpose

**A New Yorker with a problem should be able to find the next real chance to be heard by their
city government, and know exactly what to do to take it — in under a minute.**

That is the whole product. Everything else is in service of it or should be cut.

The test of whether we built the right thing: someone arrives annoyed about something
specific — a landlord, a bus route, a school, a permit — and leaves with a **date, an address,
and one action they can take this week**. If they leave with a chart, we failed.

## 2. Who it is for

In priority order. The first one wins any conflict.

1. **A resident with a live grievance.** Not curious — affected. Short attention, on a phone,
   possibly at work. Needs to know if it is already too late.
2. **A first-time participant.** Does not know that hearings are open to the public, that you
   can walk in without registering, or that written testimony is a thing. Most of the product's
   value is here, because this is pure unlock.
3. **An organiser or community-board member.** Covers several districts, needs the schedule and
   the primary documents, will notice if we are wrong.
4. **A journalist or researcher.** Needs the source link under every claim. Cheap to serve if
   provenance is built in, and they are the people who catch our errors.

Explicitly **not** the priority: someone who wants a dashboard of civic health.

## 3. The job, in the user's words

> "Something is wrong. Is anyone in government dealing with it, when, where, and can I say
> something about it?"

Four sub-questions, which are the four you originally asked, restated as user outcomes:

| | The user wants to know | Can we answer it? |
|---|---|---|
| **J1** | When and where is a meeting I could actually attend, and how do I get in the room? | **Yes, fully.** |
| **J2** | What is being discussed, and does anyone disagree about it? | **Topics yes. Disagreement only as Council Members' recorded votes — never as public opinion.** *Built: the meeting's published topic and your member's committees. Not built: per-item detail and votes (M6).* |
| **J2b** | There is far too much in motion. Which are the **big** items right now? | **Yes** — as a shortlist of what the Council is demonstrably spending its time on, ordered by its own observable activity. Not as a claim about what matters to a neighbourhood. See §4 P11 and §7. *Built: the next five meetings, chronological, no ranking. The ranking is not built.* |
| **J3** | How do I say something, and what is my deadline? | **Yes, fully — and this is the highest-value answer we have.** |
| **J4** | Who else cares about this, and who do I call? | **Partly.** We can route you to institutions today. Naming the groups that show up depends on an unproven spike. *Built: the routing half — member office, community boards, hearings office. Not built: the measured half (M7/M8).* |

## 4. Product requirements

Eleven. Each is a product promise, not an implementation. The outline's 57 constraints all
exist to deliver one of these; if a constraint cannot be traced to one, it should be cut.
The tick marks are build state as of 2026-09-22, keyed below the table.

| # | The product must | Why | From |
|---|---|---|---|
| **P1 ✅** | Show upcoming meetings with a real street address, date, time, and whether it is in person, hybrid, or remote — and never imply a date is confirmed when it can be deferred without notice. | J1. A wrong address or a stale time costs someone their trip. | you |
| **P2 ⚠️** | Show what each meeting is actually about, from its agenda — and say plainly when the agenda is not published yet. | J2. "Multiple meeting items" is not an answer. | you |
| **P3 ✅** | Tell the user what they can do and by when: that in-person testimony needs no pre-registration, how long they still have to file in writing, and when an interpreter or ASL request is due. | J3. This is the product's sharpest edge — it changes behaviour this week. | you |
| **P4 ✅** | Give the user a human to contact: their Council Member's office, their community board, and the hearings office. | J4. "Get in touch" means a phone number, not a table. | you |
| **P5 ✅** | Let the user arrive by typing an address, by picking a district, **or** by neither — browsing every district and board. *The map itself is cut from Phase 1; the dropdown, link lists and address box all work.* | Your two interactions, plus people with no fixed or safe address. | you + added |
| **P6 ⚠️** | Answer in under a second once the page is live. | Your SLA. | you |
| **P7 ❌** | Show the Council's own record where it exists — recorded votes and member attendance — labelled as what it is: how Council Members voted, not what the public thinks. | J2's honest half. | you + added |
| **P8 ✅** | Never mislead. Every date and number carries its source and when we fetched it. Where the City publishes nothing, say so and give the phone number instead of a guess. | The product is advice about deadlines. Being wrong is the worst outcome available. | added |
| **P9 ⚠️** | Be usable by the people most likely to need it: works on a cheap phone and a screen reader, and never leaks the user's home address. **Cheap phone: met and gated** — 13.7 KB heaviest page, 906 ms cold p95 on throttled 3G with a 4× CPU throttle. **Screen reader: the accessibility tree is checked on every page; no human has listened yet** (`docs/accessibility-pass.md`). **Address: met, and it was not before 2026-09-23** — the CSP blocked the committed local index, so ZIPs, neighbourhood names and district numbers were reaching the geocoder instead of resolving offline. A network-level test now asserts they do not. | Our users disproportionately include disabled people, people with limited English, and people with safety reasons to hide an address. | added |
| **P10 ✅** | Still be true in two years, or visibly say it is not. | A civic side project's normal death is going stale while looking authoritative. | added |
| **P11 ❌** | **Shortlist the big items.** Cut "everything in motion" down to a readable few, ordered by what the Council itself is measurably doing — and make each one a doorway to reading further, not a verdict. | J2b. Too much is in play to follow. Triage is the product's second-sharpest edge after deadlines. | you |

P1–P7 and P11 are yours. **P8, P9, P10 are the three additions worth arguing about** — each
costs real time. If you veto them, say so and the outline gets much smaller.

### P11 in more detail, because it replaces something that was cut

The shortlist ranks **the institution's activity**, which is observable, and never **the
public's interest**, which is not. Signals available from the Council's own record, all
individually explainable to a reader:

- **It is on an upcoming agenda.** The strongest and simplest signal, and the only one that is
  also actionable — you can still show up.
- **How many separate hearings it has received**, and how recently.
- **Where it sits in the pipeline.** Introduced → heard → laid over → reported → voted →
  enacted. "Reported out of committee" means a floor vote is close; that is urgency, measured.
- **Whether it has been laid over repeatedly.** Persistence, and the honest proxy for friction.
- **Whether the recorded vote was divided**, with the members named.
- **How long it has been in play**, including re-introduction across sessions.
- **How many members sponsor it** — *candidate only*; the open dataset carries a single bare
  surname, so co-sponsor counts depend on Legistar pages that have not been verified yet.

Two hard constraints on how it is presented:

1. **Every item shows why it is on the list**, in words, next to it — "heard 3 times since
   June, reported out of committee last week". A rank with no visible reason is the thing that
   made the old score dishonest.
2. **v1 orders and explains; it does not score.** Your own framing — surface the item and the
   material to read further — is the right first step. A single 0-100 number is not needed to
   make a shortlist useful, and adding one re-imports every problem in §5. If a composite is
   ever wanted, it needs the sensitivity analysis the outline §5 describes, and it must still
   show its components.

## 5. What the product refuses to do

These are product decisions, not technical ones, and they are the most likely thing you will
want to challenge.

- **No score for how important a topic is to a neighbourhood.** We cannot measure it. The best
  available input varies 54x across districts of equal population and *fell 58% during the
  eviction moratorium* — i.e. it drops when need peaks. It measures how well a council office
  logs cases, not what a neighbourhood needs.
  **This does not forbid P11.** The line is between measuring *the Council's activity*, which is
  in its own published record, and inferring *residents' priorities*, which is not published
  anywhere. A shortlist headed "what the Council is working on" is the first. The same list
  headed "what matters in your district" is the second, and is banned. The wording is the
  product decision, not a caption.
- **No measure of public support or opposition.** No city dataset records who attended, who
  testified, or which side they took. Anything we showed would be invented.
- **No ranking districts against each other.** A shaded map becomes "my district is worse"
  regardless of the legend.
- **No contact details we had to infer.** We link the institution or we say nothing.
- **We do not submit anything on the user's behalf.** We tell them where the form is.

## 6. What success looks like

Stated so it can fail.

1. A first-time user can get from the front page to "here is a hearing, here is the address,
   here is what I can do" without reading anything twice.
2. Every procedural fact on the site is either sourced to an official page or explicitly marked
   as not published anywhere.
3. When the data goes stale, the site says so before a user acts on it.
4. It is still correct, or visibly self-identified as stale, twelve months after the last commit.

Not success: traffic, dashboards, or completeness of the archive.

## 7. The shortlist, and at what level it exists

**Resolved 2026-09-21.** The owner's reason for wanting an interest score was triage, not
neighbourhood measurement: *"there are many many topics in motion during the city council, and it
is difficult to understand all of them, so i want there to be a way where we can create a sort of
shortlist of what are the big topics."* That is P11, it is buildable, and §5's ban does not touch
it. The community-board point is accepted.

What remains is a level-of-detail question, because topics do not naturally live at the district
level. Three levels are supportable, and they nest:

1. **Per committee, and per session** — the native level. A topic *is* a thing a committee hears.
   This is where the shortlist is strongest and where all the signals in §4 P11 exist.
2. **Citywide right now** — "the big things in front of the Council this month", built by merging
   the committee shortlists over the upcoming window. This is the front page.
3. **Per district, via the member** — and this is the bridge that was missing. A district's
   topics are the topics **its own member is working on**: the committees they sit on (and chair),
   the bills they sponsor, and how they voted on divided questions. All of that is the Council's
   own record, attributable to a district through the person who holds the seat, with no casework
   data and no inference about residents. It is a real per-district answer to "what is being
   worked on for me".

So the district page is not thin after all — it is just built from the member's record rather than
from neighbourhood statistics. Two genuine exceptions where a topic really is geographic:
**Land Use items** (a rezoning happens at an address, so it can be placed in a district) and the
**community board** calendar, which is local by construction.

Still true, and unchanged: committee hearings themselves are citywide and open to anyone, so the
site must not imply a hearing "belongs" to a district. The map is a way in; the citywide calendar
is the front page.

**Assumption flagged:** "the big topics for a specific council" reads as ambiguous between *the
Council as a body*, *a session*, and *a council district*. The three levels above cover all three
readings, and level 1 is the base the other two derive from — so no scope decision is blocked on
disambiguating it. Correct me if you meant only one of them.

## 8. Open product questions

Everything else in the outline's §11 is downstream of these.

1. ~~Is the reduction in §7 acceptable?~~ **Resolved 2026-09-21.** §4 accepted; the shortlist is
   in as P11; community board accepted; the district page is built from the member's record.
2. ~~Which jobs are in v1?~~ **Resolved 2026-09-21 — barebones Phase 1**, specified in
   `docs/phase-1-scope.md`: one input (district dropdown or address), one page of facts and
   links, **no map, no analysis**. Delivers J1, J3 and J4's routing half. J2 and J2b follow in a
   later phase. ~10–13 days.
3. ~~Do P8, P9, P10 stay?~~ **Resolved 2026-09-21: yes, all three.** And **security is the top
   priority** — see `docs/phase-1-scope.md` §4, which treats injection through scraped upstream
   content as the primary threat, since the product has no accounts to attack.
4. **Whose name is on it, and what happens when you stop maintaining it?** Still open, and it
   blocks publishing rather than building — the repo is public, the site is not.
5. ~~How long is the shortlist?~~ **5 items.** In Phase 1 this is literally "the next 5
   meetings", chronological, which needs no analysis at all. Revisit the number when ranking
   arrives.
6. ~~Domain name and indexing at Phase 1.~~ **Resolved 2026-09-21: neither.** Phase 1 is local
   only. Still open for whenever publishing happens, together with question 4.

---

Engineering detail, evidence, and the 57 constraints: `council-access-project-outline.md`.
How the plan was produced, including what was rejected: `docs/exploration-2026-09-21.md`.
