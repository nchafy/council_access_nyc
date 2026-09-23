# Shared core notes

**What this is for:** orienting whoever picks up the idea of a shared core under these two
repos, with views as plugins, working against public data from any publisher. **When to read
it:** before any cross-repo work, and before proposing any shared package, interface, or
plugin mechanism.

**Nothing in this file is approved architecture.** There is no design here — no core API, no
plugin contract, no module layout — because the owner reserved that. The candidate seams in §5
are observations, not recommendations. Do not implement anything from this file. Each repo's
source of truth is unchanged: `council-access-project-outline.md` in council_access_nyc,
`isochrone-project-outline.md` in timemap_nyc.

Committed byte-identically to both repos, so either one cloned alone carries the whole picture.
Edit both copies or neither — nothing checks this, and nothing does. Throughout: **decided** means written in a CLAUDE.md or an outline; **candidate** means
observed but unsettled; **open** means no answer yet. Last verified 2026-09-21, against both
working trees.

## 1. The goal, and the thing nobody has stated yet

Owner, 2026-09-21:

> "in the future, we should be able to create a base core package that enables new views such
> as per-district information, subway views are then plug ins for this core. […] i also want
> this common framework to work with data from any public data entity, such as the federal gov
> (data.gov), boston data, international governments, etc."

and in the same message:

> "i don't want you to design this currently, but help me understand how i can implement
> steering/additional context to both projects such that when it is time to design the common
> interface, it is easy."

**What the core would be for has not been stated, and that is the largest gap in this file.**
No one has written down what user-visible outcome it produces, or what the duplication costs.
As of 2026-09-22 the duplication still costs nothing measurable, but for a different reason
than before: council_access now has ~3,000 lines of Python, and none of it was copied from
timemap. The two solved the same-shaped problem independently under different constraints
(timemap's ingest is stdlib-only with no network; council_access needed HTTP, scraping and
fail-closed caching), and the result is that nothing has been written twice yet. A design evaluated against no stated purpose gets evaluated
against nothing, and "views as plugins" then wins by default because it is the only concrete
phrase in the room. **Open. Only the owner can answer it — see §7.**

Status: **not designed, not scheduled, not approved.** Sections 4 and 6 are the reasons it may
never be.

## 2. The two repos today

**council_access_nyc** — `~/personal/council_access_nyc`, branch `mainline`, remote
`git@github.com:nchafy/council_access_nyc.git` (public, created 2026-09-21). **Phase 1 is
built and runs locally** as of 2026-09-22: ~3,000 lines of Python plus ~2,400 of tests, 100%
coverage enforced, 110 generated pages, seven fetchers, CI green. Seven
tracked files, zero lines of Python. `product-brief.md` is the entry point,
`council-access-project-outline.md` the engineering plan, `docs/phase-1-scope.md` what was
actually built; `docs/exploration-2026-09-21.md` is the research behind all three. A throwaway
Node spike is preserved on `spike/node-etl`.

Corrections to what this file said on 2026-09-21: the pipeline is no longer "specified, not
built", and the CI problem it noted (`uv sync --frozen` with no committed `pyproject.toml`) was
fixed the same day.

**timemap_nyc** — `git@github.com:nchafy/timemap_nyc.git`, default branch `master`, work on
`001d-ingest-pipeline`. This is the repo with running code: `src/timemap/places/` is 805 lines
across 12 modules with ~1,000 lines of tests. The pipeline is **not on the default branch** —
`git ls-tree -r --name-only master | grep '^src/'` returns only `src/timemap/__init__.py`.

Both counts above are the fastest-rotting facts here. Re-derive them rather than trusting them.

## 3. What they share, and what that is worth

**Read the caveat first, because it bounds everything else.** Part of the similarity was
instructed, not discovered: council_access `CLAUDE.md` says its toolchain "Mirrors
`~/personal/timemap_nyc`" and its TDD commit markers are "matching" it, and the outline
calibrates its estimates against timemap. Toolchain, commit convention and CLAUDE.md structure
therefore carry no evidentiary weight about the problem domain. What is being called
convergence is one repo's working code and another repo's prose written by the same author
after reading it — treat it as n=1 applied twice, not n=2.

