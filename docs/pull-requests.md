# Pull requests

`mainline` is protected. Everything arrives by PR. Most work here is agent-authored and
owner-reviewed, so the reviewer's job is not to re-read every line — it is to check whether the
claims in the description are true.

## Size

PR #1 carried 37 commits and 43 files. **That is the example not to copy**: it began as one exit
criterion and absorbed four dependency migrations, a 59-board survey and two copy rewrites.

Split when any of these holds: more than ~10 commits or ~15 files · it spans a feature *and* a
refactor · a user-visible change rides along with a behaviour-neutral one · the description needs
a second "Also:".

Stack instead. A refactor that proves byte-identical output is the easiest review there is.

## The description

The commits are the changelog. State the claim in one line, the evidence as numbers, any bug the
work surfaced, what is refused or deferred, and what is still open — including what you could not
verify. A claim that is not checkable from the repo does not belong in it.

## Reviewing

### 1. Distrust the description

**Re-derive the headline number.** This caught three false claims on this branch, each with
plausible evidence attached:

| Claimed | Actually |
|---|---|
| "15 of 59 nyc.gov slugs 404" | 0 of 57 — the 404s came from *constructed* URLs, not the published list |
| "both URL forms return the same bytes" | the same URL twice differs; the page carries per-request tokens |
| "48 boards would gain a URL" | 3 — the join compared `int` keys against `str`, so every lookup returned `None` |

Same shape each time: **a measurement answering a different question than the one asked.**

### 2. Run the gates

```bash
make verify     # build + lint + tests + 391 live checks
make gates      # axe, keyboard, console, perf — not included in make verify
```

Green is the floor. The question is **what would have made this red?** If nothing, the gate is
decoration — axe passed on the first run it was ever given, which is indistinguishable from
nothing running, hence `tests/fixtures/a11y_broken/` and a rules-exercised floor. A gate that
*skips* also reports success, hence `make axe` exiting 2 when Chrome is absent.

### 3. Check what is not in the diff

- A moved threshold — `perf-budget.json`, the axe tag list, `--cov-fail-under`. Its own commit,
  with a reason.
- An assertion weakened rather than updated. Repointing a literal at new copy is correct;
  shortening it to a substring is not.
- An edited corpus expectation. `git diff --numstat -- tests/corpus/` must show additions with
  **zero deletions** — an edited expected value means parsing behaviour changed.
- A deleted citation. Copy changes must not drop a source link, denominator or window.

### 4. Refactors: demand the equivalence proof

A diff of the **built output**, not the code, with every non-clock difference explained one line
each (`.claude/skills/validate/SKILL.md`). Byte-identical is the target; whitespace counts,
because it moves a gated number. "All tests pass" is not the proof — they were written against
the old implementation and may encode its bugs.

### 5. Dependencies: check the policy

`docs/dependencies.md`. Verify the install surface rather than trusting it: this branch rejected
`websockets` (148 platform wheels for a C extension) and `selectolax` (63) on that check alone.

### 6. Read it as a reader

`make serve`, then `/district/3/` — the degraded-state page — and `/board/302/`. `docs/voice.md`
is binding on every user-facing string. No gate can check tone.

## Merging

Squash only if the commits were noise; if each carries a claim and its evidence, the history *is*
the reasoning. CI green including `gates`. An open question in the description is a blocker — the
owner resolves it, or the PR says it ships unresolved.
