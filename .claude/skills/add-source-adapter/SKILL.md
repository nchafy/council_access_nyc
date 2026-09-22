---
name: add-source-adapter
description: Add a new upstream data source (a scraped page, a Socrata dataset, a PDF, another city's portal) to Show Up NYC safely. Use when asked to pull in new data, add a dataset, scrape another page, support community boards or a new jurisdiction, or when a source's shape changes upstream. Covers the security boundary every adapter must respect and the floor/fixture obligations.
---

# Adding a source

Every source this project reads is somebody else's output, which means every
adapter is a security boundary and a reliability risk. The rules below are not
style preferences — each one exists because of a specific failure that already
happened here.

## Where it goes

```
src/showup/sources/<name>.py     one module per upstream shape
tests/unit/test_<name>.py        unit tests, fixture-driven
tests/fixtures/<name>/...        committed bytes, exactly as fetched
```

Adapters return **model objects**, never raw payloads. Nothing downstream of
`sources/` should ever see upstream markup.

## The five obligations

**1. Strip, don't trust.** Every text value goes through `text.strip_tags` before
it leaves the adapter. Never store upstream HTML as HTML.

```python
from ..text import strip_tags
committee = strip_tags(cell)          # not cell.strip()
```

Use `text.text_lines` when you need the page's visible line structure. Do **not**
split raw HTML on block tags and strip the fragments — that was a real bug: the
`<script>` open tag and its body land on different lines, the skip logic never
fires, and jQuery and CSS get parsed as visible text.

**2. Allowlist every URL.** Any href inherited from upstream goes through
`urls.safe_url` before it can be rendered. It returns `None` for anything not
https-on-an-allowlisted-host, and the renderer emits inert text for `None`.

```python
from ..urls import safe_url
detail = safe_url(href, base="https://nyc.legistar.com/")
```

Adding a host to `urls.ALLOWED_HOSTS` is a security decision. It also needs a
matching entry in `_headers` `connect-src` if the *browser* will contact it.

**3. Never guess a value.** A missing time stays `None`; a missing field is
recorded in `missing` and surfaced in the UI. "Deferred" must not become `00:00`.
An unrecognised venue becomes `offsite` carrying its raw label — inventing a City
Hall address for an off-site hearing sends someone to the wrong building.

**4. Give it a floor.** Add the source to `build.FLOORS`. Below the floor the
build raises `BuildError`, stops, and leaves the previous `site/` serving. A floor
is what turns a silent upstream redesign into a loud failure. Also assert a **body
invariant**, not just an HTTP status: several Legistar endpoints return HTTP 200
carrying an error body, so `parse_calendar` checks for `gridCalendar` and raises
`CalendarParseError` when it is absent.

**5. Commit a fixture, including a hostile one.** Fixtures are the bytes as
fetched, stored byte-exact (`tests/fixtures/** -text` in `.gitattributes`). Pick
the *pathological* cases, not the happy path — the existing district-page fixtures
are 1 (reference), 3 (no committees, source conflict), 35 and 51 (missing
`Office Hours`, non-standard suite format). At least one test must drive a hostile
string (`<script>`, a bare quote, an entity) through the adapter and assert it
renders inert.

Trim bulk from fixtures but keep the shape: the calendar fixture replaces
`__VIEWSTATE` with a marker, which shrinks it from 890 KB to 252 KB and documents
that we never POST it for pagination.

## When two sources disagree

They will. District 3 is the live case: `uvw5-9znb` records a term ending
2026-02-03 with no successor row, while `council.nyc.gov` already names the new
member. Resolve it **toward the reading that does not remove information from the
user**, and disclose the conflict in the page rather than silently picking a side.
Telling a district with a sitting member that its seat is vacant is worse than a
slightly stale name.

## Before you finish

```bash
make verify
```

Then check the district-3 screenshot: it is the page where degraded states show.

## Adding another jurisdiction

Don't, yet — and this is a deliberate constraint rather than an oversight. See
`docs/shared-core-notes.md`: the trigger for generalising has three conditions and
none is met. Keep the Legistar, Socrata and NYC names as they are; they mark where
the domain leaks in, and neutral names erase that signal. Log the observation in
`docs/OBSERVATIONS.md` instead.
