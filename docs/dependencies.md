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
| websocket-client | 1.9.2 (`>=1.9.2`, pinned in `uv.lock`) | Apache-2.0 | dev | Replaces the 127-line hand-written RFC 6455 client inside `scripts/cdp.py` — frame headers, client masking, 16- and 64-bit lengths, continuation reassembly, ping/pong; the most error-prone code in the repo and the least specific to this project |
| axe-core | 4.13.0 | MPL-2.0 | dev, fetched | R39's accessibility gate; not committed, see `vendor` note in `scripts/fetch_axe.py` |

Neither runtime entry reaches a reader: both run at build time only, and `site/` is plain
pre-rendered HTML with no third-party bytes in it.

## The WebSocket library, and why it is not `websockets`

`websocket-client` landed 2026-09-30, replacing the hand-written RFC 6455 client in
`scripts/cdp.py`. It is a **dev** dependency: `scripts/` is tooling, nothing under
`src/showup/` imports it, and `showup build` was checked in a virtualenv where it is
absent.

Rule 5 was verified, not assumed. The published wheel is a single
`websocket_client-1.9.2-py3-none-any.whl` containing only `.py` files and a
`dist-info/`: no compiled extension, no `.data/scripts`, nothing that runs at install.
A wheel cannot execute code on install the way an sdist's `setup.py` can, and pip
prefers the wheel. `pip list` after install shows one new package and no binaries.

`websockets` was the obvious candidate and was rejected on the same rule read
strictly: it publishes 148 platform-specific wheels because its masking routine is a C
extension. Its `websockets.sync.client` would have suited `Session`'s synchronous
design, but a compiled artifact per platform is a bigger install-time surface than the
framing code it replaces. `websocket-client` is synchronous by design, so `Session`
needed no change at all.

Two properties of it are load-bearing and easy to lose in an upgrade:

- **No read ceiling.** Unlike several libraries, `websocket-client` caps nothing: it
  reads whatever the frame header declares, in 16 KB chunks. So the old
  `MAX_FRAME_BYTES = 256 MB` has nothing to configure — there is no limit to raise.
  The guard moved rather than disappearing: `tests/browser/test_cdp.py` sends 4 MB to
  the page and reads ~4.8 MB of multi-byte UTF-8 back, which is what would fail if a
  future version introduced a ~1 MB default. An `Accessibility.getFullAXTree` response
  runs to megabytes and `axe.min.js` goes in at ~567 KB, so that limit would show up
  only on the biggest pages: intermittent, page-dependent, and green in review.
- **`skip_utf8_validation=True`.** The library's own validator is a per-byte Python
  loop costing ~0.1 s per megabyte, ~800x the C `bytes.decode`. `recv_text` decodes
  strictly anyway, so invalid UTF-8 still raises; the validator is pure cost on an AX
  tree.

Masking did not regress. The library's fallback `_mask` uses the same
`int.from_bytes`/`to_bytes` big-integer XOR the hand-rolled code used to keep the
~567 KB axe payload out of a Python loop, so the performance note survived the swap
without being restated in our code.

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
