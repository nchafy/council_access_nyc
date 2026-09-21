# Show Up NYC — product brief

**What this is for:** agreeing on the product before anyone argues about how to build it.
**When to read it:** first, and instead of `council-access-project-outline.md` unless you are
implementing. The outline is the engineering plan — 57 numbered constraints, of which only 8
come from the product. This file is the 8.

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
| **J2** | What is being discussed, and does anyone disagree about it? | **Topics yes. Disagreement only as Council Members' recorded votes — never as public opinion.** |
| **J3** | How do I say something, and what is my deadline? | **Yes, fully — and this is the highest-value answer we have.** |
| **J4** | Who else cares about this, and who do I call? | **Partly.** We can route you to institutions today. Naming the groups that show up depends on an unproven spike. |

## 4. Product requirements

Ten. Each is a product promise, not an implementation. The outline's 57 constraints all exist
to deliver one of these; if a constraint cannot be traced to one, it should be cut.

| # | The product must | Why | From |
|---|---|---|---|
| **P1** | Show upcoming meetings with a real street address, date, time, and whether it is in person, hybrid, or remote — and never imply a date is confirmed when it can be deferred without notice. | J1. A wrong address or a stale time costs someone their trip. | you |
| **P2** | Show what each meeting is actually about, from its agenda — and say plainly when the agenda is not published yet. | J2. "Multiple meeting items" is not an answer. | you |
| **P3** | Tell the user what they can do and by when: that in-person testimony needs no pre-registration, how long they still have to file in writing, and when an interpreter or ASL request is due. | J3. This is the product's sharpest edge — it changes behaviour this week. | you |
| **P4** | Give the user a human to contact: their Council Member's office, their community board, and the hearings office. | J4. "Get in touch" means a phone number, not a table. | you |
| **P5** | Let the user arrive by typing an address, by clicking a district on a map, **or** by neither — browsing what is happening citywide. | Your two interactions, plus people with no fixed or safe address. | you + added |
| **P6** | Answer in under a second once the page is live. | Your SLA. | you |
| **P7** | Show the Council's own record where it exists — recorded votes and member attendance — labelled as what it is: how Council Members voted, not what the public thinks. | J2's honest half. | you + added |
| **P8** | Never mislead. Every date and number carries its source and when we fetched it. Where the City publishes nothing, say so and give the phone number instead of a guess. | The product is advice about deadlines. Being wrong is the worst outcome available. | added |
| **P9** | Be usable by the people most likely to need it: works on a cheap phone and a screen reader, and never leaks the user's home address. | Our users disproportionately include disabled people, people with limited English, and people with safety reasons to hide an address. | added |
| **P10** | Still be true in two years, or visibly say it is not. | A civic side project's normal death is going stale while looking authoritative. | added |

P1–P7 are yours. **P8, P9, P10 are the three additions worth arguing about** — each costs real
time. If you veto them, say so and the outline gets much smaller.

## 5. What the product refuses to do

These are product decisions, not technical ones, and they are the most likely thing you will
want to challenge.

- **No score for how important a topic is to a neighbourhood.** We cannot measure it. The best
  available input varies 54x across districts of equal population and *fell 58% during the
  eviction moratorium* — i.e. it drops when need peaks. It measures how well a council office
  logs cases, not what a neighbourhood needs.
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

## 7. The product tension you should resolve first

**You asked for a per-district information portal with quantified topic importance. The evidence
supports a citywide "what can I do this week" tool with the district as a filter.**

Three findings drove that, all in the outline with their evidence:

- Committee hearings are **citywide**. They are not held per district and belong to no district.
  A district page can tell you who represents you and what your board does; it cannot tell you
  "your district's hearings", because there are none.
- The genuinely local, human-reachable body is the **community board**, not the council district.
  Residents routinely conflate them, and the board is often the right venue.
- The data that would have made a district page rich — casework volume, discretionary funding —
  is the data we cut, for the reasons in §5.

So the map becomes a way in rather than the centre of the product. **That is a real reduction
against what you asked for, and it is your call, not mine.** If you want the district to be the
organising unit anyway, say so — it is buildable, it just cannot carry the analytics that would
have justified it.

## 8. Open product questions

Everything else in the outline's §11 is downstream of these.

1. **Is the reduction in §7 acceptable?** District as filter, not organising key.
2. **Which jobs are in v1?** J1 and J3 are fully supported and are ~4 weeks. J2 and J4's
   routing half add ~1.5 weeks. J4's measured half is unproven. Recommendation: J1 + J3 + J4
   routing at launch, J2 immediately after.
3. **Do P8, P9, P10 stay?** They are the three requirements you did not ask for and they carry
   most of the non-feature work.
4. **Whose name is on it, and what happens when you stop maintaining it?**

---

Engineering detail, evidence, and the 57 constraints: `council-access-project-outline.md`.
How the plan was produced, including what was rejected: `docs/exploration-2026-09-21.md`.
