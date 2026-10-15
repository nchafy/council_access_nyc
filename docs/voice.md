# Voice

**State what the data says and where it came from. Do not tell the reader what to do, what to
think, or why they are here.** Owner's decision, 2026-10-07.

The reason is not style. We do not know why someone opened a district page. A reporter, a
tenant organiser, a landlord, a student and someone who just got a rezoning notice all need the
same facts and none of them need our advice. Directing them means guessing an intention, and a
guess about intention is the same class of error as a guess about a fact.

## The three classes, and what happens to each

**1. Direction — delete it.** Anything imperative, or any judgement about what matters.

| Was | Now |
|---|---|
| "Treat this as a hint, not a schedule, and confirm with the board before you travel." | "The City's dataset records this cadence. Boards publish their own schedules, and the two have been observed to differ." |
| "Most boards ask for an application and a current resume — contact the board office above." | "Most boards require an application and a current resume." |
| "often the right place to start" | *(deleted — that is advice)* |
| "The route most people do not know about" | *(deleted — that is a claim about the reader)* |

**2. Assumed relationship — make it neutral.** The reader did not tell us this is *their*
council member, and on a shareable URL they may well be looking at someone else's.

| Was | Now |
|---|---|
| "Your Council Member" | "Council Member" |
| "Your community boards" | "Community boards covering this district" |
| "Committees your member sits on" | "Committee assignments" |
| "These are the rooms where your representative has a seat — the hearings where someone accountable to you is on the dais." | *(deleted)* |
| "How to be heard" | "Testimony and attendance" |

**3. Fact, quote, or a note without which the data misleads — keep, but compress.** This is the
narrow exception, and it is not a licence to explain.

- Quoted source text stays quoted, with the subject moved off the reader: `You must "reside,
  work…"` becomes `Members must "reside, work…"`.
- A note survives only where its absence causes a misreading of the data on the page. The
  priority column repeats within a budget category; without one clause saying so, a reader
  concludes the board filed twenty-three number-one priorities. Earn it in a clause, not a
  paragraph.
- Refusals stay, as facts about the data rather than instructions: not "check with the board",
  but "no City dataset publishes this".

## The test

Read a sentence and ask: **is this in the data, or is it me?** If it is me, it needs to be
either a source note or deleted. "The register records X" passes. "X means you should Y" does
not.

A second test for length: if a sentence explains a word already on the page, cut it. The
information speaks for itself or it is not information.

## What this does not change

- **Provenance is not decoration.** Every figure keeps its source link, its denominator and its
  window. Removing prose must never remove a citation.
- **Refusals stay only where a value on the page would otherwise be misread** — see "Do not
  enumerate what is missing" below, which narrowed this on 2026-10-07. Refusing to *invent* a
  fact is absolute and always was; *listing* the facts we lack is padding and is now cut.
- **Procedural facts stay.** "In-person testimony requires no pre-registration" is a fact about
  a procedure, not advice about what to do with it.

## Headings name a thing, they do not ask a question

Owner, 2026-10-07: "The headings are assuming a question was asked too much."

A heading is a label on a section of data, not the question a reader is imagined to have
arrived with. Nominal, not interrogative, not instructional.

| Was | Now |
|---|---|
| What this board asked the City for | Fiscal Year Requests |
| When it meets | Meeting times |
| Council districts covering this board | Council districts |
| How to get involved with this board | Attending |
| How to be heard | Testimony and attendance |
| Two things nobody publishes | Time limits and registration |

The same applies to field labels inside a record: `Asked of` / `The board's words` /
`The reply, quoted` became `Requestee` / `Request` / `Response`. A field label should be the
name of the field, not a narration of how the value got there.

## Do not enumerate what is missing

Owner, 2026-10-07: "we shouldn't be outlining what is missing, rather just focusing on what is
there. If someone isn't looking for how long a board term lasts, why should we provide that we
don't supply it?"

A catalogue of absences is content nobody asked for, and it pads the page with our own
limitations. The "Things the City does not publish" section is gone for exactly that reason.

**The one narrow exception** is a field a reader will otherwise misread as present. These are
not absence catalogues; they are labels on a value that is sitting right there:

- The board office address renders directly above the meeting section. Silence reads as *that
  is the venue* — wrong on 8 of 8 boards checked. One line says it is the office.
- The per-speaker time limit and registration cut-off sit inside testimony procedure, where a
  reader is already looking. Silence reads as *there is no limit*.

The test: **would removing this sentence cause a reader to believe something false about a
value on this page?** If yes it stays, as a field note. If it would only leave them not knowing
a thing they never asked about, it goes.

## State facts, not judgements about facts

Owner, 2026-10-07, on the staleness notice: replace "the data is out of date" with "Data
fetched 7 October 2026, 11:41."

"Out of date" is our verdict. The fetch time is the fact, and the reader can judge it against
whatever they are doing. This also removes a thing the page could be wrong about — and the
measurement behind it is in `docs/refresh.md`, because a timestamp is only honest if something
refreshes.

## The policy covers data as well as templates

`src/showup/venues.py` renders inside every meeting card, five times per district page, and was
the last second-person and imperative copy on the site: "Bring photo ID… who can direct you",
"Enter through NYPD security… Tell the officers which hearing you are attending", "To speak,
register in advance". Rewritten to state each requirement — "Photo ID is required, and entry is
through security and metal detectors" — with every procedural fact kept. Copy in a Python
constant is still copy.

Both checks are now gated rather than re-measured by hand: `tests/unit/test_templates.py` and
`tests/unit/test_venues.py` fail on `\b(you|your|yours|yourself|you're)\b` in any shipped
template or venue string, and pin the sentences already cut so they cannot come back. Two
categories are deliberately out: form-control text (`Select a council district…`, `Go`, `Find`,
`Skip to content`) is an affordance rather than prose, and `assets/address.js`'s six runtime
status strings about the reader's own typed address have never been in scope.

## Provenance belongs on `/references/`, not in the paragraph

Dataset ids, denominators, windows, methods and our own measurement caveats go on the
references page. A page that shows a finding carries a short source link to it, not an inline
essay. Relocating provenance is fine; losing it is not. If brevity and a citation conflict,
the citation wins and the prose goes instead.
