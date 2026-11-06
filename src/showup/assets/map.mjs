// The map on the front page. Two layers — the 51 council districts and the 59 community
// boards — with one visible at a time, because they answer different questions and
// overlaying them makes both unreadable.
//
// MapLibre is 449 KB gzipped against a 12 KB script ceiling, so it is imported dynamically
// and only after the document has painted: the address box, the dropdowns and the link
// lists all work before a byte of it arrives. No basemap — tiles would be a third-party
// request disclosing which neighbourhood is being read, which product-brief.md §5 refuses.
// Every polygon in a layer carries the same fill; the only one that differs is the one the
// reader selected, because a shaded map reads as a ranking whatever the legend says.

import { createBaseMap } from '/vendor/basemap.mjs';
import { mountChrome } from '/vendor/chrome.mjs';

//: Set once the page's one-time setup has run. The base map rebuilds the district layers
//: on every basemap change and calls `draw` again; the camera floor and the DOM bindings
//: must not be redone with them.
let settled = false;

//: liberty compares `ref_length` without checking the feature carries it, so MapLibre
//: disables both highway-shield layers and no shield ever draws. Repaired on the loaded
//: style rather than before it, because the base map owns style loading.
function repairShieldFilters(map) {
  for (const layer of map.getStyle().layers || []) {
    const filter = layer.filter;
    if (!Array.isArray(filter)) continue;
    const repaired = JSON.parse(
      JSON.stringify(filter).replaceAll('["get","ref_length"]', '["coalesce",["get","ref_length"],0]')
    );
    if (JSON.stringify(repaired) !== JSON.stringify(filter)) map.setFilter(layer.id, repaired);
  }
}

const container = document.getElementById('map');
const status = document.getElementById('map-status');
const toggle = document.getElementById('map-toggle');

// The base map is the vendored `30daymapchallenge` module, which owns the style, the three
// map types and the failure behaviour: a style request that fails leaves the districts
// drawn and hit-testable on their own. Its tile hosts withdrew the no-third-party promise,
// recorded as an owner decision in product-brief.md §5 and justified in `_headers`.

//: The zoom window. The floor is computed per viewport — whatever zoom fits the whole city is
//: as far out as the map goes, so it can never be zoomed out to a continent. The ceiling is
//: fixed: past this the basemap has no more detail to give and the district boundary, which is
//: simplified to 2.2 m, starts to look like a decision rather than a coastline.
const MAX_ZOOM = 15;

const FILL = '#1b3f7a';
const SELECTED = '#e8431f';
const HOVERED = '#ff8c42';
const LINE = '#13264a';

//: Neighbourhood names and the City's own board labels, from the lookup the address box
//: already fetches — 5.7 KB gzipped, so reusing it costs nothing. Populated before the map
//: draws; `names.district` is keyed by number, `names.board` by `boro_cd`.
const names = { district: new Map(), board: new Map() };

//: Headline facts for the detail panel, from /data/preview.json. Null until it
//: arrives, and null forever if it does not — the panel then shows what it has.
let preview = null;

//: The district geometry's own bounds, kept so `refit` can be called again on resize.
let cityBounds = null;

//: Per-feature bounding boxes, so selecting one district frames that district instead of
//: refitting the whole city. Built once, when the geometry arrives.
const featureBounds = { council: new Map(), board: new Map() };

//: Each feature's area-weighted centroid, which is not its bounding box's centre. District
//: 35 runs north-west to south-east, so most of its bbox is other people's territory and
//: centring the bbox left the district itself off to one side (owner, 2026-10-30).
const featureCentres = { council: new Map(), board: new Map() };

//: How far a framed feature is allowed to zoom. Well below MAX_ZOOM on purpose: fitting
//: one district to the frame landed around z13.5, which reads as a street map of somewhere
//: rather than as a district in its city. At 12 the surrounding districts stay in view.
const FRAME_MAX_ZOOM = 12;

//: How long a camera move takes. Animated rather than cut, so the reader can see where the
//: view went instead of being teleported.
const CAMERA_MS = 550;

//: Street level for a geocoded address, matching what the reader asked for: a located
//: point, not a dot on a city-wide map. Capped by MAX_ZOOM, which is the tile ceiling.
const ADDRESS_ZOOM = 14;

//: The MapLibre module, kept so the pin can be built after load.
let library = null;

function indexNames(lookup) {
  for (const d of lookup.districts || []) names.district.set(String(d.n), d);
  for (const b of lookup.boards || []) names.board.set(String(b.code), b);
}

//: The Council's own committees index. Per-committee pages are not linked because no source
//: this project reads carries a committee URL, and constructing nyc.gov slugs is how 59 board
//: links were once "verified" as working when they 404ed (docs/pull-requests.md).
const COMMITTEES_INDEX = 'https://council.nyc.gov/committees/';

const BOROUGHS = {
  1: 'Manhattan',
  2: 'The Bronx',
  3: 'Brooklyn',
  4: 'Queens',
  5: 'Staten Island',
};

function boroughOf(code) {
  return BOROUGHS[String(code).charAt(0)] || 'New York City';
}

