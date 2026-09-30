# Dependency policy

**Open-source dependencies are allowed.** Owner's decision, 2026-09-30. This replaces the
earlier stdlib-only posture, which was never a licence objection — it was about attack
surface, and that is a cost to weigh, not a reason to refuse.

## The one distinction that still matters

| Class | Reaches the reader? | Policy |
|---|---|---|
| **Build-time** (Jinja, a PDF parser, a geo library) | No | **Allowed.** Meet the checklist below. |
| **Browser** (a framework, an analytics snippet, a hosted font, a CDN script) | Yes | **Still refused.** |

Browser dependencies stay out because "zero third parties" is a promise made to readers and
enforced by the CSP (`default-src 'none'`, `connect-src` limited to the geocoder). It is a
privacy guarantee, not a dependency preference. A build-time library never touches a reader;
a browser one puts a third party between us and them. If you want to change that promise,
change it deliberately in `product-brief.md` — not as a side effect of adding a library.

## Checklist for adding one

1. **OSI-approved licence**, recorded in this file with the version.
2. **Pinned by lockfile** (`uv.lock` / `package-lock.json`), with hashes.
3. **Maintained** — a release within about a year, and a security history you have looked at.
4. **Justified in one line**: what it replaces, and why hand-rolling is worse.
5. **No install-time code execution** — no postinstall scripts, no downloading binaries on
   install. This is the specific reason Playwright was refused for the browser gates: it
   fetches and executes its own browser build. `scripts/cdp.py` exists because of that rule,
   not because dependencies were banned.
6. **CI still needs no secrets.** §4.5 holds: nothing in the build should be worth
   exfiltrating from a pull request.

## Current dependencies

| Dependency | Version | Licence | Class | Why |
|---|---|---|---|---|
| pytest | >=8 | MIT | dev | test runner |
| pytest-cov | >=5 | MIT | dev | the 100% coverage gate |
| ruff | >=0.6 | MIT | dev | lint + format |
| axe-core | 4.13.0 | MPL-2.0 | dev, fetched | R39's accessibility gate; not committed, see `vendor` note in `scripts/fetch_axe.py` |

Runtime: none yet. That is now a fact about today, not a rule.

## If you add a template engine

Jinja2 is the expected first addition, and it **improves** the security posture rather than
weakening it — `autoescape=True` escapes every interpolation by default, where the current
hand-written `esc()` calls can be forgotten. The risk inverts: it becomes the opt-outs.

So the gate changes shape rather than disappearing. Require:

- `autoescape=True`, asserted by a test on the environment.
- **No `|safe`, no `Markup()`, no `{% autoescape false %}`** — a CI grep fails the build on
  those three, exactly as one already fails on `innerHTML` and `document.write`.
- The hostile-content fixture (`tests/integration/test_build.py`) keeps passing unchanged. It
  is the end-to-end proof that scraped text cannot become markup, and it should not need
  editing to accommodate a rendering change.
