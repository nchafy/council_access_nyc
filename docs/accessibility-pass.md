# The accessibility pass

**A real screen-reader pass has never been run.** It is the one open Phase 1 item (§4).

Run this before any release, and after any change to `render.py`, `site.css`, `site.js` or
`address.js`. R39 requires a documented keyboard-only and screen-reader pass per release.

## 1. The automated gates

All four run in CI on every commit.

| Gate | Command | What it proves |
|---|---|---|
| axe, WCAG 2.2 AA | `make axe` | 0 violations, all 114 pre-rendered pages |
| Keyboard + accessibility tree | `make a11y` | 122 checks over 9 page types, 0 failures |
| Console and CSP | `make console` | 0 complaints — no page logs an error or trips its own policy |
| Weight and cold load | `make perf` | 13.9 KB heaviest page vs 60 KB; 906 ms p95 vs 3000 ms |

`make a11y` presses real `Tab` keys in a real browser and reads Chrome's accessibility tree: skip
link, focus into `<main>`, DOM order, reachability, ≥2px ring, `Shift+Tab`; landmarks, accessible
names, one h1, no skipped heading levels. It also runs the front page with script execution disabled.

axe covers roughly a third to a half of WCAG issues (Deque's own figure). Everything in §3 is outside
that. A green build is the floor, not the pass.

## 2. Before a manual pass

```bash
make fetch     # only if etl/raw/ is empty; ~9 min
make verify    # must be green first
make axe       # expect 0 violations
make a11y      # expect 0 failures
make console   # expect 0 complaints
make perf      # both budgets
make serve     # then work against http://127.0.0.1:8000
```

Use `make serve`, never `python -m http.server`: the pass must run behind the real
`Content-Security-Policy`, which has already broken a feature silently once (§5).

## 3. The manual pass

Nine steps. Record each in §4.

### 3.1 Keyboard only, no mouse

On `/`, `/district/3/` and `/board/302/`, mouse unplugged:

1. Tab from the top. Is the ring visible *against the page* at every stop, not just in the computed
   style?
2. Operate the district dropdown by keyboard alone (`Alt+Down` or arrows); the page navigates on
   change.
3. Enter `11217` in the address box and submit with `Enter`. That ZIP straddles districts, so it
   offers a choice — are the choices reachable and operable?
4. Read the tab order aloud. Does the sequence match the order the page reads?

### 3.2 A real screen reader

VoiceOver on macOS (`Cmd+F5`) or NVDA on Windows. Both if available; they disagree, and the
disagreements are informative.

5. Navigate by heading (`Ctrl+Opt+Cmd+H`). Do the headings alone tell you what is on the page?
6. Navigate by landmark. Is the footer reachable, and is the staleness notice announced? Age it first:
   set `fetched_at` in `site/manifest.json` well in the past.
7. Read the meetings list. Do dates, times, `Deferred`, the testimony deadline and "in person /
   hybrid / remote" survive as speech?
8. Read the two refusal strings — registration cut-off and per-speaker time limit, which the City
   publishes nowhere. Does a listener hear "nobody has this" rather than an error on our part?
9. On `/district/3/`, the degraded page: do the empty states read as deliberate? "No committee
   assignments are published on this district's page" must not sound like a bug.

## 4. The record

One row per pass. A pass with no row did not happen.

| Date | Version | Keyboard (3.1) | Screen reader (3.2) | By | Notes |
|---|---|---|---|---|---|
| 2026-09-23 | `feat/m5-a11y-perf` | ✅ automated: 122/122 checks, 9 page types, 0 failures | ❌ **NOT RUN** | machine | `make a11y` covers steps 1–4 mechanically. The judgement half of 3.1 and all of 3.2 need a person with a screen reader. |

`make a11y` reads the accessibility tree — the data a screen reader is given. It is not a screen
reader and it does not listen. Exit criterion 5 in `docs/phase-1-scope.md` stays partly met until a
row above says a human ran §3.2. Phase 1 publishes nothing, so no reader relies on the untested half
today.

## 5. What the gates caught

Both 2026-09-23, recorded in full in `docs/OBSERVATIONS.md`:

- `connect-src` omitted `'self'`, so `/data/lookup.json`, `/data/districts.geo.json` and
  `/manifest.json` were refused: local ZIP/neighbourhood/district-number resolution fell through to
  the geocoder, inverting the privacy promise, and the staleness notice never rendered. Fixed; now
  covered by `tests/unit/test_csp.py` and `scripts/console_check.py`.
- The axe negative control (`tests/fixtures/a11y_broken/`) tested nothing — its contrast defect sat in
  a `<style>` block that `style-src 'self'` blocked. Moved to an external stylesheet.

## 6. Known gaps

| Gap | State |
|---|---|
| No real screen-reader pass (§4) | The largest gap, and the one open Phase 1 item |
| No true 390px layout check | `make shot` clamps at 500px (macOS minimum Chrome window width); `scripts/cdp.py` can now do device emulation, so fixable |
| Slow 3G measures 4.3–5.1 s, over 3 s | Reported, not gated — dominated by that profile's 2000 ms round trip, not our bytes. Reasoning in `perf-budget.json` |
| No accessibility statement page (R41, a SHOULD) | Deferred with publishing; needs a working feedback address |
| No readability gate on procedural copy (R41) | Deferred with publishing |
| `/favicon.ico` 404s on every page load | Shipping one is an open owner decision (§7.3); `scripts/console_check.py` names it as an expected browser probe |
