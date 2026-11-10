# Dependency policy

**Open-source dependencies are allowed.** Owner's decision, 2026-09-30. This replaces the
earlier stdlib-only posture, which was never a licence objection — it was about attack
surface, and that is a cost to weigh, not a reason to refuse.

## The one distinction that still matters

| Class | Reaches the reader? | Policy |
|---|---|---|
| **Build-time** (Jinja, a PDF parser, a geo library) | No | **Allowed.** Meet the checklist below. |
| **Browser, served by a third party** (a CDN script, an analytics snippet, a hosted font) | Yes, and they see the request | **Refused.** |
| **Map tiles from a third party** | Yes — the host sees which area is viewed | **Allowed since 2026-10-22**, for `tiles.openfreemap.org` only, by the owner decision in `product-brief.md` §5. No other third-party fetch is. `esri-light-gray` is wired but not reachable: adding `server.arcgisonline.com` to the CSP is a second, separate decision, and the licensing of Esri's keyless endpoints for this use is unconfirmed. |
| **Browser, vendored and served from our origin** (MapLibre) | Yes, but nobody else sees it | **Allowed since 2026-10-21.** Checklist below, plus three extra rules. |

The promise to the reader is that **no third party sees their request**, enforced by the CSP
(`default-src 'none'`, `connect-src` limited to the geocoder). That is a privacy guarantee, not
a dependency preference. A library we vendor and serve ourselves does not break it; a CDN script
or a tile host does. The first two rows have never moved. The third was opened deliberately in
`product-brief.md` §5 for the map — which is still the way to move this line, rather than as a
side effect of adding a library.

### Three extra rules for a browser dependency

1. **Vendored, never hot-linked.** Bytes are fetched at build time, pinned by checksum, and
   served from our own origin. No `src` pointing anywhere else, ever.
2. **It must not need a CSP directive.** A library that only works once the policy is loosened
   is refused here, because the loosening is the real cost. MapLibre was measured against the
   unchanged policy before it was accepted.
3. **It must be load-gated.** R40 caps reader-facing weight. A browser dependency loads on
   demand, after first paint, only on the route that needs it.

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
| beautifulsoup4 | 4.15.0 (`>=4.15.0`, pinned in `uv.lock`) | MIT | runtime (build-time) | Replaces the two hand-written `html.parser` state machines in `text.py` and the `<tr>`/`<td>`/`href` regexes in `sources/calendar.py`; the code that reads untrusted third-party HTML is the least project-specific and most attacked in the repo |
| soupsieve | 2.10 | MIT | runtime (build-time) | beautifulsoup4's selector engine; transitive, pinned in `uv.lock` |
| typing-extensions | 4.16.0 | PSF-2.0 | runtime (build-time) | beautifulsoup4's typing backport; transitive, pinned in `uv.lock` |
| jinja2 | 3.1.6 (`>=3.1.6`, pinned in `uv.lock`) | BSD-3-Clause | build-time | Replaces the hand-written HTML-in-f-strings in `render.py` and its 75 manual `esc()` call sites; `autoescape=True` makes escaping the default instead of something each interpolation has to remember |
| markupsafe | 3.0.3 | BSD-3-Clause | build-time | Jinja2's escaping primitive; transitive, pinned in `uv.lock` |
| pytest | >=8 | MIT | dev | test runner |
| pytest-cov | >=5 | MIT | dev | the 100% coverage gate |
| ruff | >=0.6 | MIT | dev | lint + format |
| websocket-client | 1.9.2 (`>=1.9.2`, pinned in `uv.lock`) | Apache-2.0 | dev | Replaces the 127-line hand-written RFC 6455 client inside `scripts/cdp.py` — frame headers, client masking, 16- and 64-bit lengths, continuation reassembly, ping/pong; the most error-prone code in the repo and the least specific to this project |
| axe-core | 4.13.0 | MPL-2.0 | dev, fetched | R39's accessibility gate; not committed, see `vendor` note in `scripts/fetch_axe.py` |
| pypdf | 6.21.4 (`>=6.21.4`, pinned in `uv.lock`) | BSD-3-Clause | runtime (build-time) | Reads the schedule PDFs that 21 community boards publish instead of a feed or a page. Replaces nothing — without it those boards' meetings are simply absent. One `py3-none-any` wheel and **no required runtime dependency at all** on 3.12; see below for why it is not poppler and not pdfminer.six |
| maplibre-gl | 6.15.0 | BSD-3-Clause | **browser, vendored** | The M3 district map. Replaces hand-rolling pan, zoom, projection and hit-testing over 51 polygons in WebGL. 449 KB gzipped across three files, so it is loaded on demand and never on first paint. Pinned by tarball sha512 plus a sha256 per extracted file in `scripts/fetch_maplibre.py`; not committed. Published 2026-10-18, so rule 3 is comfortable. npm runs at no point, so the `prepare` script in its `package.json` never executes — rule 5 holds for the same reason it does for axe-core |