/** The two layers, and everything that differs between them, in one place. */
const LAYERS = {
  council: {
    url: '/data/districts.geo.json',
    key: 'coundist',
    source: 'council',
    noun: 'council district',
    href: (id) => `/district/${id}/`,
    label: (id) => `Council District ${id}`,
    // "drawn to equal population" was asserted here and cut 2026-10-22: the criteria are in
    // City Charter §52 and were never read, so the card states who draws the lines and when,
    // which nyc.gov/site/districting does say.
    sections: (id) => {
      const hoods = (names.district.get(String(id)) || {}).hoods;
      const d = (preview && preview.districts && preview.districts[String(id)]) || {};
      const member = d.member;
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        // One value, so lines rather than a table. A seat status that is not "filled" gets
        // its own line instead of being hung off the name with a dash.
        [
          'Council Member',
          member
            ? [member.name, ...(member.seat_status === 'filled' ? [] : [`Seat recorded as ${member.seat_status}.`])]
            : ['No current member is on record for this seat.'],
        ],
        // Participatory budgeting, committees and the covering boards, exactly as the
        // district page renders them: the columns and rows are declared once, in
        // `render.district_tables`, and arrive here already shaped.
        ...(d.tables || []).map((spec) => [spec.legend, spec, spec.href]),
      ];
    },
  },
  board: {
    url: '/data/boards.geo.json',
    key: 'boro_cd',
    source: 'board',
    noun: 'community board',
    href: (id) => `/board/${id}/`,
    // The City's own label where the lookup has one ("Manhattan Community Board 1"), and the
    // derived form only as a fallback. `302` is Brooklyn's board 2: the first digit is the
    // borough, the rest the board, and the leading zero is padding, not part of the number.
    label: (id) =>
      (names.board.get(String(id)) || {}).label ||
      `Community Board ${Number(String(id).slice(1))}, ${boroughOf(id)}`,
    sections: (id) => {
      const hoods = (names.board.get(String(id)) || {}).hoods;
      const b = (preview && preview.boards && preview.boards[String(id)]) || {};
      return [
        ['Neighbourhoods', hoods ? [hoods] : []],
        // Quoted as the City's dataset records it. Boards publish their own schedules and
        // the two have been observed to differ, so this is not presented as a calendar.
        ['Meets', b.cadence ? [b.cadence] : ['No City dataset records this board\'s cadence.']],
        ['Board office', [b.address, b.phone].filter(Boolean)],
        // The covering council districts and the budget register headline, from the same
        // specs the board page renders.
        ...(b.tables || []).map((spec) => [spec.legend, spec, spec.href]),
      ];
    },
  },
};

function say(text) {
  if (status) status.textContent = text;
}

/** Tell the page's readers that nothing more will appear.
 *
 * Answers the `data-ready-when` promise in `map.html`: the accessibility gate waits for this
 * before it measures the tab order, because four controls here are revealed by script. Set on
 * every settled outcome and not only the happy one — a browser with no WebGL still has a
 * final, stable page, and a gate that failed it would be reporting the wrong thing.
 */
function declareReady() {
  document.documentElement.dataset.ready = 'map';
}

// WebGL2 before MapLibre: a 449 KB download that can only fail is worth skipping, and
// every answer on this page is reachable without it.
function hasWebgl2() {
  try {
    return Boolean(document.createElement('canvas').getContext('webgl2'));
  } catch {
    return false;
  }
}

/** Resolve after first paint, so the map never delays the content above it. */
function afterFirstPaint() {
  return new Promise((resolve) => {
    if (document.readyState === 'complete') {
      requestAnimationFrame(() => resolve());
      return;
    }
    window.addEventListener('load', () => requestAnimationFrame(() => resolve()), {
      once: true,
    });
  });
}

/** The basemap's water fill, drawn again above the overlay to clip it to the coastline.
 *  A copy of the style's layer, so its colour tracks the basemap rather than drifting. */
function waterMaskLayer(style) {
  const water = (style.layers || []).find(
    (layer) => layer['source-layer'] === 'water' && layer.type === 'fill'
  );
  if (!water) return null;
  return { ...water, id: 'water-mask', filter: water.filter || ['all'] };
}

function fetchJson(url) {
  return fetch(url).then((response) => {
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json();
  });
}

async function main() {
  // The shell first, and outside every early return below: the clock, the title bar's close
  // box and the panel are the window's own furniture, and a map that cannot draw is exactly
  // when the reader still needs the page to look finished.
  const { panel } = mountChrome();

  if (!container) {
    declareReady();
    return;
  }
  if (!hasWebgl2()) {
    say('This browser has no WebGL, so the map cannot draw. Everything is listed below.');
    declareReady();
    return;
  }

  await afterFirstPaint();
  say('Loading the map…');

  let MapLibre;
  let geometry;
  let basemap;
  try {
    const [council, board, lookup, facts] = await Promise.all([
      fetchJson(LAYERS.council.url),
      fetchJson(LAYERS.board.url),
      // Names and the panel's facts are both niceties: a failure in either must not cost
      // the map, which still draws, hit-tests and links through to the full page.
      fetchJson('/data/lookup.json').catch(() => null),
      fetchJson('/data/preview.json').catch(() => null),
    ]);
    geometry = { council, board };
    if (lookup) indexNames(lookup);
    preview = facts;
  } catch (error) {
    // Named, not swallowed: a reader who sees nothing should be told whose fault it is.
    say(`The map could not load (${error.message}). Everything is listed below.`);
    declareReady();
    return;
  }

  //: Assigned by `settleOnce` and read back in `draw`, which is why it lives out here: a
  //: basemap change rebuilds the style and calls `draw` again, and what the reader had
  //: selected is the one thing that must survive it.
  let view = null;

  const base = await createBaseMap({
    container,
    center: [-73.95, 40.7],
    zoom: 9,
    // The boundaries are the content; tilting or spinning them helps nobody read one.
    tilt: false,
    // Re-run against a clean slate after every basemap change, so it carries no
    // "already added?" guard and keeps no state of its own.
    draw(map, ctx) {
      for (const name of Object.keys(LAYERS)) {
        addFillLayer(map, LAYERS[name], geometry[name], ctx.beforeId);
      }
      for (const name of Object.keys(LAYERS)) {
        addLineLayer(map, LAYERS[name], ctx.beforeId, ctx.basemap);
      }
      // Clips the district tint to the coastline so a district does not wash over water.
      // Absent on a raster basemap, which has no water layer to clone.
      const mask = waterMaskLayer(map.getStyle());
      if (mask) map.addLayer(mask, ctx.beforeId);
      repairShieldFilters(map);
      settleOnce(map);
      // Which layer is showing and what is highlighted are both style state, and the style
      // is what was just thrown away: without this, switching basemaps reveals both
      // geographies at once and drops the selection the panel is still describing.
      if (view) view.repaint();
    },
  });

  if (!base) {
    declareReady();
    return;
  }
  MapLibre = base.library;
  library = base.library;

  function settleOnce(map) {
    // Called from the first `draw`, not beside it: the camera floor and the View both need
    // the district layers to exist, and `draw` is where they come into being. Runs once —
    // the layers are rebuilt on every basemap change, but the feature index, the zoom floor
    // and the DOM bindings are properties of the page.
    if (settled) return;
    settled = true;
    map.setMaxZoom(MAX_ZOOM);
    // `LAYERS`, `geometry` and `featureBounds` are all keyed by source name, so one key
    // walks all three.
    for (const name of Object.keys(LAYERS)) {
      indexBounds(LAYERS[name].source, LAYERS[name].key, geometry[name]);
    }
    cityBounds = geometryBounds(geometry.council);
    const bounds = cityBounds;
    if (bounds) {
      map.fitBounds(bounds, { padding: 24, animate: false });
      // Order matters. fitBounds first, so the zoom it lands on is "the whole city at this
      // viewport"; that becomes the floor. Then the pan box, which MapLibre re-checks against
      // the current zoom, so it has to come after.
      // The pan box is the *visible* extent at this zoom, not the geometry's bounds: those
      // are narrower than a laptop viewport, and MapLibre only constrains the centre, so the
      // leftover slack let the city be dragged up and down at full zoom out.
      //
      // Order is load-bearing and was wrong once. `setMaxBounds` re-constrains and can nudge
      // the zoom, so reading the zoom before it settles leaves a step of slack — the view
      // drifted once and then locked. Set the box, let it settle, then take the zoom that
      // results as the floor.
      map.setMaxBounds(map.getBounds());
      map.once('idle', () => {
        map.setMaxBounds(map.getBounds());
        map.setMinZoom(map.getZoom());
        lockPanAtMinZoom(map);
      });
    }

    view = new View(map, panel);
    view.show('council');
    bindToggle(view);
    // The panel owns its own close button; this is what the dismissal has to mean here.
    // `deselect` and not `clear`, because `Panel.close` runs this before it marks itself
    // hidden, and a handler that closed the panel again would never stop.
    if (panel) panel.onClose = () => view.deselect();
    revealZoom();
    bindSelection(view);
    bindAddress(view);
    // Last: the zoom buttons have just entered the tab order, and address.js revealed the
    // search box long before this.
    declareReady();
  }
}