What was not instructed, and does count: the stage shape
(`csv_source.py`/`geojson_source.py` → `normalize.py` → `writer.py` + `report.py` +
`errors.py`, with `tests/contract/`), and the habits of counting what could not be used instead
of dropping it, recording provenance in the artifact, committing byte-exact fixtures, and
refusing third-party JS. Run `ls src/timemap/places/` for the current shape; it cannot be stale.

The link was one-way until now: a case-insensitive grep for `council` across timemap returns
nothing. The pointer section in its CLAUDE.md is the first reference in that direction.

**Three words mean different things in the two repos.** This is the cheapest way to misread the
evidence, so it is recorded here rather than left to a textual survey:

- **contract test** — timemap validates *its own output* against JSON Schema
  (`tests/contract/test_output_contract.py`). council_access's twelve contract tests assert
  that *upstream* still returns the shape it parses, on a scheduled job that never gates a
  deploy. Two features, one word.
- **privacy guard** — timemap protects the *owner*: `tests/test_privacy_guard.py` asserts that
  fixtures contain none of his own list names (`"Food NYC"`, `"法拉盛"`, `"Massachoosits"`).
  council_access publishes everything and protects *third parties*. Same name, inverted subject.
- **provenance** — timemap carries per-record `source_files` plus file-level
  `tests/fixtures/PROVENANCE.md`, with no timestamp in any of its three artifacts.
  council_access specifies per-*field* `field_provenance{source_url, seen_at}` plus
  `manifest.json` with per-source `fetched_at` + `max_age` evaluated in the browser.

## 4. Where they diverge

All seven are **decided** in one repo or both. They matter more than §3.

1. **Dependencies.** timemap's `pyproject.toml` has `dependencies = []` with the reason in a
   comment: the ingest is deliberately stdlib-only, and geocoding is held out because it needs
   an HTTP client. council_access needs an HTTP client, `pdfplumber`, PyYAML and `mapshaper`.
2. **Serving.** council_access: "Static site, build-time ETL, no origin server. **Forced, not
   chosen**" — upstream sends no `Access-Control-Allow-Origin`. timemap: FastAPI plus OTP2 in
   Docker, on-demand computation. Anything a core needs at request time is out of scope for
   council_access by construction, and that constraint cannot be traded away.
3. **Privacy polarity.** See §3. A guard that does not parameterise *whose* privacy is silently
   wrong for one repo, and a passing guard protecting the wrong party is worse than none.
4. **Provenance granularity.** See §3. Per-field provenance is a large multiplier on timemap's
   record size with no recorded need there.
5. **What "contract test" means.** See §3.
6. **Data liveness.** timemap ingests one hand-exported private file. council_access ingests
   many live public sources that rot, several returning HTTP 200 carrying an error.
7. **Consumption mechanics.** Both repos now have public remotes, so a shared package is
   *mechanically* possible; nothing about that makes it advisable, and §6's trigger is unchanged.
   "Copy verbatim" remains the standing instruction. Default branches
   also differ (`mainline` vs `master`). This is the first mechanical fork any design hits —
   monorepo, submodule, path dependency, or copy — and the copy option is the one already in
   use, which means it has arguably been pre-decided by default rather than on purpose.

## 5. Candidate seams — unapproved observations

Not a module list and not a recommendation. Each item's reason for doubt is stated first,
because the doubt is the useful half.

- **Atomic byte-stable artifact write.** It is ~18 lines (`writer.py::_write_json` — temp file
  in the target directory then `os.replace`, sorted keys, trailing newline), so a package, a
  version and an import is a worse trade than copying it and logging the copy. council_access
  independently requires byte-reproducible artifacts.
- **Untrusted-bytes decoding.** `encoding.py` is 52 lines with no domain knowledge at all, but
  its exception inherits from `TakeoutError`, so extracting it drags a Google-named hierarchy
  along, and no municipal cp1252 payload has been seen yet.
