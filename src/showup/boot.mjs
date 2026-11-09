/* The host page.
 *
 * It owns the desktop's name and its wallpaper, and nothing else. Every program is a folder
 * under `apps/`, listed in the generated `apps/manifest.mjs`; adding one means adding a
 * folder, never editing this file.
 *
 * The shell is vendored at `/vendor/webxp/` rather than webxp's own `/src/`, which is the one
 * path difference between this host and that project's demo.
 */

import { Desktop } from '/vendor/webxp/webxp.mjs';
import { loadApps } from '/vendor/webxp/apps.mjs';
import { APPS } from '/apps/manifest.mjs';

const NAME = 'Show Up NYC';

const desktop = new Desktop({
  root: document.getElementById('webxp'),
  name: NAME,
  tagline: 'City Council hearings and deadlines, council districts, and community boards',
  footer: 'Built from the City\'s published data. Open Readme for every source.',
});

/* Three corrections to the shell's semantics, applied here because `vendor/webxp/` is a
 * pinned copy — see `vendor/webxp/PROVENANCE.md`, which records them as defects of the
 * window manager rather than of this site. Each would be better fixed upstream.
 *
 * 1. The desktop surface carries the page's content — the icons, and every window — and the
 *    shell gives it no role, so a screen-reader user gets no "skip to content" and axe
 *    reports the whole page as outside any landmark.
 * 2. The shell writes no level-1 heading. Its only heading is a window title, at level 2, so
 *    the document both lacks an h1 and starts its outline at the second level. The name is
 *    visually hidden because the taskbar already shows it: this is the heading a screen
 *    reader needs, not a second copy of a label a sighted reader can see.
 */
desktop.surface.setAttribute('role', 'main');
const heading = document.createElement('h1');
heading.className = 'visually-hidden';
heading.textContent = NAME;
// Focusable only by script. It is the landing point set after autostart below, and it must
// not become a tab stop of its own on the way past.
heading.tabIndex = -1;
desktop.surface.prepend(heading);

// For the devtools console and for the browser gates, which read geometry rather than
// trusting a screenshot. Published before the apps load, so a desktop whose apps failed is
// still inspectable.
window.webxp = desktop;

const { loaded, broken } = await loadApps(desktop, APPS);
window.webxpApps = { loaded, broken };

await desktop.autostart();

/* 3. `launch` ends in `win.takeFocus()`, which is right for a click and wrong for autostart:
 *    opening the page is not a request to be put inside a window. Measured — the caret landed
 *    on the folder's "City councils" row, so a keyboard reader arrived mid-list with no
 *    announcement of where they were, and Tab then wrapped through the desktop rather than
 *    walking it from the top.
 *
 *    The heading takes it, rather than `blur()`. Blurring looks right and is not: it clears
 *    the ring, and `document.activeElement` reads `body` afterwards, but the browser keeps a
 *    sequential focus navigation starting point where the blurred element was, so the first
 *    Tab resumed at the row after it — measured as index 6 of 11 with focus apparently on
 *    `body`. Focusing a node at the top of the document moves that starting point too.
 *
 *    A heading is also the better landing place: it is announced as "Show Up NYC, heading
 *    level 1", which is the orientation a row of a list cannot give.
 */
heading.focus();

// The readiness half of the `data-ready-when` contract the document opens with. The gates
// read it rather than sleeping: a desktop measured mid-build reports whatever the half-built
// state happened to be, which is how an axe sweep came to report a contrast failure on a
// loading placeholder and three undersized title boxes that measure 24px at rest.
//
// Set last, and only on success: the attribute is absent if `loadApps` or `autostart` throws,
// which is what makes a harness waiting on it fail instead of passing over a broken desktop.
document.documentElement.dataset.ready = 'desktop';
