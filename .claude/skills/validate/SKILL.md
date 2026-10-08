---
name: validate
description: The complete validation loop for Show Up NYC — every gate, what each one proves, and the order to run them in. Use before any commit, and as the contract for a risky refactor (swapping the renderer, a parser, or the browser driver). Covers the hermetic gate, the four browser gates, the byte and latency budgets, and the baseline-diff protocol that makes a rewrite provable rather than hopeful. Use when asked to "validate", "run all the gates", "is this safe to merge", "prove this refactor is equivalent", or when adding a dependency.
---

# The validation loop

`verify-site` covers the everyday loop. This is the **whole** gate, plus the protocol for a
change big enough that "the tests pass" is not sufficient evidence.

## The one command, and what it does not cover

```bash
make verify     # build + lint + ~9,200 tests + 482 live-response checks
```

`make verify` deliberately excludes the four browser gates — together they are about two
minutes of real Chrome, and the fast gate has to stay fast to keep being used. So `make
verify` passing is **necessary and not sufficient**.

```bash
make gates      # axe, a11y, console, perf — the four browser gates
```

## Every gate, in the order to run them

Cheapest and most specific first, so a failure names itself before you spend two minutes.

| # | Command | Proves | Cost |
|---|---|---|---|
| 1 | `make lint` | ruff clean, formatted | seconds |
| 2 | `make test` | ~9,200 tests, **100% coverage floor** | ~110 s |
| 3 | `make build` | cached sources → `site/`, fails closed | ~10 s |
| 4 | `uv run python scripts/verify.py` | 482 assertions against live responses | ~15 s |
| 5 | `make perf` | 60 KB gzipped page budget; 3 s cold on throttled 3G | ~2 min |
| 6 | `make axe` | 0 WCAG 2.2 AA violations, all 115 pages | ~25 s |
| 7 | `make a11y` | 135 keyboard + accessibility-tree checks | ~40 s |
| 8 | `make console` | no console error or CSP violation | ~20 s |
| 9 | `make shot` | layout damage a human must see | ~20 s |

`make browser` runs 6–8 as one pytest run. Add `ALL=1` to `make axe` / `make console` for all
115 pages instead of one of each type.

**A change is validated when 1–8 pass and you have looked at 9.** Not before.

## What each gate catches that the others do not

Do not treat these as interchangeable — each has already caught something no other one would.

- **`scripts/verify.py`** asserts against a *running server with the real headers*. It caught a
  host allowlisted in one place and not another. The unit tests could not: they never serve.
- **`make console`** catches requests the source does not spell out. It is how the CSP bug was
  found — `connect-src` refused the site's own `/data/lookup.json`, nothing went red, and the
  feature degraded into a fallback that sent *more* data to a third party.
- **`make axe`** needs the *rendered* tree, not the HTML we emitted. It runs behind the real
  CSP, which is how a negative-control fixture was caught testing nothing: its contrast defect
  sat in a `<style>` block that `style-src 'self'` blocked.
- **`make a11y`** presses real `Tab` keys. Reading `tabindex` out of the markup proves nothing.
- **`make perf`** has an arithmetic half (byte budget, hermetic, in CI) and a measured half
  (throttled cold load). Only the first is enforceable on every commit.
- **`make shot`** is the only gate a human reads. An unstyled page passes every HTTP check.

## Never run two suites at once in one worktree

`COVERAGE_FILE` defaults to `.coverage` in the working directory, so concurrent pytest runs
overwrite each other's data. **Every test passes and the total is wrong** — measured at
100.00%, 93.16% and 94.52% across three runs of an identical command with six pytest processes
live. A false 100% is the dangerous direction: it passes genuinely uncovered code through a gate
this project treats as a hard floor.

`make test` sets a per-process `COVERAGE_FILE`. If you invoke pytest directly while anything
else might be running, do the same.

## Coverage is a floor, not evidence

100% line coverage is enforced (`--cov-fail-under=100`) and it is the *minimum*. It says every
line ran, not that any of them are right. The XSS boundary and anything rendering a date or a
deadline need tests that assert **behaviour under hostile input** — see the `fuzz-and-corpus`
skill and the hostile-content fixture in `tests/integration/test_build.py`.

If a gate is green and you cannot name what would have made it red, the gate is not doing
anything. Two real examples, both fixed by adding the missing negative:

- axe passed on the first run it was ever given. "Clean" and "nothing ran" look identical, so
  `tests/fixtures/a11y_broken/` and a floor on rules-exercised-per-page now exist.
- A skipping gate reports success. `make axe` exits 2 rather than skipping when Chrome is
  missing, and CI asserts Chrome exists as its own step.

## The baseline-diff protocol, for a rewrite

Use this when replacing *how* something is produced without intending to change *what* is
produced — swapping the renderer for a template engine, a hand-rolled parser for a library, the
browser driver. "The tests pass" is not enough, because the tests were written against the old
implementation and may encode its bugs.

1. **Capture a baseline before touching anything.**
   ```bash
   make build && cp -R site /tmp/baseline-site
   uv run python scripts/perf.py --weight-only > /tmp/baseline-weight.txt
   uv run python scripts/axe_check.py --all --json /tmp/baseline-axe.json
   ```
2. **Make the change.**
3. **Diff the output, not the code.**
   ```bash
   make build && diff -r /tmp/baseline-site site | head -50
   ```
4. **Byte-identical is the target.** Where it is not, every single diff must be explained in
   the commit message, one line each. An unexplained diff is an unreviewed change to what a
   reader sees.
5. **Re-run gates 1–8.** Then compare the byte budget and the axe report against the baseline
   files: no page heavier, no new violation, no rule that stopped being exercised.
6. **Commit the baseline evidence in the message**, not the files. Pages compared, diffs found,
   each one's reason.

Whitespace-only diffs still count. If the new renderer emits different indentation, say so and
say why it is acceptable — it moves the gzipped byte count, which is a gated number.

## Adding a dependency

`docs/dependencies.md` is the policy; open-source dependencies are allowed. The validation
obligations on top of the normal loop:

1. **Record it** in `docs/dependencies.md` — version, OSI licence, build-time vs browser, and
   one line on what it replaces.
2. **Check for install-time code execution.** A package that downloads or runs binaries on
   install is refused. This is why the browser gates run on `scripts/cdp.py` rather than
   Playwright. Its RFC 6455 framing is `websocket-client`'s — a library is welcome, a
   library that fetches and runs a browser build is not.
3. **A browser dependency is refused outright** — "zero third parties" is a CSP-enforced
   promise to readers, not a preference.
4. **Move the guard, do not drop it.** If the dependency takes over a safety-critical job, the
   test that guarded the old code must be replaced by one that guards the new arrangement, and
   the replacement goes in *before* the migration. Concretely: adopting Jinja2 means
   `autoescape=True` asserted on the environment and a CI grep failing on `|safe`, `Markup(`
   and `{% autoescape false %}` — the same shape as the existing `innerHTML` grep — because the
   risk inverts from "forgot to escape" to "opted out of escaping".
5. **Run gate 5.** A dependency that reaches `site/` moves the byte budget.

## When a gate fails

Read the failure before changing code. These gates are specific and they have been wrong about
the code and right about the test more than once — a headless browser wrapping focus to the top
looked like a focus trap on all nine page types, and the assertion was what needed fixing.

Never make a gate pass by loosening it. Thresholds live in `perf-budget.json` and the tags in
`scripts/axe_check.py`; changing one is a reviewable diff and needs a reason in the commit, not
a quiet edit.