function addFillLayer(map, layer, data, beforeId) {
  // promoteId is what makes setFeatureState addressable: these features carry no id of
  // their own, only the one key property.
  map.addSource(layer.source, { type: 'geojson', data, promoteId: layer.key });
  map.addLayer({
    id: `${layer.source}-fill`,
    type: 'fill',
    source: layer.source,
    layout: { visibility: 'none' },
    paint: {
      // Three states, most specific first: a selected polygon stays selected while the
      // pointer is over it, so hovering cannot hide what was chosen.
      'fill-color': [
        'case',
        ['boolean', ['feature-state', 'selected'], false],
        SELECTED,
        ['boolean', ['feature-state', 'hovered'], false],
        HOVERED,
        FILL,
      ],
      // Almost transparent at rest: a district is read by its boundary, not its tint. All
      // three states fade as the reader zooms in. `['zoom']` MUST stay the top level of
      // the expression — nested, MapLibre discards the whole style silently
      // (docs/design.md §4, docs/OBSERVATIONS.md 2026-10-27).
      //
      // The selected value rose from 0.55 to 0.72 on 2026-11-04, when the basemap became
      // liberty. A selection tint is read against the land under it, and liberty's land is
      // near-white where the old palette's was olive — the same 0.55 that was emphatic on
      // olive is a wash on beige. The painted-pixels gate measured it: 80,931 pixels
      // against a floor of 150,000.
      'fill-opacity': [
        'interpolate',
        ['linear'],
        ['zoom'],
        12,
        [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.72,
          ['boolean', ['feature-state', 'hovered'], false],
          0.45,
          0.16,
        ],
        MAX_ZOOM,
        [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.22,
          ['boolean', ['feature-state', 'hovered'], false],
          0.16,
          0.05,
        ],
      ],
    },
  }, beforeId);
}

//: The boundary's colour and weight per basemap.
//:
//: A boundary is read against whatever the basemap draws under it, and that is a different
//: thing on each of the three: liberty's land is near-white, Esri's imagery is dark and
//: mottled, and OpenTopoMap is busy at every value. The navy hairline that reads on the
//: first disappears into the other two — switching basemap left the districts with no
//: visible edge, which is the whole of how a district is read here (owner's report,
//: 2026-11-06).
//:
//: A basemap with no entry falls back to `simple`'s, which is a readable default on a light
//: style rather than a guess about an unknown one.
const BOUNDARY = {
  simple: { color: LINE, width: 1.1 },
  //: White over imagery, and wider: a hairline is lost in the texture at any colour.
  satellite: { color: '#ffffff', width: 1.9 },
  //: Near-black over topography, whose own palette is light greens, yellows and white.
  geography: { color: '#111111', width: 1.9 },
};

/** The boundary, above everything the basemap draws.
 *
 * Separate from the fill because the two want opposite ends of the stack: the fill has to
 * sit under the water mask, and under the water mask the boundary was also under the roads
 * and building footprints, which made it read as broken.
 */
function addLineLayer(map, layer, beforeId, basemap) {
  const edge = BOUNDARY[basemap] || BOUNDARY.simple;
  map.addLayer(
    {
      id: `${layer.source}-line`,
      type: 'line',
      source: layer.source,
      layout: { visibility: 'none' },
      paint: { 'line-color': edge.color, 'line-width': edge.width },
    },
    beforeId
  );
}

/** Which layer is showing, and which feature in it is selected. */
class View {
  constructor(map, panel) {
    this.map = map;
    this.panel = panel;
    this.name = 'council';
    this.selected = null;
    this.many = null;
  }

  get layer() {
    return LAYERS[this.name];
  }