- **Source adapter boundary.** Both timemap adapters are `(pathlib.Path) -> list[RawEntry]`
  with no declared protocol — but both read one benign local file, while council_access needs
  paging, credentials, per-host politeness and body invariants because status codes lie. An
  interface fitted to the existing two omits the whole hard half.
- **Drop accounting.** At least three concepts hide under one word. timemap's
  `places.unresolved.geojson` is a *published work queue* that is ~98% of records and healthy;
  council_access's quarantine is a *rejection log* whose expected value is zero; and
  council_access also needs document-level rejection, where a minutes PDF whose parsed names
  disagree with the printed tally is quarantined whole. Collapsing these is the most likely
  early error. `normalize.py` states the invariant it does hold: every input entry ends up in
  exactly one of the two output sets.
- **Freshness.** Both concluded silent staleness is the primary failure mode, but the consumers
  differ: council_access's is a browser banner that keeps an abandoned site honest, timemap's is
  a GTFS calendar window bounding which dates a built graph can answer. A browser can only
  relabel; a test can fail a build.
- **Views as plugins.** The seam the owner named has the weakest evidence in either repo.
  timemap's own plan says View 2 "is View 1 with a single band and a pin filter — same backend
  call, different presentation. Build them as one view with options." So today views look like
  parameters. Evidence will arrive free when View 3 is built; nothing needs doing early to get
  it. A view boundary that does not pay for itself inside one repo will not pay across two.

**One piece of external evidence worth keeping, because it points away from the stated
framing.** Legistar is a vendor, not a city: probed 2026-09-21 with no credentials,
`webapi.legistar.com/v1/boston/bodies` returns HTTP 200 and `.../v1/nyc/bodies` returns 403.
Same vendor, same schema, different tenant policy — which is the only reason council_access must
scrape HTML, and if NYC ever unblocks it an entire scraper becomes deletable. The axis of reuse
may be the vendor or the protocol rather than the jurisdiction. **Candidate, not settled.**

## 6. The trigger, and who evaluates it

All three clauses must hold. The counts live here; there is no separate tally file. Append a
dated line at the bottom whenever someone asks the question, even when the answer is obviously
no.

- **T1 — both pipelines are real.** `git ls-tree -r --name-only master | grep
  '^src/timemap/places/'` is non-empty, **and** council_access has committed ETL code that has
  produced a published artifact from a run.
- **T2 — the publisher variety is there.** At least four source adapters across the two repos
  against at least three publisher platforms differing in transport or error semantics — not
  three files of one format. **Met as of 2026-09-22.** council_access alone ships four
  adapters across three platforms whose *error semantics genuinely differ*: Granicus/Legistar
  ASP.NET (HTTP 200 carrying error bodies), WordPress HTML (plain, but every field
  independently optional), and Socrata (JSON, reports query errors as a 200 with an `error`
  key, and needs a stable `$order` or rows silently duplicate across pages). Google Takeout in
  timemap is a fourth: local files, no network, no auth.
- **T3 — the duplication is measured.** At least three components written twice, each naming a
  file in each repo, in the two `docs/OBSERVATIONS.md` logs. **T3 measures diligence, not the
  domain:** "no duplication exists" and "nobody logged it" produce identical results. Weight it
  accordingly.

**Nothing schedules this evaluation.** No cron, no CI step, no calendar. Adding one to two
personal repos would be noise. The accepted
consequence is that if nobody asks, nothing happens and the idea dies quietly, which is
preferred over a calendar keeping it alive.

**Abandon it** when council_access has shipped its public launch (M5) while timemap's pipeline
is still not on its default branch, and the two logs record fewer than three twice-written
components. On that reading: delete §1–§7 of this file from both repos, delete the sibling
section from both CLAUDE.md files, and **keep the logs** — those observations stay true
whatever happens to this idea.

Evaluations:

