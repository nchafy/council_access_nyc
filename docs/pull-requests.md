# Pull requests

`mainline` is protected: no force-push, no direct push. Everything arrives by PR.

Most work here is authored by an agent and reviewed by the owner, so this is written for that
case. The reviewer's job is **not** to re-read every line — it is to check that the claims in
the description are true.

## Size

PR #1 on this repo carried 37 commits and 43 files. **That was too big**, and it is the example
not to copy: it began as one exit criterion and absorbed four dependency migrations, a 59-board
survey and two copy rewrites. Each was defensible; the aggregate was not reviewable in one pass.

Split when any of these is true:

- more than ~10 commits, or more than ~15 files
- it spans a feature *and* a refactor — ship the refactor first, with its equivalence proof
- a user-visible change rides along with a behaviour-neutral one
- the description needs more than one "Also:"

Stacked PRs are fine. A refactor that proves byte-identical output is the easiest review there
is; merge it, then stack the feature on top.

## The description

Not a changelog — the commits are the changelog. State:

1. **The claim**, in one line: what is now true that was not.
2. **The evidence**, as numbers: gates run, coverage, counts before → after.
3. **Bugs found**, if the work surfaced any. Three of this branch's most useful changes were
   defects found while doing something else.
4. **What is refused or deferred**, with the reason.
5. **Still open**, explicitly — including anything you could not verify.

If a claim in the description is not checkable from the repo, it does not belong in it.

## Reviewing: the loop

### 1. Read the description, then distrust it

**Re-derive the headline number yourself.** On this branch that caught three false claims that
had each been reported confidently:

| Claimed | Actually |
|---|---|
| "15 of 59 nyc.gov slugs 404" | 0 of 57 — the 404s came from *constructed* URLs, not the published list |
| "both URL forms return the same bytes" | the same URL twice returns different bytes; the page carries per-request tokens |
| "48 boards would gain a URL" | 3 — the join compared `int` keys against `str`, so every lookup silently returned `None` |

All three had plausible-looking evidence attached. The pattern: a measurement that answers a
different question than the one asked.

### 2. Run the gates yourself

```bash
make verify                                   # build + lint + tests + 391 live checks
make gates                                    # axe, keyboard, console, perf — NOT in make verify
```

Green is the floor. The question that matters: **what would have made this red?** If the answer
is "nothing", the gate is decoration. Two cases on this branch:

- axe passed on the first run it was ever given. "Clean" and "nothing ran" are indistinguishable
  without a negative control, so `tests/fixtures/a11y_broken/` and a rules-exercised floor exist.
- A gate that *skips* reports success. `make axe` exits 2 rather than skipping when Chrome is
  missing, and CI asserts Chrome exists as its own step.

### 3. Check the diff for what is *not* there

- Did a threshold move? `perf-budget.json`, the axe tag list, `--cov-fail-under`. A loosened
  threshold is a change to a promise and needs its own commit and reason.
- Did an assertion get weakened rather than updated? Updating a literal to new copy is correct;
  replacing it with a shorter substring is not.
- Did a corpus expectation change? `git diff --numstat -- tests/corpus/` should show **additions
  with zero deletions**. An edited expected value means parsing behaviour changed.
- Did provenance survive? A copy change must not delete a source link, denominator or window.

### 4. For a refactor, demand the equivalence proof

`.claude/skills/validate/SKILL.md` carries the baseline-diff protocol. The deliverable is a
diff of the **built output**, not of the code, with every non-clock difference explained one line
each. Byte-identical is the target; whitespace still counts, because it moves a gated number.

Do not accept "all tests pass" as the proof. The tests were written against the old
implementation and may encode its bugs.

### 5. For a dependency, check the policy

`docs/dependencies.md`: OSI licence recorded, pinned by lockfile, maintained, justified in a
line, **no install-time code execution**, and **no browser dependency**. Verify the install
surface rather than taking it on trust — this branch rejected `websockets` (148 platform wheels
for a C extension) and `selectolax` (63) on exactly that check.

### 6. Read it as a reader

`make serve`, then open `/district/3/` — the deliberate degraded-state page — and `/board/302/`.
`docs/voice.md` is binding on every user-facing string: no imperatives, no second person, no
advice, no catalogue of what the City does not publish. A gate cannot check tone.

## Merging

- Squash only if the commits were noise. If each one carries a claim and its evidence, keep
  them — the history is the reasoning.
- CI must be green, including the `gates` job.
- An open question in the description is a blocker, not a footnote. The owner decides it before
  merge, or the PR says explicitly that it ships unresolved.
