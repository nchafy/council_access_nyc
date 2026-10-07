# Commits

Measured on the `feat/m5-a11y-perf` branch, 37 commits: **median 3 files and 128 changed
lines**, max 28 files and 2,427 lines. The median is the target. The max was a vendored
third-party file and should not recur.

## Size

**One commit, one claim.** If the message needs "and", it is two commits.

| Rule | Why |
|---|---|
| ≤ 5 files, ≤ ~300 lines | past that, a reviewer reads the message instead of the diff |
| Generated or vendored bytes commit alone | a 567 KB blob buries the 40 lines next to it |
| A rename or a mechanical sweep commits alone | so the real change is reviewable |
| Docs that only correct a count commit alone | cheap, and keeps feature diffs clean |

**Commit the guard before the thing it guards.** `tests/unit/test_template_safety.py` landed
before Jinja2, and `tests/browser/test_cdp.py`'s large-frame test landed before the WebSocket
swap. Both pass against the old code, which is the point: a guard written afterwards is a
description of what you built, not a constraint on it.

**A correction gets its own commit.** Four claims were wrong on this branch — a slug-404 figure,
a "same bytes" comparison, a tribe-field verdict, a self-contradicting policy. Each was fixed in
its own commit naming the error. Amending history would have hidden the thing most worth reading.

## Message

Subject: `type(scope): imperative summary` — conventional commits, ≤ 72 chars. Types in use
here: `feat` `fix` `test` `refactor` `docs` `chore` `ci` `copy`.

TDD markers, matching `~/personal/timemap_nyc`: `test: … (RED)` then `feat(scope): … (GREEN)`.

**The body is where the reasoning lives, and it is not optional.** This repo strips comments
from code on purpose — the "why" has to be somewhere, and that somewhere is the commit. 1,099
body lines across 37 commits is the actual ratio, and it is not too many.

A body states, in whatever order serves the change:

1. **What was wrong**, concretely — the measurement, not the adjective.
2. **What changed**, and what you deliberately did *not* change.
3. **The evidence**: which gates ran, which numbers moved, before → after.
4. **What you refused**, and why. A refusal is a decision and it needs a record.
5. **What you could not verify.** Every report on this branch that named its gaps was more
   useful than one that did not.

Write for whoever reopens this in two years, not for the reviewer this week.

### Body anti-patterns

- "Minor fixes", "cleanup", "address feedback" — names no claim, so nothing can be checked.
- Restating the diff in prose. The diff is in the diff.
- An adjective where a number belongs. "Much faster" is unreviewable; "869 ms p95 against a
  3,000 ms threshold" is.
- Claiming a gate ran when it did not. If you skipped the browser gates, say so.

## Requirements before committing

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest -m "not upstream and not browser" -q      # 100% coverage enforced
```

Touched the renderer, assets, headers or a source? Add:

```bash
make build && uv run python scripts/verify.py           # live-response checks
```

Touched markup, copy or anything a reader sees? Add `make gates` — and read
`.claude/skills/validate/SKILL.md` first, because `make verify` passing is **necessary and not
sufficient**: it excludes the four browser gates.

**Never commit:** fetched upstream payloads (`etl/raw/`), build output (`site/`), a secret, or a
loosened threshold. Thresholds live in `perf-budget.json`; changing one is its own commit with a
reason.