One entry reaches a reader — `maplibre-gl`, on the map route only, served from `site/vendor/`.
Every other entry runs at build time. `site/` still contains **no third-party bytes**: nothing
in it is fetched from anyone else's host at read time.

## The HTML parser, and why it is not selectolax or lxml

beautifulsoup4 landed 2026-09-30, over the **stdlib `html.parser` backend**, replacing the
`_TextExtractor` / `_LineExtractor` `HTMLParser` subclasses in `text.py` and the
`<tr>`/`<td>`/`href` regexes in `sources/calendar.py`. It is a **runtime** dependency: it
runs inside `showup build`, on every scraped page.

Rule 5 was checked, not assumed. Three `py3-none-any` wheels — beautifulsoup4, soupsieve,
typing-extensions — with no `.data/scripts`, no compiled extension, and nothing that runs at
install. `tests/unit/test_html_parsing.py` asserts the absence of any `.so`/`.pyd`/`.dylib`
under `bs4/` and `soupsieve/` rather than leaving it to a reviewer's memory.

The install-surface trade-off decided the backend, consistently with the `websockets`
rejection (148 platform wheels for a C masking routine):

- **selectolax** is the fastest option and publishes **63** platform-specific wheels; its
  parser is a Cython binding to modest-html.
- **lxml** publishes **175**, plus libxml2.
- **beautifulsoup4 + `html.parser`** publishes **one** wheel, and adds **no** parser binary
  at all: the tree builder is the standard library's, so the C code in the install surface is
  exactly the CPython we already run.

Speed was never the constraint here. `showup build` reads 51 district pages and one calendar
from a local cache; best-of-three wall clock went **1.03 s to 1.24 s** over the swap, against
a budget that has nothing to say about build time. Paying 63 or 175 platform wheels to win
back 0.2 s of a cached build would be backwards.

Three properties of this arrangement are load-bearing and easy to lose:

- **The backend is named, not discovered.** `BeautifulSoup(markup, "html.parser")` — if the
  feature string were omitted, bs4 would pick the "best" installed parser, so an `lxml` that
  arrived as somebody's transitive dependency would silently change how malformed markup
  resolves. `test_html_parsing.py` asserts the builder that actually ran *and* that no
  alternative backend is importable.
- **bs4's advisory warnings are suppressed at the one parse site.** `<?xml …?>` in untrusted
  input makes it emit `XMLParsedAsHTMLWarning`, and `filterwarnings = ["error"]` would turn
  that into a raised exception inside the XSS boundary, where "never raises" is a hard
  invariant. `parse_html` ignores `UnusualUsageWarning` (the shared base of the three
  "did you mean a URL / a filename / XML?" advisories) and nothing else.
- **A tag-free value never reaches the parser.** `strip_tags` short-circuits to
  `html.unescape` + `collapse` when the input contains no `<`, which is the path almost every
  Socrata field takes. It is also what keeps entity handling byte-identical: bs4's
  html.parser builder forces `convert_charrefs=False` and substitutes references itself, which
  reads `&lt` and `&#1;` differently from the standard library. Corpus cases pin both.

One behaviour genuinely changed, and it is a fix rather than a wash: `_HREF` matched an
`href`'s **characters**, so `&amp;GUID=` was stored verbatim and rendered as
`&amp;amp;GUID=`. Taking the href as a parsed attribute decodes it once, which is what the
ingest rule always said. 255 links on 51 district pages; both forms were checked live and
Legistar keys on `ID` alone, so no reader was ever sent somewhere wrong.

## The PDF reader, and why it is not poppler and not pdfminer.six

pypdf landed 2026-10-31 to read the schedule PDFs 15 boards publish, and six more boards
joined them on 2026-11-02. It is a **runtime** dependency: it runs inside `showup fetch`, on
documents written by 21 third parties.

