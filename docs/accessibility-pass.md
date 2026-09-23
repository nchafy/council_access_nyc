# The accessibility pass

**What this is for:** R39 requires "a documented keyboard-only and screen-reader pass per
release". This is that document: the procedure, what the machine already covers, what only
a person can judge, and the record of each pass.

**When to run it:** before any release, and after any change to `render.py`, `site.css`,
`site.js` or `address.js`. The machine half runs on every commit.

---

## 1. What is automated, and what that is worth

Four gates run without a human. All four are in CI.

| Gate | Command | What it proves |
|---|---|---|
| axe, WCAG 2.2 AA | `make axe` | 0 violations on all 114 pre-rendered pages |
| Keyboard and a11y tree | `make a11y` | 122 named checks over 9 page types |
| Console and CSP | `make console` | no page logs an error or trips its own policy |
| Page weight and cold load | `make perf` | 60 KB gzipped, p95 under 3 s on throttled 3G |

**Automated checking finds a minority of accessibility defects.** Deque, who write axe,
put its coverage at roughly a third to a half of WCAG issues. Everything in section 3
below is outside that, and none of it can be delegated to a gate. A green build is the
floor, not the pass.

### What the machine half actually asserts

The keyboard audit presses real `Tab` keys in a real browser and records where focus
lands, rather than reading `tabindex` out of the markup. Per page: the first Tab reaches
the skip link, the skip link becomes visible when focused and moves focus into `<main>`,
tab order matches DOM order, every focusable element is reachable, every focused element
wears a focus ring of at least 2px, and `Shift+Tab` retraces the order.

The tree audit reads Chrome's own accessibility tree — the computed roles and names a
screen reader consumes. Per page: `banner`, `main` and `contentinfo` landmarks exist,
every interactive node has a non-empty accessible name, there is exactly one level-1
heading, and heading levels never skip.

The front page additionally proves the no-JavaScript path with script execution disabled
in the browser: all 51 district and 59 board links present as plain links, and the address
box — which cannot work without script — stays hidden rather than sitting there taking
input that goes nowhere.

---

## 2. Before starting a manual pass

```bash
make fetch          # only if etl/raw/ is empty; ~9 min
make verify         # the standard gate must be green first
make axe            # 0 violations expected
make a11y           # 0 failures expected
make console        # 0 complaints expected
make perf           # both budgets
make serve          # then work against http://127.0.0.1:8000
```

Use `make serve`, never `python -m http.server`. The manual pass has to happen behind the
real `Content-Security-Policy`, because that policy has already broken a feature silently
once — see section 5.

---

## 3. The manual pass

Nine steps. Record the result of each in section 4.

### 3.1 Keyboard only, no mouse

Unplug or ignore the mouse. On `/`, `/district/3/` and `/board/302/`:

1. Tab from the top. Does the focus ring stay visible against the page at every stop, not
   merely present in the computed style? Low contrast against a pale background is a real
   failure the automated check cannot see.
2. Use the district dropdown with the keyboard alone: Tab to it, open with `Alt+Down` or
   arrow through it, choose a district. The page should navigate on change.
3. Type `11217` into the address box and submit with `Enter`. A ZIP straddles districts,
   so it offers a choice — are the choices reachable and operable by keyboard?
4. Read the tab order aloud. Does the sequence match the order the page *reads*? A page
   can pass "tab order follows DOM order" and still have a DOM order that makes no sense.

### 3.2 A real screen reader

VoiceOver on macOS (`Cmd+F5`) or NVDA on Windows. Both, if available — they disagree, and
the disagreements are informative.

5. Navigate by heading (`Ctrl+Opt+Cmd+H` in VoiceOver). Do the headings alone tell you
   what is on the page and let you reach the part you want?
6. Navigate by landmark. Is the footer reachable, and does the staleness notice — when
   present — get announced rather than sit there as unremarked text? Age this deliberately:
   edit `site/manifest.json` and set a `fetched_at` well in the past.
7. Read the meetings list. Does each entry make sense as *speech*? Dates, times, the
   `Deferred` state, the testimony deadline, and "in person / hybrid / remote" all have to
   survive being read out of visual context.
