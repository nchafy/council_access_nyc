---
name: fuzz-and-corpus
description: Work with Show Up NYC's test corpus and fuzzer, and hold the 100% coverage floor. Use when a fuzz test fails, when adding or changing an input-parsing function, when coverage drops below 100%, when deciding whether a pragma is justified, or when asked to add test cases, fuzz something, or grow the corpus.
---

# The corpus and the fuzzer

Two artifacts with different jobs:

- **`tests/corpus/*.jsonl`** — the durable record. One line per case:
  `{"in": ..., "out": ..., "note": "why this case exists"}`. Run by
  `tests/test_corpus.py`, one parameterised test per case.
- **`tests/test_fuzz.py`** — the discovery mechanism. Deterministic mutations,
  seeded from the corpus, asserting **invariants** rather than exact values.

The corpus is what survives; the fuzzer is how it grows.

## When a fuzz test fails

It means one of two things, and telling them apart is the whole job:

**1. The code is wrong.** Fix it, then **add the failing input to the corpus** with
its now-correct expected output and a note starting `FOUND BY FUZZER:`. That turns a
one-off discovery into a permanent regression test. Committing the fix without the
corpus entry throws away the find.

**2. The invariant is wrong.** Also common, and not a lesser outcome. Two real
examples now documented in `test_fuzz.py`:

- *"`strip_tags` never emits an openable tag"* — false. `&#60;script&#62;` decodes,
  correctly and exactly once, to the characters `<script>`, because that is what the
  source literally said. Stripping is not the defence; **escaping** is. The invariant
  was moved to where the guarantee actually holds: `esc(strip_tags(x))` is inert.
- *"`strip_tags` is idempotent"* — false. `"Defer&#x3C;red"` strips to `"Defer<red"`,
  and stripping *that* gives `"Defer"`, because the decoded `<red` reads as an
  unterminated tag on the second pass. The discipline is "apply it exactly once, to
  raw upstream text" (audited true of every call site), and the asserted property is
  the safe direction: a second pass can only remove text, never add markup.

When you correct an invariant, say in the test *why the old one was wrong*. A test
that silently loosens is indistinguishable from a test that was weakened to go green.

## Adding a parser

Every input-parsing function needs both:

1. A corpus file, added to `EXPECTED_FILES` in `tests/test_corpus.py` with a runner.
   Hygiene tests enforce that every file has a runner, every case has a note, no
   input is duplicated, and no two notes collide (notes become test ids).
2. Invariants in `test_fuzz.py`. Ask what must be true for **every** input, however
   malformed — never raises, output is inert once escaped, output is `None` or
   well-formed, an approximation always errs in the safe direction.

Seed the corpus from the pathological inputs you already know: the real ones from
the data, not invented ones. `&#60;`, `<scr<script>ipt>`, en dashes, `N. Y.`,
truncation mid-attribute, `Deferred` in a time column, accented surnames.

## Invariants worth copying

- **Never raises** on any input. Upstream is untrusted and truncation is normal.
- **Inert after escaping** — `not MARKUP.search(esc(result))`. The real XSS property.
- **`None` or valid** — a parser returns a correct value or nothing, never a guess.
  `parse_us_date("02/31/2026")` must be `None`, not a rollover to 3 March.
- **Approximations err safely.** `written_safe_until` with no start time must move
  the deadline *earlier*, never later: earlier tells someone to hurry, later tells
  them they have time they do not have.
- **Lossless where it claims to be.** `_compose_address` may reorder, but every
  token must survive — losing half an address sends someone to the wrong building.

## Determinism

`SEED` is fixed. Do not make it time- or random-based: a fuzzer that goes red at
random trains people to re-run until green, which is worse than no fuzzer. To search
harder, raise `ITERATIONS` or add to `FRAGMENTS`, then commit anything it finds.

## The 100% coverage floor

`--cov-fail-under=100`. The build fails below it. Three legitimate responses when
new code drops coverage, in order of preference:

1. **Write the test.** Usually right; the branch is reachable from real data.
2. **Delete the code.** If nothing reaches it, it is dead. Four things were removed
   this way rather than tested: `unescape_once`, `Meeting.is_past`,
   `urls.is_internal`, and a `Paths` dataclass. A dead branch inside a live function
   counts too — `safe_url` had a `resolved is None` guard that `absolutize` could
   never trigger.
3. **Restructure so the branch cannot exist.** `cli.main` ended with an unreachable
   `return 2` for an unknown subcommand; a dispatch table removed it *and* made a
   missing handler raise loudly instead of returning a silent exit code. Better than
   either testing or pragma-ing it.

`# pragma: no cover` is the last resort and **needs a reason on the same line**.
There is currently exactly one in `src/` — the `if __name__ == "__main__"` entry
point. If you are adding a second, check options 1–3 first.

Coverage is necessary, not sufficient. 100% with weak assertions is worse than 90%
with strong ones, because it reads as safety. The XSS boundary (`text.py`, `urls.py`)
and anything rendering a date or deadline need tests that assert behaviour under
hostile input, not just line execution.

## Running it

```bash
uv run pytest tests/test_corpus.py -q     # the corpus, fast
uv run pytest tests/test_fuzz.py -q       # ~8,500 generated cases, a few seconds
make test                                 # everything, with the 100% gate
```
