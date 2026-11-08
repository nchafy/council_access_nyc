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

const desktop = new Desktop({
  root: document.getElementById('webxp'),
  name: 'Show Up NYC',
  tagline: 'City Council hearings and deadlines, council districts, and community boards',
  footer: 'Built from the City\'s published data. Open Readme for every source.',
});

// For the devtools console and for the browser gates, which read geometry rather than
// trusting a screenshot. Published before the apps load, so a desktop whose apps failed is
// still inspectable.
window.webxp = desktop;

const { loaded, broken } = await loadApps(desktop, APPS);
window.webxpApps = { loaded, broken };

await desktop.autostart();