  show(name) {
    if (!LAYERS[name]) return;
    this.clear({ recenter: false });
    this.name = name;
    this.repaint();
    say(`Showing ${this.layer.noun}s. Select one to open its page.`);
  }

  /** Put back everything that lives on the style rather than on this object.
   *
   * Layer visibility and feature state are both properties of a loaded style, so a basemap
   * change takes them with it. Called from `show`, where it is the whole job, and from
   * `draw`, where it is the repair.
   */
  repaint() {
    for (const other of Object.keys(LAYERS)) {
      const visibility = other === this.name ? 'visible' : 'none';
      this.map.setLayoutProperty(`${LAYERS[other].source}-fill`, 'visibility', visibility);
      this.map.setLayoutProperty(`${LAYERS[other].source}-line`, 'visibility', visibility);
    }
    for (const id of this.many || []) {
      this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    }
    if (this.selected !== null) {
      this.map.setFeatureState(
        { source: this.layer.source, id: this.selected },
        { selected: true }
      );
    }
  }

  /** Drop the selection.
   *
   * `recenter` is the difference between dismissing the panel and replacing its contents.
   * `select` and `selectMany` clear first, and returning to the city view on the way
   * produced a zoom out and back in on every click from one district to the next.
   */
  clear({ recenter = true } = {}) {
    this.deselect({ recenter });
    if (this.panel) this.panel.close();
  }

  /** Drop the selection without touching the panel.
   *
   * Split from `clear` because the panel's own close button arrives here through
   * `Panel.onClose`, which runs inside `Panel.close`: closing it again from there would
   * recurse. Whoever opened the panel closes it; this undoes the map.
   */
  deselect({ recenter = true } = {}) {
    const wasShowing = Boolean(this.panel && this.panel.isOpen);
    for (const id of this.many || []) {
      this.map.setFeatureState({ source: this.layer.source, id }, { selected: false });
    }
    this.many = null;
    hideZipOutline(this.map);
    // The pin answers "where is this address". Selecting anything else, or looking up a
    // ZIP, makes it a leftover pointing at a previous question, so it goes with the rest
    // of the selection. The address path re-drops it *after* selecting, for that reason.
    removePin();
    if (this.selected !== null) {
      this.map.setFeatureState(
        { source: this.layer.source, id: this.selected },
        { selected: false }
      );
    }
    this.selected = null;
    document.body.classList.remove('has-selection');
    // Only on a real dismissal, and only if something was up. Replacing one selection with
    // another keeps the frame.
    if (wasShowing) refit(this.map, { move: recenter });
  }

  /** Open the panel on this selection, and tell the page a sheet is up.
   *
   * `has-selection` is read by `map.css`, which takes the control cards away underneath a
   * phone's bottom sheet: compacting them still left only 124 px of map between the two.
   */
  showPanel(title, body, foot) {
    if (!this.panel) return;
    document.body.classList.add('has-selection');
    this.panel.open(title, body, foot);
  }

  /** Several features at once, with a card that names what they have in common. */
  selectMany(ids, title) {
    this.clear({ recenter: false });
    if (!ids.length) {
      say(`${title} does not resolve to a ${this.layer.noun} in this dataset.`);
      return;
    }
    this.many = ids;
    for (const id of ids) {
      this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    }
    // Whichever layer is showing: a ZIP resolves against both, so switching layers with a
    // ZIP on screen answers the same question about the other geography.
    const plural = `${this.layer.noun}s`;
    this.showPanel(
      title,
      group(`Covering this ZIP`, {
        caption: `${ids.length} ${ids.length === 1 ? this.layer.noun : plural}`,
        columns: [this.name === 'council' ? 'District' : 'Board'],
        rows: ids.map((id) => [[this.layer.label(id), this.layer.href(id)]]),
      }),
      panelFoot(
        'Select one on the map for its details',
        this.name === 'council' ? '/district/' : '/board/'
      )
    );
    refit(this.map);
    // Frame everything highlighted, in the part of the map the panel leaves visible.
    frameBounds(this.map, unionBounds(this.layer.source, ids));
    say(`${title} covers ${ids.length} ${ids.length === 1 ? this.layer.noun : plural}, all highlighted.`);
  }

  select(id) {
    this.clear({ recenter: false });
    this.selected = id;
    this.map.setFeatureState({ source: this.layer.source, id }, { selected: true });
    this.fillCard(id);
    say(`${this.layer.label(id)} selected.`);
  }

  /** The detail panel: headline facts for whatever was selected, then a link onward. */
  fillCard(id) {
    // Built with DOM calls and textContent, never innerHTML: these values are ours, but the
    // rule in CLAUDE.md is that nothing reaches the page as markup.
    const sections = [];
    for (const [heading, rows, headingHref] of this.layer.sections(id)) {
      if (!rowCount(rows)) continue;
      sections.push(group(heading, rows, headingHref));
    }
    this.showPanel(
      this.layer.label(id),
      sections,
      panelFoot(
        `Full page for ${this.layer.label(id)}`,
        this.layer.href(id),
        // Stated once for the panel rather than per field; the page carries the per-fact
        // provenance, which is what the link above is for.
        preview && preview.as_of
          ? `Summary of ${this.layer.href(id)}, built ${formatAsOf(preview.as_of)}.`
          : null
      )
    );
    // The panel docks over the canvas rather than beside it, so the container never changes
    // size and there is no `resize` to do. The camera floor still gets recomputed: the fit
    // has to account for the part of the frame the panel is covering.
    refit(this.map);
    // Pan, never zoom. Owner's decision, 2026-10-28: selecting a district is navigation,
    // and re-fitting to each polygon kept taking away the zoom the reader had chosen.
    // Searching still zooms, because a search is a question about one place.
    panIntoView(this.map, featureCentres[this.layer.source].get(String(id)));
  }
}

