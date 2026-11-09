/* Readme — what this is, where the figures come from, and what it will not tell you.
 *
 * The refusals are the part worth keeping. A civic site that ranks districts or scores
 * engagement invents a number nobody published, and this page is where that is said out loud
 * rather than left as an absence a reader has to notice.
 *
 * Built from `sheet` and `group` so it reads as part of the desktop without styling of its
 * own. The only rule this app ships is the one `app.css` could not express as a widget.
 */

import { group, sheet } from '../../vendor/webxp/widgets.mjs';

//: Written at the site root by `showup build`, beside the data it describes.
const BUILT_AT_URL = '/manifest.json';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function link(href, text) {
  const anchor = el('a', null, text);
  anchor.href = href;
  // Every off-site link carries no referrer, which is the same rule the rest of the site
  // follows: where a reader is reading from is not the City's business or ours.
  anchor.rel = 'noopener noreferrer';
  return anchor;
}

export default {
  id: 'showup-readme',
  name: 'Readme',
  icon: 'document',
  singleton: true,
  width: 560,
  height: 460,
  status: true,
  styles: ['app.css'],

  mount({ win }) {
    const root = sheet();

    root.append(
      el('h2', 'readme-title', 'Show Up NYC'),
      el('p', 'readme-line',
        'Who represents an address in New York City, and when a reader can turn up and say '
        + 'something about it. Fifty-one City Council districts and fifty-nine community '
        + 'boards, built from the City\'s own published data.',
      ),
    );

    root.append(
      group('What it is built from', {
        caption: 'Every figure on every page traces to one of these.',
        columns: ['Source', 'What it gives'],
        rows: [
          ['City Council', 'districts, members, committee membership'],
          ['NYC Planning', 'community district boundaries and profiles'],
          ['Council calendar', 'hearings, their times and their agendas'],
          ['Board calendars', 'each board\'s own published meeting dates'],
          ['Participatory budgeting', 'what a board asked the City to fund'],
        ],
      }),
    );

    root.append(
      group('What it refuses to do', {
        columns: ['Refusal', 'Why'],
        rows: [
          [
            'Rank or score districts',
            'No published figure supports it, so a rank would be this site\'s opinion '
            + 'wearing a number\'s clothes.',
          ],
          [
            'Measure sentiment or engagement',
            'Nobody publishes it. A number here would be invented.',
          ],
          [
            'Guess a URL',
            'A constructed nyc.gov address that 404s is worse than saying the City does not '
            + 'publish one.',
          ],
          [
            'Expand a prose meeting cadence into dates',
            '"Second Tuesday" is not a date until somebody publishes one, and inventing '
            + 'twelve would read as a schedule.',
          ],
        ],
      }),
    );

    // Kept as a reference so `ready` can fill it once the fetch lands. `group` takes a list
    // of lines, and a line may be a node.
    const freshness = el('span', 'readme-freshness', 'Reading the build stamp…');
    root.append(
      group('Freshness', [
        freshness,
        'Hearings are deferred or moved without notice. Every figure here is as old as the '
        + 'stamp above.',
      ]),
    );

    root.append(
      group('The City\'s own pages', [
        link('https://council.nyc.gov/districts/', 'Council district lookup'),
        link('https://communityprofiles.planning.nyc.gov/', 'Community district profiles'),
      ]),
    );

    win.app = { freshness };
    win.setStatus('Built from the City\'s published data.');
    return root;
  },

  /* The build stamp is read rather than baked in, so a stale deploy says so.
   *
   * In `ready` and not `mount` because it is a fetch: `mount` is what the window waits for
   * before it is shown, and a reader should not wait on the network to see the text.
   */
  /* The build stamp, and whether any source is past its own max age.
   *
   * Read at read time rather than baked in, which is the whole of the promise: a build
   * cannot know how old it will be when somebody opens it, so an abandoned site has to be
   * able to say so itself (docs/phase-1-scope.md §2.12).
   *
   * It states the stamp and names the source it belongs to, and it passes no verdict — no
   * "out of date", no "days ago", no instruction. The reader is told the number and left to
   * draw the conclusion, because which staleness matters depends on what they came for.
   */
  async ready({ win }) {
    const { freshness } = win.app;
    try {
      const response = await fetch(BUILT_AT_URL, { cache: 'no-store' });
      if (!response.ok) throw new Error(`${BUILT_AT_URL} returned ${response.status}`);
      const manifest = await response.json();

      const stale = [];
      for (const [name, source] of Object.entries(manifest.sources || {})) {
        const fetchedAt = Date.parse(source.fetched_at);
        if (Number.isNaN(fetchedAt) || !source.max_age_hours) continue;
        if ((Date.now() - fetchedAt) / 3_600_000 > source.max_age_hours) {
          stale.push({ name, fetchedAt });
        }
      }

      if (stale.length) {
        // The oldest, and named: "something is stale" is not an answer a reader can act on.
        const oldest = stale.reduce((a, b) => (b.fetchedAt < a.fetchedAt ? b : a));
        freshness.textContent =
          `Data fetched ${new Date(oldest.fetchedAt).toLocaleString()}`
          + ` (${oldest.name.replace(/_/g, ' ')}).`;
        freshness.classList.add('is-stale');
        return;
      }

      const built = manifest.built_at ? new Date(manifest.built_at) : null;
      freshness.textContent = built && !Number.isNaN(built.getTime())
        ? `Data fetched ${built.toLocaleString()}.`
        : 'The build stamp could not be read.';
    } catch (error) {
      // Named, not swallowed. A reader who sees no date should be told whose fault it is.
      freshness.textContent = `The build stamp could not be read (${error.message}).`;
    }
  },
};
