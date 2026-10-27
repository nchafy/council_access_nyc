# The accessibility pass

**A real screen-reader pass has never been run.** It is the one open Phase 1 item (§4).

Run this before any release, and after any change to `render.py`, `site.css`, `site.js` or
`address.js`. R39 requires a documented keyboard-only and screen-reader pass per release.

## 1. The automated gates

All five run in CI on every commit.

| Gate | Command | What it proves |
|---|---|---|
| axe, WCAG 2.2 AA | `make axe` | 0 violations, all 116 pre-rendered pages; **12 `color-contrast` incomplete**, one per page, which are the XP theme's gradients — resolved by computing the ratios, see §7 |
| Keyboard + accessibility tree | `make a11y` | 161 checks over 12 page types, 0 failures |
| Console and CSP | `make console` | 0 complaints — no page logs an error or trips its own policy |
| Reflow, WCAG 1.4.10 | `make reflow` | 0 violations at 320 px and 390 px; `ALL=1` covers all 116 |
| Weight and cold load | `make perf` | 25.4 KB heaviest page (`/map/`) vs 60 KB; geometry 226 KB vs 300 KB; the map library 439 KB vs its own 500 KB budget |

`make a11y` presses real `Tab` keys in a real browser and reads Chrome's accessibility tree: skip
link, focus into `<main>`, DOM order, reachability, ≥2px ring, `Shift+Tab`; landmarks, accessible
names, one h1, no skipped heading levels. It also runs the front page with script execution disabled.

`make reflow` sets the viewport over CDP rather than sizing a window, which is the only way to
reach a phone width on macOS (§6). The measurement is the layout viewport, not an element rect:
content that cannot fit widens the initial containing block, and once it has widened every element
fits inside the widened value, so a per-element overflow check reports clean. A `window.innerWidth`
above the requested width is the violation.

axe covers roughly a third to a half of WCAG issues (Deque's own figure). Everything in §3 is outside
that. A green build is the floor, not the pass.

## 2. Before a manual pass

```bash
make fetch     # only if etl/raw/ is empty; ~9 min
make verify    # must be green first
make axe       # expect 0 violations
make a11y      # expect 0 failures
make console   # expect 0 complaints
make reflow    # expect 0 violations at both widths
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
10. On `/board/302/`, the five request cards are native `<details>` with the `<h3>` inside the
    `<summary>`. Chrome's tree exposes **both** — a `DisclosureTriangle` carrying the title plus
    the priority and announcing `expanded`, and a separate level-3 heading carrying the title — so
    heading navigation still reaches every card while collapsed. Check that the doubled title does
    not obscure the state, and that expanding announces the change.
11. On `/references/`: does each identifier, fetch date and freshness window stay attached to its
    own dataset, or do the eight cards run together as one list?

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

Recorded in full in `docs/OBSERVATIONS.md`.

2026-10-20, the first time any page was rendered narrower than 500 px:

- Two upstream strings have no break opportunity in them, and each forced the layout viewport
  wider than the phone it was asked for: a board website URL
  (`www.nyc.gov/site/statenislandcb2/index.page`, 345 px) and a board email
  (`communityboard@queenscb3.cityofnewyork.us`, 363 px). Four pages failed at 320 px and three
  more at 390 px. Fixed in `site.css`; gated by `scripts/reflow_check.py`.
- The §6 claim that `scripts/cdp.py` "can now do device emulation" was not true — it had network
  and CPU throttling only. The emulation was written as part of the gate.
- The representative page set did not contain the worst case. The email overflows a 390 px
  viewport, and the three pages carrying it were only reached by `ALL=1`. `/district/21/` is now
  in the set.

Both 2026-09-23:

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
| Overlapping text passes every gate | Found 2026-10-22: the map panel rendered on top of the `h1` at 390 px and axe, a11y, console, reflow and perf were all green. Only a screenshot shows it. `make shot` is load-bearing, not decorative |
| `make shot` still clamps at 500px | macOS minimum Chrome window width. No longer a gap in coverage — `make reflow` measures 320px and 390px over CDP, which the window size cannot reach — but the screenshots are still not phone-width |
| `make gates` dies partway, roughly one run in two | A different gate each time, always `CDPError: lost the channel to Chrome: [Errno 54] Connection reset by peer`. Every gate passes run on its own, and CI is unaffected because it runs them as one pytest session (`make browser`, 85 passed). Observed 2026-10-20; not diagnosed |
| Slow 3G measures 4.3–5.1 s, over 3 s | Reported, not gated — dominated by that profile's 2000 ms round trip, not our bytes. Reasoning in `perf-budget.json` |
| No accessibility statement page (R41, a SHOULD) | Deferred with publishing; needs a working feedback address |
| No readability gate on procedural copy (R41) | Deferred with publishing |
| `/favicon.ico` 404s on every page load | Shipping one is an open owner decision (§7.3); `scripts/console_check.py` names it as an expected browser probe |

## 7. The XP theme's contrast, computed

axe cannot compute a contrast ratio against a gradient, so every page with the title bar
reports one `color-contrast` **incomplete** — not a pass and not a failure, axe declining to
decide. The ratios were computed against both gradient stops instead, which is the only
honest way to clear them. Luna's own palette failed twice and both were changed rather than
accepted:

| Pair | Ratio | Verdict |
|---|---|---|
| Wordmark white on the title bar's light end `#3a6ea5` | 5.31:1 | pass |
| Wordmark white on the dark end `#0a246a` | 14.25:1 | pass |
| Tagline `#dfe8f5` on the light end — **Luna's own value** | **4.30:1** | **failed**, changed to white |
| Ink `#000` on the control face `#ece9d8` | 17.21:1 | pass |
| Muted `#3a3a3a` on the control face | 9.32:1 | pass |
| Link `#0000cc` on white | 11.22:1 | pass |
| Legend `#0a2a5a` on the group box | 13.70:1 | pass |
| Button ink on the bevel's darkest stop `#d7d2bf` | 13.86:1 | pass |
| Close glyph white on `#e8785a` — **Luna's own value** | **2.89:1** | **failed**, darkened to `#c8341a` |

Re-run the computation on any change to these colours. A gradient stop is invisible to the
gate, so the only thing standing behind these numbers is that somebody worked them out.
