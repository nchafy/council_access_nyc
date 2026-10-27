# Design

Binding on every rendered surface: the visual system, the map's interaction model, and the
CSS the Content-Security-Policy leaves available. Copy is governed by `docs/voice.md`;
contrast measurements live in `docs/accessibility-pass.md` §7. This file is the *how it
looks and behaves*, and each rule below is a decision with evidence, not a preference.

## 1. The design heuristic

Owner, 2026-10-22: "the UI should provide what the user can click and should be intuitive
what to fill in each box."

- A control MUST explain itself through its label, its placeholder and its button verb.
- Prose above a control explaining why the control exists MUST be deleted. `docs/voice.md`
  §4 carries the rule and the line it does not cross: an *explanation* goes, a *disclosure*
  stays.
- A heading MUST name a thing. It MUST NOT ask a question and MUST NOT narrate.
- A heading MUST be stable over time. "Fiscal 2027 budget requests — 56 filed" changes
  every year and every refresh; "Budget requests" does not. Figures belong in the rows
  beneath, where a changing value is expected.

## 2. The visual system

Two aesthetics, scoped to two surfaces. Owner's decision, 2026-10-22 and 2026-10-23.

**Site chrome: Windows XP (Luna).** Raised bevels, a bisque control face, gradient title
bars, group boxes with legends, a red close box. Applied to the whole site, not only the
map panel.

| Token | Value | Role |
|---|---|---|
| `--face` | `#ece9d8` | control face, the "bisque" |
| `--rule` | `#919b9c` | control border |
| `--title-a` | `#0a246a` | title bar, dark end |
| `--title-b` | `#3a6ea5` | title bar, light end |

**The map: early-2000s satnav.** A bounded, high-contrast, low-detail palette, not a
general-purpose basemap. Values in `src/showup/assets/map.mjs`:

| Element | Value |
|---|---|
| Land / background | `#cfd9a8` |
| Park | `#9ec27a` |
| Water | `#1b3f7a` |
| Major road fill | `#ffe27a` |
| District fill | `#1b3f7a` (`FILL`) |
| Selected | `#e8431f` (`SELECTED`) |
| Hovered | `#ff8c42` (`HOVERED`) |
| District outline | `#13264a` (`LINE`) |

Luna's own palette failed WCAG 1.4.3 twice and MUST NOT be adopted on the strength of
period accuracy. The tagline at `#dfe8f5` measured 4.30:1 and the close box at `#e8785a`
measured 2.89:1; both were changed. Every ratio is computed in
`docs/accessibility-pass.md` §7 — a period colour MUST be measured before it ships.

**Non-text contrast still binds.** The share-bar track carries a border because the fill
alone measures 1.45:1 against the panel, below the 3:1 that WCAG 2.2 SC 1.4.11 requires
(<https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast>).

## 3. CSS under the CSP

The shipped policy is `style-src 'self'` with no `unsafe-inline`
(`_headers`). Two consequences, both load-bearing:

- An inline `style` attribute and an inline `<style>` block are both refused by the
  browser. Neither MUST be emitted, from a template or from JavaScript.
- A value computed at runtime therefore cannot be expressed as CSS. It MUST be expressed
  as an SVG geometry attribute instead — `width` on a `<rect>`, not `style="width:44%"`.
  This is why the community-board share graphic is inline SVG.

`img-src 'self'` refuses `data:` URIs. MapLibre's own zoom controls ship 39 inline
`data:image/svg+xml` background images, so they render blank **and log nothing**; the
project draws its own buttons. A control that depends on a `data:` URI MUST NOT be used.

Dark mode re-steps `--rule` to `#333a42` rather than inverting the light value.

## 4. The map

- **A map MUST NOT sit inside a scrolling page.** Owner, 2026-10-21: "never have a scroll
  in a scroll. When i try to scroll i instead just zoom out." `/map/` is its own
  full-screen route where nothing scrolls. It also keeps the 449 KB library off every
  other page.
- **Zoom is a bounded window, not a free camera.** Owner's reference is the MTA app: "an
  absolute zoom window, and a contained box." `MAX_ZOOM = 15`; the minimum is computed
  from the city's fit. `maxBounds` alone is insufficient — panning at the minimum still
  slides the city off-centre — so `dragPan` is disabled below `minZoom + 0.01` and
  re-enabled on `zoomend`.
- **`refit()` MUST recompute fit, `minZoom`, `maxBounds` and the pan lock together**, on
  load and on every container width change. Computing them separately let the detail panel
  obscure the city at full zoom-out with no way to recover the view.
- **Hover and selection MUST use `feature-state`, never `get`.** Reading a data property
  into paint is a choropleth, which §2 of the outline forbids; `tests/integration/
  test_map_route.py` gates this against the district paint block specifically. Scoping
  matters: an unscoped grep fired on an `interpolate` belonging to the basemap's woodland
  opacity.
- **District layers MUST be inserted before the first `symbol` layer** so place labels
  draw above the overlay.
- Fill opacity by state: selected `0.55`, hovered `0.35`, resting `0.12`. Every district
  and board is drawn identically — the uniform fill *is* the claim that nothing is ranked.

## 5. Selection and search

- Selecting a polygon opens a split view carrying the headline facts, and links through
  for the rest. The panel MUST NOT restate provenance per field; it states `as_of` once
  and sends the reader to the page.
- An address or ZIP MUST highlight and pin. It MUST NOT navigate. Owner, 2026-10-27:
  "instead of jumping to the detailed page, rather highlight the area." A ZIP straddling
  several districts highlights all of them.
- Every detail page MUST carry a route back to the map.
- A citywide fact MUST NOT render on a district. Council and committee meetings belong to
  no district, so the next citywide meeting moved to the landing page on 2026-10-27. This
  is the same decision as "the district is a filter, not the organising key."

## 6. Verifying a visual change

A layout defect is invisible to an HTTP assertion. These MUST run on any change to
`site.css`, `map.mjs`, or a template:

| Gate | Catches |
|---|---|
| `make reflow` | WCAG 1.4.10 at 320 px and 390 px |
| `make axe` | WCAG 2.2 AA over every page |
| `make a11y` | real `Tab` keypresses against the accessibility tree |
| `make console` | any CSP violation or console error |
| `make shot` | what the other four cannot see |

Three traps this project has already fallen into:

- **`display` beats the `hidden` attribute.** `display: inline-block` on a `hidden`
  element makes it visible and focusable. A rule that sets `display` on something
  conditionally hidden MUST carry `:not([hidden])`.
- **Read a measurement twice before trusting it.** The reflow gate failed on a different
  board page each run at 3 px — a race, not a defect. `_settled_measurement()` reads until
  two consecutive measurements agree, and `_settled_focusables` does the same for controls
  revealed after the map draws.
- **A screenshot hash is not a position test.** Dragging the cursor across districts sets
  hover state and repaints, which changes the hash while the map has not moved. Measure
  `getCenter()`; keep a no-interaction control.

WebGL needs real flags. `scripts/cdp.py` passes `--enable-unsafe-swiftshader`,
`--use-gl=angle` and `--use-angle=swiftshader`, because `--disable-gpu` yields no WebGL2
and MapLibre then draws nothing, silently.