8. Read the two refusal strings — the registration cut-off and the per-speaker time
   limit, which the City publishes nowhere. Does a listener understand that this is
   information nobody has, rather than an error or an omission on our part? This is the
   product's core honesty claim and it has to survive audio.
9. On `/district/3/`, the degraded page: do the designed empty states read as *deliberate*?
   "No committee assignments are published on this district's page" must not sound like a
   bug or like the member has no committees.

---

## 4. The record

One row per pass. A pass with no row did not happen.

| Date | Version | Keyboard (3.1) | Screen reader (3.2) | By | Notes |
|---|---|---|---|---|---|
| 2026-09-23 | `feat/m5-a11y-perf` | ✅ automated: 122/122 checks over 9 page types, 0 failures | ❌ **not run** | machine | Steps 1–4 are covered by `make a11y` in the mechanical sense (focus order, rings, reachability, the no-JS path). The judgement parts of 3.1 — whether the ring reads against the page, whether the DOM order *makes sense* — and the whole of 3.2 need a person with a screen reader and have not been done. |

**The screen-reader pass is outstanding and cannot be automated away.** `make a11y` reads
the accessibility tree, which is the data a screen reader is given; it is not a screen
reader and it does not listen. Exit criterion 5 in `docs/phase-1-scope.md` is therefore
recorded as partly met, with this as the open half. Phase 1 is local-only and nothing is
published, so nobody is currently relying on the untested half — but the criterion should
not be ticked until a row above says a human ran section 3.2.

---

## 5. What the gates have already caught

Kept because it argues for the gates better than any rationale could.

**`connect-src` forbade the site's own data (2026-09-23).** The CSP named the geocoder and
omitted `'self'`, so under the real policy three same-origin fetches were refused:
`/data/lookup.json`, `/data/districts.geo.json` and `/manifest.json`.

Consequences. Local resolution of a ZIP, a neighbourhood or a district number *is* the
privacy feature — §4.4 promises those never reach the geocoder. With the index unfetchable,
every query fell through to the geocoder, so a policy written to protect the reader's
address was causing more of their input to be sent, not less. Separately, the staleness
notice never appeared, which is the mechanism that stops an abandoned site claiming to be
fresh.

Why nothing caught it: `tests/browser/test_address_box.py` serves the site from a bare file
server with no CSP, and `scripts/verify.py` fetches the manifest over plain HTTP where no
policy applies. Both tested the feature; neither tested it under the policy shipped with
it. It surfaced the first time anything drove the site in a browser behind the real
headers, which is what this pass is.

Now covered from both ends: `tests/unit/test_csp.py` cross-checks the policy against every
URL the frontend fetches, and `scripts/console_check.py` fails on any violation in a real
browser.

**The negative control caught itself (2026-09-23).** `tests/fixtures/a11y_broken/` exists
because the site passed axe on the first run it was ever given, and "clean" cannot be
distinguished from "nothing ran". Its deliberate colour-contrast defect was in a `<style>`
block, and axe never reported it — `style-src 'self'` blocked the inline CSS, so the rule
applied to nothing. Moved to an external stylesheet.

---

## 6. Known gaps

- **No real screen-reader pass yet** (section 4). The largest gap.
- **No true 390px layout verification.** `make shot` clamps at 500px wide because macOS
  clamps Chrome's minimum window width; the CDP client in `scripts/cdp.py` can now do
  device emulation, so this is fixable and simply has not been done.
- **The reported-only Slow 3G figure exceeds 3 s** (4.3–5.1 s), dominated by that
  profile's 2000 ms round trip rather than by our bytes. See the reasoning in
  `perf-budget.json`; it is measured and published rather than quietly dropped.
- **No accessibility statement page** (R41, a SHOULD). Deferred with publishing, since it
  needs a working feedback address and nothing is public in Phase 1.
- **No readability gate** on procedural copy (R41).
- **`/favicon.ico` 404s** on every page load. Shipping a favicon is an identity decision
  (§7.3) that is deliberately still open, so `scripts/console_check.py` names it as an
  expected browser probe rather than inventing a mark.