/** One board's share of a district: the figure, and a bar beneath it.
 *
 * Bars, not a stacked bar: the shares are measured per board and do not sum to 100 (44 + 29
 * + 23 for district 35), so one stacked bar would imply a complete partition it does not
 * make. One series, so no legend: the row header names each bar.
 *
 * Width is an SVG geometry attribute, not CSS: `style-src 'self'` refuses a style attribute,
 * which rules out the usual `style="width:44%"`. Square ends rather than the 4px rounded
 * ones, because `preserveAspectRatio="none"` is what lets the bar stretch to the column and
 * it would distort a corner radius.
 */
function shareCell(label, percent) {
  const cell = document.createDocumentFragment();

  const value = document.createElement('span');
  value.className = 'share-value';
  value.textContent = label;

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'share-bar');
  svg.setAttribute('viewBox', '0 0 100 8');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${label} of the total`);
  for (const [cls, width] of [['share-track', 100], ['share-fill', percent]]) {
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('class', cls);
    rect.setAttribute('x', '0');
    rect.setAttribute('y', '0');
    rect.setAttribute('width', String(width));
    rect.setAttribute('height', '8');
    svg.append(rect);
  }
  cell.append(value, svg);
  return cell;
}

/** Whether a group's content is a table spec rather than a list of lines. */
function isTable(rows) {
  return Boolean(rows) && !Array.isArray(rows) && Array.isArray(rows.columns);
}

/** How many rows a group holds, whichever shape it is. An empty group is not rendered. */
function rowCount(rows) {
  return isTable(rows) ? rows.rows.length : rows.length;
}

/** A cell's content, in the shapes `render.py` emits plus the two the panel builds itself.
 *
 * A plain string; `{text, href}` for a link; `{text, share}` for a share figure and its
 * bar; `[text, href]`; or a Node. The object forms are what travel in `preview.json`, so
 * this function and the `cell` macro in `macros.html` are the two renderers of one shape.
 */
function fillCell(target, value) {
  if (value instanceof Node) {
    target.append(value);
    return;
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    if (value.share !== undefined && value.share !== null) {
      target.append(shareCell(value.text, value.share));
      return;
    }
    fillCell(target, value.href ? [value.text, value.href] : value.text);
    return;
  }
  const [text, href] = Array.isArray(value) ? value : [value, null];
  if (!href) {
    target.textContent = text == null ? '' : String(text);
    return;
  }
  const a = document.createElement('a');
  a.textContent = text;
  a.href = href;
  if (href.startsWith('http')) {
    // Same rule as the rest of the site: an off-site link carries no referrer.
    a.rel = 'noopener noreferrer';
  }
  target.append(a);
}


/** A group's content as a real table.
 *
 * Owner's choice, 2026-10-27, over three alternatives. The panel used to put a label and
 * its value in one line separated by an em dash, which is punctuation doing structural
 * work: it reads as neither a sentence nor a list. Real `th` elements carry `scope`, so a
 * screen reader announces the column with every cell and the relationship is in the markup
 * rather than in a dash.
 */
function table(spec) {
  const element = document.createElement('table');
  element.className = 'group-table';

  if (spec.caption) {
    const caption = document.createElement('caption');
    caption.textContent = spec.caption;
    element.append(caption);
  }

  const headRow = document.createElement('tr');
  for (const name of spec.columns) {
    const th = document.createElement('th');
    th.setAttribute('scope', 'col');
    th.textContent = name;
    headRow.append(th);
  }
  const head = document.createElement('thead');
  head.append(headRow);

  const body = document.createElement('tbody');
  for (const row of spec.rows) {
    const tr = document.createElement('tr');
    row.forEach((value, index) => {
      // The first column names its row, so it is a row header and not a plain cell.
      const cell = document.createElement(index === 0 ? 'th' : 'td');
      if (index === 0) {
        cell.setAttribute('scope', 'row');
      } else {
        // Narrow viewports hide the header row and collapse each row to a block, so the
        // column name travels with the cell for the stylesheet to print back.
        cell.dataset.label = spec.columns[index];
      }
      fillCell(cell, value);
      tr.append(cell);
    });
    body.append(tr);
  }

  element.append(head, body);
  return element;
}

/** One labelled group in the panel, as a fieldset: the era-appropriate group box.
 *
 * Content is either a list of lines — each a string, `[text, href]`, or a Node — or a table
 * spec `{ caption, columns, rows }`. Bulleted lists read as a dump; a titled group reads as
 * a record, which is what this is.
 */
function group(heading, rows, headingHref) {
  const box = document.createElement('fieldset');
  box.className = 'group';
  const legend = document.createElement('legend');
  if (headingHref) {
    const a = document.createElement('a');
    a.textContent = heading;
    a.href = headingHref;
    legend.append(a);
  } else {
    legend.textContent = heading;
  }
  box.append(legend);

  if (isTable(rows)) {
    box.append(table(rows));
    return box;
  }

  // A single value per line, for a group that is not tabular: one neighbourhood list, one
  // member, one cadence. Giving these a header row would invent columns they do not have.
  for (const row of rows) {
    const line = document.createElement('p');
    line.className = 'group-line';
    fillCell(line, row);
    box.append(line);
  }
  return box;
}

function formatAsOf(iso) {
  const when = new Date(iso);
  return Number.isNaN(when.getTime()) ? iso : when.toLocaleDateString();
}

/** The panel's foot: the link onward, and the provenance line under it.
 *
 * `Panel.open` takes one node for the foot, so these two arrive as a fragment. The link
 * carries the class the stylesheet pins to the bottom of the panel — it is the one thing the
 * panel exists to offer, and a long committee list otherwise pushes it below the fold.
 */
function panelFoot(text, href, asOf = null) {
  const foot = document.createDocumentFragment();
  const link = document.createElement('a');
  link.className = 'map-selection';
  link.textContent = text;
  link.href = href;
  foot.append(link);
  if (asOf) {
    const line = document.createElement('p');
    line.className = 'detail-asof';
    line.textContent = asOf;
    foot.append(line);
  }
  return foot;
}

function bindToggle(view) {
  if (!toggle) return;
  const buttons = [...toggle.querySelectorAll('[data-layer]')];
  for (const button of buttons) {
    button.addEventListener('click', () => {
      for (const other of buttons) other.setAttribute('aria-pressed', String(other === button));
      view.show(button.dataset.layer);
    });
  }
  toggle.hidden = false;
}

//: The pin dropped on a geocoded address. One marker, moved rather than recreated, so a
//: second lookup does not litter the map.
let pin = null;

//: The pin, as a path whose tip is the last point: `PIN_H` is chosen so the tip sits on
//: the bottom edge of the box, which is what lets `anchor: 'bottom'` put it exactly on the
//: coordinate with no offset to get wrong.
//:
//: It is drawn as SVG and not as a rotated div because **MapLibre writes its own
//: `transform` onto the marker element**, which silently overrode the `rotate(-45deg)` the
//: teardrop used to depend on: the shape rendered unrotated, so its sharp corner pointed
//: down and to the left and readers took that corner for the address (owner's report,
//: 2026-10-29). Nothing in CSS can win that fight — the shape has to carry its own
//: geometry.
const PIN_W = 20;
const PIN_H = 27;
const PIN_PATH = 'M10 27C10 27 18 16 18 10A8 8 0 1 0 2 10C2 16 10 27 10 27Z';

/** Take the pin away. Anything that is not "this address" invalidates it. */
function removePin() {
  if (!pin) return;
  pin.remove();
  pin = null;
}

function dropPin(map, MapLibre, lon, lat) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return;
  if (pin) {
    pin.setLngLat([lon, lat]);
    return;
  }
  // MapLibre's default marker is an inline-styled SVG, which `style-src 'self'` would
  // refuse. Ours carries no style attribute: the colours are a class in site.css and the
  // shape is geometry attributes, the same division the share bars use.
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'map-pin');
  svg.setAttribute('width', String(PIN_W));
  svg.setAttribute('height', String(PIN_H));
  svg.setAttribute('viewBox', `0 0 ${PIN_W} ${PIN_H}`);
  svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', PIN_PATH);
  svg.append(path);

  // `bottom`, so the point of the pin is the thing placed on the coordinate.
  pin = new MapLibre.Marker({ element: svg, anchor: 'bottom' })
    .setLngLat([lon, lat])
    .addTo(map);
}

/** Recompute the zoom floor and pan box for the current frame, leaving the camera be.
 *
 * Deriving them means briefly standing at the city fit, so the camera is saved and put
 * back in the same JavaScript turn; only the final camera is ever drawn. Without that,
 * every selection snapped out to the whole city first. `move: true` is for the one caller
 * that does want the city view. docs/design.md §4.
 */
function refit(map, { move = false } = {}) {
  if (!cityBounds) return;
  const before = { center: map.getCenter(), zoom: map.getZoom() };

  map.setMinZoom(0);
  map.setMaxBounds(null);
  map.fitBounds(cityBounds, { padding: viewPadding(map), animate: false });
  const box = map.getBounds();
  const floor = map.getZoom();

  if (!move) map.jumpTo(before);
  map.setMaxBounds(box);
  map.setMinZoom(floor);
  lockPanAtMinZoom(map);
}

/** Drag is off at full zoom out, and on as soon as the reader zooms in.
 *
 * `maxBounds` alone was not enough: MapLibre constrains the *centre*, and its tolerance left
 * one step of movement before pinning — the whole city slid up or down once on a laptop,
 * which is the thing being complained about. Disabling the handler is deterministic, and it
 * is honest about the state: at full zoom out the city is already entirely in frame, so there
 * is nowhere to pan to.
 */
let panLockBound = false;

function lockPanAtMinZoom(map) {
  const apply = () => {
    // A hair of tolerance, because zoom is a float and minZoom is whatever fitBounds left.
    if (map.getZoom() <= map.getMinZoom() + 0.01) {
      map.dragPan.disable();
    } else {
      map.dragPan.enable();
    }
  };
  // Bound once. `refit` runs on every open and close, and a fresh handler each time piled
  // up listeners that all did the same work. The bound one reads the zoom live, so it
  // stays correct as the floor changes.
  if (!panLockBound) {
    map.on('zoomend', apply);
    panLockBound = true;
  }
  apply();
}

/** Reveal the zoom control, which is hidden until the map exists to drive.
 *
 * The base map binds `#map-zoom-in` and `#map-zoom-out` itself. Binding them here as well
 * put two click listeners on each button, so one press zoomed two steps.
 */