The owner asked for "the one that is more mature code and reliable dependency". Those two
criteria point at different libraries, and the honest answer is that **poppler is the more
mature codebase and pypdf is the more reliable dependency here**:

- **poppler** (`pdftotext`, descended from Xpdf) is two decades old and packaged by every
  Linux distribution. It is also a **system binary**, installed out of band. A contributor
  without Homebrew poppler would get a build that silently produces 21 fewer boards'
  schedules — fail-open, which is the exact failure the ingest floors in
  `sources/board_meetings.py` exist to prevent. Rule 5 is about install-time execution, and
  a system binary does not break it; the reproducibility of the build is the objection.
- **pdfminer.six** is pure Python and gives the best layout boxes of the three, but requires
  `charset-normalizer` and **`cryptography`** — a compiled Rust extension, pulled in for a
  feature (encrypted PDFs) none of these documents use. That is a larger install surface
  than the thing it buys, and it is the same trade that rejected `websockets` and
  `selectolax`.
- **pypdf** publishes one `py3-none-any` wheel, built by flit, with `Root-Is-Purelib: true`,
  no `.so`/`.pyd`/`.dylib`, no `.data/scripts`, and — on 3.12 — **no required dependency at
  all** (`typing_extensions` is conditioned on `python_version < '3.11'`). It installs
  through `uv` like bs4 and jinja2 and needs nothing from the host.

Measured on Bronx CB7's October 2026 grid before choosing, and both candidates have a flaw
worth knowing:

- pypdf's `extraction_mode="layout"` **silently drops heading and footer text blocks**. On
  that document it dropped `OCTOBER 2026` — the only place the year appears, and so the most
  load-bearing token in the file. 4,762 characters of grid survived; 26 words of heading and
  footer vanished, with no error.
- `pdftotext -layout` keeps the heading but splits a superscript: `211 East 203rd Street`
  came out as `211 East 203 Street` with a bare `rd` on the next line. pypdf's layout mode
  keeps that address intact.

So `board_pdf.py` reads **both** pypdf modes and uses each for what it is good at: layout
mode for the Sunday-to-Saturday grid, where column position is the only thing that says
which day an entry belongs to, and plain mode for the month-and-year heading. Neither mode
alone is sufficient, which is why the extracted envelope carries both and
`tests/unit/test_board_pdf.py` pins the heading's absence from layout mode — if a future
pypdf starts including it, that test says so rather than the behaviour changing unobserved.

Extraction happens at **fetch** time, not build time, for one structural reason: the cache
in `sources/board_meetings.py` stores each board's `body` as a string, and a PDF is bytes.
Storing the extracted text means no PDF binary ever enters `data/`, the build stays offline,
and a fixture is a text file a reviewer can read.

## OCR, and why it is the first optional extra

Owner's instruction, 2026-11-02: install OCR. Two boards publish their agendas only as
scanned images — Bronx CB12 (58 PDFs) and Queens CB10 (65) — and pypdf extracts zero
characters from every one. Without OCR there is nothing to parse.

**It is an extra, not a runtime dependency.** `pyproject.toml` puts it under
`[project.optional-dependencies] ocr`, and `showup build` does not require it. That is not
squeamishness; it is the only honest way to accept it. Every OCR route breaks one of the
rules above, and this one breaks the install-surface rule hard:

| | beautifulsoup4 | pypdf | the `ocr` extra |
|---|---|---|---|
| Wheels | 1, `py3-none-any` | 1, `py3-none-any` | platform wheels for onnxruntime, PDFium and OpenCV |
| Required deps | 2 | **0** on 3.12 | onnxruntime, numpy, opencv-python |
| Bytes | ~100 KB | ~400 KB | tens of megabytes, plus ~15 MB of models |

The alternatives were weighed and are worse, not better:

- **`tesseract` / `pytesseract`** — a system binary plus a language model, which is exactly
  the fail-open problem that ruled out poppler for the text PDFs.
- **`ocrmypdf`** — tesseract *and* ghostscript.
- **A cloud OCR API** — a third party and a secret, which breaks rule 6 outright.

