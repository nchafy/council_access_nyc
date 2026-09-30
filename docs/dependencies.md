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
| jinja2 | 3.1.6 (`>=3.1.6`, pinned in `uv.lock`) | BSD-3-Clause | build-time | Replaces the hand-written HTML-in-f-strings in `render.py` and its 75 manual `esc()` call sites; `autoescape=True` makes escaping the default instead of something each interpolation has to remember |
| markupsafe | 3.0.3 | BSD-3-Clause | build-time | Jinja2's escaping primitive; transitive, pinned in `uv.lock` |
| pytest | >=8 | MIT | dev | test runner |
| pytest-cov | >=5 | MIT | dev | the 100% coverage gate |
| ruff | >=0.6 | MIT | dev | lint + format |
| axe-core | 4.13.0 | MPL-2.0 | dev, fetched | R39's accessibility gate; not committed, see `vendor` note in `scripts/fetch_axe.py` |

Neither runtime entry reaches a reader: both run at build time only, and `site/` is plain
pre-rendered HTML with no third-party bytes in it.

## The template engine, and the guard that came with it

Jinja2 landed 2026-09-30 and **improves** the security posture rather than weakening it —
`autoescape=True` escapes every interpolation, where a hand-written `esc()` call can be
forgotten. The risk inverts: it becomes the opt-outs. So the gate changed shape rather than
disappearing, and all three parts are live:

- `autoescape=True` and `undefined=StrictUndefined` on the one environment in
  `src/showup/templates.py`, asserted by `tests/unit/test_templates.py` and
  `tests/unit/test_template_safety.py`.
- **No `|safe`, no `Markup()`, no `{% autoescape false %}`** — `test_template_safety.py`
  greps every `.py`, `.html`, `.jinja` and `.j2` file under `src/showup/` and fails the
  build on any of them, exactly as one already fails on `innerHTML` and `document.write`.
  Composition uses `{% extends %}`, `{% import %}` and macros, none of which needs an
  opt-out, so wanting one is a sign the template is being handed pre-rendered HTML.
- The hostile-content fixture (`tests/integration/test_build.py`) still passes **unchanged**.
  It is the end-to-end proof that scraped text cannot become markup, and it did not need
  editing to accommodate the new renderer.

One compatibility detail, in `templates.py`: MarkupSafe spells the two quote entities
`&#39;` and `&#34;` where `text.esc` spells them `&#x27;` and `&quot;`. Both are inert, and
keeping `esc`'s spelling is what made the migration byte-identical over all 114 pages —
which is the only way a renderer swap can be reviewed as changing nothing.