function revealZoom() {
  const group = document.getElementById('map-zoom');
  if (group) group.hidden = false;
}

function bindSelection(view) {
  for (const name of Object.keys(LAYERS)) {
    const layer = LAYERS[name];
    const fill = `${layer.source}-fill`;
    let hovered = null;

    const setHover = (id) => {
      if (hovered === id) return;
      if (hovered !== null) {
        view.map.setFeatureState({ source: layer.source, id: hovered }, { hovered: false });
      }
      hovered = id;
      if (id !== null) {
        view.map.setFeatureState({ source: layer.source, id }, { hovered: true });
      }
    };

    view.map.on('mousemove', fill, (event) => {
      view.map.getCanvas().style.cursor = 'pointer';
      const feature = event.features && event.features[0];
      if (feature) setHover(feature.id ?? feature.properties[layer.key]);
    });
    view.map.on('mouseleave', fill, () => {
      view.map.getCanvas().style.cursor = '';
      setHover(null);
    });
    view.map.on('click', fill, (event) => {
      const feature = event.features && event.features[0];
      if (!feature) return;
      const id = feature.id ?? feature.properties[layer.key];
      if (id !== undefined && id !== null) view.select(String(id));
    });
  }
}

/** The address box dispatches; claiming the event is what stops the page navigating. */
function bindAddress(view) {
  document.addEventListener('showup:located', (event) => {
    const detail = event.detail || {};
    event.preventDefault();

    // The pin marks the address itself; the highlight marks what contains it. Dropped
    // after the selection in each branch below, because selecting clears the old pin.
    const pinHere = () => {
      if (library) dropPin(view.map, library, detail.lon, detail.lat);
    };

    // A ZIP covering several districts: highlight every one rather than making the reader
    // pick before they can see where any of them is.
    if (detail.zip && Array.isArray(detail.districts)) {
      const ids = view.name === 'council' ? detail.districts : detail.boards || [];
      view.selectMany(ids.map(String), `ZIP ${detail.zip}`);
      // After the selection, so a slow or missing overlay cannot delay the answer. Once
      // the outline is there the camera frames the ZIP rather than the union of whatever
      // covers it: the ZIP is what was typed, and the covering areas are listed in the
      // panel whether or not they fit in the frame.
      showZipOutline(view.map, detail.zcta || detail.zip).then((box) => {
        if (box) frameBounds(view.map, box);
      });
      return;
    }

    // A board picked from the suggestion list: show the layer it lives on, then select it.
    if (detail.board) {
      if (view.name !== 'board') view.show('board');
      view.select(String(detail.board));
      pinHere();
      return;
    }

    if (view.name === 'council' && detail.district) {
      view.select(String(detail.district));
      pinHere();
      panTo(view, detail);
      return;
    }

    const hit = featureAt(view, detail);
    if (hit !== null) {
      view.select(String(hit));
      pinHere();
      panTo(view, detail);
      return;
    }

    // A board cannot be derived from a district number: a district overlaps two or three
    // boards, so picking one would be a guess.
    say(
      view.name === 'board'
        ? 'That lookup gives a council district, and a district covers more than one board. ' +
            'Select a board on the map, or use the list below.'
        : 'Located, but the map could not place it.'
    );
  });
}