So the cost is paid where it falls. `board_kinds.BoardSourceKind.needs` exists for this: a
kind that cannot meet its capability fails **its own boards and no others**, which is the
same contract a dead third-party site already has. A contributor who has not installed the
extra builds 54 boards instead of 56 and every test still passes, because the fixtures hold
the text OCR returned rather than the images it read.

| Dependency | Version | Licence |
|---|---|---|
| pypdfium2 | 5.14.0 | BSD-3-Clause / Apache-2.0 (bundles Google's PDFium) |
| rapidocr-onnxruntime | 1.4.4 | Apache-2.0 |
| onnxruntime | 1.31.1 | MIT |
| numpy, opencv-python | transitive | BSD-3-Clause / Apache-2.0 |

Rasterising is why there are two libraries and not one: OCR reads pixels, and a PDF has to
be rendered before anything can look at it. pypdf cannot render, so pypdfium2 does it.

Two properties of the arrangement are load-bearing:

- **Only the machine that fetches needs it.** Extraction runs in `showup fetch` and the
  cache stores text, so a build parses what a fetch produced. This is the same reason the
  text PDFs are extracted at fetch time, and it is what keeps the extra optional in
  practice rather than only on paper.
- **The plausibility window is checked on the parsed date, never on the text.** A misread
  digit in a scan is silent. Filtering lines by the four-digit numbers in them was tried
  first and threw away the only line that mattered — Bronx CB12's notice reads "at 7:00
  P.M. in Town Hall 4101 White Plains Road", and `4101` is a street number.

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

## The basemap tile hosts, and who owes their terms now

Recorded here on 2026-11-09 because the file that carried it is being deleted. `_headers`
held this project's Content-Security-Policy, and the front end it protected has moved to the
`webxp` repository. An ETL serves nothing, so a response-header file here would be a policy
over no responses.

The three basemap types each name their own tile hosts, and two carry an obligation beyond
attribution:

| Basemap | Hosts | Term |
|---|---|---|
| Simple | `tiles.openfreemap.org` | Attribution. The owner decision of 2026-10-22, `product-brief.md` §5. |
| Satellite | `server.arcgisonline.com` | Esri's Light Gray Canvas, chosen 2026-10-26. A **commercial** service whose keyless endpoints nobody here has confirmed are licensed for this use. The owner chose it on 2026-11-04 having been told so. |
| Geography | `{a,b,c}.tile.opentopomap.org` | **CC-BY-SA**, and OpenTopoMap asks that its tiles not carry heavy traffic. Also the owner's choice of 2026-11-04. |

Two things follow for whoever now serves the map, and neither is this repository's to do:

- **That site will need a CSP, and `webxp` has none.** Not a live exposure today: that
  repository is public *source* with nothing deployed — no Pages, no host config, no CI —
  so there is no response for a header to ride on and nobody is fetching a tile. It becomes
  one the moment a static host is pointed at the tree. The policy these hosts belong in is
  `connect-src`: all three serve raster tiles, which MapLibre fetches, and `img-src`,
  `worker-src` and `blob:` were each measured unnecessary on 2026-10-22. The policy this
  project served, which covered one site with one map, was:

  ```
  default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self';
  connect-src 'self' https://geosearch.planninglabs.nyc https://tiles.openfreemap.org
    https://server.arcgisonline.com https://a.tile.opentopomap.org
    https://b.tile.opentopomap.org https://c.tile.opentopomap.org;
  form-action 'none'; base-uri 'none'; frame-ancestors 'none'
  ```

  It is **not** sufficient there. That desktop runs forty-odd programs whose network needs
  nobody here has read, so copying this verbatim would block them; it is a floor to extend,
  not a policy to adopt. The other headers it served — `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`, HSTS, `X-Frame-Options: DENY`,
  `Cross-Origin-Opener-Policy: same-origin`, and a `Permissions-Policy` denying geolocation,
  camera, microphone, payment and USB — carry over unchanged and depend on no app.

- **The heavy-traffic request is now a hosting question.** It was answerable while this was
  one static site behind one CDN. A public desktop with a map in it is a different traffic
  shape, and the OpenTopoMap term should be re-read against it rather than assumed to carry.
  The distinction worth keeping: the term is *recorded* upstream, but the assessment behind
  it was made under the old premise, and nothing says so. A term re-read under a changed
  premise is a different question from a term recorded once.

Both of the above are gated upstream rather than here — that repository now carries the
pre-deploy checklist, because it is the one that will serve.