- 2026-09-21 — T1 no: timemap's pipeline is on `001d-ingest-pipeline`, and council_access has no
  ETL code. T2 no: 1 platform of 3. T3 no: 0 of 3. **Verdict: do not design.**
- 2026-09-22 — T1 **still no**, and the reason has moved: council_access now clears its half
  (committed ETL producing artifacts from a run, though local rather than published), but
  timemap's pipeline is *still* not on its default branch — `git ls-tree -r --name-only master
  | grep '^src/'` returns only `src/timemap/__init__.py`. T2 **now yes**: four adapters, three
  platforms with genuinely different error semantics (see above). T3 **still no, 0 of 3** —
  and this is the interesting one. council_access built its ETL from scratch rather than
  copying timemap's, because the constraints differed (network and fail-closed caching versus
  a single local file), so *nothing has been written twice*. Two things that look like
  duplication are recorded in `docs/OBSERVATIONS.md` as **misfits** instead: "privacy guard"
  and "contract test" each name materially different mechanisms in the two repos.
  **Verdict: do not design.** One clause moved, and the one that actually measures shared
  substance did not.

## 7. Questions only the owner can answer

Do not answer these by inference. There is no decision queue and no ADR stub for them; they
wait here until he answers, and then the answer belongs in the relevant CLAUDE.md.

1. **Is a per-district plugin view compatible with a decision already settled against it?**
   council_access `CLAUDE.md` settles that **the district is a filter, not the organising key**,
   and bans composite scores and cross-district choropleths on measured evidence (54.2x
   variation across equal-population districts; a 0.000 gap rendered as 100-vs-99). A core whose
   headline plugin is per-district information makes the banned framing easy. Those entries
   stand; this file is not an ADR reopening them. Separately, `council-access-project-outline.md`
   cuts "Other cities" as out of scope, and that outline is the declared source of truth — so
   whether "out of scope for v1 of this product" also means "out of scope for a shared core" is
   genuinely unresolved.
2. **What is the core for, and who is the second consumer?** §1. The evidence points away from
   "another city": `django-councilmatic` issue #284 records that after thirteen years the
   durable core was a data model and the views went downstream, and a local NYC org
   (`BetaNYC/nyc-council-mcp`) has already built a normalised NYC Council data layer — so the
   realistic second consumer may be another NYC view.
3. **Does council_access get a git remote?** §4.7. Until it does, no shared-package option is
   available at all.

## 8. Read these first

In the repos: `council-access-project-outline.md` §2 (decisions with their evidence) and §6A
(the decomposed latency budget) for the constraints a core would inherit; the module docstrings
under `src/timemap/places/` — start with `models.py`, `normalize.py`, `writer.py`, which carry
the argument — plus `tests/fixtures/PROVENANCE.md` and `scripts/README.md`, the owner's own
formats for recording provenance and measured findings.

Prior art, in reading order. Dates matter; these surfaces move.

1. **`datamade/django-councilmatic` issue #284** ("Should django-councilmatic contain _any_
   templates?", open since 2022-12-15) — the record that templating moved downstream into
   per-city code and never came back. The closest analogue to this ambition, thirteen years in.
2. **`datamade/councilmatic-starter-template`** — what they shipped instead: a scaffold that
   copies, not a framework that is imported.
3. **`openstates/openstates-scrapers`** — `scrapers/` versus `scrapers_next/`, where the new
   tree covers committees and people per state and leaves bills, votes and events behind.
   Abstractions land on low-variance entities and stall on high-variance ones.
4. **Councilmatic's DNS state** — verified 2026-09-21: `nyc.councilmatic.org` is NXDOMAIN while
   `chicago.councilmatic.org` still resolves.
5. **Datasette** — the price of publishing a plugin contract: ~45 hooks, and a 1.0 line in alpha
   since 2022-11-29 while 0.x stays stable. Read before choosing any plugin mechanism.
6. **Alaveteli themes** (mySociety) — states the cost plainly: the more a theme overrides, the
   harder upgrades get. Override surface area is the upgrade tax.