function featureAt(view, detail) {
  if (!Number.isFinite(detail.lon) || !Number.isFinite(detail.lat)) return null;
  const hits = view.map.queryRenderedFeatures(view.map.project([detail.lon, detail.lat]), {
    layers: [`${view.layer.source}-fill`],
  });
  const feature = hits && hits[0];
  if (!feature) return null;
  return feature.id ?? feature.properties[view.layer.key] ?? null;
}

/** Go to a geocoded address: street level, centred in the visible frame, pin showing.
 *
 * Zoom 12 used to leave the pin as a dot on a borough-wide view, which is not a located
 * address. `padding` is what keeps the point out from behind the panel — `easeTo` centres
 * on the container otherwise, and the panel covers the right 400 px of it.
 */
function panTo(view, detail) {
  if (!Number.isFinite(detail.lon) || !Number.isFinite(detail.lat)) return;
  view.map.easeTo({
    center: [detail.lon, detail.lat],
    // Never zoom *out* to reach the address: if the reader is already closer in than
    // street level, that is the zoom they chose.
    zoom: Math.min(Math.max(view.map.getZoom(), ADDRESS_ZOOM), MAX_ZOOM),
    padding: viewPadding(view.map),
    duration: CAMERA_MS,
  });
}

/** The centroid of one ring, by the shoelace formula, with its signed area. */
function ringCentroid(ring) {
  let twiceArea = 0;
  let x = 0;
  let y = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const cross = ring[j][0] * ring[i][1] - ring[i][0] * ring[j][1];
    twiceArea += cross;
    x += (ring[j][0] + ring[i][0]) * cross;
    y += (ring[j][1] + ring[i][1]) * cross;
  }
  if (!twiceArea) return null;
  return { point: [x / (3 * twiceArea), y / (3 * twiceArea)], area: Math.abs(twiceArea / 2) };
}

/** Every ring in a geometry, outer and inner alike. */
function ringsOf(geometry) {
  const rings = [];
  const visit = (coordinates) => {
    if (!Array.isArray(coordinates) || !coordinates.length) return;
    if (Array.isArray(coordinates[0]) && typeof coordinates[0][0] === 'number') {
      rings.push(coordinates);
      return;
    }
    for (const part of coordinates) visit(part);
  };
  visit((geometry && geometry.coordinates) || []);
  return rings;
}

/** A point to centre on: the largest ring's centroid.
 *
 * The largest ring, not all of them averaged: a district with an island would otherwise
 * centre on the water between the two.
 */
function representativePoint(feature) {
  let best = null;
  for (const ring of ringsOf(feature.geometry)) {
    const centroid = ringCentroid(ring);
    if (centroid && (!best || centroid.area > best.area)) best = centroid;
  }
  return best && best.point;
}

/** One bounding box and one centre per feature, keyed by the property `promoteId` uses. */
function indexBounds(source, key, collection) {
  for (const feature of (collection && collection.features) || []) {
    const id = feature.properties && feature.properties[key];
    if (id === undefined || id === null) continue;
    const box = geometryBounds({ features: [feature] });
    if (box) featureBounds[source].set(String(id), box);
    const centre = representativePoint(feature);
    if (centre) featureCentres[source].set(String(id), centre);
  }
}

/** The union of several features' boxes, for a ZIP that straddles districts. */
function unionBounds(source, ids) {
  const boxes = ids.map((id) => featureBounds[source].get(String(id))).filter(Boolean);
  if (!boxes.length) return null;
  return boxes.reduce((a, b) => [
    [Math.min(a[0][0], b[0][0]), Math.min(a[0][1], b[0][1])],
    [Math.max(a[1][0], b[1][0]), Math.max(a[1][1], b[1][1])],
  ]);
}

// The panel's reveal, slide and deferred `hidden` are the base map's `Panel`, which this
// page now uses rather than keeping a second copy of the same two-frame dance.

//: The searched ZIP's own outline, fetched on the first ZIP lookup and never before:
//: 51 KB gzipped against the 145 KB the rest of the map's data costs. Nothing is
//: hit-tested against it, so it is simplified far more coarsely than the districts
//: (docs/OBSERVATIONS.md, 2026-10-28).
const ZIP_SOURCE = 'zip-outline';
const ZIP_URL = '/data/zips.geo.json';
let zipGeometry = null;
let zipPending = null;

/** Draw the dashed boundary of one modified ZCTA, or quietly draw nothing.
 *
 * The outline is a hint on top of an answer the panel has already given, so every failure
 * here is swallowed: a ZIP lookup must not break because an overlay could not be fetched.
 */
async function showZipOutline(map, zcta) {
  if (!zcta) return null;
  if (!zipGeometry) {
    if (!zipPending) zipPending = fetchJson(ZIP_URL).catch(() => null);
    zipGeometry = await zipPending;
  }
  if (!zipGeometry) return null;

  const feature = (zipGeometry.features || []).find(
    (candidate) => String((candidate.properties || {}).modzcta) === String(zcta)
  );
  if (!feature) return null;

  const data = { type: 'FeatureCollection', features: [feature] };
  if (map.getSource(ZIP_SOURCE)) {
    map.getSource(ZIP_SOURCE).setData(data);
  } else {
    map.addSource(ZIP_SOURCE, { type: 'geojson', data });
    map.addLayer({
      id: `${ZIP_SOURCE}-line`,
      type: 'line',
      source: ZIP_SOURCE,
      paint: {
        // Dashed, and a different colour from a district boundary, because it is a
        // different kind of line: the ZIP is what was asked about, not what was found.
        'line-color': '#2a2a2a',
        'line-width': 2,
        'line-dasharray': [2, 2],
      },
    });
  }
  map.setLayoutProperty(`${ZIP_SOURCE}-line`, 'visibility', 'visible');
  return geometryBounds({ features: [feature] });
}

/** Take the ZIP outline away: the next lookup is a different question. */
function hideZipOutline(map) {
  if (map.getLayer(`${ZIP_SOURCE}-line`)) {
    map.setLayoutProperty(`${ZIP_SOURCE}-line`, 'visibility', 'none');
  }
}

/** Camera padding that accounts for the detail panel.
 *
 * The panel is `position: absolute` *over* the map, so the container's width never changes
 * when it opens and MapLibre keeps centring on the full frame. Measured, not assumed.
 */
function viewPadding(map) {
  const edge = 24;
  const flat = { top: edge, bottom: edge, left: edge, right: edge };
  const card = document.getElementById('detail');
  if (!card || card.hidden) return flat;

  const mapBox = map.getContainer().getBoundingClientRect();
  if (!mapBox.width) return flat;

  // `offsetWidth`/`offsetHeight`, not a client rect: the panel is mid-slide for 220 ms
  // after it opens and a rect includes the transform, which would make the camera padding
  // animate along with it. Docked-vs-stacked is the stylesheet's own breakpoint, for the
  // same reason.
  const docked = window.matchMedia('(min-width: 52rem)').matches;

  if (docked) {
    const overlap = card.offsetWidth;
    if (overlap < 40) return flat;
    // Never give away more than half the frame: past that the fit zooms out so far that
    // the city is smaller than it was before the panel opened.
    return { ...flat, right: Math.min(overlap + edge, mapBox.width * 0.5) };
  }

  // Stacked under the map on a phone, where it steals height rather than width. Returning
  // flat padding here centred the selection on the container's middle, which at 390x780
  // is within a pixel of the sheet's top edge — so the district the reader had just asked
  // for was behind the sheet (measured 2026-10-31).
  const covered = card.offsetHeight;
  if (covered < 40) return flat;
  return { ...flat, bottom: Math.min(covered + edge, mapBox.height * 0.6) };
}

/** Centre a point in the part of the map the panel leaves visible, without changing zoom.
 *
 * Done in pixels at the current zoom, with the camera's padding explicitly zeroed for the
 * move, because MapLibre's `padding` is **persistent camera state** that `refit` has
 * already set through `fitBounds`. Two earlier attempts got this wrong in opposite
 * directions and both pushed the district left (owner's reports, 2026-10-30):
 *
 * - `cameraForBounds(box, { padding }).center` eased to at the *current* zoom: that centre
 *   carries the padding as a geographic shift sized for whatever zoom `cameraForBounds`
 *   picked, so at any other zoom it is the wrong number of pixels.
 * The zeroed padding below is defensive, not load-bearing: isolating it on 2026-10-31
 * showed removing it changes the measured result by nothing at all. The second fault was
 * the bounding box, not the padding — see the correction in docs/OBSERVATIONS.md.
 */
function panIntoView(map, point) {
  if (!point) return;
  const padding = viewPadding(map);
  const frame = map.getContainer().getBoundingClientRect();
  if (!frame.width || !frame.height) return;

  // The middle of what the reader can actually see, in container pixels.
  const targetX = (padding.left + (frame.width - padding.right)) / 2;
  const targetY = (padding.top + (frame.height - padding.bottom)) / 2;

  const at = map.project(point);
  const centre = map.project(map.getCenter());
  map.easeTo({
    center: map.unproject([centre.x + (at.x - targetX), centre.y + (at.y - targetY)]),
    padding: { top: 0, right: 0, bottom: 0, left: 0 },
    duration: CAMERA_MS,
  });
}

/** Frame a box in whatever part of the map the panel is not covering. */
function frameBounds(map, box) {
  if (!box) return;
  map.fitBounds(box, {
    padding: viewPadding(map),
    maxZoom: FRAME_MAX_ZOOM,
    duration: CAMERA_MS,
  });
}

/** The data's own bounding box, so the city fills the frame at any container size. */
function geometryBounds(geometry) {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  const visit = (coordinates) => {
    if (typeof coordinates[0] === 'number') {
      const [longitude, latitude] = coordinates;
      if (longitude < west) west = longitude;
      if (longitude > east) east = longitude;
      if (latitude < south) south = latitude;
      if (latitude > north) north = latitude;
      return;
    }
    for (const part of coordinates) visit(part);
  };

  for (const feature of geometry.features || []) {
    if (feature.geometry && feature.geometry.coordinates) visit(feature.geometry.coordinates);
  }
  return Number.isFinite(west)
    ? [
        [west, south],
        [east, north],
      ]
    : null;
}

main();
